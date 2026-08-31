# Package mmd_station/ into an installable Blender add-on ZIP under dist/.
# This script does not change versions, commit, push, tag, or publish a release.
param(
    [string]$Ref = "HEAD"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$packageDirectory = Join-Path $root 'mmd_station'
$initFile = Join-Path $packageDirectory '__init__.py'
$versionFile = Join-Path $packageDirectory '_version.py'
$securityScanner = Join-Path $root 'tools\security_scan.py'

if (-not (Test-Path $packageDirectory)) { throw "Package directory not found: $packageDirectory" }
if (-not (Test-Path $initFile)) { throw "__init__.py not found: $initFile" }
if (-not (Test-Path $securityScanner)) { throw "Security scanner not found: $securityScanner" }

function Invoke-SecurityScan {
    param([string[]]$ScanArguments)
    & python $securityScanner @ScanArguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Security scan blocked packaging'
    }
}

$content = [System.IO.File]::ReadAllText($initFile, [System.Text.Encoding]::UTF8)
$match = [regex]::Match($content, '"version"\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')
if (-not $match.Success) { throw 'Cannot parse version from __init__.py' }
$version = '{0}.{1}.{2}' -f $match.Groups[1].Value, $match.Groups[2].Value, $match.Groups[3].Value

if (Test-Path $versionFile) {
    $versionContent = [System.IO.File]::ReadAllText($versionFile, [System.Text.Encoding]::UTF8)
    $prereleaseMatch = [regex]::Match($versionContent, "PRERELEASE\s*=\s*(?:None|`"([^`"]*)`"|'([^']*)')")
    if ($prereleaseMatch.Success) {
        $prerelease = if ($prereleaseMatch.Groups[1].Success) {
            $prereleaseMatch.Groups[1].Value
        } elseif ($prereleaseMatch.Groups[2].Success) {
            $prereleaseMatch.Groups[2].Value
        } else {
            ''
        }
        if (-not [string]::IsNullOrWhiteSpace($prerelease)) {
            $version = "$version-$prerelease"
        }
    }
}

$distDirectory = Join-Path $root 'dist'
if (-not (Test-Path $distDirectory)) {
    New-Item -ItemType Directory -Path $distDirectory | Out-Null
}
$outputZip = Join-Path $distDirectory "mmd_station-$version.zip"
if (Test-Path $outputZip) { Remove-Item -LiteralPath $outputZip -Force }

$useGit = $false
Push-Location $root
try {
    & git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -eq 0) {
        & git rev-parse --verify --quiet "${Ref}:mmd_station" *> $null
        if ($LASTEXITCODE -eq 0) { $useGit = $true }
    }
} finally {
    Pop-Location
}

if ($useGit) {
    Invoke-SecurityScan -ScanArguments @('--ref', $Ref)
    Push-Location $root
    try {
        & git archive --format=zip --prefix=mmd_station/ -o $outputZip "${Ref}:mmd_station"
        if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
    } finally {
        Pop-Location
    }
    Write-Host "Packed via git archive ($Ref): $outputZip"
} else {
    Invoke-SecurityScan -ScanArguments @('--path', $packageDirectory)
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::Open(
        $outputZip,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    try {
        Get-ChildItem -LiteralPath $packageDirectory -File -Recurse |
            Where-Object {
                $_.Extension -ne '.pyc' -and
                $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
                $_.FullName -notmatch '[\\/]mmd_station_updater[\\/]'
            } |
            ForEach-Object {
                $relativePath = $_.FullName.Substring($root.Length + 1).Replace('\', '/')
                [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $archive,
                    $_.FullName,
                    $relativePath,
                    [System.IO.Compression.CompressionLevel]::Optimal
                ) | Out-Null
            }
    } finally {
        $archive.Dispose()
    }
    Write-Host "Packed from working tree: $outputZip"
}

try {
    Invoke-SecurityScan -ScanArguments @('--archive', $outputZip)
} catch {
    if (Test-Path $outputZip) { Remove-Item -LiteralPath $outputZip -Force }
    throw
}

Write-Host "Version: $version"
Write-Host "OK: $outputZip"
