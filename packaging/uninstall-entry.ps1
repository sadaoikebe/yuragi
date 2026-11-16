# ゆらぎのアンインストールの入口 (docs/INSTALL.md)
#
# リリースには uninstall.ps1 の名前で、setup.ps1 と並べて置く。README の 1 行で取得して実行する。
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1 [-RemoveData] [-Yes]
#
# 入っている版 (HKCU の Tag) を見つけて、その版に入っている本体 (packaging\uninstall.ps1) を呼ぶ。
# 本体はその版の置き場所を知っているので、消すのは入れた版自身に任せる。本体は Tag を
# 登録解除のあとで消すので、途中で止まったアンインストールもここで見つかる。Tag が無ければ
# 「インストールされていません」。
# 引数はそのまま本体に渡す (-RemoveData を付けたときだけ利用者のデータも消す)。

param(
    [switch]$RemoveData,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"

$tag = (Get-ItemProperty -LiteralPath "HKCU:\Software\yuragi-ime" -ErrorAction SilentlyContinue).Tag
if ($tag -eq "dev") {
    Write-Host "エラー: 開発用の登録 (dev) です。リポジトリの packaging\uninstall.ps1 で削除してください。" -ForegroundColor Red
    exit 1
}
$body = Join-Path $env:LOCALAPPDATA "yuragi-ime\versions\$tag\app\packaging\uninstall.ps1"
if (-not $tag -or -not (Test-Path -LiteralPath $body)) {
    Write-Host "ゆらぎはインストールされていません。"
    exit 0
}

Write-Host "ゆらぎ $tag アンインストール"
$argv = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $body)
if ($RemoveData) { $argv += "-RemoveData" }
if ($Yes) { $argv += "-Yes" }
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" @argv
exit $LASTEXITCODE
