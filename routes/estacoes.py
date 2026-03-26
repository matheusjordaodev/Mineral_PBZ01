import json
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, subqueryload
from routes.auth import get_current_active_user, get_admin_user
from db.models import Usuario
from pydantic import BaseModel, Field

from db.database import get_db
from db.models import BuscaAtiva, EstacaoAmostral, EspacoAmostral, Fotoquadrado, VideoTransecto
from services.azure_blob_service import AzureBlobService
from services.coleta_service import create_busca_ativa, create_fotoquadrado, create_video_transecto, ensure_campanha_exists

try:
    blob_service = AzureBlobService()
except Exception:
    blob_service = None


def get_url(url: Optional[str]) -> Optional[str]:
    return blob_service.get_sas_url(url) if blob_service and url else url


router = APIRouter(prefix="/api", tags=["estacoes"])


def parse_json_field(value: Optional[str]):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"text": value}


def parse_json_list_field(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        data = [item.strip() for item in value.split(",") if item.strip()]

    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    if isinstance(data, str) and data.strip():
        return [data.strip()]
    return []


def combine_date_time(raw_date: Optional[date], raw_time: Optional[time]) -> Optional[datetime]:
    if not raw_date:
        return None
    return datetime.combine(raw_date, raw_time or time.min)


def add_duration(start_at: Optional[datetime], duration_text: Optional[str]) -> Optional[datetime]:
    if not start_at or not duration_text:
        return None
    try:
        parts = [int(part) for part in str(duration_text).split(":")]
    except ValueError:
        return None

    if len(parts) == 2:
        hours, minutes = parts
        seconds = 0
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        return None

    try:
        return start_at + timedelta(hours=hours, minutes=minutes, seconds=seconds)
    except Exception:
        return None


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
    duracao: Optional[str] = None
    profundidade_inicial: Optional[float] = None
    profundidade_final: Optional[float] = None
    temperatura_inicial: Optional[float] = None
    temperatura_final: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    encontrou_coral_sol: bool = False
    planilha_excel_url: Optional[str] = None
    arquivo_percurso_url: Optional[str] = None
    dados_meteo: Optional[str] = None
    observacoes: Optional[str] = None
    imagens: List[str] = Field(default_factory=list)
    detalhes_coral: Optional[dict] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class VideoTransectoCreate(BaseModel):
    estacao_amostral_id: int
    data: Optional[date] = None
    hora: Optional[time] = None
    nome_video: Optional[str] = None
    observacoes: Optional[str] = None
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
    observacoes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    profundidade: Optional[float] = None
    temperatura: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    imagem_mosaico_url: Optional[str] = None
    imagens_complementares: Optional[str] = None
    dados_meteo: Optional[str] = None
    riqueza_especifica: Optional[float] = None
    diversidade_shannon: Optional[float] = None
    equitabilidade_jaccard: Optional[float] = None


@router.get("/campanhas/{campanha_id}/estacoes")
async def get_estacoes(campanha_id: str, db: Session = Depends(get_db)):
    campanha = ensure_campanha_exists(campanha_id, db)
    estacoes = (
        db.query(EstacaoAmostral)
        .options(
            subqueryload(EstacaoAmostral.espaco_amostral),
            subqueryload(EstacaoAmostral.buscas_ativas),
            subqueryload(EstacaoAmostral.video_transectos),
            subqueryload(EstacaoAmostral.fotoquadrados),
        )
        .filter(
            EstacaoAmostral.campanha_id == campanha.id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .order_by(EstacaoAmostral.numero.asc(), EstacaoAmostral.id.asc())
        .all()
    )

    result = []
    for estacao in estacoes:
        espaco = estacao.espaco_amostral
        result.append(
            {
                "id": estacao.id,
                "espaco_amostral_id": estacao.espaco_amostral_id,
                "numero": estacao.numero,
                "data": estacao.data.isoformat() if estacao.data else None,
                "hora": estacao.hora.isoformat() if estacao.hora else None,
                "observacoes": estacao.observacoes,
                "codigo": espaco.codigo if espaco else None,
                "nome": espaco.nome if espaco else None,
                "metodologia": espaco.metodologia if espaco else None,
                "ilha_id": espaco.ilha_id if espaco else None,
                "num_buscas": len([item for item in estacao.buscas_ativas if not item.deleted_at]),
                "num_videos": len([item for item in estacao.video_transectos if not item.deleted_at]),
                "num_fotos": len([item for item in estacao.fotoquadrados if not item.deleted_at]),
            }
        )
    return result


@router.get("/campanhas/{campanha_id}/pontos-amostrais")
async def get_pontos_amostrais(campanha_id: str, ilha_id: Optional[int] = None, db: Session = Depends(get_db)):
    campanha = ensure_campanha_exists(campanha_id, db)
    allowed_ilha_ids = {
        ilha.id
        for ilha in (campanha.ilhas or [])
        if getattr(ilha, "deleted_at", None) is None
    }
    if campanha.ilha_id:
        allowed_ilha_ids.add(campanha.ilha_id)

    if ilha_id is not None:
        if ilha_id not in allowed_ilha_ids:
            return []
        target_ilha_ids = [ilha_id]
    else:
        target_ilha_ids = sorted(allowed_ilha_ids)

    if not target_ilha_ids:
        return []

    pontos = (
        db.query(EspacoAmostral)
        .options(subqueryload(EspacoAmostral.ilha))
        .filter(
            EspacoAmostral.ilha_id.in_(target_ilha_ids),
            EspacoAmostral.deleted_at.is_(None),
        )
        .order_by(EspacoAmostral.id.asc())
        .all()
    )
    if not pontos:
        return []

    point_ids = [ponto.id for ponto in pontos]
    estacoes = (
        db.query(EstacaoAmostral)
        .options(
            subqueryload(EstacaoAmostral.buscas_ativas),
            subqueryload(EstacaoAmostral.video_transectos),
            subqueryload(EstacaoAmostral.fotoquadrados),
        )
        .filter(
            EstacaoAmostral.campanha_id == campanha.id,
            EstacaoAmostral.espaco_amostral_id.in_(point_ids),
            EstacaoAmostral.deleted_at.is_(None),
        )
        .order_by(EstacaoAmostral.id.asc())
        .all()
    )

    stats_by_point: Dict[int, Dict[str, Any]] = {}
    for estacao in estacoes:
        if estacao.espaco_amostral_id is None:
            continue
        stats = stats_by_point.setdefault(
            estacao.espaco_amostral_id,
            {
                "num_buscas": 0,
                "num_videos": 0,
                "num_fotos": 0,
                "estacoes_ids": [],
                "estacoes_numeros": [],
            },
        )
        stats["num_buscas"] += len([item for item in estacao.buscas_ativas if not item.deleted_at])
        stats["num_videos"] += len([item for item in estacao.video_transectos if not item.deleted_at])
        stats["num_fotos"] += len([item for item in estacao.fotoquadrados if not item.deleted_at])
        stats["estacoes_ids"].append(estacao.id)
        if estacao.numero is not None:
            stats["estacoes_numeros"].append(estacao.numero)

    result = []
    for ponto in pontos:
        stats = stats_by_point.get(ponto.id) or {}
        result.append(
            {
                "id": ponto.id,
                "espaco_amostral_id": ponto.id,
                "codigo": ponto.codigo,
                "nome": ponto.nome,
                "metodologia": ponto.metodologia,
                "ilha_id": ponto.ilha_id,
                "ilha_nome": ponto.ilha.nome if getattr(ponto, "ilha", None) else None,
                "num_buscas": stats.get("num_buscas", 0),
                "num_videos": stats.get("num_videos", 0),
                "num_fotos": stats.get("num_fotos", 0),
                "estacoes_ids": stats.get("estacoes_ids", []),
                "estacoes_numeros": stats.get("estacoes_numeros", []),
            }
        )

    return sorted(result, key=lambda item: (str(item.get("codigo") or ""), item["espaco_amostral_id"]))


@router.get("/campanhas/{campanha_id}/metodos")
async def get_campanha_metodos(campanha_id: str, db: Session = Depends(get_db)):
    campanha = ensure_campanha_exists(campanha_id, db)
    estacoes = (
        db.query(EstacaoAmostral)
        .options(
            subqueryload(EstacaoAmostral.espaco_amostral),
            subqueryload(EstacaoAmostral.buscas_ativas),
            subqueryload(EstacaoAmostral.video_transectos),
            subqueryload(EstacaoAmostral.fotoquadrados),
        )
        .filter(
            EstacaoAmostral.campanha_id == campanha.id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .all()
    )

    buscas = []
    videos = []
    fotos = []

    for estacao in estacoes:
        codigo = estacao.espaco_amostral.codigo if estacao.espaco_amostral else None
        metodologia = estacao.espaco_amostral.metodologia if estacao.espaco_amostral else None

        for busca in estacao.buscas_ativas:
            if busca.deleted_at:
                continue
            buscas.append(
                {
                    "id": busca.id,
                    "numero_busca": busca.numero_busca,
                    "data": busca.data.isoformat() if busca.data else None,
                    "encontrou_coral_sol": busca.encontrou_coral_sol,
                    "estacao_id": estacao.id,
                    "estacao_numero": estacao.numero,
                    "estacao_codigo": codigo,
                    "metodologia": metodologia,
                }
            )

        for video in estacao.video_transectos:
            if video.deleted_at:
                continue
            videos.append(
                {
                    "id": video.id,
                    "data": video.data.isoformat() if video.data else None,
                    "video_url": get_url(video.video_url),
                    "estacao_id": estacao.id,
                    "estacao_numero": estacao.numero,
                    "estacao_codigo": codigo,
                    "metodologia": metodologia,
                }
            )

        for foto in estacao.fotoquadrados:
            if foto.deleted_at:
                continue
            fotos.append(
                {
                    "id": foto.id,
                    "data": foto.data.isoformat() if foto.data else None,
                    "imagem_mosaico_url": get_url(foto.imagem_mosaico_url),
                    "estacao_id": estacao.id,
                    "estacao_numero": estacao.numero,
                    "estacao_codigo": codigo,
                    "metodologia": metodologia,
                }
            )

    return {"buscas": buscas, "videos": videos, "fotos": fotos}


class EstacaoUpdate(BaseModel):
    data: Optional[date] = None
    hora: Optional[time] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    observacoes: Optional[str] = None


@router.put("/estacoes/{estacao_id}")
async def update_estacao(estacao_id: int, payload: EstacaoUpdate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    """Atualiza dados de uma estação amostral (admin)"""
    estacao = db.query(EstacaoAmostral).filter(
        EstacaoAmostral.id == estacao_id,
        EstacaoAmostral.deleted_at.is_(None),
    ).first()
    if not estacao:
        raise HTTPException(status_code=404, detail="Estação amostral não encontrada")

    if payload.data is not None:
        estacao.data = payload.data
    if payload.hora is not None:
        estacao.hora = payload.hora
    if payload.observacoes is not None:
        estacao.observacoes = payload.observacoes
    if payload.lat is not None and payload.lon is not None:
        from geoalchemy2.elements import WKTElement
        estacao.localizacao = WKTElement(f"POINT({payload.lon} {payload.lat})", srid=4326)

    try:
        db.commit()
        db.refresh(estacao)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"success": True, "id": estacao.id}


@router.delete("/estacoes/{estacao_id}")
async def delete_estacao(estacao_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    """Soft-delete de uma estação amostral e seus métodos (admin)"""
    from datetime import datetime as _dt
    estacao = db.query(EstacaoAmostral).filter(
        EstacaoAmostral.id == estacao_id,
        EstacaoAmostral.deleted_at.is_(None),
    ).first()
    if not estacao:
        raise HTTPException(status_code=404, detail="Estação amostral não encontrada")

    now = _dt.utcnow()
    estacao.deleted_at = now
    for busca in estacao.buscas_ativas:
        if not busca.deleted_at:
            busca.deleted_at = now
    for video in estacao.video_transectos:
        if not video.deleted_at:
            video.deleted_at = now
    for foto in estacao.fotoquadrados:
        if not foto.deleted_at:
            foto.deleted_at = now

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"success": True, "deleted": estacao_id}


@router.post("/estacoes")
async def create_estacao(estacao: EstacaoCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    new_estacao = EstacaoAmostral(
        campanha_id=estacao.campanha_id,
        espaco_amostral_id=estacao.espaco_amostral_id,
        numero=estacao.numero,
        data=estacao.data,
        hora=estacao.hora,
        observacoes=estacao.observacoes,
    )

    if estacao.lat is not None and estacao.lon is not None:
        from geoalchemy2.elements import WKTElement

        new_estacao.localizacao = WKTElement(f"POINT({estacao.lon} {estacao.lat})", srid=4326)

    db.add(new_estacao)
    db.commit()
    db.refresh(new_estacao)
    return {"success": True, "id": new_estacao.id}


@router.get("/estacoes/{estacao_id}/buscas-ativas")
async def get_buscas_ativas(estacao_id: int, db: Session = Depends(get_db)):
    buscas = (
        db.query(BuscaAtiva)
        .filter(
            BuscaAtiva.estacao_amostral_id == estacao_id,
            BuscaAtiva.deleted_at.is_(None),
        )
        .all()
    )

    result = []
    for busca in buscas:
        result.append(
            {
                "id": busca.id,
                "numero_busca": busca.numero_busca,
                "data": busca.data.isoformat() if busca.data else None,
                "encontrou_coral_sol": busca.encontrou_coral_sol,
                "profundidade_inicial": float(busca.profundidade_inicial) if busca.profundidade_inicial else None,
                "profundidade_final": float(busca.profundidade_final) if busca.profundidade_final else None,
            }
        )
    return result


@router.post("/buscas-ativas")
async def post_busca_ativa(busca: BuscaAtivaCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    estacao = (
        db.query(EstacaoAmostral)
        .filter(
            EstacaoAmostral.id == busca.estacao_amostral_id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .first()
    )
    if not estacao:
        raise HTTPException(status_code=404, detail="Estacao amostral nao encontrada")

    start_at = combine_date_time(busca.data, busca.hora_inicio)
    end_at = add_duration(start_at, busca.duracao)
    dados_meteo = parse_json_field(busca.dados_meteo)

    try:
        item = create_busca_ativa(
            db,
            estacao.campanha_id,
            {
                "estacao_amostral_id": busca.estacao_amostral_id,
                "numero_busca": busca.numero_busca,
                "data_hora_inicio": start_at,
                "data_hora_fim": end_at,
                "profundidade_inicial": busca.profundidade_inicial,
                "profundidade_final": busca.profundidade_final,
                "temperatura_inicial": busca.temperatura_inicial,
                "temperatura_final": busca.temperatura_final,
                "visibilidade_vertical": busca.visibilidade_vertical,
                "visibilidade_horizontal": busca.visibilidade_horizontal,
                "encontrou_coral_sol": busca.encontrou_coral_sol,
                "planilha_excel_url": busca.planilha_excel_url,
                "arquivo_percurso_url": busca.arquivo_percurso_url,
                "dados_meteo": dados_meteo if isinstance(dados_meteo, dict) else None,
                "observacoes": busca.observacoes,
                "imagens": busca.imagens or [],
                "detalhes_coral": busca.detalhes_coral,
                "latitude": busca.latitude,
                "longitude": busca.longitude,
            },
        )
        db.commit()
        return {"success": True, "id": item.id}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/estacoes/{estacao_id}/video-transectos")
async def get_video_transectos(estacao_id: int, db: Session = Depends(get_db)):
    videos = (
        db.query(VideoTransecto)
        .filter(
            VideoTransecto.estacao_amostral_id == estacao_id,
            VideoTransecto.deleted_at.is_(None),
        )
        .all()
    )

    result = []
    for video in videos:
        result.append(
            {
                "id": video.id,
                "data": video.data.isoformat() if video.data else None,
                "video_url": get_url(video.video_url),
                "profundidade_inicial": float(video.profundidade_inicial) if video.profundidade_inicial else None,
                "profundidade_final": float(video.profundidade_final) if video.profundidade_final else None,
            }
        )
    return result


@router.post("/video-transectos")
async def post_video_transecto(video: VideoTransectoCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    estacao = (
        db.query(EstacaoAmostral)
        .filter(
            EstacaoAmostral.id == video.estacao_amostral_id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .first()
    )
    if not estacao:
        raise HTTPException(status_code=404, detail="Estacao amostral nao encontrada")

    try:
        item = create_video_transecto(
            db,
            estacao.campanha_id,
            {
                "estacao_amostral_id": video.estacao_amostral_id,
                "data_hora": combine_date_time(video.data, video.hora),
                "nome_video": video.nome_video,
                "observacoes": video.observacoes,
                "profundidade_inicial": video.profundidade_inicial,
                "profundidade_final": video.profundidade_final,
                "temperatura_inicial": video.temperatura_inicial,
                "temperatura_final": video.temperatura_final,
                "visibilidade_horizontal": video.visibilidade_horizontal,
                "visibilidade_vertical": video.visibilidade_vertical,
                "video_url": video.video_url,
                "dados_meteo": parse_json_field(video.dados_meteo) if video.dados_meteo else None,
                "riqueza_especifica": video.riqueza_especifica,
                "diversidade_shannon": video.diversidade_shannon,
                "equitabilidade_jaccard": video.equitabilidade_jaccard,
            },
        )
        db.commit()
        return {"success": True, "id": item.id}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/estacoes/{estacao_id}/fotoquadrados")
async def get_fotoquadrados(estacao_id: int, db: Session = Depends(get_db)):
    fotos = (
        db.query(Fotoquadrado)
        .filter(
            Fotoquadrado.estacao_amostral_id == estacao_id,
            Fotoquadrado.deleted_at.is_(None),
        )
        .all()
    )

    result = []
    for foto in fotos:
        result.append(
            {
                "id": foto.id,
                "data": foto.data.isoformat() if foto.data else None,
                "imagem_mosaico_url": get_url(foto.imagem_mosaico_url),
                "profundidade": float(foto.profundidade) if foto.profundidade else None,
                "temperatura": float(foto.temperatura) if foto.temperatura else None,
            }
        )
    return result


@router.post("/fotoquadrados")
async def post_fotoquadrado(foto: FotoquadradoCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    estacao = (
        db.query(EstacaoAmostral)
        .filter(
            EstacaoAmostral.id == foto.estacao_amostral_id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .first()
    )
    if not estacao:
        raise HTTPException(status_code=404, detail="Estacao amostral nao encontrada")

    try:
        item = create_fotoquadrado(
            db,
            estacao.campanha_id,
            {
                "estacao_amostral_id": foto.estacao_amostral_id,
                "data_hora": combine_date_time(foto.data, foto.hora),
                "observacoes": foto.observacoes,
                "latitude": foto.latitude,
                "longitude": foto.longitude,
                "profundidade": foto.profundidade,
                "temperatura": foto.temperatura,
                "visibilidade_vertical": foto.visibilidade_vertical,
                "visibilidade_horizontal": foto.visibilidade_horizontal,
                "imagem_mosaico_url": foto.imagem_mosaico_url,
                "imagens_complementares": parse_json_list_field(foto.imagens_complementares),
                "dados_meteo": parse_json_field(foto.dados_meteo) if foto.dados_meteo else None,
                "riqueza_especifica": foto.riqueza_especifica,
                "diversidade_shannon": foto.diversidade_shannon,
                "equitabilidade_jaccard": foto.equitabilidade_jaccard,
            },
        )
        db.commit()
        return {"success": True, "id": item.id}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
