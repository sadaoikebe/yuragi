# ゆらぎのインストールと更新。手順は DESIGN「インストール・更新・アンインストール」
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1 [-Yes]
#
# インストールも更新も同じ手順。どこで失敗しても「前の版が動く」か「新しい版が動く」の
# どちらか (DESIGN「守ること」6)。利用者のデータ (%USERPROFILE%\.yuragi-ime) は消さない (同 7)。

param(
    [switch]$Yes
)

# PowerShell 7 (pwsh) から起動されたら、Windows PowerShell 5.1 で起動し直す。
if ($PSVersionTable.PSEdition -eq "Core") {
    $relaunch = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if ($Yes) { $relaunch += "-Yes" }
    & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" @relaunch
    exit $LASTEXITCODE
}

$ErrorActionPreference = "Stop"
# この中で動かす Python は UTF-8 で入出力する (このプロセスの中だけ)。
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo = "sadaoikebe/yuragi"
$Tag = "__TAG__"                         # リリース時に workflow が刻む
$EmbedPythonVersion = "3.13.7"
$EmbedPythonSha256 = "__EMBED_SHA256__"  # 同上 (python.org の公式 zip の SHA-256)
$TorchVersion = "2.9.1"
$Local = Join-Path $env:LOCALAPPDATA "yuragi-ime"
$Shared = Join-Path $Local "shared"
$Versions = Join-Path $Local "versions"
$StagingRoot = Join-Path $Local "staging"
$ProgramRoot = Join-Path $env:ProgramFiles "yuragi-ime"
$UserData = Join-Path $env:USERPROFILE ".yuragi-ime"
$Clsid = "{A7C4E201-0B3A-4F11-9E61-0C1A0B7E0A01}"
$Layout = "0x0411:$Clsid{A7C4E202-0B3A-4F11-9E61-0C1A0B7E0A01}"
$ProductKey = "HKCU:\Software\yuragi-ime"
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
# python -m の代わり: 同梱ランタイムは ._pth があるので作業フォルダを import 経路に入れない。
$Boot = "import os,sys,runpy; sys.path.insert(0, os.getcwd()); m = sys.argv.pop(1); runpy.run_module(m, run_name='__main__', alter_sys=True)"
$Utf8NoBom = New-Object Text.UTF8Encoding($false)

function Say([string]$msg) { Write-Host $msg }
function Fail([string]$msg) {
    Write-Host "エラー: $msg" -ForegroundColor Red
    Write-Host "インストール済みの版はそのまま使えます。再実行すると続きから進みます。"
    exit 1
}
function Ask([string]$question) {
    if ($Yes) { Say "$question [Y/n] Y (-Yes)"; return $true }
    $ans = Read-Host "$question [Y/n]"
    return ($ans -eq "" -or $ans -match "^[Yy]")
}
function Invoke-Checked([string]$name, [scriptblock]$body) {
    Say "== $name"
    & $body
    if ($LASTEXITCODE -ne 0) { Fail "$name が失敗しました (終了コード $LASTEXITCODE)。" }
}

# ---------------------------------------------------------------- 1 保守中の印
if ($Tag -like "__*" -or $EmbedPythonSha256 -like "__*") {
    Fail "この setup.ps1 はリリース版ではありません。リリースページの setup.ps1 を使ってください。"
}
$createdNew = $false
$maintenance = New-Object System.Threading.Mutex($true, "Local\yuragi-ime-maintenance", [ref]$createdNew)
if (-not $createdNew) { Fail "別のインストールまたはアンインストールが実行中です。" }

Say "ゆらぎ $Tag セットアップ"
Say ""
Say "== 動作環境の確認"
$arch = $env:PROCESSOR_ARCHITECTURE
if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
if ($arch -eq "ARM64") { Fail "ARM 版 Windows には対応していません。" }
if (-not [Environment]::Is64BitOperatingSystem) { Fail "64bit 版 Windows が必要です。" }
$os = [Environment]::OSVersion.Version
if ($os.Major -lt 10) { Fail "Windows 10 以降が必要です (この PC: $os)。" }
$free = (Get-PSDrive ($env:LOCALAPPDATA.Substring(0, 1))).Free
if ($free -lt 3GB) { Fail "ディスクの空きが不足しています (必要: 3GB、空き: $([math]::Round($free / 1GB, 1))GB)。" }
Say "  Windows $($os.Major).$($os.Minor) 64bit、ディスク空き $([math]::Round($free / 1GB, 1))GB  OK"
Say ""
Say "次のものをダウンロードします (取得済みのものは省略):"
Say "  ゆらぎ本体・TIP・ブローカー・tkinter (GitHub Releases、約 35MB)"
Say "  Python $EmbedPythonVersion (python.org、約 30MB)"
Say "  PyTorch $TorchVersion CPU 版 (download.pytorch.org、約 200MB)"
Say "  transformers・huggingface_hub ほか (PyPI)"
Say "  Mozc 辞書 (github.com/google/mozc、約 93MB)"
Say "  言語モデル zenz-v2.5-medium (huggingface.co、約 620 MB)"
if (-not (Ask "続行しますか?")) { Fail "キャンセルしました。" }

function Get-Verified([string]$url, [string]$dest) {
    Invoke-WebRequest -UseBasicParsing $url -OutFile $dest
    $expected = (Invoke-WebRequest -UseBasicParsing "$url.sha256").Content
    if ($expected -is [byte[]]) { $expected = [Text.Encoding]::ASCII.GetString($expected) }
    $expected = $expected.Trim().ToLower()
    $actual = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expected) { Fail "SHA-256 不一致: $(Split-Path $dest -Leaf)" }
    Say "  $(Split-Path $dest -Leaf)  OK (SHA-256)"
    return $expected
}

# 共有物は「作りかけの名前で作って、完成したら改名」。完成したものは取り直さない。
function New-Shared([string]$final, [scriptblock]$build) {
    if (Test-Path -LiteralPath $final) { return }
    $partial = "$final.partial"
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Recurse -Force }
    New-Item -ItemType Directory -Force $partial | Out-Null
    & $build $partial
    Rename-Item -LiteralPath $partial -NewName (Split-Path $final -Leaf)
}

function Invoke-App([string]$python, [string]$app, [string[]]$moduleAndArgs) {
    Push-Location -LiteralPath $app
    try { & $python -c $Boot @moduleAndArgs } finally { Pop-Location }
}

function Write-EngineJson([string]$path, [string]$app, [string[]]$extra) {
    $engine = [ordered]@{
        format = 1
        python = $script:Python
        pythonw = (Join-Path (Split-Path $script:Python) "pythonw.exe")
        app = $app
        args = @("-c", $Boot, "yuragi.engine", "--dict-dir", $script:Dict,
                 "--cache-dir", $script:Cache, "--lm-model", $script:Model) + $extra
        admin_args = @("-c", $Boot, "yuragi.ime.admin_ui", "--dict-dir", $script:Dict)
    }
    [IO.File]::WriteAllText($path, ($engine | ConvertTo-Json -Depth 4), $Utf8NoBom)
}

# ---------------------------------------------------------------- 2 staging
Say ""
Say "== ゆらぎ本体のダウンロード"
$Stage = Join-Path $StagingRoot $Tag
# staging は自分の作業場: 前回の途中のものがあれば消して作り直す。
if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
$Download = Join-Path $Stage "download"
New-Item -ItemType Directory -Force $Download | Out-Null
$baseUrl = "https://github.com/$Repo/releases/download/$Tag"
$sourceZip = Join-Path $Download "yuragi-source.zip"
$dllPath = Join-Path $Download "yuragi_tip.dll"
$brokerPath = Join-Path $Download "yuragi-broker.exe"
[void](Get-Verified "$baseUrl/yuragi-source.zip" $sourceZip)
[void](Get-Verified "$baseUrl/yuragi_tip.dll" $dllPath)
[void](Get-Verified "$baseUrl/yuragi-broker.exe" $brokerPath)
$StageApp = Join-Path $Stage "app"
Expand-Archive -LiteralPath $sourceZip -DestinationPath $StageApp

# 同梱ランタイム: Python の版・依存の固定・torch の版で名前が決まる。中身が同じなら共有する。
# 「tk」は tkinter 一式 (リリースのアセット。同じ版の通常版 Python から取ったもの) 入りの印。
$requirements = Join-Path $StageApp "packaging\requirements.txt"
$reqHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash.Substring(0, 12).ToLower()
$runtimeId = "py$EmbedPythonVersion-tk-torch$TorchVersion-$reqHash"
$Runtime = Join-Path $Shared "runtime\$runtimeId"
New-Shared $Runtime {
    param($dir)
    Say "== Python ランタイムの作成 ($runtimeId)"
    $embedZip = Join-Path $Download "python-embed.zip"
    Invoke-WebRequest -UseBasicParsing "https://www.python.org/ftp/python/$EmbedPythonVersion/python-$EmbedPythonVersion-embed-amd64.zip" -OutFile $embedZip
    if ((Get-FileHash -LiteralPath $embedZip -Algorithm SHA256).Hash.ToLower() -ne $EmbedPythonSha256.ToLower()) {
        Fail "SHA-256 不一致: python-$EmbedPythonVersion-embed-amd64.zip"
    }
    Expand-Archive -LiteralPath $embedZip -DestinationPath $dir
    # 埋め込み版に無い tkinter 一式 (_tkinter.pyd と Tcl/Tk の DLL は直下、tcl\、Lib\tkinter\)。
    $tkZip = Join-Path $Download "python-tkinter.zip"
    [void](Get-Verified "$baseUrl/python-$EmbedPythonVersion-tkinter-amd64.zip" $tkZip)
    Expand-Archive -LiteralPath $tkZip -DestinationPath $dir
    $pth = Get-ChildItem -LiteralPath $dir -Filter "python*._pth" | Select-Object -First 1 -ExpandProperty FullName
    @(("python" + $EmbedPythonVersion.Substring(0, 4).Replace(".", "") + ".zip"), ".", "Lib", "Lib\site-packages", "import site") |
        Set-Content -LiteralPath $pth -Encoding ASCII
    $py = Join-Path $dir "python.exe"
    $getPip = Join-Path $Download "get-pip.py"
    Invoke-WebRequest -UseBasicParsing "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
    Invoke-Checked "pip のインストール" { & $py $getPip --no-warn-script-location }
    Invoke-Checked "PyTorch $TorchVersion CPU 版のインストール" {
        & $py -m pip install --no-warn-script-location --index-url https://download.pytorch.org/whl/cpu "torch==$TorchVersion"
    }
    Invoke-Checked "依存パッケージのインストール" {
        & $py -m pip install --no-warn-script-location -r $requirements
    }
    Invoke-Checked "インポートの確認" {
        & $py -c "import torch, transformers, huggingface_hub, tkinter; tkinter.Tcl()"
    }
}
$script:Python = Join-Path $Runtime "python.exe"

$manifest = Get-Content -LiteralPath (Join-Path $StageApp "data\dictionary-manifest.json") -Raw | ConvertFrom-Json
$script:Dict = Join-Path $Shared "dict\$($manifest.upstream_commit)"
New-Shared $script:Dict {
    param($dir)
    Invoke-Checked "Mozc 辞書のダウンロード" {
        Invoke-App $script:Python $StageApp @("tools.eval.fetch_mozc_dict", "--out", $dir)
    }
    Invoke-Checked "Mozc 辞書の SHA-256 照合" {
        Invoke-App $script:Python $StageApp @("yuragi.lattice.dict_manifest", "verify", "--dict-dir", $dir)
    }
}
$revision = (Select-String -LiteralPath (Join-Path $StageApp "packaging\fetch_model.py") -Pattern '^REVISION = "([0-9a-f]+)"').Matches[0].Groups[1].Value
$script:Model = Join-Path $Shared "model\$revision"
New-Shared $script:Model {
    param($dir)
    Invoke-Checked "言語モデルのダウンロード (Miwa-Keita/zenz-v2.5-medium)" {
        & $script:Python (Join-Path $StageApp "packaging\fetch_model.py") $dir
    }
}
$script:Cache = Join-Path $Shared "cache"
New-Item -ItemType Directory -Force $script:Cache | Out-Null

# ---------------------------------------------------------------- 3 試運転
# 利用者のデータには触らない: 試運転のエンジンは staging の中のフォルダを使う。
$selftestData = Join-Path $Stage "selftest-data"
New-Item -ItemType Directory -Force $selftestData | Out-Null
$stageEngine = Join-Path $Stage "engine.json"
Write-EngineJson $stageEngine $StageApp @("--data-dir", $selftestData)
Say ""
Say "== 動作テスト (初回は辞書の準備に数分かかります)"
$selftestOut = Join-Path $Stage "selftest.txt"
$proc = Start-Process -FilePath $brokerPath -ArgumentList @("--selftest", "`"$stageEngine`"", "--data-dir", "`"$selftestData`"") `
    -Wait -PassThru -RedirectStandardOutput $selftestOut
if ($proc.ExitCode -ne 0) {
    Fail "動作テストが失敗しました (終了コード $($proc.ExitCode))。ログ: $(Join-Path $selftestData 'logs')"
}
Say "  変換  OK"

# ---------------------------------------------------------------- 旧ブローカー
function Connect-Broker([int]$timeoutMs) {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $session = (Get-Process -Id $PID).SessionId
    $pipe = New-Object System.IO.Pipes.NamedPipeClientStream(".", "yuragi-ime-$sid-$session", [IO.Pipes.PipeDirection]::InOut)
    try { $pipe.Connect($timeoutMs) } catch { $pipe.Dispose(); return $null }
    $writer = New-Object IO.StreamWriter($pipe, $Utf8NoBom)
    $writer.AutoFlush = $true
    $writer.NewLine = "`n"
    $reader = New-Object IO.StreamReader($pipe, $Utf8NoBom)
    $writer.WriteLine('{"op":"hello","proto":1,"tag":"setup","bits":64}')
    return @{ Pipe = $pipe; Reader = $reader; Writer = $writer }
}
function Read-BrokerLine($conn, [int]$timeoutMs) {
    $task = $conn.Reader.ReadLineAsync()
    if ($task.Wait($timeoutMs)) { return $task.Result }
    return $null
}
function Stop-Broker {
    $conn = Connect-Broker 1000
    if ($conn) {
        [void](Read-BrokerLine $conn 2000)
        try { $conn.Writer.WriteLine('{"op":"quit"}') } catch { }
        $conn.Pipe.Dispose()
    }
    $session = (Get-Process -Id $PID).SessionId
    $brokers = @(Get-Process -Name "yuragi-broker" -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session })
    foreach ($b in $brokers) {
        if (-not $b.WaitForExit(15000)) {
            Say "  ブローカーが応答しないため強制終了します (PID $($b.Id))"
            Stop-Process -Id $b.Id -Force
            if (-not $b.WaitForExit(5000)) { Fail "ブローカー (PID $($b.Id)) を終了できませんでした。" }
        }
    }
}

# ---------------------------------------------------------------- 4 versions へ
$Version = Join-Path $Versions $Tag
New-Item -ItemType Directory -Force $Versions | Out-Null
if (Test-Path -LiteralPath $Version) {
    if ((Get-ItemProperty -LiteralPath $ProductKey -ErrorAction SilentlyContinue).Tag -eq $Tag) {
        # 同じ版の入れ直し: その版のエンジンが作業フォルダを使っているので先に止める。
        Say "  同じ版 ($Tag) を再インストールします"
        Stop-Broker
    }
    # Tag が違えば、前回が段 5 で止まった残り。動いている旧版には触らない。
    $aside = "$Version.old-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
    Rename-Item -LiteralPath $Version -NewName (Split-Path $aside -Leaf)
}
Move-Item -LiteralPath $Stage -Destination $Version
Remove-Item -LiteralPath (Join-Path $Version "selftest-data") -Recurse -Force -ErrorAction SilentlyContinue
$App = Join-Path $Version "app"
Write-EngineJson (Join-Path $Version "engine.json") $App @()

# ---------------------------------------------------------------- 5 管理者権限
# 管理者用スクリプトの呼び出しと引数を 1 つのコマンドにして -EncodedCommand 用に符号化する
# (空白・引用符・日本語を含むパスもそのまま届く)。パスと引数は単一引用符で囲む (中の ' は '' に)。
function New-ElevatedCommand([string]$scriptPath, [string[]]$arguments) {
    $quoted = @($arguments | ForEach-Object {
        if ($_ -like "-*") { $_ } else { "'" + $_.Replace("'", "''") + "'" } })
    $command = "& '" + $scriptPath.Replace("'", "''") + "' " + ($quoted -join " ")
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}
$ElevatedPath = Join-Path $App "packaging\elevated.ps1"   # from the verified source zip
function Invoke-Elevated([string[]]$arguments) {
    $resultFile = Join-Path $env:TEMP ("yuragi-elevated-" + [Guid]::NewGuid().ToString("N") + ".json")
    $encoded = New-ElevatedCommand $ElevatedPath ($arguments + @("-ResultFile", $resultFile))
    try {
        $p = Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -Wait -PassThru `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded)
    } catch {
        Fail "管理者権限の確認がキャンセルされました。"
    }
    if (-not (Test-Path -LiteralPath $resultFile)) { Fail "管理者権限の処理が結果を返さずに終了しました (終了コード $($p.ExitCode))。" }
    $result = Get-Content -LiteralPath $resultFile -Raw -Encoding UTF8 | ConvertFrom-Json
    Remove-Item -LiteralPath $resultFile -Force
    return $result
}

Say ""
Say "== Windows への登録 (管理者権限の確認が出ます)"
$result = Invoke-Elevated @("-Action", "install", "-Tag", $Tag, "-DllSource", (Join-Path $Version "download\yuragi_tip.dll"),
    "-BrokerSource", (Join-Path $Version "download\yuragi-broker.exe"), "-ScriptSource", $ElevatedPath)
# DESIGN「守ること」6: elevated.ps1 reports ok only after reading the registration back.
if (-not $result.ok) { Fail "Windows への登録に失敗しました: $($result.message)" }
$DllFinal = Join-Path $ProgramRoot "$Tag\yuragi_tip.dll"
$BrokerFinal = Join-Path $ProgramRoot "$Tag\yuragi-broker.exe"
Say "  登録: $DllFinal  OK"
$leftOld = @($result.left)

# ---------------------------------------------------------------- 6 切り替え
Say ""
Say "== 新しい版への切り替え"
Stop-Broker
New-Item -Force $ProductKey | Out-Null
Set-ItemProperty -LiteralPath $ProductKey -Name "Tag" -Value $Tag
New-Item -Force $RunKey | Out-Null
Set-ItemProperty -LiteralPath $RunKey -Name "yuragi-ime" -Value "`"$BrokerFinal`""
if ((Get-ItemProperty -LiteralPath $ProductKey).Tag -ne $Tag) { Fail "HKCU\Software\yuragi-ime に Tag を書き込めませんでした。" }
Add-Type -Namespace YuragiSetup -Name Input -MemberDefinition @'
[DllImport("input.dll", CharSet = CharSet.Unicode)]
public static extern bool InstallLayoutOrTip(string profile, uint flags);
'@
if (-not [YuragiSetup.Input]::InstallLayoutOrTip($Layout, 0)) { Fail "入力方法の一覧に追加できませんでした。" }

New-Item -ItemType Directory -Force $UserData | Out-Null

# ---------------------------------------------------------------- 7 起動と確認
$maintenance.ReleaseMutex()
$maintenance.Dispose()
Say ""
Say "== 起動確認 (最大 60 秒)"
Start-Process -FilePath $BrokerFinal
$deadline = (Get-Date).AddSeconds(60)
$state = ""
$conn = $null
while ((Get-Date) -lt $deadline -and -not $conn) { $conn = Connect-Broker 1000 }
if ($conn) {
    while ((Get-Date) -lt $deadline) {
        $line = Read-BrokerLine $conn ([Math]::Max(0, [int]($deadline - (Get-Date)).TotalMilliseconds))
        if ($null -eq $line) { break }
        $msg = $line | ConvertFrom-Json
        if ($msg.state) { $state = $msg.state }
        if ($state -eq "ready" -or $state -eq "down") { break }
    }
    $conn.Pipe.Dispose()
}
if ($state -ne "ready") {
    $why = @{ starting = '60 秒以内に起動しませんでした'; down = '起動に失敗しました' }[$state]
    if (-not $why) { $why = '応答がありません' }
    Write-Host "エラー: 変換エンジンが起動しませんでした ($why)。" -ForegroundColor Red
    Write-Host "ログ: $(Join-Path $UserData 'logs')。次回サインイン時にも起動を試みます。"
    exit 1
}
Say "  変換エンジン  OK"

# ---------------------------------------------------------------- 8 片付け
# 失敗はインストールの失敗にしない。次回の setup がまた試す。
$keep = @($Runtime, $script:Dict, $script:Model)
$cacheName = ""
try {
    Push-Location -LiteralPath $App
    $cacheName = (& $script:Python -c "import os,sys; sys.path.insert(0, os.getcwd()); from yuragi.lattice.mozc_dict import cache_name; print(cache_name())").Trim()
    Pop-Location
} catch { Pop-Location }
$cleanup = @()
$cleanup += @(Get-ChildItem -LiteralPath $Versions -Directory | Where-Object { $_.Name -ne $Tag })
foreach ($kind in @("runtime", "dict", "model")) {
    $dir = Join-Path $Shared $kind
    if (Test-Path -LiteralPath $dir) { $cleanup += @(Get-ChildItem -LiteralPath $dir -Directory | Where-Object { $keep -notcontains $_.FullName }) }
}
if ($cacheName) { $cleanup += @(Get-ChildItem -LiteralPath $script:Cache -File | Where-Object { $_.Name -ne $cacheName }) }
if (Test-Path -LiteralPath $StagingRoot) { $cleanup += @(Get-Item -LiteralPath $StagingRoot) }
$left = @()
foreach ($item in $cleanup) {
    try { Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction Stop } catch { $left += $item.FullName }
}

Say ""
Say "ゆらぎ $Tag のインストールが完了しました。"
if ($leftOld.Count) {
    Say "  使用中の旧版ファイル $($leftOld.Count) 個は残しました。次回のセットアップ時に削除します。"
}
if ($left.Count) { Say "  不要なファイル $($left.Count) 個を削除できませんでした。次回の更新時に再試行します。" }
Say ""
Say "使い方: Win+Space で「ゆらぎ」を選ぶと、タスクバーに「ゆ」が表示されます。再起動は不要です。"
Say "更新: インストールと同じ 1 行を再実行します。"
Say "アンインストール (PowerShell):"
# 前回の残りを先に消し、取得できたときだけ実行する (取得に失敗して古いファイルが走らないように)。
Say "  `$f = `"`$env:TEMP\yuragi-uninstall.ps1`"; Remove-Item `$f -ErrorAction Ignore; iwr -UseBasicParsing https://github.com/$Repo/releases/download/$Tag/uninstall.ps1 -OutFile `$f; if (`$?) { powershell -ExecutionPolicy Bypass -File `$f }"
Say "  学習データ・登録した単語・設定 ($UserData) は残ります。"
exit 0
