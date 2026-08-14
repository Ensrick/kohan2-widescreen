# Launch k2.exe on a private, non-interactive Windows desktop so its window never
# appears on any of the user's monitors and no Steam UI shows. The game still renders
# to its D3D backbuffer (projection matrices compute normally), so memory RE works.
#
#   $pid = .\run_headless.ps1            # returns the k2 PID
#   .\run_headless.ps1 -Stop            # kill any headless k2

param([switch]$Stop)

$ErrorActionPreference = 'Stop'
$GameDir = "C:\Program Files (x86)\Steam\steamapps\common\Kohan II"

if ($Stop) {
    Get-Process k2 -ErrorAction SilentlyContinue | Stop-Process -Force
    "stopped"; return
}

if (-not ('K2H.Launcher' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace K2H {
public class Launcher {
    [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern IntPtr CreateDesktop(string name, IntPtr dev, IntPtr dm, int flags, uint access, IntPtr sa);

    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    public struct STARTUPINFO {
        public int cb; public string res; public string desktop; public string title;
        public int x, y, xs, ys, xcc, ycc, fill, flags; public short showWindow, cbR;
        public IntPtr lpR, hStdIn, hStdOut, hStdErr;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION { public IntPtr hProcess, hThread; public int pid, tid; }

    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern bool CreateProcess(string app, string cmd, IntPtr pa, IntPtr ta,
        bool inherit, uint flags, IntPtr env, string curDir, ref STARTUPINFO si, out PROCESS_INFORMATION pi);

    public static int Launch(string exe, string dir, string desktopName) {
        // GENERIC_ALL = 0x10000000
        IntPtr desk = CreateDesktop(desktopName, IntPtr.Zero, IntPtr.Zero, 0, 0x10000000, IntPtr.Zero);
        if (desk == IntPtr.Zero) throw new Exception("CreateDesktop failed: " + Marshal.GetLastWin32Error());
        var si = new STARTUPINFO();
        si.cb = Marshal.SizeOf(si);
        si.desktop = desktopName;
        PROCESS_INFORMATION pi;
        if (!CreateProcess(exe, null, IntPtr.Zero, IntPtr.Zero, false, 0, IntPtr.Zero, dir, ref si, out pi))
            throw new Exception("CreateProcess failed: " + Marshal.GetLastWin32Error());
        return pi.pid;
    }
}
}
'@
}

$exe = Join-Path $GameDir 'k2.exe'
# NB: do NOT name this $pid - that is a read-only automatic variable in PowerShell.
$k2pid = [K2H.Launcher]::Launch($exe, $GameDir, 'k2headless')
Write-Host "launched k2.exe pid=$k2pid on desktop 'k2headless'"
$k2pid
