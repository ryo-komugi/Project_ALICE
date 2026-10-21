"""Public Rabbit-Hole home page and navigator directory."""
import json
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["Rabbit-Hole Home"])
NAVIGATORS_DIR = Path(__file__).resolve().parents[2] / "ALICE_Navigators"
HOME_PAGE = NAVIGATORS_DIR / "Home" / "index.html"
FOREST_PREVIEW_PAGE = NAVIGATORS_DIR / "Home" / "forest_preview.html"
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
LOCAL_PATH_PATTERN = re.compile(r"^/(?!/)[A-Za-z0-9_./-]{1,240}$")


@router.get("/home", include_in_schema=False)
@router.get("/home/", include_in_schema=False)
async def rabbit_hole_home():
    return FileResponse(
        HOME_PAGE,
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        },
    )


@router.get("/home/forest-preview", include_in_schema=False)
async def forest_animation_preview():
    """Standalone preview of the proposed forest passage animation."""
    return FileResponse(
        FOREST_PREVIEW_PAGE,
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        },
    )


@router.get("/home/api/navigators", include_in_schema=False)
async def list_navigators():
    navigators = []
    if not NAVIGATORS_DIR.is_dir():
        return {"navigators": navigators}

    for directory in NAVIGATORS_DIR.iterdir():
        if not directory.is_dir():
            continue
        slug = directory.name.casefold()
        if not SLUG_PATTERN.fullmatch(slug):
            continue
        manifest_path = directory / "navigator.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(manifest, dict):
            continue
        name = manifest.get("name")
        description = manifest.get("description")
        path = manifest.get("path")
        image = manifest.get("image", "")
        order = manifest.get("order", 1000)
        if not all(isinstance(value, str) for value in (name, description, path, image)):
            continue
        if not isinstance(order, int):
            continue
        if not name.strip() or not LOCAL_PATH_PATTERN.fullmatch(path) or ".." in path.split("/"):
            continue
        if image and (not LOCAL_PATH_PATTERN.fullmatch(image) or ".." in image.split("/")):
            continue
        navigators.append({
            "id": slug,
            "name": name[:80],
            "description": description[:240],
            "path": path,
            "image": image,
            "order": order,
        })
    navigators.sort(key=lambda navigator: (navigator["order"], navigator["name"].casefold()))
    return {"navigators": navigators}
