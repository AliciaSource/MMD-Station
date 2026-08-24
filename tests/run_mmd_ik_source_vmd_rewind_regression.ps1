$ErrorActionPreference = "Stop"

$Blender = "D:\Program Files\Blender Foundation\Blender 4.4\blender.exe"
$Script = Join-Path $PSScriptRoot "mmd_ik_source_vmd_rewind_regression.py"
$PreviousUtf8 = $env:PYTHONUTF8

try {
    $env:PYTHONUTF8 = "1"
    $ErrorActionPreference = "Continue"
    $Output = & $Blender --background --factory-startup --python-exit-code 1 --python $Script 2>&1
    $BlenderExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $Output | Where-Object {
        "$_" -match "MMD_IK_SOURCE_VMD_REWIND_(PATH_OK|REGRESSION_OK)"
    } | ForEach-Object { Write-Host "$_" }
    if ($BlenderExitCode -ne 0) {
        $Output | Out-Host
        throw "MMD IK source VMD rewind regression failed with exit code $BlenderExitCode"
    }
    if (-not ($Output -match "MMD_IK_SOURCE_VMD_REWIND_REGRESSION_OK")) {
        $Output | Out-Host
        throw "MMD IK source VMD rewind regression marker missing"
    }
}
finally {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = $PreviousUtf8
}
