"""V1 G4 draft ledger: store-authoritative immutable compiled bytes, never an approval."""
from __future__ import annotations

import json
from hashlib import sha256

from backend.app.contracts import ContractViolation
from backend.app.director.fingerprint import canonical, digest


def _fail(code, project, remedy):
    raise ContractViolation(code, project, remedy)


def _runtime_identity():
    from backend.app.director.fingerprint import ROOT, SOURCES, COMPILER_VERSION
    return {"compiler_version":COMPILER_VERSION,
            "registry_sha256":{key:sha256((ROOT / path).read_bytes()).hexdigest()
                               for key,path in SOURCES.items()}}


def current_gate_heads(store, project):
    from backend.app.projects.gates import GateService
    board = {item["gate_id"]:item["state"] for item in GateService(store).board(project)}
    if any(board.get(gate) != "APPROVED" for gate in ("G1","G2","G3")):
        _fail("COMPILER_GATE_UNAPPROVED",project,"Current G1/G2/G3 approval heads are required.")
    with store._connection() as db:
        rows=db.execute(
            "SELECT gate_id,candidate_sha256,dependency_fingerprint,approval_id "
            "FROM gate_heads WHERE project_id=? AND gate_id IN ('G1','G2','G3') "
            "ORDER BY gate_id",(project,)).fetchall()
    if len(rows)!=3:
        _fail("COMPILER_GATE_UNAPPROVED",project,"An upstream approval head is missing.")
    return {gate:{"candidate_sha256":candidate,"dependency_fingerprint":fingerprint,
                  "approval_id":approval}
            for gate,candidate,fingerprint,approval in rows}


def current_numeric_heads(store, project):
    """Current auxiliary G1 series identity; old events never authorize G4."""
    from backend.app.projects.numeric_series import NumericSeries
    NumericSeries(store)
    with store._connection() as db:
        rows = db.execute("""SELECT e.claim_id,e.series_id,e.approval_id,e.series_sha256
            FROM numeric_series_heads h JOIN numeric_series_events e
              ON e.approval_id=h.approval_id
            WHERE h.project_id=? ORDER BY e.claim_id,e.series_id""", (project,)).fetchall()
    return {claim + ":" + series: {"approval_id": approval, "series_sha256": sha}
            for claim, series, approval, sha in rows}


def ensure(store):
    # This table is deliberately separate from operator gate_heads: a draft is
    # never approval evidence for G4 or G5.
    with store._connection() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS g4_compiled_drafts (
                project_id TEXT PRIMARY KEY REFERENCES projects(project_id),
                generation INTEGER NOT NULL,
                project_revision INTEGER NOT NULL,
                manifest_sha256 TEXT NOT NULL
            )
        """)


def _read_canonical(store, content_sha, project):
    raw = store.get_artifact(content_sha)  # verifies content SHA and byte length
    try:
        obj = json.loads(raw)
        if canonical(obj) != raw or sha256(raw).hexdigest() != content_sha:
            _fail("G4_DRAFT_CORRUPT", project, "Restore exact immutable canonical draft bytes.")
    except (ValueError, TypeError) as exc:
        _fail("G4_DRAFT_CORRUPT", project, "Restore valid canonical JSON draft bytes.")
    return obj


def load(store, project):
    ensure(store)
    with store._connection() as db:
        head = db.execute(
            "SELECT generation,project_revision,manifest_sha256 "
            "FROM g4_compiled_drafts WHERE project_id=?", (project,)).fetchone()
    if not head:
        _fail("G4_DRAFT_UNREGISTERED", project,
              "Run compile_from_store against currently approved G1/G2/G3 first.")
    generation, revision, manifest_sha = head
    manifest = _read_canonical(store, manifest_sha, project)
    if manifest.get("runtime_identity") != _runtime_identity():
        _fail("G4_DRAFT_STALE", project,
              "Compiler or registered motion/layout definitions changed; recompile with approval.")
    if sorted(manifest.get("gate_heads",{})) != ["G1","G2","G3"]:
        _fail("G4_DRAFT_CORRUPT", project, "Immutable draft requires all three approval identities.")
    if (manifest.get("schema_version") != "G4CompiledDraft.v1"
            or manifest.get("project_id") != project
            or manifest.get("generation") != generation
            or manifest.get("project_revision") != revision
            or manifest.get("map_context_sha256") != digest(manifest.get("maps"))
            or manifest.get("map_requests_sha256") != digest(manifest.get("map_requests"))):
        _fail("G4_DRAFT_CORRUPT", project, "Stored draft manifest is inconsistent with SQLite head.")
    if manifest.get("numeric_series_heads",{}) != current_numeric_heads(store,project):
        _fail("G4_SOURCE_STALE", project, "Auxiliary G1 numeric series changed; fresh compile required.")
    timeline = _read_canonical(store, manifest["timeline_sha256"], project)
    blueprint = _read_canonical(store, manifest["blueprint_sha256"], project)
    if (timeline.get("project_id") != project or blueprint.get("project_id") != project
            or timeline.get("dependency_fingerprint") != manifest.get("dependency_fingerprint")
            or timeline.get("story_sha256") != blueprint.get("story_revision_sha256")
            or timeline.get("asset_snapshot_sha256") != manifest.get("asset_snapshot_sha256")
            or timeline.get("word_map_sha256") != manifest.get("word_map_sha256")
            or timeline.get("audio_sha256") != manifest.get("audio_sha256")):
        _fail("G4_DRAFT_CORRUPT", project, "Stored compiled draft and provenance manifest disagree.")
    return {"generation":generation, "revision":revision, "manifest_sha256":manifest_sha,
            "manifest":manifest, "timeline":timeline, "blueprint":blueprint}


def publish(store, project, timeline, blueprint, maps, map_requests, font_identity,
            *, expected_revision, previous=None, edit_kind=None, layer_overrides=None,
            crop_overrides=None, motion_overrides=None):
    """Immutable artifact publication first; atomic pointer/CAS/revision second.

    Failed CAS may leave unreachable content-addressed artifacts, never an
    authoritative draft. Gate approvals and original media are untouched.
    """
    from backend.app.projects.gates import GateService
    from backend.app.projects.revisions import mark_stale
    ensure(store)
    approved_heads = current_gate_heads(store,project)
    numeric_heads = current_numeric_heads(store,project)
    refresh = None
    if previous is None:
        with store._connection() as db:
            prior=db.execute(
                "SELECT generation,project_revision,manifest_sha256 "
                "FROM g4_compiled_drafts WHERE project_id=?",(project,)).fetchone()
        if prior:
            previous_head=load(store,project)
            old_heads=previous_head["manifest"]["gate_heads"]
            if (expected_revision > previous_head["revision"]
                    and (approved_heads != old_heads or
                         numeric_heads != previous_head["manifest"].get("numeric_series_heads",{}))):
                # G1/G2/G3 were independently re-approved after prior draft.
                # Fresh production compile establishes a NEW trustworthy
                # baseline; same upstream head must never reset G4 edits.
                refresh=previous_head
            elif (previous_head["revision"] != expected_revision
                    or canonical(previous_head["timeline"]) != canonical(timeline)
                    or canonical(previous_head["blueprint"]) != canonical(blueprint)
                    or canonical(previous_head["manifest"]["maps"]) != canonical(maps)
                    or canonical(previous_head["manifest"]["map_requests"]) != canonical(map_requests)):
                _fail("G4_DRAFT_EXISTS",project,
                      "Same approved G1/G2/G3 cannot replace the current G4 draft.")
    generation = ((refresh or previous)["generation"] + 1 if (refresh or previous) else 1)
    new_revision = expected_revision + 1 if previous else expected_revision
    timeline_sha = store.put_artifact(canonical(timeline), "g4_compiled_timeline")
    blueprint_sha = store.put_artifact(canonical(blueprint), "g4_compiled_blueprint")
    manifest = {
        "schema_version":"G4CompiledDraft.v1", "project_id":project,
        "generation":generation, "project_revision":new_revision,
        "timeline_sha256":timeline_sha, "blueprint_sha256":blueprint_sha,
        "map_context_sha256":digest(maps), "map_requests_sha256":digest(map_requests),
        "maps":maps, "map_requests":map_requests, "font_identity":font_identity,
        "runtime_identity":_runtime_identity(),
        "gate_heads":approved_heads,
        "numeric_series_heads":numeric_heads,
        "story_sha256":timeline["story_sha256"],
        "audio_sha256":timeline["audio_sha256"],
        "word_map_sha256":timeline["word_map_sha256"],
        "asset_snapshot_sha256":timeline["asset_snapshot_sha256"],
        "dependency_fingerprint":timeline["dependency_fingerprint"],
        "layer_overrides":layer_overrides or {},
        # These overlays are presentation-only and stay tied to the immutable
        # G4 generation.  They are replayed only after the source heads and
        # compiled layer/event identities have been verified by revise_g4.
        "crop_overrides":crop_overrides or {},
        "motion_overrides":motion_overrides or {},
    }
    manifest_sha = store.put_artifact(canonical(manifest), "g4_compiled_manifest")
    with store._transaction() as db:
        GateService._check_revision(db, project, expected_revision)
        row = db.execute(
            "SELECT generation,project_revision,manifest_sha256 "
            "FROM g4_compiled_drafts WHERE project_id=?", (project,)).fetchone()
        if previous is None:
            if refresh:
                if row != (refresh["generation"],refresh["revision"],refresh["manifest_sha256"]):
                    _fail("G4_DRAFT_STALE",project,"A newer G4 source draft won the race.")
                db.execute("UPDATE g4_compiled_drafts SET generation=?,project_revision=?,"
                           "manifest_sha256=? WHERE project_id=?",
                           (generation,new_revision,manifest_sha,project))
                mark_stale(db,project,"scene_layout")
            elif row:
                if row == (generation, new_revision, manifest_sha):
                    return  # exact idempotent recompile with unchanged approved heads
                _fail("G4_DRAFT_EXISTS", project,
                      "Same upstream approval heads cannot reset an existing G4 edit.")
            else:
                db.execute("INSERT INTO g4_compiled_drafts VALUES(?,?,?,?)",
                           (project, generation, new_revision, manifest_sha))
        else:
            if row != (previous["generation"], previous["revision"],
                       previous["manifest_sha256"]):
                _fail("G4_DRAFT_STALE", project,
                      "Another trusted draft superseded the supplied G4 baseline.")
            updated = db.execute(
                "UPDATE g4_compiled_drafts SET generation=?,project_revision=?,manifest_sha256=? "
                "WHERE project_id=? AND generation=? AND project_revision=? AND manifest_sha256=?",
                (generation, new_revision, manifest_sha, project, *row)).rowcount
            if updated != 1:
                _fail("G4_DRAFT_STALE", project, "Reload the current trusted G4 draft.")
            mark_stale(db, project, edit_kind)
            db.execute("UPDATE projects SET revision=? WHERE project_id=? AND revision=?",
                       (new_revision, project, expected_revision))
