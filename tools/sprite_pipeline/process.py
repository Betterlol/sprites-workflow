"""Process every slice of each original image, independently of actions."""

from __future__ import annotations

import math
import json
import hashlib
from pathlib import Path

from PIL import Image

from .config import Config, inside, integer, merge, positive, source_fingerprint
from .files import read_image, replace_frames
from .slices import read_slices








def process_source(cfg: Config, filename: str) -> int:
    directory = inside(cfg.directory("source_sprites"), cfg.source_id(filename))
    inventory = json.loads((directory / "_stage.json").read_text(encoding="utf-8"))
    if inventory.get("stage") != "extract" or inventory.get("source") != filename:
        raise ValueError(f"{filename}: extraction inventory does not match the original image; run extract")
    cached = read_slices(cfg, filename) if inventory.get('fingerprint') else None
    if inventory.get('fingerprint') and cached is None:
        raise ValueError(f'{filename}: extraction cache is stale or damaged; run extract')
    # Read the entire extraction inventory, never a subset selected by an action.
    sources = {Path(ref).stem: inside(directory, ref) for ref in inventory["files"]}
    if not sources:
        raise ValueError(f"{filename}: no extracted frames found; run extract")
    images = cached[0] if cached else {key: read_image(path) for key, path in sources.items()}
    frames, scale = process_images(cfg, filename, images)
    replace_frames(inside(cfg.directory("processed_sprites"), cfg.source_id(filename)), frames, owned=r"\d+\.png", metadata={
        "stage": "process", "source": filename, "scale": scale, "files": list(frames),
        "frames": inventory.get("frames", []),
        "fingerprint": source_fingerprint(cfg, filename),
        "inputs": {key: path.relative_to(cfg.directory("source_sprites")).as_posix() for key, path in sources.items()},
    })
    return len(frames)



from .imaging.processing import alpha_bbox, offset_pair, normalize, process_frames
from .domain.models import CanvasSpec

def process_images(cfg: Config, filename: str, images: dict[str, Image.Image], *, cache=None, versions=None) -> tuple[dict[str, Image.Image], float]:
    """Compatibility adapter from project config to the pure pixel processor."""
    result = process_frames(CanvasSpec(cfg.size, cfg.anchor), filename, cfg.source_spec(filename)['process'], images, cache=cache)
    if versions is not None:
        versions.update(result.versions)
    return result.frames, result.scale
