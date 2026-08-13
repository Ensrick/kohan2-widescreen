# Deploys the repo's Data/ override set into the Kohan II install.
# Copy-only: never deletes. Remove obsolete files from the game's Data\ folder by hand.

param(
    [string]$GameDir = "C:\Program Files (x86)\Steam\steamapps\common\Kohan II"
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$src = Join-Path $repo 'Data'
$dst = Join-Path $GameDir 'Data'

$count = 0
Get-ChildItem $src -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($src.Length + 1)
    $target = Join-Path $dst $rel
    $targetDir = Split-Path $target -Parent
    if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Force $targetDir | Out-Null }
    Copy-Item $_.FullName $target -Force
    $count++
}
Write-Host "Deployed $count files to $dst"
