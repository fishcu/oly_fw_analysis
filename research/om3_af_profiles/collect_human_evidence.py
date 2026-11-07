"""Reproducible byte checks for the OM-3 Human-mode trace."""
import hashlib,json,struct,re
from pathlib import Path
root=Path(__file__).parent;out=root/'analysis/human-detection'
main=(root/'analysis/decoded/00_0100_50000020.decoded.bin').read_bytes()
resource=(root/'analysis/decoded/02_0106_458c0020.decoded.bin').read_bytes()
base=0x60021020;rb=0x458c0020
checks=[]
def check(name,condition):
 checks.append({'name':name,'passed':bool(condition)})
 if not condition:raise ValueError(name)
enum=[]
for i in range(7):
 off=0x28d1dec+56*i
 name=resource[off:off+48].split(b'\0')[0].decode()
 value=struct.unpack_from('<I',resource,off-4)[0]
 enum.append({'value':value,'name':name,'label_decoded_offset':hex(off)})
check('Human settings enum equals 6',enum[-1]['name']=='MODE_SUBJECT_DETECT_HUMAN' and enum[-1]['value']==6)
selector=main[0x602cb253-base:0x602cb262-base]
check('Resource 0x800f maps to directory index 10',selector[14]==10)
topaddr,topsize=struct.unpack_from('<II',resource,10*16)
check('Directory index 10 is 0x49680000',topaddr==0x49680000 and topsize==0x4b00000)
check('Nested resource directory has OE header',resource[topaddr-rb:topaddr-rb+2]==b'OE')
models=[]
for i in range(6):
 a,n=struct.unpack_from('<II',resource,topaddr-rb+32+16*i)
 data=resource[a-rb:a-rb+n]
 check('Learning bank '+str(i)+' in decoded component bounds',len(data)==n and n==0x8f3000)
 models.append({'index':i,'logical_address':hex(a),'decoded_offset':hex(a-rb),'stored_size':n,'sha256':hashlib.sha256(data).hexdigest()})
check('Extracted Human-selected bank equals sixth directory entry',(out/'human-selected-learning-bank.bin').read_bytes()==resource[int(models[5]['decoded_offset'],16):int(models[5]['decoded_offset'],16)+models[5]['stored_size']])
resize=[]
for i in range(3):
 a=0x60a05b28+i*48;words=struct.unpack_from('<12I',main,a-base)
 resize.append({'index':i,'table_address':hex(a),'words':list(words),'interface_width':words[0],'interface_height':words[1]})
check('Resize tables describe 640x480, 640x360 and 640x340',[(r['interface_width'],r['interface_height']) for r in resize]==[(640,480),(640,360),(640,340)])
rawparams={hex(a):main[a-base] for a in range(0x60a06a44,0x60a06a55)}
check('Stabilization parameter bytes match reviewed image',list(rawparams.values())==[50,6,6,4,4,8,3,3,2,2,4,6,6,10,10,6,0])
logmap=json.loads((out/'log-id-map.json').read_text())
check('Log metadata names resolve at expected IDs',all(logmap[i]['name']==name for i,name in [(0x271,'subject_detect_offer_yc_data'),(0x27b,'learning_data_select'),(0x280,'get_index_yc_aspect'),(0x298,'regist_judge_update'),(0x2c4,'face_combination')]))
for filename in ['result-read-full-window.asm','class-filter.asm','learning-loader.asm']:
 check('Bounded decode has no failures: '+filename,'DECODE_FAILURE' not in (out/filename).read_text())
result={'scope':'Static byte checks and trace metadata; no inference, AF, timing or camera behavior tests','settings_enum':enum,'resource_selector_hex':selector.hex(),'learning_banks':models,'resize_tables':resize,'stabilization_parameter_bytes':rawparams,'checks':checks}
(out/'verified-evidence.json').write_text(json.dumps(result,indent=2))
print(str(len(checks))+' static checks passed. Human-selected stored bank: '+models[5]['sha256'])
