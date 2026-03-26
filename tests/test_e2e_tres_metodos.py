"""
Teste E2E: 3 métodos em pontos diferentes da mesma ilha.

Fluxo:
  1.  Login
  2.  Busca ilha com pontos suficientes (>= 3 espaços amostrais)
  3.  Criar campanha associada à ilha
  4.  BA  → ponto BA  (metodologia BA)
  5.  VT  → ponto VT  (metodologia FQ e VT)
  6.  FQ  → ponto FQ  (metodologia FQ e VT, diferente do VT)
  7.  Verificar /full-details mostra os 3 registros
  8.  Limpeza: deleta BA, VT, FQ e campanha

Uso:
    python tests/test_e2e_tres_metodos.py           # localhost:8080
    python tests/test_e2e_tres_metodos.py 8081
"""

from __future__ import annotations

import http.client
import json
import sys
import urllib.parse
from datetime import date, datetime

BASE_HOST = "localhost"
BASE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8080

sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None

PASSED: list[str] = []
FAILED: list[str] = []


# ─── Helpers ──────────────────────────────────────────────────────────────────

def ok(label: str):
    PASSED.append(label)
    print(f"  [OK]  {label}")


def fail(label: str, detail: str):
    FAILED.append(label)
    print(f"  [FAIL] {label}")
    print(f"         {detail}")


def log(msg: str):
    print(f"        {msg}")


def request(method: str, path: str, body=None, token: str = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=30)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def today() -> str:
    return date.today().isoformat()


def server_available() -> bool:
    try:
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        conn.close()
        return resp.status < 500
    except Exception:
        return False


# ─── Setup ────────────────────────────────────────────────────────────────────

def login() -> str:
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
    params = urllib.parse.urlencode({"username": "admin", "password": "admin"})
    conn.request("POST", "/api/login", params,
                 {"Content-Type": "application/x-www-form-urlencoded"})
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"Login falhou: {resp.status} {raw}")
    return json.loads(raw)["access_token"]


def escolher_pontos(token: str) -> tuple[dict, dict, dict, dict]:
    """
    Retorna (ilha, espaco_ba, espaco_vt, espaco_fq) onde:
      - espaco_ba  tem metodologia 'BA'
      - espaco_vt  tem metodologia 'FQ e VT'
      - espaco_fq  tem metodologia 'FQ e VT', diferente do espaco_vt
    """
    status, data = request("GET", "/api/ilhas", token=token)
    if status != 200:
        raise RuntimeError(f"Falha ao listar ilhas: {status}")

    for ilha in (data.get("ilhas") or []):
        espacos = [e for e in (ilha.get("espacos_amostrais") or []) if not e.get("deleted_at")]
        bas  = [e for e in espacos if e.get("metodologia") == "BA"]
        fqvt = [e for e in espacos if e.get("metodologia") == "FQ e VT"]
        if bas and len(fqvt) >= 2:
            return ilha, bas[0], fqvt[0], fqvt[1]

    raise RuntimeError(
        "Nenhuma ilha tem ao mesmo tempo >=1 ponto BA e >=2 pontos FQ e VT. "
        "Verifique os cadastros de espaços amostrais."
    )


def criar_campanha(token: str, ilha: dict) -> str:
    payload = {
        "nome": f"E2E 3METODOS {today()}",
        "data": today(),
        "descricao": "Campanha gerada por test_e2e_tres_metodos.py",
        "ilhas": [{"ilha_id": ilha["id"], "selecao": []}],
        "base_apoio_id": None,
        "embarcacao_id": None,
        "membros_equipe": [],
    }
    status, resp = request("POST", "/api/campanhas", payload, token)
    if status not in (200, 201):
        raise RuntimeError(f"Falha ao criar campanha: {status} {resp}")
    campanha = resp.get("campanha") or {}
    campanha_id = campanha.get("id") or campanha.get("uuid")
    if not campanha_id:
        raise RuntimeError(f"Campanha sem id: {resp}")
    return campanha_id


# ─── Bloco 1: Busca Ativa ─────────────────────────────────────────────────────

def testar_ba(token: str, campanha_id: str, espaco: dict) -> int | None:
    label_ponto = espaco.get("codigo", str(espaco["id"]))
    print(f"\n[BA] Busca Ativa — ponto {label_ponto}")

    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco["id"],
        "numero_busca": 1,
        "data_hora_inicio": f"{today()}T08:00:00",
        "data_hora_fim":    f"{today()}T08:45:00",
        "encontrou_coral_sol": True,
        "profundidade_inicial": 12.0,
        "profundidade_final":   8.0,
        "temperatura_inicial":  26.0,
        "temperatura_final":    25.5,
        "visibilidade_vertical":    8.0,
        "visibilidade_horizontal":  12.0,
        "imagens": [
            "https://example.com/ba_foto1.jpg",
            "https://example.com/ba_foto2.jpg",
        ],
        "planilha_excel_url":   "https://example.com/planilha_ba.xlsx",
        "arquivo_percurso_url": "https://example.com/percurso_ba.kml",
        "detalhes_coral": {
            "especie": "Tubastraea coccinea",
            "quantidade_estimada": 5,
            "estado": "vivo",
        },
        "dados_meteo": {"vento_velocidade": 12.0, "estado_mar": "moderado"},
        "observacoes": "BA criada por test_e2e_tres_metodos",
    }

    status, resp = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body, token)
    if status != 200:
        fail(f"BA-1 [{label_ponto}]: POST → 200", f"status={status} body={resp}")
        return None
    ok(f"BA-1 [{label_ponto}]: POST busca-ativa → 200")
    ba_id = resp.get("id")
    log(f"id={ba_id}")

    checks = [
        ("numero_busca == 1",           resp.get("numero_busca") == 1),
        ("encontrou_coral_sol == True",  resp.get("encontrou_coral_sol") is True),
        ("imagens com 2 itens",          len(resp.get("imagens") or []) == 2),
        ("planilha_excel_url presente",  bool(resp.get("planilha_excel_url"))),
        ("arquivo_percurso_url presente",bool(resp.get("arquivo_percurso_url"))),
        ("profundidade_inicial == 12.0", resp.get("profundidade_inicial") == 12.0),
        ("dados_meteo presente",         isinstance(resp.get("dados_meteo"), dict)),
        ("protocolos_dafor criado",      len(resp.get("protocolos_dafor") or []) >= 1),
    ]
    for clabel, passed in checks:
        if passed:
            ok(f"BA-1 [{label_ponto}] campo: {clabel}")
        else:
            fail(f"BA-1 [{label_ponto}] campo: {clabel}", str(resp.get(clabel.split()[0])))

    # Listagem
    status, lista = request("GET", f"/api/campanhas/{campanha_id}/busca-ativa", token=token)
    if status == 200 and any(b.get("id") == ba_id for b in lista):
        ok(f"BA-2 [{label_ponto}]: aparece na listagem")
    else:
        fail(f"BA-2 [{label_ponto}]: aparece na listagem", f"status={status}")

    return ba_id


# ─── Bloco 2: Vídeo Transecto ─────────────────────────────────────────────────

def testar_vt(token: str, campanha_id: str, espaco: dict) -> int | None:
    label_ponto = espaco.get("codigo", str(espaco["id"]))
    print(f"\n[VT] Vídeo Transecto — ponto {label_ponto}")

    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco["id"],
        "data_hora":     f"{today()}T10:00:00",
        "data_hora_fim": f"{today()}T10:40:00",
        "profundidade_inicial": 10.0,
        "profundidade_final":   6.5,
        "temperatura_inicial":  26.5,
        "temperatura_final":    25.0,
        "visibilidade_vertical":    9.0,
        "visibilidade_horizontal":  15.0,
        "riqueza_especifica":    22.0,
        "diversidade_shannon":   2.8,
        "equitabilidade_jaccard": 0.75,
        "video_url":    "https://example.com/vt_01.mp4",
        "arquivo_percurso_url": "https://example.com/percurso_vt.kml",
        "dados_meteo": {"vento_velocidade": 8.0, "estado_mar": "calmo"},
        "observacoes": "VT criado por test_e2e_tres_metodos",
    }

    status, resp = request("POST", f"/api/campanhas/{campanha_id}/video-transectos", body, token)
    if status != 200:
        fail(f"VT-1 [{label_ponto}]: POST → 200", f"status={status} body={resp}")
        return None
    ok(f"VT-1 [{label_ponto}]: POST video-transectos → 200")
    vt_id = resp.get("id")
    log(f"id={vt_id}")

    checks = [
        ("profundidade_inicial == 10.0",  resp.get("profundidade_inicial") == 10.0),
        ("riqueza_especifica == 22.0",    resp.get("riqueza_especifica") == 22.0),
        ("diversidade_shannon == 2.8",    resp.get("diversidade_shannon") == 2.8),
        ("video_url presente",            bool(resp.get("video_url"))),
        ("dados_meteo presente",          isinstance(resp.get("dados_meteo"), dict)),
    ]
    for clabel, passed in checks:
        if passed:
            ok(f"VT-1 [{label_ponto}] campo: {clabel}")
        else:
            fail(f"VT-1 [{label_ponto}] campo: {clabel}", str(resp.get(clabel.split()[0])))

    # Listagem
    status, lista = request("GET", f"/api/campanhas/{campanha_id}/video-transectos", token=token)
    if status == 200 and any(v.get("id") == vt_id for v in lista):
        ok(f"VT-2 [{label_ponto}]: aparece na listagem")
    else:
        fail(f"VT-2 [{label_ponto}]: aparece na listagem", f"status={status}")

    return vt_id


# ─── Bloco 3: Fotoquadrado ────────────────────────────────────────────────────

def testar_fq(token: str, campanha_id: str, espaco: dict) -> int | None:
    label_ponto = espaco.get("codigo", str(espaco["id"]))
    print(f"\n[FQ] Fotoquadrado — ponto {label_ponto}")

    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco["id"],
        "data_hora":     f"{today()}T11:00:00",
        "data_hora_fim": f"{today()}T11:30:00",
        "profundidade":  5.0,
        "temperatura":   26.0,
        "visibilidade_vertical":    7.0,
        "visibilidade_horizontal":  10.0,
        "imagem_mosaico_url": "https://example.com/fq_mosaico.jpg",
        "imagens_complementares": [
            "https://example.com/fq_comp1.jpg",
            "https://example.com/fq_comp2.jpg",
        ],
        "riqueza_especifica":    18.0,
        "diversidade_shannon":   2.5,
        "equitabilidade_jaccard": 0.82,
        "arquivo_percurso_url": "https://example.com/percurso_fq.kml",
        "dados_meteo": {"vento_velocidade": 5.0, "estado_mar": "calmo"},
        "observacoes": "FQ criado por test_e2e_tres_metodos",
    }

    status, resp = request("POST", f"/api/campanhas/{campanha_id}/fotoquadrados", body, token)
    if status != 200:
        fail(f"FQ-1 [{label_ponto}]: POST → 200", f"status={status} body={resp}")
        return None
    ok(f"FQ-1 [{label_ponto}]: POST fotoquadrados → 200")
    fq_id = resp.get("id")
    log(f"id={fq_id}")

    checks = [
        ("profundidade == 5.0",              resp.get("profundidade") == 5.0),
        ("imagem_mosaico_url presente",       bool(resp.get("imagem_mosaico_url"))),
        ("imagens_complementares com 2 itens", len(resp.get("imagens_complementares") or []) == 2),
        ("riqueza_especifica == 18.0",        resp.get("riqueza_especifica") == 18.0),
        ("dados_meteo presente",              isinstance(resp.get("dados_meteo"), dict)),
    ]
    for clabel, passed in checks:
        if passed:
            ok(f"FQ-1 [{label_ponto}] campo: {clabel}")
        else:
            fail(f"FQ-1 [{label_ponto}] campo: {clabel}", str(resp.get(clabel.split()[0])))

    # Listagem
    status, lista = request("GET", f"/api/campanhas/{campanha_id}/fotoquadrados", token=token)
    if status == 200 and any(f.get("id") == fq_id for f in lista):
        ok(f"FQ-2 [{label_ponto}]: aparece na listagem")
    else:
        fail(f"FQ-2 [{label_ponto}]: aparece na listagem", f"status={status}")

    return fq_id


# ─── Bloco 4: Verificação cruzada via full-details ────────────────────────────

def verificar_full_details(token: str, campanha_id: str,
                           ba_id: int | None, vt_id: int | None, fq_id: int | None,
                           espaco_ba: dict, espaco_vt: dict, espaco_fq: dict) -> None:
    print("\n[FULL] Verificação cruzada via /full-details")

    status, data = request("GET", f"/api/campanhas/{campanha_id}/full-details", token=token)
    if status != 200:
        fail("FULL-1: GET /full-details → 200", f"status={status}")
        return
    ok("FULL-1: GET /full-details → 200")

    buscas = data.get("buscas") or []
    videos  = data.get("videos") or []
    fotos   = data.get("fotos") or []

    # BA no ponto correto
    if ba_id and any(b.get("id") == ba_id for b in buscas):
        ok(f"FULL-2: BA (id={ba_id}) presente em full-details")
    else:
        fail(f"FULL-2: BA (id={ba_id}) presente em full-details",
             f"buscas={[b.get('id') for b in buscas]}")

    # VT no ponto correto
    if vt_id and any(v.get("id") == vt_id for v in videos):
        ok(f"FULL-3: VT (id={vt_id}) presente em full-details")
    else:
        fail(f"FULL-3: VT (id={vt_id}) presente em full-details",
             f"videos={[v.get('id') for v in videos]}")

    # FQ no ponto correto
    if fq_id and any(f.get("id") == fq_id for f in fotos):
        ok(f"FULL-4: FQ (id={fq_id}) presente em full-details")
    else:
        fail(f"FULL-4: FQ (id={fq_id}) presente em full-details",
             f"fotos={[f.get('id') for f in fotos]}")

    # Pontos diferentes — usa estacao_codigo (ex: "IC01") como identificador único
    codigos_ba  = {b.get("estacao_codigo") for b in buscas if b.get("id") == ba_id}
    codigos_vt  = {v.get("estacao_codigo") for v in videos  if v.get("id") == vt_id}
    codigos_fq  = {f.get("estacao_codigo") for f in fotos   if f.get("id") == fq_id}
    todos_diferentes = len(codigos_ba | codigos_vt | codigos_fq) == 3
    if todos_diferentes:
        ok(f"FULL-5: BA/VT/FQ em pontos distintos ({codigos_ba} / {codigos_vt} / {codigos_fq})")
    else:
        fail("FULL-5: BA/VT/FQ em pontos distintos",
             f"BA={codigos_ba} VT={codigos_vt} FQ={codigos_fq}")


# ─── Limpeza ──────────────────────────────────────────────────────────────────

def limpar(token: str, campanha_id: str,
           ba_id: int | None, vt_id: int | None, fq_id: int | None) -> None:
    print("\n[CLEANUP] Limpeza")

    if ba_id:
        s, r = request("DELETE", f"/api/busca-ativa/{ba_id}", token=token)
        ok("CLEANUP: BA deletada") if s == 200 else fail("CLEANUP: BA deletada", f"{s} {r}")

    if vt_id:
        s, r = request("DELETE", f"/api/video-transectos/{vt_id}", token=token)
        ok("CLEANUP: VT deletado") if s == 200 else fail("CLEANUP: VT deletado", f"{s} {r}")

    if fq_id:
        s, r = request("DELETE", f"/api/fotoquadrados/{fq_id}", token=token)
        ok("CLEANUP: FQ deletado") if s == 200 else fail("CLEANUP: FQ deletado", f"{s} {r}")

    s, r = request("DELETE", f"/api/campanhas/{campanha_id}", token=token)
    ok("CLEANUP: Campanha deletada") if s == 200 else fail("CLEANUP: Campanha deletada", f"{s} {r}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*62}")
    print(f"  Teste E2E: 3 métodos em pontos diferentes — {today()}")
    print(f"  Servidor: {BASE_HOST}:{BASE_PORT}")
    print(f"{'='*62}")

    if not server_available():
        print(f"\n[SKIP] Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
        sys.exit(0)

    # Login
    try:
        token = login()
        ok("SETUP: Login como admin → token obtido")
    except RuntimeError as e:
        print(f"  [FAIL] SETUP: {e}")
        sys.exit(1)

    # Escolher pontos
    try:
        ilha, esp_ba, esp_vt, esp_fq = escolher_pontos(token)
        ok(f"SETUP: Ilha '{ilha['nome']}' selecionada")
        ok(f"SETUP: Ponto BA  → {esp_ba.get('codigo')} (id={esp_ba['id']})")
        ok(f"SETUP: Ponto VT  → {esp_vt.get('codigo')} (id={esp_vt['id']})")
        ok(f"SETUP: Ponto FQ  → {esp_fq.get('codigo')} (id={esp_fq['id']})")
        assert esp_ba["id"] != esp_vt["id"] != esp_fq["id"] != esp_ba["id"], \
            "Pontos devem ser distintos"
        ok("SETUP: Pontos são distintos entre si")
    except (RuntimeError, AssertionError) as e:
        print(f"  [FAIL] SETUP: {e}")
        sys.exit(1)

    # Criar campanha
    try:
        campanha_id = criar_campanha(token, ilha)
        ok(f"SETUP: Campanha criada → {campanha_id}")
    except RuntimeError as e:
        print(f"  [FAIL] SETUP: {e}")
        sys.exit(1)

    # Executar os 3 métodos
    ba_id = testar_ba(token, campanha_id, esp_ba)
    vt_id = testar_vt(token, campanha_id, esp_vt)
    fq_id = testar_fq(token, campanha_id, esp_fq)

    # Verificação cruzada
    verificar_full_details(token, campanha_id, ba_id, vt_id, fq_id, esp_ba, esp_vt, esp_fq)

    # Limpeza
    limpar(token, campanha_id, ba_id, vt_id, fq_id)

    # Resultado
    total = len(PASSED) + len(FAILED)
    print(f"\n{'='*62}")
    print(f"  Resultado: {len(PASSED)}/{total} testes passaram")
    if FAILED:
        print(f"\n  Falhas ({len(FAILED)}):")
        for f in FAILED:
            print(f"    - {f}")
    print(f"{'='*62}\n")
    sys.exit(0 if not FAILED else 1)


if __name__ == "__main__":
    main()
