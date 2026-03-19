# GeoServer no projeto

Este projeto agora inclui um servico `geoserver` no `docker-compose.yml`.

## Subir o servico

```powershell
docker compose up -d geoserver
```

Painel web:

- URL: `http://localhost:8081/geoserver`
- usuario: valor de `GEOSERVER_ADMIN_USER`
- senha: valor de `GEOSERVER_ADMIN_PASSWORD`

## Conectar ao PostGIS (Azure PostgreSQL)

No GeoServer:

1. `Data > Workspaces > Add new workspace` (ex.: `pmascc`)
2. `Data > Stores > Add new Store > PostGIS`
3. Informar:
- `host`: `pbz01.postgres.database.azure.com`
- `port`: `5432`
- `database`: `postgres`
- `schema`: `public`
- `user`: `pbz01`
- `password`: senha real do banco (sem `%23`)
- `sslmode`: `require`
4. Salvar e publicar camadas (`Publish`)

Camadas recomendadas para a visualizacao do app:

- `ilhas` (camada de ilhas)
- `vw_espacos_amostrais_geo` (view com pontos fixos por ilha)
- alternativa: `estacoes_amostrais` (pontos de estacoes registradas)

## Integracao com o mapa da aplicacao

O frontend agora consulta `GET /api/geoserver/locations` para enriquecer as localizacoes de:

- ilhas
- pontos de cada ilha
- camada visual de fundo via WMS do GeoServer

Variaveis de ambiente da integracao:

- `GEOSERVER_URL` (padrao: `http://geoserver:8080/geoserver`)
- `GEOSERVER_WORKSPACE` (padrao: `pmascc`)
- `GEOSERVER_ILHAS_LAYER` (padrao: `ilhas`)
- `GEOSERVER_PONTOS_LAYER` (padrao: `vw_espacos_amostrais_geo`)
- `GEOSERVER_PUBLIC_WMS_URL` (padrao: `http://localhost:8081/geoserver/wms`)
- `GEOSERVER_WMS_LAYERS` (opcional; por padrao usa a camada de ilhas)
- `GEOSERVER_DATA_USER` e `GEOSERVER_DATA_PASSWORD` (opcional)

Se alguma camada nao estiver publicada, a aplicacao faz fallback para os dados internos.

## Servicos de exportacao/publicacao

Depois de publicar camadas, os endpoints padroes ficam assim:

- WMS: `http://localhost:8081/geoserver/pmascc/wms`
- WFS: `http://localhost:8081/geoserver/pmascc/wfs`

Exemplo `GetCapabilities`:

- `http://localhost:8081/geoserver/pmascc/wms?service=WMS&request=GetCapabilities`
- `http://localhost:8081/geoserver/pmascc/wfs?service=WFS&request=GetCapabilities`

## Observacoes

- Se a base estiver no Azure, o firewall precisa liberar a origem de rede do host/container.
- O banco precisa ter a extensao PostGIS habilitada.
- O termo comum para feicoes vetoriais e `WFS` (nao `WMF`).
