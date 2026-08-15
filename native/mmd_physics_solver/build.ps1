$ErrorActionPreference = "Stop"

$crateRoot = $PSScriptRoot
$projectRoot = Split-Path (Split-Path $crateRoot -Parent) -Parent
$destination = Join-Path $projectRoot "mmd_skirt_proxy_creator\physics_preview\bin\win_amd64"

cargo test --locked --manifest-path (Join-Path $crateRoot "Cargo.toml")
cargo build --release --locked --manifest-path (Join-Path $crateRoot "Cargo.toml")
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item `
    -LiteralPath (Join-Path $crateRoot "target\release\mmd_physics_solver.dll") `
    -Destination (Join-Path $destination "mmd_physics_solver.dll") `
    -Force

Get-FileHash (Join-Path $destination "mmd_physics_solver.dll") -Algorithm SHA256

