"""The weapon firing-sound catalogue (docs/research/weapon-sounds-F5FEE03DCFDB.md): every ProjectileWeapon type of build
F5FEE03DCFDB that names a firing sound, the Wwise banks that define its events, the packages that list those banks, the
stratagems whose call-in packages provide them, and how far each layer carries. Read-only, offline: the game.dll image,
the seven retained snapshots and the game's own bundles. Nothing is written to the game or the snapshots.

1. The sound path [C] is research/pelican-maelstrom-sound-F5FEE03DCFDB.json (re-proven here): every shot, trigger edge
   and release reads its events from the weapon's RESOLVED ProjectileWeapon record (its own copy first).
2. The loop [C] (new pins, groups loopEdge, loopRelease, loopShot, eventSelect). The update compares this update's fire
   decision with the last one (instance +0x10, 0x617058). Rising edge: the weapon's audio source (made when missing,
   0x61708A), then, for a non-MIDI weapon (0x6170F0) not in fire mode 2 with a per-shot event (0x6170DC-0x6170E9), the
   loop start +0xFC is posted when not 0 (0x6170FA-0x617134); the decision is kept (0x61726E). Falling edge: once the
   cooldown +8 has run out (0x6172C4) the release 0x616760 posts the loop stop +0x100 (not MIDI, a source exists, not 0;
   0x6167BF-0x616855) and clears the decision (0x6168AE). A loop weapon posts no per-shot event outside fire mode 2
   (0x615050-0x61505E). The fire decision starts from the firing byte (0x616D51), which follows the trigger (+1, held
   past its delay: 0x616B97, 0x616C01 / 0x616C20); the trigger is copied from the owner's blob on every machine
   (research/peer-messaging "pelicanMirror", 0x740795 / 0x7464F7: re-checked here) and only a networked-fire weapon
   (+0x94) decides on its creator alone (0x616E63; the chin turret's +0x94 is 0). So a loop starts and stops on the
   fire decision's edges, which follow the replicated trigger, on the host and on every other machine alike.
3. The event a shot posts [C]: +0x10C in fire mode 4 and +0x110 in mode 7 when not 0, else +0x104 (0x614B53-0x614BAD);
   an event of 0 posts nothing (0x614BFF).
4. The types [O]: every entry of the ProjectileWeapon type table (component world +0xF12E80) in all seven snapshots,
   identical in all of them; the WeaponData type's fire mode (+0x90).
5. The banks [O]: every wwise_bank's HIRC is scanned; an event is catalogued only where an Event object (HIRC kind 4)
   with its id exists. Bank names from the wwise_dep resources.
6. The packages [O]: every package resource's listing; the stratagems (schemas/stratagem_authoring_catalog.json)
   whose call-in packages (research/stratagem-slot-conversion "stratagemPackages", as core/assets.lua
   dependencies_for_stratagem resolves them) list a bank; residency in the retained snapshots.
7. The range [O][I] (HEURISTIC): each Play action's target, its parent chain (by validated candidates) and the first
   attenuation object found on it; the distance of its curve's last point. Leads, not proofs.
8. The names: the repo's catalogues (player, support and vehicle weapons; stratagem payloads; package residency;
   the Pelican chin turret) and the Filediver path dictionary. scripts/generate_weapon_sounds.py assigns the semantic
   names from them.

Output: research/weapon-sounds-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import functools
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_game_data as gdata  # noqa: E402
import research_event_state as base  # noqa: E402
import research_pelican_sound as rps  # noqa: E402
import snapshot_image  # noqa: E402
from research_pelican import MISSION_SNAPSHOTS, WORLD, GATLING, TURRET_HMG, table_lookup  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/weapon-sounds-F5FEE03DCFDB.json'
PW_TYPES, WD_TYPES = rps.PW_TYPES, rps.WD_TYPES
U32 = lambda raw, o: struct.unpack_from('<I', raw, o)[0]  # noqa: E731
HEX = lambda v: '%08X' % v  # noqa: E731

GAME = {
    # The update (0x616AC0): the fire decision's edges post the loop start and call the release.
    'loopEdge': [
        (0x616B97, 'cmp byte ptr [r14 + rbp + 1], dil', None, 'the trigger (instance +1) held ...'),
        (0x616C01, 'mov byte ptr [r14 + rbp], 1', None, '... past its delay: firing (+0) set ...'),
        (0x616C20, 'mov byte ptr [r14 + rbp], dil', None, '... else firing cleared'),
        (0x616D51, 'cmp byte ptr [r14 + rbp], dil', None, 'this update\'s fire decision starts from the firing byte'),
        (0x616E63, 'cmp byte ptr [r12 + 0x94], dil', None, 'only a networked-fire weapon (+0x94) decides on its creator '
            'alone (the chin turret: 0)'),
        (0x617058, 'cmp r15b, byte ptr [r14 + rbp + 0x10]', None, 'the decision against the last one (instance +0x10) '
            '...'),
        (0x61705D, 'je 0x617279', None, '... unchanged: no edge ...'),
        (0x617063, 'test r15b, r15b', None, '... rising or ...'),
        (0x617066, 'je 0x6172c4', None, '... falling'),
        (0x61708A, 'call 0x616910', None, 'rising: the weapon\'s audio source (made when missing) ...'),
        (0x6170DC, 'cmp eax, 2', None, '... fire mode 2 ...'),
        (0x6170E1, 'cmp dword ptr [r12 + 0x104], edi', None, '... with a per-shot event: no loop start ...'),
        (0x6170F0, 'cmp byte ptr [r12 + 0xed], dil', None, '... a MIDI weapon: no loop start ...'),
        (0x6170F8, 'jne 0x61713a', None, '...'),
        (0x6170FA, 'mov edx, dword ptr [r12 + 0xfc]', None, '... the loop start +0xFC ...'),
        (0x61711C, 'test edx, edx', None, '... 0: nothing posted ...'),
        (0x617134, 'call qword ptr [rsi + 0x338]', None, '... posted on the weapon\'s source'),
        (0x61726E, 'mov byte ptr [r14 + rbp + 0x10], r15b', None, 'the decision kept for the next edge'),
        (0x6172C4, 'comiss xmm7, dword ptr [r14 + rbp + 8]', None, 'falling: once the cooldown (+8) has run out ...'),
        (0x6172DA, 'call 0x616760', None, '... the release'),
    ],
    # The release (0x616760): the loop stop.
    'loopRelease': [
        (0x61678C, 'call 0x515100', None, 'the release: the resolved ProjectileWeapon ...'),
        (0x6167AD, 'cmp eax, 2', None, '... fire mode 2 ...'),
        (0x6167B2, 'cmp dword ptr [r14 + 0x104], r13d', None, '... with a per-shot event: nothing to stop ...'),
        (0x6167BF, 'cmp dword ptr [rbp + 0x1c], -1', None, '... no audio source: nothing to stop ...'),
        (0x6167C9, 'cmp byte ptr [r14 + 0xed], r13b', None, '... MIDI: its notes stopped ...'),
        (0x616806, 'mov edi, dword ptr [r14 + 0x100]', None, '... else the loop stop +0x100 ...'),
        (0x616825, 'test edi, edi', None, '... 0: nothing posted ...'),
        (0x616855, 'call qword ptr [r10 + 0x338]', None, '... posted'),
        (0x6168AE, 'mov byte ptr [rbp + 0x10], r13b', None, 'the decision cleared'),
    ],
    # The shot: a loop weapon posts no per-shot event outside fire mode 2; an event of 0 posts nothing.
    'loopShot': [
        (0x614BFF, 'test edi, edi', None, 'the shot\'s event 0 ...'),
        (0x614C01, 'je 0x6150d3', None, '... posts nothing'),
        (0x615050, 'cmp dword ptr [r8 + 0xfc], 0', None, 'a loop weapon (+0xFC) ...'),
        (0x61505A, 'cmp dword ptr [rbp - 0x58], 2', None, '... outside fire mode 2 ...'),
        (0x61505E, 'jne 0x6150d3', None, '... posts no per-shot event'),
    ],
    # The per-shot event by fire mode: +0x10C (mode 4) or +0x110 (mode 7) when not 0, else +0x104.
    'eventSelect': [
        (0x614B53, 'cmp eax, 4', None, 'fire mode 4 ...'),
        (0x614B5D, 'mov edi, dword ptr [rax + 0x10c]', None, '... +0x10C ...'),
        (0x614B65, 'je 0x614b9d', None, '... when 0, +0x104'),
        (0x614B7E, 'cmp eax, 7', None, 'fire mode 7 ...'),
        (0x614B88, 'mov edi, dword ptr [rax + 0x110]', None, '... +0x110 ...'),
        (0x614B90, 'je 0x614b9d', None, '... when 0, +0x104'),
        (0x614BAD, 'mov edi, dword ptr [rax + 0x104]', None, 'otherwise the per-shot event +0x104'),
    ],
}
# The sound fields of a ProjectileWeapon record (offset, size) and what they are.
FIELDS = {'midi': (0xED, 1), 'midiTiming': (0xF0, 8), 'midiStopDelay': (0xF8, 4), 'loopStart': (0xFC, 4),
    'loopStop': (0x100, 4), 'single': (0x104, 4), 'singleMode4': (0x10C, 4), 'singleMode7': (0x110, 4),
    'secondary': (0x114, 4), 'secondarySilenced': (0x118, 4), 'silencedLoopStart': (0x210, 4),
    'silencedLoopStop': (0x214, 4), 'silencedSingle': (0x218, 4), 'silenced': (0x22C, 1), 'networkedFireEvents': (0x94, 1)}
# The fields a Runtime chin-turret copy may take from a catalogue entry (the rest of the block stays the chin turret's):
# the MIDI switch, the loop start / stop and the per-shot event; plus the instance value derived from the MIDI switch.
CHIN_FIELDS = (('midi', 0xED, 1), ('loopStart', 0xFC, 4), ('loopStop', 0x100, 4), ('single', 0x104, 4))
WRITE_NAMES = {'single': 'event'}   # the write labels r7 used (turret.<id>.copy.sound_event)
PLAY, STOP = 0x0403, 0x0103   # Wwise action types (Play; Stop)


def sound_fields(raw):
    out = {}
    for key, (offset, size) in FIELDS.items():
        if key == 'midiTiming':
            out[key] = list(struct.unpack_from('<2f', raw, offset))
        elif key == 'midiStopDelay':
            out[key] = struct.unpack_from('<f', raw, offset)[0]
        elif size == 1:
            out[key] = raw[offset]
        else:
            out[key] = HEX(U32(raw, offset))
    return out


def classify(s, fire_mode):
    """The sound a weapon of this record makes, by the code [C]: ('loop', start, stop) for a non-MIDI weapon with a loop
    start (not fire mode 2 with a per-shot event), else ('shot', event, midi) with the event its fire mode selects; or
    None when it posts nothing."""
    single = s['single']
    if fire_mode == 4 and s['singleMode4'] != '00000000':
        single = s['singleMode4']
    elif fire_mode == 7 and s['singleMode7'] != '00000000':
        single = s['singleMode7']
    loop = s['loopStart'] != '00000000' and not s['midi'] and not (fire_mode == 2 and s['single'] != '00000000')
    if loop:
        return {'kind': 'loop', 'start': s['loopStart'], 'stop': s['loopStop']}
    if single != '00000000':
        return {'kind': 'shot', 'event': single, 'midi': s['midi']}
    return None


# --------------------------------------------------------------------------------------------- the Wwise banks
class Banks:
    """Every wwise_bank's HIRC objects (first bank defining an id keeps it for the parent / attenuation walk) and, per
    Event id, every bank that defines it."""
    KINDS = {2: 'Sound', 3: 'Action', 4: 'Event', 5: 'RandSeq', 6: 'Switch', 7: 'ActorMixer', 9: 'Layer', 14: 'Attenuation',
        0x13: 'Blend'}
    CONTAINERS = (5, 6, 7, 9, 0x13)

    def __init__(self, data, banks, deps):
        self.data, self.deps = data, deps
        self.objects, self.where, self.events = {}, {}, collections.defaultdict(list)
        self.names = {}
        for resource in sorted(banks):
            try:
                objs = rps.hirc(data.read(*banks[resource]))
            except Exception:  # noqa: BLE001  (a bank without a readable HIRC defines nothing here)
                continue
            for oid, kb in objs.items():
                if kb[0] == 4:
                    self.events[oid].append(resource)
                if oid not in self.objects:
                    self.objects[oid], self.where[oid] = kb, resource

    def name(self, resource):
        if resource not in self.names:
            try:
                self.names[resource] = self.data.read(*self.deps[resource])[8:].split(b'\0')[0].decode('latin-1')
            except Exception:  # noqa: BLE001
                self.names[resource] = None
        return self.names[resource]

    def parent_of(self, oid):
        """DirectParentID (heuristic): after the FX params (u8 override, u8 count, [bypass, count x 7]) and up to two
        newer-bank bytes, u32 bus then u32 parent; a Sound first has its 14-byte source. The candidate naming a
        container object is taken."""
        kind, body = self.objects[oid]
        start = 14 if kind == 2 else 0
        for extra in (0, 1, 2):
            try:
                count = body[start + 1]
                o = start + 2 + (1 + 7 * count if count else 0) + extra
                _bus, parent = struct.unpack_from('<II', body, o)
            except Exception:  # noqa: BLE001
                continue
            if parent in self.objects and self.objects[parent][0] in self.CONTAINERS:
                return parent
        return None

    def attenuations(self, body):
        found = []
        for o in range(0, len(body) - 3):
            v = U32(body, o)
            if v in self.objects and self.objects[v][0] == 14 and v not in found:
                found.append(v)
        return found

    @staticmethod
    def curves(body):
        """Runs of (f32 distance, f32 value, u32 interpolation) points whose distance grows from 0."""
        runs = []
        for start in range(0, len(body) - 24):
            d0, _v0, i0 = struct.unpack_from('<ffI', body, start)
            if d0 != 0.0 or i0 > 9:
                continue
            points, o = [d0], start + 12
            while o + 12 <= len(body):
                d, v, i = struct.unpack_from('<ffI', body, o)
                if not (points[-1] < d < 100000 and -200 < v < 200 and i <= 9):
                    break
                points.append(d)
                o += 12
            if len(points) >= 2:
                runs.append(points)
        return runs

    def layer(self, target):
        """One Play target: its kind, the first attenuation on its parent chain and its curves' farthest point (m)."""
        chain, oid, seen = [], target, set()
        while oid and oid not in seen and len(chain) < 10:
            seen.add(oid)
            chain.append(oid)
            oid = self.parent_of(oid)
        attenuation = None
        for o in chain:
            found = self.attenuations(self.objects[o][1])
            if found:
                attenuation = found[0]
                break
        distance = None
        if attenuation is not None:
            runs = self.curves(self.objects[attenuation][1])
            distance = round(max(r[-1] for r in runs), 1) if runs else None
        return {'target': HEX(target), 'kind': self.KINDS.get(self.objects[target][0], self.objects[target][0]),
            'attenuation': HEX(attenuation) if attenuation is not None else None, 'maxDistance': distance,
            'chainDepth': len(chain)}

    def event(self, event_id):
        """An event's actions (type, target) and, for each Play action with a target in a bank, its layer."""
        kind, body = self.objects[event_id]
        actions = struct.unpack_from('<%dI' % body[0], body, 1)
        out = []
        for action in actions:
            if action not in self.objects:
                out.append({'action': HEX(action), 'type': None})
                continue
            _k, raw = self.objects[action]
            action_type, target = struct.unpack_from('<HI', raw, 0)
            row = {'action': HEX(action), 'type': '%04X' % action_type, 'target': HEX(target)}
            if action_type == PLAY and target in self.objects:
                row['layer'] = self.layer(target)
            out.append(row)
        return out


def range_summary(actions):
    """Per distance, how many Play layers reach it (heuristic); None when no layer's curve was found."""
    by = collections.Counter(a['layer']['maxDistance'] for a in actions if a.get('layer') and
        a['layer']['maxDistance'] is not None)
    if not by:
        return None
    return {'heuristic': True, 'maxDistance': max(by), 'layers': [{'distance': d, 'count': by[d]}
        for d in sorted(by, reverse=True)], 'playLayers': sum(1 for a in actions if a.get('type') == '%04X' % PLAY)}


# ------------------------------------------------------------------------------------------------- the names
def named_sources():
    """resource (16 hex) -> [{catalogue, ...}] from the repo's catalogues."""
    names = collections.defaultdict(list)
    names['%016X' % TURRET_HMG].append({'catalogue': 'pelican', 'label': 'Pelican chin autocannon',
        'path': 'content/fac_helldivers/vehicles/shuttle_gunship/shuttle_gunship_turret_hmg'})
    vw = json.loads((ROOT / 'research/vehicle-weapons-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    for v in vw['vehicles']:
        for s in v['slots']:
            names[s['path'][2:]].append({'catalogue': 'vehicle', 'vehicle': v['name'], 'slot': s['slot'],
                'mount': s['name'], 'path': s.get('nativePath'), 'rpm': (s.get('values') or {}).get('fireRate'),
                'projectile': (s.get('values') or {}).get('projectileType')})
    st = json.loads((ROOT / 'schemas/stratagem_authoring_catalog.json').read_text(encoding='utf-8'))
    for name, s in st['stratagems'].items():
        for p in (s.get('root') or {}).get('payloads') or []:
            if p != '0x73F8498BFFDCF415':   # the hellpod every stratagem lists
                names[p[2:]].append({'catalogue': 'stratagem', 'stratagem': name, 'family': s['family']})
    sw = json.loads((ROOT / 'schemas/support_weapon_authoring_catalog.json').read_text(encoding='utf-8'))
    for w in sw['weapons']:
        for r in w['resources']:
            names[r[2:]].append({'catalogue': 'support', 'weapon': w['name']})
    pw = json.loads((ROOT / 'schemas/player_weapon_authoring_catalog.json').read_text(encoding='utf-8'))
    for w in pw['weapons']:
        for r in w['resources']:
            names[r[2:]].append({'catalogue': 'player', 'weapon': w['name'], 'slot': w['slot']})
    pr = json.loads((ROOT / 'research/package-residency-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    for key, item in sorted(pr['catalog'].items()):
        if item.get('resource'):
            names[item['resource'][2:]].append({'catalogue': 'package-residency', 'key': key, 'label': item['label'],
                'path': item.get('path'), 'package': (item.get('dependency') or {}).get('package')})
    return names


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    groups = dict(rps.GAME)
    groups.update(GAME)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in groups.items()}
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    # The trigger's replication (research/peer-messaging "pelicanMirror"): its bytes, re-checked in this image.
    peer = json.loads((ROOT / 'research/peer-messaging-F5FEE03DCFDB.json').read_text(encoding='utf-8'))['pelicanMirror']
    replication = [p for p in peer['pins'] if p['rva'] in (7604117, 7628023, 6387977, 6385251)]
    if len(replication) != 4 or any(game_data[p['rva']:p['rva'] + len(p['bytes']) // 2].hex() != p['bytes']
            for p in replication):
        raise ValueError('the trigger replication pins changed')

    # [O] Every ProjectileWeapon type and its WeaponData fire mode, in every retained snapshot.
    per_snapshot = {}
    for name in SNAPSHOTS:
        m = base.Mem(name)
        w = m.ptr(m.game + WORLD)
        if not w:
            m.close()
            continue
        pw_table, wd_table = m.ptr(w + PW_TYPES[0]), m.ptr(w + WD_TYPES[0])
        rows = {}
        for slot in range(PW_TYPES[1]):
            key, index = struct.unpack('<QQ', m.read(pw_table + 16 * slot, 16))
            if not key:
                continue
            raw = m.read(pw_table + PW_TYPES[2] + PW_TYPES[3] * (index & 0xFFFFFFFF), PW_TYPES[3])
            j = table_lookup(m, wd_table, WD_TYPES[1], key)
            wd = m.read(wd_table + WD_TYPES[2] + WD_TYPES[3] * j, WD_TYPES[3]) if j is not None else None
            rows['%016X' % key] = {**sound_fields(raw), 'projectile': U32(raw, 0),
                'rpmSlots': [round(v, 3) for v in struct.unpack_from('<3f', raw, 4)],
                'fireMode': U32(wd, 0x90) if wd else None,
                'overrideEvents': [HEX(U32(wd, 0x410 + 0x14 * e + 8)) for e in range(8)] if wd else None,
                'block': rps.block_of(raw).hex()}
        per_snapshot[name] = rows
        m.close()
    if len(per_snapshot) != 7 or len({json.dumps(r, sort_keys=True) for r in per_snapshot.values()}) != 1:
        raise ValueError('the ProjectileWeapon types differ between the retained snapshots')
    types = per_snapshot[SNAPSHOTS[0]]
    chin = types['%016X' % TURRET_HMG]
    if not (chin['single'] == '8D4641BA' and chin['midi'] == 0 and chin['loopStart'] == '00000000'
            and chin['fireMode'] == 1 and chin['networkedFireEvents'] == 0 and chin['silenced'] == 0):
        raise ValueError('the chin turret\'s firing sound changed: %r' % chin)
    # No record anywhere uses the MIDI timing or stop delay: the copy never needs them.
    if any(t['midiTiming'] != [0.0, 0.0] or t['midiStopDelay'] for t in types.values()):
        raise ValueError('a record uses the MIDI timing: the catalogue would have to carry it')

    # [O] The bundles: banks, their names, and every package listing.
    _chunk = gdata.chunk

    @functools.lru_cache(maxsize=8192)
    def cached(path, c):
        return _chunk(path, c)
    gdata.chunk = cached
    PACKAGE, BANK, DEP = (gdata.murmur64(n) for n in (b'package', b'wwise_bank', b'wwise_dep'))
    data = gdata.Data()
    packages, banks, deps, sizes = {}, {}, {}, {}
    for archive, rname, rtype, main_part, stream, gpu in data.tables():
        key = (rname, rtype)
        if key not in sizes:
            sizes[key] = main_part[1] + stream[1] + gpu[1]
        if rtype == PACKAGE and rname not in packages:
            packages[rname] = (archive, main_part)
        elif rtype == BANK and rname not in banks:
            banks[rname] = (archive, main_part)
        elif rtype == DEP and rname not in deps:
            deps[rname] = (archive, main_part)
    bank_index = Banks(data, banks, deps)

    # The sounding types and the events they name.
    sounding, missing = {}, {}
    for resource, t in sorted(types.items()):
        c = classify(t, t['fireMode'])
        if not c:
            continue
        ids = [c['start'], c['stop']] if c['kind'] == 'loop' else [c['event']]
        absent = [e for e in ids if e == '00000000' or int(e, 16) not in bank_index.events]
        if absent:
            missing[resource] = {'sound': c, 'notInABank': absent}
            continue
        sounding[resource] = c
    events = sorted({e for c in sounding.values() for e in ([c['start'], c['stop']] if c['kind'] == 'loop'
        else [c['event']])})
    event_banks = {e: sorted(bank_index.events[int(e, 16)]) for e in events}
    wanted_banks = {b for bs in event_banks.values() for b in bs}

    def listing(package):
        raw = data.read(*packages[package])
        if len(raw) < 16:
            return None
        _version, _word, count = struct.unpack_from('<III', raw, 0)
        if len(raw) != 16 + 16 * count:
            return None
        return {struct.unpack_from('<QQ', raw, 16 + 16 * i)[::-1] for i in range(count)}
    import research_entity_authoring as rea
    native = rea.Native()
    bank_packages = collections.defaultdict(list)
    package_info = {}
    for package in sorted(packages):
        items = listing(package)
        if not items:
            continue
        hits = [b for b in wanted_banks if (b, BANK) in items]
        if not hits:
            continue
        package_info[package] = {'package': '0x%016X' % package, 'name': native.path(package),
            'bytes': sum(sizes.get(i, 0) for i in items), 'resources': len(items)}
        for b in hits:
            bank_packages[b].append(package)
    # [O] Which of them the game had resident in the retained snapshots.
    import research_package_residency as rpr
    loader = rpr.loader_pins(snapshot_image.Snapshot(build_profile.SNAPSHOT))
    resident_in = collections.defaultdict(list)
    for name in SNAPSHOTS:
        s = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        states, _refs, _capacity = rpr.residency(s, loader)
        s.close()
        for package in package_info:
            if states.get(package):
                resident_in[package].append(name)
    for package, info in package_info.items():
        info['residentInSnapshots'] = len(resident_in[package])

    # The stratagems whose call-in packages provide a bank (core/assets.lua dependencies_for_stratagem).
    slots = json.loads((ROOT / 'research/stratagem-slot-conversion-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    sp = slots['stratagemPackages']
    incomplete = set(sp['callIn']['incomplete'])
    catalogue = json.loads((ROOT / 'schemas/stratagem_authoring_catalog.json').read_text(encoding='utf-8'))
    stratagems = {}
    for name, s in sorted(catalogue['stratagems'].items()):
        sid = (s.get('root') or {}).get('id')
        if sid is None:
            continue
        listed = sp['callIn']['byStableId'].get(str(sid))
        ids = [i['package'] for i in listed] if listed else ([sp['byStableId'][str(sid)]] if str(sid) in
            sp['byStableId'] else [])
        ids = [p for k, p in enumerate(ids) if p not in ids[:k] and int(p, 16)]
        if not ids:
            continue
        loads, total = [], 0
        for p in ids:
            items = listing(int(p, 16)) if int(p, 16) in packages else None
            loads.append({'package': p, 'name': native.path(int(p, 16)), 'banks': sorted('%016X' % b for b in
                wanted_banks if items and (b, BANK) in items)})
            total += sum(sizes.get(i, 0) for i in items) if items else 0
        stratagems[name] = {'stableId': sid, 'family': s['family'], 'packages': loads, 'bytes': total,
            'complete': name not in incomplete}
    bank_stratagems = collections.defaultdict(list)
    for name, s in stratagems.items():
        for p in s['packages']:
            for b in (int(x, 16) for x in p['banks']):
                if name not in bank_stratagems[b]:
                    bank_stratagems[b].append(name)

    # The events: their banks and layers (heuristic range).
    event_rows = {}
    for e in events:
        actions = bank_index.event(int(e, 16))
        event_rows[e] = {'banks': [{'resource': '%016X' % b, 'name': bank_index.name(b)} for b in event_banks[e]],
            'actions': actions, 'range': range_summary(actions)}

    names = named_sources()
    entries = []
    for resource, c in sorted(sounding.items()):
        t = types[resource]
        ids = [c['start'], c['stop']] if c['kind'] == 'loop' else [c['event']]
        # The banks: those defining every event of the sound (a loop's start and stop together).
        common = set(event_banks[ids[0]])
        for e in ids[1:]:
            common &= set(event_banks[e])
        if not common:
            missing[resource] = {'sound': c, 'notInOneBank': ids}
            continue
        bank_list = sorted(common, key=lambda b: (bank_index.name(b) or '', b))
        listed_by = sorted({p for b in bank_list for p in bank_packages[b]},
            key=lambda p: (package_info[p]['bytes'], p))
        candidates = sorted({n for b in bank_list for n in bank_stratagems[b]})
        # The chin copy's writes from the chin turret's own record: the fields the entry gives, where they differ.
        want = {'midi': c.get('midi', 0), 'loopStart': c.get('start', '00000000'),
            'loopStop': c.get('stop', '00000000'), 'single': c.get('event', '00000000')}
        writes = []
        for key, offset, size in CHIN_FIELDS:
            have = chin[key]
            to = want[key]
            if to != have:
                frm = bytes([have]) if size == 1 else struct.pack('<I', int(have, 16))
                dst = bytes([to]) if size == 1 else struct.pack('<I', int(to, 16))
                writes.append({'name': WRITE_NAMES.get(key, key), 'offset': offset, 'size': size, 'from': frm.hex(),
                    'to': dst.hex()})
        instance = [] if want['midi'] == chin['midi'] else [{'name': 'midi', 'offset': rps.INSTANCE['midi'], 'size': 1,
            'from': '%02x' % chin['midi'], 'to': '%02x' % want['midi']}]
        entries.append({'resource': resource, 'sound': c, 'fireMode': t['fireMode'], 'rpmSlots': t['rpmSlots'],
            'projectile': t['projectile'], 'secondary': t['secondary'], 'silenced': {k: t[k] for k in
                ('silenced', 'silencedLoopStart', 'silencedLoopStop', 'silencedSingle', 'secondarySilenced')},
            'networkedFireEvents': t['networkedFireEvents'],
            'overrideEvents': [e for e in (t['overrideEvents'] or []) if e != '00000000'],
            'banks': [{'resource': '%016X' % b, 'name': bank_index.name(b)} for b in bank_list],
            'packages': ['0x%016X' % p for p in listed_by],
            'stratagems': [{'name': n, 'bytes': stratagems[n]['bytes'], 'complete': stratagems[n]['complete']}
                for n in candidates],
            'range': event_rows[ids[0]]['range'],
            'chin': {'writes': writes, 'instanceWrites': instance},
            'sources': names.get(resource, []), 'path': native.path(int(resource, 16))})

    def raw32(value):
        return struct.pack('<I', int(value, 16)).hex()
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'replication': [{k: p[k] for k in ('rva', 'bytes', 'asm', 'role')} for p in replication],
        'record': {'stride': PW_TYPES[3], 'fields': {k: list(v) for k, v in FIELDS.items()},
            'blocks': [list(b) for b in rps.BLOCKS], 'span': [0xE0, PW_TYPES[3]],
            'chinFields': [list(f) for f in CHIN_FIELDS]},
        'instance': rps.INSTANCE,
        'chin': {'resource': '%016X' % TURRET_HMG, 'midi': chin['midi'], 'event': chin['single'],
            'blockBytes': chin['block'], 'fireMode': chin['fireMode']},
        'counts': {'types': len(types), 'sounding': len(sounding), 'notCatalogued': len(missing),
            'silent': len(types) - len(sounding) - len(missing), 'entries': len(entries), 'events': len(events),
            'banks': len(wanted_banks), 'packages': len(package_info)},
        'entries': entries,
        'notCatalogued': missing,
        # The types whose record names no firing sound (every sound field 0), with their catalogue names.
        'silentTypes': {resource: {'sources': names.get(resource, []), 'path': native.path(int(resource, 16))}
            for resource, t in sorted(types.items()) if not classify(t, t['fireMode'])},
        'events': event_rows,
        'packages': {p['package']: {k: v for k, v in p.items() if k != 'package'} for p in
            sorted(package_info.values(), key=lambda p: p['package'])},
        'stratagems': stratagems,
        'loop': {
            'rule': 'a loop starts on the rising edge of the fire decision (instance +0x10) and stops at the release on '
                'its falling edge, once the cooldown has run out; the decision follows the firing byte, which follows '
                'the trigger (+1) that every machine copies from the owner\'s blob; posted only for a non-MIDI record '
                '(+0xED = 0) with a loop start (+0xFC) and stop (+0x100), and only when the weapon is not in fire mode '
                '2 with a per-shot event; a loop weapon posts no per-shot event outside fire mode 2',
            'chinCopy': 'the chin turret (fire mode 1, +0x94 = 0, +0xED = 0, instance +0x38 = 0) takes a loop as its own '
                'copy\'s +0xFC (start), +0x100 (stop) and +0x104 = 0 (as the loop weapons\' own records); +0xED and the '
                'instance +0x38 stay 0, the values the game derives for a non-MIDI record; written only while it is '
                'quiet (no trigger, fire state or decision), so no loop is playing when its events change'},
        'rule': 'a weapon\'s firing sound is its resolved ProjectileWeapon record\'s events: per shot (+0x104, or +0x10C / '
            '+0x110 by fire mode; MIDI notes when +0xED), or a loop (+0xFC start, +0x100 stop) on the fire decision\'s '
            'edges; an event is catalogued only where a bank defines it',
    }
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; types', len(types), '; entries', len(entries),
        '; not catalogued', len(missing), '; banks', len(wanted_banks), '; packages', len(package_info))


if __name__ == '__main__':
    main()
