"""Explicit edit-to-downstream staleness map; never rewrite G1 facts or original bytes."""
from __future__ import annotations
from backend.app.contracts import ContractViolation
from backend.app.projects.gates import GateService

_DOWNSTREAM = {
    "scene_crop": ("G4", "G5"),
    "scene_layout": ("G4", "G5"),
    "render_retry": ("G5",),
    "voice_audio": ("G2", "G4", "G5"),
    "asset_replace": ("G3", "G4", "G5"),
    "story_text": ("G1", "G2", "G4", "G5"),
    "claim_review": ("G1", "G4", "G5"),
    "story_assets": ("G3", "G4", "G5"),
    "numeric_series": ("G4", "G5"),
    "g3_choice_set": ("G3", "G4", "G5"),
    "g3_derivative": ("G3", "G4", "G5"),
}


def mark_stale(db, project_id: str, change_kind: str) -> tuple[str, ...]:
    gates = _DOWNSTREAM[change_kind]
    for gate in gates:
        has_approval = db.execute(
            "SELECT 1 FROM gate_heads WHERE project_id=? AND gate_id=?",
            (project_id, gate)).fetchone()
        if not has_approval:
            # Invalidate any unapproved draft pointer, not an approval that never existed.
            # Candidate media/history bytes remain immutable; a future owner must publish
            # fresh dependency evidence before its first approval.
            db.execute("DELETE FROM gate_candidates WHERE project_id=? AND gate_id=?",
                       (project_id, gate))
            db.execute("DELETE FROM gate_staleness WHERE project_id=? AND gate_id=?",
                       (project_id, gate))
            continue
        db.execute("INSERT INTO gate_staleness VALUES(?,?,?) "
                   "ON CONFLICT(project_id,gate_id) DO UPDATE SET cause=excluded.cause",
                   (project_id, gate, change_kind))
    return gates


def invalidate(service: GateService, project_id: str, change_kind: str, expected_revision: int) -> dict:
    if change_kind not in _DOWNSTREAM:
        raise ContractViolation("REVISION_CHANGE_UNKNOWN", change_kind, "Select an allowed edit kind.")
    with service.store._transaction() as db:
        revision = service._check_revision(db, project_id, expected_revision)
        mark_stale(db, project_id, change_kind)
        db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision + 1, project_id))
    return {"project_revision": revision + 1, "stale_gates": list(_DOWNSTREAM[change_kind])}
