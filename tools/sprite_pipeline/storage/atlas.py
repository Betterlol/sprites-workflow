"""Write spritesheet metadata in TexturePacker's JSON Hash format."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class TexturePackerFrame:
    """One untrimmed rectangular frame in a finished spritesheet."""

    filename: str
    x: int
    y: int
    w: int
    h: int
    duration_ms: int


def write_texturepacker_hash(
    output_path: Path,
    *,
    image_name: str,
    sheet_width: int,
    sheet_height: int,
    frames: Iterable[TexturePackerFrame],
) -> None:
    """Serialize a final spritesheet as a TexturePacker-compatible JSON Hash.

    Frames are intentionally exported untrimmed because the Dafeiyu sprites use
    fixed-size canvases and a shared runtime anchor.  Anchor data remains in the
    project's animation metadata, where it can be interpreted per engine.
    """

    if sheet_width <= 0 or sheet_height <= 0:
        raise ValueError("spritesheet dimensions must be positive")

    texturepacker_frames: dict[str, dict] = {}
    for item in frames:
        if item.filename in texturepacker_frames:
            raise ValueError(f"duplicate frame filename: {item.filename}")
        if item.w <= 0 or item.h <= 0 or item.x < 0 or item.y < 0:
            raise ValueError(f"invalid frame rectangle for {item.filename}")
        if item.x + item.w > sheet_width or item.y + item.h > sheet_height:
            raise ValueError(f"frame exceeds spritesheet bounds: {item.filename}")
        if item.duration_ms <= 0:
            raise ValueError(f"frame duration must be positive: {item.filename}")

        texturepacker_frames[item.filename] = {
            "frame": {"x": item.x, "y": item.y, "w": item.w, "h": item.h},
            "rotated": False,
            "trimmed": False,
            "spriteSourceSize": {"x": 0, "y": 0, "w": item.w, "h": item.h},
            "sourceSize": {"w": item.w, "h": item.h},
            "duration": item.duration_ms,
        }

    payload = {
        "frames": texturepacker_frames,
        "meta": {
            "app": "deepseek-workflow",
            "version": "1.0",
            "image": image_name,
            "format": "RGBA8888",
            "size": {"w": sheet_width, "h": sheet_height},
            "scale": "1",
        },
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
