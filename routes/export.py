import io
import json
from pathlib import Path
from typing import Dict, List

import matplotlib
import matplotlib.pyplot as plt
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Campanha, Ilha
from services import CampanhaService, FileService

# Use a non-interactive backend
matplotlib.use("Agg")

UPLOAD_DIR = Path("app/uploads")
campanha_service = CampanhaService(UPLOAD_DIR)
file_service = FileService(UPLOAD_DIR)

router = APIRouter(prefix="/api/export", tags=["export"])


def get_campaigns_for_ilha(db: Session, ilha_id: int) -> List[Campanha]:
    """Busca campanhas da ilha considerando relacao M:N e coluna legada ilha_id."""
    return (
        db.query(Campanha)
        .outerjoin(Campanha.ilhas)
        .filter(or_(Campanha.ilha_id == ilha_id, Ilha.id == ilha_id))
        .order_by(desc(Campanha.data_campanha), desc(Campanha.id))
        .distinct()
        .all()
    )


def add_db_feature(features: List[Dict], geom, properties: Dict, feat_type: str) -> None:
    """Converte geometrias do banco em Feature GeoJSON."""
    if not geom:
        return
    try:
        shp = to_shape(geom)
        geojson_geom = mapping(shp)
        features.append(
            {
                "type": "Feature",
                "geometry": geojson_geom,
                "properties": {**properties, "type": feat_type, "origem": "banco"},
            }
        )
    except Exception as exc:
        print(f"Erro ao converter geometria do banco: {exc}")


def append_campaign_db_features(features: List[Dict], campanha: Campanha) -> None:
    """Inclui geometria dos metodos amostrais da campanha."""
    base_props = {
        "campanha_id": campanha.id,
        "campanha_nome": campanha.nome,
        "campanha_data": campanha.data_campanha.isoformat() if campanha.data_campanha else None,
    }

    for estacao in campanha.estacoes_amostrais:
        for ba in estacao.buscas_ativas:
            props = {
                **base_props,
                "id": ba.id,
                "estacao": estacao.numero,
                "data": ba.data.isoformat() if ba.data else None,
                "encontrou_coral_sol": ba.encontrou_coral_sol,
            }
            add_db_feature(features, ba.trilha, props, "Busca Ativa")

        for vt in estacao.video_transectos:
            props = {
                **base_props,
                "id": vt.id,
                "estacao": estacao.numero,
                "data": vt.data.isoformat() if vt.data else None,
            }
            add_db_feature(features, vt.trilha, props, "Video Transecto")

        for fq in estacao.fotoquadrados:
            props = {
                **base_props,
                "id": fq.id,
                "estacao": estacao.numero,
                "data": fq.data.isoformat() if fq.data else None,
            }
            add_db_feature(features, fq.localizacao, props, "Fotoquadrado")


def append_campaign_uploaded_features(features: List[Dict], campanha: Campanha, ilha_id: int) -> None:
    """
    Inclui features vindas de uploads geoespaciais da campanha (KML/KMZ convertidos em GeoJSON).
    Aqui ficam os poligonos enviados em campo.
    """
    folder_name = f"{campanha.id}_{campanha.codigo}"

    if not campanha_service.campanha_exists(str(ilha_id), folder_name):
        return

    geojson = file_service.get_geojson(str(ilha_id), folder_name)
    for feature in geojson.get("features", []):
        if not isinstance(feature, dict) or not feature.get("geometry"):
            continue

        props = dict(feature.get("properties") or {})
        props["campanha_id"] = campanha.id
        props["campanha_nome"] = campanha.nome
        props["campanha_data"] = campanha.data_campanha.isoformat() if campanha.data_campanha else None
        props["origem"] = "upload_geoespacial"

        features.append(
            {
                "type": "Feature",
                "geometry": feature.get("geometry"),
                "properties": props,
            }
        )

    # Complemento: inclui arquivos GeoJSON nativos enviados na campanha.
    geospatial_dir = campanha_service.get_campanha_path(str(ilha_id), folder_name) / "geospatial"
    if not geospatial_dir.exists():
        return

    for geojson_file in geospatial_dir.glob("*"):
        if geojson_file.suffix.lower() not in {".geojson", ".json"}:
            continue
        try:
            payload = json.loads(geojson_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        raw_features = []
        if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
            raw_features = payload.get("features") or []
        elif isinstance(payload, dict) and payload.get("type") == "Feature":
            raw_features = [payload]

        for feature in raw_features:
            if not isinstance(feature, dict) or not feature.get("geometry"):
                continue

            props = dict(feature.get("properties") or {})
            props["campanha_id"] = campanha.id
            props["campanha_nome"] = campanha.nome
            props["campanha_data"] = campanha.data_campanha.isoformat() if campanha.data_campanha else None
            props["origem"] = "upload_geojson"
            props["arquivo"] = geojson_file.name

            features.append(
                {
                    "type": "Feature",
                    "geometry": feature.get("geometry"),
                    "properties": props,
                }
            )


def build_island_feature_collection(db: Session, ilha_id: int) -> Dict:
    """Monta uma FeatureCollection unica com dados de todas as campanhas da ilha."""
    campanhas = get_campaigns_for_ilha(db, ilha_id)
    features: List[Dict] = []

    for campanha in campanhas:
        append_campaign_db_features(features, campanha)
        append_campaign_uploaded_features(features, campanha, ilha_id)

    ilha = db.query(Ilha).filter(Ilha.id == ilha_id).first()
    campanha_meta = [
        {
            "id": c.id,
            "nome": c.nome,
            "data": c.data_campanha.isoformat() if c.data_campanha else None,
        }
        for c in campanhas
    ]

    total_poligonos = 0
    for feature in features:
        geom = feature.get("geometry") or {}
        if geom.get("type") in {"Polygon", "MultiPolygon"}:
            total_poligonos += 1

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "ilha_id": ilha_id,
            "ilha_nome": ilha.nome if ilha else None,
            "total_campanhas": len(campanhas),
            "total_features": len(features),
            "total_poligonos": total_poligonos,
            "campanhas": campanha_meta,
        },
    }


def plot_geojson_feature(ax, feature: Dict) -> bool:
    """Desenha uma feature GeoJSON no eixo e retorna True quando plota algo."""
    geometry = feature.get("geometry") or {}
    properties = feature.get("properties") or {}
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")

    if not coords:
        return False

    method_type = properties.get("type")
    if geom_type in {"Polygon", "MultiPolygon"}:
        color = "#ff8c00"
    elif method_type == "Busca Ativa":
        color = "#1f77b4"
    elif method_type == "Video Transecto":
        color = "#2ca02c"
    elif method_type == "Fotoquadrado":
        color = "#d62728"
    else:
        color = "#6c757d"

    if geom_type == "Point":
        x, y = coords[0], coords[1]
        ax.plot(x, y, "o", color=color, markersize=4, alpha=0.85)
        return True

    if geom_type == "LineString":
        if len(coords) < 2:
            return False
        x_vals = [pt[0] for pt in coords if len(pt) >= 2]
        y_vals = [pt[1] for pt in coords if len(pt) >= 2]
        if not x_vals or not y_vals:
            return False
        linestyle = "--" if method_type == "Video Transecto" else "-"
        ax.plot(x_vals, y_vals, color=color, alpha=0.75, linewidth=1.8, linestyle=linestyle)
        return True

    if geom_type == "Polygon":
        ring = coords[0] if coords else []
        x_vals = [pt[0] for pt in ring if len(pt) >= 2]
        y_vals = [pt[1] for pt in ring if len(pt) >= 2]
        if not x_vals or not y_vals:
            return False
        ax.plot(x_vals, y_vals, color=color, alpha=0.9, linewidth=1.8)
        return True

    if geom_type == "MultiPolygon":
        plotted = False
        for polygon in coords:
            ring = polygon[0] if polygon else []
            x_vals = [pt[0] for pt in ring if len(pt) >= 2]
            y_vals = [pt[1] for pt in ring if len(pt) >= 2]
            if not x_vals or not y_vals:
                continue
            ax.plot(x_vals, y_vals, color=color, alpha=0.9, linewidth=1.8)
            plotted = True
        return plotted

    return False


@router.get("/wms/{ilha_id}")
async def export_wms(ilha_id: int, db: Session = Depends(get_db)):
    """
    Exporta geometrias em GeoJSON para a ilha selecionada.
    Inclui dados de TODAS as campanhas da ilha, com foco em poligonos enviados.
    """
    payload = build_island_feature_collection(db, ilha_id)
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f"attachment; filename=ilha_{ilha_id}_wms.geojson"},
    )


@router.get("/wfs/{ilha_id}")
async def export_wfs(ilha_id: int, db: Session = Depends(get_db)):
    """
    Alias de compatibilidade legada.
    Mantido para clientes antigos, retornando o mesmo payload do WMS.
    """
    return await export_wms(ilha_id, db)


@router.get("/wmf/{ilha_id}")
async def export_wmf(ilha_id: int, db: Session = Depends(get_db)):
    """
    Gera mapa vetorial (SVG) consolidado por ilha.
    Inclui geometrias de todas as campanhas vinculadas.
    """
    payload = build_island_feature_collection(db, ilha_id)
    props = payload.get("properties") or {}
    features = payload.get("features") or []

    fig, ax = plt.subplots(figsize=(10, 8))

    has_data = False
    for feature in features:
        if plot_geojson_feature(ax, feature):
            has_data = True

    ilha = db.query(Ilha).filter(Ilha.id == ilha_id).first()
    if ilha and ilha.localizacao:
        try:
            shp = to_shape(ilha.localizacao)
            if shp.geom_type == "Point":
                ax.plot(shp.x, shp.y, "k*", markersize=12)
        except Exception:
            pass

    if not has_data:
        ax.text(
            0.5,
            0.5,
            "Nenhuma geometria encontrada para esta ilha",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )

    ilha_nome = props.get("ilha_nome") or f"Ilha {ilha_id}"
    total_campanhas = props.get("total_campanhas", 0)
    total_poligonos = props.get("total_poligonos", 0)
    ax.set_title(f"Mapa - {ilha_nome} ({total_campanhas} campanhas, {total_poligonos} poligonos)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format="svg")
    buf.seek(0)
    plt.close(fig)

    return StreamingResponse(
        buf,
        media_type="image/svg+xml",
        headers={"Content-Disposition": f"attachment; filename=mapa_ilha_{ilha_id}.svg"},
    )
