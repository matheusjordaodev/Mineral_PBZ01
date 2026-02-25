from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import (
    BuscaAtiva,
    Campanha,
    EstacaoAmostral,
    Fotoquadrado,
    ProtocoloDAFOR,
    VideoTransecto,
)
from services.azure_blob_service import AzureBlobService

try:
    blob_service = AzureBlobService()
except Exception:
    blob_service = None


def get_url(url: Optional[str]) -> Optional[str]:
    return blob_service.get_sas_url(url) if blob_service and url else url


def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _serialize_dafor(item: ProtocoloDAFOR) -> dict:
    imagens = item.imagens if isinstance(item.imagens, list) else []
    return {
        "id": item.id,
        "data": item.data.isoformat() if item.data else None,
        "hora": item.hora.isoformat() if item.hora else None,
        "temperatura_inicial": _to_float(item.temperatura_inicial),
        "temperatura_final": _to_float(item.temperatura_final),
        "profundidade_inicial": _to_float(item.profundidade_inicial),
        "profundidade_final": _to_float(item.profundidade_final),
        "iar": _to_float(item.iar),
        "abundancia": item.abundancia,
        "imagens": [get_url(img) for img in imagens],
        "detalhes": item.detalhes,
    }


def _serialize_busca_ativa(item: BuscaAtiva) -> dict:
    imagens = item.imagens if isinstance(item.imagens, list) else []
    protocolos = [_serialize_dafor(p) for p in (item.protocolos_dafor or []) if not p.deleted_at]
    return {
        "id": item.id,
        "estacao_amostral_id": item.estacao_amostral_id,
        "numero_busca": item.numero_busca,
        "data": item.data.isoformat() if item.data else None,
        "hora_inicio": item.hora_inicio.isoformat() if item.hora_inicio else None,
        "duracao": str(item.duracao) if item.duracao else None,
        "profundidade_inicial": _to_float(item.profundidade_inicial),
        "profundidade_final": _to_float(item.profundidade_final),
        "temperatura_inicial": _to_float(item.temperatura_inicial),
        "temperatura_final": _to_float(item.temperatura_final),
        "visibilidade_vertical": _to_float(item.visibilidade_vertical),
        "visibilidade_horizontal": _to_float(item.visibilidade_horizontal),
        "planilha_excel_url": get_url(item.planilha_excel_url),
        "arquivo_percurso_url": get_url(item.arquivo_percurso_url),
        "dados_meteo": item.dados_meteo,
        "imagens": [get_url(img) for img in imagens],
        "encontrou_coral_sol": bool(item.encontrou_coral_sol),
        "protocolos_dafor": protocolos,
    }


def _serialize_video_transecto(item: VideoTransecto) -> dict:
    return {
        "id": item.id,
        "estacao_amostral_id": item.estacao_amostral_id,
        "data": item.data.isoformat() if item.data else None,
        "hora": item.hora.isoformat() if item.hora else None,
        "profundidade_inicial": _to_float(item.profundidade_inicial),
        "profundidade_final": _to_float(item.profundidade_final),
        "temperatura_inicial": _to_float(item.temperatura_inicial),
        "temperatura_final": _to_float(item.temperatura_final),
        "visibilidade_vertical": _to_float(item.visibilidade_vertical),
        "visibilidade_horizontal": _to_float(item.visibilidade_horizontal),
        "riqueza_especifica": _to_float(item.riqueza_especifica),
        "diversidade_shannon": _to_float(item.diversidade_shannon),
        "equitabilidade_jaccard": _to_float(item.equitabilidade_jaccard),
        "video_url": get_url(item.video_url),
        "dados_meteo": item.dados_meteo,
    }


def _serialize_fotoquadrado(item: Fotoquadrado) -> dict:
    imagens = item.imagens_complementares if isinstance(item.imagens_complementares, list) else []
    return {
        "id": item.id,
        "estacao_amostral_id": item.estacao_amostral_id,
        "data": item.data.isoformat() if item.data else None,
        "hora": item.hora.isoformat() if item.hora else None,
        "profundidade": _to_float(item.profundidade),
        "temperatura": _to_float(item.temperatura),
        "visibilidade_vertical": _to_float(item.visibilidade_vertical),
        "visibilidade_horizontal": _to_float(item.visibilidade_horizontal),
        "imagem_mosaico_url": get_url(item.imagem_mosaico_url),
        "imagens_complementares": [get_url(img) for img in imagens],
        "dados_meteo": item.dados_meteo,
        "riqueza_especifica": _to_float(item.riqueza_especifica),
        "diversidade_shannon": _to_float(item.diversidade_shannon),
        "equitabilidade_jaccard": _to_float(item.equitabilidade_jaccard),
    }


def _get_or_create_first_estacao(campanha_id: int, db: Session) -> EstacaoAmostral:
    estacao = (
        db.query(EstacaoAmostral)
        .filter(
            EstacaoAmostral.campanha_id == campanha_id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .order_by(EstacaoAmostral.id.asc())
        .first()
    )
    if estacao:
        return estacao

    estacao = EstacaoAmostral(campanha_id=campanha_id, numero=1, data=datetime.now().date())
    db.add(estacao)
    db.commit()
    db.refresh(estacao)
    return estacao


def _ensure_campanha_exists(campanha_id: int, db: Session) -> None:
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.deleted_at.is_(None))
        .first()
    )
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")


router = APIRouter()


class BuscaAtivaCreate(BaseModel):
    campanha_id: int
    data_hora_inicio: Optional[datetime] = None
    data_hora_fim: Optional[datetime] = None
    encontrou_coral_sol: bool = False
    observacoes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    imagens: List[str] = Field(default_factory=list)
    detalhes_coral: Optional[dict] = None
    planilha_excel_url: Optional[str] = None
    arquivo_percurso_url: Optional[str] = None
    dados_meteo: Optional[dict] = None
    profundidade_inicial: Optional[float] = None
    profundidade_final: Optional[float] = None
    temperatura_inicial: Optional[float] = None
    temperatura_final: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None


class VideoTransectoCreate(BaseModel):
    campanha_id: int
    nome_video: Optional[str] = None
    observacoes: Optional[str] = None
    data_hora: Optional[datetime] = None
    video_url: Optional[str] = None
    dados_meteo: Optional[dict] = None
    profundidade_inicial: Optional[float] = None
    profundidade_final: Optional[float] = None
    temperatura_inicial: Optional[float] = None
    temperatura_final: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    riqueza_especifica: Optional[float] = None
    diversidade_shannon: Optional[float] = None
    equitabilidade_jaccard: Optional[float] = None


@router.get("/api/campanhas/{campanha_id}/busca-ativa")
def get_busca_ativa(campanha_id: int, db: Session = Depends(get_db)):
    items = (
        db.query(BuscaAtiva)
        .join(EstacaoAmostral, BuscaAtiva.estacao_amostral_id == EstacaoAmostral.id)
        .filter(
            EstacaoAmostral.campanha_id == campanha_id,
            EstacaoAmostral.deleted_at.is_(None),
            BuscaAtiva.deleted_at.is_(None),
        )
        .order_by(BuscaAtiva.id.asc())
        .all()
    )
    return [_serialize_busca_ativa(item) for item in items]


@router.post("/api/campanhas/{campanha_id}/busca-ativa")
def create_busca_ativa(campanha_id: int, item: BuscaAtivaCreate, db: Session = Depends(get_db)):
    if item.campanha_id != campanha_id:
        raise HTTPException(status_code=400, detail="Campanha do corpo difere da URL")

    _ensure_campanha_exists(campanha_id, db)
    estacao = _get_or_create_first_estacao(campanha_id, db)

    inicio = _normalize_datetime(item.data_hora_inicio)
    fim = _normalize_datetime(item.data_hora_fim)

    duration = None
    if inicio and fim:
        try:
            duration = fim - inicio
        except Exception:
            duration = None

    data_reg = inicio.date() if inicio else datetime.now().date()
    hora_reg = inicio.time() if inicio else None
    count = (
        db.query(BuscaAtiva)
        .filter(
            BuscaAtiva.estacao_amostral_id == estacao.id,
            BuscaAtiva.deleted_at.is_(None),
        )
        .count()
        + 1
    )

    dados_meteo = {}
    if item.observacoes:
        dados_meteo["observacoes"] = item.observacoes
    if item.latitude is not None:
        dados_meteo["lat"] = item.latitude
    if item.longitude is not None:
        dados_meteo["lon"] = item.longitude
    if isinstance(item.dados_meteo, dict):
        dados_meteo.update(item.dados_meteo)

    db_item = BuscaAtiva(
        estacao_amostral_id=estacao.id,
        numero_busca=count,
        data=data_reg,
        hora_inicio=hora_reg,
        duracao=duration,
        profundidade_inicial=item.profundidade_inicial,
        profundidade_final=item.profundidade_final,
        temperatura_inicial=item.temperatura_inicial,
        temperatura_final=item.temperatura_final,
        visibilidade_vertical=item.visibilidade_vertical,
        visibilidade_horizontal=item.visibilidade_horizontal,
        encontrou_coral_sol=item.encontrou_coral_sol,
        imagens=item.imagens or [],
        planilha_excel_url=item.planilha_excel_url,
        arquivo_percurso_url=item.arquivo_percurso_url,
        dados_meteo=dados_meteo or None,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    if item.encontrou_coral_sol and isinstance(item.detalhes_coral, dict):
        details = dict(item.detalhes_coral)
        try:
            data_dafor = (
                datetime.strptime(details.get("data"), "%Y-%m-%d").date()
                if details.get("data")
                else data_reg
            )
            hora_dafor = (
                datetime.strptime(details.get("hora"), "%H:%M").time()
                if details.get("hora")
                else hora_reg
            )
        except Exception:
            data_dafor = data_reg
            hora_dafor = hora_reg

        imagens_dafor = details.get("imagens") if isinstance(details.get("imagens"), list) else []
        dafor = ProtocoloDAFOR(
            busca_ativa_id=db_item.id,
            data=data_dafor,
            hora=hora_dafor,
            temperatura_inicial=_to_float(details.get("temp_inicial")),
            temperatura_final=_to_float(details.get("temp_final")),
            profundidade_inicial=_to_float(details.get("prof_inicial")),
            profundidade_final=_to_float(details.get("prof_final")),
            iar=_to_float(details.get("iar")),
            imagens=imagens_dafor,
            abundancia=details.get("abundancia"),
            detalhes=details,
        )
        db.add(dafor)
        db.commit()
        db.refresh(db_item)

    return _serialize_busca_ativa(db_item)


@router.get("/api/campanhas/{campanha_id}/video-transectos")
def get_video_transectos(campanha_id: int, db: Session = Depends(get_db)):
    items = (
        db.query(VideoTransecto)
        .join(EstacaoAmostral, VideoTransecto.estacao_amostral_id == EstacaoAmostral.id)
        .filter(
            EstacaoAmostral.campanha_id == campanha_id,
            EstacaoAmostral.deleted_at.is_(None),
            VideoTransecto.deleted_at.is_(None),
        )
        .order_by(VideoTransecto.id.asc())
        .all()
    )
    return [_serialize_video_transecto(item) for item in items]


@router.post("/api/campanhas/{campanha_id}/video-transectos")
def create_video_transecto(campanha_id: int, item: VideoTransectoCreate, db: Session = Depends(get_db)):
    if item.campanha_id != campanha_id:
        raise HTTPException(status_code=400, detail="Campanha do corpo difere da URL")

    _ensure_campanha_exists(campanha_id, db)
    estacao = _get_or_create_first_estacao(campanha_id, db)

    data_reg = item.data_hora.date() if item.data_hora else datetime.now().date()
    hora_reg = item.data_hora.time() if item.data_hora else None

    video_url = item.video_url
    if not video_url and item.observacoes and "Video URL:" in item.observacoes:
        maybe_url = item.observacoes.split("Video URL:", 1)[1].strip()
        video_url = None if maybe_url.upper() == "N/A" else maybe_url

    dados_meteo = {}
    if isinstance(item.dados_meteo, dict):
        dados_meteo.update(item.dados_meteo)
    if item.nome_video:
        dados_meteo.setdefault("nome_video", item.nome_video)
    if item.observacoes:
        dados_meteo.setdefault("observacoes", item.observacoes)

    db_item = VideoTransecto(
        estacao_amostral_id=estacao.id,
        data=data_reg,
        hora=hora_reg,
        profundidade_inicial=item.profundidade_inicial,
        profundidade_final=item.profundidade_final,
        temperatura_inicial=item.temperatura_inicial,
        temperatura_final=item.temperatura_final,
        visibilidade_vertical=item.visibilidade_vertical,
        visibilidade_horizontal=item.visibilidade_horizontal,
        video_url=video_url,
        dados_meteo=dados_meteo or None,
        riqueza_especifica=item.riqueza_especifica,
        diversidade_shannon=item.diversidade_shannon,
        equitabilidade_jaccard=item.equitabilidade_jaccard,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return _serialize_video_transecto(db_item)


@router.get("/api/campanhas/{campanha_id}/fotoquadrados")
def get_fotoquadrados(campanha_id: int, db: Session = Depends(get_db)):
    items = (
        db.query(Fotoquadrado)
        .join(Fotoquadrado.estacao_amostral)
        .filter(
            EstacaoAmostral.campanha_id == campanha_id,
            EstacaoAmostral.deleted_at.is_(None),
            Fotoquadrado.deleted_at.is_(None),
        )
        .order_by(Fotoquadrado.id.asc())
        .all()
    )
    return [_serialize_fotoquadrado(item) for item in items]
