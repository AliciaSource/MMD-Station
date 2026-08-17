param(
    [string]$V90Root = $env:MMD_V90_ROOT,
    [string]$VsDevCmd = $env:MMD_VSDEVCMD
)

$ErrorActionPreference = "Stop"

$crateRoot = $PSScriptRoot
$projectRoot = Split-Path (Split-Path $crateRoot -Parent) -Parent
$destination = Join-Path $projectRoot "mmd_skirt_proxy_creator\physics_preview\bin\win_amd64"

if (-not $V90Root) {
    $V90Root = Join-Path $env:TEMP "vcpy27-portable\Microsoft\Visual C++ for Python\9.0"
}
$vcRoot = Join-Path $V90Root "VC"
$sdkRoot = Join-Path $V90Root "WinSDK"
$compilerBin = Join-Path $vcRoot "bin\amd64"
$compiler = Join-Path $compilerBin "cl.exe"
$linker = Join-Path $compilerBin "link.exe"
$includePaths = @((Join-Path $vcRoot "include"), (Join-Path $sdkRoot "include"))
$libraryPaths = @((Join-Path $vcRoot "lib\amd64"), (Join-Path $sdkRoot "lib\x64"))
$vc9Libcmt = Join-Path $libraryPaths[0] "libcmt.lib"

foreach ($requiredPath in @($compiler, $linker, $vc9Libcmt) + $includePaths + $libraryPaths) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "VC9 build input is missing: $requiredPath"
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

if ((Get-ToolBanner $compiler) -notmatch "Version 15\.00\.30729\.01") {
    throw "MMD-compatible builds require VC9 SP1 cl.exe 15.00.30729.01"
}
if ((Get-ToolBanner $linker) -notmatch "Version 9\.00\.30729\.01") {
    throw "MMD-compatible builds require VC9 SP1 link.exe 9.00.30729.01"
}

$buildCommand = Join-Path $env:TEMP ("mmd-v90-ltcg-{0}.cmd" -f ([guid]::NewGuid().ToString("N")))
$renamedLibDirectory = Join-Path $env:TEMP ("mmd-v90-libcmt-{0}" -f ([guid]::NewGuid().ToString("N")))
New-Item -ItemType Directory -Force -Path $renamedLibDirectory | Out-Null
$renamedLibcmt = Join-Path $renamedLibDirectory "mmd_vc9_libcmt.lib"
Copy-Item -LiteralPath $vc9Libcmt -Destination $renamedLibcmt -Force
$commandLines = @(
    "@echo off",
    "call `"$VsDevCmd`" -arch=x64 -host_arch=x64 >nul",
    "set `"CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER=$modernLinker`"",
    "set `"CXX=$compiler`"",
    "set `"CXX_x86_64_pc_windows_msvc=$compiler`"",
    "set `"MMD_V90_INCLUDE=$($includePaths -join ';')`"",
    "set `"MMD_V90_LIBCMT=$renamedLibcmt`"",
    "set `"CXXFLAGS=/D_ALLOW_MSC_VER_MISMATCH /fp:fast`"",
    "cd /d `"$crateRoot`"",
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
    throw "VC9 SP1 LTCG build failed with exit code $cargoExitCode"
}

New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item `
    -LiteralPath (Join-Path $crateRoot "target\release\mmd_physics_solver_mmd.dll") `
    -Destination (Join-Path $destination "mmd_physics_solver_mmd.dll") `
    -Force

Get-FileHash (Join-Path $destination "mmd_physics_solver_mmd.dll") -Algorithm SHA256
