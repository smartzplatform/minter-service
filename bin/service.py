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

    def get_provider(self):
        if not self._uses_web3:
            raise RuntimeError('web3 is not being used')
        return globals()[self._conf['web3_provider']['class']](*(self._conf['web3_provider']['args']))

    def _check_addresses(self, addresses):
        for address_name in addresses if isinstance(addresses, (list, tuple)) else (addresses, ):
            if not self._conf.get(address_name):
                raise ValueError(address_name + ' is not provided')

            if not Web3.isAddress(self._conf[address_name]):
                raise ValueError(address_name + ' is incorrect')


class Conf(ConfigurationBase):

    def __init__(self):
        super().__init__(os.path.join(os.path.dirname(__file__), '..', 'conf', 'minter.conf'))

        self._check_addresses(('reenterable_minter_address', 'account_address'))


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

    assert mint_id[0] == '0' and mint_id[1] == 'x'
    mint_id_abi = bytearray.fromhex(mint_id[2:])

    tx_hash = _target_contract()\
        .transact({'from': conf['account_address'], 'gasPrice': gas_price})\
        .mint(mint_id_abi, address, tokens)

    logging.debug('mint_tokens(): mint_id=%s, address=%s, tokens=%d, gas_price=%d: sent tx %s',
                  mint_id, address, tokens, gas_price, tx_hash)
    return '{"success": true}'


@app.route('/getMintingStatus')
def get_minting_status():
    mint_id = _get_mint_id()
    raise NotImplementedError()


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
