# Dev install via directory Junction. No ZIP and no administrator rights needed.
#
# Usage:
#   ./tools/dev_link.ps1
#   ./tools/dev_link.ps1 -Remove
param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'

$toolsDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $toolsDirectory
$packageDirectory = [System.IO.Path]::GetFullPath(
    (Join-Path $repositoryRoot 'mmd_station')
)
$addonsDirectory = [System.IO.Path]::GetFullPath(
    (Join-Path $env:APPDATA 'Blender Foundation\Blender\4.4\scripts\addons')
)
$linkPath = [System.IO.Path]::GetFullPath(
    (Join-Path $addonsDirectory 'mmd_station')
)

if ([System.IO.Path]::GetDirectoryName($linkPath) -ne $addonsDirectory) {
    throw "Refusing unexpected add-on path: $linkPath"
}

function Remove-DevJunction([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        return $false
    }
    [System.IO.Directory]::Delete($Path, $false)
    return $true
}

if ($Remove) {
    if (Remove-DevJunction $linkPath) {
        Write-Host "Removed dev Junction: $linkPath"
    } elseif (Test-Path -LiteralPath $linkPath) {
        throw "Refusing to remove a real add-on directory: $linkPath"
    } else {
        Write-Host "No dev Junction exists: $linkPath"
    }
    return
}

if (-not (Test-Path -LiteralPath $packageDirectory -PathType Container)) {
    throw "Package directory not found: $packageDirectory"
}
if (-not (Test-Path -LiteralPath $addonsDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $addonsDirectory -Force | Out-Null
}

if (Test-Path -LiteralPath $linkPath) {
    $item = Get-Item -LiteralPath $linkPath -Force
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        [System.IO.Directory]::Delete($linkPath, $false)
    } else {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backupPath = "$linkPath.pre-dev-link-$stamp"
        Move-Item -LiteralPath $linkPath -Destination $backupPath
        Write-Host "Moved the previous real installation to: $backupPath"
    }
}

New-Item -ItemType Junction -Path $linkPath -Target $packageDirectory | Out-Null

$updaterState = Join-Path $packageDirectory 'mmd_station_updater'
if (-not (Test-Path -LiteralPath $updaterState)) {
    New-Item -ItemType Directory -Path $updaterState | Out-Null
}

Write-Host "Linked $linkPath -> $packageDirectory"
Write-Host "Reload Scripts or restart Blender 4.4 after source changes."
