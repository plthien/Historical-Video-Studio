"""Content-addressed originals; byte verification on every read and collision."""
from __future__ import annotations
import hashlib
import os
import re
import tempfile
from pathlib import Path
from backend.app.contracts import ContractViolation

_HEX = re.compile(r"^[0-9a-f]{64}$")


class ArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path(self, sha256: str) -> Path:
        if not _HEX.fullmatch(sha256):
            raise ContractViolation("ARTIFACT_SHA_INVALID", "sha256", "Use lowercase 64-character SHA-256.")
        return self.root / "sha256" / sha256[:2] / sha256[2:]

    def put(self, data: bytes, claimed_sha256: str | None = None) -> tuple[str, bool]:
        digest = hashlib.sha256(data).hexdigest()
        if claimed_sha256 is not None and claimed_sha256 != digest:
            raise ContractViolation("ARTIFACT_SHA_MISMATCH", "sha256", "Re-upload the original bytes matching SHA-256.")
        path = self.path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self.read(digest)
            return digest, False
        fd, temp_path = tempfile.mkstemp(prefix=".write-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            # Never overwrite existing content if another writer won the race.
            if path.exists():
                self.read(digest)
                return digest, False
            os.replace(temp_path, path)
            return digest, True
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def read(self, sha256: str) -> bytes:
        path = self.path(sha256)
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise ContractViolation("ARTIFACT_MISSING", sha256, "Restore immutable original media bytes.") from exc
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ContractViolation("ARTIFACT_CORRUPT", sha256, "Original bytes changed; recover original file.")
        return data
