#!/usr/bin/env python3
"""Live ND32/ND64 for OM-5 Mark II (E148 1.1): build and statically check the edits.

Built into the HSL/Monochrome patch (patches/hsl/om-5-ii, via check()); this
directory's patch.json also applies it to stock on its own. Static research only.

  nd64.py EXPANDED_E148.bin [EDITS_OUT.json]     check, print, optionally write lab edits
  nd64.py --spec STOCK.BIN                        (re)write patch.json next to this file

Edits:
 1. Setting 1710 (Live ND number) allowed list: point descriptor 0x6051485c at an
    existing read-only byte run 01..06 in the same allowed-list pool and set its
    length to 6 (stock: 01..04 at 0x6050d499). E147 (OM-3) allows 1..6.
 2. ND step selector 0x6023c850..0x6023c874: stock is a switch for steps 1..4 that
    stores step x EV-unit (unit 1, 2 or 3 per 1, 1/2, 1/3 EV). Replaced in place by
    a bounded repeated addition for steps 1..6, giving the same values as E147's
    0x6031a825 switch (5x, 6x). Steps 0 and 7..255 still take the stock error
    path at 0x6023c87b; the stock store at 0x6023c875 is reused. Plain MN10300
    instructions only (no udf00). Scratch: d0, d1, as stock.
Frame count (1 << step at 0x6023ca83) and the Tv/frame tables need no change; the
tables are byte-identical to E147's.
"""
import hashlib, json, struct, sys
from pathlib import Path

B = 0x60021020
EXPANDED_SHA = '7ae7d4c60990cc859c070e0ceb6cbe612f9c5b260713f2f1256e51d137851c61'
DESC_1710, OLD_LIST, NEW_LIST = 0x6051485c, 0x6050d499, 0x6050c3d3
SEL, STORE, INVALID, RET = 0x6023c850, 0x6023c875, 0x6023c87b, 0x6023c896
ORIG_SEL = bytes.fromhex('a001c810a002c80fa003c80fa004c815ca1b12ca1212eaca0e5c548854f108f050ca2512'
                         '56')
ORIG_TAIL = bytes.fromhex('5c54f058ca1d')  # 0x6023c875 store d2 byte, bra ret


def selector():
    code = bytearray()
    def emit(h): code.extend(bytes.fromhex(h))
    def br(op, target):
        pc = SEL + len(code); d = target - pc
        assert -128 <= d < 128; code.extend(bytes([op]) + struct.pack('b', d))
    emit('a0 01'); br(0xc0, INVALID)       # cmp 1,d0 ; blt invalid
    emit('a0 06'); br(0xc1, INVALID)       # cmp 6,d0 ; bgt invalid
    emit('12 81 00')                       # extb d2 ; mov d0,d1 ; clr d0
    loop = SEL + len(code)
    emit('e8 29 ff'); br(0xc9, loop)       # add d2,d0 ; add -1,d1 ; bne loop
    emit('82'); br(0xca, STORE)            # mov d0,d2 ; bra store
    assert len(code) <= len(ORIG_SEL)
    return bytes(code) + b'\xcb' * (len(ORIG_SEL) - len(code))   # nop padding


def run(mem, d0, d2):
    """Interpret the selector region (stock or patched) for one input.
    Returns ('store', byte) or ('invalid',). Covers only the opcodes present."""
    r = {'d0': d0, 'd1': 0xdeadbeef, 'd2': d2}
    s32 = lambda v: v - (1 << 32) if v & 0x80000000 else v
    pc, cmp = SEL, 0
    for _ in range(400):
        if pc == INVALID: return ('invalid',)
        if pc == RET: return ('store', out)
        o = mem(pc, 1)[0]; nx = mem(pc, 2)
        rel = lambda: struct.unpack('b', nx[1:2])[0]
        if o == 0xa0: cmp = s32(r['d0']) - struct.unpack('b', nx[1:2])[0]; pc += 2
        elif o in (0xc0, 0xc1, 0xc8, 0xc9, 0xca):
            take = {0xc0: cmp < 0, 0xc1: cmp > 0, 0xc8: cmp == 0, 0xc9: cmp != 0, 0xca: True}[o]
            pc += rel() if take else 2
        elif o == 0x12: r['d2'] = (((r['d2'] & 255) ^ 128) - 128) & 0xffffffff; pc += 1
        elif o == 0x81: r['d1'] = r['d0']; pc += 1
        elif o == 0x82: r['d2'] = r['d0']; pc += 1
        elif o == 0x88: r['d0'] = r['d2']; pc += 1
        elif o == 0x00: r['d0'] = 0; cmp = 0; pc += 1
        elif o == 0xe8: r['d0'] = (r['d0'] + r['d2']) & 0xffffffff; pc += 1
        elif o == 0xea: r['d2'] = (r['d2'] * 2) & 0xffffffff; pc += 1
        elif o == 0x54: r['d0'] = (r['d0'] << 2) & 0xffffffff; pc += 1
        elif o == 0x56: r['d2'] = (r['d2'] << 2) & 0xffffffff; pc += 1
        elif o == 0x29:  # add imm8,d1 (sets Z)
            r['d1'] = (r['d1'] + rel()) & 0xffffffff; cmp = s32(r['d1']); pc += 2
        elif o == 0xcb: pc += 1
        elif nx == b'\xf1\x08': r['d0'] = (r['d0'] - r['d2']) & 0xffffffff; pc += 2
        elif nx == b'\x5c\x54': pc += 2                       # mov (84,sp),a0
        elif nx == b'\xf0\x50': out = r['d0'] & 255; pc += 2  # movbu d0,(a0)
        elif nx == b'\xf0\x58': out = r['d2'] & 255; pc += 2  # movbu d2,(a0)
        else: raise SystemExit(f'unhandled opcode {nx.hex()} at {pc:#x}')
    raise SystemExit('no exit')


def check(img):
    assert hashlib.sha256(img).hexdigest() == EXPANDED_SHA, 'not E148 1.1 expanded main'
    R = lambda a, n: img[a - B:a - B + n]
    assert R(SEL, len(ORIG_SEL)) == ORIG_SEL and R(STORE, len(ORIG_TAIL)) == ORIG_TAIL
    i, k, p, p2, size, stride = struct.unpack('<HHIIHH', R(DESC_1710, 16))
    assert (i, k, p, p2, size, stride) == (1710, 0x80, OLD_LIST, 0, 4, 1)
    assert R(OLD_LIST, 4) == bytes([1, 2, 3, 4]) and R(NEW_LIST, 6) == bytes(range(1, 7))
    new = selector()
    patched = bytearray(img); patched[SEL - B:SEL - B + len(new)] = new
    stock_mem = lambda a, n: img[a - B:a - B + n]
    new_mem = lambda a, n: bytes(patched[a - B:a - B + n])
    cases = 0
    for unit in (1, 2, 3):
        for step in range(256):
            want = ('store', step * unit) if 1 <= step <= 6 else ('invalid',)
            got = run(new_mem, step, unit)
            assert got == want, (step, unit, got, want)
            if 1 <= step <= 4 or step == 0 or step > 6:   # stock behaviour unchanged there
                assert run(stock_mem, step, unit) == got, (step, unit)
            cases += 1
    edits = {hex(SEL): new.hex(),
             hex(DESC_1710 + 4): struct.pack('<I', NEW_LIST).hex(),
             hex(DESC_1710 + 12): struct.pack('<H', 6).hex()}
    return edits, cases


def write_spec(stock_path):
    here = Path(__file__).resolve().parent
    repo = here.parents[2]; sys.path.insert(0, str(repo / 'tools'))
    from oly_container import parse, replace_payload, reconstruct
    from oly_compress import expand_image, repack_image
    sha = lambda b: hashlib.sha256(b).hexdigest()
    stock = Path(stock_path).read_bytes(); blocks = parse(stock)
    main = next(b for b in blocks if b.kind == 0x100)
    orig = expand_image(main.payload)
    edits, _ = check(orig)
    target = bytearray(orig); ranges, data_edits = [], []
    names = {hex(SEL): 'nd_step_selector', hex(DESC_1710 + 4): 'nd_1710_allowed_list',
             hex(DESC_1710 + 12): 'nd_1710_allowed_count'}
    for a, h in edits.items():
        at = int(a, 16) - B; data = bytes.fromhex(h)
        ranges.append({'component': '0x100', 'name': names[a], 'address': a, 'bytes': len(data),
                       'before_sha256': sha(orig[at:at + len(data)]), 'after_sha256': sha(data)})
        data_edits.append({'component': '0x100', 'name': names[a], 'address': a, 'after': h})
        target[at:at + len(data)] = data
    packed = repack_image(main.payload, target, split=True, literal_limit=0)
    assert expand_image(packed) == target
    # main-only package, as the patcher builds it: one changed component, plus a stock restore file
    image = reconstruct([replace_payload(main, packed)])
    restore = reconstruct([main])
    spec = {'schema': 'oly-patch/1', 'name': 'OM-5 Mark II Live ND32/ND64 (experimental)',
            'model': 'OM-5 Mark II', 'firmware': '1.1 build 1100', 'camera_tested': False,
            'stock': {'sha256': sha(stock)},
            'components': {'0x100': {'cpu_base': hex(B), 'image_transform': 'olycompress',
                                     'stored_before_sha256': sha(main.payload), 'stored_after_sha256': sha(packed),
                                     'before_sha256': sha(orig), 'after_sha256': sha(target), 'repack': 'split'}},
            'ranges': ranges, 'data_edits': data_edits,
            'package': {'components': ['0x100'], 'file': 'DCOLYMP/E1489999.BIN',
                        'sha256': sha(image), 'bytes': len(image), 'restore_sha256': sha(restore)}}
    (here / 'patch.json').write_text(json.dumps(spec, indent=2) + '\n')
    print('expanded', sha(target), 'package', sha(image))


if __name__ == '__main__':
    if sys.argv[1] == '--spec':
        write_spec(sys.argv[2]); sys.exit()
    edits, cases = check(Path(sys.argv[1]).read_bytes())
    print(f'{cases} selector cases pass (steps 0..255 x units 1..3); stock unchanged for 0..4 and 7..255')
    print(json.dumps(edits, indent=1))
    if len(sys.argv) > 2: Path(sys.argv[2]).write_text(json.dumps(edits, indent=0) + '\n')
