"""Armory and loadout presentation: the trait labels a weapon shows, and where the shown stats come from. Read-only.

Proves on build F5FEE03DCFDB, from the pinned type library and entity table, game.dll code and the retained
snapshots:

1. Trait labels are stored, not computed. LoadoutEntryComponentData (index 386 rows, 193 records of 32 bytes, then
   a parallel u32[193]) gives every loadout item {+0 id (name length 2), +4 LoadoutItemType, +8 u32 (11), +12 u32[5]
   (14)}. The five u32 at +12 are the item's trait tags: localization string IDs, 0 = empty slot.
2. The armory reads exactly those. The trait view-model builder (0x14E4A20) looks the item up in the LoadoutEntry
   table (0x4F5C10: resource mod 386, records at (record + 0xC1) * 32), and for each of the five slots whose ID is
   non-zero creates a trait object whose Text is the localized string of that ID (0x17802E0). Its only caller is the
   item view-model builder (0x14E7430), which menu presenters run on entering a menu; the armory template binds
   SelectedItem.WeaponData.Traits (ObservableCollection<testament.WeaponTrait>). Nothing reads DamageInfo armor
   penetration to choose a label: a weapon shows LIGHT ARMOR PENETRATING because its record holds that string ID.
3. Stat rows are computed. The stat row builder (0x14E41F0) chooses WeaponStatType rows by output family (melee,
   beam and spray lookups, beam fire mode 6) and computes their values from the weapon's component data and
   customization when the menu builds the item; no struct in the type library embeds WeaponStatType, so there is no
   stored display value for damage, capacity, recoil or fire rate.
4. The strings tables loaded in the ship snapshot (header 0x3E85F3AE, version 1, count, language, sorted IDs,
   offsets relative to the header) name every tag used by a weapon except two (EAT-411 and EAT-700), in 15
   languages; 0x03F97B57 is en-US.
5. Weapon-function mode presentation lives on the fired projectile. ProjectileInfo +4 and +8 are its long names
   (upper and mixed case) and +12 its short mode label (localization string IDs, hidden name length 10 each); +16 is a
   64-bit resource (length 8): its HUD icon. Every native selectable mode reads as these members: AC-8 APHET / FLAK,
   GR-8 HEAT / HE, the Halt FLECHETTES / STUN magazines, guidance on / off, with icons under
   content/ui/mission/hud/weapon_function/. A projectile no menu shows keeps a placeholder label (no string) and
   the shared skull icon, which is therefore the menu's default. The menu reader itself is not traced; the data
   pattern is exact across every native mode.

Requires the research-only package capstone.
Output: research/weapon-presentation-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import json
import mmap
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import research_weapon_fire_modes as fire_modes  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/weapon-presentation-F5FEE03DCFDB.json'
SHIP = 'F5FEE03DCFDB-20260926T222226Z.hd2snap'
MISSION = 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'
COMPONENT, RECORD = 'LoadoutEntryComponentData', 'LoadoutEntryComponent'
INDEX_ROWS, RECORDS, RECORD_SIZE, TAGS_OFFSET, TAG_SLOTS = 386, 193, 32, 12, 5
STRINGS_MAGIC = struct.pack('<II', 0x3E85F3AE, 1)
EN_US, EN_GB = 0x03F97B57, 0x6F4515CB
# Armor-penetration class labels: the tag a weapon shows for its penetration (exact en-US text).
PENETRATION = {'light': 'LIGHT ARMOR PENETRATING', 'medium': 'MEDIUM ARMOR PENETRATING',
    'heavy': 'HEAVY ARMOR PENETRATING', 'light_anti_tank': 'LIGHT ANTI-TANK', 'anti_tank': 'ANTI-TANK'}
# ProjectileInfo presentation members: offset -> (member, hidden name length, storage).
MODE_LAYOUT = {4: ('long name (upper case)', 10, 'UINT32'), 8: ('long name', 10, 'UINT32'),
    12: ('short mode label', 10, 'UINT32'), 16: ('HUD icon resource', 8, 'UINT64')}
ICON_PREFIX = 'content/ui/mission/hud/weapon_function/'
DEFAULT_ICON = 'content/ui/shared/misc/skull_icon'
# Native strings offered as mode labels besides those a projectile already uses (exact en-US text, every language).
EXTRA_LABELS = ('GAS', 'ARC', 'INCENDIARY', 'SMOKE', 'STANDARD')
# The generic fallback for a mode whose label has no native icon: the one weapon-function icon that shows a plain
# round (a single cartridge) and implies no effect. Reviewed by decoding the installed textures (never shipped):
# every other icon shows a specific effect or function (stun lightning, explosions, a tank, a jet, darts, pellets,
# guidance reticles, burst rounds, C4, an airstrike); the default skull belongs to another texture set.
GENERIC_ICON = 'ammo_slug'
ICON_VISUALS = {'ammo_slug': 'a single plain cartridge', 'ammo_stun': 'lightning around a round (stun)',
    'ammo_he': 'an explosion burst', 'ammo_heat': 'an explosion against a tank', 'ammo_frag': 'a fragmenting burst',
    'ammo_aphet': 'an armour-piercing round with a burst', 'ammo_flak': 'a jet (anti-air)',
    'ammo_flechettes': 'a dart', 'ammo_buckshot': 'a cluster of pellets', 'burst_fire': 'three stacked rounds',
    'guidance_on': 'a guidance reticle (guided)', 'guidance_off': 'a guidance reticle (unguided)',
    'firemode_deploy_c4': 'a deployable charge', 'airstrike': 'an aircraft with a blast',
    'default': 'a skull (another texture set, not a weapon-function icon)'}
XAML_KEYS = [b'Content="{Binding Path=SelectedItem.WeaponData.Traits', b'ObservableCollection<testament.WeaponTrait>',
    b'TabControl_ContentTemplate_SubLevel_Armory_PrimaryWeapons']

GAME_PROOFS = {
    'loadoutEntryLookup': [
        (0x4F5C37, 'imul eax, edx, 0x182', None, 'LoadoutEntry index: resource mod 386'),
        (0x4F5C7D, 'cmp r9d, 0x182', None, 'probes at most 386 rows'),
        (0x4F5C91, 'add rax, 0xc1', None, 'record + 0xC1 (386 x 16 / 32)'),
        (0x4F5C97, 'shl rax, 5', None, '32-byte records after the index'),
    ],
    'traitBuilder': [
        (0x14E4A2F, 'call 0x4f5c10', None, 'the trait builder looks up the item LoadoutEntry'),
        (0x14E4A6D, 'lea r14, [rax + 0xc]', None, 'its tag slots (+12)'),
        (0x14E4A76, 'cmp dword ptr [r14], r12d', None, 'an empty slot (0) is skipped'),
        (0x14E4A86, 'mov edx, 0x70', None, 'one 0x70-byte trait object per tag'),
        (0x14E4AED, 'mov ecx, dword ptr [r13 + rax*4 + 0xc]', None, 'the slot string ID'),
        (0x14E4AF2, 'call 0x17802e0', None, 'is localized'),
        (0x14E4B59, 'lea rcx, [rip + {rip}]', 0x22CE924, '"Text": the trait text is that string'),
        (0x14E4B87, 'call qword ptr [rax + 0x28]', None, 'added to the traits collection'),
        (0x14E4BAA, 'add r14, 4', None, 'next slot'),
        (0x14E4BAE, 'cmp ebp, 5', None, 'five slots'),
        (0x14E7DD5, 'call 0x14e4a20', None, 'its only caller: the item view-model builder'),
    ],
    'statRows': [
        (0x14E4243, 'call 0x11e7ae0', None, 'the stat row builder classifies the item'),
        (0x14E426E, 'call 0x50e360', None, 'melee weapon lookup'),
        (0x14E42A8, 'call 0x50e880', None, 'beam/spray weapon lookup'),
        (0x14E42B2, 'cmp dword ptr [rax + 0x64], 6', None, 'beam fire mode 6 (Trident) shows its own rows'),
        (0x14E42F1, 'call 0x50ed80', None, 'weapon customization lookup (values include the equipped options)'),
    ],
}


def prove_layout(native):
    lib = native.typelib_module
    desc = lib.layout(native.typelib, COMPONENT, structured=True)['members']
    if len(desc) != 3 or desc[0]['array_or_bits'] != INDEX_ROWS or desc[1]['array_or_bits'] != RECORDS \
            or desc[1]['size64'] != RECORDS * RECORD_SIZE or desc[2]['array_or_bits'] != RECORDS:
        raise ValueError('LoadoutEntryComponentData layout changed')
    members = lib.layout(native.typelib, RECORD, structured=True)['members']
    shape = [(m['offset64'], m['size64'], m['name'].split('inferred_length=')[-1]) for m in members]
    if shape != [(0, 4, '2'), (4, 4, '4'), (8, 4, '11'), (12, 20, '14')]:
        raise ValueError('LoadoutEntryComponent layout changed: %r' % shape)
    if members[1]['type_hash'] != native.probe.dl_hash('LoadoutItemType'):
        raise ValueError('LoadoutEntryComponent +4 is no longer LoadoutItemType')
    return {'component': COMPONENT, 'indexRows': INDEX_ROWS, 'records': RECORDS, 'recordSize': RECORD_SIZE,
        'recordOffset': INDEX_ROWS * 16, 'trailingArray': 'u32[193] (name length 14), after the records',
        'record': [{'offset': 0, 'member': 'id', 'nameLength': 2}, {'offset': 4, 'member': 'type (LoadoutItemType)',
            'nameLength': 4}, {'offset': 8, 'member': 'u32', 'nameLength': 11},
            {'offset': 12, 'member': 'trait tags u32[5] (localization string IDs)', 'nameLength': 14}]}


def strings_tables(path):
    table, languages = {}, collections.Counter()
    with open(path, 'rb') as handle:
        mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        start = 0
        while True:
            at = mapped.find(STRINGS_MAGIC, start)
            if at < 0:
                break
            start = at + 1
            count, language = struct.unpack_from('<II', mapped, at + 8)
            if not 0 < count < 200000 or at + 16 + 8 * count > len(mapped):
                continue
            ids = struct.unpack_from('<%dI' % count, mapped, at + 16)
            if any(ids[k] >= ids[k + 1] for k in range(min(count - 1, 64))):
                continue
            offsets = struct.unpack_from('<%dI' % count, mapped, at + 16 + 4 * count)
            languages[language] += 1
            for value, offset in zip(ids, offsets):
                end = mapped.find(b'\0', at + offset, at + offset + 4096)
                if end < 0:
                    continue
                table.setdefault(value, {})['%08X' % language] = mapped[at + offset:end].decode('utf-8', 'replace')
        xaml = []
        for key in XAML_KEYS:
            found = mapped.find(key)
            if found >= 0:
                block = mapped[found - 200:found + 320]
                xaml.append(re.sub(rb'[^\x20-\x7e]+', b' ', block).decode('ascii').strip())
        mapped.close()
    return table, languages, xaml


def projectile_rows():
    """ProjectileInfo presentation members of every projectile row (production resolver, retained snapshot)."""
    sys.path.insert(0, str(ROOT / 'sdk'))
    from research_attachment_presets import _module_sources, _lua
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + _lua(n) + ']=function(...) return assert(loadstring(' + _lua(b)
        + ',' + _lua(n) + '))(...) end' for n, b in _module_sources().items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + _lua(str(build_profile.SNAPSHOT)) + r''',{
  expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
 local reader=Reader.new(source)
 local roots=discover.locate(source,reader,profile,{projectile=true})
 local out={}
 for t,r in pairs(roots.projectile.records)do
  out[tostring(t)]={upper=b.u32(r.bytes,4),name=b.u32(r.bytes,8),short=b.u32(r.bytes,12),
   icon=b.hex(r.bytes:sub(17,24)),settings={group=r.group,row=r.row,recordType=r.kind,settingsType=r.settings_type}}
 end
 reader.verify();source.close()
 return out
end)
local ok,value
repeat ok,value=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,value);return json.encode(value)
'''
    return json.loads(execute(program.encode()))


def icon_textures(paths, icons):
    """Which texture archive each offered icon lives in, and its format, from the installed game data (read-only).
    The weapon-function icons share one archive; the default skull does not."""
    try:
        import hd2_game_data as game_data
        data = game_data.Data()
    except (OSError, AssertionError, KeyError) as error:
        return {'available': False, 'reason': str(error)}
    texture = game_data.murmur64(game_data.TEXTURE.encode())
    wanted = {}
    for item in icons:
        if item['offered'] and item['path']:
            wanted[(game_data.murmur64(item['path'].encode()), texture)] = item['semanticId']
    found = data.find(set(wanted))
    out = {}
    for key, (archive, main, _, gpu) in sorted(found.items(), key=lambda kv: wanted[kv[0]]):
        header = data.read(archive, main)
        at = header.find(b'DDS ')
        height, width = struct.unpack_from('<II', header, at + 12)
        fourcc = header[at + 84:at + 88]
        dxgi = struct.unpack_from('<I', header, at + 128)[0] if fourcc == b'DX10' else None
        out[wanted[key]] = {'archive': archive.upper(), 'width': width, 'height': height, 'dxgiFormat': dxgi,
            'gpuBytes': gpu[1]}
    archives = {v['archive'] for k, v in out.items() if k != 'default'}
    return {'available': True, 'icons': out, 'weaponFunctionArchives': sorted(archives),
        'defaultIconArchive': (out.get('default') or {}).get('archive'),
        'note': 'The weapon-function icons are one texture set (one archive); the default skull is another.'}


def mode_presentation(native, table):
    """Short mode labels and HUD icons of every projectile, and the native label and icon catalogs."""
    lib = native.typelib_module
    members = {m['offset64']: m for m in lib.layout(native.typelib, 'ProjectileInfo', structured=True)['members']}
    layout = []
    for offset, (label, length, storage) in MODE_LAYOUT.items():
        member = members[offset]
        if not member['name'].endswith('inferred_length=' + str(length)) or member['storage'] != storage:
            raise ValueError('ProjectileInfo +%d (%s) changed' % (offset, label))
        layout.append({'struct': 'ProjectileInfo', 'offset': offset, 'member': label, 'nameLength': length,
            'storage': storage})
    import research_entity_authoring as rea
    paths = rea.Native()
    rows = {int(k): v for k, v in projectile_rows().items()}
    text = lambda value: table.get(value, {}).get('%08X' % EN_US)
    shorts = collections.Counter(row['short'] for row in rows.values())
    # The placeholder is the unnamed ID nearly every projectile holds; a few others name strings that no loaded
    # strings table carries (kept by ID, never offered).
    unnamed = [value for value, _ in shorts.most_common() if not table.get(value)]
    placeholder = unnamed[0]
    if shorts[placeholder] < len(rows) // 2:
        raise ValueError('the short-label placeholder is no longer the common value')
    labels, by_text = [], {}
    # Among IDs with the same text, the one a native menu mode shows (a projectile with its own HUD icon) is the
    # canonical choice, then the most used.
    default_icon = collections.Counter(row['icon'] for row in rows.values()).most_common(1)[0][0]
    shown = collections.Counter(row['short'] for row in rows.values() if row['icon'] != default_icon)
    for value, count in sorted(shorts.items(), key=lambda kv: (-shown[kv[0]], -kv[1], kv[0])):
        if value == placeholder or not text(value):
            continue
        by_text.setdefault(text(value), []).append(value)
    canonical = {}
    for label, values in by_text.items():
        base = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')
        for index, value in enumerate(values):
            semantic = base if index == 0 else base + '_' + '%08x' % value
            canonical[value] = semantic
            labels.append({'semanticId': semantic, 'nativeId': '%08X' % value, 'label': label,
                'languages': len(table.get(value, {})), 'projectiles': sorted(t for t, r in rows.items()
                    if r['short'] == value), 'nativeUse': True, 'offered': index == 0})
    for label in EXTRA_LABELS:
        if label in by_text:
            continue
        found = sorted(v for v, names in table.items() if names.get('%08X' % EN_US) == label and len(names) == 15)
        if not found:
            raise ValueError('extra mode label %s has no fully localized string' % label)
        semantic = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')
        canonical[found[0]] = semantic
        labels.append({'semanticId': semantic, 'nativeId': '%08X' % found[0], 'label': label, 'languages': 15,
            'projectiles': [], 'nativeUse': False, 'offered': True})
    icons_used = collections.Counter(row['icon'] for row in rows.values())
    icons = []
    icon_ids = {}
    for icon, count in sorted(icons_used.items(), key=lambda kv: (-kv[1], kv[0])):
        value = int.from_bytes(bytes.fromhex(icon), 'little')
        path = paths.path(value)
        if path == DEFAULT_ICON:
            semantic = 'default'
        elif path and path.startswith(ICON_PREFIX):
            semantic = path[len(ICON_PREFIX):]
        else:
            semantic = None
        if semantic:
            icon_ids[icon] = semantic
        icons.append({'semanticId': semantic, 'resource': '0x%016X' % value, 'path': path,
            'projectiles': count, 'offered': semantic is not None})
    projectiles = {}
    for t, row in sorted(rows.items()):
        projectiles[str(t)] = {'label': None if row['short'] == placeholder else canonical.get(row['short'],
                'unnamed_%08x' % row['short']),
            'labelNativeId': '%08X' % row['short'], 'icon': icon_ids.get(row['icon']), 'iconResource': '0x%016X'
            % int.from_bytes(bytes.fromhex(row['icon']), 'little'), 'name': text(row['name']),
            'settings': row['settings']}
    # Exact icons: every native label that a projectile shows with a weapon-function icon has exactly one; a label
    # without one (and a mod's custom label) resolves to the generic fallback.
    pairs = {}
    for row in projectiles.values():
        if row['label'] and row['icon'] and row['icon'] != 'default':
            pairs.setdefault(row['label'], set()).add(row['icon'])
    if any(len(icons_) != 1 for icons_ in pairs.values()):
        raise ValueError('a native mode label shows more than one icon: %r' % pairs)
    texts = {item['semanticId']: item['label'] for item in labels}
    canonical_of = {text: next(l['semanticId'] for l in labels if l['label'] == text and l['offered'])
        for text in {l['label'] for l in labels}}
    label_icons = {}
    for item in labels:
        exact = pairs.get(item['semanticId']) or pairs.get(canonical_of[item['label']])
        label_icons[item['semanticId']] = ({'icon': next(iter(exact)), 'source': 'exact_native'} if exact else
            {'icon': GENERIC_ICON, 'source': 'generic_fallback'})
    if GENERIC_ICON not in {i['semanticId'] for i in icons if i['offered']}:
        raise ValueError('the generic fallback icon is not a native weapon-function icon')
    texture_sets = icon_textures(paths, icons)
    return {'typeLibrary': layout, 'placeholderLabel': '%08X' % placeholder, 'defaultIcon': DEFAULT_ICON,
        'labelIcons': label_icons, 'genericFallbackIcon': GENERIC_ICON, 'iconVisuals': ICON_VISUALS,
        'iconTextures': texture_sets,
        'unnamedLabels': ['%08X' % v for v in unnamed[1:]],
        'labels': labels, 'icons': icons, 'projectiles': projectiles,
        'model': {'label': 'ProjectileInfo +12: the short mode label (localization string ID); a projectile no menu '
                'shows holds the unnamed placeholder.', 'icon': 'ProjectileInfo +16: the HUD icon resource; '
                'unlisted projectiles share the skull icon.', 'names': 'ProjectileInfo +4 / +8: long names.',
            'reader': 'Every native selectable mode reads as these members; the weapon-function menu reader is not '
                'traced.', 'shared': 'A ProjectileSettings row is a definition: every weapon firing that projectile '
                'shows the same label and icon.'},
        'summary': {'projectiles': len(rows), 'labelled': sum(1 for p in projectiles.values() if p['label']),
            'labels': len(labels), 'offeredLabels': sum(1 for l in labels if l['offered']),
            'icons': sum(1 for i in icons if i['offered'])}}


def main():
    native = fire_modes.entity_research.Native()
    layout = prove_layout(native)
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / MISSION)
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in (SHIP, MISSION)}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    _, body, _, _, _ = native.probe.find_component(native.entities, COMPONENT)
    owners = collections.defaultdict(list)
    index_rows = {}
    for row in range(INDEX_ROWS):
        resource, record, reserved = struct.unpack_from('<QII', body, row * 16)
        if resource:
            if reserved:
                raise ValueError('LoadoutEntry index reserved field is non-zero')
            owners[record].append(resource)
            index_rows[resource] = (record, row)

    def record(index):
        at = INDEX_ROWS * 16 + RECORD_SIZE * index
        item_id, item_type, extra = struct.unpack_from('<III', body, at)
        return {'record': index, 'id': '%08X' % item_id, 'type': item_type,
            'tags': list(struct.unpack_from('<5I', body, at + TAGS_OFFSET))}

    table, languages, xaml = strings_tables(build_profile.snapshot_directory() / SHIP)
    mission_table, _, _ = strings_tables(build_profile.snapshot_directory() / MISSION)
    for key, value in mission_table.items():
        table.setdefault(key, {}).update(value)
    used = collections.Counter(v for rec in owners for v in record(rec)['tags'] if v)
    catalog = []
    by_text = {}
    for value, count in used.most_common():
        names = table.get(value, {})
        text = names.get('%08X' % EN_US)
        semantic = re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_') if text else None
        catalog.append({'nativeId': '%08X' % value, 'label': text, 'labelEnGb': names.get('%08X' % EN_GB),
            'languages': len(names), 'itemCount': count, 'semanticId': semantic})
    # Two distinct string IDs both read INCENDIARY; keep their IDs distinct in the semantic ID.
    seen = collections.Counter(item['semanticId'] for item in catalog if item['semanticId'])
    for item in catalog:
        if item['semanticId'] and seen[item['semanticId']] > 1:
            item['semanticId'] += '_' + item['nativeId'].lower()
        if item['semanticId']:
            by_text.setdefault(item['label'], []).append(item)
    penetration = {}
    for key, text in PENETRATION.items():
        found = by_text.get(text) or []
        if len(found) != 1:
            raise ValueError('penetration label %s is absent or ambiguous' % text)
        penetration[key] = {'label': text, 'nativeId': found[0]['nativeId'], 'semanticId': found[0]['semanticId']}
    penetration_ids = {int(v['nativeId'], 16): key for key, v in penetration.items()}

    weapons = []
    for kind, name, resources, _, _ in fire_modes.weapons(native):
        rows = []
        for resource in resources:
            r = int(resource, 16)
            for index, members in owners.items():
                if r in members:
                    rows.append((index, len(members)))
        if not rows:
            weapons.append({'kind': kind, 'weapon': name, 'state': 'absent',
                'reason': 'No LoadoutEntry record: the item is not listed by the armory.'})
            continue
        entries = [dict(record(index), owners=count) for index, count in rows]
        shapes = {tuple(e['tags']) for e in entries}
        entry = entries[0]
        tags = entry['tags']
        labels = [(table.get(v, {}).get('%08X' % EN_US) if v else None) for v in tags]
        classes = [penetration_ids[v] for v in tags if v in penetration_ids]
        row = {'kind': kind, 'weapon': name, 'records': [e['record'] for e in entries],
            'backings': {'0x%016X' % int(resource, 16): {'recordIndex': index_rows[int(resource, 16)][0],
                'indexRow': index_rows[int(resource, 16)][1], 'ownerCount': len(owners[index_rows[int(resource, 16)][0]])}
                for resource in resources if int(resource, 16) in index_rows},
            'uniqueOwner': all(e['owners'] == 1 for e in entries), 'itemId': entry['id'], 'itemType': entry['type'],
            'tags': ['%08X' % v for v in tags], 'labels': labels,
            'packed': tags[:sum(1 for v in tags if v)] == [v for v in tags if v],
            'armorPenetration': classes[0] if len(classes) == 1 else None,
            'armorPenetrationSlot': next((i for i, v in enumerate(tags) if v in penetration_ids), None)}
        if len(shapes) != 1:
            row.update(state='blocked', reason='The weapon roots list different traits.')
        elif not row['uniqueOwner']:
            row.update(state='blocked', reason='The LoadoutEntry record is shared.')
        elif any(v and not table.get(v) for v in tags):
            row.update(state='blocked', reason='A listed tag has no string in any loaded strings table.')
        elif not row['packed']:
            row.update(state='blocked', reason='The trait slots are not packed.')
        else:
            row.update(state='writable', reason=None)
        # The single penetration label: one slot holds it (replaced in place), none does (added in the first empty
        # slot, if any), or several do (per-feed or per-level labels such as the Halt's; not one selector).
        if row['state'] != 'writable':
            row.update(armorPenetrationState='blocked', armorPenetrationReason=row['reason'])
        elif len(classes) > 1:
            row.update(armorPenetrationState='blocked', armorPenetrationReason='The weapon shows several penetration '
                'labels (' + ', '.join(PENETRATION[c] for c in classes) + '); edit them through presentation.traits.')
        elif not classes and all(tags):
            row.update(armorPenetrationState='blocked', armorPenetrationReason='All five trait slots are used.')
        else:
            row.update(armorPenetrationState='single' if classes else 'none', armorPenetrationReason=None)
        weapons.append(row)
    summary = {'weapons': len(weapons), 'byState': dict(collections.Counter('%s:%s' % (w['kind'], w['state'])
        for w in weapons)), 'armorPenetrationByState': dict(collections.Counter('%s:%s' % (w['kind'],
        w.get('armorPenetrationState', 'absent')) for w in weapons)), 'loadoutEntries': len(owners), 'sharedLoadoutEntries': sum(1 for v in owners.values()
        if len(v) > 1), 'traitsUsed': len(catalog), 'traitsNamed': sum(1 for c in catalog if c['label']),
        'stringLanguages': len(languages)}
    report = {'schemaVersion': 1, 'writes': 0, 'build': build_profile.BUILD_ID, 'typeLibrary': layout,
        'proofs': proofs, 'xamlEvidence': xaml, 'languages': {'%08X' % k: v for k, v in sorted(languages.items())},
        'enUs': '%08X' % EN_US, 'enGb': '%08X' % EN_GB,
        'model': {'traits': 'LoadoutEntryComponent +12: five localization string IDs, shown in slot order; 0 = empty. '
                'The armory localizes each non-zero ID; nothing derives a label from gameplay values.',
            'refresh': 'Traits are built into the item view model when a menu presenter builds its items (on enter); an '
                'open menu keeps the labels it built.',
            'stats': 'Stat rows (WeaponStatType) are computed from component data and customization at menu build; '
                'there is no stored display value.',
            'gameplaySeparation': 'The labels are presentation only: no gameplay reader of LoadoutEntry +12 was found; '
                'changing them never changes damage or penetration.'},
        'penetrationLabels': penetration, 'traits': catalog, 'summary': summary, 'weapons': weapons,
        'modes': mode_presentation(native, table)}
    OUTPUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', newline='\n', encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
