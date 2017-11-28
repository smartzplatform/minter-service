pragma solidity 0.4.15;

import '../../contracts/ReenterableMinter.sol';
import '../../contracts/test_helpers/SimpleMintableToken.sol';
import 'truffle/Assert.sol';


contract TestReenterableMinter {

    function testMinting() {
        SimpleMintableToken token = new SimpleMintableToken();
        ReenterableMinter minter = new ReenterableMinter(token);
        token.transferOwnership(minter);

        address investor1 = address(0xa1);
        address investor2 = address(0xa2);

        Assert.equal(token.balanceOf(investor1), 0, "neq");
        Assert.equal(token.balanceOf(investor2), 0, "neq");

        minter.mint(sha3("m1"), investor1, 10000);
        Assert.equal(token.balanceOf(investor1), 10000, "neq");
        Assert.equal(token.balanceOf(investor2), 0, "neq");

        minter.mint(sha3("m2"), investor2, 12000);
        Assert.equal(token.balanceOf(investor1), 10000, "neq");
        Assert.equal(token.balanceOf(investor2), 12000, "neq");

        minter.mint(sha3("m1"), investor1, 10000);
        Assert.equal(token.balanceOf(investor1), 10000, "neq");
        Assert.equal(token.balanceOf(investor2), 12000, "neq");

        minter.mint(sha3("m1"), investor2, 12000);
        Assert.equal(token.balanceOf(investor1), 10000, "neq");
        Assert.equal(token.balanceOf(investor2), 12000, "neq");

        minter.mint(sha3("m3"), investor1, 8000);
        Assert.equal(token.balanceOf(investor1), 18000, "neq");
        Assert.equal(token.balanceOf(investor2), 12000, "neq");
    }
}
