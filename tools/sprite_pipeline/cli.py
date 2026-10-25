"""Small orchestration layer; every stage is independently callable."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .animation import playback
from .config import load_config
from .export import final_frames, pack_action, preview_action, update_manifest
from .extract import extract_source
from .process import process_source
from .select import select_action
from .locking import project_lock


STAGES = ("extract", "process", "select", "pack", "preview", "build")


def main(default_config: Path | None = None, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract -> process -> select -> pack; default: pack existing final sprites.")
    parser.add_argument("stage", nargs="?", choices=STAGES, default="pack")
    parser.add_argument("--config", type=Path, default=default_config, required=default_config is None)
    parser.add_argument("--source", action="append", dest="sources", help="Only this original image, e.g. idle.png; extract/process only; repeatable")
    parser.add_argument("--action", action="append", dest="actions", help="Only this assembled action; select/pack/preview/build only; repeatable")
    parser.add_argument("--exclude-action", action="append", dest="exclude_actions",
                        help="Exclude this action after --action selection; select/pack/preview/build only; repeatable")
    parser.add_argument("--output-root", type=Path, help="Write all stages into another directory; source paths remain config-relative")
    parser.add_argument("--no-preview", action="store_true", help="Do not render WebP during pack/build")
    args = parser.parse_args(argv)
    try:
        with project_lock(args.config):
            return execute(args)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Sprite pipeline error: {error}", file=sys.stderr)
        return 1


def execute(args) -> int:
    try:
        if args.no_preview and args.stage not in {"pack", "build"}:
            raise ValueError("--no-preview is only supported for pack/build")
        if (args.actions or args.exclude_actions) and args.stage in {"extract", "process"}:
            raise ValueError("extract/process work on original images; use --source instead of --action/--exclude-action")
        if args.sources and args.stage not in {"extract", "process"}:
            raise ValueError("--source is only supported for extract/process; build prepares all original images")
        cfg = load_config(args.config, args.output_root)
        actions = cfg.select_actions(args.actions, args.exclude_actions)
        if args.stage not in {"extract", "process"} and not actions:
            raise ValueError("Configure actions after reviewing processed sprites; extract/process can run with actions={}")
        sources = []
        if args.stage in {"extract", "process", "build"}:
            discovered = cfg.discover_sources()
            sources = list(dict.fromkeys(args.sources or discovered))
            unknown_sources = set(sources) - set(discovered)
            if unknown_sources:
                raise ValueError(f"Unknown source images: {', '.join(sorted(unknown_sources))}")
        stages = ("extract", "process", "select", "pack") if args.stage == "build" else (args.stage,)
        for stage in stages:
            summaries = []
            # Validate playback for all chosen actions before touching exports.
            if stage in {"pack", "preview"} and not args.no_preview:
                for name in actions:
                    paths, _ = final_frames(cfg, name)
                    playback(cfg.action(name), len(paths))
            for name in sources if stage in {"extract", "process"} else actions:
                if stage == "extract":
                    count = extract_source(cfg, name)
                elif stage == "process":
                    count = process_source(cfg, name)
                elif stage == "select":
                    count = select_action(cfg, name)
                elif stage == "pack":
                    summary = pack_action(cfg, name)
                    summaries.append(summary)
                    count = summary["count"]
                    if not args.no_preview:
                        preview_action(cfg, name)
                else:
                    count = preview_action(cfg, name)["steps"]
                print(f"{stage}: {name} ({count} {'steps' if stage == 'preview' else 'frames'})", flush=True)
            if summaries:
                update_manifest(cfg, summaries)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Sprite pipeline error: {error}", file=sys.stderr)
        return 1
