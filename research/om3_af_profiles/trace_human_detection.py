"""Reconstruct log-ID names and implementation candidates; no firmware modifications."""
import json,re,struct,collections
from pathlib import Path

root=Path(__file__).parent
out=root/'analysis/human-detection'
b=(root/'analysis/decoded/00_0100_50000020.decoded.bin').read_bytes()
base=0x60021020
def u32(a): return struct.unpack_from('<I',b,a-base)[0]
def string(a):
 if not base<=a<base+len(b):return None
 return b[a-base:a-base+200].split(b'\0')[0].decode('ascii',errors='replace')
table=[]
for i in range(0x34c):
 a=0x609f9048+i*36
 table.append({'id':i,'id_hex':hex(i),'record':hex(a),'short_name':string(u32(a+12)), 'name':string(u32(a+28)), 'formatter':hex(u32(a+32))})
s=(root/'analysis/decompiled-main/all-functions.c').read_text(encoding='utf-8')
implementations=collections.defaultdict(list)
sections=re.split(r'(?=/\* Address [0-9a-f]{8};)',s)
for section in sections:
 m=re.match(r'/\* Address ([0-9a-f]{8});.*?body bytes (\d+);',section)
 if not m:continue
 ids=set(int(x,0) for x in re.findall(r'FUN_6083a(?:8ed|9b5)\((0x[0-9a-f]+|[0-9]+),',section))
 for i in ids:
  if i<len(table):implementations[i].append({'address':m[1],'body_bytes':int(m[2])})
for row in table:row['implementation_candidates']=implementations[row['id']]
(out/'log-id-map.json').write_text(json.dumps(table,indent=2),encoding='utf-8')
selected=table[0x260:0x2da]
lines=[]
for r in selected:
 lines.append(f"{r['id_hex']}\t{r['name']}\t"+','.join(x['address']+':'+str(x['body_bytes']) for x in r['implementation_candidates']))
(out/'pipeline-function-map.tsv').write_text('log_id\tname\tcandidate_address:body_bytes\n'+'\n'.join(lines),encoding='utf-8')
print('\n'.join(lines))
# Reading aid only: omit conditional logger blocks; original exports remain evidence.
core=out/'reading-aids';core.mkdir(exist_ok=True)
for r in table:
 if not r['implementation_candidates']:continue
 f=max(r['implementation_candidates'],key=lambda x:x['body_bytes'])
 t=(root/f"analysis/decompiled-main/functions/{f['address']}.c").read_text(encoding='utf-8')
 lines=t.splitlines();keep=[];i=0
 while i<len(lines):
  if lines[i].lstrip().startswith('if (') and '_DAT_a337174c' in lines[i]:
   balance=0;opened=False
   while i<len(lines):
    balance+=lines[i].count('{')-lines[i].count('}')
    opened=opened or '{' in lines[i];i+=1
    if opened and balance==0:break
   continue
  keep.append(lines[i]);i+=1
 (core/(str(r['id'])+'-'+re.sub(r'[^A-Za-z0-9_]+','_',r['name'])+'.txt')).write_text('READING AID: logger guard blocks omitted; not a faithful executable program.\n'+'\n'.join(keep),encoding='utf-8')
asm=out/'assembly';asm.mkdir(exist_ok=True)
want={}
for r in table:
 if r['implementation_candidates']:
  f=max(r['implementation_candidates'],key=lambda x:x['body_bytes'])
  want.setdefault(f['address'],[]).append(str(r['id'])+'-'+re.sub('[^A-Za-z0-9_]+','_',r['name'])+'.asm')
buf=[];current=None
def flush():
 if current:
  for name in current:(asm/name).write_text(''.join(buf),encoding='utf-8')
for line in (root/'analysis/decompiled-main/all-functions.asm').open(encoding='utf-8'):
 if line.startswith('; Function '):
  flush();buf=[]
  m=re.match(r'; Function ([0-9a-f]{8})',line)
  current=want.get(m[1]) if m else None
 if current:buf.append(line)
flush()
print('Assembly files:',len(list(asm.glob('*.asm'))))

