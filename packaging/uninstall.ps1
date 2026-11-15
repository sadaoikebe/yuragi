# ゆらぎのアンインストール (REDESIGN §8.3、docs/INSTALL.md)
#
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1 [-RemoveData] [-Yes]
#
# アプリを開いたままでよい。サインアウトや再起動は求めない。
#   1 保守中の印
#   2 HKCU の Tag と Run キーを消す (最初に: 残った DLL はこれで何も起動しなくなる)、言語一覧から外す
#   3 ブローカーに quit (エンジンも終わる)
#   4 管理者権限: 登録解除、読み返し、Program Files\yuragi-ime の削除 (使用中の DLL は .trash へ移す)
#   5 HKCU の製品のキーと TSF の利用者設定、%LOCALAPPDATA%\yuragi-ime を削除
#   6 結果
# 学習した内容・登録した単語・設定 (%USERPROFILE%\.yuragi-ime) は残す。
# -RemoveData を付けたときだけ、場所と大きさを見せて確かめてから消す (I-7)。

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

# 管理者権限で動かすのは、インストール時に Program Files (管理者しか書けない) に置いた
# elevated.ps1 だけ。登録されている DLL と同じフォルダのものを使う。登録が無いとき
# (前回のアンインストールが登録解除のあとで止まった) は、Program Files\yuragi-ime\<tag>\ に
# 残っているものを使って、続きを片付ける。
$ProgramRoot = Join-Path $env:ProgramFiles "yuragi-ime"
$ElevatedScript = $null
$registeredDll = (Get-ItemProperty -LiteralPath $InprocKey -ErrorAction SilentlyContinue).'(default)'
if ($registeredDll) {
    $elevatedPath = Join-Path (Split-Path $registeredDll) "elevated.ps1"
    if (-not (Test-Path -LiteralPath $elevatedPath)) {
        Write-Host "エラー: $elevatedPath がありません。インストールの 1 行以外で入れた版は、このスクリプトでは削除できません。" -ForegroundColor Red
        exit 1
    }
} elseif (Test-Path -LiteralPath $ProgramRoot) {
    $elevatedPath = Get-ChildItem -LiteralPath $ProgramRoot -Directory |
        Where-Object { $_.Name -ne ".trash" } |
        ForEach-Object { Join-Path $_.FullName "elevated.ps1" } |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if ($elevatedPath) { $ElevatedScript = [IO.File]::ReadAllText($elevatedPath) }

# 管理者用スクリプトの中身と引数を 1 つのコマンドにして -EncodedCommand 用に符号化する。
# 引数は単一引用符で囲む (中の ' は '' に)。
function New-ElevatedCommand([string]$script, [string[]]$arguments) {
    $quoted = @($arguments | ForEach-Object {
        if ($_ -like "-*") { $_ } else { "'" + $_.Replace("'", "''") + "'" } })
    $command = "& {`n$script`n} " + ($quoted -join " ")
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}
function Say([string]$msg) { Write-Host $msg }
function Fail([string]$msg) { Write-Host "エラー: $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- 1
$createdNew = $false
$maintenance = New-Object System.Threading.Mutex($true, "Local\yuragi-ime-maintenance", [ref]$createdNew)
if (-not $createdNew) { Fail "別のインストールまたはアンインストールが実行中です。" }

# -RemoveData の確認は最初に (途中で止まらないように)。
if ($RemoveData -and (Test-Path -LiteralPath $UserData)) {
    $size = (Get-ChildItem -LiteralPath $UserData -Recurse -Force -File | Measure-Object -Property Length -Sum).Sum
    Say "学習データ・登録した単語・設定も削除します: $UserData ($([math]::Round($size / 1KB)) KB)"
    if (-not $Yes) {
        $ans = Read-Host "削除すると元に戻せません。続行しますか? [y/N]"
        if ($ans -notmatch "^[Yy]") { Fail "キャンセルしました。何も変更していません。" }
    }
}

# ---------------------------------------------------------------- 2
Say "== 自動起動と入力方法の一覧から削除"
if (Test-Path -LiteralPath $ProductKey) { Remove-ItemProperty -LiteralPath $ProductKey -Name "Tag" -ErrorAction SilentlyContinue }
Remove-ItemProperty -LiteralPath $RunKey -Name "yuragi-ime" -ErrorAction SilentlyContinue
if ((Test-Path -LiteralPath $ProductKey) -and (Get-ItemProperty -LiteralPath $ProductKey).Tag) { Fail "HKCU\Software\yuragi-ime の Tag を削除できませんでした。" }
Add-Type -Namespace YuragiUninstall -Name Input -MemberDefinition @'
[DllImport("input.dll", CharSet = CharSet.Unicode)]
public static extern bool InstallLayoutOrTip(string profile, uint flags);
'@
# ILOT_UNINSTALL
if (-not [YuragiUninstall.Input]::InstallLayoutOrTip($Layout, 1)) { Say "  入力方法の一覧: 未登録" }
Say "  OK"

# ---------------------------------------------------------------- 3
Say "== ブローカーの終了"
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$session = (Get-Process -Id $PID).SessionId
$pipe = New-Object System.IO.Pipes.NamedPipeClientStream(".", "yuragi-ime-$sid-$session", [IO.Pipes.PipeDirection]::InOut)
try {
    $pipe.Connect(1000)
    $writer = New-Object IO.StreamWriter($pipe, $Utf8NoBom)
    $writer.AutoFlush = $true
    $writer.NewLine = "`n"
    $writer.WriteLine('{"op":"hello","proto":1,"tag":"uninstall","bits":64}')
    $writer.WriteLine('{"op":"quit"}')
} catch { } finally { $pipe.Dispose() }
foreach ($b in @(Get-Process -Name "yuragi-broker" -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session })) {
    if (-not $b.WaitForExit(15000)) {
        Stop-Process -Id $b.Id -Force
        if (-not $b.WaitForExit(5000)) { Fail "ブローカー (PID $($b.Id)) を終了できませんでした。" }
    }
}
Say "  OK"

# ---------------------------------------------------------------- 4
$result = [pscustomobject]@{ ok = $true; message = "not registered"; pending_delete = @() }
if ($ElevatedScript) {
Say "== Windows からの登録解除とプログラムの削除 (管理者権限の確認が出ます)"
$resultFile = Join-Path $env:TEMP ("yuragi-elevated-" + [Guid]::NewGuid().ToString("N") + ".json")
$encoded = New-ElevatedCommand $ElevatedScript @("-Action", "uninstall", "-ResultFile", $resultFile)
try {
    $p = Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -Wait -PassThru `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded)
} catch { Fail "管理者権限の確認がキャンセルされました。ゆらぎはこの利用者では起動しなくなっています。再実行すると続きから進みます。" }
if (-not (Test-Path -LiteralPath $resultFile)) { Fail "管理者権限の処理が結果を返さずに終了しました (終了コード $($p.ExitCode))。" }
$result = Get-Content -LiteralPath $resultFile -Raw -Encoding UTF8 | ConvertFrom-Json
Remove-Item -LiteralPath $resultFile -Force
if (-not $result.ok) { Fail "登録解除またはプログラムの削除に失敗しました: $($result.message)" }
$registered = Get-ItemProperty -LiteralPath $InprocKey -ErrorAction SilentlyContinue
if ($registered) { Fail "登録解除後も登録が残っています ($($registered.'(default)'))。" }
Say "  OK"
} else {
    Say "== Windows への登録: なし (登録解除は不要)"
    if (Test-Path -LiteralPath $ProgramRoot) {
        Say "  管理者権限での削除に使う elevated.ps1 が無いため、残しました: $ProgramRoot"
    }
}

# ---------------------------------------------------------------- 5
# 登録が消えたあとの、この利用者の分: 製品のキー (Tag と揮発キー Session) と、
# 言語一覧から外したときに Windows が書く TSF の利用者設定 (Enable = 0)。
if (Test-Path -LiteralPath $ProductKey) { Remove-Item -LiteralPath $ProductKey -Recurse -Force }
$userTip = "HKCU:\SOFTWARE\Microsoft\CTF\TIP\$Clsid"
if (Test-Path -LiteralPath $userTip) { Remove-Item -LiteralPath $userTip -Recurse -Force }
$maintenance.ReleaseMutex()
$maintenance.Dispose()
$left = @()
if (Test-Path -LiteralPath $Local) {
    foreach ($item in @(Get-ChildItem -LiteralPath $Local -Force)) {
        try { Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction Stop } catch { $left += $item.FullName }
    }
    if (-not $left.Count) { Remove-Item -LiteralPath $Local -Recurse -Force -ErrorAction SilentlyContinue }
}
if ($RemoveData -and (Test-Path -LiteralPath $UserData)) {
    Remove-Item -LiteralPath $UserData -Recurse -Force
    Say "  削除: $UserData"
}

# ---------------------------------------------------------------- 6
Say ""
Say "アンインストールが完了しました。"
if (@($result.pending_delete).Count) {
    Say "  使用中のファイル $(@($result.pending_delete).Count) 個を $ProgramRoot\.trash に移しました。使われなくなったあと、Windows の再起動時か次回のセットアップ時に削除されます。"
}
if ($left.Count) { Say "  削除できなかったファイル: $($left -join ', ')" }
if (-not $RemoveData) {
    Say "学習データ・登録した単語・設定は残っています: $UserData"
    Say "  これらも削除するには、末尾に -RemoveData を付けて再実行します。"
}
exit 0
