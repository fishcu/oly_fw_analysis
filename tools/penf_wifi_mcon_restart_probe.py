#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline mcon write -> Mode envelope -> parameter rebuild contracts.

This is deliberately NOT a complete shutdown/restart simulation. Save stops
before programming; the harness explicitly copies the prepared envelope to
RAM backing for a separate native reload. It then calls the native parameter
builders. Real Wi-Fi exit and startup's choice of settings source are open.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import penf_profile_context_probe as c
from penf_landmarks import MAIN_SHA256
from penf_wifi_mcon_probe import compact, set_query, snapshot

BACKING, OBJECT, SIZE = 0x61ef2c00, 0xa1c281a8, 0x20000


def observe(f, s, key):
    return dict(**snapshot(f, s, key),
                active=struct.unpack('<i', s.read(c.ACTIVE+key*4, 4))[0],
                effective=c.current_record(f, s, 919))


def scenario(f, profile, value):
    s = c.state(f)
    c.selected(s, profile)
    key = 931 + (profile-1)*12
    c.put(s, key, 0)
    c.put(s, 919, 0)
    initial = s.read(c.WORKING, SIZE)
    s.ram('explicit_Mode_backing_RAM', BACKING, initial)
    active, banks = s.read(c.ACTIVE, c.STRIDE), s.read(c.BANKS, 9*c.STRIDE)
    before = observe(f, s, key)
    write = set_query(s, f'{key:04X}', f'{value & 0xffffffff:08X}')
    after_write = observe(f, s, key)
    assert after_write['current_record'] == value
    assert after_write['live'] == after_write['effective'] == 0
    assert s.read(c.ACTIVE, c.STRIDE) == active
    assert s.read(c.BANKS, 9*c.STRIDE) == banks

    save = c.invoke(s, 0x600733d8, 0xf0, 24, dict(a0=OBJECT),
                    stops=(0x600720e1,))
    c.at(s, save, 0x600720e1)
    assert (s.regs['d0'], s.regs['d1'], s.regs['a0'], s.regs['a1']) == (
        SIZE, 0, c.WORKING, BACKING+0x40000000)
    envelope = s.read(c.WORKING, SIZE)
    assert sum(struct.unpack('<65536H', envelope)) & 65535 == 0
    assert s.read(BACKING, SIZE) == initial
    # Separate loader experiment: do NOT resume/model the programming call.
    s.write(BACKING, envelope)
    s.write(c.WORKING, bytes([0xa5])*SIZE)
    reload = c.invoke(s, 0x6007333e, 0xb0, 20, dict(a0=OBJECT))
    c.returned(s, reload)
    assert reload['result'] == 0
    assert s.read(c.WORKING, SIZE) == envelope
    after_reload = observe(f, s, key)
    assert after_reload == after_write

    pack = c.invoke(s, 0x602c414a, 0xf0, 168,
                    dict(d0=0, d1=53+profile, a0=c.OUTPUT))
    c.returned(s, pack)
    current_parameters = list(c.words(s, c.OUTPUT+80, 12))
    assert current_parameters[0] == value

    # Contrast the current-record builder with the staged transaction route.
    # Its first snapshot call copies LIVE for these IDs, still zero here;
    # the second transfers that snapshot into the staged transaction buffer.
    # Startup reaching either route is NOT established by this probe.
    staged = []
    for entry, mask, frame in ((0x602f0a2c, 0xf0, 20), (0x602f0b12, 0, 4)):
        r = c.invoke(s, entry, mask, frame)
        c.returned(s, r)
        staged.append(compact(r))
    refreshed = c.invoke(s, 0x602c50be, 0x80, 160,
                         dict(d0=1, d1=53+profile))
    c.returned(s, refreshed)
    r = c.invoke(s, 0x602f0786, 0, 0, dict(d0=919))
    c.returned(s, r)
    assert r['result'] == 0, r
    return dict(profile=profile, setting=key, value=value, before=before,
                after_mcon=after_write, after_native_reload=after_reload,
                native_mcon=write, save_preparation=compact(save),
                native_loader=compact(reload), native_current_builder=compact(pack),
                current_parameters=current_parameters, staged_snapshot=staged,
                staged_refresh=compact(refreshed), staged_effective_sector0=r['result'],
                full_envelope_restored=True,
                live_and_active_and_saved_banks_not_synchronized_by_loader=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    f = c.Fixture()
    assert c.sha(f.image) == MAIN_SHA256
    report = dict(main_sha256=c.sha(f.image), checkpoint_sha256=c.CHECKPOINT_SHA,
        scope='Separate native mcon, save-preparation, RAM-reload and rebuild contracts; no physical camera or complete reboot',
        cases=[scenario(f, profile, value) for profile, value in ((1, 5), (2, -5), (3, 4))])
    sources = [Path(__file__), Path('tools/penf_wifi_mcon_probe.py'),
               Path('tools/penf_profile_context_probe.py'),
               Path('tools/penf_profile_lifecycle_probe.py')]
    report['source_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report['all_assertions_passed'] = True
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(f'Three save/reload/rebuild contracts passed; saved {args.out}')


if __name__ == '__main__':
    main()
