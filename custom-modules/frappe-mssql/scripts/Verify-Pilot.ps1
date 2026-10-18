param([switch]$KeepRunning)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$compose = @('compose','--project-name','frappe-mssql-pilot','--file','compose.yaml')
try {
    $settings = @{}
    Get-Content -LiteralPath '.env' | ForEach-Object {
        if ($_ -match '^([A-Z_]+)=(.*)$') { $settings[$Matches[1]] = $Matches[2] }
    }
    $page = Invoke-WebRequest -Uri 'http://localhost:18000/login' -TimeoutSec 30
    if ($page.StatusCode -ne 200) { throw 'Login page is not available.' }
    $login = Invoke-RestMethod -Uri 'http://localhost:18000/api/method/login' -Method Post -Body @{usr='Administrator';pwd=$settings.PILOT_ADMIN_PASSWORD} -SessionVariable pilotSession -TimeoutSec 30
    if ($login.message -ne 'Logged In') { throw 'Administrator login failed.' }
    & docker @compose exec -T frappe bench --site mssql.localhost execute frappe_mssql.acceptance.run
    if ($LASTEXITCODE -ne 0) { throw 'Database acceptance checks failed.' }
    foreach ($iteration in 1..2) {
        & docker @compose exec -T frappe bench --site mssql.localhost migrate
        if ($LASTEXITCODE -ne 0) { throw "Migration $iteration failed." }
    }
    & docker @compose restart frappe
    if ($LASTEXITCODE -ne 0) { throw 'Restart failed.' }
    $ok = $false
    foreach ($attempt in 1..20) {
        try {
            $ping = Invoke-RestMethod -Uri 'http://localhost:18000/api/method/ping' -TimeoutSec 5
            if ($ping.message -eq 'pong') { $ok = $true; break }
        } catch { }
        Start-Sleep -Seconds 2
    }
    if (!$ok) { throw 'The site did not recover after restart.' }
    & docker @compose exec -T frappe bench --site mssql.localhost execute frappe_mssql.acceptance.assert_persistence
    if ($LASTEXITCODE -ne 0) { throw 'Persistence validation failed.' }
    & $PSScriptRoot/Backup-Pilot.ps1 -VerifyRestore
    if ($LASTEXITCODE -ne 0) { throw 'Backup and restore validation failed.' }
    New-Item -ItemType Directory -Force -Path private | Out-Null
    @{ verified_at = [DateTime]::UtcNow.ToString('o'); result = 'passed'; checks = @('login','employees','permissions','rollback','concurrency','migration-twice','restart','native-backup-restore') } | ConvertTo-Json | Set-Content -LiteralPath private/acceptance.json
} finally {
    if (!$KeepRunning) { & $PSScriptRoot/Stop-Pilot.ps1 }
}
