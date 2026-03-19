import http.client
import json
import sys
import urllib.parse

BASE_HOST = "localhost"
BASE_PORT = 8080


def log(message):
    print(f"[TEST] {message}")


def request(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    payload = json.dumps(body) if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()

    try:
        return response.status, json.loads(raw)
    except json.JSONDecodeError:
        return response.status, raw


def login():
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    params = urllib.parse.urlencode({"username": "admin", "password": "admin"})
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    conn.request("POST", "/api/login", params, headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()

    if response.status != 200:
        raise RuntimeError(f"Login failed: {response.status} {raw}")
    return json.loads(raw)["access_token"]


def run_test():
    log("Starting questionnaire consistency test")
    token = login()
    log("Login successful")

    status, islands_payload = request("GET", "/api/ilhas", token=token)
    if status != 200 or not islands_payload.get("ilhas"):
        raise RuntimeError(f"Failed to load islands: {status} {islands_payload}")

    ilha = islands_payload["ilhas"][0]
    espacos = ilha.get("espacos_amostrais") or []
    if not espacos:
        raise RuntimeError("No sampling spaces available for the selected island")

    espaco = espacos[0]
    campanha_payload = {
        "ilhas": [
            {
                "ilha_id": ilha["id"],
                "selecao": [
                    {
                        "espaco_amostral_id": espaco["id"],
                        "pontos": [1],
                    }
                ],
            }
        ],
        "nome": "MASC 01",
        "data": "2026-03-13",
        "descricao": "Automated consistency test",
        "base_apoio_id": None,
        "embarcacao_id": None,
        "membros_equipe": [],
    }

    status, campanha_response = request("POST", "/api/campanhas", campanha_payload, token)
    if status != 200:
        raise RuntimeError(f"Failed to create campaign: {status} {campanha_response}")

    campanha_id = campanha_response["campanha"]["id"]
    log(f"Campaign created: {campanha_id}")

    status, stations_response = request("GET", f"/api/campanhas/{campanha_id}/estacoes", token=token)
    if status != 200 or not isinstance(stations_response, list) or not stations_response:
        raise RuntimeError(f"Failed to load campaign stations: {status} {stations_response}")

    station = stations_response[0]
    station_id = station["id"]
    log(f"Using station {station_id}")

    batch_payload = {
        "estacoes": [
            {
                "estacao_amostral_id": station_id,
                "buscas_ativas": [
                    {
                        "numero_busca": 1,
                        "data_hora_inicio": "2026-03-13T09:00:00",
                        "data_hora_fim": "2026-03-13T09:20:00",
                        "profundidade_inicial": 12.5,
                        "profundidade_final": 8.0,
                        "temperatura_inicial": 24.2,
                        "temperatura_final": 23.8,
                        "visibilidade_vertical": 7.0,
                        "visibilidade_horizontal": 10.0,
                        "encontrou_coral_sol": False,
                        "imagens": ["https://example.com/busca-1.jpg"],
                    }
                ],
                "video_transectos": [
                    {
                        "data_hora": "2026-03-13T10:00:00",
                        "video_url": "https://example.com/video-1.mp4",
                        "profundidade_inicial": 9.0,
                        "profundidade_final": 6.0,
                    }
                ],
                "fotoquadrados": [
                    {
                        "data_hora": "2026-03-13T11:00:00",
                        "imagem_mosaico_url": "https://example.com/foto-mosaico.jpg",
                        "imagens_complementares": [
                            "https://example.com/foto-1.jpg",
                            "https://example.com/foto-2.jpg",
                        ],
                        "profundidade": 7.5,
                        "temperatura": 23.4,
                    }
                ],
            }
        ]
    }

    status, batch_response = request(
        "POST",
        f"/api/campanhas/{campanha_id}/envio-lote",
        batch_payload,
        token,
    )
    if status != 200:
        raise RuntimeError(f"Batch submission failed: {status} {batch_response}")

    totals = batch_response.get("totais") or {}
    if totals.get("buscas_ativas") != 1 or totals.get("video_transectos") != 1 or totals.get("fotoquadrados") != 1:
        raise RuntimeError(f"Unexpected batch totals: {batch_response}")
    log("Batch submission completed")

    status, methods_response = request("GET", f"/api/campanhas/{campanha_id}/metodos", token=token)
    if status != 200:
        raise RuntimeError(f"Failed to load methods summary: {status} {methods_response}")

    if len(methods_response.get("buscas", [])) != 1:
        raise RuntimeError(f"Busca count mismatch: {methods_response}")
    if len(methods_response.get("videos", [])) != 1:
        raise RuntimeError(f"Video count mismatch: {methods_response}")
    if len(methods_response.get("fotos", [])) != 1:
        raise RuntimeError(f"Foto count mismatch: {methods_response}")

    log("Consistency test completed successfully")


if __name__ == "__main__":
    try:
        run_test()
    except Exception as exc:
        print(f"Test failed with exception: {exc}")
        sys.exit(1)
