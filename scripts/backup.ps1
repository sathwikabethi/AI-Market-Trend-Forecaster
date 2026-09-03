param(
    [string]$OutDir = "backups",
    [string]$DatabaseUrl = $env:DATABASE_URL
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

$outPath = Join-Path $repoRoot $OutDir
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

function Copy-IfExists([string]$src, [string]$dst) {
    if (Test-Path $src) {
        Copy-Item -Force -Recurse $src $dst
    }
}

if ($DatabaseUrl -and ($DatabaseUrl.StartsWith("postgres://") -or $DatabaseUrl.StartsWith("postgresql://"))) {
    $pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
    if (-not $pgDump) {
        throw "pg_dump not found on PATH. Install PostgreSQL client tools or backup via DB provider."
    }

    $sqlFile = Join-Path $outPath ("backup_{0}.sql" -f $timestamp)
    & $pgDump.Source $DatabaseUrl --no-owner --no-privileges --file $sqlFile
    Write-Host ("Database backup written to {0}" -f $sqlFile)
} else {
    $dbPath = Join-Path $repoRoot "data\\app.db"
    if (-not (Test-Path $dbPath)) {
        throw ("SQLite database not found at {0}" -f $dbPath)
    }
    $dest = Join-Path $outPath ("backup_{0}.sqlite" -f $timestamp)
    Copy-Item -Force $dbPath $dest
    Write-Host ("Database backup written to {0}" -f $dest)
}

# Best-effort: snapshot the dataset artifacts next to the DB backup.
$dataRoot = Join-Path $repoRoot "data"
$dataSnapshot = Join-Path $outPath ("data_{0}" -f $timestamp)
New-Item -ItemType Directory -Force -Path $dataSnapshot | Out-Null
Copy-IfExists (Join-Path $dataRoot "raw") (Join-Path $dataSnapshot "raw")
Copy-IfExists (Join-Path $dataRoot "processed") (Join-Path $dataSnapshot "processed")

Write-Host ("Data snapshot written to {0}" -f $dataSnapshot)

