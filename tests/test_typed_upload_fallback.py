import io
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

fake_azure_module = types.ModuleType("services.azure_blob_service")


class _AzureBlobServiceStub:
    def __init__(self):
        pass


fake_azure_module.AzureBlobService = _AzureBlobServiceStub
sys.modules["services.azure_blob_service"] = fake_azure_module

from services.file_service import FileService


class _FailingAzureService:
    def upload_file(self, file_data, blob_name, content_type=None):
        raise Exception("azure unavailable")


class TestTypedUploadFallback(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.upload_dir = Path(self.tmpdir.name)
        self.service = FileService(self.upload_dir)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_save_typed_file_falls_back_to_local_when_azure_missing(self):
        self.service.azure_service = None

        result = self.service.save_typed_file(
            ilha_id="1",
            campanha_id="campanha_teste",
            file_data=io.BytesIO(b"<kml></kml>"),
            filename="Percurso Sao Joao.kml",
        )

        saved_path = self.upload_dir / "1" / "campanha_teste" / "kml" / result["filename"]
        self.assertTrue(saved_path.exists())
        self.assertTrue(result["url"].startswith("/uploads/1/campanha_teste/kml/"))
        self.assertEqual(result["folder"], "kml")

    def test_save_typed_file_falls_back_to_local_when_azure_upload_fails(self):
        self.service.azure_service = _FailingAzureService()

        result = self.service.save_typed_file(
            ilha_id="2",
            campanha_id="campanha_teste",
            file_data=io.BytesIO(b"coluna1,coluna2"),
            filename="planilha final.csv",
        )

        saved_path = self.upload_dir / "2" / "campanha_teste" / "excel" / result["filename"]
        self.assertTrue(saved_path.exists())
        self.assertEqual(result["folder"], "excel")
        self.assertIn("/uploads/2/campanha_teste/excel/", result["url"])

    def test_save_typed_file_rejects_invalid_extension(self):
        self.service.azure_service = None

        with self.assertRaises(ValueError):
            self.service.save_typed_file(
                ilha_id="1",
                campanha_id="campanha_teste",
                file_data=io.BytesIO(b"echo test"),
                filename="script.exe",
            )

    def test_get_file_path_supports_typed_folders(self):
        self.service.azure_service = None
        result = self.service.save_typed_file(
            ilha_id="3",
            campanha_id="campanha_teste",
            file_data=io.BytesIO(b"abc"),
            filename="relatorio.xlsx",
        )

        file_path = self.service.get_file_path("3", "campanha_teste", "excel", result["filename"])
        self.assertEqual(file_path, self.upload_dir / "3" / "campanha_teste" / "excel" / result["filename"])

    def test_local_url_filename_is_sanitized_and_resolvable(self):
        self.service.azure_service = None
        result = self.service.save_typed_file(
            ilha_id="4",
            campanha_id="campanha_teste",
            file_data=io.BytesIO(b"<kml><Document /></kml>"),
            filename="Percurso Sao/Joao final.kml",
        )

        self.assertNotIn(" ", result["filename"])
        self.assertTrue(result["filename"].endswith(".kml"))

        resolved = self.service.get_file_path("4", "campanha_teste", "kml", result["filename"])
        self.assertEqual(resolved, self.upload_dir / "4" / "campanha_teste" / "kml" / result["filename"])

    def test_save_typed_file_accepts_webm_video(self):
        self.service.azure_service = None

        result = self.service.save_typed_file(
            ilha_id="5",
            campanha_id="campanha_teste",
            file_data=io.BytesIO(b"webm"),
            filename="transecto.webm",
        )

        self.assertEqual(result["folder"], "videos")
        resolved = self.service.get_file_path("5", "campanha_teste", "videos", result["filename"])
        self.assertEqual(resolved, self.upload_dir / "5" / "campanha_teste" / "videos" / result["filename"])

    def test_save_typed_file_accepts_webp_image(self):
        self.service.azure_service = None

        result = self.service.save_typed_file(
            ilha_id="6",
            campanha_id="campanha_teste",
            file_data=io.BytesIO(b"webp"),
            filename="mosaico.webp",
        )

        self.assertEqual(result["folder"], "images")
        resolved = self.service.get_file_path("6", "campanha_teste", "images", result["filename"])
        self.assertEqual(resolved, self.upload_dir / "6" / "campanha_teste" / "images" / result["filename"])


if __name__ == "__main__":
    unittest.main()
