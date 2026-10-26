"""Real FFprobe/decoded-frame QC for exact delivery bytes."""
from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from hashlib import sha256

from backend.app.contracts import ContractViolation
from backend.app.director import draft
from backend.app.director.fingerprint import canonical
from .frame_qc import inspect_frames


def inspect(store, project: str, mp4_path, render_manifest: dict) -> tuple[dict, str]:
    data = mp4_path.read_bytes(); mp4_sha = sha256(data).hexdigest()
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                            "-show_format", "-of", "json", str(mp4_path)],
                           capture_output=True, text=True, check=False)
    if probe.returncode:
        raise ContractViolation("QC_FFPROBE_FAILED", project, "Final MP4 is truncated or unreadable.", blocking_gate="G5")
    info = json.loads(probe.stdout); streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    expected = render_manifest["video"]; problems = []
    frames = int((video or {}).get("nb_read_frames") or (video or {}).get("nb_frames") or 0)
    if not video or video.get("codec_name") != "h264": problems.append("QC_VIDEO_CODEC")
    if video and (video.get("width"), video.get("height")) != (1920, 1080): problems.append("QC_RESOLUTION")
    if not video or video.get("r_frame_rate") != "30/1": problems.append("QC_FRAME_RATE")
    if video and video.get("pix_fmt") not in ("yuv420p", "yuvj420p"): problems.append("QC_PIXEL_FORMAT")
    if frames != expected["total_frames"]: problems.append("QC_FRAME_COUNT")
    if not audio or audio.get("codec_name") != "aac": problems.append("QC_AUDIO_CODEC")
    if audio and int(audio.get("sample_rate") or 0) != render_manifest["audio"]["sample_rate"]:
        problems.append("QC_AUDIO_SAMPLE_RATE")
    if audio and int(audio.get("channels") or 0) != 1: problems.append("QC_AUDIO_CHANNELS")
    if video and abs(float(video.get("start_time") or 0)) > 1 / 30: problems.append("QC_VIDEO_START")
    if audio and abs(float(audio.get("start_time") or 0)) > 1 / 30: problems.append("QC_AUDIO_START")
    source_seconds = render_manifest["audio"]["duration_samples"] / render_manifest["audio"]["sample_rate"]
    audio_seconds = float((audio or {}).get("duration") or 0)
    video_seconds = frames / 30
    # AAC/container rounding may differ by at most one authored 30fps frame.
    if abs(audio_seconds - source_seconds) > 1 / 30 + 0.001: problems.append("QC_AUDIO_DURATION")
    if abs(video_seconds - source_seconds) > 1 / 30 + 0.001: problems.append("QC_AV_SYNC")
    timeline = draft.load(store, project)["timeline"]
    boundaries = [scene["start_frame"] for scene in timeline["scenes"]]
    motion_expected = set()
    for scene in timeline["scenes"]:
        for event in scene.get("events", []):
            if event.get("duration_frames", 0) > 1:
                frame = scene["start_frame"] + event["start_frame"] + event["duration_frames"] // 2
                if frame + 1 < expected["total_frames"]:
                    boundaries.extend((frame, frame + 1)); motion_expected.add(frame)
    try:
        frame_evidence = inspect_frames(mp4_path, expected["total_frames"], boundaries, motion_expected)
        if frame_evidence["status"] != "PASS": problems.append("QC_VISUAL_ANOMALY")
    except ContractViolation as exc:
        frame_evidence = {"sampled_frames": [], "unexpected_black_frames": [],
                          "unexpected_frozen_frames": [], "status": "FAIL",
                          "decode_error": exc.code}
        problems.append(exc.code)
    report = {"schema_version": "QCReport.v1", "project_id": project, "mp4_sha256": mp4_sha,
              "render_input_manifest_sha256": sha256(canonical(render_manifest)).hexdigest(),
              "g4_manifest_sha256": render_manifest["g4_manifest_sha256"],
              "audio_sha256": render_manifest["audio"]["wav_sha256"],
              "word_map_sha256": render_manifest["audio"]["word_map_sha256"],
              "acceptance_bound_seconds": round(1 / 30, 9), "ffprobe": info,
              "decoded_frames": frame_evidence, "problems": problems,
              "status": "PASS" if not problems else "FAIL"}
    return report, store.put_artifact(canonical(report), "qc_report")
