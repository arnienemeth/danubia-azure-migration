<#
.SYNOPSIS
  Loads KEY=VALUE lines from the project's .env file into environment variables for the current
  PowerShell session. If KEY_VAULT_NAME is set and SA_PASSWORD is not, the SQL password is fetched
  from Azure Key Vault (using your 'az login' session) and kept in memory only, never on disk.
#>
$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
if (-not (Test-Path $envFile)) {
    throw ".env not found. Run: Copy-Item .env.example .env  and set your values."
}
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $key, $value = $line.Split('=', 2)
        Set-Item -Path "env:$($key.Trim())" -Value $value.Trim()
    }
}

if ($env:KEY_VAULT_NAME -and -not $env:SA_PASSWORD) {
    $secret = az keyvault secret show --vault-name $env:KEY_VAULT_NAME --name onprem-sql-sa-password `
        --query value -o tsv 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $secret) {
        throw "Could not read the SQL password from Key Vault $($env:KEY_VAULT_NAME). Are you signed in (az login) and do you have 'Key Vault Secrets User'?"
    }
    $env:SA_PASSWORD = $secret
}
