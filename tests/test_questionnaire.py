
import json
import http.client
import urllib.parse
import sys
import os

BASE_HOST = "localhost"
BASE_PORT = 8080
BASE_URL = f"http://{BASE_HOST}:{BASE_PORT}"

def log(msg):
    print(f"[TEST] {msg}")

def request(method, path, body=None, token=None):
    headers = {
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    
    json_body = json.dumps(body) if body else None
    conn.request(method, path, body=json_body, headers=headers)
    
    resp = conn.getresponse()
    resp_data = resp.read().decode('utf-8')
    conn.close()
    
    try:
        return resp.status, json.loads(resp_data)
    except json.JSONDecodeError:
        return resp.status, resp_data

def run_test():
    log("Starting Questionnaire Workflow Test...")

    # 1. Login
    log("Logging in as admin...")
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    params = urllib.parse.urlencode({'username': 'admin', 'password': 'admin'})
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    conn.request("POST", "/api/login", params, headers)
    resp = conn.getresponse()
    if resp.status != 200:
        log(f"Login failed: {resp.status} {resp.read()}")
        sys.exit(1)
    
    auth_data = json.loads(resp.read().decode('utf-8'))
    token = auth_data['access_token']
    log("Login successful.")

    # 2. Get ILHAS
    log("Fetching islands...")
    status, data = request("GET", "/api/ilhas", token=token)
    if status != 200 or not data['ilhas']:
        log(f"Failed to fetch islands or no islands found: {status}")
        sys.exit(1)
    
    ilha_id = data['ilhas'][0]['id']
    log(f"Using Ilha ID: {ilha_id}")

    # 3. Create Campaign
    log("Creating test campaign...")
    campanha_payload = {
        "ilha_id": str(ilha_id),
        "nome": "Test Campaign Automated",
        "data": "2025-01-01",
        "descricao": "Automated test campaign"
    }
    status, data = request("POST", "/api/campanhas", campanha_payload, token)
    if status != 200:
        log(f"Failed to create campaign: {status} {data}")
        sys.exit(1)
    
    campanha_id = data['campanha']['id']
    log(f"Campaign created. ID: {campanha_id}")

    # 4. Helper to create hidden station
    # The frontend does this: create station -> create method
    # We will simulate this.
    log("Creating hidden station for Busca Ativa...")
    station_payload = {
        "campanha_id": campanha_id,
        "data": "2025-01-01",
        "hora": "12:00:00",
        "observacoes": "Automated Test Station"
    }
    status, data = request("POST", "/api/estacoes", station_payload, token)
    if status != 200:
        log(f"Failed to create station: {status} {data}")
        sys.exit(1)
    
    station_id = data['id']
    log(f"Station created. ID: {station_id}")

    # 5. Create Busca Ativa
    log("Creating Busca Ativa...")
    busca_payload = {
        "estacao_amostral_id": station_id,
        "numero_busca": 1,
        "data": "2025-01-01",
        "hora_inicio": "12:00:00",
        "duracao": "00:30:00",
        "profundidade_inicial": 10.5,
        "profundidade_final": 5.0,
        "encontrou_coral_sol": True,
        "planilha_excel_url": "http://test.com/sheet.xlsx",
        "dados_meteo": "Vento SE" # Test string to JSON conversion
    }
    status, data = request("POST", "/api/buscas-ativas", busca_payload, token)
    if status != 200:
        log(f"Failed to create Busca Ativa: {status} {data}")
        sys.exit(1)
    log("Busca Ativa created.")

    # 6. Verify Methods
    log("Verifying methods list...")
    status, data = request("GET", f"/api/campanhas/{campanha_id}/metodos", token=token)
    if status != 200:
        log(f"Failed to fetch methods: {status} {data}")
        sys.exit(1)
    
    buscas = data.get('buscas', [])
    if len(buscas) > 0 and buscas[0]['estacao_id'] == station_id:
        log("✓ Validation Successful: Busca Ativa found in campaign methods.")
        # Optional: could inspect DB content if the endpoint returned details, but list endpoint is summary.
        # To be sure, let's fetch specific detail endpoint if it existed, but for now we trust the CREATE 200 OK.
    else:
        log("✗ Validation Failed: Busca Ativa not found.")
        sys.exit(1)

    log("TEST COMPLETE SUCCESS")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"Test failed with exception: {e}")
        sys.exit(1)
