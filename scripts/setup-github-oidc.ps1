<#
.SYNOPSIS
  One-time setup: lets GitHub Actions deploy to Azure WITHOUT any stored secret (OIDC federation).

.DESCRIPTION
  1. Creates an app registration + service principal "gh-danubia-platform" (the identity GitHub acts as).
  2. Adds two federated credentials: Azure trusts tokens only from this repo's main branch and pull requests.
  3. Grants the minimum roles the landing zone deployment needs.
  4. Prints the three IDs to store as GitHub repository variables (they are identifiers, not secrets).
  Safe to re-run: existing objects are reused.

.PARAMETER Repo
  GitHub repository as owner/name, for example arnienemeth/danubia-azure-migration
#>
param([Parameter(Mandatory)][string]$Repo)

$ErrorActionPreference = 'Stop'
$appName = 'gh-danubia-platform'
$subId = az account show --query id -o tsv
$tenantId = az account show --query tenantId -o tsv

# 1. App registration + service principal
$appId = az ad app list --display-name $appName --query '[0].appId' -o tsv
if (-not $appId) {
    Write-Host "Creating app registration $appName ..."
    $appId = az ad app create --display-name $appName --query appId -o tsv
}
$spId = az ad sp list --filter "appId eq '$appId'" --query '[0].id' -o tsv
if (-not $spId) {
    $spId = az ad sp create --id $appId --query id -o tsv
}

# 2. Federated credentials: which GitHub tokens Azure will accept
$existing = az ad app federated-credential list --id $appId --query '[].name' -o tsv
# GitHub can send the subject in two formats:
#   classic:  repo:owner/name:...
#   with IDs: repo:owner@<ownerId>/name@<repoId>:...   (IDs never get reused, so a renamed or re-created
#             repo with the same name cannot impersonate this one)
# Register both, so the pipeline works whichever format GitHub sends.
$gh = Invoke-RestMethod "https://api.github.com/repos/$Repo"
$owner, $name = $Repo.Split('/')
$withIds = "repo:${owner}@$($gh.owner.id)/${name}@$($gh.id)"
Write-Host "GitHub IDs: owner $($gh.owner.id), repo $($gh.id)"
$creds = @(
    @{ name = 'github-main'; subject = "repo:${Repo}:ref:refs/heads/main" },
    @{ name = 'github-pull-request'; subject = "repo:${Repo}:pull_request" },
    @{ name = 'github-main-ids'; subject = "${withIds}:ref:refs/heads/main" },
    @{ name = 'github-pull-request-ids'; subject = "${withIds}:pull_request" }
)
foreach ($c in $creds) {
    if ($existing -contains $c.name) { Write-Host "Federated credential $($c.name) exists."; continue }
    $file = New-TemporaryFile
    @{
        name      = $c.name
        issuer    = 'https://token.actions.githubusercontent.com'
        subject   = $c.subject
        audiences = @('api://AzureADTokenExchange')
    } | ConvertTo-Json | Set-Content $file -Encoding utf8
    az ad app federated-credential create --id $appId --parameters "@$file" | Out-Null
    Remove-Item $file
    Write-Host "Added federated credential $($c.name) -> $($c.subject)"
}

# 3. Roles. Contributor: create resource groups, resources, budgets. Resource Policy Contributor: assign policies.
#    Neither role can grant access to others (no role assignments), so the pipeline cannot escalate its rights.
$scope = "/subscriptions/$subId"
foreach ($role in @('Contributor', 'Resource Policy Contributor')) {
    $has = az role assignment list --assignee $spId --role $role --scope $scope --query '[0].id' -o tsv
    if (-not $has) {
        az role assignment create --assignee-object-id $spId --assignee-principal-type ServicePrincipal `
            --role $role --scope $scope | Out-Null
        Write-Host "Granted $role on the subscription."
    }
}

# 4. What to put into GitHub
Write-Host ''
Write-Host 'Add these as GitHub repository VARIABLES (Settings > Secrets and variables > Actions > Variables):'
Write-Host "  AZURE_CLIENT_ID       = $appId"
Write-Host "  AZURE_TENANT_ID       = $tenantId"
Write-Host "  AZURE_SUBSCRIPTION_ID = $subId"
Write-Host 'And one repository SECRET:  BUDGET_EMAIL = <your e-mail>'
