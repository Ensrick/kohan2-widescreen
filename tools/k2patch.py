#!/usr/bin/env python3
"""Runtime aspect-ratio patch for Kohan II: Kings of War (in memory only).

WHY IN MEMORY: k2.exe is SteamStub-encrypted on disk (.text entropy 7.999). There is
no static patch to make - the real code only exists after the stub decrypts it at
runtime - and shipping a decrypted exe is not an option.

THE BUG: the engine (Gamebryo/NetImmerse) builds every camera's view frustum with a
hardcoded 4:3 aspect and then stretches it across whatever backbuffer you run, so at
16:9 the world is 1.333x too wide.

THE FIX: in the projection builder at k2.exe+0x495598 the engine computes

    _11 = 2 * C / (right - left)        ; C = 1.0f at 0x009b43ec
    _22 = 2 * C / (top  - bottom)       ; separate reload of the same C

Both axes read the same constant through two *separate* `fld dword ptr [0x009b43ec]`
instructions. Redirecting only the _11 one to a float we own scales _11 alone:

    _11' = _11 * k,  k = (4/3) / realAspect

which keeps the vertical FOV and widens the horizontal one (the "Hor+" fix), and makes
_22/_11 equal the true backbuffer aspect. It is a 4-byte operand edit; no code cave.

    py -3 k2patch.py --verify
    py -3 k2patch.py --apply
    py -3 k2patch.py --apply --aspect 16:9
    py -3 k2patch.py --apply --wait --watch --pid 1234   # loader mode: stay resident,
                                                         # keep k synced to the window
    py -3 k2patch.py --revert
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import k2mem
import matscan

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

# --- the patch site, module-relative so it survives any rebase -----------------
FLD_11_RVA = 0x495598           # fld dword ptr [0x009b43ec]  feeding _11
ORIG_BYTES = bytes.fromhex("d905ec439b00")
OPERAND_OFF = 2                 # the imm32 sits at +2 in that instruction
C_CONST_VA = 0x009b43ec         # the shared 1.0f
PREFERRED_CAVE = 0x20000000     # try for a stable address so logs are comparable

MEM_COMMIT_RESERVE = 0x3000
PAGE_READWRITE = 0x04


def backbuffer_size(pid):
    """The real render-target size = the game window's client area."""
    EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    best = [0, 0]

    def cb(h, _):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            r = wt.RECT()
            u32.GetClientRect(h, ctypes.byref(r))
            if r.right * r.bottom > best[0] * best[1]:
                best[0], best[1] = r.right, r.bottom
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return best[0], best[1]


def alloc_cave(p):
    addr = k32.VirtualAllocEx(p.h, ctypes.c_void_p(PREFERRED_CAVE), 4096,
                              MEM_COMMIT_RESERVE, PAGE_READWRITE)
    if not addr:
        addr = k32.VirtualAllocEx(p.h, None, 4096, MEM_COMMIT_RESERVE, PAGE_READWRITE)
    if not addr:
        raise RuntimeError("VirtualAllocEx failed")
    return addr


def find_existing_cave(p):
    """If we already patched this process, recover the float address from the operand."""
    cur = p.read(p.base + FLD_11_RVA, 6)
    if len(cur) == 6 and cur[:2] == ORIG_BYTES[:2]:
        operand = struct.unpack_from("<I", cur, OPERAND_OFF)[0]
        if operand != C_CONST_VA:
            return operand
    return None


def wait_ready(pid, timeout=120.0):
    """Block until SteamStub has decrypted .text, then return the K2 handle.

    Readiness test: the patch site reads back as the exact original instruction. While
    the section is still encrypted those six bytes are ciphertext, so this doubles as a
    'the code is decrypted AND this is the build we understand' check - no sleep-guessing.
    """
    import time
    start = time.time()
    last = None
    died = False
    while time.time() - start < timeout:
        try:
            p = k2mem.K2(pid)
            got = p.read(p.base + FLD_11_RVA, 6)
            # Also require a real window: the correction factor comes from the
            # backbuffer size, which is only knowable once the client area exists.
            w, h = backbuffer_size(p.pid)
            if w and h and (got == ORIG_BYTES or find_existing_cave(p)):
                return p
            last = got
            died = not p.alive()
        except Exception as e:
            last = str(e)
        if died:
            raise RuntimeError("k2.exe exited before the code decrypted "
                               "(SteamStub refused? launched without Steam?)")
        time.sleep(0.25)
    raise RuntimeError(f"k2.exe never presented the expected code at "
                       f"+{FLD_11_RVA:#x} (last saw {last}); wrong game build?")


def verify(p, expect=None):
    w, h = backbuffer_size(p.pid)
    real = (w / h) if h else 0
    print(f"backbuffer {w}x{h}  ->  real aspect {real:.6f}")
    cur = p.read(p.base + FLD_11_RVA, 6)
    print(f"k2.exe+{FLD_11_RVA:#x}: {cur.hex()}  "
          f"({'ORIGINAL' if cur == ORIG_BYTES else 'PATCHED'})")
    cave = find_existing_cave(p)
    if cave:
        print(f"  _11 constant redirected to 0x{cave:08X} = {p.read_f32(cave):.8f}")
    mats = matscan.scan(p)
    ok = bad = 0
    print(f"{'address':>12}  {'_11':>11} {'_22':>11}  {'_22/_11':>9}  verdict")
    for addr, m in mats:
        _11, _22 = m[0], m[5]
        ratio = _22 / _11 if _11 else 0
        if abs(ratio - 1.0) < 1e-3:
            verdict = "square cam (left alone)"
        elif real and abs(ratio - real) / real <= 0.005:
            verdict = "OK  matches backbuffer"
            ok += 1
        else:
            verdict = f"stretched (want {real:.4f})"
            bad += 1
        print(f"  0x{addr:08X}  {_11:11.6f} {_22:11.6f}  {ratio:9.4f}  {verdict}")
    print(f"\n{ok} camera(s) matching backbuffer aspect, {bad} still stretched")
    return ok, bad


def apply(p, aspect=None):
    w, h = backbuffer_size(p.pid)
    real = aspect if aspect else (w / h)
    k = (4.0 / 3.0) / real
    cur = p.read(p.base + FLD_11_RVA, 6)
    if cur != ORIG_BYTES:
        cave = find_existing_cave(p)
        if cave:
            p.write(cave, struct.pack("<f", k))
            print(f"already patched; updated k -> {k:.8f} at 0x{cave:08X}")
            return cave
        raise RuntimeError(f"unexpected bytes at patch site: {cur.hex()}")
    cave = alloc_cave(p)
    p.write(cave, struct.pack("<f", k))
    newb = ORIG_BYTES[:OPERAND_OFF] + struct.pack("<I", cave)
    if not p.write(p.base + FLD_11_RVA, newb):
        raise RuntimeError("failed to write patch")
    print(f"backbuffer {w}x{h}  real aspect {real:.6f}  k = (4/3)/aspect = {k:.8f}")
    print(f"k stored at 0x{cave:08X}")
    print(f"k2.exe+{FLD_11_RVA:#x}: {ORIG_BYTES.hex()} -> {newb.hex()}")
    print(f"   fld dword ptr [0x{C_CONST_VA:08X}]  ->  fld dword ptr [0x{cave:08X}]")
    return cave


def watch(p, aspect=None, interval=2.0):
    """Stay resident and keep the cave's k in sync with the live window size.

    Why: at launch the only window may be a 4:3 splash (k=1.0, a silent no-op), and
    the user can change resolution in-game. The patched instruction rereads the cave
    on every frustum build, so refreshing the 4 cave bytes is all "live aspect" takes.
    Returns when the game exits.
    """
    import time
    cave = find_existing_cave(p)
    if not cave:
        raise RuntimeError("watch: process is not patched")
    if aspect:
        k = (4.0 / 3.0) / aspect
        p.write(cave, struct.pack("<f", k))
        print(f"watch: aspect forced, k pinned at {k:.8f}; idling until game exit",
              flush=True)
        while p.alive():
            time.sleep(interval)
        return
    last = None
    while p.alive():
        w, h = backbuffer_size(p.pid)
        if w and h and (w, h) != last:      # 0x0 = minimized/no window: keep last k
            k = (4.0 / 3.0) / (w / h)
            p.write(cave, struct.pack("<f", k))
            print(f"watch: window {w}x{h} -> k = {k:.8f}", flush=True)
            last = (w, h)
        time.sleep(interval)
    print("watch: game exited")


def revert(p):
    cur = p.read(p.base + FLD_11_RVA, 6)
    if cur == ORIG_BYTES:
        print("already original")
        return
    p.write(p.base + FLD_11_RVA, ORIG_BYTES)
    print(f"reverted k2.exe+{FLD_11_RVA:#x} -> {ORIG_BYTES.hex()}")


if __name__ == "__main__":
    pid = int(sys.argv[sys.argv.index("--pid") + 1]) if "--pid" in sys.argv else None
    if "--wait" in sys.argv:
        p = wait_ready(pid, 120.0)
    else:
        p = k2mem.K2(pid)
    print(f"pid={p.pid} base=0x{p.base:X}")
    asp = None
    if "--aspect" in sys.argv:
        s = sys.argv[sys.argv.index("--aspect") + 1]
        asp = (float(s.split(":")[0]) / float(s.split(":")[1])) if ":" in s else float(s)
    if "--apply" in sys.argv:
        apply(p, asp)
        if "--watch" in sys.argv:
            watch(p, asp)
        else:
            print()
            verify(p)
    elif "--revert" in sys.argv:
        revert(p)
    else:
        verify(p)
