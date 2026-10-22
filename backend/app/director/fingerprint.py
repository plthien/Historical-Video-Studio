"""B1-06: canonical dependency identity and revision-scoped hashes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCES = {
    "layout_registry": "contracts/registries/layouts.v1.json",
    "motion_registry": "contracts/registries/motion-presets.v1.json",
}
COMPILER_VERSION = "B1-06.v1"


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def dependency_identity(story_sha: str, final_audio: dict, word_map: dict,
                        assets: dict, maps: dict, *,
                        font_identity: dict, style_version: str) -> dict:
    fingerprints = {name: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                    for name, path in SOURCES.items()}
    return {
        "compiler_version": COMPILER_VERSION,
        "story_sha256": story_sha,
        "approved_wav_sha256": final_audio["audio_sha256"],
        "transcript_sha256": final_audio["transcript_sha256"],
        "word_map_sha256": digest(word_map),
        "g3_approved_snapshot_sha256": digest(assets),
        "geography_sha256": digest(maps),
        "font_identity": font_identity,
        "style_version": style_version,
        **fingerprints,
    }
