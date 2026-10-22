"""B1-01: exact T01–T10 payload dispatch; never invent missing authored facts."""
from __future__ import annotations

from backend.app.contracts import ContractViolation

TEMPLATES = frozenset(f"T{i:02d}" for i in range(1, 11))


def require_payload(setup: dict, supplied: dict) -> dict:
    sid = setup["setup_id"]
    template = setup.get("preferred_template")
    if template not in TEMPLATES:
        raise ContractViolation("TEMPLATE_UNKNOWN", sid,
                                "Select a canonical T01–T10 template for this authored setup.")
    if not isinstance(supplied, dict) or supplied.get("template_id") != template:
        raise ContractViolation("TEMPLATE_PAYLOAD_MISMATCH", sid,
                                "Supply the matching complete authored template payload; never synthesize quotes, maps, or claims.")
    # The canonical schema and template-specific semantic validator perform the
    # complete per-T01..T10 cardinality and reference checks after normalization.
    # These extra guards keep route geography and causal annotation distinct.
    if template == "T04" and not supplied.get("route_geometry_ref"):
        raise ContractViolation("ROUTE_GEOMETRY_MISSING", sid,
                                "Select an evidence-backed route LineString or explicitly approved schematic.")
    if template == "T10" and ("route_geometry_ref" in supplied or "route_truthfulness" in supplied):
        raise ContractViolation("EDITORIAL_ROUTE_INVALID", sid,
                                "Causal relationship connectors are not geographic routes.")
    if template == "T07":
        before, after = supplied.get("before_map"), supplied.get("after_map")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ContractViolation("MAP_PAIR_NOT_DISTINCT", sid,
                                    "Supply two reviewed and separately dated period map states.")
        if (before.get("map_requirement_id") == after.get("map_requirement_id") or
                before.get("year") == after.get("year")):
            raise ContractViolation("MAP_PAIR_NOT_DISTINCT", sid,
                                    "Before and after must have distinct map identities and years.")
    return supplied
