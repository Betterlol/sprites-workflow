"""Read-only, compact playback evidence from saved processed sprites."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from sprite_pipeline.application.sequences import sequence_steps
from sprite_pipeline.domain.actions import action_steps, review_steps
from sprite_pipeline.domain.animation import playback
from sprite_pipeline.imaging.gif import encode_gif
from sprite_pipeline.storage.configuration import Config, config_from_data, inside, positive


def _contact_pages(
    folder: Path,
    steps: list[dict],
    images: dict[str, Image.Image],
    size: tuple[int, int],
    ground: int,
) -> list[str]:
    columns, per_page, cell_width, cell_height, thumb = 6, 36, 180, 210, 160
    names = []
    for offset in range(0, len(steps), per_page):
        subset = steps[offset : offset + per_page]
        rows = (len(subset) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#e9eef4")
        draw = ImageDraw.Draw(sheet)
        for index, step in enumerate(subset):
            x, y = (index % columns) * cell_width, (index // columns) * cell_height
            draw.rectangle(
                (x + 2, y + 2, x + cell_width - 3, y + cell_height - 3),
                fill="#ffffff",
                outline="#c7d1dc",
            )
            draw.text(
                (x + 9, y + 7), f"#{step['slot']:03d}  {step['duration_ms']} ms", fill="#233247"
            )
            for tile_y in range(0, thumb, 16):
                for tile_x in range(0, thumb, 16):
                    color = "#f5f7f9" if (tile_x + tile_y) // 16 % 2 else "#e8edf2"
                    draw.rectangle(
                        (x + 10 + tile_x, y + 27 + tile_y, x + 25 + tile_x, y + 42 + tile_y),
                        fill=color,
                    )
            frame = images[step["ref"]].copy()
            scale = min(thumb / frame.width, thumb / frame.height)
            frame = frame.resize(
                (max(1, round(frame.width * scale)), max(1, round(frame.height * scale))),
                Image.Resampling.LANCZOS,
            )
            px = x + 10 + (thumb - frame.width) // 2
            py = y + 27 + (thumb - frame.height) // 2
            sheet.paste(frame, (px, py), frame)
            guide_y = py + round(ground * frame.height / size[1])
            draw.line((x + 10, guide_y, x + 169, guide_y), fill="#c95959", width=1)
            label = step["ref"]
            if len(label) > 27:
                label = "…" + label[-26:]
            draw.text((x + 9, y + 190), label, fill="#425269")
        name = f"contact-{offset // per_page + 1:03d}.png"
        sheet.save(folder / name)
        names.append(name)
    return names


def render_qa(
    cfg: Config,
    *,
    action: str | None = None,
    review: str | None = None,
    references: list[str] | None = None,
    sequence: dict | None = None,
    mode: str | None = None,
    output: Path,
) -> dict:
    """Write a new evidence directory; never modify the project or existing output."""
    config_bytes = cfg.path.read_bytes()
    current = config_from_data(json.loads(config_bytes), cfg.path, cfg.root)
    if current.data != cfg.data:
        raise ValueError("Project config changed since it was loaded; retry QA")
    if sum(value is not None for value in (action, review, references, sequence)) != 1:
        raise ValueError("Choose exactly one action, Review, processed reference list, or sequence")
    if action is not None:
        mode = mode or "runtime"
        steps = action_steps(cfg, action, mode)
        spec = cfg.action(action)
        loop = (
            playback(spec, len(spec["sprites"]))[2]
            if mode == "display"
            else (0 if spec.get("loop") else 1)
        )
        source = {"action": action}
    elif review is not None:
        if mode is not None:
            raise ValueError("Review playback mode comes from the saved Review")
        saved = cfg.data.get("workbench", {}).get("reviews", {}).get(review)
        if saved is None:
            raise ValueError(f"Unknown Review: {review}")
        steps = review_steps(cfg, saved)
        mode = saved.get("mode", "runtime")
        loop = 0 if saved.get("loop", True) else 1
        source = {"review": review}
    elif sequence is not None:
        if mode is not None:
            raise ValueError("Sequence timing and loop come from the sequence JSON")
        steps, loop = sequence_steps(cfg, sequence)
        mode = "sequence"
        source = {
            "sequence_sha256": hashlib.sha256(
                json.dumps(sequence, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
        }
    else:
        if mode is not None:
            raise ValueError("Raw processed references use the project default FPS")
        if not references:
            raise ValueError("Add at least one processed reference")
        fps = positive(cfg.data.get("defaults", {}).get("fps", 12), "defaults.fps")
        duration = round(1000 / fps)
        if duration < 1:
            raise ValueError("Default FPS is too high for playback")
        steps = [{"ref": ref, "duration_ms": duration} for ref in references]
        mode, loop, source = "raw", 1, {"references": list(references)}

    target = output.resolve()
    if target.exists():
        raise FileExistsError(f"QA output already exists: {target}")
    protected = (
        cfg.source,
        cfg.directory("processed_sprites"),
        cfg.root / "references",
        cfg.root / "reference",
    )
    if any(target.is_relative_to(path.resolve()) for path in protected):
        raise ValueError("QA output must be outside source, processed, and reference directories")

    processed = cfg.directory("processed_sprites")
    images: dict[str, Image.Image] = {}
    digests: dict[str, str] = {}
    for step in steps:
        ref = step["ref"]
        if ref in images:
            continue
        path = inside(processed, ref)
        content = path.read_bytes()
        with Image.open(io.BytesIO(content)) as source_image:
            image = source_image.convert("RGBA")
        if image.size != cfg.size:
            raise ValueError(f"{ref}: sprite size does not match project canvas")
        images[ref] = image
        digests[ref] = hashlib.sha256(content).hexdigest()

    elapsed, timeline = 0, []
    for slot, step in enumerate(steps):
        duration = step["duration_ms"]
        timeline.append({**step, "slot": slot, "start_ms": elapsed})
        elapsed += duration
    report = {
        "schema": "sprite-qa-v1",
        "source": source,
        "mode": mode,
        "loop": loop,
        "frame_size": list(cfg.size),
        "steps": timeline,
        "duration_ms": elapsed,
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "sprite_sha256": digests,
        "note": "Steps and timing describe authored playback; image encoders may merge identical frames or round GIF timing.",
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".sprite-qa-", dir=target.parent) as temporary:
        staged = Path(temporary) / "result"
        staged.mkdir()
        ordered = [images[step["ref"]] for step in timeline]
        durations = [step["duration_ms"] for step in timeline]
        ordered[0].save(
            staged / "preview.webp",
            format="WEBP",
            save_all=True,
            append_images=ordered[1:],
            duration=durations,
            loop=loop,
            lossless=True,
            method=4,
        )
        (staged / "preview.gif").write_bytes(encode_gif(ordered, durations, loop))
        contacts = _contact_pages(staged, timeline, images, cfg.size, cfg.anchor["pixels"][1])
        (staged / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if os.name == "nt":
            # Windows rename is atomic and refuses an existing directory.
            staged.rename(target)
        else:
            # Reserve the name exclusively. Replacing our own empty directory
            # publishes the complete staged tree atomically on POSIX.
            target.mkdir()
            try:
                staged.replace(target)
            except BaseException:
                try:
                    target.rmdir()
                except OSError:
                    pass  # Preserve any files another process added meanwhile.
                raise
    return {
        "output": str(target),
        "steps": len(timeline),
        "duration_ms": elapsed,
        "contacts": contacts,
        "files": ["preview.webp", "preview.gif", "report.json", *contacts],
    }
