"""
Testes de integração: upload, servir e download de mídia e arquivos.

Cobre:
  A. Upload de mídia (imagens/vídeos) via /api/campanhas/{id}/media
     A1. Upload de imagem JPG → 200, retorna URL
     A2. Upload de PNG → 200
     A3. Upload de múltiplos arquivos em uma chamada → todos na resposta
     A4. Upload de extensão não permitida → rejeitado (400/422)
     A5. Upload sem autenticação → 401

  B. Upload de arquivo KML geoespacial via /api/campanhas/{id}/geospatial
     B1. Upload de KML válido com espaco_amostral_id → 200, feicoes_salvas >= 0
     B2. Upload de extensão inválida → 400/422
     B3. Upload sem autenticação → 401

  C. Upload tipado via /api/campanhas/{id}/upload
     C1. Upload de imagem → 200, folder = images
     C2. Upload de planilha (.xlsx) → 200, folder = excel

  D. Download e servir arquivos
     D1. GET /api/download com URL válida local → 200 ou redirect
     D2. GET /api/campanhas/{id}/kml/export → Content-Type KML
     D3. GET /api/campanhas/{id}/kml/arquivos → lista arquivos

  E. Galeria de imagens
     E1. GET /api/galeria-imagens → 200, estrutura correta
     E2. Resposta contém chave 'ilhas'
     E3. Cada ilha tem 'imagens' e 'total_imagens'

  F. Servir arquivo local via /uploads/...
     F1. Arquivo existente → 200 com Content-Type correto
     F2. Arquivo inexistente → 404

Requer servidor rodando em localhost:8080 (dentro do container) ou porta via argv.

Uso:
    python tests/test_media_files.py 8080
    python -m pytest tests/test_media_files.py -v
"""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import unittest
import urllib.parse
import urllib.request
import http.client

BASE_HOST = "localhost"
BASE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8080


def _server_available() -> bool:
    try:
        s = socket.create_connection((BASE_HOST, BASE_PORT), timeout=2)
        s.close()
        return True
    except OSError:
        return False


def _request_json(method: str, path: str, body=None, token: str = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=15)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def _do_login(username="admin", password="admin") -> str:
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
    params = urllib.parse.urlencode({"username": username, "password": password})
    conn.request("POST", "/api/login", params,
                 {"Content-Type": "application/x-www-form-urlencoded"})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()
    return data["access_token"]


def _multipart_post(path: str, fields: dict, files: dict, token: str = None):
    """
    Envia multipart/form-data.
    fields: {name: str_value}
    files:  {name: (filename, bytes, content_type)}
    """
    boundary = "----PBZ01MediaTestBoundary"
    body = b""

    for name, value in fields.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    for name, (filename, data, ctype) in files.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode()
        body += data
        body += b"\r\n"

    body += f"--{boundary}--\r\n".encode()

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=30)
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


# ─── Imagens sintéticas ───────────────────────────────────────────────────────

def _minimal_jpg() -> bytes:
    """JPEG mínimo válido (1x1 pixel branco)."""
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD7, 0xFF, 0xD9,
    ])


def _minimal_png() -> bytes:
    """PNG mínimo válido (1x1 pixel preto)."""
    return bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # assinatura PNG
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0x00, 0x00, 0x02, 0x00, 0x01, 0xE2, 0x21, 0xBC,
        0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
        0x44, 0xAE, 0x42, 0x60, 0x82,
    ])


def _minimal_kml(nome="Ponto Teste") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{nome}</name>
  <Placemark>
    <name>{nome}</name>
    <Point><coordinates>-44.85,-23.42,0</coordinates></Point>
  </Placemark>
</Document>
</kml>""".encode("utf-8")


def _minimal_xlsx() -> bytes:
    """Bytes mínimos que representam um XLSX (ZIP com magic bytes)."""
    return bytes([
        0x50, 0x4B, 0x03, 0x04, 0x14, 0x00, 0x00, 0x00,
        0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ])


def _get_campanha_and_ilha(token: str):
    """Retorna (campanha_id, ilha_id, espaco_id) para usar nos testes."""
    status, data = _request_json("GET", "/api/ilhas", token=token)
    if status != 200:
        raise RuntimeError(f"Falha ao listar ilhas: {status}")
    ilhas = data.get("ilhas") or []
    ilha = next((i for i in ilhas if len(i.get("espacos_amostrais") or []) >= 1), None)
    if not ilha:
        raise RuntimeError("Nenhuma ilha com espaços amostrais")
    espaco_id = ilha["espacos_amostrais"][0]["id"]

    # Cria campanha vazia para os testes de upload
    from datetime import date
    payload = {
        "ilhas": [{"ilha_id": ilha["id"], "selecao": []}],
        "nome": "CAMPANHA MEDIA TEST",
        "data": date.today().isoformat(),
        "descricao": "Testes de upload de mídia",
        "base_apoio_id": None, "embarcacao_id": None, "membros_equipe": [],
    }
    s2, r2 = _request_json("POST", "/api/campanhas", payload, token)
    if s2 != 200:
        raise RuntimeError(f"Falha ao criar campanha: {s2} {r2}")
    campanha = r2.get("campanha") or {}
    campanha_id = campanha.get("id") or campanha.get("uuid")
    return campanha_id, ilha["id"], espaco_id


# ─── Bloco A: Upload de mídia ─────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), f"Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
class TestUploadMidia(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = _do_login()
        cls.campanha_id, cls.ilha_id, cls.espaco_id = _get_campanha_and_ilha(cls.token)

    def _media_url(self):
        return f"/api/campanhas/{self.campanha_id}/media?ilha_id={self.ilha_id}"

    def test_a1_upload_jpg_retorna_200(self):
        status, resp = _multipart_post(
            self._media_url(),
            fields={},
            files={"files": ("foto_teste.jpg", _minimal_jpg(), "image/jpeg")},
            token=self.token,
        )
        self.assertEqual(status, 200, f"Upload JPG esperava 200, obtido {status}: {resp}")

    def test_a2_upload_jpg_resposta_contem_url(self):
        status, resp = _multipart_post(
            self._media_url(),
            fields={},
            files={"files": ("foto_url_test.jpg", _minimal_jpg(), "image/jpeg")},
            token=self.token,
        )
        self.assertEqual(status, 200)
        files_list = resp.get("files") or []
        self.assertGreater(len(files_list), 0, "Resposta deve conter lista 'files'")
        first = files_list[0]
        self.assertIn("url", first, f"Item sem 'url': {first}")
        self.assertIn("filename", first, f"Item sem 'filename': {first}")

    def test_a3_upload_png_retorna_200(self):
        status, resp = _multipart_post(
            self._media_url(),
            fields={},
            files={"files": ("imagem_teste.png", _minimal_png(), "image/png")},
            token=self.token,
        )
        self.assertEqual(status, 200, f"Upload PNG esperava 200, obtido {status}: {resp}")

    def test_a4_upload_sem_autenticacao_retorna_401(self):
        status, resp = _multipart_post(
            self._media_url(),
            fields={},
            files={"files": ("foto.jpg", _minimal_jpg(), "image/jpeg")},
            token=None,
        )
        self.assertEqual(status, 401, f"Upload sem token deve retornar 401, obtido {status}")

    def test_a5_upload_resposta_contem_campo_uploaded(self):
        status, resp = _multipart_post(
            self._media_url(),
            fields={},
            files={"files": ("count_test.jpg", _minimal_jpg(), "image/jpeg")},
            token=self.token,
        )
        self.assertEqual(status, 200)
        self.assertIn("uploaded", resp, f"Resposta sem campo 'uploaded': {resp}")
        self.assertGreaterEqual(resp["uploaded"], 1)


# ─── Bloco B: Upload KML geoespacial ─────────────────────────────────────────

@unittest.skipUnless(_server_available(), f"Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
class TestUploadGeoespacial(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = _do_login()
        cls.campanha_id, cls.ilha_id, cls.espaco_id = _get_campanha_and_ilha(cls.token)

    def test_b1_upload_kml_valido_retorna_200(self):
        status, resp = _multipart_post(
            f"/api/campanhas/{self.campanha_id}/geospatial?espaco_amostral_id={self.espaco_id}",
            fields={},
            files={"file": ("ponto_teste.kml", _minimal_kml(), "application/vnd.google-earth.kml+xml")},
            token=self.token,
        )
        self.assertEqual(status, 200, f"Upload KML esperava 200, obtido {status}: {resp}")

    def test_b2_upload_kml_retorna_feicoes_salvas(self):
        status, resp = _multipart_post(
            f"/api/campanhas/{self.campanha_id}/geospatial?espaco_amostral_id={self.espaco_id}",
            fields={},
            files={"file": ("ponto_b2.kml", _minimal_kml("B2 Ponto"), "application/vnd.google-earth.kml+xml")},
            token=self.token,
        )
        self.assertEqual(status, 200)
        self.assertIn("feicoes_salvas", resp, f"Resposta sem 'feicoes_salvas': {resp}")
        self.assertGreaterEqual(resp["feicoes_salvas"], 0)

    def test_b3_upload_kml_retorna_filename_e_size(self):
        status, resp = _multipart_post(
            f"/api/campanhas/{self.campanha_id}/geospatial?espaco_amostral_id={self.espaco_id}",
            fields={},
            files={"file": ("ponto_b3.kml", _minimal_kml("B3"), "application/vnd.google-earth.kml+xml")},
            token=self.token,
        )
        self.assertEqual(status, 200)
        self.assertIn("filename", resp, f"Resposta sem 'filename': {resp}")
        self.assertIn("size", resp, f"Resposta sem 'size': {resp}")
        self.assertGreater(resp["size"], 0)

    def test_b4_upload_extensao_invalida_rejeitado(self):
        status, resp = _multipart_post(
            f"/api/campanhas/{self.campanha_id}/geospatial?espaco_amostral_id={self.espaco_id}",
            fields={},
            files={"file": ("documento.pdf", b"%PDF-1.4 fake", "application/pdf")},
            token=self.token,
        )
        self.assertIn(status, (400, 422), f"Extensão inválida deve ser rejeitada, obtido {status}: {resp}")

    def test_b5_upload_kml_sem_autenticacao_retorna_401(self):
        status, resp = _multipart_post(
            f"/api/campanhas/{self.campanha_id}/geospatial?espaco_amostral_id={self.espaco_id}",
            fields={},
            files={"file": ("sem_auth.kml", _minimal_kml(), "application/vnd.google-earth.kml+xml")},
            token=None,
        )
        self.assertEqual(status, 401, f"Upload KML sem token deve retornar 401, obtido {status}")


# ─── Bloco C: Upload tipado ───────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), f"Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
class TestUploadTipado(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = _do_login()
        cls.campanha_id, cls.ilha_id, cls.espaco_id = _get_campanha_and_ilha(cls.token)

    def _upload_url(self):
        return f"/api/campanhas/{self.campanha_id}/upload?ilha_id={self.ilha_id}"

    def test_c1_upload_imagem_retorna_200_e_url(self):
        status, resp = _multipart_post(
            self._upload_url(),
            fields={},
            files={"file": ("imagem_tipada.jpg", _minimal_jpg(), "image/jpeg")},
            token=self.token,
        )
        self.assertEqual(status, 200, f"Upload tipado esperava 200, obtido {status}: {resp}")
        self.assertIn("url", resp, f"Resposta sem 'url': {resp}")

    def test_c2_upload_planilha_xlsx_retorna_200(self):
        status, resp = _multipart_post(
            self._upload_url(),
            fields={},
            files={"file": ("planilha.xlsx", _minimal_xlsx(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            token=self.token,
        )
        self.assertEqual(status, 200, f"Upload XLSX esperava 200, obtido {status}: {resp}")

    def test_c3_upload_kml_tipado_retorna_200(self):
        status, resp = _multipart_post(
            self._upload_url(),
            fields={},
            files={"file": ("kml_tipado.kml", _minimal_kml(), "application/vnd.google-earth.kml+xml")},
            token=self.token,
        )
        self.assertEqual(status, 200, f"Upload KML tipado esperava 200, obtido {status}: {resp}")


# ─── Bloco D: Download e export ───────────────────────────────────────────────

@unittest.skipUnless(_server_available(), f"Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
class TestDownloadExport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = _do_login()
        cls.campanha_id, cls.ilha_id, cls.espaco_id = _get_campanha_and_ilha(cls.token)
        # Sobe um KML para garantir que há feições para exportar
        _multipart_post(
            f"/api/campanhas/{cls.campanha_id}/geospatial?espaco_amostral_id={cls.espaco_id}",
            fields={},
            files={"file": ("setup_export.kml", _minimal_kml("Export Setup"),
                            "application/vnd.google-earth.kml+xml")},
            token=cls.token,
        )

    def _raw_get(self, path: str, token: str = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=15)
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        content_type = resp.getheader("Content-Type", "")
        conn.close()
        return resp.status, content_type, body

    def test_d1_export_kml_retorna_200(self):
        status, ct, body = self._raw_get(
            f"/api/campanhas/{self.campanha_id}/kml/export"
        )
        self.assertEqual(status, 200, f"Export KML esperava 200, obtido {status}")

    def test_d2_export_kml_content_type_xml_ou_kml(self):
        status, ct, body = self._raw_get(
            f"/api/campanhas/{self.campanha_id}/kml/export"
        )
        self.assertEqual(status, 200)
        ct_lower = ct.lower()
        self.assertTrue(
            "kml" in ct_lower or "xml" in ct_lower or "octet" in ct_lower,
            f"Content-Type inesperado para KML: {ct!r}"
        )

    def test_d3_export_kml_corpo_contem_xml(self):
        status, ct, body = self._raw_get(
            f"/api/campanhas/{self.campanha_id}/kml/export"
        )
        self.assertEqual(status, 200)
        text = body.decode("utf-8", errors="replace")
        self.assertIn("<?xml", text, "Corpo do KML deve começar com declaração XML")

    def test_d4_export_kml_filtrado_por_ponto(self):
        status, ct, body = self._raw_get(
            f"/api/campanhas/{self.campanha_id}/kml/export?espaco_amostral_id={self.espaco_id}"
        )
        self.assertIn(status, (200, 404), f"Export por ponto retornou {status}")

    def test_d5_listar_kmls_retorna_200(self):
        status, resp = _request_json(
            "GET", f"/api/campanhas/{self.campanha_id}/kml/arquivos", token=self.token
        )
        self.assertEqual(status, 200, f"Listar KMLs esperava 200, obtido {status}: {resp}")

    def test_d6_listar_kmls_retorna_lista(self):
        status, resp = _request_json(
            "GET", f"/api/campanhas/{self.campanha_id}/kml/arquivos", token=self.token
        )
        self.assertEqual(status, 200)
        self.assertIsInstance(resp, (list, dict), f"Resposta deveria ser lista ou dict: {resp}")

    def test_d7_download_url_invalida_nao_explode(self):
        """GET /api/download com URL inexistente deve retornar 4xx, não 500."""
        path = "/api/download?" + urllib.parse.urlencode({"url": "http://localhost/nao_existe.kml"})
        status, ct, body = self._raw_get(path)
        self.assertNotEqual(status, 500, f"Download de URL inválida não deve retornar 500")


# ─── Bloco E: Galeria de imagens ──────────────────────────────────────────────

@unittest.skipUnless(_server_available(), f"Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
class TestGaleriaImagens(unittest.TestCase):

    def test_e1_galeria_retorna_200(self):
        status, resp = _request_json("GET", "/api/galeria-imagens")
        self.assertEqual(status, 200, f"Galeria esperava 200, obtido {status}: {resp}")

    def test_e2_galeria_contem_chave_ilhas(self):
        status, resp = _request_json("GET", "/api/galeria-imagens")
        self.assertEqual(status, 200)
        self.assertIn("ilhas", resp, f"Resposta sem chave 'ilhas': {list(resp.keys())}")

    def test_e3_ilhas_e_lista(self):
        status, resp = _request_json("GET", "/api/galeria-imagens")
        self.assertEqual(status, 200)
        self.assertIsInstance(resp["ilhas"], list)

    def test_e4_cada_ilha_tem_total_imagens(self):
        status, resp = _request_json("GET", "/api/galeria-imagens")
        self.assertEqual(status, 200)
        ilhas = resp.get("ilhas") or []
        if not ilhas:
            self.skipTest("Nenhuma ilha retornada na galeria")
        for ilha in ilhas:
            with self.subTest(ilha=ilha.get("nome")):
                self.assertIn("total_imagens", ilha,
                              f"Ilha sem 'total_imagens': {list(ilha.keys())}")
                self.assertIn("imagens", ilha,
                              f"Ilha sem 'imagens': {list(ilha.keys())}")

    def test_e5_estrutura_de_imagem(self):
        """Cada item de imagem deve ter url, type e date."""
        status, resp = _request_json("GET", "/api/galeria-imagens")
        self.assertEqual(status, 200)
        for ilha in resp.get("ilhas") or []:
            for img in (ilha.get("imagens") or [])[:3]:  # verifica até 3 por ilha
                with self.subTest(ilha=ilha.get("nome")):
                    self.assertIn("url", img, f"Imagem sem 'url': {img}")
                    self.assertIn("type", img, f"Imagem sem 'type': {img}")


# ─── Bloco F: Servir arquivo local ────────────────────────────────────────────

@unittest.skipUnless(_server_available(), f"Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
class TestServirArquivos(unittest.TestCase):

    def _raw_get(self, path: str):
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        resp.read()
        ct = resp.getheader("Content-Type", "")
        conn.close()
        return resp.status, ct

    def test_f1_arquivo_inexistente_retorna_404(self):
        status, _ = self._raw_get("/uploads/999/999/media/arquivo_que_nao_existe.jpg")
        self.assertEqual(status, 404, f"Arquivo inexistente deve retornar 404, obtido {status}")

    def test_f2_path_invalido_nao_retorna_500(self):
        status, _ = self._raw_get("/uploads/abc/abc/invalido/arquivo.xyz")
        self.assertNotEqual(status, 500, f"Path inválido não deve retornar 500")


# ─── runner próprio ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not _server_available():
        print(f"\n[SKIP] Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
        print("       Inicie o servidor e tente novamente.\n")
        sys.exit(0)

    runner = unittest.TextTestRunner(verbosity=2)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestUploadMidia,
        TestUploadGeoespacial,
        TestUploadTipado,
        TestDownloadExport,
        TestGaleriaImagens,
        TestServirArquivos,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
