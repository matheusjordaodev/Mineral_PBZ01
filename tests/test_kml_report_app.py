import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from utils.kml_validator import validate_kml_file


REPO_ROOT = Path(__file__).resolve().parents[1]


class KmlValidatorTests(unittest.TestCase):
    def test_validate_valid_kmz_file(self) -> None:
        result = validate_kml_file(str(REPO_ROOT / "test_sample.kmz"))

        self.assertTrue(result["valid"])
        self.assertEqual(result["metadata"]["placemark_count"], 2)
        self.assertEqual(result["metadata"]["valid_feature_count"], 2)
        self.assertEqual(result["errors"], [])

    def test_validate_invalid_xml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_file = Path(temp_dir) / "invalid.kml"
            invalid_file.write_text("<kml><Document><Placemark></kml>", encoding="utf-8")

            result = validate_kml_file(str(invalid_file))

        self.assertFalse(result["valid"])
        self.assertTrue(any("XML invalido" in error for error in result["errors"]))

    def test_cli_generates_outputs_for_valid_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            command = [
                sys.executable,
                str(REPO_ROOT / "kml_report_app.py"),
                str(REPO_ROOT / "test_sample.kmz"),
                "--output-dir",
                temp_dir,
            ]
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stdout + completed.stderr)
            self.assertIn("Status: VALIDO", completed.stdout)
            self.assertTrue((Path(temp_dir) / "test_sample.geojson").exists())
            self.assertTrue((Path(temp_dir) / "test_sample_relatorio.html").exists())


if __name__ == "__main__":
    unittest.main()
