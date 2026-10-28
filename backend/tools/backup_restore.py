"""Windows operator CLI for coherent backup/restore; never copies provider secrets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.projects.backup import create_backup, restore_backup


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--database", required=True)
    backup.add_argument("--media-root", required=True)
    backup.add_argument("--destination", required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--source", required=True)
    restore.add_argument("--destination", required=True)
    args = parser.parse_args()
    result = (create_backup(args.database, args.media_root, args.destination)
              if args.command == "backup" else restore_backup(args.source, args.destination))
    print(json.dumps({"status": "PASS", "command": args.command,
                      "projects": [x["project_id"] for x in result["projects"]],
                      "database_sha256": result["database"]["sha256"],
                      "artifact_count": len(result["artifacts"])}))


if __name__ == "__main__":
    main()
