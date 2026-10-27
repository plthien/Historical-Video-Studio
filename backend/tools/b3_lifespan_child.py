"""Independent Windows backend lifespan used by the B3 crash/restart fixture."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.server import create_app


def _write_atomic(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    args = parser.parse_args()

    application = create_app(args.sqlite, args.media_root)
    with TestClient(application):
        _write_atomic(args.status_file, {
            "backend_pid": os.getpid(),
            "recovery": application.state.recovery,
        })
        while not args.stop_file.exists():
            time.sleep(0.05)


if __name__ == "__main__":
    main()
