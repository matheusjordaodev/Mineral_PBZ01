import base64
import json
import os
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from fastapi import APIRouter, Depends

from db.models import Usuario
from routes.auth import get_current_active_user

router = APIRouter(prefix="/api/geoserver", tags=["geoserver"])


def _read_settings() -> Dict[str, object]:
    timeout_raw = os.getenv("GEOSERVER_TIMEOUT_SECONDS", "15").strip()
    try:
        timeout_seconds = max(float(timeout_raw), 1.0)
    except ValueError:
        timeout_seconds = 15.0

    return {
        "base_url": os.getenv("GEOSERVER_URL", "http://geoserver:8080/geoserver").strip().rstrip("/"),
        "workspace": os.getenv("GEOSERVER_WORKSPACE", "pmascc").strip(),
        "ilhas_layer": os.getenv("GEOSERVER_ILHAS_LAYER", "ilhas").strip(),
        "pontos_layer": os.getenv("GEOSERVER_PONTOS_LAYER", "vw_espacos_amostrais_geo").strip(),
        "public_wms_url": os.getenv(
            "GEOSERVER_PUBLIC_WMS_URL", "http://localhost:8081/geoserver/wms"
        ).strip(),
        "wms_layers": os.getenv("GEOSERVER_WMS_LAYERS", "").strip(),
        "user": os.getenv("GEOSERVER_DATA_USER", "").strip(),
        "password": os.getenv("GEOSERVER_DATA_PASSWORD", ""),
        "timeout_seconds": timeout_seconds,
    }


def _qualified_typename(workspace: str, layer: str) -> str:
    if not layer:
        return ""
    if ":" in layer:
        return layer
    if not workspace:
        return layer
    return f"{workspace}:{layer}"


def _iter_coord_pairs(coords) -> Iterable[Tuple[float, float]]:
    if not isinstance(coords, list) or not coords:
        return
    first = coords[0]
    if isinstance(first, (int, float)) and len(coords) >= 2:
        lon = float(coords[0])
        lat = float(coords[1])
        yield lon, lat
        return
    for nested in coords:
        yield from _iter_coord_pairs(nested)


def _extract_lat_lon(geometry: Optional[Dict]) -> Optional[Tuple[float, float]]:
    if not isinstance(geometry, dict):
        return None
    geom_type = str(geometry.get("type") or "")
    coords = geometry.get("coordinates")
    if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return float(coords[1]), float(coords[0])

    pairs = list(_iter_coord_pairs(coords))
    if not pairs:
        return None

    lons = [p[0] for p in pairs]
    lats = [p[1] for p in pairs]
    center_lon = (min(lons) + max(lons)) / 2.0
    center_lat = (min(lats) + max(lats)) / 2.0
    return center_lat, center_lon


def _build_request(url: str, user: str, password: str) -> Request:
    req = Request(url)
    if user:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")
    return req


def _fetch_wfs_feature_collection(settings: Dict[str, object], typename: str) -> Dict:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": typename,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    query = urlencode(params)
    url = f"{settings['base_url']}/wfs?{query}"
    req = _build_request(url, str(settings["user"]), str(settings["password"]))

    try:
        with urlopen(req, timeout=float(settings["timeout_seconds"])) as response:
            content = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GeoServer HTTP {exc.code}: {detail[:250]}") from exc
    except URLError as exc:
        raise RuntimeError(f"GeoServer unavailable: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"GeoServer request failed: {exc}") from exc

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GeoServer returned invalid JSON payload") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("GeoServer response is not a JSON object")
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError("GeoServer response does not contain a features list")
    return payload


def _fetch_wfs_feature_type_names(settings: Dict[str, object]) -> List[str]:
    params = {
        "service": "WFS",
        "request": "GetCapabilities",
    }
    url = f"{settings['base_url']}/wfs?{urlencode(params)}"
    req = _build_request(url, str(settings["user"]), str(settings["password"]))

    try:
        with urlopen(req, timeout=float(settings["timeout_seconds"])) as response:
            content = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(f"Nao foi possivel ler GetCapabilities: {exc}") from exc

    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise RuntimeError("GetCapabilities retornou XML invalido") from exc

    feature_type_names: List[str] = []
    for feature_type in root.iter():
        if not str(feature_type.tag).endswith("FeatureType"):
            continue
        for node in feature_type:
            if str(node.tag).endswith("Name") and (node.text or "").strip():
                feature_type_names.append((node.text or "").strip())
                break

    # Keep insertion order, drop duplicates.
    seen = set()
    ordered_names = []
    for name in feature_type_names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered_names.append(name)
    return ordered_names


def _select_feature_type(
    configured_name: str,
    available_names: List[str],
    preferred_workspace: str,
    keywords: List[str],
) -> str:
    if not available_names:
        return configured_name

    lower_map = {n.lower(): n for n in available_names}
    direct = lower_map.get(configured_name.lower())
    if direct:
        return direct

    ws_lower = preferred_workspace.lower()
    best_name = ""
    best_score = -1
    for name in available_names:
        full = name.lower()
        short = full.split(":")[-1]

        score = 0
        if ws_lower and full.startswith(ws_lower + ":"):
            score += 4
        for kw in keywords:
            if kw in short:
                score += 3
            elif kw in full:
                score += 1
        if score > best_score:
            best_score = score
            best_name = name

    if best_score <= 0:
        return configured_name
    return best_name


@router.get("/locations")
async def get_geoserver_locations(current_user: Usuario = Depends(get_current_active_user)):
    settings = _read_settings()
    ilhas_typename_cfg = _qualified_typename(str(settings["workspace"]), str(settings["ilhas_layer"]))
    pontos_typename_cfg = _qualified_typename(str(settings["workspace"]), str(settings["pontos_layer"]))

    warnings: List[str] = []
    ilhas_payload: Dict = {"features": []}
    pontos_payload: Dict = {"features": []}
    resolved_ilhas_typename = ilhas_typename_cfg
    resolved_pontos_typename = pontos_typename_cfg

    feature_type_names: List[str] = []
    try:
        feature_type_names = _fetch_wfs_feature_type_names(settings)
    except Exception as exc:
        warnings.append(str(exc))

    if feature_type_names:
        resolved_ilhas_typename = _select_feature_type(
            ilhas_typename_cfg,
            feature_type_names,
            str(settings["workspace"]),
            ["ilha"],
        )
        resolved_pontos_typename = _select_feature_type(
            pontos_typename_cfg,
            feature_type_names,
            str(settings["workspace"]),
            ["estacao", "espaco", "ponto"],
        )
        if resolved_ilhas_typename.lower() != ilhas_typename_cfg.lower():
            warnings.append(
                f"Camada de ilhas configurada como {ilhas_typename_cfg}, usando autodeteccao: {resolved_ilhas_typename}"
            )
        if resolved_pontos_typename.lower() != pontos_typename_cfg.lower():
            warnings.append(
                f"Camada de pontos configurada como {pontos_typename_cfg}, usando autodeteccao: {resolved_pontos_typename}"
            )

    try:
        ilhas_payload = _fetch_wfs_feature_collection(settings, resolved_ilhas_typename)
    except Exception as exc:
        warnings.append(f"Falha ao carregar camada de ilhas ({resolved_ilhas_typename}): {exc}")

    try:
        pontos_payload = _fetch_wfs_feature_collection(settings, resolved_pontos_typename)
    except Exception as exc:
        warnings.append(f"Falha ao carregar camada de pontos ({resolved_pontos_typename}): {exc}")

    ilhas_out: List[Dict] = []
    for feature in ilhas_payload.get("features", []):
        props = feature.get("properties") if isinstance(feature, dict) else None
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(props, dict):
            continue
        lat_lon = _extract_lat_lon(geometry)
        if lat_lon is None:
            continue
        ilhas_out.append(
            {
                "id": props.get("id"),
                "codigo": props.get("codigo"),
                "nome": props.get("nome"),
                "coords": [lat_lon[0], lat_lon[1]],
                "geometry": geometry,
            }
        )

    pontos_by_space_id: Dict[str, Dict] = {}
    pontos_out: List[Dict] = []
    for feature in pontos_payload.get("features", []):
        props = feature.get("properties") if isinstance(feature, dict) else None
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(props, dict):
            continue

        lat_lon = _extract_lat_lon(geometry)
        if lat_lon is None:
            lat_raw = props.get("latitude")
            lon_raw = props.get("longitude")
            try:
                lat_val = float(lat_raw)
                lon_val = float(lon_raw)
                lat_lon = (lat_val, lon_val)
            except (TypeError, ValueError):
                lat_lon = None
        if lat_lon is None:
            continue

        espaco_id = props.get("espaco_amostral_id")
        if espaco_id is None:
            espaco_id = props.get("espaco_id")
        if espaco_id is None:
            espaco_id = props.get("id")

        point_item = {
            "id": props.get("id"),
            "espaco_amostral_id": espaco_id,
            "ilha_id": props.get("ilha_id"),
            "codigo": props.get("codigo"),
            "nome": props.get("nome"),
            "latitude": lat_lon[0],
            "longitude": lat_lon[1],
        }

        space_key = str(espaco_id) if espaco_id is not None else ""
        if space_key:
            existing = pontos_by_space_id.get(space_key)
            if existing is None:
                pontos_by_space_id[space_key] = point_item
            else:
                old_id = existing.get("id")
                new_id = point_item.get("id")
                try:
                    if int(new_id) > int(old_id):
                        pontos_by_space_id[space_key] = point_item
                except Exception:
                    pass
        else:
            pontos_out.append(point_item)

    pontos_out.extend(pontos_by_space_id.values())
    using_geoserver = bool(ilhas_out or pontos_out)

    resolved_wms_layers = str(settings.get("wms_layers") or "").strip()
    if not resolved_wms_layers:
        if resolved_ilhas_typename:
            resolved_wms_layers = resolved_ilhas_typename
        elif resolved_pontos_typename:
            resolved_wms_layers = resolved_pontos_typename

    return {
        "enabled": True,
        "source": "geoserver" if using_geoserver else "fallback",
        "config": {
            "base_url": settings["base_url"],
            "workspace": settings["workspace"],
            "ilhas_typename": resolved_ilhas_typename,
            "pontos_typename": resolved_pontos_typename,
            "public_wms_url": settings["public_wms_url"],
            "wms_layers": resolved_wms_layers,
        },
        "warnings": warnings,
        "ilhas": ilhas_out,
        "pontos": pontos_out,
    }
