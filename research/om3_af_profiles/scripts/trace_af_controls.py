"""Reproducible static AF setting/control maps; no camera or firmware writes."""
from pathlib import Path
import json,struct,hashlib
R=Path(__file__).resolve().parents[1]
M=(R/'analysis/decoded/00_0100_50000020.decoded.bin').read_bytes()
B=0x60021020
assert hashlib.sha256(M).hexdigest()=='5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59'
names={x['id']:x['name'] for x in json.loads((R/'analysis/review/setting-name-candidates.json').read_text(encoding='utf-8'))['names']}
keys={0x84d1,0x88b2,0x99a1,0x9a41,0x1dd1,0x1df1,0x1e01,0x90a1,0x90b1,0x1e71,0x85b1,0xe8d9}
rows=[]
for i in range(0x8d0):
 k,n=struct.unpack_from('<HH',M,0x6062555c-B+4*i)
 if k in keys:rows.append(dict(ui_id=i,name=names.get(i),runtime_key=hex(k),array_index=n,entry=hex(0x6062555c+4*i)))
out=R/'analysis/button-af'
(out/'gui-property-key-map.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
events=[]
for code,name in [(0x1050007,'AF-ON press'),(0x1050008,'AF-ON release')]:
 pos=0
 while (pos:=M.find(struct.pack('<I',code),pos))!=-1:
  if pos+16<=len(M):
   event,f1,f2,handler=struct.unpack_from('<4I',M,pos)
   if f1==f2==1 and B<=handler<B+len(M):
    events.append(dict(event=hex(code),name=name,entry=hex(B+pos),handler=hex(handler),scope='Static event-table record; active UI state not established by this row alone.'))
  pos+=1
vtable=[dict(slot=hex(s),target=hex(struct.unpack_from('<I',M,0x60e57668+s-B)[0])) for s in [0x5c,0x60,0x64,0x3c8,0x3cc,0x3e8]]
report=dict(main_sha256=hashlib.sha256(M).hexdigest(),event_table_entries=events,ui_vtable=hex(0x60e57668),slots=vtable,
 afon_held_setter='0x610b9828',afon_held_storage='0x6036ee34',
 scope='Table and instruction evidence, not a complete physical button-to-worker trace. Ordinary shooting handlers are distinct from the earlier target-control handler.')
(out/'shooting-control-map.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(mapped_settings=len(rows),event_entries=len(events),native_mapping_test_ids=[40,85,163,1657,1658,1675,1683,1712,1803,2154,2155,2156,2157]),indent=2))
