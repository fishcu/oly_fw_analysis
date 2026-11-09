#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native task127 StlRdy1 callback -> StlRdy2 entry, with explicit busy masks.

No camera or firmware writes. The lower worker's status words are supplied
scenarios, not hardware readiness; their producers remain to be connected.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from penf_probe import ProbeState, CALLER
from penf_emulator import ENGINE
from penf_profile_context_probe import invoke, returned, at, resume, native_block
from penf_disasm import BASE, DEFAULT_IMAGE, DEFAULT_OBJDUMP, window, refs
from oly_container import sha256


def setup(fill):
    s = ProbeState(0x60235280, 0, 0, b'x', {})
    s.ram('lower_capture_status_and_callbacks', 0x61865834, bytes([fill])*132)
    initialized = resume(s, (CALLER+7,))
    returned(s, initialized)
    assert s.read(0x61865834, 9) == bytes(9)
    assert s.read(0x61865840, 120) == bytes(120)
    # Reviewed initializer affects the three halfword ring indices only.
    s.ram('capture_history_indices_and_ring', 0x618659f4, bytes([fill])*518)
    history = invoke(s, 0x601c9f7c, 0, 0)
    returned(s, history)
    # Current state12, no pending transition, diagnostics disabled. This
    # contract begins after StlRdy1 entry's preceding operations.
    s.ram('explicit_capture_transition_state', 0x61865818,
          struct.pack('<HHIHHII', 12, 255, 0, 0, 0, 0, 0))
    registration = invoke(s, 0x6024a71b, 0, 4, stops=(0x6024a72f,))
    at(s, registration, 0x6024a72f)
    assert struct.unpack('<3I', s.read(0x61865840, 12)) == (0x6024a94b, 0x04008000, 0)
    return s, dict(callback_initializer=initialized, history_initializer=history,
                   native_registration=registration)


def case(fill, flags1, flags2):
    s, preparation = setup(fill)
    s.write(0x61865834, struct.pack('<2I', flags1, flags2))
    dispatched = invoke(s, 0x60234c0d, 0xe0, 16,
                        stops=(0x6024a95b, CALLER+7))
    blocked = bool(flags1 & 0x04008000)
    if blocked:
        returned(s, dispatched)
        assert s.read(0x61865818, 4) == struct.pack('<HH', 12, 255)
        assert int.from_bytes(s.read(0x61865840, 4), 'little') == 0x6024a94b
        assert s.read(0x618659f6, 2) == bytes(2)
    else:
        at(s, dispatched, 0x6024a95b)
        assert (s.regs['d0'], s.regs['d1']) == (12, 0)
        assert s.read(0x61865818, 4) == struct.pack('<HH', 13, 255)
        assert s.read(0x61865820, 2) == struct.pack('<H', 12)
        # Consumed callback clears its pointer; mask bytes are retained.
        assert struct.unpack('<3I', s.read(0x61865840, 12)) == (0, 0x04008000, 0)
        assert s.read(0x6186584c, 108) == bytes(108)
        assert s.read(0x618659fa, 2) == bytes((64, 13))
        assert s.read(0x618659f6, 2) == b'\x01\0'
    return dict(kind='readiness_masks', fill=hex(fill), flags1=hex(flags1), flags2=hex(flags2), blocked=blocked,
                preparation=preparation, native_dispatch=dispatched,
                limitation='Stops before StlRdy2 body; external status producers not modeled')


def commands(fill, order):
    s, preparation = setup(fill)
    set_flags = invoke(s, 0x602352ab, 0xc0, 28, dict(d0=0x04008000, d1=0))
    returned(s, set_flags)
    events = []
    for i, command in enumerate(order):
        # Native task-loop interior after queue receive: the message is in
        # the actual loop's stack layout, with return/header halfword0.
        dispatched = native_block(s, 0x602348f9, 0x60234951,
            dict(a3=0x60331fa8, d3=0xffff),
            ((24, 0x18018028), (40, 0), (44, command)))
        remaining = int.from_bytes(s.read(0x61865834, 4), 'little')
        assert remaining == (0 if i else (0x8000 if command == 0x12 else 0x04000000))
        transition = resume(s, (0x60234956, 0x6024a95b))
        at(s, transition, 0x60234956 if i == 0 else 0x6024a95b)
        assert s.read(0x61865818, 2) == struct.pack('<H', 12+i)
        if i == 1:
            assert (s.regs['d0'], s.regs['d1']) == (12, 0)
        events.append(dict(command=hex(command), remaining_flags=hex(remaining),
                           table_dispatch=dispatched, transition=transition))
    return dict(kind='delivered_commands_to_capture_state', fill=hex(fill),
                preparation=preparation, native_busy_set=set_flags, commands=events,
                limitation='Queue receive/messages supplied; sender and relation to GUI flags unjoined')


WINDOWS = {
    'StlRdy1-callback-registration': (0x6024a6ec, 0x6024a733),
    'request-state13': (0x6024a94b, 0x6024a95b),
    'pending-state-write': (0x60234bc5, 0x60234bfb),
    'state-dispatch': (0x60234c0d, 0x60234cc5),
    'status-callback-initializer': (0x60235280, 0x602352ab),
    'callback-registration': (0x60235450, 0x602354e4),
    'callback-scan-and-compaction': (0x60235528, 0x602355cc),
    'native-history': (0x601c9f7c, 0x601c9fd4),
    'task-command-table-dispatch': (0x602348ee, 0x6023495e),
    'state12-command-handlers': (0x6024a919, 0x6024a94b),
    'lower-status-set-clear': (0x602352ab, 0x602353d4),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cases = [case(fill, a, b) for fill in (0, 0xa5)
             for a,b in ((0, 0), (0x8000, 0), (0x04000000, 0),
                         (0x04008000, 0), (0, 0x04008000))]
    cases.extend(commands(fill, order) for fill in (0, 0xa5)
                 for order in ((0x12, 0x2b), (0x2b, 0x12)))
    image = DEFAULT_IMAGE.read_bytes()
    disassembly = args.out/'disassembly'
    disassembly.mkdir()
    for name,(lo,hi) in WINDOWS.items():
        (disassembly/(name+'.asm')).write_text(window(image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, lo, hi))
    sources = {Path(__file__), ENGINE}
    sources.update(Path(m.__file__) for m in tuple(sys.modules.values())
                   if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == Path('tools').resolve())
    report = dict(main_sha256=sha256(image), cases=cases, camera_used=False,
                  firmware_modified=False, kernel_models=[],
                  source_sha256={str(p):sha256(p.read_bytes()) for p in sorted(sources)},
                  windows={k:[hex(x) for x in v] for k,v in WINDOWS.items()},
                  lower_flags_distinct_from_GUI_status=True,
                  lower_flag_reference_candidates={hex(a):[hex(x) for x in refs(image,a)[0]]
                                                    for a in (0x61865834,0x61865838)})
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'{len(cases)} native callback/transition cases passed; {args.out}')


if __name__ == '__main__':
    main()
