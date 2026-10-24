"""Noninteractive access to the same project operations used by the browser."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .projects import DEFAULT_WORKSPACES, ProjectStore
from .workbench import validate_editor


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
    for name in ("status", "validate", "apply", "prepare", "save", "import", "export"):
        command = commands.add_parser(name)
        command.add_argument("project")
        if name == "apply":
            command.add_argument("--source", required=True)
        if name in {"apply", "prepare", "import"}:
            command.add_argument("--revision", help="Expected config revision, if already inspected")
            command.add_argument("--asset-revision", help="Expected material revision, if already inspected")
        if name == "save":
            command.add_argument("--data", type=Path, required=True, help="Draft pipeline.json")
            command.add_argument("--revision", required=True, help="Revision returned by status")
        if name == "import":
            command.add_argument("--kind", choices=("source", "processed"), required=True)
            command.add_argument("--file", type=Path, required=True)
        if name == "export":
            command.add_argument("--format", choices=("project", "frames", "atlas", "webp", "all"), default="project")
            command.add_argument("--action", action="append", dest="actions")
            command.add_argument("--output", type=Path, required=True, help="New ZIP file; existing files are never overwritten")
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
                if args.command == "save":
                    data = json.loads(args.data.read_text(encoding="utf-8"))
                    result = project.save(data, args.revision)
                elif args.command in {"status", "validate"}:
                    result = {**project.state(), "project": store.describe(args.project)}
                    if args.command == "validate":
                        validate_editor(cfg)
                        valid = not result["warnings"]
                        result["valid"] = valid
                elif args.command == "export":
                    options = {"format": args.format, "actions": args.actions or list(cfg.data["actions"])}
                    content, _, _ = project.export(cfg.data, options)
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    with args.output.open("xb") as output:
                        output.write(content)
                    result = {"output": str(args.output.resolve()), "bytes": len(content)}
                else:
                    revision = args.revision or project.revision
                    assets = args.asset_revision or project.changes()["asset_revision"]
                    if args.command == "apply":
                        result = project.apply(cfg.data, revision, args.source, assets)
                    elif args.command == "prepare":
                        result = project.prepare(cfg.data, revision, assets)
                    else:
                        result = project.upload(args.kind, args.file.name, args.file.read_bytes(), cfg.data, revision, assets)
        print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
        return 0 if valid else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
