"""Project lifetime, conflict checks, locks and validated draft context."""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from pathlib import Path

from sprite_pipeline.application.rendering import RenderResult, RenderService
from sprite_pipeline.domain.actions import validate_editor
from sprite_pipeline.domain.errors import ConflictError
from sprite_pipeline.storage.cache import RenderCache
from sprite_pipeline.storage.configuration import (
    IMAGE_SUFFIXES,
    REFERENCE_IMAGE_SUFFIXES,
    Config,
    ConfigRepository,
    config_from_data,
    inside,
)
from sprite_pipeline.storage.history import HistoryConflictError, ProjectHistory
from sprite_pipeline.storage.locking import project_lock

REFERENCE_DIRS = ("references", "reference")


class ProjectSession:
    def __init__(self, path: Path, project_id: str | None = None):
        self.path = path.resolve()
        self.project_id = project_id
        self.configs = ConfigRepository(self.path)
        self.lock = project_lock(self.path)
        self._image_config = self.configs.load()
        self._image_config_signature = self.config_signature()
        self._asset_metadata: dict[
            Path, tuple[tuple[int, int], list[int], tuple[int, int, int, int] | None]
        ] = {}
        self.versions = ProjectHistory(self.path.parent)
        self.renderer = RenderService()
        self._encoded_cache: RenderCache[str] = RenderCache(32 * 1024 * 1024)

    def history_transaction(self, operation: str, paths: list[Path]):
        if all(path.resolve().is_relative_to(self.path.parent) for path in paths):
            return self.versions.transaction(operation, paths)
        # Explicit --config projects may keep source/processed paths outside
        # their config directory. Their legacy operations remain available.
        return nullcontext()

    def history_entries(self) -> list[dict]:
        with self.lock:
            return self.versions.list()

    def restore(self, version_id: str, revision: str, asset_revision: str | None = None) -> dict:
        with self.lock:
            self.check_revision(revision)
            self.check_assets(asset_revision)
            try:
                self.versions.restore(version_id, lambda: validate_editor(self.configs.load()))
            except HistoryConflictError as error:
                raise ConflictError(str(error)) from error
            return self.state()

    def config_signature(self) -> str:
        return self.revision

    def validate_source_location(self, cfg: Config) -> None:
        if self.project_id not in (None, "@config"):
            source = cfg.source
            if not source.is_relative_to(self.path.parent) or source == self.path.parent:
                raise ValueError(
                    "工作区工程的 source 必须位于工程目录内；旧布局请使用 --config 打开。"
                )

    @property
    def revision(self) -> str:
        return self.configs.revision

    def check_revision(self, revision: str) -> None:
        if revision != self.revision:
            raise ConflictError(
                "工程已被其他窗口或命令行修改，请重新载入后再操作；当前草稿仍保留在页面中。"
            )

    def asset_revision(self, cfg: Config) -> str:
        digest = hashlib.sha256()
        for kind, root in (
            ("source", cfg.source),
            ("slices", cfg.directory("source_sprites")),
            ("processed", cfg.directory("processed_sprites")),
            ("final", cfg.directory("sprites")),
            *((name, self.reference_root(name)) for name in REFERENCE_DIRS),
        ):
            suffixes = REFERENCE_IMAGE_SUFFIXES if kind in REFERENCE_DIRS else IMAGE_SUFFIXES
            for path in sorted(root.rglob("*")):
                if not path.is_file() or (
                    path.suffix.lower() not in suffixes and path.name != "_stage.json"
                ):
                    continue
                relative = path.relative_to(root).as_posix()
                inside(root, relative)
                stat = path.stat()
                digest.update(json.dumps([kind, relative, stat.st_mtime_ns, stat.st_size]).encode())
        return digest.hexdigest()

    def check_assets(self, revision: str | None) -> None:
        if revision is not None and revision != self.asset_revision(self.configs.load()):
            raise ConflictError("工程素材已被外部修改，请刷新素材后重试；当前草稿仍保留。")

    def changes(self) -> dict:
        with self.lock:
            return {
                "revision": self.revision,
                "asset_revision": self.asset_revision(self.configs.load()),
            }

    def draft(self, data: dict) -> Config:
        current = self.configs.load()
        cfg = config_from_data(data, self.path)
        for filename, settings in cfg.data.get("sources", {}).items():
            minimum = current.source_spec(filename)["extract"].get("next_id", 0)
            if minimum:
                extraction = settings.setdefault("extract", {})
                extraction["next_id"] = max(minimum, extraction.get("next_id", 0))
        if cfg.data.get("paths") != current.data.get("paths"):
            raise ValueError(
                "The editor cannot change project paths; open another project with --config"
            )
        if cfg.character != current.character:
            raise ValueError("The editor cannot change the project character ID")
        if max(cfg.size) > 4096:
            raise ValueError("Workbench frame dimensions must be <= 4096 pixels")
        return cfg

    def image_path(self, kind: str, reference: str) -> Path:
        signature = self.config_signature()
        if signature != self._image_config_signature:
            self._image_config = self.configs.load()
            self._image_config_signature = signature
        cfg = self._image_config
        self.validate_source_location(cfg)
        roots = {
            "source": cfg.source,
            "processed": cfg.directory("processed_sprites"),
            "reference": self.path.parent,
        }
        if kind not in roots:
            raise ValueError("Unknown image category")
        path = inside(roots[kind], reference)
        if kind == "reference":
            directory = Path(reference).parts[0]
            if directory not in REFERENCE_DIRS or not path.is_relative_to(
                self.reference_root(directory)
            ):
                raise ValueError("Reference images must be inside references/ or legacy reference/")
        suffixes = REFERENCE_IMAGE_SUFFIXES if kind == "reference" else IMAGE_SUFFIXES
        if path.suffix.lower() not in suffixes or not path.is_file():
            raise FileNotFoundError(reference)
        return path

    def reference_root(self, name: str = "references") -> Path:
        if name not in REFERENCE_DIRS:
            raise ValueError("Unknown reference directory")
        return inside(self.path.parent, name)

    def render(self, data: dict, filename: str, stage: str = "process") -> RenderResult:
        return self.renderer.render(self.draft(data), filename, stage)

    def state(self) -> dict:
        from sprite_pipeline.application.queries import project_state

        return project_state(self)
