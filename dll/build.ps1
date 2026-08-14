# Build the drop-in winmm.dll (32-bit) proxy + widescreen patcher.
# Requires Visual Studio 2022 (Community or Build Tools) with the C++ x86 toolset.
# Output: dll\winmm.dll  ->  copy into the Kohan II game folder.

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

# locate vcvarsall.bat from any VS2022 edition (sets INCLUDE/LIB/PATH for the toolset)
$cands = @(
  'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat',
  'C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat',
  'C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat',
  'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat'
)
$vcvars = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $vcvars) { throw 'vcvarsall.bat not found - install VS2022 "Desktop development with C++".' }

Push-Location $Here
try {
  # run vcvars (x86) then cl in one cmd session so the toolset env is present
  $cmd = "`"$vcvars`" x86 && cl /nologo /LD /O2 /MT winmm.c user32.lib kernel32.lib /Fe:winmm.dll /link /DEF:winmm.def /MACHINE:X86"
  cmd /c $cmd
  if ($LASTEXITCODE -ne 0) { throw "compile failed ($LASTEXITCODE)" }
  Remove-Item -ErrorAction SilentlyContinue winmm.obj, winmm.exp, winmm.lib
  Write-Host "`nBuilt: $(Join-Path $Here 'winmm.dll')"
  Write-Host "Drop that winmm.dll into your Kohan II game folder."
} finally { Pop-Location }
