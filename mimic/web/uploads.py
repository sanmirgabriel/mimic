"""Small managed source files; browser filenames never become server paths."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import UUID, uuid4

from starlette.datastructures import UploadFile

MAX_UPLOAD_BYTES = 16 * 1024 * 1024
CONTEXT_MAX_BYTES = 256 * 1024
DRAFT_TTL_SECONDS = 24 * 60 * 60
ROLES = ("dataset", "ready", "context")


class UploadStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "uploads"

    def path(self, upload_id: str, role: str) -> Path:
        if role not in ROLES or str(UUID(upload_id)) != upload_id:
            raise ValueError("Invalid source file reference. Please upload it again.")
        directory = self.root / upload_id
        path = directory / f"{role}.txt"
        if (self.root.is_symlink() or directory.is_symlink() or path.is_symlink()
                or path.resolve().parent != self.root.resolve() / upload_id):
            raise ValueError("Invalid source file reference. Please upload it again.")
        return path

    def existing(self, upload_id: str, role: str) -> str:
        try:
            path = self.path(upload_id, role)
        except (ValueError, AttributeError) as exc:
            raise ValueError("Invalid source file reference. Please upload it again.") from exc
        if not path.is_file():
            raise ValueError("This source file is no longer available. Please upload it again.")
        return str(path)

    async def save(self, upload: UploadFile, role: str) -> str:
        suffix = Path(upload.filename or "").suffix.lower()
        allowed = (".txt",) if role == "context" else (".txt", ".lst", ".wordlist", ".dic")
        if suffix not in allowed:
            raise ValueError(f"{role.title()} files must use {', '.join(allowed)}.")
        upload_id = str(uuid4())
        path = self.path(upload_id, role)
        path.parent.mkdir(parents=True, exist_ok=False)
        limit = CONTEXT_MAX_BYTES if role == "context" else MAX_UPLOAD_BYTES
        count = 0
        try:
            with path.open("xb") as stream:
                while chunk := await upload.read(64 * 1024):
                    count += len(chunk)
                    if count > limit:
                        raise ValueError(f"{role.title()} file exceeds the {limit // 1024} KiB upload limit.")
                    stream.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
            raise
        return upload_id

    def cleanup(self, jobs: list[dict]) -> None:
        """Remove only abandoned drafts older than 24h; preserve job references."""
        if not self.root.exists() or self.root.is_symlink():
            return
        referenced: set[str] = set()
        for job in jobs:
            request = job["request"]
            sources = request.get("sources", {})
            referenced.update(sources.get("dataset_paths", ()))
            referenced.update(sources.get("ready_candidate_paths", ()))
            if request.get("context_path"):
                referenced.add(request["context_path"])
        cutoff = time.time() - DRAFT_TTL_SECONDS
        for directory in self.root.iterdir():
            if not directory.is_dir() or directory.is_symlink() or directory.stat().st_mtime >= cutoff:
                continue
            try:
                paths = [self.path(directory.name, role) for role in ROLES]
            except ValueError:
                continue
            if any(str(path) in referenced for path in paths):
                continue
            # No recursive deletion: only files this store owns may be removed.
            for path in paths:
                if path.is_file():
                    path.unlink()
            if not any(directory.iterdir()):
                directory.rmdir()
