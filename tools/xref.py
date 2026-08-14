#!/usr/bin/env python3
"""List .text instructions that reference an absolute address (or embed a float).

    py -3 xref.py dump.bin 0x009c5b20        # who reads this .rdata constant
    py -3 xref.py dump.bin --float 0.75      # find the constant, then its xrefs
"""
import struct
import sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

BASE = 0x400000


def secs(img):
    e = struct.unpack_from("<I", img, 0x3C)[0]
    coff = e + 4
    n = struct.unpack_from("<H", img, coff + 2)[0]
    tbl = coff + 20 + struct.unpack_from("<H", img, coff + 16)[0]
    out = []
    for i in range(n):
        o = tbl + i * 40
        name = img[o:o + 8].rstrip(b"\0").decode("latin1")
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", img, o + 8)
        out.append((name, va, vsize))
    return out


def xrefs(img, target):
    _, tva, tvs = next(s for s in secs(img) if s[0] == ".text")
    code = img[tva:tva + tvs]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    pat = struct.pack("<I", target)
    out, idx = [], 0
    while True:
        j = code.find(pat, idx)
        if j < 0:
            break
        idx = j + 1
        hva = BASE + tva + j
        # An operand can be swallowed by several plausible decodes depending on where
        # you start (e.g. "0d imm32" = or eax, imm32 is really the tail of
        # "d8 0d imm32" = fmul dword ptr [imm32]). Walk back from the longest possible
        # prefix and keep the first decode that ends exactly on the operand - that is
        # the real instruction boundary.
        for back in range(11, 0, -1):
            got = None
            for ins in md.disasm(img[hva - BASE - back:hva - BASE - back + 16], hva - back):
                got = ins
                break
            if got and got.address == hva - back and got.address + got.size == hva + 4:
                out.append(got)
                break
    return out


def main():
    img = open(sys.argv[1], "rb").read()
    args = sys.argv[2:]
    targets = []
    if "--float" in args:
        val = float(args[args.index("--float") + 1])
        pat = struct.pack("<f", val)
        for name, va, vsize in secs(img):
            if name not in (".rdata", ".data"):
                continue
            for i in range(va, min(va + vsize, len(img)) - 4, 4):
                if img[i:i + 4] == pat:
                    targets.append(BASE + i)
        print(f"{val}f lives at: {', '.join(hex(t) for t in targets)}")
    else:
        targets = [int(args[0], 0)]

    for t in targets:
        refs = xrefs(img, t)
        print(f"\n== {len(refs)} xref(s) to {t:#010x} ==")
        for ins in refs:
            print(f"  {ins.address:#010x}  {ins.bytes.hex():<20} {ins.mnemonic:9} {ins.op_str}")


if __name__ == "__main__":
    main()
