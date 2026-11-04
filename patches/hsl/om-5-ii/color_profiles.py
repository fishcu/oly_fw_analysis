"""Build the data edits that restore Color Profile 1-3 and Monochrome Profile 1-3 picture modes on
OM-5 II (E148 1.1). Set MONO=0 in the environment for the Color Profile edits alone.
Emits {runtime_addr_hex: hex_bytes} for OM_LAB_IMAGE_PATCH. Emulator research only."""
import json, os, struct, sys
B=0x60021020
img=open(sys.argv[1],'rb').read()
R=lambda a,n: img[a-B:a-B+n]
DESC={111:0x6050de44, 504:0x6050e04c, 505:0x6050e060}
OLD_REC, OLD_VAL, N = 0x604eeae0, 0x604e1a6c, 41
INSERT_AFTER = 40           # append after the last entry, so existing indices are unchanged
CAROUSEL_AFTER = 9          # but list them after Color Creator in the SCP carousel
CP = [(54,(0xb,0,1,0)),(55,(0xb,0,2,0)),(56,(0xb,0,3,0))]
# E147 records 38..40: MONO1..3 = 57..59, major 12, profile number in word 3 (setting 989)
MONO = [(57,(0xc,0,0,1)),(58,(0xc,0,0,2)),(59,(0xc,0,0,3))] if os.environ.get('MONO','1')!='0' else []
NEW = CP + MONO
IS_MONO = {v for v,_ in MONO}
# E147 rule 15227 maps CP and MONO to Natural (1) when Focus Stacking (1356) is on, while Vivid and
# Monotone stay. The original CP port follows Vivid there; MONO follows E147. Set to True to make CP
# follow E147 as well (changes existing CP behaviour, so off until decided).
CP_FOCUS_STACKING_E147 = False
FOCUS_STACKING = [(1356,1)]
FREE_LO, FREE_HI = 0x604f1160, 0x604f25e0   # the 504/505 record copies, identical to 111's, freed by sharing
RULES, NRULES = 0x60493710, 340
for sid,d in DESC.items():
    i,k,rp,vp,size,stride = struct.unpack('<HHIIHH',R(d,16))
    assert i==sid and size==N*64 and stride==64, (sid,hex(rp),size)
assert R(0x604f1160,N*64)==R(OLD_REC,N*64)==R(0x604f1ba0,N*64)
vals=list(struct.unpack('<%dI'%N,R(OLD_VAL,4*N)))
assert vals[9]==21 and vals[40]==63
recs=[R(OLD_REC+64*i,64) for i in range(N)]
order=list(range(N)); ins=INSERT_AFTER+1
# A record that matches no entry resolves to the LAST index (0x602e1797). Settings context 1 reads 111 that
# way (stock: 63, ART16), so the new entries must not become the last one, or every context-1 refresh would
# apply CP3/MONO3. Keep a copy of the stock last entry at the end; lookups by value still find index 40.
TAIL_COPY = True
new_vals=vals[:ins]+[v for v,_ in NEW]+vals[ins:]+(vals[-1:] if TAIL_COPY else [])
new_recs=recs[:ins]+[struct.pack('<4I',*r)+bytes(48) for _,r in NEW]+recs[ins:]+(recs[-1:] if TAIL_COPY else [])
M=len(new_vals)
edits={}
# Free space once all three descriptors share one extended copy: the 504/505 record copies and 111's old record table
REGIONS=[[FREE_LO,FREE_HI],[OLD_REC,OLD_REC+N*64]]
cur=FREE_LO
def put(data):
    global cur
    for r in REGIONS:
        a=(r[0]+3)&~3
        if a+len(data)<=r[1]:
            edits[hex(a)]=data.hex(); r[0]=a+len(data); cur=r[0]; return a
    raise SystemExit('no space for %d bytes'%len(data))
rec_addr=put(b''.join(new_recs)); val_addr=put(struct.pack('<%dI'%M,*new_vals))
for sid,d in DESC.items():
    edits[hex(d+4)]=struct.pack('<IIH',rec_addr,val_addr,M*64).hex()
# rule clauses whose pair list follows 111's value order
masks={}; clauses=[]
o=RULES
for k in range(NRULES):
    rid,_,ptr,cnt=struct.unpack('<HHIH',R(o+20*k,10))
    for j in range(cnt):
        ca,cn,ma,mn,tag=struct.unpack('<IIIHH',R(ptr+16*j,16))
        if mn!=N: continue
        pairs=[struct.unpack('<HH',R(ma+4*i,4)) for i in range(N)]
        if [p[0] for p in pairs]!=vals: continue
        clauses.append((rid,ptr+16*j,ma)); masks.setdefault(ma,pairs)
def conds(cl):
    ca,cn=struct.unpack('<II',R(cl,8))
    return [struct.unpack('<HH',R(ca+4*i,4)) for i in range(cn)]
def mapping(pairs,fs):
    d=dict(pairs); out=[]
    for v,_ in NEW:
        if fs and (v in IS_MONO or CP_FOCUS_STACKING_E147): out.append((v,1)); continue
        ref=3 if v in IS_MONO else 0             # MONO follows Monotone, COLOR follows Vivid
        out.append((v, v if d[ref]==ref else d[ref]))
    return out
new_mask={}                                      # identical extended masks are shared
for rid,cl,ma in clauses:
    fs=rid==15227 and conds(cl)==FOCUS_STACKING
    data=b''.join(struct.pack('<HH',*p) for p in masks[ma][:ins]+mapping(masks[ma],fs)+masks[ma][ins:]+(masks[ma][-1:] if TAIL_COPY else []))
    if data not in new_mask: new_mask[data]=(put(data),'%x%s'%(ma,'/fs' if fs else ''))
    edits[hex(cl+8)]=struct.pack('<IH',new_mask[data][0],M).hex()
json.dump(edits,open(sys.argv[2],'w'),indent=0)
print('records',hex(rec_addr),'values',hex(val_addr),'masks',{n:hex(a) for a,n in new_mask.values()},'clauses',len(clauses),'free',[(hex(a),b-a) for a,b in REGIONS])

# --- group membership: E147 groups 111/504/505 also carry the COLOR/MONO profile selectors (record words 2 and 3)
GROUPS, NGROUPS = 1615274328, 151
want={111:(111,361,903,989),504:(504,1059,1060,1061),505:(505,1063,1064,1065)}
for k in range(NGROUPS):
    a=GROUPS+34*k; r=struct.unpack('<17H',R(a,34))
    if r[0] in want:
        assert r[1:4]==(want[r[0]][0],want[r[0]][1],3200), r
        edits[hex(a+2)]=struct.pack('<5H',*want[r[0]],3200).hex()
# SCP picture-mode carousel (stride 20, its own list) and value->label table (stride 8)
CAR, CAR_DESC = 0x61199464, 0x61199b5c
rows=[R(CAR+20*k,20) for k in range(N)]
assert struct.unpack('<I',R(CAR_DESC-4,4))[0]==111 and struct.unpack('<II',R(CAR_DESC,8))==(N,CAR)
labels={54:0x430,55:0x431,56:0x432,57:0x434,58:0x435,59:0x436}   # E147 text/availability IDs
c=CAROUSEL_AFTER+1
car=rows[:c]+[struct.pack('<5I',v,labels[v],v,0,0) for v,_ in NEW]+rows[c:]
car_addr=put(b''.join(car)); edits[hex(CAR_DESC)]=struct.pack('<II',len(car),car_addr).hex()   # display list: no tail copy
LBL, LBL_DESC = 0x611a1734, 0x611a1a00
assert struct.unpack('<I',R(LBL_DESC-4,4))[0]==111 and struct.unpack('<I',R(LBL_DESC,4))[0]==N and struct.unpack('<I',R(LBL_DESC+8,4))[0]==LBL
# rows 41.. of this table already hold 54..56 (labels 0x430..); the count alone hides them
extra=[struct.unpack('<II',R(LBL+8*k,8)) for k in range(N,N+8)]
pass
lrows=[R(LBL+8*k,8) for k in range(N)]+[struct.pack('<II',v,labels[v]) for v,_ in NEW]
lbl_addr=put(b''.join(lrows)); edits[hex(LBL_DESC)]=struct.pack('<I',len(lrows)).hex(); edits[hex(LBL_DESC+8)]=struct.pack('<I',lbl_addr).hex()
json.dump(edits,open(sys.argv[2],'w'),indent=0)
print('groups, carousel',hex(car_addr),'labels',hex(lbl_addr),'free',[(hex(a),b-a) for a,b in REGIONS])

# --- picture-mode availability lookup (0x602ddb79): mode -> availability ID, 53 rows at 0x604991f8.
# E148 has no rows for 54..56, so the lookup returns 3200 and 0x602df14f may reset 111 to i-Enhance.
# E147 maps them to 1072..1074 (0x60400b6d / 0x605dfe04); E148 still keeps those IDs (set beside
# 584/586/1076.. at 0x6162dab4). Copy the table with the three rows appended and repoint the lookup.
AV, AV_N, AV_ADD, AV_CMP = 0x604991f8, 53, 0x602ddb89, 0x602ddb9b
assert struct.unpack('<I',R(AV_ADD,4))[0]==AV and R(AV_CMP-1,2)==bytes([0xaf,AV_N])
av_rows=[R(AV+8*k,8) for k in range(AV_N)]
assert all(struct.unpack('<I',r[:4])[0] not in (54,55,56,57,58,59) for r in av_rows)
av_rows+= [struct.pack('<IHH',v,labels[v],0) for v,_ in NEW]     # MONO 1076..1078 as E147 0x605dfef4
av_addr=put(b''.join(av_rows))
edits[hex(AV_ADD)]=struct.pack('<I',av_addr).hex(); edits[hex(AV_CMP)]=bytes([len(av_rows)]).hex()
json.dump(edits,open(sys.argv[2],'w'),indent=0)
print('availability',hex(av_addr),len(av_rows),'free',[(hex(a),b-a) for a,b in REGIONS])
