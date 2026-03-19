from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, subqueryload
from routes.auth import get_current_active_user
from db.models import Usuario

from db.database import get_db
from db.models import (
    BuscaAtiva,
    Campanha,
    EspacoAmostral,
    EstacaoAmostral,
    Fotoquadrado,
    Ilha,
    ProtocoloDAFOR,
    VideoTransecto,
)
from services.azure_blob_service import AzureBlobService
from services.coleta_service import (
    create_busca_ativa,
    create_fotoquadrado,
    create_video_transecto,
    ensure_campanha_exists,
    normalize_datetime,
    to_float,
)

try:
    blob_service = AzureBlobService()
except Exception:
    blob_service = None


def get_url(url: Optional[str]) -> Optional[str]:
    return blob_service.get_sas_url(url) if blob_service and url else url


def _serialize_dafor(item: ProtocoloDAFOR) -> dict:
    imagens = item.imagens if isinstance(item.imagens, list) else []
    return {
        "id": item.id,
        "data": item.data.isoformat() if item.data else None,
        "hora": item.hora.isoformat() if item.hora else None,
        "temperatura_inicial": to_float(item.temperatura_inicial),
        "temperatura_final": to_float(item.temperatura_final),
        "profundidade_inicial": to_float(item.profundidade_inicial),
        "profundidade_final": to_float(item.profundidade_final),
        "iar": to_float(item.iar),
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
        "profundidade_inicial": to_float(item.profundidade_inicial),
        "profundidade_final": to_float(item.profundidade_final),
        "temperatura_inicial": to_float(item.temperatura_inicial),
        "temperatura_final": to_float(item.temperatura_final),
        "visibilidade_vertical": to_float(item.visibilidade_vertical),
        "visibilidade_horizontal": to_float(item.visibilidade_horizontal),
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
        "profundidade_inicial": to_float(item.profundidade_inicial),
        "profundidade_final": to_float(item.profundidade_final),
        "temperatura_inicial": to_float(item.temperatura_inicial),
        "temperatura_final": to_float(item.temperatura_final),
        "visibilidade_vertical": to_float(item.visibilidade_vertical),
        "visibilidade_horizontal": to_float(item.visibilidade_horizontal),
        "riqueza_especifica": to_float(item.riqueza_especifica),
        "diversidade_shannon": to_float(item.diversidade_shannon),
        "equitabilidade_jaccard": to_float(item.equitabilidade_jaccard),
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
        "profundidade": to_float(item.profundidade),
        "temperatura": to_float(item.temperatura),
        "visibilidade_vertical": to_float(item.visibilidade_vertical),
        "visibilidade_horizontal": to_float(item.visibilidade_horizontal),
        "imagem_mosaico_url": get_url(item.imagem_mosaico_url),
        "imagens_complementares": [get_url(img) for img in imagens],
        "dados_meteo": item.dados_meteo,
        "riqueza_especifica": to_float(item.riqueza_especifica),
        "diversidade_shannon": to_float(item.diversidade_shannon),
        "equitabilidade_jaccard": to_float(item.equitabilidade_jaccard),
    }


def _refresh_and_serialize(db: Session, model: str, item_id: int) -> Dict[str, Any]:
    if model == "busca":
        item = db.query(BuscaAtiva).filter(BuscaAtiva.id == item_id).first()
        return _serialize_busca_ativa(item)
    if model == "video":
        item = db.query(VideoTransecto).filter(VideoTransecto.id == item_id).first()
        return _serialize_video_transecto(item)
    item = db.query(Fotoquadrado).filter(Fotoquadrado.id == item_id).first()
    return _serialize_fotoquadrado(item)


router = APIRouter()


def _resolve_request_campaign(path_ref: str, db: Session, body_ref: Optional[str] = None):
    campanha = ensure_campanha_exists(path_ref, db)
    if body_ref is None:
        return campanha

    body_campanha = ensure_campanha_exists(body_ref, db)
    if body_campanha.id != campanha.id:
        raise HTTPException(status_code=400, detail="Campanha do corpo difere da URL")
    return campanha


@router.get("/api/buscas-ativas")
def list_buscas_ativas(
    ilha_id: Optional[int] = None,
    campanha_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    campanha = ensure_campanha_exists(campanha_id, db) if campanha_id else None

    query = (
        db.query(BuscaAtiva)
        .join(EstacaoAmostral, BuscaAtiva.estacao_amostral_id == EstacaoAmostral.id)
        .join(Campanha, EstacaoAmostral.campanha_id == Campanha.id)
        .outerjoin(EspacoAmostral, EstacaoAmostral.espaco_amostral_id == EspacoAmostral.id)
        .outerjoin(Ilha, EspacoAmostral.ilha_id == Ilha.id)
        .options(
            subqueryload(BuscaAtiva.estacao_amostral)
                .subqueryload(EstacaoAmostral.campanha)
                .subqueryload(Campanha.ilhas),
            subqueryload(BuscaAtiva.estacao_amostral)
                .subqueryload(EstacaoAmostral.espaco_amostral)
                .subqueryload(EspacoAmostral.ilha),
            subqueryload(BuscaAtiva.protocolos_dafor),
        )
        .filter(
            BuscaAtiva.deleted_at.is_(None),
            EstacaoAmostral.deleted_at.is_(None),
        )
    )

    if campanha:
        query = query.filter(Campanha.id == campanha.id)

    if ilha_id is not None:
        query = query.filter(Ilha.id == ilha_id)

    items = (
        query.order_by(
            Campanha.data_campanha.desc(),
            BuscaAtiva.data.desc(),
            BuscaAtiva.hora_inicio.desc(),
            BuscaAtiva.id.desc(),
        ).all()
    )

    result = []
    for item in items:
        estacao = item.estacao_amostral
        campanha_ref = estacao.campanha if estacao else None
        espaco = estacao.espaco_amostral if estacao else None
        ilha_ref = espaco.ilha if espaco else None

        if not ilha_ref and campanha_ref and campanha_ref.ilhas:
            ilha_ref = campanha_ref.ilhas[0]

        payload = _serialize_busca_ativa(item)
        payload.update(
            {
                "campanha_id": campanha_ref.codigo if campanha_ref else None,
                "campanha_nome": campanha_ref.nome if campanha_ref else None,
                "campanha_data": campanha_ref.data_campanha.isoformat()
                if campanha_ref and campanha_ref.data_campanha
                else None,
                "ilha_id": ilha_ref.id if ilha_ref else None,
                "ilha_nome": ilha_ref.nome if ilha_ref else None,
                "espaco_amostral_id": espaco.id if espaco else estacao.espaco_amostral_id if estacao else None,
                "espaco_codigo": espaco.codigo if espaco else None,
                "espaco_nome": espaco.nome if espaco else None,
                "estacao_numero": estacao.numero if estacao else None,
                "qtd_imagens": len(payload.get("imagens") or []),
                "qtd_protocolos_dafor": len(payload.get("protocolos_dafor") or []),
            }
        )
        result.append(payload)

    return result


class BuscaAtivaCreate(BaseModel):
    campanha_id: str
    estacao_amostral_id: Optional[int] = None
    numero_busca: Optional[int] = None
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
    campanha_id: str
    estacao_amostral_id: Optional[int] = None
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


class FotoquadradoCreate(BaseModel):
    campanha_id: str
    estacao_amostral_id: Optional[int] = None
    data_hora: Optional[datetime] = None
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
    imagens_complementares: List[str] = Field(default_factory=list)
    dados_meteo: Optional[dict] = None
    riqueza_especifica: Optional[float] = None
    diversidade_shannon: Optional[float] = None
    equitabilidade_jaccard: Optional[float] = None


class BuscaAtivaLoteItem(BaseModel):
    numero_busca: Optional[int] = None
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


class VideoTransectoLoteItem(BaseModel):
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


class FotoquadradoLoteItem(BaseModel):
    data_hora: Optional[datetime] = None
    observacoes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    profundidade: Optional[float] = None
    temperatura: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    imagem_mosaico_url: Optional[str] = None
    imagens_complementares: List[str] = Field(default_factory=list)
    dados_meteo: Optional[dict] = None
    riqueza_especifica: Optional[float] = None
    diversidade_shannon: Optional[float] = None
    equitabilidade_jaccard: Optional[float] = None


class EstacaoEnvioLote(BaseModel):
    estacao_amostral_id: int
    buscas_ativas: List[BuscaAtivaLoteItem] = Field(default_factory=list)
    video_transectos: List[VideoTransectoLoteItem] = Field(default_factory=list)
    fotoquadrados: List[FotoquadradoLoteItem] = Field(default_factory=list)


class EnvioLoteCreate(BaseModel):
    estacoes: List[EstacaoEnvioLote] = Field(default_factory=list)


@router.get("/api/campanhas/{campanha_id}/busca-ativa")
def get_busca_ativa(campanha_id: str, db: Session = Depends(get_db)):
    campanha = ensure_campanha_exists(campanha_id, db)
    items = (
        db.query(BuscaAtiva)
        .join(EstacaoAmostral, BuscaAtiva.estacao_amostral_id == EstacaoAmostral.id)
        .filter(
            EstacaoAmostral.campanha_id == campanha.id,
            EstacaoAmostral.deleted_at.is_(None),
            BuscaAtiva.deleted_at.is_(None),
        )
        .order_by(BuscaAtiva.id.asc())
        .all()
    )
    return [_serialize_busca_ativa(item) for item in items]


@router.post("/api/campanhas/{campanha_id}/busca-ativa")
def post_busca_ativa(campanha_id: str, item: BuscaAtivaCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    campanha = _resolve_request_campaign(campanha_id, db, item.campanha_id)

    try:
        db_item = create_busca_ativa(db, campanha.id, item.model_dump())
        db.commit()
        return _refresh_and_serialize(db, "busca", db_item.id)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/campanhas/{campanha_id}/video-transectos")
def get_video_transectos(campanha_id: str, db: Session = Depends(get_db)):
    campanha = ensure_campanha_exists(campanha_id, db)
    items = (
        db.query(VideoTransecto)
        .join(EstacaoAmostral, VideoTransecto.estacao_amostral_id == EstacaoAmostral.id)
        .filter(
            EstacaoAmostral.campanha_id == campanha.id,
            EstacaoAmostral.deleted_at.is_(None),
            VideoTransecto.deleted_at.is_(None),
        )
        .order_by(VideoTransecto.id.asc())
        .all()
    )
    return [_serialize_video_transecto(item) for item in items]


@router.post("/api/campanhas/{campanha_id}/video-transectos")
def post_video_transecto(campanha_id: str, item: VideoTransectoCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    campanha = _resolve_request_campaign(campanha_id, db, item.campanha_id)

    try:
        db_item = create_video_transecto(db, campanha.id, item.model_dump())
        db.commit()
        return _refresh_and_serialize(db, "video", db_item.id)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/campanhas/{campanha_id}/fotoquadrados")
def get_fotoquadrados(campanha_id: str, db: Session = Depends(get_db)):
    campanha = ensure_campanha_exists(campanha_id, db)
    items = (
        db.query(Fotoquadrado)
        .join(Fotoquadrado.estacao_amostral)
        .filter(
            EstacaoAmostral.campanha_id == campanha.id,
            EstacaoAmostral.deleted_at.is_(None),
            Fotoquadrado.deleted_at.is_(None),
        )
        .order_by(Fotoquadrado.id.asc())
        .all()
    )
    return [_serialize_fotoquadrado(item) for item in items]


@router.post("/api/campanhas/{campanha_id}/fotoquadrados")
def post_fotoquadrado(campanha_id: str, item: FotoquadradoCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    campanha = _resolve_request_campaign(campanha_id, db, item.campanha_id)

    payload = item.model_dump()
    payload["data_hora"] = normalize_datetime(payload.get("data_hora"))

    try:
        db_item = create_fotoquadrado(db, campanha.id, payload)
        db.commit()
        return _refresh_and_serialize(db, "foto", db_item.id)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class BuscaAtivaUpdate(BaseModel):
    numero_busca: Optional[int] = None
    data_hora_inicio: Optional[datetime] = None
    data_hora_fim: Optional[datetime] = None
    encontrou_coral_sol: Optional[bool] = None
    profundidade_inicial: Optional[float] = None
    profundidade_final: Optional[float] = None
    temperatura_inicial: Optional[float] = None
    temperatura_final: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    dados_meteo: Optional[dict] = None
    imagens: Optional[List[str]] = None


class VideoTransectoUpdate(BaseModel):
    data_hora: Optional[datetime] = None
    profundidade_inicial: Optional[float] = None
    profundidade_final: Optional[float] = None
    temperatura_inicial: Optional[float] = None
    temperatura_final: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    riqueza_especifica: Optional[float] = None
    diversidade_shannon: Optional[float] = None
    equitabilidade_jaccard: Optional[float] = None
    video_url: Optional[str] = None
    dados_meteo: Optional[dict] = None


class FotoquadradoUpdate(BaseModel):
    data_hora: Optional[datetime] = None
    profundidade: Optional[float] = None
    temperatura: Optional[float] = None
    visibilidade_vertical: Optional[float] = None
    visibilidade_horizontal: Optional[float] = None
    riqueza_especifica: Optional[float] = None
    diversidade_shannon: Optional[float] = None
    equitabilidade_jaccard: Optional[float] = None
    imagem_mosaico_url: Optional[str] = None
    imagens_complementares: Optional[List[str]] = None
    dados_meteo: Optional[dict] = None


@router.put("/api/busca-ativa/{item_id}")
def update_busca_ativa(item_id: int, payload: BuscaAtivaUpdate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    item = db.query(BuscaAtiva).filter(BuscaAtiva.id == item_id, BuscaAtiva.deleted_at.is_(None)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Busca ativa não encontrada")

    if payload.numero_busca is not None:
        item.numero_busca = payload.numero_busca
    if payload.data_hora_inicio is not None:
        item.data = payload.data_hora_inicio.date()
        item.hora_inicio = payload.data_hora_inicio.time()
    if payload.data_hora_fim is not None and payload.data_hora_inicio is not None:
        from datetime import timedelta
        delta = payload.data_hora_fim - payload.data_hora_inicio
        item.duracao = delta
    if payload.encontrou_coral_sol is not None:
        item.encontrou_coral_sol = payload.encontrou_coral_sol
    if payload.profundidade_inicial is not None:
        item.profundidade_inicial = payload.profundidade_inicial
    if payload.profundidade_final is not None:
        item.profundidade_final = payload.profundidade_final
    if payload.temperatura_inicial is not None:
        item.temperatura_inicial = payload.temperatura_inicial
    if payload.temperatura_final is not None:
        item.temperatura_final = payload.temperatura_final
    if payload.visibilidade_vertical is not None:
        item.visibilidade_vertical = payload.visibilidade_vertical
    if payload.visibilidade_horizontal is not None:
        item.visibilidade_horizontal = payload.visibilidade_horizontal
    if payload.dados_meteo is not None:
        item.dados_meteo = payload.dados_meteo
    if payload.imagens is not None:
        item.imagens = payload.imagens

    try:
        db.commit()
        return _refresh_and_serialize(db, "busca", item.id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/busca-ativa/{item_id}")
def delete_busca_ativa(item_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    from datetime import datetime as _dt
    item = db.query(BuscaAtiva).filter(BuscaAtiva.id == item_id, BuscaAtiva.deleted_at.is_(None)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Busca ativa não encontrada")
    item.deleted_at = _dt.utcnow()
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "deleted": item_id}


@router.put("/api/video-transectos/{item_id}")
def update_video_transecto(item_id: int, payload: VideoTransectoUpdate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    item = db.query(VideoTransecto).filter(VideoTransecto.id == item_id, VideoTransecto.deleted_at.is_(None)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Video transecto não encontrado")

    if payload.data_hora is not None:
        item.data = payload.data_hora.date()
        item.hora = payload.data_hora.time()
    if payload.profundidade_inicial is not None:
        item.profundidade_inicial = payload.profundidade_inicial
    if payload.profundidade_final is not None:
        item.profundidade_final = payload.profundidade_final
    if payload.temperatura_inicial is not None:
        item.temperatura_inicial = payload.temperatura_inicial
    if payload.temperatura_final is not None:
        item.temperatura_final = payload.temperatura_final
    if payload.visibilidade_vertical is not None:
        item.visibilidade_vertical = payload.visibilidade_vertical
    if payload.visibilidade_horizontal is not None:
        item.visibilidade_horizontal = payload.visibilidade_horizontal
    if payload.riqueza_especifica is not None:
        item.riqueza_especifica = payload.riqueza_especifica
    if payload.diversidade_shannon is not None:
        item.diversidade_shannon = payload.diversidade_shannon
    if payload.equitabilidade_jaccard is not None:
        item.equitabilidade_jaccard = payload.equitabilidade_jaccard
    if payload.video_url is not None:
        item.video_url = payload.video_url
    if payload.dados_meteo is not None:
        item.dados_meteo = payload.dados_meteo

    try:
        db.commit()
        return _refresh_and_serialize(db, "video", item.id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/video-transectos/{item_id}")
def delete_video_transecto(item_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    from datetime import datetime as _dt
    item = db.query(VideoTransecto).filter(VideoTransecto.id == item_id, VideoTransecto.deleted_at.is_(None)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Video transecto não encontrado")
    item.deleted_at = _dt.utcnow()
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "deleted": item_id}


@router.put("/api/fotoquadrados/{item_id}")
def update_fotoquadrado(item_id: int, payload: FotoquadradoUpdate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    item = db.query(Fotoquadrado).filter(Fotoquadrado.id == item_id, Fotoquadrado.deleted_at.is_(None)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Fotoquadrado não encontrado")

    if payload.data_hora is not None:
        item.data = payload.data_hora.date()
        item.hora = payload.data_hora.time()
    if payload.profundidade is not None:
        item.profundidade = payload.profundidade
    if payload.temperatura is not None:
        item.temperatura = payload.temperatura
    if payload.visibilidade_vertical is not None:
        item.visibilidade_vertical = payload.visibilidade_vertical
    if payload.visibilidade_horizontal is not None:
        item.visibilidade_horizontal = payload.visibilidade_horizontal
    if payload.riqueza_especifica is not None:
        item.riqueza_especifica = payload.riqueza_especifica
    if payload.diversidade_shannon is not None:
        item.diversidade_shannon = payload.diversidade_shannon
    if payload.equitabilidade_jaccard is not None:
        item.equitabilidade_jaccard = payload.equitabilidade_jaccard
    if payload.imagem_mosaico_url is not None:
        item.imagem_mosaico_url = payload.imagem_mosaico_url
    if payload.imagens_complementares is not None:
        item.imagens_complementares = payload.imagens_complementares
    if payload.dados_meteo is not None:
        item.dados_meteo = payload.dados_meteo

    try:
        db.commit()
        return _refresh_and_serialize(db, "foto", item.id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/fotoquadrados/{item_id}")
def delete_fotoquadrado(item_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    from datetime import datetime as _dt
    item = db.query(Fotoquadrado).filter(Fotoquadrado.id == item_id, Fotoquadrado.deleted_at.is_(None)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Fotoquadrado não encontrado")
    item.deleted_at = _dt.utcnow()
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "deleted": item_id}


@router.post("/api/campanhas/{campanha_id}/envio-lote")
@router.post("/api/campanhas/{campanha_id}/coletas/lote")
def post_envio_lote(campanha_id: str, payload: EnvioLoteCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    campanha = ensure_campanha_exists(campanha_id, db)
    created_refs: List[tuple[str, int]] = []
    station_results: List[Dict[str, Any]] = []

    try:
        for estacao_payload in payload.estacoes:
            estacao_result = {
                "estacao_amostral_id": estacao_payload.estacao_amostral_id,
                "buscas_ativas": [],
                "video_transectos": [],
                "fotoquadrados": [],
            }

            for busca in estacao_payload.buscas_ativas:
                item = create_busca_ativa(
                    db,
                    campanha.id,
                    {
                        **busca.model_dump(),
                        "estacao_amostral_id": estacao_payload.estacao_amostral_id,
                    },
                )
                created_refs.append(("busca", item.id))
                estacao_result["buscas_ativas"].append(item.id)

            for video in estacao_payload.video_transectos:
                item = create_video_transecto(
                    db,
                    campanha.id,
                    {
                        **video.model_dump(),
                        "estacao_amostral_id": estacao_payload.estacao_amostral_id,
                    },
                )
                created_refs.append(("video", item.id))
                estacao_result["video_transectos"].append(item.id)

            for foto in estacao_payload.fotoquadrados:
                item = create_fotoquadrado(
                    db,
                    campanha.id,
                    {
                        **foto.model_dump(),
                        "estacao_amostral_id": estacao_payload.estacao_amostral_id,
                    },
                )
                created_refs.append(("foto", item.id))
                estacao_result["fotoquadrados"].append(item.id)

            station_results.append(estacao_result)

        db.commit()

        created_payload = {
            "estacoes": [],
            "totais": {
                "buscas_ativas": 0,
                "video_transectos": 0,
                "fotoquadrados": 0,
            },
        }

        refs_by_id = {(model, item_id): _refresh_and_serialize(db, model, item_id) for model, item_id in created_refs}

        for estacao_result in station_results:
            station_payload = {
                "estacao_amostral_id": estacao_result["estacao_amostral_id"],
                "buscas_ativas": [refs_by_id[("busca", item_id)] for item_id in estacao_result["buscas_ativas"]],
                "video_transectos": [refs_by_id[("video", item_id)] for item_id in estacao_result["video_transectos"]],
                "fotoquadrados": [refs_by_id[("foto", item_id)] for item_id in estacao_result["fotoquadrados"]],
            }
            created_payload["totais"]["buscas_ativas"] += len(station_payload["buscas_ativas"])
            created_payload["totais"]["video_transectos"] += len(station_payload["video_transectos"])
            created_payload["totais"]["fotoquadrados"] += len(station_payload["fotoquadrados"])
            created_payload["estacoes"].append(station_payload)

        return created_payload
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
