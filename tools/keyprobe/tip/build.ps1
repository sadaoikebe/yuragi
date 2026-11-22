# キーの確認用の TIP（keyprobe_tip.dll、64 ビット）をビルドする。出力は tools\keyprobe\out\tip。
#
#   powershell -ExecutionPolicy Bypass -File .\tools\keyprobe\tip\build.ps1
$ErrorActionPreference = 'Stop'
$Repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))

if (-not $env:LIB) {
    $vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    $vsPath = $null
    if (Test-Path -LiteralPath $vswhere) {
        $vsPath = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    }
    if (-not $vsPath) { $vsPath = 'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools' }
    $vcvars = Join-Path $vsPath 'VC\Auxiliary\Build\vcvars64.bat'
    if (-not (Test-Path -LiteralPath $vcvars -PathType Leaf)) { throw "vcvars64.bat が見つかりません。" }
    foreach ($line in (& cmd.exe /d /c "`"$vcvars`" >nul && set")) {
        if ($line -match '^([^=]+)=(.*)$') { Set-Item -LiteralPath ('env:' + $Matches[1]) -Value $Matches[2] }
    }
}
$build = Join-Path $Repo 'build\keyprobe-tip'
& cmake -S $PSScriptRoot -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { throw 'CMake の構成に失敗しました。' }
& cmake --build $build
if ($LASTEXITCODE -ne 0) { throw 'ビルドに失敗しました。' }
Write-Host "ビルド OK: $(Join-Path $Repo 'tools\keyprobe\out\tip\keyprobe_tip.dll')"
