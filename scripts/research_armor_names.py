"""Names of every armor kit (411 HelldiverCustomizationKit rows) and every armor passive (32 rows) from the game's own
text, and their correlation with the scraped wiki data. Read-only, offline, against the retained snapshots of build
F5FEE03DCFDB (research/docs/armor-names-F5FEE03DCFDB.md).

  py scripts/research_armor_names.py      # write research/armor-names-F5FEE03DCFDB.json

Source of every row: the customization manager (game.dll +0x33264F8, research/player-attributes-F5FEE03DCFDB.json):
+0x00 the kit pointers, +0x20 the passive objects. Kit layout (filediver armor_sets.go is the LEAD for the field names;
every row in memory equals the lead byte for byte, proven by scripts/research_player_attributes.py):
+0x00 id, +0x04 dlc id, +0x08 set id, +0x0C name text id (upper), +0x10 name text id (cased), +0x14 description text
id, +0x18 rarity, +0x1C passive id, +0x20 archive, +0x28 type 0 armor / 1 helmet / 2 cape, +0x30 bodies*, +0x38 body
count. Body = {u32 body type, u32, Piece *, i64 count} (24 bytes); Piece = {u64 unit path, u32 slot, u32 piece type
0 armor / 1 undergarment / 2 accessory, u32 weight 0 light / 1 medium / 2 heavy, ...} (0x60 bytes).

Text: the game's own lookup (helldivers2.exe 0x321C40, research/stratagem-text-F5FEE03DCFDB.json) replicated against
the text registry IN EACH SNAPSHOT ([exe+0x1A101E0] = {u32 count, u32 capacity, table *[]}, walked in order, the
current language [exe+0x190C9BC]): the first registered table holding (language, id) wins. The installed game's
strings resources are a cross-check only. Names: cased id first, the upper id when the cased one has no text (the
lead's rule). Wiki data (HD2WikiImporter output) is compared, never used as a source.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import difflib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_event_state as base  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/armor-names-F5FEE03DCFDB.json'
WIKI = Path(r'C:\Users\Skye\Documents\HD2Mods\HD2WikiImporter\output')
G_CUSTOMIZATION = 0x33264F8
REGISTRY, LANGUAGE = 0x1A101E0, 0x190C9BC      # helldivers2.exe: text registry, current language hash
SLOTS = {0: 'armor', 1: 'helmet', 2: 'cape'}
WIKI_SLOTS = {'Body': 'armor', 'Helmet': 'helmet', 'Cape': 'cape'}
WEIGHTS = {0: 'light', 1: 'medium', 2: 'heavy'}
PIECE_TYPES = {0: 'armor', 1: 'undergarment', 2: 'accessory'}
PIECE_SLOTS = {0: 'helmet', 1: 'cape', 2: 'torso', 3: 'hips', 4: 'left_leg', 5: 'right_leg', 6: 'left_arm',
    7: 'right_arm', 8: 'left_shoulder', 9: 'right_shoulder'}
RARITIES = {0: 'common', 1: 'uncommon', 2: 'heroic'}
MODIFIER_TYPES = {0: 'Set', 1: 'Add', 2: 'Multiply', 3: 'Time'}


# ------------------------------------------------------------------------------------------------- game text
class SnapshotText:
    """exe 0x321C40 against the snapshot's own registry: the first table holding (language, id) wins."""

    def __init__(self, mem):
        self.mem = mem
        registry = mem.ptr(mem.exe + REGISTRY)
        self.count = mem.u32(registry)
        array = mem.ptr(registry + 8)
        self.language = mem.u32(mem.exe + LANGUAGE)
        self.tables = []
        for i in range(self.count):
            table = mem.ptr(array + 8 * i)
            magic, nl, n = struct.unpack('<III', mem.read(table, 12))
            if magic != 0x3E85F3AE:
                raise ValueError('registry table %d is not a text table' % i)
            languages = struct.unpack('<%dI' % nl, mem.read(table + 12, 4 * nl))
            if self.language not in languages:
                self.tables.append((table, {}))
                continue
            ids = struct.unpack('<%dI' % n, mem.read(table + 12 + 4 * nl, 4 * n))
            li = languages.index(self.language)
            offsets = struct.unpack('<%dI' % n, mem.read(table + 12 + 4 * nl + 4 * n + 4 * li * n, 4 * n))
            self.tables.append((table, {k: o for k, o in zip(ids, offsets) if o}))
        self.cache = {}

    def string(self, at):
        out = b''
        while True:
            chunk = self.mem.read(at + len(out), 64)
            if chunk is None:
                chunk = b''.join(self.mem.read(at + len(out) + k, 1) or b'\0' for k in range(64))
            end = chunk.find(b'\0')
            if end >= 0:
                return (out + chunk[:end]).decode('utf-8')
            out += chunk

    def __call__(self, key):
        if not key:
            return None
        if key not in self.cache:
            self.cache[key] = None
            for table, offsets in self.tables:
                if key in offsets:
                    self.cache[key] = self.string(table + offsets[key])
                    break
        return self.cache[key]


def installed_text():
    """Cross-check only: the installed game's strings resources (None when unavailable)."""
    try:
        import hd2_game_data
        import hd2_text
        data = hd2_game_data.Data()
        tables = [data.read(archive, main) for archive, _, kind, main, *_ in data.tables()
            if kind == hd2_text.STRINGS_TYPE and main[1] >= 16]
        us = hd2_text.language_hash('us')
    except Exception:  # noqa: BLE001
        return None
    return lambda key: (hd2_text.lookup(tables, key, us) or None) if key else None


# ------------------------------------------------------------------------------------------------- game rows
def read_kits(mem):
    mgr = mem.ptr(mem.game + G_CUSTOMIZATION)
    array, count = mem.ptr(mgr), mem.u32(mgr + 8)
    kits = []
    for index in range(count):
        pointer = mem.ptr(array + 8 * index)
        (kid, dlc, set_id, upper, cased, desc, rarity, passive, archive, kind, unk, bodies,
            body_count) = struct.unpack('<IIIIIIIIQIIQq', mem.read(pointer, 0x40))
        body_rows = []
        for b in range(body_count):
            body_type, _, pieces, piece_count = struct.unpack('<IIQq', mem.read(bodies + 24 * b, 24))
            raw = mem.read(pieces, 0x60 * piece_count)
            body_rows.append({'bodyType': body_type, 'pieces': [struct.unpack_from('<QIIII', raw, 0x60 * k)
                for k in range(piece_count)]})
        kits.append({'index': index, 'id': kid, 'dlc': dlc, 'set': set_id, 'nameUpper': upper, 'nameCased': cased,
            'description': desc, 'rarity': rarity, 'passive': passive, 'archive': archive, 'type': kind,
            'bodies': body_rows})
    return kits


def read_passives(mem):
    mgr = mem.ptr(mem.game + G_CUSTOMIZATION)
    array, count = mem.ptr(mgr + 0x20), mem.u32(mgr + 0x28)
    out = []
    for i in range(count):
        pointer = mem.ptr(array + 8 * i)
        pid, name, icon, mods, mod_count = struct.unpack_from('<IIQQq', mem.read(pointer, 0x20))
        raw = mem.read(mods, 16 * mod_count) if mod_count else b''
        out.append({'id': pid, 'name': name, 'modifiers': [struct.unpack_from('<IIfI', raw, 16 * k)
            for k in range(mod_count)]})
    return out


def weight_of(kit):
    """The weight of the kit's torso armor piece (slot 2 torso, piece type 0) in every body; 'mixed' if the bodies
    disagree, None without one. The other pieces' weights are not the class (arm/shoulder/undergarment pieces of one
    kit carry different weights); the torso armor piece is the one that agrees with the wiki class (stats)."""
    torso = Counter(p[3] for body in kit['bodies'] for p in body['pieces'] if p[1] == 2 and p[2] == 0)
    weights = Counter(p[3] for body in kit['bodies'] for p in body['pieces'] if p[2] == 0)
    named = {WEIGHTS.get(w, str(w)): c for w, c in weights.items()}
    if not torso:
        return None, named
    return (WEIGHTS.get(next(iter(torso)), str(next(iter(torso)))) if len(torso) == 1 else 'mixed'), named


# ------------------------------------------------------------------------------------------------- matching
def norm(text):
    return re.sub(r'[^A-Z0-9]', '', (text or '').upper())


def plain(text):
    return re.sub(r'</?c[^>]*>', '', text) if text else text


def wiki_view(row):
    value = lambda stat: row[stat]['value'] if isinstance(row.get(stat), dict) else row.get(stat)  # noqa: E731
    return {'id': row['id'], 'name': row['name'], 'class': row.get('class'), 'armorRating': value('armorRating'),
        'speed': value('speed'), 'staminaRegen': value('staminaRegen'), 'passiveName': row.get('passiveName')}


def match_passives(passives, wiki_passives):
    by_norm = {norm(w['name']): w for w in wiki_passives}
    out, used = {}, set()
    for p in passives:
        key = norm(p['nameText'])
        if key in by_norm:
            out[p['id']] = (by_norm[key], 'exact')
            used.add(by_norm[key]['id'])
    for p in passives:
        if p['id'] in out:
            continue
        free = {k: w for k, w in by_norm.items() if w['id'] not in used}
        close = difflib.get_close_matches(norm(p['nameText']), list(free), n=1, cutoff=0.85)
        if close:
            out[p['id']] = (free[close[0]], 'fuzzy')
            used.add(free[close[0]]['id'])
    return out


def main():
    # Every snapshot: the same kit and passive rows and the same resolved text (proven, not assumed).
    per_snapshot, reference = [], None
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        text = SnapshotText(mem)
        kits, passives = read_kits(mem), read_passives(mem)
        resolved = {}
        for kit in kits:
            for field in ('nameUpper', 'nameCased', 'description'):
                resolved[kit[field]] = text(kit[field])
        for p in passives:
            resolved[p['name']] = text(p['name'])
            for m in p['modifiers']:
                resolved[m[3]] = text(m[3])
        language = text.language
        per_snapshot.append({'snapshot': name, 'registryTables': text.count, 'language': '%08X' % language,
            'kits': len(kits), 'passives': len(passives)})
        state = (kits, passives, resolved)
        if reference is None:
            reference = state
        else:
            per_snapshot[-1]['rowsEqualFirst'] = kits == reference[0] and passives == reference[1]
            per_snapshot[-1]['textEqualFirst'] = resolved == reference[2]
        mem.close()
    kits, passives, resolved = reference
    if not all(s.get('rowsEqualFirst', True) for s in per_snapshot):
        raise ValueError('kit or passive rows differ between snapshots')
    text = lambda key: resolved.get(key) if key else None  # noqa: E731

    installed = installed_text()
    installed_check = None
    if installed:
        keys = [k for k in resolved if k]
        installed_check = {'ids': len(keys), 'equal': sum(1 for k in keys if installed(k) == resolved[k]),
            'differs': ['%08X' % k for k in keys if installed(k) != resolved[k]][:40]}

    by_passive_id = {p['id']: p for p in passives}
    for p in passives:
        p['nameText'] = text(p['name'])

    # Wiki
    wiki = json.loads((WIKI / 'wiki_armors.json').read_text(encoding='utf-8'))
    wiki_armors = wiki['armors']
    wiki_passives = json.loads((WIKI / 'wiki_armor_passives.json').read_text(encoding='utf-8'))['passives']
    passive_match = match_passives(passives, wiki_passives)
    wiki_passive_to_game = {w['id']: pid for pid, (w, _) in passive_match.items()}
    wiki_passive_name_to_game = {norm(w['name']): pid for pid, (w, _) in passive_match.items()}

    wiki_index = defaultdict(list)
    for row in wiki_armors:
        wiki_index[(WIKI_SLOTS[row['slot']], norm(row['name']))].append(row)

    out_kits, matched_wiki = [], set()
    for kit in kits:
        slot = SLOTS.get(kit['type'], str(kit['type']))
        cased, upper = text(kit['nameCased']), text(kit['nameUpper'])
        name = cased or upper
        weight, weights = weight_of(kit)
        candidates = wiki_index.get((slot, norm(name)), []) if name else []
        method = 'exact' if candidates else None
        if name and not candidates:  # designation + name typed differently (case, punctuation, a trailing space)
            pool = {norm(r['name']): r for r in wiki_armors if WIKI_SLOTS[r['slot']] == slot}
            close = difflib.get_close_matches(norm(name), list(pool), n=1, cutoff=0.9)
            if close:
                candidates, method = [pool[close[0]]], 'fuzzy'
        w = candidates[0] if candidates else None
        if w:
            matched_wiki.add(w['id'])
        pieces = sorted({(PIECE_SLOTS.get(p[1], p[1]), PIECE_TYPES.get(p[2], p[2])) for b in kit['bodies']
            for p in b['pieces']}, key=str)
        out_kits.append({
            'id': kit['index'], 'kitId': '%08X' % kit['id'], 'slot': slot, 'weight': weight,
            'pieceWeights': weights, 'passive': kit['passive'],
            'passiveName': by_passive_id[kit['passive']]['nameText'] if kit['passive'] in by_passive_id else None,
            'name': name, 'nameUpper': upper, 'nameCased': cased,
            'nameTextIds': {'upper': '%08X' % kit['nameUpper'], 'cased': '%08X' % kit['nameCased']},
            'description': text(kit['description']), 'descriptionTextId': '%08X' % kit['description'],
            'set': '%08X' % kit['set'] if kit['set'] else None, 'dlc': '%08X' % kit['dlc'] if kit['dlc'] else None,
            'rarity': RARITIES.get(kit['rarity'], kit['rarity']), 'archive': '%016X' % kit['archive'],
            'bodies': len(kit['bodies']), 'pieceSlots': [list(p) for p in pieces],
            'wiki': wiki_view(w) if w else None, 'wikiMatch': method,
            'wikiCandidates': len(candidates)})

    # A wiki page still without a kit: its name contained in exactly one unmatched kit name of the slot (the game's
    # cape names are longer, e.g. THE CAPE OF STARS AND SUFFRAGE / Stars and Suffrage).
    for row in wiki_armors:
        if row['id'] in matched_wiki:
            continue
        slot = WIKI_SLOTS[row['slot']]
        hits = [k for k in out_kits if k['slot'] == slot and not k['wiki'] and k['name'] and
            norm(row['name']) in norm(k['name'])]
        if len({norm(k['name']) for k in hits}) == 1:
            for k in hits:
                k['wiki'], k['wikiMatch'], k['wikiCandidates'] = wiki_view(row), 'contained', 1
            matched_wiki.add(row['id'])

    # Consistency: the wiki's passive and class of every matched kit against the game's. Several kits can carry one
    # name (variants: other set/dlc ids and archives); a wiki page is consistent when ONE kit of its name carries the
    # wiki's passive. Kits of that name with another passive are listed as variants, not as wiki mismatches.
    passive_mismatch, class_mismatch, variants = [], [], []
    groups = defaultdict(list)
    for k in out_kits:
        if k['wiki']:
            groups[k['wiki']['id']].append(k)
    for wiki_id, members in groups.items():
        w = members[0]['wiki']
        wiki_pid = wiki_passive_name_to_game.get(norm(w['passiveName'])) if w['passiveName'] else 0
        carried = sorted({k['passive'] for k in members})
        for k in members:
            k['wikiPassiveAgrees'] = k['passive'] == wiki_pid
        if wiki_pid not in carried:
            passive_mismatch.append({'wiki': wiki_id, 'name': w['name'], 'slot': members[0]['slot'],
                'kits': [k['id'] for k in members], 'gamePassives': carried, 'wikiPassiveName': w['passiveName'],
                'wikiPassiveAsGameId': wiki_pid})
        elif len(carried) > 1:
            variants.append({'wiki': wiki_id, 'name': w['name'], 'wikiPassive': wiki_pid,
                'kits': [{'id': k['id'], 'kitId': k['kitId'], 'passive': k['passive'], 'set': k['set'],
                    'dlc': k['dlc']} for k in members]})
        if members[0]['slot'] == 'armor':
            for k in members:
                if (w['class'] or '').lower() != (k['weight'] or ''):
                    class_mismatch.append({'kit': k['id'], 'name': k['name'], 'gameWeight': k['weight'],
                        'pieceWeights': k['pieceWeights'], 'wikiClass': w['class']})
    named_sets = defaultdict(list)
    for k in out_kits:
        if k['name'] and k['set']:
            named_sets[k['set']].append(k['name'])

    out_passives = []
    for p in sorted(passives, key=lambda q: q['id']):
        w, method = passive_match.get(p['id'], (None, None))
        effects = [{'key': '%08X' % key, 'type': MODIFIER_TYPES.get(t, t), 'value': round(v, 6),
            'textId': '%08X' % tid, 'text': text(tid)} for key, t, v, tid in p['modifiers']]
        lines = [plain(e['text']) for e in effects if e['text']]
        out_passives.append({'id': p['id'], 'name': p['nameText'], 'nameTextId': '%08X' % p['name'],
            'description': ' '.join(lines) or None, 'effects': effects,
            'armorKits': sum(1 for k in kits if k['passive'] == p['id'] and k['type'] == 0),
            'wiki': {'id': w['id'], 'name': w['name'], 'description': w['description']} if w else None,
            'wikiMatch': method})

    # Stats
    names = Counter()
    for k in out_kits:
        names[k['slot']] += 1
    unmatched_game = [k for k in out_kits if not k['wiki']]
    unmatched_wiki = [r for r in wiki_armors if r['id'] not in matched_wiki]
    stats = {
        'kits': len(out_kits), 'bySlot': dict(names),
        'namesResolved': sum(1 for k in out_kits if k['name']),
        'namesResolvedBySlot': {s: sum(1 for k in out_kits if k['slot'] == s and k['name']) for s in SLOTS.values()},
        'casedResolved': sum(1 for k in out_kits if k['nameCased']),
        'upperOnly': [k['id'] for k in out_kits if k['nameUpper'] and not k['nameCased']],
        'unresolved': [{'id': k['id'], 'kitId': k['kitId'], 'slot': k['slot'], 'passive': k['passive'],
            'weight': k['weight'], 'set': k['set'], 'nameTextIds': k['nameTextIds'],
            'namedKitsOfTheSameSet (lead, not a name)': sorted(set(named_sets.get(k['set'], [])))[:6]}
            for k in out_kits if not k['name']],
        'descriptionsResolved': sum(1 for k in out_kits if k['description']),
        'distinctNamesBySlot': {s: len({norm(k['name']) for k in out_kits if k['slot'] == s and k['name']})
            for s in SLOTS.values()},
        'weights': dict(Counter(str(k['weight']) for k in out_kits if k['slot'] == 'armor')),
        'kitsMatchedToWiki': len(out_kits) - len(unmatched_game),
        'kitsMatchedBySlot': {s: sum(1 for k in out_kits if k['slot'] == s and k['wiki']) for s in SLOTS.values()},
        'kitsMatchedNotExactly': [{'id': k['id'], 'name': k['name'], 'wiki': k['wiki']['name'], 'method': k['wikiMatch']} for k in out_kits
            if k['wikiMatch'] in ('fuzzy', 'contained')],
        'wikiPieces': len(wiki_armors), 'wikiPiecesMatched': len(matched_wiki),
        'wikiPiecesMatchedBySlot': {s: sum(1 for r in wiki_armors if WIKI_SLOTS[r['slot']] == s and r['id'] in
            matched_wiki) for s in SLOTS.values()},
        'gameKitsWithoutWiki': [{'id': k['id'], 'slot': k['slot'], 'name': k['name'], 'passive': k['passive'],
            'weight': k['weight'], 'set': k['set']} for k in unmatched_game],
        'wikiPiecesWithoutKit': [{'id': r['id'], 'slot': r['slot'], 'name': r['name']} for r in unmatched_wiki],
        'kitsSharingAName': {s: sum(1 for n, c in Counter(norm(k['name']) for k in out_kits if k['slot'] == s and
            k['name']).items() if c > 1) for s in SLOTS.values()},
        'passives': len(out_passives), 'passivesMatched': sum(1 for p in out_passives if p['wiki']),
        'passivesFuzzy': [{'id': p['id'], 'name': p['name'], 'wiki': p['wiki']['name']} for p in out_passives
            if p['wikiMatch'] == 'fuzzy'],
        'passivesWithoutWiki': [{'id': p['id'], 'name': p['name']} for p in out_passives if not p['wiki']],
        'wikiPassivesWithoutGame': [w['name'] for w in wiki_passives if w['id'] not in wiki_passive_to_game],
        'wikiPagesChecked': len(groups),
        'wikiArmorPagesChecked': sum(1 for m in groups.values() if m[0]['slot'] == 'armor'),
        'passiveMismatches': passive_mismatch, 'classMismatches': class_mismatch,
        'variantNamesWithOtherPassives': variants,
        'kitsDisagreeingWithTheirWikiPassive': [{'id': k['id'], 'name': k['name'], 'slot': k['slot'],
            'passive': k['passive'], 'wikiPassiveName': k['wiki']['passiveName']} for k in out_kits
            if k['wiki'] and not k.get('wikiPassiveAgrees', True)],
    }
    document = {
        'schemaVersion': 1, 'build': 'F5FEE03DCFDB', 'generatedBy': 'scripts/research_armor_names.py',
        'gameDll': base.PROFILE_DLL_SHA,
        'textPath': {'lookup': 'helldivers2.exe 0x321C40 replicated: registry [exe+0x1A101E0] {u32 count, u32 '
            'capacity, table *[]} walked in order; the first table holding (current language [exe+0x190C9BC], id) '
            'wins; table format scripts/hd2_text.py', 'kitName': 'kit +0x10 (cased) text id, else kit +0x0C (upper)',
            'kitDescription': 'kit +0x14 text id', 'passiveName': 'passive +0x04 text id',
            'passiveDescription': 'the passive object holds no description id: the effect lines are the text ids of '
            'its modifiers (+0x0C of each 16-byte modifier), tags <c=...> stripped, #BONUS kept as the game holds it',
            'installedGameCrossCheck': installed_check},
        'layouts': {'kit': {'0x00': 'u32 id', '0x04': 'u32 dlc id', '0x08': 'u32 set id', '0x0C': 'u32 name upper',
            '0x10': 'u32 name cased', '0x14': 'u32 description', '0x18': 'u32 rarity', '0x1C': 'u32 passive',
            '0x20': 'u64 archive', '0x28': 'u32 type 0 armor / 1 helmet / 2 cape', '0x30': 'Body *', '0x38': 'i64 count'},
            'body': {'0x00': 'u32 body type', '0x08': 'Piece *', '0x10': 'i64 count', 'stride': 24},
            'piece': {'0x00': 'u64 unit', '0x08': 'u32 slot', '0x0C': 'u32 type 0 armor / 1 undergarment / 2 accessory',
                '0x10': 'u32 weight 0 light / 1 medium / 2 heavy', 'stride': 0x60},
            'note': 'field names from the filediver lead (armor_sets.go); the rows equal it byte for byte; weight = '
                'the weight of the kit\'s armor-type pieces'},
        'snapshots': per_snapshot,
        'stats': stats,
        'kits': out_kits,
        'passives': out_passives,
        'writes': [],
    }
    OUTPUT.write_text(json.dumps(document, indent=1, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print('wrote', OUTPUT)
    short = {k: v for k, v in stats.items() if not isinstance(v, list) or len(v) <= 12}
    print(json.dumps(short, indent=1, ensure_ascii=False)[:6000])


if __name__ == '__main__':
    main()
