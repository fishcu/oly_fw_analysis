#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Pinned evidence for the missing SD selector and reviewed indirect starts.

Raw reference searches are candidate searches, not whole-program reachability
proofs. Exported windows document instruction-aligned dataflow reviewed here.
Offline only; no patched images or camera commands.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from penf_disasm import DEFAULT_IMAGE, DEFAULT_OBJDUMP, refs, window
from penf_landmarks import BASE, MAIN_SHA256


WINDOWS = {
    'task_start_wrapper': (0x600697ff, 0x60069864),
    'task_stop_mailbox_producer': (0x60069864, 0x600698cf),
    'cpu1_mailbox_setter': (0x60070718, 0x6007072e),
    'cpu2_mailbox_setter': (0x60070b88, 0x60070b9e),
    'queued_start_producer': (0x6006c349, 0x6006c379),
    'queued_start_consumer': (0x6006c548, 0x6006c556),
    'hls_callback_creation': (0x606b8e15, 0x606b8e48),
    'hls_eyefi_creation': (0x606ba2be, 0x606ba2f3),
    'hls_event_creation': (0x606bb998, 0x606bb9d9),
    'timer_creation_1': (0x60950157, 0x609501c1),
    'timer_creation_2': (0x60950231, 0x6095029b),
    'lowtask_record_creator': (0x606c4f59, 0x606c5059),
    'lowtask_start': (0x606c51d9, 0x606c524d),
    'thread_existing_id_constructor': (0x60950599, 0x609505b1),
    'thread_existing_id_factory': (0x60950973, 0x609509a3),
    'network_indexed_create_1': (0x60a846c4, 0x60a8470d),
    'network_indexed_create_2': (0x60a85e35, 0x60a85e82),
    'cpu1_pool_activation': (0x610199df, 0x61019a3c),
    'sd_client_and_mount_wrappers': (0x60b1cbb5, 0x60b1ce80),
    'sd_service_preparation': (0x60b1d012, 0x60b1d0e1),
    'sd_service_reply': (0x60b1d508, 0x60b1d527),
    'sd_no_file_fallback': (0x601c8e6e, 0x601c8eb2),
    'monitor_entry_and_update_request': (0x6007e361, 0x6007e43b),
    'monitor_change_state': (0x6007ea1d, 0x6007ea6e),
    'monitor_reads_temperature': (0x6007ec88, 0x6007ed26),
    'monitor_start_site': (0x601a7d67, 0x601a7d75),
    'resource_common_read_branch': (0x602b90dd, 0x602b91b5),
    'resource_storage_read': (0x602b92bb, 0x602b930b),
    'resource_read_inhibit_setter': (0x602b95d4, 0x602b95dd),
    'maintenance_card_availability': (0x606bc646, 0x606bc67d),
    'maintenance_lens_file_check': (0x602ef51b, 0x602ef599),
    'maintenance_strobe_file_check': (0x602ef290, 0x602ef30e),
    'maintenance_card_command': (0x606cc386, 0x606cc41c),
    'filesystem_start_ustart3': (0x601a77e6, 0x601a7815),
    'filesystem_initializer': (0x605989bc, 0x60598a2c),
    'filesystem_auxiliary_task': (0x6059905e, 0x60599093),
    'filesystem_receiver': (0x60598a2c, 0x60598ac0),
    'filesystem_command_router': (0x60598ac0, 0x60598e61),
    'filesystem_request_transport_prefix': (0x6006d4c2, 0x6006d518),
}

# Each row is one of the previously unidentified 15 register/computed calls.
# The explanations apply to reviewed ordinary producers, not arbitrary RAM writes.
STARTS = [
    (0x6006983b, 'same-CPU wrapper', 'Argument from 600697ff; prior constant-ID audit applies.'),
    (0x60069e97, 'dynamic creation', 'Conditional activation of the ID returned by task creation.'),
    (0x6006c54c, 'cross-CPU queued wrapper', 'Request+20; producer 6006c349 writes operation 9 and supplied ID; sole direct caller 6006982c.'),
    (0x600704bd, 'CPU1 mailbox', 'Command 10001, ID 8ff0008c. Reviewed main producer sends 10002 (stop), not 10001.'),
    (0x60070938, 'CPU2 mailbox', 'Command 10001, ID 8ff000b8. Reviewed main producer sends 10002 (stop), not 10001.'),
    (0x606b8e41, 'HLS_CALLBACK', 'Returned ID from creation at 606b8e2e, entry 606b9055.'),
    (0x606ba2ec, 'HLS_EYEFI', 'Returned ID from creation at 606ba2d7, entry 606ba65f.'),
    (0x606bb9c2, 'HLS_EVENT', 'Returned ID from creation at 606bb9b1, entry 606bb9d9.'),
    (0x606c5221, 'OlyLowTask record', 'Record+4; reviewed creator 606c4f59 stores newly allocated ID at 606c5022. All mutable-record producers not proved.'),
    (0x609501ba, 'BF_Timer constructor 1', 'Returned ID from creation at 60950172, object+8.'),
    (0x60950294, 'BF_Timer constructor 2', 'Returned ID from creation at 6095024c, object+8.'),
    (0x60950714, 'ITRON thread object', 'Object+4. Ordinary constructor creates a thread, but 60950599 can wrap a supplied existing ID; factory 60950973 remains a generic route.'),
    (0x60a83d9f, 'network indexed task', '6191e0bc+758*index+2; initializer 60a846c4 creates descriptor 60d47ee4, entry 60a83b29.'),
    (0x60a85bad, 'network worker pair', '6191f318+68*index, index<2; initializer 60a85e35 creates descriptor 60d47f4c, entry 60a85954.'),
    (0x61019a20, 'CPU1 worker pool', '101d + (record-6163057c)/20. Record comes from pool head 616306a8. No arbitrary-ID argument on this route.'),
]


def digest(b):
    return hashlib.sha256(b).hexdigest()


def transfer_candidates(data, base, targets):
    found = []
    for m in re.finditer(rb'[\xc0-\xcd\xdc\xdd]|\xfa\xff|\xfc\xff', data):
        p=m.start(); op=data[p]
        if op == 0xcb:
            continue
        if op <= 0xca:
            width, skip, kind = 1, 1, 'branch8'
        elif op in (0xcc, 0xcd):
            width, skip, kind = 2, 1, 'jmp16' if op == 0xcc else 'call16'
        elif op in (0xdc, 0xdd):
            width, skip, kind = 4, 1, 'jmp32' if op == 0xdc else 'call32'
        else:
            width, skip, kind = (2 if op == 0xfa else 4), 2, 'calls'
        if p+skip+width > len(data):
            continue
        target=(base+p+int.from_bytes(data[p+skip:p+skip+width], 'little', signed=True))&0xffffffff
        if target in targets:
            found.append(dict(site=hex(base+p), target=hex(target), encoding=kind))
    return found


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args=ap.parse_args(); args.out.mkdir(parents=True, exist_ok=False)
    b=DEFAULT_IMAGE.read_bytes()
    assert digest(b)==MAIN_SHA256
    old=Path('analysis/historical_patch_3100/stock-3100-main.bin').read_bytes()
    assert digest(old)=='3d5963c6d9385aafc99ff51892ec706bef1c4783a84f586179271a64b8401bfd'
    exports={}
    for name,(lo,hi) in WINDOWS.items():
        asm=window(b,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi)
        lines=[s for s in asm.splitlines() if re.match(r'^[0-9a-f]{8}:',s)]
        last=lines[-1].split('\t')
        assert int(last[0][:-1],16)+len(last[1].split())==hi, (name,last)
        (args.out/(name+'.asm')).write_text(asm)
        exports[name]=dict(start=hex(lo), end_exclusive=hex(hi),
            sha256=digest(b[lo-BASE:hi-BASE]), identical_3100=b[lo-BASE:hi-BASE]==old[lo-BASE:hi-BASE])
    def words(a,n=1):
        return struct.unpack_from('<'+'I'*n,b,a-BASE)
    def references(a):
        p,c=refs(b,a)
        return dict(pointer_candidates=list(map(hex,p)), call_candidates=list(map(hex,c)))
    # Tie the reviewed mailbox producers to their actual command, not their name.
    assert refs(b,0x60070718)==([],[0x60069876])
    assert refs(b,0x60070b88)==([],[0x60069895])
    assert b[0x6006986f-BASE:0x60069875-BASE]==b'\xfc\xcc\x02\x00\x01\x00'
    assert b[0x6006988e-BASE:0x60069894-BASE]==b'\xfc\xcc\x02\x00\x01\x00'
    assert refs(b,0x6006c349)==([],[0x6006982c])
    assert words(0x6003999c,7)[3]==0x6007e361
    assert words(0x6012a544,2)==(0x6007ec88,0x6007ea1d)
    assert refs(b,0xa1c5889c)==([0x602b9169,0x602b95d6],[])
    assert refs(b,0x602b95d4)==([],[0x60b1d098])
    assert words(0x60982368,2)==(0x606f8835,0x606f813d)
    assert words(0x60d47ee4,6)[2]==0x60a83b29
    assert words(0x60d47f4c,6)[2]==0x60a85954
    assert struct.unpack_from('<H',b,0x600412a0-BASE)[0]==0x101d
    assert refs(b,0x605989bc)==([],[0x601a77f3])
    assert words(0x600396c4+17*28,7)[3]==0x60598a2c
    assert words(0x600396c4+18*28,7)[3]==0x60599151
    assert [struct.unpack_from('<H',b,a-BASE)[0] for a in
            (0x600410de,0x600410e0,0x600410e2,0x60041194)]==[34,35,36,125]
    _,calls=refs(b,0x600307dd)
    assert all(a in calls for a,_,_ in STARTS)
    targets={0x60032654,0x600307dd,0x60031c77,0x60036b69,0x600697ff,
             0x60b1cbb5,0xa0b1cbb5}
    transfers=transfer_candidates(b,BASE,targets)
    assert not any(t['encoding'] not in ('call16','call32') for t in transfers)
    assert not any(int(t['target'],16) in (0x60b1cbb5,0xa0b1cbb5) for t in transfers)
    prior=json.loads(Path('analysis/update_entry_final/audit.json').read_text())
    assert prior['main_sha256']==MAIN_SHA256
    report=dict(main_sha256=MAIN_SHA256, stock3100_sha256=digest(old),
        selector_identified=False, hardware_accessed=False, windows=exports,
        computed_starts=[dict(site=hex(a),category=c,reviewed_provenance=t) for a,c,t in STARTS],
        transfer_candidates=transfers,
        references={hex(a):references(a) for a in
            (0x60b1cbb5,0x60040d8e,0x6003a128,0x6006c349,0x60070718,
             0x60070b88,0xa1c5889c,0x61c5889c,0x602b95d4,0x6007e388,
             0x605989bc,0x60041194)},
        filesystem=dict(request_queue=34, reply_queue=36, firmware_reply_queue=35,
            task=17, entry='60598a2c', initializer='605989bc',
            ordinary_initializer_call='601a77f3 in USTART3',
            ordinary_task_start='601a7801, task ID 17',
            auxiliary_task_started_by_initializer=18,
            unmount_command=18,mount_command=97,
            boundary='Native wrappers and receiver dispatcher matched separately; actual FAT/media services and readiness before SD entry remain unexecuted.'),
        preparation=dict(resource_read_inhibit='602b95d4 stores 1 at a1c5889c; reviewed read consumer bypasses RES_MODE_COMMON storage read and returns a null data pointer.',
            task26='6007e361 periodic monitoring loop; callback reads CCD and other temperatures. Updater asks for state 0 via 6007ea1d and wakes it, without joining its shutdown.',
            no_global_COLOR_exclusion_proved=True),
        card_maintenance=dict(vtable='60982340',update_offset=40,availability_offset=44,
            availability='606bc646 -> 602ef51b (L???????BIN), then on failure 602ef290 (F???????BIN)',
            command='606cc386 stages command 254 with four image IDs and flag 1; not a discovered body startup selector.'),
        limitations=['Exact-pointer and relative-encoding searches do not cover arbitrary computed control/data flow.',
            'Generic ITRON existing-thread factory, arbitrary mutable state, unknown relocations and earlier code remain outside an exhaustive proof.',
            'Post-entry SD native probes assume the sections, filesystem and firmware-service task are already ready.',
            'Main-resident compiled SD client may be unused by the physical procedure; no equivalence to earlier BOOT implementation is established.'],
        source_sha256={str(p):digest(p.read_bytes()) for p in
            (Path(__file__),DEFAULT_OBJDUMP,Path('tools/penf_disasm.py'),
             Path('analysis/update_entry_final/audit.json'))})
    (args.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(windows=len(exports), computed_start_sites=len(STARTS),
        windows_identical_3100=sum(x['identical_3100'] for x in exports.values()),
        selector_identified=False),indent=2))


if __name__=='__main__':
    main()
