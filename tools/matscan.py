#!/usr/bin/env python3
"""Find live D3D perspective-projection matrices in the running k2.exe.

The engine is NetImmerse/Gamebryo, so the projection it hands D3D is the standard
row-major LH form:

    _11   0    0    0
     0   _22   0    0
    _31  _32  _33  1.0
     0    0   _43   0

with _11 = 2n/(r-l), _22 = 2n/(t-b), _33 = f/(f-n), _43 = -nf/(f-n).
That shape (six exact zeros plus an exact 1.0 at _34) is rare enough in RAM to
identify projections without any guessing about ratios.

    py -3 matscan.py                # list every live projection matrix
    py -3 matscan.py --watch 5      # re-list every second for 5 s (see which move)
"""
import struct
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import k2mem


def scan(p):
    """Yield (addr, 16 floats) for every projection-shaped matrix in committed RAM."""
    hits = []
    for base, size, prot in p.regions(writable_only=True):
        if size > 256 * 1024 * 1024:
            continue
        data = p.read(base, size)
        n = len(data)
        # _34 == 1.0f is the cheapest anchor: scan for it, then validate the rest.
        idx = 0
        one = struct.pack("<f", 1.0)
        while True:
            j = data.find(one, idx)
            if j < 0 or j + 16 > n:
                break
            idx = j + 4
            start = j - 44  # _34 sits at matrix offset 0x2C
            if start < 0 or start + 64 > n:
                continue
            m = struct.unpack_from("<16f", data, start)
            # exact zeros required at _12 _13 _14 _21 _23 _24 _41 _42 _44
            if any(m[k] != 0.0 for k in (1, 2, 3, 4, 6, 7, 12, 13, 15)):
                continue
            if not (0.01 < m[0] < 1e4 and 0.01 < m[5] < 1e4):
                continue
            if m[10] <= 0.0 or m[14] >= 0.0:   # _33 > 0, _43 < 0 for LH perspective
                continue
            hits.append((base + start, m))
    return hits


def report(p, hits):
    print(f"{'address':>10}  {'_11':>12} {'_22':>12}  {'_22/_11':>8}  {'_33':>10} {'_43':>10}   near/far")
    for addr, m in hits:
        _11, _22, _33, _43 = m[0], m[5], m[10], m[14]
        ratio = _22 / _11 if _11 else 0
        # invert _33 = f/(f-n), _43 = -nf/(f-n)  ->  n = -_43/_33, f = _43/(1-_33)
        near = -_43 / _33 if _33 else 0
        far = _43 / (1.0 - _33) if _33 != 1.0 else 0
        print(f"0x{addr:08X}  {_11:12.6f} {_22:12.6f}  {ratio:8.4f}  {_33:10.6f} {_43:10.4f}   "
              f"{near:.3f}/{far:.1f}")


def scan_frustum(p):
    """Yield (addr, 6 floats) for every NiFrustum {l, r, t, b, near, far}.

    Gamebryo stores the frustum on the camera as six consecutive floats. The world
    cameras use a symmetric frustum, so l == -r and b == -t, with near/far straight
    from CameraNearPlane/CameraFarPlane. That is a 6-float fingerprint.
    """
    hits = []
    for base, size, prot in p.regions(writable_only=True):
        if size > 256 * 1024 * 1024:
            continue
        data = p.read(base, size)
        n = len(data)
        for i in range(0, n - 24, 4):
            l, r, t, b, near, far = struct.unpack_from("<6f", data, i)
            if not (0.0 < r < 10.0 and 0.0 < t < 10.0):
                continue
            if l != -r or b != -t:
                continue
            if not (0.0 < near < far < 100000.0):
                continue
            hits.append((base + i, (l, r, t, b, near, far)))
    return hits


if __name__ == "__main__":
    p = k2mem.K2()
    print(f"pid={p.pid} base=0x{p.base:X}")
    if "--frustum" in sys.argv:
        hits = scan_frustum(p)
        print(f"{len(hits)} symmetric frustums")
        print(f"{'address':>10}  {'right':>11} {'top':>11}  {'r/t':>8}  near/far")
        for addr, f in hits:
            print(f"0x{addr:08X}  {f[1]:11.7f} {f[2]:11.7f}  {f[1]/f[2]:8.4f}  {f[4]:.2f}/{f[5]:.1f}")
    elif "--watch" in sys.argv:
        secs = int(sys.argv[sys.argv.index("--watch") + 1])
        for i in range(secs):
            hits = scan(p)
            print(f"\n--- t+{i}s: {len(hits)} projection matrices ---")
            report(p, hits)
            time.sleep(1)
    else:
        hits = scan(p)
        print(f"{len(hits)} projection matrices")
        report(p, hits)
