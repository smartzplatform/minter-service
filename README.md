# minter-service
Service responsible for sending plenty of ethereum transactions to mint token described by interface `IMintableToken`.

## Install dependencies

```bash
npm install
pip3 install -r requirements.txt
```

## Test

### solidity

```bash
# run ganache-cli if it's not already running
./node_modules/.bin/ganache-cli --gasPrice 2000 -l 10000000 &>/tmp/ganache.log &

./node_modules/.bin/truffle test
```

### integration

```bash
./test/i/run.sh
```

## Install

```bash
./bin/deploy target_dir
```

## Configure

See `<installation dir>/conf/minter.conf`.

`geth` must be started with option `--rpcapi eth,personal`.

## Usage

### Control commands

See `./bin/ctl.py --help`.

### WSGI app

E.g. mount to uwsgi:

```bash
uwsgi --mount /yourapplication=/path/to/bin/wsgi_app:app
```

Mint after deploying token and minter contract:

```bash
curl -s 'http://127.0.0.1/mintTokens?mint_id=foo&address=0x1111111111111111111111111111111111111122&tokens_amount=1000000'
```

and check:

```bash
curl -s 'http://127.0.0.1/getMintingStatus?mint_id=foo'
```

## Docker-compose

### Build

docker-compose build

### Control service

docker-compose run minter-service shell

### Start service

docker-compose up

### Variables (will be removed)

$MINTER_CONF - path to service config file

$MINTER_DATA - path to service data directory
