"""Live-process memory helpers for k2.exe (32-bit, SteamStub-wrapped).

Shared by the RE scripts in this folder. Nothing here writes to disk inside the
game folder; k2.exe on disk is never modified (it is DRM-encrypted at rest).

    import k2mem
    p = k2mem.K2()          # attaches to the running k2.exe
    p.base, p.size          # module base / image size
    p.read(addr, n)         # bytes
    p.read_f32(addr)        # float
    p.write(addr, data)     # auto VirtualProtectEx RWX, restore after
    p.dump(path)            # save the whole decrypted image
"""

import ctypes
import ctypes.wintypes as wt
import struct
import sys

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_ALL_ACCESS = 0x1F0FFF
PAGE_EXECUTE_READWRITE = 0x40
MEM_COMMIT = 0x1000
TH32CS_SNAPMODULE = 0x8
TH32CS_SNAPMODULE32 = 0x10


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)), ("modBaseSize", wt.DWORD),
        ("hModule", wt.HMODULE), ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD),
    ]


def find_pid(name="k2.exe"):
    """Return the pid of the running game, or None."""
    import subprocess
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH", "/FO", "CSV"],
        capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith('"'):
            parts = [p.strip('"') for p in line.split('","')]
            return int(parts[1])
    return None


class K2:
    def __init__(self, pid=None):
        self.pid = pid or find_pid()
        if not self.pid:
            raise RuntimeError("k2.exe is not running")
        self.h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, self.pid)
        if not self.h:
            raise RuntimeError(f"OpenProcess failed: {ctypes.get_last_error()}")
        self.base, self.size = self._module()

    def _module(self):
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, self.pid)
        me = MODULEENTRY32()
        me.dwSize = ctypes.sizeof(me)
        if not k32.Module32First(snap, ctypes.byref(me)):
            raise RuntimeError("Module32First failed")
        while True:
            if me.szModule.decode(errors="ignore").lower() == "k2.exe":
                addr = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
                k32.CloseHandle(snap)
                return addr, me.modBaseSize
            if not k32.Module32Next(snap, ctypes.byref(me)):
                break
        k32.CloseHandle(snap)
        raise RuntimeError("k2.exe module not found")

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
        return buf.raw[:got.value]

    def read_f32(self, addr):
        d = self.read(addr, 4)
        return struct.unpack("<f", d)[0] if len(d) == 4 else None

    def read_mat4(self, addr):
        d = self.read(addr, 64)
        return list(struct.unpack("<16f", d)) if len(d) == 64 else None

    def write(self, addr, data):
        """Write bytes, temporarily making the page RWX. Returns True on success."""
        old = wt.DWORD(0)
        k32.VirtualProtectEx(self.h, ctypes.c_void_p(addr), ctypes.c_size_t(len(data)),
                             PAGE_EXECUTE_READWRITE, ctypes.byref(old))
        wrote = ctypes.c_size_t(0)
        ok = k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, len(data),
                                    ctypes.byref(wrote))
        restored = wt.DWORD(0)
        k32.VirtualProtectEx(self.h, ctypes.c_void_p(addr), ctypes.c_size_t(len(data)),
                             old, ctypes.byref(restored))
        return bool(ok) and wrote.value == len(data)

    def regions(self, writable_only=False):
        """Yield (base, size, protect) for every committed region."""
        addr = 0x10000
        mbi = MEMORY_BASIC_INFORMATION()
        while addr < 0x7FFF0000:
            if not k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                      ctypes.sizeof(mbi)):
                break
            b, sz, prot = mbi.BaseAddress or 0, mbi.RegionSize, mbi.Protect
            if mbi.State == MEM_COMMIT and sz:
                rw = prot in (0x04, 0x40, 0x08, 0x80)
                if not writable_only or rw:
                    yield b, sz, prot
            addr = b + sz if sz else addr + 0x1000

    def dump(self, path):
        """Save the decrypted module image (base..base+size) to a flat file."""
        data = bytearray()
        for off in range(0, self.size, 0x10000):
            n = min(0x10000, self.size - off)
            chunk = self.read(self.base + off, n)
            data += chunk if len(chunk) == n else b"\x00" * n
        with open(path, "wb") as f:
            f.write(data)
        return len(data)

    def alive(self):
        code = wt.DWORD(0)
        k32.GetExitCodeProcess(self.h, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE


if __name__ == "__main__":
    p = K2()
    print(f"pid={p.pid} base=0x{p.base:X} size=0x{p.size:X}")
    if len(sys.argv) > 1:
        n = p.dump(sys.argv[1])
        print(f"dumped {n} bytes -> {sys.argv[1]}")
