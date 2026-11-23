# yuragi: the only part that runs as administrator (DESIGN「共通の仕組み」).
# setup.ps1 / uninstall.ps1 run this script by its path through -EncodedCommand
# (the arguments survive any path) and read the result file. Three things only:
#   install:   put the DLLs (64- and 32-bit), the broker and this script in
#              Program Files\yuragi-ime\<tag>\, register the DLLs,
#              remove the other versions there
#   uninstall: unregister, remove Program Files\yuragi-ime
# A file that cannot be deleted (a DLL that apps have loaded) is left where it is:
# every version has its own folder, so the next run removes it.
# No Python runs here.
param(
    [Parameter(Mandatory = $true)][ValidateSet("install", "uninstall")][string]$Action,
    [Parameter(Mandatory = $true)][string]$ResultFile,
    [string]$Tag = "",
    [string]$DllSource = "",
    [string]$Dll32Source = "",
    [string]$BrokerSource = "",
    [string]$ScriptSource = ""
)
$ErrorActionPreference = "Stop"
$Clsid = "{A7C4E201-0B3A-4F11-9E61-0C1A0B7E0A01}"
$Root = Join-Path $env:ProgramFiles "yuragi-ime"
# The 64-bit build for 64-bit applications, the 32-bit one for 32-bit applications
# (DESIGN「32 ビットのアプリ」): one CLSID, a COM registration in each registry view,
# one TSF profile shared by both.
$Views = @(
    @{ Key = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$Clsid\InprocServer32"
       Regsvr = "$env:SystemRoot\System32\regsvr32.exe"; Name = "yuragi_tip.dll" },
    @{ Key = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Classes\CLSID\$Clsid\InprocServer32"
       Regsvr = "$env:SystemRoot\SysWOW64\regsvr32.exe"; Name = "yuragi_tip32.dll" }
)
function Write-Result([bool]$ok, [string]$message) {
    $result = [ordered]@{ ok = $ok; message = $message }
    [IO.File]::WriteAllText($ResultFile, ($result | ConvertTo-Json -Depth 3), (New-Object Text.UTF8Encoding($false)))
    if ($ok) { exit 0 } else { exit 1 }
}

# An identical file already there (in use) is kept.
function Place([string]$source, [string]$dest) {
    if ((Test-Path -LiteralPath $dest) -and (Get-FileHash -LiteralPath $dest).Hash -eq (Get-FileHash -LiteralPath $source).Hash) { return }
    Copy-Item -LiteralPath $source -Destination $dest -Force
}

function Registered($view) {
    $key = Get-ItemProperty -LiteralPath $view.Key -ErrorAction SilentlyContinue
    if ($key) { return $key.'(default)' }
    return $null
}

try {
    if ($Action -eq "install") {
        # setup.ps1 sent quit to the user's broker just before this (this session): wait for it
        # to end, so that its exe is replaced or removed with the rest of its version.
        $deadline = (Get-Date).AddSeconds(15)
        $session = (Get-Process -Id $PID).SessionId
        foreach ($broker in @(Get-Process -Name "yuragi-broker" -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session })) {
            [void]$broker.WaitForExit([Math]::Max(0, [int]($deadline - (Get-Date)).TotalMilliseconds))
        }
        $dir = Join-Path $Root $Tag
        New-Item -ItemType Directory -Force $dir | Out-Null
        Place $DllSource (Join-Path $dir $Views[0].Name)
        Place $Dll32Source (Join-Path $dir $Views[1].Name)
        Place $BrokerSource (Join-Path $dir "yuragi-broker.exe")
        # uninstall.ps1 runs this copy.
        Place $ScriptSource (Join-Path $dir "elevated.ps1")
        # The 32-bit one first: the profile (shared) then names the 64-bit DLL for its icon.
        foreach ($view in @($Views[1], $Views[0])) {
            $dll = Join-Path $dir $view.Name
            $proc = Start-Process $view.Regsvr -ArgumentList @("/s", "`"$dll`"") -Wait -PassThru
            if ($proc.ExitCode -ne 0) { Write-Result $false "regsvr32 ($($view.Name)) が失敗しました (終了コード $($proc.ExitCode))" }
        }
        foreach ($old in @(Get-ChildItem -LiteralPath $Root -Force | Where-Object { $_.Name -ne $Tag })) {
            Remove-Item -LiteralPath $old.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    } else {
        # A version from before the 32-bit build has the 64-bit one only.
        foreach ($view in $Views) {
            $dll = Registered $view
            if (-not $dll) { continue }
            $proc = Start-Process $view.Regsvr -ArgumentList @("/u", "/s", "`"$dll`"") -Wait -PassThru
            if ($proc.ExitCode -ne 0) {
                Write-Result $false "$dll の登録解除に失敗しました (regsvr32 終了コード $($proc.ExitCode))"
            }
        }
        Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Result $true "done"
} catch {
    Write-Result $false $_.Exception.Message
}
