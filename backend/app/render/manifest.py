"""Immutable, owner-derived RenderInputManifest.v1 construction."""
from __future__ import annotations

import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

from backend.app.contracts import ContractViolation
from backend.app.director import draft
from backend.app.director.fingerprint import canonical
from backend.app.projects.gates import GateService


def _fail(code, project, remedy):
    raise ContractViolation(code, project, remedy, blocking_gate="G4")


def build(store, project: str, *, persist: bool = True) -> tuple[dict, str]:
    gates = {item["gate_id"]: item for item in GateService(store).board(project)}
    if gates["G4"]["state"] != "APPROVED":
        _fail("G4_APPROVAL_REQUIRED", project, "Approve the exact current G4 review candidate first.")
    with store._connection() as db:
        heads = {gate: {"candidate_sha256": candidate, "dependency_fingerprint": fingerprint,
                        "approval_id": approval}
                 for gate, candidate, fingerprint, approval in db.execute(
                     "SELECT gate_id,candidate_sha256,dependency_fingerprint,approval_id FROM gate_heads "
                     "WHERE project_id=? AND gate_id IN ('G1','G2','G3','G4') ORDER BY gate_id",
                     (project,)).fetchall()}
        voice = db.execute(
            "SELECT f.audio_sha256,f.transcript_sha256,f.final_json,w.map_sha256,w.map_json "
            "FROM final_audio f JOIN word_maps w ON w.project_id=f.project_id AND w.approval_id=f.approval_id "
            "WHERE f.project_id=? AND f.approval_id=?",
            (project, heads.get("G2", {}).get("approval_id"))).fetchone()
    if set(heads) != {"G1", "G2", "G3", "G4"} or not voice:
        _fail("RENDER_SOURCE_INCOMPLETE", project, "Current G1-G4 heads, final WAV and alignment are required.")
    candidate = draft.verify_review_candidate(store, project, heads["G4"]["candidate_sha256"],
                                               heads["G4"]["dependency_fingerprint"])
    g4 = draft.load(store, project)
    final = json.loads(voice[2]); word = json.loads(voice[4])
    store.get_artifact(voice[0]); store.get_artifact(voice[3])
    if (voice[0] != g4["manifest"]["audio_sha256"] or
            voice[3] != g4["manifest"]["word_map_sha256"] or
            final.get("audio_sha256") != voice[0] or word.get("audio_sha256") != voice[0]):
        _fail("RENDER_AUDIO_STALE", project, "Approved WAV and word map must match approved G4.")
    package = json.loads((Path(__file__).parents[3] / "renderer" / "package.json").read_text("utf-8"))
    if not shutil.which("node") or not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        _fail("RENDER_TOOLCHAIN_UNAVAILABLE", project,
              "Install pinned Node 22, Remotion and FFmpeg/FFprobe on native Windows.")
    node_version = subprocess.run(["node", "--version"], capture_output=True, text=True,
                                  check=True).stdout.strip()
    ffmpeg_version = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True,
                                    check=True).stdout.splitlines()[0]
    if not node_version.startswith("v22."):
        _fail("RENDER_TOOLCHAIN_UNAVAILABLE", project, "Render requires pinned Node 22.")
    dependencies = candidate["dependencies"]
    manifest = {
        "schema_version": "RenderInputManifest.v1", "project_id": project,
        "g4_approval_id": heads["G4"]["approval_id"],
        "g4_candidate_sha256": heads["G4"]["candidate_sha256"],
        "g4_dependency_fingerprint": heads["G4"]["dependency_fingerprint"],
        "g4_manifest_sha256": dependencies["draft_manifest_sha256"],
        "timeline_sha256": dependencies["timeline_sha256"],
        "video": {"composition_id": "HistoricalTimelineV1", "width": 1920, "height": 1080,
                  "fps": 30, "total_frames": g4["timeline"]["total_frames"],
                  "codec": "h264", "pixel_format": "yuv420p", "container": "mp4"},
        "gate_heads": heads, "numeric_series_heads": dependencies["numeric_series_heads"],
        "resolved_assets": dependencies["resolved_assets"],
        "asset_snapshot_sha256": dependencies["asset_snapshot_sha256"],
        "effective_asset_snapshot_sha256": dependencies["effective_asset_snapshot_sha256"],
        "font_identity": dependencies["font_identity"], "runtime_identity": dependencies["runtime_identity"],
        "audio": {"wav_sha256": voice[0], "transcript_sha256": voice[1],
                  "word_map_sha256": voice[3], "sample_rate": final["sample_rate"],
                  "duration_samples": final["duration_samples"],
                  "section_offsets": final.get("sections", final.get("section_offsets", []))},
        "renderer": {"package_version": package["version"],
                     "remotion_version": package["dependencies"]["remotion"],
                     "node_version": node_version, "ffmpeg_version": ffmpeg_version},
    }
    raw = canonical(manifest)
    identity = sha256(raw).hexdigest()
    if persist:
        identity = store.put_artifact(raw, "render_input_manifest")
    return manifest, identity


def verify(store, project: str, manifest_sha: str) -> dict:
    raw = store.get_artifact(manifest_sha)
    try:
        saved = json.loads(raw)
    except ValueError as exc:
        _fail("RENDER_MANIFEST_CORRUPT", project, "Restore canonical render input bytes.")
    current, current_sha = build(store, project, persist=False)
    if current_sha != manifest_sha or canonical(saved) != raw or saved != current:
        _fail("RENDER_SOURCE_STALE", project, "Render only the exact current approved G4 inputs.")
    return saved
