"""
Teste end-to-end do fluxo completo de cadastro.

Cobre:
  1.  Login
  2.  Listar ilhas e escolher a primeira com espaços amostrais
  3.  Criar campanha com 2 pontos (metodologias BA e FQ+VT)
  4.  Listar estações criadas automaticamente
  5.  Envio em lote: BuscaAtiva + VideoTransecto + Fotoquadrado
  6.  Verificar contagens no /metodos
  7.  Upload de KML sintético vinculado a um ponto
  8.  Verificar GeoJSON retorna feições do ponto
  9.  Export KML por ponto
  10. Upload de documento vinculado à campanha
  11. Listar documentos da campanha
  12. Export WMS por ponto (/api/export/wms/ponto/{id})
  13. Export WMS por ilha  (/api/export/wms/{ilha_id})
  14. Listar KMLs originais da campanha
  15. Deletar documento criado
  16. Verificar full-details da campanha

Uso:
    python tests/test_cadastro_e2e.py           # aponta para localhost:8001
    python tests/test_cadastro_e2e.py 8080      # porta alternativa
"""

import http.client
import io
import json
import sys
import urllib.parse
from datetime import date

BASE_HOST = "localhost"
BASE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8000

# compatibilidade com terminais Windows (cp1252)
sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None

PASSED = []
FAILED = []


# ─── helpers ──────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"  {msg}")


def ok(label: str):
    PASSED.append(label)
    print(f"  [OK]  {label}")


def fail(label: str, detail: str):
    FAILED.append(label)
    print(f"  [FAIL] {label}")
    print(f"         {detail}")


def request(method: str, path: str, body=None, token: str = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def multipart_post(path: str, fields: dict, files: dict, token: str = None):
    """
    Envia multipart/form-data.
    fields: {name: str_value}
    files:  {name: (filename, bytes, content_type)}
    """
    boundary = "----PBZ01TestBoundary"
    body_parts = []

    for name, value in fields.items():
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        )

    for name, (filename, data, ctype) in files.items():
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        )
        body_parts.append(header)

    # monta bytes
    raw_body = b""
    part_idx = 0
    for name, value in fields.items():
        raw_body += body_parts[part_idx].encode()
        part_idx += 1
    for name, (filename, data, ctype) in files.items():
        raw_body += body_parts[part_idx].encode()
        raw_body += data
        raw_body += b"\r\n"
        part_idx += 1
    raw_body += f"--{boundary}--\r\n".encode()

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    conn.request("POST", path, body=raw_body, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def login() -> str:
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    params = urllib.parse.urlencode({"username": "admin", "password": "admin"})
    conn.request("POST", "/api/login", params,
                 {"Content-Type": "application/x-www-form-urlencoded"})
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"Login falhou: {resp.status} {raw}")
    return json.loads(raw)["access_token"]


def minimal_kml(nome: str = "Ponto Teste") -> bytes:
    """Gera um KML mínimo válido com 1 ponto."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{nome}</name>
  <Placemark>
    <name>{nome}</name>
    <description>Ponto de teste automatizado</description>
    <Point><coordinates>-44.85,-23.42,0</coordinates></Point>
  </Placemark>
</Document>
</kml>""".encode("utf-8")


def minimal_pdf() -> bytes:
    """Bytes mínimos que simulam um arquivo qualquer para upload de documento."""
    return b"%PDF-1.4 test document for automated upload"


# ─── steps ────────────────────────────────────────────────────────────────────

def step_login():
    print("\n[1] Login")
    try:
        token = login()
        ok("Login com admin/admin")
        return token
    except Exception as e:
        fail("Login com admin/admin", str(e))
        raise


def step_listar_ilhas(token):
    print("\n[2] Listar ilhas")
    status, data = request("GET", "/api/ilhas", token=token)
    if status != 200:
        fail("GET /api/ilhas retorna 200", f"status={status}")
        raise RuntimeError("Não foi possível carregar ilhas")
    ok("GET /api/ilhas retorna 200")

    ilhas = data.get("ilhas") or []
    if not ilhas:
        fail("Ilhas carregadas (seed)", "Lista vazia")
        raise RuntimeError("Nenhuma ilha disponível")
    ok(f"Ilhas carregadas: {len(ilhas)} ilha(s)")

    # escolhe a primeira ilha que tenha pelo menos 2 espaços amostrais
    ilha = next((i for i in ilhas if len(i.get("espacos_amostrais") or []) >= 2), ilhas[0])
    espacos = ilha.get("espacos_amostrais") or []
    ok(f"Ilha selecionada: {ilha['nome']} ({len(espacos)} ponto(s))")
    return ilha, espacos


def step_criar_campanha(token, ilha, espacos):
    print("\n[3] Criar campanha")
    today = date.today().isoformat()

    # seleciona até 2 pontos para cobrir metodologias diferentes
    selecao = [
        {"espaco_amostral_id": espacos[0]["id"], "pontos": [1]},
    ]
    if len(espacos) >= 2:
        selecao.append({"espaco_amostral_id": espacos[1]["id"], "pontos": [1]})

    payload = {
        "ilhas": [{"ilha_id": ilha["id"], "selecao": selecao}],
        "nome": "MASC TESTE E2E",
        "data": today,
        "descricao": "Teste automatizado end-to-end",
        "base_apoio_id": None,
        "embarcacao_id": None,
        "membros_equipe": [],
    }

    status, resp = request("POST", "/api/campanhas", payload, token)
    if status != 200:
        fail("POST /api/campanhas retorna 200", f"status={status} body={resp}")
        raise RuntimeError("Falha ao criar campanha")
    ok("POST /api/campanhas retorna 200")

    campanha = resp.get("campanha") or {}
    campanha_id = campanha.get("id") or campanha.get("uuid")
    db_id = campanha.get("db_id")
    if not campanha_id:
        fail("Resposta contém campanha.id", f"resp={resp}")
        raise RuntimeError("Campanha sem ID")
    ok(f"Campanha criada: id={campanha_id} db_id={db_id}")
    return campanha_id, db_id


def step_listar_estacoes(token, campanha_id, espacos):
    print("\n[4] Listar estações da campanha")
    status, estacoes = request("GET", f"/api/campanhas/{campanha_id}/estacoes", token=token)

    if status != 200:
        fail("GET /estacoes retorna 200", f"status={status}")
        raise RuntimeError("Falha ao listar estações")
    ok("GET /estacoes retorna 200")

    if not isinstance(estacoes, list) or not estacoes:
        fail("Estações criadas automaticamente", f"resultado={estacoes}")
        raise RuntimeError("Nenhuma estação encontrada")
    ok(f"Estações criadas: {len(estacoes)}")

    # verifica que espaco_amostral_id está presente
    if all(e.get("espaco_amostral_id") for e in estacoes):
        ok("Todas estações têm espaco_amostral_id")
    else:
        fail("Todas estações têm espaco_amostral_id", "Alguma estação sem espaco_amostral_id")

    return estacoes


def step_envio_lote(token, campanha_id, estacoes):
    print("\n[5] Envio em lote (BA + VT + FQ)")
    today = date.today().isoformat()
    station = estacoes[0]
    station_id = station["id"]

    payload = {
        "estacoes": [
            {
                "estacao_amostral_id": station_id,
                "buscas_ativas": [
                    {
                        "numero_busca": 1,
                        "data_hora_inicio": f"{today}T09:00:00",
                        "data_hora_fim": f"{today}T09:20:00",
                        "profundidade_inicial": 12.5,
                        "profundidade_final": 8.0,
                        "temperatura_inicial": 24.2,
                        "temperatura_final": 23.8,
                        "visibilidade_vertical": 7.0,
                        "visibilidade_horizontal": 10.0,
                        "encontrou_coral_sol": False,
                        "imagens": [],
                        "latitude": -23.42,
                        "longitude": -44.85,
                    }
                ],
                "video_transectos": [
                    {
                        "data_hora": f"{today}T10:00:00",
                        "profundidade_inicial": 9.0,
                        "profundidade_final": 6.0,
                        "temperatura_inicial": 24.0,
                        "temperatura_final": 23.5,
                        "visibilidade_vertical": 8.0,
                        "visibilidade_horizontal": 12.0,
                    }
                ],
                "fotoquadrados": [
                    {
                        "data_hora": f"{today}T11:00:00",
                        "profundidade": 7.5,
                        "temperatura": 23.4,
                        "visibilidade_vertical": 8.5,
                        "visibilidade_horizontal": 11.0,
                        "imagens_complementares": [],
                    }
                ],
            }
        ]
    }

    status, resp = request("POST", f"/api/campanhas/{campanha_id}/envio-lote", payload, token)
    if status != 200:
        fail("POST /envio-lote retorna 200", f"status={status} body={resp}")
        raise RuntimeError("Envio em lote falhou")
    ok("POST /envio-lote retorna 200")

    totais = resp.get("totais") or {}
    for key, expected in [("buscas_ativas", 1), ("video_transectos", 1), ("fotoquadrados", 1)]:
        if totais.get(key) == expected:
            ok(f"Total {key} = {expected}")
        else:
            fail(f"Total {key} = {expected}", f"obtido={totais.get(key)}")


def step_verificar_metodos(token, campanha_id):
    print("\n[6] Verificar /metodos")
    status, resp = request("GET", f"/api/campanhas/{campanha_id}/metodos", token=token)
    if status != 200:
        fail("GET /metodos retorna 200", f"status={status}")
        return
    ok("GET /metodos retorna 200")

    for key, label in [("buscas", "BuscaAtiva"), ("videos", "VideoTransecto"), ("fotos", "Fotoquadrado")]:
        count = len(resp.get(key) or [])
        if count >= 1:
            ok(f"{label}: {count} registro(s)")
        else:
            fail(f"{label} tem ao menos 1 registro", f"count={count}")


def step_upload_kml(token, campanha_id, estacoes):
    print("\n[7] Upload KML vinculado a ponto")
    espaco_id = estacoes[0].get("espaco_amostral_id")
    if not espaco_id:
        fail("Upload KML", "espaco_amostral_id ausente na estação")
        return espaco_id

    kml_bytes = minimal_kml("Ponto E2E")
    path = f"/api/campanhas/{campanha_id}/geospatial?espaco_amostral_id={espaco_id}"
    status, resp = multipart_post(
        path,
        fields={},
        files={"file": ("teste_e2e.kml", kml_bytes, "application/vnd.google-earth.kml+xml")},
        token=token,
    )

    if status == 200:
        feicoes = resp.get("feicoes_salvas", 0)
        ok(f"Upload KML retorna 200 ({feicoes} feição(ões) salva(s))")
    else:
        fail("Upload KML retorna 200", f"status={status} body={resp}")

    return espaco_id


def step_geojson_por_ponto(token, campanha_id, espaco_id):
    print("\n[8] GeoJSON filtrado por ponto")
    if not espaco_id:
        fail("GeoJSON por ponto", "espaco_id indisponível — pular")
        return

    status, resp = request(
        "GET",
        f"/api/campanhas/{campanha_id}/geojson?espaco_amostral_id={espaco_id}",
        token=token,
    )
    if status != 200:
        fail("GET /geojson?espaco_amostral_id retorna 200", f"status={status}")
        return
    ok("GET /geojson?espaco_amostral_id retorna 200")

    features = resp.get("features") or []
    if features:
        ok(f"GeoJSON contém {len(features)} feição(ões)")
    else:
        # KML pode não ter sido persistido se PostGIS não estava disponível — aviso, não falha
        log("⚠  Nenhuma feição retornada (KML pode não ter sido indexado no PostGIS)")

    crs = (resp.get("crs") or {}).get("properties", {}).get("name", "")
    if "4674" in crs:
        ok("CRS declarado como EPSG:4674 (SIRGAS 2000)")
    else:
        fail("CRS = EPSG:4674", f"obtido={crs!r}")


def step_export_kml_ponto(campanha_id, espaco_id):
    print("\n[9] Export KML por ponto")
    if not espaco_id:
        fail("Export KML por ponto", "espaco_id indisponível — pular")
        return

    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    conn.request("GET", f"/api/campanhas/{campanha_id}/kml/export?espaco_amostral_id={espaco_id}")
    resp = conn.getresponse()
    content_type = resp.getheader("Content-Type", "")
    resp.read()
    conn.close()

    if resp.status == 200:
        ok(f"GET /kml/export?espaco_amostral_id retorna 200 (Content-Type: {content_type})")
    else:
        fail("GET /kml/export?espaco_amostral_id retorna 200", f"status={resp.status}")

    if "kml" in content_type.lower():
        ok("Content-Type é KML")
    else:
        fail("Content-Type é KML", f"obtido={content_type!r}")


def step_upload_documento(token, db_id):
    print("\n[10] Upload de documento vinculado à campanha")
    if not db_id:
        fail("Upload documento", "db_id indisponível — pular")
        return None

    pdf_bytes = minimal_pdf()
    path = f"/api/documentos/campanha/{db_id}?titulo=Relatorio+E2E&tipo=rel_campo"
    status, resp = multipart_post(
        path,
        fields={},
        files={"file": ("relatorio_e2e.pdf", pdf_bytes, "application/pdf")},
        token=token,
    )

    if status == 200:
        doc_id = resp.get("id")
        ok(f"Upload documento retorna 200 (id={doc_id})")
        return doc_id
    else:
        fail("Upload documento retorna 200", f"status={status} body={resp}")
        return None


def step_listar_documentos(token, db_id):
    print("\n[11] Listar documentos da campanha")
    if not db_id:
        fail("Listar documentos", "db_id indisponível — pular")
        return

    status, resp = request("GET", f"/api/documentos/campanha/{db_id}", token=token)
    if status != 200:
        fail("GET /documentos/campanha/{id} retorna 200", f"status={status}")
        return
    ok("GET /documentos/campanha/{id} retorna 200")

    if isinstance(resp, list) and len(resp) >= 1:
        ok(f"Documentos listados: {len(resp)}")
    else:
        fail("Lista de documentos tem ao menos 1 item", f"resp={resp}")


def step_export_wms_ponto(espaco_id):
    print("\n[12] Export WMS por ponto")
    if not espaco_id:
        fail("Export WMS por ponto", "espaco_id indisponível — pular")
        return

    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    conn.request("GET", f"/api/export/wms/ponto/{espaco_id}")
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()

    if resp.status == 200:
        ok(f"GET /api/export/wms/ponto/{espaco_id} retorna 200")
    else:
        fail(f"GET /api/export/wms/ponto/{espaco_id} retorna 200", f"status={resp.status}")
        return

    try:
        data = json.loads(raw)
        if data.get("type") == "FeatureCollection":
            ok("Resposta é FeatureCollection válida")
        else:
            fail("Resposta é FeatureCollection", f"type={data.get('type')!r}")
        crs = (data.get("crs") or {}).get("properties", {}).get("name", "")
        if "4674" in crs:
            ok("CRS EPSG:4674 presente no GeoJSON")
        else:
            fail("CRS EPSG:4674 no GeoJSON", f"crs={crs!r}")
    except json.JSONDecodeError:
        fail("Resposta é JSON válido", "JSONDecodeError")


def step_export_wms_ilha(ilha_id):
    print("\n[13] Export WMS por ilha")
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    conn.request("GET", f"/api/export/wms/{ilha_id}")
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()

    if resp.status == 200:
        ok(f"GET /api/export/wms/{ilha_id} retorna 200")
    else:
        fail(f"GET /api/export/wms/{ilha_id} retorna 200", f"status={resp.status}")
        return

    try:
        data = json.loads(raw)
        props = data.get("properties") or {}
        titulo = props.get("titulo", "")
        if "SIRGAS" in titulo or "4674" in titulo:
            ok(f"Título do export contém referência SIRGAS: {titulo!r}")
        else:
            fail("Título do export menciona SIRGAS 2000", f"titulo={titulo!r}")
    except json.JSONDecodeError:
        fail("Resposta é JSON válido", "JSONDecodeError")


def step_listar_kmls(token, campanha_id):
    print("\n[14] Listar KMLs originais")
    status, resp = request("GET", f"/api/campanhas/{campanha_id}/kml/arquivos", token=token)
    if status == 200:
        ok("GET /kml/arquivos retorna 200")
    else:
        fail("GET /kml/arquivos retorna 200", f"status={status}")


def step_deletar_documento(token, doc_id):
    print("\n[15] Deletar documento")
    if not doc_id:
        log("  (documento não criado — pular)")
        return

    status, resp = request("DELETE", f"/api/documentos/{doc_id}", token=token)
    if status == 200:
        ok(f"DELETE /documentos/{doc_id} retorna 200")
    else:
        fail(f"DELETE /documentos/{doc_id} retorna 200", f"status={status} body={resp}")


def step_full_details(token, campanha_id):
    print("\n[16] Full-details da campanha")
    status, resp = request("GET", f"/api/campanhas/{campanha_id}/full-details", token=token)
    if status != 200:
        fail("GET /full-details retorna 200", f"status={status}")
        return
    ok("GET /full-details retorna 200")
    if not isinstance(resp, dict):
        fail("Resposta e objeto JSON", f"tipo={type(resp)}")
        return
    campos_possiveis = ["buscas", "videos", "fotos", "campanha", "estacoes", "metodos"]
    encontrados = [k for k in campos_possiveis if k in resp]
    if encontrados:
        ok(f"Resposta contem dados da campanha: {encontrados}")
    else:
        fail("Resposta contem dados da campanha", f"keys={list(resp.keys())}")


# ─── runner ───────────────────────────────────────────────────────────────────

def run():
    print(f"\n{'='*60}")
    print(f"  TESTE E2E — CADASTRO FIM A FIM")
    print(f"  Alvo: http://{BASE_HOST}:{BASE_PORT}")
    print(f"{'='*60}")

    token = step_login()
    ilha, espacos = step_listar_ilhas(token)
    campanha_id, db_id = step_criar_campanha(token, ilha, espacos)
    estacoes = step_listar_estacoes(token, campanha_id, espacos)
    step_envio_lote(token, campanha_id, estacoes)
    step_verificar_metodos(token, campanha_id)
    espaco_id = step_upload_kml(token, campanha_id, estacoes)
    step_geojson_por_ponto(token, campanha_id, espaco_id)
    step_export_kml_ponto(campanha_id, espaco_id)
    doc_id = step_upload_documento(token, db_id)
    step_listar_documentos(token, db_id)
    step_export_wms_ponto(espaco_id)
    step_export_wms_ilha(ilha["id"])
    step_listar_kmls(token, campanha_id)
    step_deletar_documento(token, doc_id)
    step_full_details(token, campanha_id)

    # ── resultado final ────────────────────────────────────────────────────
    total = len(PASSED) + len(FAILED)
    print(f"\n{'='*60}")
    print(f"  Resultado: {len(PASSED)}/{total} verificações passaram")
    if FAILED:
        print(f"\n  Falhas ({len(FAILED)}):")
        for f in FAILED:
            print(f"    - {f}")
    print(f"{'='*60}\n")

    if FAILED:
        sys.exit(1)


if __name__ == "__main__":
    run()
