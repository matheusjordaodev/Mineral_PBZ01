"""
Testes de autenticação e autorização.

Cobre:
  1. Login com credenciais corretas → JWT válido
  2. Login com senha errada → 401
  3. Login com usuário inexistente → 401
  4. Endpoint protegido sem token → 401
  5. Endpoint protegido com token malformado → 401
  6. Endpoint protegido com token expirado → 401
  7. GET /api/me com token válido → retorna dados do usuário
  8. GET /api/me não expõe senha_hash
  9. Login sem campos obrigatórios → 4xx

Uso:
    python -m pytest tests/test_auth.py -v          # porta 8001
    python -m pytest tests/test_auth.py -v --port 8080
    python tests/test_auth.py                       # runner próprio
    python tests/test_auth.py 8080
"""

from __future__ import annotations

import http.client
import json
import socket
import sys
import unittest
import urllib.parse

# Porta: argumento numérico via CLI direto, ou padrão
BASE_HOST = "localhost"
BASE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8001


def _server_available() -> bool:
    """Verifica se o servidor está acessível antes de tentar conexão."""
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
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def _do_login(username: str, password: str):
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
    params = urllib.parse.urlencode({"username": username, "password": password})
    conn.request("POST", "/api/login", params,
                 {"Content-Type": "application/x-www-form-urlencoded"})
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


# ─── Suite de testes ──────────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), f"Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
class TestLogin(unittest.TestCase):

    def test_login_credenciais_corretas_retorna_200(self):
        status, data = _do_login("admin", "admin")
        self.assertEqual(status, 200, f"Esperado 200, obtido {status}: {data}")

    def test_login_retorna_access_token(self):
        _, data = _do_login("admin", "admin")
        token = data.get("access_token")
        self.assertIsNotNone(token, "access_token ausente na resposta")
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20, "token parece inválido (muito curto)")

    def test_login_retorna_token_type_bearer(self):
        _, data = _do_login("admin", "admin")
        self.assertEqual(data.get("token_type", "").lower(), "bearer")

    def test_login_senha_errada_retorna_401(self):
        status, _ = _do_login("admin", "senha-completamente-errada-xyz")
        self.assertEqual(status, 401, f"Esperado 401, obtido {status}")

    def test_login_usuario_inexistente_retorna_401(self):
        status, _ = _do_login("usuario_que_nao_existe_abc123", "qualquer")
        self.assertEqual(status, 401, f"Esperado 401, obtido {status}")

    def test_login_sem_username_retorna_4xx(self):
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
        params = urllib.parse.urlencode({"password": "admin"})
        conn.request("POST", "/api/login", params,
                     {"Content-Type": "application/x-www-form-urlencoded"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertIn(resp.status, (400, 401, 422),
                      f"Esperado 4xx sem username, obtido {resp.status}")

    def test_login_sem_password_retorna_4xx(self):
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
        params = urllib.parse.urlencode({"username": "admin"})
        conn.request("POST", "/api/login", params,
                     {"Content-Type": "application/x-www-form-urlencoded"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertIn(resp.status, (400, 401, 422),
                      f"Esperado 4xx sem password, obtido {resp.status}")


@unittest.skipUnless(_server_available(), f"Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
class TestAutorizacao(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Obtém token válido uma única vez para todos os testes da classe."""
        status, data = _do_login("admin", "admin")
        if status != 200:
            raise unittest.SkipTest(f"Login falhou ({status}) — não é possível testar autorização")
        cls.token = data["access_token"]

    def test_endpoint_sem_token_retorna_401_me(self):
        status, _ = _request_json("GET", "/api/users/me")
        self.assertEqual(status, 401, f"GET /api/users/me sem token deve retornar 401, obtido {status}")

    def test_endpoint_sem_token_retorna_401_usuarios(self):
        status, _ = _request_json("GET", "/api/users")
        self.assertEqual(status, 401, f"GET /api/users sem token deve retornar 401, obtido {status}")

    def test_token_malformado_retorna_401(self):
        tokens_invalidos = [
            "nao.e.um.jwt.valido",
            "Bearer eyInvalid",
            "eyJhbGciOiJIUzI1NiJ9.invalido.invalido",
        ]
        for tok in tokens_invalidos:
            with self.subTest(token=tok[:30]):
                status, _ = _request_json("GET", "/api/users/me", token=tok)
                self.assertEqual(status, 401,
                                 f"Token malformado deve retornar 401, obtido {status}")

    def test_token_expirado_retorna_401(self):
        # JWT com exp=1 (epoch 1970) — obviamente expirado
        # Header: {"alg":"HS256","typ":"JWT"} / Payload: {"sub":"admin","exp":1}
        expired = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiJhZG1pbiIsImV4cCI6MX0"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        status, _ = _request_json("GET", "/api/users/me", token=expired)
        self.assertEqual(status, 401, f"Token expirado deve retornar 401, obtido {status}")

    def test_me_com_token_valido_retorna_200(self):
        status, data = _request_json("GET", "/api/users/me", token=self.token)
        self.assertEqual(status, 200, f"GET /api/users/me com token válido deve retornar 200: {data}")

    def test_me_retorna_dados_do_usuario(self):
        _, data = _request_json("GET", "/api/users/me", token=self.token)
        username = data.get("username") or data.get("sub") or data.get("nome_completo")
        self.assertIsNotNone(username, f"Resposta não contém identificação do usuário: {data}")

    def test_me_nao_expoe_senha_hash(self):
        _, data = _request_json("GET", "/api/users/me", token=self.token)
        self.assertNotIn("senha_hash", data, "senha_hash não deve ser exposta na resposta")
        self.assertNotIn("password", data, "password não deve ser exposto na resposta")


# ─── runner próprio (sem pytest) ──────────────────────────────────────────────

if __name__ == "__main__":
    if not _server_available():
        print(f"\n[SKIP] Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
        print("       Inicie o servidor e tente novamente.\n")
        sys.exit(0)

    runner = unittest.TextTestRunner(verbosity=2)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestLogin))
    suite.addTests(loader.loadTestsFromTestCase(TestAutorizacao))
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
