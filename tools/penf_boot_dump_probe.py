#!/usr/bin/env python3
"""Offline PEN-F diagnostic dump qualification; never connects to a camera.

Runs stock instructions with synthetic RAM/controller responses. Stops before
erase/program operations. Negative results are findings, not expected safety.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from penf_diagnostic_lifetime_probe import parser_state
from penf_emulator import ENGINE, Region, firmware
from penf_probe import CALLER, LOGS, ProbeState

READ = 0x600219B5
PHYSICAL_READ = 0x60021C4F
REPAIR = 0x600217A6
ERASE = 0x60022029
PROGRAM = 0x60021E3E
LOCK, UNLOCK = 0x600226D0, 0x600226F9
WAIT, STATUS = 0x600220F5, 0x600220AD
BITMAP, CURSOR, POOL = 0x61C556B4, 0x61C554C8, 0x6122A540
RING, SOCKET = 0x19000000, 0x19010000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def hit(state, hooks, limit=200000):
    result = state.run(hooks, limit=limit)
    require(result['status'] == 'breakpoint', f"Unexpected stop: {result}")
    return state.regs['pc']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def allocation_case(cpu, full):
    args = ('flash', 'p', 'dump', '40000000')
    blob = b''
    pointers = []
    for arg in args:
        pointers.append(0x19000100 + len(blob))
        blob += arg.encode() + b'\0'
    state = ProbeState(0x601A6F6C, 0xF0, 20, bytes(16), dict(a0=0x19000000, d0=4))
    state.ram('arguments', 0x19000000, struct.pack('<4I', *pointers), aliases=False)
    state.ram('strings', 0x19000100, blob, aliases=False)
    state.ram('command_buffer_pointers', 0x6117119C, bytes(8))
    bits = b'\xff' * 16 if full else bytes(16)
    state.ram('allocation_bits', BITMAP, bits)
    state.ram('allocation_cursor', CURSOR, struct.pack('<I', 0xFFFFFFFF))
    state.regions.append(Region('cpu', 0x8050, struct.pack('<I', cpu), 'r'))
    parser_state(state)
    services = {0x60022EE7, 0x60086C0B, 0x60086C54, 0x60070BC0, 0x60070CB1,
                0x60023A62}  # Last: exhaustion diagnostic only, statically reviewed.
    hooks = services | LOGS | {READ, LOCK, UNLOCK, ERASE, PROGRAM}
    calls = []
    for _ in range(25):
        pc = hit(state, hooks)
        calls.append(hex(pc))
        if pc == READ:
            break
        require(pc not in {LOCK, UNLOCK, ERASE, PROGRAM}, 'Unexpected service')
        if pc in LOGS:
            state.diagnostic()
        else:
            state.return_from_model(0)
    else:
        raise ValueError('No read request')
    expected = (0 if cpu == 0 else POOL + (63 if cpu == 1 else 95) * 0x4040) if full else POOL + (0, 64, 96)[cpu] * 0x4040
    require(state.regs['d0'] == expected, 'Unexpected allocator result')
    require(state.regs['d1'] == 0x40000000 and state.regs['a0'] == 2048, 'Wrong read request')
    if full:
        require(state.read(BITMAP, 16) == bits, 'Full bitmap changed')
    return dict(cpu=cpu, pool_full=full, read_destination=hex(expected),
                allocator_diagnostic_reached=hex(0x60023A62) in calls,
                flash_lock_reached=False, stopped_before_read=True,
                bitmap_after=state.read(BITMAP, 16).hex(), calls=calls, steps=state.steps)


def controller_state(state, correction):
    for address in (0x98800128, 0x98D011C0, 0x98D01800, 0x98D01804):
        state.regions.append(Region(f'controller_{address:x}', address, bytes(4), 'rw', True))
    state.regions.append(Region('correction_nibble_scenario', 0x98D01194,
                                struct.pack('<I', correction), 'r'))


def read_case(physical=False, correction=0, wait_result=0, status_results=(0,), destination=POOL):
    entry, frame = (PHYSICAL_READ, 28) if physical else (READ, 44)
    state = ProbeState(entry, 0xF0, frame, bytes(16),
                       dict(d0=destination, d1=0x40000000, a0=2048))
    state.ram('identity_block_zero', 0x61171FC0, struct.pack('<I', 0))
    controller_state(state, correction)
    hooks = LOGS | {CALLER + 7, WAIT, STATUS, REPAIR, ERASE, PROGRAM, LOCK, UNLOCK,
                   0x60021A2F, 0x60021CA0}
    status_index, starts, waits, dma = 0, 0, 0, []
    for _ in range(50):
        pc = hit(state, hooks, limit=1000)
        if pc in {CALLER + 7, REPAIR}:
            break
        require(pc not in {ERASE, PROGRAM, LOCK, UNLOCK}, 'Unexpected service')
        if pc in LOGS:
            state.diagnostic()
        elif pc in {0x60021A2F, 0x60021CA0}:
            dma.append(hex(state.regs['a3'] if physical else state.regs['d0']))
            step = state.run(hooks - {pc}, limit=1)
            require(step['completed'] == 1, 'DMA operand step failed')
        elif pc == WAIT:
            starts += 1
            state.return_from_model(wait_result)
        else:
            require(status_index < len(status_results), 'Read retried beyond supplied scenario')
            state.return_from_model(status_results[status_index])
            status_index += 1
            waits += 1
    else:
        raise ValueError('Read did not stop')
    repair = state.regs['pc'] == REPAIR
    require(repair == (not physical and correction > 13), 'Wrong repair selection')
    require(repair or state.regs['sp'] == 0x18018000, 'Stack damaged')
    expected_dma = 0xFFFFFFFF if destination == 0 else destination - 0x60000000
    require(dma == [hex(expected_dma)] * starts, 'Wrong DMA address')
    return dict(entry=hex(entry), correction_nibble=correction, modeled_completion=wait_result,
                modeled_status_results=list(status_results), destination=hex(destination),
                dma_addresses=dma, request_count=starts, status_poll_calls=waits,
                repair_reached=repair, stopped_at=hex(state.regs['pc']),
                returned_status=None if repair else state.regs['d0'], steps=state.steps,
                diagnostics=[e['message'] for e in state.events if 'message' in e])


def repair_case():
    state = ProbeState(REPAIR, 0xF0, 36, bytes(16), dict(d0=0))
    state.ram('block_zero', 0x61171FC0, struct.pack('<II', 0, 0))
    state.ram('first_replacement_slot', 0x61173EC0, struct.pack('<II', 992, 0xFFFFFFFF))
    pc = hit(state, {PHYSICAL_READ, ERASE, PROGRAM})
    require(pc == PHYSICAL_READ, 'Repair did not start with block copy')
    require((state.regs['d0'], state.regs['d1'], state.regs['a0']) ==
            (0x61F22C00, 0x40000000, 131072), 'Wrong block copy')
    state.return_from_model(0)  # No DMA or actual block read.
    pc = hit(state, {ERASE, PROGRAM})
    require(pc == ERASE, 'Did not reach erase')
    require((state.regs['d0'], state.regs['d1']) == (0x47C00000, 131072), 'Wrong erase target')
    require(state.read(0x61171FC0, 4) == struct.pack('<I', 992), 'Mapping unchanged')
    return dict(stopped_before_erase=True, erase_destination=hex(state.regs['d0']),
                erase_bytes=state.regs['d1'], block_zero_mapping_after=992,
                modeled_calls=[hex(PHYSICAL_READ)], steps=state.steps)


def locked_read_case(lower_result):
    state = ProbeState(0x600224C2, 0xF0, 32, bytes(16),
                       dict(a0=0x40000000, a1=POOL, d1=2048, d0=0))
    state.ram('runtime_state', 0x8FF00078, struct.pack('<I', 7), aliases=False)
    state.ram('flash_debug_disabled', 0x61171198, bytes(4))
    state.ram('saturated_read_log', 0xA1C280C0, struct.pack('<I', 100))
    services = {0x60069606, 0x600696F9, 0x60022EE7, READ}
    calls = []
    semaphore_ids = []
    for _ in range(12):
        pc = hit(state, services | {CALLER+7, ERASE, PROGRAM}, limit=1000)
        if pc == CALLER+7:
            break
        require(pc not in {ERASE, PROGRAM}, 'Unexpected write')
        calls.append(hex(pc))
        if pc in {0x60069606, 0x600696F9}:
            semaphore_ids.append(state.regs['d0'])
        state.return_from_model(lower_result if pc == READ else 0)
    else:
        raise ValueError('Locked read did not return')
    require(calls == [hex(x) for x in (0x60069606, 0x60022EE7, READ, 0x60022EE7, 0x600696F9)],
            'Wrong lock/read/unlock order')
    require(len(set(semaphore_ids)) == 1, 'Semaphore mismatch')
    require(state.regs['d0'] == 0 and state.regs['sp'] == 0x18018000, 'Unexpected wrapper result')
    return dict(lower_result=lower_result, returned_status=state.regs['d0'],
                semaphore_id=semaphore_ids[0], calls=calls, steps=state.steps)


def tx_state(fill=0, start=0):
    state = ProbeState(0x600429D1, 0, 0, bytes(16), dict(d0=0))
    state.ram('wifi_enabled', 0xA1C8AD54, struct.pack('<I', 1))
    state.ram('wifi_tx_pointer', 0xA1C8AE30, struct.pack('<IH', RING, start))
    state.ram('wifi_tx_buffer', RING, bytes(8192), aliases=False)
    state.ram('socket', SOCKET, struct.pack('<I', 7), aliases=False)
    # Entry is a task (owns its prologue), not a CALL with a preset frame.
    state.regs = dict(pc=0x60AAA554, sp=0x18018000, psw=0, d0=SOCKET)
    state.write(0x18010000, bytes([fill]) * 65536)
    hit(state, {0x6003172B})  # Idle: establishes the task's local consumer index.
    state.return_from_model(0)
    return state


def tx_case(text, start=0, failure=False, fill=0, full_ring=False):
    state = tx_state(fill, start)
    # The native producer is separately tested below. Inject equivalent bytes
    # here so TX can be isolated without resetting its live register state.
    for i, byte in enumerate(text):
        state.write(RING + ((start + i) & 8191), bytes([byte]))
    state.write(0xA1C8AE34, struct.pack('<H', (start + len(text)) & 8191))
    sends = []
    for _ in range(len(text) + 10):
        pc = hit(state, {0x6003172B, 0x60A82CB0}, limit=20000)
        if pc == 0x6003172B:
            break
        require(state.regs['d0'] == 7 and state.regs['a1'] == 0, 'Wrong socket request')
        data = state.read(state.regs['a0'], state.regs['d1'])
        accepted = 0 if failure else len(data)
        sends.append((data, accepted))
        state.return_from_model(0xFFFFFFFF if failure else accepted)
    else:
        raise ValueError('TX did not idle')
    submitted = b''.join(data for data, _ in sends)
    accepted = b''.join(data[:count] for data, count in sends)
    # The UART route already changes LF to CRLF. TX adds a second CR.
    expected = text.replace(b'\n', b'\r\n')
    if full_ring:
        require(len(text) == 8192 and not submitted, 'Full ring was not mistaken for empty')
        return dict(input_bytes=8192, output_bytes=0, producer_caught_consumer=True,
                    lost_bytes=8192, steps=state.steps)
    require(submitted == expected,
            f'TX bytes differ: actual {len(submitted)} {submitted[:120]!r}, expected {len(expected)} {expected[:120]!r}')
    require((accepted != expected) == failure, 'Unexpected send-failure behavior')
    return dict(input_bytes=len(text), start_index=start, stack_fill=fill,
                send_failure_scenario=failure, sends=len(sends), sent_lengths=[len(x[0]) for x in sends],
                output_bytes=len(submitted), lost_bytes=len(submitted)-len(accepted),
                retransmitted=False, steps=state.steps)


def producer_case(start, enabled):
    state = ProbeState(0x600429D1, 0, 0, bytes(16), dict(d0=0x41))
    state.ram('wifi_enabled', 0xA1C8AD54, struct.pack('<I', int(enabled)))
    state.ram('wifi_tx_pointer', 0xA1C8AE30, struct.pack('<IH', RING, start))
    state.ram('wifi_tx_buffer', RING, b'\x5a' * 8192, aliases=False)
    hit(state, {CALLER+7})
    index = int.from_bytes(state.read(0xA1C8AE34, 2), 'little')
    require(index == ((start + 1) & 8191 if enabled else start), 'Wrong ring index')
    require(state.read(RING+start, 1) == (b'A' if enabled else b'Z'), 'Wrong ring byte')
    return dict(start_index=start, enabled=enabled, end_index=index, steps=state.steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    require(not args.out.exists(), 'Choose a new output path')
    allocations = [allocation_case(cpu, full) for cpu in range(3) for full in (False, True)]
    print('Allocation and command-prefix cases passed', flush=True)
    reads = [read_case(correction=n) for n in (0, 13, 14, 15)]
    reads += [read_case(physical=True, correction=15), read_case(wait_result=2),
              read_case(status_results=(2, 0)), read_case(destination=0)]
    repair = repair_case()
    locked_reads = [locked_read_case(value) for value in (0,2)]
    print('Read, retry and repair-branch cases passed', flush=True)
    producers = [producer_case(start, enabled) for start in (0,8191) for enabled in (False,True)]
    text = b''.join(f'{0x40000000+i:08X} : '.encode() + b'0100 0302 0504 0706 0908 0B0A 0D0C 0F0E\r\n'
                    for i in range(0,2048,16))
    transmissions = [tx_case(text, start=8180, fill=0xA5), tx_case(text[:104], fill=0)]
    transmissions += [tx_case(b'0123456789abcdef\r\n', failure=True),
                      tx_case(b'A' * 8192, full_ring=True)]
    report = dict(main_sha256=digest(firmware()), source_sha256=digest(Path(__file__).read_bytes()),
                  engine_sha256=digest(ENGINE.read_bytes()), allocations=allocations, reads=reads,
                  repair=repair, locked_reads=locked_reads, producers=producers, transmissions=transmissions,
                  limits=[
        'Offline synthetic scenarios; no camera, actual boot bytes or installable firmware.',
        'Only listed controller registers exist; completion and status polling are modeled.',
        'The correction nibble is a scenario, not a measured error count or documented register definition.',
        'No DMA executes. Repair stops before erase; the preceding block read is modeled.',
        'Allocator critical-section services and failure reporter are modeled; no live contention.',
        'Wi-Fi TX is isolated with modeled socket sends and delay; no network or concurrent producer.',
        'Send error is an injected boundary outcome, not a measured network occurrence.',
    ])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS: {len(allocations)+len(reads)+1+len(locked_reads)+len(producers)+len(transmissions)} cases; {args.out}')


if __name__ == '__main__':
    main()
