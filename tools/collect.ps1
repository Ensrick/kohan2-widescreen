# Harvests the widescreen/4K override files out of the Kohan II install into this repo.
# Scope: display-related files ONLY (everything else belongs to the Battleborn repo).
# Copy-only: never deletes.

param(
    [string]$GameDir = "C:\Program Files (x86)\Steam\steamapps\common\Kohan II"
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$src = Join-Path $GameDir 'Data'
$dst = Join-Path $repo 'Data'

$owned = @('AVars.tgi', 'UVars.tgi', 'Localization\strings_rtse_ui.tgi')

$count = 0
Get-ChildItem $src -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($src.Length + 1)
    if ($rel -like 'UI\*' -or $rel -like 'Fonts\*' -or $owned -contains $rel) {
        $target = Join-Path $dst $rel
        $targetDir = Split-Path $target -Parent
        if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Force $targetDir | Out-Null }
        Copy-Item $_.FullName $target -Force
        $count++
    }
}
Write-Host "Collected $count display-related files into $dst"
