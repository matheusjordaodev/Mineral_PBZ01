"""
Campaign Routes - API endpoints for campaign operations
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
from datetime import date as date_cls
from urllib.parse import quote
from uuid import uuid4

from services import CampanhaService, FileService
from services.coleta_service import ensure_campanha_exists
from routes.auth import get_current_active_user, get_admin_user
from db.models import Usuario
from db.database import get_db
from db.models import Ilha, Campanha, CampanhaIlha, EspacoAmostral, EstacaoAmostral, FeicaoKml
from db.seeds import seed_ilhas, seed_espacos_amostrais
from sqlalchemy.orm import Session, joinedload, subqueryload
from sqlalchemy import func, desc, text
import json
from sqlalchemy.exc import IntegrityError
from geoalchemy2.shape import to_shape
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from services.azure_blob_service import AzureBlobService

try:
    blob_service = AzureBlobService()
except Exception:
    blob_service = None

def get_url(url: Optional[str]) -> Optional[str]:
    return blob_service.get_sas_url(url) if blob_service and url else url


def classify_campaign_recency(campaign_date):
    if not campaign_date:
        return "red", None
    days_since = (date_cls.today() - campaign_date).days
    if days_since < 0:
        days_since = 0
    if days_since <= 30:
        return "green", days_since
    if days_since <= 90:
        return "yellow", days_since
    return "red", days_since


def collect_station_media_urls(estacao):
    items = []

    for busca in (estacao.buscas_ativas or []):
        if busca.deleted_at:
            continue
        for img in (busca.imagens or []):
            resolved = get_url(img)
            if resolved:
                items.append({"url": resolved, "media_type": "image", "label": "Busca Ativa"})
        for dafor in (busca.protocolos_dafor or []):
            if dafor.deleted_at:
                continue
            for img in (dafor.imagens or []):
                resolved = get_url(img)
                if resolved:
                    items.append({"url": resolved, "media_type": "image", "label": "Coral-sol (DAFOR)"})

    for foto in (estacao.fotoquadrados or []):
        if foto.deleted_at:
            continue
        if foto.imagem_mosaico_url:
            resolved = get_url(foto.imagem_mosaico_url)
            if resolved:
                items.append({"url": resolved, "media_type": "image", "label": "Fotoquadrado"})
        for img in (foto.imagens_complementares or []):
            resolved = get_url(img)
            if resolved:
                items.append({"url": resolved, "media_type": "image", "label": "Fotoquadrado"})

    for video in (estacao.video_transectos or []):
        if video.deleted_at or not video.video_url:
            continue
        resolved = get_url(video.video_url)
        if resolved:
            items.append({"url": resolved, "media_type": "video", "label": "Vídeo Transecto"})

    deduped = []
    seen = set()
    for item in items:
        if item["url"] not in seen:
            deduped.append(item)
            seen.add(item["url"])
    return deduped


def collect_campaign_folder_media_urls(campanha, ilha_ids):
    """Fallback media list from campaign media folder when station method media is empty."""
    if not campanha:
        return []

    folder_name = f"{campanha.id}_{campanha.codigo}"
    media_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".avi"}
    video_exts = {".mp4", ".mov", ".avi"}
    items = []

    for ilha_id in ilha_ids or []:
        media_dir = campanha_service.get_campanha_path(str(ilha_id), folder_name) / "media"
        if not media_dir.exists():
            continue

        for file_path in sorted(media_dir.iterdir()):
            if not file_path.is_file():
                continue
            ext = file_path.suffix.lower()
            if ext not in media_exts:
                continue
            filename = quote(file_path.name)
            url = f"/uploads/{ilha_id}/{folder_name}/media/{filename}"
            items.append({"url": url, "media_type": "video" if ext in video_exts else "image", "label": ""})

    deduped = []
    seen = set()
    for item in items:
        if item["url"] not in seen:
            deduped.append(item)
            seen.add(item["url"])
    return deduped


def collect_campaign_azure_media_urls(campanha, ilha_ids):
    """Fallback media list from Azure blobs under /{ilha}/{campanha}/media/."""
    if not campanha or not blob_service:
        return []

    folder_name = f"{campanha.id}_{campanha.codigo}"
    media_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".avi"}
    video_exts = {".mp4", ".mov", ".avi"}
    items = []

    try:
        container_client = blob_service.blob_service_client.get_container_client(blob_service.container_name)
        for ilha_id in ilha_ids or []:
            prefix = f"{ilha_id}/{folder_name}/media/"
            for blob in container_client.list_blobs(name_starts_with=prefix):
                blob_name = blob.name or ""
                ext = Path(blob_name).suffix.lower()
                if ext not in media_exts:
                    continue
                blob_client = container_client.get_blob_client(blob_name)
                resolved = get_url(blob_client.url)
                if resolved:
                    items.append({"url": resolved, "media_type": "video" if ext in video_exts else "image", "label": ""})
    except Exception:
        return []

    deduped = []
    seen = set()
    for item in items:
        if item["url"] not in seen:
            deduped.append(item)
            seen.add(item["url"])
    return deduped


def _empty_station_detail_response(message: str = "Nenhuma campanha registrada nesta estacao."):
    return {
        "found": False,
        "message": message,
        "cor_status": "red",
        "dias_desde_campanha": None,
        "media": [],
    }


def _to_float_or_none(value):
    try:
        return float(value) if value is not None else None
    except Exception:
        return None


def _clean_station_observation(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {
        "registro criado via web",
        "registro criado automaticamente",
        "registro automatico",
    }:
        return None
    return text


def _format_station_summary_value(value):
    if value is None:
        return None
    try:
        raw = f"{float(value):.2f}"
    except Exception:
        return None
    if raw.endswith(".00"):
        return raw[:-3]
    if raw.endswith("0"):
        return raw[:-1]
    return raw


def _build_station_detail_payload(estacao, campanha, espaco=None):
    if not estacao or estacao.deleted_at:
        return _empty_station_detail_response()

    campanha = campanha or estacao.campanha
    espaco = espaco or estacao.espaco_amostral

    recency_color, days_since_campaign = classify_campaign_recency(
        campanha.data_campanha if campanha else None
    )
    media_urls = collect_station_media_urls(estacao)

    fotoquadrados_validos = [f for f in (estacao.fotoquadrados or []) if not f.deleted_at]
    buscas_validas = [b for b in (estacao.buscas_ativas or []) if not b.deleted_at]
    videos_validos = [v for v in (estacao.video_transectos or []) if not v.deleted_at]

    fotos_fq = len(fotoquadrados_validos)
    fotos_busca = sum(len(b.imagens or []) for b in buscas_validas)
    fotos_dafor = 0
    for busca in buscas_validas:
        fotos_dafor += sum(
            len((p.imagens or [])) for p in (busca.protocolos_dafor or []) if not p.deleted_at
        )
    num_fotos = fotos_fq + fotos_busca + fotos_dafor

    num_buscas = len(buscas_validas)
    num_videos = len(videos_validos)

    latest_busca = max(buscas_validas, key=lambda x: x.id, default=None)
    latest_video = max(videos_validos, key=lambda x: x.id, default=None)
    latest_foto = max(fotoquadrados_validos, key=lambda x: x.id, default=None)

    observacoes_busca = None
    if latest_busca and isinstance(latest_busca.dados_meteo, dict):
        observacoes_busca = latest_busca.dados_meteo.get("observacoes")
    observacoes_video = None
    if latest_video and isinstance(latest_video.dados_meteo, dict):
        observacoes_video = latest_video.dados_meteo.get("observacoes")
    observacoes_foto = None
    if latest_foto and isinstance(latest_foto.dados_meteo, dict):
        observacoes_foto = latest_foto.dados_meteo.get("observacoes")

    base_observacao = (
        _clean_station_observation(estacao.observacoes)
        or _clean_station_observation(observacoes_busca)
        or _clean_station_observation(observacoes_video)
        or _clean_station_observation(observacoes_foto)
    )

    metodo_origem = None
    prof_ini = None
    prof_fim = None
    temp_ini = None
    temp_fim = None
    vis_ini = None
    vis_fim = None

    if latest_busca:
        metodo_origem = "Busca Ativa"
        prof_ini = _to_float_or_none(latest_busca.profundidade_inicial)
        prof_fim = _to_float_or_none(latest_busca.profundidade_final)
        temp_ini = _to_float_or_none(latest_busca.temperatura_inicial)
        temp_fim = _to_float_or_none(latest_busca.temperatura_final)
        vis_ini = _to_float_or_none(latest_busca.visibilidade_vertical)
        vis_fim = _to_float_or_none(latest_busca.visibilidade_horizontal)
    elif latest_video:
        metodo_origem = "Video Transecto"
        prof_ini = _to_float_or_none(latest_video.profundidade_inicial)
        prof_fim = _to_float_or_none(latest_video.profundidade_final)
        temp_ini = _to_float_or_none(latest_video.temperatura_inicial)
        temp_fim = _to_float_or_none(latest_video.temperatura_final)
        vis_ini = _to_float_or_none(latest_video.visibilidade_vertical)
        vis_fim = _to_float_or_none(latest_video.visibilidade_horizontal)
    elif latest_foto:
        metodo_origem = "Foto Quadrado"
        prof_ini = _to_float_or_none(latest_foto.profundidade)
        temp_ini = _to_float_or_none(latest_foto.temperatura)
        vis_ini = _to_float_or_none(latest_foto.visibilidade_vertical)
        vis_fim = _to_float_or_none(latest_foto.visibilidade_horizontal)

    num_coral_sol = 0
    for busca in buscas_validas:
        num_coral_sol += len([p for p in (busca.protocolos_dafor or []) if not p.deleted_at])

    resumo_partes = []
    if metodo_origem:
        resumo_partes.append(f"Metodo: {metodo_origem}")
    if prof_ini is not None or prof_fim is not None:
        if prof_ini is not None and prof_fim is not None:
            resumo_partes.append(
                f"Profundidade (m): {_format_station_summary_value(prof_ini)} a {_format_station_summary_value(prof_fim)}"
            )
        elif prof_ini is not None:
            resumo_partes.append(f"Profundidade inicial (m): {_format_station_summary_value(prof_ini)}")
        else:
            resumo_partes.append(f"Profundidade final (m): {_format_station_summary_value(prof_fim)}")
    if temp_ini is not None or temp_fim is not None:
        if temp_ini is not None and temp_fim is not None:
            resumo_partes.append(
                f"Temperatura (C): {_format_station_summary_value(temp_ini)} a {_format_station_summary_value(temp_fim)}"
            )
        elif temp_ini is not None:
            resumo_partes.append(f"Temperatura inicial (C): {_format_station_summary_value(temp_ini)}")
        else:
            resumo_partes.append(f"Temperatura final (C): {_format_station_summary_value(temp_fim)}")
    if vis_ini is not None or vis_fim is not None:
        if vis_ini is not None and vis_fim is not None:
            resumo_partes.append(
                f"Visibilidade (m): {_format_station_summary_value(vis_ini)} a {_format_station_summary_value(vis_fim)}"
            )
        elif vis_ini is not None:
            resumo_partes.append(f"Visibilidade inicial (m): {_format_station_summary_value(vis_ini)}")
        else:
            resumo_partes.append(f"Visibilidade final (m): {_format_station_summary_value(vis_fim)}")
    resumo_partes.append(f"Fotos: {num_fotos}")
    resumo_partes.append(f"Busca ativa: {'sim' if num_buscas > 0 else 'nao'}")
    resumo_partes.append(f"Coral-sol: {'sim' if num_coral_sol > 0 else 'nao'}")
    resumo_tecnico = " | ".join(resumo_partes) if resumo_partes else None

    if base_observacao and resumo_tecnico:
        observacoes_resumo = f"{base_observacao} | {resumo_tecnico}"
    else:
        observacoes_resumo = base_observacao or resumo_tecnico

    if not media_urls and campanha:
        island_candidates = []
        if espaco and getattr(espaco, "ilha_id", None):
            island_candidates.append(espaco.ilha_id)
        if getattr(campanha, "ilha_id", None):
            island_candidates.append(campanha.ilha_id)
        for ilha in (campanha.ilhas or []):
            island_candidates.append(ilha.id)

        unique_islands = []
        seen_islands = set()
        for ilha_id in island_candidates:
            if ilha_id in seen_islands:
                continue
            unique_islands.append(ilha_id)
            seen_islands.add(ilha_id)

        media_urls = collect_campaign_folder_media_urls(campanha, unique_islands)
        if not media_urls:
            media_urls = collect_campaign_azure_media_urls(campanha, unique_islands)

    return {
        "found": True,
        "cor_status": recency_color,
        "dias_desde_campanha": days_since_campaign,
        "estacao": {
            "codigo": espaco.codigo if espaco else None,
            "metodologia": espaco.metodologia if espaco else None,
            "latitude": espaco.latitude if espaco else None,
            "longitude": espaco.longitude if espaco else None,
        },
        "campanha": {
            "id": campanha.codigo if campanha else None,
            "uuid": campanha.codigo if campanha else None,
            "db_id": campanha.id if campanha else None,
            "nome": campanha.nome if campanha else None,
            "data": campanha.data_campanha.isoformat() if campanha and campanha.data_campanha else None,
            "status": campanha.status if campanha else None,
        },
        "dados": {
            "data": estacao.data.isoformat() if estacao.data else None,
            "hora": str(estacao.hora) if estacao.hora else None,
            "observacoes": observacoes_resumo,
            "metodo_origem": metodo_origem,
            "profundidade_inicial": prof_ini,
            "profundidade_final": prof_fim,
            "temperatura_inicial": temp_ini,
            "temperatura_final": temp_fim,
            "visibilidade_inicial": vis_ini,
            "visibilidade_final": vis_fim,
            "num_coral_sol": num_coral_sol,
            "resumo_tecnico": resumo_tecnico,
            "num_fotoquadrados": num_fotos,
            "num_buscas_ativas": num_buscas,
            "num_video_transectos": num_videos,
        },
        "media": media_urls,
    }

# Configuration
UPLOAD_DIR = Path("app/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Services
campanha_service = CampanhaService(UPLOAD_DIR)
file_service = FileService(UPLOAD_DIR)

# Router
router = APIRouter(prefix="/api", tags=["campanhas"])


# Schemas
class PontosSelecao(BaseModel):
    espaco_amostral_id: int
    pontos: List[int] # List of point numbers (1-8)

class IlhaSelecao(BaseModel):
    ilha_id: int
    selecao: List[PontosSelecao] = []

class CampanhaCreate(BaseModel):
    ilhas: List[IlhaSelecao]
    nome: str
    data: str
    descricao: Optional[str] = ""
    base_apoio_id: Optional[int] = None
    embarcacao_id: Optional[int] = None
    membros_equipe: List[int] = []

@router.get("/all-campanhas")
async def get_all_campanhas(db: Session = Depends(get_db)):
    """Retorna lista de todas as campanhas de todas as ilhas para o filtro global"""
    # Eager load ilhas
    campanhas = db.query(Campanha).options(subqueryload(Campanha.ilhas)).order_by(desc(Campanha.data_campanha)).all()
    
    result = []
    for c in campanhas:
        # Join island names
        island_names = [i.nome for i in c.ilhas]
        island_ids = [i.id for i in c.ilhas]
        
        # Fallback for old data if ilhas relation is empty but ilha_id exists
        if not island_names and c.ilha_id:
             legacy_ilha = db.query(Ilha).filter(Ilha.id == c.ilha_id).first()
             if legacy_ilha:
                 island_names = [legacy_ilha.nome]
                 island_ids = [legacy_ilha.id]

        result.append({
            "id": c.codigo,
            "uuid": c.codigo,
            "db_id": c.id,
            "nome": c.nome,
            "data": c.data_campanha.strftime("%Y-%m-%d"),
            "ilha_id": island_ids[0] if island_ids else c.ilha_id,
            "ilha_nome": island_names[0] if island_names else None,
            "ilha_ids": island_ids,
            "ilha_names": island_names, # List of strings
            "status": c.status
        })
        
    return JSONResponse(content={"campanhas": result})


@router.get("/ilhas")
async def get_ilhas(db: Session = Depends(get_db)):
    """Retorna lista de todas as ilhas com status da última campanha E espaços amostrais"""
    seed_ilhas(db)
    seed_espacos_amostrais(db)

    # 1 query: ilhas + subquery-load de espacos_amostrais
    ilhas = db.query(Ilha).options(subqueryload(Ilha.espacos_amostrais)).all()

    all_espaco_ids = [ea.id for ilha in ilhas for ea in ilha.espacos_amostrais]

    # 1 query: última campanha por ilha via DISTINCT ON
    latest_campanha_by_ilha: dict = {}
    if ilhas:
        rows = (
            db.query(CampanhaIlha.ilha_id, Campanha)
            .join(Campanha, CampanhaIlha.campanha_id == Campanha.id)
            .order_by(CampanhaIlha.ilha_id, desc(Campanha.data_campanha))
            .distinct(CampanhaIlha.ilha_id)
            .all()
        )
        latest_campanha_by_ilha = {row[0]: row[1] for row in rows}

    # 1 query: ID da última estação por espaco via DISTINCT ON
    # 1 query: carregar essas estações com campanha via joinedload
    estacoes_with_campanha: dict = {}
    if all_espaco_ids:
        id_rows = (
            db.query(EstacaoAmostral.id, EstacaoAmostral.espaco_amostral_id)
            .join(Campanha, EstacaoAmostral.campanha_id == Campanha.id)
            .filter(
                EstacaoAmostral.espaco_amostral_id.in_(all_espaco_ids),
                EstacaoAmostral.deleted_at == None,
            )
            .order_by(
                EstacaoAmostral.espaco_amostral_id,
                desc(Campanha.data_campanha),
                desc(EstacaoAmostral.id),
            )
            .distinct(EstacaoAmostral.espaco_amostral_id)
            .all()
        )
        latest_ids = [row[0] for row in id_rows]
        if latest_ids:
            estacoes = (
                db.query(EstacaoAmostral)
                .options(joinedload(EstacaoAmostral.campanha))
                .filter(EstacaoAmostral.id.in_(latest_ids))
                .all()
            )
            estacoes_with_campanha = {e.espaco_amostral_id: e for e in estacoes}

    result = []
    for ilha in ilhas:
        point = to_shape(ilha.localizacao)
        coords = [point.y, point.x]

        espacos = []
        for ea in ilha.espacos_amostrais:
            latest_estacao = estacoes_with_campanha.get(ea.id)
            latest_campaign_payload = None
            recency_color = "red"
            days_since_campaign = None

            if latest_estacao and latest_estacao.campanha:
                recency_color, days_since_campaign = classify_campaign_recency(
                    latest_estacao.campanha.data_campanha
                )
                c = latest_estacao.campanha
                latest_campaign_payload = {
                    "id": c.codigo,
                    "uuid": c.codigo,
                    "db_id": c.id,
                    "nome": c.nome,
                    "data": c.data_campanha.isoformat() if c.data_campanha else None,
                    "status": c.status,
                }

            espacos.append({
                "id": ea.id,
                "codigo": ea.codigo,
                "nome": ea.nome,
                "descricao": ea.descricao,
                "metodologia": ea.metodologia,
                "latitude": ea.latitude,
                "longitude": ea.longitude,
                "latest_campaign": latest_campaign_payload,
                "dias_desde_campanha": days_since_campaign,
                "cor_status": recency_color,
            })

        ilha_dict = {
            "id": ilha.id,
            "nome": ilha.nome,
            "coords": coords,
            "regiao": ilha.regiao,
            "espacos_amostrais": espacos,
            "latest_campaign": None,
        }

        latest_campanha = latest_campanha_by_ilha.get(ilha.id)
        if latest_campanha:
            ilha_dict["latest_campaign"] = {
                "id": latest_campanha.codigo,
                "uuid": latest_campanha.codigo,
                "db_id": latest_campanha.id,
                "nome": latest_campanha.nome,
                "data": latest_campanha.data_campanha.isoformat(),
                "status": latest_campanha.status,
            }

        result.append(ilha_dict)

    return JSONResponse(content={"ilhas": result})


@router.get("/estacoes/{estacao_id}/ultima-campanha")
async def get_estacao_ultima_campanha(estacao_id: int, db: Session = Depends(get_db)):
    """Retorna dados da ultima campanha que coletou nesta estacao (espaco amostral)"""

    ultima = db.query(EstacaoAmostral)\
        .filter(EstacaoAmostral.espaco_amostral_id == estacao_id)\
        .join(Campanha)\
        .filter(EstacaoAmostral.deleted_at == None)\
        .order_by(desc(Campanha.data_campanha), desc(EstacaoAmostral.id))\
        .first()

    if not ultima:
        return JSONResponse(content=_empty_station_detail_response())

    campanha = ultima.campanha
    espaco = db.query(EspacoAmostral).get(estacao_id)
    return JSONResponse(content=_build_station_detail_payload(ultima, campanha, espaco))


@router.get("/campanhas/{campanha_id}/estacoes/{estacao_id}/dados")
async def get_campanha_estacao_dados(campanha_id: str, estacao_id: int, db: Session = Depends(get_db)):
    """Retorna os dados da estação dentro da campanha selecionada."""

    campanha = ensure_campanha_exists(campanha_id, db)
    estacao = (
        db.query(EstacaoAmostral)
        .filter(
            EstacaoAmostral.id == estacao_id,
            EstacaoAmostral.campanha_id == campanha.id,
            EstacaoAmostral.deleted_at.is_(None),
        )
        .first()
    )

    if not estacao:
        return JSONResponse(
            content=_empty_station_detail_response(
                "Nenhum dado registrado para esta estacao na campanha selecionada."
            )
        )

    return JSONResponse(content=_build_station_detail_payload(estacao, campanha, estacao.espaco_amostral))

@router.get("/ilhas/{ilha_id}/campanhas")
async def get_campanhas_ilha(ilha_id: str, db: Session = Depends(get_db)):
    """Lista todas as campanhas de uma ilha"""
    
    try:
        i_id_int = int(ilha_id)
    except ValueError:
        return JSONResponse(content={"campanhas": []})

    # Query using M:N
    campanhas_db = db.query(Campanha)\
        .join(Campanha.ilhas)\
        .filter(Ilha.id == i_id_int)\
        .order_by(desc(Campanha.data_campanha))\
        .all()
    
    result = []
    for c in campanhas_db:
        folder_name = f"{c.id}_{c.codigo}"
        
        # Check files in THIS ilha folder
        c_path = campanha_service.get_campanha_path(str(i_id_int), folder_name)
        
        num_geo = 0
        num_media = 0
        
        if c_path.exists():
            geo_dir = c_path / "geospatial"
            if geo_dir.exists():
                num_geo = len(list(geo_dir.glob("*")))
        try:
            num_media = len(file_service.get_media_list(str(i_id_int), folder_name))
        except Exception:
            num_media = 0
        
        result.append({
            "id": c.codigo,
            "uuid": c.codigo,
            "db_id": c.id,
            "nome": c.nome,
            "data": c.data_campanha.strftime("%Y-%m-%d"),
            "descricao": c.descricao,
            "status": c.status,
            "num_geospatial": num_geo,
            "num_media": num_media
        })

    return JSONResponse(content={"campanhas": result})


@router.post("/campanhas")
async def create_campanha(campanha: CampanhaCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    """Cria nova campanha para uma ou mais ilhas com pontos amostrais selecionados"""
    
    if not campanha.ilhas:
        raise HTTPException(status_code=400, detail="Pelo menos uma ilha deve ser selecionada")

    ilha_ids = [i.ilha_id for i in campanha.ilhas]
    
    try:
        # Link Ilhas
        db_ilhas = db.query(Ilha).filter(Ilha.id.in_(ilha_ids)).all()
        if len(db_ilhas) != len(ilha_ids):
             raise HTTPException(status_code=404, detail="Uma ou mais ilhas não encontradas")

        # 1. Create Campanha DB Record
        
        # Use first ilha as 'primary' for legacy column if needed, or None
        primary_ilha_id = ilha_ids[0]
        codigo = str(uuid4())
        while db.query(Campanha.id).filter(Campanha.codigo == codigo).first():
            codigo = str(uuid4())
        
        new_campanha = Campanha(
            ilha_id=primary_ilha_id, # Legacy/Primary
            nome=campanha.nome,
            data_campanha=campanha.data,
            codigo=codigo,
            descricao=campanha.descricao,
            base_apoio_id=campanha.base_apoio_id,
            embarcacao_id=campanha.embarcacao_id
        )
        
        new_campanha.ilhas = db_ilhas
        
        # Link Team Members
        if campanha.membros_equipe:
            from db.models import MembroEquipe
            equipe = db.query(MembroEquipe).filter(MembroEquipe.id.in_(campanha.membros_equipe)).all()
            new_campanha.equipe = equipe

        db.add(new_campanha)
        db.flush()  # Generate ID without final commit

        # 2. Create EstacaoAmostral (Sample Points) based on selection
        from db.models import EstacaoAmostral
        
        for ilha_sel in campanha.ilhas:
            for pts_sel in ilha_sel.selecao:
                for ponto_num in pts_sel.pontos:
                    if 1 <= ponto_num <= 8:
                        new_estacao = EstacaoAmostral(
                            campanha_id=new_campanha.id,
                            espaco_amostral_id=pts_sel.espaco_amostral_id,
                            numero=ponto_num,
                            data=new_campanha.data_campanha,
                            # Localizacao could be refinements later, default to Ilha or Space location if available
                        )
                        db.add(new_estacao)
        
        # 3. Create Folder Structure for EACH Island
        folder_name = f"{new_campanha.id}_{new_campanha.codigo}"
        
        for ilha_id in ilha_ids:
            campanha_service.create_campanha(
                ilha_id=str(ilha_id), 
                nome=campanha.nome,
                data=campanha.data,
                descricao=campanha.descricao,
                custom_id=folder_name
            )

        db.commit()
        db.refresh(new_campanha)
        
        return JSONResponse(content={"success": True, "campanha": new_campanha.to_dict()})
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflito de dados ao criar campanha. Tente novamente.")
    except Exception as e:
        db.rollback()
        print(f"Error creating campanha: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campanhas/{campanha_id}")
async def get_campanha(campanha_id: str, db: Session = Depends(get_db)):
    """Retorna detalhes básicos de uma campanha pelo ID"""
    campanha = ensure_campanha_exists(campanha_id, db)

    return {
        "id": campanha.codigo,
        "uuid": campanha.codigo,
        "db_id": campanha.id,
        "nome": campanha.nome,
        "data": campanha.data_campanha,
        "ilha_id": campanha.ilha_id,
        "ilha_ids": [ilha.id for ilha in campanha.ilhas],
        "ilha_nomes": [ilha.nome for ilha in campanha.ilhas],
        "status": campanha.status,
        "descricao": campanha.descricao
    }


class CampanhaUpdate(BaseModel):
    nome: Optional[str] = None
    data: Optional[str] = None
    descricao: Optional[str] = None
    status: Optional[str] = None


@router.put("/campanhas/{campanha_id}")
async def update_campanha(campanha_id: str, payload: CampanhaUpdate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    """Atualiza dados de uma campanha (admin)"""
    campanha = ensure_campanha_exists(campanha_id, db)

    if payload.nome is not None:
        campanha.nome = payload.nome
    if payload.data is not None:
        from datetime import date as _date
        campanha.data_campanha = _date.fromisoformat(payload.data)
    if payload.descricao is not None:
        campanha.descricao = payload.descricao
    if payload.status is not None:
        campanha.status = payload.status

    try:
        db.commit()
        db.refresh(campanha)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "success": True,
        "campanha": {
            "id": campanha.codigo,
            "nome": campanha.nome,
            "data": campanha.data_campanha.isoformat() if campanha.data_campanha else None,
            "descricao": campanha.descricao,
            "status": campanha.status,
        }
    }


@router.delete("/campanhas/{campanha_id}")
async def delete_campanha(campanha_id: str, db: Session = Depends(get_db), current_user: Usuario = Depends(get_admin_user)):
    """Soft-delete de uma campanha (admin)"""
    campanha = ensure_campanha_exists(campanha_id, db)

    from datetime import datetime as _dt
    campanha.deleted_at = _dt.utcnow()

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"success": True, "deleted": campanha_id}


@router.post("/campanhas/{campanha_id}/geospatial")
async def upload_geospatial(
    campanha_id: str,
    espaco_amostral_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user),
):
    """Upload de arquivo geoespacial (KML/KMZ/GeoJSON/Shapefile) vinculado a um ponto cadastrado."""

    campanha = ensure_campanha_exists(campanha_id, db)

    # Resolve o ponto cadastrado e deriva a ilha a partir dele
    espaco = db.query(EspacoAmostral).filter(
        EspacoAmostral.id == espaco_amostral_id,
        EspacoAmostral.deleted_at.is_(None),
    ).first()
    if not espaco:
        raise HTTPException(status_code=404, detail="Ponto amostral não encontrado")

    ilha_id = espaco.ilha_id
    folder_name = f"{campanha.id}_{campanha.codigo}"

    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
        campanha_service.create_campanha(
            ilha_id=str(ilha_id),
            nome=campanha.nome,
            data=str(campanha.data_campanha),
            descricao=campanha.descricao or "",
            custom_id=folder_name
        )

    try:
        result = file_service.save_geospatial_file(
            ilha_id=str(ilha_id),
            campanha_id=folder_name,
            file_data=file.file,
            filename=file.filename
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Persiste geometrias no PostGIS
    saved_count = 0
    try:
        from utils.kml_parser import parse_kml_file
        from geoalchemy2.shape import from_shape
        from shapely.geometry import shape as shapely_shape

        geospatial_path = Path(result["path"])
        parsed_features = []
        if geospatial_path.exists():
            ext = geospatial_path.suffix.lower()
            if ext in (".kml", ".kmz"):
                parsed = parse_kml_file(str(geospatial_path))
                parsed_features = parsed.get("features", [])
            elif ext in (".geojson", ".json"):
                with open(geospatial_path, "r", encoding="utf-8") as fj:
                    gj = json.load(fj)
                if gj.get("type") == "FeatureCollection":
                    parsed_features = gj.get("features", [])
                elif gj.get("type") == "Feature":
                    parsed_features = [gj]

        if parsed_features:
            # Remove feições anteriores do mesmo arquivo para esta campanha/ponto
            db.query(FeicaoKml).filter(
                FeicaoKml.campanha_id == campanha.id,
                FeicaoKml.espaco_amostral_id == espaco.id,
                FeicaoKml.arquivo_origem == file.filename,
            ).delete()

            for feat in parsed_features:
                geom_dict = feat.get("geometry")
                props = feat.get("properties", {})
                if not geom_dict:
                    continue
                try:
                    shp = shapely_shape(geom_dict)
                    geom_wkb = from_shape(shp, srid=4326)
                except Exception:
                    continue

                feicao = FeicaoKml(
                    campanha_id=campanha.id,
                    espaco_amostral_id=espaco.id,
                    ilha_id=ilha_id,
                    arquivo_origem=file.filename,
                    nome=props.get("name") or props.get("Nome") or "Feição",
                    descricao=props.get("description") or "",
                    tipo_geometria=geom_dict.get("type", "Unknown"),
                    geom=geom_wkb,
                    propriedades=props,
                )
                db.add(feicao)
                saved_count += 1

            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Aviso: falha ao salvar geometrias no PostGIS: {e}")

    return JSONResponse(content={
        "success": True,
        **result,
        "espaco_amostral_id": espaco.id,
        "ilha_id": ilha_id,
        "feicoes_salvas": saved_count,
    })


@router.post("/campanhas/{campanha_id}/media")
async def upload_media(campanha_id: str, ilha_id: str, files: List[UploadFile] = File(...), db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_user)):
    """Upload de múltiplos arquivos de mídia (fotos/vídeos)"""
    
    campanha = ensure_campanha_exists(campanha_id, db)

    folder_name = f"{campanha.id}_{campanha.codigo}"

    # Cria pasta se não existir (campanhas antigas ou criadas fora do fluxo padrão)
    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
        campanha_service.create_campanha(
            ilha_id=str(ilha_id),
            nome=campanha.nome,
            data=str(campanha.data_campanha),
            descricao=campanha.descricao or "",
            custom_id=folder_name
        )
    
    # Prepare files
    file_list = [(f.file, f.filename) for f in files]
    
    try:
        uploaded_files = file_service.save_media_files(
            ilha_id=str(ilha_id),
            campanha_id=folder_name,
            files=file_list
        )
        return JSONResponse(content={
            "success": True,
            "uploaded": len(uploaded_files),
            "files": uploaded_files
        })
    except Exception as e:
        import traceback
        print(f"[upload_media] ERROR: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campanhas/{campanha_id}/files")
async def get_campanha_files(campanha_id: str, ilha_id: str, db: Session = Depends(get_db)):
    """Lista todos os arquivos de uma campanha"""
    
    campanha = ensure_campanha_exists(campanha_id, db)
        
    folder_name = f"{campanha.id}_{campanha.codigo}"
    
    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
        raise HTTPException(status_code=404, detail="Campanha não encontrada na pasta")
    
    files = file_service.list_files(str(ilha_id), folder_name)
    return JSONResponse(content=files)


@router.get("/campanhas/{campanha_id}/geojson")
async def get_campanha_geojson(campanha_id: str, ilha_id: Optional[str] = None, espaco_amostral_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Retorna geometrias da campanha em formato GeoJSON (banco PostGIS + fallback arquivo local)"""

    campanha = ensure_campanha_exists(campanha_id, db)

    # 1. Busca do banco PostGIS usando ST_AsGeoJSON (sem dependência de shapely)
    try:
        query_params = {"cid": campanha.id}
        espaco_filter = ""
        if espaco_amostral_id:
            espaco_filter = " AND espaco_amostral_id = :eid"
            query_params["eid"] = int(espaco_amostral_id)

        rows = db.execute(text(f"""
            SELECT
                ST_AsGeoJSON(ST_Transform(geom, 4674))::text AS geom_json,
                nome, descricao, arquivo_origem, tipo_geometria, propriedades
            FROM feicoes_kml
            WHERE campanha_id = :cid AND deleted_at IS NULL{espaco_filter}
        """), query_params).fetchall()

        if rows:
            features = []
            for row in rows:
                try:
                    geom_dict = json.loads(row.geom_json)
                except Exception:
                    continue
                props = row.propriedades or {}
                features.append({
                    "type": "Feature",
                    "geometry": geom_dict,
                    "properties": {
                        "name": row.nome,
                        "description": row.descricao or "",
                        "arquivo_origem": row.arquivo_origem,
                        "tipo_geometria": row.tipo_geometria,
                        **props
                    }
                })
            if features:
                return JSONResponse(content={
                    "type": "FeatureCollection",
                    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}},
                    "features": features,
                    "source": "database",
                    "metadata": {"total_features": len(features)}
                })
    except Exception as e:
        print(f"Aviso: falha ao consultar feições do banco: {e}")

    # 2. Fallback: arquivo local — varre todas as pastas de ilha para encontrar o KML
    folder_name = f"{campanha.id}_{campanha.codigo}"
    all_features = []

    # Set para O(1) lookup; ilha_id informada vem primeiro
    ilha_dirs_seen: set = set()
    ilha_dirs_to_try: list = []
    if ilha_id:
        ilha_dirs_seen.add(str(ilha_id))
        ilha_dirs_to_try.append(str(ilha_id))
    if UPLOAD_DIR.exists():
        for d in UPLOAD_DIR.iterdir():
            if d.is_dir() and d.name not in ilha_dirs_seen:
                ilha_dirs_seen.add(d.name)
                ilha_dirs_to_try.append(d.name)

    for iid in ilha_dirs_to_try:
        geojson = file_service.get_geojson(iid, folder_name)
        feats = geojson.get("features", [])
        if feats:
            all_features.extend(feats)
            break  # encontrou; não duplica com outras ilhas

    return JSONResponse(content={
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}},
        "features": all_features,
        "source": "file",
        "metadata": {"total_features": len(all_features)}
    })


@router.get("/campanhas/{campanha_id}/media-list")
async def get_campanha_media_list(campanha_id: str, ilha_id: str, db: Session = Depends(get_db)):
    """Lista arquivos de mídia com URLs de acesso"""
    
    campanha = ensure_campanha_exists(campanha_id, db)
        
    folder_name = f"{campanha.id}_{campanha.codigo}"
    
    # Check FS existence (optional, but good for safety)
    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
         # If folder is missing but DB exists, maybe we return empty list or specific error?
         # For now, let's just return empty list or handle gracefully
         return JSONResponse(content={"media": []})
    
    media_list = file_service.get_media_list(str(ilha_id), folder_name)
    return JSONResponse(content={"media": media_list})


@router.get("/campanhas/{campanha_id}/kml/arquivos")
async def list_kml_arquivos(campanha_id: str, db: Session = Depends(get_db)):
    """Lista arquivos KML/KMZ originais disponíveis para a campanha"""
    campanha = ensure_campanha_exists(campanha_id, db)
    folder_name = f"{campanha.id}_{campanha.codigo}"

    arquivos = []
    ilhas_para_busca = campanha.ilhas if campanha.ilhas else []
    if not ilhas_para_busca and campanha.ilha_id:
        legacy = db.query(Ilha).filter(Ilha.id == campanha.ilha_id).first()
        if legacy:
            ilhas_para_busca = [legacy]

    for ilha in ilhas_para_busca:
        geo_dir = campanha_service.get_campanha_path(str(ilha.id), folder_name) / "geospatial"
        if not geo_dir.exists():
            continue
        for f in sorted(geo_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in ('.kml', '.kmz'):
                arquivos.append({
                    "nome": f.name,
                    "ilha_id": ilha.id,
                    "ilha_nome": ilha.nome,
                    "tamanho_bytes": f.stat().st_size
                })

    return JSONResponse(content={"arquivos": arquivos})


@router.get("/campanhas/{campanha_id}/kml/download-original")
async def download_kml_original(campanha_id: str, arquivo: str, ilha_id: str, db: Session = Depends(get_db)):
    """Baixa o arquivo KML/KMZ original que foi enviado"""
    campanha = ensure_campanha_exists(campanha_id, db)
    folder_name = f"{campanha.id}_{campanha.codigo}"

    # Previne path traversal
    if any(c in arquivo for c in ('/', '\\', '..')):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    geo_dir = campanha_service.get_campanha_path(str(ilha_id), folder_name) / "geospatial"
    file_path = geo_dir / arquivo

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    media_type = (
        'application/vnd.google-earth.kmz'
        if arquivo.lower().endswith('.kmz')
        else 'application/vnd.google-earth.kml+xml'
    )
    return FileResponse(path=str(file_path), filename=arquivo, media_type=media_type)


@router.get("/campanhas/{campanha_id}/kml/export")
async def export_kml_from_db(campanha_id: str, espaco_amostral_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Gera e baixa um arquivo KML a partir das geometrias salvas no PostGIS.
    Se espaco_amostral_id for informado, exporta apenas as feições daquele ponto."""
    campanha = ensure_campanha_exists(campanha_id, db)

    from geoalchemy2.shape import to_shape
    from shapely.ops import transform as shp_transform
    import pyproj

    # Transformação 4326 → 4674 para garantir CRS correto na saída
    _proj_4326 = pyproj.CRS("EPSG:4326")
    _proj_4674 = pyproj.CRS("EPSG:4674")
    _transformer = pyproj.Transformer.from_crs(_proj_4326, _proj_4674, always_xy=True)

    def _to_4674(shape):
        return shp_transform(_transformer.transform, shape)

    q = db.query(FeicaoKml).filter(
        FeicaoKml.campanha_id == campanha.id,
        FeicaoKml.deleted_at == None
    )
    if espaco_amostral_id is not None:
        q = q.filter(FeicaoKml.espaco_amostral_id == espaco_amostral_id)
    feicoes = q.all()

    def _esc(text: str) -> str:
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<Document>',
        f'<name>{_esc(campanha.nome)}</name>',
        '<description>Sistema de Referência: SIRGAS 2000 (EPSG:4674)</description>',
        '<atom:author><atom:name>SIRGAS 2000 / EPSG:4674</atom:name></atom:author>',
    ]

    for f in feicoes:
        try:
            shape = _to_4674(to_shape(f.geom))
        except Exception:
            continue

        lines.append('<Placemark>')
        lines.append(f'<name>{_esc(f.nome or "")}</name>')
        if f.descricao:
            lines.append(f'<description>{_esc(f.descricao)}</description>')

        if shape.geom_type == 'Point':
            lines += [
                '<Point><coordinates>',
                f'{shape.x},{shape.y},0',
                '</coordinates></Point>'
            ]
        elif shape.geom_type == 'LineString':
            coords = ' '.join(f'{x},{y},0' for x, y in shape.coords)
            lines += [
                '<LineString><coordinates>',
                coords,
                '</coordinates></LineString>'
            ]
        elif shape.geom_type in ('Polygon', 'MultiPolygon'):
            polys = list(shape.geoms) if shape.geom_type == 'MultiPolygon' else [shape]
            for poly in polys:
                outer = ' '.join(f'{x},{y},0' for x, y in poly.exterior.coords)
                lines += [
                    '<Polygon>',
                    '<outerBoundaryIs><LinearRing><coordinates>',
                    outer,
                    '</coordinates></LinearRing></outerBoundaryIs>',
                ]
                for interior in poly.interiors:
                    inner = ' '.join(f'{x},{y},0' for x, y in interior.coords)
                    lines += [
                        '<innerBoundaryIs><LinearRing><coordinates>',
                        inner,
                        '</coordinates></LinearRing></innerBoundaryIs>',
                    ]
                lines.append('</Polygon>')

        lines.append('</Placemark>')

    lines += ['</Document>', '</kml>']
    kml_content = '\n'.join(lines)

    safe_name = campanha.nome.replace(' ', '_')
    if espaco_amostral_id is not None:
        espaco = db.query(EspacoAmostral).filter(EspacoAmostral.id == espaco_amostral_id).first()
        ponto_suffix = f"_ponto_{espaco.codigo or espaco_amostral_id}" if espaco else f"_ponto_{espaco_amostral_id}"
        filename = f"{safe_name}{ponto_suffix}_export.kml"
    else:
        filename = f"{safe_name}_export.kml"

    return Response(
        content=kml_content.encode('utf-8'),
        media_type='application/vnd.google-earth.kml+xml',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@router.get("/campanhas/{campanha_id}/full-details")
async def get_campanha_full_details(campanha_id: str, db: Session = Depends(get_db)):
    """Retorna detalhes completos da campanha, incluindo métodos (Busca Ativa, etc.)"""
    
    campanha = ensure_campanha_exists(campanha_id, db)
        
    # Aggregate data from all stations
    buscas = []
    videos = []
    fotos = []
    

    for estacao in campanha.estacoes_amostrais:
        if estacao.deleted_at:
            continue

        estacao_codigo = estacao.espaco_amostral.codigo if estacao.espaco_amostral else None

        # Busca Ativa
        for b in estacao.buscas_ativas:
            if b.deleted_at:
                continue
            buscas.append({
                "id": b.id,
                "estacao": estacao.numero,
                "estacao_id": estacao.id,
                "estacao_codigo": estacao_codigo,
                "numero_busca": b.numero_busca,
                "data": b.data.isoformat() if b.data else None,
                "hora_inicio": b.hora_inicio.isoformat() if b.hora_inicio else None,
                "duracao": str(b.duracao) if b.duracao else None,
                "prof_ini": float(b.profundidade_inicial) if b.profundidade_inicial else None,
                "prof_fim": float(b.profundidade_final) if b.profundidade_final else None,
                "temp_ini": float(b.temperatura_inicial) if b.temperatura_inicial else None,
                "temp_fim": float(b.temperatura_final) if b.temperatura_final else None,
                "vis_vert": float(b.visibilidade_vertical) if b.visibilidade_vertical else None,
                "vis_hor": float(b.visibilidade_horizontal) if b.visibilidade_horizontal else None,
                "encontrou_coralsol": b.encontrou_coral_sol,
                "excel_url": get_url(b.planilha_excel_url),
                "track_url": get_url(b.arquivo_percurso_url),
                "dados_meteo": b.dados_meteo
            })
            
        # Video Transecto
        for v in estacao.video_transectos:
            if v.deleted_at:
                continue
            videos.append({
                "id": v.id,
                "estacao": estacao.numero,
                "estacao_id": estacao.id,
                "estacao_codigo": estacao_codigo,
                "data": v.data.isoformat() if v.data else None,
                "hora": v.hora.isoformat() if v.hora else None,
                "prof_ini": float(v.profundidade_inicial) if v.profundidade_inicial else None,
                "prof_fim": float(v.profundidade_final) if v.profundidade_final else None,
                "temp_ini": float(v.temperatura_inicial) if v.temperatura_inicial else None,
                "temp_fim": float(v.temperatura_final) if v.temperatura_final else None,
                "vis_vert": float(v.visibilidade_vertical) if v.visibilidade_vertical else None,
                "vis_hor": float(v.visibilidade_horizontal) if v.visibilidade_horizontal else None,
                "riqueza": float(v.riqueza_especifica) if v.riqueza_especifica else None,
                "shannon": float(v.diversidade_shannon) if v.diversidade_shannon else None,
                "jaccard": float(v.equitabilidade_jaccard) if v.equitabilidade_jaccard else None,
                "video_url": get_url(v.video_url),
                "dados_meteo": v.dados_meteo
            })
            
        # Foto Quadrado
        for f in estacao.fotoquadrados:
            if f.deleted_at:
                continue
            fotos.append({
                "id": f.id,
                "estacao": estacao.numero,
                "estacao_id": estacao.id,
                "estacao_codigo": estacao_codigo,
                "data": f.data.isoformat() if f.data else None,
                "hora": f.hora.isoformat() if f.hora else None,
                "profundidade": float(f.profundidade) if f.profundidade else None,
                "temperatura": float(f.temperatura) if f.temperatura else None,
                "vis_vert": float(f.visibilidade_vertical) if f.visibilidade_vertical else None,
                "vis_hor": float(f.visibilidade_horizontal) if f.visibilidade_horizontal else None,
                "riqueza": float(f.riqueza_especifica) if f.riqueza_especifica else None,
                "shannon": float(f.diversidade_shannon) if f.diversidade_shannon else None,
                "mosaico_url": get_url(f.imagem_mosaico_url),
                "dados_meteo": f.dados_meteo
            })
            
    return JSONResponse(content={
        "buscas": buscas,
        "videos": videos,
        "fotos": fotos
    })
