"""Bounded decoded-frame evidence from the real final MP4."""
from __future__ import annotations

import hashlib
import re
import subprocess

from backend.app.contracts import ContractViolation


_FRAME = re.compile(r"^frame:(?P<frame>\d+)")
_YAVG = re.compile(r"^lavfi\.signalstats\.YAVG=(?P<value>[0-9.]+)")


def _inspect_full_stream(path, total_frames: int, fps: int = 30) -> dict:
    """One bounded-memory decode pass catches black frames outside samples."""
    thresholds = {"limited_range_y_black": 16, "limited_range_y_average_max": 20,
                  "minimum_frames": 1}
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(path),
         "-map", "0:v:0", "-vf",
         "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
         "-an", "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert proc.stdout is not None and proc.stderr is not None
    current_frame = None; decoded = 0; black_frames = []
    for line in proc.stdout:
        frame_match = _FRAME.match(line.strip())
        if frame_match:
            current_frame = int(frame_match.group("frame")); decoded += 1
            continue
        y_match = _YAVG.match(line.strip())
        if y_match and current_frame is not None and float(y_match.group("value")) <= 20:
            black_frames.append(current_frame)
    stderr = proc.stderr.read(); returncode = proc.wait()
    if returncode or decoded != total_frames:
        raise ContractViolation("QC_FULL_STREAM_DECODE_FAILED", str(path),
                                f"Decoded {decoded}/{total_frames} authored frames for visual QC. {stderr[-200:]}",
                                blocking_gate="G5")
    intervals = []
    for frame in black_frames:
        if intervals and frame == intervals[-1]["end_frame"] + 1:
            intervals[-1]["end_frame"] = frame
            intervals[-1]["end_seconds"] = (frame + 1) / fps
            intervals[-1]["duration_seconds"] = ((frame + 1) - intervals[-1]["start_frame"]) / fps
        else:
            intervals.append({"start_seconds": frame / fps, "end_seconds": (frame + 1) / fps,
                              "duration_seconds": 1 / fps,
                              "start_frame": frame, "end_frame": frame})
    return {"method": "ffmpeg.signalstats.streaming_yavg", "thresholds": thresholds,
            "decoded_frames": decoded, "decoded_expected_frames": total_frames,
            "black_intervals": intervals,
            "status": "PASS" if not intervals else "FAIL"}


def inspect_frames(path, total_frames: int, scene_boundaries: list[int],
                   motion_expected: set[int] | None = None) -> dict:
    full_stream = _inspect_full_stream(path, total_frames)
    indices = sorted({0, max(0, total_frames // 2), max(0, total_frames - 1),
                      *[max(0, min(total_frames - 1, value)) for value in scene_boundaries]})
    evidence = []
    for frame in indices:
        proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf",
            f"select=eq(n\\,{frame}),scale=64:36", "-frames:v", "1", "-f", "rawvideo",
            "-pix_fmt", "rgb24", "-"], capture_output=True, check=False)
        if proc.returncode or len(proc.stdout) != 64 * 36 * 3:
            raise ContractViolation("QC_FRAME_DECODE_FAILED", str(frame),
                                    "Final MP4 must decode every sampled authored frame.", blocking_gate="G5")
        values = proc.stdout
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        evidence.append({"frame": frame, "sha256": hashlib.sha256(values).hexdigest(),
                         "luma_mean": round(mean, 3), "variance": round(variance, 3)})
    unexplained_black = [x["frame"] for x in evidence if x["luma_mean"] < 1 and x["variance"] < 1]
    expected = motion_expected or set()
    frozen = [b["frame"] for a, b in zip(evidence, evidence[1:])
              if a["frame"] in expected and b["frame"] == a["frame"] + 1
              and b["sha256"] == a["sha256"]]
    return {"sampled_frames": evidence, "unexpected_black_frames": unexplained_black,
            "unexpected_frozen_frames": frozen,
            "full_stream": full_stream,
            "status": "PASS" if not unexplained_black and not frozen
                      and full_stream["status"] == "PASS" else "FAIL"}
