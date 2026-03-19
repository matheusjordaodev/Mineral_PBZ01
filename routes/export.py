import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional

import matplotlib
import matplotlib.pyplot as plt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Campanha, EspacoAmostral, FeicaoKml, Ilha

# Use a non-interactive backend
matplotlib.use("Agg")

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


try:
    import pyproj
    from shapely.ops import transform as _shp_transform
    _proj_4674 = pyproj.CRS("EPSG:4674")
    _proj_4326 = pyproj.CRS("EPSG:4326")
    _transformer_to_4674 = pyproj.Transformer.from_crs(_proj_4326, _proj_4674, always_xy=True)

    def _geom_to_4674(shp):
        return _shp_transform(_transformer_to_4674.transform, shp)
except Exception:
    def _geom_to_4674(shp):  # type: ignore
        return shp


def add_db_feature(features: List[Dict], geom, properties: Dict, feat_type: str) -> None:
    """Converte geometrias do banco em Feature GeoJSON reprojetando para EPSG:4674."""
    if not geom:
        return
    try:
        shp = _geom_to_4674(to_shape(geom))
        geojson_geom = mapping(shp)
        merged_props = {"type": feat_type, "origem": "banco"}
        merged_props.update(properties)
        features.append(
            {
                "type": "Feature",
                "geometry": geojson_geom,
                "properties": merged_props,
            }
        )
    except Exception as exc:
        print(f"Erro ao converter geometria do banco: {exc}")


def append_campaign_db_features(features: List[Dict], campanha: Campanha) -> None:
    """Inclui geometrias da campanha: feições KML importadas e métodos amostrais."""
    base_props = {
        "campanha_id": campanha.id,
        "campanha_nome": campanha.nome,
        "campanha_data": campanha.data_campanha.isoformat() if campanha.data_campanha else None,
    }

    # Feições KML/KMZ importadas (polígonos, linhas e pontos persistidos no PostGIS)
    for feicao in campanha.feicoes_kml:
        if feicao.deleted_at is not None:
            continue
        espaco = feicao.espaco_amostral
        props = {
            **base_props,
            "id": feicao.id,
            "nome": feicao.nome,
            "descricao": feicao.descricao,
            "arquivo_origem": feicao.arquivo_origem,
            "espaco_amostral_id": feicao.espaco_amostral_id,
            "espaco_codigo": espaco.codigo if espaco else None,
            "espaco_nome": espaco.nome if espaco else None,
            "ilha_id": feicao.ilha_id or (espaco.ilha_id if espaco else None),
            "origem": "upload_geoespacial",
            **(feicao.propriedades or {}),
        }
        add_db_feature(features, feicao.geom, props, feicao.tipo_geometria or "Feição KML")

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


def _ilha_centro(ilha) -> tuple:
    """Retorna (lon, lat) do centro da ilha ou (None, None)."""
    if ilha and ilha.localizacao:
        try:
            shp = to_shape(ilha.localizacao)
            if shp.geom_type == "Point":
                return float(shp.x), float(shp.y)
        except Exception:
            pass
    return None, None


def build_island_feature_collection(db: Session, ilha_id: int) -> Dict:
    """Monta uma FeatureCollection unica com dados de todas as campanhas da ilha."""
    campanhas = get_campaigns_for_ilha(db, ilha_id)
    features: List[Dict] = []

    for campanha in campanhas:
        append_campaign_db_features(features, campanha)

    ilha = db.query(Ilha).filter(Ilha.id == ilha_id).first()
    centro_lon, centro_lat = _ilha_centro(ilha)

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

    nomes_campanhas = ", ".join(c.nome for c in campanhas[:3]) if campanhas else ""
    if len(campanhas) > 3:
        nomes_campanhas += f" (+{len(campanhas) - 3})"
    ilha_nome = ilha.nome if ilha else f"Ilha {ilha_id}"
    titulo = f"{ilha_nome} — {nomes_campanhas} — SIRGAS 2000 (EPSG:4674)" if nomes_campanhas else f"{ilha_nome} — SIRGAS 2000 (EPSG:4674)"

    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}},
        "features": features,
        "properties": {
            "ilha_id": ilha_id,
            "ilha_nome": ilha_nome,
            "titulo": titulo,
            "total_campanhas": len(campanhas),
            "total_features": len(features),
            "total_poligonos": total_poligonos,
            "campanhas": campanha_meta,
            "centro_lon": centro_lon,
            "centro_lat": centro_lat,
        },
    }


def resolve_inkscape_binary() -> Optional[str]:
    configured = os.getenv("INKSCAPE_PATH", "").strip()
    if configured and Path(configured).exists():
        return configured

    from_path = shutil.which("inkscape.com") or shutil.which("inkscape")
    if from_path:
        return from_path

    common_paths = [
        r"C:\Program Files\Inkscape\bin\inkscape.com",
        r"C:\Program Files\Inkscape\bin\inkscape.exe",
        r"C:\Program Files (x86)\Inkscape\bin\inkscape.com",
        r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
    ]
    for candidate in common_paths:
        if Path(candidate).exists():
            return candidate
    return None


def convert_svg_to_wmf_bytes(svg_bytes: bytes) -> bytes:
    inkscape_bin = resolve_inkscape_binary()
    if not inkscape_bin:
        raise RuntimeError(
            "Inkscape nao encontrado. Instale o Inkscape ou configure INKSCAPE_PATH para habilitar exportacao WMF."
        )

    with tempfile.TemporaryDirectory(prefix="wmf_export_") as tmpdir:
        svg_path = Path(tmpdir) / "map.svg"
        wmf_path = Path(tmpdir) / "map.wmf"
        svg_path.write_bytes(svg_bytes)

        cmd = [
            inkscape_bin,
            str(svg_path),
            f"--export-filename={wmf_path}",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        if proc.returncode != 0:
            error_text = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"Inkscape falhou ao converter SVG para WMF (code {proc.returncode}): {error_text[:600]}")

        if not wmf_path.exists():
            raise RuntimeError("Inkscape concluiu sem gerar arquivo WMF.")

        return wmf_path.read_bytes()


def make_point_feature(lon: float, lat: float, properties: Dict) -> Dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }


def build_sampling_points_feature_collection(db: Session, ilha_id: int) -> Dict:
    """Monta FeatureCollection de pontos amostrais fixos da ilha."""
    ilha = db.query(Ilha).filter(Ilha.id == ilha_id).first()
    centro_lon, centro_lat = _ilha_centro(ilha)
    espacos = (
        db.query(EspacoAmostral)
        .filter(
            EspacoAmostral.ilha_id == ilha_id,
            EspacoAmostral.deleted_at == None,
            EspacoAmostral.latitude != None,
            EspacoAmostral.longitude != None,
        )
        .order_by(EspacoAmostral.codigo.asc(), EspacoAmostral.nome.asc())
        .all()
    )

    features: List[Dict] = []
    for ea in espacos:
        try:
            lat = float(ea.latitude)
            lon = float(ea.longitude)
        except (TypeError, ValueError):
            continue
        props = {
            "id": ea.id,
            "ilha_id": ea.ilha_id,
            "codigo": ea.codigo,
            "nome": ea.nome,
            "metodologia": ea.metodologia,
            "type": "Ponto Amostral",
            "origem": "espacos_amostrais",
        }
        features.append(make_point_feature(lon, lat, props))

    ilha_nome = ilha.nome if ilha else f"Ilha {ilha_id}"
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}},
        "features": features,
        "properties": {
            "ilha_id": ilha_id,
            "ilha_nome": ilha_nome,
            "total_features": len(features),
            "titulo": f"Pontos amostrais — {ilha_nome} — SIRGAS 2000 (EPSG:4674)",
            "filename": f"pontos_ilha_{ilha_id}.wmf",
            "centro_lon": centro_lon,
            "centro_lat": centro_lat,
        },
    }


def build_campaigns_feature_collection(db: Session, ilha_id: int) -> Dict:
    """Monta FeatureCollection de geometrias de campanhas realizadas na ilha."""
    payload = build_island_feature_collection(db, ilha_id)
    props = payload.get("properties") or {}
    ilha_nome = props.get("ilha_nome") or f"Ilha {ilha_id}"
    props["titulo"] = f"Campanhas realizadas - {ilha_nome}"
    props["filename"] = f"campanhas_ilha_{ilha_id}.wmf"
    payload["properties"] = props
    return payload


def build_island_points_feature_collection(db: Session, ilha_id: Optional[int] = None) -> Dict:
    """Monta FeatureCollection com pontos de localizacao das ilhas."""
    query = db.query(Ilha).filter(Ilha.deleted_at == None)
    if ilha_id is not None:
        query = query.filter(Ilha.id == ilha_id)
    ilhas = query.order_by(Ilha.nome.asc()).all()

    features: List[Dict] = []
    for ilha in ilhas:
        if not ilha.localizacao:
            continue
        try:
            shp = to_shape(ilha.localizacao)
            if shp.geom_type != "Point":
                continue
            props = {
                "id": ilha.id,
                "codigo": ilha.codigo,
                "nome": ilha.nome,
                "regiao": ilha.regiao,
                "type": "Ponto Ilha",
                "origem": "ilhas",
            }
            features.append(make_point_feature(float(shp.x), float(shp.y), props))
        except Exception:
            continue

    suffix = f"ilha_{ilha_id}" if ilha_id is not None else "todas_as_ilhas"
    titulo = "Pontos das ilhas — SIRGAS 2000 (EPSG:4674)"
    centro_lon, centro_lat = None, None
    if ilha_id is not None:
        target_nome = next((f.get("properties", {}).get("nome") for f in features), None)
        if target_nome:
            titulo = f"Ponto da ilha — {target_nome} — SIRGAS 2000 (EPSG:4674)"
        else:
            titulo = f"Ponto da ilha {ilha_id} — SIRGAS 2000 (EPSG:4674)"
        # Centro do único ponto exportado
        if features:
            coords = (features[0].get("geometry") or {}).get("coordinates") or []
            if len(coords) >= 2:
                centro_lon, centro_lat = float(coords[0]), float(coords[1])

    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}},
        "features": features,
        "properties": {
            "ilha_id": ilha_id,
            "total_features": len(features),
            "titulo": titulo,
            "filename": f"pontos_das_ilhas_{suffix}.wmf",
            "centro_lon": centro_lon,
            "centro_lat": centro_lat,
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
    elif method_type == "Ponto Amostral":
        color = "#00bcd4"
    elif method_type == "Ponto Ilha":
        color = "#9c27b0"
    else:
        color = "#6c757d"

    if geom_type == "Point":
        x, y = float(coords[0]), float(coords[1])
        ax.plot(x, y, "o", color=color, markersize=4, alpha=0.85)
        label = properties.get("codigo") or properties.get("nome") or properties.get("name") or ""
        coord_str = f"{y:.6f}, {x:.6f}"
        annotation = f"{label}\n({coord_str})" if label else coord_str
        ax.annotate(
            annotation,
            xy=(x, y),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=5,
            color="#222222",
            clip_on=True,
        )
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


def render_wmf_feature_collection(payload: Dict, default_filename: str) -> StreamingResponse:
    """Renderiza FeatureCollection e retorna WMF real para download."""
    props = payload.get("properties") or {}
    features = payload.get("features") or []

    fig, ax = plt.subplots(figsize=(10, 8))

    has_data = False
    for feature in features:
        if plot_geojson_feature(ax, feature):
            has_data = True

    if not has_data:
        ax.text(
            0.5,
            0.5,
            "Nenhuma geometria encontrada para esta exportacao",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )

    # Centraliza o mapa na coordenada da ilha com buffer fixo
    centro_lon = props.get("centro_lon")
    centro_lat = props.get("centro_lat")
    buffer_deg = props.get("buffer_deg", 0.05)  # ~5 km padrão
    if centro_lon is not None and centro_lat is not None:
        ax.set_xlim(centro_lon - buffer_deg, centro_lon + buffer_deg)
        ax.set_ylim(centro_lat - buffer_deg, centro_lat + buffer_deg)

    title = props.get("titulo")
    if not title:
        ilha_nome = props.get("ilha_nome") or "Ilha"
        total_campanhas = props.get("total_campanhas", 0)
        total_poligonos = props.get("total_poligonos", 0)
        title = f"Mapa - {ilha_nome} ({total_campanhas} campanhas, {total_poligonos} poligonos)"

    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Longitude (SIRGAS 2000 / EPSG:4674)")
    ax.set_ylabel("Latitude (SIRGAS 2000 / EPSG:4674)")
    ax.grid(True)

    # Garante precisão total (6 casas decimais) nos ticks — sem arredondamento
    import matplotlib.ticker as mticker
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.6f"))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.6f"))
    plt.xticks(rotation=45, ha="right", fontsize=7)
    plt.yticks(fontsize=7)
    plt.tight_layout()

    buf_svg = io.BytesIO()
    plt.savefig(buf_svg, format="svg")
    svg_bytes = buf_svg.getvalue()
    plt.close(fig)

    try:
        wmf_bytes = convert_svg_to_wmf_bytes(svg_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha na exportacao WMF: {exc}")

    filename = str(props.get("filename") or default_filename)
    if not filename.lower().endswith(".wmf"):
        filename = f"{filename}.wmf"

    return StreamingResponse(
        io.BytesIO(wmf_bytes),
        media_type="application/x-msmetafile",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
    ilha = db.query(Ilha).filter(Ilha.id == ilha_id).first()
    centro_lon, centro_lat = _ilha_centro(ilha)
    if ilha and ilha.localizacao:
        try:
            shp = to_shape(ilha.localizacao)
            if shp.geom_type == "Point":
                payload.setdefault("features", []).append(
                    make_point_feature(
                        float(shp.x),
                        float(shp.y),
                        {"type": "Ponto Ilha", "nome": ilha.nome, "origem": "ilhas"},
                    )
                )
        except Exception:
            pass
    # Garante centro no properties mesmo que já tenha sido setado em build_island_feature_collection
    if centro_lon is not None:
        payload.setdefault("properties", {})["centro_lon"] = centro_lon
        payload["properties"]["centro_lat"] = centro_lat
    return render_wmf_feature_collection(payload, f"mapa_ilha_{ilha_id}.wmf")


@router.get("/wmf/{ilha_id}/pontos")
async def export_wmf_pontos(ilha_id: int, db: Session = Depends(get_db)):
    """Exporta somente os pontos amostrais fixos da ilha em WMF (SVG)."""
    payload = build_sampling_points_feature_collection(db, ilha_id)
    return render_wmf_feature_collection(payload, f"pontos_ilha_{ilha_id}.wmf")


@router.get("/wmf/{ilha_id}/campanhas")
async def export_wmf_campanhas(ilha_id: int, db: Session = Depends(get_db)):
    """Exporta somente geometrias de campanhas realizadas na ilha em WMF (SVG)."""
    payload = build_campaigns_feature_collection(db, ilha_id)
    return render_wmf_feature_collection(payload, f"campanhas_ilha_{ilha_id}.wmf")


@router.get("/wmf/{ilha_id}/pontos-ilha")
async def export_wmf_ponto_ilha(ilha_id: int, db: Session = Depends(get_db)):
    """Exporta ponto de localizacao da ilha selecionada em WMF (SVG)."""
    payload = build_island_points_feature_collection(db, ilha_id=ilha_id)
    return render_wmf_feature_collection(payload, f"ponto_ilha_{ilha_id}.wmf")


@router.get("/wmf/global/pontos-ilhas")
async def export_wmf_pontos_ilhas(db: Session = Depends(get_db)):
    """Exporta pontos de localizacao de todas as ilhas em WMF (SVG)."""
    payload = build_island_points_feature_collection(db, ilha_id=None)
    return render_wmf_feature_collection(payload, "pontos_das_ilhas.wmf")


# ---------------------------------------------------------------------------
# Endpoints por ponto amostral (espaco_amostral_id)
# ---------------------------------------------------------------------------

def build_ponto_feature_collection(db: Session, espaco_amostral_id: int, campanha_id: Optional[int] = None) -> Dict:
    """Monta FeatureCollection com feições KML de um ponto amostral específico."""
    espaco = db.query(EspacoAmostral).filter(EspacoAmostral.id == espaco_amostral_id).first()
    if not espaco:
        return {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}},
            "features": [],
            "properties": {"total_features": 0},
        }

    ilha = db.query(Ilha).filter(Ilha.id == espaco.ilha_id).first()
    centro_lon, centro_lat = _ilha_centro(ilha)
    # Se o ponto tem coordenadas próprias, usa-as como centro
    if espaco.latitude and espaco.longitude:
        try:
            centro_lat = float(espaco.latitude)
            centro_lon = float(espaco.longitude)
        except (TypeError, ValueError):
            pass

    query = db.query(FeicaoKml).filter(
        FeicaoKml.espaco_amostral_id == espaco_amostral_id,
        FeicaoKml.deleted_at.is_(None),
    )
    if campanha_id is not None:
        query = query.filter(FeicaoKml.campanha_id == campanha_id)
    feicoes = query.all()

    features: List[Dict] = []
    for f in feicoes:
        if not f.geom:
            continue
        try:
            shp = _geom_to_4674(to_shape(f.geom))
            geom_dict = mapping(shp)
        except Exception:
            continue
        props = {
            "id": f.id,
            "nome": f.nome,
            "descricao": f.descricao or "",
            "espaco_amostral_id": espaco_amostral_id,
            "espaco_codigo": espaco.codigo,
            "espaco_nome": espaco.nome,
            "campanha_id": f.campanha_id,
            "type": f.tipo_geometria or "Feição KML",
            "origem": "feicoes_kml",
        }
        features.append({"type": "Feature", "geometry": geom_dict, "properties": props})

    # Inclui também o ponto fixo do espaço amostral
    if espaco.latitude and espaco.longitude:
        try:
            features.append(make_point_feature(
                float(espaco.longitude), float(espaco.latitude),
                {"type": "Ponto Amostral", "codigo": espaco.codigo, "nome": espaco.nome,
                 "metodologia": espaco.metodologia, "origem": "espacos_amostrais"},
            ))
        except (TypeError, ValueError):
            pass

    ilha_nome = ilha.nome if ilha else ""
    titulo = f"Ponto {espaco.codigo or espaco.nome} — {ilha_nome} — SIRGAS 2000 (EPSG:4674)"

    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}},
        "features": features,
        "properties": {
            "espaco_amostral_id": espaco_amostral_id,
            "espaco_codigo": espaco.codigo,
            "espaco_nome": espaco.nome,
            "ilha_nome": ilha_nome,
            "total_features": len(features),
            "titulo": titulo,
            "filename": f"ponto_{espaco.codigo or espaco_amostral_id}.wmf",
            "centro_lon": centro_lon,
            "centro_lat": centro_lat,
            "buffer_deg": 0.02,  # buffer menor — foco no ponto
        },
    }


@router.get("/wms/ponto/{espaco_amostral_id}")
async def export_wms_ponto(espaco_amostral_id: int, campanha_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Exporta geometrias KML de um ponto amostral em GeoJSON (SIRGAS 2000)."""
    payload = build_ponto_feature_collection(db, espaco_amostral_id, campanha_id)
    espaco_codigo = payload.get("properties", {}).get("espaco_codigo") or espaco_amostral_id
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f"attachment; filename=ponto_{espaco_codigo}_wms.geojson"},
    )


@router.get("/wmf/ponto/{espaco_amostral_id}")
async def export_wmf_ponto(espaco_amostral_id: int, campanha_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Exporta geometrias KML de um ponto amostral em WMF (SVG)."""
    payload = build_ponto_feature_collection(db, espaco_amostral_id, campanha_id)
    espaco_codigo = payload.get("properties", {}).get("espaco_codigo") or espaco_amostral_id
    return render_wmf_feature_collection(payload, f"ponto_{espaco_codigo}.wmf")
