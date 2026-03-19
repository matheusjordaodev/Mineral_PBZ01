from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel as PydanticBase
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, contains_eager

from db.database import get_db
from db.models import Campanha, Documento, Ilha, Usuario
from routes.auth import get_current_active_user
from services.azure_blob_service import AzureBlobService
from services.file_service import FileService

UPLOAD_DIR = Path("app/uploads")
_file_service = FileService(UPLOAD_DIR)

try:
    blob_service = AzureBlobService()
except Exception:
    blob_service = None


def get_url(url: Optional[str]) -> Optional[str]:
    return blob_service.get_sas_url(url) if blob_service and url else url


router = APIRouter(prefix="/api", tags=["documentos"])


@router.get("/documentos")
async def get_documentos(ilha_id: Optional[int] = None, db: Session = Depends(get_db)):
    # Join explícito para filtragem; contains_eager popula o relacionamento campanha
    # sem queries adicionais por documento
    query = (
        db.query(Documento)
        .join(Campanha, Documento.campanha_id == Campanha.id)
        .outerjoin(Campanha.ilhas)
        .options(
            contains_eager(Documento.campanha).contains_eager(Campanha.ilhas)
        )
        .filter(
            Documento.deleted_at.is_(None),
            Campanha.deleted_at.is_(None),
        )
    )

    if ilha_id:
        query = query.filter(or_(Campanha.ilha_id == ilha_id, Ilha.id == ilha_id))

    docs = query.order_by(desc(Documento.data_upload)).distinct().all()

    # Coleta ilha_ids legados (campanha.ilha_id sem relação M:N) e carrega em bulk
    legacy_ilha_ids = {
        doc.campanha.ilha_id
        for doc in docs
        if doc.campanha and doc.campanha.ilha_id and not doc.campanha.ilhas
    }
    legacy_ilhas: dict = {}
    if legacy_ilha_ids:
        rows = db.query(Ilha.id, Ilha.nome).filter(Ilha.id.in_(legacy_ilha_ids)).all()
        legacy_ilhas = {r[0]: r[1] for r in rows}

    result = []
    for doc in docs:
        campanha = doc.campanha
        ilha_names = []
        if campanha:
            ilha_names.extend([i.nome for i in (campanha.ilhas or []) if i.nome])
        if not ilha_names and campanha and campanha.ilha_id:
            nome = legacy_ilhas.get(campanha.ilha_id)
            if nome:
                ilha_names.append(nome)

        result.append(
            {
                "id": doc.id,
                "titulo": doc.titulo,
                "url": get_url(doc.url),
                "tipo": doc.tipo,
                "data": doc.data_upload.isoformat() if doc.data_upload else None,
                "campanha": campanha.nome if campanha else None,
                "ilha": ", ".join(ilha_names) if ilha_names else None,
            }
        )

    return result


@router.get("/documentos/campanha/{campanha_id}")
async def get_documentos_campanha(campanha_id: int, db: Session = Depends(get_db)):
    """Lista documentos vinculados a uma campanha específica."""
    docs = (
        db.query(Documento)
        .filter(Documento.campanha_id == campanha_id, Documento.deleted_at.is_(None))
        .order_by(desc(Documento.data_upload))
        .all()
    )
    return [
        {
            "id": doc.id,
            "titulo": doc.titulo,
            "url": get_url(doc.url),
            "tipo": doc.tipo,
            "data": doc.data_upload.isoformat() if doc.data_upload else None,
        }
        for doc in docs
    ]


@router.post("/documentos/campanha/{campanha_id}")
async def upload_documento_campanha(
    campanha_id: int,
    titulo: str,
    tipo: Optional[str] = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    """Faz upload de um documento e vincula à campanha."""
    campanha = db.query(Campanha).filter(Campanha.id == campanha_id, Campanha.deleted_at.is_(None)).first()
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    # Salva o arquivo localmente em app/uploads/documentos/{campanha_id}/
    doc_dir = UPLOAD_DIR / "documentos" / str(campanha_id)
    doc_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = file.filename.replace(" ", "_") if file.filename else "documento"
    dest = doc_dir / safe_filename
    content = await file.read()
    dest.write_bytes(content)

    relative_url = f"/uploads/documentos/{campanha_id}/{safe_filename}"

    doc = Documento(
        campanha_id=campanha_id,
        titulo=titulo,
        url=relative_url,
        tipo=tipo or "outro",
        data_upload=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "titulo": doc.titulo,
        "url": get_url(doc.url) or doc.url,
        "tipo": doc.tipo,
        "data": doc.data_upload.isoformat(),
    }


@router.delete("/documentos/{documento_id}")
async def delete_documento(
    documento_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    """Remove (soft-delete) um documento."""
    from datetime import datetime as _dt
    doc = db.query(Documento).filter(Documento.id == documento_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    doc.deleted_at = _dt.utcnow()
    db.commit()
    return {"ok": True}
