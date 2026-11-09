#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: GPL-3.0-or-later
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Apply the small, reproducible strict-mode changes to our pinned GNU tree."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'toolchains/mn103-gnu-src'
REF = SRC / '.penf-pristine'
ORIGINAL_SHA256 = {
    'interp.c': 'f6c34c6c81ff67bda52d6b57d0ea47954587e36908923cd7e4e59a90424cd37b',
    'mn10300.igen': '355754c61879dc24bf6128bbba5a7931355731000e8cb213082b9b9cd4df0129',
}
PATCH_NOTICE = '''SPDX-License-Identifier: GPL-3.0-or-later
Modifications: Copyright 2026 fishku
GNU simulator source context retains its upstream copyrights and notices.
License: LICENSES/GPL-3.0.txt
Source: binutils-gdb 87ffb882e0f4d73401a0746177ffabb8e8bbe4ac

'''


def main():
    REF.mkdir(parents=True, exist_ok=True)
    changes = []
    for name in ('interp.c', 'mn10300.igen'):
        pristine = REF / name
        if not pristine.exists():
            original = (SRC / 'sim/mn10300' / name).read_bytes()
            if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256[name]:
                raise RuntimeError('Fresh pinned GNU sources required to establish pristine input')
            pristine.write_bytes(original)
        original = pristine.read_text()
        assert hashlib.sha256(original.encode()).hexdigest() == ORIGINAL_SHA256[name]
        updated = original
        if name == 'interp.c':
            updated = updated.replace('struct _state State;', '''struct _state State;
/* PEN-F harness: record faults without synthesizing a board exception. */
unsigned penf_fault_kind, penf_fault_map, penf_fault_size;
unsigned penf_fault_address, penf_fault_pc;
''', 1)
            updated = updated.replace('  sim_do_command (sd, "memory region 0,0x100000");',
                                      '  /* PEN-F: no implicit memory regions. */', 1)
            updated = updated.replace('  sim_do_command (sd, "memory region 0x40000000,0x200000");', '', 1)
            start = updated.index('  if ( NULL != board')
            end = updated.index('  /* check for/establish', start)
            updated = updated[:start] + '''  if (board != NULL)
    {
      sim_io_eprintf (sd, "PEN-F harness does not supply a board model.\\n");
      return NULL;
    }

''' + updated[end:]
            marker = '  switch (sig)\n    {'
            assert updated.count(marker) == 1
            updated = updated.replace(marker, '''  penf_fault_kind = 1;
  penf_fault_map = map;
  penf_fault_size = nr_bytes;
  penf_fault_address = addr;
  penf_fault_pc = cia;
  switch (sig)
    {''')
            start = updated.index('  static int in_interrupt = 0;', updated.index('\nprogram_interrupt ('))
            end = updated.index('\n}\n', start)
            updated = updated[:start] + '''  if (!penf_fault_kind)
    {
      penf_fault_kind = 2;
      penf_fault_pc = cia;
    }
  PC = cia;
  sim_engine_halt(sd, cpu, NULL, cia, sim_stopped, sig);''' + updated[end:]
        else:
            assert updated.count('  do_syscall (SD);') == 1
            updated = updated.replace('  do_syscall (SD);',
                                      '  program_interrupt (SD, CPU, cia, SIM_SIGILL); /* No host calls. */')
            start = updated.index('  /* OP_F0FE (); */')
            end = updated.index('\n}', start)
            updated = updated[:start] + '''  PC = cia;
  program_interrupt (SD, CPU, cia, SIM_SIGTRAP); /* Unknown trap service. */''' + updated[end:]
            # Panasonic MN103001G/F01K manual, pp. 3-6, 3-8, 3-9.
            # Dedicated slots are unused by the selected mn10300 machine.
            # N/Z are undefined by that manual; preserve them deterministically.
            updated += '''

// PEN-F candidate MAC context transfers; see research/mn103_extensions/.
8.0xf6+4.0xc,2.DM1,2.DN0:D0:::penf_getchx
"getchx"
*mn10300
{
  PC = cia;
  State.regs[REG_D0 + DN0] = State.regs[15];
  PSW = (PSW & ~(PSW_C | PSW_V)) | (State.regs[17] ? PSW_V : 0);
}

8.0xf6+4.0xd,2.DM1,2.DN0:D0:::penf_getclx
"getclx"
*mn10300
{
  PC = cia;
  State.regs[REG_D0 + DN0] = State.regs[16];
  PSW = (PSW & ~(PSW_C | PSW_V)) | (State.regs[17] ? PSW_V : 0);
}

8.0xf5+4.0x1,2.DM1,2.DN0:D0:::penf_putcx
"putcx"
*mn10300
{
  PC = cia;
  State.regs[15] = State.regs[REG_D0 + DM1];
  State.regs[16] = State.regs[REG_D0 + DN0];
  State.regs[17] = (PSW & PSW_V) != 0;
}
'''
        target = SRC / 'sim/mn10300' / name
        current = target.read_text()
        # Accept our earlier strict patch when adding the documented extension.
        old_updated = updated.split('\n\n// PEN-F candidate MAC context transfers;')[0] if name == 'mn10300.igen' else updated
        if current not in (original, updated, old_updated.rstrip()+'\n', old_updated):
            raise RuntimeError(f'Refusing to overwrite unexpected source changes: {target}')
        if current != updated:
            target.write_text(updated)
        changes.extend(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                          fromfile=f'a/sim/mn10300/{name}', tofile=f'b/sim/mn10300/{name}'))
    (ROOT / 'tools/mn103_strict.patch').write_text(PATCH_NOTICE + ''.join(changes))
    print('Strict-mode patch applied; source diff saved to tools/mn103_strict.patch')


if __name__ == '__main__':
    main()
