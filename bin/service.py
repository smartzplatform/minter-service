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


logging.basicConfig(level=logging.DEBUG)

conf = Conf()
web3 = Web3(conf.get_provider())

app = Flask(__name__)


@app.route('/mintTokens')
def mint_tokens():
    mint_id = _get_mint_id()
    address = _get_address()
    tokens = _get_tokens()

    gas_price = web3.eth.gasPrice

    tx_hash = _target_contract()\
        .transact({'from': conf['account_address'], 'gasPrice': gas_price})\
        .mint(Web3.toBytes(hexstr=mint_id), address, tokens)

    logging.debug('mint_tokens(): mint_id=%s, address=%s, tokens=%d, gas_price=%d: sent tx %s',
                  mint_id, address, tokens, gas_price, tx_hash)
    return '{"success": true}'


@app.route('/getMintingStatus')
def get_minting_status():
    mint_id = _get_mint_id()

    # вариант:
    # проверить намайнена ли 6 блоков назад, если да -  успех
    # найти транзакцию, если не нашлась -  не минтится либо node_syncing
    # если failed (но не AlreadyMinted) - failed
    # иначе минтится

    # Checking if it was mined enough block ago.
    if 'require_confirmations' in conf:
        saved_default = web3.eth.defaultBlock
        web3.eth.defaultBlock = max(0, web3.eth.blockNumber - int(conf['require_confirmations']))
    else:
        saved_default = None
    try:
        if _target_contract().call().m_processed_mint_id(Web3.toBytes(hexstr=mint_id)):
            return '{"status": "minted"}'
    finally:
        if 'require_confirmations' in conf:
            assert saved_default is not None
            web3.eth.defaultBlock = saved_default

    # предыдущий вариант

    if _target_contract().call().m_processed_mint_id(Web3.toBytes(hexstr=mint_id)):
        # mined

        форк блокчейна во время этой проверки?
        if 'require_confirmations' in conf:
            # checking if there are enough confirmations
            to_block = web3.eth.blockNumber
            from_block = max(0, to_block - int(conf['require_confirmations']) + 1)

            event_filter = _target_contract().eventFilter('MintSuccess',
                    {'filter': {'mint_id': Web3.toBytes(hexstr=mint_id)}, 'fromBlock': from_block, 'toBlock': to_block})
            try:
                events = event_filter.get_all_entries()
            finally:
                event_filter.stop_watching()

            assert len(events) <= 1
            if events:
                return '{"status": "minting"}'

        return '{"status": "minted"}'

    # иначе ищи в TxPool.content

    # Eth.syncing?

    # status failed?


def _get_mint_id():
    mint_id = request.args['mint_id']
    if '' == mint_id:
        abort(400, 'empty mint_id')
    return Web3.sha3(text=mint_id)


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
    return web3.eth.contract(conf['reenterable_minter_address'], abi=_abi('ReenterableMinter'))


if __name__ == '__main__':
    app.run()
