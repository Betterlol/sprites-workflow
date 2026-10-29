"""Normalize pixels with resolved settings; no project or path IO."""

import hashlib
import json
import math
from dataclasses import dataclass

from PIL import Image

from sprite_pipeline.domain.models import Cache, CanvasSpec
from sprite_pipeline.domain.validation import integer, merge, positive


@dataclass(frozen=True)
class ProcessResult:
    frames: dict[str, Image.Image]
    scale: float
    versions: dict[str, str]


def alpha_bbox(image: Image.Image, threshold: int) -> tuple | None:
    return image.getchannel("A").point(lambda value: 255 if value >= threshold else 0).getbbox()


def offset_pair(value, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must be [x, y]")
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in value
    ):
        raise ValueError(f"{label} must contain finite numbers")
    return tuple(value)


def normalize(image: Image.Image, cfg: CanvasSpec, settings: dict, scale: float) -> Image.Image:
    mode = settings.get("mode", "anchor")
    scale_x = positive(settings.get("scale_x", 1.0), "process.scale_x")
    if mode == "copy":
        if scale_x != 1:
            raise ValueError(
                "copy mode requires process.scale_x = 1; use anchor or contain to resize"
            )
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
    # Horizontal adjustment follows the resolved uniform scale; height and anchors stay shared.
    size = (
        max(1, round(cropped.width * scale * scale_x)),
        max(1, round(cropped.height * scale)),
    )
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
    if overflow == "error" and (
        x < 0 or y < 0 or x + cropped.width > width or y + cropped.height > height
    ):
        raise ValueError(
            f"Sprite would be clipped at {(x, y)} with size {cropped.size}; adjust canvas/scale/offset or set overflow='clip'"
        )
    canvas = Image.new("RGBA", cfg.size, (0, 0, 0, 0))
    canvas.alpha_composite(cropped, (x, y))
    return canvas


def process_frames(
    cfg: CanvasSpec,
    filename: str,
    settings: dict,
    images: dict[str, Image.Image],
    *,
    cache: Cache[Image.Image] | None = None,
) -> ProcessResult:
    if not images:
        raise ValueError("No extracted frames to process")
    scale = positive(settings.get("scale", 1.0), f"{filename}.process.scale")
    if settings.get("fit_height") is not None and images:
        target = positive(settings["fit_height"], "process.fit_height")
        threshold = integer(settings.get("alpha_threshold", 16), "process.alpha_threshold", 1)
        if threshold > 255:
            raise ValueError("process.alpha_threshold must be <= 255")
        boxes = [alpha_bbox(image, threshold) for image in images.values()]
        if any(box is None for box in boxes):
            raise ValueError(f"{filename}: an empty processing input was found")
        scale *= min(
            positive(settings.get("max_scale", 1.0), "process.max_scale"),
            target / max(box[3] - box[1] for box in boxes),
        )
    overrides = settings.get("overrides", {})
    unknown = set(overrides) - set(images)
    if unknown:
        raise ValueError(
            f"{filename}: process overrides refer to unknown sprite IDs: {sorted(unknown)}"
        )
    frames = {}
    versions = {}
    base_settings = {key: value for key, value in settings.items() if key != "overrides"}
    for key, image in images.items():
        options = merge(base_settings, overrides.get(key, {}))
        # The base scale has already been combined with fit_height above.
        options.pop("scale", None)
        if "scale" in overrides.get(key, {}):
            options["scale"] = overrides[key]["scale"]
        digest = hashlib.sha256(image.tobytes())
        digest.update(
            json.dumps([image.size, cfg.size, cfg.anchor, options, scale], sort_keys=True).encode()
        )
        version = digest.hexdigest()
        rendered = cache.get(version) if cache is not None else None
        if rendered is None:
            rendered = normalize(image, cfg, options, scale)
            if cache is not None:
                cache.put(version, rendered, rendered.width * rendered.height * 4)
        frames[f"{key}.png"] = rendered
        versions[f"{key}.png"] = version
    return ProcessResult(frames, scale, versions)
