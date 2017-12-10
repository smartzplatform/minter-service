#!/bin/bash
source /venv/bin/activate
./node_modules/.bin/ganache-cli --gasPrice 2000 -l 10000000 &>/tmp/ganache.log &
./node_modules/.bin/truffle test
./test/i/run.sh

