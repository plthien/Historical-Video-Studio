"""Bounded decoded-frame evidence from the real final MP4."""
from __future__ import annotations

import hashlib
import subprocess

from backend.app.contracts import ContractViolation


def inspect_frames(path, total_frames: int, scene_boundaries: list[int],
                   motion_expected: set[int] | None = None) -> dict:
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
            "status": "PASS" if not unexplained_black and not frozen else "FAIL"}
