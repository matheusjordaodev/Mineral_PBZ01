"""
Validation utilities for KML and KMZ files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
import zipfile

from utils.kml_parser import _detect_ns, _find, _findall, parse_linestring, parse_point, parse_polygon


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _make_result(file_path: Path) -> Dict[str, Any]:
    return {
        "input_file": str(file_path.resolve()),
        "valid": False,
        "file_type": file_path.suffix.lower(),
        "embedded_kml": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "errors": [],
        "warnings": [],
        "metadata": {
            "document_name": None,
            "description": None,
            "namespace": None,
            "placemark_count": 0,
            "valid_feature_count": 0,
        },
        "placemarks": [],
        "geojson": {
            "type": "FeatureCollection",
            "features": [],
            "metadata": {},
        },
        "output_files": {},
    }


def _add_issue(result: Dict[str, Any], level: str, message: str) -> None:
    result[f"{level}s"].append(message)


def _read_kml_bytes(file_path: Path) -> Tuple[bytes, Optional[str]]:
    suffix = file_path.suffix.lower()
    if suffix not in {".kml", ".kmz"}:
        raise ValueError("Extensao nao suportada. Use um arquivo .kml ou .kmz.")

    if suffix == ".kml":
        return file_path.read_bytes(), None

    try:
        with zipfile.ZipFile(file_path, "r") as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".kml")]
            if not members:
                raise ValueError("O arquivo KMZ nao contem nenhum arquivo .kml interno.")

            embedded_name = next(
                (name for name in members if Path(name).name.lower() == "doc.kml"),
                members[0],
            )
            return archive.read(embedded_name), embedded_name
    except zipfile.BadZipFile as exc:
        raise ValueError("O arquivo KMZ nao e um zip valido.") from exc


def _parse_geometry(kind: str, coords_text: str) -> Dict[str, Any]:
    if kind == "Point":
        geometry = parse_point(coords_text)
        if len(geometry["coordinates"]) != 2:
            raise ValueError("Point exige longitude e latitude.")
        return geometry

    if kind == "LineString":
        geometry = parse_linestring(coords_text)
        if len(geometry["coordinates"]) < 2:
            raise ValueError("LineString exige pelo menos dois pontos.")
        return geometry

    if kind == "Polygon":
        geometry = parse_polygon(coords_text)
        ring = geometry["coordinates"][0]
        if len(ring) < 4:
            raise ValueError("Polygon exige ao menos quatro coordenadas.")
        return geometry

    raise ValueError(f"Geometria nao suportada: {kind}")


def _extract_geometry(placemark: ET.Element, ns: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    candidates = [
        ("Point", _find(placemark, ".//kml:Point/kml:coordinates", ns)),
        ("LineString", _find(placemark, ".//kml:LineString/kml:coordinates", ns)),
        (
            "Polygon",
            _find(
                placemark,
                ".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates",
                ns,
            ),
        ),
    ]

    for kind, coord_elem in candidates:
        if coord_elem is None or not coord_elem.text or not coord_elem.text.strip():
            continue
        try:
            return _parse_geometry(kind, coord_elem.text), errors, warnings
        except (IndexError, ValueError) as exc:
            errors.append(f"Geometria {kind} invalida: {exc}")

    multi = _find(placemark, ".//kml:MultiGeometry", ns)
    if multi is None:
        warnings.append("Placemark sem geometria suportada.")
        return None, errors, warnings

    geometries = []
    for child in multi:
        kind = _local_name(child.tag)
        if kind == "Polygon":
            coord_elem = _find(child, ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns)
        else:
            coord_elem = _find(child, "kml:coordinates", ns)

        if coord_elem is None or not coord_elem.text or not coord_elem.text.strip():
            warnings.append(f"Elemento {kind} em MultiGeometry sem coordenadas.")
            continue

        try:
            geometries.append(_parse_geometry(kind, coord_elem.text))
        except (IndexError, ValueError) as exc:
            errors.append(f"Geometria {kind} invalida em MultiGeometry: {exc}")

    if not geometries:
        if not errors:
            warnings.append("MultiGeometry sem geometrias utilizaveis.")
        return None, errors, warnings

    if len(geometries) == 1:
        return geometries[0], errors, warnings

    return {"type": "GeometryCollection", "geometries": geometries}, errors, warnings


def validate_kml_file(file_path: str) -> Dict[str, Any]:
    path = Path(file_path)
    result = _make_result(path)

    if not path.exists():
        _add_issue(result, "error", "Arquivo nao encontrado.")
        return result

    try:
        kml_bytes, embedded_kml = _read_kml_bytes(path)
        result["embedded_kml"] = embedded_kml
    except (OSError, ValueError) as exc:
        _add_issue(result, "error", str(exc))
        return result

    try:
        root = ET.fromstring(kml_bytes)
    except ET.ParseError as exc:
        _add_issue(result, "error", f"XML invalido: {exc}")
        return result

    root_name = _local_name(root.tag).lower()
    if root_name != "kml":
        _add_issue(result, "warning", "Elemento raiz diferente de <kml>.")

    ns = _detect_ns(root)
    namespace = ns.get("kml")
    result["metadata"]["namespace"] = namespace
    if namespace is None:
        _add_issue(result, "warning", "Namespace KML nao identificado.")

    document = _find(root, ".//kml:Document", ns)
    if document is None:
        document = root
    name_elem = _find(document, "kml:name", ns)
    if name_elem is not None and name_elem.text:
        result["metadata"]["document_name"] = name_elem.text.strip()

    desc_elem = _find(document, "kml:description", ns)
    if desc_elem is not None and desc_elem.text:
        result["metadata"]["description"] = desc_elem.text.strip()

    placemarks = _findall(root, ".//kml:Placemark", ns)
    result["metadata"]["placemark_count"] = len(placemarks)
    if not placemarks:
        _add_issue(result, "warning", "Nenhum Placemark encontrado.")

    features: List[Dict[str, Any]] = []
    placemark_results: List[Dict[str, Any]] = []
    for index, placemark in enumerate(placemarks, start=1):
        name_elem = _find(placemark, "kml:name", ns)
        name = name_elem.text.strip() if name_elem is not None and name_elem.text else f"Placemark {index}"

        desc_elem = _find(placemark, "kml:description", ns)
        description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

        geometry, geometry_errors, geometry_warnings = _extract_geometry(placemark, ns)
        placemark_result = {
            "name": name,
            "valid": geometry is not None and not geometry_errors,
            "geometry_type": geometry["type"] if geometry else None,
            "errors": geometry_errors,
            "warnings": geometry_warnings,
        }
        placemark_results.append(placemark_result)

        for issue in geometry_errors:
            _add_issue(result, "error", f"{name}: {issue}")
        for issue in geometry_warnings:
            _add_issue(result, "warning", f"{name}: {issue}")

        if geometry is None:
            continue

        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "name": name,
                    "description": description,
                },
            }
        )

    result["placemarks"] = placemark_results
    result["metadata"]["valid_feature_count"] = len(features)
    result["geojson"] = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": result["metadata"].copy(),
    }
    result["valid"] = not result["errors"]
    return result


def write_geojson(validation_result: Dict[str, Any], output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(validation_result["geojson"], file_handle, indent=2, ensure_ascii=False)
    validation_result["output_files"]["geojson"] = str(path.resolve())
    return str(path.resolve())


def _render_issue_list(items: List[str], empty_text: str) -> str:
    if not items:
        return f"<p>{escape(empty_text)}</p>"
    rendered_items = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"<ul>{rendered_items}</ul>"


def _render_output_files(output_files: Dict[str, str]) -> str:
    if not output_files:
        return "<p>Nenhum arquivo adicional gerado.</p>"
    rendered_items = "".join(
        f"<li><strong>{escape(name)}:</strong> {escape(path)}</li>"
        for name, path in output_files.items()
    )
    return f"<ul>{rendered_items}</ul>"


def _render_placemarks(placemarks: List[Dict[str, Any]]) -> str:
    if not placemarks:
        return "<p>Nenhum placemark identificado.</p>"

    rows = []
    for placemark in placemarks:
        issues = placemark["errors"] + placemark["warnings"]
        issue_text = "<br>".join(escape(issue) for issue in issues) if issues else "Sem observacoes"
        rows.append(
            "<tr>"
            f"<td>{escape(placemark['name'])}</td>"
            f"<td>{escape(placemark['geometry_type'] or '-')}</td>"
            f"<td>{'Sim' if placemark['valid'] else 'Nao'}</td>"
            f"<td>{issue_text}</td>"
            "</tr>"
        )
    return (
        "<table>"
        "<thead><tr><th>Placemark</th><th>Geometria</th><th>Valido</th><th>Observacoes</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def write_html_report(validation_result: Dict[str, Any], output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    validation_result["output_files"]["html_report"] = str(path.resolve())

    status_text = "VALIDO" if validation_result["valid"] else "INVALIDO"
    status_class = "valid" if validation_result["valid"] else "invalid"
    metadata = validation_result["metadata"]
    geojson_preview = json.dumps(validation_result["geojson"], indent=2, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Relatorio KML/KMZ</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f1e8;
      --panel: #fffdf8;
      --border: #d4c6ab;
      --text: #2d2419;
      --muted: #786754;
      --ok: #2f6b3c;
      --bad: #9f2d2d;
      --accent: #9a6b2f;
    }}
    body {{
      margin: 0;
      padding: 32px;
      background: radial-gradient(circle at top, #fff8ea 0%, var(--bg) 55%);
      color: var(--text);
      font-family: "Segoe UI", Tahoma, sans-serif;
    }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      display: grid;
      gap: 20px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px 24px;
      box-shadow: 0 14px 40px rgba(63, 43, 15, 0.08);
    }}
    h1, h2 {{
      margin-top: 0;
    }}
    .status {{
      display: inline-block;
      padding: 8px 14px;
      border-radius: 999px;
      font-weight: 700;
      letter-spacing: 0.08em;
    }}
    .status.valid {{
      background: rgba(47, 107, 60, 0.14);
      color: var(--ok);
    }}
    .status.invalid {{
      background: rgba(159, 45, 45, 0.14);
      color: var(--bad);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}
    .card {{
      padding: 14px;
      border-radius: 14px;
      background: #fff9ef;
      border: 1px solid #ead9bb;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }}
    pre {{
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      background: #221c14;
      color: #efe4d2;
      padding: 16px;
      border-radius: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid #ead9bb;
      padding: 12px 10px;
    }}
    ul {{
      padding-left: 20px;
    }}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Relatorio de validacao KML/KMZ</h1>
      <p class="status {status_class}">{status_text}</p>
      <div class="grid">
        <div class="card">
          <span class="label">Arquivo</span>
          <strong>{escape(validation_result['input_file'])}</strong>
        </div>
        <div class="card">
          <span class="label">Tipo</span>
          <strong>{escape(validation_result['file_type'])}</strong>
        </div>
        <div class="card">
          <span class="label">KML Interno</span>
          <strong>{escape(validation_result['embedded_kml'] or '-')}</strong>
        </div>
        <div class="card">
          <span class="label">Gerado Em</span>
          <strong>{escape(validation_result['generated_at'])}</strong>
        </div>
      </div>
    </section>

    <section>
      <h2>Resumo</h2>
      <div class="grid">
        <div class="card">
          <span class="label">Documento</span>
          <strong>{escape(metadata['document_name'] or 'Sem nome')}</strong>
        </div>
        <div class="card">
          <span class="label">Namespace</span>
          <strong>{escape(metadata['namespace'] or 'Nao identificado')}</strong>
        </div>
        <div class="card">
          <span class="label">Placemarks</span>
          <strong>{metadata['placemark_count']}</strong>
        </div>
        <div class="card">
          <span class="label">Features validas</span>
          <strong>{metadata['valid_feature_count']}</strong>
        </div>
      </div>
      <p>{escape(metadata['description'] or 'Sem descricao')}</p>
    </section>

    <section>
      <h2>Erros</h2>
      {_render_issue_list(validation_result['errors'], 'Nenhum erro encontrado.')}
    </section>

    <section>
      <h2>Avisos</h2>
      {_render_issue_list(validation_result['warnings'], 'Nenhum aviso encontrado.')}
    </section>

    <section>
      <h2>Placemarks</h2>
      {_render_placemarks(validation_result['placemarks'])}
    </section>

    <section>
      <h2>Arquivos Gerados</h2>
      {_render_output_files(validation_result['output_files'])}
    </section>

    <section>
      <h2>GeoJSON</h2>
      <pre>{escape(geojson_preview)}</pre>
    </section>
  </main>
</body>
</html>
"""

    path.write_text(html_content, encoding="utf-8")
    return str(path.resolve())
