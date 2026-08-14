# Structural scan of ALL committed writable memory in k2.exe for D3D-style 4x4 float
# matrices whose _22/_11 ratio is ~4:3 (the stretched-projection signature), i.e.
#   _11=A  _12.._14=0  _21=0  _22=B  with 1.25 < B/A < 1.42
# Prints absolute addresses. -PokeAddr multiplies _11 at that absolute address by -Mul
# (default 0.75 = 4:3 -> 16:9 horizontal correction). In-memory only.
#
#   .\matrixscan.ps1                       # find candidates
#   .\matrixscan.ps1 -PokeAddr 0x12AB3450 -Mul 0.75
#   .\matrixscan.ps1 -PokeAddr 0x12AB3450 -Mul 1.3333334   # revert

param(
    [string]$PokeAddr = "",
    [double]$Mul = 0.75,
    [double]$RatioMin = 1.25,
    [double]$RatioMax = 1.42
)

$ErrorActionPreference = 'Stop'

if (-not ('K2M.MScan' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace K2M {
public class MScan {
    [DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, IntPtr size, out IntPtr read);
    [DllImport("kernel32.dll")] public static extern bool WriteProcessMemory(IntPtr h, IntPtr addr, byte[] buf, IntPtr size, out IntPtr written);
    [DllImport("kernel32.dll")] public static extern int VirtualQueryEx(IntPtr h, IntPtr addr, out MEMORY_BASIC_INFORMATION mbi, uint size);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);

    [StructLayout(LayoutKind.Sequential)]
    public struct MEMORY_BASIC_INFORMATION {
        public IntPtr BaseAddress; public IntPtr AllocationBase; public uint AllocationProtect;
        public IntPtr RegionSize; public uint State; public uint Protect; public uint Type;
    }

    public static List<long> Scan(int pid, double ratioMin, double ratioMax) {
        var hits = new List<long>();
        IntPtr h = OpenProcess(0x0010 | 0x0400, false, pid); // VM_READ | QUERY_INFORMATION
        if (h == IntPtr.Zero) throw new Exception("OpenProcess failed");
        try {
            long addr = 0x10000;
            long max = 0x7FFF0000; // 32-bit target
            MEMORY_BASIC_INFORMATION mbi;
            while (addr < max && VirtualQueryEx(h, (IntPtr)addr, out mbi, (uint)Marshal.SizeOf(typeof(MEMORY_BASIC_INFORMATION))) != 0) {
                long regionSize = mbi.RegionSize.ToInt64();
                bool writable = (mbi.Protect & 0x04) != 0 || (mbi.Protect & 0x40) != 0; // PAGE_READWRITE | PAGE_EXECUTE_READWRITE
                if (mbi.State == 0x1000 && writable && regionSize > 0 && regionSize < 512L*1024*1024) { // MEM_COMMIT
                    var buf = new byte[regionSize];
                    IntPtr got;
                    if (ReadProcessMemory(h, mbi.BaseAddress, buf, (IntPtr)regionSize, out got) && got.ToInt64() >= 24) {
                        long n = got.ToInt64();
                        for (long i = 0; i + 24 <= n; i += 4) {
                            float a = BitConverter.ToSingle(buf, (int)i);
                            if (a < 0.01f || a > 100f || float.IsNaN(a)) continue;
                            // _12,_13,_14,_21 all zero
                            bool zeros = true;
                            for (long z = i + 4; z < i + 20; z += 4) {
                                if (BitConverter.ToInt32(buf, (int)z) != 0) { zeros = false; break; }
                            }
                            if (!zeros) continue;
                            float b = BitConverter.ToSingle(buf, (int)(i + 20));
                            if (b < 0.01f || b > 100f || float.IsNaN(b)) continue;
                            double ratio = b / a;
                            if (ratio >= ratioMin && ratio <= ratioMax) hits.Add(mbi.BaseAddress.ToInt64() + i);
                        }
                    }
                }
                addr = mbi.BaseAddress.ToInt64() + regionSize;
            }
        } finally { CloseHandle(h); }
        return hits;
    }

    public static float[] ReadPair(int pid, long addr) {
        IntPtr h = OpenProcess(0x0010, false, pid);
        try {
            var buf = new byte[24]; IntPtr got;
            ReadProcessMemory(h, (IntPtr)addr, buf, (IntPtr)24, out got);
            return new float[] { BitConverter.ToSingle(buf, 0), BitConverter.ToSingle(buf, 20) };
        } finally { CloseHandle(h); }
    }

    public static bool PokeM11(int pid, long addr, double mul) {
        IntPtr h = OpenProcess(0x0038, false, pid);
        try {
            var buf = new byte[4]; IntPtr got;
            ReadProcessMemory(h, (IntPtr)addr, buf, (IntPtr)4, out got);
            float v = BitConverter.ToSingle(buf, 0);
            var nb = BitConverter.GetBytes((float)(v * mul));
            IntPtr w;
            return WriteProcessMemory(h, (IntPtr)addr, nb, (IntPtr)4, out w);
        } finally { CloseHandle(h); }
    }
}
}
'@
}

$proc = Get-Process k2 -ErrorAction Stop | Select-Object -First 1

if ($PokeAddr) {
    $a = [Convert]::ToInt64(($PokeAddr -replace '^0[xX]', ''), 16)
    $before = [K2M.MScan]::ReadPair($proc.Id, $a)
    $ok = [K2M.MScan]::PokeM11($proc.Id, $a, $Mul)
    $after = [K2M.MScan]::ReadPair($proc.Id, $a)
    "poke 0x{0:X}: _11 {1} -> {2} (_22 {3}), ok={4}" -f $a, $before[0], $after[0], $after[1], $ok
} else {
    $hits = [K2M.MScan]::Scan($proc.Id, $RatioMin, $RatioMax)
    "candidates: $($hits.Count)"
    foreach ($hh in $hits) {
        $pair = [K2M.MScan]::ReadPair($proc.Id, $hh)
        "0x{0:X}  _11={1}  _22={2}  ratio={3:F4}" -f $hh, $pair[0], $pair[1], ($pair[1]/$pair[0])
    }
}
