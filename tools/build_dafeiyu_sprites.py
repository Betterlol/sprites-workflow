"""Dafeiyu preset for the shared sprite pipeline (default: repack final PNGs).

Use extract/process for review, select to promote configured sprites, and pack
to export them. `build` explicitly runs every stage and replaces selected frames.
"""

from pathlib import Path

from sprite_pipeline.cli import main as run_pipeline


CONFIG = Path(__file__).resolve().parents[1] / "assets" / "sprites" / "dafeiyu" / "pipeline.json"


def main() -> int:
    return run_pipeline(default_config=CONFIG)


if __name__ == "__main__":
    raise SystemExit(main())
