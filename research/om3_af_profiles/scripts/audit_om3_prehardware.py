"""Read-only inventories, with raw reference candidates labeled as such."""
from pathlib import Path
import hashlib, json, struct, bisect
R=Path(__file__).resolve().parents[1]; O=R/'analysis/button-af/prehardware'
b=(R/'analysis/decoded/00_0100_50000020.decoded.bin').read_bytes(); base=0x60021020
assert hashlib.sha256(b).hexdigest()=='5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59'
def literals(v):
 p=0; a=[]; needle=struct.pack('<I',v)
 while (p:=b.find(needle,p))>=0:a.append(hex(base+p));p+=1
 return a
targets={0x60902c64:'active target accessor',0x609b3bb2:'stock target accessor',0x609b3ecd:'stock enum converter',0x6087215e:'outer result publisher',0x60af491f:'AFL request constructor',0x60af64fd:'AFL associated command constructor',0x60ddaa7c:'secondary allocation context getter'}
calls={hex(t):{'label':label,'relative_call_candidates':[]} for t,label in targets.items()}
for i,op in enumerate(b[:-8]):
 if op==0xdd:t=(base+i+struct.unpack_from('<i',b,i+1)[0])&0xffffffff
 elif op==0xcd:t=(base+i+struct.unpack_from('<h',b,i+1)[0])&0xffffffff
 else:continue
 if t in targets:calls[hex(t)]['relative_call_candidates'].append(hex(base+i))
names=json.loads((R/'analysis/review/setting-name-candidates.json').read_text(encoding='utf8'))['names'];mapped=[]
for n in names:
 if any(s in n['name'] for s in ('AF_AREA','AF_TARGET','CUSTOM_MODE','SLEEP','RESET','SUBJECT_DETECT','SUBJECT_SELECT')):
  i=n['id']
  if i<0x8d0:
   k,idx=struct.unpack_from('<HH',b,0x6062555c-base+4*i);mapped.append(dict(n,key=hex(k),index=idx))
tailstart=0x60a8f088;tailend=0x60a8f800
assert all(v==255 for v in b[tailstart-base:tailend-base])
packed_size=(O/'packed-code.emulator-only.bin').stat().st_size
out=dict(scope='Raw literals and relative-call candidates; not complete references or reachability. Native probes separately validate selected paths.',calls=calls,literals={hex(v):literals(v) for v in (0xa33ca384,0xa33f2ce0,0x62b770a0,0x84d1,0x99a1)},related_settings=mapped,section_descriptors=[dict(index=i,words=[hex(struct.unpack_from('<I',b,0x60029b28-base+12*i+j)[0]) for j in (0,4,8)]) for i in range(10)],padding=dict(start=hex(tailstart),end_exclusive=hex(tailend),length=tailend-tailstart,original_byte='ff',packed_code_bytes=packed_size,remaining_bytes=tailend-tailstart-packed_size,runtime_ownership='unproven'),prototype_storage=dict(control_start='0x700c1000',bank_start='0x700c2000',orientation_bank_bytes=0x130,ownership='emulator fixture; no camera allocator reservation'))
(O/'static-inventory.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(call_candidates={v['label']:len(v['relative_call_candidates']) for v in calls.values()},settings=len(mapped),padding=out['padding']),indent=2))
