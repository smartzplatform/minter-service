#!/usr/bin/env python3

import sys
import os
import logging

from web3 import Web3
from flask import Flask, abort, request

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'lib')))

from mixbytes.minter import MinterService, UsageError


conf_filename = os.path.join(os.path.dirname(__file__), '..', 'conf', 'minter.conf')
contracts_directory = os.path.join(os.path.dirname(__file__), '..', 'built_contracts')

app = Flask(__name__)
wsgi_minter = None


@app.route('/mintTokens')
def mint_tokens():
    wsgi_minter.mint_tokens(_get_mint_id(), _get_address(), _get_tokens())
    return '{"success": true}'


@app.route('/getMintingStatus')
def get_minting_status():
    return '{{"status": "{}"}}'.format(wsgi_minter.get_minting_status(_get_mint_id()))


def _get_mint_id():
    """
    Extracts mint id from current request parameters.
    :return: mint id
    """
    mint_id = request.args['mint_id']
    assert isinstance(mint_id, (str, bytes))

    if 0 == len(mint_id):
        abort(400, 'empty mint_id')

    return mint_id


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


def _fatal(message, *args):
    print(message.format(*args), file=sys.stderr)
    sys.exit(1)


def main():
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
        try:
            print('Generated new account: {}'.format(MinterService(conf_filename, contracts_directory).init_account()))
        except UsageError as exc:
            _fatal('{}', exc.message)

    elif len(sys.argv) > 1 and 'deploy_contract' == sys.argv[1]:
        logging.basicConfig(level=logging.INFO)
        if len(sys.argv) != 3:
            _fatal('usage: {} deploy_contract <token_address>', sys.argv[0])
        token_address = sys.argv[2]
        if not Web3.isAddress(token_address):
            _fatal('bad token address: {}', token_address)

        try:
            print('ReenterableMinter deployed at: {}'.format(
                MinterService(conf_filename, contracts_directory).deploy_contract(token_address)))
        except UsageError as exc:
            _fatal('{}', exc.message)

    elif len(sys.argv) > 1 and 'recover_ether' == sys.argv[1]:
        logging.basicConfig(level=logging.INFO)
        if len(sys.argv) != 3:
            _fatal('usage: {} recover_ether <address_to_send_ether_to>', sys.argv[0])
        target_address = sys.argv[2]
        if not Web3.isAddress(target_address):
            _fatal('bad address: {}', target_address)

        try:
            tx_hash = MinterService(conf_filename, contracts_directory).recover_ether(target_address)
            if tx_hash is None:
                print("Nothing could be sent")
            else:
                print("Mined transaction: {}".format(tx_hash))
        except UsageError as exc:
            _fatal('{}', exc.message)

    else:
        # run WSGI
        logging.basicConfig(level=logging.DEBUG)
        globals()['wsgi_minter'] = MinterService(conf_filename, contracts_directory, wsgi_mode=True)
        app.run()


if __name__ == '__main__':
    main()
