param([switch]$Build, [switch]$FromPublicSources)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$lockPath = Join-Path (Get-Location) 'versions.lock.json'
if (!(Test-Path -LiteralPath $lockPath)) { throw 'Missing versions.lock.json: complete the source update and pinning first.' }
$lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
$baseTag = $lock.frappe_base.tag
$baseId = if (!$FromPublicSources) { docker image inspect $baseTag --format '{{.Id}}' 2>$null } else { $null }
if ($FromPublicSources -or $LASTEXITCODE -ne 0 -or $baseId -ne $lock.frappe_base.image_id) {
    if (!(Test-Path private/source-base.json)) { throw 'Run scripts/Build-SourceBase.ps1 to build the pinned public sources first.' }
    $sourceBase = Get-Content -Raw private/source-base.json | ConvertFrom-Json
    foreach ($app in 'frappe','erpnext','hrms') {
        if ($sourceBase.apps.$app.commit -ne $lock.apps.$app.commit) { throw "The source base uses a different revision of $app." }
    }
    $baseTag = $sourceBase.tag
    $baseId = docker image inspect $baseTag --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $baseId -ne $sourceBase.image_id) { throw 'The source base differs from its recorded image.' }
}
$total = [double](docker info --format '{{.MemTotal}}')
$percent = docker stats --no-stream --format '{{.MemPerc}}'
$usedPercent = ($percent | ForEach-Object { [double]($_ -replace '%','') } | Measure-Object -Sum).Sum
$free = $total * (1 - $usedPercent / 100)
if ($free -lt 3.5GB) { throw 'At least 3.5 GiB of available Docker memory is required. Other services have not been stopped.' }
if (!(Test-Path -LiteralPath '.env')) {
    function New-PilotPassword { 'Aa1!' + [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24)) }
    $settings = @{
        MSSQL_IMAGE = $lock.sqlserver.image
        REDIS_IMAGE = $lock.redis.image
        FRAPPE_BASE_IMAGE = $baseTag
        MSSQL_SA_PASSWORD = New-PilotPassword
        PILOT_DB_PASSWORD = New-PilotPassword
        PILOT_ADMIN_PASSWORD = New-PilotPassword
    }
    $settings.GetEnumerator() | Sort-Object Name | ForEach-Object { '{0}={1}' -f $_.Name,$_.Value } | Set-Content -Encoding utf8 -LiteralPath '.env'
} else {
    $lines = Get-Content -LiteralPath '.env'
    if ($lines -match '^FRAPPE_BASE_IMAGE=') {
        $lines = $lines -replace '^FRAPPE_BASE_IMAGE=.*$', ('FRAPPE_BASE_IMAGE=' + $baseTag)
    } else {
        $lines += 'FRAPPE_BASE_IMAGE=' + $baseTag
    }
    $lines | Set-Content -Encoding utf8 -LiteralPath '.env'
}
$compose = @('compose','--project-name','frappe-mssql-pilot','--file','compose.yaml')
& docker @compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed.' }
if ($Build) {
    & docker @compose build frappe
    if ($LASTEXITCODE -ne 0) { throw 'Pilot image build failed.' }
}
& docker @compose up --detach
if ($LASTEXITCODE -ne 0) { throw 'Pilot startup failed. See docker compose logs.' }
Write-Output 'Pilot startup requested: http://localhost:18000. Credentials are in the ignored .env file.'
