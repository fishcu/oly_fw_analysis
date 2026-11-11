"""Extract structurally bounded embedded images from the verified 0106 payload."""
import hashlib,json,struct
from pathlib import Path
root=Path(__file__).resolve().parent
source=root/'analysis/decoded/02_0106_458c0020.decoded.bin'
b=source.read_bytes()
assert hashlib.sha256(b).hexdigest()=='3d9fd4426b45fbe4b715599422af38c6d22392c08543a69f63c28291c5a0b059'
out=root/'analysis/embedded'
out.mkdir(exist_ok=True)
records=[]
def save(name,start,size,kind,details):
    assert 0<=start<start+size<=len(b)
    data=b[start:start+size]
    (out/name).write_bytes(data)
    records.append(dict(file=name,decoded_resource_offset=hex(start),bytes=size,
                        sha256=hashlib.sha256(data).hexdigest(),kind=kind,details=details))
sq=b.index(b'hsqs')
header=struct.unpack_from('<5I6H8Q',b,sq)
assert header[9:11]==(4,0)
save('rootfs.squashfs',sq,header[12],'SquashFS 4.0',dict(inodes=header[1],compression_id=header[5]))
elf=b.index(b'\x7fELF')
assert b[elf+4:elf+7]==b'\x02\x01\x01'
eh=struct.unpack_from('<HHIQQQIHHHHHH',b,elf+16)
assert eh[1]==183
phoff,shoff=eh[4],eh[5]
phentsize,phnum,shentsize,shnum=eh[8],eh[9],eh[10],eh[11]
extent=max(64,phoff+phentsize*phnum,shoff+shentsize*shnum)
for i in range(phnum):
    ph=struct.unpack_from('<IIQQQQQQ',b,elf+phoff+i*phentsize)
    extent=max(extent,ph[2]+ph[5])
for i in range(shnum):
    sh=struct.unpack_from('<IIQQQQIIQQ',b,elf+shoff+i*shentsize)
    if sh[1]!=8:extent=max(extent,sh[4]+sh[5]) # SHT_NOBITS has no file data.
save('embedded-aarch64.elf',elf,extent,'ELF64 AArch64',dict(entry=hex(eh[3]),type=eh[0]))
start=0
while True:
    magic=b.find(b'ARM\x64',start)
    if magic<0:break
    offset=magic-0x38
    if offset>=0:
        text_offset,size,flags=struct.unpack_from('<QQQ',b,offset+8)
        if 0<size<=len(b)-offset:
            save('linux-arm64-Image.bin',offset,size,'ARM64 Linux Image',dict(text_offset=hex(text_offset),flags=hex(flags)))
            break
    start=magic+4
(out/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(records,indent=2))
