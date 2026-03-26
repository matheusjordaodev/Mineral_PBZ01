"""
Routes for Image Gallery
Aggregates images/videos grouped by Ilha → Ponto Amostral (EspacoAmostral).
Sources:
  1. DB records: fotoquadrados, vídeo transectos, buscas ativas
  2. Upload files: Azure Blob (images/ e videos/ subfolders)

Performance:
  - Um único list_blobs() do container inteiro em vez de N chamadas por campanha/ilha
  - Cache em memória com TTL de 5 minutos para blobs e resultado final
"""

import time
from collections import defaultdict
from pathlib import Path
import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, subqueryload, joinedload

from db.database import get_db
from db.models import BuscaAtiva, Campanha, EspacoAmostral, EstacaoAmostral, Ilha
from services.azure_blob_service import AzureBlobService
from services.file_service import FileService

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))

router = APIRouter(prefix="/api", tags=["imagens"])

# ── Cache em memória ──────────────────────────────────────────────────────────
_CACHE_TTL = 300  # segundos (5 min)

_blob_cache: dict = {"data": None, "ts": 0.0}       # todos os blobs do container
_galeria_cache: dict = {"data": None, "ts": 0.0}    # resultado final serializado

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm"}
DOC_EXTS = {".pdf", ".xls", ".xlsx", ".csv", ".ods", ".kml", ".kmz", ".geojson", ".zip", ".shp"}
MEDIA_FOLDERS = {"images", "videos", "excel", "kml"}


def _invalidate_galeria_cache():
    """Chamado após qualquer upload para forçar refresh."""
    _blob_cache["ts"] = 0.0
    _galeria_cache["ts"] = 0.0


def _all_media_blobs(azure_service: AzureBlobService) -> dict:
    """
    Retorna dict: (ilha_id_str, campanha_folder) → list[{url, nome, media_type, date}]
    Faz UM único list_blobs() e agrupa em Python.
    Resultado é cacheado por _CACHE_TTL segundos.
    """
    now = time.monotonic()
    if _blob_cache["data"] is not None and (now - _blob_cache["ts"]) < _CACHE_TTL:
        return _blob_cache["data"]

    grouped: dict = defaultdict(list)
    try:
        container_client = azure_service.blob_service_client.get_container_client(
            azure_service.container_name
        )
        for blob in container_client.list_blobs():
            parts = blob.name.split("/")
            # Estrutura esperada: {ilha_id}/{campanha_folder}/{folder}/{filename}
            if len(parts) < 4:
                continue
            ilha_id_str, campanha_folder, folder, *rest = parts
            if folder not in MEDIA_FOLDERS:
                continue
            filename = rest[-1] if rest else parts[-1]
            ext = Path(filename).suffix.lower()
            blob_url = f"https://{azure_service.blob_service_client.account_name}.blob.core.windows.net/{azure_service.container_name}/{blob.name}"
            if ext in VIDEO_EXTS:
                media_type = "video"
            elif ext in DOC_EXTS or folder in ("excel", "kml"):
                media_type = "document"
            else:
                media_type = "image"
            grouped[(ilha_id_str, campanha_folder)].append({
                "url": blob_url,
                "nome": filename,
                "media_type": media_type,
                "date": blob.last_modified.isoformat() if blob.last_modified else None,
            })
    except Exception as exc:
        print(f"[galeria] list_blobs falhou: {exc}")

    _blob_cache["data"] = grouped
    _blob_cache["ts"] = now
    return grouped


@router.get("/galeria-imagens")
async def get_galeria_imagens(db: Session = Depends(get_db)):
    # ── Verifica cache do resultado final ─────────────────────────────────────
    now = time.monotonic()
    if _galeria_cache["data"] is not None and (now - _galeria_cache["ts"]) < _CACHE_TTL:
        return JSONResponse(content=_galeria_cache["data"])

    # ── Azure blob service ────────────────────────────────────────────────────
    try:
        azure_service = AzureBlobService()
        blob_map = _all_media_blobs(azure_service)
    except Exception:
        azure_service = None
        blob_map = {}

    def get_url(url: str) -> str:
        return url  # get_sas_url já retorna a URL direto

    # ── 1. Ilhas + espaços amostrais (1 query) ────────────────────────────────
    ilhas = (
        db.query(Ilha)
        .options(subqueryload(Ilha.espacos_amostrais))
        .order_by(Ilha.nome)
        .all()
    )

    # ── 2. Campanhas com todas as relações (4 queries via subqueryload) ────────
    campanhas = (
        db.query(Campanha)
        .options(
            subqueryload(Campanha.ilhas),
            subqueryload(Campanha.estacoes_amostrais)
                .joinedload(EstacaoAmostral.espaco_amostral),
            subqueryload(Campanha.estacoes_amostrais)
                .subqueryload(EstacaoAmostral.fotoquadrados),
            subqueryload(Campanha.estacoes_amostrais)
                .subqueryload(EstacaoAmostral.video_transectos),
            subqueryload(Campanha.estacoes_amostrais)
                .subqueryload(EstacaoAmostral.buscas_ativas)
                .subqueryload(BuscaAtiva.protocolos_dafor),
        )
        .filter(Campanha.deleted_at.is_(None))
        .order_by(desc(Campanha.data_campanha))
        .all()
    )

    # espaco_id → list[media_item]
    espaco_media: dict = defaultdict(list)
    # "ilha_{ilha_id}" → list[media_item]  (uploads sem ponto específico)
    ilha_uploads: dict = defaultdict(list)

    for campanha in campanhas:
        ilha_ids = [i.id for i in campanha.ilhas]
        if not ilha_ids and campanha.ilha_id:
            ilha_ids = [campanha.ilha_id]

        campanha_label = (
            f"{campanha.nome} "
            f"({campanha.data_campanha.strftime('%d/%m/%Y') if campanha.data_campanha else '-'})"
        )
        folder_name = f"{campanha.id}_{campanha.codigo}"

        # ── Mídias do banco ───────────────────────────────────────────────────
        for estacao in campanha.estacoes_amostrais:
            if estacao.deleted_at:
                continue
            espaco = estacao.espaco_amostral
            if not espaco:
                continue
            eid = espaco.id
            espaco_label = espaco.codigo or espaco.nome
            base_date = campanha.data_campanha.isoformat() if campanha.data_campanha else None

            for foto in estacao.fotoquadrados:
                if foto.deleted_at:
                    continue
                d = foto.data.isoformat() if foto.data else base_date
                if foto.imagem_mosaico_url:
                    espaco_media[eid].append({
                        "type": "Mosaico", "media_type": "image",
                        "url": get_url(foto.imagem_mosaico_url), "date": d,
                        "label": f"{campanha_label} · {espaco_label} · Mosaico",
                        "campanha": campanha_label,
                    })
                if isinstance(foto.imagens_complementares, list):
                    for idx, u in enumerate(foto.imagens_complementares, 1):
                        if u:
                            espaco_media[eid].append({
                                "type": "Fotoquadrado", "media_type": "image",
                                "url": get_url(u), "date": d,
                                "label": f"{campanha_label} · {espaco_label} · Foto {idx}",
                                "campanha": campanha_label,
                            })

            for video in estacao.video_transectos:
                if video.deleted_at:
                    continue
                vd = video.data.isoformat() if video.data else base_date
                if video.video_url:
                    espaco_media[eid].append({
                        "type": "Vídeo Transecto", "media_type": "video",
                        "url": get_url(video.video_url),
                        "date": vd,
                        "label": f"{campanha_label} · {espaco_label} · Vídeo",
                        "campanha": campanha_label,
                    })
                if hasattr(video, "arquivo_percurso_url") and video.arquivo_percurso_url:
                    espaco_media[eid].append({
                        "type": "Vídeo Transecto", "media_type": "document",
                        "url": get_url(video.arquivo_percurso_url),
                        "date": vd,
                        "nome": Path(video.arquivo_percurso_url).name,
                        "label": f"{campanha_label} · {espaco_label} · VT Percurso",
                        "campanha": campanha_label,
                    })

            for busca in estacao.buscas_ativas:
                if busca.deleted_at:
                    continue
                d = busca.data.isoformat() if busca.data else base_date
                if isinstance(busca.imagens, list):
                    for idx, u in enumerate(busca.imagens, 1):
                        if u:
                            espaco_media[eid].append({
                                "type": "Busca Ativa", "media_type": "image",
                                "url": get_url(u), "date": d,
                                "label": f"{campanha_label} · {espaco_label} · Busca {busca.numero_busca} · Foto {idx}",
                                "campanha": campanha_label,
                            })
                if busca.planilha_excel_url:
                    espaco_media[eid].append({
                        "type": "Busca Ativa", "media_type": "document",
                        "url": get_url(busca.planilha_excel_url), "date": d,
                        "nome": Path(busca.planilha_excel_url).name,
                        "label": f"{campanha_label} · {espaco_label} · Busca {busca.numero_busca} · Planilha",
                        "campanha": campanha_label,
                    })
                if busca.arquivo_percurso_url:
                    espaco_media[eid].append({
                        "type": "Busca Ativa", "media_type": "document",
                        "url": get_url(busca.arquivo_percurso_url), "date": d,
                        "nome": Path(busca.arquivo_percurso_url).name,
                        "label": f"{campanha_label} · {espaco_label} · Busca {busca.numero_busca} · Percurso",
                        "campanha": campanha_label,
                    })
                for dafor in busca.protocolos_dafor:
                    if dafor.deleted_at or not isinstance(dafor.imagens, list):
                        continue
                    dd = dafor.data.isoformat() if dafor.data else d
                    for idx, u in enumerate(dafor.imagens, 1):
                        if u:
                            espaco_media[eid].append({
                                "type": "DAFOR", "media_type": "image",
                                "url": get_url(u), "date": dd,
                                "label": f"{campanha_label} · {espaco_label} · DAFOR · Foto {idx}",
                                "campanha": campanha_label,
                            })

        # ── Uploads do Azure (lookup no mapa já construído) ───────────────────
        for ilha_id in ilha_ids:
            blobs = blob_map.get((str(ilha_id), folder_name), [])
            for blob in blobs:
                ilha_uploads[ilha_id].append({
                    "type": "Upload", "media_type": blob["media_type"],
                    "url": blob["url"], "date": blob["date"],
                    "label": f"{campanha_label} · {blob['nome']}",
                    "campanha": campanha_label,
                })

    # ── 3. Montar resultado Ilha → Pontos ─────────────────────────────────────
    result = []
    for ilha in ilhas:
        pontos = []
        for espaco in ilha.espacos_amostrais:
            midias = espaco_media.get(espaco.id, [])
            if midias:
                pontos.append({
                    "id": espaco.id,
                    "codigo": espaco.codigo or espaco.nome,
                    "nome": espaco.nome,
                    "metodologia": espaco.metodologia,
                    "midias": midias,
                    "total": len(midias),
                })

        uploads = ilha_uploads.get(ilha.id, [])
        if uploads:
            pontos.append({
                "id": None,
                "codigo": "—",
                "nome": "Arquivos enviados",
                "metodologia": None,
                "midias": uploads,
                "total": len(uploads),
            })

        total = sum(p["total"] for p in pontos)
        if total > 0:
            result.append({
                "id": ilha.id,
                "nome": ilha.nome,
                "pontos": pontos,
                "total": total,
            })

    payload = {"ilhas": result}
    _galeria_cache["data"] = payload
    _galeria_cache["ts"] = time.monotonic()

    return JSONResponse(content=payload)


@router.post("/galeria-imagens/invalidar-cache")
async def invalidar_cache_galeria():
    """Invalida o cache da galeria (chamado internamente após uploads)."""
    _invalidate_galeria_cache()
    return {"ok": True}
