# Scan the running k2.exe image for a 4-byte float pattern and optionally poke matches.
# Handles read-only image pages via VirtualProtectEx. All pokes are in-memory only
# (nothing on disk) and revert on game restart.
#
#   .\aspectscan.ps1 -Find 1.3333334                          # list image offsets holding the float
#   .\aspectscan.ps1 -Poke 0x123456,0x234567 -Value 1.7777778 # write Value at these offsets
#   .\aspectscan.ps1 -Poke 0x123456 -Value 1.3333334          # revert

param(
    [double]$Find = [double]::NaN,
    [string[]]$Poke = @(),
    [double]$Value = [double]::NaN
)

$ErrorActionPreference = 'Stop'

Add-Type -Name Scan -Namespace K2A -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out int read);
[DllImport("kernel32.dll")] public static extern bool WriteProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out int written);
[DllImport("kernel32.dll")] public static extern bool VirtualProtectEx(IntPtr h, IntPtr addr, UIntPtr size, uint newProt, out uint oldProt);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
'@

$proc = Get-Process k2 -ErrorAction Stop | Select-Object -First 1
$module = $proc.Modules | Where-Object ModuleName -eq 'k2.exe'
$base = [int64]$module.BaseAddress
$size = $module.ModuleMemorySize

# PROCESS_VM_READ | VM_WRITE | VM_OPERATION
$h = [K2A.Scan]::OpenProcess(0x0038, $false, $proc.Id)
if ($h -eq [IntPtr]::Zero) { throw 'OpenProcess failed' }

try {
    if (-not [double]::IsNaN($Find)) {
        $buf = New-Object byte[] $size
        $n = 0
        [K2A.Scan]::ReadProcessMemory($h, [IntPtr]$base, $buf, $size, [ref]$n) | Out-Null
        if ($n -eq 0) { throw 'image read failed' }
        $pat = [BitConverter]::GetBytes([float]$Find)
        $hits = @()
        for ($i = 0; $i -le $n - 4; $i++) {
            if ($buf[$i] -eq $pat[0] -and $buf[$i+1] -eq $pat[1] -and $buf[$i+2] -eq $pat[2] -and $buf[$i+3] -eq $pat[3]) {
                $hits += ('0x{0:X}' -f $i)
            }
        }
        "pattern $Find ($(($pat | ForEach-Object { $_.ToString('X2') })) ): $($hits.Count) hits in image (size $size)"
        $hits
    }

    foreach ($p in $Poke) {
        if ([double]::IsNaN($Value)) { throw '-Poke requires -Value' }
        $rel = [Convert]::ToInt64(($p -replace '^0[xX]', ''), 16)
        $addr = [IntPtr]($base + $rel)
        $old = [uint32]0
        # PAGE_EXECUTE_READWRITE = 0x40
        [K2A.Scan]::VirtualProtectEx($h, $addr, [UIntPtr]4, 0x40, [ref]$old) | Out-Null
        $vbuf = [BitConverter]::GetBytes([float]$Value)
        $n = 0
        $ok = [K2A.Scan]::WriteProcessMemory($h, $addr, $vbuf, 4, [ref]$n)
        $restored = [uint32]0
        [K2A.Scan]::VirtualProtectEx($h, $addr, [UIntPtr]4, $old, [ref]$restored) | Out-Null
        $rbuf = New-Object byte[] 4
        [K2A.Scan]::ReadProcessMemory($h, $addr, $rbuf, 4, [ref]$n) | Out-Null
        "poke {0} -> {1} (write ok: {2}, reads back {3})" -f $p, $Value, $ok, [BitConverter]::ToSingle($rbuf, 0)
    }
} finally {
    [K2A.Scan]::CloseHandle($h) | Out-Null
}
