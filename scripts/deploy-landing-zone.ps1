<#
.SYNOPSIS
  Deploys the Danubia landing zone from your PC. Shows a what-if preview first and asks before changing anything.
#>
. "$PSScriptRoot\load-env.ps1"
if (-not $env:BUDGET_EMAIL) { throw 'Set BUDGET_EMAIL in .env first.' }

$root = Split-Path $PSScriptRoot -Parent
az deployment sub create `
    --name danubia-landing-zone `
    --location swedencentral `
    --template-file "$root\infra\main.bicep" `
    --parameters "$root\infra\main.dev.bicepparam" `
    --confirm-with-what-if
