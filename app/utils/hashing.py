import hashlib
from pathlib import Path

CHUNK_SIZE = 1024 * 1024  # 1MB


def sha256_of_file(path: Path) -> str:
    """Stream a file through SHA-256 so large evidence files (video) don't
    have to be loaded into memory at once."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    """SHA-256 of an in-memory byte string. Used only where there is no
    file to hash -- currently just the canonical case-closure statement
    signed in app/routers/cases.py close_case (see app/utils/signing.py).
    Every document keeps using sha256_of_file above; this is additive, not
    a replacement for the existing hashing logic."""
    return hashlib.sha256(data).hexdigest()

