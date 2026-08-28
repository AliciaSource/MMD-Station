param(
    [string]$V120Bin = $env:MMD_V120_BIN,
    [string]$V120Include = $env:MMD_V120_INCLUDE,
    [string]$V120Lib = $env:MMD_V120_LIB,
    [string]$V120Ide = $env:MMD_V120_IDE,
    [string]$VsDevCmd = $env:MMD_VSDEVCMD
)

$ErrorActionPreference = "Stop"

$crateRoot = $PSScriptRoot
$projectRoot = Split-Path (Split-Path $crateRoot -Parent) -Parent
$destination = Join-Path $projectRoot "mmd_station\physics_preview\bin\win_amd64"

if (-not $V120Bin) {
    $visualStudio120 = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio 12.0"
    $V120Bin = Join-Path $visualStudio120 "VC\bin\x86_amd64"
    $V120Include = Join-Path $visualStudio120 "VC\include"
    $V120Lib = Join-Path $visualStudio120 "VC\lib\amd64"
    $V120Ide = Join-Path $visualStudio120 "Common7\IDE"
}

$compiler = Join-Path $V120Bin "cl.exe"
$linker = Join-Path $V120Bin "link.exe"
foreach ($requiredPath in @($compiler, $linker, $V120Include)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "VS2013 RTM build input is missing: $requiredPath"
    }
}
$v120LibPaths = @($V120Lib -split ";" | Where-Object { $_ })
if ($v120LibPaths.Count -eq 0) {
    throw "MMD_V120_LIB must contain at least one x64 library directory"
}
foreach ($libraryPath in $v120LibPaths) {
    if (-not (Test-Path -LiteralPath $libraryPath)) {
        throw "VS2013 RTM library directory is missing: $libraryPath"
    }
}

if (-not $VsDevCmd) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        $modernVisualStudio = & $vswhere -latest -products * `
            -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
            -property installationPath
        if ($modernVisualStudio) {
            $VsDevCmd = Join-Path $modernVisualStudio "Common7\Tools\VsDevCmd.bat"
        }
    }
}
if (-not $VsDevCmd -or -not (Test-Path -LiteralPath $VsDevCmd)) {
    throw "A current Visual Studio VsDevCmd.bat is required for the Rust and Windows SDK libraries"
}

$savedPath = $env:PATH
try {
    $pathParts = @($V120Bin, (Split-Path $V120Bin -Parent))
    if ($V120Ide) {
        $pathParts += $V120Ide
    }
    $env:PATH = ($pathParts -join ";") + ";" + $savedPath
    function Get-ToolBanner([string]$toolPath) {
        $probe = [Diagnostics.ProcessStartInfo]::new()
        $probe.FileName = $toolPath
        $probe.Arguments = "/?"
        $probe.UseShellExecute = $false
        $probe.RedirectStandardOutput = $true
        $probe.RedirectStandardError = $true
        $process = [Diagnostics.Process]::Start($probe)
        $banner = $process.StandardOutput.ReadToEnd() + $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        return $banner
    }
    $compilerBanner = Get-ToolBanner $compiler
    $linkerBanner = Get-ToolBanner $linker
} finally {
    $env:PATH = $savedPath
}
if ($compilerBanner -notmatch "Version 18\.00\.21005\.1") {
    throw "Bit-compatible builds require VS2013 RTM cl.exe 18.00.21005.1"
}
if ($linkerBanner -notmatch "Version 12\.00\.21005\.1") {
    throw "Bit-compatible builds require VS2013 RTM link.exe 12.00.21005.1"
}

$buildCommand = Join-Path $env:TEMP ("mmd-v120-ltcg-{0}.cmd" -f ([guid]::NewGuid().ToString("N")))
$commandLines = @(
    "@echo off",
    "call `"$VsDevCmd`" -arch=x64 -host_arch=x64 >nul",
    "set `"CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER=$linker`"",
    "set `"PATH=$($pathParts -join ';');%PATH%`"",
    "set `"INCLUDE=$V120Include;%INCLUDE%`"",
    "set `"LIB=$($v120LibPaths -join ';');%LIB%`"",
    "set `"CXX=$compiler`"",
    "set `"CXX_x86_64_pc_windows_msvc=$compiler`"",
    "set `"CXXFLAGS=/D_ALLOW_MSC_VER_MISMATCH /fp:fast /GL`"",
    "set `"RUSTFLAGS=-C link-arg=/LTCG`"",
    "cd /d `"$crateRoot`"",
    "cargo test --release --locked",
    "if errorlevel 1 exit /b %errorlevel%",
    "cargo build --release --locked"
)
[IO.File]::WriteAllLines($buildCommand, $commandLines, [Text.UTF8Encoding]::new($false))
try {
    & cmd.exe /d /c $buildCommand
    $cargoExitCode = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $buildCommand -Force -ErrorAction SilentlyContinue
}
if ($cargoExitCode -ne 0) {
    throw "VS2013 RTM LTCG build failed with exit code $cargoExitCode"
}

New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item `
    -LiteralPath (Join-Path $crateRoot "target\release\mmd_physics_solver.dll") `
    -Destination (Join-Path $destination "mmd_physics_solver.dll") `
    -Force

Get-FileHash (Join-Path $destination "mmd_physics_solver.dll") -Algorithm SHA256
