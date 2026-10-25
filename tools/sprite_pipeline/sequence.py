"""Small, explicit playback sequence format for read-only agent tools."""

from __future__ import annotations

from .config import Config, inside, integer


def sequence_steps(cfg: Config, sequence: dict) -> tuple[list[dict], int]:
    """Validate ordered processed references, millisecond timing and WebP loop count."""
    if not isinstance(sequence, dict) or set(sequence) - {"steps", "loop"}:
        raise ValueError("Sequence must contain only steps and optional loop")
    items = sequence.get("steps")
    if not isinstance(items, list) or not 1 <= len(items) <= 10_000:
        raise ValueError("Sequence needs 1–10000 steps")
    loop = integer(sequence.get("loop", 1), "sequence.loop")
    if loop > 65_535:
        raise ValueError("sequence.loop must be <= 65535")
    steps = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != {"ref", "duration_ms"}:
            raise ValueError(f"Sequence step {index} needs ref and duration_ms")
        ref = item["ref"]
        if inside(cfg.directory("processed_sprites"), ref).suffix.lower() != ".png":
            raise ValueError(f"Sequence step {index} must reference a processed PNG")
        duration = integer(item["duration_ms"], f"sequence.steps[{index}].duration_ms", 1)
        if duration > 655_350:
            raise ValueError("Sequence duration exceeds GIF's per-frame limit")
        steps.append({"ref": ref, "duration_ms": duration})
    return steps, loop
