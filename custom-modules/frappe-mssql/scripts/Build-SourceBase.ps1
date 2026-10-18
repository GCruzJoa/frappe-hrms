$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$tag = 'local/frappe-mssql:source-base'
docker build --file Dockerfile.source --tag $tag .
if ($LASTEXITCODE -ne 0) { throw 'Pinned public source build failed.' }
$imageId = docker image inspect $tag --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the source image.' }
New-Item -ItemType Directory -Force -Path private | Out-Null
@{ tag=$tag; image_id=$imageId; apps=(Get-Content -Raw versions.lock.json | ConvertFrom-Json).apps } | ConvertTo-Json -Depth 8 | Set-Content private/source-base.json
Write-Output 'Source base built. Start-Pilot.ps1 will use it when the captured local snapshot is unavailable.'
