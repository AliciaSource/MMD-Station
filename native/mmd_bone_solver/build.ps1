param([string]$V90Root = $env:MMD_V90_ROOT)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$project = Split-Path (Split-Path $root -Parent) -Parent
$dest = Join-Path $project "mmd_skirt_proxy_creator\mmd_ik_runtime\bin\win_amd64"
if (-not $V90Root) { $V90Root = Join-Path $env:TEMP "vcpy27-portable\Microsoft\Visual C++ for Python\9.0" }
$vc = Join-Path $V90Root "VC"
$sdk = Join-Path $V90Root "WinSDK"
$cl = Join-Path $vc "bin\amd64\cl.exe"
$link = Join-Path $vc "bin\amd64\link.exe"
$inc = @((Join-Path $vc "include"), (Join-Path $sdk "include"))
$libs = @((Join-Path $vc "lib\amd64"), (Join-Path $sdk "lib\x64"))
foreach ($p in @($cl, $link) + $inc + $libs) { if (-not (Test-Path -LiteralPath $p)) { throw "VC9 input missing: $p" } }
$build = Join-Path $root "build"
New-Item -ItemType Directory -Force $build, $dest | Out-Null
& $cl /nologo /c /O2 /GL /fp:fast /EHsc /MT /D_CRT_SECURE_NO_WARNINGS "/I$($inc[0])" "/I$($inc[1])" `
    /Fo"$build\mmd_bone_solver.obj" "$root\mmd_bone_solver.cpp"
if ($LASTEXITCODE) { throw "cl failed: $LASTEXITCODE" }
& $link /nologo /DLL /LTCG /OUT:"$build\mmd_bone_solver.dll" "$build\mmd_bone_solver.obj" `
    "/LIBPATH:$($libs[0])" "/LIBPATH:$($libs[1])" kernel32.lib user32.lib
if ($LASTEXITCODE) { throw "link failed: $LASTEXITCODE" }
Copy-Item -LiteralPath "$build\mmd_bone_solver.dll" -Destination "$dest\mmd_bone_solver.dll" -Force
Get-FileHash "$dest\mmd_bone_solver.dll" -Algorithm SHA256
