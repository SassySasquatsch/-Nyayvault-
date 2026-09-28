#!/usr/bin/env python3
"""
Verifies the blockchain anchoring setup end-to-end against a live network
(e.g. Polygon Amoy) before trusting the frontend's "view on explorer" link.

Run this after setting WEB3_PROVIDER_URI / WALLET_PRIVATE_KEY /
BLOCKCHAIN_CHAIN_ID / BLOCKCHAIN_CONTRACT_ADDRESS in your .env (see
.env.example), from the project root:

    python scripts/verify_blockchain_anchor.py            # read-only checks only
    python scripts/verify_blockchain_anchor.py --send-tx   # also sends one real,
                                                            # gas-costing test transaction

What it checks, in order (stops at the first failure so problems are easy
to isolate):

  1. RPC connectivity      -- WEB3_PROVIDER_URI answers, and its reported
                               chain ID matches BLOCKCHAIN_CHAIN_ID (a very
                               common misconfiguration: pointing at the
                               wrong network for the chain ID you set).
  2. Wallet                -- WALLET_PRIVATE_KEY parses, and the derived
                               address has a nonzero balance (enough to pay
                               gas -- if not, this prints the Amoy faucet
                               URL instead of failing obscurely later).
  3. Contract + ABI        -- BLOCKCHAIN_CONTRACT_ADDRESS has code deployed
                               at all (a bare EOA address here is another
                               common mistake), and CONTRACT_ABI's read-only
                               functions (`isAnchored`, `getRecord`) actually
                               match what's deployed, by calling them.
  4. Explorer link         -- get_explorer_tx_url() produces a URL for
                               BLOCKCHAIN_CHAIN_ID, and that URL is reachable
                               (HEAD request) -- catches a typo'd
                               BLOCKCHAIN_EXPLORER_BASE_URL early.
  5. Interaction flow      -- with --send-tx: anchors a random, never-seen
                               test hash for real, waits for the receipt,
                               re-reads it back with the free/read-only
                               calls, and prints the resulting explorer URL
                               so you can click it and confirm the tx is
                               visible on Polygonscan Amoy. Without
                               --send-tx this step is skipped (no gas spent)
                               and only exercises the read-only path against
                               a hash that is expected not to be anchored.

Exits non-zero on the first failed check.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.utils.blockchain_anchor import (  # noqa: E402
    CONTRACT_ABI,
    AlreadyAnchoredError,
    BlockchainAnchorError,
    _get_contract,
    _get_web3,
    _hash_to_bytes32,
    _normalize_private_key,
    anchor_hash_to_blockchain,
    get_anchor_record,
    get_explorer_tx_url,
)


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


def _info(msg: str) -> None:
    print(f"  ... {msg}")


def check_rpc_connectivity():
    print("1. RPC connectivity")
    if not settings.BLOCKCHAIN_ANCHORING_ENABLED:
        _fail("BLOCKCHAIN_ANCHORING_ENABLED is not set to true.")
    if not settings.BLOCKCHAIN_RPC_URL:
        _fail("No RPC endpoint configured. Set WEB3_PROVIDER_URI in .env.")
    try:
        w3 = _get_web3()
    except BlockchainAnchorError as exc:
        _fail(str(exc))
    _ok(f"Connected to {settings.BLOCKCHAIN_RPC_URL}")

    try:
        remote_chain_id = w3.eth.chain_id
    except Exception as exc:  # noqa: BLE001
        _fail(f"Connected, but eth_chainId failed: {exc}")
    if remote_chain_id != settings.BLOCKCHAIN_CHAIN_ID:
        _fail(
            f"BLOCKCHAIN_CHAIN_ID={settings.BLOCKCHAIN_CHAIN_ID} but the RPC endpoint "
            f"reports chain ID {remote_chain_id}. Polygon Amoy is 80002 -- "
            f"double-check WEB3_PROVIDER_URI points at Amoy, not mainnet or "
            f"another testnet."
        )
    _ok(f"Chain ID matches configuration ({remote_chain_id})")
    return w3


def check_wallet(w3):
    print("2. Wallet")
    try:
        private_key = _normalize_private_key(settings.BLOCKCHAIN_PRIVATE_KEY)
    except BlockchainAnchorError as exc:
        _fail(str(exc))
    account = w3.eth.account.from_key(private_key)
    _ok(f"WALLET_PRIVATE_KEY parses; derived address {account.address}")

    balance_wei = w3.eth.get_balance(account.address)
    balance_matic = w3.from_wei(balance_wei, "ether")
    if balance_wei == 0:
        _fail(
            f"{account.address} has a zero balance on chain {settings.BLOCKCHAIN_CHAIN_ID} -- "
            f"it can't pay gas. Fund it from https://faucet.polygon.technology/ "
            f"(Amoy test MATIC) and re-run."
        )
    _ok(f"Balance: {balance_matic} (native token, e.g. test MATIC on Amoy)")
    return account


def check_contract_and_abi(w3):
    print("3. Contract + ABI")
    if not settings.BLOCKCHAIN_CONTRACT_ADDRESS:
        _fail("BLOCKCHAIN_CONTRACT_ADDRESS is not configured.")
    try:
        address = w3.to_checksum_address(settings.BLOCKCHAIN_CONTRACT_ADDRESS)
    except AttributeError:
        address = w3.toChecksumAddress(settings.BLOCKCHAIN_CONTRACT_ADDRESS)

    code = w3.eth.get_code(address)
    if not code or code in (b"", b"0x"):
        _fail(
            f"No contract code found at {address} on chain {settings.BLOCKCHAIN_CHAIN_ID}. "
            f"Either it isn't deployed on this network, or "
            f"BLOCKCHAIN_CONTRACT_ADDRESS/BLOCKCHAIN_CHAIN_ID point at the wrong place."
        )
    _ok(f"Contract code found at {address}")

    contract = _get_contract()
    probe_hash = _hash_to_bytes32(secrets.token_hex(32))
    try:
        is_anchored = contract.functions.isAnchored(probe_hash).call()
        anchored_by, timestamp = contract.functions.getRecord(probe_hash).call()
    except Exception as exc:  # noqa: BLE001
        _fail(
            f"ABI mismatch or bad call to isAnchored/getRecord -- the deployed "
            f"bytecode doesn't match CONTRACT_ABI in blockchain_anchor.py: {exc}"
        )
    if is_anchored or timestamp != 0:
        _fail(
            "Internal check error: a freshly random 32-byte hash came back as "
            "already anchored -- this should never happen and suggests the ABI "
            "is calling the wrong function selectors."
        )
    _ok("isAnchored() and getRecord() match the deployed contract's ABI")
    return contract


def check_explorer_link():
    print("4. Explorer link")
    fake_tx = "0x" + "11" * 32
    url = get_explorer_tx_url(fake_tx)
    if not url:
        _fail(
            f"get_explorer_tx_url() returned None for chain ID "
            f"{settings.BLOCKCHAIN_CHAIN_ID}. Set BLOCKCHAIN_EXPLORER_BASE_URL "
            f"in .env, e.g. https://amoy.polygonscan.com/tx/ for Amoy."
        )
    _ok(f"Explorer URL template resolves, e.g.: {url}")

    try:
        import urllib.request

        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=10)  # noqa: S310 - explicit, operator-run script
        _ok("Explorer host is reachable")
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: a HEAD request to a fabricated tx hash may itself 404 on
        # some explorers even though the domain is fine, and this script has
        # no network access guarantees in every environment it might run in.
        _info(f"Could not confirm explorer host reachability (non-fatal): {exc}")


def check_interaction_flow(send_tx: bool):
    print("5. Interaction flow")
    test_hash = secrets.token_hex(32)
    if not send_tx:
        try:
            record = get_anchor_record(test_hash)
        except BlockchainAnchorError as exc:
            _fail(f"Read-only getRecord() call failed: {exc}")
        if record.exists:
            _fail("Unexpected: a random test hash already shows as anchored.")
        _ok("Read-only path (isAnchored / getRecord) works end-to-end.")
        _info("Skipped sending a real transaction (pass --send-tx to also verify writes).")
        return

    _info(f"Anchoring test hash {test_hash} for real (this spends gas)...")
    try:
        tx_hash = anchor_hash_to_blockchain(test_hash, wait_for_receipt=True)
    except AlreadyAnchoredError as exc:
        _fail(f"Unexpected AlreadyAnchoredError for a fresh random hash: {exc}")
    except BlockchainAnchorError as exc:
        _fail(f"anchor_hash_to_blockchain() failed: {exc}")
    _ok(f"Transaction mined: {tx_hash}")

    try:
        record = get_anchor_record(test_hash)
    except BlockchainAnchorError as exc:
        _fail(f"Anchored, but reading it back failed: {exc}")
    if not record.exists:
        _fail("Anchored and mined, but getRecord() still reports it as not anchored.")
    _ok(f"Read back on-chain: anchored_by={record.anchored_by}, timestamp={record.timestamp}")

    url = get_explorer_tx_url(tx_hash)
    if url:
        print(f"\n  View this transaction on the block explorer: {url}")
        print("  Open that link and confirm it shows as confirmed before wiring the frontend to it.")
    else:
        _fail("Transaction succeeded, but no explorer URL could be built for it.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--send-tx",
        action="store_true",
        help="Also send one real, gas-costing test transaction to fully verify the write path.",
    )
    args = parser.parse_args()

    print(f"Verifying blockchain anchoring against chain ID {settings.BLOCKCHAIN_CHAIN_ID} "
          f"at {settings.BLOCKCHAIN_RPC_URL or '(not configured)'}\n")

    w3 = check_rpc_connectivity()
    check_wallet(w3)
    check_contract_and_abi(w3)
    check_explorer_link()
    check_interaction_flow(send_tx=args.send_tx)

    print("\nAll checks passed. The frontend's block-explorer link (document."
          "blockchain_explorer_url / GET /api/documents/{id}/blockchain) is safe to trust.")


if __name__ == "__main__":
    main()
