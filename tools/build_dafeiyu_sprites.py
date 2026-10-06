"""Normalize generated Dafeiyu animation sheets into engine-ready PNG sprites.

The source sheets use action-specific grids, so this script deliberately does
not use the Hollow Knight template JSON.  It finds each frame's alpha bounds,
keeps a stable per-action scale, and places it on a 640px canvas with a shared
bottom anchor (x=320, y=570).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "assets" / "sprites" / "dafeiyu_sources"
OUT = ROOT / "assets" / "sprites" / "dafeiyu"
# 640 keeps the widest dash tail and special-cast effect at native detail.  A
# 512 canvas was the remaining source of edge clipping after extraction.
FRAME = 640
GROUND_Y = 570
ANCHOR = {"x": 0.5, "y": 0.89, "pixels": [320, GROUND_Y]}

# Paths are the selected transparent-alpha generations.  Frames are read in
# visual order: left-to-right, then top-to-bottom.
ACTIONS = {
    "idle": {"file": "idle.png", "cols": 4, "rows": 2, "fps": 8, "loop": True},
    "run": {"file": "run.png", "cols": 4, "rows": 2, "fps": 12, "loop": True},
    "jump": {"file": "jump.png", "cols": 3, "rows": 2, "fps": 12, "loop": False},
    "land": {"file": "land.png", "cols": 3, "rows": 2, "fps": 14, "loop": False},
    "dash": {"file": "dash.png", "cols": 3, "rows": 2, "fps": 16, "loop": False},
    "attack": {"file": "attack.png", "cols": 3, "rows": 2, "fps": 14, "loop": False},
    "hurt": {"file": "hurt.png", "cols": 5, "rows": 1, "fps": 12, "loop": False},
    "die": {"file": "die.png", "cols": 6, "rows": 1, "fps": 10, "loop": False},
    # The existing die_05 output is retained byte-for-byte as this action's
    # opening frame, followed by five generated dissolve/true-form frames.
    "die_reveal": {"file": "die_reveal.png", "cols": 5, "rows": 1, "fps": 10, "loop": False, "prepend": "die_05_start.png"},
    "attack_special": {"file": "attack_special.png", "cols": 4, "rows": 2, "fps": 12, "loop": False},
}


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def _distance_to_box(box: tuple[int, int, int, int], other: tuple[int, int, int, int]) -> float:
    """Euclidean gap between two axis-aligned boxes (zero when touching)."""
    dx = max(box[0] - other[2], other[0] - box[2], 0)
    dy = max(box[1] - other[3], other[1] - box[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def _split_merged_die_component(components: list[dict], expected: int) -> list[dict]:
    """Split the one touching pair in the generated death strip.

    The two prone poses touch by a few anti-aliased pixels in the source.  The
    split follows the lowest-alpha vertical valley and overlaps 12 px so neither
    pose loses the hair/tail pixels which caused the reported cut-off.
    """
    if len(components) != expected - 1:
        return components
    widest_index = max(range(len(components)), key=lambda index: components[index]["bbox"][2] - components[index]["bbox"][0])
    widest = components[widest_index]
    x0, _, x1, _ = widest["bbox"]
    mask = widest["mask"]
    counts = mask.sum(axis=0)
    lo = x0 + (x1 - x0) // 4
    hi = x1 - (x1 - x0) // 4
    seam = int(lo + np.argmin(counts[lo:hi]))
    x_coords = np.arange(mask.shape[1])[None, :]
    left = mask & (x_coords <= seam + 12)
    right = mask & (x_coords >= seam - 12)
    components.pop(widest_index)
    components.extend(
        [
            {"mask": left, "bbox": _bbox(left), "size": int(left.sum())},
            {"mask": right, "bbox": _bbox(right), "size": int(right.sum())},
        ]
    )
    return components


def extract_character_frames(name: str, source: Image.Image, cols: int, rows: int) -> list[Image.Image]:
    """Extract figures globally instead of cutting at generated-grid boundaries.

    AI sprite sheets often place a tail, hand, or effect a few pixels outside
    its nominal cell.  Connected-component extraction preserves that material
    and only uses the visual row/column order to sequence frames.
    """
    alpha = np.asarray(source.getchannel("A"))
    opaque = alpha >= 16
    labels, count = ndimage.label(opaque, structure=np.ones((3, 3), dtype=np.uint8))
    components = []
    for label in range(1, count + 1):
        mask = labels == label
        size = int(mask.sum())
        if size >= 80:  # discard invisible one-pixel preview noise
            components.append({"mask": mask, "bbox": _bbox(mask), "size": size})

    major_threshold = max(10_000, int(opaque.sum() * 0.02))
    major = [item for item in components if item["size"] >= major_threshold]
    minor = [item for item in components if item["size"] < major_threshold]
    expected = cols * rows
    if name == "die":
        major = _split_merged_die_component(major, expected)
    if len(major) != expected:
        raise ValueError(f"{name}: expected {expected} character silhouettes, found {len(major)}")

    # The generated rows are visually distinct.  Sort row-wise rather than by
    # the arbitrary nominal grid, which is exactly what caused spill clipping.
    major.sort(key=lambda item: (item["bbox"][1] + item["bbox"][3]) / 2)
    ordered: list[dict] = []
    for row in range(rows):
        row_items = major[row * cols : (row + 1) * cols]
        ordered.extend(sorted(row_items, key=lambda item: (item["bbox"][0] + item["bbox"][2]) / 2))

    if name == "die":
        # The regenerated source has six clean silhouettes, but its visual grid
        # is not the intended motion order.  This maps them to the authored
        # sequence: stand -> stagger -> knees buckle -> fall -> prone -> still.
        ordered = [ordered[index] for index in (0, 2, 5, 1, 3, 4)]

    # Detached special-attack droplets are assigned to the nearest character
    # silhouette.  Normal actions have only negligible preview noise here.
    groups: list[list[dict]] = [[item] for item in ordered]
    for item in minor:
        target = min(range(len(ordered)), key=lambda index: _distance_to_box(item["bbox"], ordered[index]["bbox"]))
        groups[target].append(item)

    result = []
    for group in groups:
        combined = np.logical_or.reduce([item["mask"] for item in group])
        box = _bbox(combined)
        x0, y0, x1, y1 = box
        pixels = np.asarray(source.crop(box)).copy()
        selected_alpha = alpha[y0:y1, x0:x1].copy()
        selected_alpha[~combined[y0:y1, x0:x1]] = 0
        pixels[:, :, 3] = selected_alpha
        result.append(Image.fromarray(pixels, "RGBA"))
    return result


def alpha_bbox(image: Image.Image):
    # Alpha under 16 is invisible noise left by generative previews.
    alpha = image.getchannel("A").point(lambda v: 255 if v >= 16 else 0)
    return alpha.getbbox()


def build_action(name: str, spec: dict) -> dict:
    src = Image.open(GENERATED / spec["file"]).convert("RGBA")
    raw_frames = extract_character_frames(name, src, spec["cols"], spec["rows"])
    boxes = [alpha_bbox(frame) for frame in raw_frames]
    if any(box is None for box in boxes):
        raise ValueError(f"{name}: an empty frame was found")

    # Fix the action scale once, using its tallest standing / action frame.
    # This prevents the common AI-sheet issue of per-frame scale pulsing.
    source_height = max(box[3] - box[1] for box in boxes if box)
    scale = min(1.0, 432 / source_height) if source_height else 1.0
    
    if name == "attack_special":
        scale = 1.05

    frame_dir = OUT / "frames" / name
    frame_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[Image.Image] = []
    frame_entries = []
    if "prepend" in spec:
        start = Image.open(GENERATED / spec["prepend"]).convert("RGBA")
        if start.size != (FRAME, FRAME):
            raise ValueError(f"{name}: prepended frame must be {FRAME}x{FRAME}, got {start.size}")
        filename = f"{name}_00.png"
        start.save(frame_dir / filename, optimize=True)
        normalized.append(start)
        frame_entries.append({"filename": f"frames/{name}/{filename}", "duration_ms": round(1000 / spec["fps"])})

    for index, (raw, box) in enumerate(zip(raw_frames, boxes), start=len(normalized)):
        cropped = raw.crop(box)
        new_size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
        cropped = cropped.resize(new_size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        # Center horizontally; all non-prone actions share a fixed ground anchor.
        x = (FRAME - cropped.width) // 2
        if (name == "die" and index >= 3) or name == "die_reveal":
            y = GROUND_Y - cropped.height + 24
        elif name in {"jump", "land"} and index == 0:
            y = GROUND_Y - cropped.height - 50
        else:
            y = GROUND_Y - cropped.height
        y = max(8, min(FRAME - cropped.height - 8, y))
        canvas.alpha_composite(cropped, (x, y))
        filename = f"{name}_{index:02d}.png"
        canvas.save(frame_dir / filename, optimize=True)
        normalized.append(canvas)
        frame_entries.append({"filename": f"frames/{name}/{filename}", "duration_ms": round(1000 / spec["fps"])})

    # A 4-column atlas keeps every single action sheet compact and consistent.
    sheet_cols = min(4, len(normalized))
    sheet_rows = (len(normalized) + sheet_cols - 1) // sheet_cols
    sheet = Image.new("RGBA", (sheet_cols * FRAME, sheet_rows * FRAME), (0, 0, 0, 0))
    atlas_frames = {}
    for index, frame in enumerate(normalized):
        x, y = (index % sheet_cols) * FRAME, (index // sheet_cols) * FRAME
        sheet.alpha_composite(frame, (x, y))
        atlas_frames[f"{name}_{index:02d}.png"] = {"frame": {"x": x, "y": y, "w": FRAME, "h": FRAME}, "anchor": ANCHOR}
    sheet_path = OUT / "sheets" / f"dafeiyu_{name}.png"
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sheet_path, optimize=True)

    # Preview only: a transparent animated WebP confirms the exact frame order
    # without making a game runtime depend on an animated format.
    preview_path = OUT / "previews" / f"dafeiyu_{name}.webp"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    normalized[0].save(
        preview_path,
        save_all=True,
        append_images=normalized[1:],
        duration=round(1000 / spec["fps"]),
        loop=0 if spec["loop"] else 1,
        lossless=True,
        method=6,
    )

    metadata = {
        "schema": "dafeiyu-sprites-v2",
        "action": name,
        "source": "AI-generated from assets/refer/dafeiyu-game-identity.png; extracted by alpha-connected silhouette rather than Hollow Knight template JSON",
        "sheet": sheet_path.name,
        "frame_size": {"w": FRAME, "h": FRAME},
        "anchor": ANCHOR,
        "fps": spec["fps"],
        "loop": spec["loop"],
        "frames": frame_entries,
        "atlas_frames": atlas_frames,
    }
    (OUT / "metadata" / f"dafeiyu_{name}.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "metadata" / f"dafeiyu_{name}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "name": name,
        "count": len(normalized),
        "fps": spec["fps"],
        "loop": spec["loop"],
        "sheet": f"sheets/{sheet_path.name}",
        "preview": f"previews/{preview_path.name}",
    }


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    actions = [build_action(name, spec) for name, spec in ACTIONS.items()]
    manifest = {
        "character": "dafeiyu",
        "version": 2,
        "frame_size": {"w": FRAME, "h": FRAME},
        "anchor": ANCHOR,
        "facing": "right",
        "actions": actions,
        "notes": [
            "All output PNGs use transparent alpha.",
            "Playback order follows zero-padded filenames.",
            "Frames are reconstructed from alpha-connected character silhouettes, so generated sheet overflow is retained instead of cropped at nominal grid lines.",
            "Use the same anchor for each frame; do not use Template/*.json for this character.",
        ],
    }
    (OUT / "dafeiyu_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {sum(x['count'] for x in actions)} frames to {OUT}")


if __name__ == "__main__":
    main()
