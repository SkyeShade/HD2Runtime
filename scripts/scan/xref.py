"""Cross-references from candidate fields into native code (research only).

``CodeImage`` is an unpacked module image (game.dll or the executable) taken from a retained snapshot (the on-disk
game.dll is packed) and cached under build/scan-cache, keyed by the module's SHA-256 and size. It provides:

* the .pdata function map (``chunk``, ``root``: chained unwind info followed to the primary function);
* memory-light reference scans over .text (one int32 view per byte phase, every hit re-decoded): rip-relative
  references to a global (``references``), rel32 call/jump sites (``calls_to``), 32-bit immediates (``immediates``),
  string references (``string_refs``);
* ``field_accesses``: every [reg + disp] operand of a function whose displacement is one of the candidate offsets,
  with access size, read/write and float use (movss/comiss/mulss/... mark a float read);
* ``reachable``: recursive-descent instruction starts of a function (tail jumps to other functions not followed);
* ``global_accessors``: the functions that reference a global (e.g. a component manager), the usual first step from
  a component to the code that reads its fields;
* ``pin``: a reviewed instruction pin {rva, bytes, asm, role} in the format the research JSON files use.

Every result is an address in the analysed image. Nothing is written anywhere; research only.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys

import capstone
from capstone import x86
import numpy

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import snapshot_image  # noqa: E402

CACHE = ROOT / 'build/scan-cache'
FLOAT_MNEMONICS = ('movss', 'comiss', 'ucomiss', 'addss', 'subss', 'mulss', 'divss', 'minss', 'maxss', 'cvtss2sd',
    'cvttss2si', 'cvtss2si', 'sqrtss', 'vmovss', 'vcomiss', 'vucomiss', 'vaddss', 'vsubss', 'vmulss', 'vdivss',
    'vminss', 'vmaxss', 'vfmadd', 'vfmsub', 'vfnmadd', 'movaps', 'movups', 'vmovaps', 'vmovups', 'shufps',
    'insertps', 'vinsertps', 'movd', 'vmovd', 'movsd', 'vbroadcastss', 'unpcklps', 'movlps', 'movhps')
DEFAULT_SNAPSHOT = 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'


def _module_key(snapshot: snapshot_image.Snapshot, module: str) -> tuple[str, int]:
    info = snapshot.modules[module.lower()]
    return info['sha256'] or 'unknown', info['size']


def load_image(module: str = 'game.dll', snapshot: str | None = None) -> tuple[int, bytes, str]:
    """(base, image bytes, module sha256) from a retained snapshot, cached on disk."""
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / (snapshot or DEFAULT_SNAPSHOT))
    try:
        name = module.lower()
        if name in ('exe', 'executable'):
            name = next(key for key in snap.modules if key.endswith('.exe'))
        digest, size = _module_key(snap, name)
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f'{name}-{digest[:16]}-{size:x}.bin'
        base = snap.modules[name]['base']
        if path.is_file() and path.stat().st_size == size:
            return base, path.read_bytes(), digest
        base, data = snap.module_image(name)
        path.write_bytes(data)
        return base, data, digest
    finally:
        snap.close()


class CodeImage:
    def __init__(self, data: bytes, base: int = 0, name: str = 'game.dll', sha256: str | None = None):
        self.data, self.base, self.name, self.sha256 = data, base, name, sha256
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.lite = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        pe = struct.unpack_from('<I', data, 60)[0]
        if data[pe:pe + 4] != b'PE\0\0':
            raise ValueError('not a PE image')
        self.image_size = struct.unpack_from('<I', data, pe + 80)[0]
        sections = struct.unpack_from('<H', data, pe + 6)[0]
        optional = struct.unpack_from('<H', data, pe + 20)[0]
        at = pe + 24 + optional
        self.sections = {}
        for i in range(sections):
            name = data[at:at + 8].rstrip(b'\0').decode('latin-1')
            vsize, vaddr = struct.unpack_from('<II', data, at + 8)
            self.sections[name] = (vaddr, vaddr + vsize)
            at += 40
        exc_rva, exc_size = struct.unpack_from('<II', data, pe + 24 + 112 + 3 * 8)
        table = numpy.frombuffer(data[exc_rva:exc_rva + exc_size // 12 * 12], dtype='<u4').reshape(-1, 3)
        table = table[(table[:, 0] < table[:, 1]) & (table[:, 1] <= len(data))]
        order = numpy.argsort(table[:, 0], kind='stable')
        self.pdata = table[order]
        self.pdata_begin = self.pdata[:, 0].astype(numpy.int64)
        # The shipped modules are protected: the section table no longer names the original code section (the
        # protector's sections start after it). The code range is the extent of the exception directory's functions
        # below the first listed section (0x1000.. for game.dll and the executable).
        first_section = min(start for start, _ in self.sections.values()) if self.sections else len(data)
        original = self.pdata[self.pdata[:, 1] <= first_section]
        if len(original) == 0:
            original = self.pdata
        self.text = (int(original[:, 0].min()), int(original[:, 1].max()))
        self._phases = None

    @classmethod
    def from_snapshot(cls, module: str = 'game.dll', snapshot: str | None = None) -> 'CodeImage':
        base, data, digest = load_image(module, snapshot)
        return cls(data, base, module, digest)

    # -- raw reads -------------------------------------------------------------------------------------------
    def u32(self, rva): return struct.unpack_from('<I', self.data, rva)[0]
    def u64(self, rva): return struct.unpack_from('<Q', self.data, rva)[0]
    def f32(self, rva): return struct.unpack_from('<f', self.data, rva)[0]

    def cstr(self, rva):
        return self.data[rva:self.data.index(b'\0', rva)].decode('latin-1')

    # -- functions -------------------------------------------------------------------------------------------
    def chunk(self, rva):
        i = int(numpy.searchsorted(self.pdata_begin, rva, side='right')) - 1
        if i >= 0 and self.pdata[i, 0] <= rva < self.pdata[i, 1]:
            return int(self.pdata[i, 0]), int(self.pdata[i, 1])
        return None

    def root(self, rva):
        """The primary function start of the chunk containing rva (chained unwind info followed)."""
        chunk = self.chunk(rva)
        if not chunk:
            return None
        i = int(numpy.searchsorted(self.pdata_begin, chunk[0], side='right')) - 1
        unwind, begin = int(self.pdata[i, 2]), chunk[0]
        for _ in range(16):
            if not (self.data[unwind] >> 3) & 4:
                break
            count = self.data[unwind + 2]
            at = unwind + 4 + ((count + 1) & ~1) * 2
            begin, _, unwind = struct.unpack_from('<III', self.data, at)
        return begin

    def insn(self, rva):
        found = next(self.md.disasm(self.data[rva:rva + 16], rva, 1), None)
        if found is None:
            raise ValueError('undecodable instruction at %x' % rva)
        return found

    def disasm(self, start, end=None):
        if end is None:
            chunk = self.chunk(start)
            end = chunk[1] if chunk else start + 0x400
        return list(self.md.disasm(self.data[start:end], start))

    def reachable(self, start, limit=40000) -> dict:
        seen, work = {}, [start]
        lo, hi = self.text
        while work and len(seen) < limit:
            a = work.pop()
            while a not in seen and lo <= a < hi:
                ins = next(self.md.disasm(self.data[a:a + 16], a, 1), None)
                if ins is None:
                    break
                seen[a] = ins
                if ins.mnemonic in ('ret', 'int3', 'ud2'):
                    break
                if ins.mnemonic == 'jmp':
                    op = ins.operands[0]
                    if op.type == x86.X86_OP_IMM:
                        target = self.chunk(op.imm)
                        if not (target and target[0] == op.imm and op.imm != start):
                            work.append(op.imm)
                    break
                if ins.mnemonic.startswith('j') and ins.operands and ins.operands[0].type == x86.X86_OP_IMM:
                    work.append(ins.operands[0].imm)
                a += ins.size
        return seen

    def function_insns(self, rva) -> list:
        root = self.root(rva) or rva
        return [ins for _, ins in sorted(self.reachable(root).items())]

    @staticmethod
    def rip_target(insn):
        for op in insn.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base == x86.X86_REG_RIP:
                return insn.address + insn.size + op.mem.disp
        return None

    def calls_in(self, rva) -> list[int]:
        """Direct call targets of a function (in order of address)."""
        out = []
        for ins in self.function_insns(rva):
            if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type == x86.X86_OP_IMM:
                out.append(ins.operands[0].imm)
        return out

    # -- reference scans -------------------------------------------------------------------------------------
    def _phase_keys(self):
        if self._phases is None:
            self._phases = []
            lo, hi = self.text
            size = hi - lo
            for phase in range(4):
                count = (size - phase) // 4
                view = numpy.frombuffer(self.data, dtype='<i4', offset=lo + phase, count=count)
                positions = numpy.arange(count, dtype=numpy.int64) * 4 + lo + phase
                self._phases.append(positions + 4 + view.astype(numpy.int64))
        return self._phases

    def _decode_covering(self, disp_at, tail):
        """The instruction whose 32-bit field at disp_at ends tail bytes before the instruction end."""
        chunk = self.chunk(disp_at)
        if not chunk:
            return None
        for address, size, _, _ in self.lite.disasm_lite(self.data[chunk[0]:chunk[1]], chunk[0]):
            if address <= disp_at < address + size:
                return address if address + size == disp_at + 4 + tail else None
            if address > disp_at:
                return None
        return None

    def references(self, target) -> list:
        """Validated instructions whose rip displacement or rel32 resolves to target (globals, calls, jumps)."""
        found = {}
        lo = self.text[0]
        for phase, keys in enumerate(self._phase_keys()):
            for tail in (0, 1, 2, 4):
                for hit in numpy.nonzero(keys == target - tail)[0]:
                    address = self._decode_covering(lo + phase + int(hit) * 4, tail)
                    if address is not None:
                        found[address] = self.insn(address)
        return [found[a] for a in sorted(found)]

    def _call_index(self):
        """(sorted targets, their E8/E9 positions) of every byte in .text that could start a rel32 call or jmp: built
        once (one pass), so a caller lookup costs a binary search plus re-decoding its few hits."""
        if getattr(self, '_calls', None) is None:
            lo, hi = self.text
            raw = numpy.frombuffer(self.data, dtype=numpy.uint8, offset=lo, count=hi - lo - 4)
            positions = numpy.nonzero((raw == 0xE8) | (raw == 0xE9))[0].astype(numpy.int64)
            words = numpy.frombuffer(self.data, dtype=numpy.uint8, offset=lo, count=hi - lo)
            rel = (words[positions + 1].astype(numpy.int64) | (words[positions + 2].astype(numpy.int64) << 8)
                | (words[positions + 3].astype(numpy.int64) << 16) | (words[positions + 4].astype(numpy.int64) << 24))
            rel = numpy.where(rel >= 1 << 31, rel - (1 << 32), rel)
            targets = positions + lo + 5 + rel
            order = numpy.argsort(targets, kind='stable')
            self._calls = (targets[order], positions[order] + lo)
        return self._calls

    def calls_to(self, target) -> list[int]:
        """Direct call and jmp sites of target (rel32), each re-decoded: an E8/E9 byte inside another instruction is
        not a site. Same result as filtering references(target) to calls and jumps, without its full scan."""
        targets, positions = self._call_index()
        first = int(numpy.searchsorted(targets, target, side='left'))
        last = int(numpy.searchsorted(targets, target, side='right'))
        found = []
        for at in sorted(int(p) for p in positions[first:last]):
            if self._decode_covering(at + 1, 0) == at:
                ins = self.insn(at)
                if ins.mnemonic in ('call', 'jmp'):
                    found.append(at)
        return found

    def global_accessors(self, global_rva) -> dict[int, list[int]]:
        """Function root -> instruction addresses that reference the global."""
        result = {}
        for ins in self.references(global_rva):
            if ins.mnemonic in ('call', 'jmp'):
                continue
            root = self.root(ins.address)
            result.setdefault(root, []).append(ins.address)
        return result

    def immediates(self, value: int, width: int = 4, limit: int = 2000) -> list:
        """Instructions in .text that carry ``value`` as an immediate (or a displacement) of ``width`` bytes."""
        lo, hi = self.text
        needle = value.to_bytes(width, 'little', signed=value < 0)
        found, at = {}, self.data.find(needle, lo, hi)
        while at >= 0 and len(found) < limit:
            chunk = self.chunk(at)
            if chunk:
                for address, size, _, _ in self.lite.disasm_lite(self.data[chunk[0]:chunk[1]], chunk[0]):
                    if address <= at < address + size:
                        if at + width <= address + size:
                            ins = self.insn(address)
                            if any(op.type == x86.X86_OP_IMM and (op.imm & ((1 << (8 * width)) - 1)) ==
                                   (value & ((1 << (8 * width)) - 1)) for op in ins.operands) or any(
                                    op.type == x86.X86_OP_MEM and op.mem.disp == value for op in ins.operands):
                                found[address] = ins
                        break
                    if address > at:
                        break
            at = self.data.find(needle, at + 1, hi)
        return [found[a] for a in sorted(found)]

    def find_bytes(self, needle: bytes, section: str | None = None) -> list[int]:
        lo, hi = self.sections[section] if section else (0, len(self.data))
        out, at = [], self.data.find(needle, lo, hi)
        while at >= 0:
            out.append(at)
            at = self.data.find(needle, at + 1, hi)
        return out

    def string_refs(self, text: str) -> dict[int, list[int]]:
        """String RVA -> instructions referencing it (exact NUL-terminated ASCII strings)."""
        result = {}
        for at in self.find_bytes(text.encode('latin-1') + b'\0'):
            if at and self.data[at - 1] != 0:
                continue
            result[at] = [ins.address for ins in self.references(at)]
        return result

    # -- field access ----------------------------------------------------------------------------------------
    def field_accesses(self, rva, offsets=None, include_rsp=False) -> list[dict]:
        """Every [reg + disp] operand of the function containing rva, optionally only the given displacements.
        Each item: rva, asm, disp, base/index registers, size, write (destination memory), float (float-domain
        mnemonic)."""
        wanted = set(offsets) if offsets is not None else None
        out = []
        for ins in self.function_insns(rva):
            for position, op in enumerate(ins.operands):
                if op.type != x86.X86_OP_MEM or op.mem.base == x86.X86_REG_RIP:
                    continue
                base = ins.reg_name(op.mem.base) if op.mem.base else None
                if not include_rsp and base in ('rsp', 'rbp') and op.mem.index == 0:
                    continue
                if wanted is not None and op.mem.disp not in wanted:
                    continue
                if ins.mnemonic == 'lea':
                    continue
                out.append({'rva': ins.address, 'asm': ins.mnemonic + ' ' + ins.op_str, 'disp': op.mem.disp,
                    'base': base, 'index': ins.reg_name(op.mem.index) if op.mem.index else None,
                    'size': op.size, 'write': position == 0 and ins.mnemonic.startswith(('mov', 'vmov', 'add', 'sub',
                        'and', 'or', 'xor', 'inc', 'dec')) and ins.mnemonic not in ('movzx', 'movsx', 'movsxd'),
                    'float': ins.mnemonic.startswith(FLOAT_MNEMONICS)})
        return out

    def displacement_scan(self, functions, offsets) -> dict[int, list[dict]]:
        """field_accesses over many functions; only functions with at least one hit are returned."""
        result = {}
        for function in functions:
            hits = self.field_accesses(function, offsets)
            if hits:
                result[function] = hits
        return result

    # -- pins ------------------------------------------------------------------------------------------------
    def pin(self, rva, role, expected_asm: str | None = None) -> dict:
        ins = self.insn(rva)
        asm = ins.mnemonic + (' ' + ins.op_str if ins.op_str else '')
        if expected_asm is not None and asm != expected_asm:
            raise ValueError('instruction at %x changed: %r != %r' % (rva, asm, expected_asm))
        entry = {'rva': rva, 'bytes': self.data[rva:rva + ins.size].hex(), 'asm': asm, 'role': role}
        target = self.rip_target(ins)
        if target is not None:
            entry['ripTarget'] = target
        if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == x86.X86_OP_IMM:
            entry['branchTarget'] = ins.operands[0].imm
        return entry

    def prologue(self, rva, size=16) -> str:
        return self.data[rva:rva + size].hex()

    def describe(self) -> dict:
        return {'module': self.name, 'sha256': self.sha256, 'imageSize': self.image_size,
            'text': [self.text[0], self.text[1]], 'functions': int(len(self.pdata))}


def image_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()
