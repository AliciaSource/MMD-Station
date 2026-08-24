param(
    [string]$Blender = "D:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
    [string]$BlendFile = ""
)

$ErrorActionPreference = "Stop"
if (-not $BlendFile) {
    $model = ([char]0x6a21) + ([char]0x578b)
    $character = ([char]0x9cf4) + ([char]0x6f6e) + "-" +
        ([char]0x9054) + ([char]0x5c3c) + ([char]0x5a6d)
    $variant = ([char]0x9054) + ([char]0x5c3c) + ([char]0x5a6d)
    $BlendFile = Join-Path "D:\MMD" "$model\Alicia\$character\$variant\04.blend"
}
$script = Join-Path $PSScriptRoot "mmd_04_interaction_matrix_regression.py"
if (-not (Test-Path -LiteralPath $Blender -PathType Leaf)) {
    throw "Blender executable not found: $Blender"
}
if (-not (Test-Path -LiteralPath $BlendFile -PathType Leaf)) {
    throw "Blend file not found: $BlendFile"
}

$oldSolver = $env:SPX_TEST_SOLVER_TARGET
$oldIK = $env:SPX_ENABLE_IK
try {
    foreach ($solver in @("MMD", "PMX")) {
        foreach ($ik in @($false, $true)) {
            $env:SPX_TEST_SOLVER_TARGET = $solver
            if ($ik) {
                $env:SPX_ENABLE_IK = "1"
            } else {
                Remove-Item Env:SPX_ENABLE_IK -ErrorAction SilentlyContinue
            }
            Write-Host "Running solver=$solver ik=$ik"
            $ErrorActionPreference = "Continue"
            $output = & $Blender --factory-startup --background $BlendFile --python $script 2>&1
            $exitCode = $LASTEXITCODE
            $ErrorActionPreference = "Stop"
            $marker = "MMD_04_INTERACTION_MATRIX_OK solver=$solver ik=$ik"
            $matched = @($output | Where-Object { "$_" -match [regex]::Escape($marker) })
            if ($exitCode -ne 0 -or $matched.Count -eq 0) {
                $output | Out-Host
                throw "Interaction regression failed: solver=$solver ik=$ik exit=$exitCode"
            }
            $matched | ForEach-Object { Write-Host "$_" }
        }
    }
} finally {
    if ($null -eq $oldSolver) {
        Remove-Item Env:SPX_TEST_SOLVER_TARGET -ErrorAction SilentlyContinue
    } else {
        $env:SPX_TEST_SOLVER_TARGET = $oldSolver
    }
    if ($null -eq $oldIK) {
        Remove-Item Env:SPX_ENABLE_IK -ErrorAction SilentlyContinue
    } else {
        $env:SPX_ENABLE_IK = $oldIK
    }
}
