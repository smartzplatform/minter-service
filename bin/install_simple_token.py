import os
import sys
import subprocess
import unittest
from shutil import rmtree
from os.path import join
import logging
import json
from time import sleep
from plumbum import cli
from plumbum import local
from plumbum.cmd import truffle
import yaml
import shutil
import logging

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

from mixbytes.minter import MinterService, UsageError, get_receipt_status

def _token_json():
         with open(os.path.join('build', 'contracts', 'SimpleMintableToken.json')) as fh:
             return json.load(fh)

def _get_receipt_blocking(tx_hash, w3):
    logging.info("Wait for transaction %s" % tx_hash)
    while True:
        receipt = w3.eth.getTransactionReceipt(tx_hash)
        if receipt is not None:
            return receipt

        sleep(0.5)

def _blocking_to_wait_ethers(account, w3):
    gas_price = w3.eth.gasPrice
    gas_limit = int(w3.eth.getBlock('latest').gasLimit * 0.9)
    expected_balance = gas_price * gas_limit
    logging.info("Wait for sufficient balance %s on account %s" % (expected_balance, account))
    while True:
        balance = w3.eth.getBalance(account)
        if balance > expected_balance:
            return balance
      
        sleep(0.5)
            

class SimpleTokenInstaller(cli.Application):
    _redis_host = 'localhost'
    _redis_port = 6379
    _ethereum_node = 'http://localhost:8545'

    @cli.switch("--redis", str)
    def redis(self, redis):
        host_and_port = str(redis).split(":")
        self._redis_host = host_and_port[0]
        self._redis_port = int(host_and_port[1])
        self._network = "development"
        
        
    @cli.switch("--ethereum-node", str)
    def ethereum_node(self, node):
        self._ethereum_node="http://%s" % (node)

    @cli.switch("--data-dir", str)
    def data_dir(self, data_dir):
        self._data_dir=data_dir

    def main(self):
    
        conf_file = os.path.join("/tmp", "minter.conf")
        minter_data_dir = self._data_dir or "/tmp/ganache-minter-data"
        if not os.path.exists(minter_data_dir):
            os.mkdir(minter_data_dir)


        with open(conf_file, 'w') as stream:
            yaml.dump({
                'data_directory': minter_data_dir,
                'web3_provider': {
                    'args':[self._ethereum_node],
                    'class': 'HTTPProvider'
                },
                'redis': {
                    'host': self._redis_host,
                    'port': self._redis_port,
                    'db': 0

                }
            }, stream)

        compiled_contracts_dir = os.path.join('build', 'contracts')
        minter_service_init = MinterService(conf_file, compiled_contracts_dir, False)

        minter_address = minter_service_init.get_or_init_account()

        with MinterService(conf_file, compiled_contracts_dir, True) as minter_service:
        

            w3 = minter_service.create_web3()


            if not minter_service.is_contract_deployed():
                logging.info("Init minter contracts")
                _blocking_to_wait_ethers(minter_address, w3)            
                get_bytecode = lambda json_: json_.get('bytecode') or json_['unlinked_binary']

                contract_json = _token_json()            
                token_contract = minter_service.token_address() or w3.eth.contract(abi=contract_json['abi'], bytecode=get_bytecode(contract_json))

                gas_price = w3.eth.gasPrice
                gas_limit = int(w3.eth.getBlock('latest').gasLimit * 0.9)

                logging.info("Deploy token contract...")
                tx_hash = token_contract.deploy(transaction={'from': minter_address, 'gasPrice': gas_price, 'gas': gas_limit})

                token_address = _get_receipt_blocking(tx_hash, w3).contractAddress

                logging.info("Deploy minter contract...")
                address = minter_service.deploy_contract(token_address)
            print("Token address: %s" % (minter_service.token_address()))
        
        os.remove(conf_file)
        if not self._data_dir:
            shutil.rmtree(minter_data_dir)
    
    

if __name__=="__main__":
    SimpleTokenInstaller().main()

