#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Connected offline SD transactions after explicit client/service entry.

Native client, service, decoder, validator, flash wrapper and reply consumer.
Filesystem, RTOS transport and low-level storage are explicit host models.
This does not synthesize a power-on selector, run concurrent image processing,
access a camera, or write an update BIN. Unknown accesses stop the experiment.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ROOT, ENGINE, Region, firmware
from penf_probe import ProbeState, LOGS, CALLER, BUFFER, RESULT
from penf_update_probe import synthetic_block
import penf_input_recovery_probe as sd
from penf_recovery_isolation_probe import without_ranges
from penf_repack_preflight import sha, save
from oly_container import decode
from penf_landmarks import COLOR_TABLE_ADDRESS, COLOR_TABLE_SIZE


HOLES = [(0x604f6a2e, 0x604f8461), (COLOR_TABLE_ADDRESS, COLOR_TABLE_ADDRESS+COLOR_TABLE_SIZE),
         (0x6069b2b0, 0x6069b7c0)]


class GuardedState(ProbeState):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.regions = without_ranges(self.regions, HOLES)


def relocated_helpers(s):
    s.regions.append(Region('relocated_helpers', 0x47000800,
        firmware()[0x113c9e0:0x113c9e0+0x1800], 'rx'))


def connected_transaction(scenario, active_monitor=False):
    assert scenario in ('valid', 'bad-checksum', 'late-bad-checksum', 'no-file')
    # 4096-byte main-component fixture, decoded only by the native updater.
    package = bytearray(synthetic_block(0x100, address=0x403a0000, size=4032))
    if scenario == 'bad-checksum':
        package[40] ^= 1
    elif scenario == 'late-bad-checksum':
        later = bytearray(synthetic_block(0x101, address=0x41800000, size=4032))
        later[40] ^= 1
        package.extend(later)
    package = bytes(package)
    original = sd.ProbeState
    sd.ProbeState = GuardedState
    try:
        first, client = sd.sd_client(None if scenario == 'no-file' else package)
    finally:
        sd.ProbeState = original
    request = first['request']
    assert (request is None) == (scenario == 'no-file'), first
    client_events_before_resume = len(client.events)
    operations = []; milestones = []; messages = []; reply = None
    service = None; storage = bytearray(b'\x55' * 131072)
    if request is not None:
        service = GuardedState(0x60b1d012, 0, 4, bytes(16), {})
        # Distinct stack for the two synthetic tasks, with shared client output
        # pointers preserved exactly. Queue delivery copies native bytes.
        shared = next(r for r in client.regions if r.name == 'stack')
        service.regions = [r for r in service.regions if r.name != 'stack']
        service.regions.append(replace(shared, name='client_stack'))
        service.ram('service_stack', 0x19010000, bytes(0x10000), aliases=False)
        service.regs['sp'] = 0x19018000
        service.ram('service_globals', 0x619a5f88, bytes(32))
        service.ram('resource_read_inhibit', 0x61c5889c, bytes(4))
        service.ram('monitor_state', 0x61c38b0c,
                    bytes(56)+bytes((int(active_monitor),))+bytes(7))
        service.ram('package', int(request['buffer'], 16), package)
        service.ram('native_access_mode', 0x61171110, bytes(2))
        service.ram('native_debug_flag', 0x61171198, bytes(4))
        service.ram('diagnostic_log_full', 0x61c280c0, struct.pack('<I', 100))
        service.ram('native_page_scratch', 0x61c9c500, b'\xa5'*2048)
        # Explicit non-RTOS storage branch, as in the earlier flash probe.
        # This is not evidence of scheduler exclusion on the physical camera.
        service.regions.append(Region('storage_context_scenario',
                                     0x8ff003fc, bytes(4), 'r'))
        relocated_helpers(service)
        services = {0x600226d0: 'storage lock', 0x600226f9: 'storage unlock',
                    0x60022ee7: 'fixed counter', 0x6007dc71: 'coherent cache'}
        observe = {0x60b1d527: 'shared validator entered',
                   0x6013024b: 'flash backend entered',
                   0x60130389: 'lower write/readback returned',
                   0x6007129d: 'program wrapper returned',
                   0x60b1d0fa: 'shared validator returned'}
        hooks = LOGS | set(services) | set(observe) | {
            0x6006932d, 0x60069429, 0x6003535d, 0x60069606, 0x600696f9,
            0x60038368, 0x60022402, 0x60021e3e, 0x600224c2,
            0x601c8d7c, 0x601c8eb2, CALLER+7}
        delivered = False
        for _ in range(300):
            result = service.run(hooks, limit=200000)
            pc = service.regs['pc']
            if result['status'] != 'breakpoint':
                raise AssertionError((hex(pc), result))
            if pc in LOGS:
                service.diagnostic(); continue
            if pc in observe:
                milestones.append(dict(name=observe[pc], pc=hex(pc),
                    d0=service.regs['d0'], d1=service.regs['d1']))
                step = service.run(hooks-{pc}, limit=1)
                assert step['status'] == 'instruction_limit'
                continue
            if pc in services:
                service.events.append(dict(kind='model', name=services[pc], pc=hex(pc)))
            elif pc == 0x6006932d:
                assert not delivered, 'Service requested another message before replying'
                dest, size = struct.unpack('<II', service.read(service.regs['a0'], 8))
                assert service.regs['d0'] == 125 and size == 32
                descriptor = bytes.fromhex(request['descriptor_hex'])
                service.write(dest, descriptor)
                messages.append(dict(direction='client to service', queue=125,
                                     payload_hex=descriptor.hex()))
                delivered = True
            elif pc == 0x60069429:
                pointer, size = struct.unpack('<II', service.read(service.regs['a0'], 8))
                assert service.regs['d0'] == 35 and size == 12
                reply = service.read(pointer, size)
                messages.append(dict(direction='service to client', queue=35,
                                     payload_hex=reply.hex()))
                break
            elif pc == 0x6003535d:
                assert service.regs['d0'] == 26
                service.write(service.regs['a0'], struct.pack('<H', 2 if active_monitor else 16))
            elif pc in (0x60069606, 0x600696f9, 0x60038368):
                assert service.regs['d0'] == (26 if pc == 0x60038368 else 21)
            elif pc in (0x601c8d7c, 0x601c8eb2):
                # Validator progress notification; no fake validation result.
                service.events.append(dict(kind='model', name='progress indication',
                    pc=hex(pc), d0=service.regs['d0'], d1=service.regs['d1']))
            elif pc in (0x60022402, 0x60021e3e, 0x600224c2):
                if pc == 0x60021e3e:
                    addr, count = service.regs['d1'], service.regs['a0']
                else:
                    addr, count = service.regs['a0'], service.regs['d1']
                # The native main dispatcher converts the container's
                # 403a0000 destination to the storage API's 803a0000 alias.
                offset = addr-0x803a0000
                assert 0 <= offset and offset+count <= len(storage), (hex(pc), hex(addr), count)
                if pc == 0x60022402:
                    name = 'erase'
                    lo = offset//131072*131072
                    hi = (offset+count+131071)//131072*131072
                    storage[lo:hi] = b'\xff'*(hi-lo)
                elif pc == 0x60021e3e:
                    name = 'program'
                    storage[offset:offset+count] = service.read(service.regs['d0'], count)
                else:
                    name = 'readback'
                    service.write(service.regs['a1'], storage[offset:offset+count])
                operations.append(dict(operation=name, address=hex(addr), bytes=count))
            else:
                raise AssertionError(('Unexpected service boundary', hex(pc)))
            service.return_from_model(0)
        assert reply is not None
        assert struct.unpack_from('<H', reply)[0] == (0 if scenario == 'valid' else 0x3211)
        client_stack = service.read(shared.address, len(shared.data))
        client.write(shared.address, client_stack)
        client.return_from_model(0)  # Original client send now delivered.

    client_hooks = LOGS | {0x6006932d, 0x60022720, 0x601c9016,
        0x60022ee7, 0x601c8d7c, 0x601c8eb2, 0x601c8e6e,
        0x60b1ce80, 0x600697ff, 0x60069927, 0x60069943, 0x6006be0f}
    terminal = None; normal_start = []
    fallback_seen = False
    for _ in range(120):
        result = client.run(client_hooks, limit=100000)
        pc = client.regs['pc']
        assert result['status'] == 'breakpoint', (hex(pc), result)
        if pc in LOGS:
            client.diagnostic(); continue
        if pc in (0x601c8d7c, 0x601c8eb2):
            terminal = dict(pc=hex(pc), d0=client.regs['d0'], d1=client.regs['d1'],
                            kind='success indication' if pc == 0x601c8d7c else 'error indication')
            break
        if pc == 0x601c8e6e:
            assert not fallback_seen
            fallback_seen = True
            step = client.run(client_hooks-{pc}, limit=1)
            assert step['status'] == 'instruction_limit'
            continue
        if pc == 0x6006932d:
            assert reply is not None
            dest, capacity = struct.unpack('<II', client.read(client.regs['a0'], 8))
            assert client.regs['d0'] == 35 and capacity >= len(reply)
            client.write(dest, reply)
        elif pc == 0x60b1ce80:
            # Native client continues checking G/H/W alternatives after E.
            args = client.regs['a0']
            ptr = struct.unpack('<I', client.read(args+8, 4))[0]
            name = client.read(ptr, 11).decode('ascii')
            assert name != 'E122????BIN'
            client.return_from_model(0xe00); continue
        elif pc == 0x600697ff:
            normal_start.append(client.regs['d0'])
        elif pc == 0x60069943:
            terminal = dict(pc=hex(pc), kind='client exit after USTART1 activation')
            break
        client.return_from_model(0)
    assert terminal is not None
    expected_kind = {'valid': 'success indication', 'bad-checksum': 'error indication',
                     'late-bad-checksum': 'error indication',
                     'no-file': 'client exit after USTART1 activation'}[scenario]
    assert terminal['kind'] == expected_kind
    if scenario == 'valid':
        assert [o['operation'] for o in operations] == ['erase', 'program', 'readback']
        assert bytes(storage[:len(package)]) == package[:32]+decode(package[32:-32])+package[-32:]
        assert terminal['d0'] == 3 and terminal['d1'] == 2
    else:
        assert not operations
    assert normal_start == ([47] if scenario == 'no-file' else [])
    return dict(scenario=scenario, active_monitor=active_monitor,
        client_entry='0x60b1cbb5', service_entry='0x60b1d012',
        client_instructions=client.steps, service_instructions=0 if service is None else service.steps,
        file_sha256=sha(package) if request else None,
        first_phase=first, messages=messages, milestones=milestones,
        storage_operations=operations, terminal=terminal, normal_task_starts=normal_start,
        stored_fixture_sha256=sha(storage[:4096]),
        client_resume_events=client.events[client_events_before_resume:],
        service_events=[] if service is None else service.events,
        runtime_inaccessible=[[hex(a),hex(z)] for a,z in HOLES],
        physical_selector_tested=False, actual_scheduler_exclusion_tested=False,
        limit='Explicit post-entry client and already-ready service; modeled filesystem and RTOS transport. '
              'Modeled low-level storage and non-RTOS storage context. Completion indication is the endpoint, not a power cycle.')


def card_availability(present):
    s = GuardedState(0x606bc646, 0xc0, 52, bytes(16), {})
    relocated_helpers(s)
    hooks = LOGS | {CALLER+7, 0x60b1ce80, 0x602e13ea, 0x602e12a6,
                   0x602e143c, 0x602e14b9}
    patterns = []
    for _ in range(40):
        result = s.run(hooks, limit=10000)
        pc = s.regs['pc']
        assert result['status'] == 'breakpoint', result
        if pc == CALLER+7:
            break
        if pc in LOGS:
            s.diagnostic()
        elif pc == 0x60b1ce80:
            p = struct.unpack('<I', s.read(s.regs['a0']+8, 4))[0]
            pattern = s.read(p, 11).decode('ascii')
            patterns.append(pattern)
            s.return_from_model(0 if pattern in present else 0xe00)
        else:
            s.return_from_model(0)  # API tracing/bookkeeping only.
    assert s.regs['pc'] == CALLER+7
    assert s.regs['d0'] == int(bool(set(patterns)&set(present)))
    assert not any(p.startswith('E') for p in patterns)
    return dict(present=list(present), native_searches=patterns, available=s.regs['d0'],
                instructions=s.steps, native_entry='0x606bc646',
                limit='Availability predicate; filesystem and API bookkeeping modeled, no image parsed.')


def filesystem_contract(mount):
    target, frame = (0x60b1ce10, 104) if mount else (0x60b1ce50, 120)
    s = GuardedState(target, 0x80, frame, bytes(16), dict(d0=0, d1=1800))
    hooks = LOGS | {0x605a165b, 0x6006d4c2, CALLER+7}
    readiness = 0
    for _ in range(20):
        r = s.run(hooks, limit=10000)
        pc = s.regs['pc']
        assert r['status'] == 'breakpoint', r
        if pc in LOGS:
            s.diagnostic()
        elif pc == 0x605a165b:
            readiness += 1
            s.return_from_model(0)  # Media preparation; no physical I/O.
        elif pc == 0x6006d4c2:
            break
        else:
            raise AssertionError('Wrapper returned before submitting request')
    assert s.regs['d0'] == 34 and s.regs['a1'] == 36
    command = s.regs['d1']
    assert command == (97 if mount else 18)
    params = s.read(s.regs['a0'], 48)
    # Transport is modeled. The receiving router runs with the native command
    # and unchanged parameter bytes; task ID 95 is an explicit entry assumption.
    receiver = GuardedState(0x60598ac0, 0xb0, 16, params, dict(a0=RESULT))
    receiver.write(RESULT, struct.pack('<4I', 36, 95, command, BUFFER))
    lower = 0x60590d07 if mount else 0x605a165b
    r = receiver.run({lower, CALLER+7}, limit=10000)
    assert r['status'] == 'breakpoint' and receiver.regs['pc'] == lower, r
    assert receiver.regs['a0'] == BUFFER
    offset = 4 if mount else 36
    translated = struct.unpack('<H', receiver.read(BUFFER+offset, 2))[0]
    assert translated == (0x2000 if mount else 2), hex(translated)
    return dict(operation='mount' if mount else 'unmount', wrapper=hex(target),
        request_queue=34, reply_queue=36, command=command,
        readiness_calls_modeled=readiness, consumer_task=17,
        consumer_entry='0x60598a2c', router='0x60598ac0',
        lower_entry=hex(lower), translated_operation=hex(translated),
        wrapper_instructions=s.steps, router_instructions=receiver.steps,
        limit='Native wrappers and FILECLBK dispatch only; transport and media preparation modeled; stops before lower filesystem/media operation.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=False)
    results = []
    for scenario in ('valid', 'bad-checksum', 'late-bad-checksum', 'no-file'):
        for active in ((False, True) if scenario != 'no-file' else (False,)):
            report = connected_transaction(scenario, active)
            name = scenario+'-monitor'+str(int(active))
            save(args.out, name, report)
            results.append(dict(file=name+'.json', terminal=report['terminal'],
                client_instructions=report['client_instructions'],
                service_instructions=report['service_instructions']))
            print(name, report['terminal'], flush=True)
    availability = [card_availability(present) for present in
                    ((), ('E122????BIN',), ('L???????BIN',), ('F???????BIN',))]
    save(args.out, 'card-availability', availability)
    filesystem = [filesystem_contract(mount) for mount in (False, True)]
    save(args.out, 'filesystem-contract', filesystem)
    sources = [Path(__file__).resolve(), ROOT/'tools/penf_landmarks.py',ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py',
        ROOT/'tools/penf_input_recovery_probe.py', ROOT/'tools/penf_boot_emulator.py',
        ROOT/'tools/penf_emulator.py', ROOT/'tools/penf_recovery_isolation_probe.py',
        ROOT/'tools/oly_container.py', ENGINE]
    save(args.out, 'summary', dict(all_assertions_passed=True, hardware_accessed=False,
        update_image_created=False, main_sha256=sha(firmware()), results=results,
        availability_cases=len(availability), filesystem_contract_cases=len(filesystem),
        source_sha256={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sources}))


if __name__ == '__main__':
    main()
