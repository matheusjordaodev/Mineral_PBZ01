"""
CLI app to validate KML/KMZ files and generate output artifacts.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from utils.kml_validator import validate_kml_file, write_geojson, write_html_report


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida um arquivo KML/KMZ e gera relatorio HTML e GeoJSON."
    )
    parser.add_argument("input_file", help="Caminho para o arquivo .kml ou .kmz")
    parser.add_argument(
        "--output-dir",
        default="saida_kml",
        help="Diretorio onde os arquivos de saida serao gerados (padrao: saida_kml)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input_file)
    output_dir = Path(args.output_dir)
    report_path = output_dir / f"{input_path.stem}_relatorio.html"
    geojson_path = output_dir / f"{input_path.stem}.geojson"

    validation = validate_kml_file(str(input_path))

    if validation["valid"]:
        write_geojson(validation, str(geojson_path))

    write_html_report(validation, str(report_path))

    print(f"Arquivo analisado: {validation['input_file']}")
    print(f"Status: {'VALIDO' if validation['valid'] else 'INVALIDO'}")
    print(f"Placemarks encontrados: {validation['metadata']['placemark_count']}")
    print(f"Features validas: {validation['metadata']['valid_feature_count']}")

    if validation["errors"]:
        print("Erros:")
        for error in validation["errors"]:
            print(f"  - {error}")

    if validation["warnings"]:
        print("Avisos:")
        for warning in validation["warnings"]:
            print(f"  - {warning}")

    if "geojson" in validation["output_files"]:
        print(f"GeoJSON gerado: {validation['output_files']['geojson']}")
    print(f"Relatorio HTML: {validation['output_files']['html_report']}")

    return 0 if validation["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
