"""A1 behavioral assertions over real JSON Schema, SQLite and immutable bytes."""
import copy
import json
import sqlite3
from pathlib import Path
import pytest
from backend.app.api.imports import import_story
from backend.app.contracts import ContractViolation, validate_visual_blueprint
from backend.app.projects.models import StoryCandidate
from backend.app.projects.storage import ProjectStore

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def story():
    return json.loads((ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "db.sqlite", tmp_path / "originals")


def test_schema_import_24_sections_and_g1_draft(story, store):
    assert len(story["sections"]) == 24
    project = story["project"]
    store.create_project(project["project_id"], project["title"])
    r = import_story(store, json.dumps(story), 0)
    assert r["gate_state"] == "DRAFT"
    assert store.revision(project["project_id"]) == 1
    assert store.get_story(project["project_id"]).data() == story
    reopened = ProjectStore(store.database, store.artifacts.root)
    assert reopened.get_story(project["project_id"]).sha256 == r["candidate_sha256"]


def test_schema_import_rejects_unknown_ids_without_side_effects(story, store):
    store.create_project(story["project"]["project_id"], "Real persisted project")
    story["sections"][0]["claim_refs"] = ["claim_DOES_NOT_EXIST"]
    with pytest.raises(ContractViolation) as err:
        import_story(store, json.dumps(story), 0)
    assert err.value.code == "CROSS_REFERENCE_MISSING"
    assert store.revision(story["project"]["project_id"]) == 0


def test_schema_import_rejects_duplicate_json_keys_and_invalid_enum(story):
    with pytest.raises(ContractViolation, match="JSON_DUPLICATE_KEY"):
        StoryCandidate.parse('{"schema_version":1,"schema_version":2}')
    story["visual_setups"][0]["preferred_template"] = "T11"
    with pytest.raises(ContractViolation) as err:
        StoryCandidate.parse(json.dumps(story))
    assert err.value.code == "SCHEMA_INVALID"
    assert "visual_setups" in err.value.path


def test_schema_template_oneof_and_invalid_variant():
    original = json.loads((ROOT / "contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json").read_text())
    blueprint = json.loads((ROOT / "contracts/examples/visual_cases/VisualBlueprint.visual_cases.synthetic.json").read_text())
    validate_visual_blueprint(original, blueprint)
    tags = {p["template_payload"]["template_id"] for p in blueprint["setup_plans"]}
    assert tags == {f"T{i:02}" for i in range(1, 11)}
    bad = copy.deepcopy(blueprint)
    bad["setup_plans"][0]["template_payload"]["template_id"] = "T99"
    with pytest.raises(ContractViolation, match="SCHEMA_INVALID"):
        validate_visual_blueprint(original, bad)


def test_storage_artifact_corruption_and_reopen(store):
    data = b"\x00\x00original binary\xff"
    digest = store.put_artifact(data, "original")
    assert ProjectStore(store.database, store.artifacts.root).get_artifact(digest) == data
    path = store.artifacts.path(digest)
    path.write_bytes(b"tampered")
    with pytest.raises(ContractViolation, match="ARTIFACT_CORRUPT"):
        store.get_artifact(digest)
    with pytest.raises(ContractViolation, match="ARTIFACT_CORRUPT"):
        store.put_artifact(data, "original")


def test_storage_revision_conflict_rollbacks_and_never_approves(story, store):
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Fixture")
    candidate = StoryCandidate.parse(story)
    store.import_story(candidate, 0)
    with pytest.raises(ContractViolation, match="REVISION_CONFLICT"):
        store.import_story(candidate, 0)
    assert store.revision(project_id) == 1
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM story_candidates").fetchone()[0] == 1
        assert db.execute("SELECT DISTINCT gate_state FROM story_candidates").fetchone()[0] == "DRAFT"


def test_artifact_mismatched_sha_leaves_no_metadata(store):
    with pytest.raises(ContractViolation, match="ARTIFACT_SHA_MISMATCH"):
        store.put_artifact(b"original", "original", "0" * 64)
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0


def test_storage_partial_sqlite_revision_rollback(story, store):
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Fixture")
    candidate = StoryCandidate.parse(story)
    with sqlite3.connect(store.database) as db:
        db.execute("CREATE TRIGGER reject_revision BEFORE UPDATE OF revision ON projects "
                   "BEGIN SELECT RAISE(ABORT, 'simulated disk transaction failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        store.import_story(candidate, 0)
    assert store.revision(project_id) == 0
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM story_candidates").fetchone()[0] == 0
