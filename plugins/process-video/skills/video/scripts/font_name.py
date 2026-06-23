#!/usr/bin/env python3
"""Print a TTF/OTF's internal name records (nameID 1/2/4, platform 3).

The nameID=1 value is the family name to use as `Fontname` in an ASS Style line
(libass resolves fonts by this internal name, not the filename — e.g.
`Jost-Light.ttf` is internally `Jost* Light`).

Usage: python3 font_name.py <font.ttf>
"""
import struct, sys

if len(sys.argv) != 2:
    sys.exit("usage: font_name.py <font.ttf>")

data = open(sys.argv[1], "rb").read()
num_tables = struct.unpack(">H", data[4:6])[0]
tables = {}
for i in range(num_tables):
    rec = data[12 + i * 16:28 + i * 16]
    tables[rec[:4].decode("ascii", "replace")] = struct.unpack(">II", rec[8:16])

if "name" not in tables:
    sys.exit("error: no 'name' table found")
off, ln = tables["name"]
nd = data[off:off + ln]
count, str_off = struct.unpack(">HH", nd[2:6])
labels = {1: "family (nameID=1)", 2: "subfamily (nameID=2)", 4: "full (nameID=4)"}
for i in range(count):
    pid, eid, lid, nid, slen, soff = struct.unpack(">HHHHHH", nd[6 + i * 12:18 + i * 12])
    if nid in (1, 2, 4) and pid == 3:
        try:
            print(f"{labels[nid]}: {nd[str_off + soff:str_off + soff + slen].decode('utf-16-be')}")
        except Exception:
            pass
