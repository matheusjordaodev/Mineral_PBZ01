# Documentacao de Funcoes da Aplicacao (PMASCC)

## 1. Visao geral
Esta aplicacao implementa uma plataforma web para gestao de campanhas de monitoramento em ilhas, com foco em dados geoespaciais, metodos amostrais marinhos e evidencias de campo (imagens, videos e documentos).

Arquitetura principal:
- Backend: FastAPI
- Persistencia: PostgreSQL + PostGIS (SQLAlchemy/GeoAlchemy2)
- Frontend: Jinja2 + HTML/CSS/JS
- Armazenamento de arquivos: local (`app/uploads`) e Azure Blob Storage
- Visualização - WMS enxuto, focado na área de análise usando  FastAPI + PostGIS + pyemf3
## 2. Fluxo funcional da aplicacao
1. Na inicializacao, a API valida conexao com banco, cria tabelas e executa seeds (admin, ilhas, cadastros e espacos amostrais).
2. A rota `/` entrega a interface web principal.
3. A interface consome endpoints REST para cadastro, consulta, upload e exportacao de dados.

## 3. Funcionalidades por modulo

### 3.1 Autenticacao e gestao de usuarios
Responsavel por login JWT e administracao de usuarios.

Endpoints:
- `POST /api/login`: autentica usuario e retorna token Bearer.
- `GET /api/users/me`: retorna dados do usuario autenticado.
- `GET /api/users`: lista usuarios ativos (somente admin).
- `POST /api/users`: cria usuario (somente admin).
- `PUT /api/users/{user_id}`: atualiza usuario (somente admin).
- `PATCH /api/users/{user_id}/deactivate`: desativa usuario (somente admin).
- `PATCH /api/users/{user_id}/activate`: reativa usuario (somente admin).
- `DELETE /api/users/{user_id}`: exclusao logica de usuario (somente admin).
- `POST /api/setup/admin`: garante criacao do admin inicial (apoio de setup).

Regras relevantes:
- Senha com hash (`pbkdf2_sha256`).
- Token JWT com expiracao.
- Usuario admin nao pode desativar/deletar a propria conta.

### 3.2 Cadastros mestres
Responsavel por manter tabelas de apoio operacional.

Entidades:
- Bases de apoio
- Embarcacoes
- Equipe
- Espacos amostrais (estacoes fixas por ilha)

Endpoints:
- `GET/POST /api/bases-apoio`
- `PUT/DELETE /api/bases-apoio/{id}`
- `GET/POST /api/embarcacoes`
- `PUT/DELETE /api/embarcacoes/{id}`
- `GET/POST /api/equipe`
- `PUT/DELETE /api/equipe/{id}`
- `GET/POST /api/espacos-amostrais`
- `PUT/DELETE /api/espacos-amostrais/{id}`

Regras relevantes:
- Exclusao logica (`deleted_at`) para cadastros.
- Bases de apoio podem registrar ponto geografico (`POINT`) via lat/lon.
- Espacos amostrais aceitam filtro por `ilha_id`.

### 3.3 Ilhas e campanhas
Responsavel pela visao geral das ilhas e ciclo de vida das campanhas.

Endpoints:
- `GET /api/all-campanhas`: lista global de campanhas.
- `GET /api/ilhas`: lista ilhas com ultima campanha e espacos amostrais.
- `GET /api/ilhas/{ilha_id}/campanhas`: lista campanhas da ilha.
- `POST /api/campanhas`: cria campanha para uma ou mais ilhas.
- `GET /api/campanhas/{campanha_id}`: detalhes basicos da campanha.
- `GET /api/estacoes/{estacao_id}/ultima-campanha`: resumo da ultima campanha por espaco amostral.
- `GET /api/campanhas/{campanha_id}/full-details`: consolidado completo de metodos da campanha.

Regras relevantes:
- Campanha possui relacionamento N:N com ilhas (`campanhas_ilhas`).
- Codigo de campanha e gerado com padrao `CAMP-XXX-AAAAMMDD` com sufixo sequencial quando necessario.
- Na criacao da campanha, o sistema cria estacoes amostrais conforme pontos selecionados (1..8).
- Classificacao de recencia para status visual:
  - Verde: ate 30 dias
  - Amarelo: 31 a 90 dias
  - Vermelho: acima de 90 dias

### 3.4 Estacoes e metodos por estacao
Responsavel pelo registro e consulta operacional por estacao amostral.

Endpoints:
- `GET /api/campanhas/{campanha_id}/estacoes`: lista estacoes de uma campanha.
- `GET /api/campanhas/{campanha_id}/metodos`: lista metodos agregados da campanha.
- `POST /api/estacoes`: cria estacao amostral.
- `GET /api/estacoes/{estacao_id}/buscas-ativas`
- `POST /api/buscas-ativas`
- `GET /api/estacoes/{estacao_id}/video-transectos`
- `POST /api/video-transectos`
- `GET /api/estacoes/{estacao_id}/fotoquadrados`
- `POST /api/fotoquadrados`

Regras relevantes:
- `dados_meteo` e campos de imagens complementares podem ser recebidos e normalizados de JSON/texto.
- Conversoes de dados numericos e datas sao tratadas na serializacao para resposta da API.

### 3.5 Dados por campanha (camada agregada)
Responsavel por endpoints diretos da campanha para formularios/questionarios e integracoes.

Endpoints:
- `GET /api/campanhas/{campanha_id}/busca-ativa`
- `POST /api/campanhas/{campanha_id}/busca-ativa`
- `GET /api/campanhas/{campanha_id}/video-transectos`
- `POST /api/campanhas/{campanha_id}/video-transectos`
- `GET /api/campanhas/{campanha_id}/fotoquadrados`

Regras relevantes:
- Se a campanha nao tiver estacao, o sistema cria automaticamente a primeira estacao.
- Em Busca Ativa, quando `encontrou_coral_sol=true`, o sistema pode criar registro DAFOR vinculado.
- Imagens e URLs sao resolvidas com suporte Azure (quando habilitado).

### 3.6 Upload e consulta de arquivos
Responsavel por geoespacial e midia de campanha.

Endpoints:
- `POST /api/campanhas/{campanha_id}/geospatial?ilha_id=...`: upload geoespacial.
- `POST /api/campanhas/{campanha_id}/media?ilha_id=...`: upload multiplo de midia.
- `GET /api/campanhas/{campanha_id}/files?ilha_id=...`: lista arquivos da campanha.
- `GET /api/campanhas/{campanha_id}/geojson?ilha_id=...`: gera GeoJSON consolidado local.
- `GET /api/campanhas/{campanha_id}/media-list?ilha_id=...`: lista de midia (legado).
- `GET /uploads/{ilha_id}/{campanha_id}/{tipo}/{filename}`: serve arquivo local legado.

Regras relevantes:
- Geoespacial aceito: `.kml`, `.kmz`, `.geojson`, `.json`, `.shp`, `.zip`.
- Midia aceita: `.jpg`, `.jpeg`, `.png`, `.mp4`, `.mov`, `.avi`.
- Arquivos geoespaciais sao salvos localmente para parsing (KML/KMZ -> GeoJSON).
- Midia e enviada para Azure Blob quando a integracao esta disponivel.

### 3.7 Galeria de imagens e documentos
Responsavel por consulta consolidada para visualizacao.

Endpoints:
- `GET /api/galeria-imagens`: agrega imagens por ilha/campanha/estacao/metodo.
- `GET /api/documentos`: lista documentos (com filtro opcional por `ilha_id`).

Regras relevantes:
- Galeria inclui imagens de Fotoquadrado, Busca Ativa e DAFOR.
- URLs podem ser resolvidas para Azure conforme configuracao.

### 3.8 Exportacao geoespacial
Responsavel por exportar dados geograficos consolidados por ilha.

Endpoints:
- `GET /api/export/wms/{ilha_id}`: retorna `FeatureCollection` GeoJSON.
- `GET /api/export/wfs/{ilha_id}`: alias legado para o mesmo payload do WMS.
- `GET /api/export/wmf/{ilha_id}`: gera mapa vetorial WMF consolidado.

Regras relevantes:
- Combina geometrias do banco (Busca Ativa, Video Transecto, Fotoquadrado) + uploads geoespaciais.
- Retorna metadados de consolidacao (total de campanhas, features e poligonos).

### 3.9 Interface web
Rota principal:
- `GET /`: renderiza `templates/index.html` com headers anti-cache.

### 3.10 WebGIS prototipo adicional
Existe uma versao modular em `app/main.py` com rotas simples de prototipo:
- `GET /api/layers`
- `GET /api/features/{layer_id}`
- `GET /api/media/{feature_id}`

## 4. Regras transversais
- Soft delete em diversas entidades via campo `deleted_at`.
- Suporte a geometria PostGIS (`POINT`, `LINESTRING`) com GeoAlchemy2.
- Modelo de armazenamento hibrido:
  - Banco: metadados e dados de negocio
  - Disco local: parsing e legado geoespacial
  - Azure Blob: midia e URLs publicas

## 5. Principais entidades de dominio
- `Ilha`
- `Campanha`
- `EspacoAmostral`
- `EstacaoAmostral`
- `BuscaAtiva`
- `ProtocoloDAFOR`
- `VideoTransecto`
- `Fotoquadrado`
- `Documento`
- `BaseApoio`
- `Embarcacao`
- `MembroEquipe`
- `Usuario`

## 6. Observacoes tecnicas importantes

- A listagem de arquivos em `/files` prioriza dados locais para geoespacial; midia em Azure nao e listada nesse fluxo atual.
- A rota `/uploads/...` atende arquivos do  blobs Azure.
