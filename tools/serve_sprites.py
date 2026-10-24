"""Run the local Sprite Workbench; no frontend build or external service needed."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Sprite Workbench")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "assets/sprites/dafeiyu/pipeline.json")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        import uvicorn
        from sprite_pipeline.server import create_app
    except ImportError as error:
        parser.exit(1, f"Missing dependency: {error}. Install: python -m pip install -r tools/requirements-workbench.txt\n")
    app = create_app(args.config)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Sprite Workbench: {url}\nProject: {args.config.resolve()}", flush=True)
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
