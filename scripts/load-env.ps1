<#
.SYNOPSIS
  Loads KEY=VALUE lines from the project's .env file into environment variables
  for the current PowerShell session. Lines starting with # are comments.
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
