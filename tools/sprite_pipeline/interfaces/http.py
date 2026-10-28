"""Same-origin, loopback-only HTTP interface for the local workbench."""

from __future__ import annotations

import base64
import binascii
import mimetypes
import secrets
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from sprite_pipeline.domain.errors import ConflictError
from sprite_pipeline.storage.locking import ProjectBusyError
from sprite_pipeline.application.jobs import ExportJobs
from sprite_pipeline.application.projects import DEFAULT_WORKSPACES, EXTERNAL_ID, ProjectStore


def create_app(config_path: Path | None = None, workspace_root: Path | None = None) -> FastAPI:
    store = ProjectStore(workspace_root or DEFAULT_WORKSPACES, config_path)
    jobs = ExportJobs()
    token = secrets.token_urlsafe(32)
    web_root = Path(__file__).resolve().parents[1] / "web"
    app = FastAPI(title="Sprite Workbench", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.projects = store
    app.state.export_jobs = jobs
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
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = ("private, no-cache" if request.url.path.startswith("/static/")
                                                 else "no-store")
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
        project = store.get(project_id)
        state = project.state()
        data = state["data"]
        description = {"id": project_id, "name": data.get("project", {}).get("name") or data["character"],
                       "character": data["character"], "frame_size": data["frame_size"],
                       "directory": str(project.path.parent), "config": str(project.path),
                       "external": project_id == EXTERNAL_ID}
        return {**state, "project": description, "token": token}

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        return snapshot(project_id)

    @app.get("/api/projects/{project_id}/changes")
    def get_changes(project_id: str):
        return store.get(project_id).changes()

    @app.get("/api/projects/{project_id}/history")
    def get_history(project_id: str):
        return {"versions": store.get(project_id).history_entries()}

    @app.get("/api/projects/{project_id}/image")
    def get_image(project_id: str, kind: str, ref: str, v: str | None = None):
        project = store.image_project(project_id)
        with project.lock:
            path = project.image_path(kind, ref)
            before = path.stat()
            content = path.read_bytes()
            after = path.stat()
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise ConflictError("图片在读取时发生变化，请重试。")
            current_version = f"{after.st_mtime_ns}-{after.st_size}"
            cache_control = "private, max-age=31536000, immutable" if v == current_version else "no-store"
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return Response(content, media_type=media_type, headers={"Cache-Control": cache_control})

    @app.post("/api/projects/{project_id}/jobs/export")
    def start_export_job(project_id: str, payload: dict = Body(...)):
        return jobs.start(project_id, store.get(project_id), payload["data"], payload.get("options", {}),
                          payload.get("revision"), payload.get("asset_revision"))

    @app.post("/api/projects/{project_id}/jobs/prepare")
    def start_prepare_job(project_id: str, payload: dict = Body(...)):
        return jobs.start_prepare(project_id, store.get(project_id), payload["data"],
                                  payload.get("revision"), payload.get("asset_revision"))

    @app.get("/api/projects/{project_id}/jobs/{job_id}")
    def get_export_job(project_id: str, job_id: str):
        return jobs.status(project_id, job_id)

    @app.post("/api/projects/{project_id}/jobs/{job_id}/cancel")
    def cancel_export_job(project_id: str, job_id: str):
        return jobs.cancel(project_id, job_id)

    @app.get("/api/projects/{project_id}/jobs/{job_id}/download")
    def download_export_job(project_id: str, job_id: str):
        content, filename, media_type = jobs.download(project_id, job_id)
        return Response(content, media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    def operate(project_id: str, operation: str, payload: dict):
        project = store.get(project_id)
        if operation == 'save-slices':
            return project.save_slices(payload['source'], payload['extract'], payload.get('revision'), payload.get('asset_revision'))
        if operation == "restore":
            return project.restore(payload["version"], payload.get("revision"), payload.get("asset_revision"))
        data = payload["data"]
        revision = payload.get("revision")
        assets = payload.get("asset_revision")
        if operation == "save":
            return project.save(data, revision)
        if operation == "preview":
            return project.preview(data, payload["source"], payload.get("stage", "process"), payload.get('known'))
        if operation == "apply":
            return project.apply(data, revision, payload["source"], assets)
        if operation == "prepare":
            return project.prepare(data, revision, assets)
        if operation == "migrate":
            return project.migrate(data, revision, assets)
        if operation == "delete":
            return project.delete(payload["kind"], payload["references"], data, revision, assets)
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
    def legacy_image(kind: str, ref: str, v: str | None = None):
        return get_image(initial_id(), kind, ref, v)

    @app.post("/api/{operation}")
    def legacy_operation(operation: str, payload: dict = Body(...)):
        return operate(initial_id(), operation, payload)

    app.mount("/static", StaticFiles(directory=web_root), name="static")
    return app
