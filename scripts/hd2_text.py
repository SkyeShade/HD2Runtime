"""The game's text tables (`strings` resources) and the lookup that reads them (docs/custom-text.md,
research/stratagem-text-F5FEE03DCFDB.json).

A table, as helldivers2.exe 0x321C40 reads it:
    u32 magic 0x3E85F3AE, u32 language count L, u32 id count N,
    L language hashes (ascending), N text ids (ascending),
    L x N u32 offsets from the table start, language-major (0 = this table has no text for that pair),
    NUL-terminated UTF-8 texts.
A text id is the upper 32 bits of MurmurHash64A (seed 0) of its key; a language hash the same of its code. The lookup
walks the registered tables in order; the first table holding the (current language, id) pair wins, otherwise the text
is empty. Offline tooling: the Runtime builds the same bytes in Lua (runtime/text_resources.lua).
"""
from __future__ import annotations

import struct

from hd2_archive import resource_hash

MAGIC = 0x3E85F3AE
STRINGS_TYPE = 0x0D972BAB10B40FD3
# The game's text languages, in the order of its language table (game.dll +0x37C5650; research/stratagem-text-*.json).
LANGUAGES = ('us', 'gb', 'bp', 'de', 'es', 'fr', 'it', 'jp', 'ko', 'ms', 'pl', 'pt', 'ru', 'cn', 'tc')


def text_id(key: str) -> int:
    return resource_hash(key) >> 32


def language_hash(code: str) -> int:
    return resource_hash(code) >> 32


def custom_key(resource: str, text: str) -> str:
    """The key of a mod's own text: <mod resource id>/text/<id> (mod-local, like images)."""
    return resource + '/text/' + text


def build(entries: dict[int, dict[int, str]]) -> bytes:
    """{language hash: {text id: text}} -> table bytes. Texts shared by several pairs are stored once."""
    languages = sorted(entries)
    ids = sorted(set().union(*[set(v) for v in entries.values()])) if entries else []
    nl, n = len(languages), len(ids)
    head = struct.pack('<III', MAGIC, nl, n) + struct.pack('<%dI' % nl, *languages) + struct.pack('<%dI' % n, *ids)
    base = len(head) + 4 * nl * n
    blob, offsets, seen = bytearray(), [], {}
    for language in languages:
        for key in ids:
            text = entries[language].get(key)
            if text is None:
                offsets.append(0)
                continue
            data = text.encode('utf-8') + b'\0'
            if data not in seen:
                seen[data] = base + len(blob)
                blob += data
            offsets.append(seen[data])
    return head + struct.pack('<%dI' % (nl * n), *offsets) + bytes(blob)


def parse(data: bytes) -> dict[int, dict[int, str]]:
    magic, nl, n = struct.unpack_from('<III', data)
    if magic != MAGIC:
        raise ValueError('not a text table')
    languages = struct.unpack_from('<%dI' % nl, data, 12)
    ids = struct.unpack_from('<%dI' % n, data, 12 + 4 * nl)
    offsets = struct.unpack_from('<%dI' % (nl * n), data, 12 + 4 * nl + 4 * n)
    out = {}
    for li, language in enumerate(languages):
        texts = out.setdefault(language, {})
        for i, key in enumerate(ids):
            at = offsets[li * n + i]
            if at:
                texts[key] = data[at:data.index(b'\0', at)].decode('utf-8')
    return out


def find(data: bytes, key: int, language: int):
    """One table, as 0x321C40 reads it: the text, or None (not in this table: the lookup tries the next one)."""
    _, nl, n = struct.unpack_from('<III', data)
    languages = struct.unpack_from('<%dI' % nl, data, 12)
    if language not in languages:
        return None
    ids = struct.unpack_from('<%dI' % n, data, 12 + 4 * nl)
    if key not in ids:
        return None
    at = struct.unpack_from('<I', data, 12 + 4 * nl + 4 * n + 4 * (languages.index(language) * n + ids.index(key)))[0]
    if at == 0:
        return None
    return data[at:data.index(b'\0', at)].decode('utf-8')


def lookup(tables: list[bytes], key: int, language: int) -> str:
    """The registered tables in order: the first that has the pair wins; else the empty string."""
    for table in tables:
        found = find(table, key, language)
        if found is not None:
            return found
    return ''
