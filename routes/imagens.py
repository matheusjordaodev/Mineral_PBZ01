"""
Routes for Image Gallery
Aggregates images from different methods grouped by island.
"""

from collections import defaultdict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, subqueryload

from db.database import get_db
from db.models import BuscaAtiva, Campanha, EstacaoAmostral, Ilha, VideoTransecto
from services.azure_blob_service import AzureBlobService

router = APIRouter(prefix="/api", tags=["imagens"])


@router.get("/galeria-imagens")
async def get_galeria_imagens(db: Session = Depends(get_db)):
    try:
        blob_service = AzureBlobService()
    except Exception:
        blob_service = None

    def get_url(url: str) -> str:
        return blob_service.get_sas_url(url) if blob_service and url else url

    # 1 query: todas as ilhas
    ilhas = db.query(Ilha).order_by(Ilha.nome).all()

    # 4 queries via subqueryload: campanhas + ilhas + estacoes + fotos/buscas/dafors
    campanhas = (
        db.query(Campanha)
        .options(
            subqueryload(Campanha.ilhas),
            subqueryload(Campanha.estacoes_amostrais).subqueryload(EstacaoAmostral.fotoquadrados),
            subqueryload(Campanha.estacoes_amostrais).subqueryload(EstacaoAmostral.video_transectos),
            subqueryload(Campanha.estacoes_amostrais)
                .subqueryload(EstacaoAmostral.buscas_ativas)
                .subqueryload(BuscaAtiva.protocolos_dafor),
        )
        .filter(Campanha.deleted_at.is_(None))
        .order_by(desc(Campanha.data_campanha))
        .all()
    )

    # Agrupa imagens por ilha_id em Python (sem queries adicionais)
    ilha_images: dict = defaultdict(list)

    for campanha in campanhas:
        ilha_ids = [i.id for i in campanha.ilhas]
        if not ilha_ids and campanha.ilha_id:
            ilha_ids = [campanha.ilha_id]
        if not ilha_ids:
            continue

        campanha_info = f"{campanha.nome} ({campanha.data_campanha.strftime('%d/%m/%Y')})"

        for estacao in campanha.estacoes_amostrais:
            if estacao.deleted_at:
                continue
            estacao_info = f"Estacao {estacao.numero}"

            for foto in estacao.fotoquadrados:
                if foto.deleted_at:
                    continue
                for ilha_id in ilha_ids:
                    if foto.imagem_mosaico_url:
                        ilha_images[ilha_id].append({
                            "type": "Mosaico",
                            "url": get_url(foto.imagem_mosaico_url),
                            "date": foto.data.isoformat() if foto.data else campanha.data_campanha.isoformat(),
                            "label": f"{campanha_info} - {estacao_info} - Mosaico",
                            "campanha_id": campanha.id,
                            "ilha_id": ilha_id,
                        })
                    if isinstance(foto.imagens_complementares, list):
                        for index, img_url in enumerate(foto.imagens_complementares, start=1):
                            ilha_images[ilha_id].append({
                                "type": "Fotoquadrado (Compl.)",
                                "url": get_url(img_url),
                                "date": foto.data.isoformat() if foto.data else campanha.data_campanha.isoformat(),
                                "label": f"{campanha_info} - {estacao_info} - Foto {index}",
                                "campanha_id": campanha.id,
                                "ilha_id": ilha_id,
                            })

            for video in estacao.video_transectos:
                if video.deleted_at or not video.video_url:
                    continue
                for ilha_id in ilha_ids:
                    ilha_images[ilha_id].append({
                        "type": "Vídeo Transecto",
                        "media_type": "video",
                        "url": get_url(video.video_url),
                        "date": video.data.isoformat() if video.data else campanha.data_campanha.isoformat(),
                        "label": f"{campanha_info} - {estacao_info} - Vídeo",
                        "campanha_id": campanha.id,
                        "ilha_id": ilha_id,
                    })

            for busca in estacao.buscas_ativas:
                if busca.deleted_at:
                    continue
                for ilha_id in ilha_ids:
                    if isinstance(busca.imagens, list):
                        for index, img_url in enumerate(busca.imagens, start=1):
                            ilha_images[ilha_id].append({
                                "type": "Busca Ativa",
                                "url": get_url(img_url),
                                "date": busca.data.isoformat() if busca.data else campanha.data_campanha.isoformat(),
                                "label": f"{campanha_info} - {estacao_info} - Busca {busca.numero_busca} - Foto {index}",
                                "campanha_id": campanha.id,
                                "ilha_id": ilha_id,
                            })
                    for dafor in busca.protocolos_dafor:
                        if dafor.deleted_at or not isinstance(dafor.imagens, list):
                            continue
                        for index, img_url in enumerate(dafor.imagens, start=1):
                            ilha_images[ilha_id].append({
                                "type": "DAFOR",
                                "url": get_url(img_url),
                                "date": dafor.data.isoformat() if dafor.data else busca.data.isoformat(),
                                "label": f"{campanha_info} - {estacao_info} - DAFOR - Foto {index}",
                                "campanha_id": campanha.id,
                                "ilha_id": ilha_id,
                            })

    result = [
        {
            "id": ilha.id,
            "nome": ilha.nome,
            "imagens": ilha_images.get(ilha.id, []),
            "total_imagens": len(ilha_images.get(ilha.id, [])),
        }
        for ilha in ilhas
    ]

    return JSONResponse(content={"ilhas": result})
