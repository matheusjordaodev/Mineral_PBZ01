from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from db.database import get_db
from db.models import BuscaAtiva, VideoTransecto, Fotoquadrado, ProtocoloDAFOR, Campanha
from services.azure_blob_service import AzureBlobService

try:
    blob_service = AzureBlobService()
except Exception:
    blob_service = None

def get_url(url: Optional[str]) -> Optional[str]:
    return blob_service.get_sas_url(url) if blob_service and url else url

router = APIRouter()

# --- Pydantic Schemas (Simplified) ---

class BuscaAtivaCreate(BaseModel):
    campanha_id: int
    data_hora_inicio: Optional[datetime] = None
    data_hora_fim: Optional[datetime] = None
    encontrou_coral_sol: bool = False
    observacoes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    imagens: List[str] = []
    detalhes_coral: Optional[dict] = None
    planilha_excel_url: Optional[str] = None
    arquivo_percurso_url: Optional[str] = None

class VideoTransectoCreate(BaseModel):
    campanha_id: int
    nome_video: str
    observacoes: Optional[str] = None

# --- Endpoints ---

@router.get("/api/campanhas/{campanha_id}/busca-ativa")
def get_busca_ativa(campanha_id: int, db: Session = Depends(get_db)):
    # Join with EstacaoAmostral to filter by Campanha
    from db.models import EstacaoAmostral
    items = db.query(BuscaAtiva).join(EstacaoAmostral).filter(EstacaoAmostral.campanha_id == campanha_id).all()
    result = []
    for item in items:
        d = item.to_dict()
        d['planilha_excel_url'] = get_url(d.get('planilha_excel_url'))
        d['arquivo_percurso_url'] = get_url(d.get('arquivo_percurso_url'))
        d['imagens'] = [get_url(i) for i in (d.get('imagens') or [])]
        result.append(d)
    return result

@router.post("/api/campanhas/{campanha_id}/busca-ativa")
def create_busca_ativa(campanha_id: int, item: BuscaAtivaCreate, db: Session = Depends(get_db)):
    # Find implicit EstacaoAmostral
    from db.models import EstacaoAmostral, ProtocoloDAFOR
    estacao = db.query(EstacaoAmostral).filter(EstacaoAmostral.campanha_id == campanha_id).first()
    
    if not estacao:
        estacao = EstacaoAmostral(campanha_id=campanha_id, numero=1)
        db.add(estacao)
        db.commit()
        db.refresh(estacao)
    
    # Calculate duration if possible
    duration = None
    if item.data_hora_inicio and item.data_hora_fim:
        duration = item.data_hora_fim - item.data_hora_inicio

    # Determine data/hora
    data_reg = item.data_hora_inicio.date() if item.data_hora_inicio else datetime.now().date()
    hora_reg = item.data_hora_inicio.time() if item.data_hora_inicio else None

    # Determine count
    count = db.query(BuscaAtiva).filter(BuscaAtiva.estacao_amostral_id == estacao.id).count() + 1
    
    db_item = BuscaAtiva(
        estacao_amostral_id=estacao.id,
        numero_busca=count,
        data=data_reg,
        hora_inicio=hora_reg,
        duracao=duration,
        encontrou_coral_sol=item.encontrou_coral_sol,
        imagens=item.imagens,
        planilha_excel_url=item.planilha_excel_url,
        arquivo_percurso_url=item.arquivo_percurso_url,
        # Trilha/Location would need GeoAlchemy object creation from lat/lon, skipped for simplicity now or stored in meteo
        dados_meteo={"observacoes": item.observacoes, "lat": item.latitude, "lon": item.longitude} 
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    # Handle Coral Sol Details (Protocolo DAFOR)
    if item.encontrou_coral_sol and item.detalhes_coral:
        details = item.detalhes_coral
        # Safely extract
        try:
            dafor = ProtocoloDAFOR(
                busca_ativa_id=db_item.id,
                data=datetime.strptime(details.get('data'), "%Y-%m-%d").date() if details.get('data') else data_reg,
                hora=datetime.strptime(details.get('hora'), "%H:%M").time() if details.get('hora') else hora_reg,
                temperatura_inicial=details.get('temp_inicial'),
                temperatura_final=details.get('temp_final'),
                profundidade_inicial=details.get('prof_inicial'),
                profundidade_final=details.get('prof_final'),
                iar=details.get('iar'),
                abundancia=details.get('abundancia'), # Schema might not have this yet
                detalhes=details # Store full blob just in case
            )
            db.add(dafor)
            db.commit()
        except Exception as e:
            print(f"Error saving DAFOR: {e}")
            # Don't fail the whole request?
            pass

    return db_item.to_dict()

@router.get("/api/campanhas/{campanha_id}/video-transectos")
def get_video_transectos(campanha_id: int, db: Session = Depends(get_db)):
    items = db.query(VideoTransecto).filter(VideoTransecto.campanha_id == campanha_id).all()
    result = []
    for item in items:
        d = item.to_dict()
        d['video_url'] = get_url(d.get('video_url'))
        result.append(d)
    return result

@router.post("/api/campanhas/{campanha_id}/video-transectos")
def create_video_transecto(campanha_id: int, item: VideoTransectoCreate, db: Session = Depends(get_db)):
    db_item = VideoTransecto(
        campanha_id=campanha_id,
        nome_video=item.nome_video,
        observacoes=item.observacoes
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item.to_dict()

# Placeholder for future expansion
@router.get("/api/campanhas/{campanha_id}/fotoquadrados")
def get_fotoquadrados(campanha_id: int, db: Session = Depends(get_db)):
    items = db.query(Fotoquadrado).filter(Fotoquadrado.campanha_id == campanha_id).all()
    result = []
    for item in items:
        d = item.to_dict()
        d['imagem_mosaico_url'] = get_url(d.get('imagem_mosaico_url'))
        # If there are complementares, might need to map them too if returned
        result.append(d)
    return result
