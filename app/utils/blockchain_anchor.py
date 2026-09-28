"""
Lightweight blockchain anchoring layer.

Purpose: take a file's SHA-256 hash (already computed by
app/utils/hashing.py at upload time) and register it on a local/testnet
smart contract via web3.py, so a tamper-check can later be corroborated
against an immutable, third-party-verifiable record -- independent of our
own database.

Design constraints this module respects:
  - The database remains the single source of truth for actual storage and
    queries. This module does exactly one thing: send a hash to a chain and
    hand back the transaction hash. It never reads/writes case or document
    rows itself -- callers (see app/routers/documents.py) own that.
  - web3.py is imported lazily, inside functions, not at module import time.
    If it isn't installed, or `BLOCKCHAIN_ANCHORING_ENABLED` is left off (the
    default), importing this module -- and importing the rest of the app --
    still works with zero setup, exactly as before this feature existed.
  - Every failure mode (no node running, bad private key, no contract
    deployed, insufficient gas funds, etc.) raises a clear, typed exception
    instead of hanging or crashing the caller. Callers are expected to run
    this in a background task and treat failures as non-fatal to the upload
    itself (see documents.py).

Deploying the contract
-----------------------
A minimal Solidity source for the expected contract lives alongside this
file at app/utils/contracts/HashAnchor.sol. Deploy it to any local/testnet
chain (Ganache, Anvil, Hardhat node, Polygon Amoy, Sepolia, etc.) with
Remix, Hardhat, or Foundry, then set these env vars (see .env.example):

    BLOCKCHAIN_ANCHORING_ENABLED=true
    WEB3_PROVIDER_URI=https://rpc-amoy.polygon.technology
    BLOCKCHAIN_CHAIN_ID=80002
    WALLET_PRIVATE_KEY=0x...            # a dev/test account's key only
    BLOCKCHAIN_CONTRACT_ADDRESS=0x...   # address HashAnchor was deployed to

(BLOCKCHAIN_RPC_URL / BLOCKCHAIN_PRIVATE_KEY are accepted as older aliases
for WEB3_PROVIDER_URI / WALLET_PRIVATE_KEY -- see app/config.py.)

The contract's `anchorHash(bytes32)` stores (sender, block.timestamp)
keyed by the hash and emits a `HashAnchored` event; `isAnchored(bytes32)`
and `getRecord(bytes32)` are free (read-only) calls anyone can use to
independently verify a hash was anchored, without trusting this API.

Block explorer links
---------------------
`get_explorer_tx_url()` turns a transaction hash into a clickable
block-explorer URL (e.g. Polygonscan for Amoy) so the frontend can link out
to independent, third-party proof of the transaction instead of only
trusting this API's own record of it. It never raises -- an unknown chain
ID with no BLOCKCHAIN_EXPLORER_BASE_URL configured just yields None, and
callers (see app/routers/documents.py) treat that as "no link to show".
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from app.config import settings

# Fallback table of public block-explorer "transaction" URL prefixes, keyed
# by chain ID. Used only when BLOCKCHAIN_EXPLORER_BASE_URL isn't set.
# Extend this (or just set BLOCKCHAIN_EXPLORER_BASE_URL) for any other chain.
_KNOWN_EXPLORERS: dict[int, str] = {
    1: "https://etherscan.io/tx/",                 # Ethereum mainnet
    11155111: "https://sepolia.etherscan.io/tx/",  # Sepolia testnet
    137: "https://polygonscan.com/tx/",            # Polygon mainnet
    80002: "https://amoy.polygonscan.com/tx/",     # Polygon Amoy testnet
    1337: "",                                       # local dev chain -- no public explorer
}

# ABI for app/utils/contracts/HashAnchor.sol. Kept in sync by hand since the
# contract is intentionally tiny and stable -- if you change the .sol file,
# update this to match (or generate it with solc/Hardhat and paste it here).
CONTRACT_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "fileHash", "type": "bytes32"}],
        "name": "anchorHash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "fileHash", "type": "bytes32"}],
        "name": "isAnchored",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "fileHash", "type": "bytes32"}],
        "name": "getRecord",
        "outputs": [
            {"internalType": "address", "name": "anchoredBy", "type": "address"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "bytes32", "name": "fileHash", "type": "bytes32"},
            {"indexed": True, "internalType": "address", "name": "anchoredBy", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "name": "HashAnchored",
        "type": "event",
    },
]


class BlockchainAnchorError(Exception):
    """Raised for any anchoring failure: disabled, misconfigured, node
    unreachable, transaction rejected, etc. Always safe to catch broadly
    and treat as non-fatal by callers that must not block on-chain issues."""


class AlreadyAnchoredError(BlockchainAnchorError):
    """Raised when the contract already has a record for this exact hash
    (HashAnchor.sol rejects duplicate anchors). Not really a failure --
    the hash is provably on-chain already -- but there's no *new*
    transaction hash to report, so it's surfaced distinctly."""


@dataclass(frozen=True)
class AnchorRecord:
    anchored_by: str
    timestamp: int
    exists: bool


def _require_web3():
    try:
        from web3 import Web3
    except ImportError as exc:
        raise BlockchainAnchorError(
            "web3.py is not installed. Run `pip install web3` (see requirements.txt)."
        ) from exc
    return Web3


@lru_cache(maxsize=1)
def _get_web3():
    """Builds (and caches) a single Web3 connection for the process. Cached
    so every anchoring call doesn't re-handshake with the node -- this is
    the only part of the module that's shared/reused across calls."""
    Web3 = _require_web3()

    if not settings.BLOCKCHAIN_ANCHORING_ENABLED:
        raise BlockchainAnchorError(
            "Blockchain anchoring is disabled (set BLOCKCHAIN_ANCHORING_ENABLED=true)."
        )
    if not settings.BLOCKCHAIN_RPC_URL:
        raise BlockchainAnchorError(
            "No RPC endpoint configured (set WEB3_PROVIDER_URI)."
        )

    # request_kwargs sets the HTTP timeout web3 uses under the hood (via
    # `requests`), so a hung/unreachable public RPC (rather than an outright
    # connection error) can't block the caller indefinitely -- it raises the
    # same BlockchainAnchorError as every other connectivity failure below.
    try:
        w3 = Web3(
            Web3.HTTPProvider(
                settings.BLOCKCHAIN_RPC_URL,
                request_kwargs={"timeout": settings.BLOCKCHAIN_RPC_TIMEOUT_SECONDS},
            )
        )
    except Exception as exc:  # noqa: BLE001 - malformed URL, bad scheme, etc.
        raise BlockchainAnchorError(
            f"Could not construct a Web3 HTTPProvider for {settings.BLOCKCHAIN_RPC_URL!r}: {exc}"
        ) from exc

    try:
        connected = w3.is_connected()
    except Exception as exc:  # noqa: BLE001 - node might be down, DNS fail, TLS error, timeout, etc.
        raise BlockchainAnchorError(
            f"Could not reach blockchain node at {settings.BLOCKCHAIN_RPC_URL}: {exc}"
        ) from exc
    if not connected:
        raise BlockchainAnchorError(
            f"Blockchain node at {settings.BLOCKCHAIN_RPC_URL} is not responding."
        )
    return w3


def _get_contract():
    if not settings.BLOCKCHAIN_CONTRACT_ADDRESS:
        raise BlockchainAnchorError(
            "BLOCKCHAIN_CONTRACT_ADDRESS is not configured -- deploy HashAnchor.sol "
            "and set its address first."
        )
    w3 = _get_web3()
    try:
        address = w3.to_checksum_address(settings.BLOCKCHAIN_CONTRACT_ADDRESS)
    except AttributeError:
        # web3.py v5 fallback (v6+ uses the snake_case name above).
        address = w3.toChecksumAddress(settings.BLOCKCHAIN_CONTRACT_ADDRESS)
    return w3.eth.contract(address=address, abi=CONTRACT_ABI)


def _hash_to_bytes32(sha256_hex: str) -> bytes:
    cleaned = sha256_hex[2:] if sha256_hex.startswith("0x") else sha256_hex
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise BlockchainAnchorError(f"'{sha256_hex}' is not valid hex.") from exc
    if len(raw) != 32:
        raise BlockchainAnchorError(
            f"Expected a 32-byte SHA-256 hash, got {len(raw)} bytes."
        )
    return raw


def _normalize_private_key(raw: str) -> str:
    """
    Robustly parses a private key from configuration into the "0x" + 64 hex
    chars form web3.py expects, regardless of small formatting differences
    between how people paste keys in (surrounding quotes/whitespace, missing
    "0x", uppercase hex, a key copied with a trailing newline, etc.).

    Raises BlockchainAnchorError with a clear message for anything that
    still isn't a plausible private key afterwards, rather than letting
    web3.py raise an opaque error deep inside signing.
    """
    if not raw or not raw.strip():
        raise BlockchainAnchorError(
            "WALLET_PRIVATE_KEY is not configured."
        )
    key = raw.strip().strip("'\"")
    if key.lower().startswith("0x"):
        key = key[2:]
    if not key:
        raise BlockchainAnchorError("WALLET_PRIVATE_KEY is empty after normalization.")
    try:
        int(key, 16)
    except ValueError as exc:
        raise BlockchainAnchorError(
            "WALLET_PRIVATE_KEY is not valid hexadecimal. Check for typos, stray "
            "characters, or that a mnemonic/seed phrase wasn't pasted in by mistake."
        ) from exc
    if len(key) != 64:
        raise BlockchainAnchorError(
            f"WALLET_PRIVATE_KEY should be 32 bytes (64 hex chars) once the '0x' "
            f"prefix is stripped -- got {len(key)} chars instead."
        )
    return f"0x{key}"


def _sign_and_send(w3, tx: dict) -> str:
    private_key = _normalize_private_key(settings.BLOCKCHAIN_PRIVATE_KEY)
    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    # web3.py v6 renamed .rawTransaction -> .raw_transaction; support both
    # so this keeps working whichever major version is installed.
    raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
    if raw is None:
        raise BlockchainAnchorError("Unexpected web3.py version: signed tx has no raw bytes attribute.")
    tx_hash = w3.eth.send_raw_transaction(raw)
    tx_hash_hex = tx_hash.hex()
    return tx_hash_hex if tx_hash_hex.startswith("0x") else f"0x{tx_hash_hex}"


def anchor_hash_to_blockchain(sha256_hex: str, *, wait_for_receipt: bool = False) -> str:
    """
    Anchors a SHA-256 file hash on-chain by calling HashAnchor.anchorHash().

    Args:
        sha256_hex: 64-char hex SHA-256 digest (with or without "0x").
        wait_for_receipt: if True, blocks until the transaction is mined
            (useful for a CLI/manual call); if False (the default, and what
            the upload endpoint uses), returns as soon as the transaction is
            broadcast so a slow block time never stalls the caller.

    Returns:
        The transaction hash as a "0x..." hex string.

    Raises:
        BlockchainAnchorError: anchoring is disabled/misconfigured, the
            node is unreachable, or the transaction was rejected.
        AlreadyAnchoredError: this exact hash is already on-chain.
    """
    private_key = _normalize_private_key(settings.BLOCKCHAIN_PRIVATE_KEY)

    w3 = _get_web3()
    contract = _get_contract()
    file_hash = _hash_to_bytes32(sha256_hex)

    account = w3.eth.account.from_key(private_key)

    # Read-only pre-check (free, no gas) -- avoids burning gas on a
    # transaction we already know the contract will revert.
    try:
        already = contract.functions.isAnchored(file_hash).call()
    except Exception as exc:  # noqa: BLE001
        raise BlockchainAnchorError(f"Could not reach contract at "
                                     f"{settings.BLOCKCHAIN_CONTRACT_ADDRESS}: {exc}") from exc
    if already:
        raise AlreadyAnchoredError(f"Hash {sha256_hex} is already anchored on-chain.")

    try:
        nonce = w3.eth.get_transaction_count(account.address, "pending")
        tx = contract.functions.anchorHash(file_hash).build_transaction(
            {
                "chainId": settings.BLOCKCHAIN_CHAIN_ID,
                "from": account.address,
                "nonce": nonce,
                "gas": settings.BLOCKCHAIN_GAS_LIMIT,
                "gasPrice": w3.eth.gas_price,
            }
        )
        tx_hash_hex = _sign_and_send(w3, tx)

        if wait_for_receipt:
            w3.eth.wait_for_transaction_receipt(
                tx_hash_hex, timeout=settings.BLOCKCHAIN_TX_TIMEOUT_SECONDS
            )
        return tx_hash_hex
    except BlockchainAnchorError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any web3/node error uniformly
        raise BlockchainAnchorError(f"Anchoring transaction failed: {exc}") from exc


def get_anchor_record(sha256_hex: str) -> AnchorRecord:
    """
    Free, read-only lookup of a hash's on-chain anchor record. Lets anyone
    (not just this API) independently verify anchoring without trusting our
    database's `blockchain_tx_hash` column.
    """
    contract = _get_contract()
    file_hash = _hash_to_bytes32(sha256_hex)
    try:
        anchored_by, timestamp = contract.functions.getRecord(file_hash).call()
    except Exception as exc:  # noqa: BLE001
        raise BlockchainAnchorError(f"Could not read anchor record: {exc}") from exc
    return AnchorRecord(anchored_by=anchored_by, timestamp=timestamp, exists=timestamp != 0)


def get_explorer_tx_url(tx_hash: Optional[str]) -> Optional[str]:
    """
    Builds a clickable block-explorer URL for a transaction hash (e.g.
    Polygonscan Amoy: https://amoy.polygonscan.com/tx/0x...), so the
    frontend can link out to independent, third-party proof of the
    transaction rather than only trusting this API's own record of it.

    Never raises: returns None if there's no tx_hash, or no known/configured
    explorer for the current BLOCKCHAIN_CHAIN_ID. This is a pure string
    operation -- it never touches the RPC node -- so it works even while the
    chain is unreachable.
    """
    if not tx_hash:
        return None
    base = settings.BLOCKCHAIN_EXPLORER_BASE_URL or _KNOWN_EXPLORERS.get(
        settings.BLOCKCHAIN_CHAIN_ID, ""
    )
    if not base:
        return None
    return f"{base.rstrip('/')}/{tx_hash}"


def reset_connection_cache() -> None:
    """Drops the cached Web3 connection. Mainly useful for tests, or after
    changing BLOCKCHAIN_* settings at runtime."""
    _get_web3.cache_clear()
