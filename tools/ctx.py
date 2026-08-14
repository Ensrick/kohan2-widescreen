#!/usr/bin/env python3
"""Disassemble a window of k2.exe around a VA, or hunt float immediates in .text.

Operates on a decrypted memory dump (flat loaded image, file offset == RVA).

    py -3 ctx.py dump.bin 0x00509f3f            # disasm around a VA
    py -3 ctx.py dump.bin 0x00509f3f -n 60      # 60 instructions
    py -3 ctx.py dump.bin --imm 15.0            # every .text site embedding 15.0f
    py -3 ctx.py dump.bin --func 0x00509e00     # disasm until ret
"""
import struct
import sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

BASE = 0x400000


def load(path):
    return open(path, "rb").read()


def sections(img):
    e = struct.unpack_from("<I", img, 0x3C)[0]
    coff = e + 4
    nsec = struct.unpack_from("<H", img, coff + 2)[0]
    sec_tbl = coff + 20 + struct.unpack_from("<H", img, coff + 16)[0]
    out = []
    for i in range(nsec):
        o = sec_tbl + i * 40
        name = img[o:o + 8].rstrip(b"\0").decode("latin1")
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", img, o + 8)
        out.append((name, va, vsize))
    return out


def disasm(img, va, n=40, back=0):
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    start = va - back
    rva = start - BASE
    blob = img[rva:rva + 16 * n + 32]
    return list(md.disasm(blob, start))[:n]


def show(img, va, n=40, back=0, mark=None):
    # Starting mid-instruction makes capstone bail on the first byte, so try
    # successively smaller back-offsets until the stream actually reaches va.
    best = []
    for b in range(back, -1, -1):
        out = disasm(img, va, n, b)
        if any(i.address == va for i in out) and len(out) > len(best):
            best = out
            break
    if not best:
        best = disasm(img, va, n, 0)
    for ins in best:
        m = " ->" if mark is not None and ins.address == mark else "   "
        raw = ins.bytes.hex()
        print(f"{m} {ins.address:#010x}  {raw:<20} {ins.mnemonic:9} {ins.op_str}")


def main():
    img = load(sys.argv[1])
    args = sys.argv[2:]

    if "--imm" in args:
        val = float(args[args.index("--imm") + 1])
        pat = struct.pack("<f", val)
        text = next(s for s in sections(img) if s[0] == ".text")
        _, tva, tvs = text
        blob = img[tva:tva + tvs]
        idx = 0
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        print(f"sites embedding {val}f ({pat.hex()}) in .text:")
        while True:
            j = blob.find(pat, idx)
            if j < 0:
                break
            idx = j + 1
            hva = BASE + tva + j
            # walk back to find the instruction that contains these bytes
            found = None
            for back in range(1, 12):
                for ins in md.disasm(img[hva - BASE - back:hva - BASE - back + 16], hva - back):
                    if ins.address <= hva and ins.address + ins.size >= hva + 4:
                        found = ins
                    break
                if found:
                    break
            if found:
                print(f"  {found.address:#010x}  {found.bytes.hex():<20} {found.mnemonic:9} {found.op_str}")
            else:
                print(f"  {hva:#010x}  (data / no clean decode)")
        return

    if "--func" in args:
        va = int(args[args.index("--func") + 1], 0)
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        rva = va - BASE
        count = 0
        for ins in md.disasm(img[rva:rva + 0x3000], va):
            print(f"   {ins.address:#010x}  {ins.bytes.hex():<20} {ins.mnemonic:9} {ins.op_str}")
            count += 1
            if ins.mnemonic == "ret" or count > 400:
                break
        return

    va = int(args[0], 0)
    n = int(args[args.index("-n") + 1]) if "-n" in args else 40
    back = int(args[args.index("-b") + 1], 0) if "-b" in args else 48
    show(img, va, n, back, mark=va)


if __name__ == "__main__":
    main()
