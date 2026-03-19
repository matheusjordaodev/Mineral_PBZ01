"""
KML/KMZ Parser Utility
Extracts geometries and metadata from KML files
"""

import re
import xml.etree.ElementTree as ET
import zipfile
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


# Known KML namespaces in order of preference
_KML_NAMESPACES = [
    'http://www.opengis.net/kml/2.2',
    'http://www.opengis.net/kml/2.3',
    'http://earth.google.com/kml/2.2',
    'http://earth.google.com/kml/2.1',
    'http://earth.google.com/kml/2.0',
]


def _detect_ns(root: ET.Element) -> Dict[str, str]:
    """
    Detect the KML namespace from the root element tag or element text.
    Returns a namespace dict like {'kml': 'http://...'} or {} for bare tags.
    """
    tag = root.tag
    if tag.startswith('{'):
        ns_uri = tag[1:tag.index('}')]
        return {'kml': ns_uri}

    # Scan element tree for a known namespace
    raw = ET.tostring(root, encoding='unicode')
    for ns_uri in _KML_NAMESPACES:
        if ns_uri in raw:
            return {'kml': ns_uri}

    return {}  # no namespace — use bare tag names


def _find(elem: ET.Element, path: str, ns: Dict[str, str]) -> Optional[ET.Element]:
    """Find with namespace or bare (fallback)."""
    result = elem.find(path, ns) if ns else None
    if result is None:
        # Strip 'kml:' prefix and try bare
        bare_path = re.sub(r'kml:', '', path)
        result = elem.find(bare_path)
    return result


def _findall(elem: ET.Element, path: str, ns: Dict[str, str]) -> List[ET.Element]:
    """Findall with namespace or bare (fallback)."""
    results = elem.findall(path, ns) if ns else []
    if not results:
        bare_path = re.sub(r'kml:', '', path)
        results = elem.findall(bare_path)
    return results


_ZIP_MAGIC = b'PK\x03\x04'


def parse_kml_file(file_path) -> Dict[str, Any]:
    """
    Parse KML or KMZ file and extract geometries.
    Detecta arquivos KMZ (ZIP) pelo conteúdo, independente da extensão.

    Returns:
        Dictionary with geometries in GeoJSON format and metadata
    """
    file_path = Path(file_path)

    with open(file_path, 'rb') as f:
        header = f.read(4)
        f.seek(0)
        raw = f.read()

    # Detecta ZIP pelo magic bytes PK\x03\x04 — cobre KMZ renomeado como .kml
    is_zip = header.startswith(_ZIP_MAGIC)

    if is_zip or file_path.suffix.lower() == '.kmz':
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(raw), 'r') as z:
                kml_files = [f for f in z.namelist() if f.lower().endswith('.kml')]
                if not kml_files:
                    raise ValueError("No KML file found in KMZ archive")
                with z.open(kml_files[0]) as f:
                    kml_content = f.read()
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Arquivo ZIP inválido ou corrompido: {exc}")
    else:
        kml_content = raw

    return parse_kml_content(kml_content)


def parse_kml_content(kml_content: bytes) -> Dict[str, Any]:
    """
    Parse KML content and extract geometries.

    Returns:
        {
            "type": "FeatureCollection",
            "features": [...],
            "metadata": {...}
        }
    """
    # Normaliza encoding antes de parsear
    # 1. UTF-8 BOM
    if kml_content.startswith(b'\xef\xbb\xbf'):
        kml_content = kml_content[3:]
    # 2. UTF-16 BOM (LE ou BE)
    elif kml_content.startswith(b'\xff\xfe') or kml_content.startswith(b'\xfe\xff'):
        try:
            kml_content = kml_content.decode('utf-16').encode('utf-8')
        except Exception:
            pass
    # 3. UTF-16 LE sem BOM — começa com '<\x00' (byte nulo na posição 2 causa "invalid token")
    elif len(kml_content) >= 2 and kml_content[0:2] in (b'<\x00', b'\x00<'):
        try:
            enc = 'utf-16-le' if kml_content[0:2] == b'<\x00' else 'utf-16-be'
            kml_content = kml_content.decode(enc).encode('utf-8')
        except Exception:
            pass
    # 4. Remove possível declaração XML com encoding incompatível antes de re-encodar
    if kml_content.startswith(b'<?xml'):
        # Substitui declaração para forçar UTF-8
        end = kml_content.find(b'?>')
        if end != -1:
            kml_content = b'<?xml version="1.0" encoding="UTF-8"?>' + kml_content[end + 2:]

    try:
        root = ET.fromstring(kml_content)
    except ET.ParseError:
        # Tenta latin-1
        try:
            root = ET.fromstring(kml_content.decode('latin-1').encode('utf-8'))
        except ET.ParseError:
            # Última tentativa: remove caracteres de controle e tenta novamente
            try:
                clean = bytes(b for b in kml_content if b >= 0x09)
                root = ET.fromstring(clean)
            except ET.ParseError as e:
                raise ValueError(f"Invalid KML: {e}")

    ns = _detect_ns(root)

    features = []
    metadata = {
        "document_name": None,
        "description": None,
        "placemark_count": 0
    }

    # Document info
    doc = _find(root, './/kml:Document', ns)
    if doc is not None:
        name_elem = _find(doc, 'kml:name', ns)
        if name_elem is not None:
            metadata["document_name"] = name_elem.text
        desc_elem = _find(doc, 'kml:description', ns)
        if desc_elem is not None:
            metadata["description"] = desc_elem.text

    # Extract all Placemarks
    for placemark in _findall(root, './/kml:Placemark', ns):
        feature = extract_placemark(placemark, ns)
        if feature:
            features.append(feature)
            metadata["placemark_count"] += 1

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": metadata
    }


def extract_placemark(placemark: ET.Element, ns: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Extract a single Placemark as a GeoJSON Feature."""

    name_elem = _find(placemark, 'kml:name', ns)
    name_text = (name_elem.text or '').strip() if name_elem is not None else "Unnamed"

    desc_elem = _find(placemark, 'kml:description', ns)
    desc_text = (desc_elem.text or '').strip() if desc_elem is not None else ""

    geometry = None

    # Point
    point = _find(placemark, './/kml:Point/kml:coordinates', ns)
    if point is not None and point.text:
        try:
            geometry = parse_point(point.text)
        except Exception:
            pass

    # LineString
    if geometry is None:
        ls = _find(placemark, './/kml:LineString/kml:coordinates', ns)
        if ls is not None and ls.text:
            try:
                geometry = parse_linestring(ls.text)
            except Exception:
                pass

    # Polygon (com suporte a buracos innerBoundaryIs)
    if geometry is None:
        poly_elem = _find(placemark, './/kml:Polygon', ns)
        if poly_elem is not None:
            outer = _find(poly_elem, './/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
            if outer is not None and outer.text:
                try:
                    rings = [parse_ring(outer.text)]
                    for inner in _findall(poly_elem, 'kml:innerBoundaryIs/kml:LinearRing/kml:coordinates', ns):
                        if inner.text:
                            rings.append(parse_ring(inner.text))
                    geometry = {"type": "Polygon", "coordinates": rings}
                except Exception:
                    pass

    # MultiGeometry — recurse e monta GeometryCollection
    if geometry is None:
        multi = _find(placemark, './/kml:MultiGeometry', ns)
        if multi is not None:
            geoms = []
            for child in multi:
                tag_local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                try:
                    if tag_local == 'Point':
                        coords_elem = _find(child, 'kml:coordinates', ns)
                        if coords_elem is not None and coords_elem.text:
                            geoms.append(parse_point(coords_elem.text))
                    elif tag_local == 'LineString':
                        coords_elem = _find(child, 'kml:coordinates', ns)
                        if coords_elem is not None and coords_elem.text:
                            geoms.append(parse_linestring(coords_elem.text))
                    elif tag_local == 'Polygon':
                        outer = _find(child, './/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
                        if outer is not None and outer.text:
                            rings = [parse_ring(outer.text)]
                            for inner in _findall(child, 'kml:innerBoundaryIs/kml:LinearRing/kml:coordinates', ns):
                                if inner.text:
                                    rings.append(parse_ring(inner.text))
                            geoms.append({"type": "Polygon", "coordinates": rings})
                except Exception:
                    pass
            if len(geoms) == 1:
                geometry = geoms[0]
            elif geoms:
                geometry = {'type': 'GeometryCollection', 'geometries': geoms}

    if geometry is None:
        return None

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "name": name_text,
            "description": desc_text
        }
    }


def parse_ring(coords_text: str) -> list:
    """Converte texto de coordenadas KML em lista de [lon, lat]."""
    ring = []
    for token in coords_text.strip().split():
        if token:
            parts = token.split(',')
            if len(parts) >= 2:
                ring.append([float(parts[0]), float(parts[1])])
    return ring


def parse_point(coords_text: str) -> Dict[str, Any]:
    coords = coords_text.strip().split(',')
    lon, lat = float(coords[0]), float(coords[1])
    return {"type": "Point", "coordinates": [lon, lat]}


def parse_linestring(coords_text: str) -> Dict[str, Any]:
    return {"type": "LineString", "coordinates": parse_ring(coords_text)}


def parse_polygon(coords_text: str) -> Dict[str, Any]:
    """Converte apenas o anel externo. Para buracos use parse_ring diretamente."""
    return {"type": "Polygon", "coordinates": [parse_ring(coords_text)]}


def kml_to_geojson_file(kml_path: str, output_path: str) -> None:
    result = parse_kml_file(kml_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = parse_kml_file(sys.argv[1])
        print(json.dumps(result, indent=2))
