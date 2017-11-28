var SimpleMintableToken = artifacts.require("./test_helpers/SimpleMintableToken.sol");

module.exports = function(deployer) {
  deployer.deploy(SimpleMintableToken);
};
