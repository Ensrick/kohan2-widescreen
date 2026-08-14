#!/usr/bin/env python3
"""Native-16:9 frustum patch for Kohan II (runtime code detour).

WHY THIS instead of the _11 redirect:
  The projection builder at k2.exe+0x495280 computes the view frustum from a
  bounds struct (arg4 = {L,R,B,T,near,far,...}):
      _11 = 2*near/(R-L)      _22 = 2*near/(B-T)
  and copies that same (R-L)-derived data into the camera-state object used for
  culling and the visible-ground quad. The old fix scaled only _11 (the displayed
  projection), so the world showed 16:9 but the drawn/culled region stayed 4:3 -
  the black band past the old edge, plus vegetation/shadow desync.

  This fix widens (R-L) about its midpoint at the builder's ENTRY, so projection
  AND cull/draw extent both become 16:9 in lockstep - i.e. as if the engine were
  natively widescreen. Vertical FOV (B-T) is untouched => Hor+.

  a=(1+f)/2, b=(1-f)/2, f = realAspect / (4/3):
      L' = a*L + b*R     R' = b*L + a*R
  which preserves the midpoint and scales the width by exactly f.

  With this installed, the _11 redirect MUST be reverted (this module does it),
  otherwise the correction is applied twice.

Detour: overwrite the 5-byte entry prologue (sub esp,0x18 / push ebx / push esi)
with a jmp to a VirtualAllocEx cave that widens L/R, runs the displaced prologue,
and jmps back.

    py -3 frustumpatch.py --apply            # aspect from the game window
    py -3 frustumpatch.py --apply --aspect 16:9
    py -3 frustumpatch.py --verify
    py -3 frustumpatch.py --revert
"""
import ctypes, struct, sys
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import k2mem, k2patch

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
TH32CS_SNAPTHREAD = 0x4
THREAD_SUSPEND_RESUME = 0x0002


class _THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                ("th32ThreadID", ctypes.c_ulong), ("th32OwnerProcessID", ctypes.c_ulong),
                ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", ctypes.c_ulong)]


def _thread_ids(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = _THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
    out = []
    if k32.Thread32First(snap, ctypes.byref(te)):
        while True:
            if te.th32OwnerProcessID == pid:
                out.append(te.th32ThreadID)
            if not k32.Thread32Next(snap, ctypes.byref(te)):
                break
    k32.CloseHandle(snap)
    return out


class _FrozenProcess:
    """Suspend every thread of the target for the duration of a code write, so we
    never overwrite an instruction a thread is mid-execution on (that AV'd once)."""
    def __init__(self, pid):
        self.pid = pid; self.handles = []

    def __enter__(self):
        for tid in _thread_ids(self.pid):
            h = k32.OpenThread(THREAD_SUSPEND_RESUME, False, tid)
            if h:
                k32.SuspendThread(h)
                self.handles.append(h)
        return self

    def __exit__(self, *a):
        for h in self.handles:
            k32.ResumeThread(h); k32.CloseHandle(h)
        self.handles = []

# Detour INSIDE the projection-setup branch, AFTER edi is reloaded from arg5 at
# 0x895454 so it points at the real frustum bounds struct
# {L@0,R@4,B@8,T@0xc,near@0x10,far@0x14,persp-flag@0x18}. (arg4, the earlier edi,
# was the camera basis vectors - widening that did nothing.) This runs before the
# width (R-L) is consumed for the projection, so widening L,R here fixes it.
# Displaced bytes (eax is reloaded by the first, so our fnstsw clobber is safe):
#   0x89545D  8b02            mov eax,[edx]
#   0x89545F  8d8e20030000    lea ecx,[esi+0x320]     (resume at 0x895465)
PROJ_RVA = 0x49545D
DISPLACED = bytes.fromhex("8b028d8e20030000")   # 8 bytes (jmp5 + 3 nop fills it)
RESUME_RVA = 0x495465
FUNC_RVA = PROJ_RVA                 # patch-site alias used by is_patched/read_counters
JMP_SIG = 0xE9
PREFERRED_CAVE = 0x20010000
MEM_COMMIT_RESERVE = 0x3000
PAGE_EXECUTE_READWRITE = 0x40


def alloc_cave(p):
    for want in (PREFERRED_CAVE, None):
        a = k32.VirtualAllocEx(p.h, ctypes.c_void_p(want) if want else None,
                               4096, MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE)
        if a:
            return a
    raise RuntimeError("VirtualAllocEx failed")


CTR_ENTRY = 0x800      # in-cave counter: detour executed
CTR_WIDEN = 0x804      # in-cave counter: both guards passed, widen ran
CTR_PERSP = 0x808      # in-cave counter: perspective gate passed
SLOT_RATIO = 0x80C     # in-cave float: last perspective cam's |(R-L)/(B-T)|


def build_cave(cave, resume_va, a_val, b_val, instrument=False):
    """Return (blob, code_va). Layout: [a][b][4/3][eps][code...].

    Runs at the projection-setup site with edi = frustum bounds. Guards:
      - perspective only: byte [edi+0x18] == 0  (else skip - leaves ortho/minimap)
      - ~4:3 only: |(R-L)/(B-T)| within eps of 4/3 (idempotent; skips already-16:9)
    Then widens L,R about their midpoint by f:  L'=aL+bR, R'=bL+aR.
    Uses only edi + the FPU (+ ax via fnstsw, which is dead here). No stack args.

    instrument=True adds inc [cave+CTR_ENTRY] at start and inc [cave+CTR_WIDEN]
    at the widen branch.
    """
    a_addr, b_addr, ft_addr, eps_addr = cave + 0, cave + 4, cave + 8, cave + 12
    code = cave + 16
    inc_entry = (b"\xff\x05" + struct.pack("<I", cave + CTR_ENTRY)) if instrument else b""
    inc_widen = (b"\xff\x05" + struct.pack("<I", cave + CTR_WIDEN)) if instrument else b""

    # --- widen body (part B), edi-based ---
    partB = inc_widen
    partB += bytes.fromhex("d907")                 # fld  [edi]        L
    partB += bytes.fromhex("d94704")               # fld  [edi+4]      R | L
    partB += bytes.fromhex("d9c1")                 # fld  st1          L R L
    partB += b"\xd8\x0d" + struct.pack("<I", a_addr)   # fmul [a]      aL R L
    partB += bytes.fromhex("d9c1")                 # fld  st1          R aL R L
    partB += b"\xd8\x0d" + struct.pack("<I", b_addr)   # fmul [b]      bR aL R L
    partB += bytes.fromhex("dec1")                 # faddp st1,st0     newL R L
    partB += bytes.fromhex("d9c2")                 # fld  st2          L newL R L
    partB += b"\xd8\x0d" + struct.pack("<I", b_addr)   # fmul [b]      bL newL R L
    partB += bytes.fromhex("d9c2")                 # fld  st2          R bL newL R L
    partB += b"\xd8\x0d" + struct.pack("<I", a_addr)   # fmul [a]      aR bL newL R L
    partB += bytes.fromhex("dec1")                 # faddp st1,st0     newR newL R L
    partB += bytes.fromhex("d95f04")               # fstp [edi+4]      store R'
    partB += bytes.fromhex("d91f")                 # fstp [edi]        store L'
    partB += bytes.fromhex("ddd8")                 # fstp st0          pop
    partB += bytes.fromhex("ddd8")                 # fstp st0          pop

    partC = bytearray(DISPLACED)                   # displaced insns (SKIP lands here)

    inc_persp = (b"\xff\x05" + struct.pack("<I", cave + CTR_PERSP)) if instrument else b""
    fst_ratio = (b"\xd9\x15" + struct.pack("<I", cave + SLOT_RATIO)) if instrument else b""

    # --- guard (part A), edi-based ---
    partA = inc_entry
    partA += bytes.fromhex("807f1800")             # cmp byte [edi+0x18], 0  (persp flag)
    JNE = b"\x0f\x85"                              # jne SKIP (not perspective)
    partA += JNE + b"\x00\x00\x00\x00"
    partA += inc_persp                             # count perspective-gate passes
    partA += bytes.fromhex("d94704")               # fld  [edi+4]     R
    partA += bytes.fromhex("d827")                 # fsub [edi]       R-L
    partA += bytes.fromhex("d94708")               # fld  [edi+8]     B | (R-L)
    partA += bytes.fromhex("d8670c")               # fsub [edi+0xc]   B-T | (R-L)
    partA += bytes.fromhex("def9")                 # fdivp st1,st0    (R-L)/(B-T)
    partA += bytes.fromhex("d9e1")                 # fabs             |ratio|
    partA += fst_ratio                             # store |ratio| (keeps st0)
    partA += b"\xd8\x25" + struct.pack("<I", ft_addr)  # fsub [4/3]
    partA += bytes.fromhex("d9e1")                 # fabs
    partA += b"\xd8\x1d" + struct.pack("<I", eps_addr) # fcomp [eps]
    partA += bytes.fromhex("dfe0")                 # fnstsw ax
    partA += bytes.fromhex("9e")                   # sahf
    JAE = b"\x0f\x83"                              # jae SKIP (not ~4:3)
    partA += JAE + b"\x00\x00\x00\x00"

    b_off = len(partA)
    c_off = b_off + len(partB)
    skip_va = code + c_off

    # patch JNE (skip if not perspective): opcode at inc(len)+cmp(4)
    jne_pos = len(inc_entry) + 4
    jne_end = code + jne_pos + 2 + 4
    partA = partA[:jne_pos + 2] + struct.pack("<i", skip_va - jne_end) + partA[jne_pos + 6:]
    # patch JAE (skip if not ~4:3): last 6 bytes of partA
    jae_pos = len(partA) - 6
    jae_end = code + len(partA)
    partA = partA[:jae_pos + 2] + struct.pack("<i", skip_va - jae_end)

    body = partA + partB + bytes(partC)
    jmp_from = code + len(body)
    body += b"\xe9" + struct.pack("<i", resume_va - (jmp_from + 5))

    header = struct.pack("<ffff", a_val, b_val, 4.0 / 3.0, 0.06)
    return header + body, code


def is_patched(p):
    b = p.read(p.base + FUNC_RVA, 1)
    return len(b) == 1 and b[0] == JMP_SIG


def apply(p, aspect=None, instrument=False):
    # 1. make sure the _11 redirect is OFF (this fix supersedes it)
    if p.read(p.base + k2patch.FLD_11_RVA, 6) != k2patch.ORIG_BYTES:
        with _FrozenProcess(p.pid):
            k2patch.revert(p)
        print("reverted _11 redirect (superseded by frustum patch)")
    if is_patched(p):
        print("frustum patch already installed"); return
    w, h = k2patch.backbuffer_size(p.pid)
    real = aspect if aspect else (w / h)
    f = real / (4.0 / 3.0)
    a_val = (1.0 + f) / 2.0
    b_val = (1.0 - f) / 2.0
    cave = alloc_cave(p)
    resume_va = p.base + RESUME_RVA
    blob, code_va = build_cave(cave, resume_va, a_val, b_val, instrument=instrument)
    # cave is brand-new memory no thread executes yet -> safe to write unfrozen
    if not p.write(cave, blob):
        raise RuntimeError("failed writing cave")
    # entry jmp is LIVE code -> freeze threads so we never tear an in-flight insn
    entry = p.base + PROJ_RVA
    rel = code_va - (entry + 5)
    patch = b"\xe9" + struct.pack("<i", rel) + b"\x90" * (len(DISPLACED) - 5)
    with _FrozenProcess(p.pid):
        if not p.write(entry, patch):
            raise RuntimeError("failed writing entry jmp")
    self_cave[0] = cave
    print(f"backbuffer {w}x{h}  real {real:.5f}  f={f:.5f}  a={a_val:.5f} b={b_val:.5f}")
    print(f"cave 0x{cave:08X} (code 0x{code_va:08X}); entry k2.exe+0x{FUNC_RVA:X} -> jmp cave"
          f"{'  [instrumented]' if instrument else ''}")
    print("frustum widened at source; _11 redirect left original")


self_cave = [None]     # remember the cave addr this session for counter reads


def read_counters(p):
    """dict(entry, persp, widen, ratio) from the instrumented cave, or None."""
    entry = p.read(p.base + PROJ_RVA, 5)
    if len(entry) < 5 or entry[0] != JMP_SIG:
        return None
    rel = struct.unpack("<i", entry[1:5])[0]
    cave = (p.base + PROJ_RVA + 5 + rel) - 16

    def u32(off):
        d = p.read(cave + off, 4)
        return struct.unpack("<I", d)[0] if len(d) == 4 else None

    def f32(off):
        d = p.read(cave + off, 4)
        return struct.unpack("<f", d)[0] if len(d) == 4 else None

    return {"entry": u32(CTR_ENTRY), "persp": u32(CTR_PERSP),
            "widen": u32(CTR_WIDEN), "ratio": f32(SLOT_RATIO)}


def revert(p):
    if not is_patched(p):
        print("frustum patch not installed"); return
    with _FrozenProcess(p.pid):
        p.write(p.base + PROJ_RVA, DISPLACED)
    print(f"reverted k2.exe+0x{PROJ_RVA:X} (cave leaked, harmless)")


def verify(p):
    print(f"frustum patch: {'INSTALLED' if is_patched(p) else 'absent'}")
    cur = p.read(p.base + k2patch.FLD_11_RVA, 6)
    print(f"_11 redirect: {'ORIGINAL' if cur == k2patch.ORIG_BYTES else 'PATCHED'}")
    k2patch.verify(p)


if __name__ == "__main__":
    p = k2mem.K2()
    print(f"pid={p.pid} base=0x{p.base:X}")
    asp = None
    if "--aspect" in sys.argv:
        s = sys.argv[sys.argv.index("--aspect") + 1]
        asp = (float(s.split(":")[0]) / float(s.split(":")[1])) if ":" in s else float(s)
    if "--apply" in sys.argv:
        apply(p, asp); print(); verify(p)
    elif "--revert" in sys.argv:
        revert(p)
    else:
        verify(p)
