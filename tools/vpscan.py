#!/usr/bin/env python3
"""Scan the live k2.exe for D3DVIEWPORT9 structures.

D3DVIEWPORT9 = { DWORD X, Y, Width, Height; float MinZ, MaxZ }.
MinZ/MaxZ are almost always 0.0f / 1.0f, giving an 8-byte anchor
(00 00 00 00 00 00 80 3F). Read the 16 bytes before it as X,Y,W,H.
Reports plausible viewports so we can see whether the 3D render rect is
the full backbuffer (3840x2160) or a pillarboxed 4:3 sub-rect.

    py -3 vpscan.py            # uses running k2.exe
"""
import struct, sys
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import k2mem

ANCHOR = struct.pack("<ff", 0.0, 1.0)   # MinZ=0.0, MaxZ=1.0


def main():
    p = k2mem.K2()
    print(f"pid={p.pid} base=0x{p.base:X}")
    seen = {}
    for b, sz, prot in p.regions(writable_only=True):
        if sz > 64 * 1024 * 1024:
            continue
        data = p.read(b, sz)
        idx = 0
        while True:
            j = data.find(ANCHOR, idx)
            if j < 0:
                break
            idx = j + 1
            if j < 16:
                continue
            x, y, w, h = struct.unpack_from("<IIII", data, j - 16)
            # plausibility: sane screen dims
            if 320 <= w <= 8192 and 200 <= h <= 4320 and x < 8192 and y < 4320:
                key = (x, y, w, h)
                seen[key] = seen.get(key, 0) + 1
    print(f"{'X':>6} {'Y':>6} {'W':>6} {'H':>6}  {'W/H':>7}  count")
    for (x, y, w, h), c in sorted(seen.items(), key=lambda kv: -kv[1]):
        ar = w / h if h else 0
        note = ""
        if abs(ar - 4/3) < 0.02: note = "4:3"
        elif abs(ar - 16/9) < 0.02: note = "16:9"
        elif abs(ar - 16/10) < 0.02: note = "16:10"
        print(f"{x:6} {y:6} {w:6} {h:6}  {ar:7.4f}  {c:5}  {note}")


if __name__ == "__main__":
    main()
