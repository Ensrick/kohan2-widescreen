# Changelog

All notable changes to the Kohan II Widescreen mod. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-08-14

First working widescreen release. Corrects the stretched 3D view and the cramped
high-resolution camera - all in memory, nothing on disk is modified (`k2.exe` is
Steam-DRM encrypted and is never touched).

### Added
- **Drop-in `avifil32.dll`** - the whole fix in one file. Drop it in the game folder
  next to `k2.exe` and play; delete it to uninstall. It proxies the 3 (now 9) functions
  the game imports from the system DLL and, once Steam's DRM decrypts the game, applies
  the patch from inside the process. Chosen over a `winmm.dll` proxy because Steam's
  overlay pre-loads `winmm` from the system folder, bypassing an app-folder copy.
- **Aspect-ratio fix.** The engine builds every 3D camera with a hardcoded 4:3 frustum
  and stretches it across the backbuffer. A detour at the projection builder
  (`k2.exe+0x49545D`) widens the frustum bounds `(R-L)` at the source to your real screen
  aspect, so projection **and** the drawn/culled ground widen together - true "Hor+"
  widescreen with no black bars, vertical FOV unchanged.
- **Resolution-aware zoom-out.** Higher-resolution displays otherwise render a fixed
  world-extent per zoom, so the world looks cramped/close-up. The same detour scales the
  frustum (and far plane) by `screenHeight / 1024`, so 1440p/4K show proportionally more
  world - matching the apparent size of the game's design resolution (1280x1024).
- **Script + editor installs** for people who prefer not to use a DLL:
  `Kohan2Widescreen.ps1` (standalone or as a Steam launch option) and
  `Apply-Widescreen.bat`. Dev tool: `tools/frustumpatch.py`.
- RE tooling that produced the fix (`tools/`): `hwbp.py`, `k2mem.py`, `matscan.py`,
  `k2console.py`, `analyze.py`, `mute_k2.ps1`, `vpscan.py`.

### Known issues
- The **main-menu 3D backdrop** is composed for 4:3, so widening/zooming it leaves the
  framing slightly off. Gameplay is unaffected. A fix (skip the patch at the menu) is
  planned for the next release.
- The manual **scroll-out range** (hard-coded in the engine) is unchanged; the
  resolution-aware default already provides the extra zoom-out on high-res displays.

### Superseded
- The earlier `_11`-redirect loader (`k2widescreen.ps1` + `k2patch.py --watch`) fixed
  only the displayed projection, leaving the draw region at 4:3. Replaced by the
  frustum-bounds detour above, which fixes both.

### Notes
- Located and applied successfully (`Logs\log-203-ok.log`); pending a human visual check
  at native 3840x2160, plus one wrapped launch to confirm SteamStub accepts the
  launch-options parent.

### Fixed
- Startup crash on Windows 11 (`SetupFonts()` fatal "ERROR: Processing non-Unicode
  TrueType font") - two independent causes, both hit the same engine error:
  1. Vanilla font definitions reference GulimChe and MingLiU, which current Windows no
     longer ships; the OS substitutes Arial and the engine rejects it. Override copies
     of `Fonts/font_{tiny,small,medium,large}.tgi` drop the CJK character sets (unused
     by the English game).
  2. The 2026-05 Windows update replaced Arial itself with a file the 2004 engine
     cannot parse, so `font = arial` in the small/tiny definitions (and large's
     `backup_font`) crashed even with all CJK sets removed. Those now use the bundled
     `/fonts/truetype/LBRITED.TTF` instead of any system font.
  Loose-depot overrides of the font files DO load (verified via glyph-texture counts in
  the logs). Evidence: `Logs\log-188` through `log-193`, 2026-08-13; fix confirmed
  in-game (game boots to menu).

## [0.1.0] - 2026-08-13

Initial import of the October 2024 working files, split out of the Battleborn repo.

### Added
- `3840x2160` entry in `UI/resolution.tgi` with `resolution_3840x2160_name` label in
  `Localization/strings_rtse_ui.tgi`.
- `UI/3840/` asset folder: 620+ hand-upscaled interface textures (arrows, panels, list
  boxes, drop-downs, CSD icons, main-menu background, splash screen) with GIMP sources
  in `gimp/`.
- `UI/Menus/main.tgi`: menu background texture path parameterized by resolution folder.
- `AVars.tgi`: `InterfacePositioningWidth/Height` 1024x768 -> 1280x720,
  `CameraFarPlane` 512 -> 768.
- `UVars.tgi`: `TerrainTexturePoolDesiredNumEntries` 120 -> 1240.
- Cheat Engine table (`ce/`) with `k2.exe`-relative render-scaling statics.
- `tools/collect.ps1` / `tools/deploy.ps1` sync scripts, `docs/WIDESCREEN.md` research notes.

### Known issues
- Not yet verified in-game; the 3840x2160 label fix (`strings_rtse_ui.tgi` in the live
  depot) has never been tested together with the resolution entry.
