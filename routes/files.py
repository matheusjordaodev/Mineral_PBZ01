"""
File Routes - API endpoints for serving static files
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from services import FileService


# Configuration
UPLOAD_DIR = Path("app/uploads")

# Services
file_service = FileService(UPLOAD_DIR)

# Router
router = APIRouter(tags=["files"])


# Media type mapping
MEDIA_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.mp4': 'video/mp4',
    '.mov': 'video/quicktime',
    '.avi': 'video/x-msvideo',
    '.kml': 'application/vnd.google-earth.kml+xml',
    '.kmz': 'application/vnd.google-earth.kmz',
    '.geojson': 'application/geo+json',
    '.json': 'application/json'
}


@router.get("/uploads/{ilha_id}/{campanha_id}/{tipo}/{filename:path}")
async def serve_file(ilha_id: str, campanha_id: str, tipo: str, filename: str):
    """Serve arquivos de mídia e geoespaciais"""
    
    try:
        file_path = file_service.get_file_path(ilha_id, campanha_id, tipo, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if file_path is None:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    # Detect media type
    media_type = MEDIA_TYPES.get(file_path.suffix.lower(), 'application/octet-stream')
    
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename
    )
