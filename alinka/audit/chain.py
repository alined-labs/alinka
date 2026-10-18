"""RFC 8785 canonical bytes and the hash chain: hash = sha256(prev_hash + bytes)."""

from __future__ import annotations

import hashlib
from typing import Any

import rfc8785

from alinka.types import DecisionRecord

GENESIS = "0" * 64


def canonical_bytes(fields: dict[str, Any]) -> bytes:
    """Canonical bytes of a record's JSON form, without its own `hash`."""
    return rfc8785.dumps({k: v for k, v in fields.items() if k != "hash"})


def link(prev_hash: str, data: bytes) -> str:
    return hashlib.sha256(prev_hash.encode("ascii") + data).hexdigest()


def seal(fields: dict[str, Any]) -> DecisionRecord:
    """Validate the unsealed fields, then fill `hash` from prev_hash and the canonical bytes."""
    draft = DecisionRecord.model_validate({**fields, "hash": ""})
    data = canonical_bytes(draft.model_dump(mode="json"))
    return draft.model_copy(update={"hash": link(draft.prev_hash, data)})


def stored_bytes(record: DecisionRecord) -> bytes:
    """What the log stores: the canonical bytes of the whole record, hash included."""
    return rfc8785.dumps(record.model_dump(mode="json"))
