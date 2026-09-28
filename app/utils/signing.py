"""
Digital signatures for actions that need legal/evidentiary weight.

Purpose: give every user an RSA keypair at account creation (see
app/routers/users.py create_user), and use it to sign the SHA-256 hash a
document already has (app/utils/hashing.py) -- never a second, competing
hash -- so a forensic report upload, a court order/judgment upload, or a
judge's case-closure action can later be proven to have come from that
specific person and not been altered since, independent of the app's own
say-so.

Design constraints this module respects (same shape as
app/utils/blockchain_anchor.py):
  - The database remains the single source of truth. This module does
    exactly one thing: turn a hash + a private key into a signature, or a
    hash + a signature + a public key into a valid/invalid verdict. It
    never reads/writes case, document or user rows itself -- callers (see
    app/routers/documents.py, app/routers/cases.py) own that.
  - `cryptography` is imported lazily, inside functions, not at module
    import time. If it isn't installed, importing this module -- and the
    rest of the app -- still works with zero setup.
  - Every failure mode (library missing, corrupt/undecodable key, signature
    that doesn't match) raises a clear, typed exception instead of hanging,
    crashing, or -- worst of all -- silently returning a fabricated result.
    Callers treat a SigningError on the *signing* side as non-fatal to the
    upload/action itself (the record is simply left unsigned, exactly like
    a document that never got anchored on-chain); callers on the
    *verification* side surface it to the caller rather than guessing.

Key storage
-----------
Each user's private key is generated once, at account creation, as a
PKCS#8 DER/PEM structure encrypted with a passphrase derived from the
server's own SECRET_KEY (app/config.py) via PBKDF2-HMAC-SHA256. This keeps
a stolen database backup alone from yielding usable private keys (an
attacker also needs SECRET_KEY), without requiring an external KMS/HSM for
this prototype. The public key is stored in plaintext -- it is public by
definition, and the whole point of asymmetric signing is that verifying a
signature never requires the private key.

For anything beyond local/demo use, swap `_derive_key_encryption_key()` for
a real per-tenant key held in a KMS/HSM, exactly as the README already
flags for SECRET_KEY and WALLET_PRIVATE_KEY.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Optional

from app.config import settings

# RSA-PSS with SHA-256 is the algorithm this module actually produces;
# stored alongside every signature so a future migration to e.g. ECDSA
# doesn't strand old signatures with an ambiguous verification method.
ALGORITHM = "RSA-PSS-SHA256"
_KEY_SIZE_BITS = 2048


class SigningError(Exception):
    """Raised for any signing/verification failure: library missing,
    unreadable/undecodable key material, or (during verification) a
    signature that does not match. Always safe to catch broadly and treat
    as "no signature could be produced/confirmed" -- never as permission to
    fabricate a result."""


class InvalidSignatureError(SigningError):
    """Raised specifically when a signature does not verify against the
    given public key and hash. Distinguished from other SigningErrors so
    callers can tell "provably invalid" apart from "could not be checked
    at all" (missing library, corrupt key, etc.)."""


def _require_cryptography():
    try:
        from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils as asym_utils
        from cryptography.hazmat.primitives import hashes, serialization
    except ImportError as exc:
        raise SigningError(
            "The 'cryptography' library is not installed. Run "
            "`pip install cryptography` (see requirements.txt). No signature "
            "was produced or verified -- NyayVault never fabricates a result."
        ) from exc
    return padding, rsa, hashes, serialization, asym_utils


def _derive_key_encryption_key() -> bytes:
    """A 32-byte key derived from the server's SECRET_KEY via PBKDF2, used
    to encrypt (never to sign with) each user's private key at rest. Never
    the SECRET_KEY itself, and never written anywhere."""
    salt = b"nyayvault-signing-key-v1"  # fixed, non-secret domain-separation salt
    return hashlib.pbkdf2_hmac("sha256", settings.SECRET_KEY.encode("utf-8"), salt, 200_000, dklen=32)


def is_available() -> bool:
    """True if this process can sign/verify at all right now. Never raises;
    callers use this to decide whether to even attempt signing, exactly
    like blockchain_anchor.py callers check BLOCKCHAIN_ANCHORING_ENABLED
    before anchoring."""
    try:
        _require_cryptography()
        return True
    except SigningError:
        return False


@dataclass(frozen=True)
class KeyPair:
    private_key_encrypted_pem: str  # PKCS#8 PEM, encrypted -- store as-is
    public_key_pem: str             # SubjectPublicKeyInfo PEM -- plaintext


def generate_keypair() -> KeyPair:
    """
    Generates a fresh RSA-2048 keypair for a new user. Called once, from
    app/routers/users.py create_user, never re-derived or reused.

    Raises:
        SigningError: 'cryptography' is not installed. The caller (user
            creation) proceeds without keys -- exactly the same
            never-block-the-primary-action posture as a missing
            web3.py/blockchain node for evidence uploads.
    """
    padding, rsa, hashes, serialization, asym_utils = _require_cryptography()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=_KEY_SIZE_BITS)

    encrypted_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(_derive_key_encryption_key()),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return KeyPair(
        private_key_encrypted_pem=encrypted_pem.decode("ascii"),
        public_key_pem=public_pem.decode("ascii"),
    )


def _load_private_key(encrypted_pem: str):
    padding, rsa, hashes, serialization, asym_utils = _require_cryptography()
    try:
        return serialization.load_pem_private_key(
            encrypted_pem.encode("ascii"), password=_derive_key_encryption_key()
        )
    except Exception as exc:  # noqa: BLE001 - wrong SECRET_KEY, corrupt PEM, etc.
        raise SigningError(f"Could not decrypt/parse the signer's private key: {exc}") from exc


def _load_public_key(public_pem: str):
    padding, rsa, hashes, serialization, asym_utils = _require_cryptography()
    try:
        return serialization.load_pem_public_key(public_pem.encode("ascii"))
    except Exception as exc:  # noqa: BLE001 - corrupt/missing key on the user row
        raise SigningError(f"Could not parse the signer's stored public key: {exc}") from exc


@dataclass(frozen=True)
class Signature:
    signature_b64: str
    algorithm: str


def sign_hash(private_key_encrypted_pem: str, sha256_hex: str) -> Signature:
    """
    Signs a document's existing SHA-256 hash (never recomputes or replaces
    it -- see app/utils/hashing.py) with the actor's private key.

    Args:
        private_key_encrypted_pem: the signer's User.private_key_encrypted_pem.
        sha256_hex: the 64-char hex digest already computed for this
            document (Document.hash_sha256), or, for an action with no
            underlying file (case closure), a hash produced by
            app/utils/hashing.sha256_of_bytes over a canonical description
            of the action.

    Returns:
        A Signature with base64-encoded signature bytes and the algorithm
        identifier used, ready to store on a Signature row.

    Raises:
        SigningError: 'cryptography' is unavailable, the key can't be
            decrypted/parsed, or sha256_hex is not a valid digest. Callers
            must treat this as "no signature produced" and continue --
            never as permission to invent one.
    """
    padding, rsa, hashes, serialization, asym_utils = _require_cryptography()
    digest = _digest_bytes(sha256_hex)
    private_key = _load_private_key(private_key_encrypted_pem)

    try:
        # Prehashed: `digest` IS the SHA-256 of the file already (see
        # app/utils/hashing.py) -- this signs that 32-byte value directly
        # rather than hashing it a second time.
        raw_signature = private_key.sign(
            digest,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            asym_utils.Prehashed(hashes.SHA256()),
        )
    except Exception as exc:  # noqa: BLE001 - any RSA-layer failure
        raise SigningError(f"Signing failed: {exc}") from exc

    return Signature(signature_b64=base64.b64encode(raw_signature).decode("ascii"), algorithm=ALGORITHM)


def _digest_bytes(sha256_hex: str) -> bytes:
    cleaned = (sha256_hex or "").strip().lower()
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise SigningError(f"'{sha256_hex}' is not valid hex.") from exc
    if len(raw) != 32:
        raise SigningError(f"Expected a 32-byte SHA-256 hash, got {len(raw)} bytes.")
    return raw


def verify_signature(public_key_pem: str, sha256_hex: str, signature_b64: str, algorithm: str) -> bool:
    """
    Re-verifies a stored signature against a public key and a hash (the
    caller decides which hash: the one recorded at signing time, or the
    file's hash right now -- see GET /api/documents/{id}/signature/verify,
    which uses the *current* file hash so a tampered file fails
    verification even if the signature bytes themselves are intact).

    Returns:
        True if the signature is valid for this exact (public key, hash)
        pair.

    Raises:
        SigningError: 'cryptography' is unavailable, the stored public key
            or signature bytes are corrupt/undecodable, or `algorithm`
            isn't one this module knows how to verify. Never returns True
            or False in these cases -- an inconclusive check must never be
            reported as either a pass or a fail.
    """
    if algorithm != ALGORITHM:
        raise SigningError(
            f"Unsupported signature algorithm '{algorithm}' (expected '{ALGORITHM}')."
        )
    padding, rsa, hashes, serialization, asym_utils = _require_cryptography()
    digest = _digest_bytes(sha256_hex)
    public_key = _load_public_key(public_key_pem)

    try:
        raw_signature = base64.b64decode(signature_b64)
    except Exception as exc:  # noqa: BLE001 - malformed base64 on the stored row
        raise SigningError(f"Stored signature is not valid base64: {exc}") from exc

    from cryptography.exceptions import InvalidSignature

    try:
        public_key.verify(
            raw_signature,
            digest,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            asym_utils.Prehashed(hashes.SHA256()),
        )
        return True
    except InvalidSignature:
        return False
    except Exception as exc:  # noqa: BLE001 - malformed signature bytes, wrong key type, etc.
        raise SigningError(f"Signature verification failed: {exc}") from exc
