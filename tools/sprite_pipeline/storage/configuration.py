"""Configuration and shared validation; paths are relative to the config file."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from sprite_pipeline.storage.files import write_json

OUTPUT_DIRS = ("source_sprites", "processed_sprites", "sprites", "spritesheets", "webp", "metadata")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
from sprite_pipeline.domain.validation import NAME, integer, merge, positive

PROJECT_PATHS = {
    "source": "source",
    "source_sprites": "source_sprites",
    "processed_sprites": "processed_sprites",
    "sprites": "exports/frames",
    "spritesheets": "exports/sheets",
    "webp": "exports/previews",
    "metadata": "exports/metadata",
    "manifest": "exports/manifest.json",
}


def inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError(f"Expected a nonempty relative path: {relative!r}")
    path = (root / relative).resolve()
    if path == root.resolve() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes its stage directory: {relative!r}")
    return path


@dataclass(frozen=True)
class Config:
    path: Path
    root: Path
    data: dict

    @property
    def character(self) -> str:
        return self.data["character"]

    @property
    def size(self) -> tuple[int, int]:
        return tuple(self.data["frame_size"])

    @property
    def anchor(self) -> dict:
        return self.data["anchor"]

    @property
    def source(self) -> Path:
        return (self.path.parent / self.data["paths"].get("source", "source")).resolve()

    def directory(self, stage: str) -> Path:
        return inside(self.root, self.data["paths"].get(stage, stage))

    def action(self, name: str) -> dict:
        defaults = {
            key: value
            for key, value in self.data.get("defaults", {}).items()
            if key not in {"extract", "process"}
        }
        return merge(defaults, self.data["actions"][name])

    def select_actions(
        self, included: list[str] | None = None, excluded: list[str] | None = None
    ) -> list[str]:
        """Resolve CLI action filters without changing the project or authored order."""
        selected = list(dict.fromkeys(self.data["actions"] if included is None else included))
        exclusions = set(excluded or [])
        unknown = (set(selected) | exclusions) - set(self.data["actions"])
        if unknown:
            raise ValueError(f"Unknown actions: {', '.join(sorted(unknown))}")
        selected = [name for name in selected if name not in exclusions]
        if not selected and exclusions:
            raise ValueError("No actions remain after --action/--exclude-action filtering")
        return selected

    def source_spec(self, filename: str) -> dict:
        defaults = {
            key: self.data.get("defaults", {}).get(key, {}) for key in ("extract", "process")
        }
        return merge(defaults, self.data.get("sources", {}).get(filename, {}))

    def source_id(self, filename: str) -> str:
        return Path(filename).with_suffix("").as_posix()

    def discover_sources(
        self, *, allow_empty: bool = False, allow_missing: bool = False
    ) -> list[str]:
        """Discover every original image, regardless of action selections."""
        if not self.source.is_dir():
            if allow_empty and allow_missing:
                return []
            raise FileNotFoundError(f"Source directory does not exist: {self.source}")
        filenames = sorted(
            path.relative_to(self.source).as_posix()
            for path in self.source.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if not filenames and not allow_empty:
            raise ValueError(f"No source images found in {self.source}")
        stale = set(self.data.get("sources", {})) - set(filenames)
        if stale and not allow_missing:
            raise ValueError(f"Source rules refer to missing images: {', '.join(sorted(stale))}")
        ids = {}
        for filename in filenames:
            inside(self.source, filename)
            key = self.source_id(filename).casefold()
            if key.split("/")[0] in {"imports", "_approved"}:
                raise ValueError(f"Source name uses a reserved processed directory: {filename}")
            if key in ids:
                raise ValueError(
                    f"Source images share the same output directory: {ids[key]}, {filename}"
                )
            ids[key] = filename
        # A file foo.png and nested foo/bar.png would mix inventories/outputs.
        keys = [Path(key) for key in ids]
        for i, key in enumerate(keys):
            if any(
                key.is_relative_to(other) or other.is_relative_to(key) for other in keys[i + 1 :]
            ):
                raise ValueError("Source image output directories must not contain each other")
        return filenames


def load_config(path: Path, output_root: Path | None = None) -> Config:
    path = path.resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    return config_from_data(data, path, output_root)


def source_fingerprint(cfg: Config, filename: str) -> str:
    digest = hashlib.sha256(inside(cfg.source, filename).read_bytes())
    digest.update(
        json.dumps(
            {"rules": cfg.source_spec(filename), "size": cfg.size, "anchor": cfg.anchor},
            sort_keys=True,
        ).encode()
    )
    return digest.hexdigest()


def config_from_data(data: dict, path: Path, output_root: Path | None = None) -> Config:
    """Validate an independent, in-memory draft without touching project files."""
    path = path.resolve()
    if not isinstance(data, dict):
        raise ValueError("Project configuration must be an object")
    data = copy.deepcopy(data)
    if data.get("version") != 2:
        raise ValueError(
            "Unsupported pipeline config version; expected 2 with separate sources and actions"
        )
    if not NAME.fullmatch(data.get("character", "")):
        raise ValueError("character must contain only letters, numbers, underscores and hyphens")
    project = data.get("project", {})
    if not isinstance(project, dict) or not isinstance(project.get("name", ""), str):
        raise ValueError("project must be an object with an optional display name")
    size = data.get("frame_size")
    if not isinstance(size, list) or len(size) != 2:
        raise ValueError("frame_size must be [width, height]")
    for dimension in size:
        integer(dimension, "frame_size", 1)
    if "anchor" not in data:
        data["anchor"] = {"x": 0.5, "y": 1.0, "pixels": [size[0] // 2, size[1]]}
    anchor = data["anchor"]
    if (
        not isinstance(anchor, dict)
        or not isinstance(anchor.get("pixels"), list)
        or len(anchor["pixels"]) != 2
    ):
        raise ValueError("anchor must include pixels: [x, y]")
    for axis in ("x", "y"):
        value = anchor.get(axis)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise ValueError(f"anchor.{axis} must be between 0 and 1")
    for value, limit in zip(anchor["pixels"], size):
        integer(value, "anchor.pixels")
        if value > limit:
            raise ValueError("anchor.pixels must be within the frame canvas")
    data.setdefault("paths", {})
    if not isinstance(data["paths"], dict):
        raise ValueError("paths must be an object")
    cfg = Config(path, (output_root or path.parent).resolve(), data)
    if "manifest" in data["paths"]:
        manifest = inside(cfg.root, data["paths"]["manifest"])
        if manifest.suffix.lower() != ".json":
            raise ValueError("paths.manifest must be a JSON file")
        if manifest.is_relative_to(cfg.source) or manifest == path:
            raise ValueError("Manifest must not overwrite project inputs")
    dirs = [cfg.directory(stage) for stage in OUTPUT_DIRS]
    for i, directory in enumerate(dirs):
        if "manifest" in data["paths"] and (
            manifest.is_relative_to(directory) or directory.is_relative_to(manifest)
        ):
            raise ValueError("Manifest and output stage directories must not overlap")
        for other in dirs[i + 1 :]:
            if directory.is_relative_to(other) or other.is_relative_to(directory):
                raise ValueError(
                    "Output stage directories must be distinct and must not contain each other"
                )
        if cfg.source.is_relative_to(directory) or directory.is_relative_to(cfg.source):
            raise ValueError("Source and output stage directories must not overlap")
    data.setdefault("actions", {})
    if not isinstance(data["actions"], dict):
        raise ValueError("actions must be an object (it may be empty while preparing sources)")
    if not isinstance(data.get("sources", {}), dict):
        raise ValueError(
            "sources must be an object containing per-file extraction/processing rules"
        )
    if not isinstance(data.get("defaults", {}), dict) or "imports" in data.get("defaults", {}):
        raise ValueError("defaults must be an object without legacy imports")
    for filename, settings in data.get("sources", {}).items():
        inside(cfg.source, filename)
        if (
            Path(filename).as_posix() != filename
            or Path(filename).suffix.lower() not in IMAGE_SUFFIXES
        ):
            raise ValueError(
                f"Source rule keys must be relative image filenames using '/' separators: {filename!r}"
            )
        if not isinstance(settings, dict) or set(settings) - {"extract", "process"}:
            raise ValueError(f"{filename}: source rules may only contain extract and process")
    for settings in [data.get("defaults", {}), *data.get("sources", {}).values()]:
        for field in ("extract", "process"):
            if field in settings and not isinstance(settings[field], dict):
                raise ValueError(
                    f"{field} rules must be objects; every source goes through extraction and processing"
                )
        if {"imports", "inputs"} & set(settings.get("process", {})) or "file" in settings.get(
            "extract", {}
        ):
            raise ValueError(
                "Source files are discovered automatically; imports/inputs/extract.file are no longer supported"
            )
        overrides = settings.get("process", {}).get("overrides", {})
        if not isinstance(overrides, dict) or any(
            not isinstance(value, dict) for value in overrides.values()
        ):
            raise ValueError("process.overrides must map sprite IDs to processing objects")
        split = settings.get("extract", {}).get("split_widest")
        if split is not None and not isinstance(split, dict):
            raise ValueError("extract.split_widest must be an object")
        identities = settings.get("extract", {}).get("identities", [])
        extraction = settings.get("extract", {})
        integer(extraction.get("next_id", 0), "extract.next_id")
        region_ids = extraction.get("region_ids")
        if region_ids is not None:
            if (
                not isinstance(region_ids, list)
                or any(
                    not isinstance(key, str) or not re.fullmatch(r"\d{3,}", key)
                    for key in region_ids
                )
                or len(set(region_ids)) != len(region_ids)
                or len({int(key) for key in region_ids}) != len(region_ids)
            ):
                raise ValueError("extract.region_ids must contain unique numeric IDs")
        if not isinstance(identities, list):
            raise ValueError("extract.identities must be an array")
        filenames = set()
        for item in identities:
            if not isinstance(item, dict) or not re.fullmatch(r"\d+\.png", item.get("file", "")):
                raise ValueError(
                    "extract.identities entries need a numeric PNG file and source_box"
                )
            box = item.get("source_box")
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                raise ValueError("extract.identities source_box must have four coordinates")
            for value in box:
                integer(value, "extract.identities source_box")
            if box[0] >= box[2] or box[1] >= box[3] or item["file"] in filenames:
                raise ValueError("extract.identities needs unique IDs and nonempty rectangles")
            filenames.add(item["file"])
    for name in data["actions"]:
        if not NAME.fullmatch(name):
            raise ValueError(f"Invalid action name: {name!r}")
        if not isinstance(data["actions"][name], dict):
            raise ValueError(f"{name}: action configuration must be an object")
        spec = cfg.action(name)
        for field in ("pack", "animation"):
            if field in spec and not isinstance(spec[field], dict):
                raise ValueError(f"{name}.{field} must be an object")
        if {"extract", "process", "imports"} & set(data["actions"][name]):
            raise ValueError(
                f"{name}: actions only assemble processed sprites; put extraction/processing rules in sources"
            )
        fps = positive(spec.get("fps", 12), f"{name}.fps")
        if round(1000 / fps) < 1:
            raise ValueError(f"{name}.fps gives a frame duration below 1ms")
        if not isinstance(spec.get("loop", False), bool):
            raise ValueError(f"{name}.loop must be boolean")
        integer(spec.get("pack", {}).get("columns", 4), f"{name}.pack.columns", 1)
        selection = spec.get("sprites")
        if selection is not None:
            if not isinstance(selection, list) or not selection:
                raise ValueError(f"{name}.sprites must be a nonempty ordered list")
            for ref in selection:
                if inside(cfg.directory("processed_sprites"), ref).suffix.lower() != ".png":
                    raise ValueError(f"{name}.sprites entries must reference PNG files")
    return cfg


@dataclass(frozen=True)
class ConfigSnapshot:
    config: Config
    revision: str


class ConfigRepository:
    """Persistence seam for the current pipeline.json format.

    Callers own project locks and operation transactions. Keeping those scopes
    outside this adapter lets pixel writes and configuration changes roll back
    together. A snapshot's revision always hashes the exact bytes it decoded.
    """

    def __init__(self, path: Path):
        self.path = path.resolve()

    def load(self) -> Config:
        return load_config(self.path)

    def snapshot(self) -> ConfigSnapshot:
        raw = self.path.read_bytes()
        return ConfigSnapshot(
            config_from_data(json.loads(raw), self.path), hashlib.sha256(raw).hexdigest()
        )

    @property
    def revision(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def save(self, data: dict) -> None:
        write_json(self.path, data)
