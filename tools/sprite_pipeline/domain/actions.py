"""Runtime, display and review composition shared by all clients."""
from sprite_pipeline.domain.animation import playback
from sprite_pipeline.domain.validation import integer, NAME
from sprite_pipeline.domain.models import ActionConfig

def action_steps(cfg: ActionConfig, name: str, mode: str = "runtime") -> list[dict]:
    if name not in cfg.data["actions"]:
        raise ValueError(f"Unknown action: {name}")
    spec = cfg.action(name)
    references = spec.get("sprites") or []
    if not references:
        raise ValueError(f"{name}: add at least one sprite to the action")
    if mode == "display":
        order, durations, _ = playback(spec, len(references))
    elif mode == "runtime":
        order = list(range(len(references)))
        durations = [round(1000 / spec.get("fps", 12))] * len(order)
    else:
        raise ValueError("Playback mode must be runtime or display")
    return [{"ref": references[index], "action": name, "frame": index, "duration_ms": duration}
            for index, duration in zip(order, durations)]

def review_steps(cfg: ActionConfig, review: dict, *, allow_empty: bool = False) -> list[dict]:
    if not isinstance(review, dict) or not isinstance(review.get("clips", []), list):
        raise ValueError("A review must contain a clips array")
    if not isinstance(review.get("loop", True), bool):
        raise ValueError("review.loop must be boolean")
    mode = review.get("mode", "runtime")
    if mode not in {"runtime", "display"}:
        raise ValueError("review.mode must be runtime or display")
    result = []
    for clip_index, clip in enumerate(review.get("clips", [])):
        if not isinstance(clip, dict):
            raise ValueError("Review clips must be objects")
        repeat = integer(clip.get("repeat", 1), "clip.repeat", 1)
        if repeat > 100:
            raise ValueError("A review clip may repeat at most 100 times")
        name = clip.get("action")
        if name not in cfg.data["actions"]:
            raise ValueError(f"Review references unknown action: {name}")
        if not cfg.action(name).get("sprites") and allow_empty:
            continue
        steps = action_steps(cfg, name, mode)
        start = integer(clip.get("start", 0), "clip.start")
        end = clip.get("end")
        end = len(steps) - 1 if end is None else integer(end, "clip.end")
        if not 0 <= start <= end < len(steps):
            raise ValueError(f"{name}: clip range must be within 0..{len(steps) - 1}")
        for repetition in range(repeat):
            for position, step in enumerate(steps[start:end + 1]):
                result.append({**step, "clip": clip_index, "repetition": repetition,
                               "boundary": position == 0})
                if len(result) > 10000:
                    raise ValueError("Review exceeds 10,000 playback steps")
    if not result and not allow_empty:
        raise ValueError("Add at least one nonempty action to the review")
    return result

def validate_editor(cfg: ActionConfig) -> None:
    for name in cfg.data["actions"]:
        spec = cfg.action(name)
        if spec.get("sprites"):
            playback(spec, len(spec["sprites"]))
    editor = cfg.data.get("workbench", {})
    if not isinstance(editor, dict) or not isinstance(editor.get("reviews", {}), dict):
        raise ValueError("workbench.reviews must be an object")
    for name, review in editor.get("reviews", {}).items():
        if not NAME.fullmatch(name):
            raise ValueError(f"Invalid review ID: {name}")
        review_steps(cfg, review, allow_empty=True)
