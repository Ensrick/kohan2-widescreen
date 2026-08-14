# Build the drop-in avifil32.dll (32-bit) proxy + widescreen patcher.
# Requires Visual Studio 2022 (Community or Build Tools) with the C++ x86 toolset.
# Output: dll\avifil32.dll  ->  copy into the Kohan II game folder.
#
# (avifil32, not winmm: Steam's overlay pre-loads winmm from System32, so an
#  app-folder winmm.dll is ignored. The overlay does not touch avifil32.)

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
  $cmd = "`"$vcvars`" x86 && cl /nologo /LD /O2 /MT avifil32.c user32.lib kernel32.lib /Fe:avifil32.dll /link /DEF:avifil32.def /MACHINE:X86"
  cmd /c $cmd
  if ($LASTEXITCODE -ne 0) { throw "compile failed ($LASTEXITCODE)" }
  Remove-Item -ErrorAction SilentlyContinue avifil32.obj, avifil32.exp, avifil32.lib
  Write-Host "`nBuilt: $(Join-Path $Here 'avifil32.dll')"
  Write-Host "Drop that avifil32.dll into your Kohan II game folder."
} finally { Pop-Location }
