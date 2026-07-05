// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract ReputationRegistry {
    address public owner;
    address public trainingLedger;
    mapping(address => uint256) public reputation;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event TrainingLedgerSet(address indexed trainingLedger);
    event ReputationChanged(address indexed node, uint256 score, int256 delta);

    modifier onlyOwner() {
        require(msg.sender == owner, "REPUTATION_ONLY_OWNER");
        _;
    }

    modifier onlyLedger() {
        require(msg.sender == trainingLedger, "REPUTATION_ONLY_LEDGER");
        _;
    }

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "REPUTATION_ZERO_OWNER");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setTrainingLedger(address ledger) external onlyOwner {
        require(ledger != address(0), "REPUTATION_ZERO_LEDGER");
        trainingLedger = ledger;
        emit TrainingLedgerSet(ledger);
    }

    function seedReputation(address node, uint256 score) external onlyOwner {
        require(score <= 100, "REPUTATION_SCORE_RANGE");
        reputation[node] = score;
        emit ReputationChanged(node, score, int256(score));
    }

    function applyContribution(address node, bool validated) external onlyLedger {
        uint256 current = reputation[node] == 0 ? 80 : reputation[node];
        if (validated) {
            current = current >= 99 ? 100 : current + 1;
            emit ReputationChanged(node, current, 1);
        } else {
            current = current <= 54 ? 50 : current - 4;
            emit ReputationChanged(node, current, -4);
        }
        reputation[node] = current;
    }
}
