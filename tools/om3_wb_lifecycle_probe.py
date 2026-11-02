#!/usr/bin/env python3
"""Native WB interrupted-record, switching-footprint and late-read probes.

No camera access. Torn record states are injected into emulator RAM; this is
not a simulation of physical NAND power loss. Capture probes enter bounded
native slices with an explicit synthetic destination, not a complete shutter.
"""
import argparse,json,os,random,shutil,tempfile
from pathlib import Path
import om3_wb_emulator_probe as base

TOKENS="""      if(tok.startsWith('WBDRIVE:')) {
        const [,id,v]=tok.split(':').map(Number);s.begin(tok);
        if(!([901,1578,1632].includes(id)||(id>=1580&&id<=1605)))throw new Error('WB id');
        s.lab.call(0x50ac91be,{d0:id,d1:v,a0:1},null,[0xf0,20],500000);s.settle(tok);
        return s.end(tok,'get',[],[],{get:{value:1}});
      }
      if(tok.startsWith('WBWORDS:')) {
        const words=JSON.parse(tok.slice(8));s.begin(tok);
        for(let i=0;i<4;i++)s.lab.call(0x503f87eb,{d0:916+i,d1:1,a0:words[i]},null,[0x80,8],200000);
        return s.end(tok,'get',[],[],{get:{value:1}});
      }
      if(tok==='WBALTALL') {
        s.begin(tok);const words=[];
        for(let sid=0;sid<2256;sid++)words.push(s.lab.call(0x503f87c2,{d0:sid,d1:1},null,[0x80,8],200000).d0>>>0);
        return s.end(tok,'get',[],[],{get:{words}});
      }
      if(tok.startsWith('WBTINTCOPY:')) {
        s.begin(tok);const kelvin=Number(tok.split(':')[1]),l=s.lab,dest=0xa3fe0000;
        const data=new Uint8Array(40000).fill(0xa5);new DataView(data.buffer).setUint16(37642,kelvin,true);l.sim.write(dest,data);
        l.hook(0x60457c44-0x10021020,(h,r)=>{const ptr=new Uint8Array(4);new DataView(ptr.buffer).setUint32(0,dest,true);h.sim.write(r.sp+8,ptr);h.passthrough(r);},'WB-processing-entry');
        l.hook(0x60457c80-0x10021020,(h,r)=>h.return_here(r,[0xf0,32]),'WB-processing-stop');
        try {l.call(0x60457c44-0x10021020,{},null,[0xf0,32],200000);}
        finally {l.hooks.delete(0x60457c44);l.hooks.delete(0x60457c80);}
        const ab=l.sim.read(dest+37734,4),k=l.sim.read(dest+5422,2);
        return s.end(tok,'get',[],[],{get:{ab:ab[0]|ab[1]<<8,gm:ab[2]|ab[3]<<8,kelvin:k[0]|k[1]<<8}});
      }
"""

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator',required=True,type=Path)
    parser.add_argument('--node',default=shutil.which('node'))
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--library-path',type=Path)
    parser.add_argument('--steps',type=int,default=200)
    args=parser.parse_args()
    if not 1<=args.steps<=10000:parser.error('--steps must be 1..10000')
    if args.library_path:os.environ['LD_LIBRARY_PATH']=str(args.library_path.resolve())
    base.NODE=str(Path(args.node).resolve());base.IMAGE=args.image.resolve()
    spec=json.loads((base.ROOT/'patches/hsl/om-3/patch.json').read_text())
    with tempfile.TemporaryDirectory(prefix='om3-wb-lifecycle-') as t:
        base.EMU=Path(t)/'emu-copy';base.prepare_copy(args.emulator.resolve(),base.EMU,base.IMAGE,spec)
        base.edit(base.EMU/'emu/src/lab/player.mjs',"      if (tok === 'WBSNAPSHOT')",TOKENS+"      if (tok === 'WBSNAPSHOT')")
        base.edit(base.EMU/'emu/src/lab/play.mjs',"  // H-G4SET: a group-4 input through the firmware's own producer", """  creative_probe(value) {
    this.begin(`creative raw ${value}`);
    for(let bit=0;bit<3;bit++)set_bit(this.images[4],0,bit,(value>>bit)&1);
    const image=this.images[4].slice();const [codes,decoded]=this.push_group(4);
    this.lab.sim.write(G4_IMAGE,image);this.images[4].set(image);
    return this.end(`creative raw ${value}`,'switch',[],[],{creative_raw:value,codes,decoded});
  }
  // H-G4SET: a group-4 input through the firmware's own producer""")
        base.edit(base.EMU/'emu/src/lab/player.mjs',"      if (tok === 'WBSNAPSHOT')", "      if(tok.startsWith('WBCREATIVE:'))return s.creative_probe(Number(tok.split(':')[1]));\n      if (tok === 'WBSNAPSHOT')")

        s=base.Session(str(Path(t)/'nv.json'))
        def token(text):return s.inp({'type':'token','token':text})['get']
        def write(i,v):token(f'WBDRIVE:{i}:{v}')
        def wb():return tuple(s.setting(i) for i in (1578,1632,39,132))
        def check(expected):assert wb()==tuple(v&0xffffffff for v in expected),(wb(),expected)
        def pack(mode,k,ab,gm):
            tint=(ab&255)|((gm&255)<<8)
            return [mode,k,tint,mode^k^tint^0x57420101]
        try:
            s.ready()
            for i,v in [(1578,9),(1632,5400),(1592,1),(1605,-1)]:write(i,v)
            old=pack(9,5600,2,3);new=pack(6,6500,-2,-3)
            states=[old,old[:3]+[0],[new[0],old[1],old[2],0],[new[0],new[1],old[2],0],new[:3]+[0],new]
            for position,words in enumerate(states):
                write(901,54);token('WBWORDS:'+json.dumps(words))
                s.inp({'type':'control','op':'power','value':0});s.inp({'type':'control','op':'power','value':1})
                assert s.read(0xa031efd8,1)==b'\0'
                write(901,64)
                check((9,5600,2,3) if position==0 else (6,6500,-2,-3) if position==5 else (9,5400,1,-1))
                print(json.dumps({'case':'interrupted-record','completed_writes':position,'passed':True}),flush=True)
            # Reinitialise all four records before the deterministic switching test.
            modes=[54,55,56,64];configs=[(9,4000+i*1000,i-2,2-i) for i in range(4)]
            for mode,config in zip(modes,configs):
                write(901,mode)
                for sid,val in zip([1578,1632,1592,1605],config):write(sid,val)
            before=token('WBALTALL')['words'];rng=random.Random(1471100)
            for step in range(args.steps):
                index=rng.randrange(4);write(901,modes[index]);check(configs[index])
                assert s.read(0xa031efd8,1)==b'\0'
            after=token('WBALTALL')['words']
            outside=[i for i,(a,b) in enumerate(zip(before,after)) if a!=b and not 904<=i<=923]
            assert not outside,outside
            print(json.dumps({'case':'switching-footprint','steps':args.steps,'changed_outside_wb_part1':outside,'passed':True}),flush=True)
            switches=[]
            for raw in range(8):
                record=s.inp({'type':'token','token':f'WBCREATIVE:{raw}'})
                mode=s.setting(901)
                if mode in modes:check(configs[modes.index(mode)])
                switches.append({'raw':raw,'mode':mode})
            print(json.dumps({'case':'creative-switch-inputs','observations':switches,'profile_transition_observed':len({item['mode'] for item in switches})>1,'scope':'input attempt only; no transition means this route remains unqualified'}),flush=True)
            # Earlier capture Kelvin with live tint from a subsequently selected profile.
            write(901,54);capture=token('WBSNAPSHOT')['bytes'];captured_kelvin=capture[38]|capture[39]<<8
            write(901,55);late=token(f'WBTINTCOPY:{captured_kelvin}')
            assert late=={'kelvin':4000,'ab':65535,'gm':1},late
            print(json.dumps({'case':'native-processing-late-read','captured_kelvin':captured_kelvin,'processing':late,'observed':'earlier Kelvin combined with later profile tint','scope':'controlled native slice; live job timing not established'}),flush=True)
        finally:s.stop()

if __name__=='__main__':main()
