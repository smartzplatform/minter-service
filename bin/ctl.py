#!/usr/bin/env python3

import sys
import os
import logging

from web3 import Web3

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'lib')))

from mixbytes.minter import MinterService, UsageError


conf_filename = os.path.join(os.path.dirname(__file__), '..', 'conf', 'minter.conf')
contracts_directory = os.path.join(os.path.dirname(__file__), '..', 'built_contracts')


def _fatal(message, *args):
    print(message.format(*args), file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('help', '-h', '--help'):
        print("""
    Usage:

    step 1: ctl.py init_account - initializes new account to use for minting
    step 1.1: * send ether to and periodically refill balance of minting account

    step 2: ctl.py deploy_contract <token_address> - deploy ReenterableMinter contract needed for minting
    step 2.1: * make sure deployed ReenterableMinter contract have permissions to mint token

    step 3: * use wsgi_app:app as a WSGI app (to mint and check minting status)

    step 4: ctl.py recover_ether <address_to_send_ether_to> - recover ether remaining on minting account
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
        _fatal('no command given, see {} help', sys.argv[0])


if __name__ == '__main__':
    main()
