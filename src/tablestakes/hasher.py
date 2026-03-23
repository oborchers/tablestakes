"""Content hashing for optimistic concurrency control."""

import hashlib


def compute_hash(raw_content: str) -> str:
    """Compute SHA-256 hash truncated to 12 hex chars.

    The hash is computed on the raw file content (exact substring),
    not on any normalized or converted form.
    """
    return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()[:12]
