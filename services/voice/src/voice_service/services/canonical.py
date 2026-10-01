"""One canonical JSON hashing definition (CLAUDE.md §6): every content hash in voice uses it."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_sha256(payload: Any) -> str:
    """Full sha256 hex of ``payload`` serialised with sorted keys and no whitespace."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
