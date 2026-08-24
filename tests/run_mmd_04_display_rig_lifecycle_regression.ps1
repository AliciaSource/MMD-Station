$ErrorActionPreference = "Stop"

$Blender = "D:\Program Files\Blender Foundation\Blender 4.4\blender.exe"
$ModelDirectory = -join [char[]](0x6A21, 0x578B)
$CharacterDirectory = -join [char[]](0x9CF4, 0x6F6E, 0x2D, 0x9054, 0x5C3C, 0x5A6D)
$DaniyaDirectory = -join [char[]](0x9054, 0x5C3C, 0x5A6D)
$Blend = Join-Path "D:\MMD" $ModelDirectory
$Blend = Join-Path $Blend "Alicia"
$Blend = Join-Path $Blend $CharacterDirectory
$Blend = Join-Path $Blend $DaniyaDirectory
$Blend = Join-Path $Blend "04.blend"
$Script = Join-Path $PSScriptRoot "mmd_04_display_rig_lifecycle_regression.py"
$SavedCopy = Join-Path $env:TEMP ("spx-mmd-04-display-rig-lifecycle-" + [guid]::NewGuid().ToString("N") + ".blend")
$PreviousPhase = $env:SPX_LIFECYCLE_PHASE
$PreviousPath = $env:SPX_LIFECYCLE_SAVE_PATH
$PreviousUtf8 = $env:PYTHONUTF8

try {
    $env:PYTHONUTF8 = "1"
    $env:SPX_LIFECYCLE_SAVE_PATH = $SavedCopy
    $env:SPX_LIFECYCLE_PHASE = "exercise"
    $ErrorActionPreference = "Continue"
    & $Blender --background --factory-startup $Blend --python-exit-code 1 --python $Script
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) {
        throw "DisplayRig lifecycle exercise failed with exit code $LASTEXITCODE"
    }

    $env:SPX_LIFECYCLE_PHASE = "verify_saved"
    $ErrorActionPreference = "Continue"
    & $Blender --background --factory-startup $SavedCopy --python-exit-code 1 --python $Script
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) {
        throw "DisplayRig saved-copy verification failed with exit code $LASTEXITCODE"
    }
}
finally {
    $ErrorActionPreference = "Stop"
    if (Test-Path -LiteralPath $SavedCopy) {
        Remove-Item -LiteralPath $SavedCopy -Force
    }
    $env:SPX_LIFECYCLE_PHASE = $PreviousPhase
    $env:SPX_LIFECYCLE_SAVE_PATH = $PreviousPath
    $env:PYTHONUTF8 = $PreviousUtf8
}
