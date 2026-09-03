param(
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

function Remove-IfExists([string]$Path) {
    if (-not (Test-Path $Path)) {
        return
    }
    if ($WhatIf) {
        Write-Host ("[WhatIf] Would remove: {0}" -f $Path)
        return
    }
    try {
        Remove-Item -Force -Recurse $Path -ErrorAction Stop
        Write-Host ("Removed: {0}" -f $Path)
    } catch {
        Write-Warning ("Failed to remove {0}: {1}" -f $Path, $_.Exception.Message)
    }
}

# Standard Python cache dirs.
$skipPatterns = @(
    "\\.venv\\",
    "\\frontend\\src\\node_modules\\"
)

Get-ChildItem -Recurse -Directory -Force -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $full = $_.FullName; -not ($skipPatterns | Where-Object { $full -like "*$_*" }) } |
    ForEach-Object { Remove-IfExists $_.FullName }

# Standard pytest cache (if enabled).
Get-ChildItem -Recurse -Directory -Force -Filter ".pytest_cache" -ErrorAction SilentlyContinue |
    Where-Object { $full = $_.FullName; -not ($skipPatterns | Where-Object { $full -like "*$_*" }) } |
    ForEach-Object { Remove-IfExists $_.FullName }

# Non-standard cache dirs that can show up in some environments.
Get-ChildItem -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "pytest-cache-files-*" } | ForEach-Object {
    Remove-IfExists $_.FullName
}

Write-Host "Done."
Write-Host "Note: If you see permission denied for pytest-cache-files-* folders, run PowerShell as Administrator and re-run this script."
