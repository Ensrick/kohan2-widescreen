# Launch Kohan II without it ever appearing on a monitor.
#
# Two modes:
#   -Mode Hidden   launch on a private CreateDesktop desktop. Nothing can ever be seen,
#                  but Direct3D9 reports "No adapters available" on a non-input desktop,
#                  so the renderer never comes up. Useful only for RE against the
#                  decrypted image (SteamStub decrypts .text before the renderer inits).
#   -Mode Parked   launch on the normal desktop with STARTF_USESHOWWINDOW/SW_HIDE, then
#                  park the window far outside the virtual screen and show it
#                  non-activating. The renderer works; the window is never on a monitor
#                  and never takes focus.  <-- the mode that can actually render
#
# k2.exe is SteamStub-wrapped: it exits instantly unless the Steam client is running AND
# SteamAppId/SteamGameId are in the environment. This script sets them.
#
#   $id = .\k2launch.ps1 -Mode Parked
#   .\k2launch.ps1 -Stop

param(
    [ValidateSet('Hidden', 'Parked')][string]$Mode = 'Parked',
    [switch]$Stop,
    [int]$ParkSeconds = 90,
    # Engine console commands, each prefixed with '+' (see readme.txt section 7),
    # e.g. -GameArgs '+set CameraFOV 25'.
    # NB: do NOT name this $Args - like $pid it is a PowerShell automatic variable.
    [string]$GameArgs = ''
)

$ErrorActionPreference = 'Stop'
$GameDir = "C:\Program Files (x86)\Steam\steamapps\common\Kohan II"
$AppId = '97130'

if ($Stop) {
    Get-Process k2 -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Milliseconds 400
    "stopped"; return
}

if (-not (Get-Process steam -ErrorAction SilentlyContinue)) {
    throw "Steam client is not running - SteamStub cannot decrypt k2.exe. Start Steam first."
}

if (-not ('K2L.Launcher' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
namespace K2L {
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

    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
    public delegate bool EnumProc(IntPtr h, IntPtr p);

    const int STARTF_USESHOWWINDOW = 0x00000001;
    const int SW_HIDE = 0;
    const int SW_SHOWNOACTIVATE = 4;
    const uint SWP_NOSIZE = 0x0001, SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010;

    public static List<IntPtr> WindowsOf(int pid) {
        var list = new List<IntPtr>();
        EnumWindows((h, p) => {
            int wp; GetWindowThreadProcessId(h, out wp);
            if (wp == pid) list.Add(h);
            return true;
        }, IntPtr.Zero);
        return list;
    }

    // Far outside the virtual screen: SM_XVIRTUALSCREEN=76, SM_CXVIRTUALSCREEN=78
    public static int ParkX() { return GetSystemMetrics(76) + GetSystemMetrics(78) + 200; }
    public static int ParkY() { return GetSystemMetrics(77) + GetSystemMetrics(79) + 200; }

    public static int Launch(string exe, string dir, string desktopName, bool hideAndPark) {
        return Launch(exe, dir, desktopName, hideAndPark, null);
    }

    public static int Launch(string exe, string dir, string desktopName, bool hideAndPark, string extraArgs) {
        var si = new STARTUPINFO();
        si.cb = Marshal.SizeOf(si);
        // PowerShell marshals $null to "", so test for empty too.
        if (!string.IsNullOrEmpty(desktopName)) {
            IntPtr desk = CreateDesktop(desktopName, IntPtr.Zero, IntPtr.Zero, 0, 0x10000000, IntPtr.Zero);
            if (desk == IntPtr.Zero) throw new Exception("CreateDesktop failed: " + Marshal.GetLastWin32Error());
            si.desktop = desktopName;
        }
        if (hideAndPark) { si.flags = STARTF_USESHOWWINDOW; si.showWindow = SW_HIDE; }
        // lpCommandLine must carry argv[0] itself when lpApplicationName is also given.
        string cmd = string.IsNullOrEmpty(extraArgs) ? null : "\"" + exe + "\" " + extraArgs;
        PROCESS_INFORMATION pi;
        if (!CreateProcess(exe, cmd, IntPtr.Zero, IntPtr.Zero, false, 0, IntPtr.Zero, dir, ref si, out pi))
            throw new Exception("CreateProcess failed: " + Marshal.GetLastWin32Error());
        return pi.pid;
    }

    /// Keep every window of the process parked off-screen and non-activating.
    /// Runs on a background thread so the game can be driven meanwhile.
    public static void ParkLoop(int pid, int seconds) {
        var t = new System.Threading.Thread(() => {
            int px = ParkX(), py = ParkY();
            var sw = Stopwatch.StartNew();
            var seen = new HashSet<IntPtr>();
            while (sw.Elapsed.TotalSeconds < seconds) {
                try {
                    foreach (var h in WindowsOf(pid)) {
                        SetWindowPos(h, IntPtr.Zero, px, py, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
                        if (!seen.Contains(h)) { ShowWindow(h, SW_SHOWNOACTIVATE); seen.Add(h); }
                    }
                } catch { }
                System.Threading.Thread.Sleep(5);
            }
        });
        t.IsBackground = true;
        t.Start();
    }
}
}
'@
}

$env:SteamAppId = $AppId
$env:SteamGameId = $AppId
$env:SteamPath = 'C:\Program Files (x86)\Steam'

$exe = Join-Path $GameDir 'k2.exe'
if ($Mode -eq 'Hidden') {
    $k2pid = [K2L.Launcher]::Launch($exe, $GameDir, 'k2headless', $false, $GameArgs)
    Write-Host "launched k2.exe pid=$k2pid on private desktop 'k2headless' (renderer will NOT init)"
} else {
    $k2pid = [K2L.Launcher]::Launch($exe, $GameDir, '', $true, $GameArgs)
    [K2L.Launcher]::ParkLoop($k2pid, $ParkSeconds)
    $px = [K2L.Launcher]::ParkX(); $py = [K2L.Launcher]::ParkY()
    Write-Host "launched k2.exe pid=$k2pid hidden; parking any window at $px,$py for $ParkSeconds s"
}
$k2pid
