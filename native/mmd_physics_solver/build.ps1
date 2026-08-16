$ErrorActionPreference = "Stop"

$crateRoot = $PSScriptRoot
$projectRoot = Split-Path (Split-Path $crateRoot -Parent) -Parent
$destination = Join-Path $projectRoot "mmd_skirt_proxy_creator\physics_preview\bin\win_amd64"

$savedErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
cargo test --locked --manifest-path (Join-Path $crateRoot "Cargo.toml")
$cargoTestExitCode = $LASTEXITCODE
$ErrorActionPreference = $savedErrorActionPreference
if ($cargoTestExitCode -ne 0) {
    throw "cargo test failed with exit code $cargoTestExitCode"
}
$ErrorActionPreference = "Continue"
cargo build --release --locked --manifest-path (Join-Path $crateRoot "Cargo.toml")
$cargoBuildExitCode = $LASTEXITCODE
$ErrorActionPreference = $savedErrorActionPreference
if ($cargoBuildExitCode -ne 0) {
    throw "cargo build failed with exit code $cargoBuildExitCode"
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item `
    -LiteralPath (Join-Path $crateRoot "target\release\mmd_physics_solver.dll") `
    -Destination (Join-Path $destination "mmd_physics_solver.dll") `
    -Force

Get-FileHash (Join-Path $destination "mmd_physics_solver.dll") -Algorithm SHA256
