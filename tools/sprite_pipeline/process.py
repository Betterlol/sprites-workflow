"""Normalize native slices or loose source PNGs into reviewable sprites."""

from __future__ import annotations

import math
import json
from pathlib import Path

from PIL import Image

from .config import Config, NAME, inside, integer, merge, positive
from .files import read_image, replace_frames


def alpha_bbox(image: Image.Image, threshold: int) -> tuple | None:
    return image.getchannel("A").point(lambda value: 255 if value >= threshold else 0).getbbox()


def offset_pair(value, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must be [x, y]")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError(f"{label} must contain finite numbers")
    return tuple(value)


def normalize(image: Image.Image, cfg: Config, settings: dict, scale: float) -> Image.Image:
    mode = settings.get("mode", "anchor")
    if mode == "copy":
        if image.size != cfg.size:
            raise ValueError(f"copy mode requires {cfg.size}, got {image.size}")
        return image
    scale = positive(settings.get("scale", scale), "process.scale")
    if mode == "anchor":
        threshold = integer(settings.get("alpha_threshold", 16), "process.alpha_threshold", 1)
        if threshold > 255:
            raise ValueError("process.alpha_threshold must be <= 255")
        box = alpha_bbox(image, threshold)
        if box is None:
            raise ValueError("Cannot anchor an empty sprite")
        cropped = image.crop(box)
    elif mode == "contain":
        cropped = image
        scale = min(cfg.size[0] / image.width, cfg.size[1] / image.height) * scale
    else:
        raise ValueError(f"Unknown processing mode: {mode}")
    # Keep a single scale for the action; individual overrides are explicit.
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    cropped = cropped.resize(size, Image.Resampling.LANCZOS)
    dx, dy = offset_pair(settings.get("offset", [0, 0]), "process.offset")
    width, height = cfg.size
    x = (width - cropped.width) // 2 + round(dx)
    if mode == "anchor":
        x = round(cfg.anchor["pixels"][0]) - (cropped.width + 1) // 2 + round(dx)
        y = round(cfg.anchor["pixels"][1] - cropped.height + dy)
    else:
        y = (height - cropped.height) // 2 + round(dy)
    if settings.get("clamp_y", False):
        padding = integer(settings.get("padding", 0), "process.padding")
        y = max(padding, min(height - cropped.height - padding, y))
    overflow = settings.get("overflow", "error")
    if overflow not in {"error", "clip"}:
        raise ValueError("process.overflow must be 'error' or 'clip'")
    if overflow == "error" and (x < 0 or y < 0 or x + cropped.width > width or y + cropped.height > height):
        raise ValueError(f"Sprite would be clipped at {(x, y)} with size {cropped.size}; adjust canvas/scale/offset or set overflow='clip'")
    canvas = Image.new("RGBA", cfg.size, (0, 0, 0, 0))
    canvas.alpha_composite(cropped, (x, y))
    return canvas


def process_action(cfg: Config, name: str) -> int:
    spec = cfg.action(name)
    settings = spec.get("process", {})
    # Explicit inputs bypass extraction. Each input has a stable ID and stage.
    inputs = settings.get("inputs")
    sources: dict[str, Path] = {}
    if inputs is not None:
        if not isinstance(inputs, dict) or not inputs:
            raise ValueError(f"{name}.process.inputs must be a nonempty object")
        for key, item in inputs.items():
            if not NAME.fullmatch(key):
                raise ValueError(f"Invalid processed sprite ID: {key!r}")
            stage = item.get("stage", "source")
            if stage not in {"source", "source_sprites"}:
                raise ValueError("process.inputs stage must be source or source_sprites")
            sources[key] = inside(cfg.source if stage == "source" else cfg.directory(stage), item["file"])
    elif spec.get("extract") is not None:
        directory = cfg.directory("source_sprites") / name
        # Use the extraction inventory, not a glob that could include review PNGs.
        inventory = json.loads((directory / "_stage.json").read_text(encoding="utf-8"))
        sources = {Path(ref).stem: inside(directory, ref) for ref in inventory["files"]}
    imports = spec.get("imports", {})
    if not sources and not imports:
        raise ValueError(f"{name}: no processing inputs; run extract or configure process.inputs/imports")
    images = {key: read_image(path) for key, path in sources.items()}
    scale = positive(settings.get("scale", 1.0), f"{name}.process.scale")
    if settings.get("fit_height") is not None and images:
        target = positive(settings["fit_height"], "process.fit_height")
        threshold = integer(settings.get("alpha_threshold", 16), "process.alpha_threshold", 1)
        if threshold > 255:
            raise ValueError("process.alpha_threshold must be <= 255")
        boxes = [alpha_bbox(image, threshold) for image in images.values()]
        if any(box is None for box in boxes):
            raise ValueError(f"{name}: an empty processing input was found")
        scale *= min(positive(settings.get("max_scale", 1.0), "process.max_scale"), target / max(box[3] - box[1] for box in boxes))
    overrides = settings.get("overrides", {})
    unknown = set(overrides) - set(images)
    if unknown:
        raise ValueError(f"{name}: process overrides refer to unknown sprite IDs: {sorted(unknown)}")
    frames: dict[str, Image.Image | Path] = {}
    for key, image in images.items():
        options = merge(settings, overrides.get(key, {}))
        # The base scale has already been combined with fit_height above.
        options.pop("scale", None)
        if "scale" in overrides.get(key, {}):
            options["scale"] = overrides[key]["scale"]
        frames[f"{key}.png"] = normalize(image, cfg, options, scale)
    # Approved anchor poses are copied byte-for-byte, without normalization.
    for key, ref in imports.items():
        if not NAME.fullmatch(key) or f"{key}.png" in frames:
            raise ValueError(f"Invalid or duplicate imported sprite ID: {key!r}")
        path = inside(cfg.source, ref)
        if read_image(path).size != cfg.size:
            raise ValueError(f"{name}/{key}: imported sprite must be {cfg.size}")
        frames[f"{key}.png"] = path
    replace_frames(cfg.directory("processed_sprites") / name, frames, owned=r"\d+\.png", metadata={
        "stage": "process", "scale": scale, "files": list(frames),
        "inputs": {key: {
            "stage": "source" if path.is_relative_to(cfg.source) else "source_sprites",
            "file": path.relative_to(cfg.source if path.is_relative_to(cfg.source) else cfg.directory("source_sprites")).as_posix(),
        } for key, path in sources.items()},
        "imports": imports,
    })
    return len(frames)
