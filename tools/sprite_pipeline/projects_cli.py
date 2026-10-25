"""Noninteractive access to the same project operations used by the browser."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .projects import DEFAULT_WORKSPACES, ProjectStore
from .qa import render_qa
from .workbench import ConflictError, validate_editor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage local sprite projects; results are JSON.")
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACES)
    parser.add_argument("--json", action="store_true", help="Print compact JSON for agents")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create a self-contained empty project")
    create.add_argument("name")
    create.add_argument("--id", help="Directory name; defaults to the project name, including Unicode")
    create.add_argument("--width", type=int, default=640)
    create.add_argument("--height", type=int, default=640)
    create.add_argument("--anchor-x", type=float, default=.5)
    create.add_argument("--anchor-y", type=float, default=.9)
    commands.add_parser("list")
    for name in ("status", "validate", "apply", "prepare", "save", "import", "delete", "export", "qa"):
        command = commands.add_parser(name)
        command.add_argument("project")
        if name == "apply":
            command.add_argument("--source", required=True)
        if name in {"apply", "prepare", "import", "delete"}:
            command.add_argument("--revision", help="Expected config revision, if already inspected")
            command.add_argument("--asset-revision", help="Expected material revision, if already inspected")
        if name == "save":
            command.add_argument("--data", type=Path, required=True, help="Draft pipeline.json")
            command.add_argument("--revision", required=True, help="Revision returned by status")
        if name == "import":
            command.add_argument("--kind", choices=("source", "processed", "reference"), required=True)
            command.add_argument("--file", type=Path, action="append", required=True, help="Repeat to import multiple images")
        if name == "delete":
            command.add_argument("--kind", choices=("source", "processed", "reference"), required=True)
            command.add_argument("--ref", action="append", required=True, dest="references", help="Repeat to delete a batch; in-use sprites are protected")
        if name == "export":
            command.add_argument("--format", choices=("project", "frames", "atlas", "webp", "gif", "all"), default="project")
            command.add_argument("--action", action="append", dest="actions")
            command.add_argument("--exclude-action", action="append", dest="exclude_actions",
                                 help="Exclude an action after --action selection; repeatable; resource exports only")
            command.add_argument("--output", type=Path, required=True, help="New ZIP file; existing files are never overwritten")
        if name == "qa":
            selection = command.add_mutually_exclusive_group(required=True)
            selection.add_argument("--action", help="Inspect one saved action")
            selection.add_argument("--review", help="Inspect one saved Review")
            selection.add_argument("--ref", action="append", dest="references",
                                   help="Inspect processed references in the given order; repeat for each slot")
            selection.add_argument("--sequence", type=Path,
                                   help="JSON with ordered processed refs, duration_ms and loop")
            command.add_argument("--mode", choices=("runtime", "display"),
                                 help="Action playback mode; defaults to runtime")
            command.add_argument("--output", type=Path, required=True,
                                 help="New evidence directory; existing directories are never overwritten")
    history = commands.add_parser("history", help="List recoverable artwork operations")
    history.add_argument("project")
    restore = commands.add_parser("restore", help="Restore a recorded artwork operation")
    restore.add_argument("project")
    restore.add_argument("version", help="Version ID returned by history")
    restore.add_argument("--revision", help="Expected config revision, if already inspected")
    restore.add_argument("--asset-revision", help="Expected material revision, if already inspected")
    args = parser.parse_args(argv)
    try:
        store = ProjectStore(args.workspace_root)
        valid = True
        if args.command == "create":
            result = store.create(args.name, args.id, frame_size=[args.width, args.height], anchor=[args.anchor_x, args.anchor_y])
        elif args.command == "list":
            result = {"projects": store.list()}
        else:
            project = store.get(args.project)
            # Hold the same lock across reading current state and committing an
            # operation, so a CLI command cannot overwrite a browser writer.
            with project.lock:
                cfg = load_config(project.path)
                if args.command == "history":
                    result = {"versions": project.history_entries()}
                elif args.command == "restore":
                    revision = args.revision or project.revision
                    assets = args.asset_revision or project.changes()["asset_revision"]
                    result = project.restore(args.version, revision, assets)
                elif args.command == "save":
                    data = json.loads(args.data.read_text(encoding="utf-8"))
                    result = project.save(data, args.revision)
                elif args.command in {"status", "validate"}:
                    result = {**project.state(), "project": store.describe(args.project)}
                    if args.command == "validate":
                        validate_editor(cfg)
                        valid = not result["warnings"]
                        result["valid"] = valid
                elif args.command == "export":
                    if args.format == "project":
                        if args.exclude_actions:
                            raise ValueError("--exclude-action is not supported for project backups; choose frames, atlas, webp, gif or all")
                        actions = args.actions or list(cfg.data["actions"])
                    else:
                        actions = cfg.select_actions(args.actions, args.exclude_actions)
                    options = {"format": args.format, "actions": actions}
                    content, _, _ = project.export(cfg.data, options)
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    with args.output.open("xb") as output:
                        output.write(content)
                    result = {"output": str(args.output.resolve()), "bytes": len(content)}
                elif args.command == "qa":
                    sequence = json.loads(args.sequence.read_text(encoding="utf-8")) if args.sequence else None
                    result = render_qa(cfg, action=args.action, review=args.review,
                                       references=args.references, sequence=sequence,
                                       mode=args.mode, output=args.output)
                else:
                    revision = args.revision or project.revision
                    assets = args.asset_revision or project.changes()["asset_revision"]
                    if args.command == "apply":
                        result = project.apply(cfg.data, revision, args.source, assets)
                    elif args.command == "prepare":
                        result = project.prepare(cfg.data, revision, assets)
                    elif args.command == "delete":
                        result = project.delete(args.kind, args.references, cfg.data, revision, assets)
                    else:
                        result = project.state()
                        imported, failed, skipped = [], [], []
                        for index, path in enumerate(args.file):
                            try:
                                result = project.upload(args.kind, path.name, path.read_bytes(), result["data"], revision, assets)
                                imported.append(path.name)
                                revision, assets = result["revision"], result["asset_revision"]
                            except (ValueError, OSError, KeyError, TypeError) as error:
                                failed.append({"file": path.name, "error": str(error)})
                                if isinstance(error, ConflictError):
                                    skipped = [str(p) for p in args.file[index + 1:]]
                                    break
                        result = {**result, "imported": imported, "failed": failed, "skipped": skipped}
                        valid = not failed
        print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
        return 0 if valid else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
