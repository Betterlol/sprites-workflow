"""Stable region identity matching without reading project files."""
from pathlib import PurePosixPath as Path

def preserve_slice_ids(boxes: list[tuple], previous: list[dict], minimum_next_id: int = 0) -> list[str]:
    """Match old region identities before assigning fresh IDs to new regions."""
    old = {Path(item["file"]).stem: tuple(item["source_box"]) for item in previous
           if isinstance(item, dict) and "file" in item and "source_box" in item}
    used = set()
    result = [None] * len(boxes)
    next_id = max(minimum_next_id, max([int(key) for key in old if key.isdigit()] + [-1]) + 1)
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
