# Changelog

All notable changes to the Kohan II Widescreen & 4K UI mod. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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
