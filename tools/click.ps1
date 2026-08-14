# Click at absolute screen pixel coordinates (physical pixels, DPI-aware).
# Brings the k2 window to foreground first if present.
#   .\click.ps1 -X 1920 -Y 1080
#   .\click.ps1 -X 1920 -Y 1080 -Double

param(
    [Parameter(Mandatory)][int]$X,
    [Parameter(Mandatory)][int]$Y,
    [switch]$Double
)

$ErrorActionPreference = 'Stop'
Add-Type -Name Input -Namespace K2 -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
'@
[K2.Input]::SetProcessDPIAware() | Out-Null

$p = Get-Process k2 -ErrorAction SilentlyContinue | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
if ($p) { [K2.Input]::SetForegroundWindow($p.MainWindowHandle) | Out-Null; Start-Sleep -Milliseconds 400 }

[K2.Input]::SetCursorPos($X, $Y) | Out-Null
Start-Sleep -Milliseconds 150
# MOUSEEVENTF_LEFTDOWN=2, LEFTUP=4
[K2.Input]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60; [K2.Input]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
if ($Double) { Start-Sleep -Milliseconds 120; [K2.Input]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60; [K2.Input]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero) }
"clicked $X,$Y"
