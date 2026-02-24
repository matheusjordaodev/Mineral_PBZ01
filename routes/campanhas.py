"""
Campaign Routes - API endpoints for campaign operations
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
from datetime import date as date_cls
from urllib.parse import quote

from services import CampanhaService, FileService
from db.database import get_db
from db.models import Ilha, Campanha, EspacoAmostral, EstacaoAmostral
from db.seeds import seed_ilhas
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
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
    urls = []

    for busca in (estacao.buscas_ativas or []):
        if busca.deleted_at:
            continue
        for img in (busca.imagens or []):
            resolved = get_url(img)
            if resolved:
                urls.append(resolved)

    for foto in (estacao.fotoquadrados or []):
        if foto.deleted_at:
            continue
        if foto.imagem_mosaico_url:
            resolved = get_url(foto.imagem_mosaico_url)
            if resolved:
                urls.append(resolved)
        for img in (foto.imagens_complementares or []):
            resolved = get_url(img)
            if resolved:
                urls.append(resolved)

    deduped = []
    seen = set()
    for url in urls:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped


def collect_campaign_folder_media_urls(campanha, ilha_ids):
    """Fallback media list from campaign media folder when station method media is empty."""
    if not campanha:
        return []

    folder_name = f"{campanha.id}_{campanha.codigo}"
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    urls = []

    for ilha_id in ilha_ids or []:
        media_dir = campanha_service.get_campanha_path(str(ilha_id), folder_name) / "media"
        if not media_dir.exists():
            continue

        for file_path in sorted(media_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in image_exts:
                continue
            filename = quote(file_path.name)
            urls.append(f"/uploads/{ilha_id}/{folder_name}/media/{filename}")

    deduped = []
    seen = set()
    for url in urls:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped


def collect_campaign_azure_media_urls(campanha, ilha_ids):
    """Fallback media list from Azure blobs under /{ilha}/{campanha}/media/."""
    if not campanha or not blob_service:
        return []

    folder_name = f"{campanha.id}_{campanha.codigo}"
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    urls = []

    try:
        container_client = blob_service.blob_service_client.get_container_client(blob_service.container_name)
        for ilha_id in ilha_ids or []:
            prefix = f"{ilha_id}/{folder_name}/media/"
            for blob in container_client.list_blobs(name_starts_with=prefix):
                blob_name = blob.name or ""
                suffix = Path(blob_name).suffix.lower()
                if suffix not in image_exts:
                    continue
                blob_client = container_client.get_blob_client(blob_name)
                resolved = get_url(blob_client.url)
                if resolved:
                    urls.append(resolved)
    except Exception:
        return []

    deduped = []
    seen = set()
    for url in urls:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped

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
    campanhas = db.query(Campanha).order_by(desc(Campanha.data_campanha)).all()
    
    result = []
    for c in campanhas:
        # Join island names
        island_names = [i.nome for i in c.ilhas]
        island_ids = [i.id for i in c.ilhas]
        
        # Fallback for old data if ilhas relation is empty but ilha_id exists
        if not island_names and c.ilha_id:
             # This requires lazy load or join, checking if accessible
             pass

        result.append({
            "id": c.id,
            "nome": c.nome,
            "data": c.data_campanha.strftime("%Y-%m-%d"),
            "ilha_ids": island_ids,
            "ilha_names": island_names, # List of strings
            "status": c.status
        })
        
    return JSONResponse(content={"campanhas": result})


@router.get("/ilhas")
async def get_ilhas(db: Session = Depends(get_db)):
    """Retorna lista de todas as ilhas com status da última campanha E espaços amostrais"""
    # Auto-seed if empty
    seed_ilhas(db)
    
    ilhas = db.query(Ilha).all()
    result = []
    
    for ilha in ilhas:
        # Get latest campaign via M:N
        latest_campanha = db.query(Campanha)\
            .join(Campanha.ilhas)\
            .filter(Ilha.id == ilha.id)\
            .order_by(desc(Campanha.data_campanha))\
            .first()
            
        # Convert coords
        point = to_shape(ilha.localizacao)
        coords = [point.y, point.x] # Lat, Lon
        
        # Get Sample Spaces
        espacos = []
        for ea in ilha.espacos_amostrais:
             latest_estacao = db.query(EstacaoAmostral)\
                 .join(Campanha, EstacaoAmostral.campanha_id == Campanha.id)\
                 .filter(
                     EstacaoAmostral.espaco_amostral_id == ea.id,
                     EstacaoAmostral.deleted_at == None
                 )\
                 .order_by(desc(Campanha.data_campanha), desc(EstacaoAmostral.id))\
                 .first()

             latest_campaign_payload = None
             recency_color = "red"
             days_since_campaign = None

             if latest_estacao and latest_estacao.campanha:
                 recency_color, days_since_campaign = classify_campaign_recency(latest_estacao.campanha.data_campanha)
                 latest_campaign_payload = {
                     "id": latest_estacao.campanha.id,
                     "nome": latest_estacao.campanha.nome,
                     "data": latest_estacao.campanha.data_campanha.isoformat() if latest_estacao.campanha.data_campanha else None,
                     "status": latest_estacao.campanha.status
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
                 "cor_status": recency_color
             })

        ilha_dict = {
            "id": ilha.id,
            "nome": ilha.nome,
            "coords": coords,
            "regiao": ilha.regiao,
            "espacos_amostrais": espacos,
            "latest_campaign": None
        }
        
        if latest_campanha:
            ilha_dict["latest_campaign"] = {
                "id": latest_campanha.id,
                "nome": latest_campanha.nome,
                "data": latest_campanha.data_campanha.isoformat(),
                "status": latest_campanha.status
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
        return JSONResponse(content={
            "found": False,
            "message": "Nenhuma campanha registrada nesta estacao.",
            "cor_status": "red",
            "dias_desde_campanha": None,
            "media": []
        })

    campanha = ultima.campanha
    espaco = db.query(EspacoAmostral).get(estacao_id)
    recency_color, days_since_campaign = classify_campaign_recency(campanha.data_campanha if campanha else None)
    media_urls = collect_station_media_urls(ultima)

    num_fotos = len([f for f in (ultima.fotoquadrados or []) if not f.deleted_at])
    num_buscas = len([b for b in (ultima.buscas_ativas or []) if not b.deleted_at])
    num_videos = len([v for v in (ultima.video_transectos or []) if not v.deleted_at])

    if not media_urls and campanha:
        island_candidates = []
        if espaco and getattr(espaco, "ilha_id", None):
            island_candidates.append(espaco.ilha_id)
        if getattr(campanha, "ilha_id", None):
            island_candidates.append(campanha.ilha_id)
        for ilha in (campanha.ilhas or []):
            island_candidates.append(ilha.id)

        # preserve order while de-duplicating
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

    result = {
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
            "id": campanha.id,
            "nome": campanha.nome,
            "data": campanha.data_campanha.isoformat() if campanha.data_campanha else None,
            "status": campanha.status,
        },
        "dados": {
            "data": ultima.data.isoformat() if ultima.data else None,
            "hora": str(ultima.hora) if ultima.hora else None,
            "observacoes": ultima.observacoes,
            "num_fotoquadrados": num_fotos,
            "num_buscas_ativas": num_buscas,
            "num_video_transectos": num_videos,
        },
        "media": media_urls
    }

    return JSONResponse(content=result)

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
            media_dir = c_path / "media"
            if geo_dir.exists():
                num_geo = len(list(geo_dir.glob("*")))
            if media_dir.exists():
                num_media = len(list(media_dir.glob("*")))
        
        result.append({
            "id": c.id, 
            "nome": c.nome,
            "data": c.data_campanha.strftime("%Y-%m-%d"),
            "descricao": c.descricao,
            "status": c.status,
            "num_geospatial": num_geo,
            "num_media": num_media
        })

    return JSONResponse(content={"campanhas": result})


@router.post("/campanhas")
async def create_campanha(campanha: CampanhaCreate, db: Session = Depends(get_db)):
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
        
        new_campanha = Campanha(
            ilha_id=primary_ilha_id, # Legacy/Primary
            nome=campanha.nome,
            data_campanha=campanha.data,
            codigo=f"CAMP-{campanha.nome[:3].upper()}-{campanha.data.replace('-','')}",
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
        db.commit() # Commit to get ID
        db.refresh(new_campanha)

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
        
        db.commit()

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
        
        return JSONResponse(content={"success": True, "campanha": new_campanha.to_dict()})
    except Exception as e:
        db.rollback()
        print(f"Error creating campanha: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campanhas/{campanha_id}")
async def get_campanha(campanha_id: str, db: Session = Depends(get_db)):
    """Retorna detalhes básicos de uma campanha pelo ID"""
    try:
        c_id = int(campanha_id)
        campanha = db.query(Campanha).filter(Campanha.id == c_id).first()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Campaign ID")

    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    
    return {
        "id": campanha.id,
        "nome": campanha.nome,
        "data": campanha.data_campanha,
        "ilha_id": campanha.ilha_id,
        "status": campanha.status,
        "descricao": campanha.descricao
    }


@router.post("/campanhas/{campanha_id}/geospatial")
async def upload_geospatial(campanha_id: str, ilha_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload de arquivo geoespacial (KML/KMZ/GeoJSON/Shapefile)"""
    
    # Resolve DB ID
    try:
        c_id = int(campanha_id)
        campanha = db.query(Campanha).filter(Campanha.id == c_id).first()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Campaign ID")
        
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha não encontrada no banco")
    
    folder_name = f"{campanha.id}_{campanha.codigo}"

    # Verificar se campanha existe no FS
    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
        # Create if missing? Or raise error? Service creates on create_campanha.
        # Ideally it should exist.
        raise HTTPException(status_code=404, detail="Pasta da campanha não encontrada")
    
    try:
        result = file_service.save_geospatial_file(
            ilha_id=str(ilha_id),
            campanha_id=folder_name,
            file_data=file.file,
            filename=file.filename
        )
        # Update DB count if needed, or trigger something? For now just return success.
        return JSONResponse(content={"success": True, **result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campanhas/{campanha_id}/media")
async def upload_media(campanha_id: str, ilha_id: str, files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Upload de múltiplos arquivos de mídia (fotos/vídeos)"""
    
    # Resolve DB ID
    try:
        c_id = int(campanha_id)
        campanha = db.query(Campanha).filter(Campanha.id == c_id).first()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Campaign ID")
        
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha não encontrada no banco")
    
    folder_name = f"{campanha.id}_{campanha.codigo}"
    
    # Verificar se campanha existe
    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campanhas/{campanha_id}/files")
async def get_campanha_files(campanha_id: str, ilha_id: str, db: Session = Depends(get_db)):
    """Lista todos os arquivos de uma campanha"""
    
    # Resolve DB ID
    try:
        c_id = int(campanha_id)
        campanha = db.query(Campanha).filter(Campanha.id == c_id).first()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Campaign ID")
        
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
        
    folder_name = f"{campanha.id}_{campanha.codigo}"
    
    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
        raise HTTPException(status_code=404, detail="Campanha não encontrada na pasta")
    
    files = file_service.list_files(str(ilha_id), folder_name)
    return JSONResponse(content=files)


@router.get("/campanhas/{campanha_id}/geojson")
async def get_campanha_geojson(campanha_id: str, ilha_id: str, db: Session = Depends(get_db)):
    """Retorna geometrias da campanha em formato GeoJSON"""
    
    # Resolve DB ID
    try:
        c_id = int(campanha_id)
        campanha = db.query(Campanha).filter(Campanha.id == c_id).first()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Campaign ID")
        
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
        
    folder_name = f"{campanha.id}_{campanha.codigo}"
    
    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
        # Empty GeoJSON if folder missing
        return JSONResponse(content={"type": "FeatureCollection", "features": []})
    
    geojson = file_service.get_geojson(str(ilha_id), folder_name)
    return JSONResponse(content=geojson)


@router.get("/campanhas/{campanha_id}/media-list")
async def get_campanha_media_list(campanha_id: str, ilha_id: str, db: Session = Depends(get_db)):
    """Lista arquivos de mídia com URLs de acesso"""
    
    # Resolve DB ID to Folder Name
    try:
        c_id = int(campanha_id)
        campanha = db.query(Campanha).filter(Campanha.id == c_id).first()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Campaign ID")
        
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha não encontrada no banco")
        
    folder_name = f"{campanha.id}_{campanha.codigo}"
    
    # Check FS existence (optional, but good for safety)
    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
         # If folder is missing but DB exists, maybe we return empty list or specific error?
         # For now, let's just return empty list or handle gracefully
         return JSONResponse(content={"media": []})
    
    media_list = file_service.get_media_list(str(ilha_id), folder_name)
    return JSONResponse(content={"media": media_list})


@router.get("/campanhas/{campanha_id}/full-details")
async def get_campanha_full_details(campanha_id: str, db: Session = Depends(get_db)):
    """Retorna detalhes completos da campanha, incluindo métodos (Busca Ativa, etc.)"""
    
    try:
        c_id = int(campanha_id)
        campanha = db.query(Campanha).filter(Campanha.id == c_id).first()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Campaign ID")
        
    if not campanha:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
        
    # Aggregate data from all stations
    buscas = []
    videos = []
    fotos = []
    

    for estacao in campanha.estacoes_amostrais:
        # Busca Ativa
        for b in estacao.buscas_ativas:
            buscas.append({
                "estacao": estacao.numero,
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
            videos.append({
                "estacao": estacao.numero,
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
            fotos.append({
                "estacao": estacao.numero,
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

