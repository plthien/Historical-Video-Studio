"""B3-05 native Windows clean ZIP bootstrap/reopen evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
V3_PROMPT_RELATIVE = "backend/app/projects/prompts/external_story_brief_v3.md"
V3_PROMPT_SHA256 = "e7234d15cc00a1f8b47196e7a7190296218ff9654bff4beb9818826c6848e494"


def _run(command: list[str], *, cwd: Path, env: dict | None = None, timeout: int = 600,
         expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode != expected:
        raise RuntimeError("COMMAND_FAILED:" + " ".join(command) + "\n" + result.stdout + result.stderr)
    return result


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _package() -> dict:
    result = _run([str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   "scripts/windows/package.ps1"], cwd=ROOT, timeout=1200)
    for line in reversed(result.stdout.splitlines()):
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            continue
        if document.get("status") == "PACKAGE_PASS":
            return document
    raise RuntimeError("PACKAGE_RESULT_JSON_MISSING")


def _manifest_inventory(extracted: Path, archive: Path, head: str) -> tuple[dict, int]:
    manifest = json.loads((extracted / "package-manifest.json").read_text("utf-8-sig"))
    if manifest["source_commit"] != head:
        raise RuntimeError("PACKAGE_SOURCE_COMMIT_MISMATCH")
    files = {item["path"]: item for item in manifest["files"]}
    actual = {str(path.relative_to(extracted)).replace("\\", "/"): path
              for path in extracted.rglob("*") if path.is_file()
              and path.name != "package-manifest.json"}
    if set(actual) != set(files):
        raise RuntimeError("PACKAGE_FILE_INVENTORY_MISMATCH")
    for relative, path in actual.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != files[relative]["sha256"] or path.stat().st_size != files[relative]["byte_count"]:
            raise RuntimeError("PACKAGE_FILE_HASH_MISMATCH:" + relative)
        lowered = relative.lower()
        if ("node_modules/" in lowered or lowered.startswith((".venv/", ".artifacts/"))
                or "/.venv/" in lowered or "/.artifacts/" in lowered
                or lowered.endswith((".sqlite", ".sqlite-wal", ".sqlite-shm", ".log", ".pyc"))
                or Path(relative).name.lower().startswith(".env")):
            raise RuntimeError("PACKAGE_FORBIDDEN_FILE:" + relative)
    if hashlib.sha256(archive.read_bytes()).hexdigest() == "0" * 64:
        raise RuntimeError("PACKAGE_ARCHIVE_HASH_INVALID")
    return manifest, len(actual)


def _tree_identity(root: Path) -> dict[str, str]:
    """Hash persisted operator data before a negative launch; never inspect contents."""
    if not root.exists():
        return {}
    return {str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def _tree_identity_digest(identity: dict[str, str]) -> str:
    """Create a stable, non-content-bearing identity for an operator data tree."""
    serialized = "\n".join(f"{relative}:{digest}" for relative, digest in sorted(identity.items()))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _launcher(root: Path, data: Path, port: int, evidence: Path, *, skip: bool,
              project: str = "", env: dict | None = None, expected: int = 0) -> subprocess.CompletedProcess[str]:
    command = [str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(root / "scripts/windows/start-studio.ps1"), "-Smoke", "-NoBrowser",
               "-Port", str(port), "-DataRoot", str(data), "-EvidencePath", str(evidence)]
    if skip:
        command.append("-SkipBootstrap")
    if project:
        command.extend(["-VerifyProjectId", project])
    return _run(command, cwd=root, env=env, timeout=1200, expected=expected)


def run(output: Path) -> dict:
    if os.name != "nt":
        raise RuntimeError("CLEAN_PACKAGE_SMOKE_REQUIRES_WINDOWS")
    package = _package()
    archive = Path(package["archive"]).resolve()
    head = _run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="hvs-clean-package-") as temporary:
        temp = Path(temporary)
        extracted_parent = temp / "extracted"
        extracted_parent.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted_parent)
        roots = [path for path in extracted_parent.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("PACKAGE_ROOT_INVALID")
        extracted = roots[0]
        manifest, verified_count = _manifest_inventory(extracted, archive, head)
        manifest_files = {item["path"]: item for item in manifest["files"]}
        prompt_path = extracted / V3_PROMPT_RELATIVE
        if (V3_PROMPT_RELATIVE not in manifest_files or not prompt_path.is_file()
                or manifest_files[V3_PROMPT_RELATIVE]["sha256"] != V3_PROMPT_SHA256
                or hashlib.sha256(prompt_path.read_bytes()).hexdigest() != V3_PROMPT_SHA256):
            raise RuntimeError("PACKAGE_V3_PROMPT_ASSET_MISSING_OR_CHANGED")
        if any((extracted / name).exists() for name in (".venv", "node_modules", "data")):
            raise RuntimeError("PACKAGE_NOT_CLEANLY_EXTRACTED")
        data = temp / "external-data"
        first_evidence, second_evidence = temp / "first.json", temp / "second.json"
        first = _launcher(extracted, data, _free_port(), first_evidence, skip=False)
        first_doc = json.loads(first_evidence.read_text("utf-8-sig"))
        if not (first_doc["api_ready"] and first_doc["ui_status"] == 200
                and first_doc["process_cleanup"] and first_doc["source_commit"] == head):
            raise RuntimeError("FIRST_PACKAGE_LAUNCH_EVIDENCE_INVALID")
        project = "proj_clean_package"
        artifact_bytes = b"clean extracted package immutable media"
        script = ("from backend.app.projects.storage import ProjectStore; "
                  "from backend.app.projects.authoring_brief import BRIEF_VERSION,build_brief; "
                  "import hashlib,json,os; "
                  "s=ProjectStore(os.environ['HVS_DB'],os.environ['HVS_MEDIA']); "
                  f"s.create_project('{project}','Clean package reopen'); "
                  "b=build_brief(s,'proj_clean_package',topic='Packaged V3 authoring',"
                  "audience='Adult learners',runtime_minutes=7,editorial_goals='Synthetic package probe.'); "
                  f"print(json.dumps({{'artifact':s.put_artifact({artifact_bytes!r},'clean_package_probe'),"
                  "'brief_version':BRIEF_VERSION,'brief_sha256':hashlib.sha256(b.encode()).hexdigest(),"
                  "'v3_header':b.startswith('# EXTERNAL CHATGPT')}))")
        runtime_env = os.environ.copy()
        runtime_env.update({"HVS_DB": str(data / "historical-studio.sqlite"),
                            "HVS_MEDIA": str(data / "media")})
        packaged_authoring = json.loads(_run(
            [str(extracted / ".venv/Scripts/python.exe"), "-c", script],
            cwd=extracted, env=runtime_env).stdout)
        created = packaged_authoring["artifact"]
        if (packaged_authoring["brief_version"] != "HVS-EXTERNAL-STORY-BRIEF.v3"
                or not packaged_authoring["v3_header"]
                or not re.fullmatch(r"[0-9a-f]{64}", packaged_authoring["brief_sha256"])):
            raise RuntimeError("PACKAGE_V3_BRIEF_RUNTIME_INVALID")
        second = _launcher(extracted, data, _free_port(), second_evidence, skip=True, project=project)
        second_doc = json.loads(second_evidence.read_text("utf-8-sig"))
        inspect = ("from backend.app.projects.storage import ProjectStore; import os,json; "
                   "s=ProjectStore(os.environ['HVS_DB'],os.environ['HVS_MEDIA']); "
                   f"print(json.dumps({{'revision':s.revision('{project}'),'bytes':"
                   f"s.get_artifact('{created}').decode()}}))")
        reopened = json.loads(_run([str(extracted / ".venv/Scripts/python.exe"), "-c", inspect],
                                   cwd=extracted, env=runtime_env).stdout)
        if (second_doc["project_read"] != {"project_id": project, "project_revision": 0}
                or reopened != {"revision": 0, "bytes": artifact_bytes.decode()}
                or not second_doc["process_cleanup"]):
            raise RuntimeError("PACKAGE_REOPEN_CONTINUITY_INVALID")

        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0)); occupied.listen()
            port = occupied.getsockname()[1]
            conflict = _launcher(extracted, data, port, temp / "conflict.json", skip=True, expected=1)
        if "already in use" not in conflict.stdout + conflict.stderr:
            raise RuntimeError("PACKAGE_OCCUPIED_PORT_NEGATIVE_MISSING")

        path_parts = []
        node_dir = Path(shutil.which("node") or "").parent
        if node_dir.is_dir():
            path_parts.append(str(node_dir))
        path_parts.extend([str(extracted / ".venv/Scripts"), str(Path(os.environ["WINDIR"]) / "System32")])
        no_ffmpeg = os.environ.copy(); no_ffmpeg["PATH"] = os.pathsep.join(path_parts)
        missing = _launcher(extracted, data, _free_port(), temp / "missing.json", skip=True,
                            env=no_ffmpeg, expected=1)
        if "ffmpeg is required" not in missing.stdout + missing.stderr:
            raise RuntimeError("PACKAGE_MISSING_FFMPEG_NEGATIVE_MISSING")

        index = extracted / "frontend/dist/index.html"
        saved = index.read_bytes(); index.unlink()
        persisted_before = _tree_identity(data)
        try:
            corrupt = _launcher(extracted, data, _free_port(), temp / "corrupt.json", skip=True, expected=1)
        finally:
            index.write_bytes(saved)
        corrupt_text = corrupt.stdout + corrupt.stderr
        corrupt_evidence_path = temp / "corrupt.json"
        corrupt_evidence = (json.loads(corrupt_evidence_path.read_text("utf-8-sig"))
                            if corrupt_evidence_path.exists() else {})
        persisted_after = _tree_identity(data)
        if ("FRONTEND_BUNDLE_STALE" not in corrupt_text or "BUILD_MISSING" not in corrupt_text
                or "STUDIO_READY" in corrupt_text or corrupt_evidence.get("api_ready")
                or corrupt_evidence.get("ui_status") == 200 or persisted_after != persisted_before):
            raise RuntimeError("PACKAGE_CORRUPT_RUNTIME_NEGATIVE_MISSING:\n" + corrupt_text)

        report = {
            "schema_version": "B3CleanPackageLaunchEvidence.v2", "status": "PASS",
            "scope": "SYNTHETIC_TEST_ONLY", "source_commit": head,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "manifest_file_count": len(manifest["files"]), "verified_sha_count": verified_count,
            "extracted_root": str(extracted), "data_root": str(data),
            "first_launch": first_doc, "second_launch": second_doc,
            "continuity": {"project_id": project, "revision_before": 0, "revision_after": reopened["revision"],
                           "media_sha256": created, "media_bytes_preserved": True},
            "authoring_v3": {"prompt_path": V3_PROMPT_RELATIVE,
                             "prompt_sha256": V3_PROMPT_SHA256, **packaged_authoring},
            "negatives": {"occupied_port": "PASS", "missing_ffmpeg": "PASS",
                          "missing_frontend_runtime": "PASS_BUILD_MISSING_NO_DATA_MUTATION"},
            "negative_details": {"missing_frontend_runtime": {
                "exit_code": corrupt.returncode,
                "studio_ready": "STUDIO_READY" in corrupt_text,
                "api_ready": bool(corrupt_evidence.get("api_ready")),
                "ui_status": corrupt_evidence.get("ui_status"),
                "data_tree_before_sha256": _tree_identity_digest(persisted_before),
                "data_tree_after_sha256": _tree_identity_digest(persisted_after),
            }},
            "commands": {"first_skip_bootstrap": False, "second_skip_bootstrap": True},
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"status": "CLEAN_PACKAGE_PASS", "evidence": str(output),
                      "source_commit": report["source_commit"],
                      "archive_sha256": report["archive_sha256"]}))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "reports/acceptance/generated/clean-package-launch.json")
    args = parser.parse_args()
    run(args.output.resolve())


if __name__ == "__main__":
    main()
