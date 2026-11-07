"""Recover kallsyms into an ELF without executing the embedded kernel."""
import json,logging,struct,sys
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path[:0]=[str(root/'tooling/python-deps'),str(root/'tooling/vmlinux-to-elf')]
from vmlinux_to_elf.core.elf_symbolizer import ElfSymbolizer
logging.basicConfig(level=logging.INFO,format='%(message)s')
p=root/'analysis/embedded'
raw=(p/'linux-arm64-Image.bin').read_bytes()
ElfSymbolizer(raw,str(p/'linux-kernel-symbolized.elf'),elf_machine=183,bit_size=64)
b=(p/'linux-kernel-symbolized.elf').read_bytes()
h=struct.unpack_from('<HHIQQQIHHHHHH',b,16)
sections=[struct.unpack_from('<IIQQQQIIQQ',b,h[5]+i*h[10]) for i in range(h[11])]
sy=next(s for s in sections if s[1]==2)
st=sections[sy[6]]
strings=b[st[4]:st[4]+st[5]]
symbols={}
for i in range(sy[5]//sy[9]):
    s=struct.unpack_from('<IBBHQQ',b,sy[4]+i*sy[9])
    name=strings[s[0]:].split(b'\0',1)[0].decode(errors='replace')
    symbols[name]=s[4]
# Independent cross-check: the ARM64 Image header's entry branch must target stext.
ins=struct.unpack_from('<I',raw,0)[0]
assert ins&0xfc000000==0x14000000
imm=ins&0x3ffffff
if imm&(1<<25):imm-=1<<26
branch_offset=imm*4
base=0xffffff8008080000
assert symbols['stext']==base+branch_offset
report=dict(symbol_count=sy[5]//sy[9],base=hex(base),stext=hex(symbols['stext']),
            header_branch_target_offset=hex(branch_offset),entry_branch_matches_stext=True,
            caveat='Reconstructed ELF from kallsyms; not an original vendor ELF. Tool emits relative-offset heuristic warnings; entry mapping cross-checked.')
(p/'kernel-symbol-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
