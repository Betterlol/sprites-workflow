"""Compare exact runtime slot composition without changing authored actions."""

from __future__ import annotations

import hashlib
import json

from sprite_pipeline.application.sequences import sequence_steps
from sprite_pipeline.domain.actions import action_steps, review_steps
from sprite_pipeline.storage.configuration import Config, inside


def compare_composition(
    cfg: Config, action: str, *, review: str | None = None, sequence: dict | None = None
) -> dict:
    """Return the first ref/timing mismatch and descriptive join boundaries."""
    if (review is None) == (sequence is None):
        raise ValueError("Choose exactly one Review or explicit sequence")
    full = action_steps(cfg, action, "runtime")
    if review is not None:
        saved = cfg.data.get("workbench", {}).get("reviews", {}).get(review)
        if saved is None:
            raise ValueError(f"Unknown Review: {review}")
        if saved.get("mode", "runtime") != "runtime":
            raise ValueError("Composition checks need a runtime Review")
        parts = review_steps(cfg, saved)
        source = {"review": review}
    else:
        parts, _ = sequence_steps(cfg, sequence)
        source = {
            "sequence_sha256": hashlib.sha256(
                json.dumps(sequence, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
        }

    processed = cfg.directory("processed_sprites")
    for ref in {step["ref"] for step in [*full, *parts]}:
        path = inside(processed, ref)
        if not path.is_file():
            raise FileNotFoundError(f"Processed sprite is missing: {ref}")

    def comparable(step: dict | None) -> dict | None:
        return None if step is None else {key: step[key] for key in ("ref", "duration_ms")}

    mismatch = None
    for slot in range(max(len(full), len(parts))):
        expected = comparable(full[slot]) if slot < len(full) else None
        actual = comparable(parts[slot]) if slot < len(parts) else None
        if expected != actual:
            mismatch = {"slot": slot, "full": expected, "composition": actual}
            break
    boundaries = [
        {
            "slot": slot,
            "clip": step["clip"],
            "previous_ref": parts[slot - 1]["ref"],
            "next_ref": step["ref"],
            "same_ref": parts[slot - 1]["ref"] == step["ref"],
        }
        for slot, step in enumerate(parts)
        if slot and step.get("boundary")
    ]
    return {
        "valid": mismatch is None,
        "action": action,
        "source": source,
        "full_steps": len(full),
        "composition_steps": len(parts),
        "full_duration_ms": sum(step["duration_ms"] for step in full),
        "composition_duration_ms": sum(step["duration_ms"] for step in parts),
        "first_mismatch": mismatch,
        "boundaries": boundaries,
        "note": "Repeated boundary references are reported, never removed automatically.",
    }
