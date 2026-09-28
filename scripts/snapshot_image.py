"""Read a loaded module image out of a retained HD2SNAP snapshot. Read-only research helper.

Mirrors the header/index decoding of core/snapshot_format.lua. `module_image('game.dll')`
returns (base, bytes) for the whole mapped image, with uncaptured pages left as zeros.
The on-disk game.dll is packed; the snapshot holds the unpacked image the game executes.
"""
from __future__ import annotations

import bisect
from pathlib import Path
import struct

MAGIC = b'HD2SNAP\0'
CAPTURED = 1


class Snapshot:
    def __init__(self, path: Path):
        self.handle = open(path, 'rb')
        preamble = self.handle.read(16)
        if preamble[:8] != MAGIC or struct.unpack_from('<I', preamble, 8)[0] != 1:
            raise ValueError('unsupported snapshot format')
        length = struct.unpack_from('<I', preamble, 12)[0]
        self.handle.seek(0)
        header = self.handle.read(length)
        at = 16
        _, regions, modules, _, _, _ = struct.unpack_from('<6I', header, at)
        at += 24
        at += 32  # maximum address, total virtual, total captured, capture time
        self.executable_sha256 = header[at:at + 64].decode()
        self.game_dll_sha256 = header[at + 64:at + 128].decode()
        at += 128

        def text():
            nonlocal at
            size = struct.unpack_from('<I', header, at)[0]
            at += 4
            value = header[at:at + size]
            at += size
            return value

        for _ in range(3):
            text()
        at += 64  # diagnostics counters
        self.modules = {}
        for _ in range(modules):
            name = text().decode().lower()
            base, size = struct.unpack_from('<QQ', header, at)
            at += 16
            self.modules[name] = {'base': base, 'size': size, 'sha256': header[at:at + 64].decode()}
            at += 64
        self.regions = []
        for _ in range(regions):
            row = struct.unpack_from('<QQQIIIIQQII', header, at)
            at += 64
            self.regions.append({'base': row[0], 'allocation_base': row[1], 'size': row[2], 'state': row[3],
                'type': row[4], 'protect': row[5], 'status': row[6], 'data_offset': row[8]})
        self.bases = [region['base'] for region in self.regions]

    def region(self, address: int):
        index = bisect.bisect_right(self.bases, address) - 1
        if index < 0:
            return None
        region = self.regions[index]
        return region if address < region['base'] + region['size'] else None

    def module_image(self, name: str) -> tuple[int, bytes]:
        module = self.modules[name.lower()]
        base, size = module['base'], module['size']
        image = bytearray(size)
        address = base
        while address < base + size:
            region = self.region(address)
            if region is None:
                index = bisect.bisect_right(self.bases, address)
                address = self.bases[index] if index < len(self.bases) else base + size
                continue
            end = min(region['base'] + region['size'], base + size)
            if region['status'] == CAPTURED:
                self.handle.seek(region['data_offset'] + address - region['base'])
                image[address - base:end - base] = self.handle.read(end - address)
            address = end
        return base, bytes(image)

    def close(self):
        self.handle.close()
