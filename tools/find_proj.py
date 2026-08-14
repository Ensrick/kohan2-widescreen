#!/usr/bin/env python3
"""Locate the perspective-projection construction inside a DECRYPTED k2.exe image.

k2.exe is SteamStub-encrypted on disk, so static analysis has to run against a dump
of the running process (see k2mem.py). This script takes that flat image dump - where
file offset == RVA, because it is the loaded layout - parses the PE section table,
verifies .text actually decrypted, then:

  1. finds every occurrence of the projection-relevant float constants,
  2. byte-searches .text for absolute references to those constants,
  3. disassembles context around each reference with capstone.

Usage:
    py -3 find_proj.py <dump.bin> [--base 0x400000]
"""
import struct
import sys
import math
from collections import Counter
from capstone import Cs, CS_ARCH_X86, CS_MODE_32


def f32bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


CONSTS = {
    f32bits(4.0 / 3.0):     "aspect 4/3 (1.3333334)",
    f32bits(3.0 / 4.0):     "0.75",
    f32bits(15.0):          "15.0 (CameraFOV)",
    f32bits(7.5):           "7.5 (fov/2)",
    f32bits(7.5957537):     "cot(7.5deg) = _11",
    f32bits(10.127671):     "_22 observed",
    f32bits(math.tan(math.radians(7.5))): "tan(7.5deg)",
    f32bits(math.pi / 180.0): "deg2rad",
    f32bits(180.0 / math.pi): "rad2deg",
    f32bits(0.5 * math.pi / 180.0): "deg2rad/2",
    f32bits(1.7777778):     "16/9",
    f32bits(512.0):         "512.0 (CameraFarPlane)",
    f32bits(1.0019569):     "zf/(zf-zn) for 1/512",
}


def entropy(b):
    if not b:
        return 0.0
    c = Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def main():
    path = sys.argv[1]
    base = 0x400000
    if "--base" in sys.argv:
        base = int(sys.argv[sys.argv.index("--base") + 1], 0)
    img = open(path, "rb").read()

    e_lfanew = struct.unpack_from("<I", img, 0x3C)[0]
    assert img[e_lfanew:e_lfanew + 4] == b"PE\0\0", "not a PE"
    coff = e_lfanew + 4
    nsec = struct.unpack_from("<H", img, coff + 2)[0]
    opt = coff + 20
    opt_size = struct.unpack_from("<H", img, coff + 16)[0]
    sec_tbl = opt + opt_size

    secs = []
    for i in range(nsec):
        o = sec_tbl + i * 40
        name = img[o:o + 8].rstrip(b"\0").decode("latin1")
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", img, o + 8)
        secs.append((name, va, vsize, raw, rawsize))

    print(f"image base {base:#x}   dump {len(img):,} bytes")
    print(f"{'section':10} {'VA':>10} {'vsize':>10}   entropy (in-memory)")
    for name, va, vsize, raw, rawsize in secs:
        blob = img[va:va + min(vsize, len(img) - va)]
        print(f"{name:10} {base + va:#010x} {vsize:#10x}   {entropy(blob[:0x80000]):.3f}")

    def section_of(rva):
        for name, va, vsize, raw, rawsize in secs:
            if va <= rva < va + max(vsize, rawsize):
                return name
        return "?"

    # ---- 1. constant occurrences -------------------------------------------------
    const_rvas = {}
    for name, va, vsize, raw, rawsize in secs:
        if name not in (".rdata", ".data", ".text"):
            continue
        end = min(va + vsize, len(img))
        for i in range(va, end - 4):
            v = struct.unpack_from("<I", img, i)[0]
            if v in CONSTS:
                const_rvas[i] = CONSTS[v]

    print(f"\n== constant occurrences ({len(const_rvas)}) ==")
    for rva, lbl in sorted(const_rvas.items()):
        print(f"  {base + rva:#010x}  [{section_of(rva):7}]  {lbl}")

    # ---- 2. absolute code references --------------------------------------------
    text = next(s for s in secs if s[0] == ".text")
    _, tva, tvs, _, _ = text
    code = img[tva:tva + tvs]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True

    def decode_at(va, n=1, back=0):
        rva = va - base
        out = []
        for ins in md.disasm(img[rva - back:rva - back + 16 * n + 16], va - back):
            out.append(ins)
            if len(out) >= n:
                break
        return out

    print("\n== .text references to those constants ==")
    for crva, lbl in sorted(const_rvas.items()):
        if section_of(crva) == ".text":
            continue
        pat = struct.pack("<I", base + crva)
        idx, hits = 0, []
        while True:
            j = code.find(pat, idx)
            if j < 0:
                break
            idx = j + 1
            hits.append(base + tva + j)
        if not hits:
            continue
        print(f"\n# {lbl} @ {base + crva:#010x}  ({len(hits)} ref)")
        for hva in hits:
            # walk back up to 15 bytes to find an instruction that swallows the operand
            shown = False
            for back in range(1, 16):
                ins_list = decode_at(hva, n=1, back=back)
                if not ins_list:
                    continue
                ins = ins_list[0]
                if ins.address <= hva and ins.address + ins.size >= hva + 4:
                    print(f"    {ins.address:#010x}: {ins.mnemonic:8} {ins.op_str}")
                    shown = True
                    break
            if not shown:
                print(f"    (operand bytes at {hva:#010x}, no clean decode)")


if __name__ == "__main__":
    main()
