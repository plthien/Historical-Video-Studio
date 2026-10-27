"""Native Windows B3 media smoke; all generated decisions/media are synthetic test-only."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app.api.server import create_app
from backend.app.render.frame_qc import inspect_frames


def _tools():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("B3_NATIVE_FFMPEG_REQUIRED")


def _render(path: Path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
        "color=c=navy:s=1920x1080:r=30:d=1", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=48000:duration=1", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(path)], check=True)


def run(case: str, mode: str):
    if mode != "local": raise RuntimeError("B3 delivery smoke is local-only")
    _tools()
    with TemporaryDirectory(prefix="hvs-b3-smoke-") as dirname:
        root = Path(dirname); movie = root / "synthetic-final.mp4"; _render(movie)
        probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                                "-of", "json", str(movie)], capture_output=True, text=True, check=True)
        streams = json.loads(probe.stdout)["streams"]
        video = next(x for x in streams if x["codec_type"] == "video")
        audio = next(x for x in streams if x["codec_type"] == "audio")
        if case == "render-mp4":
            if (video["codec_name"], video["width"], video["height"], video["r_frame_rate"],
                    audio["codec_name"]) != ("h264", 1920, 1080, "30/1", "aac"):
                raise RuntimeError("B3_RENDER_STREAMS_INVALID")
        elif case == "final-video-qc":
            evidence = inspect_frames(movie, 30, [0, 15, 29])
            if evidence["status"] != "PASS" or len(evidence["sampled_frames"]) != 3:
                raise RuntimeError("B3_DECODED_FRAME_QC_FAILED")
        elif case == "export-approved":
            app = create_app(root / "state.sqlite", root / "media")
            store = app.state.store; store.create_project("proj_export_smoke", "Synthetic export smoke")
            mp4 = store.put_artifact(movie.read_bytes(), "final_mp4")
            credits = store.put_artifact(b'{"schema_version":"AttributionManifest.v1","assets":[]}',
                                         "attribution_manifest")
            manifest = store.put_artifact(b'{"schema_version":"RenderInputManifest.v1"}',
                                          "render_input_manifest")
            with store._transaction() as db:
                db.execute("INSERT INTO delivery_exports VALUES(?,?,?,?,?,?,?,?)",
                    ("export_smoke", "proj_export_smoke", "job_smoke", "approval_g5_smoke",
                     mp4, credits, manifest, "{}"))
            response = TestClient(app).get(f"/api/v1/projects/proj_export_smoke/delivery/artifacts/{mp4}")
            if response.status_code != 200 or response.content != movie.read_bytes():
                raise RuntimeError("B3_EXPORT_BYTE_FIDELITY_FAILED")
        else: raise RuntimeError("B3_SMOKE_CASE_UNKNOWN")
        print(json.dumps({"status": "LOCAL_PASS", "case": case,
                          "evidence": "SYNTHETIC_TEST_ONLY_REAL_H264_AAC"}))
