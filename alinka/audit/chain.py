"""RFC 8785 canonical bytes and the hash chain: hash = sha256(prev_hash + bytes)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    count: int
    head: str
    bad_seq: int | None = None  # 1-based position of the first bad record
    error: str | None = None


def verify_chain(records_bytes: Iterable[bytes]) -> ChainCheck:
    """Re-hash the stored bytes in order; any edit, reorder or gap breaks the chain."""
    prev, n = GENESIS, 0
    for n, raw in enumerate(records_bytes, start=1):
        try:
            obj = json.loads(raw)
            if rfc8785.dumps(obj) != bytes(raw):
                return ChainCheck(False, n - 1, prev, n, "los bytes no son canónicos")
            if obj.get("prev_hash") != prev:
                return ChainCheck(
                    False, n - 1, prev, n, "el enlace con el registro anterior no coincide"
                )
            if obj.get("seq") != n:
                return ChainCheck(False, n - 1, prev, n, "falta un registro o cambió el orden")
            if link(prev, canonical_bytes(obj)) != obj.get("hash"):
                return ChainCheck(False, n - 1, prev, n, "el hash no coincide con el contenido")
        except (ValueError, TypeError, rfc8785.CanonicalizationError) as exc:
            return ChainCheck(False, n - 1, prev, n, f"registro ilegible: {type(exc).__name__}")
        prev = obj["hash"]
    return ChainCheck(True, n, prev)
