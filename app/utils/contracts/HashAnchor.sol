// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title HashAnchor
/// @notice Anchors a SHA-256 file hash on-chain as (sender, timestamp).
///         Intentionally minimal: this contract does not store any file
///         content or metadata, only a 32-byte hash pointer -- the actual
///         evidence, case data, and audit trail stay in NyayVault's own
///         database. This contract exists purely to give a hash a
///         tamper-evident, independently-verifiable timestamp.
contract HashAnchor {
    struct AnchorRecord {
        address anchoredBy;
        uint256 timestamp;
    }

    mapping(bytes32 => AnchorRecord) public records;

    event HashAnchored(bytes32 indexed fileHash, address indexed anchoredBy, uint256 timestamp);

    /// @notice Registers `fileHash` on-chain. Reverts if it was already
    ///         anchored (a hash should only ever be anchored once).
    function anchorHash(bytes32 fileHash) external {
        require(records[fileHash].timestamp == 0, "HashAnchor: already anchored");
        records[fileHash] = AnchorRecord({anchoredBy: msg.sender, timestamp: block.timestamp});
        emit HashAnchored(fileHash, msg.sender, block.timestamp);
    }

    /// @notice Free read-only check for whether a hash has been anchored.
    function isAnchored(bytes32 fileHash) external view returns (bool) {
        return records[fileHash].timestamp != 0;
    }

    /// @notice Free read-only fetch of who anchored a hash, and when.
    function getRecord(bytes32 fileHash) external view returns (address anchoredBy, uint256 timestamp) {
        AnchorRecord memory r = records[fileHash];
        return (r.anchoredBy, r.timestamp);
    }
}
