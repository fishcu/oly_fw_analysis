#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Trace native COLOR/MONO work lists and request boundaries, offline only.

The CPU executes original firmware. Dimensions, allocation and queue acceptance
are explicit fixture models; there are no hardware pixels or camera accesses.
"""
import argparse
from itertools import product
import json
from pathlib import Path
import struct
import sys

from penf_emulator import firmware, ENGINE
from penf_probe import CALLER
from penf_hsl_context_probe import reenter, finished
from penf_vignette_camera_probe import (
    AllocationProbe, JOB, SLOTS, STRIDE, SIZE_QUERY, SERVICE, word,
)
from penf_repack_preflight import sha
from penf_grain_probe import fixture, complete, C, Q, O
from penf_probe import RESULT
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP

QUEUE = 0x604c2f1d
CURRENT = JOB + 12228
MASK_DATA = 0x19020000

# Function-aligned evidence windows. Ordering here is organizational, not a
# claimed ordering of pixels inside the ISP. Stop addresses are exclusive.
WINDOWS = {
    'job-preparation': (0x604c20ce,0x604c2447),
    'job-advance': (0x604c2447,0x604c2732),
    'job-finalizer': (0x604c2732,0x604c27bb),
    'initial-job-list': (0x604c2a4f,0x604c2bbf),
    'request-wait-release': (0x604c2bbf,0x604c2dd7),
    'creative-job-selector': (0x604c542d,0x604c630e),
    'primary-color-job': (0x604c4c84,0x604c4ce6),
    'grain-jobs-callbacks': (0x604c81db,0x604c8482),
    'late-shading-entry': (0x604c971e,0x604c9730),
    'late-shading-callback': (0x604c98fb,0x604c9910),
    'late-shading-wrapper': (0x604c9ad2,0x604c9b3b),
    'late-dispatch': (0x604c4710,0x604c4999),
    'final-output-submit': (0x604d5d7e,0x604d5f4d),
    'engine-dispatch-gates': (0x604aa595,0x604aaacd),
    'color-engine-dispatch': (0x604f2973,0x604f2a94),
    'raw-auxiliary-config': (0x604e874f,0x604e8894),
    'sibling-engine-dispatch': (0x604ec9e0,0x604eca35),
    'color-matrix': (0x604f45a6,0x604f46d5),
    'six-axis': (0x604f556c,0x604f5a63),
    'rgb-curve-config': (0x604f6083,0x604f6546),
    'global-chroma-gain': (0x604f698e,0x604f69ce),
    'tone-config': (0x604f7c66,0x604f7d3e),
    'post-ycc-tone-selector': (0x604f7ae0,0x604f7be4),
    'color-config-sequences': (0x604f8543,0x604f89c3),
}


def image_descriptor(pointer, fmt, dimensions, pitch=None):
    w, h = dimensions
    b = bytearray(64)
    struct.pack_into('<I', b, 0, pointer)
    struct.pack_into('<6H', b, 8, fmt, pitch or w, w, h, w, h)
    return bytes(b)


def describe(b):
    return dict(pointer=hex(struct.unpack_from('<I', b)[0]),
                format=hex(struct.unpack_from('<H', b, 8)[0]),
                pitch=struct.unpack_from('<H', b, 10)[0],
                stored_size=list(struct.unpack_from('<2H', b, 12)),
                window_size=list(struct.unpack_from('<2H', b, 16)))


class JobProbe(AllocationProbe):
    def __init__(self, mode=12, grain=3, shading=-5, dimensions=(5184, 3888),
                 alternate=0, fmt=0x0205, output_format=0x0702,
                 shading_enabled=True):
        super().__init__(dimensions)
        self.requests = []
        self.next_buffer = 0x30000000
        self.spec = dict(mode=mode, grain=grain, shading=shading,
                         dimensions=list(dimensions), alternate=alternate,
                         source_format=hex(fmt), output_format=hex(output_format),
                         shading_enabled=shading_enabled)
        s = self.s
        self.source = image_descriptor(0x40000000, fmt, dimensions)
        s.write(JOB+36, self.source)
        s.write(JOB+14, struct.pack('<H', mode))
        # Same size/aspect/header constants used by the existing still/recview
        # constructor fixture; full peripheral metadata is not supplied.
        s.write(JOB+22, b'\x01\x01')
        s.write(JOB+28, b'\x01')
        s.write(JOB+12192, struct.pack('<I', mode))
        # The ordinary constructor sets the shading-capable flag even at level
        # zero (604c1f5b..604c1f8b); do not equate zero strength to a missing job.
        flags = (0x80000 if shading_enabled else 0) | (0x200000 if mode == 12 else 0)
        s.write(JOB+16, struct.pack('<I', flags))
        s.write(JOB+12204, bytes([alternate]))
        s.write(JOB+0x1665, bytes([grain, shading & 255]))
        output = bytearray(image_descriptor(0x50000000, output_format, dimensions))
        if output_format >> 8 == 7:
            # Compact JPEG descriptor has codec fields here, not an input crop.
            output[16:20] = bytes(4)
        s.write(JOB+5232, output)
        # Explicit synthetic pre-existing radial-mask descriptor, not pixels.
        s.ram('radial_mask', MASK_DATA,
              bytes(12)+image_descriptor(0x60000000, 0x03a4, (128,128)), aliases=False)
        s.write(JOB+0x35b0, struct.pack('<I', MASK_DATA))

    def run_job(self, target, mask=0, frame=0, registers=None):
        s = self.s
        reenter(s, target, mask, frame, registers or dict(a0=JOB))
        start = s.steps
        for _ in range(64):
            r = s.run({CALLER+7, SIZE_QUERY, SERVICE, QUEUE}, limit=150000)
            pc = s.regs['pc']
            if r['status'] != 'breakpoint' or pc == CALLER+7:
                break
            if pc == SIZE_QUERY:
                assert s.regs['a0'] == JOB+4
                for ptr, value in zip((s.regs['a1'], s.regs['d0']), self.dimensions):
                    s.write(ptr, struct.pack('<H', value))
                self.calls.append(dict(model='dimensions', dimensions=self.dimensions))
                s.return_from_model(1)
            elif pc == SERVICE:
                assert s.regs['a0'] == JOB+4
                operation, slot = s.regs['d0'], s.regs['a1']
                if operation in (18,19):
                    assert (slot-JOB-SLOTS) % STRIDE == 0
                    assert 0 <= (slot-JOB-SLOTS)//STRIDE < 64
                    if operation == 18:
                        size, tag = word(s,slot+72), word(s,slot+76)
                        pointer = self.next_buffer
                        self.next_buffer += (size+0xffff)&~0xffff
                        self.live[slot] = pointer
                        s.write(slot+64, struct.pack('<I',pointer))
                        self.calls.append(dict(model='allocate', pointer=hex(pointer),
                            size=size, tag=hex(tag), slot=hex(slot)))
                    else:
                        assert self.live.pop(slot) == word(s,slot+64)
                        self.calls.append(dict(model='release',slot=hex(slot)))
                    s.return_from_model(1)
                elif operation == 13:
                    self.calls.append(dict(model='parameter availability', operation=operation,
                        key=hex(struct.unpack('<H',s.read(slot,2))[0]),
                        argument=s.read(slot,8).hex(), result=1))
                    s.return_from_model(1)
                else:
                    raise AssertionError(('unmodeled service',operation,hex(s.regs['mdr'])))
            else:
                assert s.regs['a0'] == JOB
                kind = s.read(CURRENT+16,1)[0]
                assert kind in (0,3)
                # Kind 3 uses the shorter packet. Bytes beyond it belong to
                # reusable workspace and can retain the preceding kind-0 job.
                request = s.read(CURRENT,1132 if kind==0 else 624)
                self.requests.append(dict(caller=hex(s.regs['mdr']),
                    kind=kind, stage=hex(struct.unpack_from('<H',request,12)[0]),
                    picture_mode=struct.unpack_from('<H',request,10)[0],
                    source=describe(request[20:84]), secondary=describe(request[84:148]),
                    outputs=([describe(request[532+56*i:588+56*i]) for i in range(5)
                              if any(request[532+56*i:588+56*i])] if kind == 0 else
                             [describe(request[276:340])]),
                    mask=describe(request[404:468] if kind==0 else request[148:212]),
                    dependency_token=hex(word(s,s.regs['sp']+28)),
                    assigned_token=hex(0x12340001+len(self.requests)),
                    request_size=len(request), request_sha256=sha(request),
                    request_hex=request.hex()))
                # Queue transport is not emulated. A deterministic token replaces
                # successful acceptance; no completion or ISP work is implied.
                s.write(s.regs['d1'],struct.pack('<I',0x12340000+len(self.requests)))
                s.return_from_model(0)
        if r['status'] != 'breakpoint' or s.regs['pc'] != CALLER+7:
            raise AssertionError((r['status'],r.get('fault'),hex(s.regs['pc'])))
        finished(s,r)
        assert s.read(JOB+36,64) == self.source
        return dict(entry=hex(target),instructions=s.steps-start,result=hex(s.regs['d0']))

    def select(self):
        result = self.run_job(0x604c542d,0xf0,36)
        assert result['result'] == '0x0'
        count = struct.unpack('<H',self.s.read(JOB+12198,2))[0]
        assert 0 < count <= 16
        entries = [struct.unpack('<3I',self.s.read(JOB+11868+12*i,12))
                   for i in range(count)]
        return entries,result

    def all_jobs(self):
        entries, selection = self.select()
        jobs=[]
        for i,(entry,callback,token) in enumerate(entries):
            self.s.write(JOB+12196,struct.pack('<H',i))
            before=len(self.requests)
            result=self.run_job(entry)
            assert result['result'] == '0x0', result
            jobs.append(dict(index=i,callback=hex(callback),**result,
                             requests=list(range(before,len(self.requests)))))
        for previous,current in zip(self.requests,self.requests[1:]):
            assert current['dependency_token'] == previous['assigned_token']
        assert self.requests[0]['dependency_token'] == '0x0'
        for request in self.requests:
            request['engine_selection'] = inspect_request(request)
        return dict(fixture=self.spec,selection=selection,jobs=jobs,
                    requests=self.requests,models=self.calls,
                    dependency_chain_verified=True, original_source_preserved=True,
                    live_allocations_at_submission_end=len(self.live))


def inspect_request(row):
    """Execute native gates on a captured request, without configuring pixels.

    Engine context mode/source/output pointers are explicit fixtures matching
    the native context layout. The request itself is byte-for-byte unchanged.
    Tone selection is queried only where the color-engine gate is enabled.
    """
    mode, stage = row['picture_mode'], int(row['stage'],16)
    request = bytes.fromhex(row['request_hex'])
    s,_ = fixture(0x604aa9f4,0x20,4,mode,stage)
    s.write(Q,request+bytes(1132-len(request)))
    s.write(C+20,struct.pack('<I',Q+20))
    s.write(C+28,struct.pack('<I',Q+(532 if row['kind']==0 else 276)))
    out={}
    for name,target,mask,frame in (
        ('raw_auxiliary_gate',0x604aa9c1,0,0),
        ('color_tone_gate',0x604aa9f4,0x20,4),
        ('sibling_engine_gate',0x604aaa74,0,0),
        ('combiner_selector',0x604fb7b8,0x20,8),
    ):
        reenter(s,target,mask,frame,dict(a0=C))
        complete(s)
        out[name]=s.regs['d0']
    if out['color_tone_gate']:
        reenter(s,0x604f75e5,0xf0,24,dict(a0=Q,a1=RESULT))
        complete(s)
        pointer=s.regs['a0']
        out['selected_tone_pointer']=hex(pointer)
        out['selected_tone_sha256']=sha(s.read(pointer,512))
    else:
        out['selected_tone_pointer']=None
    if row['kind']==3:
        # A small native routing run stops at either the shared pipeline or
        # the dedicated JPEG setup. Neither called implementation is modeled.
        route=0x1a000000
        s.ram('routing_work',route,struct.pack('<I',C)+bytes(60),aliases=False)
        reenter(s,0x604aa915,0,0,dict(a0=route))
        r=s.run({0x604aa68f,0x604ad7e4},limit=2000)
        assert r['status']=='breakpoint' and s.regs['pc'] in (0x604aa68f,0x604ad7e4)
        out['kind3_route_stop']=hex(s.regs['pc'])
        out['jpeg_only_route']=s.regs['pc']==0x604ad7e4
    assert s.read(Q,len(request))==request
    out['request_unchanged']=True
    return out


def validate_case(result):
    spec=result['fixture']; rows=result['requests']
    mode,alt=spec['mode'],spec['alternate']
    if spec['shading_enabled']:
        stages=([0] if mode==11 else [0x902,0xf005,0] if alt else [0x900,0x901,0xf005,0])
        assert [int(r['stage'],16) for r in rows]==stages
        assert rows[-1]['outputs'][0]['pointer']=='0x50000000'
        if mode==12:
            late,final=rows[-2:]
            assert late['source']['pointer']==rows[-3]['outputs'][0]['pointer']
            assert final['source']['pointer']==late['outputs'][0]['pointer']
            assert late['engine_selection']['color_tone_gate']==0
            assert late['engine_selection']['combiner_selector']==(33 if spec['shading'] else 0)
            if spec['output_format']=='0x702':
                assert final['engine_selection']['jpeg_only_route']
    if mode==12 and not alt:
        mask,develop=rows[:2]
        assert mask['source']==develop['source']
        assert develop['mask']['pointer']==mask['outputs'][0]['pointer']
        assert mask['engine_selection']['selected_tone_pointer']=='0x60610742'
        assert develop['engine_selection']['selected_tone_pointer']!='0x60610742'
        assert develop['engine_selection']['combiner_selector']==31
    elif mode==12:
        assert rows[0]['engine_selection']['combiner_selector']==32


def configuration_controls():
    """Small native controls, separate from the unmodified captured requests."""
    six_axis=[]
    # Values independently matched to the Workspace six-axis specification.
    expected={
        1: [18,4,24,0,8,8, 0,2,4,-1,-6,0],
        2: [0]*12,
        3: [-22,4,-16,0,4,-8, 3,0,-3,9,8,10],
        4: [14,0,0,5,0,0, -1,0,2,-2,0,0],
        11: [0]*12,
        12: [0]*12,
    }
    for mode, coefficients in expected.items():
        s,request=fixture(0x604f55de,0xf0,100,mode,0)
        complete(s)
        actual=list(struct.unpack('<12h',s.read(O+0x20c+108,24)))
        assert actual==coefficients
        assert s.read(Q,len(request))==request
        six_axis.append(dict(mode=mode,saturation=actual[:6],hue=actual[6:],
                             instructions=s.steps,request_unchanged=True))
    post_ycc=[]
    for mode,fmt,bypass in product((11,12),(0x0302,0x03a4),(0,1)):
        s,_=fixture(0x604f2973,0x20,8,mode,0xf005)
        s.write(Q+16,b'\x03')
        s.write(Q+28,struct.pack('<H',fmt))
        # Explicit control: enable the optional color-config route that the
        # stock late-shading request skips. This is not a native-job observation.
        s.write(Q+578,b'\x01')
        s.write(Q+587,bytes([bypass]))
        s.write(C+20,struct.pack('<I',Q+20))
        request=s.read(Q,1132)
        complete(s)
        tint=word(s,O+0x20c+76)
        tone=word(s,O+0x20c+0x1230)
        assert tint==(0 if fmt==0x0302 else 0x00808001)
        assert tone==0x605fdd38
        assert s.read(Q,1132)==request
        post_ycc.append(dict(mode=mode,source_format=hex(fmt),bypass=bypass,
            explicit_color_route_enable=True,tint_word=hex(tint),
            tone_pointer=hex(tone),instructions=s.steps,request_unchanged=True))
    return dict(six_axis=six_axis,post_ycc=post_ycc)


LIMITS = [
    'Original CPU code selects jobs and packs requests. No ISP pixels, JPEG bytes or camera I/O.',
    'Synthetic source/output descriptors and a pre-existing 128x128 radial-mask descriptor; no upstream sensor/capture producer or mask-cache construction.',
    'Dimensions, successful allocation, parameter-availability replies and enqueue acceptance modeled explicitly. Buffer addresses/tokens are synthetic.',
    'Work-list functions invoked in selected order; no RTOS concurrency, completion interrupt, queue wait, cache coherency or automatic release exercised.',
    'Mode/source/output pointers supplied for independent native engine gates; other engine context defaults are fixture values.',
    'Header variant and alternate flag are controlled inputs, not verified live-view/High-Res/user-mode labels.',
    'A zero shading level retains a supplied radial descriptor. This tests the downstream selector, not upstream zero-effect optimization.',
    'Separate post-YCC controls explicitly enable an otherwise skipped color configuration path; they do not claim stock late shading uses that path.',
]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--mode',type=int,default=12)
    ap.add_argument('--grain',type=int,default=3)
    ap.add_argument('--shading',type=int,default=-5)
    ap.add_argument('--alternate',type=int,choices=(0,1),default=0)
    ap.add_argument('--source-format',type=lambda x:int(x,0),default=0x0205)
    ap.add_argument('--output-format',type=lambda x:int(x,0),default=0x0702)
    ap.add_argument('--matrix',action='store_true',help='COLOR/MONO, grain Off/High, shading 0/-5, both alternate routes and two input families')
    ap.add_argument('--disassembly',action='store_true',help='Regenerate pinned native evidence windows alongside the audit')
    args=ap.parse_args()
    if args.matrix:
        cases=[JobProbe(mode,grain,shade,alternate=alt,fmt=fmt).all_jobs()
               for mode,grain,shade,alt,fmt in product((11,12),(0,3),(0,-5),(0,1),(0x0105,0x0205))]
        # Non-JPEG outputs verify that the last pass can be an ordinary
        # format/output pass rather than the dedicated JPEG-only fast route.
        cases += [JobProbe(mode,3,-5,output_format=0x0302).all_jobs() for mode in (11,12)]
    else:
        cases=[JobProbe(args.mode,args.grain,args.shading,alternate=args.alternate,
                       fmt=args.source_format,output_format=args.output_format).all_jobs()]
    for result in cases:
        validate_case(result)
    args.out.mkdir(exist_ok=False,parents=True)
    root=Path(__file__).resolve().parent.parent
    sources={Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).resolve().is_relative_to(root/'tools'):
            sources.add(Path(path).resolve())
    report=dict(firmware_sha256=sha(firmware()),engine_sha256=sha(ENGINE.read_bytes()),
                source_sha256={str(p.relative_to(root)):sha(p.read_bytes()) for p in sorted(sources)},
                cases=cases,configuration_controls=configuration_controls(),limits=LIMITS)
    (args.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    if args.disassembly:
        destination=args.out/'disassembly'
        destination.mkdir()
        windows=[]
        data=firmware()
        for name,(start,stop) in WINDOWS.items():
            path=destination/(name+'.asm')
            path.write_text(window(data,DEFAULT_IMAGE,DEFAULT_OBJDUMP,start,stop))
            windows.append(dict(file=path.name,start=hex(start),stop_exclusive=hex(stop),
                                sha256=sha(path.read_bytes())))
        (destination/'manifest.json').write_text(json.dumps(dict(
            firmware_sha256=sha(data),windows=windows),indent=2)+'\n')
    print(json.dumps(dict(out=str(args.out),cases=len(cases),
                         requests=sum(len(c['requests']) for c in cases))))


if __name__ == '__main__':
    main()
