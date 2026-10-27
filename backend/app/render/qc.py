"""Real FFprobe/decoded-frame QC for exact delivery bytes."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from array import array
from hashlib import sha256

from backend.app.contracts import ContractViolation
from backend.app.director import draft
from backend.app.director.fingerprint import canonical
from .frame_qc import inspect_frames


def _decoded_energy(path, sample_rate: int) -> dict:
    """Decode mono PCM in one-second windows without retaining the soundtrack."""
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-map", "0:a:0",
         "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    chunk_size = sample_rate * 2
    windows = []
    while True:
        data = proc.stdout.read(chunk_size)
        if not data:
            break
        if len(data) % 2:
            proc.kill(); proc.wait()
            raise ContractViolation("QC_AUDIO_DECODE_FAILED", str(path),
                                    "Decoded audio contained a partial PCM sample.", blocking_gate="G5")
        samples = array("h"); samples.frombytes(data)
        if sys.byteorder != "little": samples.byteswap()
        if samples:
            rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768
            windows.append(20 * math.log10(max(rms, 1e-12)))
    stderr = proc.stderr.read().decode("utf-8", "replace")
    returncode = proc.wait()
    if returncode or not windows:
        raise ContractViolation("QC_AUDIO_DECODE_FAILED", str(path),
                                "Decode the approved WAV and delivered AAC signal.", blocking_gate="G5")
    energy = sum(10 ** (value / 10) for value in windows) / len(windows)
    return {"window_seconds": 1, "window_count": len(windows),
            "rms_dbfs": round(10 * math.log10(max(energy, 1e-24)), 3),
            "windows_dbfs": [round(value, 3) for value in windows],
            "decoder_stderr": stderr[-500:]}


def _compare_audio(store, mp4_path, audio_manifest: dict) -> dict:
    wav_sha = audio_manifest["wav_sha256"]
    store.get_artifact(wav_sha)  # verifies registered byte count and SHA-addressed path
    wav_path = store.artifacts.path(wav_sha)
    sample_rate = audio_manifest["sample_rate"]
    source = _decoded_energy(wav_path, sample_rate)
    output = _decoded_energy(mp4_path, sample_rate)
    audible = [index for index, value in enumerate(source["windows_dbfs"]) if value > -45]
    comparable = [index for index in audible if index < len(output["windows_dbfs"])]
    matched = [index for index in comparable
               if output["windows_dbfs"][index] > -60
               and source["windows_dbfs"][index] - output["windows_dbfs"][index] <= 12]
    ratio = len(matched) / len(audible) if audible else 1.0
    deficit = source["rms_dbfs"] - output["rms_dbfs"]
    status = "PASS" if (not audible or (len(comparable) == len(audible)
                                        and ratio >= .8 and deficit <= 12)) else "FAIL"
    return {"method": "decoded_pcm_rms_windows", "approved_wav_sha256": wav_sha,
            "audible_source_threshold_dbfs": -45, "maximum_deficit_db": 12,
            "minimum_matching_audible_ratio": .8,
            "source": source, "output": output,
            "audible_source_windows": audible, "matching_ratio": round(ratio, 6),
            "global_deficit_db": round(deficit, 3), "status": status}


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
    if audio and audio.get("codec_name") == "aac":
        audio_evidence = _compare_audio(store, mp4_path, render_manifest["audio"])
        if audio_evidence["status"] != "PASS":
            problems.append("QC_AUDIO_CONTENT_MISMATCH")
    else:
        audio_evidence = {"method": "decoded_pcm_rms_windows", "status": "FAIL",
                          "approved_wav_sha256": render_manifest["audio"]["wav_sha256"],
                          "decode_error": "QC_AUDIO_CODEC"}
    report = {"schema_version": "QCReport.v1", "project_id": project, "mp4_sha256": mp4_sha,
              "render_input_manifest_sha256": sha256(canonical(render_manifest)).hexdigest(),
              "g4_manifest_sha256": render_manifest["g4_manifest_sha256"],
              "audio_sha256": render_manifest["audio"]["wav_sha256"],
              "word_map_sha256": render_manifest["audio"]["word_map_sha256"],
              "acceptance_bound_seconds": round(1 / 30, 9), "ffprobe": info,
              "decoded_frames": frame_evidence, "decoded_audio": audio_evidence,
              "problems": problems,
              "status": "PASS" if not problems else "FAIL"}
    return report, store.put_artifact(canonical(report), "qc_report")
