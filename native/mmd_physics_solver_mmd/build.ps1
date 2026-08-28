param(
    [string]$Vc10Sp1Root = $env:MMD_VC10_SP1_ROOT,
    [string]$Vc10Root = $env:MMD_VC10_ROOT,
    [string]$WinSdk71Root = $env:MMD_WINSDK71_ROOT,
    [string]$VsDevCmd = $env:MMD_VSDEVCMD
)

$ErrorActionPreference = "Stop"

$crateRoot = $PSScriptRoot
$projectRoot = Split-Path (Split-Path $crateRoot -Parent) -Parent
$destination = Join-Path $projectRoot "mmd_station\physics_preview\bin\win_amd64"

if (-not $Vc10Sp1Root) {
    $Vc10Sp1Root = Join-Path $env:TEMP "vc10sp1-portable\Program Files(64)\Microsoft Visual Studio 10.0"
}
if (-not $Vc10Root) {
    $Vc10Root = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio 10.0"
}
if (-not $WinSdk71Root) {
    $WinSdk71Root = Join-Path $env:TEMP "spx-winsdk71-portable\Program Files\Microsoft SDKs\Windows\v7.1"
}
$vcRoot = Join-Path $Vc10Sp1Root "VC"
$sdkRoot = $WinSdk71Root
$compilerBin = Join-Path $vcRoot "bin\amd64"
$compiler = Join-Path $compilerBin "cl.exe"
$linker = Join-Path $compilerBin "link.exe"
$includePaths = @((Join-Path $Vc10Root "VC\include"), (Join-Path $sdkRoot "Include"))
$libraryPaths = @((Join-Path $vcRoot "lib\amd64"), (Join-Path $sdkRoot "lib\x64"))
$vcLibDirectory = $libraryPaths[0]
$vcLibcmt = Join-Path $vcLibDirectory "libcmt.lib"

foreach ($requiredPath in @($compiler, $linker, $vcLibcmt) + $includePaths + $libraryPaths) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "VC10 SP1 build input is missing: $requiredPath"
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
    throw "A current Visual Studio VsDevCmd.bat is required for Rust and Windows SDK libraries"
}
$visualStudioRoot = Split-Path (Split-Path (Split-Path $VsDevCmd -Parent) -Parent) -Parent
$modernLinker = Get-ChildItem (Join-Path $visualStudioRoot "VC\Tools\MSVC") -Directory |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName "bin\Hostx64\x64\link.exe" } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
if (-not $modernLinker) {
    throw "Current MSVC x64 linker was not found under $visualStudioRoot"
}
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

if ((Get-ToolBanner $compiler) -notmatch "Version 16\.00\.40219\.01") {
    throw "MMD-compatible builds require VC10 SP1 cl.exe 16.00.40219.01"
}
if ((Get-ToolBanner $linker) -notmatch "Version 10\.00\.40219\.01") {
    throw "MMD-compatible builds require VC10 SP1 link.exe 10.00.40219.01"
}

$buildCommand = Join-Path $env:TEMP ("mmd-vc10sp1-{0}.cmd" -f ([guid]::NewGuid().ToString("N")))
$renamedLibDirectory = Join-Path $env:TEMP ("mmd-vc10sp1-libcmt-{0}" -f ([guid]::NewGuid().ToString("N")))
New-Item -ItemType Directory -Force -Path $renamedLibDirectory | Out-Null
$renamedLibcmt = Join-Path $renamedLibDirectory "mmd_vc10sp1_libcmt.lib"
Copy-Item -LiteralPath $vcLibcmt -Destination $renamedLibcmt -Force
$commandLines = @(
    "@echo off",
    "call `"$VsDevCmd`" -arch=x64 -host_arch=x64 >nul",
    "set `"CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER=$modernLinker`"",
    "set `"PATH=$compilerBin;%PATH%`"",
    "set `"CXX=$compiler`"",
    "set `"CXX_x86_64_pc_windows_msvc=$compiler`"",
    "set `"MMD_LEGACY_INCLUDE=$($includePaths -join ';')`"",
    "set `"MMD_LEGACY_LIBCMT=$renamedLibcmt`"",
    "set `"LIB=$renamedLibDirectory;%LIB%;$($libraryPaths -join ';')`"",
    "set `"CXXFLAGS=/D_ALLOW_MSC_VER_MISMATCH /fp:fast /Ox`"",
    "set `"RUSTFLAGS=-C link-arg=/LTCG`"",
    "cd /d `"$crateRoot`"",
    "cargo clean",
    "cargo test --release",
    "if errorlevel 1 exit /b %errorlevel%",
    "cargo build --release"
)
[IO.File]::WriteAllLines($buildCommand, $commandLines, [Text.UTF8Encoding]::new($false))
try {
    & cmd.exe /d /c $buildCommand
    $cargoExitCode = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $buildCommand -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $renamedLibDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
if ($cargoExitCode -ne 0) {
    throw "VC10 SP1 build failed with exit code $cargoExitCode"
}

New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item `
    -LiteralPath (Join-Path $crateRoot "target\release\mmd_physics_solver_mmd.dll") `
    -Destination (Join-Path $destination "mmd_physics_solver_mmd.dll") `
    -Force

Get-FileHash (Join-Path $destination "mmd_physics_solver_mmd.dll") -Algorithm SHA256
