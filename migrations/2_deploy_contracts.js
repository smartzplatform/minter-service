var SimpleMintableToken = artifacts.require("./test_helpers/SimpleMintableToken.sol");
var ReenterableMinter = artifacts.require("./ReenterableMinter.sol");

module.exports = function(deployer) {
  deployer.deploy(SimpleMintableToken).then(function(){
    return deployer.deploy(ReenterableMinter, SimpleMintableToken.address).then(function(){
      return SimpleMintableToken.deployed().then(function(token){
        return token.transferOwnership(ReenterableMinter.address);
      });
    });
  });
};
