"""Normalize generated Dafeiyu animation sheets into engine-ready PNG sprites.

The source sheets use action-specific grids, so this script deliberately does
not use the Hollow Knight template JSON.  It finds each frame's alpha bounds,
keeps a stable per-action scale, and places it on a 512px canvas with a shared
bottom anchor (x=256, y=456).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "assets" / "sprites" / "dafeiyu_sources"
OUT = ROOT / "assets" / "sprites" / "dafeiyu"
FRAME = 512
ANCHOR = {"x": 0.5, "y": 0.89, "pixels": [256, 456]}

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
    "attack_special": {"file": "attack_special.png", "cols": 4, "rows": 2, "fps": 12, "loop": False},
}


def crop_grid(source: Image.Image, cols: int, rows: int) -> list[Image.Image]:
    """Split a sheet using proportional boundaries, including odd dimensions."""
    w, h = source.size
    xs = [round(i * w / cols) for i in range(cols + 1)]
    ys = [round(i * h / rows) for i in range(rows + 1)]
    return [source.crop((xs[x], ys[y], xs[x + 1], ys[y + 1])) for y in range(rows) for x in range(cols)]


def alpha_bbox(image: Image.Image):
    # Alpha under 16 is invisible noise left by generative previews.
    alpha = image.getchannel("A").point(lambda v: 255 if v >= 16 else 0)
    return alpha.getbbox()


def build_action(name: str, spec: dict) -> dict:
    src = Image.open(GENERATED / spec["file"]).convert("RGBA")
    raw_frames = crop_grid(src, spec["cols"], spec["rows"])
    boxes = [alpha_bbox(frame) for frame in raw_frames]
    if any(box is None for box in boxes):
        raise ValueError(f"{name}: an empty frame was found")

    # Fix the action scale once, using its tallest standing / action frame.
    # This prevents the common AI-sheet issue of per-frame scale pulsing.
    source_height = max(box[3] - box[1] for box in boxes if box)
    scale = min(1.0, 432 / source_height) if source_height else 1.0
    if name == "attack_special":
        # Effects are allowed to extend upward, while preserving readable body size.
        scale = min(scale, 0.92)

    frame_dir = OUT / "frames" / name
    frame_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[Image.Image] = []
    frame_entries = []
    for index, (raw, box) in enumerate(zip(raw_frames, boxes)):
        cropped = raw.crop(box)
        new_size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
        cropped = cropped.resize(new_size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        # Center horizontally; all non-prone actions share a fixed ground anchor.
        x = (FRAME - cropped.width) // 2
        if name == "die" and index >= 3:
            y = 456 - cropped.height + 24
        elif name in {"jump", "land"} and index == 0:
            y = 456 - cropped.height - 50
        else:
            y = 456 - cropped.height
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
        "schema": "dafeiyu-sprites-v1",
        "action": name,
        "source": "AI-generated from asserts/refer/dafeiyu-game-identity.png; not aligned to Hollow Knight template JSON",
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
        "version": 1,
        "frame_size": {"w": FRAME, "h": FRAME},
        "anchor": ANCHOR,
        "facing": "right",
        "actions": actions,
        "notes": [
            "All output PNGs use transparent alpha.",
            "Playback order follows zero-padded filenames.",
            "Use the same anchor for each frame; do not use Template/*.json for this character.",
        ],
    }
    (OUT / "dafeiyu_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {sum(x['count'] for x in actions)} frames to {OUT}")


if __name__ == "__main__":
    main()
