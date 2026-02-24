from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date, time

from db.database import get_db
from db.models import EstacaoAmostral, BuscaAtiva, VideoTransecto, Fotoquadrado
from services.azure_blob_service import AzureBlobService

try:
    blob_service = AzureBlobService()
except Exception:
    blob_service = None

def get_url(url: Optional[str]) -> Optional[str]:
    return blob_service.get_sas_url(url) if blob_service and url else url

router = APIRouter(prefix="/api", tags=["estacoes"])

# --- Schemas ---

# --- Schemas ---

import json

def parse_json_field(value: Optional[str]):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"text": value}

# --- Schemas ---

class EstacaoCreate(BaseModel):
    campanha_id: int
    espaco_amostral_id: Optional[int] = None
    numero: Optional[int] = None
    data: Optional[date] = None
    hora: Optional[time] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    observacoes: Optional[str] = None

class BuscaAtivaCreate(BaseModel):
    estacao_amostral_id: int
    numero_busca: Optional[int] = None
    data: Optional[date] = None
    hora_inicio: Optional[time] = None
    duracao: Optional[str] = None # HH:MM:SS format
    profundidade_inicial: Optional[float] = None
    profundidade_final: Optional[float] = None
    temperatura_inicial: Optional[float] = None
    temperatura_final: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    encontrou_coral_sol: bool = False
    planilha_excel_url: Optional[str] = None
    arquivo_percurso_url: Optional[str] = None
    dados_meteo: Optional[str] = None # JSON string or text

class VideoTransectoCreate(BaseModel):
    estacao_amostral_id: int
    data: Optional[date] = None
    hora: Optional[time] = None
    profundidade_inicial: Optional[float] = None
    profundidade_final: Optional[float] = None
    temperatura_inicial: Optional[float] = None
    temperatura_final: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    video_url: Optional[str] = None
    dados_meteo: Optional[str] = None
    riqueza_especifica: Optional[float] = None
    diversidade_shannon: Optional[float] = None
    equitabilidade_jaccard: Optional[float] = None

class FotoquadradoCreate(BaseModel):
    estacao_amostral_id: int
    data: Optional[date] = None
    hora: Optional[time] = None
    profundidade: Optional[float] = None
    temperatura: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    imagem_mosaico_url: Optional[str] = None
    imagens_complementares: Optional[str] = None # JSON array string
    dados_meteo: Optional[str] = None
    riqueza_especifica: Optional[float] = None
    diversidade_shannon: Optional[float] = None
    equitabilidade_jaccard: Optional[float] = None

# --- Estações Amostrais ---

@router.get("/campanhas/{campanha_id}/estacoes")
async def get_estacoes(campanha_id: int, db: Session = Depends(get_db)):
    """Get all sampling stations for a campaign"""
    estacoes = db.query(EstacaoAmostral).filter(
        EstacaoAmostral.campanha_id == campanha_id,
        EstacaoAmostral.deleted_at == None
    ).all()
    
    result = []
    for e in estacoes:
        result.append({
            "id": e.id,
            "espaco_amostral_id": e.espaco_amostral_id,
            "numero": e.numero,
            "data": e.data.isoformat() if e.data else None,
            "hora": e.hora.isoformat() if e.hora else None,
            "observacoes": e.observacoes,
            "num_buscas": len([b for b in e.buscas_ativas if not b.deleted_at]),
            "num_videos": len([v for v in e.video_transectos if not v.deleted_at]),
            "num_fotos": len([f for f in e.fotoquadrados if not f.deleted_at])
        })
    return result

@router.get("/campanhas/{campanha_id}/metodos")
async def get_campanha_metodos(campanha_id: int, db: Session = Depends(get_db)):
    """Get all methods (active search, video, photo) for a campaign"""
    # Fetch all stations for this campaign
    estacoes = db.query(EstacaoAmostral).filter(
        EstacaoAmostral.campanha_id == campanha_id,
        EstacaoAmostral.deleted_at == None
    ).all()
    
    buscas = []
    videos = []
    fotos = []
    
    for e in estacoes:
        # Busca Ativa
        for b in e.buscas_ativas:
            if not b.deleted_at:
                buscas.append({
                    "id": b.id,
                    "numero_busca": b.numero_busca,
                    "data": b.data.isoformat() if b.data else None,
                    "encontrou_coral_sol": b.encontrou_coral_sol,
                    "estacao_id": e.id
                })
        
        # Vídeo Transecto
        for v in e.video_transectos:
            if not v.deleted_at:
                videos.append({
                    "id": v.id,
                    "data": v.data.isoformat() if v.data else None,
                    "video_url": get_url(v.video_url),
                    "estacao_id": e.id
                })
        
        # Foto Quadrado
        for f in e.fotoquadrados:
            if not f.deleted_at:
                fotos.append({
                    "id": f.id,
                    "data": f.data.isoformat() if f.data else None,
                    "imagem_mosaico_url": get_url(f.imagem_mosaico_url),
                    "estacao_id": e.id
                })
                
    return {
        "buscas": buscas,
        "videos": videos,
        "fotos": fotos
    }

@router.post("/estacoes")
async def create_estacao(estacao: EstacaoCreate, db: Session = Depends(get_db)):
    """Create a new sampling station"""
    new_estacao = EstacaoAmostral(
        campanha_id=estacao.campanha_id,
        espaco_amostral_id=estacao.espaco_amostral_id,
        numero=estacao.numero,
        data=estacao.data,
        hora=estacao.hora,
        observacoes=estacao.observacoes
    )
    
    if estacao.lat and estacao.lon:
        from geoalchemy2.elements import WKTElement
        new_estacao.localizacao = WKTElement(f"POINT({estacao.lon} {estacao.lat})", srid=4326)
    
    db.add(new_estacao)
    db.commit()
    db.refresh(new_estacao)
    return {"success": True, "id": new_estacao.id}

# --- Busca Ativa ---

@router.get("/estacoes/{estacao_id}/buscas-ativas")
async def get_buscas_ativas(estacao_id: int, db: Session = Depends(get_db)):
    """Get all active searches for a station"""
    buscas = db.query(BuscaAtiva).filter(
        BuscaAtiva.estacao_amostral_id == estacao_id,
        BuscaAtiva.deleted_at == None
    ).all()
    
    result = []
    for b in buscas:
        result.append({
            "id": b.id,
            "numero_busca": b.numero_busca,
            "data": b.data.isoformat() if b.data else None,
            "encontrou_coral_sol": b.encontrou_coral_sol,
            "profundidade_inicial": float(b.profundidade_inicial) if b.profundidade_inicial else None,
            "profundidade_final": float(b.profundidade_final) if b.profundidade_final else None
        })
    return result

@router.post("/buscas-ativas")
async def create_busca_ativa(busca: BuscaAtivaCreate, db: Session = Depends(get_db)):
    """Create a new active search"""
    new_busca = BuscaAtiva(
        estacao_amostral_id=busca.estacao_amostral_id,
        numero_busca=busca.numero_busca,
        data=busca.data,
        hora_inicio=busca.hora_inicio,
        duracao=busca.duracao, # Assuming string for now, SQLAlchemy parses intervals often 
        profundidade_inicial=busca.profundidade_inicial,
        profundidade_final=busca.profundidade_final,
        temperatura_inicial=busca.temperatura_inicial,
        temperatura_final=busca.temperatura_final,
        visibilidade_vertical=busca.visibilidade_vertical,
        visibilidade_horizontal=busca.visibilidade_horizontal,
        encontrou_coral_sol=busca.encontrou_coral_sol,
        planilha_excel_url=busca.planilha_excel_url,
        arquivo_percurso_url=busca.arquivo_percurso_url,
        dados_meteo=parse_json_field(busca.dados_meteo)
    )
    
    db.add(new_busca)
    db.commit()
    db.refresh(new_busca)
    return {"success": True, "id": new_busca.id}

# --- Vídeo Transecto ---

@router.get("/estacoes/{estacao_id}/video-transectos")
async def get_video_transectos(estacao_id: int, db: Session = Depends(get_db)):
    """Get all video transects for a station"""
    videos = db.query(VideoTransecto).filter(
        VideoTransecto.estacao_amostral_id == estacao_id,
        VideoTransecto.deleted_at == None
    ).all()
    
    result = []
    for v in videos:
        result.append({
            "id": v.id,
            "data": v.data.isoformat() if v.data else None,
            "video_url": get_url(v.video_url),
            "profundidade_inicial": float(v.profundidade_inicial) if v.profundidade_inicial else None,
            "profundidade_final": float(v.profundidade_final) if v.profundidade_final else None
        })
    return result

@router.post("/video-transectos")
async def create_video_transecto(video: VideoTransectoCreate, db: Session = Depends(get_db)):
    """Create a new video transect"""
    new_video = VideoTransecto(
        estacao_amostral_id=video.estacao_amostral_id,
        data=video.data,
        hora=video.hora,
        profundidade_inicial=video.profundidade_inicial,
        profundidade_final=video.profundidade_final,
        temperatura_inicial=video.temperatura_inicial,
        temperatura_final=video.temperatura_final,
        visibilidade_horizontal=video.visibilidade_horizontal,
        visibilidade_vertical=video.visibilidade_vertical,
        video_url=video.video_url,
        dados_meteo=parse_json_field(video.dados_meteo),
        riqueza_especifica=video.riqueza_especifica,
        diversidade_shannon=video.diversidade_shannon,
        equitabilidade_jaccard=video.equitabilidade_jaccard
    )
    
    db.add(new_video)
    db.commit()
    db.refresh(new_video)
    return {"success": True, "id": new_video.id}

# --- Foto Quadrado ---

@router.get("/estacoes/{estacao_id}/fotoquadrados")
async def get_fotoquadrados(estacao_id: int, db: Session = Depends(get_db)):
    """Get all photo quadrats for a station"""
    fotos = db.query(Fotoquadrado).filter(
        Fotoquadrado.estacao_amostral_id == estacao_id,
        Fotoquadrado.deleted_at == None
    ).all()
    
    result = []
    for f in fotos:
        result.append({
            "id": f.id,
            "data": f.data.isoformat() if f.data else None,
            "imagem_mosaico_url": get_url(f.imagem_mosaico_url),
            "profundidade": float(f.profundidade) if f.profundidade else None,
            "temperatura": float(f.temperatura) if f.temperatura else None
        })
    return result

@router.post("/fotoquadrados")
async def create_fotoquadrado(foto: FotoquadradoCreate, db: Session = Depends(get_db)):
    """Create a new photo quadrat"""
    new_foto = Fotoquadrado(
        estacao_amostral_id=foto.estacao_amostral_id,
        data=foto.data,
        hora=foto.hora,
        profundidade=foto.profundidade,
        temperatura=foto.temperatura,
        visibilidade_vertical=foto.visibilidade_vertical,
        visibilidade_horizontal=foto.visibilidade_horizontal,
        imagem_mosaico_url=foto.imagem_mosaico_url,
        imagens_complementares=parse_json_field(foto.imagens_complementares),
        dados_meteo=parse_json_field(foto.dados_meteo),
        riqueza_especifica=foto.riqueza_especifica,
        diversidade_shannon=foto.diversidade_shannon,
        equitabilidade_jaccard=foto.equitabilidade_jaccard
    )
    
    db.add(new_foto)
    db.commit()
    db.refresh(new_foto)
    return {"success": True, "id": new_foto.id}
