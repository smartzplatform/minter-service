#!/usr/bin/env python3

import sys
import os
import json
import logging
from functools import lru_cache
import copy
import stat
from time import sleep

import yaml
from web3 import Web3, HTTPProvider, IPCProvider
from flask import Flask, abort, request

import redis
import redis.exceptions

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'lib')))

from mixbytes.filelock import FileLock, WouldBlockError
from mixbytes.conf import ConfigurationBase


class Conf(ConfigurationBase):

    def __init__(self):
        super().__init__(os.path.join(os.path.dirname(__file__), '..', 'conf', 'minter.conf'))
        self._uses_web3 = True

        self._check_dirs('data_directory')

        if 'require_confirmations' in self:
            self._check_ints('require_confirmations')

        if 'gas_limit' in self:
            self._check_ints('gas_limit')

        # TODO validate redis

        if self._uses_web3 and self._conf['web3_provider']['class'] not in ('HTTPProvider', 'IPCProvider'):
            raise TypeError('bad web3 provider')

    def get_provider(self):
        if not self._uses_web3:
            raise RuntimeError('web3 is not being used')
        return globals()[self._conf['web3_provider']['class']](*(self._conf['web3_provider']['args']))

    def get_redis(self):
        return redis.StrictRedis(
                host=self.get('redis', {}).get('host', '127.0.0.1'),
                port=self.get('redis', {}).get('port', 6379),
                db=self.get('redis', {}).get('db', 0))

    def _check_addresses(self, addresses):
        self._check_strings(addresses)
        for address_name in addresses if isinstance(addresses, (list, tuple)) else (addresses, ):
            if not Web3.isAddress(self._conf[address_name]):
                raise ValueError(address_name + ' is incorrect')


class State(object):

    def __init__(self, filename, lock_shared=False):
        self._filename = filename

        self._lock = FileLock(filename + ".lock", non_blocking=True, shared=lock_shared)
        try:
            self._lock.lock()   # implicit unlock is at process termination
        except WouldBlockError:
            _fatal('Can\'t acquire state lock: looks like another instance is running')

        if os.path.isfile(filename):
            with open(filename) as fh:
                self._state = yaml.safe_load(fh)
            self._created = False
        else:
            self._state = dict()
            self._created = True

        self._original = copy.deepcopy(self._state)


    def __enter__(self):
        assert self._lock is not None, "reuse is not possible"
        return self     # already locked

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.unlock()
        self._lock = None


    def __getitem__(self, key):
        assert self._lock is not None
        return self._state[key]

    def __setitem__(self, key, value):
        assert self._lock is not None
        self._state[key] = value

    def __contains__(self, item):
        assert self._lock is not None
        return item in self._state

    def get(self, key, default):
        assert self._lock is not None
        return self._state.get(key, default)


    @property
    def account_address(self):
        return self.get('account', dict()).get('address')

    def get_account_address(self):
        if self.account_address is None:
            raise RuntimeError('account was not initialized')
        return self.account_address

    def get_minter_contract_address(self):
        if 'minter_contract' not in self:
            raise RuntimeError('contract was not deployed')
        return self['minter_contract']


    def save(self, sync=False):
        assert self._lock is not None
        if self._state == self._original:
            return
        with open(self._filename, 'w') as fh:
            if self._created:
                os.chmod(self._filename, stat.S_IRUSR | stat.S_IWUSR)

            yaml.safe_dump(self._state, fh, default_flow_style=False)

            if sync:
                fh.flush()
                os.fsync(fh.fileno())


conf = Conf()
w3_instance = Web3(conf.get_provider())
redis_instance = conf.get_redis()

app = Flask(__name__)
app_state = None


@app.route('/mintTokens')
def mint_tokens():
    mint_id = _get_mint_id()
    address = _get_address()
    tokens = _get_tokens()

    gas_price = w3_instance.eth.gasPrice
    gas_limit = _gas_limit()

    tx_hash = _target_contract()\
        .transact({'from': app_state.get_account_address(), 'gasPrice': gas_price, 'gas': gas_limit})\
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
    assert isinstance(mint_id, (str, bytes))
    if isinstance(mint_id, str):
        mint_id = mint_id.encode('utf-8')

    if 0 == len(mint_id):
        abort(400, 'empty mint_id')

    return Web3.toBytes(hexstr=Web3.sha3(mint_id))


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
def _built_contract(contract_name):
    with open(os.path.join(os.path.dirname(__file__), '..', 'built_contracts', contract_name + '.json')) as fh:
        return json.load(fh)


@lru_cache(1)
def _target_contract():
    return w3_instance.eth.contract(app_state.get_minter_contract_address(),
                                    abi=_built_contract('ReenterableMinter')['abi'])


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
    contract_address_bytes = Web3.toBytes(hexstr=app_state.get_minter_contract_address())
    assert 20 == len(contract_address_bytes)
    return Web3.toBytes(hexstr=Web3.sha3(contract_address_bytes + mint_id))


def _silent_redis_call(call_fn, *args, **kwargs):
    try:
        return call_fn(*args, **kwargs)
    except redis.exceptions.ConnectionError as exc:
        logging.warning('could not contact redis: %s', exc)
        return None


def _fatal(message, *args):
    print(message.format(*args), file=sys.stderr)
    sys.exit(1)


def _load_state(lock_shared=False):
    return State(os.path.join(conf['data_directory'], 'state.yaml'), lock_shared)


def _get_receipt_blocking(tx_hash):
    while True:
        receipt = w3_instance.eth.getTransactionReceipt(tx_hash)
        if receipt is not None:
            return receipt
        sleep(1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('help', '-h', '--help'):
        print("""
Usage:

step 1: service.py init_account - initializes new account to use for minting
step 1.1: * send ether to and periodically refill balance of minting account

step 2: service.py deploy_contract <token_address> - deploy ReenterableMinter contract needed for minting
step 2.1: * make sure deployed ReenterableMinter contract have permissions to mint token

step 3: * use service.py as a WSGI app (to mint and check minting status)

step 4: service.py recover_ether <address_to_send_ether_to> - recover ether remaining on minting account
            """.strip())
        sys.exit(0)

    if len(sys.argv) > 1 and 'init_account' == sys.argv[1]:
        logging.basicConfig(level=logging.INFO)

        with _load_state() as state:
            if state.account_address is not None:
                _fatal('Account is already initialized (address: {})', state.account_address)

            password = Web3.sha3(os.urandom(100))[2:42]
            address = w3_instance.personal.newAccount(password)
            assert Web3.isAddress(address)

            state['account'] = {
                'password': password,
                'address': address,
            }
            state.save(True)

        print('Generated new account: {}'.format(address))

    elif len(sys.argv) > 1 and 'deploy_contract' == sys.argv[1]:
        logging.basicConfig(level=logging.INFO)
        if len(sys.argv) != 3:
            _fatal('usage: {} deploy_contract <token_address>', sys.argv[0])
        token_address = sys.argv[2]
        if not Web3.isAddress(token_address):
            _fatal('bad token address: {}', token_address)

        gas_price = w3_instance.eth.gasPrice
        gas_limit = int(w3_instance.eth.getBlock('latest').gasLimit * 0.9)

        with _load_state() as state:
            contract = w3_instance.eth.contract(abi=_built_contract('ReenterableMinter')['abi'],
                                                bytecode=_built_contract('ReenterableMinter')['unlinked_binary'])

            w3_instance.personal.unlockAccount(state.get_account_address(), state['account']['password'])

            tx_hash = contract.deploy(transaction={'from': state.get_account_address(),
                                                   'gasPrice': gas_price, 'gas': gas_limit},
                                      args=[token_address])

            print('Waiting for tx: ' + tx_hash)
            logging.debug('deploy_contract: token_address=%s, gas_price=%d, gas=%d: sent tx %s',
                          token_address, gas_price, gas_limit, tx_hash)

            address = _get_receipt_blocking(tx_hash)['contractAddress']
            assert Web3.isAddress(address)

            state['minter_contract'] = address
            state.save(True)

            print('ReenterableMinter deployed at: ' + address)

    elif len(sys.argv) > 1 and 'recover_ether' == sys.argv[1]:
        logging.basicConfig(level=logging.INFO)
        if len(sys.argv) != 3:
            _fatal('usage: {} recover_ether <address_to_send_ether_to>', sys.argv[0])
        target_address = sys.argv[2]
        if not Web3.isAddress(target_address):
            _fatal('bad address: {}', target_address)

        with _load_state() as state:
            w3_instance.personal.unlockAccount(state.get_account_address(), state['account']['password'])

            tx_hash = w3_instance.eth.sendTransaction({'from': state.get_account_address(), 'to': target_address,
                    'value': w3_instance.eth.getBalance(state.get_account_address())})

            print('Waiting for tx: ' + tx_hash)
            _get_receipt_blocking(tx_hash)
            print('Mined.')

    else:
        logging.basicConfig(level=logging.DEBUG)

        with _load_state(lock_shared=True) as state:
            globals()['app_state'] = state

            w3_instance.personal.unlockAccount(state.get_account_address(), state['account']['password'])

            app.run()
