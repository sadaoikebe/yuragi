# ゆらぎのアンインストールの入口 (docs/INSTALL.md)
#
# リリースには uninstall.ps1 の名前で、setup.ps1 と並べて置く。README の 1 行で取得して実行する。
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1 [-RemoveData] [-Yes]
#
# 入っている版を見つけて、その版に入っている本体 (packaging\uninstall.ps1) を呼ぶ。
# 本体はその版の置き場所を知っているので、消すのは入れた版自身に任せる。
#   1 HKCU の Tag (この利用者に入っている版)
#   2 Tag が無ければ、Program Files に登録が残っている版。本体は Tag を最初に消すので、
#     途中で止まったアンインストールのやり直しはここで見つかる
#   3 登録も無ければ、%LOCALAPPDATA%\yuragi-ime\versions に本体が残っている版 (登録解除の
#     あとで止まったアンインストール。本体は %LOCALAPPDATA%\yuragi-ime を最後に消す)
# 引数はそのまま本体に渡す (-RemoveData を付けたときだけ利用者のデータも消す)。

param(
    [switch]$RemoveData,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Clsid = "{A7C4E201-0B3A-4F11-9E61-0C1A0B7E0A01}"
$InprocKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$Clsid\InprocServer32"
$ProgramRoot = Join-Path $env:ProgramFiles "yuragi-ime"

$tag = (Get-ItemProperty -LiteralPath "HKCU:\Software\yuragi-ime" -ErrorAction SilentlyContinue).Tag
if (-not $tag) {
    $dll = (Get-ItemProperty -LiteralPath $InprocKey -ErrorAction SilentlyContinue).'(default)'
    if ($dll -and (Split-Path (Split-Path $dll)) -eq $ProgramRoot) { $tag = Split-Path (Split-Path $dll) -Leaf }
}
$resumed = $false
if (-not $tag) {
    $versions = Join-Path $env:LOCALAPPDATA "yuragi-ime\versions"
    if (Test-Path -LiteralPath $versions) {
        $tag = Get-ChildItem -LiteralPath $versions -Directory |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "app\packaging\uninstall.ps1") } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty Name
        $resumed = [bool]$tag
    }
}
if ($tag -eq "dev") {
    Write-Host "エラー: 開発用の登録 (dev) です。リポジトリの packaging\uninstall.ps1 で削除してください。" -ForegroundColor Red
    exit 1
}
$body = Join-Path $env:LOCALAPPDATA "yuragi-ime\versions\$tag\app\packaging\uninstall.ps1"
if (-not $tag -or -not (Test-Path -LiteralPath $body)) {
    Write-Host "ゆらぎはインストールされていません。"
    exit 0
}

if ($resumed) { Write-Host "ゆらぎ $tag アンインストール (前回の続き)" } else { Write-Host "ゆらぎ $tag アンインストール" }
$argv = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $body)
if ($RemoveData) { $argv += "-RemoveData" }
if ($Yes) { $argv += "-Yes" }
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" @argv
exit $LASTEXITCODE
