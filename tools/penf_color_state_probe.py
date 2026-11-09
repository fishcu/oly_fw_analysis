#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded native construction and running-state provenance for COLOR edits.

Offline research; unknown calls and memory accesses remain strict boundaries.
No camera access or firmware output.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from penf_color_context_probe import ContextContracts, initialize
from penf_color_request_probe import (
    ALLOCATORS, EMPTY_WAIT, Fixture, MAIN_THREAD, STILL,
    FACTORY, ROOT, WRAPPED_SEQUENCE, SEQUENCE, REQUEST,
    at, returned, u32, word,
    sequence_cache, edit_prefix, continue_case,
    CHECKPOINT_SHA, DEFAULT_IMAGE, DEFAULT_OBJDUMP, ENGINE, sha, window,
)
from penf_disasm import BASE
from penf_probe import CALLER

MODE, CATEGORY, SELECT_EVENT = 0x24005000, 0x24006000, 0x24007000
CATEGORY_CONTROL = 0x24008000

ALLOCATIONS = {
    (0x609520a6, 0x60951818): None,  # Native bounded string capacity.
    (0x609520a6, 0x609322c6): 80,    # Twenty-pointer native event collection.
    (0x60950a6e, 0x609285b2): 28,    # Native self-generated init-success event.
    (0x60950a6e, 0x60932f31): 16,    # Native reply-manager ownership.
    (0x60950a78, 0x606b4dbb): 48,    # Twelve native shared-resource slots.
    (0x60950a6e, 0x606b4df1): 8,     # Shared-resource mutex wrapper.
    (0x60950a6e, 0x606f1eb0): 36,    # Native reception singleton.
    (0x60950a6e, 0x6094b9e4): 28,    # Category init-success event.
    (0x60950a6e, 0x60936116): 32,    # Root mode-change completion.
    (0x60950a6e, 0x6094af9f): 32,    # Mode category-change completion.
    **{(0x609520a6, ret): 80 for ret in (
        0x609336dc, 0x60809784, 0x608097aa, 0x608097d5,
        0x608097fb, 0x60809829, 0x6080989f,
        0x606bc1bd,
        0x60934f19, 0x60934f3b, 0x60942b2c, 0x60942b4e,
        0x60941338, 0x60941356, 0x6094b397,
        0x60930404, 0x609305f2, 0x6092e69e, 0x60933327,
    )},
}


class StateContracts(ContextContracts):
    media_status = 0

    @property
    def hooks(self):
        hooks=super().hooks | {0x606b49c5, 0x606b4bac}
        if self.media_status is not None:
            hooks.add(0x6059a278)
        return hooks

    def model(self):
        s = self.s
        pc, ret, a, d = (s.regs[k] for k in ('pc', 'mdr', 'a0', 'd0'))
        if pc in ALLOCATORS and (pc, ret) in ALLOCATIONS:
            expected = ALLOCATIONS[(pc, ret)]
            if expected is None:
                assert d == word(s, s.regs['a2']+4) and 0 < d <= 512, (
                    d, hex(s.regs['a2']), word(s, s.regs['a2']+4))
                assert d % word(s, 0x616061f0) == 0
            else:
                assert d == expected
            ptr = self.next_address
            self.next_address += (d+0xfff) & ~0xfff
            s.ram('state_allocation_'+hex(ptr), ptr, bytes([self.fill])*d, aliases=False)
            self.heap[ptr] = dict(bytes=d, caller=ret)
            s.regs['a0'] = ptr
            self.events.append(dict(entry=hex(pc), caller_return=hex(ret),
                                    operation='allocation', bytes=d, address=hex(ptr)))
            s.return_from_model(0)
        elif pc == 0x6059a278:
            assert ret == 0x602f1cbe and 0 <= d <= 7
            self.events.append(dict(entry=hex(pc), caller_return=hex(ret),
                operation='supplied media-status scenario', media=d, status=self.media_status))
            s.return_from_model(self.media_status)
        elif pc in (0x606b4d81, 0x606b4d91) and ret in (0x606bc054, 0x606bc079):
            enter = pc == 0x606b4d81
            assert ret == (0x606bc054 if enter else 0x606bc079)
            assert a == word(s, word(s, 0x6160094c)+8)
            assert word(s, a) == 0x609524c0
            if enter:
                assert a not in self.held
                self.held.add(a)
            else:
                assert a in self.held
                self.held.remove(a)
            self.events.append(dict(entry=hex(pc), caller_return=hex(ret),
                operation='reception singleton lock' if enter else 'reception singleton unlock',
                address=hex(a)))
            s.return_from_model(0)
        elif pc == 0x609520b0 and ret == 0x609305de:
            allocation = self.heap.pop(a)
            assert allocation == dict(bytes=80, caller=0x60930404)
            s.regions = [region for region in s.regions if region.address != a]
            self.events.append(dict(entry=hex(pc), caller_return=hex(ret),
                operation='free subscription vector', address=hex(a), allocation=allocation))
            s.return_from_model(0)
        elif pc == 0x60950a5a and (ret, self.heap[a]['caller']) in (
            (0x6094f029, 0x609285b2), (0x6094f029, 0x6094b9e4),
            (0x60936159, 0x60936116), (0x6094afe4, 0x6094af9f),
        ):
            allocation = self.heap.pop(a)
            assert allocation['bytes'] == (28 if ret == 0x6094f029 else 32)
            s.regions = [region for region in s.regions if region.address != a]
            self.events.append(dict(entry=hex(pc), caller_return=hex(ret),
                operation='free', address=hex(a), allocation=allocation))
            s.return_from_model(0)
        elif pc in (0x606b49c5, 0x606b4bac):
            self.events.append(dict(entry=hex(pc), caller_return=hex(ret),
                                    operation='diagnostic output omitted', level=d))
            s.return_from_model(0)
        elif pc == 0x60031be2 and ret == 0x6059c8eb:
            s.write(a, struct.pack('<H', self.foreground_task))
            self.events.append(dict(entry=hex(pc), caller_return=hex(ret),
                operation='explicit active-task query', task=self.foreground_task))
            s.return_from_model(0)
        else:
            try:
                super().model()
            except (KeyError, AssertionError) as exc:
                raise AssertionError(dict(entry=hex(pc), caller_return=hex(ret),
                    a0=hex(a), d0=d, reason=str(exc),
                    stack=[hex(x) for x in struct.unpack('<64I', s.read(s.regs['sp'],256))],
                    recent_events=self.events[-4:])) from exc


def construction(f, fill, profile=1, sector=1):
    e, c, preparation = initialize(f, profile, sector, fill)
    c = StateContracts(c)
    s = e.s
    s.ram('NEW_shooting_component_destination', STILL, bytes([fill])*1940, aliases=False)
    result = c.call(0x60927b64, 0x30, 12, dict(a0=STILL, a1=0), stop=0x607be7df)
    at(s, result, 0x607be7df)
    return e, c, dict(preparation=preparation, constructor=result)


def initialization(f, fill, profile=1, sector=1, media_status=0):
    e, c, prefix = construction(f, fill, profile, sector)
    c.media_status = media_status
    preparation = prefix['preparation']
    s = e.s
    base = prefix['constructor']
    # Separate constructor-tail contract: the intervening peripheral
    # relations are not replayed. Preserve that gap explicitly.
    reset = c.call(0x60927b6e,0x30,12,dict(a0=STILL,a3=0))
    returned(s,reset)
    assert word(s,STILL)==0x60a4769c and word(s,STILL+100)==MAIN_THREAD
    reply_owner = c.call(0x60932f17,0x30,12,dict(a0=STILL))
    returned(s,reply_owner)
    assert word(s,STILL+260)==1
    # Absence of both sequence children is an explicit transition scenario.
    u32(s, STILL+928, 0)
    u32(s, STILL+932, 0)
    s.ram('captured_event_ancestor_id', 0x618ea180, f.read(0x618ea180, 2))
    producer = c.call(0x6092858d, 0, 4, dict(a0=STILL))
    returned(s, producer)
    assert word(s, STILL+256) == word(s, STILL+556) == 10
    assert word(s, STILL+148) == 0 and word(s, STILL+980) == 0
    c.foreground_task = 64
    stop=0x60803ced if media_status and media_status & 0x3080 else EMPTY_WAIT
    run = c.call(0x606b486e, 0x20, 8, stop=stop)
    if media_status is None:
        assert run['status']=='memory_fault' and run['pc']=='0x60589fe7', run
        assert run['fault']['address']==0xa1c87ad4 and run['fault']['access']=='read'
    else:
        at(s, run, stop)
    if stop==EMPTY_WAIT and media_status is not None:
        assert word(s, STILL+256) == word(s, STILL+980) == 14
    else:
        assert word(s,STILL+256)==10 and word(s,STILL+980)==0
    assert word(s, STILL+252) == 4 and word(s, STILL+556) == 0
    assert word(s, STILL+148) == STILL and word(s, 0x61606058) == STILL
    return e, c, dict(preparation=preparation, base=base, reset=reset,
        producer=producer, transition=run, reply_owner=reply_owner,
        supplied_media_status=media_status,
        final_state={str(off):hex(word(s,STILL+off)) for off in (100,148,252,256,260,264,556,980)})


def selection(e, c):
    s = e.s
    results = {}
    for name, obj, size, entry, mask, frame, stop in (
        ('root', ROOT, 620, 0x60934ed4, 0xf0, 24, None),
        ('mode', MODE, 384, 0x6094a294, 0x30, 16, 0x607c028d),
        ('category', CATEGORY, 456, 0x6094b34d, 0x30, 16, None),
    ):
        s.ram('native_'+name+'_destination', obj, bytes([c.fill])*size, aliases=False)
        kw = {} if stop is None else dict(stop=stop)
        r = c.call(entry, mask, frame, dict(a0=obj, a1=0), **kw)
        returned(s, r) if stop is None else at(s, r, stop)
        assert word(s, obj+148) == 0 and word(s, obj+100) == MAIN_THREAD
        results[name+'_construction'] = r

    # Cached factory-container pointers are explicit warm-factory fixtures.
    # Run their real getters: the interior component offset is native code.
    for slot, offset, obj, getter in (
        (0x61606084,1872,ROOT,0x60934b3d),
        (0x61606174,532,MODE,0x6094a075),
        (0x61606178,508,CATEGORY,0x6094b142),
        (0x61606044,1152,STILL,0x609274a3),
    ):
        u32(s, slot, obj-offset)
        r = c.call(getter, 0x30, 12, dict(a0=MAIN_THREAD))
        returned(s, r)
        assert s.regs['a0'] == obj
        results['warm_factory_'+hex(slot)] = r

    # Populate the actual ID/pointer registries using native append routines.
    for parent, child, register in (
        (ROOT, MODE, 0x60934f90), (MODE, CATEGORY, 0x60942ba9),
        (CATEGORY, STILL, 0x609413b1),
    ):
        r = c.call(register, 0x30, 12, dict(a0=parent, a1=child, d0=1))
        returned(s, r)
        results['register_'+hex(parent)] = r

    for parent, child, field, entry, mask, frame, stop in (
        (ROOT,MODE,296,0x60935e93,0x30,12,0x60935eda),
        (MODE,CATEGORY,296,0x60942dd9,0x30,12,0x60942de6),
        (CATEGORY,STILL,300,0x6094b4af,0x20,8,0x6094161a),
    ):
        r = c.call(entry,mask,frame,dict(a0=parent,d0=1),stop=stop)
        at(s,r,stop)
        assert word(s,parent+field)==child
        results['pending_child_'+hex(parent)] = r

    # Replay the native static initializer's observer-vector tail. The list
    # starts empty: delivery to real registered observers is outside this case.
    s.ram('native_layer_observers',0x618ea19c,bytes([c.fill])*16,aliases=False)
    r=c.call(0x609332fe,0xa0,44)
    returned(s,r)
    results['observer_registry_initialization']=r
    # The category dispatcher consults this controller even with no active
    # subscriptions. Construct it rather than substituting a zero pointer.
    s.ram('native_category_control',CATEGORY_CONTROL,bytes([c.fill])*348,aliases=False)
    r=c.call(0x609367a9,0x30,12,dict(a0=CATEGORY_CONTROL,a1=0))
    returned(s,r)
    results['controller_construction']=r
    for entry, parent, child in (
        (0x60941725,CATEGORY,CATEGORY_CONTROL),
        (0x6093070a,CATEGORY_CONTROL,CATEGORY),
    ):
        r=c.call(entry,0,0,dict(a0=parent,a1=child))
        returned(s,r)
        results['controller_relation_'+hex(entry)]=r
    assert word(s,CATEGORY+328)==CATEGORY_CONTROL
    assert word(s,CATEGORY_CONTROL+176)==0  # Constructed, not started.
    for parent in (ROOT,MODE,CATEGORY):
        r=c.call(0x60932f17,0x30,12,dict(a0=parent))
        returned(s,r)
        results['reply_owner_'+hex(parent)]=r
    # Active parent entries are separate native contracts; the preceding
    # peripheral/switcher handshakes are not silently skipped in one trace.
    for parent, entry in ((ROOT,0x60935980),(MODE,0x6094abd3)):
        r=c.call(entry,0,4,dict(a0=parent))
        returned(s,r)
        assert word(s,parent+252)==4
        results['active_parent_'+hex(parent)]=r
    for parent, entry in ((ROOT,0x609360c6),(MODE,0x6094af52)):
        r=c.call(entry,0,0,dict(a0=parent))
        returned(s,r)
        results['pending_state_'+hex(parent)]=r

    s.ram('injected_selection_event', SELECT_EVENT, bytes([c.fill])*28, aliases=False)
    # Unrelated native event3346 and null-current-event controls must leave
    # selection unchanged. Stop at the actual fallback handler.
    controls=[]
    for parent, entry, mask, frame, fallback in (
        (ROOT,0x609360d3,0xb0,20,0x60935f89),
        (MODE,0x6094af5f,0xb0,24,0x6094adb5),
        (CATEGORY,0x6094bb12,0xa0,12,0x6094b849),
    ):
        for unrelated in (False,True):
            old=word(s,parent+148)
            if unrelated:
                returned(s,c.call(0x607637d5,0,4,dict(a0=SELECT_EVENT)))
            u32(s,parent+104,SELECT_EVENT if unrelated else 0)
            r=c.call(entry,mask,frame,dict(a0=parent),stop=fallback)
            at(s,r,fallback)
            assert word(s,parent+148)==old
            controls.append(dict(parent=hex(parent),event=3346 if unrelated else None,
                                 execution=r,selection_unchanged=True))
    results['nonselection_controls']=controls
    r = c.call(0x607637ad,0,4,dict(a0=SELECT_EVENT))
    returned(s,r)
    results['event3345_constructor'] = r
    for parent, child, entry, mask, frame, state in (
        (CATEGORY,STILL,0x6094bb12,0xa0,12,11),
        (ROOT,MODE,0x609360d3,0xb0,20,13),
        (MODE,CATEGORY,0x6094af5f,0xb0,24,13),
    ):
        # Event delivery is supplied, not a claim that every preceding
        # component-switcher handshake has been replayed.
        u32(s,parent+104,SELECT_EVENT)
        r=c.call(entry,mask,frame,dict(a0=parent))
        returned(s,r)
        assert word(s,parent+148)==child
        u32(s,parent+104,0)
        results['selection3345_'+hex(parent)] = r
        if parent==CATEGORY:
            r=c.call(0x606b486e,0x20,8,stop=EMPTY_WAIT)
            at(s,r,EMPTY_WAIT)
            results['category_success_dispatch']=r
        assert word(s,parent+148)==child
        assert word(s,parent+252)==4 and word(s,parent+256)==state
    results['final_parent_states']={hex(parent):{
        'selected_child':hex(word(s,parent+148)),
        'parent':word(s,parent+252),'state':word(s,parent+256),
    } for parent in (ROOT,MODE,CATEGORY,STILL)}

    s.ram('native_transition_factory',FACTORY,bytes([c.fill])*12,aliases=False)
    r=c.call(0x60934a8d,0x30,16,dict(a0=FACTORY,a1=MAIN_THREAD))
    returned(s,r)
    assert word(s,FACTORY+8)==ROOT
    u32(s,0x61602c58,FACTORY)
    results['factory_constructor'] = r
    r=c.call(0x6093464e,0x20,8,dict(a0=ROOT))
    returned(s,r)
    assert s.regs['a0']==STILL
    results['recursive_selected_leaf'] = r
    return results


def exchange(f, fill, profile=1, sector=1):
    e,c,initial = initialization(f, fill, profile, sector)
    s=e.s
    selected = selection(e,c)
    cache=sequence_cache(e,c)
    u32(s,STILL+928,WRAPPED_SEQUENCE)
    s.ram('no_sequence_event_subscription',WRAPPED_SEQUENCE+176,bytes(4),aliases=False)
    s.ram('current_sequence_cache_pointer',WRAPPED_SEQUENCE+2836,
          struct.pack('<I',SEQUENCE),aliases=False)
    s.ram('dispatcher_stack',0x18110000,bytes([fill])*0x10000,aliases=False)
    # Initialization already consumed its own event. Retain its complete log
    # separately so the existing exchange asserts only its three messages.
    initial['all_initialization_models'] = c.events
    c.events=[]
    c.observations=[]
    c.foreground_task=200+profile
    prefix=edit_prefix(e)
    r=c.run(stop=REQUEST)
    at(s,r,REQUEST)
    details=dict(profile=profile,sector=sector,fill=hex(fill),
        preparation=initial['preparation'],sequence_cache=cache,prefix=prefix,
        request_api_stop=r)
    result=continue_case(e,c,details,timeout=profile==1,pump_entry=(0x606b486e,0x20,8))
    for parent,child,state in ((ROOT,MODE,13),(MODE,CATEGORY,13),
                               (CATEGORY,STILL,11),(STILL,STILL,14)):
        assert (word(s,parent+148),word(s,parent+252),word(s,parent+256))==(child,4,state)
    return dict(kind='native_initialization_selection_and_COLOR_exchange',
        initialization=initial, selection=selected, exchange=result)


WINDOWS = {
    'NEW-constructor-and-tail':(0x60927b64,0x60927b90),
    'NEW-state-initializer':(0x60927bf8,0x60927c18),
    'native-base-construction':(0x6093253b,0x6093258e),
    'native-transition-construction':(0x609345b4,0x6093463a),
    'component-construction':(0x609336a7,0x609336f3),
    'collection-construction':(0x60932297,0x609322cc),
    'string-capacity':(0x609517f5,0x60951824),
    'shooting-constructor-prefix':(0x6080974d,0x608098d1),
    'shooting-constructor-relation-frontier':(0x6080aa74,0x6080aaf4),
    'state21-mount-response':(0x6092831c,0x6092849b),
    'init10-self-event':(0x6092858d,0x609285f2),
    'init-success-exit-and-transition':(0x6092804d,0x6092810a),
    'clear-init-collection-select-self':(0x6080aa2a,0x6080aa3d),
    'active-parent-entry':(0x60928730,0x60928767),
    'active-media-check':(0x60803b3c,0x60803b6b),
    'media-status-translation':(0x602f1c93,0x602f1d77),
    'media-query':(0x6059a278,0x6059a2f1),
    'state14-entry':(0x6092a013,0x6092a028),
    'reply-manager-owner':(0x60932f17,0x60932f55),
    'root-constructor':(0x60934ed4,0x60934f5b),
    'mode-constructor-prefix':(0x6094a294,0x6094a2e7),
    'category-constructor':(0x6094b34d,0x6094b3c4),
    'root-pending-shoot-mode':(0x60935e93,0x60935f05),
    'mode-pending-category':(0x60942dd9,0x60942e19),
    'category-pending-component':(0x6094b4af,0x6094b4cc),
    'root-selection-event':(0x60935bdc,0x60935c1d),
    'root-active-selection':(0x609360c6,0x60936172),
    'root-active-parent':(0x6093597d,0x6093598e),
    'mode-active-parent':(0x6094abd0,0x6094ac0c),
    'mode-selection-event':(0x6094af5f,0x6094b0bd),
    'category-selection-event':(0x6094bb12,0x6094bb72),
    'selection-event-constructors':(0x607637ad,0x607637ff),
    'warm-shooting-getter':(0x609274a3,0x609274e6),
    'component-factory-caller':(0x6094b401,0x6094b4aa),
    'transition-factory':(0x60934a8d,0x60934aaf),
    'recursive-leaf':(0x60934649,0x60934672),
    'category-success-and-active':(0x6094b825,0x6094b8c3),
    'category-self-event':(0x6094b9c1,0x6094ba1b),
    'category-active-parent':(0x6094bc8f,0x6094bcd0),
    'category-active-state':(0x6094bf4f,0x6094bf64),
    'controller-construction':(0x609367a9,0x60936867),
    'controller-base-construction':(0x609303cb,0x60930431),
    'controller-vector-replacement':(0x609305c5,0x60930602),
    'controller-default-reception':(0x6093069a,0x6093070a),
    'controller-owner':(0x6093070a,0x6093071b),
    'category-controller-relation':(0x60941725,0x6094172f),
    'observer-registry-initializer':(0x609332fe,0x60933339),
    'reception-getter':(0x606bc03c,0x606bc07c),
    'reception-factory':(0x606f1e95,0x606f1ecb),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    f=Fixture()
    cases=[]
    for fill in (0,0xa5):
        for profile,sector in ((1,1),(2,6),(3,12)):
            cases.append(exchange(f,fill,profile,sector))
            print(f'COLOR{profile}/sector{sector}, fill {fill:#x}: native init, selection, reply passed',flush=True)
        for media_status in (0x80,0x1000,0x2000,None):
            e,c,r=initialization(f,fill,media_status=media_status)
            cases.append(dict(kind='media_status_boundary',fill=hex(fill),result=r))
            print(f'Media status {media_status}, fill {fill:#x}: strict boundary passed',flush=True)
    directory=args.out/'disassembly'
    directory.mkdir()
    windows={}
    for name,(lo,hi) in WINDOWS.items():
        (directory/(name+'.asm')).write_text(window(f.image,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))
        windows[name]=dict(start=hex(lo),end=hex(hi),sha256=sha(f.image[lo-BASE:hi-BASE]))
    root=Path.cwd()
    sources={Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and Path(file).resolve().is_relative_to(root/'tools'):
            sources.add(Path(file).resolve())
    report=dict(main_sha256=sha(f.image),checkpoint_sha256=CHECKPOINT_SHA,
        engine_sha256=sha(ENGINE.read_bytes()),
        source_sha256={str(path.relative_to(root)):sha(path.read_bytes()) for path in sorted(sources)},
        cases=cases,windows=windows,
        limits=[
            'Bounded native contracts, not connected cold boot or a real RTOS scheduler.',
            'NEW constructor prefix and tail are separate; peripheral relations and the predecessor of init10 are not executed.',
            'Initial sequence children are absent; normal exchange supplies the existing warm cache and child-subscription scenario.',
            'Clear media status is supplied. Nonzero selected bits stop at the native media callback; no hardware readiness is claimed.',
            'Warm factory-container pointers, parent registry membership, event3345 delivery and global factory publication are explicit fixtures.',
            'Parent handlers finish and selected children survive the native state changes. Event3345 ingress and root/mode active entry remain separate contracts, not a replay of all switcher handshakes.',
            'Native category controller is constructed but not started; its subscriptions, layer observers and parent reply-manager lists are empty.',
            'Application state10001 and GUI IDs201-203 are explicit witnesses; OS queues, locks, heap and scheduling remain modeled.',
            'No firmware modification, installable image, camera access or physical recovery guarantee.',
        ])
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(cases)} native exchange/control cases passed.',flush=True)


if __name__ == '__main__':
    main()
