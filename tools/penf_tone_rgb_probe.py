import struct
from dataclasses import replace

from penf_probe import CALLER
from penf_hsl_context_probe import reenter, CACHE, LOCKS
from penf_diagnostic_lifetime_probe import helpers
from penf_tone_points import FivePoints, STORAGE_IDS
from penf_tone_probe import INITIAL_SP, PRESERVED, _check_guards
from penf_tone_transport_probe import (setup, settings, call, put32, u32, owner,
                                     acquisition, stopped, ACTIVE, WORDS)
from penf_tone_integration_probe import JOB, REQUEST, CONTEXT, OUTPUT, LUT
from penf_tone_editor_probe import fixture, actuator, mode, current, ACTUATOR, SERVICE

NEUTRAL = FivePoints().pack()
CURVES = (FivePoints(), FivePoints((64,320,544,704,960)),
          FivePoints((16,208,480,800,1023)), FivePoints((32,288,576,816,992)))


def channel_words(s, rows):
    for ids, words in zip(STORAGE_IDS, rows):
        for setting, word in zip(ids, words):
            call(s, 0x602f0710, 0x80, 8, d0=setting, d1=1, a0=word)


def snapshot_cases(candidate):
    s = setup(candidate)
    settings(s)
    rows = tuple(tuple(CURVES[(profile + channel) % 4].pack() for channel in range(4))
                 for profile in range(3))
    channel_words(s, rows)
    call(s, candidate.symbols['hl_publish'])
    assert s.read(candidate.symbols['tone_source'], 48) == struct.pack('<12I', *(w for row in rows for w in row))
    for slot in range(45):
        profile = slot % 3
        address = owner(s, slot, profile + 1, alias=bool(slot % 2))
        acquisition(s, address, slot >= 40)
        expected = struct.pack('<4I', *rows[profile])
        assert s.read(candidate.symbols['tone_rows'] + slot * 16, 16) == expected
        s.write(candidate.symbols['tone_source'], bytes(48))
        call(s, candidate.symbols['hl_owner_to_job'], a0=address, a2=JOB + 14920)
        assert s.read(JOB + 14944, 16) == expected
        call(s, candidate.symbols['hl_publish'])
        address = owner(s, slot, 0)
        acquisition(s, address, slot >= 40)
        call(s, candidate.symbols['hl_owner_to_job'], a0=address, a2=JOB + 14920)
        assert s.read(JOB + 14944, 16) == bytes(16)
    return dict(owners=45, channels=4, acquired_snapshot_immutable=True, reuse_clears_all_channels=True)


def manager_cases(graph):
    s = fixture(graph.base, replace(graph.editor, image=graph.image))
    channel_words(s, ((NEUTRAL,)*4,)*3)
    reports = []
    for profile, ids in enumerate(STORAGE_IDS):
        for channel, setting in enumerate(ids):
            word = CURVES[1].pack()
            actuator(s, (profile+1)%3+1, ((channel+1)%4)*3+2)
            before = s.read(ACTIVE, WORDS*8)
            high = ids[0]
            reenter(s, graph.symbols['tone_manager_gate'], 0xe0, 16,
                    dict(PRESERVED, a0=0x19102000, d0=high, d1=word+(channel<<28)))
            stop = (0x602c1067,0x602c1080,0x602c1099)[profile]
            stopped(s, s.run({stop},limit=100000), stop)
            expected = bytearray(before)
            struct.pack_into('<I',expected,(WORDS+setting)*4,word)
            assert s.read(ACTIVE,WORDS*8)==expected
            assert s.regs['d2']==high
            reports.append((profile+1,channel,setting))
    return dict(requests=reports, async_cursor_independent=True)


def editor_cases(graph):
    s = fixture(graph.base, replace(graph.editor,image=graph.image))
    words = tuple(curve.pack() for curve in CURVES)
    channel_words(s,(words,)*3)
    count = 0
    for profile, ids in enumerate(STORAGE_IDS,1):
        mode(s,53+profile)
        current(s,profile,(0,0,0))
        for channel in range(4):
            for page in range(3):
                encoded = channel*3+page
                actuator(s,profile,encoded)
                call(s,0x60c878ec,0xf0,28,a0=ACTUATOR)
                assert u32(s,ACTUATOR+164)==ids[0]+(1 if page==1 else 2)
                assert struct.unpack('<H',s.read(ACTUATOR+194,2))[0]==encoded
                reenter(s,0x60c87245,0,0,dict(PRESERVED,a0=ACTUATOR,d1=0))
                stopped(s,s.run({0x607363b3},limit=100000),0x607363b3)
                axis=(3,2,4)[page]
                expected=CURVES[channel].edit(axis,-1).pack()+(channel<<28)
                assert (s.regs['d0'],s.regs['a1'])==(ids[0],expected),(profile,channel,page,s.regs['a1'],expected)
                put32(s,INITIAL_SP+4,ACTUATOR);put32(s,INITIAL_SP+20,53+profile)
                s.regs=dict(PRESERVED,pc=0x60c87670,sp=INITIAL_SP,d0=0,d1=0,a0=0,a1=0,a3=0,psw=0)
                stopped(s,s.run({0x60c879c8},limit=100000),0x60c879c8)
                assert struct.unpack('<H',s.read(ACTUATOR+194,2))[0]==channel*3+(page+1)%3
                count+=1
    return dict(states=count, input_channels_explicit=True, info_retains_channel=True)


def gamma_state(candidate, words, *, stage=0x100, creative=0, retained=False):
    s=setup(candidate,processing=True,endpoint_word=NEUTRAL,custom=False)
    s.write(JOB+14948,struct.pack('<3I',*words))
    s.write(REQUEST+12,struct.pack('<H',stage))
    s.write(REQUEST+1071,bytes((creative,)))
    if retained:
        cache=0x1a070020
        s.ram('retained_gamma',cache,bytes(6000),aliases=False)
        put32(s,REQUEST+924,cache)
        put32(s,CONTEXT+16,0x1a060020)
    helpers(s)
    return s


def run_gamma(s, candidate):
    before=s.read(REQUEST,1848)
    controls=u32(s,CONTEXT+56)
    reenter(s,0x604f8543,0xf0,40,dict(PRESERVED,a0=CONTEXT))
    result=s.run({CALLER+7},limit=500000)
    stopped(s,result,CALLER+7)
    assert s.regs['sp']==INITIAL_SP
    assert s.read(REQUEST,1848)==before
    assert u32(s,CONTEXT+56)==controls
    _check_guards(s,JOB,14960);_check_guards(s,OUTPUT,5212)
    pointers=struct.unpack('<2I',s.read(OUTPUT+1052,8))
    return tuple(tuple(struct.unpack('<256I',s.read(p,1024))) if p else None for p in pointers)


def expected_map(words, curves):
    lanes=[curve.apply(tuple((w>>(10*channel))&1023 for w in words))
           for channel,curve in enumerate(curves)]
    return tuple((word&0xc0000000)|lanes[0][i]|(lanes[1][i]<<10)|(lanes[2][i]<<20)
                 for i,word in enumerate(words))


def gamma_cases(candidate):
    reports=[]
    for stage,creative,selected in ((0x100,0,1),(0xa400,1,0),(0xa000,1,1)):
        baseline=gamma_state(replace(candidate,image=candidate.reference),(0,0,0),stage=stage,creative=creative)
        stock=run_gamma(baseline,candidate)
        s=gamma_state(candidate,(NEUTRAL,)*3,stage=stage,creative=creative,retained=True)
        native=run_gamma(s,candidate)
        assert native==stock
        pointers=struct.unpack('<3I',s.read(OUTPUT+4644,12))
        sources={p:s.read(p,512) for p in pointers}
        sequences=[(CURVES[1],CURVES[0],CURVES[0]),(CURVES[0],CURVES[2],CURVES[0]),
                   (CURVES[0],CURVES[0],CURVES[3]),CURVES[1:],(CURVES[0],)*3]
        for curves in sequences:
            s.write(JOB+14948,struct.pack('<3I',*(c.pack() for c in curves)))
            put32(s,CONTEXT+56,0)
            actual=run_gamma(s,candidate)
            expected=list(stock);expected[selected]=expected_map(stock[selected],curves)
            assert actual==tuple(expected),(stage,creative,selected)
            assert all(s.read(p,512)==value for p,value in sources.items())
        s.write(JOB+14948,struct.pack('<3I',0xffffffff,2000,0xa5dffc00))
        assert run_gamma(s,candidate)==stock
        reports.append(dict(stage=stage,creative=creative,selected=selected,all_256_words=True,rebuilds=len(sequences)+2))
    return reports


def upload_cases(candidate):
    reports=[]
    hardware=0x1a0a0020
    for stage,creative in ((0x100,0),(0xa400,1),(0xa000,1)):
        for hardware_bank in (0,1):
            s=gamma_state(candidate,tuple(c.pack() for c in CURVES[1:]),stage=stage,creative=creative,retained=True)
            put32(s,CONTEXT+56,0);put32(s,CONTEXT+100,0x40)
            tables=run_gamma(s,candidate)
            dirty=u32(s,CONTEXT+100)
            assert dirty&0x40
            put32(s,CONTEXT+52,17)
            s.write(CONTEXT+189,bytes((hardware_bank,)))
            s.ram('warm_gamma_cache',CACHE,struct.pack('<2I',*(17 if i==hardware_bank else 0 for i in range(2))))
            s.ram('gamma_hardware_submission',hardware,b'\xa5'*8192,aliases=False)
            reenter(s,0x604b58c4,0xf0,36,dict(PRESERVED,a0=hardware,a1=CONTEXT))
            models=[]
            for _ in range(5):
                result=s.run({CALLER+7}|set(LOCKS),limit=100000)
                pc=s.regs['pc']
                if pc==CALLER+7:break
                assert pc in LOCKS and s.regs['d0']==4,(result,hex(pc))
                models.append(hex(pc));s.return_from_model(0)
            stopped(s,result,CALLER+7)
            for gamma_bank,offset in ((0,3072),(1,1024)):
                expected=b'\xa5'*1024 if tables[gamma_bank] is None else struct.pack('<256I',*tables[gamma_bank])
                assert s.read(hardware+offset,1024)==expected
            assert models==['0x604fa0ca','0x604fa0ec']
            reports.append(dict(stage=stage,creative=creative,hardware_bank=hardware_bank,dirty=dirty,
                                cache='same tag',modeled_functions=models))
    return reports


def cycle_cases(graph):
    controller,event=0x19110000,0x19111000
    s=fixture(graph.base,replace(graph.editor,image=graph.image))
    s.ram('tone_controller',controller,struct.pack('<2I',ACTUATOR,0x19112000),aliases=False)
    s.ram('current_controller',0x6161b810,struct.pack('<I',controller))
    s.ram('current_screen',0x6161b81c,struct.pack('<H',0x13b8))
    s.ram('trash_event',event,b'\x02\x02',aliases=False)
    for address in (0x61618eb0,0x6161ad04,0x6161bf84):s.ram(hex(address),address,bytes(4))
    before=s.read(ACTIVE,WORDS*8)
    cases=[]
    for profile in (1,2,3):
        mode(s,53+profile)
        for channel in range(4):
            for page in range(3):
                actuator(s,profile,channel*3+page)
                s.write(ACTUATOR+100,struct.pack('<H',0x13b8));put32(s,0x6161bf84,9)
                reenter(s,graph.symbols['tone_cycle'],0xf0,40,dict(PRESERVED,a0=event))
                calls=[]
                for _ in range(3):
                    result=s.run({CALLER+7,0x60c84901,0x60d147e8},limit=100000)
                    if s.regs['pc']==CALLER+7:break
                    calls.append(s.regs['pc']);s.return_from_model(0)
                stopped(s,result,CALLER+7)
                assert s.regs['d0']==1 and calls==[0x60c84901,0x60d147e8]
                assert struct.unpack('<H',s.read(ACTUATOR+194,2))[0]==((channel+1)%4)*3+page
                assert u32(s,0x6161bf84)==0
                assert s.read(ACTIVE,WORDS*8)==before
                cases.append((profile,channel,page))
    for address in (0x61618eb0,0x6161ad04,ACTUATOR+16,ACTUATOR+44,ACTUATOR+200):
        actuator(s,3,11);s.write(ACTUATOR+100,struct.pack('<H',0x13b8))
        put32(s,address,1)
        call(s,graph.symbols['tone_cycle'],0xf0,40,a0=event)
        assert s.regs['d0']==0 and struct.unpack('<H',s.read(ACTUATOR+194,2))[0]==11
        put32(s,address,0)
    return dict(states=cases,setting_writes=0,equal_neutral_draw_requested=True,
                modeled_functions=['native viewer completion','native draw-request completion'])


def channel_display_cases(graph, folder):
    from penf_tone_viewer_probe import getter_adapter,footer_state,VIEWER
    from penf_tone_graph_probe import fixture as graph_fixture,paint,assert_geometry
    from PIL import Image, ImageDraw
    getter=getter_adapter(folder/'rgb-getter')
    rows=[]
    for channel in range(4):
        s=footer_state(graph,getter,page=channel*3,controls=(0,0,0))
        registers=dict(s.regs)
        channel_words(s,(tuple(c.pack() for c in CURVES),)*3)
        s.regs=registers
        result=s.run({0x60cf9bec},limit=100000)
        stopped(s,result,0x60cf9bec)
        label=s.read(VIEWER+26,66).decode('utf-16le').split('\0')[0]
        assert label.startswith(('ALL','R','G','B')[channel]+' '),label
        assert label.endswith('@A028@ DEL'),label
        s=graph_fixture(graph,page=channel*3,word=CURVES[channel].pack())
        channel_words(s,(tuple(c.pack() for c in CURVES),)*3)
        result=paint(s,graph)
        assert_geometry(result,s.graph_inputs)
        preview=Image.new('RGB',(640,480),'#161616')
        draw=ImageDraw.Draw(preview)
        draw.text((18,18),'Native graph requests; illustrative palette and footer font',fill='white')
        draw.text((18,38),'Synthetic fixture, not a camera capture',fill='white')
        draw.rectangle((348,107,610,373),outline='#888888')
        for rectangle in result['rectangles']:
            x,y,w,h=(rectangle[k] for k in ('x','y','width','height'))
            draw.rectangle((x,y,x+w-1,y+h-1),fill='#eeeeee')
        draw.text((100,440),label.replace('@A028@',' [INFO]'),fill='white')
        filename='channel-'+('ALL','R','G','B')[channel]+'.png'
        preview.save(folder/filename)
        rows.append(dict(channel=channel,label=label,render=filename,paint=result))
    return dict(channels=rows,footer_and_graph_native=True)


def unmap(s, holes):
    from penf_recovery_isolation_probe import without_ranges
    s.regions = [r for r in s.regions if not any(a <= r.address and r.address+len(r.data) <= b for a,b in holes)]
    s.regions = without_ranges(s.regions, holes)


def gamma_boundary_cases(candidate):
    reports=[]
    for kind in ('callback','parent','record','mode','empty_owner','unloaded'):
        states=[]
        for reference in (False,True):
            c=replace(candidate,image=candidate.reference) if reference else candidate
            s=gamma_state(c,tuple(c.pack() for c in CURVES[1:]))
            reenter(s,0x604f8543,0xf0,40,dict(PRESERVED,a0=CONTEXT))
            stopped(s,s.run({0x604f8588},limit=100000),0x604f8588)
            if kind=='callback':put32(s,REQUEST,0)
            elif kind=='parent':put32(s,REQUEST+1848,JOB+4)
            elif kind=='record':put32(s,REQUEST+4,REQUEST+1849)
            elif kind=='mode':s.write(REQUEST+8,struct.pack('<I',0x000c0000))
            elif kind=='empty_owner':s.write(JOB+14944,bytes(16))
            else:
                s.write(0x61c58404,b'\x04')
                unmap(s,[(0x6115b014,0x6115c800),(0xa115b014,0xa115c800)])
            if kind=='mode':
                stopped(s,s.run({0x604f6083},limit=100000),0x604f6083)
                states.append((s.regs['a0'],s.regs['sp'],tuple(s.regs[k] for k in PRESERVED),s.read(CONTEXT,192)))
                continue
            stopped(s,s.run({0x604f858d},limit=500000),0x604f858d)
            states.append((s.read(OUTPUT,5212),s.read(CONTEXT,192),s.regs['d0']))
        assert states[0]==states[1],kind
        reports.append(kind)
    s=gamma_state(candidate,tuple(c.pack() for c in CURVES[1:]))
    reenter(s,0x604f8543,0xf0,40,dict(PRESERVED,a0=CONTEXT))
    stopped(s,s.run({candidate.symbols['tone_rgb_after_native']},limit=100000),candidate.symbols['tone_rgb_after_native'])
    private=0x1a0b0020
    s.ram('foreign_gamma',private,b'\x3f'*1024,aliases=False)
    put32(s,OUTPUT+1056,private)
    stopped(s,s.run({CALLER+7},limit=500000),CALLER+7)
    assert s.read(private,1024)==b'\x3f'*1024
    samples=tuple(0xc0000000|(i*4)|((i*4)<<10)|((i*4)<<20) for i in range(256))
    s.write(private,struct.pack('<256I',*samples))
    call(s,candidate.symbols['tone_rgb_map'],0xf0,16,a0=private,d0=CURVES[1].pack(),d1=0)
    actual=struct.unpack('<256I',s.read(private,1024))
    assert actual==expected_map(samples,(CURVES[1],CURVES[0],CURVES[0]))
    return dict(stock_fallbacks=reports,scope="gamma builder return before other outer processing stages",mode_scope="native builder entry and argument ABI; mode-specific processing fixture not mapped",foreign_pointer_unmodified=True,reserved_bits_preserved=True)


def gamma_stack_case(candidate):
    from penf_tone_graph_probe import PeakState
    s=gamma_state(candidate,tuple(c.pack() for c in CURVES[1:]))
    s.__class__=PeakState;s.measure_stack=True;s.minimum_sp=INITIAL_SP
    run_gamma(s,candidate)
    peak=INITIAL_SP-s.minimum_sp
    assert peak<1024,peak
    return dict(peak_stack_bytes=peak,scope='Native ordinary outer builder with three nonneutral RGB curves; not full image-worker stack high water.')


def reset_and_reject_cases(graph):
    s=fixture(graph.base,replace(graph.editor,image=graph.image))
    channel_words(s,(tuple(c.pack() for c in CURVES),)*3)
    for profile,ids in enumerate(STORAGE_IDS,1):
        mode(s,53+profile)
        for channel in range(4):
            for page,axes in enumerate(((1,3),(2,),(0,4))):
                actuator(s,profile,channel*3+page)
                put32(s,INITIAL_SP+4,ACTUATOR);put32(s,INITIAL_SP+20,53+profile)
                s.regs=dict(PRESERVED,pc=0x60c875e4,sp=INITIAL_SP,d0=0,d1=0,a0=0,a1=0,a3=0,psw=0)
                stopped(s,s.run({0x607363b3},limit=100000),0x607363b3)
                expected=CURVES[channel]
                for axis in axes:expected=expected.edit(axis,0)
                assert (s.regs['d0'],s.regs['a1'])==(ids[0],expected.pack()+(channel<<28))
    before=s.read(ACTIVE,WORDS*8)
    for channel in range(4):
        for loaded in (True,False):
            s.write(0x61c58404,bytes((0xa4 if loaded else 4,)))
            payload=(0xbf000000 if loaded else NEUTRAL)+(channel<<28)
            call(s,graph.symbols['tone_manager_gate'],0xe0,16,a0=0x19102000,d0=967,d1=payload)
            assert s.regs['d0']==0 and s.read(ACTIVE,WORDS*8)==before
    return dict(reset_states=36,malformed_or_unloaded_requests=8)


def dispatcher_cases(graph):
    controller,event=0x19110000,0x19111000
    reports=[]
    for event_id,loaded,modal in ((0x9016,True,False),(0x9004,True,False),
                                  (0x9016,False,False),(0x9016,True,True)):
        pairs=[]
        for reference in ((False,) if event_id==0x9016 and loaded and not modal else (False,True)):
            image=graph.base.reference if reference else graph.image
            s=fixture(graph.base,replace(graph.editor,image=image))
            actuator(s,1,0);mode(s,54)
            s.write(ACTUATOR+100,struct.pack('<H',0x13b8))
            s.ram('tone_controller',controller,struct.pack('<2I',ACTUATOR,0x19112000),aliases=False)
            s.ram('current_controller',0x6161b810,struct.pack('<I',controller))
            s.ram('current_screen',0x6161b81c,struct.pack('<H',0x13b8))
            s.ram('fsm_event',event,b'\x02\x02',aliases=False)
            for address in (0x61618eb0,0x6161ad04,0x6161bf84):s.ram(hex(address),address,bytes(4))
            if modal:put32(s,0x61618eb0,1)
            if not loaded:
                s.write(0x61c58404,b'\x04')
                unmap(s,[(0x6115b014,0x6115c800),(0xa115b014,0xa115c800)])
            reenter(s,0x60bcba4d,0,0,dict(PRESERVED,a0=event,d0=event_id,d1=0x1234,a1=0x4321))
            calls=[]
            for _ in range(4):
                result=s.run({CALLER+7,0x60bcbbc7,0x60c84901,0x60d147e8},limit=100000)
                if s.regs['pc'] in (CALLER+7,0x60bcbbc7):break
                calls.append(s.regs['pc']);s.return_from_model(0)
            target=CALLER+7 if event_id==0x9016 and loaded and not modal else 0x60bcbbc7
            stopped(s,result,target)
            if target==CALLER+7:
                assert s.regs['sp']==INITIAL_SP and s.regs['d0']==0
                assert all(s.regs[k]==v for k,v in PRESERVED.items())
                assert calls==[0x60c84901,0x60d147e8]
                assert struct.unpack('<H',s.read(ACTUATOR+194,2))[0]==3
            else:
                pairs.append((dict(s.regs),s.read(s.regs['sp'],32)))
        if pairs:assert pairs[0]==pairs[1]
        reports.append(dict(event=event_id,loaded=loaded,modal=modal))
    return reports


def unloaded_selection_cases(graph):
    count=0
    for mask in (4,0x24,0x84):
        s=fixture(graph.base,replace(graph.editor,image=graph.image))
        mode(s,54)
        s.write(0x61c58404,bytes((mask,)))
        holes=[]
        if not mask&0x20:holes.append((0x610f1e54,0x610f2000))
        if not mask&0x80:holes.append((0x6115b014,0x6115c800))
        holes += [(a+0x40000000,b+0x40000000) for a,b in holes]
        unmap(s,holes)
        before=s.read(ACTIVE,WORDS*8)
        for state in (3,5,8,11,12):
            actuator(s,1,state)
            reenter(s,0x60c878ec,0xf0,28,dict(PRESERVED,a0=ACTUATOR))
            stopped(s,s.run({0x60c878f2},limit=100000),0x60c878f2)
            assert s.read(ACTUATOR+194,2)==bytes(2)
            assert s.regs['a3']==ACTUATOR+188
            actuator(s,1,state)
            put32(s,INITIAL_SP+4,ACTUATOR);put32(s,INITIAL_SP+20,54)
            s.regs=dict(PRESERVED,pc=0x60c87670,sp=INITIAL_SP,d0=0,d1=0,a0=0,a1=0,a3=0,psw=0)
            stopped(s,s.run({0x60c878f2},limit=100000),0x60c878f2)
            assert struct.unpack('<H',s.read(ACTUATOR+194,2))[0]<3
            actuator(s,1,state)
            put32(s,INITIAL_SP+4,ACTUATOR)
            s.regs=dict(PRESERVED,pc=0x60c875e4,sp=INITIAL_SP,d0=0,d1=0,a0=0,a1=0,a3=0,psw=0)
            stopped(s,s.run({0x60c878dd},limit=100000),0x60c878dd)
            assert s.read(ACTIVE,WORDS*8)==before
            count+=1
    return dict(states=count,late_memory_unmapped=True,native_table_indices_bounded=True)
