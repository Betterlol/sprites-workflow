"""Explicit batch stages, sharing pixel algorithms and native slice storage.

The batch process command requires extracted slices; interactive rendering may
also cut an unsaved draft. These entry-point policies intentionally differ.
"""

import json
import re
from pathlib import Path

from PIL import Image

from sprite_pipeline.domain.actions import action_steps
from sprite_pipeline.domain.models import CanvasSpec
from sprite_pipeline.imaging.extraction import cut_frames
from sprite_pipeline.imaging.processing import process_frames
from sprite_pipeline.storage.configuration import Config, inside, source_fingerprint
from sprite_pipeline.storage.files import read_image, replace_frames
from sprite_pipeline.storage.identities import slice_ids
from sprite_pipeline.storage.slices import read_slices, write_slices


def process_images(
    cfg: Config, filename: str, images: dict[str, Image.Image], *, cache=None, versions=None
) -> tuple[dict[str, Image.Image], float]:
    """Compatibility adapter from project config to the pure pixel processor."""
    result = process_frames(
        CanvasSpec(cfg.size, cfg.anchor),
        filename,
        cfg.source_spec(filename)["process"],
        images,
        cache=cache,
    )
    if versions is not None:
        versions.update(result.versions)
    return result.frames, result.scale


def extract_source(cfg: Config, filename: str) -> int:
    spec = cfg.source_spec(filename)["extract"]
    source_path = inside(cfg.source, filename)
    frames, boxes = cut_frames(read_image(source_path), spec)
    keys = slice_ids(cfg, filename, boxes)
    files = {f"{key}.png": frame for key, frame in zip(keys, frames)}
    write_slices(
        cfg,
        filename,
        dict(zip(keys, frames)),
        [{"file": name, "source_box": box} for name, box in zip(files, boxes)],
    )
    return len(frames)


def process_source(cfg: Config, filename: str) -> int:
    directory = inside(cfg.directory("source_sprites"), cfg.source_id(filename))
    inventory = json.loads((directory / "_stage.json").read_text(encoding="utf-8"))
    if inventory.get("stage") != "extract" or inventory.get("source") != filename:
        raise ValueError(
            f"{filename}: extraction inventory does not match the original image; run extract"
        )
    cached = read_slices(cfg, filename) if inventory.get("fingerprint") else None
    if inventory.get("fingerprint") and cached is None:
        raise ValueError(f"{filename}: extraction cache is stale or damaged; run extract")
    # Read the entire extraction inventory, never a subset selected by an action.
    sources = {Path(ref).stem: inside(directory, ref) for ref in inventory["files"]}
    if not sources:
        raise ValueError(f"{filename}: no extracted frames found; run extract")
    images = cached[0] if cached else {key: read_image(path) for key, path in sources.items()}
    frames, scale = process_images(cfg, filename, images)
    replace_frames(
        inside(cfg.directory("processed_sprites"), cfg.source_id(filename)),
        frames,
        owned=r"\d+\.png",
        metadata={
            "stage": "process",
            "source": filename,
            "scale": scale,
            "files": list(frames),
            "frames": inventory.get("frames", []),
            "fingerprint": source_fingerprint(cfg, filename),
            "inputs": {
                key: path.relative_to(cfg.directory("source_sprites")).as_posix()
                for key, path in sources.items()
            },
        },
    )
    return len(frames)


def select_action(cfg: Config, name: str) -> int:
    selection = [step["ref"] for step in action_steps(cfg, name)]
    if not selection:
        raise ValueError(
            f"{name}: configure sprites as an ordered list of processed PNG paths before selecting"
        )
    frames, provenance = {}, []
    for index, reference in enumerate(selection):
        path = inside(cfg.directory("processed_sprites"), reference)
        image = read_image(path)
        if image.size != cfg.size:
            raise ValueError(f"{reference}: expected frame size {cfg.size}, got {image.size}")
        filename = f"{name}_{index:02d}.png"
        frames[filename] = path
        provenance.append({"filename": filename, "processed_sprite": reference})
    replace_frames(
        cfg.directory("sprites") / name,
        frames,
        owned=re.escape(name) + r"_\d+\.png",
        metadata={
            "stage": "select",
            "files": list(frames),
            "frames": provenance,
        },
    )
    return len(frames)
