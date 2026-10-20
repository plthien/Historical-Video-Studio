"""SQLite revisions + atomically published immutable story snapshots and artifact metadata."""
from __future__ import annotations
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from backend.app.contracts import ContractViolation
from backend.app.projects.models import StoryCandidate
from backend.app.assets.store import ArtifactStore

_PROJECT = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,63}$")


class ProjectStore:
    def __init__(self, database: str | Path, media_root: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts = ArtifactStore(media_root)
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY, title TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS story_candidates (
                    project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    sha256 TEXT NOT NULL, story_json BLOB NOT NULL,
                    gate_state TEXT NOT NULL DEFAULT 'DRAFT' CHECK (gate_state = 'DRAFT'),
                    PRIMARY KEY (project_id, revision),
                    FOREIGN KEY (project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    sha256 TEXT PRIMARY KEY, byte_count INTEGER NOT NULL, kind TEXT NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE
                );
            """)

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def create_project(self, project_id: str, title: str) -> None:
        if not _PROJECT.fullmatch(project_id) or not title.strip():
            raise ContractViolation("PROJECT_INVALID", project_id, "Use a valid project ID and nonempty title.")
        with self._transaction() as db:
            db.execute("INSERT INTO projects (project_id, title) VALUES (?, ?)", (project_id, title))

    def revision(self, project_id: str) -> int:
        with self._connection() as db:
            row = db.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise ContractViolation("PROJECT_NOT_FOUND", project_id, "Create the project before importing.")
        return row[0]

    def import_story(self, candidate: StoryCandidate, expected_revision: int) -> int:
        from backend.app.projects.gates import GateService
        GateService(self)  # ensure the gate ledger exists before same-transaction invalidation
        with self._transaction() as db:
            row = db.execute("SELECT revision FROM projects WHERE project_id=?",
                             (candidate.project_id,)).fetchone()
            if row is None:
                raise ContractViolation("PROJECT_NOT_FOUND", candidate.project_id, "Create project before import.")
            if row[0] != expected_revision:
                raise ContractViolation("REVISION_CONFLICT", candidate.project_id,
                                        "Reload the project and resubmit against current revision.")
            # Validate canonical bytes again: do not trust forged candidate dataclass constructors.
            checked = StoryCandidate.parse(candidate.canonical_bytes)
            if checked.sha256 != candidate.sha256 or checked.project_id != candidate.project_id:
                raise ContractViolation("STORY_SHA_MISMATCH", candidate.project_id,
                                        "Re-validate the story candidate against original content.")
            previous = db.execute("SELECT sha256,story_json FROM story_candidates WHERE project_id=? "
                                  "ORDER BY revision DESC LIMIT 1", (candidate.project_id,)).fetchone()
            if previous and previous[0] == candidate.sha256:
                return row[0]  # same canonical content: keep approval and current revision
            new_revision = row[0] + 1
            if previous:
                # New source truth invalidates dependent snapshots in this SAME transaction.
                # Relevance-specific G3 invalidation remains owned by its asset binding logic.
                from backend.app.projects.revisions import mark_stale
                mark_stale(db, candidate.project_id, "story_text")
                old_story, new_story = json.loads(previous[1]), checked.data()
                # Only asset-relevant edits stale G3. Preserve independent approved source bytes.
                def relevance(story):
                    return (story["asset_requirements"],
                            [(s["section_id"], s["asset_requirement_refs"]) for s in story["sections"]],
                            [(s["setup_id"], s["requirement_refs"]) for s in story["visual_setups"]])
                if relevance(old_story) != relevance(new_story):
                    mark_stale(db, candidate.project_id, "story_assets")
            db.execute("INSERT INTO story_candidates (project_id, revision, sha256, story_json)"
                       " VALUES (?, ?, ?, ?)",
                       (candidate.project_id, new_revision, candidate.sha256, candidate.canonical_bytes))
            db.execute("UPDATE projects SET revision=? WHERE project_id=? AND revision=?",
                       (new_revision, candidate.project_id, row[0]))
            return new_revision

    def get_story(self, project_id: str, revision: int | None = None) -> StoryCandidate:
        with self._connection() as db:
            if revision is None:
                row = db.execute("SELECT s.sha256, s.story_json FROM story_candidates s "
                                 "JOIN projects p ON p.project_id=s.project_id AND s.revision<=p.revision "
                                 "WHERE s.project_id=? ORDER BY s.revision DESC LIMIT 1", (project_id,)).fetchone()
            else:
                row = db.execute("SELECT sha256, story_json FROM story_candidates WHERE project_id=? AND revision=?",
                                 (project_id, revision)).fetchone()
        if row is None:
            raise ContractViolation("STORY_NOT_FOUND", project_id, "Import a story candidate first.")
        result = StoryCandidate.parse(row[1])
        if row[0] != result.sha256 or result.project_id != project_id or row[1] != result.canonical_bytes:
            raise ContractViolation("STORY_SHA_MISMATCH", project_id, "Restore unchanged candidate snapshot bytes.")
        return result

    def put_artifact(self, data: bytes, kind: str, claimed_sha256: str | None = None) -> str:
        if not kind or len(kind) > 64:
            raise ContractViolation("ARTIFACT_KIND_INVALID", kind, "Specify a short nonempty artifact kind.")
        # Serialize publication with the metadata commit. Roll back newly published original on failed insert.
        with self._transaction() as db:
            digest, newly_created = self.artifacts.put(data, claimed_sha256)
            try:
                path = self.artifacts.path(digest)
                relative = str(path.relative_to(self.artifacts.root)).replace("\\", "/")
                db.execute("INSERT OR IGNORE INTO artifacts(sha256, byte_count, kind, relative_path)"
                           " VALUES (?, ?, ?, ?)", (digest, len(data), kind, relative))
                row = db.execute("SELECT byte_count, kind, relative_path FROM artifacts WHERE sha256=?",
                                 (digest,)).fetchone()
                if row != (len(data), kind, relative):
                    raise ContractViolation("ARTIFACT_METADATA_CONFLICT", digest, "Restore correct artifact metadata.")
            except BaseException:
                if newly_created:
                    self.artifacts.path(digest).unlink(missing_ok=True)
                raise
        return digest

    def get_artifact(self, sha256: str) -> bytes:
        with self._connection() as db:
            row = db.execute("SELECT byte_count, relative_path FROM artifacts WHERE sha256=?",
                             (sha256,)).fetchone()
        if row is None:
            raise ContractViolation("ARTIFACT_NOT_FOUND", sha256, "Register the original artifact first.")
        if row[1] != str(self.artifacts.path(sha256).relative_to(self.artifacts.root)).replace("\\", "/"):
            raise ContractViolation("ARTIFACT_METADATA_CONFLICT", sha256, "Repair immutable storage metadata.")
        data = self.artifacts.read(sha256)
        if len(data) != row[0]:
            raise ContractViolation("ARTIFACT_SIZE_MISMATCH", sha256, "Restore original file and metadata.")
        return data
