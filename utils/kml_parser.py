"""
KML/KMZ Parser Utility
Extracts geometries and metadata from KML files
"""

import xml.etree.ElementTree as ET
import zipfile
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_kml_file(file_path: str) -> Dict[str, Any]:
    """
    Parse KML or KMZ file and extract geometries
    
    Args:
        file_path: Path to KML or KMZ file
        
    Returns:
        Dictionary with geometries in GeoJSON format and metadata
    """
    file_path = Path(file_path)
    
    # Handle KMZ (zip) files
    if file_path.suffix.lower() == '.kmz':
        with zipfile.ZipFile(file_path, 'r') as z:
            kml_files = [f for f in z.namelist() if f.lower().endswith('.kml')]
            if not kml_files:
                raise ValueError("No KML file found in KMZ archive")
            
            with z.open(kml_files[0]) as f:
                kml_content = f.read()
    else:
        with open(file_path, 'rb') as f:
            kml_content = f.read()
    
    return parse_kml_content(kml_content)


def parse_kml_content(kml_content: bytes) -> Dict[str, Any]:
    """
    Parse KML content and extract geometries
    
    Returns:
        {
            "type": "FeatureCollection",
            "features": [...],
            "metadata": {...}
        }
    """
    try:
        root = ET.fromstring(kml_content)
    except ET.ParseError as e:
        raise ValueError(f"Invalid KML: {e}")
    
    # Namespace handling
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    
    features = []
    metadata = {
        "document_name": None,
        "description": None,
        "placemark_count": 0
    }
    
    # Get document info
    doc = root.find('.//kml:Document', ns)
    if doc is not None:
        name_elem = doc.find('kml:name', ns)
        if name_elem is not None:
            metadata["document_name"] = name_elem.text
        
        desc_elem = doc.find('kml:description', ns)
        if desc_elem is not None:
            metadata["description"] = desc_elem.text
    
    # Extract Placemarks
    for placemark in root.findall('.//kml:Placemark', ns):
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
    """Extract a single Placemark as GeoJSON Feature"""
    
    # Get name and description
    name = placemark.find('kml:name', ns)
    name_text = name.text if name is not None else "Unnamed"
    
    description = placemark.find('kml:description', ns)
    desc_text = description.text if description is not None else ""
    
    # Try to extract geometry
    geometry = None
    
    # Point
    point = placemark.find('.//kml:Point/kml:coordinates', ns)
    if point is not None:
        geometry = parse_point(point.text)
    
    # LineString
    if geometry is None:
        linestring = placemark.find('.//kml:LineString/kml:coordinates', ns)
        if linestring is not None:
            geometry = parse_linestring(linestring.text)
    
    # Polygon
    if geometry is None:
        polygon = placemark.find('.//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
        if polygon is not None:
            geometry = parse_polygon(polygon.text)
    
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


def parse_point(coords_text: str) -> Dict[str, Any]:
    """Parse Point coordinates"""
    coords = coords_text.strip().split(',')
    lon, lat = float(coords[0]), float(coords[1])
    
    return {
        "type": "Point",
        "coordinates": [lon, lat]
    }


def parse_linestring(coords_text: str) -> Dict[str, Any]:
    """Parse LineString coordinates"""
    coordinates = []
    for line in coords_text.strip().split():
        if line:
            parts = line.split(',')
            if len(parts) >= 2:
                lon, lat = float(parts[0]), float(parts[1])
                coordinates.append([lon, lat])
    
    return {
        "type": "LineString",
        "coordinates": coordinates
    }


def parse_polygon(coords_text: str) -> Dict[str, Any]:
    """Parse Polygon coordinates"""
    coordinates = []
    for line in coords_text.strip().split():
        if line:
            parts = line.split(',')
            if len(parts) >= 2:
                lon, lat = float(parts[0]), float(parts[1])
                coordinates.append([lon, lat])
    
    # Polygon needs array of rings
    return {
        "type": "Polygon",
        "coordinates": [coordinates]
    }


def kml_to_geojson_file(kml_path: str, output_path: str) -> None:
    """
    Convert KML file to GeoJSON file
    
    Args:
        kml_path: Path to input KML/KMZ
        output_path: Path to output GeoJSON
    """
    result = parse_kml_file(kml_path)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # Test with example file
    import sys
    if len(sys.argv) > 1:
        result = parse_kml_file(sys.argv[1])
        print(json.dumps(result, indent=2))
