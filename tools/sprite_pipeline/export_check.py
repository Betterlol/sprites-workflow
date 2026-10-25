"""Independent, read-only checks for resource ZIPs against current processed PNGs."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from .animation import playback
from .config import Config, config_from_data, inside
from .workbench import action_steps


def _image(content: bytes) -> Image.Image:
    with Image.open(io.BytesIO(content)) as image:
        return image.convert("RGBA")


def _visible_equal(left: Image.Image, right: Image.Image) -> bool:
    if left.size != right.size:
        return False
    a, b = np.asarray(left.convert("RGBA")), np.asarray(right.convert("RGBA"))
    mask = a[:, :, 3] > 0
    return bool(np.array_equal(a[:, :, 3], b[:, :, 3])
                and np.array_equal(a[:, :, :3][mask], b[:, :, :3][mask]))


def _gif_matches(actual: Image.Image, expected: Image.Image) -> bool:
    """Check decoded GIF against an independent palette conversion of source."""
    rgba = expected.convert("RGBA")
    original = np.asarray(rgba)
    mask = original[:, :, 3] >= 128
    decoded = np.asarray(actual.convert("RGBA"))
    if not np.array_equal(decoded[:, :, 3] > 0, mask):
        return False
    if not mask.any():
        return True
    rgb = rgba.convert("RGB")
    hidden = rgba.getchannel("A").point(lambda alpha: 255 if alpha < 128 else 0)
    rgb.paste((0, 0, 0), (0, 0), hidden)
    quantized = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT,
                             dither=Image.Dither.NONE).convert("RGB")
    return bool(np.array_equal(decoded[:, :, :3][mask], np.asarray(quantized)[mask]))


def _issue(issues: list[dict], path: str, message: str) -> None:
    issues.append({"path": path, "message": message})


def _webp_durations(content: bytes) -> list[int]:
    """Read ANMF's 24-bit millisecond duration without relying on Pillow metadata."""
    if len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise ValueError("Invalid WebP RIFF header")
    limit = int.from_bytes(content[4:8], "little") + 8
    if limit > len(content):
        raise ValueError("Truncated WebP RIFF data")
    durations, offset = [], 12
    while offset + 8 <= limit:
        chunk = content[offset:offset + 4]
        length = int.from_bytes(content[offset + 4:offset + 8], "little")
        end = offset + 8 + length
        if end > limit:
            raise ValueError("Truncated WebP chunk")
        if chunk == b"ANMF":
            if length < 16:
                raise ValueError("Truncated WebP animation frame")
            durations.append(int.from_bytes(content[offset + 20:offset + 23], "little"))
        offset = end + (length & 1)
    if offset != limit:
        raise ValueError("Invalid WebP chunk padding")
    return durations


def _preview(archive: zipfile.ZipFile, names: set[str], prefix: str, character: str,
             action: str, ordered: list[Image.Image], order: list[int],
             durations: list[int], loop: int,
             issues: list[dict], notes: list[str]) -> None:
    media = f"{prefix}/{character}_{action}.{prefix}"
    record = f"{prefix}/{character}_{action}.animation.json"
    for name in (media, record):
        if name not in names:
            _issue(issues, name, "Preview and playback record must appear together")
    if record in names:
        try:
            actual = json.loads(archive.read(record))
            expected_steps = [{"frame": f"{action}_{index:02d}.png", "duration_ms": duration}
                              for index, duration in zip(order, durations)]
            if (actual.get("action") != action or actual.get("loop") != loop
                    or actual.get("steps") != expected_steps):
                _issue(issues, record, "Authored playback record differs from the action")
        except (ValueError, TypeError, AttributeError):
            _issue(issues, record, "Invalid playback record")
    if media not in names:
        return
    try:
        content = archive.read(media)
        with Image.open(io.BytesIO(content)) as animation:
            count = animation.n_frames
            frames, observed = [], []
            for index in range(count):
                animation.seek(index)
                observed.append(animation.info.get("duration"))
                frames.append(animation.convert("RGBA"))
            observed_loop = animation.info.get("loop")
        if prefix == "webp":
            encoded = _webp_durations(content)
            if encoded:
                if len(encoded) != count:
                    _issue(issues, media, "WebP ANMF count differs from decoded frame count")
                observed = encoded
        if any(frame.size != ordered[0].size for frame in frames):
            _issue(issues, media, "Preview canvas size differs from processed sprites")
            return
        static_without_timing = count == 1 and observed[0] is None
        expected_duration = (sum(durations) if prefix == "webp" else
                             sum(max(20, round(duration / 10) * 10) for duration in durations))
        expected_ticks = (durations if prefix == "webp" else
                          [max(20, round(duration / 10) * 10) for duration in durations])
        if static_without_timing:
            notes.append(f"{media}: static image has no encoded timing; checked the playback record")
        elif any(duration is None for duration in observed) or sum(observed) != expected_duration:
            _issue(issues, media, "Decoded preview duration differs from authored playback")
        expected_loop = loop if prefix == "webp" else (0 if loop == 0 else loop - 1 if loop > 1 else None)
        if not static_without_timing and observed_loop != expected_loop:
            _issue(issues, media, "Decoded preview loop differs from authored playback")
        if count == len(ordered):
            if not static_without_timing and observed != expected_ticks:
                _issue(issues, media, "Decoded per-frame timing differs from authored playback")
            for index, (actual, expected) in enumerate(zip(frames, ordered)):
                if prefix == "webp":
                    same = _visible_equal(actual, expected)
                else:
                    same = _gif_matches(actual, expected)
                if not same:
                    _issue(issues, media, f"Decoded frame {index} differs from processed sprite")
                    break
        else:
            if prefix == "webp":
                groups: list[tuple[Image.Image, int]] = []
                for expected, duration in zip(ordered, durations):
                    if groups and _visible_equal(groups[-1][0], expected):
                        groups[-1] = (groups[-1][0], groups[-1][1] + duration)
                    else:
                        groups.append((expected, duration))
                if (len(groups) != count
                        or (not static_without_timing and observed != [duration for _, duration in groups])
                        or any(not _visible_equal(actual, expected)
                               for actual, (expected, _) in zip(frames, groups))):
                    _issue(issues, media, "Combined WebP frames differ from processed playback")
            elif static_without_timing:
                if not all(_gif_matches(frames[0], expected) for expected in ordered):
                    _issue(issues, media, "Static GIF differs from authored processed frames")
            else:
                cursor = 0
                for actual, observed_duration in zip(frames, observed):
                    combined = 0
                    while cursor < len(ordered) and combined < observed_duration:
                        if not _gif_matches(actual, ordered[cursor]):
                            _issue(issues, media, f"Combined GIF frame differs at step {cursor}")
                            break
                        combined += expected_ticks[cursor]
                        cursor += 1
                    if combined != observed_duration:
                        _issue(issues, media, "Combined GIF frame timing differs from authored steps")
                        break
                if cursor != len(ordered):
                    _issue(issues, media, "Combined GIF omits authored steps")
            notes.append(f"{media}: encoder combined {len(ordered)} authored steps into {count} decoded frames")
    except (OSError, ValueError, EOFError) as error:
        _issue(issues, media, f"Cannot decode preview: {error}")


def check_export(cfg: Config, archive_path: Path, *, expect_format: str | None = None,
                 expected_actions: list[str] | None = None) -> dict:
    """Inspect a projects.py resource export; report mismatches without writing files."""
    if expect_format not in {None, "frames", "atlas", "webp", "gif", "all"}:
        raise ValueError("Expected format must be frames, atlas, webp, gif or all")
    issues: list[dict] = []
    notes: list[str] = []
    result = {"archive": str(archive_path.resolve()), "valid": False,
              "actions": [], "issues": issues, "notes": notes}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            listed = archive.namelist()
            names = set(listed)
            if len(listed) != len(names):
                _issue(issues, "archive", "Duplicate ZIP member names")
                return result
            damaged = archive.testzip()
            if damaged:
                _issue(issues, damaged, "ZIP CRC check failed")
                return result
            if "pipeline.json" not in names:
                _issue(issues, "pipeline.json", "Resource ZIP has no embedded project config")
                return result
            if any(name.startswith(("source/", "processed_sprites/")) for name in names):
                _issue(issues, "archive", "Project backup is not a resource export")
                return result
            try:
                embedded = config_from_data(json.loads(archive.read("pipeline.json")), cfg.path, cfg.root)
            except (ValueError, TypeError, KeyError) as error:
                _issue(issues, "pipeline.json", f"Invalid embedded config: {error}")
                return result
            if embedded.data != cfg.data:
                _issue(issues, "pipeline.json", "ZIP config differs from the current saved project")
            character = embedded.character
            selected = list(embedded.data["actions"])
            required_actions = set(expected_actions or [])
            for action in required_actions - set(selected):
                _issue(issues, "archive", f"Expected action is not in embedded config: {action}")
            for action in selected:
                frame_prefix = f"sprites/{action}/"
                sheet_name = f"spritesheets/{character}_{action}.png"
                sheet_json = f"spritesheets/{character}_{action}.json"
                meta_name = f"metadata/{character}_{action}.json"
                present = {
                    "frames": any(name.startswith(frame_prefix) for name in names),
                    "atlas": any(name in names for name in (sheet_name, sheet_json, meta_name)),
                    "webp": any(name in names for name in (f"webp/{character}_{action}.webp",
                                                             f"webp/{character}_{action}.animation.json")),
                    "gif": any(name in names for name in (f"gif/{character}_{action}.gif",
                                                            f"gif/{character}_{action}.animation.json")),
                }
                formats = [name for name, included in present.items() if included]
                if not formats:
                    if action in required_actions:
                        _issue(issues, "archive", f"Expected action has no resource files: {action}")
                    continue
                required = list(present) if expect_format == "all" else [expect_format] if expect_format else []
                for kind in required:
                    if not present[kind]:
                        _issue(issues, "archive", f"Missing {kind} resources for {action}")
                result["actions"].append({"name": action, "formats": formats})
                try:
                    runtime = action_steps(embedded, action)
                    sprites = []
                    for step in runtime:
                        ref = step["ref"]
                        path = inside(cfg.directory("processed_sprites"), ref)
                        content = path.read_bytes()
                        image = _image(content)
                        if image.size != cfg.size:
                            raise ValueError(f"{ref}: processed canvas size differs from current project")
                        sprites.append((content, image))
                except (ValueError, OSError, KeyError, TypeError) as error:
                    _issue(issues, f"processed_sprites/{action}", f"Cannot read current processed frames: {error}")
                    continue
                filenames = [f"{action}_{index:02d}.png" for index in range(len(runtime))]
                if present["frames"]:
                    expected = {frame_prefix + filename for filename in filenames}
                    if {name for name in names if name.startswith(frame_prefix)} != expected:
                        _issue(issues, frame_prefix, "Exported runtime frame names/count differ from action")
                    for index, filename in enumerate(filenames):
                        path = frame_prefix + filename
                        if path not in names or archive.read(path) != sprites[index][0]:
                            _issue(issues, path, "Exported PNG bytes differ from current processed sprite")
                if present["atlas"]:
                    for path in (sheet_name, sheet_json, meta_name):
                        if path not in names:
                            _issue(issues, path, "Atlas export is missing a required file")
                    if all(path in names for path in (sheet_name, sheet_json, meta_name)):
                        try:
                            sheet = _image(archive.read(sheet_name))
                            atlas = json.loads(archive.read(sheet_json))
                            meta = json.loads(archive.read(meta_name))
                            columns = min(embedded.action(action).get("pack", {}).get("columns", 4), len(runtime))
                            width, height = cfg.size
                            expected_size = (columns * width, ((len(runtime) + columns - 1) // columns) * height)
                            if sheet.size != expected_size:
                                _issue(issues, sheet_name, "Atlas canvas dimensions differ from action")
                            expected_meta = [{"filename": frame_prefix + filename,
                                              "duration_ms": step["duration_ms"]}
                                             for filename, step in zip(filenames, runtime)]
                            if (meta.get("action") != action or meta.get("frames") != expected_meta
                                    or meta.get("fps") != embedded.action(action).get("fps", 12)
                                    or meta.get("loop") != embedded.action(action).get("loop", False)
                                    or meta.get("frame_size") != {"w": width, "h": height}
                                    or meta.get("anchor") != embedded.anchor
                                    or meta.get("sheet") != f"{character}_{action}.png"):
                                _issue(issues, meta_name, "Runtime metadata differs from action")
                            frames_data = atlas.get("frames", {})
                            if set(frames_data) != set(filenames):
                                _issue(issues, sheet_json, "Atlas frame keys differ from action")
                            if (atlas.get("meta", {}).get("image") != f"{character}_{action}.png"
                                    or atlas.get("meta", {}).get("size") != {"w": sheet.width, "h": sheet.height}
                                    or atlas.get("meta", {}).get("format") != "RGBA8888"):
                                _issue(issues, sheet_json, "Atlas image metadata differs from sheet")
                            for index, filename in enumerate(filenames):
                                rect = {"x": index % columns * width, "y": index // columns * height,
                                        "w": width, "h": height}
                                if frames_data.get(filename, {}).get("frame") != rect:
                                    _issue(issues, sheet_json, f"Atlas placement differs for {filename}")
                                if frames_data.get(filename, {}).get("duration") != runtime[index]["duration_ms"]:
                                    _issue(issues, sheet_json, f"Atlas timing differs for {filename}")
                                if (frames_data.get(filename, {}).get("rotated") is not False
                                        or frames_data.get(filename, {}).get("trimmed") is not False
                                        or frames_data.get(filename, {}).get("sourceSize") != {"w": width, "h": height}
                                        or frames_data.get(filename, {}).get("spriteSourceSize") !=
                                        {"x": 0, "y": 0, "w": width, "h": height}):
                                    _issue(issues, sheet_json, f"Atlas frame attributes differ for {filename}")
                                if meta.get("atlas_frames", {}).get(filename, {}).get("frame") != rect:
                                    _issue(issues, meta_name, f"Runtime atlas placement differs for {filename}")
                                if meta.get("atlas_frames", {}).get(filename, {}).get("anchor") != embedded.anchor:
                                    _issue(issues, meta_name, f"Runtime anchor differs for {filename}")
                                crop = sheet.crop((rect["x"], rect["y"], rect["x"] + width, rect["y"] + height))
                                if not _visible_equal(crop, sprites[index][1]):
                                    _issue(issues, sheet_name, f"Atlas pixels differ for {filename}")
                                    break
                        except (OSError, ValueError, TypeError, AttributeError) as error:
                            _issue(issues, sheet_name, f"Cannot inspect atlas: {error}")
                if present["webp"] or present["gif"]:
                    order, durations, loop = playback(embedded.action(action), len(runtime))
                    ordered = [sprites[index][1] for index in order]
                    for prefix in ("webp", "gif"):
                        if present[prefix]:
                            _preview(archive, names, prefix, character, action,
                                     ordered, order, durations, loop, issues, notes)
            atlas_actions = [entry["name"] for entry in result["actions"] if "atlas" in entry["formats"]]
            if atlas_actions:
                manifest_path = f"{character}_manifest.json"
                if manifest_path not in names:
                    _issue(issues, manifest_path, "Atlas export is missing its manifest")
                else:
                    try:
                        manifest = json.loads(archive.read(manifest_path))
                        if (manifest.get("character") != character
                                or manifest.get("frame_size") != {"w": cfg.size[0], "h": cfg.size[1]}
                                or manifest.get("anchor") != embedded.anchor):
                            _issue(issues, manifest_path, "Manifest project details differ")
                        entries = manifest.get("actions", [])
                        if {entry.get("name") for entry in entries} != set(atlas_actions):
                            _issue(issues, manifest_path, "Manifest action list differs from archive")
                        for action in atlas_actions:
                            matching = [entry for entry in entries if entry.get("name") == action]
                            if len(matching) != 1:
                                _issue(issues, manifest_path, f"Manifest needs exactly one entry for {action}")
                                continue
                            entry = matching[0]
                            spec = embedded.action(action)
                            if (entry.get("count") != len(spec["sprites"])
                                    or entry.get("fps") != spec.get("fps", 12)
                                    or entry.get("loop") != spec.get("loop", False)
                                    or entry.get("sheet") != f"spritesheets/{character}_{action}.png"
                                    or entry.get("preview") != f"webp/{character}_{action}.webp"):
                                _issue(issues, manifest_path, f"Manifest action details differ for {action}")
                    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
                        _issue(issues, manifest_path, f"Cannot inspect manifest: {error}")
            if not result["actions"]:
                _issue(issues, "archive", "No action resource files found")
    except (zipfile.BadZipFile, OSError) as error:
        _issue(issues, "archive", f"Cannot read ZIP: {error}")
    result["valid"] = not issues
    return result
