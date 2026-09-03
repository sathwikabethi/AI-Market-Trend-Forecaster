param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,

    [string]$DatabaseUrl = $env:DATABASE_URL,

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backupPath = Resolve-Path $BackupFile

if (-not $Force) {
    throw "Refusing to restore without -Force. Restoring will overwrite the current database."
}

if ($DatabaseUrl -and ($DatabaseUrl.StartsWith("postgres://") -or $DatabaseUrl.StartsWith("postgresql://"))) {
    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if (-not $psql) {
        throw "psql not found on PATH. Install PostgreSQL client tools to restore."
    }
    if (-not ($backupPath.Path.ToLower().EndsWith(".sql"))) {
        throw "Expected a .sql dump for PostgreSQL restore."
    }

    & $psql.Source $DatabaseUrl -f $backupPath.Path
    Write-Host ("PostgreSQL restore completed from {0}" -f $backupPath.Path)
} else {
    if (-not ($backupPath.Path.ToLower().EndsWith(".sqlite") -or $backupPath.Path.ToLower().EndsWith(".db"))) {
        throw "Expected a .sqlite/.db file for SQLite restore."
    }

    $dbPath = Join-Path $repoRoot "data\\app.db"
    $dbDir = Split-Path -Parent $dbPath
    New-Item -ItemType Directory -Force -Path $dbDir | Out-Null
    Copy-Item -Force $backupPath.Path $dbPath
    Write-Host ("SQLite restore completed to {0}" -f $dbPath)
}

