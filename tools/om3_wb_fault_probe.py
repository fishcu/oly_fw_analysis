#!/usr/bin/env python3
"""Bounded OM-3 WB ABI, loader-failure and interrupted-record experiments.

Runs only in a private OM-Emu copy; no camera access. Native commit completion,
section storage and diagnostics are explicit stand-ins in these fault cases.
"""
import argparse,json,os,shutil,tempfile
from pathlib import Path
import om3_wb_emulator_probe as base

TOKEN = """      if (tok.startsWith('HSLABI:')) {
        s.begin(tok);const kind=tok.split(':')[1], l=s.lab, hooks=[];
        const install=(pc,fn)=>{l.hook(pc-0x10021020,fn,'HSL-ABI-model');hooks.push(pc);};
        let result, expected;
        try {
          if(kind==='display') {
            l.sim.write(0xa031efa0,new Uint8Array([0]));
            install(0x60b1d401,(h,r)=>h.return_here(r,[0,4]));
            result=l.call(0x60b1d363-0x10021020,{d0:123,d1:0x24681357,a0:0x12345678,a1:0x87654321},null,[0,4],500000);
            expected={d0:5,d1:0x24681357,a0:0x12345678,a1:0x87654321};
          } else if(kind==='delete') {
            const obj=0xa3ffb100;l.sim.write(obj,new Uint8Array([4,24]));
            for(const pc of [0x6125becc,0x6125c7a7]) install(pc,(h,r)=>h.return_here(r,[0,4]));
            const entry=l.sim.u32(0x615d0b64);
            result=l.call(entry-0x10021020,{d0:0x9016,d1:0x24681357,a0:obj,a1:0x87654321},null,[0,4],500000);
            expected={d0:0x9016,d1:0x24681357,a0:obj,a1:0x87654321};
          } else if(kind==='builder') {
            const patch=0x60518615, raw=l.sim.read(patch,5);
            if(raw[0]!==0xdc)throw new Error('builder jump encoding');
            const body=(patch+new DataView(raw.buffer,raw.byteOffset).getInt32(1,true))>>>0;
            const call=body+22, b=l.sim.read(call,5);
            if(b[0]!==0xcd)throw new Error('builder helper encoding');
            const helper=(call+new DataView(b.buffer,b.byteOffset).getInt16(1,true))>>>0;
            install(0x60518381,(h,r)=>h.finish(r,{d0:0x13579bdf,d1:0x24681357,a0:0x12345678,a1:0x87654321}));
            install(helper,(h,r)=>h.return_here({...r,d0:3,d1:4,a0:5,a1:6},[0xf0,24]));
            install(0x6051861a,(h,r)=>h.return_here(r,[0,4]));
            result=l.call(patch-0x10021020,{},null,[0,4],500000);
            expected={d0:0x13579bdf,d1:0x24681357,a0:0x12345678,a1:0x87654321};
          } else throw new Error('HSL ABI case');
          const got=Object.fromEntries(Object.keys(expected).map(k=>[k,result[k]>>>0]));
          return s.end(tok,'get',[],[],{get:{got,expected}});
        } finally {for(const pc of hooks)l.hooks.delete(pc);}
      }
      if (tok.startsWith('WBABI:')) {
        s.begin(tok);const id=Number(tok.split(':')[1]);const entry=0x503d0e86;
        s.lab.hook(entry,(l,r)=>l.return_here({...r,d0:0x13579bdf},[0xf0,20]),'WB-original-return-model');
        let result;
        try {result=s.lab.call(0x503d0e81,{d0:id,d1:9,a0:0x12345678,a1:0x87654321},null,[0xf0,20],500000);}
        finally {s.lab.hooks.delete(0x603f1ea6);}
        return s.end(tok,'get',[],[],{get:{value:result.d0>>>0}});
      }
      if (tok.startsWith('WBLOAD:')) {
        s.begin(tok);const mode=tok.split(':')[1];
        const l=s.lab;const expected=l.image.subarray(0x60a8f100-0x60021020,0x60a8f100-0x60021020+WB_SIZE);
        l.wbFault=mode;
        const poison=mode==='bitflip' ? expected.slice() : new Uint8Array(WB_SIZE).fill(0xcb);
        if(mode==='bitflip')poison[poison.length-1]^=1;
        l.sim.write(0xa0a8f100,poison);
        const bits=l.sim.u32(0xa32de590);const b=new Uint8Array(4);new DataView(b.buffer).setUint32(0,['cached','bitflip'].includes(mode) ? bits|8 : bits&~8,true);l.sim.write(0xa32de590,b);
        let result,loadedAfter;
        try {result=l.call(0x50ac91be,{d0:1578,d1:9,a0:1},null,[0xf0,20],500000);loadedAfter=l.sim.u32(0xa32de590);}
        finally {l.wbFault=null;l.sim.write(0xa0a8f100,expected);l.sim.write(0xa32de590,b);}
        return s.end(tok,'get',[],[],{get:{value:result.d0>>>0,loadedAfter}});
      }
"""

def install_faults(emu,spec):
    size=next(r['bytes'] for r in spec['ranges'] if r['name']=='wb_extension')
    p=emu/'emu/src/lab/player.mjs'
    base.edit(p,"      if (tok === 'WBSNAPSHOT')",TOKEN.replace('WB_SIZE',str(size))+"      if (tok === 'WBSNAPSHOT')")
    # Both storage hooks can serve a load, depending on the bring-up stage.
    for name,receiver in [('menu.mjs','l'),('storage.mjs','h')]:
        p=emu/'emu/src/lab'/name
        anchor=f"{receiver}.sim.write(r.a0,{receiver}.image.subarray(0x60828000-0x60021020,0x60a8f800-0x60021020));"
        inject=f"""if({receiver}.wbFault) {{
          if({receiver}.wbFault==='partial') {receiver}.sim.write(0xa0a8f100,{receiver}.image.subarray(0x60a8f100-0x60021020,0x60a8f100-0x60021020+16));
          {receiver}.finish(r,{{d0:1}});return;
        }}
        """
        base.edit(p,anchor,inject+anchor)
    p=emu/'emu/src/lab/menu.mjs'
    base.edit(p,'    this.install_observers();',"    this.hook(0x50002f60,(l,r)=>l.finish(r,{d0:0}),'WB-loader-diagnostic-model');\n    this.install_observers();")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator',required=True,type=Path)
    parser.add_argument('--node',default=shutil.which('node'))
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--library-path',type=Path)
    parser.add_argument('--case',action='append',help='Run selected named case(s) only')
    args=parser.parse_args()
    if args.library_path:os.environ['LD_LIBRARY_PATH']=str(args.library_path.resolve())
    base.NODE=str(Path(args.node).resolve());base.IMAGE=args.image.resolve()
    spec=json.loads((base.ROOT/'patches/hsl/om-3/patch.json').read_text())
    with tempfile.TemporaryDirectory(prefix='om3-wb-fault-') as t:
        base.EMU=Path(t)/'emu-copy';base.prepare_copy(args.emulator.resolve(),base.EMU,base.IMAGE,spec)
        install_faults(base.EMU,spec)
        results=[]
        for token in args.case or ['WBABI:1578','WBABI:261','HSLABI:display','HSLABI:delete','HSLABI:builder','WBLOAD:fail','WBLOAD:partial','WBLOAD:cached','WBLOAD:bitflip']:
            session=base.Session(str(Path(t)/(token.replace(':','-')+'.json')))
            try:
                session.ready();out=session.inp({'type':'token','token':token})['get']
                if token.startswith('WBABI:'):assert out['value']==0x13579bdf,out
                if token.startswith('HSLABI:'):assert out['got']==out['expected'],out
                if token.startswith('WBLOAD:'):assert not out['loadedAfter']&8,out
                results.append({'case':token,'passed':True})
            except Exception as error:
                results.append({'case':token,'passed':False,'error':str(error)})
            finally:session.stop()
            print(json.dumps(results[-1]),flush=True)
        if not all(r['passed'] for r in results):raise SystemExit(1)

if __name__=='__main__':main()
