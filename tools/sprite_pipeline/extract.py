"""Cut source images at native resolution, without motion order or transforms."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from .config import Config, inside, integer
from .files import read_image, replace_frames


def preserve_slice_ids(boxes: list[tuple], previous: list[dict]) -> list[str]:
    """Match old region identities before assigning fresh IDs to new regions."""
    old = {Path(item["file"]).stem: tuple(item["source_box"]) for item in previous
           if isinstance(item, dict) and "file" in item and "source_box" in item}
    used = set()
    result = [None] * len(boxes)
    next_id = max([int(key) for key in old if key.isdigit()] + [-1]) + 1
    for i, box in enumerate(boxes):
        matches = [key for key, previous_box in old.items() if previous_box == tuple(box) and key not in used]
        if len(matches) == 1:
            result[i] = matches[0]
            used.add(matches[0])
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        if result[i] is not None:
            continue
        candidates = []
        for key, (a0, b0, a1, b1) in old.items():
            if key in used:
                continue
            intersection = max(0, min(x1, a1) - max(x0, a0)) * max(0, min(y1, b1) - max(y0, b0))
            union = (x1 - x0) * (y1 - y0) + (a1 - a0) * (b1 - b0) - intersection
            if union and intersection / union > .5:
                candidates.append(key)
        if len(candidates) == 1:
            key = candidates[0]
        else:
            key = f"{next_id:03d}"
            next_id += 1
        result[i] = key
        used.add(key)
    return result


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


def bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if not len(xs):
        raise ValueError("Cannot extract an empty alpha component")
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def distance(box, other) -> float:
    dx = max(box[0] - other[2], other[0] - box[2], 0)
    dy = max(box[1] - other[3], other[1] - box[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def component_frames(source: Image.Image, spec: dict) -> tuple[list[Image.Image], list[tuple]]:
    if ("cols" in spec) != ("rows" in spec):
        raise ValueError("Provide both extract.cols and extract.rows, or omit both for automatic component layout")
    cols = integer(spec["cols"], "extract.cols", 1) if "cols" in spec else None
    rows = integer(spec["rows"], "extract.rows", 1) if "rows" in spec else None
    threshold = integer(spec.get("alpha_threshold", 16), "extract.alpha_threshold", 1)
    if threshold > 255:
        raise ValueError("extract.alpha_threshold must be <= 255")
    min_pixels = integer(spec.get("min_component_pixels", 80), "extract.min_component_pixels", 1)
    major_pixels = integer(spec.get("major_min_pixels", 10_000), "extract.major_min_pixels", 1)
    fraction = spec.get("major_fraction", 0.02)
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0 <= fraction <= 1:
        raise ValueError("extract.major_fraction must be between 0 and 1")
    alpha = np.asarray(source.getchannel("A"))
    opaque = alpha >= threshold
    labels, _ = ndimage.label(opaque, structure=np.ones((3, 3), dtype=np.uint8))
    counts = np.bincount(labels.ravel())
    components = []
    for label in np.flatnonzero(counts[1:] >= min_pixels) + 1:
        mask = labels == label
        components.append({"mask": mask, "bbox": bbox(mask), "size": int(counts[label])})
    major_threshold = max(major_pixels, int(opaque.sum() * fraction))
    major = [item for item in components if item["size"] >= major_threshold]
    minor = [item for item in components if item["size"] < major_threshold]
    expected = cols * rows if cols is not None else None
    split = spec.get("split_widest")
    if split is not None and expected is None:
        raise ValueError("split_widest requires explicit cols and rows")
    if split is not None and len(major) == expected - 1 and major:
        overlap = integer(split.get("overlap", 0), "extract.split_widest.overlap")
        widest_index = max(range(len(major)), key=lambda i: major[i]["bbox"][2] - major[i]["bbox"][0])
        widest = major.pop(widest_index)
        x0, _, x1, _ = widest["bbox"]
        mask = widest["mask"]
        lo, hi = x0 + (x1 - x0) // 4, x1 - (x1 - x0) // 4
        seam = int(lo + np.argmin(mask.sum(axis=0)[lo:hi]))
        xs = np.arange(mask.shape[1])[None, :]
        for part in (mask & (xs <= seam + overlap), mask & (xs >= seam - overlap)):
            major.append({"mask": part, "bbox": bbox(part), "size": int(part.sum())})
    if not major:
        raise ValueError("No character silhouettes found; adjust extraction thresholds or use grid/boxes/image")
    if expected is not None and len(major) != expected:
        raise ValueError(f"Expected {expected} character silhouettes, found {len(major)}; adjust extraction config or use explicit boxes")
    major.sort(key=lambda item: (item["bbox"][1] + item["bbox"][3]) / 2)
    ordered = []
    if rows is not None:
        for row in range(rows):
            ordered.extend(sorted(major[row * cols:(row + 1) * cols], key=lambda item: (item["bbox"][0] + item["bbox"][2]) / 2))
    else:
        # Without an authored layout, group figures whose vertical bounds overlap
        # by at least half the smaller figure, then order each row horizontally.
        visual_rows = []
        for item in major:
            y0, y1 = item["bbox"][1], item["bbox"][3]
            for row in visual_rows:
                ry0, ry1 = row[0]["bbox"][1], row[0]["bbox"][3]
                if min(y1, ry1) - max(y0, ry0) >= min(y1 - y0, ry1 - ry0) * 0.5:
                    row.append(item)
                    break
            else:
                visual_rows.append([item])
        for row in visual_rows:
            ordered.extend(sorted(row, key=lambda item: item["bbox"][0]))
    groups = [[item] for item in ordered]
    for item in minor:
        target = min(range(len(ordered)), key=lambda i: distance(item["bbox"], ordered[i]["bbox"]))
        groups[target].append(item)
    frames, boxes = [], []
    for group in groups:
        mask = np.logical_or.reduce([item["mask"] for item in group])
        box = bbox(mask)
        x0, y0, x1, y1 = box
        pixels = np.asarray(source.crop(box)).copy()
        pixels[:, :, 3] = np.where(mask[y0:y1, x0:x1], alpha[y0:y1, x0:x1], 0)
        frames.append(Image.fromarray(pixels))
        boxes.append(box)
    return frames, boxes


def cut_frames(source: Image.Image, spec: dict) -> tuple[list[Image.Image], list[tuple]]:
    method = spec.get("method", "components")
    if method == "components":
        return component_frames(source, spec)
    if method == "image":
        boxes = [(0, 0, source.width, source.height)]
    elif method == "grid":
        cols = integer(spec["cols"], "extract.cols", 1)
        rows = integer(spec["rows"], "extract.rows", 1)
        if cols > source.width or rows > source.height:
            raise ValueError("Grid cells must have positive dimensions")
        xs = [round(source.width * i / cols) for i in range(cols + 1)]
        ys = [round(source.height * i / rows) for i in range(rows + 1)]
        boxes = [(xs[x], ys[y], xs[x + 1], ys[y + 1]) for y in range(rows) for x in range(cols)]
    elif method == "boxes":
        boxes = spec.get("boxes", [])
        if not boxes:
            raise ValueError("extract.boxes must be nonempty")
        for box in boxes:
            if len(box) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in box):
                raise ValueError("Each extraction box must be [left, top, right, bottom] integers")
            x0, y0, x1, y1 = box
            if not (0 <= x0 < x1 <= source.width and 0 <= y0 < y1 <= source.height):
                raise ValueError(f"Extraction box outside source image: {box}")
    else:
        raise ValueError(f"Unknown extraction method: {method}")
    return [source.crop(box) for box in boxes], boxes


def extract_source(cfg: Config, filename: str) -> int:
    spec = cfg.source_spec(filename)["extract"]
    source_path = inside(cfg.source, filename)
    frames, boxes = cut_frames(read_image(source_path), spec)
    keys = preserve_slice_ids(boxes, previous_slices(cfg, filename))
    files = {f"{key}.png": frame for key, frame in zip(keys, frames)}
    replace_frames(inside(cfg.directory("source_sprites"), cfg.source_id(filename)), files, owned=r"\d+\.png", metadata={
        "stage": "extract", "source": filename, "files": list(files),
        "frames": [{"file": filename, "source_box": box} for filename, box in zip(files, boxes)],
    })
    return len(frames)
