"""Lossless expansion and bounded LZ4 repacking of main-block olycompress spans."""
import struct

MAGIC = b'olycompress' + b' ' * 5


def _length(data, pos, value):
    if value != 15:
        return value, pos
    while True:
        if pos >= len(data):
            raise ValueError('Truncated LZ4 length')
        n = data[pos]
        pos += 1
        value += n
        if n != 255:
            return value, pos


def _sequences(data, raw_size):
    """Yield (decoded literals, offset, match length, output match start)."""
    pos = 0
    out = bytearray()
    rows = []
    while pos < len(data):
        token = data[pos]
        pos += 1
        lit_len, pos = _length(data, pos, token >> 4)
        if pos + lit_len > len(data):
            raise ValueError('Truncated LZ4 literals')
        literals = bytes(data[pos:pos + lit_len])
        pos += lit_len
        out.extend(literals)
        start = len(out)
        if pos == len(data):
            rows.append((literals, 0, 0, start))
            break
        if pos + 2 > len(data):
            raise ValueError('Truncated LZ4 offset')
        offset = int.from_bytes(data[pos:pos + 2], 'little')
        pos += 2
        if not 0 < offset <= len(out):
            raise ValueError('Invalid LZ4 offset')
        match_len, pos = _length(data, pos, token & 15)
        match_len += 4
        for _ in range(match_len):
            out.append(out[-offset])
        rows.append((literals, offset, match_len, start))
    if len(out) != raw_size:
        raise ValueError(f'LZ4 raw length {len(out)} != {raw_size}')
    return bytes(out), rows


def _extra(value):
    if value < 15:
        return b''
    value -= 15
    return b'\xff' * (value // 255) + bytes([value % 255])


def _encode(literals, offset=0, match_len=0):
    result = bytearray([min(len(literals), 15) << 4 | (min(match_len - 4, 15) if offset else 0)])
    result.extend(_extra(len(literals)))
    result.extend(literals)
    if offset:
        result.extend(offset.to_bytes(2, 'little'))
        result.extend(_extra(match_len - 4))
    return result


def _split_window(target, start, length, offset, raw):
    """Encode target[start:start + length] (a stock match whose source no longer
    matches) as [(literals, offset, match_len)] using the stock offset where the
    bytes still agree and offset-1 runs elsewhere, so the patched stream keeps
    short literal runs. Matches stay at least 12 bytes before the end of the
    span and end at least 5 bytes before it (LZ4 block rules)."""
    out, lits, i, end = [], bytearray(), start, start + length
    while i < end:
        best = None
        for off in (offset, 1):
            if not 0 < off <= i:
                continue
            n = 0
            while i + n < end and target[i + n] == target[i + n - off]:
                n += 1
            if n >= 16 and (best is None or n > best[1]):
                best = (off, n)
        if best and i <= raw - 12:
            off, n = best
            n = min(n, raw - 5 - i)
            if n >= 4:
                out.append((bytes(lits), off, n))
                lits.clear()
                i += n
                continue
        lits.append(target[i])
        i += 1
    return out, bytes(lits)


def _repack(original, target, rows, split=False):
    pending = bytearray()
    packed = bytearray()
    at = 0
    raw = len(target)
    for literals, offset, match_len, start in rows:
        pending.extend(target[at:start])
        at = start
        if offset:
            # Keep a match only if replaying it from the already patched output
            # gives precisely the requested bytes, including overlapping copies.
            if target[start:start + match_len] == target[start - offset:start - offset + match_len]:
                packed.extend(_encode(pending, offset, match_len))
                pending.clear()
            elif split:
                parts, rest = _split_window(target, start, match_len, offset, raw)
                for lits, off, n in parts:
                    pending.extend(lits)
                    packed.extend(_encode(pending, off, n))
                    pending.clear()
                pending.extend(rest)
            else:
                pending.extend(target[start:start + match_len])
            at += match_len
    packed.extend(_encode(pending))
    decoded, _ = _sequences(packed, len(target))
    if decoded != target:
        raise ValueError('Repacked LZ4 does not match expanded target')
    return bytes(packed)


def max_literal_run(data, raw):
    """Longest literal run of an LZ4 block (for comparison with the stock stream)."""
    _, rows = _sequences(data, raw)
    return max(len(r[0]) for r in rows)


def spans(stored):
    p = 0
    result = []
    while (p := stored.find(MAGIC, p)) >= 0:
        if p + 32 > len(stored):
            raise ValueError('Truncated olycompress header')
        packed, raw = struct.unpack_from('<II', stored, p + 16)
        if stored[p + 24:p + 32] != bytes(8) or p + 32 + packed > len(stored) or p + raw > len(stored):
            raise ValueError('Invalid olycompress span')
        result.append((p, packed, raw))
        p += raw
    return result


def expand_image(stored):
    result = bytearray(stored)
    for p, packed, raw in spans(stored):
        data, _ = _sequences(stored[p + 32:p + 32 + packed], raw)
        result[p:p + raw] = data
    return bytes(result)


def repack_image(stored, target, split=False, literal_limit=None):
    if len(stored) != len(target):
        raise ValueError('Expanded image size changed')
    original = expand_image(stored)
    result = bytearray(stored)
    ranges = spans(stored)
    for p, packed, raw in ranges:
        if original[p:p + raw] == target[p:p + raw]:
            continue
        _, rows = _sequences(stored[p + 32:p + 32 + packed], raw)
        data = _repack(original[p:p + raw], target[p:p + raw], rows, split)
        if literal_limit is not None:
            stock_max = max(len(r[0]) for r in rows)
            if max_literal_run(data, raw) > max(stock_max, literal_limit):
                raise ValueError(f'olycompress at {p:#x}: literal run {max_literal_run(data, raw)} exceeds '
                                 f'the stock maximum {stock_max}')
        if len(data) + 32 > raw:
            raise ValueError(f'olycompress at {p:#x} exceeds its {raw} byte span')
        result[p:p + raw] = bytes([255]) * raw
        result[p:p + 16] = MAGIC
        struct.pack_into('<II', result, p + 16, len(data), raw)
        result[p + 24:p + 32] = bytes(8)
        result[p + 32:p + 32 + len(data)] = data
    end = 0
    for p, _, raw in ranges:
        result[end:p] = target[end:p]
        end = p + raw
    result[end:] = target[end:]
    if expand_image(result) != target:
        raise ValueError('Repacked image round trip failed')
    return bytes(result)
