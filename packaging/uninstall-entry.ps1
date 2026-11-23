# ゆらぎのアンインストールの入口。手順は DESIGN「インストール・更新・アンインストール」
#
# リリースには uninstall.ps1 の名前で、setup.ps1 と並べて置く。README の 1 行で取得して実行する。
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1 [-RemoveData] [-Yes]
#
# 入っている版 (HKCU の Tag) を見つけて、その版に入っている本体 (packaging\uninstall.ps1) を呼ぶ。
# 本体はその版の置き場所を知っているので、消すのは入れた版自身に任せる。本体は Tag を
# 登録解除のあとで消すので、途中で止まったアンインストールもここで見つかる。Tag が無ければ
# 「インストールされていません」(-RemoveData なら、残っている利用者のデータだけを消す)。
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
    # README の「全部消す場合」の 1 行は、先にアンインストールしたあとでも利用者のデータを消す
    # (本体の -RemoveData と同じく、場所と大きさを見せて確かめてから)。
    $userData = Join-Path $env:USERPROFILE ".yuragi-ime"
    if ($RemoveData -and (Test-Path -LiteralPath $userData)) {
        $size = (Get-ChildItem -LiteralPath $userData -Recurse -Force -File | Measure-Object -Property Length -Sum).Sum
        Write-Host "学習データ・登録した単語・設定を削除します: $userData ($([math]::Round($size / 1KB)) KB)"
        if (-not $Yes) {
            $ans = Read-Host "削除すると元に戻せません。続行しますか? [y/N]"
            if ($ans -notmatch "^[Yy]") { Write-Host "キャンセルしました。何も変更していません。"; exit 1 }
        }
        Remove-Item -LiteralPath $userData -Recurse -Force
        Write-Host "  削除: $userData"
    }
    exit 0
}

Write-Host "ゆらぎ $tag アンインストール"
$argv = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $body)
if ($RemoveData) { $argv += "-RemoveData" }
if ($Yes) { $argv += "-Yes" }
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" @argv
exit $LASTEXITCODE
