"""Immutable story representation and durable revision identity."""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from backend.app.contracts import ContractViolation, validate_story_package


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ContractViolation("JSON_DUPLICATE_KEY", "/" + key, "Remove duplicate keys from the imported JSON.")
        obj[key] = value
    return obj


def _bad_constant(constant: str):
    raise ContractViolation("JSON_NONFINITE", "/", f"Invalid JSON numeric constant: {constant}.")


@dataclass(frozen=True, slots=True)
class StoryCandidate:
    project_id: str
    sha256: str
    canonical_bytes: bytes

    @classmethod
    def parse(cls, raw: bytes | str | dict[str, Any]) -> "StoryCandidate":
        try:
            if isinstance(raw, (bytes, str)):
                payload = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_bad_constant)
            else:
                payload = raw
            validate_story_package(payload)
            content = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                 sort_keys=True, separators=(",", ":")).encode("utf-8")
        except (UnicodeError, json.JSONDecodeError, TypeError, OverflowError, ValueError) as exc:
            if isinstance(exc, ContractViolation):
                raise
            raise ContractViolation("STORY_JSON_INVALID", "/", "Provide a valid UTF-8 JSON StoryPackage.", message=str(exc)) from exc
        return cls(project_id=payload["project"]["project_id"], sha256=hashlib.sha256(content).hexdigest(),
                   canonical_bytes=content)

    def data(self) -> dict[str, Any]:
        return json.loads(self.canonical_bytes)
