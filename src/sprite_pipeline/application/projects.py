"""Filesystem-backed project discovery and creation, shared by GUI and agents."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from sprite_pipeline.application.project import Project
from sprite_pipeline.domain.errors import ConflictError
from sprite_pipeline.storage.configuration import (
    NAME,
    PROJECT_PATHS,
    Config,
    config_from_data,
    inside,
    load_config,
)
from sprite_pipeline.storage.files import write_json
from sprite_pipeline.storage.locking import project_lock

DEFAULT_WORKSPACES = Path(__file__).resolve().parents[3] / "workspaces"
EXTERNAL_ID = "@config"


def validate_project_id(value: str) -> str:
    """Portable single directory names; Unicode is supported on Windows too."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 80
        or value != value.strip()
        or value in {".", ".."}
        or value.startswith(".")
        or value.endswith(".")
        or any(ord(c) < 32 or c in '\\/:*?"<>|@' for c in value)
        or value.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *[f"COM{i}" for i in range(1, 10)],
            *[f"LPT{i}" for i in range(1, 10)],
        }
    ):
        raise ValueError(
            "工程目录名无效：请使用 1–80 个字符，避开路径分隔符、末尾句点及 Windows 保留名称。"
        )
    return value


class ProjectStore:
    def __init__(self, root: Path = DEFAULT_WORKSPACES, config_path: Path | None = None):
        self.root = root.resolve()
        self.cache: dict[Path, Project] = {}
        self._validated: dict[Path, str] = {}
        self._validated_config: dict[Path, Config] = {}
        self.lock = threading.RLock()
        self.initial_id = None
        self.external = None
        if config_path is not None:
            config_path = config_path.resolve()
            cfg = load_config(config_path)
            if (
                config_path.name == "pipeline.json"
                and config_path.parent.parent == self.root
                and cfg.source != config_path.parent
                and cfg.source.is_relative_to(config_path.parent)
            ):
                self.initial_id = config_path.parent.name
                self.get(self.initial_id)
            else:
                self.external = config_path
                self.initial_id = EXTERNAL_ID

    def config_path(self, project_id: str) -> Path:
        if project_id == EXTERNAL_ID and self.external is not None:
            return self.external
        validate_project_id(project_id)
        directory = inside(self.root, project_id)
        if directory.parent != self.root:
            raise ValueError("工程目录必须直接位于工作区根目录下。")
        path = directory / "pipeline.json"
        if path.resolve().parent != directory:
            raise ValueError("工程配置不能链接到其他目录。")
        return path

    def get(self, project_id: str) -> Project:
        path = self.config_path(project_id)
        with self.lock:
            cached = self.cache.get(path)
            if cached is not None and self._validated.get(path) == cached.config_signature():
                if project_id != EXTERNAL_ID:
                    source = self._validated_config[path].source
                    if not source.is_relative_to(path.parent) or source == path.parent:
                        raise ValueError(
                            "工作区工程的 source 必须位于工程目录内；旧布局请使用 --config 打开。"
                        )
                return cached
        signature = hashlib.sha256(path.read_bytes()).hexdigest()
        cfg = load_config(path)
        if project_id != EXTERNAL_ID:
            if not cfg.source.is_relative_to(path.parent) or cfg.source == path.parent:
                raise ValueError(
                    "工作区工程的 source 必须位于工程目录内；旧布局请使用 --config 打开。"
                )
        with self.lock:
            if path not in self.cache:
                self.cache[path] = Project(path, project_id=project_id)
            if self.cache[path].config_signature() != signature:
                raise ConflictError("工程配置正在变化，请稍后重试。")
            self._validated[path] = signature
            self._validated_config[path] = cfg
            return self.cache[path]

    def image_project(self, project_id: str) -> Project:
        """Reuse validated image roots while the config file is unchanged."""
        return self.get(project_id)

    def describe(self, project_id: str) -> dict:
        project = self.get(project_id)
        cfg = load_config(project.path)
        return {
            "id": project_id,
            "name": cfg.data.get("project", {}).get("name") or cfg.character,
            "character": cfg.character,
            "frame_size": list(cfg.size),
            "directory": str(project.path.parent),
            "config": str(project.path),
            "external": project_id == EXTERNAL_ID,
        }

    def list(self) -> list[dict]:
        entries = []
        if self.external is not None:
            try:
                entries.append(self.describe(EXTERNAL_ID))
            except (ValueError, OSError, TypeError, KeyError) as error:
                entries.append(
                    {"id": EXTERNAL_ID, "name": self.external.parent.name, "error": str(error)}
                )
        if self.root.is_dir():
            for directory in sorted(self.root.iterdir(), key=lambda p: p.name.casefold()):
                if directory.name.startswith(".") or not (directory / "pipeline.json").is_file():
                    continue
                if (
                    self.external is not None
                    and (directory / "pipeline.json").resolve() == self.external
                ):
                    continue
                try:
                    entries.append(self.describe(directory.name))
                except (ValueError, OSError, TypeError, KeyError) as error:
                    entries.append(
                        {"id": directory.name, "name": directory.name, "error": str(error)}
                    )
        return entries

    def create(
        self,
        name: str,
        project_id: str | None = None,
        *,
        frame_size: list[int] | None = None,
        anchor: list[float] | None = None,
    ) -> dict:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError("请输入 1–120 个字符的工程名称。")
        name = name.strip()
        project_id = validate_project_id(name if project_id is None else project_id)
        size = [640, 640] if frame_size is None else frame_size
        anchor = [0.5, 0.9] if anchor is None else anchor
        if (
            not isinstance(anchor, list)
            or len(anchor) != 2
            or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1
                for v in anchor
            )
        ):
            raise ValueError("anchor must contain normalized x/y values between 0 and 1")
        character = (
            project_id
            if NAME.fullmatch(project_id)
            else "character-" + hashlib.sha256(project_id.encode()).hexdigest()[:10]
        )
        data = {
            "version": 2,
            "project": {"name": name},
            "character": character,
            "frame_size": size,
            "paths": dict(PROJECT_PATHS),
            "defaults": {
                "fps": 12,
                "loop": False,
                "extract": {
                    "method": "components",
                    "min_component_pixels": 16,
                    "major_min_pixels": 80,
                },
                "process": {"mode": "anchor", "overflow": "error"},
                "pack": {"columns": 4},
            },
            "sources": {},
            "actions": {},
            "workbench": {"reviews": {}},
        }
        # Validate size before using it in arithmetic, and validate before creating files.
        destination = self.config_path(project_id).parent
        cfg = config_from_data(data, destination / "pipeline.json")
        if max(cfg.size) > 4096:
            raise ValueError("Workbench frame dimensions must be <= 4096 pixels")
        data["anchor"] = {
            "x": anchor[0],
            "y": anchor[1],
            "pixels": [round(size[0] * anchor[0]), round(size[1] * anchor[1])],
        }
        config_from_data(data, destination / "pipeline.json")
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock, project_lock(self.root / "projects.json"):
            if any(p.name.casefold() == project_id.casefold() for p in self.root.iterdir()):
                raise FileExistsError("工程目录已存在，请换一个目录名；已有内容不会被覆盖。")
            # Publish a complete project only after initialization succeeds. Windows
            # rename also rejects a destination created by a competing process.
            with TemporaryDirectory(prefix=".sprite-project-", dir=self.root) as temporary:
                staged = Path(temporary) / project_id
                staged.mkdir()
                for directory in ("source", "source_sprites", "processed_sprites", "references"):
                    (staged / directory).mkdir()
                write_json(staged / "pipeline.json", data)
                (staged / "README.md").write_text(
                    f"# {name}\n\n原图放入 source/，参考资料放入 references/。\n"
                    "处理规则、动作和 Review 统一保存于 pipeline.json。\n"
                    "人工修图放入 processed_sprites/imports/，保持工程画布尺寸。\n"
                    "source_sprites/ 是可重建缓存；exports/ 仅按需生成。\n",
                    encoding="utf-8",
                )
                staged.rename(destination)
        return self.describe(project_id)
