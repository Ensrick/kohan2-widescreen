# Kohan II widescreen - Steam launch-options wrapper (set-and-forget mode).
#
# One-time install: Steam > Library > Kohan II: Kings of War > Properties >
# General > Launch Options:
#
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\danjo\source\repos\kohan2-widescreen\tools\k2ws-steam.ps1" %command%
#
# Steam then runs THIS script in place of the game. It starts the real game command
# (as a child, inheriting Steam's environment, so SteamStub decrypts normally),
# applies the aspect patch the moment the code is decrypted, and stays resident
# keeping the correction factor synced to the live window size until the game exits
# (so a 4:3 splash window or an in-game resolution change never leaves a stale k).
#
# Nothing on disk is modified. To uninstall, clear the launch options.
# Requires Python 3 on PATH (`py -3`); k2patch.py/k2mem.py live next to this script.

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($args.Count -lt 1) {
    throw 'usage: k2ws-steam.ps1 <game exe> [args...]  (Steam launch options: ... %command%)'
}
$Exe = $args[0]
$Rest = @($args | Select-Object -Skip 1)
$GameDir = Split-Path -Parent $Exe
$LogDir = Join-Path $GameDir 'Logs'
$Log = Join-Path $LogDir 'k2widescreen.log'

function Say($m) {
    $line = '{0}  [k2ws-steam] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Write-Host $line
    if (Test-Path $LogDir) { try { Add-Content -Path $Log -Value $line } catch {} }
}

# --- 1. start the real game command -------------------------------------------------
if ($Rest.Count) {
    $proc = Start-Process -FilePath $Exe -ArgumentList $Rest -WorkingDirectory $GameDir -PassThru
} else {
    $proc = Start-Process -FilePath $Exe -WorkingDirectory $GameDir -PassThru
}
Say "launched '$Exe' pid=$($proc.Id)"

Start-Sleep -Seconds 3
if ($proc.HasExited) {
    Say (("game exited immediately (exit={0}). SteamStub may refuse a wrapped launch: " +
          "clear the Steam launch options and use k2widescreen.ps1 -AttachOnly instead.") -f $proc.ExitCode)
    exit 1
}

# --- 2. install the native-16:9 frustum patch once decrypted --------------------------
# frustumpatch detours the projection builder, so it self-maintains across every
# camera rebuild (no resident watcher needed) and widens the DRAW extent too, not just
# the displayed projection. Wait-and-attach returns as soon as the process exits, so
# this call blocks for the whole session.
& py -3 (Join-Path $Here 'frustumpatch.py') --apply --wait --pid $proc.Id 2>&1 |
    ForEach-Object { Say $_ }
if ($LASTEXITCODE -ne 0) {
    Say "frustum patch exited with code $LASTEXITCODE (game runs unpatched this session)"
    exit $LASTEXITCODE
}
# keep the wrapper alive until the game closes so Steam shows 'running'
while (-not $proc.HasExited) { Start-Sleep -Seconds 5 }
Say 'session over'
