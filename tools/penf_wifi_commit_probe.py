#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline PEN-F Wi-Fi setting application and mode-restore contracts.

Runs the stock raw CGI setter or the application's public-setter prefix,
then separately invokes the stock mode transition used by Wi-Fi exit.
These are joined state contracts, not a complete Wi-Fi session simulation.
Unknown accesses stop. No radio, scheduler, nonvolatile programming or
hardware-dependent callback is modeled as successful.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import penf_profile_context_probe as c
from penf_landmarks import MAIN_SHA256
from penf_wifi_mcon_probe import compact, set_query, snapshot

NORMAL_WRITE_BOUNDARY = 0x602bb68b  # stored current/LIVE, before dependencies
COMMIT_BOUNDARY = 0x602bd7f9       # transaction committed, before callbacks
MODE_RETURN_BOUNDARY = 0x602bd9dc  # inner transition returned (can be a no-op)


def pending_request(f):
    """The native application getter reads the CGI's pending scalar triple."""
    s = c.state(f)
    s.ram('captured_wifi_debug_flag', 0x61c8a870, f.read(0x61c8a870, 2))
    assert s.read(0x61c8a870, 2) == b'\0\0'
    rows = []
    for key, value in ((9, 16), (904, 85), (943, -5)):
        # Synthetic pending request: the ordinary CGI only exposes its own
        # named property table. ID943 is a possible adapter contract, NOT an
        # advertised COLOR property or proof of arbitrary HTTP reachability.
        s.ram('synthetic_pending_request', 0x61c8a8b4,
              struct.pack('<IIi', key, 0, value))
        r = c.invoke(s, 0x60aa1d7c, 0xb0, 20,
                     dict(a0=c.OUTPUT, a1=c.OUTPUT+2, d0=c.OUTPUT+4))
        c.returned(s, r)
        actual = struct.unpack('<HHi', s.read(c.OUTPUT, 8))
        assert actual == (key, 0, value)
        rows.append(dict(id=key, value=value, native=compact(r),
                         received=list(actual)))
    return rows


def scenario(f, profile, value, writer, source_mode):
    s = c.state(f)
    c.selected(s, profile)
    key = 931 + (profile-1)*12
    # Explicit bank-0 shooting contexts: native mode4=A, mode6=M.
    # Public selector2 below decodes to bank0 / native mode4 / submode0.
    for k in (24, 26, 43):
        c.put(s, k, source_mode)
    c.put(s, key, 0)
    c.put(s, 919, 0)
    banks = s.read(c.BANKS, 9*c.STRIDE)
    before = snapshot(f, s, key)
    if writer == 'raw_mcon':
        write = set_query(s, f'{key:04X}', f'{value & 0xffffffff:08X}')
        expected = 0
    else:
        s.ram('captured_wifi_controller_log_flag', 0x61603c40,
              f.read(0x61603c40, 2))
        assert s.read(0x61603c40, 2) == b'\0\0'
        # Native receiver helper used by set_camprop's application event.
        # This supplies a COLOR ID directly: normal HTTP doesn't expose it.
        # The object is deliberately unmapped: the reviewed prefix does not
        # dereference it when the captured log flag is zero.
        write = c.invoke(s, 0x607ab8fd, 0xa0, 20,
                         dict(d0=key, d1=0, a0=0x210a0000,
                              a1=value & 0xffffffff),
                         stops=(NORMAL_WRITE_BOUNDARY,))
        c.at(s, write, NORMAL_WRITE_BOUNDARY)
        expected = value
    after_write = snapshot(f, s, key)
    assert after_write == dict(current_record=value, live=expected)
    assert s.read(c.BANKS, 9*c.STRIDE) == banks

    # New invocation from this RAM state. We do not pretend the stopped
    # property callbacks or HTTP completion have executed.
    transition = c.invoke(s, 0x602ba0c7, 0xc0, 16, dict(d0=2),
                          stops=(COMMIT_BOUNDARY, MODE_RETURN_BOUNDARY))
    after_transition = snapshot(f, s, key)
    if source_mode == 6:
        c.at(s, transition, COMMIT_BOUNDARY)
        assert after_transition == dict(current_record=expected, live=expected)
        assert c.current_record(f, s, 919) == expected
        assert s.read(0x6189a4b0, 1) == b'\0'
        count = s.regs['d2']
        changed = list(struct.unpack(f'<{count}H', s.read(s.regs['a2'], 2*count)))
    else:
        c.at(s, transition, MODE_RETURN_BOUNDARY)
        assert transition['result'] == 0
        assert after_transition == after_write
        assert c.current_record(f, s, 919) == 0
        changed = []
    assert c.current_record(f, s, 26) == 4
    assert s.read(c.BANKS, 9*c.STRIDE) == banks
    return dict(profile=profile, id=key, value=value, writer=writer,
                transition='M_to_A' if source_mode == 6 else 'A_to_A',
                before=before, after_write=after_write,
                after_transition=after_transition,
                effective_sector0=c.current_record(f, s, 919),
                saved_banks_unchanged=True, changed_ids=changed,
                write=compact(write), mode_transition=compact(transition),
                scope='Separate native prefixes; no complete Wi-Fi exit, callback delivery or physical save')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    f = c.Fixture()
    assert c.sha(f.image) == MAIN_SHA256
    report = dict(main_sha256=MAIN_SHA256, checkpoint_sha256=c.CHECKPOINT_SHA,
                  pending_request=pending_request(f), scenarios=[])
    for profile, value in ((1, 5), (2, -5), (3, 4)):
        for writer in ('raw_mcon', 'public_receiver_prefix'):
            report['scenarios'].append(scenario(f, profile, value, writer, 6))
            print(f'Passed COLOR{profile} {writer}, M -> A', flush=True)
    report['scenarios'].append(scenario(f, 2, 5, 'raw_mcon', 4))
    report['all_assertions_passed'] = True
    sources = [Path(__file__), Path('tools/penf_wifi_mcon_probe.py'),
               Path('tools/penf_profile_context_probe.py'),
               Path('tools/penf_profile_followup_probe.py'),
               Path('tools/penf_profile_lifecycle_probe.py')]
    report['source_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sources}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(f'Seven transition contracts and three pending-request cases passed: {args.out}')


if __name__ == '__main__':
    main()
