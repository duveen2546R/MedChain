// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IConsortiumRegistry {
    function isActiveNode(address node) external view returns (bool);
}

interface IReputationRegistry {
    function applyContribution(address node, bool validated) external;
}

contract TrainingLedger {
    address public owner;
    IConsortiumRegistry public registry;
    IReputationRegistry public reputation;

    struct Contribution {
        bytes32 roundId;
        string modelVersion;
        address contributor;
        bytes32 updateHash;
        string artifactCid;
        bool validated;
        uint256 timestamp;
    }

    Contribution[] private contributions;
    mapping(bytes32 => mapping(address => bool)) public submittedByRound;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event ContributionRecorded(
        bytes32 indexed roundId,
        address indexed contributor,
        bytes32 indexed updateHash,
        string modelVersion,
        string artifactCid,
        bool validated
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "LEDGER_ONLY_OWNER");
        _;
    }

    constructor(address registryAddress, address reputationAddress) {
        require(registryAddress != address(0), "LEDGER_ZERO_REGISTRY");
        require(reputationAddress != address(0), "LEDGER_ZERO_REPUTATION");
        owner = msg.sender;
        registry = IConsortiumRegistry(registryAddress);
        reputation = IReputationRegistry(reputationAddress);
        emit OwnershipTransferred(address(0), msg.sender);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "LEDGER_ZERO_OWNER");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function recordContribution(
        bytes32 roundId,
        string calldata modelVersion,
        address contributor,
        bytes32 updateHash,
        string calldata artifactCid,
        bool validated
    ) external onlyOwner {
        require(roundId != bytes32(0), "LEDGER_EMPTY_ROUND");
        require(updateHash != bytes32(0), "LEDGER_EMPTY_HASH");
        require(bytes(artifactCid).length > 0, "LEDGER_EMPTY_CID");
        require(registry.isActiveNode(contributor), "LEDGER_INACTIVE_NODE");
        require(!submittedByRound[roundId][contributor], "LEDGER_DUPLICATE_SUBMISSION");

        submittedByRound[roundId][contributor] = true;
        contributions.push(Contribution({
            roundId: roundId,
            modelVersion: modelVersion,
            contributor: contributor,
            updateHash: updateHash,
            artifactCid: artifactCid,
            validated: validated,
            timestamp: block.timestamp
        }));
        reputation.applyContribution(contributor, validated);

        emit ContributionRecorded(roundId, contributor, updateHash, modelVersion, artifactCid, validated);
    }

    function contributionCount() external view returns (uint256) {
        return contributions.length;
    }

    function getContribution(uint256 index) external view returns (Contribution memory) {
        require(index < contributions.length, "LEDGER_INDEX_RANGE");
        return contributions[index];
    }
}
