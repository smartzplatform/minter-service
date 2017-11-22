module.exports = {
  networks: {
    development: {
      host: "localhost",
      port: 8545,
      network_id: "*" // Match any network id
    },

    ropsten: {  // testnet
      host: "localhost",
      port: 8547,
      network_id: 3
    },

    rinkeby: {  // testnet
      host: "localhost",
      port: 8547,
      network_id: 4
    }
  }
};
