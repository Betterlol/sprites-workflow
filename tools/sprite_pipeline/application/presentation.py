"""Legacy response representation shared by HTTP and projects CLI.

URL construction lives at the response boundary, never in domain/image rules.
These helpers preserve the existing public snapshot and preview wire format.
"""
import base64
from pathlib import Path
from urllib.parse import quote, urlencode
from PIL import Image
from sprite_pipeline.imaging.png import png_bytes

def data_url(image: Image.Image) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes(image)).decode("ascii")

def image_url(kind: str, reference: str, path: Path, project_id: str | None = None) -> str:
    stat = path.stat()
    route = f"/api/projects/{quote(project_id, safe='')}/image" if project_id is not None else "/api/image"
    return route + "?" + urlencode({"kind": kind, "ref": reference, "v": f"{stat.st_mtime_ns}-{stat.st_size}"})
