param(
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,

    [Parameter(Mandatory = $false)]
    [string]$Location = "eastus",

    [Parameter(Mandatory = $false)]
    [string]$ResourceGroupName = "rg-enterprise-knowledge-demo",

    [Parameter(Mandatory = $false)]
    [string]$SearchServiceName = "",

    [Parameter(Mandatory = $false)]
    [string]$DocumentIntelligenceName = "",

    [Parameter(Mandatory = $false)]
    [string]$FoundryResourceName = "",

    [Parameter(Mandatory = $false)]
    [string]$FoundryProjectName = "enterprise-knowledge-project",

    [Parameter(Mandatory = $false)]
    [string]$StorageAccountName = "",

    [Parameter(Mandatory = $false)]
    [string]$StorageContainerName = "document-figure-artifacts",

    [Parameter(Mandatory = $false)]
    [string]$SearchSku = "standard",

    [Parameter(Mandatory = $false)]
    [switch]$CreateFoundryProject,

    [Parameter(Mandatory = $false)]
    [switch]$CreateOptionalModelDeployments,

    [Parameter(Mandatory = $false)]
    [string]$ChatModelName = "gpt-4.1-mini",

    [Parameter(Mandatory = $false)]
    [string]$ChatModelVersion = "",

    [Parameter(Mandatory = $false)]
    [string]$ChatDeploymentName = "gpt-4-1-mini",

    [Parameter(Mandatory = $false)]
    [string]$EmbeddingModelName = "text-embedding-3-large",

    [Parameter(Mandatory = $false)]
    [string]$EmbeddingModelVersion = "",

    [Parameter(Mandatory = $false)]
    [string]$EmbeddingDeploymentName = "text-embedding-3-large"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RandomSuffix {
    -join ((97..122) + (48..57) | Get-Random -Count 6 | ForEach-Object { [char]$_ })
}

function Ensure-Name {
    param(
        [string]$Value,
        [string]$Prefix,
        [int]$MaxLength = 24,
        [switch]$LowercaseOnly
    )

    if ($Value) {
        return $Value
    }

    $suffix = Get-RandomSuffix
    $candidate = "$Prefix$suffix"
    if ($LowercaseOnly) {
        $candidate = $candidate.ToLowerInvariant()
    }
    if ($candidate.Length -gt $MaxLength) {
        return $candidate.Substring(0, $MaxLength)
    }
    return $candidate
}

function Invoke-Az {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ">> az $($Arguments -join ' ')" -ForegroundColor Cyan
    $raw = & az @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
    return $raw
}

function Invoke-AzJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $raw = Invoke-Az -Arguments $Arguments
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return $raw | ConvertFrom-Json
}

$SearchServiceName = Ensure-Name -Value $SearchServiceName -Prefix "eksearch" -MaxLength 20 -LowercaseOnly
$DocumentIntelligenceName = Ensure-Name -Value $DocumentIntelligenceName -Prefix "ekdocint" -MaxLength 20 -LowercaseOnly
$FoundryResourceName = Ensure-Name -Value $FoundryResourceName -Prefix "ekfoundry" -MaxLength 20 -LowercaseOnly
$StorageAccountName = Ensure-Name -Value $StorageAccountName -Prefix "ekstore" -MaxLength 20 -LowercaseOnly

$tenantInfo = Invoke-AzJson -Arguments @("account", "show", "--subscription", $SubscriptionId, "--output", "json")
if (-not $tenantInfo) {
    throw "Unable to resolve the target subscription. Run 'az login' first."
}

Invoke-Az -Arguments @("account", "set", "--subscription", $SubscriptionId) | Out-Null

Write-Host "Registering providers..." -ForegroundColor Yellow
Invoke-Az -Arguments @("provider", "register", "--namespace", "Microsoft.Search", "--wait") | Out-Null
Invoke-Az -Arguments @("provider", "register", "--namespace", "Microsoft.CognitiveServices", "--wait") | Out-Null
Invoke-Az -Arguments @("provider", "register", "--namespace", "Microsoft.Storage", "--wait") | Out-Null

Write-Host "Creating resource group..." -ForegroundColor Yellow
Invoke-Az -Arguments @("group", "create", "--name", $ResourceGroupName, "--location", $Location, "--output", "none") | Out-Null

Write-Host "Creating storage account..." -ForegroundColor Yellow
Invoke-Az -Arguments @(
    "storage", "account", "create",
    "--name", $StorageAccountName,
    "--resource-group", $ResourceGroupName,
    "--location", $Location,
    "--sku", "Standard_LRS",
    "--kind", "StorageV2",
    "--min-tls-version", "TLS1_2",
    "--allow-blob-public-access", "false",
    "--output", "none"
) | Out-Null

$storageScope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.Storage/storageAccounts/$StorageAccountName"
try {
    $signedInUserId = (Invoke-Az -Arguments @("ad", "signed-in-user", "show", "--query", "id", "--output", "tsv")).Trim()
    if ($signedInUserId) {
        Write-Host "Granting Storage Blob Data Contributor to the signed-in user..." -ForegroundColor Yellow
        Invoke-Az -Arguments @(
            "role", "assignment", "create",
            "--assignee-object-id", $signedInUserId,
            "--assignee-principal-type", "User",
            "--role", "Storage Blob Data Contributor",
            "--scope", $storageScope,
            "--output", "none"
        ) | Out-Null
    }
}
catch {
    Write-Warning "Unable to assign Storage Blob Data Contributor automatically. You may need to grant blob data access manually."
}

Write-Host "Creating blob container for extracted figures..." -ForegroundColor Yellow
Invoke-Az -Arguments @(
    "storage", "container", "create",
    "--name", $StorageContainerName,
    "--account-name", $StorageAccountName,
    "--auth-mode", "login",
    "--public-access", "off",
    "--output", "none"
) | Out-Null

Write-Host "Creating Azure AI Search service..." -ForegroundColor Yellow
Invoke-Az -Arguments @(
    "search", "service", "create",
    "--name", $SearchServiceName,
    "--resource-group", $ResourceGroupName,
    "--location", $Location,
    "--sku", $SearchSku,
    "--partition-count", "1",
    "--replica-count", "1",
    "--semantic-search", "standard",
    "--auth-options", "aadOrApiKey",
    "--aad-auth-failure-mode", "http401WithBearerChallenge",
    "--identity-type", "SystemAssigned",
    "--public-network-access", "enabled",
    "--output", "none"
) | Out-Null

Write-Host "Creating Document Intelligence resource..." -ForegroundColor Yellow
Invoke-Az -Arguments @(
    "cognitiveservices", "account", "create",
    "--name", $DocumentIntelligenceName,
    "--resource-group", $ResourceGroupName,
    "--location", $Location,
    "--kind", "FormRecognizer",
    "--sku", "S0",
    "--custom-domain", $DocumentIntelligenceName,
    "--yes",
    "--output", "none"
) | Out-Null

Write-Host "Creating Foundry resource..." -ForegroundColor Yellow
Invoke-Az -Arguments @(
    "cognitiveservices", "account", "create",
    "--name", $FoundryResourceName,
    "--resource-group", $ResourceGroupName,
    "--location", $Location,
    "--kind", "AIServices",
    "--sku", "S0",
    "--custom-domain", $FoundryResourceName,
    "--assign-identity",
    "--yes",
    "--output", "none"
) | Out-Null

$accountPatchBody = @{
    properties = @{
        allowProjectManagement = $true
    }
} | ConvertTo-Json -Depth 10 -Compress

$accountPatchBodyEscaped = $accountPatchBody.Replace('"', '\"')
Write-Host "Enabling project management on Foundry resource..." -ForegroundColor Yellow
Invoke-Az -Arguments @(
    "rest",
    "--method", "PATCH",
    "--uri", "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.CognitiveServices/accounts/${FoundryResourceName}?api-version=2025-06-01",
    "--headers", "Content-Type=application/json",
    "--body", $accountPatchBodyEscaped,
    "--output", "none"
) | Out-Null

$projectUri = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.CognitiveServices/accounts/${FoundryResourceName}/projects/${FoundryProjectName}?api-version=2025-06-01"

if ($CreateFoundryProject) {
    Write-Host "Creating Foundry project..." -ForegroundColor Yellow
    $projectBody = @{
        location = $Location
        identity = @{
            type = "SystemAssigned"
        }
        properties = @{
            displayName = $FoundryProjectName
            description = "Project for enterprise knowledge ingestion and grounded chat."
        }
    } | ConvertTo-Json -Depth 10 -Compress
    $projectBodyEscaped = $projectBody.Replace('"', '\"')

    Invoke-Az -Arguments @(
        "rest",
        "--method", "PUT",
        "--uri", $projectUri,
        "--headers", "Content-Type=application/json",
        "--body", $projectBodyEscaped,
        "--output", "none"
    ) | Out-Null
}

if ($CreateOptionalModelDeployments) {
    Write-Host "Creating optional Foundry model deployments..." -ForegroundColor Yellow

    if ($ChatModelVersion) {
        Invoke-Az -Arguments @(
            "cognitiveservices", "account", "deployment", "create",
            "--resource-group", $ResourceGroupName,
            "--name", $FoundryResourceName,
            "--deployment-name", $ChatDeploymentName,
            "--model-format", "OpenAI",
            "--model-name", $ChatModelName,
            "--model-version", $ChatModelVersion,
            "--sku-name", "Standard",
            "--sku-capacity", "1",
            "--output", "none"
        ) | Out-Null
    }
    else {
        Write-Warning "Skipping chat model deployment because ChatModelVersion was not provided."
    }

    if ($EmbeddingModelVersion) {
        Invoke-Az -Arguments @(
            "cognitiveservices", "account", "deployment", "create",
            "--resource-group", $ResourceGroupName,
            "--name", $FoundryResourceName,
            "--deployment-name", $EmbeddingDeploymentName,
            "--model-format", "OpenAI",
            "--model-name", $EmbeddingModelName,
            "--model-version", $EmbeddingModelVersion,
            "--sku-name", "Standard",
            "--sku-capacity", "1",
            "--output", "none"
        ) | Out-Null
    }
    else {
        Write-Warning "Skipping embedding model deployment because EmbeddingModelVersion was not provided."
    }
}

$searchAdminKeys = Invoke-AzJson -Arguments @("search", "admin-key", "show", "--resource-group", $ResourceGroupName, "--service-name", $SearchServiceName, "--output", "json")
$searchQueryKeyName = "app-query-key"
$existingQueryKeys = Invoke-AzJson -Arguments @("search", "query-key", "list", "--resource-group", $ResourceGroupName, "--service-name", $SearchServiceName, "--output", "json")
$queryKey = $existingQueryKeys | Where-Object { $_.name -eq $searchQueryKeyName } | Select-Object -First 1
if (-not $queryKey) {
    $queryKey = Invoke-AzJson -Arguments @("search", "query-key", "create", "--resource-group", $ResourceGroupName, "--service-name", $SearchServiceName, "--name", $searchQueryKeyName, "--output", "json")
}

$docIntKeys = Invoke-AzJson -Arguments @("cognitiveservices", "account", "keys", "list", "--name", $DocumentIntelligenceName, "--resource-group", $ResourceGroupName, "--output", "json")
$docIntShow = Invoke-AzJson -Arguments @("cognitiveservices", "account", "show", "--name", $DocumentIntelligenceName, "--resource-group", $ResourceGroupName, "--output", "json")
$foundryShow = Invoke-AzJson -Arguments @("cognitiveservices", "account", "show", "--name", $FoundryResourceName, "--resource-group", $ResourceGroupName, "--output", "json")

$output = [ordered]@{
    resourceGroup = $ResourceGroupName
    location = $Location
    storageAccount = $StorageAccountName
    searchService = $SearchServiceName
    documentIntelligence = $DocumentIntelligenceName
    foundryResource = $FoundryResourceName
    foundryProject = $(if ($CreateFoundryProject) { $FoundryProjectName } else { "" })
    env = [ordered]@{
        AZURE_SEARCH_ENDPOINT = "https://$SearchServiceName.search.windows.net"
        AZURE_SEARCH_KEY = $searchAdminKeys.primaryKey
        AZURE_SEARCH_QUERY_KEY = $queryKey.key
        AZURE_SEARCH_INDEX_NAME = "enterprise-knowledge-index"
        AZURE_SEARCH_KNOWLEDGE_SOURCE_NAME = "enterprise-knowledge-source"
        AZURE_SEARCH_KNOWLEDGE_BASE_NAME = "enterprise-knowledge-base"
        AZURE_SEARCH_API_VERSION = "2026-04-01"
        AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT = $docIntShow.properties.endpoint
        AZURE_DOCUMENT_INTELLIGENCE_KEY = $docIntKeys.key1
        AZURE_DOCUMENT_INTELLIGENCE_MODEL = "prebuilt-layout"
        AZURE_FOUNDRY_RESOURCE_ENDPOINT = $foundryShow.properties.endpoint
        AZURE_FOUNDRY_RESOURCE_ID = $foundryShow.id
        AZURE_FOUNDRY_PROJECT_NAME = $(if ($CreateFoundryProject) { $FoundryProjectName } else { "" })
        AZURE_STORAGE_ACCOUNT = $StorageAccountName
        AZURE_STORAGE_CONTAINER = $StorageContainerName
        ENABLE_IMAGE_UNDERSTANDING = "true"
    }
}

Write-Host ""
Write-Host "Provisioning complete. Use these values in your .env file:" -ForegroundColor Green
$output | ConvertTo-Json -Depth 10
