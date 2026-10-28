from __future__ import annotations
import copy
import io
import json
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from sprite_pipeline.domain.actions import action_steps, review_steps, validate_editor
from sprite_pipeline.domain.errors import ExportCancelled
from sprite_pipeline.storage.configuration import Config, PROJECT_PATHS, inside
from sprite_pipeline.storage.files import read_image
from sprite_pipeline.imaging.gif import encode_gif
from sprite_pipeline.application.export_formats import pack_action, preview_action, preview_gif, update_manifest

REFERENCE_DIRS = ("references", "reference")

class ExportOperations:
    def __init__(self, session):
        self.session = session

    def export(self, data: dict, options: dict, *, progress=None, cancelled=None,
               expected_asset_revision: str | None = None,
               expected_revision: str | None = None) -> tuple[bytes, str, str]:
        with self.session.lock:
            if expected_revision is not None:
                self.session.check_revision(expected_revision)
            if expected_asset_revision is not None:
                self.session.check_assets(expected_asset_revision)
            def check_cancel() -> None:
                if cancelled is not None and cancelled.is_set():
                    raise ExportCancelled("Export cancelled")
            def report(completed: int, total: int, phase: str) -> None:
                check_cancel()
                if progress is not None:
                    progress(completed, total, phase)
                check_cancel()
            cfg = self.session.draft(data)
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
                        reference_root = self.session.reference_root(name)
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
