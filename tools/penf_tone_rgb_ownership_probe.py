import struct
from dataclasses import replace
from penf_emulator import BASE, firmware
from penf_probe import ProbeState, CALLER
from penf_hsl_context_probe import reenter
from penf_code_space_load_probe import load
from penf_recovery_isolation_probe import without_ranges
from penf_tone_points import STORAGE_IDS
from penf_tone_transport_probe import settings, call, put32, u32, ACTIVE, BANKS, WORDS
from penf_tone_probe import INITIAL_SP


def storage_cases():
    image=firmware()
    ids=tuple(i for row in STORAGE_IDS for i in row)
    defaults={i:struct.unpack_from('<I',image,0x603c8bb0-BASE+i*4)[0] for i in ids}
    for index in range(54):
        mode,submode,pointer,count,_=struct.unpack_from('<HHIHH',image,0x603c891c-BASE+index*12)
        records=struct.iter_unpack('<HBB',image[pointer-BASE:pointer-BASE+count*4])
        assert sorted(r for r in records if r[0] in ids)==[(i,0,0) for i in sorted(ids)]
    reset_membership=[]
    for pointer,count,present in ((0x603ca598,25,False),(0x603cb010,478,False),
                                  (0x603ca5ca,1315,True),(0x603cba8c,855,True)):
        keys=struct.unpack_from('<%dH'%count,image,pointer-BASE)
        assert all((i in keys)==present for i in ids)
        reset_membership.append(dict(pointer=hex(pointer),count=count,all_present=present))
    s=ProbeState(0x602c6125,0xf0,20,bytes(256),{})
    settings(s)
    native_defaults=image[0x603c8bb0-BASE:0x603c8bb0-BASE+WORDS*4]
    active=native_defaults+struct.pack('<1274I',*(0xface0000|i for i in range(WORDS)))
    s.write(ACTIVE,active);s.write(BANKS,active*9)
    s.ram('native_initialized_runtime',0x615fc540,image[0x601ea800-BASE:0x601ea800-BASE+133664])
    for bank in range(9):
        expected=bytearray(s.read(ACTIVE,WORDS*8))
        for i in ids:
            value=0x7abc0000+i+bank*0x10000
            call(s,0x602f0710,0x80,8,d0=i,d1=1,a0=value)
            call(s,0x602f06e7,0x80,8,d0=i,d1=1)
            assert s.regs['d0']==value
            struct.pack_into('<I',expected,(WORDS+i)*4,value)
        assert s.read(ACTIVE,WORDS*8)==expected
        call(s,0x602f067a,0xc0,12,d0=bank)
        for i in ids:put32(s,ACTIVE+(WORDS+i)*4,0)
        call(s,0x602f063e,0xc0,12,d0=bank)
        assert s.read(ACTIVE,WORDS*8)==expected
    saved=s.read(BANKS,9*WORDS*8)
    result=call(s,0x602c6125,0xf0,20)
    assert s.read(BANKS,9*WORDS*8)==saved
    assert all(u32(s,ACTIVE+(WORDS+i)*4)==defaults[i] for i in ids)
    return dict(ids=ids,banks=9,filters=54,reset_membership=reset_membership,
                default_reset=result,modeled_native_functions=[])


def residency_cases(graph):
    stock=firmware()
    spans=((0x601cafc0,0x601cafe0),(0x60427c30,0x60427c70),
           (0x60427fc0,0x60428000),(0x6115b800,0x6115c800))
    assert all(stock[a-BASE:b-BASE]==b'\xff'*(b-a) for a,b in spans)
    reports=[]
    for section_id,low,high,source in ((1,0x60142800,0x601cb000,0x404c1800),
                                      (2,0x6022a800,0x60428000,0x405a9800),
                                      (8,0x61104000,0x6115c800,0x41483000)):
        s=ProbeState(0x600421e1,0,0,bytes(16),{})
        s.regions=[replace(r,data=graph.image) if r.name=='main' else r for r in s.regions]
        s.ram('selected',0x61c583fc,struct.pack('<I',section_id)+bytes(8))
        s.ram('section',low,b'\xa5'*(high-low),executable=True)
        s.ram('after_section',high,b'\x67'*64)
        section=dict(id=section_id,destination=hex(low),end_exclusive=hex(high),flash_source=hex(source))
        first=load(s,section,graph.image)
        assert s.read(high,64)==b'\x67'*64
        s.write(low,b'\x55'*(high-low))
        second=load(s,section,graph.image)
        assert s.read(high,64)==b'\x67'*64
        if section_id==2:
            before=s.read(0x60427c30,64)
            reenter(s,0x6006da8c,0xa0,12,dict(d0=2))
            result=s.run({CALLER+7},limit=1000)
            assert result['status']=='breakpoint' and s.regs['sp']==INITIAL_SP
            assert s.read(0x60427c30,64)==before
            absent=ProbeState(0x6006da8c,0xa0,12,bytes(16),dict(d0=2))
            absent.regions=without_ranges(absent.regions,[(0x60427c30,0x60427c70)])
            absent.regs=dict(pc=CALLER,sp=INITIAL_SP,psw=0,d0=2)
            result=absent.run({CALLER+7},limit=1000)
            assert result['status']=='breakpoint' and absent.regs['sp']==INITIAL_SP
        if section_id==8:
            reenter(s,0x60042123,0xe0,44,{})
            models=[]
            for _ in range(8):
                result=s.run({CALLER+7,0x60069138,0x6007fa6a},limit=1000)
                if s.regs['pc']==CALLER+7:break
                assert result['status']=='breakpoint'
                models.append(hex(s.regs['pc']));s.return_from_model(0)
            assert s.regs['pc']==CALLER+7 and s.regs['sp']==INITIAL_SP
            assert s.read(0xa1c58404,1)==b'\x80'
            assert s.read(0xa1c583fc,4)==bytes(4)
            assert s.read(high,64)==b'\x67'*64
        reports.append(dict(section=section_id,first_load=first,reload=second))
    return dict(sections=reports,limits='Storage/event/cache service models; no physical cache or complete runtime/DMA ownership proof.')
