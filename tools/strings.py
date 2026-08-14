#!/usr/bin/env python3
"""Extract ASCII strings (with VAs) from a decrypted k2.exe image dump.

    py -3 strings.py dump.bin                 # every string >= 5 chars
    py -3 strings.py dump.bin -g Console      # only those matching a regex
    py -3 strings.py dump.bin -g "^-" -n 3    # short strings starting with '-'
"""
import re
import struct
import sys

BASE = 0x400000


def main():
    img = open(sys.argv[1], "rb").read()
    args = sys.argv[2:]
    minlen = int(args[args.index("-n") + 1]) if "-n" in args else 5
    pat = args[args.index("-g") + 1] if "-g" in args else None
    rx = re.compile(pat, re.I) if pat else None

    e = struct.unpack_from("<I", img, 0x3C)[0]
    coff = e + 4
    nsec = struct.unpack_from("<H", img, coff + 2)[0]
    tbl = coff + 20 + struct.unpack_from("<H", img, coff + 16)[0]
    ranges = []
    for i in range(nsec):
        o = tbl + i * 40
        name = img[o:o + 8].rstrip(b"\0").decode("latin1")
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", img, o + 8)
        if name in (".rdata", ".data", ".text"):
            ranges.append((name, va, min(vsize, len(img) - va)))

    # The engine keeps every var / console-command name as UTF-16, so scan both.
    wide = "-a" not in args
    arx = re.compile(rb"[\x20-\x7e]{%d,}" % minlen)
    wrx = re.compile(rb"(?:[\x20-\x7e]\x00){%d,}" % minlen)
    for name, va, size in ranges:
        blob = img[va:va + size]
        for m in arx.finditer(blob):
            s = m.group().decode("latin1")
            if rx and not rx.search(s):
                continue
            print(f"{BASE + va + m.start():#010x} [{name:6}] A  {s}")
        if not wide:
            continue
        for m in wrx.finditer(blob):
            s = m.group().decode("utf-16-le")
            if rx and not rx.search(s):
                continue
            print(f"{BASE + va + m.start():#010x} [{name:6}] W  {s}")


if __name__ == "__main__":
    main()
