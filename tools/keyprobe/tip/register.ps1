# キーの確認用の TIP を登録し、入力方式の一覧に「キーの確認（keyprobe）」を足す。-Remove で外し、probe.json と probe.log を消す。どちらも UAC 1 回。
#
#   powershell -ExecutionPolicy Bypass -File .\tools\keyprobe\tip\register.ps1
#   powershell -ExecutionPolicy Bypass -File .\tools\keyprobe\tip\register.ps1 -Remove
#
# ゆらぎの登録には触らない。DLL は out\tip\keyprobe_tip-a.dll / -b.dll / ... のうち使用中でないものに
# コピーして登録するので、古い DLL を読み込んだアプリを閉じなくても入れ直せる。
param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$Out = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\out\tip'))
$Clsid = '{B3F0A501-6C2E-4D8A-9B47-2E5D1C0F7A11}'
$Layout = "0x0411:$Clsid{B3F0A502-6C2E-4D8A-9B47-2E5D1C0F7A11}"
$Inproc = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$Clsid\InprocServer32"
Add-Type -Namespace YuragiKeyProbe -Name Input -MemberDefinition @'
[DllImport("input.dll", CharSet = CharSet.Unicode)]
public static extern bool InstallLayoutOrTip(string profile, uint flags);
'@
$registered = (Get-ItemProperty -LiteralPath $Inproc -ErrorAction SilentlyContinue).'(default)'

function Invoke-Regsvr32([string[]]$arguments) {
    $p = Start-Process "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList $arguments -Verb RunAs -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "regsvr32 が失敗しました (終了コード $($p.ExitCode))。" }
}

if ($Remove) {
    [void][YuragiKeyProbe.Input]::InstallLayoutOrTip($Layout, 1)  # ILOT_UNINSTALL
    if ($registered) { Invoke-Regsvr32 @('/s', '/u', "`"$registered`"") }
    foreach ($name in 'probe.json', 'probe.log') {
        Remove-Item -LiteralPath (Join-Path $env:USERPROFILE ".yuragi-ime\$name") -ErrorAction SilentlyContinue
    }
    Write-Host '確認用の TIP を外しました。'
    return
}

$dll = Join-Path $Out 'keyprobe_tip.dll'
if (-not (Test-Path -LiteralPath $dll)) { throw "$dll がありません。先に build.ps1 を実行してください。" }
$slot = $null
foreach ($letter in [char[]]'abcdefghijklmnopqrstuvwxyz') {
    $candidate = Join-Path $Out "keyprobe_tip-$letter.dll"
    if ($candidate -eq $registered) { continue }
    try {
        Copy-Item -LiteralPath $dll -Destination $candidate -Force
        $slot = $candidate
        break
    } catch { }
}
if (-not $slot) { throw 'keyprobe_tip-a.dll から -z.dll まですべて使用中です。古い DLL を使うアプリを閉じてください。' }
Invoke-Regsvr32 @('/s', "`"$slot`"")
if ((Get-ItemProperty -LiteralPath $Inproc).'(default)' -ne $slot) { throw "登録を読み返すと $slot ではありませんでした。" }
[void][YuragiKeyProbe.Input]::InstallLayoutOrTip($Layout, 0)
Write-Host ("登録した DLL: " + [IO.Path]::GetFileName($slot) + "。Win+Space で「キーの確認（keyprobe）」を選んでください。")
