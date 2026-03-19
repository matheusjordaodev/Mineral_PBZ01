import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

load_dotenv()

app = FastAPI(title=os.getenv("APP_NAME", "PMASCC WebGIS"))

# CORS: origens permitidas via env var ALLOWED_ORIGINS (separadas por vírgula)
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if _allowed_origins else ["http://localhost:8080", "http://localhost:8001"],
    allow_credentials=bool(_allowed_origins),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Servir arquivos estáticos (HTML / CSS / JS / imagens)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Serve a página principal do WebGIS."""
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path)


@app.get("/api/layers")
async def get_layers():
    """
    Lista as camadas disponíveis no WebGIS.
    Aqui estamos fixando algumas camadas baseadas no PPT:
    - Busca Ativa
    - Videotransecto
    - Fotoquadrado
    """
    layers = [
        {
            "id": "busca_ativa",
            "nome": "Busca Ativa",
            "tipo": "pontos",
            "default_visible": True,
        },
        {
            "id": "videotransecto",
            "nome": "Videotransecto",
            "tipo": "pontos",
            "default_visible": False,
        },
        {
            "id": "fotoquadrado",
            "nome": "Fotoquadrado",
            "tipo": "pontos",
            "default_visible": False,
        },
    ]
    return {"layers": layers}


@app.get("/api/features/{layer_id}")
async def get_features(layer_id: str):
    """
    Retorna GeoJSON da camada especificada.
    No protótipo, buscamos arquivos .geojson na pasta app/data.
    No futuro, você pode trocar isso por consultas em PostGIS/GeoServer.
    """
    geojson_path = DATA_DIR / f"{layer_id}.geojson"
    if not geojson_path.exists():
        raise HTTPException(status_code=404, detail="Camada não encontrada")

    with geojson_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)


@app.get("/api/media/{feature_id}")
async def get_media(feature_id: str):
    """
    Retorna URLs de imagens/vídeos associadas a um ponto/estação.
    Aqui é mock. Depois você pode buscar em banco/S3.
    """
    # Exemplo simples: retorna sempre um conjunto de imagens de exemplo
    # baseado no ID (só para mostrar o carrossel funcionando).
    mock_media = {
        "imagens": [
            {
                "url": "https://via.placeholder.com/600x400?text=Foto+1",
                "descricao": "Foto 1 da campanha",
            },
            {
                "url": "https://via.placeholder.com/600x400?text=Foto+2",
                "descricao": "Foto 2 da campanha",
            },
        ],
        "videos": [
            {
                "url": "https://www.w3schools.com/html/mov_bbb.mp4",
                "descricao": "Vídeo de exemplo",
            }
        ],
    }
    return mock_media
