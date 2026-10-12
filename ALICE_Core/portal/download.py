from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import config

router = APIRouter()


@router.get("/download/{filename}")
def download(filename: str):
    path = Path(config.DIR_SHARE) / filename
    if not path.exists():
        raise HTTPException(status_code=404,detail="File not found.")

    return FileResponse(path=str(path), filename=filename, media_type="application/octet-stream")