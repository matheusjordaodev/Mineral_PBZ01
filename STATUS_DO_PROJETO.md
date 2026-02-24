# Status do Projeto WebGIS - PMASCC

## Visão Geral
Aplicação WebGIS para monitoramento da Serra do Mar (Coral-sol), utilizando FastAPI (Python) e Leaflet (JS).
Atualmente existem duas estruturas no repositório:
1. **`app.py`**: Versão monolítica que contém HTML/CSS/JS embutidos. É a versão configurada no `Dockerfile` atualmente.
2. **`app/`**: Estrutura modularizada (recomendada) separando rotas, estáticos e templates. O arquivo `app/main.py` parece ser uma refatoração em andamento.

## O Que Já Foi Feito
### Infraestrutura
- [x] **Docker**: Container configurado com Python 3.9 e libs necessárias.
- [x] **Servidor**: FastAPI rodando com Uvicorn na porta 8080.

### Frontend (Mapas & UI)
- [x] **Mapa Interativo**: Integração com Leaflet funcional.
- [x] **Ferramentas GIS**: Zoom, reset de view, controle de camadas (ligar/desligar ilhas), ferramenta de medição simples.
- [x] **Interface do Usuário**:
    - Tema escuro personalizado.
    - Sidebar flutuante.
    - Componentes de UI (Botões, Modais, Cards).
    - Tela de Login (Mock visual).
- [x] **Visualização de Dados**:
    - Pontos e Ilhas plotados no mapa.
    - Modais de detalhes com abas (Projeto, Documentos, Imagens, Filtros).
    - Galeria/Carrossel de imagens (Mock).

## O Que Falta Fazer / Pontos de Melhoria

### 1. Refatoração e Arquitetura (Prioridade Alta)
- **Migração para Modularidade**: Abandonar o arquivo único `app.py` e migrar a lógica para a pasta `app/`, separando rotas (`routers`), modelos (`models`) e serviços (`services`).
- **Arquivos Estáticos**: Mover todo HTML, CSS e JS que está em strings dentro do Python para arquivos reais em `app/static/` e `app/templates/`.

### 2. Backend & Dados
- **Banco de Dados**: Implementar conexão com PostGIS para persistir as geometrias e dados das campanhas.
- **API Real**: Substituir os dados "mockados" (dicionários fixos no código) por consultas reais ao banco de dados.
- **GeoJSON Dinâmico**: Servir as camadas via API GeoJSON gerada em tempo de execução.

### 3. Segurança
- **Autenticação JWT**: Implementar login real com tokens JWT, substituindo a verificação simples de string (`admin`/`admin`).
- **Gestão de Usuários**: Criar tabela de usuários e permissões.

### 4. Funcionalidades Avançadas
- **Upload de Mídia**: Permitir upload real de fotos e vídeos das campanhas (armazenamento local ou S3).
- **Filtros Avançados**: Fazer com que os filtros de "Campanha", "Ilha" e "Método" realmente atualizem o mapa.

## Resumo Técnico
| Componente | Estado Atual | Tecnologia |
|------------|--------------|------------|
| **Backend** | Monolito em `app.py` | FastAPI |
| **Frontend** | Embutido no Python | HTML5, Vanilla JS, CSS3 |
| **Mapas** | Funcional | Leaflet, OSM/CartoDB |
| **Dados** | Hardcoded (Mocks) | JSON em memória |
| **Deploy** | Containerizado | Docker |
