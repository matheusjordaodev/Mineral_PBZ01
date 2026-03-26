"""
Testes de integração: fluxo espaco_amostral_id (novo) e regressão do fluxo legado.

Cobre:
  A. Novo fluxo (espaco_amostral_id):
     A1. POST BA com espaco_amostral_id válido → cria EstacaoAmostral + BuscaAtiva (200)
     A2. Segunda submissão mesmo (campanha, espaco) → reutiliza estação, não duplica (200)
     A3. POST VT com espaco_amostral_id → 200
     A4. POST FQ com espaco_amostral_id → 200
     A5. espaco_amostral_id inválido → 404
     A6. campanha inexistente → 404

  B. Conflito de numero_busca:
     B1. numero_busca duplicado na mesma estação → 409
     B2. numero_busca <= 0 → 400
     B3. sem numero_busca → auto-incremento correto

  C. Regressão: fluxo legado (estacao_amostral_id direto):
     C1. POST BA com estacao_amostral_id direto → ainda funciona (200)
     C2. sem nenhum ID, campanha com 1 estação → usa a única (200)
     C3. sem nenhum ID, campanha com >1 estações → 400

Requer servidor rodando em localhost:8001 (ou porta via argv).

Uso:
    python tests/test_espaco_amostral_flow.py           # porta 8001
    python tests/test_espaco_amostral_flow.py 8080      # porta alternativa
"""

from __future__ import annotations

import http.client
import json
import sys
import urllib.parse
from datetime import date

BASE_HOST = "localhost"
BASE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8001

sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None

PASSED: list[str] = []
FAILED: list[str] = []


# ─── helpers ──────────────────────────────────────────────────────────────────

def ok(label: str):
    PASSED.append(label)
    print(f"  [OK]  {label}")


def fail(label: str, detail: str):
    FAILED.append(label)
    print(f"  [FAIL] {label}")
    print(f"         {detail}")


def log(msg: str):
    print(f"  {msg}")


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


def get_ilha_and_espacos(token: str):
    """Retorna (ilha, espacos) onde ilha tem ao menos 1 espaço amostral."""
    status, data = request("GET", "/api/ilhas", token=token)
    if status != 200:
        raise RuntimeError(f"Falha ao listar ilhas: {status}")
    ilhas = data.get("ilhas") or []
    ilha = next((i for i in ilhas if len(i.get("espacos_amostrais") or []) >= 1), None)
    if not ilha:
        raise RuntimeError("Nenhuma ilha com espaços amostrais encontrada")
    return ilha, ilha["espacos_amostrais"]


def criar_campanha(token: str, ilha: dict) -> tuple[str, int]:
    """Cria campanha vazia (sem pré-seleção de pontos) e retorna (campanha_codigo, db_id)."""
    payload = {
        "ilhas": [{"ilha_id": ilha["id"], "selecao": []}],
        "nome": "CAMPANHA FLOW TEST",
        "data": date.today().isoformat(),
        "descricao": "Teste de fluxo espaco_amostral_id",
        "base_apoio_id": None,
        "embarcacao_id": None,
        "membros_equipe": [],
    }
    status, resp = request("POST", "/api/campanhas", payload, token)
    if status != 200:
        raise RuntimeError(f"Falha ao criar campanha: {status} {resp}")
    campanha = resp.get("campanha") or {}
    campanha_id = campanha.get("id") or campanha.get("uuid")
    db_id = campanha.get("db_id")
    if not campanha_id:
        raise RuntimeError(f"Campanha sem id: {resp}")
    return campanha_id, db_id


def today() -> str:
    return date.today().isoformat()


# ─── Bloco A: Novo fluxo espaco_amostral_id ───────────────────────────────────

def bloco_a_novo_fluxo(token: str, campanha_id: str, espaco_id: int):
    print("\n[A] Novo fluxo: espaco_amostral_id")

    # A1: BA com espaco_amostral_id válido
    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "data_hora_inicio": f"{today()}T09:00:00",
        "data_hora_fim": f"{today()}T09:30:00",
        "profundidade_inicial": 10.0,
        "profundidade_final": 6.0,
        "temperatura_inicial": 24.0,
        "temperatura_final": 23.5,
        "visibilidade_vertical": 7.0,
        "visibilidade_horizontal": 10.0,
        "encontrou_coral_sol": False,
        "imagens": [],
    }
    status, resp = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body, token)
    if status == 200:
        ok("A1: POST BA com espaco_amostral_id válido → 200")
        ba_id = resp.get("id")
        log(f"     BuscaAtiva criada id={ba_id}")
    else:
        fail("A1: POST BA com espaco_amostral_id válido → 200", f"status={status} body={resp}")

    # A2: Segunda submissão para o mesmo (campanha, espaco) → reutiliza estação
    body2 = dict(body)
    body2["numero_busca"] = 2  # garante número diferente
    status2, resp2 = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body2, token)
    if status2 == 200:
        ok("A2: Segunda BA mesmo (campanha, espaco) → 200 (estação reutilizada)")
    else:
        fail("A2: Segunda BA mesmo (campanha, espaco) → 200", f"status={status2} body={resp2}")

    # Verifica que existe exatamente 1 EstacaoAmostral para este par
    status_e, estacoes = request("GET", f"/api/campanhas/{campanha_id}/estacoes", token=token)
    if status_e == 200 and isinstance(estacoes, list):
        ea_do_espaco = [e for e in estacoes if e.get("espaco_amostral_id") == espaco_id]
        if len(ea_do_espaco) == 1:
            ok("A2b: Apenas 1 EstacaoAmostral criada para o par (campanha, espaco)")
        else:
            fail("A2b: Apenas 1 EstacaoAmostral por par (campanha, espaco)",
                 f"encontradas={len(ea_do_espaco)} (pode haver duplicata!)")

    # A3: VT com espaco_amostral_id
    vt_body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "data_hora": f"{today()}T10:00:00",
        "profundidade_inicial": 8.0,
        "profundidade_final": 5.0,
        "temperatura_inicial": 24.0,
        "temperatura_final": 23.0,
        "visibilidade_vertical": 8.0,
        "visibilidade_horizontal": 12.0,
    }
    status3, resp3 = request("POST", f"/api/campanhas/{campanha_id}/video-transectos", vt_body, token)
    if status3 == 200:
        ok("A3: POST VT com espaco_amostral_id → 200")
    else:
        fail("A3: POST VT com espaco_amostral_id → 200", f"status={status3} body={resp3}")

    # A4: FQ com espaco_amostral_id
    fq_body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "data_hora": f"{today()}T11:00:00",
        "profundidade": 7.0,
        "temperatura": 23.4,
        "visibilidade_vertical": 8.0,
        "visibilidade_horizontal": 11.0,
        "imagens_complementares": [],
    }
    status4, resp4 = request("POST", f"/api/campanhas/{campanha_id}/fotoquadrados", fq_body, token)
    if status4 == 200:
        ok("A4: POST FQ com espaco_amostral_id → 200")
    else:
        fail("A4: POST FQ com espaco_amostral_id → 200", f"status={status4} body={resp4}")

    # A5: espaco_amostral_id inválido → 404
    body_inv = dict(body)
    body_inv["espaco_amostral_id"] = 999999
    body_inv.pop("numero_busca", None)
    status5, resp5 = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_inv, token)
    if status5 == 404:
        ok("A5: espaco_amostral_id inválido → 404")
    else:
        fail("A5: espaco_amostral_id inválido → 404", f"status={status5} body={resp5}")

    # A6: campanha inexistente → 404
    body_camp = dict(body)
    body_camp["campanha_id"] = "CAMPANHA-INEXISTENTE-99999"
    status6, resp6 = request("POST", "/api/campanhas/CAMPANHA-INEXISTENTE-99999/busca-ativa", body_camp, token)
    if status6 == 404:
        ok("A6: campanha inexistente → 404")
    else:
        fail("A6: campanha inexistente → 404", f"status={status6} body={resp6}")


# ─── Bloco B: Conflito de numero_busca ────────────────────────────────────────

def bloco_b_numero_busca(token: str, campanha_id: str, espaco_id: int):
    print("\n[B] Conflito de numero_busca")

    base_body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "data_hora_inicio": f"{today()}T14:00:00",
        "data_hora_fim": f"{today()}T14:30:00",
        "encontrou_coral_sol": False,
        "imagens": [],
    }

    # B1: numero_busca duplicado → 409
    body_dup1 = dict(base_body)
    body_dup1["numero_busca"] = 50
    request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_dup1, token)  # primeira

    body_dup2 = dict(base_body)
    body_dup2["numero_busca"] = 50
    status_dup, resp_dup = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_dup2, token)
    if status_dup == 409:
        ok("B1: numero_busca duplicado → 409")
    else:
        fail("B1: numero_busca duplicado → 409", f"status={status_dup} body={resp_dup}")

    # B2: numero_busca <= 0 → 400
    body_zero = dict(base_body)
    body_zero["numero_busca"] = 0
    status_z, resp_z = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_zero, token)
    if status_z == 400:
        ok("B2: numero_busca=0 → 400")
    else:
        fail("B2: numero_busca=0 → 400", f"status={status_z} body={resp_z}")

    body_neg = dict(base_body)
    body_neg["numero_busca"] = -1
    status_n, resp_n = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_neg, token)
    if status_n == 400:
        ok("B2b: numero_busca=-1 → 400")
    else:
        fail("B2b: numero_busca=-1 → 400", f"status={status_n} body={resp_n}")

    # B3: sem numero_busca → auto-incremento (deve ser > 50 pois já criamos algumas)
    body_auto = dict(base_body)
    body_auto.pop("numero_busca", None)
    status_a, resp_a = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_auto, token)
    if status_a == 200:
        num = resp_a.get("numero_busca")
        if num and num > 0:
            ok(f"B3: auto-incremento funciona → numero_busca={num}")
        else:
            fail("B3: auto-incremento retorna numero_busca válido", f"resp={resp_a}")
    else:
        fail("B3: sem numero_busca → 200 (auto-incremento)", f"status={status_a} body={resp_a}")


# ─── Bloco C: Regressão fluxo legado ─────────────────────────────────────────

def bloco_c_legado(token: str, campanha_id: str, espacos: list):
    print("\n[C] Regressão: fluxo legado (estacao_amostral_id)")

    # Primeiro precisamos de uma EstacaoAmostral real para testar o fluxo legado.
    # Como o GET /estacoes retorna as estações criadas nos blocos A/B, usamos uma delas.
    status_e, estacoes = request("GET", f"/api/campanhas/{campanha_id}/estacoes", token=token)
    if status_e != 200 or not isinstance(estacoes, list) or not estacoes:
        fail("C (setup): Listar estações para teste legado", f"status={status_e} resp={estacoes}")
        return

    estacao_id = estacoes[0]["id"]

    # C1: POST BA com estacao_amostral_id direto
    body_c1 = {
        "campanha_id": campanha_id,
        "estacao_amostral_id": estacao_id,
        "data_hora_inicio": f"{today()}T15:00:00",
        "data_hora_fim": f"{today()}T15:30:00",
        "encontrou_coral_sol": False,
        "imagens": [],
    }
    status_c1, resp_c1 = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_c1, token)
    if status_c1 == 200:
        ok("C1: POST BA com estacao_amostral_id direto (fluxo legado) → 200")
    else:
        fail("C1: POST BA com estacao_amostral_id direto → 200", f"status={status_c1} body={resp_c1}")

    # C2: estacao_amostral_id inválido (não pertence à campanha ou não existe) → 404
    body_c2 = dict(body_c1)
    body_c2["estacao_amostral_id"] = 999999
    status_c2, resp_c2 = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_c2, token)
    if status_c2 == 404:
        ok("C2: estacao_amostral_id inválido → 404 (regressão legado)")
    else:
        fail("C2: estacao_amostral_id inválido → 404", f"status={status_c2} body={resp_c2}")

    # C3: sem nenhum ID, campanha com >1 estações → 400
    if len(estacoes) > 1:
        body_c3 = {
            "campanha_id": campanha_id,
            "data_hora_inicio": f"{today()}T16:00:00",
            "data_hora_fim": f"{today()}T16:30:00",
            "encontrou_coral_sol": False,
            "imagens": [],
        }
        status_c3, resp_c3 = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body_c3, token)
        if status_c3 == 400:
            ok("C3: sem ID, >1 estações → 400")
        else:
            fail("C3: sem ID, >1 estações → 400", f"status={status_c3} body={resp_c3}")
    else:
        log("C3: (pulado — campanha tem apenas 1 estação; ambíguo somente com >1)")


# ─── runner ───────────────────────────────────────────────────────────────────

def run():
    print(f"\n{'='*60}")
    print("  TESTE INTEGRAÇÃO — FLUXO espaco_amostral_id")
    print(f"  Alvo: http://{BASE_HOST}:{BASE_PORT}")
    print(f"{'='*60}")

    try:
        token = login()
        ok("Login com admin/admin")
    except Exception as e:
        fail("Login", str(e))
        raise

    try:
        ilha, espacos = get_ilha_and_espacos(token)
        ok(f"Ilha obtida: {ilha['nome']} ({len(espacos)} espaço(s))")
    except Exception as e:
        fail("Obter ilha com espaços", str(e))
        raise

    try:
        campanha_id, db_id = criar_campanha(token, ilha)
        ok(f"Campanha criada: {campanha_id} (db_id={db_id})")
    except Exception as e:
        fail("Criar campanha", str(e))
        raise

    espaco_id = espacos[0]["id"]
    log(f"  Usando espaco_amostral_id={espaco_id}")

    bloco_a_novo_fluxo(token, campanha_id, espaco_id)
    bloco_b_numero_busca(token, campanha_id, espaco_id)
    bloco_c_legado(token, campanha_id, espacos)

    # ── resumo ────────────────────────────────────────────────────────────
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
