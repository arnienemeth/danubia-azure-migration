<#
.SYNOPSIS
  Starts Danubia's simulated on-premises SQL Server and creates the DanubiaERP database.

.DESCRIPTION
  SQL Server 2022 (Developer edition, free) runs in a Docker container. The database is set to
  compatibility level 130, so it behaves like the company's old SQL Server 2016.
  Data lives in a named Docker volume, so it survives container restarts and re-creation.
  Safe to run as often as you like: it creates, starts or skips as needed.
#>
. "$PSScriptRoot\load-env.ps1"

$container = 'danubia-sql'
$image     = 'mcr.microsoft.com/mssql/server:2022-latest'
$volume    = 'danubia-sql-data'
$sqlcmd    = '/opt/mssql-tools18/bin/sqlcmd'

# 1. Create or start the container
$status = docker ps -a --filter "name=^$container$" --format '{{.Status}}'
if (-not $status) {
    Write-Host "Creating container $container (first run downloads ~1.5 GB) ..."
    docker run -d --name $container `
        -e ACCEPT_EULA=Y `
        -e MSSQL_PID=Developer `
        -e "MSSQL_SA_PASSWORD=$env:SA_PASSWORD" `
        -p 1433:1433 `
        -v "${volume}:/var/opt/mssql" `
        $image | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'docker run failed. Is Docker Desktop running?' }
}
elseif ($status -notlike 'Up*') {
    Write-Host "Starting existing container $container ..."
    docker start $container | Out-Null
}
else {
    Write-Host "$container is already running."
}

# 2. Wait until SQL Server accepts logins (it needs 10-30 seconds on first start)
Write-Host 'Waiting for SQL Server ' -NoNewline
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    docker exec $container $sqlcmd -S localhost -U sa -P $env:SA_PASSWORD -C -Q 'SELECT 1' *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Write-Host '.' -NoNewline
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw "SQL Server did not become ready. Check the log: docker logs $container" }
Write-Host ' ready.'

# 3. Create the ERP database and make it behave like SQL Server 2016
$sql = "IF DB_ID('DanubiaERP') IS NULL CREATE DATABASE DanubiaERP; " +
       "ALTER DATABASE DanubiaERP SET COMPATIBILITY_LEVEL = 130; " +
       "SET NOCOUNT ON; " +
       "SELECT name, compatibility_level FROM sys.databases WHERE name = 'DanubiaERP'; " +
       "SELECT SERVERPROPERTY('ProductVersion') AS version, SERVERPROPERTY('Edition') AS edition;"
docker exec $container $sqlcmd -S localhost -U sa -P $env:SA_PASSWORD -C -W -Q $sql
