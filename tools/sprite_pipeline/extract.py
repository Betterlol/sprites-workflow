"""Cut source images at native resolution, without motion order or transforms."""

from __future__ import annotations

import json
from pathlib import Path

from .imaging.extraction import bbox, distance, component_frames, cut_frames
from .domain.identity import preserve_slice_ids

from .config import Config, inside, integer
from .files import read_image
from .slices import write_slices




def slice_ids(cfg: Config, filename: str, boxes: list[tuple]) -> list[str]:
    spec = cfg.source_spec(filename)['extract']
    explicit = spec.get('region_ids') if spec.get('method') == 'boxes' else None
    if explicit is not None:
        if len(explicit) != len(boxes):
            raise ValueError('extract.region_ids must match extract.boxes')
        return list(explicit)
    return preserve_slice_ids(boxes, previous_slices(cfg, filename), spec.get('next_id', 0))


def previous_slices(cfg: Config, filename: str) -> list[dict]:
    authored = cfg.source_spec(filename)["extract"].get("identities")
    if authored:
        return authored
    # Older projects fall back to stage inventories until the first GUI apply.
    for stage in ("processed_sprites", "source_sprites"):
        inventory = inside(cfg.directory(stage), cfg.source_id(filename)) / "_stage.json"
        if inventory.exists():
            payload = json.loads(inventory.read_text(encoding="utf-8"))
            if payload.get("source") == filename and payload.get("frames"):
                return payload["frames"]
    return []










def extract_source(cfg: Config, filename: str) -> int:
    spec = cfg.source_spec(filename)["extract"]
    source_path = inside(cfg.source, filename)
    frames, boxes = cut_frames(read_image(source_path), spec)
    keys = slice_ids(cfg, filename, boxes)
    files = {f"{key}.png": frame for key, frame in zip(keys, frames)}
    write_slices(cfg, filename, dict(zip(keys, frames)),
                 [{"file": name, "source_box": box} for name, box in zip(files, boxes)])
    return len(frames)
