# 4K / widescreen state (imported 2026-08-13)

Goal: run Kohan II at 3840x2160 fullscreen with a usable UI.

## What the engine already supports (verified in game files)

- **The resolution list is data-driven.** `UI/resolution.tgi` declares `[Resolution]`
  blocks; the mod already adds `IDS = 3840x2160` alongside the vanilla `IDS = 0x0` entry.
  Each declared width expects a matching `UI/<width>/` asset folder - vanilla ships
  `UI/800/` and `UI/1280/`; the mod adds `UI/3840/` (624 hand-upscaled files: arrows,
  panels, list boxes, drop-downs, CSD icons, main-menu background, splash screen).
- **Engine resolution vars** (`UVars.tgi`, `[UserVariables]`):
  - `int ResolutionX = 1024` / `int ResolutionY = 768`
  - `flag ResolutionWindowed` (code default false)
  - `flag ResolutionCoopFullscreenMode = false` - per the inline comment, `true` runs the
    game in a borderless window at the desktop resolution without a mode change,
    ignoring ResolutionX/Y. A native borderless-fullscreen path already in the engine.
  - `int OptionsAcceptNewResolutionTimeout = 10`
- **Depot order** (`startup\autoexec.txt`): `data.rwd` -> `data/` -> `%USERDATA%/data/ 1`,
  so loose files and Documents\Kohan2 override the archive.
- `UI/Menus/main.tgi` is also overridden in the live Data set (menu layout tweaks).

## Cheat Engine progress (`ce/Kohan II Kings of War.CT`, last edit 2024-10-30)

Module-relative static addresses in `k2.exe` (stable across runs, convertible to a
permanent hex patch or small patcher). Identified so far:

- `k2.exe+6F62FC` float "Horizontal Scaling (1.53125)"
- `k2.exe+6F6310` float "Vertical Render Scaling (1.75)"
- `k2.exe+6F6300` float "Camera Default Zoom Dist (1.5)"
- `k2.exe+6E62BC` float "Portrait Window Model Scaling?"
- Minimap Red/Green/Blue floats, terrain/mountain gradient floats, physics object
  scaling, UV texture mapping - plus ~60 probes still labeled "?".

Note 1.53125 = 1568/1024 and 1.75 = 1344/768 are plausible viewport/aspect ratios; the
horizontal/vertical pair is the prime lever for aspect correction if the data-driven
route leaves the world view stretched.

## Community knowledge (researched 2026-08-13)

- Steam users run the game at widescreen resolutions **without any exe patch** - the known
  problem is UI distortion (stretched minimap frame), not mode rejection
  ([Steam thread](https://steamcommunity.com/app/97130/discussions/0/864973123403825582/)).
  This supports the data-driven approach: declare the mode, supply the UI assets.
- A **"Kohan 2 Interface Fix for Widescreen"** mod exists (fixes the minimap frame). The
  old host `awakening.chimaerica.com/downloads.php` is dead; the community (The Awakening)
  moved its file archive to a
  [Google Drive folder](https://drive.google.com/drive/folders/1cpH9i4MCGLU0F5BUmJzrpWIt_QsnYCYx)
  via [theawakening.bravesites.com](http://theawakening.bravesites.com/). Worth grabbing:
  how it re-cuts the minimap UI teaches the layout system for the 3840 HUD.
- Stability on Win 10/11: XP SP2 compat mode + run-as-admin + DEP exception for `k2.exe`
  ([Steam guide](https://steamcommunity.com/sharedfiles/filedetails/?id=2823214193)).
  Some users report crashes when changing resolution in-game; setting it via config
  before launch avoids that.
- Old gameplay mods archive (reference for .tgi patterns):
  [theawakening.chimaerica.com/downloads/kow_mods.htm](http://theawakening.chimaerica.com/downloads/kow_mods.htm)
  (HTTP only - the HTTPS cert is a parked bravehost wildcard).

## Known gap in the live Data set

The `resolution_3840x2160_name = "3840x2160"` string was added to
`Localization/strings_rtse_ui.tgi` **in the workbench only** (now at
`workbench/Localization/strings_rtse_ui.tgi`). The game never mounts `Data (Mod)\`, so the
live `Data\` depot is missing that file - in-game the 3840x2160 entry would show an
unresolved label. Fix: copy it into `Data/Localization/` (it also carries the vanilla
resolution names, so it is safe to ship whole).

## Unknowns / next steps

1. Copy `strings_rtse_ui.tgi` into the live `Data/Localization/` and deploy.
2. **In-game verification** (needs a manual launch): does 3840x2160 appear in the options
   dropdown, does the mode apply, and what breaks (HUD layout, minimap, cursor, zoom)?
3. `ResolutionCoopFullscreenMode = true` in `Documents\Kohan2\data\User\` (user depot
   wins) may be the cheapest full-res path - worth testing before any exe patching.
4. Only if the engine rejects or clamps the mode, go binary: `k2.exe` is a 32-bit D3D
   executable, 8,089,600 bytes, and `k2 - Copy.exe` is a byte-identical backup - no patch
   has been applied yet. Cheat Engine / x32dbg entry points: the options-menu mode
   enumeration (EnumDisplaySettings / D3D EnumAdapterModes), the ResolutionX/Y var
   read, and any hardcoded clamp. Community evidence suggests this won't be needed.
5. Pull the Interface Fix for Widescreen from the community GDrive and study its minimap
   layout changes for the 3840 HUD.
