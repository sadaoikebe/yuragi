# 開発用: TIP とブローカーのビルドと試験だけ (DESIGN「開発時」)。リリースのワークフローもこれを使う。
# 管理者権限は要らない。登録は dev-register.ps1 で別に行う。
#
#   powershell -ExecutionPolicy Bypass -File .\src\tip\dev-build.ps1 [-Tag dev]
#
# 出力: dist\yuragi_tip.dll・dist\yuragi_tip32.dll (32 ビットのアプリ用) と dist\yuragi-broker.exe
# (Release、タグを埋め込む)。
param([string]$Tag = "dev")
$ErrorActionPreference = 'Stop'
$Repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))

function Find-Vcvars([string]$name) {
    $vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    $vsPath = $null
    if (Test-Path -LiteralPath $vswhere) {
        $vsPath = & $vswhere -latest -products '*' `
            -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -ne 0) { $vsPath = $null }
    }
    if (-not $vsPath -or -not (Test-Path -LiteralPath (Join-Path $vsPath "VC\Auxiliary\Build\$name") -PathType Leaf)) {
        $vsPath = 'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools'
    }
    $vcvars = Join-Path $vsPath "VC\Auxiliary\Build\$name"
    if (-not (Test-Path -LiteralPath $vcvars -PathType Leaf)) {
        throw "$name が見つかりません。Visual Studio の C++ ビルドツールをインストールしてください。"
    }
    return $vcvars
}

# Visual Studio の開発者環境を、このプロセスに読み込む。
function Use-DevEnvironment([string]$name) {
    $vcvars = Find-Vcvars $name
    $environment = & cmd.exe /d /c "`"$vcvars`" >nul && set"
    if ($LASTEXITCODE -ne 0) { throw "$name による開発者環境の読み込みに失敗しました。" }
    foreach ($line in $environment) {
        if ($line -match '^([^=]+)=(.*)$') { Set-Item -LiteralPath ('env:' + $Matches[1]) -Value $Matches[2] }
    }
    if (-not $env:LIB) { throw '開発者環境の読み込みに失敗しました（LIB が未設定です）。' }
}

function Build([string]$part, [string]$buildName) {
    $source = Join-Path $Repo "src\$part"
    $build = Join-Path $Repo "build\$buildName"
    & cmake -S $source -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release "-DYURAGI_TAG=$Tag"
    if ($LASTEXITCODE -ne 0) { throw "${buildName}: CMake の構成に失敗しました。" }
    & cmake --build $build
    if ($LASTEXITCODE -ne 0) { throw "${buildName}: ビルドに失敗しました。" }
    & ctest --test-dir $build --output-on-failure
    if ($LASTEXITCODE -ne 0) { throw "${buildName}: CTest に失敗しました。" }
}

# 64 ビット (未読み込みのときだけ読み込む)。
if (-not $env:LIB) { Use-DevEnvironment 'vcvars64.bat' }
Build 'tip' 'tip-release'
Build 'broker' 'broker-release'
# 32 ビットのアプリが読み込む TIP (DESIGN「32 ビットのアプリ」)。最後に x86 の環境へ切り替える。
Use-DevEnvironment 'vcvars32.bat'
Build 'tip' 'tip32-release'
Write-Host "ビルド OK (タグ $Tag): $(Join-Path $Repo 'dist')"
