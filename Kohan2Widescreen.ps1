# Kohan II: Kings of War - Widescreen / native-aspect fix (self-contained).
#
# No Python, no installs: this is the whole fix in one PowerShell file. It patches
# the running game IN MEMORY only - k2.exe on disk is never modified (it is Steam-DRM
# encrypted, so there is nothing on disk to edit and no cracked exe is shipped).
#
# WHAT IT DOES: the engine builds every 3D camera with a hardcoded 4:3 frustum and
# stretches it across your screen. This widens the frustum to your real screen aspect,
# so the world renders correctly (you see more at the sides - "Hor+"; vertical view is
# unchanged) and the terrain draws to the full width (no black bars).
#
# ------------------------------------------------------------------------------------
# EASIEST INSTALL (automatic, every launch): set it as a Steam launch option.
#   Steam > Library > right-click "Kohan II: Kings of War" > Properties >
#   General > Launch Options, paste exactly:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File "FULL\PATH\TO\Kohan2Widescreen.ps1" %command%
#
#   (replace FULL\PATH\TO with where you put this file). Play normally - done.
#
# MANUAL USE: launch the game yourself, get into a map, then run:
#     powershell -NoProfile -ExecutionPolicy Bypass -File Kohan2Widescreen.ps1
#   (double-click Apply-Widescreen.bat does exactly this.)
#
#   Force a specific aspect:   ... -File Kohan2Widescreen.ps1 -Aspect 16:9
#   Undo (until next launch):  ... -File Kohan2Widescreen.ps1 -Revert
# ------------------------------------------------------------------------------------

param(
    [string]$Aspect = '',        # e.g. "16:9"; default: read from the game window
    [switch]$Revert,
    [int]$TimeoutSec = 180,
    [string]$SelfTest = '',      # internal: dump cave hex for a given "cave,resume" and exit
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Command           # captures Steam's %command% (the game exe + args)
)

$ErrorActionPreference = 'Stop'

# ---- native process/memory API -----------------------------------------------------
Add-Type -Name WS -Namespace K2 -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint a, bool i, int pid);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int n, out int read);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool WriteProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int n, out int wrote);
[DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr VirtualAllocEx(IntPtr h, IntPtr addr, uint size, uint type, uint prot);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool VirtualProtectEx(IntPtr h, IntPtr addr, uint size, uint prot, out uint old);
[DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr CreateToolhelp32Snapshot(uint flags, int pid);
[DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenThread(uint a, bool i, uint tid);
[DllImport("kernel32.dll")] public static extern uint SuspendThread(IntPtr h);
[DllImport("kernel32.dll")] public static extern uint ResumeThread(IntPtr h);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
[DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
public struct RECT { public int left, top, right, bottom; }
[StructLayout(LayoutKind.Sequential)] public struct MODULEENTRY32 {
  public uint dwSize; public uint th32ModuleID; public uint th32ProcessID; public uint GlblcntUsage;
  public uint ProccntUsage; public IntPtr modBaseAddr; public uint modBaseSize; public IntPtr hModule;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string szModule;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst=260)] public string szExePath; }
[DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Auto)] public static extern bool Module32First(IntPtr h, ref MODULEENTRY32 e);
[DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Auto)] public static extern bool Module32Next(IntPtr h, ref MODULEENTRY32 e);
[StructLayout(LayoutKind.Sequential)] public struct THREADENTRY32 {
  public uint dwSize; public uint cntUsage; public uint th32ThreadID; public uint th32OwnerProcessID;
  public int tpBasePri; public int tpDeltaPri; public uint dwFlags; }
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool Thread32First(IntPtr h, ref THREADENTRY32 e);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool Thread32Next(IntPtr h, ref THREADENTRY32 e);
'@

$PROC_ALL = 0x1F0FFF
$PAGE_RWX = 0x40
$MEM_COMMIT_RESERVE = 0x3000
$TH32_MODULE = 0x8 -bor 0x10
$TH32_THREAD = 0x4
$THREAD_SUSPEND = 0x2

$PROJ_RVA   = 0x49545D
$RESUME_RVA = 0x495465
$DISPLACED  = [byte[]](0x8b,0x02,0x8d,0x8e,0x20,0x03,0x00,0x00)   # mov eax,[edx]; lea ecx,[esi+0x320]

function Say($m) { Write-Host "[widescreen] $m" }

function Get-K2 {
    Get-Process k2 -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Get-ModuleBase($pid) {
    $snap = [K2.WS]::CreateToolhelp32Snapshot($TH32_MODULE, $pid)
    if ($snap -eq [IntPtr]::Zero -or $snap.ToInt64() -eq -1) { return $null }
    try {
        $e = New-Object K2.WS+MODULEENTRY32; $e.dwSize = [uint32][System.Runtime.InteropServices.Marshal]::SizeOf($e)
        if (-not [K2.WS]::Module32First($snap, [ref]$e)) { return $null }
        do {
            if ($e.szModule -ieq 'k2.exe') { return $e.modBaseAddr.ToInt64() }
        } while ([K2.WS]::Module32Next($snap, [ref]$e))
    } finally { [K2.WS]::CloseHandle($snap) | Out-Null }
    return $null
}

function Read-Mem($h, [int64]$addr, [int]$n) {
    $buf = New-Object byte[] $n; $got = 0
    [void][K2.WS]::ReadProcessMemory($h, [IntPtr]$addr, $buf, $n, [ref]$got)
    return $buf[0..($got-1)]
}

function Write-Mem($h, [int64]$addr, [byte[]]$data) {
    $old = 0
    [void][K2.WS]::VirtualProtectEx($h, [IntPtr]$addr, [uint32]$data.Length, $PAGE_RWX, [ref]$old)
    $wrote = 0
    $ok = [K2.WS]::WriteProcessMemory($h, [IntPtr]$addr, $data, $data.Length, [ref]$wrote)
    $r = 0; [void][K2.WS]::VirtualProtectEx($h, [IntPtr]$addr, [uint32]$data.Length, $old, [ref]$r)
    return ($ok -and $wrote -eq $data.Length)
}

function Freeze-Threads($pid) {
    $snap = [K2.WS]::CreateToolhelp32Snapshot($TH32_THREAD, 0)
    $handles = @()
    $e = New-Object K2.WS+THREADENTRY32; $e.dwSize = [uint32][System.Runtime.InteropServices.Marshal]::SizeOf($e)
    if ([K2.WS]::Thread32First($snap, [ref]$e)) {
        do {
            if ($e.th32OwnerProcessID -eq $pid) {
                $th = [K2.WS]::OpenThread($THREAD_SUSPEND, $false, $e.th32ThreadID)
                if ($th -ne [IntPtr]::Zero) { [void][K2.WS]::SuspendThread($th); $handles += $th }
            }
        } while ([K2.WS]::Thread32Next($snap, [ref]$e))
    }
    [K2.WS]::CloseHandle($snap) | Out-Null
    return $handles
}

function Thaw-Threads($handles) {
    foreach ($h in $handles) { [void][K2.WS]::ResumeThread($h); [K2.WS]::CloseHandle($h) | Out-Null }
}

function Get-BackbufferAspect($proc) {
    $r = New-Object K2.WS+RECT
    if ($proc.MainWindowHandle -ne [IntPtr]::Zero -and [K2.WS]::GetClientRect($proc.MainWindowHandle, [ref]$r)) {
        if ($r.right -gt 0 -and $r.bottom -gt 0) { return [double]$r.right / [double]$r.bottom }
    }
    return $null
}

# Build the code-cave bytes (mirrors the validated frustumpatch.py exactly).
function Build-Cave([int64]$cave, [int64]$resume, [float]$a, [float]$b) {
    $aAddr = [uint32]$cave; $bAddr = [uint32]($cave + 4); $ftAddr = [uint32]($cave + 8); $epsAddr = [uint32]($cave + 12)
    $code = $cave + 16
    $u = { param($v) [BitConverter]::GetBytes([uint32]$v) }
    $i = { param($v) [BitConverter]::GetBytes([int32]$v) }

    $partB = [System.Collections.Generic.List[byte]]::new()
    $partB.AddRange([byte[]](0xd9,0x07));                              $partB.AddRange([byte[]](0xd9,0x47,0x04))
    $partB.AddRange([byte[]](0xd9,0xc1)); $partB.AddRange([byte[]](0xd8,0x0d)); $partB.AddRange([byte[]](& $u $aAddr))
    $partB.AddRange([byte[]](0xd9,0xc1)); $partB.AddRange([byte[]](0xd8,0x0d)); $partB.AddRange([byte[]](& $u $bAddr))
    $partB.AddRange([byte[]](0xde,0xc1))
    $partB.AddRange([byte[]](0xd9,0xc2)); $partB.AddRange([byte[]](0xd8,0x0d)); $partB.AddRange([byte[]](& $u $bAddr))
    $partB.AddRange([byte[]](0xd9,0xc2)); $partB.AddRange([byte[]](0xd8,0x0d)); $partB.AddRange([byte[]](& $u $aAddr))
    $partB.AddRange([byte[]](0xde,0xc1))
    $partB.AddRange([byte[]](0xd9,0x5f,0x04)); $partB.AddRange([byte[]](0xd9,0x1f))
    $partB.AddRange([byte[]](0xdd,0xd8)); $partB.AddRange([byte[]](0xdd,0xd8))

    $partC = [byte[]]$DISPLACED

    $partA = [System.Collections.Generic.List[byte]]::new()
    $partA.AddRange([byte[]](0x80,0x7f,0x18,0x00))              # cmp byte [edi+0x18],0
    $partA.AddRange([byte[]](0x0f,0x85,0,0,0,0))               # jne SKIP (rel later)
    $partA.AddRange([byte[]](0xd9,0x47,0x04))                  # fld [edi+4]
    $partA.AddRange([byte[]](0xd8,0x27))                       # fsub [edi]
    $partA.AddRange([byte[]](0xd9,0x47,0x08))                  # fld [edi+8]
    $partA.AddRange([byte[]](0xd8,0x67,0x0c))                  # fsub [edi+0xc]
    $partA.AddRange([byte[]](0xde,0xf9))                       # fdivp
    $partA.AddRange([byte[]](0xd9,0xe1))                       # fabs
    $partA.AddRange([byte[]](0xd8,0x25)); $partA.AddRange([byte[]](& $u $ftAddr))   # fsub [4/3]
    $partA.AddRange([byte[]](0xd9,0xe1))                       # fabs
    $partA.AddRange([byte[]](0xd8,0x1d)); $partA.AddRange([byte[]](& $u $epsAddr))  # fcomp [eps]
    $partA.AddRange([byte[]](0xdf,0xe0,0x9e))                  # fnstsw ax ; sahf
    $partA.AddRange([byte[]](0x0f,0x83,0,0,0,0))               # jae SKIP (rel later)

    $bOff = $partA.Count
    $cOff = $bOff + $partB.Count
    $skipVa = $code + $cOff

    # JNE opcode (0f 85) at offset 4 in partA; its rel32 operand at offset 6..9
    $jneEnd = $code + 4 + 2 + 4
    $tmp = [byte[]](& $i ($skipVa - $jneEnd))
    for ($k=0; $k -lt 4; $k++) { $partA[6 + $k] = $tmp[$k] }
    # JAE = last 6 bytes of partA
    $jaePos = $partA.Count - 6
    $jaeEnd = $code + $partA.Count
    $tmp = [byte[]](& $i ($skipVa - $jaeEnd))
    for ($k=0; $k -lt 4; $k++) { $partA[$jaePos + 2 + $k] = $tmp[$k] }

    $body = [System.Collections.Generic.List[byte]]::new()
    $body.AddRange($partA); $body.AddRange($partB); $body.AddRange($partC)
    $jmpFrom = $code + $body.Count
    $body.Add(0xe9); $body.AddRange([byte[]](& $i ($resume - ($jmpFrom + 5))))

    $header = [System.Collections.Generic.List[byte]]::new()
    $header.AddRange([BitConverter]::GetBytes($a)); $header.AddRange([BitConverter]::GetBytes($b))
    $header.AddRange([BitConverter]::GetBytes([float](4.0/3.0))); $header.AddRange([BitConverter]::GetBytes([float]0.06))

    $blob = [System.Collections.Generic.List[byte]]::new()
    $blob.AddRange($header); $blob.AddRange($body)
    return @{ Blob = $blob.ToArray(); Code = $code }
}

function Apply-Patch($proc, [double]$aspect) {
    $pid = $proc.Id
    $base = Get-ModuleBase $pid
    if (-not $base) { throw 'could not find k2.exe module base' }
    $h = [K2.WS]::OpenProcess($PROC_ALL, $false, $pid)
    if ($h -eq [IntPtr]::Zero) { throw 'OpenProcess failed' }
    try {
        $site = $base + $PROJ_RVA
        $cur = Read-Mem $h $site 5
        if ($cur.Count -ge 1 -and $cur[0] -eq 0xe9) { Say 'already patched'; return }
        # sanity: the site must read as the exact instructions we expect (also proves decrypt + correct build)
        $chk = Read-Mem $h $site 8
        if (@(Compare-Object $chk $DISPLACED -SyncWindow 0).Count -ne 0) {
            throw ('unexpected bytes at patch site (' + (($chk|ForEach-Object {$_.ToString("x2")}) -join '') + ') - not decrypted yet, or wrong game build')
        }
        $f = $aspect / (4.0 / 3.0)
        $a = [float]((1.0 + $f) / 2.0); $b = [float]((1.0 - $f) / 2.0)
        $cave = [K2.WS]::VirtualAllocEx($h, [IntPtr]0x20010000, 4096, $MEM_COMMIT_RESERVE, $PAGE_RWX)
        if ($cave -eq [IntPtr]::Zero) { $cave = [K2.WS]::VirtualAllocEx($h, [IntPtr]::Zero, 4096, $MEM_COMMIT_RESERVE, $PAGE_RWX) }
        if ($cave -eq [IntPtr]::Zero) { throw 'VirtualAllocEx failed' }
        $caveVa = $cave.ToInt64()
        $built = Build-Cave $caveVa ($base + $RESUME_RVA) $a $b
        if (-not (Write-Mem $h $caveVa $built.Blob)) { throw 'writing cave failed' }
        # entry jmp is LIVE code -> freeze threads so we never tear an in-flight instruction
        $rel = [int32]($built.Code - ($site + 5))
        $patch = [byte[]]((0xe9) + [BitConverter]::GetBytes($rel) + (0x90,0x90,0x90))
        $frozen = Freeze-Threads $pid
        try {
            if (-not (Write-Mem $h $site $patch)) { throw 'writing entry jmp failed' }
        } finally { Thaw-Threads $frozen }
        Say ("aspect {0:N4}  factor {1:N4}  cave 0x{2:X}  -> patched k2.exe+0x{3:X}" -f $aspect, $f, $caveVa, $PROJ_RVA)
        Say 'widescreen active. It applies on the next camera rebuild - move the camera once if needed.'
    } finally { [K2.WS]::CloseHandle($h) | Out-Null }
}

function Revert-Patch($proc) {
    $base = Get-ModuleBase $proc.Id
    $h = [K2.WS]::OpenProcess($PROC_ALL, $false, $proc.Id)
    try {
        $frozen = Freeze-Threads $proc.Id
        try { [void](Write-Mem $h ($base + $PROJ_RVA) $DISPLACED) } finally { Thaw-Threads $frozen }
        Say 'reverted (restart the game for a clean state).'
    } finally { [K2.WS]::CloseHandle($h) | Out-Null }
}

# ---- self-test: prove cave bytes match the reference patcher, then exit -------------
if ($SelfTest) {
    $parts = $SelfTest -split ','
    $cave = [Convert]::ToInt64($parts[0], 16); $resume = [Convert]::ToInt64($parts[1], 16)
    $f = (16.0/9.0) / (4.0/3.0)
    $r = Build-Cave $cave $resume ([float]((1+$f)/2)) ([float]((1-$f)/2))
    ($r.Blob | ForEach-Object { $_.ToString('x2') }) -join ''
    return
}

# ---- main --------------------------------------------------------------------------
# If Steam passed %command%, launch the game first (that is the game exe + its args).
$proc = Get-K2
if (-not $proc -and $Command -and $Command.Count -ge 1) {
    $exe = $Command[0]; $rest = @($Command | Select-Object -Skip 1)
    Say "launching game: $exe"
    if ($rest.Count) { $proc = Start-Process -FilePath $exe -ArgumentList $rest -PassThru }
    else { $proc = Start-Process -FilePath $exe -PassThru }
}

if ($Revert) {
    if (-not $proc) { $proc = Get-K2 }
    if (-not $proc) { throw 'k2.exe is not running.' }
    Revert-Patch $proc
    return
}

# wait for the process + SteamStub decryption (the patch site reads back as real code)
$deadline = (Get-Date).AddSeconds($TimeoutSec)
Say 'waiting for the game to be ready...'
while ((Get-Date) -lt $deadline) {
    if (-not $proc) { $proc = Get-K2 }
    if ($proc -and -not $proc.HasExited) {
        try {
            $base = Get-ModuleBase $proc.Id
            if ($base) {
                $h = [K2.WS]::OpenProcess($PROC_ALL, $false, $proc.Id)
                $ok = $false
                if ($h -ne [IntPtr]::Zero) {
                    $chk = Read-Mem $h ($base + $PROJ_RVA) 8
                    $ok = (@(Compare-Object $chk $DISPLACED -SyncWindow 0).Count -eq 0)
                    [K2.WS]::CloseHandle($h) | Out-Null
                }
                if ($ok) { break }
            }
        } catch {}
    }
    Start-Sleep -Milliseconds 500
}
if (-not $proc -or $proc.HasExited) { throw 'game did not start (is Steam running / logged in?).' }

# resolve aspect
if ($Aspect) {
    if ($Aspect -match '^\s*(\d+(\.\d+)?)\s*:\s*(\d+(\.\d+)?)\s*$') { $asp = [double]$Matches[1] / [double]$Matches[3] }
    else { $asp = [double]$Aspect }
} else {
    $asp = Get-BackbufferAspect $proc
    if (-not $asp) { $asp = 16.0 / 9.0; Say 'could not read window size; assuming 16:9' }
}

Apply-Patch $proc $asp

# When run as a Steam launch wrapper, stay alive until the game exits so Steam shows it running.
if ($Command -and $Command.Count -ge 1) {
    while (-not $proc.HasExited) { Start-Sleep -Seconds 5 }
    Say 'game closed.'
}
