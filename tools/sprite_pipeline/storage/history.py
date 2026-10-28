"""Incremental, project-local recovery for committed artwork operations."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path

from sprite_pipeline.storage.configuration import inside

VERSION_ID = re.compile(r"\d{20}-[0-9a-f]{8}\Z")


class HistoryConflictError(ValueError):
    """The files to restore no longer match the completed operation."""


class OperationNotStarted(FileExistsError):
    """An exclusive file creation failed before this transaction changed any file."""


class ProjectHistory:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.root = self.project_root / ".sprite-workbench-history"
        self.versions = self.root / "versions"

    def _check_storage(self, *, create: bool = False) -> None:
        for directory in (self.root, self.versions):
            if directory.exists() and directory.resolve() != directory:
                raise ValueError("History directories cannot be links")
        if create:
            self.versions.mkdir(parents=True, exist_ok=True)

    def _relative(self, path: Path) -> str:
        absolute = path.absolute()
        if not absolute.is_relative_to(self.project_root):
            raise ValueError("History can only track files inside the project directory")
        relative = absolute.relative_to(self.project_root).as_posix()
        self._safe(relative)
        return relative

    def _safe(self, relative: str) -> Path:
        path = inside(self.project_root, relative)
        if path.is_relative_to(self.root):
            raise ValueError("History cannot include its own files")
        return path

    def _files(self, roots: list[str]) -> dict[str, Path]:
        files = {}
        for relative in roots:
            root = self._safe(relative)
            candidates = root.rglob("*") if root.is_dir() else [root]
            for path in candidates:
                if path.is_file():
                    name = self._relative(path)
                    files[name] = self._safe(name)
        return files

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _snapshot(self, roots: list[str]) -> dict[str, str]:
        return {name: self._digest(path) for name, path in self._files(roots).items()}

    def _restore_archive(
        self, archive_path: Path, before: dict[str, str], roots: list[str]
    ) -> None:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                if set(archive.namelist()) != set(before):
                    raise ValueError("History archive does not match its manifest")
                # Verify the complete archive before touching any current file.
                for name, expected in before.items():
                    digest = hashlib.sha256()
                    with archive.open(name) as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(block)
                    if digest.hexdigest() != expected:
                        raise ValueError("History archive checksum mismatch: " + name)
                current = self._files(roots)
                for name in sorted(set(current) - set(before), reverse=True):
                    current[name].unlink()
                for name, expected in before.items():
                    path = self._safe(name)
                    if path.is_file() and self._digest(path) == expected:
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(
                        prefix=".sprite-restore-", dir=path.parent
                    ) as temporary:
                        staged = Path(temporary) / path.name
                        with archive.open(name) as source, staged.open("wb") as output:
                            shutil.copyfileobj(source, output)
                        staged.replace(path)
        except (zipfile.BadZipFile, KeyError) as error:
            raise ValueError("History archive is damaged") from error

    @contextmanager
    def transaction(self, operation: str, paths: list[Path]):
        roots = sorted({self._relative(path) for path in paths})
        self._check_storage(create=True)
        pending = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.versions))
        archive_path = pending / "before.zip"
        before = {}
        keep_pending = False
        try:
            files = self._files(roots)
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED) as archive:
                for name, path in files.items():
                    before[name] = self._digest(path)
                    archive.write(path, name)
            try:
                yield
                after = self._snapshot(roots)
                version_id = f"{time.time_ns():020d}-{secrets.token_hex(4)}"
                manifest = {
                    "id": version_id,
                    "operation": operation,
                    "created_at": time.time(),
                    "roots": roots,
                    "before": before,
                    "after": after,
                }
                (pending / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                pending.replace(self.versions / version_id)
            except OperationNotStarted:
                # Another writer owns the destination. Rolling back the
                # before/after difference would remove that writer's file.
                raise
            except BaseException:
                try:
                    self._restore_archive(archive_path, before, roots)
                except BaseException as rollback_error:
                    keep_pending = True
                    raise OSError(
                        f"Automatic rollback failed; backup kept at {pending}"
                    ) from rollback_error
                raise
        finally:
            if pending.exists() and not keep_pending:
                shutil.rmtree(pending)

    def list(self) -> list[dict]:
        self._check_storage()
        if not self.versions.is_dir():
            return []
        result = []
        for directory in sorted(self.versions.iterdir(), reverse=True):
            if not directory.is_dir() or not VERSION_ID.fullmatch(directory.name):
                continue
            if directory.resolve() != directory or (directory / "manifest.json").is_symlink():
                raise ValueError("History version cannot be a link")
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            result.append(
                {
                    "id": manifest["id"],
                    "operation": manifest["operation"],
                    "created_at": manifest["created_at"],
                    "files": len(set(manifest["before"]) | set(manifest["after"])),
                }
            )
        return result

    def restore(self, version_id: str, validate) -> None:
        self._check_storage()
        if not isinstance(version_id, str) or not VERSION_ID.fullmatch(version_id):
            raise ValueError("Invalid history version ID")
        directory = self.versions / version_id
        if directory.resolve() != directory or (directory / "before.zip").is_symlink():
            raise ValueError("History version cannot be a link")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("id") != version_id:
            raise ValueError("History version ID mismatch")
        roots = manifest["roots"]
        before, after = manifest["before"], manifest["after"]
        for name in [*roots, *before, *after]:
            self._safe(name)
        if self._snapshot(roots) != after:
            raise HistoryConflictError(
                "历史版本之后这些文件已被修改，请先备份或重新载入，不能直接覆盖。"
            )
        with self.transaction("restore", [self._safe(name) for name in roots]):
            self._restore_archive(directory / "before.zip", before, roots)
            validate()
