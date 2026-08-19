param(
    [string]$V90Root = $env:MMD_V90_ROOT
)

$ErrorActionPreference = "Stop"

if (-not $V90Root) {
    $V90Root = Join-Path $env:TEMP "vcpy27-portable\Microsoft\Visual C++ for Python\9.0"
}

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$bulletSource = Join-Path $repoRoot "native\mmd_physics_solver_mmd\vendor\mmd-anim-physics-bullet\vendor\bullet-2.75\src"
$source = Join-Path $PSScriptRoot "mmd_raw_trace_hook_generic.cpp"
$output = Join-Path $PSScriptRoot "bin\mmd_raw_trace_hook_generic.dll"
$compiler = Join-Path $V90Root "VC\bin\amd64\cl.exe"
$linker = Join-Path $V90Root "VC\bin\amd64\link.exe"
$vcInclude = Join-Path $V90Root "VC\include"
$sdkInclude = Join-Path $V90Root "WinSDK\include"
$vcLib = Join-Path $V90Root "VC\lib\amd64"
$sdkLib = Join-Path $V90Root "WinSDK\lib\x64"
$object = Join-Path $env:TEMP ("mmd-raw-trace-hook-{0}.obj" -f ([guid]::NewGuid().ToString("N")))

foreach ($path in @($compiler, $linker, $source, $bulletSource, $vcInclude, $sdkInclude, $vcLib, $sdkLib)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Raw trace hook build input is missing: $path"
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path $output -Parent) | Out-Null
try {
    & $compiler /nologo /O2 /EHsc /MT "/I$bulletSource" "/I$vcInclude" "/I$sdkInclude" /c $source "/Fo$object"
    if ($LASTEXITCODE -ne 0) {
        throw "Raw trace hook compilation failed with exit code $LASTEXITCODE"
    }
    & $linker /nologo /dll "/out:$output" $object kernel32.lib "/libpath:$sdkLib" "/libpath:$vcLib"
    if ($LASTEXITCODE -ne 0) {
        throw "Raw trace hook link failed with exit code $LASTEXITCODE"
    }
} finally {
    Remove-Item -LiteralPath $object -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath ([IO.Path]::ChangeExtension($output, ".lib")) -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath ([IO.Path]::ChangeExtension($output, ".exp")) -Force -ErrorAction SilentlyContinue
}

Get-FileHash $output -Algorithm SHA256
