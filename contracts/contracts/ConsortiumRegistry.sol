// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract ConsortiumRegistry {
    address public owner;

    struct Node {
        string orgId;
        bytes32 role;
        bool active;
        uint256 registeredAt;
    }

    mapping(address => Node) private nodes;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event NodeRegistered(address indexed node, string orgId, bytes32 role);
    event NodeStatusChanged(address indexed node, bool active);

    modifier onlyOwner() {
        require(msg.sender == owner, "REGISTRY_ONLY_OWNER");
        _;
    }

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "REGISTRY_ZERO_OWNER");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function registerNode(address node, string calldata orgId, bytes32 role) external onlyOwner {
        require(node != address(0), "REGISTRY_ZERO_NODE");
        require(bytes(orgId).length > 0, "REGISTRY_EMPTY_ORG");
        nodes[node] = Node({
            orgId: orgId,
            role: role,
            active: true,
            registeredAt: block.timestamp
        });
        emit NodeRegistered(node, orgId, role);
    }

    function setNodeActive(address node, bool active) external onlyOwner {
        require(nodes[node].registeredAt != 0, "REGISTRY_UNKNOWN_NODE");
        nodes[node].active = active;
        emit NodeStatusChanged(node, active);
    }

    function isActiveNode(address node) external view returns (bool) {
        return nodes[node].active;
    }

    function getNode(address node) external view returns (string memory orgId, bytes32 role, bool active, uint256 registeredAt) {
        Node memory record = nodes[node];
        return (record.orgId, record.role, record.active, record.registeredAt);
    }
}
