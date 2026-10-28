"""Stage-local IO. No stage removes a character's entire output directory."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


def read_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # A failed serialization must not truncate an existing file.
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with TemporaryDirectory(prefix=".sprite-json-", dir=path.parent) as temporary:
        staged = Path(temporary) / path.name
        staged.write_text(serialized, encoding="utf-8")
        staged.replace(path)


def frame_changes(
    directory: Path, frames: dict[str, Image.Image], owned: str
) -> tuple[set[str], list[Path]]:
    changed = set()
    for name, image in frames.items():
        try:
            previous = read_image(directory / name)
            if previous.size != image.size or previous.tobytes() != image.tobytes():
                changed.add(name)
        except (OSError, ValueError):
            changed.add(name)
    stage = directory / "_stage.json"
    old_names = (
        json.loads(stage.read_text(encoding="utf-8")).get("files", []) if stage.exists() else []
    )
    removed = [
        path
        for path in directory.glob("*.png")
        if path.name not in frames and (re.fullmatch(owned, path.name) or path.name in old_names)
    ]
    return changed, removed


def replace_frames(
    directory: Path,
    frames: dict[str, Image.Image | Path],
    *,
    owned: str,
    metadata: dict,
    write_names: set[str] | None = None,
) -> None:
    """Render/validate everything before replacing owned PNGs for one item.

    Extra review notes and images with unrelated names are left alone. This is
    stage-local replacement, not a transaction across all sources/actions.
    """
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".sprite-frames-", dir=directory.parent) as temporary:
        staged = Path(temporary)
        for name, frame in frames.items():
            if write_names is not None and name not in write_names:
                continue
            if isinstance(frame, Path):
                shutil.copyfile(frame, staged / name)
            else:
                frame.save(staged / name, optimize=True)
        (staged / "_stage.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        previous = directory / "_stage.json"
        old_names = (
            json.loads(previous.read_text(encoding="utf-8")).get("files", [])
            if previous.exists()
            else []
        )
        for old in directory.glob("*.png"):
            if old.name not in frames and (re.fullmatch(owned, old.name) or old.name in old_names):
                old.unlink()
        for path in staged.iterdir():
            path.replace(directory / path.name)


def numbered_frames(directory: Path, action: str) -> list[Path]:
    pattern = re.compile(re.escape(action) + r"_(\d+)\.png\Z")
    matches = [
        (int(match[1]), path)
        for path in directory.glob("*.png")
        if (match := pattern.fullmatch(path.name))
    ]
    matches.sort(key=lambda entry: entry[0])
    if not matches:
        raise FileNotFoundError(
            f"No final sprites in {directory}; run select or add numbered PNGs first"
        )
    if [index for index, _ in matches] != list(range(len(matches))):
        raise ValueError(
            f"{directory}: frame numbers must be contiguous from 0; run select to renumber"
        )
    return [path for _, path in matches]
