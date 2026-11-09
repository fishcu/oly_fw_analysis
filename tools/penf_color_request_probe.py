#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Stock COLOR edit -> selected-state request -> native event-pump reply.

Offline only. Explicit selected running state, isolated task contexts and OS
FIFO/flag models; not connected boot, physical scheduling or camera recovery.
No firmware modification. Unknown instructions, accesses and call sites stop.
"""
import argparse
import struct
import json
from penf_color_notification_probe import (
    ALLOCATORS, CHECKPOINT_SHA, Contracts, DEFAULT_IMAGE, DEFAULT_OBJDUMP,
    DIRTY, ENGINE, Fixture, LISTENERS, MANAGER, REQUEST, SEQUENCE,
    VIEW_CALLBACKS, VIEWER, at, current_record, edit_prefix, prepare,
    returned, sequence_cache, sha, u32, window, word,
)
from pathlib import Path
from penf_emulator import Region

FACTORY, ROOT, STILL, REPLIES, WRAPPED_SEQUENCE = (0x24000000,0x24001000,0x24002000,0x24003000,0x24004000)
ALT_CALLER, ALT_STACK = 0x18100000, 0x18118000
MAIN_THREAD = 0x618ea278
WAIT, EMPTY_WAIT, COMPLETION, CHANGE_SEQUENCE = 0x606b5072, 0x6003814e, 0x606f1c9c, 0x608038b2
EXTRA_ALLOCS = {(0x60950a6e,0x60931eb6):8,(0x60950a6e,0x606b8c39):12,
 (0x60950a6e,0x6093205b):28,(0x60950a6e,0x60932176):28,(0x60950a6e,0x60804306):32}

class RequestContracts(Contracts):
    def __init__(self, old):
        self.__dict__.update(old.__dict__)
        self.queues={}
        self.flags={}
        self.framework_lock=False
        self.extra_observations={0x60934b16,0x6093464e,0x609326fc,0x6080779f,0x60808c9e,0x608042d1,
                                 0x60931e5f,0x606f1c9c,0x606f1cc3,0x60951b30,0x608042e5,
                                 0x609287a9,0x60929d14}

    @property
    def hooks(self):
        return super().hooks | self.extra_observations | {0x609520d2,0x609520be,0x60036920,0x600366eb,
             0x60034f09,0x60034dad,0x60030c1d,0x60950a5a,0x60031443}

    def model(self):
        s=self.s
        pc,ret,a,d=(s.regs[k] for k in ('pc','mdr','a0','d0'))
        item=dict(entry=hex(pc),caller_return=hex(ret))
        result=0
        if pc in self.extra_observations:
            self.observations.append(dict(entry=hex(pc),caller_return=hex(ret),a0=hex(a),a1=hex(s.regs['a1']),d0=d,d1=s.regs['d1']))
            step=s.run(self.hooks-{pc},limit=1)
            assert step['status']=='instruction_limit' and step['completed']==1
            return
        if pc in ALLOCATORS and (pc,ret) in EXTRA_ALLOCS:
            assert EXTRA_ALLOCS[(pc,ret)]==d,(hex(pc),hex(ret),d)
            ptr=self.next_address;self.next_address+=0x1000
            s.ram('request_allocation_'+hex(ptr),ptr,bytes([self.fill])*d,aliases=False)
            self.heap[ptr]=dict(bytes=d,caller=ret)
            s.regs['a0']=ptr
            item.update(operation='allocation',address=hex(ptr),bytes=d)
        elif pc==0x60950a5a:
            expected={0x606b8d52:(12,0x606b8c39),0x60931e8f:(8,0x60931eb6),
                      0x6080434c:(32,0x60804306),0x606b505a:(8,0x609509dc),
                      0x606f2803:(12,0x606f1397)}
            if ret==0x6094f029:
                assert self.heap[a]['caller'] in (0x607607fd,0x6093205b,0x60932176)
                expected[ret]=(self.heap[a]['bytes'],self.heap[a]['caller'])
            assert ret in expected,(hex(ret),hex(a),self.heap[a])
            assert (self.heap[a]['bytes'],self.heap[a]['caller'])==expected[ret]
            allocation=self.heap.pop(a)
            s.regions=[region for region in s.regions if region.address!=a]
            item.update(operation='free',address=hex(a),allocation=allocation)
        elif pc==0x60031443:
            assert ret==0x6094fe69 and self.handles[d]=='semaphore'
            del self.handles[d]
            item.update(operation='delete OS semaphore',handle=d)
        elif pc in (0x606b5072,0x606b5062) and ret in (0x606f1cd6,0x606f1a7e,0x606f1a9e,0x606f1aaf,0x606f130a):
            if ret==0x606f130a:
                assert a==word(s,word(s,0x61600950))
            else:assert a==self.private_wait
            take=pc==0x606b5072
            assert word(s,a)==0x609524f0
            handle=int.from_bytes(s.read(word(s,a+4)+4,2),'little')
            assert self.handles[handle]=='semaphore'
            if take:
                assert d==1000 and a not in self.held
                self.held.add(a)
            else:
                assert a in self.held
                self.held.remove(a)
            result=1
            item.update(operation='available semaphore take' if take else 'semaphore give',address=hex(a))
        elif pc in (0x609520d2,0x609520be):
            enter=pc==0x609520d2
            assert ret in (0x6095004e,0x6095007f,0x6094ffbf,0x60950018,0x6095000f)
            assert self.framework_lock != enter
            self.framework_lock=enter
            result=int(enter)
            item.update(operation='framework lock enter' if enter else 'framework lock leave')
        elif pc==0x60036920:
            assert ret==0x60950059 and self.handles[d]=='queue'
            event=s.regs['d1'];q=self.queues.setdefault(d,[])
            assert len(q)<400
            q.append(event)
            item.update(operation='OS queue send',queue=d,event=hex(event),
                        type=int.from_bytes(s.read(event+4,2),'little'),target=hex(word(s,event+24)))
        elif pc in (0x600366eb,0x60030c1d):
            assert self.handles[d]=='flag'
            assert ret in (0x60950429,0x60950458)
            if pc==0x600366eb:self.flags[d]=self.flags.get(d,0)|s.regs['d1']
            else:self.flags[d]=self.flags.get(d,0)&s.regs['d1']
            item.update(operation='OS flag update',handle=d,pattern=self.flags[d])
        elif pc==0x60034f09:
            assert ret==0x6094ffcb and self.handles[d]=='queue'
            # ITRON T_RDTQ: two halfword waiting-task IDs, then count.
            s.write(a,struct.pack('<HHI',0,0,len(self.queues.get(d,[]))))
            item.update(operation='OS queue query',queue=d,count=len(self.queues.get(d,[])))
        elif pc==0x60034dad:
            assert ret==0x6094fff9 and self.handles[d]=='queue'
            event=self.queues[d].pop(0)
            u32(s,a,event)
            item.update(operation='OS queue receive',queue=d,event=hex(event),
                        type=int.from_bytes(s.read(event+4,2),'little'))
        else:
            return super().model()
        self.events.append(item)
        s.return_from_model(result)

def separate_resume(c, context, stop):
    """Share RAM, preserve the paused editor's registers and entire stack.

    Only pause at native instruction addresses, never at the mutable model
    return trampoline. This is explicit host scheduling, not a kernel model.
    """
    s=c.s
    saved=s.regs.copy()
    original_stack=s.read(0x18010000,0x10000)
    s.regs=context.copy()
    r=c.run(stop=stop)
    result_regs=s.regs.copy()
    assert s.read(0x18010000,0x10000)==original_stack
    s.regs=saved
    return r,result_regs


def separate_call(c,address,mask,frame,regs=None,stop=ALT_CALLER+7):
    s=c.s
    caller=b'\xdd'+struct.pack('<i',address-ALT_CALLER)+bytes((mask,frame))+b'\xcb'
    s.regions=[r for r in s.regions if r.name!='separate_caller']
    s.regions.append(Region('separate_caller',ALT_CALLER,caller,'rx'))
    context=dict(pc=ALT_CALLER,sp=ALT_STACK,psw=0,**(regs or {}))
    r,result_regs=separate_resume(c,context,stop)
    if stop==ALT_CALLER+7:
        assert r['status']=='breakpoint' and result_regs['pc']==stop,r
        assert result_regs['sp']==ALT_STACK
    return r,result_regs

def request_fixture(f, profile, sector, fill, variant, *, prepared=None,
                    reactive_context=MAIN_THREAD):
    """Build the selected-state witness; optionally retain an initialized context."""
    e,base,p=prepared if prepared is not None else prepare(f,profile,sector,fill,0x10001)
    cache=sequence_cache(e,base)
    prefix=edit_prefix(e)
    r=base.run(stop=REQUEST);at(e.s,r,REQUEST)
    c=base if isinstance(base,RequestContracts) else RequestContracts(base)
    s=e.s
    s.ram('dispatcher_stack',0x18110000,bytes([fill])*0x10000,aliases=False)
    s.ram('native_reactive_base',STILL,bytes([fill])*112,aliases=False)
    base_ctor=separate_call(c,0x60950afc,0x30,16,dict(a0=STILL,a1=reactive_context,d0=0))[0]
    vtable=0x60a4769c if variant=='new' else 0x609f0410
    u32(s,STILL,vtable)
    for off,data in ((118,bytes(2)),(148,struct.pack('<I',STILL)),(256,bytes(4)),
                     (264,struct.pack('<I',REPLIES)),(928,struct.pack('<2I',WRAPPED_SEQUENCE,0)),(980,bytes(4))):
        s.ram('selected_still_'+str(off),STILL+off,data,aliases=False)
    s.ram('reply_manager_destination',REPLIES,bytes([fill])*16,aliases=False)
    reply_ctor=separate_call(c,0x60931b47,0,0,dict(a0=REPLIES))[0]
    entry=0x6092a01b if variant=='new' else 0x60808fb3
    state_entry=separate_call(c,entry,0,0,dict(a0=STILL))[0]
    s.ram('explicit_factory',FACTORY,struct.pack('<3I',0x60a49514,0,ROOT),aliases=False)
    s.ram('explicit_root_selection',ROOT+148,struct.pack('<I',STILL),aliases=False)
    u32(s,0x61602c58,FACTORY)
    s.ram('no_sequence_event_subscription',WRAPPED_SEQUENCE+176,bytes(4),aliases=False)
    s.ram('current_sequence_cache_pointer',WRAPPED_SEQUENCE+2836,struct.pack('<I',SEQUENCE),aliases=False)
    s.ram('captured_event_ancestor_id',0x618ea180,f.read(0x618ea180,2))
    assert word(s,STILL+256)==14 and word(s,STILL+980)==14
    assert word(s,STILL+100)==MAIN_THREAD
    assert s.read(0x618ea180,2)==bytes(2)
    assert word(s,0x61606208)==0
    details=dict(profile=profile,sector=sector,fill=hex(fill),variant=variant,vtable=hex(vtable),preparation=p,
                 sequence_cache=cache,prefix=prefix,request_api_stop=r,
                 reactive_base_constructor=base_ctor,reply_manager_constructor=reply_ctor,
                 native_state14_entry=state_entry)
    return e,c,details


def queue_info(s):
    queue=word(s,MAIN_THREAD+68)
    return (int.from_bytes(s.read(queue+36,2),'little'),
            int.from_bytes(s.read(queue+52,2),'little'))


def held_editor(e,c,details):
    s=e.s
    responder=word(s,0x61602470)
    assert c.private_wait in c.held
    assert word(s,responder+120)==c.private_wait
    assert word(s,responder+132)==0xf0000001
    assert s.read(0x619bd870,96).hex()==details['preparation']['display_before']['wheel_hex']
    assert not c.timers and word(s,MANAGER+564)==0
    return dict(responder=hex(responder),private_semaphore=hex(c.private_wait),
                result=hex(word(s,responder+132)),wheel_unchanged=True,notifications_started=False)


def case(f,profile,sector,fill,*,variant='new',stale=False,missing_cache=False,timeout=False):
    e,c,details=request_fixture(f,profile,sector,fill,variant)
    return continue_case(e,c,details,variant=variant,stale=stale,
                         missing_cache=missing_cache,timeout=timeout)


def continue_case(e,c,details,*,variant='new',stale=False,missing_cache=False,
                  timeout=False,pump_entry=(0x60951be7,0xf0,44)):
    """Run a prepared editor request, preserving all reply and lifetime checks."""
    s=e.s
    f=e.f
    if stale:
        original=int.from_bytes(s.read(SEQUENCE+164,2),'little')
        s.write(SEQUENCE+164,struct.pack('<H',original^1))
    if missing_cache:
        s.regions=[r for r in s.regions if r.name!='current_sequence_cache_pointer']
    send=c.run(stop=WAIT)
    at(s,send,WAIT)
    assert s.regs['mdr']==0x606f1a7e and s.regs['a0']==c.private_wait and s.regs['d0']==1000
    details.update(send_and_actual_wait=send,undelivered_request=held_editor(e,c,details))
    qid,flagid=queue_info(s)
    assert len(c.queues[qid])==1
    event=c.queues[qid][0]
    responder=word(s,0x61602470)
    assert word(s,event+24)==STILL
    stop=CHANGE_SEQUENCE if stale else COMPLETION
    pump,context=separate_call(c,*pump_entry,dict(a0=MAIN_THREAD),stop=stop)
    details['native_pump_to_completion']=pump
    if stale or missing_cache:
        if stale:
            assert pump['status']=='breakpoint' and context['pc']==CHANGE_SEQUENCE,pump
            assert (context['a0'],context['d0'])==(STILL,2)
        else:
            assert pump['status']=='memory_fault' and pump['pc']=='0x607e11a2',pump
            assert pump['fault']['address']==WRAPPED_SEQUENCE+2836 and pump['fault']['access']=='read'
        details['strict_control']='stale cache reaches changeSequence' if stale else 'missing cache pointer faults'
        details['still_waiting']=held_editor(e,c,details)
        assert [x['type'] for x in c.events if x.get('operation')=='OS queue send']==[0x404e,11771]
        return details
    assert pump['status']=='breakpoint' and context['pc']==COMPLETION,pump
    assert context['a0']==responder
    handler='0x609287a9' if variant=='new' else '0x6080779f'
    assert sum(x['entry']==handler for x in pump['observations'])==1
    details['acknowledgement_did_not_release_wait']=held_editor(e,c,details)
    if timeout:
        # Explicit elapsed-interval control while completion is paused before
        # executing. Returning false is a timeout, NEVER a fabricated success.
        assert s.regs['pc']==WAIT and s.regs['a0'] in c.held
        s.return_from_model(0)
        timed=c.run(stop=WAIT)
        at(s,timed,WAIT)
        assert s.regs['mdr']==0x606f1a9e and s.regs['d0']==1000
        details['one_supplied_timeout_then_native_retry']=dict(execution=timed,**held_editor(e,c,details))
    completion,context=separate_resume(c,context,EMPTY_WAIT)
    details['completion_and_pump_empty_wait']=completion
    assert completion['status']=='breakpoint' and context['pc']==EMPTY_WAIT,completion
    assert (context['d0'],context['d1'],context['a1'])==(flagid,1,1)
    assert not c.queues[qid] and c.flags[flagid]==0 and not c.framework_lock
    assert c.private_wait not in c.held
    assert (word(s,responder+120),word(s,responder+132))==(0,0)
    reply_manager=word(s,STILL+264)
    assert reply_manager and word(s,reply_manager+4)==word(s,reply_manager+8)==0
    assert word(s,STILL+104)==word(s,responder+104)==0
    assert word(s,STILL+16)==word(s,responder+16)==0
    assert s.read(SEQUENCE+162,24).hex()==details['sequence_cache']['cache']
    sends=[x for x in c.events if x.get('operation')=='OS queue send']
    receives=[x for x in c.events if x.get('operation')=='OS queue receive']
    assert [x['type'] for x in sends]==[0x404e,11771,11770]
    assert [(x['event'],x['type']) for x in sends]==[(x['event'],x['type']) for x in receives]
    assert [x['target'] for x in sends]==[hex(STILL),hex(responder),hex(responder)]
    assert all(int(x['event'],0) not in c.heap for x in sends)
    assert [x['d0'] for x in c.observations if x['entry']=='0x608042e5']==[0]
    before=bytes.fromhex(details['preparation']['display_before']['wheel_hex'])
    result=c.run()
    returned(s,result)
    details['original_editor_return']=result
    assert not c.held and not c.framework_lock
    assert current_record(f,s,e.key)==-2 and word(s,DIRTY)==1
    wheel=s.read(0x619bd870,96)
    assert wheel==s.read(VIEWER+36,96)
    assert [i for i,(a,b) in enumerate(zip(before,wheel)) if a!=b]==[2]
    assert list(wheel[1:3])==[3,3]
    assert word(s,MANAGER+564)==1 and word(s,word(s,MANAGER+572))==e.key
    assert len(c.timers)==1
    observed=[x['entry'] for x in result['observations']]
    assert all(observed.count(hex(cb))==1 for cb in LISTENERS+VIEW_CALLBACKS)
    assert [x['d0'] for x in result['observations'] if x['entry']=='0x6076081d']==[0]
    temporary_callers={0x607607fd,0x606f1397,0x60931eb6,0x606b8c39,0x6093205b,0x60932176,0x60804306}
    assert not [a for a in c.heap.values() if a['caller'] in temporary_callers]
    details.update(queue_exchange=sends,wheel_hex=wheel.hex(),temporary_request_objects_freed=True,
                   all_semaphores_released=True,original_stack_restored=True)
    return details


WINDOWS={
    'factory-send':(0x60934b16,0x60934b31),
    'selected-component':(0x60934649,0x60934672),
    'component-send-and-dispatch':(0x609326fc,0x609327c0),
    'reactive-send':(0x60950e5f,0x60950eab),
    'reactive-send-target':(0x6095147e,0x609514e5),
    'reactive-dispatch':(0x60950d38,0x60950de6),
    'reactive-handler':(0x60951134,0x609511f7),
    'component-handler':(0x60932b34,0x60932bda),
    'still-child-selection':(0x6080b9fd,0x6080ba48),
    'still-state-dispatch':(0x60806c86,0x60806d1f),
    'still-state14':(0x60808fb3,0x6080901a),
    'still-settings-action':(0x608042cc,0x6080434f),
    'request-ancestor':(0x606b8b1c,0x606b8b48),
    'sequence-event-subscription':(0x6093045e,0x609304f8),
    'reply-registration':(0x60931c41,0x60931c59),
    'reply-complete':(0x60931e5f,0x60931e92),
    'reply-ack':(0x60932012,0x6093212d),
    'reply-success':(0x6093212d,0x6093228c),
    'request-wait':(0x606f1a3f,0x606f1abb),
    'release-wait':(0x606f1c9c,0x606f1cd9),
    'thread-dispatch-and-pump':(0x60951b2b,0x60951cd9),
    'queue-pop-and-send':(0x6094ffa7,0x60950084),
    'queue-query-kernel-layout':(0x60034f09,0x60034fec),
    'queue-flag-updates':(0x60950412,0x60950471),
    'list-insert':(0x606b8c25,0x606b8c63),
    'list-remove':(0x606b8d20,0x606b8d55),
    'semaphore-delete':(0x6094fe4a,0x6094fe7f),
    'shooting-constructor-ownership':(0x609274e6,0x6092753f),
    'new-shooting-constructor':(0x60927b64,0x60927b90),
    'new-shooting-state-dispatch':(0x60927c2e,0x60927cc7),
    'new-shooting-state14':(0x6092a01b,0x6092a082),
    'new-shooting-settings-handler':(0x60929d14,0x60929d72),
}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',required=True,type=Path)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    f=Fixture()
    report=dict(main_sha256=sha(f.image),checkpoint_sha256=CHECKPOINT_SHA,cases=[])
    assert report['main_sha256']=='a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4'
    for fill in (0,0xa5):
        for profile,sector in ((1,1),(2,6),(3,12)):
            report['cases'].append(case(f,profile,sector,fill,timeout=profile==1))
            print(f'NEW shooting, COLOR{profile}, sector{sector}, fill{fill:#x}: native request/reply and editor return passed',flush=True)
        report['cases'].append(case(f,1,1,fill,variant='base'))
        print(f'Base shooting, fill{fill:#x}: native request/reply and editor return passed',flush=True)
    report['stale_sequence_control']=case(f,1,1,0xa5,stale=True)
    print('Stale sequence cache: strict changeSequence stop passed',flush=True)
    report['unmapped_cache_pointer_control']=case(f,1,1,0xa5,missing_cache=True)
    print('Unmapped sequence pointer: strict native read fault passed',flush=True)
    report['limits']=[
        'Explicit state10001, selected factory/component bindings and native state14 entry; no provenance from running boot',
        'Still base609f0410 and NEW60a4769c vtables tested; other components/states not covered',
        'Child-sequence subscription state0, no secondary sequence; captured ancestor gate618ea180=0 and61604864=0',
        'Native base and reply-manager constructors; the full still-component constructor was not run',
        'FIFO, flags, heap, OS handles, locks and separate stack scheduling are explicit host contracts',
        'Fixture taskID64 does not establish editor task ownership or real scheduler independence',
        'No missing-reply success, stale-sequence success, physical display, ISP, capture, persistence or recovery model',
        'Group observers remain empty and notification timer is scheduled but not fired',
    ]
    sources=[Path(__file__)]+[Path('tools')/name for name in (
        'penf_color_notification_probe.py','penf_color_refresh_probe.py','penf_color_edit_probe.py',
        'penf_profile_lifecycle_probe.py','penf_profile_context_probe.py','penf_profile_followup_probe.py',
        'penf_probe.py','penf_boot_emulator.py','penf_emulator.py','penf_recovery_isolation_probe.py')]
    report['source_sha256']={str(p):sha(p.read_bytes()) for p in sources}
    report['engine_sha256']=sha(ENGINE.read_bytes())
    directory=args.out/'disassembly'
    directory.mkdir()
    for name,(lo,hi) in WINDOWS.items():
        (directory/(name+'.asm')).write_text(window(f.image,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('All connected request contracts and controls passed.',flush=True)


if __name__=='__main__':main()
