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

## Usage

See `./bin/service.py -h`
