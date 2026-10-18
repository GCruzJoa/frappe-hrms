$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose --project-name frappe-mssql-pilot --file compose.yaml down
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the pilot.' }
Write-Output 'Pilot containers stopped. Named volumes have been preserved.'
