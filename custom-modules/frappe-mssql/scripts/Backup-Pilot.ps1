param([switch]$VerifyRestore)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$compose = @('compose','--project-name','frappe-mssql-pilot','--file','compose.yaml')
& docker @compose exec -T sqlserver mkdir -p /var/opt/mssql/backup
if ($LASTEXITCODE -ne 0) { throw 'Could not create the native backup directory.' }
$arguments = if ($VerifyRestore) { '{"verify_restore":true}' } else { '{}' }
& docker @compose exec -T frappe bench --site mssql.localhost execute frappe_mssql.backup.run --kwargs $arguments
if ($LASTEXITCODE -ne 0) { throw 'Native backup or restore verification failed.' }
$backupDir = Join-Path (Get-Location) ('private\backups\' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
& docker @compose cp sqlserver:/var/opt/mssql/backup/pilot.bak (Join-Path $backupDir 'pilot.bak')
if ($LASTEXITCODE -ne 0) { throw 'Native backup export failed.' }
& docker @compose cp frappe:/tmp/frappe-mssql-site-files.tar.gz (Join-Path $backupDir 'site-files.tar.gz')
if ($LASTEXITCODE -ne 0) { throw 'Site file export failed.' }
Get-ChildItem -LiteralPath $backupDir -File | Get-FileHash -Algorithm SHA256 | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backupDir 'sha256.json')
Write-Output "Backup exported to $backupDir"
