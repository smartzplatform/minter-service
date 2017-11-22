#!/usr/bin/env python3

import sys
import os
import json
import re
import logging
from functools import lru_cache

import yaml
from web3 import Web3, HTTPProvider, IPCProvider
from flask import Flask, abort, request

import redis
import redis.exceptions


class ConfigurationBase(object):

    def __init__(self, filename, uses_web3=True):
        self.filename = filename
        self._uses_web3 = uses_web3

        with open(filename) as fh:
            self._conf = yaml.safe_load(fh)

        if self._uses_web3 and self._conf['web3_provider']['class'] not in ('HTTPProvider', 'IPCProvider'):
            raise TypeError('bad web3 provider')

    def __getitem__(self, key):
        return self._conf[key]

    def __contains__(self, item):
        return item in self._conf

    def get(self, key, default):
        return self._conf.get(key, default)

    def get_provider(self):
        if not self._uses_web3:
            raise RuntimeError('web3 is not being used')
        return globals()[self._conf['web3_provider']['class']](*(self._conf['web3_provider']['args']))

    def _check_existence(self, names):
        for name in names if isinstance(names, (list, tuple)) else (names, ):
            if self._conf.get(name) is None:
                raise ValueError(name + ' is not provided')

    def _check_addresses(self, addresses):
        self._check_existence(addresses)
        for address_name in addresses if isinstance(addresses, (list, tuple)) else (addresses, ):
            if not Web3.isAddress(self._conf[address_name]):
                raise ValueError(address_name + ' is incorrect')

    def _check_ints(self, names):
        self._check_existence(names)
        for name in names if isinstance(names, (list, tuple)) else (names, ):
            try:
                int(self._conf[name])
            except ValueError:
                raise ValueError(name + ' is not an integer')


class Conf(ConfigurationBase):

    def __init__(self):
        super().__init__(os.path.join(os.path.dirname(__file__), '..', 'conf', 'minter.conf'))

        self._check_addresses(('reenterable_minter_address', 'account_address'))

        if 'require_confirmations' in self:
            self._check_ints('require_confirmations')

        if 'gas_limit' in self:
            self._check_ints('gas_limit')

        # TODO validate redis

    def get_redis(self):
        return redis.StrictRedis(
                host=self.get('redis', {}).get('host', '127.0.0.1'),
                port=self.get('redis', {}).get('port', 6379),
                db=self.get('redis', {}).get('db', 0))


logging.basicConfig(level=logging.DEBUG)

conf = Conf()
w3_instance = Web3(conf.get_provider())
redis_instance = conf.get_redis()

app = Flask(__name__)


@app.route('/mintTokens')
def mint_tokens():
    mint_id = _get_mint_id()
    address = _get_address()
    tokens = _get_tokens()

    gas_price = w3_instance.eth.gasPrice
    gas_limit = _gas_limit()

    tx_hash = _target_contract()\
        .transact({'from': conf['account_address'], 'gasPrice': gas_price, 'gas': gas_limit})\
        .mint(mint_id, address, tokens)

    # remembering tx hash for get_minting_status references - optional step
    _silent_redis_call(redis_instance.lpush, _redis_mint_tx_key(mint_id), Web3.toBytes(hexstr=tx_hash))

    logging.debug('mint_tokens(): mint_id=%s, address=%s, tokens=%d, gas_price=%d, gas=%d: sent tx %s',
                  Web3.toHex(mint_id), address, tokens, gas_price, gas_limit, tx_hash)
    return '{"success": true}'


@app.route('/getMintingStatus')
def get_minting_status():
    mint_id = _get_mint_id()

    # Checking if it was mined enough block ago.
    if 'require_confirmations' in conf:
        confirmed_block = w3_instance.eth.blockNumber - int(conf['require_confirmations'])
        if confirmed_block < 0:
            # we are at the beginning of blockchain for some reason
            return '{"status": "minting"}'

        saved_default = w3_instance.eth.defaultBlock
        w3_instance.eth.defaultBlock = confirmed_block
    else:
        saved_default = None

    try:
        if _target_contract().call().m_processed_mint_id(mint_id):
            # TODO background eviction thread/process
            _silent_redis_call(redis_instance.delete, _redis_mint_tx_key(mint_id))

            return '{"status": "minted"}'
    finally:
        if 'require_confirmations' in conf:
            assert saved_default is not None
            w3_instance.eth.defaultBlock = saved_default

    # Checking if it was mined recently (still subject to removal from blockchain!).
    if _target_contract().call().m_processed_mint_id(mint_id):
        return '{"status": "minting"}'

    # finding all known transaction ids which could mint this mint_id
    tx_bin_ids = _silent_redis_call(redis_instance.lrange, _redis_mint_tx_key(mint_id), 0, -1) or []

    # getting transactions
    txs = filter(None, (w3_instance.eth.getTransaction(Web3.toHex(tx_id)) for tx_id in tx_bin_ids))

    # searching for failed transactions
    for tx in txs:
        if tx.blockNumber is None:
            continue    # not mined yet

        receipt = w3_instance.eth.getTransactionReceipt(tx.hash)
        if receipt is None:
            continue    # blockchain reorg?

        if 0 == int(receipt.status, 16):
            # If any of the transactions has failed, it's a very bad sign
            # (failure due to reentrance should't be possible, see ReenterableMinter).
            return '{"status": "failed"}'

    if txs:
        # There is still hope.
        return '{"status": "minting"}'
    else:
        # Last chance - maybe we're out of sync?
        if w3_instance.eth.syncing:
            return '{"status": "node_syncing"}'

        # There are no signs of minting - now its vise for client to re-mint this mint_id.
        return '{"status": "not_minted"}'


def _get_mint_id():
    """
    Extracts mint id from current request parameters.
    :return: mint id (bytes)
    """
    mint_id = request.args['mint_id']
    if '' == mint_id:
        abort(400, 'empty mint_id')
    return Web3.sha3(text=mint_id, encoding='bytes')


def _get_address():
    return _validate_address(request.args['address'])


def _get_tokens():
    tokens = request.args['tokens_amount']
    try:
        return int(tokens)
    except ValueError:
        abort(400, 'bad tokens_amount')


def _validate_address(address):
    if not Web3.isAddress(address):
        abort(400, 'bad address')
    return address


@lru_cache(128)
def _abi(abi_name):
    with open(os.path.join(os.path.dirname(__file__), '..', 'abi', abi_name + '.json')) as fh:
        return json.load(fh)


@lru_cache(1)
def _target_contract():
    return w3_instance.eth.contract(conf['reenterable_minter_address'], abi=_abi('ReenterableMinter'))


def _gas_limit():
    # Strange behaviour was observed on Rinkeby with web3py 3.16:
    # looks like web3py set default gas limit a bit above typical block gas limit and ultimately the transaction was
    # completely ignored (getTransactionReceipt AND getTransaction returned None, and the tx was absent in
    # eth.pendingTransactions).
    # That's why 90% of the last block gasLimit should be a safe cap (I'd recommend to limit it further in conf file
    # based on specific token case).

    limit = int(w3_instance.eth.getBlock('latest').gasLimit * 0.9)
    return min(int(conf['gas_limit']), limit) if 'gas_limit' in conf else limit


def _redis_mint_tx_key(mint_id):
    """
    Creating unique redis key for current minter contract and mint_id
    :param mint_id: mint id (bytes)
    :return: redis-compatible string
    """
    contract_address_bytes = Web3.toBytes(hexstr=conf['reenterable_minter_address'])
    assert 20 == len(contract_address_bytes)
    return Web3.sha3(contract_address_bytes + mint_id, encoding='bytes')


def _silent_redis_call(call_fn, *args, **kwargs):
    try:
        return call_fn(*args, **kwargs)
    except redis.exceptions.ConnectionError as exc:
        logging.warning('could not contact redis: %s', exc)
        return None


if __name__ == '__main__':
    app.run()
