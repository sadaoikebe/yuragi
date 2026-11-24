# 開発用: dist\ のビルドをこの PC に登録して使う (DESIGN「開発時」)。タグは dev。
#
#   powershell -ExecutionPolicy Bypass -File .\src\tip\dev-register.ps1 [-Python <python.exe>]
#
# - HKCU の Tag を dev にし、%LOCALAPPDATA%\yuragi-ime\versions\dev\engine.json を
#   このリポジトリに向ける (yuragi.engine --require-lm)。
# - -Python を渡すと、その Python で python -m yuragi.engine を動かす (torch と transformers が要る)。
#   渡さなければ、入っている製品版の engine.json から同梱の Python と LM のモデルを借りる
#   (辞書とキャッシュはリポジトリの既定)。--require-lm なので、LM を読めない Python では起動しない。
# - DLL とブローカーは dist\ から読み込む (開発機に限り Program Files に置かない)。
#   DLL は dist\yuragi_tip-a.dll / -b.dll / ... のうち、登録中でなく使用中でもないものに
#   コピーして登録するので、古い DLL を読み込んだアプリを閉じなくても更新できる。
# - 登録 (regsvr32) だけ管理者権限 (UAC 1 回)。登録後にレジストリを読み返して確かめる。
param([string]$Python = "")
$ErrorActionPreference = 'Stop'
$Repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Dist = Join-Path $Repo 'dist'
$Clsid = '{A7C4E201-0B3A-4F11-9E61-0C1A0B7E0A01}'
$Layout = "0x0411:$Clsid{A7C4E202-0B3A-4F11-9E61-0C1A0B7E0A01}"
$Utf8NoBom = New-Object Text.UTF8Encoding($false)

# $Product (製品版の engine.json) を渡すと、その Python と LM のモデルで、リポジトリのソースを動かす。
function Write-DevEngineConfig([string]$Path, [string]$Python, [string]$Repo, $Product = $null) {
    $engine = [ordered]@{
        python = $Python
        pythonw = (Join-Path (Split-Path $Python) 'pythonw.exe')
        app = $Repo
        args = @('-m', 'yuragi.engine', '--require-lm')
        admin_args = @('-m', 'yuragi.ime.admin_ui')
    }
    if ($Product) {
        # 同梱の Python は埋め込み版で、-m では作業フォルダを探さない。製品版と同じ -c の前置きで読む。
        $given = @($Product.args)
        if ($given.Count -lt 3 -or $given[0] -ne '-c' -or $given[2] -ne 'yuragi.engine') {
            throw '製品版の engine.json の形が想定と違います。-Python で Python を渡してください。'
        }
        $lm = @()
        for ($i = 3; $i -lt $given.Count - 1; $i++) {
            if ($given[$i] -in @('--lm-model', '--lm-cpu-model')) { $lm += @($given[$i], $given[$i + 1]) }
        }
        $engine.python = $Product.python
        $engine.pythonw = $Product.pythonw
        $engine.args = @($given[0], $given[1], 'yuragi.engine', '--require-lm') + $lm
        $engine.admin_args = @($given[0], $given[1], 'yuragi.ime.admin_ui')
    }
    [IO.File]::WriteAllText($Path, ($engine | ConvertTo-Json -Depth 3), [Text.UTF8Encoding]::new($false))
}

# 入っている製品版の engine.json (今のタグ。dev なら、いちばん新しい版)。
function Find-ProductEngine {
    $versions = Join-Path $env:LOCALAPPDATA 'yuragi-ime\versions'
    $tag = (Get-ItemProperty -LiteralPath 'HKCU:\Software\yuragi-ime' -ErrorAction SilentlyContinue).Tag
    $paths = @()
    if ($tag -and $tag -ne 'dev') { $paths += Join-Path $versions "$tag\engine.json" }
    $paths += @(Get-ChildItem -LiteralPath $versions -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne 'dev' } | Sort-Object LastWriteTime -Descending |
        ForEach-Object { Join-Path $_.FullName 'engine.json' })
    foreach ($p in $paths) {
        if (Test-Path -LiteralPath $p) { return (Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json) }
    }
    return $null
}

$product = $null
if (-not $Python) {
    $product = Find-ProductEngine
    if (-not $product) { throw '製品版が入っていません。torch と transformers の入った Python を -Python で渡してください。' }
    $Python = $product.python
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Python が見つかりません: $Python" }
foreach ($f in @('yuragi_tip.dll', 'yuragi-broker.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Dist $f))) { throw "$f がありません。先に dev-build.ps1 を実行してください。" }
}

# 旧ブローカーを終わらせる (エンジンも終わる)。
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$session = (Get-Process -Id $PID).SessionId
$pipe = New-Object System.IO.Pipes.NamedPipeClientStream('.', "yuragi-ime-$sid-$session", [IO.Pipes.PipeDirection]::InOut)
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
foreach ($b in @(Get-Process -Name 'yuragi-broker' -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session })) {
    if (-not $b.WaitForExit(15000)) { throw "ブローカー (PID $($b.Id)) が終わりません。" }
}

# DLL のスロット: いま登録されていなくて、上書きできる最初のもの (a, b, c, ...)。
# 登録を解いても、読み込んだアプリ (explorer など) は DLL を掴んだままなので、
# 解除して入れ直すと a も b も使用中のことがある。
$inproc = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$Clsid\InprocServer32"
$registered = (Get-ItemProperty -LiteralPath $inproc -ErrorAction SilentlyContinue).'(default)'
$slot = $null
foreach ($letter in [char[]]'abcdefghijklmnopqrstuvwxyz') {
    $candidate = Join-Path $Dist "yuragi_tip-$letter.dll"
    if ($candidate -eq $registered) { continue }
    try {
        Copy-Item -LiteralPath (Join-Path $Dist 'yuragi_tip.dll') -Destination $candidate -Force
        $slot = $candidate
        break
    } catch { }
}
if (-not $slot) {
    throw "dist\yuragi_tip-a.dll から -z.dll まですべて使用中です。古い DLL を使うアプリを終了してから再実行してください。"
}
# packaging\uninstall.ps1 は登録済み DLL と同じフォルダの elevated.ps1 を使う。
Copy-Item -LiteralPath (Join-Path $Repo 'packaging\elevated.ps1') -Destination (Join-Path $Dist 'elevated.ps1') -Force
$p = Start-Process "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList @('/s', "`"$slot`"") -Verb RunAs -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "regsvr32 が失敗しました (終了コード $($p.ExitCode))。" }
if ((Get-ItemProperty -LiteralPath $inproc).'(default)' -ne $slot) { throw "登録を読み返すと $slot ではありませんでした。" }

# この利用者の分: タグ、engine.json、言語一覧。
New-Item -Force 'HKCU:\Software\yuragi-ime' | Out-Null
Set-ItemProperty -LiteralPath 'HKCU:\Software\yuragi-ime' -Name 'Tag' -Value 'dev'
$version = Join-Path $env:LOCALAPPDATA 'yuragi-ime\versions\dev'
New-Item -ItemType Directory -Force $version | Out-Null
Write-DevEngineConfig (Join-Path $version 'engine.json') $Python $Repo $product
Add-Type -Namespace YuragiDev -Name Input -MemberDefinition @'
[DllImport("input.dll", CharSet = CharSet.Unicode)]
public static extern bool InstallLayoutOrTip(string profile, uint flags);
'@
[void][YuragiDev.Input]::InstallLayoutOrTip($Layout, 0)

Start-Process -FilePath (Join-Path $Dist 'yuragi-broker.exe')
Write-Host ("登録した DLL: " + [IO.Path]::GetFileName($slot) + "、ブローカーを起動しました (タグ dev)。")
Write-Host '新しく開いたアプリから新版が読み込まれます。開いていたアプリは旧版の DLL のまま新しいブローカーにつながります。'
