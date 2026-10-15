"""Configuration and shared validation; paths are relative to the config file."""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path


OUTPUT_DIRS = ("source_sprites", "processed_sprites", "sprites", "spritesheets", "webp", "metadata")
NAME = re.compile(r"[A-Za-z0-9_-]+\Z")


def positive(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return value


def integer(value, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError(f"Expected a nonempty relative path: {relative!r}")
    path = (root / relative).resolve()
    if path == root.resolve() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes its stage directory: {relative!r}")
    return path


def merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


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
        return merge(self.data.get("defaults", {}), self.data["actions"][name])


def load_config(path: Path, output_root: Path | None = None) -> Config:
    path = path.resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("Unsupported pipeline config version; expected 1")
    if not NAME.fullmatch(data.get("character", "")):
        raise ValueError("character must contain only letters, numbers, underscores and hyphens")
    size = data.get("frame_size")
    if not isinstance(size, list) or len(size) != 2:
        raise ValueError("frame_size must be [width, height]")
    for dimension in size:
        integer(dimension, "frame_size", 1)
    if "anchor" not in data:
        data["anchor"] = {"x": 0.5, "y": 1.0, "pixels": [size[0] // 2, size[1]]}
    anchor = data["anchor"]
    if not isinstance(anchor, dict) or not isinstance(anchor.get("pixels"), list) or len(anchor["pixels"]) != 2:
        raise ValueError("anchor must include pixels: [x, y]")
    for axis in ("x", "y"):
        value = anchor.get(axis)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"anchor.{axis} must be between 0 and 1")
    for value, limit in zip(anchor["pixels"], size):
        integer(value, "anchor.pixels")
        if value > limit:
            raise ValueError("anchor.pixels must be within the frame canvas")
    data.setdefault("paths", {})
    cfg = Config(path, (output_root or path.parent).resolve(), data)
    dirs = [cfg.directory(stage) for stage in OUTPUT_DIRS]
    for i, directory in enumerate(dirs):
        for other in dirs[i + 1:]:
            if directory.is_relative_to(other) or other.is_relative_to(directory):
                raise ValueError("Output stage directories must be distinct and must not contain each other")
        if cfg.source.is_relative_to(directory) or directory.is_relative_to(cfg.source):
            raise ValueError("Source and output stage directories must not overlap")
    if not isinstance(data.get("actions"), dict) or not data["actions"]:
        raise ValueError("actions must be a nonempty object")
    for name in data["actions"]:
        if not NAME.fullmatch(name):
            raise ValueError(f"Invalid action name: {name!r}")
        spec = cfg.action(name)
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
