"""Code literals passed to a native function, and the dispatcher entries whose code passes them (research only).

Some identities live in code, not data: the game requests an explosion with a type that is an immediate operand of the
requesting function (``mov edx, 0xf2; call <behavior explosion wrapper>``). This module finds every call site of a
function, resolves the value an argument register holds there, and attributes the calling code to the dispatcher entries
that run it (a BehaviorId's or an AbilityId's handler), so the literal can be tied to the entities that own those ids.

* ``register_literal(block, register)``: the value a register holds at the end of a straight-line block (the
  instructions before a call, newest first). ``mov r, imm`` and ``xor r, r`` resolve; ``lea r, [s + imm]`` and
  ``mov r, s`` resolve through ``s`` inside the same block. Anything else (a memory load, an arithmetic result, a write
  in another block) is unresolved: None. Pure; synthetic blocks are enough to test it.
* ``CallLiterals(image)``: per call site of a target, the straight-line block before it, bounded by the previous call,
  ret, jmp or conditional jump, and by any address a direct branch or a known jump table can enter (``entries``), so a
  value set on another path is never taken for this one.
* ``Dispatcher``: a 32-bit jump table of handler stubs (entry ``i`` serves id ``i + 1``); ``handlers`` maps the function
  a stub calls first to its ids, ``stub_ids(site)`` the ids whose stub reaches ``site`` in straight-line code.
* ``Attribution``: the dispatcher ids that run a function, directly (it is a stub's handler, or a call site lies in a
  stub) or through callers up to ``depth`` levels; ``complete`` is False when some caller path ends unattributed.

Nothing here names anything: the research script that uses it names the ids' owners from data. Read-only.
"""
from __future__ import annotations

import bisect
import re

FAMILIES: dict[str, str] = {}
for _names in (('rax', 'eax', 'ax', 'al'), ('rbx', 'ebx', 'bx', 'bl'), ('rcx', 'ecx', 'cx', 'cl'),
        ('rdx', 'edx', 'dx', 'dl'), ('rsi', 'esi', 'si', 'sil'), ('rdi', 'edi', 'di', 'dil'),
        ('rbp', 'ebp', 'bp', 'bpl')) + tuple(('r%d' % n, 'r%dd' % n, 'r%dw' % n, 'r%db' % n) for n in range(8, 16)):
    for _name in _names:
        FAMILIES[_name] = _names[0]
_IMMEDIATE = re.compile(r'(\w+), (0x[0-9a-f]+|\d+)')
_PAIR = re.compile(r'(\w+), (\w+)')
_LEA = re.compile(r'(\w+), \[(\w+) \+ (0x[0-9a-f]+|\d+)\]')
BLOCK_ENDS = ('call', 'ret', 'jmp', 'int3')


def register_literal(block, register, depth=3):
    """The literal ``register`` holds after ``block`` (instructions (address, size, mnemonic, operands), newest first),
    or None. Only writes inside the block count."""
    family = FAMILIES.get(register)
    if family is None:
        return None
    for index, (_, _, mnemonic, operands) in enumerate(block):
        destination = operands.split(',')[0].strip()
        if FAMILIES.get(destination) != family:
            continue
        literal = _IMMEDIATE.fullmatch(operands)
        if mnemonic == 'mov' and literal:
            return int(literal.group(2), 0)
        pair = _PAIR.fullmatch(operands)
        if mnemonic == 'xor' and pair and FAMILIES.get(pair.group(2)) == family:
            return 0
        if depth > 0:
            lea = _LEA.fullmatch(operands)
            if mnemonic == 'lea' and lea and lea.group(2) in FAMILIES:
                base = register_literal(block[index + 1:], lea.group(2), depth - 1)
                return None if base is None else (base + int(lea.group(3), 0)) & 0xFFFFFFFF
            if mnemonic == 'mov' and pair and pair.group(2) in FAMILIES:
                return register_literal(block[index + 1:], pair.group(2), depth - 1)
        return None
    return None


class CallLiterals:
    """Call sites of a target with the literal an argument register holds there (scan.xref.CodeImage)."""

    def __init__(self, image, entries=()):
        self.image = image
        self.entries = set(entries)
        self._chunks = {}

    def _chunk(self, rva):
        chunk = self.image.chunk(rva)
        if chunk not in self._chunks:
            insns = list(self.image.lite.disasm_lite(self.image.data[chunk[0]:chunk[1]], chunk[0]))
            targets = set()
            for _, _, mnemonic, operands in insns:
                if mnemonic.startswith('j') and re.fullmatch(r'0x[0-9a-f]+', operands):
                    targets.add(int(operands, 16))
            self._chunks[chunk] = (insns, [i[0] for i in insns], targets)
        return self._chunks[chunk]

    def block(self, site):
        """The straight-line instructions before ``site``, newest first (empty when the site does not decode)."""
        insns, addresses, targets = self._chunk(site)
        index = bisect.bisect_left(addresses, site)
        if index >= len(addresses) or addresses[index] != site:
            return []
        out = []
        for j in range(index - 1, -1, -1):
            address, size, mnemonic, _ = insns[j]
            if address + size != insns[j + 1][0] or mnemonic in BLOCK_ENDS or mnemonic.startswith('j'):
                break
            out.append(insns[j])
            if address in targets or address in self.entries:
                break
        return out

    def literal(self, site, register):
        return register_literal(self.block(site), register)

    def calls(self, target, register):
        """[(site, function root, literal or None)] for every direct call of ``target``."""
        return [(site, self.image.root(site), self.literal(site, register))
            for site in self.image.calls_to(target) if self.image.chunk(site)]


class Dispatcher:
    """A jump table of handler stubs: entry i (an image-relative u32) serves id i + 1."""

    def __init__(self, image, name, table, count, stub_limit=40):
        self.image, self.name, self.table, self.count = image, name, table, count
        self.stubs = [image.u32(table + 4 * i) for i in range(count)]
        self.by_stub = {}
        for index, stub in enumerate(self.stubs):
            self.by_stub.setdefault(stub, []).append(index + 1)
        self.ordered = sorted(self.by_stub)
        self.handlers = {}
        for stub, ids in self.by_stub.items():
            handler = self._first_call(stub, stub_limit)
            if handler is not None:
                self.handlers.setdefault(handler, []).extend(ids)
        for ids in self.handlers.values():
            ids.sort()

    def _first_call(self, stub, limit):
        at = stub
        for _ in range(limit):
            try:
                ins = self.image.insn(at)
            except ValueError:
                return None
            if ins.mnemonic == 'call':
                return int(ins.op_str, 16) if re.fullmatch(r'0x[0-9a-f]+', ins.op_str) else None
            if ins.mnemonic in ('jmp', 'ret', 'int3'):
                return None
            at += ins.size
        return None

    def stub_ids(self, site):
        """The ids whose stub reaches ``site`` in straight-line code (no jmp or ret before it), else []."""
        index = bisect.bisect_right(self.ordered, site) - 1
        if index < 0:
            return []
        stub = self.ordered[index]
        at = stub
        while at < site:
            try:
                ins = self.image.insn(at)
            except ValueError:
                return []
            if ins.mnemonic in ('jmp', 'ret', 'int3'):
                return []
            at += ins.size
        return list(self.by_stub[stub]) if at == site else []


class Attribution:
    """The (dispatcher, id) pairs that run a function: as a stub's handler, from a stub, or through callers."""

    def __init__(self, image, dispatchers, depth=3):
        self.image, self.dispatchers, self.depth = image, dispatchers, depth
        self._memo = {}

    def at_site(self, site):
        found = set()
        for dispatcher in self.dispatchers:
            found |= {(dispatcher.name, i) for i in dispatcher.stub_ids(site)}
        return found

    def function(self, root, _depth=0, _stack=()):
        """(ids, complete) for the function starting at root."""
        direct = set()
        for dispatcher in self.dispatchers:
            direct |= {(dispatcher.name, i) for i in dispatcher.handlers.get(root, [])}
        if direct:
            return direct, True
        if _depth >= self.depth or root in _stack:
            return set(), False
        if root in self._memo:
            return self._memo[root]
        owners, complete = set(), True
        callers = self.image.calls_to(root)
        if not callers:
            complete = False
        for caller in callers:
            stub = self.at_site(caller)
            if stub:
                owners |= stub
                continue
            parent = self.image.root(caller)
            if parent is None:
                complete = False
                continue
            found, done = self.function(parent, _depth + 1, _stack + (root,))
            owners |= found
            complete = complete and done
        self._memo[root] = (owners, complete)
        return owners, complete

    def site(self, site):
        """(ids, complete) for a call site: its stub when it lies in one, else its function's attribution."""
        stub = self.at_site(site)
        if stub:
            return stub, True
        root = self.image.root(site)
        if root is None:
            return set(), False
        return self.function(root)
