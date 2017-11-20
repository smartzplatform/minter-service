pragma solidity 0.4.15;

import './IMintableToken.sol';
import 'zeppelin-solidity/contracts/ownership/Ownable.sol';


contract ReenterableMinter is Ownable {
    event MintSuccess(bytes32 indexed mint_id);
    event AlreadyMinted(bytes32 indexed mint_id);

    function ReenterableMinter(IMintableToken token){
        m_token = token;
    }

    function mint(bytes32 mint_id, address to, uint256 amount) onlyOwner {
        if (m_processed_mint_id[mint_id]) {
            AlreadyMinted(mint_id);
            revert();
        }

        m_token.mint(to, amount);
        m_processed_mint_id[mint_id] = true;
        MintSuccess(mint_id);
    }

    IMintableToken public m_token;

    mapping(bytes32 => bool) public m_processed_mint_id;
}
