# ゆらぎのアンインストール。手順は DESIGN「インストール・更新・アンインストール」
#
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1 [-RemoveData] [-Yes]
#
# 学習した内容・登録した単語・設定 (%USERPROFILE%\.yuragi-ime) は、-RemoveData を付けたときだけ、
# 場所と大きさを見せて確かめてから消す (DESIGN「守ること」7)。

param(
    [switch]$RemoveData,
    [switch]$Yes
)

if ($PSVersionTable.PSEdition -eq "Core") {
    $relaunch = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if ($RemoveData) { $relaunch += "-RemoveData" }
    if ($Yes) { $relaunch += "-Yes" }
    & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" @relaunch
    exit $LASTEXITCODE
}

$ErrorActionPreference = "Stop"
$Local = Join-Path $env:LOCALAPPDATA "yuragi-ime"
$UserData = Join-Path $env:USERPROFILE ".yuragi-ime"
$Clsid = "{A7C4E201-0B3A-4F11-9E61-0C1A0B7E0A01}"
$Layout = "0x0411:$Clsid{A7C4E202-0B3A-4F11-9E61-0C1A0B7E0A01}"
$ProductKey = "HKCU:\Software\yuragi-ime"
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
$InprocKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$Clsid\InprocServer32"
Set-Location $env:USERPROFILE   # 自分を含むフォルダを消すので外に出る

# 管理者権限で動かすのは、インストール時に Program Files に置いた elevated.ps1。
# 登録されている DLL と同じフォルダのものを使う。
$elevatedPath = $null
$registeredDll = (Get-ItemProperty -LiteralPath $InprocKey -ErrorAction SilentlyContinue).'(default)'
if ($registeredDll) {
    $elevatedPath = Join-Path (Split-Path $registeredDll) "elevated.ps1"
    if (-not (Test-Path -LiteralPath $elevatedPath)) {
        Write-Host "エラー: $elevatedPath がありません。インストールの 1 行以外で入れた版は、このスクリプトでは削除できません。" -ForegroundColor Red
        exit 1
    }
}

# 管理者用スクリプトの呼び出しと引数を 1 つのコマンドにして -EncodedCommand 用に符号化する
# (空白・引用符・日本語を含むパスもそのまま届く)。パスと引数は単一引用符で囲む。PowerShell は ' のほか
# U+2018・U+2019・U+201A・U+201B も単一引用符として読むので、5 種類とも二重にする。
function New-ElevatedCommand([string]$scriptPath, [string[]]$arguments) {
    # パスは - で始まらないので、引数の値と同じく囲まれる。
    $quoted = @(@($scriptPath) + $arguments | ForEach-Object { if ($_ -like "-*") { $_ } else {
        "'" + [Management.Automation.Language.CodeGeneration]::EscapeSingleQuotedStringContent($_) + "'" } })
    $command = "& " + ($quoted -join " ")
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}
function Say([string]$msg) { Write-Host $msg }
function Fail([string]$msg) { Write-Host "エラー: $msg" -ForegroundColor Red; exit 1 }

# データの削除も指定された場合は、アンインストールを始める前に確認する。
if ($RemoveData -and (Test-Path -LiteralPath $UserData)) {
    $size = (Get-ChildItem -LiteralPath $UserData -Recurse -Force -File | Measure-Object -Property Length -Sum).Sum
    Say "学習データ・登録した単語・設定も削除します: $UserData ($([math]::Round($size / 1KB)) KB)"
    if (-not $Yes) {
        $ans = Read-Host "削除すると元に戻せません。続行しますか? [y/N]"
        if ($ans -notmatch "^[Yy]") { Fail "キャンセルしました。何も変更していません。" }
    }
}

# この利用者の自動起動と入力方法の一覧からゆらぎを外す。
Say "== 自動起動と入力方法の一覧から削除"
Remove-ItemProperty -LiteralPath $RunKey -Name "yuragi-ime" -ErrorAction SilentlyContinue
Add-Type -Namespace YuragiUninstall -Name Input -MemberDefinition @'
[DllImport("input.dll", CharSet = CharSet.Unicode)]
public static extern bool InstallLayoutOrTip(string profile, uint flags);
'@
# ILOT_UNINSTALL
if (-not [YuragiUninstall.Input]::InstallLayoutOrTip($Layout, 1)) { Say "  入力方法の一覧: 未登録" }
Say "  OK"

# 実行ファイルを削除できるよう、このセッションのブローカーを止める。
Say "== ブローカーの終了"
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$session = (Get-Process -Id $PID).SessionId
$pipe = New-Object System.IO.Pipes.NamedPipeClientStream(".", "yuragi-ime-$sid-$session", [IO.Pipes.PipeDirection]::InOut)
try {
    $pipe.Connect(1000)
    $writer = New-Object IO.StreamWriter($pipe, $Utf8NoBom)
    $writer.AutoFlush = $true
    $writer.NewLine = "`n"
    $writer.WriteLine('{"op":"hello","proto":1}')
    # 返事を 1 行読んでから quit を送る (読まずに閉じると、ブローカーは返事の書き込みに失敗して
    # 接続を閉じ、後ろの quit が届かないことがある)。
    $reader = New-Object IO.StreamReader($pipe, $Utf8NoBom)
    [void]$reader.ReadLineAsync().Wait(2000)
    $writer.WriteLine('{"op":"quit"}')
} catch { } finally { $pipe.Dispose() }
foreach ($b in @(Get-Process -Name "yuragi-broker" -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session })) {
    if (-not $b.WaitForExit(15000)) {
        Stop-Process -Id $b.Id -Force
        if (-not $b.WaitForExit(5000)) { Fail "ブローカー (PID $($b.Id)) を終了できませんでした。" }
    }
}
# インストール先から動いているもの (設定ウィンドウなど) も終わらせる。動いたままだと消し切れない。
$prefix = "$Local\"
foreach ($p in @(Get-Process | Where-Object { $_.SessionId -eq $session -and $_.Path -and
        $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    [void]$p.WaitForExit(5000)
}
Say "  OK"

# 管理者権限で DLL の登録を解除し、プログラムのファイルを削除する。
if ($elevatedPath) {
Say "== Windows からの登録解除とプログラムの削除 (管理者権限の確認が出ます)"
$resultFile = Join-Path $env:TEMP ("yuragi-elevated-" + [Guid]::NewGuid().ToString("N") + ".json")
$encoded = New-ElevatedCommand $elevatedPath @("-Action", "uninstall", "-ResultFile", $resultFile)
try {
    $p = Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -Wait -PassThru `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded)
} catch { Fail "管理者権限の確認がキャンセルされました。再実行すると続きから進みます。" }
if (-not (Test-Path -LiteralPath $resultFile)) { Fail "管理者権限の処理が結果を返さずに終了しました (終了コード $($p.ExitCode))。" }
$result = Get-Content -LiteralPath $resultFile -Raw -Encoding UTF8 | ConvertFrom-Json
Remove-Item -LiteralPath $resultFile -Force
if (-not $result.ok) { Fail "登録解除またはプログラムの削除に失敗しました: $($result.message)" }
Say "  OK"
} else {
    Say "== Windows への登録: なし (登録解除は不要)"
}

# 登録解除が済んでから、この利用者の Tag と TSF の設定を消す。
# TSF の設定には、入力方法の一覧から外したときに Windows が残す Enable = 0 も含まれる。
if (Test-Path -LiteralPath $ProductKey) { Remove-Item -LiteralPath $ProductKey -Recurse -Force }
$userTip = "HKCU:\SOFTWARE\Microsoft\CTF\TIP\$Clsid"
if (Test-Path -LiteralPath $userTip) { Remove-Item -LiteralPath $userTip -Recurse -Force }
Remove-Item -LiteralPath $Local -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $Local) { Fail "プログラムのフォルダを消し切れませんでした: $Local  使っているアプリを閉じて、もう一度実行してください。" }
if ($RemoveData -and (Test-Path -LiteralPath $UserData)) {
    Remove-Item -LiteralPath $UserData -Recurse -Force
    Say "  削除: $UserData"
}

# 終了を知らせ、利用者データを残す場合はその場所を表示する。
Say ""
Say "アンインストールが完了しました。"
if (-not $RemoveData) {
    Say "学習データ・登録した単語・設定は残っています: $UserData"
    Say "  これらも削除するには、README の「全部消す場合」の1行 (-RemoveData 付き) を実行します。"
}
exit 0
