"""Read-only access to resources of the installed (slim) Helldivers 2 data folder (research only).

Port of HD2RuntimeGUI.Core/GameAssets/GameDataReader.cs (Filediver's documented layout): DSAR bundles (LZ4 chunks),
the bundles.nxa DSAA index, Stingray archive tables (0xF0000011). Also returns the .stream and .gpu_resources parts.
Nothing is written to the game folder."""
import os
import struct

DATA = r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\data'
TEXTURE = 'texture'


def murmur64(data: bytes) -> int:
    m, mask = 0xC6A4A7935BD1E995, (1 << 64) - 1
    h = (len(data) * m) & mask
    whole = len(data) // 8 * 8
    for i in range(0, whole, 8):
        k = (int.from_bytes(data[i:i + 8], 'little') * m) & mask
        k ^= k >> 47
        h = ((h ^ ((k * m) & mask)) * m) & mask
    if whole != len(data):
        t = int.from_bytes(data[whole:], 'little')
        h = ((h ^ t) * m) & mask
    h ^= h >> 47
    h = (h * m) & mask
    return h ^ (h >> 47)


def lz4_block(src: bytes, size: int) -> bytes:
    dst = bytearray(size)
    s = d = 0
    while s < len(src):
        token = src[s]; s += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[s]; s += 1; lit += b
                if b != 255:
                    break
        dst[d:d + lit] = src[s:s + lit]; s += lit; d += lit
        if s >= len(src):
            break
        off = src[s] | src[s + 1] << 8; s += 2
        match = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                b = src[s]; s += 1; match += b
                if b != 255:
                    break
        for _ in range(match):
            dst[d] = dst[d - off]; d += 1
    return bytes(dst)


def dsar(path):
    with open(path, 'rb') as f:
        head = f.read(32)
        assert head[:4] == b'DSAR', path
        count = struct.unpack_from('<I', head, 8)[0]
        raw = f.read(32 * count)
    return [struct.unpack_from('<QQIIB', raw, 32 * i) for i in range(count)]  # uoff, coff, usize, csize, comp


def chunk(path, c):
    uoff, coff, usize, csize, comp = c
    with open(path, 'rb') as f:
        f.seek(coff)
        data = f.read(csize)
    if comp == 0:
        return data
    assert comp == 3, comp
    return lz4_block(data, usize)


class Data:
    def __init__(self, folder=DATA):
        self.folder = folder
        nxa = os.path.join(folder, 'bundles.nxa')
        index = b''.join(chunk(nxa, c) for c in dsar(nxa))
        assert index[:4] == b'DSAA'
        nxa_count, item_count = struct.unpack_from('<II', index, 12)
        items = [struct.unpack_from('<QIIQ', index, 24 + 24 * i) for i in range(item_count)]
        name_offsets = [struct.unpack_from('<I', index, 24 + 24 * item_count + 4 * i)[0] for i in range(nxa_count)]
        cstr = lambda o: index[o:index.index(b'\0', o)].decode()
        self.bundles = []
        for o in name_offsets:
            path = os.path.join(folder, cstr(o))
            self.bundles.append((path, dsar(path)))
        self.items = {}
        for size, name_off, count, entries_off in items:
            name = cstr(name_off)
            entries = [(struct.unpack_from('<I', index, entries_off + 16 * i)[0],
                struct.unpack_from('<I', index, entries_off + 16 * i + 8)[0], index[entries_off + 16 * i + 15])
                for i in range(count)]
            self.items[name] = (size, entries)

    def item_bytes(self, name, start=0, length=None):
        size, entries = self.items[name]
        length = size - start if length is None else length
        out = bytearray()
        for i, (aoff, boff, bidx) in enumerate(entries):
            end = entries[i + 1][0] if i + 1 < len(entries) else size
            if end <= start or aoff >= start + length:
                continue
            path, chunks = self.bundles[bidx]
            ci = next(k for k, c in enumerate(chunks) if c[0] == boff)
            pos = aoff
            while pos < end:
                data = chunk(path, chunks[ci]); ci += 1
                seg_start, seg_end = pos, pos + len(data)
                lo, hi = max(seg_start, start), min(seg_end, start + length)
                if lo < hi:
                    out += data[lo - seg_start:hi - seg_start]
                pos = seg_end
                if pos >= start + length:
                    break
        return bytes(out)

    def tables(self):
        for name in sorted(self.items):
            if '.' in name or len(name) != 16:
                continue
            head = self.item_bytes(name, 0, 72)
            if len(head) < 72 or struct.unpack_from('<I', head)[0] != 0xF0000011:
                continue
            types, files = struct.unpack_from('<II', head, 4)
            table = self.item_bytes(name, 0, 72 + 32 * types + 80 * files)
            start = 72 + 32 * types
            for i in range(files):
                e = table[start + 80 * i:start + 80 * (i + 1)]
                rname, rtype, omain, ostream, ogpu = struct.unpack_from('<QQQQQ', e)
                smain, sstream, sgpu = struct.unpack_from('<III', e, 56)
                yield name, rname, rtype, (omain, smain), (ostream, sstream), (ogpu, sgpu)

    def find(self, wanted):
        """{(name hash, type hash): (archive, main, stream, gpu)} for the wanted resources."""
        found = {}
        for archive, rname, rtype, main, stream, gpu in self.tables():
            if (rname, rtype) in wanted and (rname, rtype) not in found:
                found[(rname, rtype)] = (archive, main, stream, gpu)
                if len(found) == len(wanted):
                    break
        return found

    def read(self, archive, part, suffix=''):
        offset, size = part
        name = archive + suffix
        if name not in self.items or size == 0:
            return b''
        return self.item_bytes(name, offset, size)
