# Contributing

## Setup

1. Kohan II: Kings of War v1.2.3 (Steam), default install at
   `C:\Program Files (x86)\Steam\steamapps\common\Kohan II` (both tools take a
   `-GameDir` override).
2. The game loads loose files in `Data\` over the `Data.rwd` archive, no repack needed.
   To browse vanilla data for reference, extract `Data.rwd` with the community
   K2ExtractRWD tool (archived in the Battleborn repo under `tools/third_party/`).

## Workflow

1. Edit files in the repo, run `tools\deploy.ps1`, and test in-game - resolution
   changes are safest set before launch (in-game switching can crash on modern Windows).
2. If you edited in the game's `Data\` folder instead, run `tools\collect.ps1` to pull
   the display-scoped files back into the repo.
3. Update `CHANGELOG.md` under `[Unreleased]` in the same commit.
4. Push. Pull requests and issues live on GitHub; the GitLab remote is a mirror.

## Rules

- **Only new or modified override files.** Never commit unmodified game data, the
  `.rwd` archives, or the game executable.
- **Stay in scope.** This repo owns display-related files only (`UI/`, `AVars.tgi`,
  `UVars.tgi`, `strings_rtse_ui.tgi`). Gameplay/balance changes belong in the
  Battleborn repo.
- When changing a vanilla value in a `.tgi`, keep the original as a trailing comment
  (existing style: `float CameraFarPlane = 768 ;; 512`).
- Keep `docs/WIDESCREEN.md` current when findings change.
