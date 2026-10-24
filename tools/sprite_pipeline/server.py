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

from .workbench import ConflictError
from .locking import ProjectBusyError
from .projects import DEFAULT_WORKSPACES, ProjectStore


def create_app(config_path: Path | None = None, workspace_root: Path | None = None) -> FastAPI:
    store = ProjectStore(workspace_root or DEFAULT_WORKSPACES, config_path)
    token = secrets.token_urlsafe(32)
    web_root = Path(__file__).resolve().parent / "web"
    app = FastAPI(title="Sprite Workbench", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.projects = store
    app.state.project = store.get(store.initial_id) if store.initial_id is not None else None
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
    @app.exception_handler(ProjectBusyError)
    @app.exception_handler(FileExistsError)
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

    @app.get("/api/projects")
    def list_projects():
        return {"projects": store.list(), "token": token, "initial_project": store.initial_id,
                "workspace_root": str(store.root)}

    @app.post("/api/projects")
    def create_project(payload: dict = Body(...)):
        return store.create(payload["name"], payload.get("id"), frame_size=payload.get("frame_size"),
                            anchor=payload.get("anchor"))

    def snapshot(project_id: str):
        return {**store.get(project_id).state(), "project": store.describe(project_id), "token": token}

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        return snapshot(project_id)

    @app.get("/api/projects/{project_id}/changes")
    def get_changes(project_id: str):
        return store.get(project_id).changes()

    @app.get("/api/projects/{project_id}/image")
    def get_image(project_id: str, kind: str, ref: str):
        project = store.get(project_id)
        with project.lock:
            return FileResponse(project.image_path(kind, ref))

    def operate(project_id: str, operation: str, payload: dict):
        project = store.get(project_id)
        data = payload["data"]
        revision = payload.get("revision")
        assets = payload.get("asset_revision")
        if operation == "save":
            return project.save(data, revision)
        if operation == "preview":
            return project.preview(data, payload["source"])
        if operation == "apply":
            return project.apply(data, revision, payload["source"], assets)
        if operation == "prepare":
            return project.prepare(data, revision, assets)
        if operation == "migrate":
            return project.migrate(data, revision, assets)
        if operation == "upload":
            try:
                content = base64.b64decode(payload["content"], validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError("Invalid image upload") from error
            return project.upload(payload["kind"], payload["filename"], content, data, revision, assets)
        if operation == "export":
            content, filename, media_type = project.export(data, payload.get("options", {}))
            return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
        raise FileNotFoundError("Unknown project operation")

    @app.post("/api/projects/{project_id}/{operation}")
    def project_operation(project_id: str, operation: str, payload: dict = Body(...)):
        return operate(project_id, operation, payload)

    # Explicit --config keeps the original single-project API available. There
    # is no mutable server-wide active project, even when several tabs are open.
    def initial_id():
        if store.initial_id is None:
            raise ValueError("Select a project using /api/projects first")
        return store.initial_id

    @app.get("/api/project")
    def legacy_project():
        return snapshot(initial_id())

    @app.get("/api/image")
    def legacy_image(kind: str, ref: str):
        return get_image(initial_id(), kind, ref)

    @app.post("/api/{operation}")
    def legacy_operation(operation: str, payload: dict = Body(...)):
        return operate(initial_id(), operation, payload)

    app.mount("/static", StaticFiles(directory=web_root), name="static")
    return app
