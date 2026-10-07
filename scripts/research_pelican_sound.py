"""The Pelican chin gun's firing sound (research/docs/pelican-maelstrom-sound-F5FEE03DCFDB.md): where a projectile
weapon's firing audio is referenced, whether that reference lives in the per-instance ProjectileWeapon copy the Runtime
already makes for a Runtime Pelican's chin turret, and what the TD-110 Maelstrom's main gun (attach_tank_gun) uses.
Read-only, offline: the game.dll image, the seven retained snapshots of build F5FEE03DCFDB and the game's own bundles.
Nothing is written.

1. The reference [C]. Every shot resolves the weapon's ProjectileWeapon record through 0x515100 (its per-instance copy
   when it has one, else its type's) and keeps it for the whole shot (0x612A13, 0x612A1F). From THAT record it reads the
   per-shot Wwise event +0x104 (by fire mode: +0x10C for mode 4, +0x110 for mode 7; +0x218 while silenced, +0x22C), the
   MIDI switch +0xED and the loop start +0xFC (a loop weapon posts no per-shot event). The trigger's rising edge in the
   update posts the loop start +0xFC (0x6170FA) from the record it resolves (0x616B4C); the trigger release posts the
   loop stop +0x100 (0x616806) from the record it resolves (0x61678C). Nothing caches an event id. A WeaponData
   override (its type table +0x410, matched by the instance's selections +0x350) replaces +0x104 only with a non-zero
   event (0x614BA6-0x614BAB); the three weapons' tables are empty in every snapshot [O].
2. The posting [C]. A plain event goes to the engine's table [game+0x3326318] +0x338 with the WwiseWorld
   [[game+0x3326340]+0x10F8] and the weapon's own audio source (instance +0x1C, made on demand at its node +0x18); a MIDI
   weapon (+0xED) posts MIDI notes through +0x510 instead, three notes ahead at the shot interval (instance +0xC) with
   the record's timing randomization (+0xF0). The update passes the interval as the RTPC "CyclingTime" while the
   trigger is held (0x616BD5), for every weapon.
3. The one derived per-instance value [C][O]. At creation the instance record's +0x38 = the resolved record's +0xED
   (0x611CD9 -> 0x611D52 / 0x611D67); it is read only by the trigger release (0x6168B2): 0 destroys the weapon's audio
   source there, 1 keeps it for the notes still scheduled. Observed: every live projectile weapon of both mission
   snapshots has instance +0x38 = its resolved +0xED.
4. The Maelstrom's main gun [O]. Its type record (D58AE6A04EDB10DE) posts event E5CA1945 as MIDI (+0xED = 1), no loop.
   The chin turret posts the autocannon's 8D4641BA (+0xED = 0); the Gatling Sentry loops (+0xFC / +0x100). Every other
   byte of the firing-sound block (+0xED, +0xF0..+0x11B, +0x210..+0x21B, +0x22C) is the same in the chin turret and the
   Maelstrom's gun. All three are fire mode 1 (WeaponData type +0x90).
5. The bank [O]. E5CA1945 is an Event (5 Play actions, targets in the same bank) of content/audio/vehicle_storm_tank,
   listed by the Maelstrom's own package (tank_storm) and the Maelstrom slot-3 weapon's loadout package (a strict subset
   of it), both in the Runtime's asset catalogue. The Runtime requests tank_storm: the Maelstrom stratagem's own call-in
   package (live-proven loader path), resident in both mission snapshots; the residency check accepts either.

Output: research/pelican-maelstrom-sound-F5FEE03DCFDB.json.
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
import snapshot_image  # noqa: E402
from research_pelican import MISSION_SNAPSHOTS, WORLD, GATLING, TURRET_HMG, table_lookup  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/pelican-maelstrom-sound-F5FEE03DCFDB.json'
MAELSTROM_GUN = 0xD58AE6A04EDB10DE        # TD-110 Maelstrom slot 0, attach_tank_gun (research/vehicle-weapons)
MAELSTROM_STRATAGEM = 460870572           # its StratagemInfo stable id (domains/stratagem_slots.lua)
PW_TYPES = (0xF12E80, 542, 0x21E0, 0x268)  # component world table: offset, slots, records, stride
WD_TYPES = (0xF12BD8, 0x2DA, 0x2DA0, 0x4D0)
PW_MANAGER = 0x33266D8
ENGINE, WORLD_CONTEXT = 0x3326318, 0x3326340
# The firing-sound block of a ProjectileWeapon record (offset, size): the MIDI switch, the MIDI timing and stop delay,
# the loop start / stop, the per-shot events (by fire mode), the secondary events, the silenced events and switch.
BLOCKS = [(0xED, 1), (0xF0, 0x2C), (0x210, 0xC), (0x22C, 1)]
INSTANCE = {'stride': 0xA8, 'firing': 0x0, 'trigger': 0x1, 'interval': 0xC, 'decision': 0x10, 'sourceNode': 0x18,
    'source': 0x1C, 'queue': 0x20, 'queueSize': 16, 'midi': 0x38}

GAME = {
    # The shot (0x6128B0): the resolved record, kept for the whole shot, names the event.
    'soundShot': [
        (0x612A13, 'call 0x515100', None, 'a shot: the resolved ProjectileWeapon (its own copy when it has one) ...'),
        (0x612A1F, 'mov qword ptr [rsp + 0x68], rax', None, '... kept for the whole shot'),
        (0x612C88, 'call 0x756730', None, 'the weapon\'s fire mode (the weapon-data manager\'s entry) ...'),
        (0x612C8D, 'mov dword ptr [rbp - 0x58], eax', None, '... kept for the shot'),
        (0x614B50, 'mov eax, dword ptr [rbp - 0x58]', None, 'the per-shot event: by fire mode ...'),
        (0x614B5D, 'mov edi, dword ptr [rax + 0x10c]', None, '... mode 4: +0x10C ...'),
        (0x614B88, 'mov edi, dword ptr [rax + 0x110]', None, '... mode 7: +0x110 ...'),
        (0x614BA6, 'mov edi, dword ptr [rcx + 8]', None, '... an override record\'s event when one is set ...'),
        (0x614BAD, 'mov edi, dword ptr [rax + 0x104]', None, '... else the record\'s per-shot event +0x104'),
        (0x614BBB, 'lea r8, [rip + {rip}]', 0x2247628, 'the RTPC "rounds_fired" ...'),
        (0x614BD0, 'call qword ptr [rax + 0x378]', None, '... set on the weapon\'s audio source (engine table +0x378)'),
        (0x614BDB, 'movzx eax, byte ptr [r8 + 0x22c]', None, 'silenced (+0x22C) ...'),
        (0x614BE7, 'mov r14d, dword ptr [r8 + 0x218]', None, '... its silenced per-shot event +0x218'),
        (0x614BFC, 'mov r14d, edi', None, 'the shot\'s event'),
        (0x614C07, 'mov edi, dword ptr [r8 + 0x114]', None, 'the secondary event +0x114 ...'),
        (0x614C12, 'mov eax, dword ptr [r8 + 0x118]', None, '... (+0x118 while silenced)'),
        (0x614C1E, 'cmp byte ptr [r8 + 0x94], 0', None, 'networked fire events (+0x94: 0 on all three weapons)'),
        (0x614C4D, 'cmp byte ptr [r8 + 0xed], 0', None, 'MIDI (+0xED) ...'),
        (0x614C55, 'je 0x615050', None, '... not MIDI: the plain event'),
        (0x615050, 'cmp dword ptr [r8 + 0xfc], 0', None, 'a loop weapon (+0xFC) ...'),
        (0x61505A, 'cmp dword ptr [rbp - 0x58], 2', None, '... posts no per-shot event (but in fire mode 2)'),
        (0x61508D, 'mov r10, qword ptr [rip + {rip}]', ENGINE, 'the engine table ...'),
        (0x61509D, 'mov rcx, qword ptr [rip + {rip}]', WORLD_CONTEXT, '... the world context ...'),
        (0x6150AA, 'mov edx, r14d', None, '... the event ...'),
        (0x6150AD, 'mov rcx, qword ptr [rcx + 0x10f8]', None, '... on its WwiseWorld (+0x10F8) ...'),
        (0x6150B4, 'call qword ptr [r10 + 0x338]', None, '... posted (engine table +0x338) on the weapon\'s source'),
        (0x614DBD, 'call 0xfe7410', None, 'the secondary event ...'),
        (0xFE7410, 'test r8d, r8d', None, '... none (0) ...'),
        (0xFE7413, 'je 0xfe74b5', None, '... does nothing'),
    ],
    # The per-shot event override: an entry of the weapon's WeaponData type table +0x410 (8 x 0x14) whose id one of
    # its WeaponData instance's selections (+0x350, 4) names; its event (+8) replaces +0x104 only when not 0.
    'soundOverride': [
        (0x612A82, 'mov rcx, qword ptr [rip + {rip}]', 0x3326CE0, 'the weapon-data manager ...'),
        (0x612BD4, 'call 0x509a40', None, '... the weapon\'s resolved WeaponData record ...'),
        (0x612BEE, 'lea r13, [rax + 0x410]', None, '... its override entries (+0x410, 8 x 0x14) ...'),
        (0x612C04, 'lea rax, [r11 + 0x350]', None, '... against its instance\'s selections (+0x350, 4) ...'),
        (0x612C11, 'cmp dword ptr [rax], ecx', None, '... by id ...'),
        (0x612C50, 'mov qword ptr [rbp + 0x30], rcx', None, '... the matched entry, kept'),
        (0x614B9D, 'mov rcx, qword ptr [rbp + 0x30]', None, 'the shot: a matched override ...'),
        (0x614BA6, 'mov edi, dword ptr [rcx + 8]', None, '... its event ...'),
        (0x614BA9, 'test edi, edi', None, '... only when not 0 ...'),
        (0x614BAB, 'jne 0x614bb3', None, '... else the record\'s +0x104'),
    ],
    # The MIDI path: notes posted through the engine table +0x510, three ahead at the shot interval.
    'soundMidi': [
        (0x614D37, 'je 0x614dfd', None, 'MIDI, fire modes 1 and 3: notes scheduled ahead'),
        (0x614D96, 'call qword ptr [rax + 0x510]', None, 'MIDI, other modes: one note posted (engine table +0x510)'),
        (0x614ED4, 'movss xmm1, dword ptr [r15 + 0xf0]', None, 'the record\'s MIDI timing randomization (+0xF0)'),
        (0x614FA8, 'mov r10, qword ptr [rax + 0x510]', None, 'a scheduled note ...'),
        (0x614FC2, 'call r10', None, '... posted'),
        (0x61500A, 'addss xmm7, dword ptr [rax + 0xc]', None, 'the next one a shot interval (instance +0xC) later ...'),
        (0x61500F, 'cmp ecx, 3', None, '... three ahead'),
    ],
    # The weapon's audio source: instance +0x1C, made on demand at its node (+0x18, resolved at creation from +0x21C).
    'soundSource': [
        (0x611C72, 'mov edx, dword ptr [r13 + 0x21c]', None, 'creation: the source node by its name (+0x21C) ...'),
        (0x611CAD, 'mov dword ptr [rbp + 0x18], eax', None, '... into the instance record +0x18'),
        (0x614A3B, 'mov r8, qword ptr [rax + 0x5a0]', None, 'a shot: the weapon\'s source (engine table +0x5A0) ...'),
        (0x614A46, 'mov edx, dword ptr [rax + rcx + 0x1c]', None, '... instance +0x1C ...'),
        (0x614A60, 'mov rax, qword ptr [rax + 0x590]', None, '... made when missing (engine table +0x590) ...'),
        (0x614A6F, 'mov r14d, dword ptr [rcx + rax + 0x18]', None, '... at its node'),
    ],
    # The update (0x616AC0): the resolved record; the barrel cadence; the loop start on the trigger's rising edge.
    'soundUpdate': [
        (0x616B4C, 'call 0x515100', None, 'the update: the resolved ProjectileWeapon ...'),
        (0x616B54, 'mov qword ptr [rsp + 0x78], rax', None, '... kept'),
        (0x616B97, 'cmp byte ptr [r14 + rbp + 1], dil', None, 'while the trigger (instance +1) is held ...'),
        (0x616BAA, 'movss xmm6, dword ptr [r14 + rbp + 0xc]', None, '... the shot interval ...'),
        (0x616BCC, 'call 0x616910', None, '... on the weapon\'s source ...'),
        (0x616BD5, 'lea r8, [rip + {rip}]', 0x2247638, '... as the RTPC "CyclingTime" ...'),
        (0x616BE2, 'call rbx', None, '... every update, for every weapon'),
        (0x616D9E, 'mov r12, qword ptr [rsp + 0x78]', None, 'the resolved record ...'),
        (0x616DCA, 'cmp byte ptr [r12 + 0xed], dil', None, '... its MIDI switch ...'),
        (0x616E4C, 'mov byte ptr [r14 + rbp + 0x38], al', None, '... re-derived into instance +0x38 when its wielder '
            'first becomes valid'),
        (0x61702D, 'mov r12, qword ptr [rsp + 0x78]', None, 'the resolved record ...'),
        (0x6170F0, 'cmp byte ptr [r12 + 0xed], dil', None, '... not MIDI ...'),
        (0x6170FA, 'mov edx, dword ptr [r12 + 0xfc]', None, '... its loop start +0xFC ...'),
        (0x61710C, 'mov eax, dword ptr [r12 + 0x210]', None, '... (+0x210 while silenced) ...'),
        (0x617134, 'call qword ptr [rsi + 0x338]', None, '... posted on the trigger\'s rising edge'),
    ],
    # The trigger release (0x616760): the resolved record; the MIDI notes stopped or the loop stop posted; the source.
    'soundRelease': [
        (0x61678C, 'call 0x515100', None, 'the release: the resolved ProjectileWeapon ...'),
        (0x6167C9, 'cmp byte ptr [r14 + 0xed], r13b', None, '... MIDI ...'),
        (0x6167F1, 'call qword ptr [rax + 0x528]', None, '... its notes stopped (engine table +0x528) ...'),
        (0x616806, 'mov edi, dword ptr [r14 + 0x100]', None, '... else its loop stop +0x100 ...'),
        (0x616816, 'mov eax, dword ptr [r14 + 0x214]', None, '... (+0x214 while silenced) ...'),
        (0x616855, 'call qword ptr [r10 + 0x338]', None, '... posted'),
        (0x6168B2, 'cmp byte ptr [rbp + 0x38], r13b', None, 'instance +0x38 = 0 ...'),
        (0x6168E0, 'call qword ptr [rax + 0x598]', None, '... the weapon\'s source destroyed (engine table +0x598)'),
        (0x6188A8, 'call qword ptr [rax + 0x598]', None, 'the weapon\'s other teardown routines destroy its source '
            'unconditionally'),
        (0x6189A8, 'call qword ptr [rax + 0x598]', None, '...'),
        (0x618A88, 'call qword ptr [rax + 0x598]', None, '...'),
    ],
    # Creation (0x611B20): the one value derived from the record's sound: instance +0x38.
    'soundCreation': [
        (0x611BD8, 'call 0x515100', None, 'creation: the resolved ProjectileWeapon ...'),
        (0x611CD9, 'cmp byte ptr [r13 + 0xed], 0', None, '... MIDI (+0xED)? ...'),
        (0x611D52, 'mov byte ptr [rbp + 0x38], 0', None, '... no: instance +0x38 = 0 ...'),
        (0x611D67, 'mov byte ptr [rbp + 0x38], 1', None, '... yes: instance +0x38 = 1 ...'),
        (0x611E48, 'lea r8, [rip + {rip}]', 0x2247638, '... and its source made at once with "CyclingTime"'),
    ],
}


def block_of(raw):
    return b''.join(raw[o:o + n] for o, n in BLOCKS)


def sound_of(raw):
    u32 = lambda o: struct.unpack_from('<I', raw, o)[0]
    return {'midi': raw[0xED], 'loopStart': '%08X' % u32(0xFC), 'loopStop': '%08X' % u32(0x100),
        'single': '%08X' % u32(0x104), 'singleMode4': '%08X' % u32(0x10C), 'singleMode7': '%08X' % u32(0x110),
        'secondary': '%08X' % u32(0x114), 'silenced': raw[0x22C], 'sourceNode': '%08X' % u32(0x21C),
        'networkedFireEvents': raw[0x94], 'midiTiming': list(struct.unpack_from('<2f', raw, 0xF0)),
        'midiStopDelay': struct.unpack_from('<f', raw, 0xF8)[0], 'lowAmmoRounds': u32(0x68),
        'lowAmmoEvent': '%08X' % u32(0x6C), 'casingAudio': '%08X' % u32(0xD8), 'blockBytes': block_of(raw).hex()}


def hirc(raw):
    at = raw.find(b'HIRC')
    if at < 0:
        return {}
    _size, count = struct.unpack_from('<II', raw, at + 4)
    out, o = {}, at + 12
    for _ in range(count):
        kind = raw[o]
        size, oid = struct.unpack_from('<II', raw, o + 1)
        out[oid] = (kind, raw[o + 9:o + 5 + size])
        o += 5 + size
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    strings = {'%X' % rva: game_data[rva:game_data.index(b'\0', rva)].decode() for rva in (0x2247628, 0x2247638)}
    if strings != {'2247628': 'rounds_fired', '2247638': 'CyclingTime'}:
        raise ValueError('the RTPC names moved: %r' % strings)

    # [O] The three types' firing sound and fire mode, in every retained snapshot that holds the type tables.
    kinds = {'chinTurret': TURRET_HMG, 'gatlingSentry': GATLING, 'maelstromMainGun': MAELSTROM_GUN}
    types = {}
    for name in SNAPSHOTS:
        m = base.Mem(name)
        w = m.ptr(m.game + WORLD)
        pw_table, wd_table = (m.ptr(w + PW_TYPES[0]), m.ptr(w + WD_TYPES[0])) if w else (None, None)
        found = {}
        for key, resource in kinds.items():
            i = table_lookup(m, pw_table, PW_TYPES[1], resource) if pw_table else None
            j = table_lookup(m, wd_table, WD_TYPES[1], resource) if wd_table else None
            if i is None or j is None:
                continue
            raw = m.read(pw_table + PW_TYPES[2] + PW_TYPES[3] * i, PW_TYPES[3])
            wd = m.read(wd_table + WD_TYPES[2] + WD_TYPES[3] * j, WD_TYPES[3])
            found[key] = {**sound_of(raw), 'projectile': struct.unpack_from('<I', raw, 0)[0],
                'rpm': struct.unpack_from('<f', raw, 8)[0], 'fireMode': struct.unpack_from('<I', wd, 0x90)[0],
                'overrideEvents': [struct.unpack_from('<I', wd, 0x410 + 0x14 * e + 8)[0] for e in range(8)]}
        # How many weapon types use the override table at all (it is real data, not padding).
        if wd_table:
            used = total = 0
            for slot in range(WD_TYPES[1]):
                key, index = struct.unpack('<QQ', m.read(wd_table + 16 * slot, 16))
                if key:
                    wd = m.read(wd_table + WD_TYPES[2] + WD_TYPES[3] * (index & 0xFFFFFFFF), WD_TYPES[3])
                    total += 1
                    used += any(struct.unpack_from('<I', wd, 0x410 + 0x14 * e + 8)[0] for e in range(8))
            found['overrideTable'] = {'weaponTypes': total, 'withOverrideEvents': used}
        m.close()
        types[name] = found
    complete = [name for name, found in types.items() if set(kinds) <= set(found)]
    if not set(MISSION_SNAPSHOTS) <= set(complete):
        raise ValueError('the mission snapshots do not hold all three types: %r' % {k: list(v) for k, v in types.items()})
    if len({json.dumps(types[name], sort_keys=True) for name in complete}) != 1:
        raise ValueError('the three types\' firing sounds differ between snapshots')
    t = types[complete[0]]
    chin, gat, mael = t['chinTurret'], t['gatlingSentry'], t['maelstromMainGun']
    if not (chin['midi'] == 0 and chin['single'] == '8D4641BA' and chin['loopStart'] == '00000000'
            and mael['midi'] == 1 and mael['single'] == 'E5CA1945' and mael['loopStart'] == '00000000'
            and gat['midi'] == 0 and gat['loopStart'] == '98F18D8B' and gat['loopStop'] == '0C5CA529'
            and gat['single'] == '00000000' and chin['fireMode'] == mael['fireMode'] == gat['fireMode'] == 1
            and chin['networkedFireEvents'] == mael['networkedFireEvents'] == 0
            and chin['silenced'] == mael['silenced'] == 0):
        raise ValueError('the firing sounds changed: %r' % t)
    # No override can replace the per-shot event of these three weapons (their tables are empty), while the table is
    # used by other weapon types.
    if any(any(t[k]['overrideEvents']) for k in kinds) or not t['overrideTable']['withOverrideEvents']:
        raise ValueError('the per-shot event overrides changed: %r' % {k: t[k]['overrideEvents'] for k in kinds})
    a, b = bytes.fromhex(chin['blockBytes']), bytes.fromhex(mael['blockBytes'])
    differ, cursor = [], 0
    for offset, size in BLOCKS:
        for k in range(size):
            if a[cursor + k] != b[cursor + k]:
                differ.append(offset + k)
        cursor += size
    if differ != [0xED, 0x104, 0x105, 0x106, 0x107]:
        raise ValueError('the chin turret\'s and the Maelstrom gun\'s firing-sound blocks differ elsewhere: %r' % differ)

    # [O] The derived instance value: every live projectile weapon's instance +0x38 = its resolved record's +0xED.
    instances = {}
    for name in MISSION_SNAPSHOTS:
        m = base.Mem(name)
        w = m.ptr(m.game + WORLD)
        pw_table = m.ptr(w + PW_TYPES[0])
        mgr = m.ptr(m.game + PW_MANAGER)
        keys, cap, empty = m.ptr(mgr + 0x50), m.u32(mgr + 0x58), m.u32(mgr + 0x5C)
        rows = []
        for k in range(cap):
            entity, index = struct.unpack('<II', m.read(keys + 8 * k, 8))
            if entity == empty or index == 0xFFFFFFFF:
                continue
            handle = m.ptr(m.ptr(mgr + 0x68) + 8 * index)
            resource = m.u64(handle)
            ti = table_lookup(m, pw_table, PW_TYPES[1], resource)
            record = m.read(pw_table + PW_TYPES[2] + PW_TYPES[3] * ti, PW_TYPES[3])
            inst = m.read(m.ptr(mgr + 0x78) + INSTANCE['stride'] * index, INSTANCE['stride'])
            rows.append({'entity': entity, 'resource': '%016X' % resource, 'recordMidi': record[0xED],
                'instanceMidi': inst[INSTANCE['midi']], 'source': '%08X' % struct.unpack_from('<I', inst, 0x1C)[0],
                'idleQueue': inst[0x20:0x30] == bytes(16)})
        copies = m.u32(mgr + 0xC8)
        m.close()
        if copies or not rows or any(r['recordMidi'] != r['instanceMidi'] for r in rows):
            raise ValueError('%s: instance +0x38 is not the resolved +0xED: %r' % (name, rows))
        instances[name] = {'copies': copies, 'weapons': len(rows), 'midi': sum(r['recordMidi'] for r in rows),
            'rule': 'instance +0x38 == resolved +0xED for every weapon', 'rows': rows}

    # [O] The banks: which bank defines each event, and which packages list the Maelstrom's.
    _chunk = gdata.chunk

    @functools.lru_cache(maxsize=4096)
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

    def listing(package):
        """A package resource's {(name, type)}: {u32 0 or 1, u32 (varies), u32 count, u32 0} then count (type, name)."""
        raw = data.read(*packages[package])
        _version, _word, count = struct.unpack_from('<III', raw, 0)
        if len(raw) != 16 + 16 * count:
            raise ValueError('%016X: not a package listing' % package)
        return {struct.unpack_from('<QQ', raw, 16 + 16 * i)[::-1] for i in range(count)}

    def bank_name(resource):
        raw = data.read(*deps[resource])
        return raw[8:].split(b'\0')[0].decode('latin-1')
    events = {'E5CA1945': None, '8D4641BA': None, '98F18D8B': None, '0C5CA529': None}
    candidates = {0x35756AA5B47C3F2B, 0x0914072DBEC9D227, 0x9078FA36A3602B78, 0xF76157C8E398C764}
    found_events = collections.defaultdict(list)
    maelstrom_event = None
    for resource in sorted(candidates):
        objects = hirc(data.read(*banks[resource]))
        for event in events:
            entry = objects.get(int(event, 16))
            if entry and entry[0] == 4:
                found_events[event].append({'bank': '%016X' % resource, 'name': bank_name(resource)})
                if event == 'E5CA1945':
                    body = entry[1]
                    actions = struct.unpack_from('<%dI' % body[0], body, 1)
                    plays = []
                    for action in actions:
                        kind, raw = objects[action]
                        action_type, target = struct.unpack_from('<HI', raw, 0)
                        plays.append({'action': '%08X' % action, 'type': '%04X' % action_type, 'target': '%08X' % target,
                            'targetKind': objects[target][0] if target in objects else None})
                    maelstrom_event = {'bank': '%016X' % resource, 'actions': plays}
    MAEL_BANK = 0x35756AA5B47C3F2B
    if not (maelstrom_event and maelstrom_event['bank'] == '%016X' % MAEL_BANK
            and all(p['type'] == '0403' and p['targetKind'] in (2, 5) for p in maelstrom_event['actions'])
            and bank_name(MAEL_BANK) == 'content/audio/vehicle_storm_tank'
            and [e['name'] for e in found_events['8D4641BA']] == ['content/audio/wep_autocannon',
                'content/audio/vehicle_shuttle']
            and [e['name'] for e in found_events['98F18D8B']] == ['content/audio/stratagems_sentry_gatling']):
        raise ValueError('the firing events moved between banks: %r %r' % (maelstrom_event, dict(found_events)))
    listed_by = sorted('%016X' % p for p in packages if (MAEL_BANK, BANK) in listing(p))
    residency = json.loads((ROOT / 'research/package-residency-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    catalogue = []
    for key, item in sorted(residency['catalog'].items()):
        package = (item.get('dependency') or {}).get('package')
        if package and package[2:] in listed_by and item['dependency'].get('inBundleDatabase'):
            items = listing(int(package, 16))
            catalogue.append({'key': key, 'label': item['label'], 'package': package,
                'name': item['dependency']['name'] or 'unnamed loadout package of ' + item['label'],
                'bytes': sum(sizes.get(i, 0) for i in items), 'resources': len(items),
                'banks': sorted(bank_name(n) for n, t in items if t == BANK)})
    catalogue.sort(key=lambda c: c['bytes'])
    if [c['key'] for c in catalogue] != ['mounted_weapon/mounted-weapon/v1/td-110-maelstrom-slot-3-weapon/'
            '605fcfcd1be790c4', 'vehicle/TD-110 Maelstrom']:
        raise ValueError('the catalogued packages listing the Maelstrom\'s bank changed: %r' % catalogue)
    subset = listing(int(catalogue[0]['package'], 16)) <= listing(int(catalogue[1]['package'], 16))
    # The package the Runtime requests: the Maelstrom stratagem's own call-in package (the loader requests a call-in
    # package exactly like a carrier's, live-proven for the Gatling Sentry's), which is also the vehicle's own loadout
    # package. The smaller slot-3 weapon package is a strict subset, but the game did not load it in either mission
    # snapshot and no mounted-weapon package load is live-proven (research/package-residency-live-evidence.json, test C:
    # INCONCLUSIVE); the residency check accepts either.
    slots = json.loads((ROOT / 'research/stratagem-slot-conversion-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    call_in = slots['stratagemPackages']['byStableId'][str(MAELSTROM_STRATAGEM)]
    requested = [c for c in catalogue if c['package'] == call_in]
    if len(requested) != 1 or requested[0]['key'] != 'vehicle/TD-110 Maelstrom':
        raise ValueError('the Maelstrom\'s call-in package is not a catalogued package listing its bank: %r' % call_in)
    # [O] Whether a package listing it was resident in the retained mission snapshots (the loadouts there).
    import research_package_residency as rpr
    loader = rpr.loader_pins(snapshot_image.Snapshot(build_profile.SNAPSHOT))
    resident = {}
    for name in MISSION_SNAPSHOTS:
        s = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        states, _refs, _capacity = rpr.residency(s, loader)
        s.close()
        resident[name] = {c['package']: bool(states.get(int(c['package'], 16))) for c in catalogue}

    def raw32(value):
        return struct.pack('<I', int(value, 16)).hex()
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'engine': {'table': '0x%X' % ENGINE, 'worldContext': '0x%X' % WORLD_CONTEXT, 'wwiseWorld': 0x10F8,
            'postEvent': 0x338, 'postMidi': 0x510, 'setRtpc': 0x378, 'source': 0x5A0, 'makeSource': 0x590,
            'destroySource': 0x598, 'stopNote': 0x528, 'rtpcs': strings},
        # The firing-sound block of a ProjectileWeapon record (offsets in the 0x268-byte record and its copy).
        'record': {'stride': PW_TYPES[3], 'midi': 0xED, 'midiTiming': 0xF0, 'midiStopDelay': 0xF8, 'loopStart': 0xFC,
            'loopStop': 0x100, 'single': 0x104, 'singleMode4': 0x10C, 'singleMode7': 0x110, 'secondary': 0x114,
            'secondarySilenced': 0x118, 'silencedLoopStart': 0x210, 'silencedLoopStop': 0x214, 'silencedSingle': 0x218,
            'sourceNode': 0x21C, 'silenced': 0x22C, 'networkedFireEvents': 0x94,
            'blocks': [list(b) for b in BLOCKS], 'span': [0xE0, PW_TYPES[3]]},
        # The weapon's instance record (0xA8 bytes; projectile_weapon manager +0x78).
        'instance': INSTANCE,
        'observed': {'types': types, 'completeIn': complete, 'instances': instances, 'resident': resident},
        'chin': {'resource': '%016X' % TURRET_HMG, 'midi': chin['midi'], 'event': chin['single'],
            'blockBytes': chin['blockBytes'], 'banks': found_events['8D4641BA']},
        'gatlingSentry': {'resource': '%016X' % GATLING, 'loopStart': gat['loopStart'], 'loopStop': gat['loopStop'],
            'banks': found_events['98F18D8B']},
        'sounds': {'maelstrom_main_gun': {
            'id': 'firing-sound/v1/td-110-maelstrom/attach-tank-gun',
            'label': 'TD-110 Maelstrom main gun', 'vehicle': 'TD-110 Maelstrom', 'mount': 'attach_tank_gun',
            'resource': '%016X' % MAELSTROM_GUN, 'event': mael['single'], 'midi': mael['midi'],
            'blockBytes': mael['blockBytes'], 'fireMode': mael['fireMode'],
            'bank': {'name': 'content/audio/vehicle_storm_tank', 'resource': '%016X' % MAEL_BANK,
                'event': maelstrom_event},
            # The copy's writes (the only differences from the chin turret's own block) and the instance's.
            'writes': [{'name': 'midi', 'offset': 0xED, 'size': 1, 'from': '00', 'to': '01'},
                {'name': 'event', 'offset': 0x104, 'size': 4, 'from': raw32(chin['single']),
                    'to': raw32(mael['single'])}],
            'instanceWrites': [{'name': 'midi', 'offset': INSTANCE['midi'], 'size': 1, 'from': '00', 'to': '01'}],
            'packages': catalogue, 'assetKey': requested[0]['key'], 'stratagem': MAELSTROM_STRATAGEM,
            'assetWhy': 'the Maelstrom stratagem\'s own call-in package (the vehicle\'s loadout package; resident in '
                'both mission snapshots, where the game loaded it); the smaller slot-3 weapon package is a strict '
                'subset but was never loaded by the game there and no mounted-weapon package load is live-proven',
            'smallerIsSubset': subset, 'listedBy': listed_by}},
        'rule': 'a projectile weapon\'s firing sound is its RESOLVED ProjectileWeapon record\'s +0xED (MIDI) and its '
            'events (+0x104 per shot, +0xFC / +0x100 loop), read at every shot and trigger transition; the per-instance '
            'copy the Runtime makes for a chin turret owns them; instance +0x38 is the one value derived from them at '
            'creation (the source kept at release for MIDI)',
        'verdict': 'instance-local: three guarded writes of the chin turret\'s own copy (+0xED, +0x104) and its own '
            'instance record (+0x38); the bank must be resident (a catalogued package that lists it)',
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; complete in', len(complete), 'snapshots; bank',
        'listed by', listed_by)


if __name__ == '__main__':
    main()
