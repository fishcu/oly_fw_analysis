"""Canonical fixed-quarter five-point state and integer reference transfer."""
from dataclasses import dataclass

TAG = 0xb0000000
LEGACY_TAG = 0xa5d00000
LEGACY_NEUTRAL = 0xa5dffc00
DEFAULT_HEIGHTS = (0, 256, 512, 768, 1023)


def quantize(value):
    return 1023 if value >= 1008 else min(992, ((max(0, value) + 7) // 16) * 16)


@dataclass(frozen=True)
class FivePoints:
    heights: tuple[int, int, int, int, int] = DEFAULT_HEIGHTS

    def __post_init__(self):
        y = self.heights
        if (len(y) != 5 or any(type(v) is not int for v in y)
                or not 0 <= y[0] <= y[1] <= y[2] <= y[3] <= y[4] <= 1023
                or not 288 <= y[2] <= 736 or y[2] % 32
                or any(v != 1023 and v % 16 for i, v in enumerate(y) if i != 2)):
            raise ValueError('Expected five ordered representable heights')

    @property
    def middle(self):
        return (self.heights[2] - 512) // 32

    def pack(self):
        b, s, m, h, w = self.heights
        return TAG | b // 16 | (s // 16) << 6 | (h // 16) << 12 | (w // 16) << 18 | ((m - 288) // 32) << 24

    def edit(self, axis, command):
        if axis not in range(5) or command not in (-1, 0, 1):
            raise ValueError('Expected axis0..4 and decrease/reset/increase command')
        y = list(self.heights)
        lower = y[axis - 1] if axis else 0
        upper = y[axis + 1] if axis < 4 else 1023
        value = DEFAULT_HEIGHTS[axis] if command == 0 else y[axis] + command * (32 if axis == 2 else 16)
        if axis == 2:
            lower = max(288, (lower + 31) // 32 * 32)
            upper = min(736, upper // 32 * 32)
        else:
            value = quantize(value)
        y[axis] = max(lower, min(upper, value))
        return FivePoints(tuple(y))

    def apply(self, values):
        result = []
        for x in values:
            if type(x) is not int or not 0 <= x <= 1023:
                raise ValueError('Transfer input must be ten-bit')
            t = 4 * x
            k = min(3, t // 1023)
            u = t - k * 1023
            result.append(self.heights[k] + u * (self.heights[k + 1] - self.heights[k]) // 1023)
        return tuple(result)


def decode(word):
    if type(word) is not int or not 0 <= word <= 0xffffffff or word >> 28 != 11:
        return None
    codes = [(word >> shift) & 63 for shift in (0, 6, 12, 18)]
    heights = [1023 if q == 63 else q * 16 for q in codes]
    middle_code = (word >> 24) & 15
    if middle_code == 15:
        return None
    try:
        return FivePoints(tuple(heights[:2] + [288 + 32 * middle_code] + heights[2:]))
    except ValueError:
        return None


def resolve(word, raw_hml):
    current = decode(word)
    if current is not None:
        return current
    if len(raw_hml) != 3 or any(type(v) is not int or not -7 <= v <= 7 for v in raw_hml):
        return FivePoints()
    high, middle, low = raw_hml
    m = 512 + 32 * middle
    s = min(256 + 16 * low, m)
    h = max(768 + 16 * high, m)
    b, w = ((word & 1023, (word >> 10) & 1023)
            if word >> 20 == 0xa5d else (0, 1023))
    return FivePoints((min(quantize(b), s), s, m, h, max(quantize(w), h)))
