"""
File Service - Business logic for file operations
"""

import os as _os
import re
import shutil
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from services.azure_blob_service import AzureBlobService
from utils.kml_parser import parse_kml_file

GEOSPATIAL_EXTENSIONS = {".kml", ".kmz", ".geojson", ".json", ".shp", ".zip"}
MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".avi", ".webm"}
EXCEL_EXTENSIONS = {".xls", ".xlsx", ".csv", ".ods"}
MEDIA_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".kml": "application/vnd.google-earth.kml+xml",
    ".kmz": "application/vnd.google-earth.kmz",
    ".geojson": "application/geo+json",
    ".json": "application/json",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".zip": "application/zip",
    ".shp": "application/octet-stream",
}


def _folder_for_ext(ext: str) -> str:
    if ext in GEOSPATIAL_EXTENSIONS:
        return "kml"
    if ext in EXCEL_EXTENSIONS:
        return "excel"
    if ext in {".mp4", ".mov", ".avi", ".webm"}:
        return "videos"
    return "images"


def _allowed_typed_extensions() -> set[str]:
    return GEOSPATIAL_EXTENSIONS | EXCEL_EXTENSIONS | MEDIA_EXTENSIONS


def _sanitize_filename_stem(filename: str) -> str:
    stem = Path(filename or "").stem
    normalized = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._-")
    return sanitized or "arquivo"


MAX_GEOSPATIAL_MB = float(_os.getenv("MAX_GEOSPATIAL_FILE_MB", "50"))


class FileService:
    """Service for file-related operations"""

    def __init__(self, upload_dir: Path):
        self.upload_dir = upload_dir
        try:
            self.azure_service = AzureBlobService()
        except Exception as e:
            print(f"Warning: Azure Blob Service could not be initialized. {e}")
            self.azure_service = None

    def save_geospatial_file(self, ilha_id: str, campanha_id: str, file_data, filename: str) -> Dict[str, Any]:
        """Save geospatial file locally (for parsing) and optionally to Azure."""
        file_ext = Path(filename).suffix.lower()

        if file_ext not in GEOSPATIAL_EXTENSIONS:
            raise ValueError(f"Tipo de arquivo nao permitido. Use: {', '.join(GEOSPATIAL_EXTENSIONS)}")

        geospatial_dir = self.upload_dir / ilha_id / campanha_id / "geospatial"
        geospatial_dir.mkdir(exist_ok=True, parents=True)

        file_path = geospatial_dir / filename

        if hasattr(file_data, "seek"):
            file_data.seek(0)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file_data, buffer)

        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_GEOSPATIAL_MB:
            file_path.unlink(missing_ok=True)
            raise ValueError(
                f"Arquivo muito grande ({file_size_mb:.1f} MB). "
                f"Tamanho maximo permitido: {MAX_GEOSPATIAL_MB:.0f} MB"
            )

        if file_ext == ".kmz":
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    kml_files = [name for name in zf.namelist() if name.lower().endswith(".kml")]
                    if kml_files:
                        zf.extract(kml_files[0], geospatial_dir)
            except Exception as e:
                raise Exception(f"Erro ao extrair KMZ: {str(e)}")

        azure_url = None
        if self.azure_service:
            try:
                if hasattr(file_data, "seek"):
                    file_data.seek(0)
                import uuid

                file_path_obj = Path(filename)
                unique_filename = (
                    f"{_sanitize_filename_stem(filename)}_{uuid.uuid4().hex[:8]}{file_path_obj.suffix.lower()}"
                )
                blob_name = f"{ilha_id}/{campanha_id}/geospatial/{unique_filename}"
                azure_url = self.azure_service.upload_file(file_data, blob_name)
            except Exception as e:
                print(f"Failed to upload geospatial to Azure: {e}")

        return {
            "filename": filename,
            "size": file_path.stat().st_size,
            "path": str(file_path),
            "url": azure_url,
        }

    def save_typed_file(self, ilha_id: str, campanha_id: str, file_data, filename: str) -> Dict[str, Any]:
        """
        Save one file using a type-specific subfolder.
        Falls back to local storage when Azure is unavailable or the upload fails.
        """
        import uuid as _uuid

        file_path_obj = Path(filename)
        file_ext = file_path_obj.suffix.lower()
        if file_ext not in _allowed_typed_extensions():
            raise ValueError(
                "Tipo de arquivo nao permitido. Use: "
                + ", ".join(sorted(_allowed_typed_extensions()))
            )

        folder = _folder_for_ext(file_ext)
        safe_stem = _sanitize_filename_stem(filename)
        unique_filename = f"{safe_stem}_{_uuid.uuid4().hex[:8]}{file_ext}"
        blob_name = f"{ilha_id}/{campanha_id}/{folder}/{unique_filename}"
        content_type = MEDIA_CONTENT_TYPES.get(file_ext)

        if self.azure_service:
            try:
                if hasattr(file_data, "seek"):
                    file_data.seek(0)
                file_url = self.azure_service.upload_file(file_data, blob_name, content_type=content_type)
                return {"url": file_url, "folder": folder, "filename": unique_filename}
            except Exception as exc:
                print(f"Error uploading typed file to Azure ({filename}): {exc}. Falling back to local storage.")

        return self._save_local_typed_file(
            ilha_id=ilha_id,
            campanha_id=campanha_id,
            folder=folder,
            file_data=file_data,
            filename=unique_filename,
        )

    def save_media_files(self, ilha_id: str, campanha_id: str, files: List) -> List[Dict[str, Any]]:
        """Save multiple files using type-specific subfolders."""
        import uuid

        uploaded_files = []

        for file_data, filename in files:
            file_path_obj = Path(filename)
            file_ext = file_path_obj.suffix.lower()
            if file_ext not in _allowed_typed_extensions():
                continue

            folder = _folder_for_ext(file_ext)
            safe_stem = _sanitize_filename_stem(filename)
            unique_filename = f"{safe_stem}_{uuid.uuid4().hex[:8]}{file_ext}"
            blob_name = f"{ilha_id}/{campanha_id}/{folder}/{unique_filename}"
            content_type = MEDIA_CONTENT_TYPES.get(file_ext)
            file_size = 0

            if hasattr(file_data, "seek"):
                file_data.seek(0)
                try:
                    file_size = file_data.getbuffer().nbytes
                except Exception:
                    pass

            if self.azure_service:
                try:
                    if hasattr(file_data, "seek"):
                        file_data.seek(0)
                    file_url = self.azure_service.upload_file(file_data, blob_name, content_type=content_type)
                    uploaded_files.append({"filename": filename, "size": file_size, "url": file_url})
                    continue
                except Exception as e:
                    print(f"Error uploading {filename} to Azure: {e}. Falling back to local storage.")

            local_result = self._save_local_typed_file(
                ilha_id=ilha_id,
                campanha_id=campanha_id,
                folder=folder,
                file_data=file_data,
                filename=unique_filename,
            )
            uploaded_files.append(
                {
                    "filename": filename,
                    "size": local_result["size"],
                    "url": local_result["url"],
                }
            )

        return uploaded_files

    def _save_local_typed_file(
        self,
        ilha_id: str,
        campanha_id: str,
        folder: str,
        file_data,
        filename: str,
    ) -> Dict[str, Any]:
        target_dir = self.upload_dir / ilha_id / campanha_id / folder
        target_dir.mkdir(exist_ok=True, parents=True)
        file_path = target_dir / filename

        if hasattr(file_data, "seek"):
            file_data.seek(0)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file_data, buffer)

        return {
            "url": f"/uploads/{ilha_id}/{campanha_id}/{folder}/{quote(filename)}",
            "folder": folder,
            "filename": filename,
            "path": str(file_path),
            "size": file_path.stat().st_size,
        }

    def _list_media_blobs(self, ilha_id: str, campanha_id: str) -> List[Dict[str, Any]]:
        if not self.azure_service:
            return []

        prefix = f"{ilha_id}/{campanha_id}/media/"
        container_client = self.azure_service.blob_service_client.get_container_client(
            self.azure_service.container_name
        )

        files = []
        for blob in container_client.list_blobs(name_starts_with=prefix):
            blob_name = blob.name or ""
            filename = Path(blob_name).name
            blob_client = container_client.get_blob_client(blob_name)
            files.append(
                {
                    "nome": filename,
                    "filename": filename,
                    "tamanho": blob.size,
                    "size": blob.size,
                    "modificado": blob.last_modified.isoformat() if blob.last_modified else None,
                    "url": self.azure_service.get_sas_url(blob_client.url),
                }
            )
        return files

    def list_files(self, ilha_id: str, campanha_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """List all files in a campaign. Hybrid: local for geo, Azure for media."""
        campanha_path = self.upload_dir / ilha_id / campanha_id

        files = {"geospatial": [], "media": []}

        geospatial_dir = campanha_path / "geospatial"
        if geospatial_dir.exists():
            for file_path in geospatial_dir.glob("*"):
                if file_path.is_file() and file_path.name != "metadata.json":
                    files["geospatial"].append(
                        {
                            "nome": file_path.name,
                            "tamanho": file_path.stat().st_size,
                            "modificado": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                        }
                    )

        if self.azure_service:
            try:
                files["media"] = self._list_media_blobs(ilha_id, campanha_id)
            except Exception as exc:
                print(f"Failed to list media from Azure: {exc}")

        return files

    def get_geojson(self, ilha_id: str, campanha_id: str) -> Dict[str, Any]:
        """Get GeoJSON from all geospatial files in campaign (local)."""
        campanha_path = self.upload_dir / ilha_id / campanha_id
        geospatial_dir = campanha_path / "geospatial"

        if not geospatial_dir.exists():
            return {
                "type": "FeatureCollection",
                "features": [],
                "metadata": {"message": "Nenhum arquivo geoespacial encontrado"},
            }

        all_features = []
        metadata_list = []

        for file_path in geospatial_dir.glob("*"):
            if file_path.suffix.lower() in [".kml", ".kmz"]:
                try:
                    result = parse_kml_file(str(file_path))
                    all_features.extend(result.get("features", []))
                    metadata_list.append({"filename": file_path.name, **result.get("metadata", {})})
                except Exception as e:
                    print(f"Error parsing {file_path}: {e}")

        return {
            "type": "FeatureCollection",
            "features": all_features,
            "metadata": {
                "files": metadata_list,
                "total_features": len(all_features),
            },
        }

    def get_media_list(self, ilha_id: str, campanha_id: str) -> List[Dict[str, Any]]:
        """Get list of media files with URLs (deprecated/Azure)."""
        try:
            return self._list_media_blobs(ilha_id, campanha_id)
        except Exception as exc:
            print(f"Failed to get media list from Azure: {exc}")
            return []

    def list_media_blobs_for_campanha_ilha(self, ilha_id: str, campanha_id: str) -> List[Dict[str, Any]]:
        """List image/video blobs for one campaign/island in Azure."""
        if not self.azure_service:
            return []
        try:
            container_client = self.azure_service.blob_service_client.get_container_client(
                self.azure_service.container_name
            )
            video_exts = {".mp4", ".mov", ".avi", ".webm"}
            result = []
            for folder in ("images", "videos"):
                prefix = f"{ilha_id}/{campanha_id}/{folder}/"
                for blob in container_client.list_blobs(name_starts_with=prefix):
                    ext = Path(blob.name).suffix.lower()
                    blob_client = container_client.get_blob_client(blob.name)
                    result.append(
                        {
                            "url": self.azure_service.get_sas_url(blob_client.url),
                            "nome": Path(blob.name).name,
                            "media_type": "video" if ext in video_exts else "image",
                            "date": blob.last_modified.isoformat() if blob.last_modified else None,
                        }
                    )
            return result
        except Exception as exc:
            print(f"[list_media_blobs_for_campanha_ilha] {exc}")
            return []

    def get_file_path(self, ilha_id: str, campanha_id: str, tipo: str, filename: str) -> Optional[Path]:
        """Get a local file path for serving uploads."""
        allowed_types = {"geospatial", "media", "kml", "excel", "videos", "images"}
        if tipo not in allowed_types:
            raise ValueError("Tipo invalido. Use 'geospatial', 'media', 'kml', 'excel', 'videos' ou 'images'")

        file_path = self.upload_dir / ilha_id / campanha_id / tipo / filename
        if file_path.exists() and file_path.is_file():
            return file_path

        return None
