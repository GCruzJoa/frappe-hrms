param([switch]$KeepRunning)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$compose = @('compose', '--project-name', 'frappe-mssql-pilot', '--file', 'compose.yaml')
$python = '/home/frappe/frappe-bench/env/bin/python'
New-Item -ItemType Directory -Force -Path private/module-validation | Out-Null

function Invoke-SiteHelper([string]$Method, [string[]]$Extra = @()) {
    & docker @compose exec -T frappe $python -m frappe_mssql.run_site $Method @Extra
    if ($LASTEXITCODE -ne 0) { throw "Module helper failed: $Method" }
}
function Copy-Result([string]$Remote, [string]$Name) {
    $destination = "private/module-validation/$Name.json"
    & docker @compose cp "frappe:/tmp/$Remote" $destination
    if ($LASTEXITCODE -ne 0) { throw "Cannot retrieve $Name evidence" }
    return Get-Content -LiteralPath $destination -Raw | ConvertFrom-Json
}
try {
    Invoke-SiteHelper 'qa.prepare'
    Invoke-SiteHelper 'qa.seed_reports' -Extra @('--qa')
    Invoke-SiteHelper 'module_audit.catalog' -Extra @('--qa')
    $catalog = Copy-Result 'frappe-mssql-catalog-audit.json' 'catalog'
    if ($catalog.status -ne 'passed') { throw 'Missing or mismatched DocTypes' }
    Invoke-SiteHelper 'module_audit.run' -Extra @('--qa', '--kwargs', '{"phase":"schema"}')
    $schema = Copy-Result 'frappe-mssql-schema-audit.json' 'schema'
    Invoke-SiteHelper 'module_audit.run' -Extra @('--qa', '--kwargs', '{"phase":"reports"}')
    $reports = Copy-Result 'frappe-mssql-reports-audit.json' 'reports'
    Invoke-SiteHelper 'module_workflows.run' -Extra @('--qa')
    $workflows = Copy-Result 'frappe-mssql-workflows.json' 'workflows'
    & docker @compose exec -T frappe $python /opt/frappe-mssql/scripts/odbc_smoke.py
    if ($LASTEXITCODE -ne 0) { throw 'ODBC contract validation failed' }
    $badSchema = @($schema.entries | Where-Object { $_.status -notin @('passed', 'not-applicable') })
    $badReports = @($reports.entries | Where-Object { $_.status -notin @('passed', 'not-applicable-country') })
    if ($badSchema.Count -or $badReports.Count -or $workflows.failed) { throw 'Incomplete module validation; inspect the JSON evidence' }
    foreach ($name in @('General Ledger', 'Accounts Receivable', 'Stock Ledger', 'Stock Balance',
        'Serial and Batch Wise Stock Balance', 'Salary Register', 'Employee CTC Break-up',
        'Income Tax Computation', 'BOM Explorer', 'Production Plan Summary')) {
        $result = $reports.entries | Where-Object name -eq $name
        if (!$result -or $result.status -ne 'passed' -or $result.result_rows -lt 1) {
            throw "Report was not exercised with data: $name"
        }
    }
    Write-Host 'Module inventory, schema reads, reports with QA fixtures, business workflows and ODBC contract passed.'
} finally {
    if (!$KeepRunning) { & $PSScriptRoot/Stop-Pilot.ps1 }
}
