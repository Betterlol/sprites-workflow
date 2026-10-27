"""Local editor domain: drafts, shared rendering, reference-only actions and exports.

Only explicit apply/save/import operations change the project. Preview and export
operate on a validated snapshot and never rebuild the published CLI directories.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import shutil
import zipfile
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlencode

from PIL import Image

from .animation import playback
from .config import Config, IMAGE_SUFFIXES, NAME, PROJECT_PATHS, config_from_data, inside, integer, load_config, source_fingerprint
from .export import pack_action, preview_action, preview_gif, update_manifest
from .extract import cut_frames, preserve_slice_ids, previous_slices, slice_ids
from .slices import read_slices, write_slices
from .files import numbered_frames, read_image, replace_frames, write_json
from .history import HistoryConflictError, OperationNotStarted, ProjectHistory
from .process import process_images
from .gif import encode_gif
from .locking import project_lock

REFERENCE_DIRS = ("references", "reference")


class ConflictError(ValueError):
    """The on-disk project changed since the editor loaded it."""


class OperationCancelled(Exception):
    """A long operation was stopped at a safe item boundary."""


class ExportCancelled(OperationCancelled):
    """An export was stopped at a safe item boundary."""


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def data_url(image: Image.Image) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes(image)).decode("ascii")


def image_url(kind: str, reference: str, path: Path, project_id: str | None = None) -> str:
    stat = path.stat()
    route = f"/api/projects/{quote(project_id, safe='')}/image" if project_id is not None else "/api/image"
    return route + "?" + urlencode({"kind": kind, "ref": reference, "v": f"{stat.st_mtime_ns}-{stat.st_size}"})


def action_steps(cfg: Config, name: str, mode: str = "runtime") -> list[dict]:
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


def review_steps(cfg: Config, review: dict, *, allow_empty: bool = False) -> list[dict]:
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


def validate_editor(cfg: Config) -> None:
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


class Project:
    def __init__(self, path: Path, project_id: str | None = None):
        self.path = path.resolve()
        self.project_id = project_id
        self.lock = project_lock(self.path)
        self._image_config = load_config(self.path)
        self._image_config_signature = self.config_signature()
        self._asset_metadata: dict[Path, tuple[tuple[int, int], list[int], tuple[int, int, int, int] | None]] = {}
        self.versions = ProjectHistory(self.path.parent)

    def history_transaction(self, operation: str, paths: list[Path]):
        if all(path.resolve().is_relative_to(self.path.parent) for path in paths):
            return self.versions.transaction(operation, paths)
        # Explicit --config projects may keep source/processed paths outside
        # their config directory. Their legacy operations remain available.
        return nullcontext()

    def history_entries(self) -> list[dict]:
        with self.lock:
            return self.versions.list()

    def restore(self, version_id: str, revision: str, asset_revision: str | None = None) -> dict:
        with self.lock:
            self.check_revision(revision)
            self.check_assets(asset_revision)
            try:
                self.versions.restore(version_id, lambda: validate_editor(load_config(self.path)))
            except HistoryConflictError as error:
                raise ConflictError(str(error)) from error
            return self.state()

    def config_signature(self) -> str:
        return self.revision

    def validate_source_location(self, cfg: Config) -> None:
        if self.project_id not in (None, "@config"):
            source = cfg.source
            if not source.is_relative_to(self.path.parent) or source == self.path.parent:
                raise ValueError("工作区工程的 source 必须位于工程目录内；旧布局请使用 --config 打开。")

    @property
    def revision(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def check_revision(self, revision: str) -> None:
        if revision != self.revision:
            raise ConflictError("工程已被其他窗口或命令行修改，请重新载入后再操作；当前草稿仍保留在页面中。")

    def asset_revision(self, cfg: Config) -> str:
        digest = hashlib.sha256()
        for kind, root in (("source", cfg.source), ("slices", cfg.directory("source_sprites")), ("processed", cfg.directory("processed_sprites")),
                           ("final", cfg.directory("sprites")),
                           *((name, self.reference_root(name)) for name in REFERENCE_DIRS)):
            for path in sorted(root.rglob("*")):
                if not path.is_file() or (path.suffix.lower() not in IMAGE_SUFFIXES and path.name != "_stage.json"):
                    continue
                relative = path.relative_to(root).as_posix()
                inside(root, relative)
                stat = path.stat()
                digest.update(json.dumps([kind, relative, stat.st_mtime_ns, stat.st_size]).encode())
        return digest.hexdigest()

    def check_assets(self, revision: str | None) -> None:
        if revision is not None and revision != self.asset_revision(load_config(self.path)):
            raise ConflictError("工程素材已被外部修改，请刷新素材后重试；当前草稿仍保留。")

    def changes(self) -> dict:
        with self.lock:
            return {"revision": self.revision, "asset_revision": self.asset_revision(load_config(self.path))}

    def draft(self, data: dict) -> Config:
        current = load_config(self.path)
        cfg = config_from_data(data, self.path)
        for filename, settings in cfg.data.get('sources', {}).items():
            minimum = current.source_spec(filename)['extract'].get('next_id', 0)
            if minimum:
                extraction = settings.setdefault('extract', {})
                extraction['next_id'] = max(minimum, extraction.get('next_id', 0))
        if cfg.data.get("paths") != current.data.get("paths"):
            raise ValueError("The editor cannot change project paths; open another project with --config")
        if cfg.character != current.character:
            raise ValueError("The editor cannot change the project character ID")
        if max(cfg.size) > 4096:
            raise ValueError("Workbench frame dimensions must be <= 4096 pixels")
        return cfg

    def image_path(self, kind: str, reference: str) -> Path:
        signature = self.config_signature()
        if signature != self._image_config_signature:
            self._image_config = load_config(self.path)
            self._image_config_signature = signature
        cfg = self._image_config
        self.validate_source_location(cfg)
        roots = {"source": cfg.source, "processed": cfg.directory("processed_sprites"), "reference": self.path.parent}
        if kind not in roots:
            raise ValueError("Unknown image category")
        path = inside(roots[kind], reference)
        if kind == "reference":
            directory = Path(reference).parts[0]
            if directory not in REFERENCE_DIRS or not path.is_relative_to(self.reference_root(directory)):
                raise ValueError("Reference images must be inside references/ or legacy reference/")
        if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
            raise FileNotFoundError(reference)
        return path

    def reference_root(self, name: str = "references") -> Path:
        if name not in REFERENCE_DIRS:
            raise ValueError("Unknown reference directory")
        return inside(self.path.parent, name)

    def state(self) -> dict:
        with self.lock:
            raw = self.path.read_bytes()
            cfg = config_from_data(json.loads(raw), self.path)
            self.validate_source_location(cfg)
            assets = []
            root = cfg.directory("processed_sprites")
            present_assets = set()
            for path in sorted(root.rglob("*.png")):
                reference = path.relative_to(root).as_posix()
                inside(root, reference)
                present_assets.add(path)
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                cached = self._asset_metadata.get(path)
                if cached is None or cached[0] != signature:
                    with Image.open(path) as image:
                        cached = (signature, list(image.size), image.convert("RGBA").getbbox())
                    self._asset_metadata[path] = cached
                assets.append({"ref": reference, "url": image_url("processed", reference, path, self.project_id),
                               "size": cached[1], "bbox": cached[2]})
            self._asset_metadata = {path: metadata for path, metadata in self._asset_metadata.items()
                                    if path in present_assets}
            sources = []
            discovered = cfg.discover_sources(allow_empty=True, allow_missing=True)
            for filename in discovered:
                path = inside(cfg.source, filename)
                with Image.open(path) as image:
                    size = list(image.size)
                directory = inside(root, cfg.source_id(filename))
                stage_path = directory / "_stage.json"
                stage = json.loads(stage_path.read_text(encoding="utf-8")) if stage_path.exists() else {}
                fingerprint = stage.get("fingerprint")
                sources.append({"file": filename, "url": image_url("source", filename, path, self.project_id), "size": size,
                                "count": sum(a["ref"].startswith(cfg.source_id(filename) + "/") for a in assets),
                                "stale": bool(fingerprint and fingerprint != self.fingerprint(cfg, filename))})
            legacy_count = len(list(cfg.directory("sprites").rglob("*.png")))
            reference_images = []
            for name in REFERENCE_DIRS:
                root = self.reference_root(name)
                for path in sorted(root.rglob("*")):
                    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                        relative = path.relative_to(root).as_posix()
                        inside(root, relative)
                        ref = name + "/" + relative
                        with Image.open(path) as image:
                            reference_images.append({"ref": ref, "file": relative, "size": list(image.size),
                                "url": image_url("reference", ref, path, self.project_id)})
            warnings = []
            missing = set(cfg.data.get("sources", {})) - set(discovered)
            if missing:
                warnings.append("原图缺失，请恢复图片或移除对应规则：" + ", ".join(sorted(missing)))
            references = {a["ref"] for a in assets}
            missing_refs = {ref for name in cfg.data["actions"] for ref in cfg.action(name).get("sprites") or []
                            if ref not in references}
            if missing_refs:
                warnings.append(f"有 {len(missing_refs)} 个动作素材引用缺失，请准备素材或调整引用。")
            return {"data": cfg.data, "revision": hashlib.sha256(raw).hexdigest(), "sources": sources, "assets": assets,
                    "references": reference_images,
                    "asset_revision": self.asset_revision(cfg), "warnings": warnings,
                    "project_file": self.path.name, "legacy_count": legacy_count}

    def save(self, data: dict, revision: str) -> dict:
        with self.lock:
            self.check_revision(revision)
            cfg = self.draft(data)
            validate_editor(cfg)
            self.check_revision(revision)
            write_json(self.path, cfg.data)
            return {"revision": self.revision}

    def fingerprint(self, cfg: Config, filename: str) -> str:
        return source_fingerprint(cfg, filename)

    def save_slices(self, filename: str, extract: dict, revision: str, asset_revision: str | None = None) -> dict:
        """Commit only one extraction recipe and its native slices, preserving other edits."""
        with self.lock:
            self.check_revision(revision)
            self.check_assets(asset_revision)
            current = load_config(self.path)
            baseline_assets = self.asset_revision(current)
            data = copy.deepcopy(current.data)
            settings = data.setdefault('sources', {}).setdefault(filename, {})
            settings['extract'] = copy.deepcopy(extract)
            previous = previous_slices(current, filename)
            old_ids = {Path(item['file']).stem for item in previous}
            minimum = max(current.source_spec(filename)['extract'].get('next_id', 0),
                          max([int(key) for key in old_ids] + [-1]) + 1)
            settings['extract']['next_id'] = max(minimum, settings['extract'].get('next_id', 0))
            cfg, images, _, descriptors, _ = self.render(data, filename, 'extract')
            keys = set(images)
            prefix = cfg.source_id(filename) + '/'
            available = {prefix + item['file'] for item in descriptors}
            broken = {ref for name in current.data['actions'] for ref in (current.action(name).get('sprites') or [])
                      if ref.startswith(prefix) and ref not in available}
            if broken:
                raise ValueError('区域仍被已保存动作使用，请先保存动作中的移除或替换：' + ', '.join(sorted(broken)))
            unused_overrides = set(current.source_spec(filename)['process'].get('overrides', {})) - keys
            if unused_overrides:
                raise ValueError('区域仍有已保存的单帧调整，请先重置并保存这些帧：' + ', '.join(sorted(unused_overrides)))
            rules = cfg.data['sources'][filename]['extract']
            rules['identities'] = descriptors
            rules['next_id'] = max(rules['next_id'], max(map(int, keys), default=-1) + 1)
            if rules.get('method') == 'boxes':
                rules['region_ids'] = list(images)
            directory = inside(cfg.directory('source_sprites'), cfg.source_id(filename))
            self.check_revision(revision)
            self.check_assets(baseline_assets)
            with self.history_transaction('save slices', [self.path, directory]):
                write_slices(cfg, filename, images, descriptors)
                write_json(self.path, cfg.data)
            return self.state()

    def render(self, data: dict, filename: str, stage: str = "process") -> tuple[Config, dict, dict, list, float]:
        if stage not in {"extract", "process"}:
            raise ValueError("Unknown preview stage")
        cfg = self.draft(data)
        if filename not in cfg.discover_sources():
            raise ValueError("Unknown source image")
        cached = read_slices(cfg, filename)
        if cached is None:
            raw, boxes = cut_frames(read_image(inside(cfg.source, filename)), cfg.source_spec(filename)["extract"])
            keys = slice_ids(cfg, filename, boxes)
            images = dict(zip(keys, raw))
            descriptors = [{"file": f"{key}.png", "source_box": box} for key, box in zip(keys, boxes)]
        else:
            images, descriptors = cached
        frames, scale = ({f"{key}.png": image for key, image in images.items()}, 1.0) if stage == "extract" else process_images(cfg, filename, images)
        return cfg, images, frames, descriptors, scale

    def preview(self, data: dict, filename: str, stage: str = "process") -> dict:
        with self.lock:
            cfg, _raw, frames, descriptors, scale = self.render(data, filename, stage)
            return {"stage": stage, "scale": scale,
                "next_id": max(cfg.source_spec(filename)['extract'].get('next_id', 0), max(map(int, _raw), default=-1) + 1),
                "frames": [
                {"id": Path(item["file"]).stem, "ref": cfg.source_id(filename) + "/" + item["file"],
                 "box": item["source_box"], "url": data_url(frames[item["file"]]),
                 "bbox": frames[item["file"]].getbbox()}
                for item in descriptors]}

    def apply(self, data: dict, revision: str, filename: str, asset_revision: str | None = None) -> dict:
        with self.lock:
            self.check_revision(revision)
            self.check_assets(asset_revision)
            cfg, _, frames, descriptors, scale = self.render(data, filename)
            validate_editor(cfg)
            prefix = cfg.source_id(filename) + "/"
            available = {prefix + name for name in frames}
            broken = {ref for name in cfg.data["actions"] for ref in (cfg.action(name).get("sprites") or [])
                      if ref.startswith(prefix) and ref not in available}
            if broken:
                raise ValueError("切图会移除正在使用的素材，请先从动作中移除或替换这些引用：" + ", ".join(sorted(broken)))
            self.check_revision(revision)
            self.check_assets(asset_revision)
            cfg.data.setdefault("sources", {}).setdefault(filename, {}).setdefault("extract", {})["identities"] = descriptors
            directory = inside(cfg.directory("processed_sprites"), cfg.source_id(filename))
            with self.history_transaction("apply", [self.path, directory]):
                replace_frames(directory, frames, owned=r"\d+\.png", metadata={
                    "stage": "process", "source": filename, "scale": scale, "files": list(frames),
                    "frames": descriptors, "fingerprint": self.fingerprint(cfg, filename),
                })
                write_json(self.path, cfg.data)
            return self.state()

    def prepare(self, data: dict, revision: str, asset_revision: str | None = None,
                *, progress=None, cancelled=None) -> dict:
        """Prepare absent sources only; existing processed artwork is never rebuilt."""
        with self.lock:
            self.check_revision(revision)
            self.check_assets(asset_revision)
            cfg = self.draft(data)
            pending = []
            sources = cfg.discover_sources()
            if progress is not None:
                progress(0, len(sources), "准备原图")
            for index, filename in enumerate(sources, 1):
                if cancelled is not None and cancelled.is_set():
                    raise OperationCancelled("Preparation cancelled")
                directory = inside(cfg.directory("processed_sprites"), cfg.source_id(filename))
                if not list(directory.glob("*.png")):
                    rendered = self.render(cfg.data, filename)
                    pending.append((filename, rendered))
                if progress is not None:
                    progress(index, len(sources), filename)
                if cancelled is not None and cancelled.is_set():
                    raise OperationCancelled("Preparation cancelled")
            # Render all sources before making any changes on validation failure.
            validate_editor(cfg)
            self.check_revision(revision)
            self.check_assets(asset_revision)
            if cancelled is not None and cancelled.is_set():
                raise OperationCancelled("Preparation cancelled")
            directories = [inside(cfg.directory("processed_sprites"), cfg.source_id(filename)) for filename, _ in pending]
            with self.history_transaction("prepare", [self.path, *directories]):
                for filename, (_, _, frames, descriptors, scale) in pending:
                    cfg.data.setdefault("sources", {}).setdefault(filename, {}).setdefault("extract", {})["identities"] = descriptors
                    replace_frames(inside(cfg.directory("processed_sprites"), cfg.source_id(filename)), frames,
                                   owned=r"\d+\.png", metadata={
                                       "stage": "process", "source": filename, "scale": scale, "files": list(frames),
                                       "frames": descriptors, "fingerprint": self.fingerprint(cfg, filename)})
                write_json(self.path, cfg.data)
            return self.state()

    def migrate(self, data: dict, revision: str, asset_revision: str | None = None) -> dict:
        """Preserve published/manual frame pixels as reusable approved assets."""
        with self.lock:
            self.check_revision(revision)
            self.check_assets(asset_revision)
            cfg = self.draft(data)
            copies = []
            changed = 0
            for name in cfg.data["actions"]:
                try:
                    final = numbered_frames(cfg.directory("sprites") / name, name)
                except FileNotFoundError:
                    continue
                refs = cfg.action(name).get("sprites") or []
                references = []
                for index, path in enumerate(final):
                    image = read_image(path)
                    if image.size != cfg.size:
                        raise ValueError(f"{path.name}: final frame size does not match this project")
                    reference = refs[index] if index < len(refs) else None
                    processed = inside(cfg.directory("processed_sprites"), reference) if reference else None
                    if processed and processed.exists() and read_image(processed).tobytes() == image.tobytes():
                        references.append(reference)
                    else:
                        digest = hashlib.sha256(image.tobytes()).hexdigest()[:12]
                        reference = f"_approved/{name}/{index:03d}-{digest}.png"
                        copies.append((path, inside(cfg.directory("processed_sprites"), reference)))
                        references.append(reference)
                        changed += 1
                cfg.data["actions"][name]["sprites"] = references
            validate_editor(cfg)
            self.check_revision(revision)
            self.check_assets(asset_revision)
            with self.history_transaction("migrate", [self.path, *(destination for _, destination in copies)]):
                for source, destination in copies:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                write_json(self.path, cfg.data)
            return {**self.state(), "imported": changed}

    def upload(self, kind: str, filename: str, content: bytes, data: dict, revision: str,
               asset_revision: str | None = None) -> dict:
        with self.lock:
            self.check_revision(revision)
            self.check_assets(asset_revision)
            cfg = self.draft(data)
            if not filename or Path(filename).name != filename or any(c in filename for c in '\\/:*?"<>|\x00') or filename.endswith((" ", ".")):
                raise ValueError("Use an image filename without directory components")
            if Path(filename).suffix.lower() not in IMAGE_SUFFIXES:
                raise ValueError("Unsupported image format")
            with Image.open(io.BytesIO(content)) as original:
                original.load()
                image = original.convert("RGBA")
            if kind == "source":
                destination = inside(cfg.source, filename)
                stem = Path(filename).with_suffix("").as_posix().casefold()
                if stem in {"imports", "_approved"}:
                    raise ValueError("This filename is reserved for imported or approved sprites")
                if any(cfg.source_id(name).casefold() == stem for name in cfg.discover_sources(allow_empty=True, allow_missing=True)):
                    raise ValueError("An original with this output name already exists")
                cfg.data.setdefault("sources", {}).setdefault(filename, {})
            elif kind == "processed":
                if image.size != cfg.size:
                    raise ValueError(f"Processed sprite must use the project canvas {cfg.size}")
                destination = inside(cfg.directory("processed_sprites"), "imports/" + Path(filename).stem + ".png")
                content = png_bytes(image)
            elif kind == "reference":
                destination = inside(self.reference_root(), filename)
            else:
                raise ValueError("Unknown upload category")
            if destination.exists():
                raise ValueError("An image with this filename already exists; rename the import")
            validate_editor(cfg)
            self.check_revision(revision)
            self.check_assets(asset_revision)
            with self.history_transaction("upload " + kind, [self.path, destination]):
                destination.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation also avoids races with external import tools.
                try:
                    output = destination.open("xb")
                except FileExistsError as error:
                    raise OperationNotStarted("An image with this filename already exists; rename the import") from error
                with output:
                    output.write(content)
                write_json(self.path, cfg.data)
            return self.state()

    def delete(self, kind: str, references: list[str], data: dict, revision: str,
               asset_revision: str | None = None) -> dict:
        """Delete a validated batch; in-use sprites and partial failures are protected."""
        with self.lock:
            self.check_revision(revision)
            self.check_assets(asset_revision)
            cfg = self.draft(data)
            validate_editor(cfg)
            if (not isinstance(references, list) or not 1 <= len(references) <= 1000
                    or any(not isinstance(ref, str) for ref in references)
                    or len({ref.casefold() for ref in references}) != len(references)):
                raise ValueError("Select 1–1000 distinct image references")
            targets = []
            blocked_refs = set()
            prefixes = []
            metadata = {}
            def target_path(root: Path, reference: str) -> Path:
                path = inside(root, reference)
                if path != (root / reference).absolute():
                    raise ValueError("Linked paths cannot be deleted automatically; remove the link separately")
                return path
            if kind == "source":
                known = set(cfg.discover_sources(allow_empty=True, allow_missing=True)) | set(cfg.data.get("sources", {}))
                for ref in references:
                    if ref not in known:
                        raise FileNotFoundError(f"Unknown source: {ref}")
                    source = target_path(cfg.source, ref)
                    if source.exists():
                        if not source.is_file():
                            raise ValueError(f"Source is not an image file: {ref}")
                        targets.append(source)
                    prefix = cfg.source_id(ref)
                    if any(name != ref and cfg.source_id(name).casefold().startswith(prefix.casefold() + "/") for name in known):
                        raise ValueError("Source output directories overlap; fix the source rules before deletion")
                    prefixes.append(prefix + "/")
                    for stage in ("source_sprites", "processed_sprites"):
                        root = cfg.directory(stage)
                        directory = target_path(root, prefix)
                        if directory.exists():
                            # Resolve every descendant before moving a directory;
                            # a junction must never turn deletion into an escape.
                            for path in directory.rglob("*"):
                                inside(root, path.relative_to(root).as_posix())
                            targets.append(directory)
                    cfg.data.get("sources", {}).pop(ref, None)
            elif kind == "processed":
                blocked_refs.update(references)
                for ref in references:
                    path = self.image_path(kind, ref)
                    target_path(cfg.directory("processed_sprites"), ref)
                    if path.suffix.lower() != ".png":
                        raise ValueError("Processed references must be PNG files")
                    targets.append(path)
                    stage = target_path(cfg.directory("processed_sprites"), str(Path(ref).parent / "_stage.json"))
                    if stage.is_file():
                        payload = metadata.setdefault(stage, json.loads(stage.read_text(encoding="utf-8")))
                        payload["files"] = [name for name in payload.get("files", []) if name != path.name]
                        # Retain region identities and overrides: explicitly
                        # applying the source later may regenerate this sprite.
            elif kind == "reference":
                targets = [self.image_path(kind, ref) for ref in references]
                for ref in references:
                    target_path(self.path.parent, ref)
            else:
                raise ValueError("Unknown deletion category")
            uses = {name for name in cfg.data["actions"] for ref in cfg.action(name).get("sprites") or []
                    if ref in blocked_refs or any(ref.startswith(prefix) for prefix in prefixes)}
            if uses:
                raise ValueError("素材仍被动作使用，请先从这些动作移除或替换引用：" + ", ".join(sorted(uses)))
            self.check_revision(revision)
            self.check_assets(asset_revision)
            replacements = {**metadata, self.path: cfg.data}
            # Stage removed files and old metadata beside the project. If a
            # filesystem write fails, put them all back before reporting failure.
            with self.history_transaction("delete " + kind, [*targets, *replacements]):
                with TemporaryDirectory(prefix=".sprite-delete-", dir=self.path.parent) as temporary:
                    staged = []
                    written = []
                    try:
                        for index, path in enumerate(dict.fromkeys([*targets, *replacements])):
                            backup = Path(temporary) / str(index)
                            path.replace(backup)
                            staged.append((path, backup))
                        for path, payload in replacements.items():
                            write_json(path, payload)
                            written.append(path)
                    except BaseException:
                        for path in reversed(written):
                            path.unlink()
                        for path, backup in reversed(staged):
                            backup.replace(path)
                        raise
            return {**self.state(), "deleted": len(references)}

    def export(self, data: dict, options: dict, *, progress=None, cancelled=None,
               expected_asset_revision: str | None = None,
               expected_revision: str | None = None) -> tuple[bytes, str, str]:
        with self.lock:
            if expected_revision is not None:
                self.check_revision(expected_revision)
            if expected_asset_revision is not None:
                self.check_assets(expected_asset_revision)
            def check_cancel() -> None:
                if cancelled is not None and cancelled.is_set():
                    raise ExportCancelled("Export cancelled")
            def report(completed: int, total: int, phase: str) -> None:
                check_cancel()
                if progress is not None:
                    progress(completed, total, phase)
                check_cancel()
            cfg = self.draft(data)
            validate_editor(cfg)
            kind = options.get("format", "all")
            if kind not in {"frames", "atlas", "webp", "gif", "all", "project", "review"}:
                raise ValueError("Unknown export format")
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                if kind == "project":
                    project_data = copy.deepcopy(cfg.data)
                    project_data["paths"] = dict(PROJECT_PATHS)
                    files = []
                    for filename in cfg.discover_sources(allow_empty=True, allow_missing=True):
                        files.append((inside(cfg.source, filename), "source/" + filename))
                    root = cfg.directory("processed_sprites")
                    for path in root.rglob("*"):
                        if path.is_file() and (path.suffix.lower() == ".png" or path.name == "_stage.json"):
                            reference = path.relative_to(root).as_posix()
                            files.append((inside(root, reference), "processed_sprites/" + reference))
                    for name in REFERENCE_DIRS:
                        reference_root = self.reference_root(name)
                        for path in reference_root.rglob("*"):
                            if path.is_file():
                                relative = path.relative_to(reference_root).as_posix()
                                files.append((inside(reference_root, relative), name + "/" + relative))
                    readme = cfg.path.parent / "README.md"
                    if readme.is_file():
                        files.append((inside(cfg.path.parent, "README.md"), "README.md"))
                    total = len(files) + 1
                    report(0, total, "准备工程文件")
                    archive.writestr("pipeline.json", json.dumps(project_data, ensure_ascii=False, indent=2))
                    report(1, total, "pipeline.json")
                    for index, (path, relative) in enumerate(files, 2):
                        check_cancel()
                        archive.write(path, relative)
                        report(index, total, relative)
                elif kind == "review":
                    report(0, 1, "正在编码 Review")
                    review = options.get("review")
                    steps = review_steps(cfg, review)
                    image_cache = {ref: read_image(inside(cfg.directory("processed_sprites"), ref)) for ref in {step["ref"] for step in steps}}
                    images = [image_cache[step["ref"]] for step in steps]
                    if any(image.size != cfg.size for image in images):
                        raise ValueError("Review sprites must match the project canvas")
                    buffer = io.BytesIO()
                    images[0].save(buffer, format="WEBP", save_all=True, append_images=images[1:],
                                   duration=[s["duration_ms"] for s in steps], loop=0 if review.get("loop", True) else 1,
                                   lossless=True, method=4)
                    archive.writestr("review.webp", buffer.getvalue())
                    archive.writestr("review.gif", encode_gif(
                        images, [s["duration_ms"] for s in steps], 0 if review.get("loop", True) else 1))
                    archive.writestr("review.animation.json", json.dumps({"review": review, "steps": steps}, ensure_ascii=False, indent=2))
                    report(1, 1, "Review")
                else:
                    names = options.get("actions")
                    if not isinstance(names, list) or not names or len(names) != len(set(names)):
                        raise ValueError("Select one or more distinct actions to export")
                    if any(name not in cfg.data["actions"] for name in names):
                        raise ValueError("Unknown export action")
                    total = len(names) + 1
                    report(0, total, "准备动作")
                    # The legacy exporters work in a disposable directory only.
                    with TemporaryDirectory(prefix="sprite-export-") as temporary:
                        export_data = copy.deepcopy(cfg.data)
                        export_data["paths"] = {key: key for key in (
                            "source_sprites", "processed_sprites", "sprites", "spritesheets", "webp", "gif", "metadata")}
                        export_cfg = Config(cfg.path, Path(temporary), export_data)
                        summaries = []
                        for action_index, name in enumerate(names, 1):
                            check_cancel()
                            steps = action_steps(cfg, name)
                            if kind in {"atlas", "all"}:
                                columns = min(cfg.action(name).get("pack", {}).get("columns", 4), len(steps))
                                if columns * cfg.size[0] > 16384 or ((len(steps) + columns - 1) // columns) * cfg.size[1] > 16384:
                                    raise ValueError("Atlas exceeds 16,384 pixels on an axis; adjust columns or split the action")
                            folder = export_cfg.directory("sprites") / name
                            folder.mkdir(parents=True)
                            for index, step in enumerate(steps):
                                check_cancel()
                                source = inside(cfg.directory("processed_sprites"), step["ref"])
                                if read_image(source).size != cfg.size:
                                    raise ValueError(f"{step['ref']}: sprite size does not match project canvas")
                                shutil.copyfile(source, folder / f"{name}_{index:02d}.png")
                            if kind in {"atlas", "all"}:
                                summaries.append(pack_action(export_cfg, name))
                            if kind in {"webp", "all"}:
                                preview_action(export_cfg, name)
                            if kind in {"gif", "all"}:
                                preview_gif(export_cfg, name)
                            report(action_index, total, name)
                        if summaries:
                            update_manifest(export_cfg, summaries)
                        for path in Path(temporary).rglob("*"):
                            if path.is_file():
                                check_cancel()
                                relative = path.relative_to(temporary)
                                if relative.parts[0] != "sprites" or kind in {"frames", "all"}:
                                    archive.write(path, relative.as_posix())
                        archive.writestr("pipeline.json", json.dumps(cfg.data, ensure_ascii=False, indent=2))
                        report(total, total, "ZIP")
            return output.getvalue(), f"{cfg.character}-{kind}.zip", "application/zip"
