"""Mission-time slot type conversion (docs/custom-stratagems.md, "Mission-time slot conversion: research"): can the
Runtime change ONE entry of the local player's mission stratagem record from a token type (for example a second
Orbital Precision Strike) to an owned, unselected vanilla carrier type, so the game treats that slot as the carrier?
Read-only, offline: the game.dll image, the seven retained snapshots of build F5FEE03DCFDB and the game's bundle
database. Nothing is written.

Proves:

1. The record. [game+0x347CE50] = the per-peer stratagem records ({u64 peer, ...}, 0x1690 bytes, count +0x2D200); a
   record's stratagem state at +0x38 holds up to 16 entries of 0x30 bytes at +0x188 (+0 type, +4 uses, +9 granted
   flag, +0x18 cooldown end) and their count at +0x788.
2. Its writers. 0x66EFD0 clears a record and appends a mission's default stratagems (granted flag 1); 0x66F190 appends
   entries (type, uses, the entry's granted flag, cooldown 0). The ship's sync (StateShip on_synchronized_tasks_done,
   0xADBB50), a loadout handler (0xAD9020: the player's loadout block, then clear + defaults + append) and the loadout
   screen's exit rebuild the local record; mission systems append granted stratagems (0x856FE0, flag 1); the peer sync
   (0x11E82D0) writes received entries. No writer checks ownership or that a type was in the saved loadout.
3. Its readers. Each frame every HUD slot takes its entry's type (0x183675C) and rebuilds its arrows when the type
   changed (0x1836D09) and its icon when it differs from the remembered type (0x183A05B): a type change refreshes the
   slot through the vanilla HUD path. The matcher (0x66D8C0) reads each entry's type, copies that type's code and keeps
   one candidate per type; its result is the matched TYPE (0x66E1E3 -> buffer +0x14), which activation (0x671440) maps
   to the type's row. Uses (+4), cooldown (+0x18) and in-flight beacons ((peer, slot index)) stay with the entry.
4. Loadout order: in the mission snapshots the local record's non-granted entries are exactly the saved loadout, in
   order. At the mission end transition the record is already rebuilt for the ship: the loadout only (no defaults),
   in reverse order, so a mission-time conversion is discarded by the game itself.
5. Assets: in every mission snapshot the game holds the root package of every record entry's type (and the loadout
   packages of carried equipment), aboard the ship none; the unselected carrier's package is resident in no snapshot.
   The proof carrier's package is in the bundle database.
5b. A stratagem's FULL call-in package list (docs/research/gas-eat-F5FEE03DCFDB.md): the mission loader (0x1753330)
   asks 0x1753080(out, type, -, level) for every record entry's packages: the row's +0xA8 package when non-zero; the
   row's +0xF8 weapon key looked up in the loadout weapon table [game+0x33269E8] (entries from +0x1B2C, count +0x1B48,
   0x20 bytes: +0 key, +8 entity resource), that entity's registry record (0x4F5680) +8 package; each +0x118 entry
   (0x20 bytes) whose +0 is the level adds its +0x18; each +0x178 entry (0x10 bytes) adds the entity package of its +8.
   Support weapons have +0xA8 = 0 and their package via +0xF8 (EAT-17: packages/generated/loadout/lat_oneshot);
   backpacks use +0xA8. Every package of the A8 and F8 branches is listed per stable id; a stratagem whose +0x118 or
   +0x178 list is not empty has a level- or entity-dependent part this research does not derive: it is listed as
   incomplete (never a carrier).
6. Reports: the mission_end / mission_reward events (0x1347A10, from the state change 0xAB3350) and the mission-start log
   serialize the record's selectable entries by enum name (0x135CEB0).

Output: research/stratagem-slot-conversion-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import research_package_residency as residency  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS, HUD, LOADOUT, TABLE, RECORDS, SAVE_STORE  # noqa: E402
from validate_event_world_snapshot import MISSION  # noqa: E402

OUTPUT = ROOT / 'research/stratagem-slot-conversion-F5FEE03DCFDB.json'
RECORD_STRIDE, RECORD_COUNT, STATE = 0x1690, 0x2D200, 0x38
ENTRIES, ENTRY_STRIDE, ENTRY_COUNT, MAX_ENTRIES = 0x188, 0x30, 0x788, 16
USES, GRANTED, COOLDOWN = 4, 9, 0x18
DEFAULT_SETS, SETS, SET_SIZE = 0x213F550, 0, 6
# The beacon's look (research "beaconPresentation"): the beam is the thrown ball type's row +0xD4 into a table of 24-byte
# entries (the beam unit's resource, an index, its HDR colour); the ping (HUD marker) colour is the row's +0xB8.
BEAM_ROW, PING_ROW, BEAM_TABLE, BEAM_STRIDE = 0xD4, 0xB8, 0x32E26A0, 24
PING_COLOURS = {'red': 0x21D4790, 'blue': 0x21D4770, 'yellow': 0x21D4760}

GAME = {
    'recordClear': [
        (0x66F0B2, 'mov dword ptr [r15 + 0x788], 0', None, 'clear: the entry count = 0'),
        (0x66F0D6, 'lea rax, [rip + {rip}]', DEFAULT_SETS, 'the mission default sets (6 types each)'),
        (0x66F11E, 'mov dword ptr [rdi + 0x188], r8d', None, 'a default entry: its type ...'),
        (0x66F133, 'mov byte ptr [rdi + 0x191], 1', None, '... granted flag 1'),
    ],
    'recordAppend': [
        (0x66F2A7, 'mov dword ptr [rsi + 0x188], edx', None, 'append: the type'),
        (0x66F2CD, 'mov dword ptr [rsi + 0x18c], eax', None, 'its uses'),
        (0x66F2D7, 'mov byte ptr [rsi + 0x191], al', None, 'the entry\'s granted flag (0 for a loadout pick)'),
        (0x66F2E0, 'mov qword ptr [rsi + 0x1a0], 0', None, 'cooldown end 0'),
        (0x66F2EB, 'mov dword ptr [r15 + 0x788], eax', None, 'the count + 1 (no ownership or loadout check)'),
    ],
    'rebuilds': [
        (0xAD9046, 'call 0x17540b0', None, 'a loadout handler: the player\'s loadout block ...'),
        (0xAD9166, 'call 0x66efd0', None, '... clear + the mission\'s defaults ...'),
        (0xAD917D, 'call 0x66f190', None, '... then the loadout appended'),
        (0xADC5BA, 'call 0x66efd0', None, 'StateShip on_synchronized_tasks_done: clear ...'),
        (0xADC5CF, 'call 0x66f190', None, '... and the loadout appended'),
        (0x1467A52, 'call 0x66f190', None, 'the loadout screen\'s exit appends the picked loadout'),
        (0x8570A4, 'mov word ptr [rsp + 0x28], 0x100', None, 'a mission-granted stratagem (granted flag 1) ...'),
        (0x8570B5, 'call 0x66f190', None, '... appended'),
        (0x11E8365, 'mov dword ptr [rcx + 0x188], r14d', None, 'the peer sync writes received entries'),
    ],
    'matcherResult': [
        (0x66DADC, 'mov r8d, dword ptr [r15 + rcx*8 + 0x188]', None, 'the matcher reads each entry\'s type'),
        (0x66DB9B, 'call 0xa106c0', None, 'that type\'s code'),
        (0x66DC10, 'mov ebp, dword ptr [r13 + rsi*4]', None, 'one candidate per type'),
        (0x66E1E3, 'mov dword ptr [r9 + 0x14], r13d', None, 'the result'),
        (0xA903CC, 'call 0x66d8c0', None, 'stratagem input: each direction runs the matcher'),
        (0xA9040A, 'mov r9d, dword ptr [r12 + 0x14]', None, 'the matched type ...'),
        (0xA904BB, 'call 0x671440', None, '... to activation'),
        (0x671484, 'cmp ebp, 0x7c', None, 'activation takes a type (124 Reinforce special) ...'),
        (0x6714B2, 'mov rax, qword ptr [rcx + rbp*8]', None, '... and its row'),
    ],
    'perEntry': [
        (0x66D3E5, 'mov eax, dword ptr [rdx + rcx*8 + 0x18c]', None, 'uses: per entry'),
        (0x66D24A, 'mov rcx, qword ptr [rsi + 0x1a0]', None, 'cooldown end: per entry'),
        (0x66D262, 'mov rax, qword ptr [rip + {rip}]', 0x3326D98, 'the in-flight call-ins'),
        (0x66D26B, 'mov r8d, dword ptr [rax + 0x1c]', None, 'their count'),
        (0x66D274, 'mov r9, qword ptr [rax + 0x60]', None, 'their entries (0x28 bytes)'),
        (0x66D278, 'mov r11, qword ptr [rdi + 0x9e8]', None, 'the record state +0x9E8: the key a call-in carries'),
        (0x66D286, 'cmp qword ptr [r9 + rcx*8 + 0x10], r11', None, 'entry +0x10: that key'),
        (0x66D28D, 'cmp dword ptr [r9 + rcx*8 + 0x18], r10d', None, 'entry +0x18: the slot index'),
        (0x66D294, 'cmp byte ptr [r9 + rcx*8 + 1], bl', None, 'entry +1 = 0: still in flight'),
    ],
    # The beacon's look, decided when the thrown ball lands, from the ball's own type: the BEAM (and its glow) from the
    # row's +0xD4 (0 none, 1 red, 2 blue, 3 yellow: the table's HDR colours), the PING from the row's +0xB8 (0 red, 2
    # blue, else yellow). Two independent members: the Orbital EMS Strike has a blue beam and a red ping.
    'beaconPresentation': [
        (0x6A218B, 'mov eax, dword ptr [r14 + rcx*8 + 8]', None, 'landing: the thrown ball\'s own type ...'),
        (0x6A219D, 'mov rax, qword ptr [rdx + rax*8 + 0x37cb600]', None, '... its StratagemInfo row ...'),
        (0x6A21A5, 'mov r14d, dword ptr [rax + 0xd4]', None, '... +0xD4: the beam (0: none) ...'),
        (0x6A21AC, 'test r14d, r14d', None, '...'),
        (0x6A21BC, 'lea eax, [r14 - 1]', None, '... minus one ...'),
        (0x6A21C8, 'movups xmm0, xmmword ptr [rdx + rax*8 + 0x32e26a0]', None, '... indexes the beam table (24 bytes '
            'each: the beam unit, its colour)'),
        (0x13D1557, 'mov eax, dword ptr [rdi + 0xb8]', None, 'the ping: the row\'s +0xB8 ...'),
        (0x13D1568, 'movaps xmm0, xmmword ptr [rip + {rip}]', PING_COLOURS['red'], '... 0: red'),
        (0x13D157E, 'cmp eax, 2', None, '...'),
        (0x13D1583, 'movaps xmm0, xmmword ptr [rip + {rip}]', PING_COLOURS['blue'], '... 2: blue'),
        (0x13D1593, 'movaps xmm0, xmmword ptr [rip + {rip}]', PING_COLOURS['yellow'], '... else: yellow'),
    ],
    'callInPackages': [
        (0x1753437, 'call 0x1753080', None, 'the mission loader asks for each record entry\'s packages'),
        (0x17533E8, 'mov eax, dword ptr [rdi + rcx*8 + 0x188]', None, 'the entry\'s type'),
        (0x175340A, 'mov r9d, dword ptr [rdi + rax*4 + 0x78c]', None, 'its level'),
        (0x17530C3, 'cmp qword ptr [rsi + 0xa8], rbx', None, 'the row\'s +0xA8 package, when not zero'),
        (0x17530E3, 'mov eax, dword ptr [rsi + 0xf8]', None, 'the row\'s +0xF8 weapon key'),
        (0x17530ED, 'mov rcx, qword ptr [rip + {rip}]', 0x33269E8, 'the loadout weapon table'),
        (0x17530F4, 'mov r8d, dword ptr [rcx + 0x1b48]', None, 'its entry count'),
        (0x1753100, 'mov r9d, dword ptr [rcx + 0x1b2c]', None, 'its first entry index (0x20 bytes each)'),
        (0x1753118, 'cmp dword ptr [rcx], eax', None, 'entry +0: the key'),
        (0x1753134, 'mov rcx, qword ptr [rcx + 8]', None, 'entry +8: the weapon entity resource'),
        (0x175313B, 'call 0x4f5680', None, 'its registry record'),
        (0x1753145, 'mov rcx, qword ptr [rax + 8]', None, 'record +8: the weapon\'s package'),
        (0x175315F, 'cmp dword ptr [rsi + 0x120], edx', None, 'the +0x118 list\'s count'),
        (0x1753170, 'mov rax, qword ptr [rsi + 0x118]', None, 'the +0x118 list (level packages)'),
        (0x175319E, 'cmp dword ptr [rsi + 0x180], edi', None, 'the +0x178 list\'s count'),
        (0x17531B0, 'mov rcx, qword ptr [rsi + 0x178]', None, 'the +0x178 list (entity packages)'),
        (0x4F568F, 'mov r10, qword ptr [rax + 0xf12558]', None, 'the registry: the world\'s +0xF12558'),
        (0x4F56A7, 'imul eax, edx, 0x438', None, 'hashed over 0x438 slots (16 bytes: key, index)'),
        (0x4F5701, 'add rax, 0x21c', None, 'the record: (index + 0x21C) x 0x20 into the registry'),
    ],
    'reports': [
        (0x135D0E4, 'mov rax, qword ptr [r9 + rax*8 + 0x21d4aa0]', None, 'the loadout by enum name'),
        (0x1348228, 'call 0x135ceb0', None, 'mission_end / mission_reward events ...'),
        (0xAB3412, 'call 0x1347a10', None, '... from the state change'),
    ],
}
HUD_ROWS = {'hudSlots': HUD['slots'], 'hudRedraw': HUD['redraw'], 'hudRecord': HUD['record'],
    'hudIcon': [row for row in LOADOUT['presentation'] if row[0] in (0x183A053, 0x183A05B, 0x183A1E5, 0x183A352)],
    'availability': [row for row in LOADOUT['picker'] if row[0] >= 0x136FC00]}


WEAPON_TABLE, WORLD_GLOBAL, REGISTRY = 0x33269E8, 0x346BF98, 0xF12558
PACKAGES_SNAPSHOT = 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'


def call_in_packages(mem, row):
    """0x1753080 for one row, its A8 and F8 branches (level 0): [(via, package)], and whether the level/entity lists
    (+0x118, +0x178) are empty (complete)."""
    out = []
    a8 = mem.u64(row + 0xA8)
    if a8:
        out.append(('A8', a8))
    f8 = mem.u32(row + 0xF8)
    if f8:
        table = mem.ptr(mem.game + WEAPON_TABLE)
        count, first = mem.u32(table + 0x1B48), mem.u32(table + 0x1B2C)
        registry = mem.ptr(mem.ptr(mem.game + WORLD_GLOBAL) + REGISTRY)
        for i in range(count):
            entry = table + (first << 5) + i * 0x20
            if mem.u32(entry) != f8:
                continue
            resource = mem.u64(entry + 8)
            slot = resource % 0x438
            for _ in range(0x438):
                key = mem.u64(registry + slot * 16)
                if key == resource:
                    record = registry + ((mem.u32(registry + slot * 16 + 8) + 0x21C) << 5)
                    if mem.u64(record + 8):
                        out.append(('F8', mem.u64(record + 8)))
                    break
                if not key:
                    break
                slot = 0 if slot == 0x437 else slot + 1
            break
        # A key the table does not hold (or a weapon with no package) adds nothing: the game's own rule.
    complete = not (mem.u32(row + 0x120) or mem.u32(row + 0x180))
    return out, complete


def catalogue_roots():
    text = (ROOT / 'domains/stratagem_authoring.lua').read_text(encoding='utf-8')
    roots = {}
    for m in re.finditer(r'\["name"\]="([^"]+)",\["family"\]="[^"]*",\["rootResolution"\]="[^"]*",\["root"\]=\{\["id"\]='
            r'(\d+),\["package"\]="([^"]+)"', text):
        roots[m.group(1)] = {'id': int(m.group(2)), 'package': int(m.group(3), 16)}
    return roots


def owned(mem, catalogue, stable_id):
    """The availability check's ownership rule, read-only: (state, parent state) of the kind-10 record, or None."""
    first, last = mem.u32(catalogue + 0xD1D0C), mem.u32(catalogue + 0xD1D10)
    for pos in range(first, last):
        index = mem.u32(catalogue + 0xD1D48 + pos * 4)
        record = catalogue + 0xB9CE4 + index * 24
        if mem.u32(record + 8) == stable_id:
            state = mem.u32(catalogue + 0x1CE4 + mem.u32(record) * 0xB8 + 0x14)
            back = mem.u32(record + 0x10)
            parent = mem.u32(catalogue + 0x1CE4 + mem.u32(record - back * 24) * 0xB8 + 0x14) if back else None
            return state, parent
    return None


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    pins_loader = residency.loader_pins(snap)
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in list(GAME.items()) + list(HUD_ROWS.items())}
    # 0xADBB50 is StateShip's on_synchronized_tasks_done: its own log strings name it.
    named = set()
    for address, size, mnemonic, operands in game.md.disasm_lite(game.data[0xADBB50:0xADBB50 + 0x400], 0xADBB50):
        m = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', operands)
        if mnemonic == 'lea' and m:
            target = address + size + int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            try:
                named.add(game.cstr(target))
            except ValueError:
                pass
    if not {'on_synchronized_tasks_done', 'StateShip'} <= named:
        raise ValueError('the StateShip rebuild moved: %r' % sorted(named)[:8])
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    # The beam table [C]: entry k (beam k + 1) holds the beam unit's resource, its index k and its HDR colour.
    beams = {}
    for k in range(3):
        raw = game_data[BEAM_TABLE + k * BEAM_STRIDE:BEAM_TABLE + (k + 1) * BEAM_STRIDE]
        unit, index = struct.unpack_from('<QI', raw, 0)
        colour = [round(v, 4) for v in struct.unpack_from('<3f', raw, 12)]
        if index != k:
            raise ValueError('the beam table moved: entry %d holds index %d' % (k, index))
        beams[str(k + 1)] = {'unit': '0x%016X' % unit, 'colour': colour}
    hue = {key: max(range(3), key=lambda i: b['colour'][i]) for key, b in beams.items()}
    if not (hue['1'] == 0 and beams['1']['colour'][0] > 10 * max(beams['1']['colour'][1:]) and hue['2'] == 2
            and beams['2']['colour'][0] == 0 and beams['3']['colour'][0] >= beams['3']['colour'][1]
            > 10 * beams['3']['colour'][2]):
        raise ValueError('the beam colours are no longer red, blue, yellow: %r' % beams)
    for key, label in (('1', 'red'), ('2', 'blue'), ('3', 'yellow')):
        beams[key]['colourName'] = label
    pings = {}
    for label, address in PING_COLOURS.items():
        pings[label] = [round(v, 4) for v in struct.unpack_from('<4f', game_data, address)]

    roots = catalogue_roots()
    bundles = residency.bundle_database()['packages']
    missing = sorted(n for n, r in roots.items() if r['package'] not in bundles)
    if roots['Orbital 120mm HE Barrage']['package'] not in bundles:
        raise ValueError('the package of the proof carrier is not in the bundle database')
    by_package = {r['package']: n for n, r in roots.items()}
    snapshots = []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        rows = {i: mem.ptr(mem.game + TABLE + 8 * i) for i in range(1, 150)}
        type_of_id = {mem.u32(p + 4): i for i, p in rows.items()}
        records = mem.ptr(mem.game + RECORDS)
        out = []
        for index in range(mem.u32(records + RECORD_COUNT) or 0):
            record = records + index * RECORD_STRIDE
            state = record + STATE
            count = mem.u32(state + ENTRY_COUNT)
            entries = []
            for k in range(min(count, MAX_ENTRIES)):
                at = state + ENTRIES + k * ENTRY_STRIDE
                entries.append({'type': mem.u32(at), 'uses': struct.unpack('<i', mem.read(at + USES, 4))[0],
                    'granted': mem.read(at + GRANTED, 1)[0]})
            out.append({'peer': '0x%016X' % mem.u64(record), 'entries': entries})
        store = mem.ptr(mem.game + SAVE_STORE)
        saved = [type_of_id.get(mem.u32(store + 0x4C + 8 * k)) for k in range(32)
            if mem.u32(store + 0x4C + 8 * k + 4)] if store and mem.read(store + 0x3C, 1)[0] else []
        snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        resident, refs, _ = residency.residency(snap, pins_loader)
        snap.close()
        held = sorted(by_package[p] for p in refs if p in by_package)
        record_types = {e['type'] for r in out for e in r['entries']}
        type_names = {i: n for n, r in roots.items() for i, p in rows.items() if mem.u32(p + 4) == r['id']}
        expected = sorted(type_names[t] for t in record_types if t in type_names)
        catalogue = mem.ptr(mem.game + 0x347CEF8)
        carrier = roots['Orbital 120mm HE Barrage']
        crow = rows[type_of_id[carrier['id']]]
        snapshots.append({'snapshot': name, 'records': out, 'savedLoadout': saved,
            'loadoutEntries': [e['type'] for r in out[:1] for e in r['entries'] if e['granted'] == 0],
            'stratagemPackagesHeld': held, 'recordTypePackages': expected,
            'recordTypesHeld': set(expected) <= set(held),
            'carrier120mm': {'type': type_of_id[carrier['id']], 'enabled': mem.u32(crow + 0xC0) & 1,
                'selectable': (mem.u32(crow + 0x80) >> 1) & 1, 'maxUses': struct.unpack('<i', mem.read(crow + 0x50, 4))[0],
                'owned': owned(mem, catalogue, carrier['id']), 'inRecord': type_of_id[carrier['id']] in record_types,
                'packageResident': bool(resident.get(carrier['package']))}})
        mem.close()
    # Every catalogued stratagem's beam and ping, by stable id [O] (the Runtime reads them live from the row).
    mem = base.Mem(SNAPSHOTS[0])
    rows = {mem.u32(p + 4): p for p in (mem.ptr(mem.game + TABLE + 8 * i) for i in range(1, 150)) if p}
    looks = {}
    for name, root in sorted(roots.items()):
        row = rows.get(root['id'])
        if row:
            looks[name] = {'id': root['id'], 'beam': mem.u32(row + BEAM_ROW), 'ping': mem.u32(row + PING_ROW)}
    mem.close()
    if looks['Orbital EMS Strike']['beam'] != 2 or looks['Orbital 120mm HE Barrage']['beam'] != 1:
        raise ValueError('the observed beams changed: %r' % {k: looks[k] for k in ('Orbital EMS Strike',
            'Orbital 120mm HE Barrage')})
    for s in snapshots:
        s['phase'] = MISSION.get(s['snapshot'], 'ship')
        in_mission = s['phase'] in ('alive', 'reinforced')
        if (in_mission and not (s['recordTypesHeld'] and s['stratagemPackagesHeld'])) or (
                not in_mission and s['stratagemPackagesHeld']) or s['carrier120mm']['packageResident']:
            raise ValueError('stratagem package residency: %r' % s['snapshot'])
        # In the mission the record's loadout entries are the save in order; at the mission end transition the record
        # is already rebuilt for the ship (loadout only, in reverse order).
        s['loadoutOrder'] = ('saved order' if s['loadoutEntries'] == s['savedLoadout'] else 'reversed'
            if s['loadoutEntries'] == list(reversed(s['savedLoadout'])) else 'other')
        if in_mission and s['loadoutOrder'] != 'saved order':
            raise ValueError('the mission record is not the saved loadout in order: %r' % s['snapshot'])

    # 5b. Every catalogued stratagem's full call-in package list (the A8 and F8 branches), from the mission snapshot.
    mem = base.Mem(PACKAGES_SNAPSHOT)
    rows_by_id = {mem.u32(p + 4): p for p in (mem.ptr(mem.game + TABLE + 8 * i) for i in range(1, 150)) if p}
    full, incomplete, unbundled = {}, [], []
    for name, root in sorted(roots.items()):
        row = rows_by_id.get(root['id'])
        if not row:
            continue
        found, complete = call_in_packages(mem, row)
        if not complete:
            incomplete.append(name)
        if found and found[0][0] == 'A8' and found[0][1] != root['package']:
            raise ValueError('%s: the live +0xA8 is not the catalogued root package' % name)
        if any(p not in bundles for _, p in found):
            unbundled.append(name)
            continue
        if found:
            full[str(root['id'])] = [{'package': '0x%016X' % p, 'via': via} for via, p in found]
    mem.close()
    eat = roots['EAT-17 Expendable Anti-Tank']
    if [i['via'] for i in full.get(str(eat['id']), [])] != ['F8']:
        raise ValueError('the EAT-17\'s call-in package is no longer its +0xF8 weapon\'s: %r' % full.get(str(eat['id'])))

    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': pins,
        'pinnedBytesMismatchPerSnapshot': relocation,
        'record': {'global': '0x%X' % RECORDS, 'stride': RECORD_STRIDE, 'count': RECORD_COUNT, 'state': STATE,
            'entries': ENTRIES, 'entryStride': ENTRY_STRIDE, 'entryCount': ENTRY_COUNT, 'maxEntries': MAX_ENTRIES,
            'entry': {'type': 0, 'uses': USES, 'granted': GRANTED, 'cooldownEnd': COOLDOWN}, 'key': 0x9E8},
        'callIns': {'global': '0x3326D98', 'count': 0x1C, 'entries': 0x60, 'stride': 0x28, 'key': 0x10, 'slot': 0x18,
            'done': 1},
        'stratagemPackages': {'roots': len(roots), 'inBundleDatabase': len(roots) - len(missing),
            'notInBundleDatabase': missing,
            'byStableId': {str(r['id']): '0x%016X' % r['package'] for r in roots.values() if r['package'] in bundles},
            # The full list the mission loader requests (5b): every A8 and F8 package, in the loader's order.
            'callIn': {'snapshot': PACKAGES_SNAPSHOT, 'weaponTable': '0x%X' % WEAPON_TABLE, 'byStableId': full,
                'incomplete': incomplete, 'notInBundleDatabase': unbundled}},
        'beacon': {'beamRow': BEAM_ROW, 'pingRow': PING_ROW, 'beamTable': '0x%X' % BEAM_TABLE, 'beamStride': BEAM_STRIDE,
            'beams': beams, 'pings': pings, 'pingRule': {'0': 'red', '2': 'blue', 'else': 'yellow'},
            'observed': looks},
        'snapshots': snapshots,
        'determinations': {
            'conversion': ('Possible as one 4-byte write of the local record entry\'s type, after the mission\'s last '
                'rebuild of the record and before the slot is used: the HUD, the matcher and activation read the type '
                'live, and uses, cooldown and in-flight beacons stay with the entry.'),
            'hud': 'The vanilla HUD refreshes the slot from a type change (arrows and icon); no HUD write.',
            'matcher': ('Two different types are two candidates; the carrier\'s code comes from its row; the result is '
                'the carrier type and activation takes its row.'),
            'ownership': 'No record writer or reader checks ownership or the saved loadout (Runtime policy: owned only).',
            'assets': ('An unselected carrier\'s package is not resident in the mission: it must be loaded first, the '
                'same native way the game holds record types\' packages.'),
            'savedLoadout': 'Untouched: the record is separate from the save store and the loadout screen\'s record.',
            'missionEnd': ('The record is rebuilt for the ship by the mission end transition (loadout only, reverse '
                'order): the conversion is discarded without a restore write.'),
            'reports': ('A slot still converted when the mission ends is in the mission_end / mission_reward events '
                'under the carrier\'s enum name; whether they leave the machine is not established.'),
            'multiplayer': 'Not synchronised: a direct write sends nothing; peers keep the token. Solo only.',
            'beacon': ('The beacon\'s colour is the row\'s BEAM (+0xD4: 1 red, 2 blue, 3 yellow, 0 none), chosen at '
                'landing from the thrown ball\'s type; the ping colour is a separate member (+0xB8: 0 red, 2 blue, else '
                'yellow). The delivery family (orbital, eagle, ...) and the call-in class decide neither: the Orbital '
                'EMS Strike is an orbital bombardment with a blue beam.')}}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; held = record types in the mission snapshots:',
        all(s['recordTypesHeld'] for s in snapshots if s['phase'] in ('alive', 'reinforced')), '; carrier',
        snapshots[3]['carrier120mm'], '; packages not in the bundle database', len(missing))


if __name__ == '__main__':
    main()
