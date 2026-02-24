from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional

from db.database import get_db
from db.models import Documento, Campanha, Ilha
from services.azure_blob_service import AzureBlobService

try:
    blob_service = AzureBlobService()
except Exception:
    blob_service = None

def get_url(url: Optional[str]) -> Optional[str]:
    return blob_service.get_sas_url(url) if blob_service and url else url

router = APIRouter(prefix="/api", tags=["documentos"])

@router.get("/documentos")
async def get_documentos(ilha_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Lista documentos.
    Se ilha_id for fornecido, filtra documentos das campanhas dessa ilha.
    Caso contrário, retorna todos.
    """
    query = db.query(Documento).join(Campanha, Documento.campanha_id == Campanha.id).join(Ilha, Campanha.ilha_id == Ilha.id)
    
    if ilha_id:
        query = query.filter(Ilha.id == ilha_id)
    
    # Order by date desc
    docs = query.order_by(desc(Documento.data_upload)).all()
    
    result = []
    for d in docs:
        result.append({
            "id": d.id,
            "titulo": d.titulo,
            "url": get_url(d.url),
            "tipo": d.tipo,
            "data": d.data_upload.isoformat() if d.data_upload else None,
            "campanha": d.campanha.nome if d.campanha else None,
            "ilha": d.campanha.ilha.nome if d.campanha and d.campanha.ilha else None
        })
        
    return result
