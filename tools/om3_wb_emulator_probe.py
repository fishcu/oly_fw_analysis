#!/usr/bin/env python3
"""Exercise the combined OM-3 WB/HSL image in a temporary copy of OM-Emu.

Requires an OM-Emu checkout with the E147 stock main/resources unpacked and
Node >=26. The supplied checkout is read only; source modifications, test NVRAM,
and the exact section-4 storage stand-in live in a private temporary directory.
This is a native GUI/settings integration test, not an ISP or camera test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def edit(path,old,new):
    source=path.read_text()
    if old not in source:raise RuntimeError(f'Unsupported OM-Emu source: {path.name}')
    path.write_text(source.replace(old,new,1))

def audit_layout(image):
    """Bounded native table/placement audit, independent of the recall algorithm."""
    data=image.read_bytes()
    def read(address,size):return data[address-0x60021020:address-0x60021020+size]
    for index in range(22):
        group,variant,table,count=struct.unpack('<HHII',read(0x605f6c7c+12*index,12))
        assert group and 0<count<3000
        entries=[struct.unpack('<HBB',read(table+4*i,4)) for i in range(count)]
        target=[row for row in entries if 904<=row[0]<=923]
        assert sorted(row[0] for row in target)==list(range(904,924))
        assert all(row[1]==0 for row in target)
    assert struct.unpack('<HHII',read(0x605f6c7c+22*12,12))[0]==0
    assert struct.unpack('<III',read(0x60029b28+3*12,12))==(0x60828000,0x50807000,0)
    assert 0x6031e920+1524==0x6031ef14
    spec=json.loads((ROOT/'patches/hsl/om-3/patch.json').read_text())
    regions={r['name']:r for r in spec['ranges']}
    assert int(regions['wb_loader']['address'],16)==0x6031ef14
    assert 0x6031ef14+regions['wb_loader']['bytes']<=0x6031efa0
    assert int(regions['wb_extension']['address'],16)==0x60a8f100
    size=regions['wb_extension']['bytes']
    assert size%4==0 and 0x60a8f100+size<=0x60a8f800
    import re
    linker=(ROOT/'patches/hsl/om-3/wb.ld').read_text()
    words=int(re.search(r'wb_code_words = (\d+);',linker)[1])
    expected=int(re.search(r'wb_code_xor = (0x[0-9a-f]+);',linker)[1],16)
    total=0
    for word in struct.unpack('<'+str(size//4)+'I',read(0x60a8f100,size)):total^=word
    assert words==size//4 and total==expected
    print('PASS 22 native mode tables select part 0 for WB extension IDs 904..923; code stays within audited loaded tails',flush=True)

def prepare_copy(source,dest,image,spec):
    shutil.copytree(source/'emu',dest/'emu',ignore=shutil.ignore_patterns('node_modules','.cache'))
    (dest/'unpacked').symlink_to((source/'unpacked').resolve(),target_is_directory=True)
    patch=spec['components']['0x100']
    expected=patch['after_sha256']
    if hashlib.sha256(image.read_bytes()).hexdigest()!=expected:raise ValueError('Image is not the recorded OM-3 WB/HSL build')
    audit_layout(image)
    ranges=[(int(x['address'],16)-0x60021020,x['bytes']) for x in spec['ranges']]
    old='export function loadImage() { return image ??= expandImage(checkImage(readBytes(ORIGINAL))); }'
    new="""export function loadImage() {
      if (image) return image;
      const stock=checkImage(readBytes(ORIGINAL));
      const candidate=readBytes(process.env.OM3_WB_PROBE_IMAGE);
      if (MODEL_INFO.name!=='OM-3' || sha256(candidate)!=='EXPECTED' || candidate.length!==stock.length) throw new Error('WB probe image mismatch');
      const ranges=RANGES;
      for (let i=0;i<stock.length;i++) if(candidate[i]!==stock[i] && !ranges.some(([s,n])=>i>=s && i<s+n)) throw new Error('Unexpected WB image edit');
      return image=expandImage(candidate);
    }""".replace('EXPECTED',expected).replace('RANGES',json.dumps(ranges))
    edit(dest/'emu/checks/lib/env.mjs',old,new)
    menu=dest/'emu/src/lab/menu.mjs'
    storage_model="""    // Probe-only successful read of this exact firmware section from the pinned image.
    this.hook(0x500022b1,(l,r)=>{
      if(r.a0!==0xa0828000 || r.a1!==0x50807000 || r.d0!==0x267800 || r.d1!==0x10200) throw new Error('Unexpected section storage request');
      l.sim.write(r.a0,l.image.subarray(0x60828000-0x60021020,0x60a8f800-0x60021020));l.finish(r,{d0:0});
    },'S-WB-SECTION4-STORAGE');
"""
    edit(menu,'    this.install_observers();',storage_model+'    this.install_observers();')
    old="    const wantPrints = REGISTRY_PRINTS.map((p) => (loaded?.has(p[0]) ? p.replace('lD.', 'lR.') : p));"
    new="    const wantPrints = REGISTRY_PRINTS.map((p) => (loaded?.has(p[0]) || (p[0] === 'B' && saved?.scpu && reg.prints.includes('BlR.')) ? p.replace('lD.', 'lR.') : p));"
    edit(menu,old,new)
    edit(dest/'emu/src/lab/storage.mjs','  _nand(h, r) {',"""  _nand(h, r) {
    if(r.a0===0xa0828000 && r.a1===0x50807000 && r.d0===0x267800 && r.d1===0x10200){
      h.sim.write(r.a0,h.image.subarray(0x60828000-0x60021020,0x60a8f800-0x60021020));h.finish(r,{d0:0});return;
    }
""")
    edit(dest/'emu/src/dev/vsccompose.mjs',"      if (planc !== 0x100) {", "      if(p===P_IMG2 && planc===0x1100) return PLANE_NOT_DRAWN; // no ARGB/ISP emulation\n      if (planc !== 0x100) {")
    player=dest/'emu/src/lab/player.mjs'
    tokens="""      if (tok === 'WBSNAPSHOT') {
        s.begin(tok);
        // Execute the stock compact WB copy slice against the live native DB.
        // This scratch destination belongs only to this emulator experiment.
        const dest=0xa3ffb000, start=0x5046669a, stop=0x50466716;
        s.lab.sim.write(dest,new Uint8Array(64).fill(0xa5));
        s.lab.hook(start,(l,r)=>{const p=new Uint8Array(4);new DataView(p.buffer).setUint32(0,dest,true);l.sim.write(r.sp+4,p);l.passthrough(r);},'WB-copy-entry');
        s.lab.hook(stop,(l,r)=>l.return_here(r,[0xf0,28]),'WB-copy-stop');
        try {s.lab.call(start,{},null,[0xf0,28],200000);}
        finally {s.lab.hooks.delete(0x604876ba);s.lab.hooks.delete(0x60487736);}
        return s.end(tok,'get',[],[],{get:{bytes:[...s.lab.sim.read(dest,64)]}});
      }
      if (tok.startsWith('SETGET:') || tok.startsWith('ALTGET:')) {
        const sid=Number(tok.split(':')[1]);s.begin(tok);
        const r=tok.startsWith('SETGET:') ? s.lab.call(0x503cf37d,{d0:sid},null,[0,4],200000) : s.lab.call(0x503f87c2,{d0:sid,d1:1},null,[0x80,8],200000);
        s.settle(tok);return s.end(tok,'get',[],[],{get:{value:r.d0>>>0}});
      }
"""
    edit(player,"      if (tok.startsWith('EV:') || tok.startsWith('SET:')", tokens+"      if (tok.startsWith('EV:') || tok.startsWith('SET:')")

def cellv(h,l): vv=((l&15)<<4)|(h&15); return 0x48310000|((vv^255)<<8)|vv
class Session:
 def __init__(s,nvram):
  node=NODE; player=EMU/'emu/bin/play.mjs'
  env=dict(os.environ, OM_EMU_NVRAM=nvram, OM3_WB_PROBE_IMAGE=str(IMAGE))
  s.proc=subprocess.Popen([str(node),str(player),'--model','E147','--no-browser','--debug-api','--start','menu','--tab','1,2,1'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
  url=None; startup=[]
  for line in s.proc.stdout:
   startup.append(line.rstrip())
   if line.startswith('play: '): url=line.strip()[6:]; break
  if not url: raise RuntimeError('player did not provide URL: '+str(startup[-20:]))
  s.output=[]
  threading.Thread(target=lambda: [s.output.append(line.rstrip()) for line in s.proc.stdout],daemon=True).start()
  s.base=url.split('/?',1)[0]; s.token=url.split('?t=',1)[1]
 def post(s,path,data):
  req=urllib.request.Request(s.base+path,data=json.dumps(data).encode(),headers={'X-Token':s.token,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=120) as r: return json.load(r)
 def inp(s,data):
  r=s.post('/api/input?sync=1',data)['result']
  if r.get('error'): raise RuntimeError(r['error'])
  return r['record']
 def key(s,k): a=s.inp({'type':'key','id':k,'action':'down'}); s.inp({'type':'key','id':k,'action':'up'}); time.sleep(0.4); return a
 def dial(s,k,n=1): s.inp({'type':'dial','id':k,'detents':n}); time.sleep(0.3)
 def read(s,addr,n): return bytes.fromhex(s.post('/api/debug',{'op':'read','addr':hex(addr),'size':n})['hex'])
 def write(s,addr,b): s.post('/api/debug',{'op':'write','addr':hex(addr),'hex':b.hex()})
 def axis(s): return s.read(0xa031efa0,1)[0]
 def set_axis(s,a):
  for _ in range(3):
   if s.axis()==a: return
   s.key('delete')
  raise RuntimeError('axis did not reach %d'%a)
 def cell(s,i): return s.inp({'type':'token','token':'ALTGET:'+str(i)})['get']['value']
 def setting(s,i): return s.inp({'type':'token','token':'SETGET:'+str(i)})['get']['value']
 def ready(s):
  deadline=time.monotonic()+60
  while time.monotonic()<deadline:
   req=urllib.request.Request(s.base+'/api/status?after=0',headers={'X-Token':s.token})
   with urllib.request.urlopen(req,timeout=10) as response: status=json.load(response)
   if status.get('phase')=='error':raise RuntimeError(status.get('error'))
   if status.get('phase')=='running' and status.get('gui')=='0x0108' and status.get('gate')==0:return
   time.sleep(.5)
  raise TimeoutError('Player startup did not settle')
 def colour_page(s): s.key('ok'); s.key('ok'); time.sleep(0.3)
 def stop(s):
  s.proc.terminate()
  try: s.proc.wait(timeout=10)
  except subprocess.TimeoutExpired: s.proc.kill(); s.proc.wait()

def main():
 global EMU,NODE,IMAGE
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--emulator',required=True,type=Path,help='OM-Emu checkout with unpacked E147 firmware')
 parser.add_argument('--node',default=shutil.which('node'),help='Node >=26 executable')
 parser.add_argument('--library-path',help='Optional dynamic-library directory for Node')
 parser.add_argument('--image',required=True,type=Path,help='decoded/0100.bin from the shared builder')
 args=parser.parse_args()
 if not args.node:parser.error('--node is required')
 NODE=str(Path(args.node).resolve());IMAGE=args.image.resolve()
 if args.library_path:os.environ['LD_LIBRARY_PATH']=str(Path(args.library_path).resolve())
 spec=json.loads((ROOT/'patches/hsl/om-3/patch.json').read_text())
 with tempfile.TemporaryDirectory(prefix='om3-wb-emulator-') as directory:
  EMU=Path(directory)/'emulator'
  prepare_copy(args.emulator.resolve(),EMU,IMAGE,spec)
  run_integration()

def run_integration():
 p=EMU/'emu/src/lab/player.mjs';src=p.read_text();anchor="      if (tok.startsWith('SETGET:') || tok.startsWith('ALTGET:')) {"
 addition="""      if (tok.startsWith('WBALT:')) {
         const [,sid,val]=tok.split(':').map(Number);
         if (sid<904 || sid>923) throw new Error('WBALT id');
         s.begin(tok);s.lab.call(0x503f87eb,{d0:sid,d1:1,a0:val},null,[0x80,8],200000);
         return s.end(tok,'get',[],[],{get:{value:1}});
       }
       if (tok.startsWith('WBUI:')) {
         const [,sid,val]=tok.split(':').map(Number);
         if (!([901,1578,1632].includes(sid) || (sid>=1580 && sid<=1605))) throw new Error('WBUI id');
         s.begin(tok);const result=s.lab.call(0x50ac91be,{d0:sid,d1:val,a0:1},null,[0xf0,20],500000).d0 >>> 0;
         s.settle(tok);return s.end(tok,'get',[],[],{get:{value:result}});
       }
 """
 while "      if (tok.startsWith('WBALT:'))" in src or "      if (tok.startsWith('WBUI:'))" in src:
  start=min(i for i in [src.find("      if (tok.startsWith('WBALT:'))"),src.find("      if (tok.startsWith('WBUI:'))")] if i>=0);end=src.index(anchor,start);src=src[:start]+src[end:]
 p.write_text(src.replace(anchor,addition+anchor,1))
 with tempfile.TemporaryDirectory() as t:
  nv=str(Path(t)/'nv.json');s=Session(nv)
  def setv(i,v):s.inp({'type':'token','token':f'WBUI:{i}:{v}'})
  def wb():return tuple(s.setting(i) for i in [1578,1632,39,132])
  def check(w):
   got=wb();assert got==tuple(v&0xffffffff for v in w),(w,got)
   copy=s.inp({'type':'token','token':'WBSNAPSHOT'})['get']['bytes']
   assert (copy[33],copy[34],copy[38]|copy[39]<<8)==(w[2]&255,w[3]&255,w[1]),copy
   assert copy[:33]==[0xa5]*33 and copy[37]==0xa5 and copy[40:]==[0xa5]*24,copy

   print('PASS mode',s.setting(901),'WB',w,flush=True)
  try:
   s.ready();print('boot',s.setting(901),wb(),flush=True)
   for i,v in [(1578,9),(1632,5600),(1592,2),(1605,3)]:setv(i,v)
   check((9,5600,2,3))
   s.colour_page();s.key('right');assert s.setting(901)==55
   for i,v in [(1632,6500),(1592,-1),(1605,1)]:setv(i,v)
   check((9,6500,-1,1))
   s.key('right');assert s.setting(901)==56
   for i,v in [(1578,6),(1632,4200),(1584,-2),(1597,-3)]:setv(i,v)
   check((6,4200,-2,-3))
   s.key('right');assert s.setting(901)==64
   for i,v in [(1578,9),(1632,3000),(1592,4),(1605,-4)]:setv(i,v)
   check((9,3000,4,-4))
   for expected in [(6,4200,-2,-3),(9,6500,-1,1),(9,5600,2,3)]:s.key('left');check(expected)
   for expected in [(9,6500,-1,1),(6,4200,-2,-3),(9,3000,4,-4)]:s.key('right');check(expected)
   # Last stock non-COLOR bank is separate from all four COLOR records.
   setv(901,2)
   for i,v in [(1578,9),(1632,8000),(1592,-5),(1605,5)]:setv(i,v)
   check((9,8000,-5,5));setv(901,54);check((9,5600,2,3))
   setv(901,2);check((9,8000,-5,5));setv(901,64);check((9,3000,4,-4))
   s.inp({'type':'control','op':'power','value':0});s.inp({'type':'control','op':'power','value':1});check((9,3000,4,-4))
  finally:
   print('PLAYER TAIL',s.output[-25:],flush=True);s.stop()
  s=Session(nv)
  try:
   s.ready();check((9,3000,4,-4));setv(901,54);check((9,5600,2,3))
   # Native WB GUI edits must be saved, without a harness-side recall routine.
   s.key('ok');s.key('right');s.key('ok')
   s.key('down');s.dial('main',1);check((9,5800,2,3))
   s.key('down');s.dial('main',1);check((9,5800,2,4))
   setv(901,55);check((9,6500,-1,1));setv(901,54);check((9,5800,2,4))
   s.key('menu');s.key('menu')
   for _ in range(5):s.inp({'type':'key','id':'mode_dial','action':'down'});time.sleep(.6)
   print('custom bank',s.setting(901),wb(),flush=True)
   check((0,5400,0,0))
   for i,v in [(1578,9),(1632,7000),(1592,3),(1605,-2)]:setv(i,v)
   setv(901,55);setv(1632,7200);check((9,7200,3,-2))
   setv(901,54);check((9,7000,3,-2));setv(901,55);check((9,7200,3,-2))
   for _ in range(5):s.inp({'type':'key','id':'mode_dial','action':'down'});time.sleep(.6)
   check((9,5800,2,4))
   for _ in range(5):s.inp({'type':'key','id':'mode_dial','action':'down'});time.sleep(.6)
   # Native C1 recall discards unassigned edits in its default save policy.
   check((0,5400,0,0));setv(901,55);check((0,5400,0,0))
   for _ in range(5):s.inp({'type':'key','id':'mode_dial','action':'down'});time.sleep(.6)
   check((9,5800,2,4))
   # Corrupt a saved destination checksum. Recall must inherit the current WB.
   s.inp({'type':'token','token':'WBALT:919:0'});setv(901,64);check((9,5800,2,4))
   setv(901,54)
   for mode,kelvin,tint in [(19,5400,0),(9,1999,0),(9,14001,0),(9,5400,8),(9,5400,0x8000),(9,5400,0x10000)]:
    words=[mode,kelvin,tint,mode^kelvin^tint^0x57420101]
    for offset,value in enumerate(words):s.inp({'type':'token','token':f'WBALT:{916+offset}:{value}'})
    setv(901,64);check((9,5800,2,4));setv(901,54)
   print('PASS checksum and WB field validation',flush=True)

  finally:
   print('PLAYER TAIL',s.output[-25:],flush=True);s.stop()
  s=Session(str(Path(t)/'hsl-nv.json'))
  try:
   s.ready();s.colour_page();s.key('down');s.set_axis(1);s.dial('main',2)
   assert s.cell(928)==cellv(2,0),(s.setting(903),hex(s.cell(928)),s.axis())
   s.set_axis(2);s.dial('main',-1);assert s.cell(928)==cellv(2,-1)
   for i,v in [(1578,9),(1632,5600),(1592,2),(1605,3)]:setv(i,v)
   setv(901,55);setv(1632,6500);setv(901,54);check((9,5600,2,3))
   assert s.cell(928)==cellv(2,-1)
   print('PASS HSL coexistence',flush=True)
   setv(901,55)
   for index,mode in enumerate([0,18,3,1,6,17,7,8,13,14,15,16,9]):
    ab=index%7-3;gm=3-index%7
    for sid,value in [(1578,mode),(1632,6000),(1580+index,ab),(1593+index,gm)]:setv(sid,value)
    setv(901,54);check((9,5600,2,3));setv(901,55);check((mode,6000,ab,gm))
   assert s.cell(928)==cellv(2,-1)
   print('PASS all 13 WB selections with HSL retained',flush=True)
  finally:s.stop()
  print('PASS firmware WB profile independence, GUI switching, native setters, persistence across process restart',flush=True)

if __name__=='__main__':main()
