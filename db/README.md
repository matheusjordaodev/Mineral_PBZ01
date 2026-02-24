# PMASCC - Database Setup

## Modelo de Banco de Dados

O sistema utiliza **PostgreSQL** com extensão **PostGIS** para armazenar dados geoespaciais.

### Estrutura

```
db/
├── init.sql       # Script de inicialização (tabelas, índices, dados)
├── models.py      # Modelos SQLAlchemy + GeoAlchemy2
└── database.py    # Configuração de conexão
```

## Tabelas

1. **ilhas** - Dados das ilhas com localização (Point)
2. **campanhas** - Campanhas de monitoramento
3. **arquivos_geoespaciais** - KML/KMZ com geometrias PostGIS
4. **arquivos_midia** - Fotos e vídeos com GPS
5. **usuarios** - Controle de acesso (futuro)

## Setup com Docker

### 1. Iniciar o banco de dados

```bash
docker compose up db -d
```

O script `db/init.sql` será executado automaticamente na primeira inicialização.

### 2. Verificar

```bash
docker compose exec db psql -U pmascc_user -d pmascc_db -c "SELECT nome FROM ilhas;"
```

### 3. Iniciar aplicação completa

```bash
docker compose up --build
```

## Setup Local (sem Docker)

### 1. Instalar PostgreSQL + PostGIS

```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgis

# macOS
brew install postgresql postgis

# Windows
# Baixar instalador do PostgreSQL com PostGIS
```

### 2. Criar banco de dados

```bash
createdb -U postgres pmascc_db
psql -U postgres -d pmascc_db -c "CREATE EXTENSION postgis;"
```

### 3. Executar script de inicialização

```bash
psql -U postgres -d pmascc_db -f db/init.sql
```

### 4. Configurar .env

```bash
cp .env.example .env
# Editar DATABASE_URL conforme necessário
```

### 5. Instalar dependências Python

```bash
pip install -r requirements.txt
```

### 6. Testar conexão

```bash
python db/database.py
```

## Queries Úteis

### Listar ilhas com coordenadas

```sql
SELECT nome, ST_AsText(localizacao) as coords 
FROM ilhas;
```

### Buscar ilhas em um raio (10km)

```sql
SELECT nome 
FROM ilhas 
WHERE ST_DWithin(
    localizacao,
    ST_MakePoint(-46.6750, -24.4861)::geography,
    10000  -- metros
);
```

### Ver campanhas de uma ilha

```sql
SELECT c.nome, c.data_campanha, c.status
FROM campanhas c
JOIN ilhas i ON c.ilha_id = i.id
WHERE i.codigo = 'queimada_grande'
ORDER BY c.data_campanha DESC;
```

### Contar arquivos por campanha

```sql
SELECT 
    c.nome,
    COUNT(DISTINCT ag.id) as arquivos_geo,
    COUNT(DISTINCT am.id) as arquivos_midia
FROM campanhas c
LEFT JOIN arquivos_geoespaciais ag ON c.id = ag.campanha_id
LEFT JOIN arquivos_midia am ON c.id = am.campanha_id
GROUP BY c.id, c.nome;
```

## Extensões

O banco usa as seguintes extensões:
- **PostGIS** - Tipos e funções geoespaciais
- **JSONB** - Armazenamento eficiente de metadados

## Índices Espaciais

Índices GIST foram criados para otimizar queries espaciais:
- `idx_ilhas_localizacao`
- `idx_arquivos_geo_geometria`
- `idx_arquivos_midia_localizacao`
