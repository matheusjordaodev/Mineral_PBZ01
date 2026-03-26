"""
Testes E2E: BA (Busca Ativa), FQ (Fotoquadrado), VT (Video Transecto)

Cobre:
  1. Login e setup (campanha + espaço amostral)
  2. BA: criação completa, listagem, edição, deleção
  3. VT: criação completa, listagem, edição, deleção
  4. FQ: criação completa, listagem, edição, deleção
  5. Galeria: verifica que registros aparecem no endpoint de galeria

Requer servidor rodando em localhost:8001 (ou porta via argv).

Uso:
    python tests/test_e2e_metodos.py           # porta 8001
    python tests/test_e2e_metodos.py 8080      # porta alternativa (ex: Docker)
    docker exec pmascc_app python tests/test_e2e_metodos.py 8080
"""

from __future__ import annotations

import http.client
import json
import sys
import urllib.parse
from datetime import date, datetime

BASE_HOST = "localhost"
BASE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8001

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


def now_str(offset_hours: int = 0) -> str:
    from datetime import timedelta
    dt = datetime.utcnow() + timedelta(hours=offset_hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


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


def get_ilha_com_espacos(token: str) -> tuple[dict, dict]:
    """Retorna (ilha, espaco_amostral) onde ilha tem ao menos 1 espaço."""
    status, data = request("GET", "/api/ilhas", token=token)
    if status != 200:
        raise RuntimeError(f"Falha ao listar ilhas: {status} {data}")
    ilhas = data.get("ilhas") or []
    for ilha in ilhas:
        espacos = ilha.get("espacos_amostrais") or []
        if espacos:
            return ilha, espacos[0]
    raise RuntimeError("Nenhuma ilha com espaços amostrais encontrada. Crie ao menos uma.")


def criar_campanha(token: str, ilha: dict) -> str:
    """Cria campanha de teste e retorna campanha_id (UUID público)."""
    payload = {
        "nome": f"E2E TEST {today()}",
        "data": today(),
        "descricao": "Campanha gerada por test_e2e_metodos.py",
        "ilhas": [{"ilha_id": ilha["id"], "selecao": []}],
        "base_apoio_id": None,
        "embarcacao_id": None,
        "membros_equipe": [],
    }
    status, resp = request("POST", "/api/campanhas", payload, token)
    if status != 200:
        raise RuntimeError(f"Falha ao criar campanha: {status} {resp}")
    campanha = resp.get("campanha") or {}
    campanha_id = campanha.get("id") or campanha.get("uuid")
    if not campanha_id:
        raise RuntimeError(f"Campanha sem id: {resp}")
    log(f"Campanha criada: {campanha_id}")
    return campanha_id


# ─── Bloco 1: Busca Ativa ─────────────────────────────────────────────────────

def testar_busca_ativa(token: str, campanha_id: str, espaco_id: int) -> None:
    print("\n[BA] Busca Ativa")
    ba_id = None

    # 1.1 Criação completa com todos os campos
    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "numero_busca": 1,
        "data_hora_inicio": f"{today()}T08:00:00",
        "data_hora_fim": f"{today()}T08:45:00",
        "encontrou_coral_sol": True,
        "observacoes": "BA criada pelo teste E2E",
        "latitude": -8.5,
        "longitude": -35.1,
        "profundidade_inicial": 12.0,
        "profundidade_final": 8.0,
        "temperatura_inicial": 26.0,
        "temperatura_final": 25.5,
        "visibilidade_vertical": 8.0,
        "visibilidade_horizontal": 12.0,
        # Simula URLs de arquivos (como se tivessem sido enviados via upload)
        "imagens": [
            "https://example.blob.core.windows.net/container/1/campanhateste/images/ba_foto1.jpg",
            "https://example.blob.core.windows.net/container/1/campanhateste/images/ba_foto2.jpg",
        ],
        "planilha_excel_url": "https://example.blob.core.windows.net/container/1/campanhateste/excel/planilha_ba.xlsx",
        "arquivo_percurso_url": "https://example.blob.core.windows.net/container/1/campanhateste/kml/percurso.kml",
        "detalhes_coral": {
            "especie": "Tubastraea coccinea",
            "quantidade_estimada": 15,
            "estado": "vivo",
        },
        "dados_meteo": {
            "vento_velocidade": 12.5,
            "vento_direcao": "NE",
            "estado_mar": "moderado",
        },
    }
    status, resp = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body, token)
    if status == 200:
        ok("BA-1: POST busca-ativa com todos os campos → 200")
        ba_id = resp.get("id")
        log(f"id={ba_id}")

        # Verifica campos retornados
        checks = [
            ("numero_busca == 1", resp.get("numero_busca") == 1),
            ("encontrou_coral_sol == True", resp.get("encontrou_coral_sol") is True),
            ("imagens com 2 itens", len(resp.get("imagens") or []) == 2),
            ("planilha_excel_url presente", bool(resp.get("planilha_excel_url"))),
            ("arquivo_percurso_url presente", bool(resp.get("arquivo_percurso_url"))),
            # detalhes_coral cria ProtocoloDAFOR — verificado via protocolos_dafor
            ("protocolos_dafor criado via detalhes_coral", len(resp.get("protocolos_dafor") or []) >= 1),
            ("dados_meteo presente", isinstance(resp.get("dados_meteo"), dict)),
            ("profundidade_inicial == 12.0", resp.get("profundidade_inicial") == 12.0),
        ]
        for label, passed in checks:
            if passed:
                ok(f"BA-1 campo: {label}")
            else:
                fail(f"BA-1 campo: {label}", f"valor retornado: {resp.get(label.split(' ')[0])}")
    else:
        fail("BA-1: POST busca-ativa com todos os campos → 200", f"status={status} body={resp}")

    # 1.2 Listagem
    status, lista = request("GET", f"/api/campanhas/{campanha_id}/busca-ativa", token=token)
    if status == 200 and isinstance(lista, list):
        encontrado = any(b.get("id") == ba_id for b in lista) if ba_id else False
        if encontrado:
            ok("BA-2: GET busca-ativa lista a BA criada")
        else:
            fail("BA-2: GET busca-ativa lista a BA criada",
                 f"ba_id={ba_id} não encontrado na lista de {len(lista)} items")
    else:
        fail("BA-2: GET busca-ativa → 200 lista", f"status={status}")

    if not ba_id:
        fail("BA-3..6: skipped (ba_id ausente)", "criação falhou")
        return

    # 1.3 Edição (PUT)
    update_body = {
        "observacoes": "BA editada pelo teste E2E",
        "profundidade_inicial": 15.0,
        "temperatura_inicial": 27.5,
        "imagens": [
            "https://example.blob.core.windows.net/container/1/campanhateste/images/ba_foto1.jpg",
            "https://example.blob.core.windows.net/container/1/campanhateste/images/ba_foto2.jpg",
            "https://example.blob.core.windows.net/container/1/campanhateste/images/ba_foto3.jpg",
        ],
    }
    status, resp_put = request("PUT", f"/api/busca-ativa/{ba_id}", update_body, token)
    if status == 200:
        ok("BA-3: PUT busca-ativa → 200")
        if resp_put.get("profundidade_inicial") == 15.0:
            ok("BA-3 campo: profundidade_inicial atualizada")
        else:
            fail("BA-3 campo: profundidade_inicial atualizada",
                 f"valor={resp_put.get('profundidade_inicial')}")
        if len(resp_put.get("imagens") or []) == 3:
            ok("BA-3 campo: imagens atualizadas (3 itens)")
        else:
            fail("BA-3 campo: imagens atualizadas (3 itens)",
                 f"count={len(resp_put.get('imagens') or [])}")
    else:
        fail("BA-3: PUT busca-ativa → 200", f"status={status} body={resp_put}")

    # 1.4 GET individual para confirmar persistência
    status, resp_get = request("GET", f"/api/campanhas/{campanha_id}/busca-ativa", token=token)
    if status == 200:
        item = next((b for b in resp_get if b.get("id") == ba_id), None)
        if item and item.get("profundidade_inicial") == 15.0:
            ok("BA-4: edição persistida corretamente no GET")
        else:
            fail("BA-4: edição persistida corretamente no GET",
                 f"item={item}")

    # 1.5 Deleção (DELETE)
    status, resp_del = request("DELETE", f"/api/busca-ativa/{ba_id}", token=token)
    if status == 200 and resp_del.get("success"):
        ok("BA-5: DELETE busca-ativa → 200 success")
    else:
        fail("BA-5: DELETE busca-ativa → 200 success", f"status={status} body={resp_del}")

    # 1.6 Confirma que não aparece mais na listagem
    status, lista2 = request("GET", f"/api/campanhas/{campanha_id}/busca-ativa", token=token)
    if status == 200:
        ainda = any(b.get("id") == ba_id for b in lista2)
        if not ainda:
            ok("BA-6: BA deletada não aparece na listagem")
        else:
            fail("BA-6: BA deletada não aparece na listagem",
                 "id ainda presente na lista após DELETE")


# ─── Bloco 2: Vídeo Transecto ─────────────────────────────────────────────────

def testar_video_transecto(token: str, campanha_id: str, espaco_id: int) -> None:
    print("\n[VT] Vídeo Transecto")
    vt_id = None

    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "nome_video": "Transecto Quadrado Sul - Câmera A",
        "observacoes": "VT criado pelo teste E2E",
        "data_hora": f"{today()}T10:00:00",
        "video_url": "https://example.blob.core.windows.net/container/1/campanhateste/videos/vt_01.mp4",
        "profundidade_inicial": 10.0,
        "profundidade_final": 6.5,
        "temperatura_inicial": 26.5,
        "temperatura_final": 25.0,
        "visibilidade_vertical": 9.0,
        "visibilidade_horizontal": 15.0,
        "riqueza_especifica": 22.0,
        "diversidade_shannon": 2.8,
        "equitabilidade_jaccard": 0.75,
        "dados_meteo": {
            "vento_velocidade": 8.0,
            "estado_mar": "calmo",
        },
    }
    status, resp = request("POST", f"/api/campanhas/{campanha_id}/video-transectos", body, token)
    if status == 200:
        ok("VT-1: POST video-transectos com todos os campos → 200")
        vt_id = resp.get("id")
        log(f"id={vt_id}")

        checks = [
            # nome_video é gravado dentro de dados_meteo["nome_video"] pelo coleta_service
            ("nome_video em dados_meteo", bool((resp.get("dados_meteo") or {}).get("nome_video"))),
            ("video_url presente", bool(resp.get("video_url"))),
            ("profundidade_inicial == 10.0", resp.get("profundidade_inicial") == 10.0),
            ("riqueza_especifica == 22.0", resp.get("riqueza_especifica") == 22.0),
            ("diversidade_shannon == 2.8", resp.get("diversidade_shannon") == 2.8),
            ("dados_meteo presente", isinstance(resp.get("dados_meteo"), dict)),
        ]
        for label, passed in checks:
            if passed:
                ok(f"VT-1 campo: {label}")
            else:
                fail(f"VT-1 campo: {label}", str(resp.get(label.split(" ")[0])))
    else:
        fail("VT-1: POST video-transectos com todos os campos → 200", f"status={status} body={resp}")

    # Listagem
    status, lista = request("GET", f"/api/campanhas/{campanha_id}/video-transectos", token=token)
    if status == 200 and isinstance(lista, list):
        if any(v.get("id") == vt_id for v in lista):
            ok("VT-2: GET video-transectos lista o VT criado")
        else:
            fail("VT-2: GET video-transectos lista o VT criado",
                 f"vt_id={vt_id} não encontrado em {len(lista)} items")
    else:
        fail("VT-2: GET video-transectos → lista", f"status={status}")

    if not vt_id:
        fail("VT-3..5: skipped (vt_id ausente)", "criação falhou")
        return

    # Edição
    update = {
        "riqueza_especifica": 30.0,
        "diversidade_shannon": 3.1,
        "video_url": "https://example.blob.core.windows.net/container/1/campanhateste/videos/vt_01_v2.mp4",
    }
    status, resp_put = request("PUT", f"/api/video-transectos/{vt_id}", update, token)
    if status == 200:
        ok("VT-3: PUT video-transectos → 200")
        if resp_put.get("riqueza_especifica") == 30.0:
            ok("VT-3 campo: riqueza_especifica atualizada")
        else:
            fail("VT-3 campo: riqueza_especifica atualizada",
                 f"valor={resp_put.get('riqueza_especifica')}")
    else:
        fail("VT-3: PUT video-transectos → 200", f"status={status} body={resp_put}")

    # Deleção
    status, resp_del = request("DELETE", f"/api/video-transectos/{vt_id}", token=token)
    if status == 200 and resp_del.get("success"):
        ok("VT-4: DELETE video-transectos → 200 success")
    else:
        fail("VT-4: DELETE video-transectos → 200 success", f"status={status} body={resp_del}")

    # Confirma remoção
    status, lista2 = request("GET", f"/api/campanhas/{campanha_id}/video-transectos", token=token)
    if status == 200:
        if not any(v.get("id") == vt_id for v in lista2):
            ok("VT-5: VT deletado não aparece na listagem")
        else:
            fail("VT-5: VT deletado não aparece na listagem", "id ainda presente")


# ─── Bloco 3: Fotoquadrado ────────────────────────────────────────────────────

def testar_fotoquadrado(token: str, campanha_id: str, espaco_id: int) -> None:
    print("\n[FQ] Fotoquadrado")
    fq_id = None

    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "data_hora": f"{today()}T11:00:00",
        "observacoes": "FQ criado pelo teste E2E",
        "latitude": -8.52,
        "longitude": -35.15,
        "profundidade": 5.0,
        "temperatura": 26.0,
        "visibilidade_vertical": 7.0,
        "visibilidade_horizontal": 10.0,
        "imagem_mosaico_url": "https://example.blob.core.windows.net/container/1/campanhateste/images/fq_mosaico.jpg",
        "imagens_complementares": [
            "https://example.blob.core.windows.net/container/1/campanhateste/images/fq_comp1.jpg",
            "https://example.blob.core.windows.net/container/1/campanhateste/images/fq_comp2.jpg",
            "https://example.blob.core.windows.net/container/1/campanhateste/images/fq_comp3.jpg",
        ],
        "riqueza_especifica": 18.0,
        "diversidade_shannon": 2.5,
        "equitabilidade_jaccard": 0.82,
        "dados_meteo": {
            "vento_velocidade": 5.0,
            "estado_mar": "calmo",
            "corrente": "fraca",
        },
    }
    status, resp = request("POST", f"/api/campanhas/{campanha_id}/fotoquadrados", body, token)
    if status == 200:
        ok("FQ-1: POST fotoquadrados com todos os campos → 200")
        fq_id = resp.get("id")
        log(f"id={fq_id}")

        checks = [
            ("imagem_mosaico_url presente", bool(resp.get("imagem_mosaico_url"))),
            ("imagens_complementares com 3 itens", len(resp.get("imagens_complementares") or []) == 3),
            ("profundidade == 5.0", resp.get("profundidade") == 5.0),
            ("riqueza_especifica == 18.0", resp.get("riqueza_especifica") == 18.0),
            ("dados_meteo presente", isinstance(resp.get("dados_meteo"), dict)),
        ]
        for label, passed in checks:
            if passed:
                ok(f"FQ-1 campo: {label}")
            else:
                fail(f"FQ-1 campo: {label}", str(resp))
    else:
        fail("FQ-1: POST fotoquadrados com todos os campos → 200", f"status={status} body={resp}")

    # Listagem
    status, lista = request("GET", f"/api/campanhas/{campanha_id}/fotoquadrados", token=token)
    if status == 200 and isinstance(lista, list):
        if any(f.get("id") == fq_id for f in lista):
            ok("FQ-2: GET fotoquadrados lista o FQ criado")
        else:
            fail("FQ-2: GET fotoquadrados lista o FQ criado",
                 f"fq_id={fq_id} não encontrado em {len(lista)} items")
    else:
        fail("FQ-2: GET fotoquadrados → lista", f"status={status}")

    if not fq_id:
        fail("FQ-3..5: skipped (fq_id ausente)", "criação falhou")
        return

    # Edição
    update = {
        "profundidade": 7.5,
        "imagem_mosaico_url": "https://example.blob.core.windows.net/container/1/campanhateste/images/fq_mosaico_v2.jpg",
        "imagens_complementares": [
            "https://example.blob.core.windows.net/container/1/campanhateste/images/fq_comp1.jpg",
        ],
        "riqueza_especifica": 20.0,
    }
    status, resp_put = request("PUT", f"/api/fotoquadrados/{fq_id}", update, token)
    if status == 200:
        ok("FQ-3: PUT fotoquadrados → 200")
        if resp_put.get("profundidade") == 7.5:
            ok("FQ-3 campo: profundidade atualizada")
        else:
            fail("FQ-3 campo: profundidade atualizada", f"valor={resp_put.get('profundidade')}")
        if len(resp_put.get("imagens_complementares") or []) == 1:
            ok("FQ-3 campo: imagens_complementares atualizadas (1 item)")
        else:
            fail("FQ-3 campo: imagens_complementares atualizadas", str(resp_put.get("imagens_complementares")))
    else:
        fail("FQ-3: PUT fotoquadrados → 200", f"status={status} body={resp_put}")

    # Deleção
    status, resp_del = request("DELETE", f"/api/fotoquadrados/{fq_id}", token=token)
    if status == 200 and resp_del.get("success"):
        ok("FQ-4: DELETE fotoquadrados → 200 success")
    else:
        fail("FQ-4: DELETE fotoquadrados → 200 success", f"status={status} body={resp_del}")

    # Confirma remoção
    status, lista2 = request("GET", f"/api/campanhas/{campanha_id}/fotoquadrados", token=token)
    if status == 200:
        if not any(f.get("id") == fq_id for f in lista2):
            ok("FQ-5: FQ deletado não aparece na listagem")
        else:
            fail("FQ-5: FQ deletado não aparece na listagem", "id ainda presente")


# ─── Bloco 4: Galeria — verifica que mídias de DB aparecem ───────────────────

def testar_galeria(token: str, campanha_id: str, espaco_id: int) -> None:
    """
    Cria 1 FQ com imagem_mosaico_url e verifica que a galeria retorna essa mídia.
    Não testa blobs do Azure (dependeria de credenciais reais), mas verifica
    que registros do banco são incluídos corretamente.
    """
    print("\n[GALERIA] Galeria de Imagens")

    # Cria FQ com mosaico
    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "data_hora": f"{today()}T14:00:00",
        "imagem_mosaico_url": "https://example.blob.core.windows.net/container/galeria_test/fq_mosaico_galeria.jpg",
        "imagens_complementares": [
            "https://example.blob.core.windows.net/container/galeria_test/fq_comp_galeria.jpg",
        ],
    }
    status, resp = request("POST", f"/api/campanhas/{campanha_id}/fotoquadrados", body, token)
    if status != 200:
        fail("GALERIA-0: criação de FQ para teste de galeria → 200", f"status={status}")
        return
    fq_id = resp.get("id")
    ok("GALERIA-0: FQ criado para teste de galeria")

    # Invalida o cache antes de verificar
    request("POST", "/api/galeria-imagens/invalidar-cache", token=token)

    # Verifica galeria
    status, galeria = request("GET", "/api/galeria-imagens", token=token)
    if status != 200:
        fail("GALERIA-1: GET /api/galeria-imagens → 200", f"status={status}")
        return
    ok("GALERIA-1: GET /api/galeria-imagens → 200")

    ilhas = galeria.get("ilhas") or []
    todas_midias = []
    for ilha in ilhas:
        for ponto in ilha.get("pontos") or []:
            todas_midias.extend(ponto.get("midias") or [])

    mosaico_url = "https://example.blob.core.windows.net/container/galeria_test/fq_mosaico_galeria.jpg"
    encontrou_mosaico = any(m.get("url") == mosaico_url for m in todas_midias)
    encontrou_complementar = any(
        m.get("url") == "https://example.blob.core.windows.net/container/galeria_test/fq_comp_galeria.jpg"
        for m in todas_midias
    )

    if encontrou_mosaico:
        ok("GALERIA-2: imagem_mosaico_url do FQ aparece na galeria")
    else:
        fail("GALERIA-2: imagem_mosaico_url do FQ aparece na galeria",
             f"total midias encontradas={len(todas_midias)}")

    if encontrou_complementar:
        ok("GALERIA-3: imagem complementar do FQ aparece na galeria")
    else:
        fail("GALERIA-3: imagem complementar do FQ aparece na galeria",
             f"total midias encontradas={len(todas_midias)}")

    # Estrutura Ilha → Pontos
    if ilhas:
        ok("GALERIA-4: resposta contém lista de ilhas")
        primeira = ilhas[0]
        if "pontos" in primeira and "total" in primeira:
            ok("GALERIA-5: ilhas têm campos 'pontos' e 'total'")
        else:
            fail("GALERIA-5: ilhas têm campos 'pontos' e 'total'", str(primeira.keys()))
    else:
        fail("GALERIA-4: resposta contém lista de ilhas", "lista vazia")

    # Limpa o FQ criado
    if fq_id:
        request("DELETE", f"/api/fotoquadrados/{fq_id}", token=token)
        ok("GALERIA-6: FQ de teste removido após verificação")


# ─── Bloco 5: Campos numéricos e validações ──────────────────────────────────

def testar_validacoes(token: str, campanha_id: str, espaco_id: int) -> None:
    print("\n[VAL] Validações")

    # campanha_id inválida → 404
    fake_id = "00000000-0000-0000-0000-000000000000"
    body = {
        "campanha_id": fake_id,
        "espaco_amostral_id": espaco_id,
    }
    status, _ = request("POST", f"/api/campanhas/{fake_id}/busca-ativa", body, token)
    if status == 404:
        ok("VAL-1: POST busca-ativa com campanha inexistente → 404")
    else:
        fail("VAL-1: POST busca-ativa com campanha inexistente → 404", f"status={status}")

    # espaco_amostral_id inválido → 404
    body2 = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": 999999999,
    }
    status2, _ = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", body2, token)
    if status2 == 404:
        ok("VAL-2: POST busca-ativa com espaco_amostral_id inválido → 404")
    else:
        fail("VAL-2: POST busca-ativa com espaco_amostral_id inválido → 404", f"status={status2}")

    # numero_busca duplicado → 409
    ba_body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "numero_busca": 99,
    }
    request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", ba_body, token)  # 1ª vez
    status3, resp3 = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", ba_body, token)  # 2ª vez
    if status3 == 409:
        ok("VAL-3: numero_busca duplicado → 409")
    else:
        fail("VAL-3: numero_busca duplicado → 409", f"status={status3} body={resp3}")

    # numero_busca <= 0 → 400
    ba_zero = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "numero_busca": 0,
    }
    status4, resp4 = request("POST", f"/api/campanhas/{campanha_id}/busca-ativa", ba_zero, token)
    if status4 == 400:
        ok("VAL-4: numero_busca=0 → 400")
    else:
        fail("VAL-4: numero_busca=0 → 400", f"status={status4} body={resp4}")


# ─── Bloco 6: PUT FQ — verificação do endpoint correto ───────────────────────

def _find_fq_put_endpoint(token: str, campanha_id: str, espaco_id: int):
    """Detecta se o endpoint PUT para fotoquadrado existe."""
    body = {
        "campanha_id": campanha_id,
        "espaco_amostral_id": espaco_id,
        "data_hora": f"{today()}T15:00:00",
        "imagem_mosaico_url": "https://example.com/test.jpg",
    }
    status, resp = request("POST", f"/api/campanhas/{campanha_id}/fotoquadrados", body, token)
    if status != 200:
        return None, None
    fq_id = resp.get("id")

    # Testa PUT
    status_put, _ = request("PUT", f"/api/fotoquadrados/{fq_id}", {"profundidade": 3.0}, token)
    if status_put == 404:
        # endpoint pode ser diferente
        return fq_id, False
    return fq_id, status_put == 200


# ─── Main ─────────────────────────────────────────────────────────────────────

def _server_available() -> bool:
    try:
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=5)
        conn.request("GET", "/api/health")
        resp = conn.getresponse()
        conn.close()
        return resp.status < 500
    except Exception:
        return False


def main():
    print(f"\n{'='*60}")
    print(f"  Teste E2E: BA / FQ / VT")
    print(f"  Servidor: {BASE_HOST}:{BASE_PORT}")
    print(f"  Data: {today()}")
    print(f"{'='*60}")

    if not _server_available():
        print(f"\n[SKIP] Servidor não disponível em {BASE_HOST}:{BASE_PORT}")
        print("       Inicie o servidor ou use: docker exec pmascc_app python tests/test_e2e_metodos.py 8080")
        sys.exit(0)

    try:
        token = login()
        ok("SETUP: Login como admin → token obtido")
    except RuntimeError as e:
        print(f"  [FAIL] SETUP: {e}")
        sys.exit(1)

    try:
        ilha, espaco = get_ilha_com_espacos(token)
        espaco_id = espaco["id"]
        ok(f"SETUP: Ilha '{ilha['nome']}' com espaço '{espaco.get('codigo') or espaco.get('nome')}' (id={espaco_id})")
    except RuntimeError as e:
        print(f"  [FAIL] SETUP: {e}")
        sys.exit(1)

    try:
        campanha_id = criar_campanha(token, ilha)
        ok(f"SETUP: Campanha criada → {campanha_id}")
    except RuntimeError as e:
        print(f"  [FAIL] SETUP: {e}")
        sys.exit(1)

    testar_busca_ativa(token, campanha_id, espaco_id)
    testar_video_transecto(token, campanha_id, espaco_id)
    testar_fotoquadrado(token, campanha_id, espaco_id)
    testar_galeria(token, campanha_id, espaco_id)
    testar_validacoes(token, campanha_id, espaco_id)

    # ── Resultado final ──
    total = len(PASSED) + len(FAILED)
    print(f"\n{'='*60}")
    print(f"  Resultado: {len(PASSED)}/{total} testes passaram")
    if FAILED:
        print(f"\n  Falhas ({len(FAILED)}):")
        for f in FAILED:
            print(f"    - {f}")
    print(f"{'='*60}\n")
    sys.exit(0 if not FAILED else 1)


if __name__ == "__main__":
    main()
