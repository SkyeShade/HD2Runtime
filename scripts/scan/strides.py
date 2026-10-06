"""Array and struct-stride discovery in raw bytes (research only).

Typed records already carry their inline-array strides; this is for memory the type library does not describe: the
per-instance blocks of component managers in retained snapshots, runtime arrays, and unknown tails.

Each 4-byte word is classified into a token (zero, small integer, plausible float, pointer-like, hash-like, other).
A stride S (a multiple of 4) is scored by how often word i and word i + S/4 share a token over the window; the best
strides are then split into elements and every column is described (constant, varying, its token).
"""
from __future__ import annotations

from collections import Counter
import math
import struct

ZERO, SMALL, FLOAT, POINTER, HASH, OTHER = 'zero', 'small_int', 'float', 'pointer', 'hash', 'other'


def token(word: int) -> str:
    if word == 0:
        return ZERO
    if word < 0x10000 or word >= 0xFFFF0000:
        return SMALL
    value = struct.unpack('<f', struct.pack('<I', word))[0]
    if math.isfinite(value) and 1e-4 <= abs(value) <= 1e7:
        return FLOAT
    return HASH


def tokens(raw: bytes, base: int = 0) -> list[str]:
    """One token per aligned 4-byte word. 8-byte aligned words that look like user-mode pointers mark both halves."""
    count = len(raw) // 4
    words = struct.unpack('<%dI' % count, raw[:count * 4])
    out = [token(word) for word in words]
    for index in range(0, count - 1, 2):
        # 64-bit Windows heap and module addresses have a high dword of 0x100..0x7FFF; a small integer next to a
        # 32-bit value (high dword 1..0xFF) is not a pointer.
        if 0x100 <= words[index + 1] <= 0x7FFF and (base + index * 4) % 8 == 0:
            out[index] = out[index + 1] = POINTER
    return out


def score_strides(raw: bytes, min_stride: int = 8, max_stride: int = 512, base: int = 0) -> list[dict]:
    """Strides ranked by token periodicity (agreement over non-zero words), best first."""
    seq = tokens(raw, base)
    # Zero and small integers compare as one class (flags and indices are often zero), but a pair of zeros carries
    # no information and is skipped.
    cls = ['int' if t in (ZERO, SMALL) else t for t in seq]
    results = []
    for stride in range(min_stride, min(max_stride, len(raw) // 2) + 1, 4):
        lag = stride // 4
        compared = agree = informative = 0
        for i in range(len(seq) - lag):
            if seq[i] == ZERO and seq[i + lag] == ZERO:
                continue
            compared += 1
            if cls[i] == cls[i + lag]:
                agree += 1
                if cls[i] != 'int':
                    informative += 1
        if compared >= 8:
            score = agree / compared
            results.append({'stride': stride, 'score': round(score, 4), 'compared': compared,
                'informative': informative})
    # Prefer the fundamental: a multiple of a stride that scores nearly as well is a harmonic, not a new stride.
    kept = [r for r in results if not any(q['stride'] < r['stride'] and r['stride'] % q['stride'] == 0
        and q['score'] >= r['score'] - 0.05 for q in results)]
    kept.sort(key=lambda r: (-r['score'], r['stride']))
    return kept[:8]


def columns(raw: bytes, stride: int, start: int = 0, count: int | None = None) -> dict:
    """Split ``raw`` into ``count`` elements of ``stride`` bytes from ``start`` and describe each 4-byte column."""
    available = (len(raw) - start) // stride
    count = available if count is None else min(count, available)
    cols = []
    for offset in range(0, stride - 3, 4):
        words = [struct.unpack_from('<I', raw, start + i * stride + offset)[0] for i in range(count)]
        kinds = Counter(token(word) for word in words)
        floats = [struct.unpack('<f', struct.pack('<I', w))[0] for w in words]
        column = {'offset': offset, 'tokens': dict(kinds), 'distinct': len(set(words)),
            'constant': len(set(words)) == 1}
        if kinds.get(FLOAT, 0) + kinds.get(ZERO, 0) == count and kinds.get(FLOAT):
            column['floatRange'] = [round(min(floats), 6), round(max(floats), 6)]
        elif kinds.get(SMALL, 0) + kinds.get(ZERO, 0) == count:
            column['intRange'] = [min(words), max(words)]
        cols.append(column)
    return {'stride': stride, 'start': start, 'elements': count, 'columns': cols}


def runs(raw: bytes, stride: int, key_offset: int = 0, predicate=None) -> list[tuple[int, int]]:
    """Maximal runs of consecutive elements whose key word satisfies ``predicate`` (default: non-zero):
    (start offset, element count). Finds the occupied part of a fixed-capacity array."""
    predicate = predicate or (lambda word: word != 0)
    out, start, length = [], None, 0
    for at in range(0, len(raw) - stride + 1, stride):
        word = struct.unpack_from('<I', raw, at + key_offset)[0]
        if predicate(word):
            if start is None:
                start, length = at, 0
            length += 1
        elif start is not None:
            out.append((start, length))
            start = None
    if start is not None:
        out.append((start, length))
    return out
