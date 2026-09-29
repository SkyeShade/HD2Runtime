"""Status-effect catalog and the native status attachment model. Offline research; nothing here writes memory.

Inputs: the retained snapshot's live StatusEffectSettings and DamageSettings allocations (located through the
production discovery path), the pinned type library, and the generated Runtime domain tables (for consumers).

Native model (typed members only):

- StatusEffectSettings: one 152-byte StatusEffectInfo row per StatusEffectType. +0 is the type, +8 a string the
  game itself stores with the row (its display/debug name, e.g. "Fire", "Stun Medium"), +40 the duration (the
  member Runtime already authors as status.duration), +44 the DamageInfoType the status deals while active.
- DamageInfo: four inline {StatusEffectType +44+8n, value f32 +48+8n} slots. An unused slot is type 0; used slots
  are packed from slot 1. A DamageInfo row is what a hit applies: projectile direct hits, explosions, beam / arc /
  spray ticks and melee all reach a DamageInfo row, so status application is owned by the damage definition, not
  by the projectile or weapon.

Every status row's own name string is its semantic identity: the enum's numeric values are renumbered between
builds (filediver's older enum has Stun Small at 36; this build stores "Stun Small" at 37), so numbers are never
treated as identity. A status is *attachable* (offered as a status_reference value) only when at least one weapon,
explosion or stratagem DamageInfo row in the live table already applies it through a slot, so the attachment
mechanism is proven for that status. It must also be applied by at least one weapon, stratagem or throwable attack
Runtime maps, so its gameplay behaviour on a player-side attack is established; statuses only enemies, terrain,
weather, stims or other systems apply are catalogued read-only.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import statistics
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402
from migration import build_view  # noqa: E402
from reference_format import dl_hash  # noqa: E402

OUTPUT = ROOT / 'research/status-effects-F5FEE03DCFDB.json'
ROW_SIZE = 152
DAMAGE_ROW = 76
SLOTS = 4
# (offset, size, storage, hidden-name length) of every StatusEffectInfo / DamageInfo member this research reads.
STATUS_FINGERPRINT = ((0, 4, 'ENUM_INT32', 4), (8, 8, 'STR', 10), (36, 4, 'FP32', 8), (40, 4, 'FP32', 8),
    (44, 4, 'ENUM_UINT32', 16))
# Families by the row's own name. Only these families can be attachable; everything else is applied by other
# systems (stims, terrain, weather, UI, character state).
FAMILIES = (
    ('fire', ('Fire', 'BurningLight', 'BurningHeavy', 'Thermite', 'Cyborg Fire', 'Lava')),
    ('stun', ('Stun Small', 'Stun Medium', 'Stun Large', 'Stun Massive', 'Stun Illuminate', 'TornadoStun')),
    ('gas', ('Gas', 'Gas_Confusion', 'Poison', 'Gloom', 'Choked')),
    ('electric', ('Electric',)),
    ('slow', ('Slowed', 'Rooted', 'FlamerSlowed')),
    ('acid', ('Acid Splash', 'Acid Stream')),
    ('bleed', ('Bleed',)),
    ('sense', ('Blind', 'Deaf', 'Confusion', 'Fire_Panic', 'Flashlighted', 'Smoke_Covered',
        'Inverted_Aim_Assist', 'Illuminate Scrambler')),
    ('radiation', ('RadiationLight', 'RadiationHeavy')),
    ('stim', ('Stim Fx', 'Stim Stamina', 'Stim Heal', 'Stim Pistol Heal', 'Stim Combat Drugs', 'Stim Cooldown',
        'Backpack Chemicals')),
    ('terrain', ('Sand', 'Mud', 'Snow', 'Submerged', 'Thornbush', 'Cactus', 'Barbwire', 'BushSmall', 'BushLarge')),
    ('weather', ('Intense Heat', 'Extreme Cold', 'Tremor', 'Sandstorm', 'Blizzard', 'Acid Storm',
        'Weather Insulated')),
    ('system', ('Hidden', 'Constitution', 'Constitution Booster Armor Resistance', 'Post Mortem Explosion',
        'Pure Damage', 'Dark Fluid', 'Death March', 'Hotshot Laser Rifle', 'PoisonVulnerability')),
)
DOMAINS = ('player_weapon_authoring', 'support_weapon_authoring', 'vehicle_weapon_authoring', 'stratagem_authoring',
    'throwable_authoring', 'booster_authoring', 'attachment_authoring', 'pod_payload_authoring')


def slug(value: str) -> str:
    """'Stun Medium' -> stun_medium, 'BurningHeavy' -> burning_heavy, 'Gas_Confusion' -> gas_confusion."""
    value = re.sub(r'(?<=[a-z])(?=[A-Z])', '_', value)
    return re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')


def family_of(name: str) -> str | None:
    return next((family for family, names in FAMILIES if name in names), None)


def fingerprint(library, type_name: str) -> set:
    array = library.layout(type_name)['members'][0]
    return {(m['offset'], m['size'], m['storage'], m['nameLength'])
        for m in build_view._record_layout(library, array['type_hash']).members}


def rows(region: bytes, base: int, stride: int, group_type: int) -> list[bytes]:
    count = struct.unpack_from('<I', region, 0)[0]
    at = 4
    for _ in range(count):
        magic, _, kind, size, _, _ = struct.unpack_from('<4s5I', region, at)
        root = at + 24
        if kind == group_type:
            pointer, entries = struct.unpack_from('<QQ', region, root)
            start = pointer - base
            return [region[start + i * stride:start + (i + 1) * stride] for i in range(entries)]
        at = root + size
    raise ValueError('settings group absent')


def string_at(region: bytes, base: int, pointer: int) -> str | None:
    if not base <= pointer < base + len(region):
        return None
    start = pointer - base
    return region[start:region.index(0, start)].decode('utf-8')


def f32(raw: bytes, at: int) -> float:
    return round(struct.unpack_from('<f', raw, at)[0], 6)


def domain_consumers(tables: dict) -> dict:
    """damage recordType -> [{domain, object, field path}] from every generated domain table's DamageInfo backings."""
    consumers = {}

    def visit(domain, obj, node, path):
        if isinstance(node, dict):
            backing = node.get('backing')
            if isinstance(backing, dict) and backing.get('settings') == 'damage' and backing.get('recordType') is not None:
                key = int(backing['recordType'])
                entry = {'domain': domain, 'object': obj}
                if entry not in consumers.setdefault(key, []):
                    consumers[key].append(entry)
            elif isinstance(backing, dict) and backing.get('kind') == 'DamageInfo':
                key = int(backing.get('nativeIdentity') or backing.get('recordType'))
                entry = {'domain': domain, 'object': obj}
                if entry not in consumers.setdefault(key, []):
                    consumers[key].append(entry)
            for key, value in node.items():
                visit(domain, obj, value, path + [key])
        elif isinstance(node, list):
            for value in node:
                visit(domain, obj, value, path)
    for domain in DOMAINS:
        table = tables.get(domain) or {}
        for collection in ('weapons', 'stratagems', 'throwables', 'boosters', 'attachments', 'racks'):
            for name, entry in sorted((table.get(collection) or {}).items()):
                visit(domain, name, entry, [])
    return consumers


def build() -> dict:
    import snapshot_regions
    from migration import source
    library = build_view.TypeLibrary((build_profile.datalibrary() / 'dl_library.dl_typelib').read_bytes())
    if set(STATUS_FINGERPRINT) - fingerprint(library, 'StatusEffectSettings'):
        raise ValueError('StatusEffectInfo layout fingerprint changed')
    status_base, status_region = snapshot_regions.region_bytes('status')
    damage_base, damage_region = snapshot_regions.region_bytes('damage')
    status_rows = rows(status_region, status_base, ROW_SIZE, dl_hash('StatusEffectSettings'))
    damage_rows = rows(damage_region, damage_base, DAMAGE_ROW, dl_hash('DamageSettings'))
    tables = source.load_tables(source.resolve_ref('current'))
    consumers = domain_consumers(tables)

    # Every DamageInfo row's status slots.
    applied = {}
    packing_violations = []
    for index, raw in enumerate(damage_rows):
        damage_type = struct.unpack_from('<I', raw, 0)[0]
        seen_empty = False
        for slot in range(SLOTS):
            kind = struct.unpack_from('<I', raw, 44 + 8 * slot)[0]
            value = f32(raw, 48 + 8 * slot)
            if kind == 0:
                seen_empty = True
                continue
            if seen_empty:
                packing_violations.append({'damageType': damage_type, 'slot': slot + 1})
            applied.setdefault(kind, []).append({'damageType': damage_type, 'row': index, 'slot': slot + 1,
                'strength': value, 'consumers': consumers.get(damage_type, [])})
    slot_usage = {str(n): sum(1 for raw in damage_rows
        if sum(1 for s in range(SLOTS) if struct.unpack_from('<I', raw, 44 + 8 * s)[0]) == n) for n in range(5)}

    statuses = []
    names_seen = {}
    for row, raw in enumerate(status_rows):
        kind = struct.unpack_from('<i', raw, 0)[0]
        name = string_at(status_region, status_base, struct.unpack_from('<Q', raw, 8)[0])
        if not name:
            raise ValueError(f'status row {row} has no in-allocation name string')
        ordinal = names_seen[name] = names_seen.get(name, 0) + 1
        semantic = slug(name) + ('' if ordinal == 1 else f'_{ordinal}')
        family = family_of(name)
        users = applied.get(kind, [])
        weapon_users = [u for u in users if u['consumers']]
        damage_type = struct.unpack_from('<I', raw, 44)[0]
        damage = None
        if damage_type:
            match = [r for r in damage_rows if struct.unpack_from('<I', r, 0)[0] == damage_type]
            if len(match) == 1:
                d = match[0]
                damage = {'damageType': damage_type, 'standardDamage': struct.unpack_from('<i', d, 4)[0],
                    'durableDamage': struct.unpack_from('<i', d, 8)[0],
                    'armorPenetration': list(struct.unpack_from('<4I', d, 12))}
        strengths = sorted(u['strength'] for u in users)
        statuses.append({'semanticId': semantic, 'name': name, 'nativeType': kind, 'row': row, 'family': family,
            'duration': f32(raw, 40), 'member36': f32(raw, 36), 'tickDamage': damage,
            'slotUsers': len(users), 'weaponSlotUsers': len(weapon_users),
            'knownConsumers': sorted({(c['domain'], c['object']) for u in users for c in u['consumers']}),
            'strength': {'min': strengths[0], 'median': statistics.median(strengths), 'max': strengths[-1]}
                if strengths else None,
            'attachable': bool(weapon_users),
            'attachableReason': (None if weapon_users else
                'no DamageInfo slot applies it (applied by another system)' if not users else
                'only non-player DamageInfo rows (enemies, hazards) apply it')})
    for item in statuses:
        item['knownConsumers'] = [{'domain': d, 'object': o} for d, o in item['knownConsumers']]
    return {'schemaVersion': 1,
        'source': {'snapshot': build_profile.SNAPSHOT_NAME, 'mode': 'snapshot', 'writes': 0, 'protectionChanges': 0,
            'fixtureFallback': 'disabled'},
        'model': {
            'owner': 'DamageInfo',
            'slots': SLOTS, 'slotLayout': {'type': '+44 + 8n (StatusEffectType, u32)', 'strength': '+48 + 8n (f32)'},
            'packing': 'used slots are contiguous from slot 1; no live DamageInfo row has a gap'
                if not packing_violations else 'gaps observed', 'packingViolations': packing_violations,
            'damageRows': len(damage_rows), 'rowsBySlotsUsed': slot_usage,
            'statusRows': len(status_rows),
        },
        'statuses': statuses,
        # Every live DamageInfo row's four slots, [statusType, strength], for the weapon generators.
        'damageSlots': {str(struct.unpack_from('<I', raw, 0)[0]): [[struct.unpack_from('<I', raw, 44 + 8 * s)[0],
            f32(raw, 48 + 8 * s)] for s in range(SLOTS)] for raw in damage_rows}}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    s = report['statuses']
    print(json.dumps({'statuses': len(s), 'attachable': sum(x['attachable'] for x in s),
        'damageRows': report['model']['damageRows'], 'rowsBySlotsUsed': report['model']['rowsBySlotsUsed'],
        'packing': report['model']['packing']}, indent=1))


if __name__ == '__main__':
    main()
