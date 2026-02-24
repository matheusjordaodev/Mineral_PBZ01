# Guia de Deploy e Atualização no Azure (Docker)

Este guia descreve o processo para containerizar a aplicação, subir para o Azure Container Registry (ACR) e fazer o deploy no Azure Web App for Containers.

## Pré-requisitos

1.  **Docker** instalado e rodando na sua máquina.
2.  **Azure CLI** instalado (`az login` realizado).
3.  Um **Resource Group** no Azure (ex: `rg-guara-vermelho`).

---

## 1. Preparação (Primeira Vez)

### 1.1 Criar o Azure Container Registry (ACR)
Se você ainda não tem um registro para guardar suas imagens:

```powershell
# Exemplo de criação (substitua <nome_unico_acr> por um nome único, ex: acrguaravermelho)
az acr create --resource-group rg-guara-vermelho --name <nome_unico_acr> --sku Basic --admin-enabled true
```

### 1.2 Login no ACR
```powershell
az acr login --name <nome_unico_acr>
```

---

## 2. Deploy Inicial

### 2.1 Construir a Imagem
Na pasta raiz do projeto (`c:\bluebell\guara_vermelho`), rode:

```powershell
# Substitua <nome_unico_acr> pelo nome do seu ACR
docker build -t <nome_unico_acr>.azurecr.io/guara-app:v1 .
```

### 2.2 Enviar a Imagem (Push)
```powershell
docker push <nome_unico_acr>.azurecr.io/guara-app:v1
```

### 2.3 Criar o Web App
```powershell
# Cria o plano de serviço (app service plan)
az appservice plan create --name plan-guara --resource-group rg-guara-vermelho --sku B1 --is-linux

# Cria o Web App apontando para a imagem
az webapp create --resource-group rg-guara-vermelho --plan plan-guara --name app-guara-vermelho --deployment-container-image-name <nome_unico_acr>.azurecr.io/guara-app:v1
```

### 2.4 Configurar Variáveis e Porta
O Web App precisa saber qual porta expor (8000) e como conectar no banco.

**Configuração da Porta:**
```powershell
az webapp config appsettings set --resource-group rg-guara-vermelho --name app-guara-vermelho --settings WEBSITES_PORT=8000
```

**Configuração do Banco de Dados (Produção):**
Para que o App "converse" com o PostGIS na Azure, você deve configurar a variável `DATABASE_URL`.

1.  **Opção Recomendada (Azure Database for PostgreSQL):**
    *   Crie um recurso "Azure Database for PostgreSQL - Flexible Server" no portal.
    *   Habilite a extensão PostGIS (`CREATE EXTENSION postgis;`).
    *   Obtenha a string de conexão (Host, User, Password).
    *   Configure no App Service:
    ```powershell
    # Exemplo:
    az webapp config appsettings set --resource-group rg-guara-vermelho --name app-guara-vermelho --settings DATABASE_URL="postgresql://usuario:senha@meu-servidor-postgres.postgres.database.azure.com:5432/pmascc_db"
    ```

2.  **Opção Container (Docker Compose no Azure):**
    *   Se você subir os dois containers juntos (App + DB) usando um Docker Compose no Azure Web App, a conexão interna funciona igual localmente (`host=db`).
    *   *Nota:* Para produção real, banco em container não é recomendado (risco de perda de dados se não montar volumes Azure Storage corretamente).

---

## 3. Como Atualizar a Imagem (Sua Pergunta)

Sempre que você modificar o código (`app.py`, etc.) e quiser atualizar o site, siga estes passos:

### Passo 1: Construir Nova Versão
Incremente a tag (ex: de `v1` para `v2`) para manter histórico, ou use `latest` (mas tags numeradas são mais seguras).

```powershell
# Exemplo mudando para v2
docker build -t <nome_unico_acr>.azurecr.io/guara-app:v2 .
```

### Passo 2: Enviar Nova Versão
```powershell
docker push <nome_unico_acr>.azurecr.io/guara-app:v2
```

### Passo 3: Atualizar o Web App
Avise o Azure para usar a nova tag.

```powershell
az webapp config container set --name app-guara-vermelho --resource-group rg-guara-vermelho --docker-custom-image-name <nome_unico_acr>.azurecr.io/guara-app:v2
```
*O Azure irá reiniciar a aplicação automaticamente com a nova imagem.*

---

## Comandos Úteis

- **Ver logs**: `az webapp log tail --name app-guara-vermelho --resource-group rg-guara-vermelho`
- **Reiniciar manualmente**: `az webapp restart --name app-guara-vermelho --resource-group rg-guara-vermelho`
