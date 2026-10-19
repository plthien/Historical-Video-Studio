"""Canonical schema validation; never fork frozen schema or visual semantics."""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "contracts" / "schema"
sys.path.insert(0, str(ROOT / "scripts"))
from check_design_contracts import ContractError  # noqa: E402
from validate_visual_design import validate_blueprint, validate_directed_story  # noqa: E402


class ContractViolation(ValueError):
    def __init__(self, code: str, path: str, remediation: str, *, message: str | None = None):
        self.code = code
        self.path = path
        self.remediation = remediation
        self.message = message or remediation
        super().__init__(f"{code} at {path}: {self.message}")

    def as_problem(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "remediation": self.remediation, "retryable": False,
                "entity_id": self.path, "blocking_gate": "G1"}


@lru_cache(maxsize=12)
def _validator(name: str) -> Draft202012Validator:
    path = SCHEMAS / f"{name}.schema.json"
    if not path.is_file():  # external caller must not select arbitrary filesystem path
        raise ContractViolation("SCHEMA_UNKNOWN", name, "Use one of the twelve versioned schema names.")
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _path(error: ValidationError) -> str:
    items = list(error.absolute_path)
    return "/" + "/".join(str(i).replace("~", "~0").replace("/", "~1") for i in items)


def validate_document(name: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ContractViolation("SCHEMA_INVALID", "/", "Top-level contract must be a JSON object.")
    validator = _validator(name)
    error = next(iter(validator.iter_errors(payload)), None)
    if error:
        raise ContractViolation("SCHEMA_INVALID", _path(error), "Correct this field against the canonical "
                                f"{name} JSON Schema.", message=error.message)


def _semantic(call, *args) -> None:
    try:
        call(*args)
    except ContractError as error:
        raise ContractViolation(error.code, str(error.path), error.remediation, message=str(error)) from error
    except ValidationError as error:
        raise ContractViolation("SCHEMA_INVALID", _path(error), "Correct the canonical JSON Schema violation.",
                                message=error.message) from error


def validate_story_package(payload: dict[str, Any]) -> None:
    validate_document("StoryPackage.v1", payload)
    _semantic(validate_directed_story, payload)


def validate_visual_blueprint(story: dict[str, Any], blueprint: dict[str, Any]) -> None:
    # The existing validator verifies all ten tagged template payloads, cue/slot/claim references.
    validate_document("VisualBlueprint.v1", blueprint)
    _semantic(validate_blueprint, story, blueprint)
