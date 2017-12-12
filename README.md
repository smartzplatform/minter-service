# minter-service
Service responsible for sending plenty of ethereum transactions to mint token described by interface `IMintableToken`.


## Docker-compose

### Optional: configure

`geth` data directory under `services` - `ethereum_node` - `volumes`.

Exported service port under `services` - `minter-service` - `ports`.

Service data directory (holds state of small size) and config under `services` - `minter-service` - `volumes`.

Edit minter.conf (the only thing you should tweak is `require_confirmations`).

### Build

docker-compose build

### Start service in control mode

docker-compose run minter-service shell

For help use ./ctl.py -h

enter ctrl-D after finished

### Start service http-mode

docker-compose up

### Stop service

docker-compose stop


## Usage

### Control commands

Run `docker-compose run minter-service shell`,

see `./bin/ctl.py --help`.

### WSGI app

Exported at port `8000`.

Mint after deploying token and minter contract:

```bash
curl -s 'http://127.0.0.1:8000/mintTokens?mint_id=foo&address=0x1111111111111111111111111111111111111122&tokens_amount=1000000'
```

and check:

```bash
curl -s 'http://127.0.0.1:8000/getMintingStatus?mint_id=foo'
```


## Development

### Install dependencies

```bash
npm install
pip3 install -r requirements.txt
```

### Test

#### solidity

```bash
# run ganache-cli if it's not already running
./node_modules/.bin/ganache-cli --gasPrice 2000 -l 10000000 &>/tmp/ganache.log &

./node_modules/.bin/truffle test
```

#### integration

```bash
./test/i/run.sh
```

### Install

```bash
./bin/deploy target_dir
```

### Configure

See `<installation dir>/conf/minter.conf`.

`geth` must be started with option `--rpcapi eth,personal`.
