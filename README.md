# Kohan II Widescreen & 4K UI

Widescreen / high-resolution support and modern-Windows compatibility fixes for
Kohan II: Kings of War v1.2.3 (Steam): a data-driven 3840x2160 mode, a hand-upscaled 4K
interface, and a font fix for the Windows 11 startup crash. Split out of the
[Battleborn](https://github.com/Ensrick/kohan2-battleborn) gameplay mod so display fixes
can evolve (and eventually be shared) independently of balance changes.

This comes in two parts: a **data mod** (the 4K UI + Windows 11 font fix, installed by
copying files) and a **runtime aspect fix** (`Kohan2Widescreen.ps1`) that corrects the
stretched 3D view so the game renders as if it natively supported your monitor's aspect
ratio.

## Quick start: the widescreen aspect fix

The engine draws the 3D world with a hardcoded 4:3 view and stretches it across your
screen. This fix widens the camera to your real aspect (you see more to the sides;
vertical view unchanged - "Hor+"), and terrain fills the full width with no black bars.

**It is a memory-only patch: the game files on disk are never modified.** (`k2.exe` is
Steam-DRM encrypted, so there is nothing to hex-edit and no cracked exe is shipped -
the fix patches the running game each session.) It needs only Windows PowerShell, which
every Windows install already has - no Python, no other downloads.

### Option A - automatic, every launch (recommended)

In Steam: **Library -> right-click _Kohan II: Kings of War_ -> Properties -> General ->
Launch Options**, and paste (adjust the path to where you saved this repo):

```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\kohan2-widescreen\Kohan2Widescreen.ps1" %command%
```

Now just play. The script launches the game, waits for it to be ready, and applies the
fix automatically. (At the main menu the 3D backdrop may look stretched for a second,
then corrects itself - that is normal.)

### Option B - one-click, when the game is already running

1. Launch Kohan II and load into a map (skirmish / campaign / editor).
2. Double-click **`Apply-Widescreen.bat`**.

To force a specific aspect (e.g. ultrawide), run from a terminal:
`powershell -ExecutionPolicy Bypass -File Kohan2Widescreen.ps1 -Aspect 21:9`.
To undo it for the session: `... -Revert` (or just restart the game).

> **Note:** run the aspect fix at your desktop/native resolution in borderless or
> windowed-fullscreen so the game window matches your monitor; the script reads that
> window size to compute the correction.

**Status:** the aspect fix is working (native-16:9 confirmed in game). The 4K UI data
mod is still being verified in-game - see `docs/WIDESCREEN.md`. Technical write-up of the
aspect fix is in `docs/ASPECT_PATCH.md`.

## How it works (data mod)

The engine's resolution list is data-driven, no exe patch required:

- `Data/UI/resolution.tgi` declares `[Resolution]` blocks; this mod adds `3840x2160`.
- Each declared width expects a matching `Data/UI/<width>/` asset folder; this mod ships
  `UI/3840/` (620+ upscaled arrows, panels, list boxes, drop-downs, CSD icons, menu
  background, splash screen).
- `Data/UI/Menus/main.tgi` parameterizes the menu background path by resolution folder
  (`/UI/%s/Default/...`).
- `Data/Localization/strings_rtse_ui.tgi` adds the `resolution_3840x2160_name` label.
- `Data/AVars.tgi`: `InterfacePositioningWidth/Height` 1024x768 -> 1280x720 (16:9 UI
  space), `CameraFarPlane` 512 -> 768.
- `Data/UVars.tgi`: `TerrainTexturePoolDesiredNumEntries` 120 -> 1240 (more terrain tiles
  visible at 4K).
- `Data/Fonts/font_{tiny,small,medium,large}.tgi`: CJK character sets removed (Windows
  11 no longer ships GulimChe / classic MingLiU) AND all system-font references replaced
  with bundled TTFs - the 2026-05 Windows update's Arial is unparseable by the 2004
  engine and fatals startup with "ERROR: Processing non-Unicode TrueType font". See
  `CHANGELOG.md` for the full diagnosis.

The game mounts loose `Data\` files over `Data.rwd` (see the game's
`startup\autoexec.txt`), so installing is just copying `Data/` into the game folder.

## Repo layout

| Path | What it is |
|---|---|
| `Kohan2Widescreen.ps1` | The runtime aspect fix - self-contained, no dependencies. |
| `Apply-Widescreen.bat` | Double-click convenience wrapper for the script. |
| `Data/` | The deployable override set (display-related files only). |
| `gimp/` | GIMP `.xcf` sources for the upscaled UI art. |
| `ce/` | Cheat Engine table: `k2.exe`-relative statics for render scaling, camera zoom, minimap colors, plus unidentified probes. Research material for aspect correction. |
| `docs/WIDESCREEN.md` | Engine findings, community research, and the work queue. |
| `tools/collect.ps1` | Game install -> repo (display-scoped). |
| `tools/deploy.ps1` | Repo `Data/` -> game `Data\`. Copy-only, never deletes. |

## Workflow

1. Edit in the repo (or in the game's `Data\` folder, then `tools\collect.ps1`).
2. `tools\deploy.ps1` to install.
3. Commit and push (origin pushes to **both** GitHub and GitLab).

## License & content policy

Original work in this repository (scripts, docs, the Cheat Engine table, and authored
art sources) is MIT-licensed - see `LICENSE`.

Modified game-data files (`.tgi` overrides and interface textures derived from the
game's art) are derivative works of Kohan II: Kings of War, included solely so the mod
functions; all rights to the underlying game content remain with TimeGate Studios and
its successors. This repository never contains unmodified game data, the `Data.rwd` /
`Music.rwd` archives, or the game executable.

## Remotes

Mirrored for redundancy - a single `git push` updates both:

- GitHub: `github.com/Ensrick/kohan2-widescreen` (fetch + push)
- GitLab: `gitlab.com/ensrick7/kohan2-widescreen` (push mirror)
