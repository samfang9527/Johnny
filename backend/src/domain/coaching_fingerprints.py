"""Stable content hashes; database timestamps and presentation copy are excluded by callers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any


def canonical_fingerprint(value: Any) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(key): normalize(item[key]) for key in sorted(item)}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item.normalize())
        return item
    encoded = json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()
