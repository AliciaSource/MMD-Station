param(
    [string]$V120Bin = $env:MMD_V120_BIN,
    [string]$V120Include = $env:MMD_V120_INCLUDE,
    [string]$V120Lib = $env:MMD_V120_LIB,
    [string]$V120CoreLib = $env:MMD_V120_CORE_LIB,
    [string]$V120Ide = $env:MMD_V120_IDE,
    [string]$VsDevCmd = $env:MMD_VSDEVCMD
)

$ErrorActionPreference = "Stop"

$crateRoot = $PSScriptRoot
$projectRoot = Split-Path (Split-Path $crateRoot -Parent) -Parent
$destination = Join-Path $projectRoot "mmd_skirt_proxy_creator\physics_preview\bin\win_amd64"

$visualStudio120 = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio 12.0"
$cachedToolchainRoot = Join-Path $env:TEMP "v120_toolchain"
$cachedCompilerRoot = Join-Path $cachedToolchainRoot "vc_compilerCore86\Program Files\Microsoft Visual Studio 12.0"
$cachedLibraryRoot = Join-Path $cachedToolchainRoot "vc_librarycore86\Program Files\Microsoft Visual Studio 12.0"
$cachedDesktopLibraryRoot = Join-Path $cachedToolchainRoot "vc_LibraryDesktopX64\Program Files\Microsoft Visual Studio 12.0"
$toolchainLayouts = @(
    [pscustomobject]@{
        Bin = Join-Path $visualStudio120 "VC\bin\x86_amd64"
        Include = Join-Path $visualStudio120 "VC\include"
        Lib = Join-Path $visualStudio120 "VC\lib\amd64"
        CoreLib = Join-Path $visualStudio120 "VC\lib\amd64"
        Ide = Join-Path $visualStudio120 "Common7\IDE"
    },
    [pscustomobject]@{
        Bin = Join-Path $cachedCompilerRoot "VC\bin\x86_amd64"
        Include = Join-Path $cachedLibraryRoot "VC\include"
        Lib = Join-Path $cachedDesktopLibraryRoot "VC\lib\amd64"
        CoreLib = Join-Path $cachedLibraryRoot "VC\lib\amd64"
        Ide = Join-Path $cachedCompilerRoot "Common7\IDE"
    }
)

$toolchainLayout = $null
if ($V120Bin) {
    $requestedBin = [IO.Path]::GetFullPath($V120Bin).TrimEnd("\", "/")
    $toolchainLayout = $toolchainLayouts | Where-Object {
        [IO.Path]::GetFullPath($_.Bin).TrimEnd("\", "/").Equals(
            $requestedBin,
            [StringComparison]::OrdinalIgnoreCase
        )
    } | Select-Object -First 1
} else {
    $toolchainLayout = $toolchainLayouts | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.Bin "cl.exe")) -and
        (Test-Path -LiteralPath (Join-Path $_.Bin "link.exe"))
    } | Select-Object -First 1
}
if ($toolchainLayout) {
    if (-not $V120Bin) { $V120Bin = $toolchainLayout.Bin }
    if (-not $V120Include) { $V120Include = $toolchainLayout.Include }
    if (-not $V120Lib) { $V120Lib = $toolchainLayout.Lib }
    if (-not $V120CoreLib) { $V120CoreLib = $toolchainLayout.CoreLib }
    if (-not $V120Ide) { $V120Ide = $toolchainLayout.Ide }
}

foreach ($requiredParameter in @("V120Bin", "V120Include", "V120Lib")) {
    if (-not (Get-Variable -Name $requiredParameter -ValueOnly)) {
        throw "$requiredParameter is required because no complete VS2013 RTM toolchain layout was found"
    }
}

foreach ($directoryPath in @($V120Bin, $V120Include)) {
    if (-not (Test-Path -LiteralPath $directoryPath -PathType Container)) {
        throw "VS2013 RTM build directory is missing: $directoryPath"
    }
}
$V120Bin = (Resolve-Path -LiteralPath $V120Bin).Path
$V120Include = (Resolve-Path -LiteralPath $V120Include).Path
$compiler = Join-Path $V120Bin "cl.exe"
$linker = Join-Path $V120Bin "link.exe"
foreach ($requiredPath in @($compiler, $linker, $V120Include)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "VS2013 RTM build input is missing: $requiredPath"
    }
}
$v120LibPaths = @($V120Lib -split ";" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($v120LibPaths.Count -eq 0) {
    throw "MMD_V120_LIB must contain at least one x64 library directory"
}
foreach ($libraryPath in $v120LibPaths) {
    if (-not (Test-Path -LiteralPath $libraryPath -PathType Container)) {
        throw "VS2013 RTM library directory is missing: $libraryPath"
    }
}
$v120LibPaths = @($v120LibPaths | ForEach-Object { (Resolve-Path -LiteralPath $_).Path })
if (-not $V120CoreLib) {
    $coreLibraryCandidates = @($v120LibPaths | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_ "msvcprt.lib")) -and
        (Test-Path -LiteralPath (Join-Path $_ "msvcrt.lib"))
    })
    if ($coreLibraryCandidates.Count -eq 1) {
        $V120CoreLib = $coreLibraryCandidates[0]
    }
}
if (-not $V120CoreLib) {
    throw "VS2013 x64 core libraries are missing. Pass -V120CoreLib or set MMD_V120_CORE_LIB to the directory containing msvcprt.lib and msvcrt.lib"
}
if (-not (Test-Path -LiteralPath $V120CoreLib -PathType Container)) {
    throw "VS2013 x64 core library directory is missing: $V120CoreLib"
}
$V120CoreLib = (Resolve-Path -LiteralPath $V120CoreLib).Path
$msvcprtLibrary = Join-Path $V120CoreLib "msvcprt.lib"
$msvcrtLibrary = Join-Path $V120CoreLib "msvcrt.lib"
foreach ($coreLibrary in @($msvcprtLibrary, $msvcrtLibrary)) {
    if (-not (Test-Path -LiteralPath $coreLibrary -PathType Leaf)) {
        throw "VS2013 x64 core library is missing: $coreLibrary"
    }
}
if ($V120Ide) {
    if (-not (Test-Path -LiteralPath $V120Ide -PathType Container)) {
        throw "VS2013 RTM IDE directory is missing: $V120Ide"
    }
    $V120Ide = (Resolve-Path -LiteralPath $V120Ide).Path
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
    "if errorlevel 1 exit /b %errorlevel%",
    "set `"MMD_MODERN_LINKER=`"",
    "for /f `"delims=`" %%I in ('where link.exe') do if not defined MMD_MODERN_LINKER set `"MMD_MODERN_LINKER=%%I`"",
    "if not defined MMD_MODERN_LINKER exit /b 9009",
    "set `"CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER=%MMD_MODERN_LINKER%`"",
    "set `"CARGO_ENCODED_RUSTFLAGS=`"",
    "set `"RUSTFLAGS=`"",
    "set `"CARGO_TARGET_DIR=$crateRoot\target`"",
    "set `"PATH=$($pathParts -join ';');%PATH%`"",
    "echo PMX_BUILD_MODERN_LINKER=%MMD_MODERN_LINKER%",
    "echo PMX_BUILD_V120_COMPILER=$compiler",
    "echo PMX_BUILD_V120_FINAL_LINKER=$linker",
    "set `"INCLUDE=$V120Include;%INCLUDE%`"",
    "set `"LIB=$V120CoreLib;$($v120LibPaths -join ';');%LIB%`"",
    "set `"CXX=$compiler`"",
    "set `"CXX_x86_64_pc_windows_msvc=$compiler`"",
    "set `"CXXFLAGS=/D_ALLOW_MSC_VER_MISMATCH /fp:fast`"",
    "cd /d `"$crateRoot`"",
    "cargo clean --release -p mmd-anim-physics-bullet",
    "if errorlevel 1 exit /b %errorlevel%",
    "cargo test --release --locked",
    "if errorlevel 1 exit /b %errorlevel%",
    "cargo clean --release -p mmd-anim-physics-bullet",
    "if errorlevel 1 exit /b %errorlevel%",
    "set `"CXXFLAGS=/D_ALLOW_MSC_VER_MISMATCH /fp:fast /GL`"",
    "cargo rustc --release --locked --lib -- -C `"linker=$linker`" -C `"link-arg=/LTCG`" -C `"link-arg=$msvcprtLibrary`" -C `"link-arg=$msvcrtLibrary`""
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
