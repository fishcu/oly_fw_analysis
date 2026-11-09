# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Shared strict harness for isolated PEN-F native function probes.

The caller, stack, result and package addresses are synthetic host fixtures,
not identified camera RAM. This adds no hardware models or flash access.
The main payload is pinned by penf_emulator.firmware(). Unknown instructions
and native memory accesses retain the emulator's stop behavior.
"""
import struct

from penf_boot_emulator import BootState, HOOK_RETURN
from penf_emulator import BASE, Region, firmware

CALLER = 0x18000000
BUFFER = 0x20000000
RESULT = 0x18020000
LOGS = {0x6002304a, 0x600232c4, 0x60023260, 0x6002331e}


class ProbeState(BootState):
    """Native call fixture using the reviewed MN103 call/return convention.

    ``mask`` and ``frame`` describe the target's register-save mask and frame
    size. Callers must select these from the target's actual instructions.
    """

    def __init__(self, target, mask, frame, package, registers):
        caller = b'\xdd' + struct.pack('<i', target - CALLER) + bytes((mask, frame)) + b'\xcb'
        self.regions = [
            Region('main', BASE, firmware(), 'rx'),
            Region('caller', CALLER, caller, 'rx'),
            Region('stack', 0x18010000, bytes(0x10000), 'rw', True),
            Region('result', RESULT, bytes(16), 'rw', True),
            Region('return_trampoline', HOOK_RETURN, b'\xcb' * 8, 'rx'),
            Region('input_package', BUFFER, package, 'rw', True),
        ]
        self.regs = dict(pc=CALLER, sp=0x18018000, psw=0)
        self.regs.update(registers)
        self.events = []
        self.steps = 0
        self.cpu = 0

    def read_c_string(self, address, limit=200):
        """Read a bounded native string; an unmapped byte still stops the probe."""
        if limit <= 0:
            raise ValueError('String limit must be positive')
        value = bytearray()
        for offset in range(limit):
            byte = self.read(address + offset, 1)[0]
            if byte == 0:
                break
            value.append(byte)
        return bytes(value)

    def diagnostic(self):
        address = self.regs['a0']
        message = self.read_c_string(address).decode('ascii', errors='replace')
        self.events.append(dict(
            kind='model', name='diagnostic output suppressed',
            entry=hex(self.regs['pc']), message=message, value=self.regs['d0'],
        ))
        self.return_from_model(0)
