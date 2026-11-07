"""Test the exact emulator code bytes against the real component parser IN MEMORY."""
from pathlib import Path
import sys,struct,json,hashlib
R=Path(__file__).resolve().parents[1];O=R/'analysis/button-af/prehardware'
sys.path.insert(0,str(R/'reference/tools'))
from oly_container import parse,replace_payload,encode,decode,sha256
source=R/'firmware/catalog/OLY_E_147_1100_0000_0000.BIN'
with source.open('rb') as f:
 header=f.read(32);size=struct.unpack_from('<I',header,12)[0];raw=header+f.read(size+32)
stock,=parse(raw);code=(O/'packed-code.emulator-only.bin').read_bytes();base=0x60021020;at=0x60a8f088-base
assert len(code)==1780 and stock.payload[at:at+len(code)]==b'\xff'*len(code)
changed=bytearray(stock.payload);changed[at:at+len(code)]=code;encoded=encode(changed)
try:parse(stock.header+encoded+stock.trailer)
except ValueError as ex:assert 'checksum mismatch' in str(ex)
else:raise AssertionError('Unrepaired changed component accepted')
fixed=replace_payload(stock,changed);parsed,=parse(fixed.header+encoded+fixed.trailer)
assert parsed.payload==changed and decode(encoded)==changed
assert fixed.header==stock.header and fixed.trailer[:28]==stock.trailer[:28] and len(fixed.payload)==len(stock.payload)
result=dict(packed_code_bytes=len(code),component_payload_bytes=len(stock.payload),code_address='0x60a8f088',unrepaired_edit_rejected=True,repaired_component_parser_accepted=True,encode_decode_identical=True,metadata_and_size_preserved=True,modified_component_sha256=sha256(fixed.header+encoded+fixed.trailer),saved_modified_component=False,scope='Host component parser and exact emulator code bytes only. Hooks/data allocation are not installed. No native full-image validator, loader lifetime, boot, flash or camera acceptance established.')
(O/'packed-container-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result,indent=2))
