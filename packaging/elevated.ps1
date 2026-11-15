# yuragi: the only part that runs as administrator (REDESIGN §8.1).
# setup.ps1 / uninstall.ps1 pass this script's text with -EncodedCommand (never
# a path the user can rewrite) and read the result file. Three things only:
#   install:   put the DLL, the broker and this script in Program Files\yuragi-ime\<tag>\
#              (hashes checked where they land), register the DLL, read it back,
#              remove the other versions there
#   uninstall: unregister, read it back, remove Program Files\yuragi-ime
# A file that cannot be deleted (a DLL that apps have loaded) is renamed into
# Program Files\yuragi-ime\.trash\: Windows lets a loaded DLL be renamed, not deleted,
# so its place is free at once. Windows is asked to delete it at the next start; some
# PCs refuse every such request, so each later run of this script also empties .trash.
# No Python runs here.
param(
    [Parameter(Mandatory = $true)][ValidateSet("install", "uninstall")][string]$Action,
    [Parameter(Mandatory = $true)][string]$ResultFile,
    [string]$Tag = "",
    [string]$DllSource = "",
    [string]$DllSha256 = "",
    [string]$BrokerSource = "",
    [string]$BrokerSha256 = "",
    [string]$ScriptSource = "",
    [string]$ScriptSha256 = ""
)
$ErrorActionPreference = "Stop"
$Clsid = "{A7C4E201-0B3A-4F11-9E61-0C1A0B7E0A01}"
$Root = Join-Path $env:ProgramFiles "yuragi-ime"
$InprocKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$Clsid\InprocServer32"
$Trash = Join-Path $Root ".trash"
$pending = New-Object System.Collections.ArrayList   # moved into .trash, still in use

Add-Type -Namespace YuragiElevated -Name Native -MemberDefinition @'
[DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool MoveFileEx(string existing, string replacement, int flags);
'@

function Write-Result([bool]$ok, [string]$message) {
    $result = [ordered]@{ ok = $ok; message = $message; pending_delete = @($pending) }
    [IO.File]::WriteAllText($ResultFile, ($result | ConvertTo-Json -Depth 3), (New-Object Text.UTF8Encoding($false)))
    if ($ok) { exit 0 } else { exit 1 }
}

function Get-Sha256([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() }

function Get-Win32Message {
    $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    return "Win32 エラー ${code}: $((New-Object ComponentModel.Win32Exception($code)).Message)"
}

# A file that cannot be deleted now (in use) goes into .trash under a unique name.
function Move-ToTrash([string]$path) {
    New-Item -ItemType Directory -Force $Trash | Out-Null
    $dest = Join-Path $Trash ([Guid]::NewGuid().ToString("N") + "-" + (Split-Path $path -Leaf))
    if (-not [YuragiElevated.Native]::MoveFileEx($path, $dest, 0)) {
        throw "$path を削除も移動もできませんでした ($(Get-Win32Message))"
    }
    # MOVEFILE_DELAY_UNTIL_REBOOT. If Windows refuses, a later run empties .trash.
    [void][YuragiElevated.Native]::MoveFileEx($dest, $null, 4)
    [void]$pending.Add($dest)
}

# What is left in .trash from earlier runs, deleted once no app has it loaded.
function Clear-Trash {
    if (-not (Test-Path -LiteralPath $Trash)) { return }
    foreach ($item in @(Get-ChildItem -LiteralPath $Trash -Force)) {
        try { Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction Stop } catch { }
    }
    if (-not @(Get-ChildItem -LiteralPath $Trash -Force).Count) { Remove-Item -LiteralPath $Trash -Force }
}

# Removed now; what is in use goes into .trash. Nothing half-deleted is left in place,
# and nobody is asked to sign out or restart (§8.3).
function Remove-OrTrash([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    try { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop; return } catch { }
    $item = Get-Item -LiteralPath $path -Force
    $files = @($item)
    if ($item -is [IO.DirectoryInfo]) { $files = @(Get-ChildItem -LiteralPath $path -Recurse -Force -File) }
    foreach ($file in $files) {
        try { Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop } catch { Move-ToTrash $file.FullName }
    }
    # Only empty folders are left.
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}

# Copied next to its place, checked there (only administrators write there),
# then given its name. An identical file already in place (in use) is kept; a
# different one in use (the same version installed again) goes into .trash first.
function Place([string]$source, [string]$sha256, [string]$dest) {
    if ((Test-Path -LiteralPath $dest) -and (Get-Sha256 $dest) -eq $sha256.ToLower()) { return }
    $tmp = "$dest.new"
    Copy-Item -LiteralPath $source -Destination $tmp -Force
    if ((Get-Sha256 $tmp) -ne $sha256.ToLower()) {
        Remove-Item -LiteralPath $tmp -Force
        throw "SHA-256 mismatch for $(Split-Path $dest -Leaf)"
    }
    Remove-OrTrash $dest
    Move-Item -LiteralPath $tmp -Destination $dest
}

function Registered() {
    $key = Get-ItemProperty -LiteralPath $InprocKey -ErrorAction SilentlyContinue
    if ($key) { return $key.'(default)' }
    return $null
}

try {
    Clear-Trash
    if ($Action -eq "install") {
        $dir = Join-Path $Root $Tag
        New-Item -ItemType Directory -Force $dir | Out-Null
        $dll = Join-Path $dir "yuragi_tip.dll"
        Place $DllSource $DllSha256 $dll
        Place $BrokerSource $BrokerSha256 (Join-Path $dir "yuragi-broker.exe")
        # uninstall.ps1 runs this copy: only administrators can change it there.
        Place $ScriptSource $ScriptSha256 (Join-Path $dir "elevated.ps1")
        $proc = Start-Process "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList @("/s", "`"$dll`"") -Wait -PassThru
        if ($proc.ExitCode -ne 0) { Write-Result $false "regsvr32 が失敗しました (終了コード $($proc.ExitCode))" }
        # I-6: registered is what the registry says, read back.
        if ((Registered) -ne $dll) { Write-Result $false "登録後のレジストリに $dll がありません" }
        foreach ($old in @(Get-ChildItem -LiteralPath $Root -Force | Where-Object { $_.Name -ne $Tag -and $_.Name -ne ".trash" })) {
            Remove-OrTrash $old.FullName
        }
    } else {
        $dll = Registered
        if ($dll) {
            $proc = Start-Process "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList @("/u", "/s", "`"$dll`"") -Wait -PassThru
            if ($proc.ExitCode -ne 0 -or (Registered)) {
                Write-Result $false "$dll の登録解除に失敗しました (regsvr32 終了コード $($proc.ExitCode))"
            }
        }
        if (Test-Path -LiteralPath $Root) {
            foreach ($item in @(Get-ChildItem -LiteralPath $Root -Force | Where-Object { $_.Name -ne ".trash" })) {
                Remove-OrTrash $item.FullName
            }
            # Program Files\yuragi-ime stays only while .trash holds a file in use.
            if (-not @(Get-ChildItem -LiteralPath $Root -Force).Count) { Remove-Item -LiteralPath $Root -Force }
        }
    }
    Write-Result $true "done"
} catch {
    Write-Result $false $_.Exception.Message
}
