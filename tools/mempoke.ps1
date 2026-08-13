# Read or write a float/int32 in the running k2.exe at a module-relative offset.
# Non-elevated: k2 runs as the same user. No UI, no prompts.
#
#   .\mempoke.ps1 6F62FC            # read float at k2.exe+6F62FC
#   .\mempoke.ps1 6F62FC -Set 1.15  # write float
#   .\mempoke.ps1 6F62F0 -Int       # read int32
#
# Known addresses (from ce/Kohan II Kings of War.CT):
#   6F62FC  float  Horizontal Scaling   (observed 1.53125)
#   6F6310  float  Vertical Render Scaling (observed 1.75)
#   6F6300  float  Camera Default Zoom Dist (observed 1.5)
#   6E62BC  float  Portrait Window Model Scaling?

param(
    [Parameter(Mandatory)][string]$Offset,
    [double]$Set = [double]::NaN,
    [switch]$Int
)

$ErrorActionPreference = 'Stop'

Add-Type -Name Mem -Namespace K2 -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out int read);
[DllImport("kernel32.dll")] public static extern bool WriteProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out int written);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
'@

$proc = Get-Process k2 -ErrorAction Stop | Select-Object -First 1
$module = $proc.Modules | Where-Object ModuleName -eq 'k2.exe'
if (-not $module) { throw 'k2.exe module not found in process' }
$base = [int64]$module.BaseAddress
$rel = [Convert]::ToInt64(($Offset -replace '^0[xX]', ''), 16)
$addr = [IntPtr]($base + $rel)

# PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
$h = [K2.Mem]::OpenProcess(0x0038, $false, $proc.Id)
if ($h -eq [IntPtr]::Zero) { throw "OpenProcess failed (game running? same user?)" }

try {
    $n = 0
    if (-not [double]::IsNaN($Set)) {
        $buf = if ($Int) { [BitConverter]::GetBytes([int32]$Set) } else { [BitConverter]::GetBytes([float]$Set) }
        if (-not [K2.Mem]::WriteProcessMemory($h, $addr, $buf, 4, [ref]$n)) { throw 'WriteProcessMemory failed' }
    }
    $buf = New-Object byte[] 4
    if (-not [K2.Mem]::ReadProcessMemory($h, $addr, $buf, 4, [ref]$n)) { throw 'ReadProcessMemory failed' }
    $val = if ($Int) { [BitConverter]::ToInt32($buf, 0) } else { [BitConverter]::ToSingle($buf, 0) }
    [pscustomobject]@{ Offset = ('0x{0:X}' -f $rel); Address = ('0x{0:X}' -f [int64]$addr); Value = $val }
} finally {
    [K2.Mem]::CloseHandle($h) | Out-Null
}
