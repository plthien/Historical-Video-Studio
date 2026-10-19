"""A1 import owner. HTTP wiring belongs to A1-06; never approve at import."""
from backend.app.projects.models import StoryCandidate
from backend.app.projects.storage import ProjectStore


def import_story(store: ProjectStore, raw_json: bytes | str, expected_revision: int) -> dict:
    candidate = StoryCandidate.parse(raw_json)
    revision = store.import_story(candidate, expected_revision)
    return {"project_id": candidate.project_id, "project_revision": revision,
            "candidate_sha256": candidate.sha256, "gate_id": "G1",
            "gate_state": "DRAFT", "next_action": "REVIEW_G1"}
