"""A2-03 G2 frozen selection candidate and final WAV assembly."""
from __future__ import annotations
import hashlib
import json

from backend.app.contracts import ContractViolation, validate_document
from backend.app.projects.gates import _g1_identity, _head, _story
from backend.app.voice.qc import join_wavs


def canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transcript_for(sections: list[dict]) -> str:
    return "\n".join(s["narration"] for s in sections)


def selection_snapshot(db, project_id: str) -> dict | None:
    """Pure SQLite view; not itself approval, does not publish media or mutate revision."""
    # Foundation GateService may exist before A2 voice tables are initialized.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='voice_selected'").fetchone():
        return None
    current_sha, fp, _ = _g1_identity(db, project_id)
    head = _head(db, project_id, "G1")
    stale = db.execute("SELECT 1 FROM gate_staleness WHERE project_id=? AND gate_id='G1'",
                       (project_id,)).fetchone()
    if not head or tuple(head) != (current_sha, fp) or stale:
        return None
    story_sha, story = _story(db, project_id)
    sections = story["sections"]
    selected = []
    for section in sections:
        row = db.execute(
            "SELECT a.attempt_id,a.story_sha256,a.text_sha256,a.audio_sha256,"
            "a.sample_rate,a.channels,a.sample_count "
            "FROM voice_selected v JOIN voice_attempts a ON a.attempt_id=v.attempt_id "
            "AND a.project_id=v.project_id AND a.section_id=v.section_id "
            "WHERE v.project_id=? AND v.section_id=?",
            (project_id, section["section_id"])).fetchone()
        if (not row or row[1] != story_sha or
                row[2] != sha(section["narration"].encode("utf-8"))):
            return None
        selected.append({"section_id": section["section_id"], "attempt_id": row[0],
                         "audio_sha256": row[3], "sample_rate": row[4],
                         "channels": row[5], "sample_count": row[6]})
    return {"story_sha256": story_sha, "g1_fingerprint": fp,
            "transcript_sha256": sha(transcript_for(sections).encode("utf-8")),
            "selected": selected}


def selection_identity(db, project_id: str) -> tuple[str, str] | None:
    snapshot = selection_snapshot(db, project_id)
    if not snapshot:
        return None
    digest = sha(canonical(snapshot))
    return digest, digest


def assemble_frozen(store, project_id: str, snapshot: dict) -> tuple[dict, bytes, str]:
    story = store.get_story(project_id)
    if story.sha256 != snapshot["story_sha256"]:
        raise ContractViolation("FINAL_AUDIO_SOURCE_STALE", project_id,
                                "The approved story changed; reselect sections and approve again.")
    sections = story.data()["sections"]
    if [s["section_id"] for s in sections] != [s["section_id"] for s in snapshot["selected"]]:
        raise ContractViolation("FINAL_AUDIO_SECTIONS_INVALID", project_id,
                                "Section order/set changed during assembly.")
    transcript = transcript_for(sections)
    if sha(transcript.encode("utf-8")) != snapshot["transcript_sha256"]:
        raise ContractViolation("FINAL_AUDIO_SOURCE_STALE", project_id, "Transcript hash changed.")
    parts = []
    for entry in snapshot["selected"]:
        audio = store.get_artifact(entry["audio_sha256"])
        parts.append((entry["section_id"], audio))
    output, offsets, duration = join_wavs(parts)
    for entry, offset in zip(snapshot["selected"], offsets):
        if offset["end_sample"] - offset["start_sample"] != entry["sample_count"]:
            raise ContractViolation("FINAL_AUDIO_SAMPLES_CHANGED", entry["section_id"],
                                    "Persisted samples disagree with selected attempt metadata.")
    final = {"schema_version": "FinalAudio.v1", "project_id": project_id,
             "story_revision_sha256": story.sha256,
             "selected_attempt_ids": [x["attempt_id"] for x in snapshot["selected"]],
             "audio_sha256": sha(output), "transcript_sha256": snapshot["transcript_sha256"],
             "sample_rate": 24000, "channels": 1, "duration_samples": duration,
             "section_offsets": offsets}
    validate_document("FinalAudio.v1", final)
    return final, output, transcript
