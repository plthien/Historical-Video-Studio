"""Operator-invoked coherent local-studio backup and fail-closed restore."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


FORMAT = "HistoricalVideoStudioBackup.v1"


class BackupError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> Path:
    relative = Path(value.replace("/", os.sep))
    if relative.is_absolute() or ".." in relative.parts:
        raise BackupError(f"BACKUP_PATH_INVALID: {value}")
    return relative


def _integrity(database: Path) -> None:
    try:
        with sqlite3.connect(database) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise BackupError("BACKUP_DATABASE_DAMAGED") from exc
    if not result or result[0] != "ok":
        raise BackupError("BACKUP_DATABASE_DAMAGED")


def _code_identity(root: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def create_backup(database: str | Path, media_root: str | Path, destination: str | Path,
                  *, application_root: str | Path | None = None) -> dict:
    database, media_root, destination = Path(database).resolve(), Path(media_root).resolve(), Path(destination).resolve()
    if not database.is_file():
        raise BackupError("BACKUP_DATABASE_NOT_FOUND")
    if destination.exists():
        raise BackupError("BACKUP_DESTINATION_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination
    temporary.mkdir()
    try:
        snapshot = temporary / "studio.sqlite"
        with sqlite3.connect(database) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        # Provider credentials are machine-local configuration, not project
        # evidence. Preserve provider/base selection while requiring explicit
        # credential re-entry after restore.
        with sqlite3.connect(snapshot) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_provider_settings'").fetchone():
                db.execute("UPDATE local_provider_settings SET api_key='' ")
                db.commit()
        _integrity(snapshot)
        with sqlite3.connect(snapshot) as db:
            projects = [{"project_id": row[0], "title": row[1], "revision": row[2]}
                        for row in db.execute("SELECT project_id,title,revision FROM projects ORDER BY project_id")]
            artifacts = list(db.execute(
                "SELECT sha256,byte_count,kind,relative_path FROM artifacts ORDER BY sha256"))
        copied = []
        for digest, byte_count, kind, relative_path in artifacts:
            relative = _safe_relative(relative_path)
            source = (media_root / relative).resolve()
            if media_root not in source.parents or not source.is_file():
                raise BackupError(f"BACKUP_ARTIFACT_MISSING: {digest}")
            if source.stat().st_size != byte_count or _sha(source) != digest:
                raise BackupError(f"BACKUP_ARTIFACT_TAMPERED: {digest}")
            target = temporary / "media" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append({"sha256": digest, "byte_count": byte_count, "kind": kind,
                           "relative_path": relative_path})
        root = Path(application_root).resolve() if application_root else Path(__file__).resolve().parents[3]
        manifest = {"schema_version": FORMAT, "scope": "LOCAL_STUDIO_ALL_PROJECTS",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "code_identity": _code_identity(root), "projects": projects,
                    "database": {"path": "studio.sqlite", "sha256": _sha(snapshot),
                                 "integrity_check": "ok"},
                    "artifacts": copied,
                    "credentials_included": False,
                    "credential_remediation": "Re-enter machine-local provider credentials after restore."}
        manifest_temporary = temporary / ("manifest.json.partial-" + uuid4().hex)
        manifest_temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(manifest_temporary, temporary / "manifest.json")
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def restore_backup(source: str | Path, destination: str | Path) -> dict:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise BackupError("RESTORE_DESTINATION_EXISTS")
    try:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError("RESTORE_MANIFEST_INVALID") from exc
    if manifest.get("schema_version") != FORMAT:
        raise BackupError("RESTORE_FORMAT_INCOMPATIBLE")
    snapshot = source / _safe_relative(manifest["database"]["path"])
    if not snapshot.is_file() or _sha(snapshot) != manifest["database"]["sha256"]:
        raise BackupError("RESTORE_DATABASE_TAMPERED")
    _integrity(snapshot)
    for item in manifest.get("artifacts", []):
        artifact = source / "media" / _safe_relative(item["relative_path"])
        if (not artifact.is_file() or artifact.stat().st_size != item["byte_count"]
                or _sha(artifact) != item["sha256"]):
            raise BackupError(f"RESTORE_ARTIFACT_TAMPERED: {item['sha256']}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination
    try:
        data = temporary / "data"
        data.mkdir(parents=True)
        restored_db = data / "historical-studio.sqlite"
        with sqlite3.connect(snapshot) as original, sqlite3.connect(restored_db) as target:
            original.backup(target)
        _integrity(restored_db)
        for item in manifest.get("artifacts", []):
            relative = _safe_relative(item["relative_path"])
            target = data / "media" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / "media" / relative, target)
        marker = temporary / ("restore-manifest.json.partial-" + uuid4().hex)
        marker.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(marker, temporary / "restore-manifest.json")
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
