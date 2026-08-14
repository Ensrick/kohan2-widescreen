# Aspect-ratio patch - how it works

Kohan II builds every 3D camera's view frustum with a **hardcoded 4:3 aspect** and then
stretches that image across whatever backbuffer you run. At 16:9 the world is exactly
1.333x too wide. This patch corrects it at runtime.

## Why it must be a runtime patch, not a file edit

`k2.exe` is **SteamStub-encrypted** (`.text` on-disk entropy 7.999; entry point sits in a
trailing `.bind` DRM stub). The real code and its constants only exist after the stub
decrypts them into memory at launch. There is no on-disk byte to edit, and shipping a
decrypted/unpacked exe is not an option. So the fix attaches to the running, decrypted
process and edits one instruction in memory. Nothing on disk is touched.

## The exact fix

Located with a hardware-breakpoint "find-what-writes" on the live projection matrix
(`tools/hwbp.py`), traced back to the frustum builder at **`k2.exe+0x495598`**:

```
_11 = 2 * C / (right - left)     ; horizontal scale
_22 = 2 * C / (top  - bottom)    ; vertical scale
```

Both axes load the same constant `C = 1.0f` (at VA `0x009b43ec` in `.rdata`) through two
**separate** `fld dword ptr [0x009b43ec]` instructions. Because `1.0f` is shared by code
all over the binary, you cannot just change the constant. Instead the loader allocates a
4-byte "cave", stores `k = (4/3) / realAspect` there, and redirects **only the `_11`
load** to it:

```
k2.exe+0x495598:  d9 05 ec 43 9b 00   fld dword ptr [0x009b43ec]   ; C = 1.0
        ->        d9 05 <cave addr>   fld dword ptr [cave]         ; k = 0.75 at 16:9
```

Scaling `_11` alone keeps the vertical field of view and widens the horizontal one (the
"Hor+" widescreen behavior - you see more at the sides, nothing is cropped). After the
edit `_22/_11` equals the true backbuffer aspect. `k` is derived from the game window's
actual client size, so it is correct at any resolution/aspect (1.0 at 4:3 = no-op).

The edit is a single 4-byte operand change; it persists for the whole session (patching
the per-frame matrix values does not stick - the engine rewrites them every frame).

## Usage

### Automatic on every launch (recommended)

One-time install - Steam > Library > Kohan II: Kings of War > Properties > General >
Launch Options:

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\danjo\source\repos\kohan2-widescreen\tools\k2ws-steam.ps1" %command%
```

Steam then runs the wrapper in place of the game. It starts the real game command as a
child (inheriting Steam's environment, so SteamStub decrypts normally), patches the
instruction the moment the code is decrypted, and stays resident until the game exits,
keeping `k` synced to the live window size every 2 s. That last part matters twice:

- at startup the only window may be a 4:3 splash, which would bake in `k = 1.0` (a
  silent no-op) if computed once;
- an in-game resolution change would otherwise leave a stale `k`.

Because the patched instruction rereads the cave on every frustum build, refreshing the
4 cave bytes is all "live aspect" takes - no re-patching. To uninstall, clear the
launch options; nothing on disk is modified either way. If the game dies within
seconds of a wrapped launch (SteamStub refusing a non-Steam parent), the wrapper logs
it to `Logs\k2widescreen.log` and gives up cleanly - fall back to the manual loader
below.

### Manual / one-shot

Steam must be running (SteamStub needs it to decrypt). From `tools/`:

```powershell
# Launch the game via Steam and patch it once it is up:
.\k2widescreen.ps1

# Or, if the game is already running (recommended for a visual check):
.\k2widescreen.ps1 -AttachOnly

# Force a specific aspect instead of deriving from the window:
.\k2widescreen.ps1 -AttachOnly -Aspect 16:9

# Undo the in-memory patch (or just restart the game):
.\k2widescreen.ps1 -Revert
```

The projection is only built while a 3D world is on screen (a skirmish/campaign/editor
map, not the main menu), so apply the patch after a map is loaded and verify there.

## Tooling (the RE record)

| File | Role |
|---|---|
| `tools/hwbp.py` | WOW64 hardware-breakpoint find-what-writes; how `0x495598` was located. |
| `tools/k2mem.py` | Process open / read / write / module base helpers. |
| `tools/matscan.py` | Scans committed memory for 4x4 float projection matrices. |
| `tools/k2patch.py` | Applies/verifies/reverts the 4-byte redirect; `verify()` proves `_22/_11 == backbuffer aspect`; `--watch` stays resident syncing `k` to the window. |
| `tools/k2widescreen.ps1` | Manual loader: launch (via Steam) or attach, wait for decrypt, patch, log. |
| `tools/k2ws-steam.ps1` | Steam launch-options wrapper: auto-patch + watch on every launch. |
| `tools/vpscan.py` | Scans live memory for D3DVIEWPORT9 structs (render rect vs backbuffer check). |
| `tools/mute_k2.ps1` | Per-app mute of k2 audio sessions (used during headless RE). |
| `tools/analyze.py` | Static PE/capstone scan - kept as the record of why static patching is impossible (encrypted `.text`). |

## Status

Located and patched; the loader ran successfully (`Logs\log-203-ok.log`). The
launch-options wrapper (`k2ws-steam.ps1`) makes it automatic per launch. Still owed:

1. a human visual check that the world looks correct at the native 3840x2160;
2. one wrapped launch to confirm this SteamStub build accepts a non-Steam parent
   process (it inherits Steam's environment, which is what the stub checks, but this
   build has not been tried).
