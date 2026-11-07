"""Decode a captured OM-3 queue-95 envelope offline; never connects to a camera.

python scripts/decode_om3_queue95.py --request HEX [--payload HEX] [--reply HEX]
The payload bytes must be supplied separately: its address is camera RAM.
"""
import argparse
import json
from pathlib import Path
import struct

MAP = Path(__file__).resolve().parents[1] / 'analysis/review/queue95/dispatch-map.json'
if not MAP.exists():
    MAP = Path(__file__).resolve().parents[1] / 'recorded-evidence/review/queue95/dispatch-map.json'
GUARD_EXCEPTIONS = {0x50, 0x4a, 0x4b, 0x53, 0x54, 0x51, 0x55, 0x5a}

def decode_request(raw, payload=None):
    if len(raw) != 16:
        raise ValueError('Queue-95 request must be exactly 16 bytes')
    reply_queue, token, command, pointer = struct.unpack('<4I', raw)
    entries = json.loads(MAP.read_text(encoding='utf-8'))
    entry = entries[command] if command < len(entries) else None
    result = {'reply_queue_word': reply_queue, 'reply_requested': reply_queue != 0,
              'correlation_word': f'{token:08x}', 'command': command,
              'command_hex': f'0x{command:x}', 'payload_pointer': f'{pointer:08x}',
              'dispatch_entry': entry,
              'guard': 'may be deferred if context+0x94 bit 0x8000 is set'
                       if command not in GUARD_EXCEPTIONS else 'exempt from this specific deferral guard'}
    if command in (0x2a, 0x2b, 0x2c) and payload is not None:
        if len(payload) < 8:
            raise ValueError('AF start/end payload requires at least 8 supplied bytes')
        kind, flags = struct.unpack_from('<2I', payload)
        branch = ('lock' if flags & 4 else 'IAF pause/restart' if flags & 8
                  else 'take-once' if flags & 0x10 else 'invalid operation selection')
        result['af_payload'] = {'kind_word': kind, 'flags_word': f'{flags:08x}',
                                'selected_branch': branch,
                                'high_bit_set': bool(flags & 0x80000000)}
        if command == 0x2c:
            result['af_payload']['selected_branch'] = 'kind-5 end-then-lock-start transition (flags overwritten to 4)'
            result['af_payload']['alternate_start'] = (
                'requires kind=5; overwrites flags with 4, calls end helper with D0=1, '
                'then starts through 603c895e only when its checks permit it')
    return result

def decode_reply(raw):
    if len(raw) != 12:
        raise ValueError('Common reply must be exactly 12 bytes')
    status = struct.unpack_from('<H', raw)[0]
    token, pointer = struct.unpack_from('<2I', raw, 4)
    return {'status_u16': f'{status:04x}',
            'status_note': {0: 'zero handler status, subject to global override',
                            0x4b00: 'seen on invalid/state-rejected AF branches',
                            0x4b01: 'out-of-range or unsupported-command status'}.get(status, 'not semantically decoded'),
            'padding_2_3_hex': raw[2:4].hex(), 'correlation_word': f'{token:08x}',
            'payload_pointer': f'{pointer:08x}',
            'limit': 'reply status alone does not prove focus acquisition'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True, help='16-byte request in hexadecimal')
    parser.add_argument('--payload', help='separate payload bytes in hexadecimal')
    parser.add_argument('--reply', help='12-byte common reply in hexadecimal')
    args = parser.parse_args()
    try:
        result = decode_request(bytes.fromhex(args.request), bytes.fromhex(args.payload) if args.payload else None)
        if args.reply:
            result['reply'] = decode_reply(bytes.fromhex(args.reply))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
