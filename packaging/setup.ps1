# ゆらぎのインストールと更新。手順は DESIGN「インストール・更新・アンインストール」
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1 [-Yes] [-Cpu]
#
# -AssetDir: リリースのアセット (DLL 2 つ・ブローカー・ソース zip・tkinter) を GitHub からではなく
#   このフォルダから取る (公開前の版を実機で試すため)。
# -Cpu: NVIDIA の GPU があっても CPU 版の PyTorch を使う (GPU のドライバが不安定な PC など)。
#
# インストールも更新も同じ手順。利用者のデータ (%USERPROFILE%\.yuragi-ime) は消さない (DESIGN「守ること」7)。

param(
    [switch]$Yes,
    [switch]$Cpu,
    [string]$AssetDir = ""
)

# PowerShell 7 (pwsh) から起動されたら、Windows PowerShell 5.1 で起動し直す。
if ($PSVersionTable.PSEdition -eq "Core") {
    $relaunch = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if ($Yes) { $relaunch += "-Yes" }
    if ($Cpu) { $relaunch += "-Cpu" }
    if ($AssetDir) { $relaunch += @("-AssetDir", $AssetDir) }
    & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" @relaunch
    exit $LASTEXITCODE
}

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 の Invoke-WebRequest は進行表示を描くたびに遅くなる (数十 MB で数分)。
$ProgressPreference = "SilentlyContinue"
if ($AssetDir) { $AssetDir = (Resolve-Path -LiteralPath $AssetDir).Path }
# この中で動かす Python は UTF-8 で入出力する (このプロセスの中だけ)。
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo = "sadaoikebe/yuragi"
$Tag = "__TAG__"                         # リリース時に workflow が刻む
$EmbedPythonVersion = "3.13.7"
$EmbedPythonSha256 = "__EMBED_SHA256__"  # 同上 (python.org の公式 zip の SHA-256)
$TorchVersion = "2.9.1"
# torch の wheel (CPython 3.13・64 ビット Windows) の SHA-256。種類ごとに 1 つ。torch は --no-deps で入れ、
# その依存は packaging\requirements.txt に (ハッシュ付きで) ある。版を上げたら 3 つとも取り直す。
$TorchSha256 = @{
    cpu = "404a7ab2fffaf2ca069e662f331eb46313692b2f1630df2720094284f390ccef"
    cu126 = "625703f377a53e20cade81291ac742f044ea46a1e86a3949069e62e321025ba3"
    cu128 = "ad9183864acdd99fc5143d7ca9d3d2e7ddfc9a9600ff43217825d4e5e9855ccc"
}
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
$script:SwitchCompleted = $false
function Fail([string]$msg) {
    Write-Host "エラー: $msg" -ForegroundColor Red
    if ($script:SwitchCompleted) {
        Write-Host "新しい版への切り替えは済んでいます。その後の処理でエラーが発生しました。"
    } else {
        Write-Host "新しい版への切り替えを完了できませんでした。"
    }
    Write-Host "セットアップを再実行してください。"
    exit 1
}
# Fail を通らない失敗 (予期しない例外) も同じ形で表示して止める。
trap { Fail $_.Exception.Message }
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

# PyTorch の版の選び方 (torch 2.9.1 の CUDA 版の配布物に合わせる)。nvidia-smi の出力から決める。
#   $SmiHeader: nvidia-smi の通常の出力 ("CUDA Version: 12.8" = ドライバが扱える CUDA の上限。
#               ドライバ 610 系からは "CUDA UMD Version: 13.3")
#   $SmiGpus:   nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader の行
# cu128 は Volta より前の GPU を含まないので Turing (7.5) 以降に限る。cu126 は Pascal (6.0) から。
# 判定できないものは CPU 版。CUDA 版でも、エンジンは GPU で計算できなければ CPU で動く。
function Select-TorchVariant([string]$SmiHeader, [string[]]$SmiGpus) {
    if ($SmiHeader -notmatch "CUDA (?:UMD )?Version:\s*(\d+)\.(\d+)") { return "cpu" }
    $cuda = [int]$Matches[1] * 100 + [int]$Matches[2]
    $variant = "cpu"
    foreach ($line in $SmiGpus) {
        if ($line -match ",\s*(\d+)\.(\d+)\s*$") {
            $cap = [int]$Matches[1] * 10 + [int]$Matches[2]
            if ($cap -ge 75 -and $cuda -ge 1208) { return "cu128" }
            if ($cap -ge 60 -and $cap -lt 100 -and $cuda -ge 1206) { $variant = "cu126" }
        }
    }
    return $variant
}

# この PC の NVIDIA GPU を nvidia-smi (NVIDIA のドライバに付属) で調べる。無ければ CPU 版。
# ドライバはあるのに GPU が見えない (ノート PC で GPU を切っている、など) ときは $script:GpuOff。
$script:GpuOff = $false
function Get-TorchVariant {
    $smi = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source
    if (-not $smi) {
        $smi = @((Join-Path $env:SystemRoot "System32\nvidia-smi.exe"),
                 (Join-Path $env:ProgramFiles "NVIDIA Corporation\NVSMI\nvidia-smi.exe")) |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $smi) { return "cpu" }
    # nvidia-smi の stderr を Windows PowerShell 5.1 が止める誤りにしないように。
    $ErrorActionPreference = "Continue"
    try {
        $header = (& $smi 2>$null) -join "`n"
        if ($LASTEXITCODE -ne 0) { $script:GpuOff = $true; return "cpu" }
        $gpus = @(& $smi "--query-gpu=name,compute_cap" "--format=csv,noheader" 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $gpus.Count) { $script:GpuOff = $true; return "cpu" }
    } catch { return "cpu" }
    return (Select-TorchVariant $header $gpus)
}

# 配布用のスクリプトであることと、動作環境を確認する。
if ($Tag -like "__*" -or $EmbedPythonSha256 -like "__*") {
    Fail "この setup.ps1 はリリース版ではありません。リリースページの setup.ps1 を使ってください。"
}

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
$TorchVariant = if ($Cpu) { "cpu" } else { Get-TorchVariant }
if ($Cpu) {
    Say "  -Cpu: CPU 版 PyTorch を使います"
} elseif ($TorchVariant -ne "cpu" -and $free -lt 10GB) {
    Say "  CUDA 対応の GPU がありますが、GPU 版 PyTorch にはディスクの空きが 10GB 要るため CPU 版を使います"
    $TorchVariant = "cpu"
} elseif ($TorchVariant -ne "cpu") {
    Say "  CUDA 対応の GPU があります: GPU 版 PyTorch ($TorchVariant) を使います"
} elseif ($script:GpuOff) {
    Say "  NVIDIA のドライバはありますが、GPU が見えません (GPU を切る設定になっているなど): CPU 版 PyTorch を使います"
    Say "  GPU を使うには、GPU を有効にしてから、もう一度インストールの 1 行を実行してください"
} else {
    Say "  CUDA 対応の GPU はありません: CPU 版 PyTorch を使います"
}
$TorchIndex = "https://download.pytorch.org/whl/$TorchVariant"
Say ""
Say "次のものをダウンロードします (取得済みのものは省略):"
Say "  ゆらぎ本体・TIP・ブローカー・tkinter (GitHub Releases、約 35MB)"
Say "  Python $EmbedPythonVersion (python.org、約 30MB)"
if ($TorchVariant -eq "cpu") {
    Say "  PyTorch $TorchVersion CPU 版 (download.pytorch.org、約 200MB)"
} else {
    Say "  PyTorch $TorchVersion GPU 版 $TorchVariant (download.pytorch.org、約 3GB。展開後 約 5GB)"
}
Say "  transformers・huggingface_hub ほか (PyPI)"
Say "  Mozc 辞書 (github.com/google/mozc、約 93MB)"
Say "  言語モデル zenz-v2.5-small (CPU 用、huggingface.co、約 170MB)"
if ($TorchVariant -ne "cpu") { Say "  言語モデル zenz-v2.5-medium (GPU 用、huggingface.co、約 620MB)" }
if (-not (Ask "続行しますか?")) { Fail "キャンセルしました。" }

function Get-Asset([string]$url, [string]$dest) {
    if ($AssetDir) { Copy-Item -LiteralPath (Join-Path $AssetDir ($url.Split("/")[-1])) -Destination $dest }
    else { Invoke-WebRequest -UseBasicParsing $url -OutFile $dest }
}

# 共有物は無ければ作る。作りかけの名前で作って、できたら改名する (途中で止まったものは次に作り直す)。
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
        python = $script:Python
        pythonw = (Join-Path (Split-Path $script:Python) "pythonw.exe")
        app = $app
        args = @("-c", $Boot, "yuragi.engine", "--dict-dir", $script:Dict,
                 "--cache-dir", $script:Cache) + $script:ModelArgs + $extra
        admin_args = @("-c", $Boot, "yuragi.ime.admin_ui", "--dict-dir", $script:Dict)
    }
    [IO.File]::WriteAllText($path, ($engine | ConvertTo-Json -Depth 4), $Utf8NoBom)
}

# 配布物を作業フォルダーに取得して展開する。
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
$dll32Path = Join-Path $Download "yuragi_tip32.dll"  # 32 ビットのアプリ用 (DESIGN「32 ビットのアプリ」)
$brokerPath = Join-Path $Download "yuragi-broker.exe"
Get-Asset "$baseUrl/yuragi-source.zip" $sourceZip
Get-Asset "$baseUrl/yuragi_tip.dll" $dllPath
Get-Asset "$baseUrl/yuragi_tip32.dll" $dll32Path
Get-Asset "$baseUrl/yuragi-broker.exe" $brokerPath
$StageApp = Join-Path $Stage "app"
Expand-Archive -LiteralPath $sourceZip -DestinationPath $StageApp

# 同梱ランタイム: Python の版・依存の固定・torch の版で名前が決まる。中身が同じなら共有する。
# 「tk」は tkinter 一式 (リリースのアセット。同じ版の通常版 Python から取ったもの) 入りの印。
$requirements = Join-Path $StageApp "packaging\requirements.txt"
$reqHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash.Substring(0, 12).ToLower()
# CPU 版は従来の名前のまま (既存のランタイムを使い続ける)。GPU 版は名前に印を付けて別に作る。
$torchId = if ($TorchVariant -eq "cpu") { "torch$TorchVersion" } else { "torch$TorchVersion-$TorchVariant" }
$runtimeId = "py$EmbedPythonVersion-tk-$torchId-$reqHash"
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
    Get-Asset "$baseUrl/python-$EmbedPythonVersion-tkinter-amd64.zip" $tkZip
    Expand-Archive -LiteralPath $tkZip -DestinationPath $dir
    $pth = Get-ChildItem -LiteralPath $dir -Filter "python*._pth" | Select-Object -First 1 -ExpandProperty FullName
    @(("python" + $EmbedPythonVersion.Substring(0, 4).Replace(".", "") + ".zip"), ".", "Lib", "Lib\site-packages", "import site") |
        Set-Content -LiteralPath $pth -Encoding ASCII
    $py = Join-Path $dir "python.exe"
    $getPip = Join-Path $Download "get-pip.py"
    Invoke-WebRequest -UseBasicParsing "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
    # pip は利用者の設定 (pip.ini・PIP_* の環境変数) もキャッシュも使わない (--isolated --no-cache-dir)。
    # PIP_REQUIRE_VIRTUALENV などがあると入らず、PIP_INDEX_URL などがあると取得先が変わるため。
    Invoke-Checked "pip のインストール" { & $py $getPip --isolated --no-cache-dir --no-warn-script-location }
    # 版とハッシュを固定して入れる (--require-hashes: 書いていないもの・ハッシュの違うものは入らない)。
    $torchRequirement = Join-Path $Download "torch-requirement.txt"
    "torch==$TorchVersion --hash=sha256:$($TorchSha256[$TorchVariant])" | Set-Content -LiteralPath $torchRequirement -Encoding ASCII
    Invoke-Checked "PyTorch $TorchVersion ($TorchVariant) のインストール" {
        & $py -m pip install --isolated --no-cache-dir --no-warn-script-location --require-hashes --no-deps --index-url $TorchIndex -r $torchRequirement
    }
    Invoke-Checked "依存パッケージのインストール" {
        & $py -m pip install --isolated --no-cache-dir --no-warn-script-location --require-hashes -r $requirements
    }
    if ($TorchVariant -ne "cpu") {
        # 情報だけ。モデルを暖機できるデバイスはエンジンが判定する。
        & $py -c "import torch; print('  CUDA devices visible to torch:', torch.cuda.device_count())"
    }
}
$script:Python = Join-Path $Runtime "python.exe"

# 辞書の置き場所の名前は、マニフェストのファイル一覧のハッシュ (キャッシュの名前と同じもの)。
# 辞書が変われば必ず別の名前になる。
Push-Location -LiteralPath $StageApp
try {
    $dictId = & $script:Python -c "import os,sys; sys.path.insert(0, os.getcwd()); from yuragi.lattice.mozc_dict import files_digest; print(files_digest())"
} finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { Fail "辞書マニフェストを読めませんでした。" }
$script:Dict = Join-Path $Shared "dict\$dictId"
New-Shared $script:Dict {
    param($dir)
    Invoke-Checked "Mozc 辞書のダウンロード" {
        Invoke-App $script:Python $StageApp @("tools.eval.fetch_mozc_dict", "--out", $dir)
    }
    Invoke-Checked "Mozc 辞書の SHA-256 照合" {
        Invoke-App $script:Python $StageApp @("yuragi.lattice.dict_manifest", "verify", "--dict-dir", $dir)
    }
}
# 言語モデル (CONVERSION「装置とモデル」): CPU 用の small は常に、GPU 版 PyTorch なら GPU 用の medium も。
# どれを使うかは、エンジンが起動のたびに実測して決める。
# 引数名は $modelName: 中で呼ぶ Invoke-Checked の $name に隠されないように。
function Get-Model([string]$modelName) {
    $line = Select-String -LiteralPath (Join-Path $StageApp "packaging\fetch_model.py") -Pattern "^MODEL_$modelName = \(`"([^`"]+)`", `"([0-9a-f]+)`"\)"
    if (-not $line) { Fail "packaging\fetch_model.py に MODEL_$modelName がありません。" }
    $repo = $line.Matches[0].Groups[1].Value
    $dir = Join-Path $Shared "model\$($line.Matches[0].Groups[2].Value)"
    $fetchModel = Join-Path $StageApp "packaging\fetch_model.py"
    New-Shared $dir {
        param($partial)
        Invoke-Checked "言語モデルのダウンロード ($repo)" { & $script:Python $fetchModel $modelName $partial }
    } | Out-Host   # the download's output must not become this function's value
    return $dir
}
$script:Models = @(Get-Model "small")
$script:ModelArgs = @("--lm-cpu-model", $script:Models[0])
if ($TorchVariant -ne "cpu") {
    $medium = Get-Model "medium"
    $script:Models += $medium
    $script:ModelArgs = @("--lm-model", $medium) + $script:ModelArgs
}
$script:Cache = Join-Path $Shared "cache"
New-Item -ItemType Directory -Force $script:Cache | Out-Null

# 専用のフォルダーで試運転し、利用者の学習履歴や個人辞書から分ける。
$selftestData = Join-Path $Stage "selftest-data"
New-Item -ItemType Directory -Force $selftestData | Out-Null
$stageEngine = Join-Path $Stage "engine.json"
# --require-lm: LM を読み込んで暖機できなければ失敗にする (LM なしのまま「完了」にしない)。
Write-EngineJson $stageEngine $StageApp @("--data-dir", $selftestData, "--require-lm")
Say ""
Say "== 動作テスト (初回は辞書の準備に数分かかります)"
$selftestOut = Join-Path $Stage "selftest.txt"
$proc = Start-Process -FilePath $brokerPath -ArgumentList @("--selftest", "`"$stageEngine`"", "--data-dir", "`"$selftestData`"") `
    -Wait -PassThru -RedirectStandardOutput $selftestOut
if ($proc.ExitCode -ne 0) {
    Fail "動作テストが失敗しました (終了コード $($proc.ExitCode))。ログ: $(Join-Path $selftestData 'logs')"
}
Say "  変換  OK"

# 終了依頼と起動確認に使うブローカーの接続を扱う。
function Connect-Broker([int]$timeoutMs) {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $session = (Get-Process -Id $PID).SessionId
    $pipe = New-Object System.IO.Pipes.NamedPipeClientStream(".", "yuragi-ime-$sid-$session", [IO.Pipes.PipeDirection]::InOut)
    try { $pipe.Connect($timeoutMs) } catch { $pipe.Dispose(); return $null }
    $writer = New-Object IO.StreamWriter($pipe, $Utf8NoBom)
    $writer.AutoFlush = $true
    $writer.NewLine = "`n"
    $reader = New-Object IO.StreamReader($pipe, $Utf8NoBom)
    $writer.WriteLine('{"op":"hello","proto":1}')
    return @{ Pipe = $pipe; Reader = $reader; Writer = $writer }
}
function Read-BrokerLine($conn, [int]$timeoutMs) {
    $task = $conn.Reader.ReadLineAsync()
    if ($task.Wait($timeoutMs)) { return $task.Result }
    return $null
}
# 返事を 1 行読んでから quit を送る (読まずに閉じると quit が届かないことがある)。
function Send-Quit {
    $conn = Connect-Broker 1000
    if ($conn) {
        [void](Read-BrokerLine $conn 2000)
        try { $conn.Writer.WriteLine('{"op":"quit"}') } catch { }
        $conn.Pipe.Dispose()
    }
}
function Stop-Broker {
    Send-Quit
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

# 試運転を終えたファイルをインストール先に移す。
$Version = Join-Path $Versions $Tag
New-Item -ItemType Directory -Force $Versions | Out-Null
if (Test-Path -LiteralPath $Version) {
    if ((Get-ItemProperty -LiteralPath $ProductKey -ErrorAction SilentlyContinue).Tag -eq $Tag) {
        # 同じ版の入れ直し: その版のエンジンが作業フォルダを使っているので先に止める。
        Say "  同じ版 ($Tag) を再インストールします"
        Stop-Broker
    }
    $aside = "$Version.old-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
    Rename-Item -LiteralPath $Version -NewName (Split-Path $aside -Leaf)
}
Move-Item -LiteralPath $Stage -Destination $Version
Remove-Item -LiteralPath (Join-Path $Version "selftest-data") -Recurse -Force -ErrorAction SilentlyContinue
$App = Join-Path $Version "app"
Write-EngineJson (Join-Path $Version "engine.json") $App @()

# DLL の配置と登録を行うスクリプトを管理者権限で呼び出す。
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
$ElevatedPath = Join-Path $App "packaging\elevated.ps1"
function Invoke-Elevated([string[]]$arguments) {
    $resultFile = Join-Path $env:TEMP ("yuragi-elevated-" + [Guid]::NewGuid().ToString("N") + ".json")
    $encoded = New-ElevatedCommand $ElevatedPath ($arguments + @("-ResultFile", $resultFile))
    try {
        $p = Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -Wait -PassThru `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded)
    } catch {
        Fail "管理者権限の確認がキャンセルされました。"
    }
    if (-not (Test-Path -LiteralPath $resultFile)) {
        Fail "管理者権限の処理が結果を返さずに終了しました (終了コード $($p.ExitCode))。"
    }
    $result = Get-Content -LiteralPath $resultFile -Raw -Encoding UTF8 | ConvertFrom-Json
    Remove-Item -LiteralPath $resultFile -Force
    return $result
}

Say ""
Say "== Windows への登録 (管理者権限の確認が出ます)"
# 旧ブローカーを終わらせておく (elevated.ps1 は旧版を消す前にその終了を待つので、旧版の exe も消える)。
Send-Quit
$result = Invoke-Elevated @("-Action", "install", "-Tag", $Tag,
    "-DllSource", (Join-Path $Version "download\yuragi_tip.dll"),
    "-Dll32Source", (Join-Path $Version "download\yuragi_tip32.dll"),
    "-BrokerSource", (Join-Path $Version "download\yuragi-broker.exe"),
    "-ScriptSource", $ElevatedPath)
if (-not $result.ok) { Fail "Windows への登録に失敗しました: $($result.message)" }
$DllFinal = Join-Path $ProgramRoot "$Tag\yuragi_tip.dll"
$BrokerFinal = Join-Path $ProgramRoot "$Tag\yuragi-broker.exe"
Say "  登録: $DllFinal  OK"

# インストール済みの版と、サインイン時に起動するブローカーを更新する。
Say ""
Say "== 新しい版への切り替え"
Stop-Broker
New-Item -Force $ProductKey | Out-Null
Set-ItemProperty -LiteralPath $ProductKey -Name "Tag" -Value $Tag
# Run は他のアプリと共有するため、キーが無いときだけ作る。
if (-not (Test-Path -LiteralPath $RunKey)) {
    New-Item -Path $RunKey | Out-Null
}
Set-ItemProperty -LiteralPath $RunKey -Name "yuragi-ime" -Value "`"$BrokerFinal`""
$script:SwitchCompleted = $true
Add-Type -Namespace YuragiSetup -Name Input -MemberDefinition @'
[DllImport("input.dll", CharSet = CharSet.Unicode)]
public static extern bool InstallLayoutOrTip(string profile, uint flags);
'@
if (-not [YuragiSetup.Input]::InstallLayoutOrTip($Layout, 0)) { Fail "入力方法の一覧に追加できませんでした。" }

New-Item -ItemType Directory -Force $UserData | Out-Null

# 新しい変換エンジンが起動したことを、ブローカーの応答で確かめる。
Say ""
Say "== 起動確認 (最大 120 秒)"
Start-Process -FilePath $BrokerFinal
$deadline = (Get-Date).AddSeconds(120)
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
    $why = @{ starting = '120 秒以内に起動しませんでした'; down = '起動に失敗しました' }[$state]
    if (-not $why) { $why = '応答がありません' }
    Write-Host "ログ: $(Join-Path $UserData 'logs')。次回サインイン時にも起動を試みます。"
    Fail "変換エンジンが起動しませんでした ($why)。"
}
Say "  変換エンジン  OK"

# 新しい版が使うファイルを残し、旧版と作業ファイルを片付ける。
# 消せないもの (使用中) は残す。次回の setup がまた消す。
$keep = @($Runtime, $script:Dict) + $script:Models
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
$cleanup += @(Get-Item -LiteralPath (Join-Path $Version "download"), (Join-Path $Version "selftest.txt") -ErrorAction SilentlyContinue)
foreach ($item in $cleanup) { Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue }

Say ""
Say "ゆらぎ $Tag のインストールが完了しました。"
Say ""
Say "使い方: Win+Space で「ゆらぎ」を選ぶと、タスクバーに「ゆ」が表示されます。再起動は不要です。"
Say "更新: インストールと同じ 1 行を再実行します。"
Say "アンインストール (PowerShell):"
# 前回の残りを先に消し、取得できたときだけ実行する (取得に失敗して古いファイルが走らないように)。
Say "  `$f = `"`$env:TEMP\yuragi-uninstall.ps1`"; Remove-Item `$f -ErrorAction Ignore; iwr -UseBasicParsing https://github.com/$Repo/releases/download/$Tag/uninstall.ps1 -OutFile `$f; if (`$?) { powershell -ExecutionPolicy Bypass -File `$f }"
Say "  学習データ・登録した単語・設定 ($UserData) は残ります。"
exit 0
