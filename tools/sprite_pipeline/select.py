"""Promote an explicitly ordered list of reviewed sprites with fresh numbering."""

from __future__ import annotations

import re

from .config import Config, inside
from .files import read_image, replace_frames


def select_action(cfg: Config, name: str) -> int:
    selection = cfg.action(name).get("sprites")
    if not selection:
        raise ValueError(f"{name}: configure sprites as an ordered list of processed PNG paths before selecting")
    frames, provenance = {}, []
    for index, reference in enumerate(selection):
        path = inside(cfg.directory("processed_sprites"), reference)
        image = read_image(path)
        if image.size != cfg.size:
            raise ValueError(f"{reference}: expected frame size {cfg.size}, got {image.size}")
        filename = f"{name}_{index:02d}.png"
        frames[filename] = path
        provenance.append({"filename": filename, "processed_sprite": reference})
    replace_frames(cfg.directory("sprites") / name, frames, owned=re.escape(name) + r"_\d+\.png", metadata={
        "stage": "select", "files": list(frames), "frames": provenance,
    })
    return len(frames)
