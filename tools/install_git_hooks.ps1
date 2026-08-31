# Install repository-owned Git hooks for this clone.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Push-Location $root
try {
    & git config core.hooksPath .githooks
    if ($LASTEXITCODE -ne 0) { throw 'Failed to configure core.hooksPath' }
    $configured = (& git config --get core.hooksPath).Trim()
    if ($configured -ne '.githooks') {
        throw "Unexpected core.hooksPath: $configured"
    }
} finally {
    Pop-Location
}

Write-Host 'Git security hooks installed: .githooks'
