"""Read-only firmware reconnaissance; outputs candidates, not reachability claims."""
from pathlib import Path
import json, struct, hashlib
R=Path(__file__).resolve().parents[1]
M=(R/'analysis/decoded/00_0100_50000020.decoded.bin').read_bytes()
B=0x60021020
def u32(a):return struct.unpack_from('<I',M,a-B)[0]
out={}
out['af_ui_vtable']=[dict(slot=hex(s),address=hex(0x60e57668+s),target=hex(u32(0x60e57668+s))) for s in [0x3c8,0x3cc,0x3e8]]
out['section_descriptors']=[dict(id=i+1,words=[hex(u32(0x60029b28+12*i+j)) for j in [0,4,8]]) for i in range(10)]
out['strings']={k:[] for k in ['AF','update']}
for line in (R/'analysis/decoded/strings.jsonl').open():
 x=json.loads(line);s=x['text'].lower()
 if x['block']==0 and any(t in s for t in ['half','afon','af_on','release ready','shutter','firmup','checksum','e147','signature','rsa verify']):
  out['strings']['AF' if any(t in s for t in ['half','afon','af_on','release ready','shutter']) else 'update'].append(x)
out['main_sha256']=hashlib.sha256(M).hexdigest()
dispatch=json.loads((R/'analysis/button-af/worker-dispatch-map.json').read_text())
messages=[]
for a in range(0x60a83454,0x60a83654,8):
 key,target=u32(a),u32(a+4)
 if not key:continue
 match=[x for x in dispatch if target<=int(x['dispatch_call'],16)<target+40]
 messages.append(dict(table_address=hex(a),message=hex(key-1),dispatch=hex(target),operation=match[0]['label'] if len(match)==1 else 'unresolved'))
(R/'analysis/button-af/worker-message-map.json').write_text(json.dumps(messages,indent=2))
def hits(value):
 needle=struct.pack('<I',value);ans=[];pos=0
 while (pos:=M.find(needle,pos))!=-1:
  ans.append(hex(B+pos));pos+=1
 return ans
out['literal_candidates']={hex(v):hits(v) for v in [0x41b0062,0x41b0038,0x60e57668,0xa33ac4ac,0xa33ac4b4,0xa33ac4b6,0xa33ac4be,0xa33ac4c6]}
(R/'analysis/button-af/gap-literal-candidates.json').write_text(json.dumps(out['literal_candidates'],indent=2))
(R/'analysis/button-af/gap-recon.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:v for k,v in out.items() if k!='strings'},indent=2))
N=json.loads((R/'analysis/review/setting-name-candidates.json').read_text())
Q=(R/'analysis/decoded/02_0106_458c0020.decoded.bin').read_bytes()
for x in N['names']:
 if any(s in x['name'] for s in ['AF_TARGET','AF_AREA','SUBJECT_DETECT','SUBJECT_SELECT']):
  i=x['id'];o=int(N['component_offset'],16)+52*i
  print('LABEL',i,x['name'],'tail',Q[o+40:o+52].hex())
