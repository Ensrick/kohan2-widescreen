# Kohan II: Kings of War - widescreen aspect-ratio loader.
#
# Launches the game and patches the projection builder in memory so the 3D world uses
# the true backbuffer aspect instead of the engine's hardcoded 4:3. Nothing on disk is
# modified: k2.exe is SteamStub-encrypted and is never touched.
#
# Normal use (game on your screen, your configured resolution):
#     .\k2widescreen.ps1
#
# Attach to an already-running game instead of launching one:
#     .\k2widescreen.ps1 -AttachOnly
#
# Force a specific aspect rather than deriving it from the window:
#     .\k2widescreen.ps1 -Aspect 16:9
#
# Development mode - runs the game parked outside the virtual screen so it is never
# visible and never takes focus (used to verify the patch without showing the game):
#     .\k2widescreen.ps1 -Parked
#
# Requires: the Steam client running (SteamStub will not decrypt otherwise), and
# Python 3 on PATH (`py -3`).

param(
    [switch]$Parked,
    [switch]$AttachOnly,
    [string]$Aspect = '',
    [switch]$Revert,
    [int]$TimeoutSec = 120
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$GameDir = "C:\Program Files (x86)\Steam\steamapps\common\Kohan II"
$LogDir = Join-Path $GameDir 'Logs'
$Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

function Say($m) { Write-Host "[k2widescreen] $m" }

if ($Revert) {
    py -3 (Join-Path $Here 'k2patch.py') --revert
    return
}

# --- 1. launch (or find) the game --------------------------------------------------
$proc = Get-Process k2 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($AttachOnly) {
    if (-not $proc) { throw "-AttachOnly given but k2.exe is not running." }
    Say "attaching to running k2.exe pid=$($proc.Id)"
    $k2pid = $proc.Id
} elseif ($proc) {
    Say "k2.exe already running (pid=$($proc.Id)); attaching instead of launching"
    $k2pid = $proc.Id
} else {
    if (-not (Get-Process steam -ErrorAction SilentlyContinue)) {
        throw "Steam client is not running - SteamStub cannot decrypt k2.exe. Start Steam first."
    }
    if ($Parked) {
        $k2pid = & (Join-Path $Here 'k2launch.ps1') -Mode Parked -ParkSeconds $TimeoutSec |
                 Select-Object -Last 1
    } else {
        # Launch through Steam: k2.exe is SteamStub-wrapped and CRASHES if started
        # directly (the stub needs Steam as its parent to decrypt). The game appears
        # normally on your screen at your configured resolution.
        Say "launching via Steam (steam://rungameid/97130)"
        Start-Process "steam://rungameid/97130" | Out-Null
        $deadline = (Get-Date).AddSeconds($TimeoutSec)
        while ((Get-Date) -lt $deadline) {
            $p = Get-Process k2 -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($p) { $k2pid = $p.Id; break }
            Start-Sleep -Milliseconds 400
        }
        if (-not $k2pid) { throw "k2.exe did not start within $TimeoutSec s (is Steam logged in?)" }
    }
    Say "launched k2.exe pid=$k2pid"
}

# --- 2. wait for SteamStub to decrypt, then patch ----------------------------------
Say "waiting for SteamStub to decrypt .text, then patching..."
$patchArgs = @((Join-Path $Here 'k2patch.py'), '--apply', '--wait', '--pid', "$k2pid")
if ($Aspect) { $patchArgs += @('--aspect', $Aspect) }
$out = & py -3 @patchArgs 2>&1
$out | ForEach-Object { Write-Host "  $_" }

if ($LASTEXITCODE -ne 0) { throw "patch failed (see output above)" }

# --- 3. record the result ----------------------------------------------------------
$logLine = "$Stamp  pid=$k2pid  " + (($out | Where-Object { $_ -match 'real aspect|->' }) -join ' | ')
Add-Content -Path (Join-Path $LogDir 'k2widescreen.log') -Value $logLine
Say "done. Patch is in memory for this session only; run it again next launch."
