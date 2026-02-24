# Roteiro de Apresentação - Frontend WebGIS (PMASCC)

## 1. Introdução
*   **Apresentador**: "Olá a todos. Hoje vou apresentar o estado atual do frontend da aplicação WebGIS desenvolvida para o **PMASCC (Projeto de Monitoramento de Áreas Susceptíveis à Colonização Por Coral-sol)**."
*   **Contexto**: "A aplicação foi construída utilizando **Python (FastAPI)** para o backend e **HTML5/CSS3/JavaScript (Leaflet)** para o frontend. O foco atual foi a estruturação da interface do usuário (UI) e a implementação das funcionalidades interativas de mapa."

---

## 2. Acesso e Identidade Visual (Tela de Login)
*   **Ação**: Abrir a aplicação.
*   **Destaque Visual**:
    *   Mostrar a tela de login com design moderno (Background escuro com gradiente).
    *   Ressaltar o título completo do projeto em destaque: **"PMASCC - Projeto de Monitoramento..."**.
    *   Mencionar o card de login com efeito *glassmorphism* (fundo translúcido).
*   **Interação**:
    *   Preencher usuário e senha (padrão: `admin` / `admin`).
    *   Clicar em "Entrar" para demonstrar a transição suave para o painel principal.

---

## 3. Visão Geral do Painel (Dashboard)
*   **Ação**: Após o login, apresentar a estrutura da tela principal.
*   **Barra Superior (Topbar)**:
    *   Identificação clara do projeto no topo.
    *   **Status do Usuário**: Mostrar onde o usuário logado é identificado.
    *   **Botão Sair**: Funcionalidade de logout disponível.
*   **Menu Principal**:
    *   Apresentar os botões de acesso rápido: **Projeto, Documentos, Imagens**.
    *   Apresentar os filtros rápidos: **Filtro Campanha, Filtro Ilha, Filtro Método**.

---

## 4. Funcionalidades de Mapa (GIS)
*   **Ação**: Focar a atenção no mapa central.
*   **Navegação**:
    *   Demonstrar o **Zoom** (Scroll do mouse ou botões laterais).
    *   Demonstrar o **Pan** (Arrastar o mapa).
*   **Barra de Ferramentas (GIS Toolbar)**:
    *   Mostrar a barra lateral flutuante (canto direito).
    *   **Botão Menu (Hambúrguer)**: Demonstrar que a barra pode ser ocultada/exibida (bom para telas menores).
    *   **Reset View**: Clicar para voltar a visão geral do litoral de SP.
    *   **Camadas (Ilhas)**: Ligar e desligar a visualização das ilhas (Toggle Ilhas).
    *   **Ferramenta de Medição**:
        *   Ativar o modo "Medir".
        *   Clicar em dois pontos no mapa para mostrar o cálculo de distância em tempo real (na caixa inferior esquerda).
        *   Clicar em "Limpar" para remover a medição.

---

## 5. Visualização de Dados e Interatividade
*   **Ação**: Interagir com os elementos de dados.
*   **Marcadores no Mapa**:
    *   Mostrar os pontos coloridos distribuídos pelo litoral (Ilha de Queimada Grande, Ilha Anchieta, etc.).
    *   Explicar que as cores representam status ou categorias diferentes (Vermelho, Amarelo, Verde).
*   **Info (Identify Mode)**:
    *   Ativar o botão "Info".
    *   Clicar em uma ilha para simular a obtenção de detalhes daquela localidade.
*   **Modais de Detalhes (Mocks)**:
    *   **Clicar nos botões do Menu Superior**:
        *   **Projeto**:
            *   Exibe lista de projetos recentes (ex: Coral-Sol 2025).
            *   Resumo do projeto ativo: Escopo, Região e Equipe.
            *   Próximas entregas: Relatórios e mapeamentos agendados.
        *   **Documentos**:
            *   **Organização por Campanhas**: Explicar que os arquivos serão estruturados com base nas campanhas realizadas.
            *   Acesso rápido aos arquivos mais utilizados (PDFs, DOCX).
            *   Área de Upload/Download (mock) e itens pendentes de revisão.
        *   **Imagens**:
            *   Galeria visual com miniaturas das ilhas (ex: Ilha da Moela).
            *   Metadados esperados para cada imagem (Data, Coordenadas, Autor).
        *   **Filtro Campanha**:
            *   Simulação de filtos por Ano (2024/01, 2024/02), Período (Q1/Q2) e Status.
            *   Exibição dinâmica da contagem de resultados.
        *   **Filtro Ilha**:
            *   Seleção específica de ilha e classificação por Risco (Alto, Médio, Baixo).
            *   Destaque para ilhas críticas (ex: Ilha da Moela - Risco Alto).
        *   **Filtro Método**:
            *   Segmentação por metodologia de coleta (Visual, Vídeo, Fotogrametria).
            *   Input de densidade mínima e exemplos de legenda por cores.

---

## 6. Conclusão e Próximos Passos
*   **Resumo**: "Como podem ver, a estrutura de Frontend está robusta e responsiva. Temos:"
    1.  Sistema de autenticação visualmente pronto.
    2.  Mapa interativo com ferramentas GIS funcionais (Medição, Zoom, Camadas).
    3.  Interface preparada para exibir dados complexos (Modais e Painéis).
*   **Próximos Passos**: "O próximo passo técnico é conectar esta interface ao Banco de Dados PostGIS para que as informações de campanhas, fotos e relatórios sejam carregadas em tempo real."
'