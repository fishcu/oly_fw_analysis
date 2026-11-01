"""Execute placed five-point graph callbacks against explicit native UI fixtures."""
if not __debug__:
    raise RuntimeError('Graph evidence requires assertions')

import argparse
from dataclasses import replace
import json
from itertools import product
from pathlib import Path
import struct

from penf_emulator import BASE, Region, execute, firmware
from penf_probe import ProbeState, CALLER
from penf_hsl_context_probe import reenter
from penf_color_text_probe import fixture as font_fixture, CONTEXT, BACKEND
from penf_profile_context_probe import resume
from penf_profile_lifecycle_probe import returned
from penf_tone_editor_probe import fixture as editor_fixture, actuator, current, mode, ACTUATOR
from penf_tone_graph_candidate import build_graph
from penf_tone_transport_probe import put32, set_words, stopped
from penf_tone_integration_probe import packed
from penf_tone_probe import PRESERVED, INITIAL_SP, NativeToneParameters, native_tone, identity_lut, sha
from penf_tone_points import FivePoints, resolve
from penf_recovery_isolation_probe import without_ranges

RECEIVER, CHILDREN, ROOT_OBJECT, JOB, CONTROLLER = 0x19600000,0x19700000,0x19800000,0x19801000,0x19804000
RASTER=0x606e15cc


class PeakState(ProbeState):
    def run(self,hooks,limit=100000):
        if not getattr(self,'measure_stack',False):
            return super().run(hooks,limit=limit)
        result=execute(self.regions,self.regs,0xffffffff,breakpoints=hooks,
                       limit=min(limit,100000),trace_limit=100000,timeout=120,changed_captures=True)
        assert len(result['trace'])>=result['completed'],(len(result['trace']),result['completed'])
        self.minimum_sp=min(getattr(self,'minimum_sp',INITIAL_SP),result['registers']['sp'],
                            *(r['sp'] for r in result['trace']))
        for item in result['memory']:
            self.write(self.regions[item['index']].address,bytes.fromhex(item['hex']))
        self.regs=result['registers'];self.steps+=result['completed']
        result['memory']=[];result['trace']=[]
        self.events.append(dict(kind='execution',result=result))
        return result


def fixture(graph,profile=1,page=0,controls=(0,0,0),word=None,layout=0,layer=2,measure_stack=False):
    s=editor_fixture(graph.base,replace(graph.editor,image=graph.image))
    s.__class__=PeakState
    f=font_fixture()
    existing={r.name for r in s.regions}
    for r in f.regions:
        if r.name not in existing and r.name not in {'main','caller','stack','result','return_trampoline','input_package'}:
            s.regions.append(r)
    s.regions=[replace(r,data=r.data+bytes(4)) if r.name=='drawing_context_fixture' else r for r in s.regions]
    width=640+80*layout
    for off in (4,24):s.write(CONTEXT+off,struct.pack('<4h',0,0,width-1,479))
    s.write(BACKEND,struct.pack('<3H',0,width,480))
    put32(s,BACKEND+92,0x60bcc0e8)
    s.ram('opaque_surfaces',0x19510000,bytes(96),aliases=False)
    s.write(0x61a8e308,struct.pack('<6I',*(0x19510000+i*16 for i in range(6))))
    s.ram('native_logging_disabled',0x6161bdd4,bytes(8))
    root=bytearray(2044)
    struct.pack_into('<I',root,0,0x60de1944)
    struct.pack_into('<4H',root,8,0,0,width,480)
    s.ram('root_fixture',ROOT_OBJECT,root,aliases=False)
    s.ram('root_singleton_pointer',0x6160cbf8,struct.pack('<I',ROOT_OBJECT))
    receiver=bytearray(1040)
    struct.pack_into('<I',receiver,0,0x60ec4cac)
    struct.pack_into('<4H',receiver,8,0,0,width,480)
    struct.pack_into('<III',receiver,96,RECEIVER+96,RECEIVER+96,0)
    for i in range(33):struct.pack_into('<I',receiver,792+4*i,CHILDREN+320*i)
    s.ram('tone_display_receiver',RECEIVER,receiver,aliases=False)
    for i in range(33):
        child=bytearray(300)
        struct.pack_into('<IH',child,0,0x60de3ff8,32771)
        struct.pack_into('<4H',child,8,348+70*layout,107,262,266)
        struct.pack_into('<I',child,16,1)
        child[131]=29
        s.ram('display_child_'+str(i),CHILDREN+320*i,child,aliases=False)
    s.ram('native_paint_job',JOB,struct.pack('<3I',0,layer,CONTEXT),aliases=False)
    actuator(s,profile,page);mode(s,53+profile);current(s,profile,controls)
    word=FivePoints().pack() if word is None else word
    set_words(s,[word]*3)
    controller=bytearray(180)
    struct.pack_into('<I',controller,0,ACTUATOR)
    struct.pack_into('<3I',controller,8,3,18,20)
    s.ram('tone_controller_fixture',CONTROLLER,controller,aliases=False)
    s.ram('current_controller',0x6161b810,struct.pack('<I',CONTROLLER))
    s.events=[];s.steps=0;s.minimum_sp=INITIAL_SP;s.measure_stack=measure_stack
    s.graph_inputs=dict(profile=profile,page=page,controls=controls,word=word,layout=layout,layer=layer)
    return s


def paint(s,graph):
    context=s.read(CONTEXT,684);backend=s.read(BACKEND,160)
    receiver=s.read(RECEIVER,1040)
    rectangles=[];native_return=None;native_context=None
    after_native=graph.symbols['tone_paint_after_native']
    stops=(after_native,RASTER,CALLER+7)
    reenter(s,graph.symbols['tone_paint_gate'],0,0,dict(PRESERVED,a0=RECEIVER,a1=JOB))
    r=s.run(set(stops),limit=100000)
    while s.regs['pc']!=CALLER+7:
        pc=s.regs['pc']
        if r['status']!='breakpoint':
            raise AssertionError((r['status'],r.get('fault'),hex(pc)))
        if pc==after_native:
            native_return=s.regs['d0'];native_context=s.read(CONTEXT,684)
            r=resume(s,tuple(x for x in stops if x!=pc),limit=100000)
            continue
        elif pc==RASTER:
            raw=s.read(s.regs['a0'],28)
            x,y,w,h=struct.unpack_from('<4h',raw,8)
            rectangles.append(dict(x=x,y=y,width=w,height=h,palette=raw[20]))
            s.return_from_model(0)
        else:raise AssertionError(hex(pc))
        r=resume(s,stops,limit=100000)
    returned(s,r)
    assert s.read(CONTEXT,684)==native_context
    assert s.regs['d0']==native_return
    assert s.read(BACKEND,160)==backend
    assert s.read(RECEIVER,1040)==receiver
    assert s.regs['sp']==INITIAL_SP
    assert all(s.regs[k]==v for k,v in PRESERVED.items()),s.regs
    return dict(rectangles=rectangles,
                peak_stack_bytes=INITIAL_SP-s.minimum_sp if s.measure_stack else None,complete_return=True,
                context_matches_native_paint=True,native_paint_return_preserved=True,
                native_context_changed_bytes=sum(a!=b for a,b in zip(context,native_context)),
                backend_unchanged=True,receiver_unchanged=True,
                callee_saved_unchanged=True,stack_restored=True,
                models=['rectangle raster submission'])


def assert_geometry(result,inputs):
    points=resolve(inputs['word'],inputs['controls'])
    curve=points.apply(identity_lut())
    x0=351+70*inputs['layout'];bottom=367
    rectangles=[];previous=bottom-(curve[0]>>2)
    markers=dict(zip((0,64,128,191,255),points.heights))
    for index,value in enumerate(curve):
        y=bottom-(value>>2)
        rectangles.append(dict(x=x0+index,y=min(y,previous),width=1,height=abs(y-previous)+1,palette=5))
        if index in markers:
            rectangles.append(dict(x=x0+index-2,y=bottom-(markers[index]>>2)-2,width=5,height=5,palette=5))
        previous=y
    assert result['rectangles']==rectangles,[(i,a,b) for i,(a,b) in enumerate(zip(result['rectangles'],rectangles)) if a!=b][:5]
    result.update(inputs=inputs,heights=points.heights,curve_sha256=sha(struct.pack('<256H',*curve)),
                  oracle_rectangles_equal=True,exact_quarter_anchor_heights=True,
                  text_owned_by_native_footer=True)


def paint_cases(graph):
    cases=[]
    for options in (dict(profile=1,page=0,word=FivePoints((64,320,544,704,960)).pack(),measure_stack=True),
                    dict(profile=2,page=2,controls=(-7,7,-7),word=packed(1023,0),layout=1),
                    dict(profile=3,page=1,controls=(4,-2,-3),word=0)):
        state=fixture(graph,**options)
        result=paint(state,graph)
        assert_geometry(result,state.graph_inputs)
        cases.append(result)
    return cases


def remove_late(state,mask):
    state.write(0x61c58404,bytes((mask,)))
    holes=[]
    if not mask&0x20:holes.append((0x610f1e54,0x610f2000))
    if not mask&0x80:holes.append((0x6115b014,0x6115c800))
    holes += [(lo+0x40000000,hi+0x40000000) for lo,hi in holes]
    state.regions=[r for r in state.regions if not any(lo<=r.address and r.address+len(r.data)<=hi for lo,hi in holes)]
    state.regions=without_ranges(state.regions,holes)


def filter_cases(graph):
    state=fixture(graph)
    receiver=state.read(RECEIVER,1040)
    children=b''.join(state.read(CHILDREN+320*i,300) for i in range(33))
    cases=[]
    def run(index,hidden):
        put32(state,INITIAL_SP+116,RECEIVER);put32(state,INITIAL_SP+204,CHILDREN+320*index)
        state.regs=dict(PRESERVED,pc=0x60bf7c40,sp=INITIAL_SP,psw=0,d0=0xabcdef,d1=0x123456,a0=0,a1=0)
        target=0x60bf80cf if hidden else 0x60bf7c47
        stopped(state,state.run({0x60bf80cf,0x60bf7c47},limit=20000),target)
        assert state.regs['sp']==INITIAL_SP
        assert all(state.regs[k]==v for k,v in PRESERVED.items()),(index,state.regs)
        if hidden:assert state.regs['d0']==0
        else:
            assert state.regs['a0']==CHILDREN+320*index
            assert state.regs['a1']==int.from_bytes(state.read(0x60de3ff8+80,4),'little')
        assert state.read(RECEIVER,1040)==receiver
        assert b''.join(state.read(CHILDREN+320*i,300) for i in range(33))==children
        cases.append(dict(child=index,hidden=hidden))
    for profile in (1,2,3):
        mode(state,53+profile)
        for page in (0,1,2):
            actuator(state,profile,page)
            hidden=set(range(5,10))|set(range(13,22))|set(range(26,32))
            for index in range(33):run(index,index in hidden)
    actuator(state,1,2)
    for public in (1,55,57,59):
        mode(state,public)
        for index in (5,26,31):run(index,False)
    mode(state,54)
    put32(state,CONTROLLER,0)
    for index in (26,31):run(index,False)
    put32(state,CONTROLLER,ACTUATOR)
    for mask in (4,0x24,0x84):
        original=list(state.regions);remove_late(state,mask)
        for index in (5,26,31):run(index,False)
        state.regions=original
    return dict(cases=len(cases),profiles=3,pages=3,all_children=33,
                native_hidden_join_or_exact_displaced_loads=True,receiver_and_children_unchanged=True,
                absent_late_code_unmapped=True,models=[])


def paint_fallback_cases(graph):
    cases=[]
    for reason in ('mono','stale_profile','non_tone','null_controller','layer1','missing6','missing8','missing_both'):
        state=fixture(graph,page=2)
        if reason=='mono':mode(state,57)
        elif reason=='stale_profile':mode(state,55)
        elif reason=='non_tone':put32(state,ACTUATOR,0x60de3ff8)
        elif reason=='null_controller':put32(state,0x6161b810,0)
        elif reason=='layer1':put32(state,JOB+4,1)
        else:remove_late(state,{'missing6':0x84,'missing8':0x24,'missing_both':4}[reason])
        if reason.startswith('missing'):
            reenter(state,graph.symbols['tone_paint_gate'],0,0,dict(PRESERVED,a0=RECEIVER,a1=JOB))
            stopped(state,state.run({0x60bbe8b6},limit=100),0x60bbe8b6)
            assert state.regs['a0']==RECEIVER and state.regs['a1']==JOB
            result=dict(stock_entry_preserved=True,late_code_unmapped=True)
        else:
            result=paint(state,graph)
            assert not result['rectangles']
        cases.append(dict(reason=reason,**result))
    return cases


def update_cases(graph):
    cases=[]
    for public,attached in ((54,False),(54,True),(57,False)):
        state=fixture(graph);mode(state,public)
        if attached:put32(state,RECEIVER+20,ROOT_OBJECT)
        reenter(state,graph.symbols['tone_update_gate'],0,0,dict(PRESERVED,a0=RECEIVER,a1=0x123456))
        stopped(state,state.run({0x60c58464},limit=100),0x60c58464)
        assert state.regs['a0']==RECEIVER and state.regs['a1']==0x123456
        state.return_from_model(0x1234)
        target=0x60bc07e5 if public==54 else CALLER+7
        result=resume(state,(target,CALLER+7),limit=20000)
        assert result['status']=='breakpoint' and state.regs['pc']==target,result
        if public==54:
            assert (state.regs['a0'],state.regs['d0'],state.regs['a1'])==(RECEIVER,1,0)
            result=resume(state,(CALLER+7,),limit=20000)
            if attached:
                assert result['status']=='memory_fault' and state.regs['pc']==0x60bca69c
                assert result['fault']['address']==0x61a8dfb4
                assert struct.unpack('<H',state.read(ROOT_OBJECT+1368,2))[0]==1
                assert struct.unpack('<4h',state.read(ROOT_OBJECT+1388,8))==(0,0,639,479),state.read(ROOT_OBJECT+1388,8).hex()
            else:returned(state,result)
        if not attached:
            assert state.regs['d0']==0x1234 and state.regs['sp']==INITIAL_SP
            assert all(state.regs[k]==v for k,v in PRESERVED.items())
        cases.append(dict(public=public,attached=attached,full_receiver_invalidation=public==54,
                          original_return_preserved=not attached,queue_boundary=attached,
                          models=['unchanged original tone update return']))
    return cases


def composed_cases(graph,folder):
    from penf_tone_editor_probe import reference_cases,input_cases,page_cases,reset_cases
    from penf_tone_integration_probe import build_adapter,cached_endpoint_cases
    from penf_tone_transport_probe import pipeline,entry_compatibility
    base=replace(graph.base,image=graph.image)
    editor=replace(graph.editor,image=graph.image)
    adapter=build_adapter(Path(folder)/'reference-adapter')
    return dict(native_reference=reference_cases(base,editor,adapter),
                body_inputs=input_cases(base,editor),pages=page_cases(base,editor),
                held_reset=reset_cases(base,editor),native_entry=entry_compatibility(base),
                cached_endpoints=cached_endpoint_cases(adapter,image=graph.image,
                    entry=graph.symbols['tone_native_builder']),
                neutral_inner_pipeline=pipeline(base,raw=(0,0,0,0,0)),
                changed_inner_pipeline=pipeline(base))


def full_reference_domain(graph):
    from penf_tone_editor_probe import CURVE
    from penf_tone_transport_probe import call
    state=editor_fixture(graph.base,replace(graph.editor,image=graph.image))
    minimum_delta=1023
    for count,controls in enumerate(product(range(-7,8),repeat=3),1):
        current(state,1,controls)
        call(state,graph.symbols['tone_reference'],0xf0,16,d0=967,a0=CURVE)
        curve=struct.unpack('<256H',state.read(CURVE,512))
        assert curve[0]==0 and curve[-1]==1023 and max(curve)<=1023
        delta=min(b-a for a,b in zip(curve,curve[1:]));assert delta>=0
        minimum_delta=min(minimum_delta,delta)
        expected=resolve(0,controls)
        assert state.regs['d0']==expected.pack() and curve==expected.apply(identity_lut())
        if count%225==0:print(json.dumps(dict(reference_cases=count)),flush=True)
    return dict(cases=count,minimum_adjacent_delta=minimum_delta,fixed_abscissae=[0,0.25,0.5,0.75,1],models=[])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--full-reference-domain',action='store_true')
    p.add_argument('--only',choices=('paint','filter','fallback','update','composed'))
    a=p.parse_args();g=build_graph(a.out/'candidate');result={}
    audits={'paint':lambda:paint_cases(g),'filter':lambda:filter_cases(g),
            'fallback':lambda:paint_fallback_cases(g),'update':lambda:update_cases(g),
            'composed':lambda:composed_cases(g,a.out)}
    for name,audit in audits.items():
        if a.only and name!=a.only:continue
        result[name]=audit()
        (a.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(contract=name,passed=True)),flush=True)
    if a.full_reference_domain:
        result['full_reference_domain']=full_reference_domain(g)
        (a.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
