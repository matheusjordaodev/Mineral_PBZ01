param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$Location,

    [Parameter(Mandatory = $true)]
    [string]$AcrName,

    [Parameter(Mandatory = $true)]
    [string]$PlanName,

    [Parameter(Mandatory = $true)]
    [string]$WebAppName,

    [Parameter(Mandatory = $true)]
    [string]$GeoServerAdminPassword,

    [string]$GeoServerAdminUser = "admin",
    [string]$ImageName = "pbz01-geoserver",
    [string]$ImageTag = "v1",
    [string]$Sku = "B1",
    [string]$GeoServerVersion = "2.28.0",
    [string]$StableExtensions = "importer,ysld"
)

$ErrorActionPreference = "Stop"

$imageRef = "$AcrName.azurecr.io/$ImageName`:$ImageTag"
$buildContext = (Resolve-Path (Join-Path $PSScriptRoot "..\..\geoserver-azure-example")).Path

Write-Host "Ensuring resource group..."
az group create --name $ResourceGroup --location $Location | Out-Null

Write-Host "Ensuring Azure Container Registry..."
$null = az acr show --name $AcrName --resource-group $ResourceGroup 2>$null
if ($LASTEXITCODE -ne 0) {
    az acr create `
        --resource-group $ResourceGroup `
        --name $AcrName `
        --sku Basic `
        --admin-enabled true `
        --location $Location | Out-Null
} else {
    az acr update --name $AcrName --admin-enabled true | Out-Null
}

Write-Host "Building GeoServer image in ACR..."
az acr build `
    --registry $AcrName `
    --image "${ImageName}:$ImageTag" `
    --build-arg "GEOSERVER_VERSION=$GeoServerVersion" `
    $buildContext | Out-Null

Write-Host "Ensuring App Service plan..."
$null = az appservice plan show --name $PlanName --resource-group $ResourceGroup 2>$null
if ($LASTEXITCODE -ne 0) {
    az appservice plan create `
        --name $PlanName `
        --resource-group $ResourceGroup `
        --sku $Sku `
        --is-linux `
        --location $Location | Out-Null
}

Write-Host "Ensuring GeoServer Web App..."
$null = az webapp show --name $WebAppName --resource-group $ResourceGroup 2>$null
if ($LASTEXITCODE -ne 0) {
    az webapp create `
        --resource-group $ResourceGroup `
        --plan $PlanName `
        --name $WebAppName `
        --deployment-container-image-name $imageRef | Out-Null
}

$acrUser = az acr credential show --name $AcrName --query username --output tsv
$acrPassword = az acr credential show --name $AcrName --query passwords[0].value --output tsv

Write-Host "Configuring container image..."
az webapp config container set `
    --name $WebAppName `
    --resource-group $ResourceGroup `
    --docker-custom-image-name $imageRef `
    --docker-registry-server-url "https://$AcrName.azurecr.io" `
    --docker-registry-server-user $acrUser `
    --docker-registry-server-password $acrPassword | Out-Null

$appSettings = @(
    "WEBSITES_PORT=8080",
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE=true",
    "WEBSITES_CONTAINER_START_TIME_LIMIT=600",
    "WEBSITE_WARMUP_PATH=/geoserver/web/",
    "WEBSITE_WARMUP_STATUSES=200,302",
    "WEBAPP_CONTEXT=geoserver",
    "GEOSERVER_DATA_DIR=/home/site/geoserver_data",
    "SKIP_DEMO_DATA=true",
    "ROOT_WEBAPP_REDIRECT=true",
    "RUN_UNPRIVILEGED=true",
    "CHANGE_OWNERSHIP_ON_FOLDERS=/opt /home/site/geoserver_data /usr/local/tomcat/conf/Catalina/localhost",
    "PROXY_BASE_URL=https://$WebAppName.azurewebsites.net/geoserver",
    "GEOSERVER_ADMIN_USER=$GeoServerAdminUser",
    "GEOSERVER_ADMIN_PASSWORD=$GeoServerAdminPassword"
)

if ([string]::IsNullOrWhiteSpace($StableExtensions)) {
    $appSettings += "INSTALL_EXTENSIONS=false"
} else {
    $appSettings += "INSTALL_EXTENSIONS=true"
    $appSettings += "STABLE_EXTENSIONS=$StableExtensions"
}

az webapp config appsettings set `
    --resource-group $ResourceGroup `
    --name $WebAppName `
    --settings $appSettings | Out-Null

Write-Host ""
Write-Host "GeoServer deployed:"
Write-Host "  URL: https://$WebAppName.azurewebsites.net/geoserver"
Write-Host "  WMS: https://$WebAppName.azurewebsites.net/geoserver/wms"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open the GeoServer admin UI and create workspace/store/layers."
Write-Host "  2. Publish pmascc:ilhas and pmascc:vw_espacos_amostrais_geo."
Write-Host "  3. Update the application with the values from app-integration.env.example."
Write-Host ""
Write-Host "Important:"
Write-Host "  After the first successful startup, remove GEOSERVER_ADMIN_USER and"
Write-Host "  GEOSERVER_ADMIN_PASSWORD from App Service settings if you want to"
Write-Host "  manage users and roles directly inside GeoServer."
