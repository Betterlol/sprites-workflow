"""Pack final PNGs for the runtime and render independent WebP previews."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from texturepacker import TexturePackerFrame, write_texturepacker_hash

from sprite_pipeline.domain.animation import playback
from sprite_pipeline.storage.configuration import Config, inside
from sprite_pipeline.storage.files import numbered_frames, read_image, write_json
from sprite_pipeline.imaging.gif import encode_gif


def final_frames(cfg: Config, name: str) -> tuple[list[Path], list[Image.Image]]:
    paths = numbered_frames(cfg.directory("sprites") / name, name)
    images = [read_image(path) for path in paths]
    for path, image in zip(paths, images):
        if image.size != cfg.size:
            raise ValueError(f"{path}: expected {cfg.size}, got {image.size}")
    return paths, images


def preview_action(cfg: Config, name: str) -> dict:
    paths, images = final_frames(cfg, name)
    order, durations, loop = playback(cfg.action(name), len(images))
    output = cfg.directory("webp") / f"{cfg.character}_{name}.webp"
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".sprite-preview-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        images[order[0]].save(
            staged, save_all=True, append_images=[images[index] for index in order[1:]],
            duration=durations, loop=loop, lossless=True, method=6,
        )
        staged.replace(output)
    # Describes authored playback even if WebP merges consecutive identical poses.
    write_json(output.with_suffix(".animation.json"), {
        "schema": "sprite-preview-v1", "action": name, "loop": loop,
        "steps": [{"frame": paths[index].name, "duration_ms": duration} for index, duration in zip(order, durations)],
    })
    return {"preview": output.relative_to(cfg.root).as_posix(), "steps": len(order)}


def preview_gif(cfg: Config, name: str) -> dict:
    paths, images = final_frames(cfg, name)
    order, durations, loop = playback(cfg.action(name), len(images))
    output = cfg.directory("gif") / f"{cfg.character}_{name}.gif"
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".sprite-gif-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        staged.write_bytes(encode_gif([images[index] for index in order], durations, loop))
        staged.replace(output)
    write_json(output.with_suffix(".animation.json"), {
        "schema": "sprite-preview-v1", "action": name, "loop": loop,
        "steps": [{"frame": paths[index].name, "duration_ms": duration} for index, duration in zip(order, durations)],
    })
    return {"preview": output.relative_to(cfg.root).as_posix(), "steps": len(order)}


def pack_action(cfg: Config, name: str) -> dict:
    paths, images = final_frames(cfg, name)
    spec = cfg.action(name)
    width, height = cfg.size
    columns = min(spec.get("pack", {}).get("columns", 4), len(images))
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * width, rows * height), (0, 0, 0, 0))
    atlas_frames, tp_frames = {}, []
    duration = round(1000 / spec.get("fps", 12))
    for index, (path, image) in enumerate(zip(paths, images)):
        x, y = index % columns * width, index // columns * height
        sheet.alpha_composite(image, (x, y))
        atlas_frames[path.name] = {"frame": {"x": x, "y": y, "w": width, "h": height}, "anchor": cfg.anchor}
        tp_frames.append(TexturePackerFrame(path.name, x, y, width, height, duration))
    output = cfg.directory("spritesheets") / f"{cfg.character}_{name}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".sprite-atlas-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        sheet.save(staged, optimize=True)
        write_texturepacker_hash(staged.with_suffix(".json"), image_name=output.name,
                                 sheet_width=sheet.width, sheet_height=sheet.height, frames=tp_frames)
        staged.replace(output)
        staged.with_suffix(".json").replace(output.with_suffix(".json"))
    metadata = {
        "schema": cfg.data.get("metadata_schema", "sprite-pipeline-v1"), "action": name,
        "source": cfg.data.get("source_description", "assembled from configured processed sprites"),
        "sheet": output.name, "frame_size": {"w": width, "h": height},
        "anchor": cfg.anchor, "fps": spec.get("fps", 12), "loop": spec.get("loop", False),
        "frames": [{"filename": path.relative_to(cfg.root).as_posix(), "duration_ms": duration} for path in paths],
        "atlas_frames": atlas_frames,
    }
    write_json(cfg.directory("metadata") / f"{cfg.character}_{name}.json", metadata)
    return {"name": name, "count": len(images), "fps": metadata["fps"], "loop": metadata["loop"],
            "sheet": output.relative_to(cfg.root).as_posix(),
            "preview": (cfg.directory("webp") / f"{cfg.character}_{name}.webp").relative_to(cfg.root).as_posix()}


def update_manifest(cfg: Config, actions: list[dict]) -> None:
    output = inside(cfg.root, cfg.data["paths"].get("manifest", f"{cfg.character}_manifest.json"))
    manifest = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    existing = {entry["name"]: entry for entry in manifest.get("actions", [])}
    for entry in actions:
        entry = dict(entry)
        for field in ("sheet", "preview"):
            entry[field] = Path(os.path.relpath(cfg.root / entry[field], output.parent)).as_posix()
        existing[entry["name"]] = entry
    manifest.update({
        "character": cfg.character, "version": cfg.data.get("manifest_version", 1),
        "frame_size": {"w": cfg.size[0], "h": cfg.size[1]}, "anchor": cfg.anchor,
        "facing": cfg.data.get("facing", "right"),
        "actions": [existing[name] for name in cfg.data["actions"] if name in existing],
        "notes": cfg.data.get("notes", [
            "Runtime playback follows numbered final PNGs; preview playback is configured independently.",
            "Run extract/process for review, select to promote, pack to export, or preview for WebP only.",
        ]),
    })
    write_json(output, manifest)
