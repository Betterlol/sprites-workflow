"""WebP-only playback order/timing; never used to order the runtime atlas."""

from __future__ import annotations

from sprite_pipeline.domain.validation import integer, positive


def playback(spec: dict, count: int) -> tuple[list[int], list[int], int]:
    animation = spec.get("animation", {})
    order = animation.get("order", list(range(count)))
    if not isinstance(order, list) or not order:
        raise ValueError("animation.order must be a nonempty list of final sprite indices")
    for index in order:
        integer(index, "animation.order index")
        if index >= count:
            raise ValueError(f"animation.order index {index} is outside {count} final sprites")
    if "durations_ms" in animation:
        durations = animation["durations_ms"]
        if not isinstance(durations, list) or len(durations) != len(order):
            raise ValueError(
                "animation.durations_ms must have one duration per playback step (including repeated frames)"
            )
    else:
        fps = positive(animation.get("fps", spec.get("fps", 12)), "animation.fps")
        duration = animation.get("duration_ms", round(1000 / fps))
        durations = [duration] * len(order)
    for duration in durations:
        integer(duration, "animation duration_ms", 1)
        if duration > 16_777_215:
            raise ValueError("WebP frame duration exceeds the 24-bit format limit")
    loop = animation.get("loop", 0 if spec.get("loop", False) else 1)
    integer(loop, "animation.loop")
    if loop > 65_535:
        raise ValueError("animation.loop must be <= 65535 (0 means infinite)")
    return order, durations, loop
