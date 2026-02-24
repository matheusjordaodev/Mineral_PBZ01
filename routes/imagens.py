"""
Routes for Image Gallery
Aggregates images from different methods (Fotoquadrado, Busca Ativa, etc.) grouped by Island.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.database import get_db
from db.models import Ilha, Campanha, EstacaoAmostral, Fotoquadrado, BuscaAtiva
from services.azure_blob_service import AzureBlobService

router = APIRouter(prefix="/api", tags=["imagens"])

@router.get("/galeria-imagens")
async def get_galeria_imagens(db: Session = Depends(get_db)):
    """
    Retorna estrutura de dados com todas as ilhas e suas respectivas imagens
    coletadas em diferentes métodos.
    """
    
    # 1. Fetch all islands
    ilhas = db.query(Ilha).order_by(Ilha.nome).all()
    
    try:
        blob_service = AzureBlobService()
    except Exception:
        blob_service = None
        
    def get_url(url: str) -> str:
        return blob_service.get_sas_url(url) if blob_service and url else url
        
    result = []
    
    for ilha in ilhas:
        imagens_ilha = []
        
        # 2. For each island, find campaigns -> stations -> methods -> images
        # This could be optimized with joins, but for clarity and complex JSON structures we'll iterate
        # Optimization: Query all needed data for this island
        
        campanhas = db.query(Campanha).filter(Campanha.ilha_id == ilha.id).order_by(desc(Campanha.data_campanha)).all()
        
        for campanha in campanhas:
            campanha_info = f"{campanha.nome} ({campanha.data_campanha.strftime('%d/%m/%Y')})"
            
            for estacao in campanha.estacoes_amostrais:
                estacao_info = f"Estação {estacao.numero}"
                
                # A. Fotoquadrados
                for foto in estacao.fotoquadrados:
                    # Mosaico
                    if foto.imagem_mosaico_url:
                        imagens_ilha.append({
                            "type": "Mosaico",
                            "url": get_url(foto.imagem_mosaico_url),
                            "date": foto.data.isoformat() if foto.data else campanha.data_campanha.isoformat(),
                            "label": f"{campanha_info} - {estacao_info} - Mosaico",
                            "campanha_id": campanha.id,
                            "ilha_id": ilha.id
                        })
                    
                    # Complementares
                    if foto.imagens_complementares:
                        # Ensure it's a list
                        imgs = foto.imagens_complementares
                        if isinstance(imgs, list):
                            for i, img_url in enumerate(imgs):
                                imagens_ilha.append({
                                    "type": "Fotoquadrado (Compl.)",
                                    "url": get_url(img_url),
                                    "date": foto.data.isoformat() if foto.data else campanha.data_campanha.isoformat(),
                                    "label": f"{campanha_info} - {estacao_info} - Foto {i+1}",
                                    "campanha_id": campanha.id,
                                    "ilha_id": ilha.id
                                })
                
                # B. Busca Ativa
                for busca in estacao.buscas_ativas:
                    if busca.imagens:
                        imgs = busca.imagens
                        if isinstance(imgs, list):
                            for i, img_url in enumerate(imgs):
                                imagens_ilha.append({
                                    "type": "Busca Ativa",
                                    "url": get_url(img_url),
                                    "date": busca.data.isoformat() if busca.data else campanha.data_campanha.isoformat(),
                                    "label": f"{campanha_info} - {estacao_info} - Busca {busca.numero_busca} - Foto {i+1}",
                                    "campanha_id": campanha.id,
                                    "ilha_id": ilha.id
                                })
                    
                    # Protocolo DAFOR images
                    for dafor in busca.protocolos_dafor:
                        if dafor.imagens:
                            imgs = dafor.imagens
                            if isinstance(imgs, list):
                                for i, img_url in enumerate(imgs):
                                    imagens_ilha.append({
                                        "type": "DAFOR",
                                        "url": img_url,
                                        "date": dafor.data.isoformat() if dafor.data else busca.data.isoformat(),
                                        "label": f"{campanha_info} - {estacao_info} - DAFOR - Foto {i+1}",
                                        "campanha_id": campanha.id,
                                        "ilha_id": ilha.id
                                    })

        # Add to result if has images (or even if empty, to show the island)
        result.append({
            "id": ilha.id,
            "nome": ilha.nome,
            "imagens": imagens_ilha,
            "total_imagens": len(imagens_ilha)
        })
        
    return JSONResponse(content={"ilhas": result})
