# Headless screen capture to PNG. Works while the game runs in borderless
# (ResolutionCoopFullscreenMode) - exclusive fullscreen would black-screen this.
#
#   .\capture.ps1                      # -> capture_<timestamp>.png next to script
#   .\capture.ps1 -Out C:\x\shot.png

param([string]$Out = "")

$ErrorActionPreference = 'Stop'
Add-Type -Name DPI -Namespace K2 -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[K2.DPI]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

if (-not $Out) { $Out = Join-Path $PSScriptRoot ("capture_{0:yyyyMMdd_HHmmss}.png" -f (Get-Date)) }

$vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap($vs.Width, $vs.Height)
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen($vs.Location, [System.Drawing.Point]::Empty, $vs.Size)
$gfx.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Get-Item $Out | Select-Object FullName, Length
