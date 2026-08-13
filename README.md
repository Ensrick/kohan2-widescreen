# Kohan II Widescreen & 4K UI

Widescreen / high-resolution support and modern-Windows compatibility fixes for
Kohan II: Kings of War v1.2.3 (Steam): a data-driven 3840x2160 mode, a hand-upscaled 4K
interface, and a font fix for the Windows 11 startup crash. Split out of the
[Battleborn](https://github.com/Ensrick/kohan2-battleborn) gameplay mod so display fixes
can evolve (and eventually be shared) independently of balance changes.

**Status: work in progress - not yet verified in-game.** See `docs/WIDESCREEN.md` for the
current state, engine findings, and next steps.

## How it works

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
