#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Prepare an IDA 4.9/MN103 import and optional Linux/Wine batch export."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def make_script(spec, directory):
    base = int(spec['base'], 16)
    size = spec['bytes']
    quote = json.dumps
    windows = '\n'.join(f'  export_window(f, {int(a,16):#x}, {int(b,16):#x});' for a,b in spec['windows'])
    target = int(spec['xref_target'], 16)
    return f'''#include <idc.idc>
static export_window(f, ea, end)
{{
  auto size, i;
  fprintf(f, "WINDOW %08X %08X\\n", ea, end);
  while (ea < end) {{
    size = MakeCode(ea);
    fprintf(f, "%08X %d ", ea, size);
    for (i = 0; i < size; i = i + 1) fprintf(f, "%02X", Byte(ea + i));
    fprintf(f, " %s\\n", GetDisasm(ea));
    if (size <= 0) break;
    ea = ea + size;
  }}
}}
static main()
{{
  auto f, input, ref;
  Batch(1);
  f = fopen({quote(directory+'/listing.txt')}, "w");
  SegDelete(FirstSeg(), SEGDEL_PERM | SEGDEL_SILENT);
  SegCreate({base:#x}, {base+size:#x}, 0, 1, 0, 0);
  SegRename({base:#x}, "MAIN");
  input = fopen({quote(directory+'/input.bin')}, "rb");
  loadfile(input, 0, {base:#x}, {size});
  fclose(input);
{windows}
  MakeCode({target:#x});
  for (ref = RfirstB({target:#x}); ref != BADADDR; ref = RnextB({target:#x}, ref))
    fprintf(f, "XREF %08X -> %08X\\n", ref, {target:#x});
  fprintf(f, "COMPLETE\\n");
  fclose(f);
  Exit(0);
}}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=HERE/'models/pen-f-3101.json')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--windows-directory', default='Z:/ida-output', help='IDC path as seen by IDA; default matches the Wine wrapper')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--installation', type=Path, help='IDA installation with extracted/app/idag.exe, prefix and optional runtime')
    args = parser.parse_args()
    spec = json.loads(args.model.read_text())
    data = args.image.read_bytes()
    if len(data) != spec['bytes'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
        parser.error('Image does not match the selected model/build')
    if args.run and (args.installation is None or args.windows_directory != 'Z:/ida-output'):
        parser.error('--run requires --installation and the default virtual Windows directory')
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'input.bin').write_bytes(data)
    (args.out/'export.idc').write_text(make_script(spec, args.windows_directory.rstrip('/')))
    (args.out/'model.json').write_text(json.dumps(spec, indent=2)+'\n')
    if args.run:
        subprocess.run([sys.executable, str(HERE/'wine.py'), '--installation', str(args.installation.resolve()), '--out', str(args.out.resolve())], check=True)
        result = args.out/'listing.txt'
        text = result.read_text(encoding='cp1252')
        expected = f"XREF {int(spec['expected_xref_from'],16):08X} -> {int(spec['xref_target'],16):08X}"
        if 'COMPLETE' not in text or expected not in text:
            raise SystemExit('Incomplete export; inspect batch-ida.log and batch-wine.log')
        result.write_text(text, encoding='utf-8')
    print(args.out.resolve())


if __name__ == '__main__':
    main()
