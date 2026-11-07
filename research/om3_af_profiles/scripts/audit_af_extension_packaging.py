"""Counterfactual component changes IN MEMORY ONLY. No installable image output."""
from pathlib import Path
import sys,struct,json,hashlib
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'reference/tools'))
from oly_container import parse,replace_payload,encode,sha256

source=R/'firmware/catalog/OLY_E_147_1100_0000_0000.BIN'
h=hashlib.sha256()
with source.open('rb') as f:
 while chunk:=f.read(1024*1024):h.update(chunk)
assert h.hexdigest()=='8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d'
with source.open('rb') as f:
 header=f.read(32);n=struct.unpack_from('<I',header,12)[0]
 raw=header+f.read(n+32)
stock,=parse(raw);base=0x60021020
assert encode(stock.payload)==raw[32:-32]
rows=[]
for sid,start,end,pad in [(1,0x60134000,0x6031f000,0x6031e910),(4,0x60828000,0x60a8f800,0x60a8f088),(9,0x61809000,0x619a9800,0x619a966c)]:
 assert stock.payload[pad-base:end-base]==b'\xff'*(end-pad)
 # A marker is data for an offline packaging experiment, never executable patch code.
 changed=bytearray(stock.payload);at=pad-base+16;changed[at:at+16]=bytes(range(0x30,0x40))
 encoded=encode(changed)
 try:parse(stock.header+encoded+stock.trailer)
 except ValueError as exc:
  assert 'checksum mismatch' in str(exc);bad_rejected=True
 else:raise AssertionError('Unrepaired edit was not rejected')
 repaired=replace_payload(stock,changed)
 parsed,=parse(repaired.header+encoded+repaired.trailer)
 assert parsed.payload==changed
 assert repaired.header==stock.header and repaired.trailer[:28]==stock.trailer[:28]
 assert len(changed)==len(stock.payload)
 rows.append(dict(section=sid,start=hex(start),end_exclusive=hex(end),ff_tail=hex(pad),ff_tail_bytes=end-pad,
  changed_address=hex(base+at),changed_bytes=16,unrepaired_checksum_rejected=bad_rejected,
  repaired_component_accepted_by_offline_parser=True,metadata_preserved=True,
  encoded_component_sha256=sha256(repaired.header+encoded+repaired.trailer)))
report=dict(source_sha256=h.hexdigest(),stock_component_roundtrip=True,experiments=rows,
 scope='In-memory markers and offline component parser only. No installable package saved. No camera validator, flash writer, boot or recovery executed.',
 conclusion='Same-size changed main components can be encoded with valid additive checksums. This does not establish on-camera acceptance or later code/data ownership.')
(R/'analysis/button-af/packaging-experiments.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
