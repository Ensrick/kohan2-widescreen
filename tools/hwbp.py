#!/usr/bin/env python3
"""Find-what-writes for the running k2.exe, via x86 hardware debug registers.

This is the RE record for the aspect-ratio patch: it is how the projection-building
instruction was located. k2.exe is SteamStub-encrypted on disk, so there is no static
target to breakpoint - the only way in is to attach to the decrypted, running process.

Mechanics: DebugActiveProcess, then on every thread set DR0 = watched address and
DR7 = local-enable + RW=write + LEN=4. The CPU then raises EXCEPTION_SINGLE_STEP
*after* the storing instruction retires, so EIP points just past the writer.

Python here is 64-bit and the target is WOW64, so all context access goes through
Wow64Get/SetThreadContext with a WOW64_CONTEXT.

    py -3 hwbp.py 0x0A2C8CB4              # watch a 4-byte write, report 3 hits
    py -3 hwbp.py 0x0A2C8CB4 --hits 6 --timeout 120
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001
EXCEPTION_DEBUG_EVENT = 1
CREATE_THREAD_DEBUG_EVENT = 2
CREATE_PROCESS_DEBUG_EVENT = 3
EXIT_THREAD_DEBUG_EVENT = 4
EXCEPTION_BREAKPOINT = 0x80000003
EXCEPTION_SINGLE_STEP = 0x80000004

CONTEXT_DEBUG = 0x00010010 | 0x00010001 | 0x00010002 | 0x00010004 | 0x00010008
THREAD_ALL_ACCESS = 0x1FFFFF
TH32CS_SNAPTHREAD = 0x4


class FLOATING_SAVE_AREA(ctypes.Structure):
    _fields_ = [("ControlWord", wt.DWORD), ("StatusWord", wt.DWORD), ("TagWord", wt.DWORD),
                ("ErrorOffset", wt.DWORD), ("ErrorSelector", wt.DWORD), ("DataOffset", wt.DWORD),
                ("DataSelector", wt.DWORD), ("RegisterArea", ctypes.c_byte * 80),
                ("Cr0NpxState", wt.DWORD)]


class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [
        ("ContextFlags", wt.DWORD),
        ("Dr0", wt.DWORD), ("Dr1", wt.DWORD), ("Dr2", wt.DWORD),
        ("Dr3", wt.DWORD), ("Dr6", wt.DWORD), ("Dr7", wt.DWORD),
        ("FloatSave", FLOATING_SAVE_AREA),
        ("SegGs", wt.DWORD), ("SegFs", wt.DWORD), ("SegEs", wt.DWORD), ("SegDs", wt.DWORD),
        ("Edi", wt.DWORD), ("Esi", wt.DWORD), ("Ebx", wt.DWORD), ("Edx", wt.DWORD),
        ("Ecx", wt.DWORD), ("Eax", wt.DWORD), ("Ebp", wt.DWORD), ("Eip", wt.DWORD),
        ("SegCs", wt.DWORD), ("EFlags", wt.DWORD), ("Esp", wt.DWORD), ("SegSs", wt.DWORD),
        ("ExtendedRegisters", ctypes.c_byte * 512),
    ]


class EXCEPTION_RECORD(ctypes.Structure):
    pass


EXCEPTION_RECORD._fields_ = [
    ("ExceptionCode", wt.DWORD), ("ExceptionFlags", wt.DWORD),
    ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)),
    ("ExceptionAddress", ctypes.c_void_p), ("NumberParameters", wt.DWORD),
    ("ExceptionInformation", ctypes.c_void_p * 15)]


class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("ExceptionRecord", EXCEPTION_RECORD), ("dwFirstChance", wt.DWORD)]


class CREATE_THREAD_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("hThread", wt.HANDLE), ("lpThreadLocalBase", ctypes.c_void_p),
                ("lpStartAddress", ctypes.c_void_p)]


class DEBUG_EVENT_U(ctypes.Union):
    _fields_ = [("Exception", EXCEPTION_DEBUG_INFO),
                ("CreateThread", CREATE_THREAD_DEBUG_INFO),
                ("pad", ctypes.c_byte * 200)]


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [("dwDebugEventCode", wt.DWORD), ("dwProcessId", wt.DWORD),
                ("dwThreadId", wt.DWORD), ("u", DEBUG_EVENT_U)]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", wt.LONG),
                ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]


def thread_ids(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    out = []
    if k32.Thread32First(snap, ctypes.byref(te)):
        while True:
            if te.th32OwnerProcessID == pid:
                out.append(te.th32ThreadID)
            if not k32.Thread32Next(snap, ctypes.byref(te)):
                break
    k32.CloseHandle(snap)
    return out


def dr7_for_write4(slot=0):
    """Local-enable slot, RW=01 (data write), LEN=11 (4 bytes)."""
    return (1 << (slot * 2)) | (0b01 << (16 + slot * 4)) | (0b11 << (18 + slot * 4))


def arm(tid, addr, disarm=False):
    h = k32.OpenThread(THREAD_ALL_ACCESS, False, tid)
    if not h:
        return False
    ctx = WOW64_CONTEXT()
    ctx.ContextFlags = CONTEXT_DEBUG
    ok = k32.Wow64GetThreadContext(h, ctypes.byref(ctx))
    if ok:
        ctx.ContextFlags = CONTEXT_DEBUG
        ctx.Dr0 = 0 if disarm else addr
        ctx.Dr7 = 0 if disarm else dr7_for_write4(0)
        ctx.Dr6 = 0
        ok = k32.Wow64SetThreadContext(h, ctypes.byref(ctx))
    k32.CloseHandle(h)
    return bool(ok)


def get_ctx(tid):
    h = k32.OpenThread(THREAD_ALL_ACCESS, False, tid)
    ctx = WOW64_CONTEXT()
    ctx.ContextFlags = CONTEXT_DEBUG
    k32.Wow64GetThreadContext(h, ctypes.byref(ctx))
    k32.CloseHandle(h)
    return ctx


def clear_dr6(tid):
    h = k32.OpenThread(THREAD_ALL_ACCESS, False, tid)
    ctx = WOW64_CONTEXT()
    ctx.ContextFlags = CONTEXT_DEBUG
    if k32.Wow64GetThreadContext(h, ctypes.byref(ctx)):
        ctx.ContextFlags = CONTEXT_DEBUG
        ctx.Dr6 = 0
        k32.Wow64SetThreadContext(h, ctypes.byref(ctx))
    k32.CloseHandle(h)


def st_regs(ctx):
    """Decode the x87 register stack (80-byte area, 8 x 10-byte extended doubles)."""
    raw = bytes(bytearray(ctx.FloatSave.RegisterArea))
    out = []
    for i in range(8):
        b = raw[i * 10:(i + 1) * 10]
        mant = int.from_bytes(b[:8], "little")
        se = int.from_bytes(b[8:10], "little")
        sign = -1 if se & 0x8000 else 1
        exp = se & 0x7FFF
        if exp == 0 and mant == 0:
            out.append(0.0)
            continue
        try:
            out.append(sign * mant * 2.0 ** (exp - 16383 - 63))
        except OverflowError:
            out.append(float("inf"))
    return out


def start_trigger(pid, kind):
    """Poke the engine from a helper thread so the watched write actually happens.

    The projection is not rebuilt every frame at the menu; it is rebuilt on camera
    events. Re-rendering for a screenshot is one such event and is drivable from
    outside the process.
    """
    import threading

    def go():
        time.sleep(1.5)
        sys.path.insert(0, __file__.rsplit("\\", 1)[0])
        import k2console
        h = k2console.main_hwnd(pid)
        for _ in range(6):
            if kind == "screenshot":
                k2console.screenshot(h)
            time.sleep(1.0)

    t = threading.Thread(target=go, daemon=True)
    t.start()


def watch(pid, addr, max_hits=3, timeout=90.0, trigger=None):
    if not k32.DebugActiveProcess(pid):
        raise RuntimeError(f"DebugActiveProcess failed: {ctypes.get_last_error()}")
    k32.DebugSetProcessKillOnExit(False)   # leave the game alive when we detach
    evt = DEBUG_EVENT()
    hits = []
    armed = False
    start = time.time()
    try:
        while len(hits) < max_hits and time.time() - start < timeout:
            if not k32.WaitForDebugEvent(ctypes.byref(evt), 200):
                continue
            code = evt.dwDebugEventCode
            status = DBG_CONTINUE
            if code == EXCEPTION_DEBUG_EVENT:
                ec = evt.u.Exception.ExceptionRecord.ExceptionCode
                if ec == EXCEPTION_BREAKPOINT and not armed:
                    for tid in thread_ids(pid):
                        arm(tid, addr)
                    armed = True
                    print(f"armed DR0=0x{addr:08X} on {len(thread_ids(pid))} threads")
                    if trigger:
                        start_trigger(pid, trigger)
                elif ec == EXCEPTION_SINGLE_STEP:
                    # ALWAYS swallow single-step with DBG_CONTINUE. We are the only
                    # thing arming debug registers, so every one of these is ours -
                    # and handing one back to the app makes its top-level SEH abort
                    # with "unhandled exception - Single Step (80000004)".
                    ctx = get_ctx(evt.dwThreadId)
                    if True:
                        hits.append((evt.dwThreadId, ctx))
                        print(f"\n--- hit {len(hits)} --- tid={evt.dwThreadId} "
                              f"EIP=0x{ctx.Eip:08X} dr6=0x{ctx.Dr6:X} "
                              f"(the write is the instruction just before EIP)")
                        print(f"    eax=0x{ctx.Eax:08X} ebx=0x{ctx.Ebx:08X} ecx=0x{ctx.Ecx:08X} "
                              f"edx=0x{ctx.Edx:08X}")
                        print(f"    esi=0x{ctx.Esi:08X} edi=0x{ctx.Edi:08X} ebp=0x{ctx.Ebp:08X} "
                              f"esp=0x{ctx.Esp:08X}")
                        sts = st_regs(ctx)
                        print(f"    st0..st3 = {sts[0]:.7g} {sts[1]:.7g} {sts[2]:.7g} {sts[3]:.7g}")
                        clear_dr6(evt.dwThreadId)
                    else:
                        status = DBG_EXCEPTION_NOT_HANDLED
                else:
                    status = DBG_EXCEPTION_NOT_HANDLED
            elif code == CREATE_THREAD_DEBUG_EVENT and armed:
                arm(evt.dwThreadId, addr)
            k32.ContinueDebugEvent(evt.dwProcessId, evt.dwThreadId, status)
    finally:
        for tid in thread_ids(pid):
            arm(tid, 0, disarm=True)
        k32.DebugActiveProcessStop(pid)
    return hits


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("\\", 1)[0])
    import k2mem
    addr = int(sys.argv[1], 0)
    hits = int(sys.argv[sys.argv.index("--hits") + 1]) if "--hits" in sys.argv else 3
    tmo = float(sys.argv[sys.argv.index("--timeout") + 1]) if "--timeout" in sys.argv else 90.0
    trig = sys.argv[sys.argv.index("--trigger") + 1] if "--trigger" in sys.argv else None
    pid = k2mem.find_pid()
    print(f"attaching to pid {pid}, watching writes to 0x{addr:08X}")
    got = watch(pid, addr, hits, tmo, trig)
    print(f"\n{len(got)} hit(s); detached, game left running")
