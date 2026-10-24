"""Same-origin, loopback-only HTTP interface for the local workbench."""

from __future__ import annotations

import base64
import binascii
import secrets
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .workbench import ConflictError, Project


def create_app(config_path: Path) -> FastAPI:
    project = Project(config_path)
    token = secrets.token_urlsafe(32)
    web_root = Path(__file__).resolve().parent / "web"
    app = FastAPI(title="Sprite Workbench", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.project = project
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.url.netloc}"
            if origin and origin != expected:
                return JSONResponse({"error": "Only the local workbench origin may change this project"}, status_code=403)
            if not secrets.compare_digest(request.headers.get("x-workbench-token", ""), token):
                return JSONResponse({"error": "Reload the workbench to refresh its local session"}, status_code=403)
            if int(request.headers.get("content-length", "0")) > 64 * 1024 * 1024:
                return JSONResponse({"error": "Request exceeds 64 MiB"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ConflictError)
    async def conflict_error(request: Request, error: ConflictError):
        return JSONResponse({"error": str(error)}, status_code=409)

    async def input_error(request: Request, error: Exception):
        return JSONResponse({"error": str(error)}, status_code=404 if isinstance(error, FileNotFoundError) else 400)

    for error_type in (ValueError, TypeError, KeyError, OSError):
        app.add_exception_handler(error_type, input_error)

    @app.get("/")
    def index():
        return FileResponse(web_root / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/project")
    def get_project():
        return {**project.state(), "token": token}

    @app.get("/api/image")
    def get_image(kind: str, ref: str):
        return FileResponse(project.image_path(kind, ref))

    @app.post("/api/save")
    def save(payload: dict = Body(...)):
        return project.save(payload["data"], payload["revision"])

    @app.post("/api/preview")
    def preview(payload: dict = Body(...)):
        return project.preview(payload["data"], payload["source"])

    @app.post("/api/apply")
    def apply(payload: dict = Body(...)):
        return project.apply(payload["data"], payload["revision"], payload["source"])

    @app.post("/api/prepare")
    def prepare(payload: dict = Body(...)):
        return project.prepare(payload["data"], payload["revision"])

    @app.post("/api/migrate")
    def migrate(payload: dict = Body(...)):
        return project.migrate(payload["data"], payload["revision"])

    @app.post("/api/upload")
    def upload(payload: dict = Body(...)):
        try:
            content = base64.b64decode(payload["content"], validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("Invalid image upload") from error
        return project.upload(payload["kind"], payload["filename"], content, payload["data"], payload["revision"])

    @app.post("/api/export")
    def export(payload: dict = Body(...)):
        content, filename, media_type = project.export(payload["data"], payload.get("options", {}))
        return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    app.mount("/static", StaticFiles(directory=web_root), name="static")
    return app
