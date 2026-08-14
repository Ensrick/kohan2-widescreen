#!/usr/bin/env python3
"""Static analysis of k2.exe to locate the perspective-projection construction.

No external deps beyond capstone. Parses the PE by hand (32-bit), finds occurrences
of the projection-related float constants, and disassembles .text around every
instruction that references those constants via absolute [imm32] addressing.

Usage:
    py -3 analyze.py "C:\\...\\k2.exe"
"""
import struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files (x86)\Steam\steamapps\common\Kohan II\k2.exe"

def f32(x): return struct.unpack("<I", struct.pack("<f", x))[0]

# Projection-relevant constants -> label
CONSTS = {
    f32(15.0):        "FOV 15.0",
    f32(7.5):         "FOV/2 7.5",
    f32(7.5957537):   "cot(7.5)=xScale",
    f32(0.13165249):  "tan(7.5)",
    f32(4.0/3.0):     "aspect 1.3333",
    f32(3.0/4.0):     "0.75",
    f32(0.017453292): "deg2rad",
    f32(57.29578):    "rad2deg",
    f32(0.008726646): "deg2rad/2",
    f32(30.0):        "30.0",
    f32(45.0):        "45.0",
    f32(90.0):        "90.0",
}

def main():
    data = open(EXE, "rb").read()
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[e_lfanew:e_lfanew+4] == b"PE\0\0", "not a PE"
    coff = e_lfanew + 4
    machine, nsec = struct.unpack_from("<HH", data, coff)
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    assert magic == 0x10b, f"not PE32 (magic {magic:#x})"
    image_base = struct.unpack_from("<I", data, opt + 28)[0]
    sec_tbl = opt + struct.unpack_from("<H", data, coff + 16)[0]  # opt header size
    secs = []
    for i in range(nsec):
        off = sec_tbl + i*40
        name = data[off:off+8].rstrip(b"\0").decode("latin1")
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, off+8)
        secs.append((name, va, vsize, raw, rawsize))
    print(f"image_base={image_base:#x}  sections:")
    for n,va,vs,raw,rs in secs:
        print(f"  {n:8} VA {image_base+va:#010x} size {vs:#x} raw {raw:#x}")

    def va_to_off(va):
        r = va - image_base
        for n,sva,vs,raw,rs in secs:
            if sva <= r < sva+max(vs,rs):
                return raw + (r - sva)
        return None
    def off_to_va(off):
        for n,sva,vs,raw,rs in secs:
            if raw <= off < raw+rs:
                return image_base + sva + (off - raw)
        return None

    # 1) find constant occurrences (in initialized sections)
    const_vas = {}   # va -> label
    for n,sva,vs,raw,rs in secs:
        if n not in (".rdata", ".data", ".text"): continue
        blob = data[raw:raw+rs]
        for i in range(0, len(blob)-4):
            v = struct.unpack_from("<I", blob, i)[0]
            if v in CONSTS:
                va = image_base + sva + i
                const_vas[va] = CONSTS[v]
    print("\n== constant occurrences ==")
    for va,lbl in sorted(const_vas.items()):
        print(f"  {va:#010x}  {lbl}")

    # 2) byte-search .text for the little-endian VA of each constant occurrence;
    #    any instruction referencing it absolutely embeds those 4 bytes verbatim.
    text = next(s for s in secs if s[0] == ".text")
    tname, tva, tvs, traw, trs = text
    code = data[traw:traw+trs]
    code_base_va = image_base + tva
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True

    def disasm_containing(ref_va):
        """Find the instruction whose bytes include ref_va's 4-byte LE pattern by
        trying backward start offsets until decode lands the ref inside one insn."""
        pat = struct.pack("<I", ref_va)
        results = []
        idx = 0
        while True:
            j = code.find(pat, idx)
            if j < 0: break
            idx = j + 1
            hit_va = code_base_va + j
            best = None
            for back in range(1, 16):
                start = hit_va - back
                soff = va_to_off(start)
                if soff is None: continue
                for ins in md.disasm(data[soff:soff+16], start):
                    if ins.address <= hit_va < ins.address + ins.size and ins.address + ins.size >= hit_va + 4:
                        best = (start, ins)
                        break
                if best: break
            results.append((hit_va, best))
        return results

    print("\n== code refs (byte-search on constant VA) ==")
    for cva, lbl in sorted(const_vas.items()):
        refs = disasm_containing(cva)
        if not refs: continue
        print(f"\n# {lbl} @ {cva:#010x}: {len(refs)} ref(s)")
        for hit_va, best in refs:
            if not best:
                print(f"    ref bytes @ {hit_va:#010x} (no clean decode)")
                continue
            start, ins = best
            print(f"    >> {ins.address:#010x}: {ins.mnemonic} {ins.op_str}")
            # context: disasm ~10 insns before and after this instruction
            ctx_start = ins.address - 40
            soff = va_to_off(ctx_start)
            if soff is None: continue
            for c in md.disasm(data[soff:soff+96], ctx_start):
                mark = "  ->" if c.address == ins.address else "    "
                print(f"    {mark} {c.address:#010x}: {c.mnemonic:7} {c.op_str}")

if __name__ == "__main__":
    main()
