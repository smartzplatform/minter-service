#!/bin/bash
./node_modules/.bin/ganache-cli&
./node_modules/.bin/truffle test
./test/i/run.sh

