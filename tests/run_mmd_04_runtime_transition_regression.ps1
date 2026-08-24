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
$Script = Join-Path $PSScriptRoot "mmd_04_runtime_transition_regression.py"
$PreviousUtf8 = $env:PYTHONUTF8

try {
    $env:PYTHONUTF8 = "1"
    $ErrorActionPreference = "Continue"
    & $Blender --background --factory-startup $Blend --python-exit-code 1 --python $Script
    $BlenderExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($BlenderExitCode -ne 0) {
        throw "Runtime transition regression failed with exit code $BlenderExitCode"
    }
}
finally {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = $PreviousUtf8
}
