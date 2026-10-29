"""Finite, reference-based composition shared by actions, reviews and exporters."""

from copy import deepcopy
from pathlib import PurePosixPath

from sprite_pipeline.domain.animation import playback
from sprite_pipeline.domain.validation import NAME, integer, merge, positive

KINDS = {"sprite", "action", "sequence"}
MAX_STEPS = 10000
MAX_DEPTH = 32


def resource_spec(data: dict, kind: str, reference: str) -> dict:
    collection = (
        data.get("actions", {})
        if kind == "action"
        else data.get("workbench", {}).get("reviews", {})
    )
    if kind not in {"action", "sequence"} or reference not in collection:
        raise ValueError(f"Unknown {kind} resource: {reference}")
    value = collection[reference]
    return merge(data.get("defaults", {}), value) if kind == "action" else value


def resource_slots(spec: dict, kind: str) -> list[dict]:
    """Read legacy resources without changing the authored representation."""
    if "slots" in spec:
        if not isinstance(spec["slots"], list):
            raise ValueError("Resource slots must be an array")
        return spec["slots"]
    if kind == "action":
        return [
            {"id": f"frame-{i}", "resource": {"kind": "sprite", "ref": ref}}
            for i, ref in enumerate(spec.get("sprites") or [])
        ]
    if not isinstance(spec.get("clips", []), list):
        raise ValueError("Sequence clips must be an array")
    return [
        {**clip, "id": f"clip-{i}", "resource": {"kind": "action", "ref": clip.get("action")}}
        for i, clip in enumerate(spec.get("clips", []))
    ]


def validate_target(target: dict) -> None:
    if not isinstance(target, dict) or target.get("kind") not in KINDS:
        raise ValueError("Slot resource needs kind: sprite, action or sequence")
    ref = target.get("ref")
    if not isinstance(ref, str) or not ref:
        raise ValueError("Slot resource needs a nonempty reference")
    if target["kind"] == "sprite":
        path = PurePosixPath(ref)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in ref
            or ":" in ref
            or path.suffix.lower() != ".png"
        ):
            raise ValueError(f"Expected a relative processed PNG reference: {ref}")
    elif not NAME.fullmatch(ref):
        raise ValueError(f"Invalid resource ID: {ref}")


class ResourceResolver:
    def __init__(self, data: dict, *, allow_empty: bool = False):
        self.data = data
        self.allow_empty = allow_empty

    def resolve(self, kind: str, reference: str, mode: str = "runtime") -> list[dict]:
        return self.expand(kind, reference, resource_spec(self.data, kind, reference), mode, ())

    def expand(self, kind: str, reference: str, spec: dict, mode: str, stack: tuple) -> list[dict]:
        if mode not in {"runtime", "display"}:
            raise ValueError("Playback mode must be runtime or display")
        key = f"{kind}:{reference}"
        if key in stack:
            raise ValueError("Circular resource reference: " + " → ".join((*stack, key)))
        if len(stack) >= MAX_DEPTH:
            raise ValueError(f"Resource nesting exceeds {MAX_DEPTH} levels")
        stack = (*stack, key)
        slots = resource_slots(spec, kind)
        if len(slots) > MAX_STEPS:
            raise ValueError("Resource exceeds 10,000 slots")
        fps = positive(
            spec.get("fps", self.data.get("defaults", {}).get("fps", 12)), "resource.fps"
        )
        duration = max(1, round(1000 / fps))
        result, ids = [], set()
        for index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                raise ValueError("Each resource slot must be an object")
            slot_id = slot.get("id", f"slot-{index}")
            if not isinstance(slot_id, str) or not slot_id or slot_id in ids:
                raise ValueError("Resource slot IDs must be nonempty and unique")
            ids.add(slot_id)
            target = slot.get("resource")
            validate_target(target)
            repeat = integer(slot.get("repeat", 1), "slot.repeat", 1)
            if repeat > 100:
                raise ValueError("A slot may repeat at most 100 times")
            speed = positive(slot.get("speed", 1), "slot.speed")
            if not 0.01 <= speed <= 100:
                raise ValueError("slot.speed must be between 0.01 and 100")
            child_mode = slot.get("mode", mode if kind == "sequence" else "runtime")
            if child_mode not in {"runtime", "display"}:
                raise ValueError("Slot playback mode must be runtime or display")
            if target["kind"] == "sprite":
                hold = integer(slot.get("duration_ms", duration), "slot.duration_ms", 1)
                if hold > 16777215:
                    raise ValueError("Sprite duration exceeds the WebP format limit")
                children = [
                    {"ref": target["ref"], "duration_ms": hold, "origin": [], "lineage": []}
                ]
            else:
                if "duration_ms" in slot:
                    raise ValueError("Use speed or repeat for a clip; duration_ms is for a sprite")
                children = self.expand(
                    target["kind"],
                    target["ref"],
                    resource_spec(self.data, target["kind"], target["ref"]),
                    child_mode,
                    stack,
                )
            start = integer(slot.get("start", 0), "slot.start")
            end = slot.get("end")
            if end is not None:
                end = integer(end, "slot.end")
            if not children and self.allow_empty:
                continue
            end = len(children) - 1 if end is None else end
            if not 0 <= start <= end < len(children):
                raise ValueError(
                    f"{key}, slot {index + 1}: range must be within 0..{len(children) - 1}"
                )
            for repetition in range(repeat):
                for child in children[start : end + 1]:
                    item = deepcopy(child)
                    item.update(
                        slot=index,
                        slot_id=slot_id,
                        repetition=repetition,
                        duration_ms=max(1, round(child["duration_ms"] / speed)),
                    )
                    if item["duration_ms"] > 16777215:
                        raise ValueError("Expanded frame duration exceeds the WebP format limit")
                    item["origin"] = [slot_id, str(repetition), *child["origin"]]
                    item["lineage"] = [
                        {
                            "kind": kind,
                            "ref": reference,
                            "slot": index,
                            "slot_id": slot_id,
                            "repetition": repetition,
                        },
                        *child["lineage"],
                    ]
                    result.append(item)
                    if len(result) > MAX_STEPS:
                        raise ValueError("Expanded resource exceeds 10,000 playback steps")
        if not result:
            if self.allow_empty:
                return []
            raise ValueError(f"{key}: add at least one nonempty resource")
        for index, item in enumerate(result):
            item.update(
                frame=index, action=reference if kind == "action" else item.get("action", reference)
            )
        animation = spec.get("animation", {})
        if kind == "action" and mode == "display":
            order, durations, _ = playback(spec, len(result))
            explicit_duration = bool({"fps", "duration_ms", "durations_ms"} & set(animation))
            result = [
                {
                    **deepcopy(result[index]),
                    "origin": [*result[index]["origin"], "@display", str(position)],
                    "duration_ms": durations[position]
                    if explicit_duration or "slots" not in spec
                    else result[index]["duration_ms"],
                }
                for position, index in enumerate(order)
            ]
        if kind == "sequence":
            previous = None
            for item in result:
                item["clip"] = item["slot"]
                marker = (item["slot"], item["repetition"])
                item["boundary"] = marker != previous
                previous = marker
        return result


def resolve_resource(
    data: dict, kind: str, reference: str, mode: str = "runtime", *, allow_empty: bool = False
) -> list[dict]:
    return ResourceResolver(data, allow_empty=allow_empty).resolve(kind, reference, mode)


def sprite_users(data: dict) -> dict[str, set[str]]:
    """Direct authored uses protect frames even in unreferenced or trimmed clips."""
    uses = {}
    collections = (
        ("action", data.get("actions", {})),
        ("sequence", data.get("workbench", {}).get("reviews", {})),
    )
    for kind, resources in collections:
        for name, spec in resources.items():
            for slot in resource_slots(spec, kind):
                target = slot.get("resource", {})
                if target.get("kind") == "sprite":
                    uses.setdefault(target["ref"], set()).add(f"{kind}:{name}")
    return uses


def validate_resources(data: dict) -> None:
    editor = data.get("workbench", {})
    if not isinstance(editor, dict) or not isinstance(editor.get("reviews", {}), dict):
        raise ValueError("workbench.reviews must be an object")
    resolver = ResourceResolver(data, allow_empty=True)
    for kind, resources in (
        ("action", data.get("actions", {})),
        ("sequence", editor.get("reviews", {})),
    ):
        for name, spec in resources.items():
            if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(spec, dict):
                raise ValueError(f"Invalid {kind} resource: {name}")
            if not isinstance(spec.get("loop", False), bool):
                raise ValueError("Resource loop must be boolean")
            if kind == "sequence" and spec.get("mode", "runtime") not in {"runtime", "display"}:
                raise ValueError("Sequence mode must be runtime or display")
            for mode in (
                ("runtime", "display") if kind == "action" else (spec.get("mode", "runtime"),)
            ):
                resolver.resolve(kind, name, mode)
