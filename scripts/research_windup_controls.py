"""Wind-up, spin-up and charge-up controls of every weapon (research only; build F5FEE03DCFDB).

Read-only. Inputs: the pinned datalibrary (scan.tables), the game.dll image of a retained snapshot (scan.xref) and the
earlier heat-member research (research/las-beam-overhaul-comparison-F5FEE03DCFDB.json).

A player report (0.30.4): "Weapons with windup don't seem to have an option to reduce it (like the Sickle)". Every
component that delays a weapon's first shot, with its native consumer:

1. WeaponHeatComponentData firing charge (+148 charge needed, +152 gained per second held, +156 lost per second
   released, +160 reset after each shot). The charge update (0x763780) resolves the record every frame and clamps
   charge = min(+148, charge + dt x +152) while the trigger is held (0x7643DE / 0x7643EC), charge = max(0, charge -
   dt x +156) when released (0x7648A2); the fire gate (0x77EAD0) lets the weapon fire only when charge >= +148
   (0x77EDB6). Each shot sets the charge to +148 (0x762E01) and back to 0 when +160 is set (0x762E17: the Quasar).
   Wind-up = +148 / +152 seconds (0 = instant). Owners with a wind-up: LAS-16 Sickle, LAS-17 Double-Edge Sickle,
   LAS-5 Scythe, LAS-7 Dagger, LAS-98 Laser Cannon, LAS-99 Quasar Cannon, the AX/LAS-5 Rover gun, the A/LAS-98 Laser
   Sentry; the Sai, Trident and Talon hold 0 (no wind-up).
2. WeaponWindUpComponentData spin-up (+0 wind-up seconds, +4 spin-down switch, +12 barrel-spin multiplier). The
   wind-up update (0x78A420, every frame from the world update 0x57178C) resolves the record (0x78A492, resolver
   0x4F8090: the type record unless an instance copy exists) and advances the spin progress by dt / +0 while firing
   (0x78A4EC; +0 <= 0 sets it to 1 at once, 0x78A4DE). On release, +4 <= 0 stops the barrels at once (0x78A519 ->
   0x78A51F); otherwise the progress falls by dt / +0 (0x78A52C divides by +0, not +4): the spin-down always takes
   the wind-up time and +4's magnitude is never read. The fire gate (0x77EAD0, manager game+0x33267A0 at 0x77EAF7)
   fires only at progress >= 1 (0x77ED6C). Owners: the M-1000 Maxigun, the A/G-16 Gatling Sentry, the EXO-45 Patriot
   minigun, the TD-110 Maelstrom tank gun and mission turrets.
3. WeaponChargeComponentData hold-to-charge (charge.level_1/2/3): a charge-up the player holds on purpose, not a
   wind-up. Support charge weapons (Railgun, Arc Thrower, Epoch, Meltagun) expose it; the primary plasma weapons
   (PLAS-101 Purifier, PLAS-15 Loyalist, PLAS-39 Accelerator Rifle) do not (no charge.* on player weapons yet).
4. No delay member: MG-43, M-105 Stalwart, MGX-42 Bullet Storm and the FRV guns fire at once. ProjectileWeapon +144
   (a 4-byte float, 0 on every record) has no traced reader: not a lead to expose.

  py scripts/research_windup_controls.py          # write research/windup-controls-F5FEE03DCFDB.json + docs md
  py scripts/research_windup_controls.py --check  # fail if the committed outputs are stale
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scan import report, tables  # noqa: E402
from research_railgun_charge import check_pins  # noqa: E402

OUTPUT = ROOT / 'research/windup-controls-F5FEE03DCFDB.json'
MARKDOWN = ROOT / 'research/docs/windup-controls-F5FEE03DCFDB.md'
HEAT_RESEARCH = ROOT / 'research/las-beam-overhaul-comparison-F5FEE03DCFDB.json'
WINDUP_MANAGER = 0x33267A0
ONE = 0x23C6D70

PINS = [
    # firing charge (WeaponHeat)
    (0x763809, 'call 0x50e1f0', 'charge update: the WeaponHeat record (resolver) every frame', 'heat_charge'),
    (0x7643DE, 'mulss xmm8, dword ptr [r13 + 0x98]', 'held: charge += dt x +152 ...', 'heat_charge'),
    (0x7643EC, 'minss xmm8, dword ptr [r13 + 0x94]', '... capped at +148', 'heat_charge'),
    (0x7648A2, 'mulss xmm0, dword ptr [r13 + 0x9c]', 'released: charge -= dt x +156 (floored at 0)', 'heat_charge'),
    (0x77EDAB, 'call 0x50e1f0', 'fire gate: the WeaponHeat record ...', 'heat_charge'),
    (0x77EDB6, 'comiss xmm0, dword ptr [rax + 0x94]', '... fires only when charge >= +148', 'heat_charge'),
    (0x762E01, 'mov dword ptr [r15 + r14*8 + 0xc], eax', 'each shot: charge = +148 ...', 'heat_charge'),
    (0x762E17, 'cmp byte ptr [rsi + 0xa0], bpl', '... reset to 0 when +160 is set', 'heat_charge'),
    (0x763373, 'divss xmm7, dword ptr [rbx + 0x94]', 'charge fraction (guarded: +148 = 0 is safe)', 'heat_charge'),
    (0x77E640, 'call 0x77ead0', 'trigger state machine: firing starts only when the gate passes ...', 'gate'),
    (0x77E71E, 'call 0x77ead0', '... and stops when it fails', 'gate'),
    # spin-up (WeaponWindUp)
    (0x57178C, 'call 0x78a420', 'world update: the wind-up update every frame', 'windup'),
    (0x78A492, 'call 0x4f8090', 'the WeaponWindUp record (resolver: the type record unless an instance copy)',
        'windup'),
    (0x78A4D4, 'movss xmm1, dword ptr [rbp]', 'firing: +0 wind-up seconds ...', 'windup'),
    (0x78A4DE, 'mov dword ptr [rsi + rdi*8 + 4], 0x3f800000', '... <= 0: progress 1 at once ...', 'windup'),
    (0x78A4EC, 'divss xmm0, xmm1', '... else progress += dt / +0 ...', 'windup'),
    (0x78A4FF, 'movss dword ptr [rsi + rdi*8 + 4], xmm1', '... capped at 1', 'windup'),
    (0x78A519, 'comiss xmm7, dword ptr [rbp + 4]', 'released: +4 <= 0 ...', 'windup'),
    (0x78A51F, 'mov dword ptr [rsi + rdi*8 + 4], ebx', '... progress 0 at once', 'windup'),
    (0x78A52C, 'divss xmm0, dword ptr [rbp]', 'else progress -= dt / +0 (the wind-up time, not +4)', 'windup'),
    (0x78A679, 'mulss xmm3, dword ptr [rbp + 0xc]', '+12: barrel-spin animation multiplier', 'windup'),
    (0x77EAF7, 'mov r9, qword ptr [rip', 'fire gate: the wind-up manager ...', 'windup'),
    (0x77ED65, 'movss xmm0, dword ptr [r12 + r15*8 + 4]', '... spin progress ...', 'windup'),
    (0x77ED6C, 'comiss xmm0, dword ptr [rip', '... fires only at progress >= 1.0', 'windup'),
]
RIP_TARGETS = {0x77EAF7: WINDUP_MANAGER, 0x77ED6C: ONE}

NAMES = {'minigun': 'M-1000 Maxigun', 'sentry_gatling': 'A/G-16 Gatling Sentry'}
# record -> (name, the owner resource the name is proven for: vehicle mount paths from research/vehicle-weapons, the
# sentry and the support weapon from their reviewed roots)
WINDUP_OWNERS = {0: ('EXO-45 Patriot Exosuit minigun (right arm)', 0x08F6089289C83D22),
    1: ('TD-110 Maelstrom tank gun', 0xD58AE6A04EDB10DE), 2: ('A/G-16 Gatling Sentry', None),
    8: ('M-1000 Maxigun', None)}

# weapon -> (component, how to reduce the wind-up, Runtime target, fields)
CONTROLS = [
    ('LAS-16 Sickle', 'heat', 'hd2.weapon', 'heat.firing_charge (0 = instant) or heat.charge_gain_per_second'),
    ('LAS-17 Double-Edge Sickle', 'heat', 'hd2.weapon', 'heat.firing_charge or heat.charge_gain_per_second'),
    ('LAS-5 Scythe', 'heat', 'hd2.weapon', 'heat.firing_charge or heat.charge_gain_per_second'),
    ('LAS-7 Dagger', 'heat', 'hd2.weapon', 'heat.firing_charge or heat.charge_gain_per_second'),
    ('LAS-98 Laser Cannon', 'heat', 'hd2.support_weapon', 'heat.firing_charge or heat.charge_gain_per_second'),
    ('LAS-99 Quasar Cannon', 'heat', 'hd2.support_weapon', 'heat.firing_charge or heat.charge_gain_per_second '
        '(heat.reset_charge_after_shot: every shot charges again)'),
    ('AX/LAS-5 Rover gun', 'heat', 'hd2.vehicle_weapon', 'heat.firing_charge or heat.charge_gain_per_second'),
    ('A/LAS-98 Laser Sentry', 'heat', 'hd2.stratagem(...):weapon(\'primary\')',
        'heat.firing_charge or heat.charge_gain_per_second'),
    ('M-1000 Maxigun', 'windup', 'hd2.support_weapon', 'windup.wind_up_seconds (0 = instant)'),
    ('A/G-16 Gatling Sentry', 'windup', 'hd2.stratagem(...):weapon(\'primary\')', 'windup.wind_up_seconds'),
    ('EXO-45 Patriot Exosuit minigun', 'windup', 'hd2.vehicle_weapon', 'windup.wind_up_seconds'),
    ('TD-110 Maelstrom tank gun', 'windup', 'hd2.vehicle_weapon', 'windup.wind_up_seconds'),
    ('LAS-12 Sai, LAS-13 Trident, LAS-58 Talon', 'heat', '-', 'none needed: +148 = 0 (no wind-up)'),
    ('MG-43, M-105 Stalwart, MGX-42 Bullet Storm, FRV guns', '-', '-', 'none: no wind-up member'),
    ('PLAS-101 Purifier, PLAS-15 Loyalist, PLAS-39 Accelerator Rifle', 'charge', '-', 'a hold-to-charge '
        '(WeaponCharge), not a wind-up; charge.* is offered on support charge weapons only'),
]


def f32(raw, offset):
    return round(struct.unpack_from('<f', raw, offset)[0], 6)


def owners(t, component, record):
    return [t.label(resource) for resource in component.owner_map().get(record, [])]


def build() -> dict:
    t = tables.pinned()
    windup = t.component('WeaponWindUpComponentData')
    heat = t.component('WeaponHeatComponentData')
    charge = t.component('WeaponChargeComponentData')
    if windup.record_size != 36:
        raise ValueError('WeaponWindUpComponentData layout changed')
    spin = []
    for record in range(windup.count):
        raw = windup.raw(record)
        labels = owners(t, windup, record)
        spin.append({'record': record, 'owners': labels, 'name': WINDUP_OWNERS.get(record, (None,))[0],
            'windUpSeconds': f32(raw, 0), 'spinDownSwitch': f32(raw, 4), 'spinMultiplier': f32(raw, 12),
            'linkedAmmoGate': raw[32]})
    for record, (name, resource) in WINDUP_OWNERS.items():
        found = windup.owner_map().get(record, [])
        if not found or resource is not None and found != [resource]:
            raise ValueError(f'WeaponWindUp record {record} ({name}) changed owner')
    known = {r['record']: r for r in json.loads(HEAT_RESEARCH.read_text(encoding='utf-8'))['heat148']['records']}
    charges = []
    for record in range(heat.count):
        raw = heat.raw(record)
        need, gain, loss = f32(raw, 148), f32(raw, 152), f32(raw, 156)
        if record in known and abs(known[record]['values']['148'] - need) > 1e-6:
            raise ValueError(f'WeaponHeat record {record} +148 differs from the earlier research')
        charges.append({'record': record, 'owners': owners(t, heat, record),
            'names': [o.get('name') for o in known.get(record, {}).get('owners', []) if o.get('name')],
            'firingCharge': need, 'gainPerSecond': gain, 'lossPerSecond': loss, 'resetAfterShot': raw[160],
            'windUpSeconds': None if need <= 0 else (round(need / gain, 4) if gain > 0 else 'never')})
    hold = []
    for record in range(charge.count):
        raw = charge.raw(record)
        hold.append({'record': record, 'owners': owners(t, charge, record),
            'chargeTimes': [f32(raw, 0), f32(raw, 24), f32(raw, 48)]})

    from scan import xref
    image = xref.CodeImage.from_snapshot('game.dll')
    pins = check_pins(image, PINS, RIP_TARGETS)
    if abs(image.f32(ONE) - 1.0) > 1e-9:
        raise ValueError('the wind-up gate constant changed')
    return report.document('Wind-up, spin-up and charge-up controls', {'gameDll': image.describe(),
        'components': ['WeaponWindUpComponentData', 'WeaponHeatComponentData', 'WeaponChargeComponentData']}, [],
        spinUp={'component': 'WeaponWindUpComponentData', 'recordSize': windup.record_size, 'records': spin,
            'members': {'+0': 'wind-up seconds (progress += dt / +0; <= 0 instant)',
                '+4': 'spin-down switch: <= 0 stops the barrels at once; any positive value spins down over +0 '
                    '(its magnitude is never read)', '+12': 'barrel-spin animation multiplier',
                '+32': 'Maxigun only: the gate also needs a WeaponLinkedAmmo instance (name unproven)'},
            'lifecycle': 'resolved every frame (0x78A492); no entity delta targets the component: type record'},
        firingCharge={'component': 'WeaponHeatComponentData', 'records': charges,
            'members': {'+148': 'charge needed to fire', '+152': 'charge gained per second held',
                '+156': 'charge lost per second released', '+160': 'charge resets after each shot'},
            'windUp': '+148 / +152 seconds (+148 = 0: instant)'},
        holdToCharge={'component': 'WeaponChargeComponentData', 'records': hold,
            'note': 'charge times (+0/+24/+48 seconds per level): a deliberate charge, not a wind-up'},
        controls=[{'weapon': w, 'mechanism': m, 'target': target, 'reduce': how} for w, m, target, how in CONTROLS],
        corrections=['windup.wind_down_seconds is a switch, not a time: the spin-down divides by the wind-up time '
            '(0x78A52C); 0 stops the barrels at once, any positive value spins down over windup.wind_up_seconds.'],
        pins=pins,
        openQuestions=['Whether a Maxigun instance gets its own WeaponWindUp copy (resolver 0x4F8090 instance '
            'branch): none of the retained snapshots shows one; if one existed, writes would reach only weapons '
            'created later.', 'Charge times of the primary plasma weapons (Purifier, Loyalist, Accelerator Rifle): '
            'not offered on player weapons yet.'])


def markdown(doc: dict) -> str:
    lines = ['# Wind-up, spin-up and charge-up controls', '',
        f"Build {doc['build']}. Generated by `scripts/research_windup_controls.py` (research only). Evidence and "
        'pins: `research/windup-controls-F5FEE03DCFDB.json`.', '', '## Which field reduces the wind-up', '',
        report.markdown_table(['weapon', 'mechanism', 'target', 'reduce it with'],
            [[c['weapon'], c['mechanism'], c['target'], c['reduce']] for c in doc['controls']]), '',
        '## Firing charge (WeaponHeat +148..+160)', '']
    lines += [f"- {k}: {v}" for k, v in doc['firingCharge']['members'].items()]
    lines += [f"- wind-up = {doc['firingCharge']['windUp']}", '', report.markdown_table(['record', 'owners',
        'named', '+148', '+152', '+156', '+160', 'wind-up (s)'], [[r['record'], ', '.join(r['owners'][:3]),
        ', '.join(r['names']), r['firingCharge'], r['gainPerSecond'], r['lossPerSecond'], r['resetAfterShot'],
        r['windUpSeconds']] for r in doc['firingCharge']['records'] if r['firingCharge'] > 0 or r['names']]), '',
        '## Spin-up (WeaponWindUp)', '']
    lines += [f"- {k}: {v}" for k, v in doc['spinUp']['members'].items()]
    lines += [f"- lifecycle: {doc['spinUp']['lifecycle']}", '', report.markdown_table(['record', 'owners', 'named',
        '+0 wind-up s', '+4 switch', '+12 spin'], [[r['record'], ', '.join(r['owners'][:3]), r['name'] or '',
        r['windUpSeconds'], r['spinDownSwitch'], r['spinMultiplier']] for r in doc['spinUp']['records']]), '',
        '## Hold-to-charge (WeaponCharge)', '', doc['holdToCharge']['note'] + '.', '',
        report.markdown_table(['record', 'owners', 'charge times (s)'], [[r['record'], ', '.join(r['owners'][:3]),
            r['chargeTimes']] for r in doc['holdToCharge']['records']]), '', '## Corrections', '']
    lines += [f'- {c}' for c in doc['corrections']]
    lines += ['', '## Pins', '', report.markdown_table(['rva', 'group', 'asm', 'role'],
        [[f"{p['rva']:#x}" if isinstance(p.get('rva'), int) else p.get('rva'), p['group'], p['asm'], p['role']]
            for p in doc['pins']]), '', '## Open questions', '']
    lines += [f'- {q}' for q in doc['openQuestions']]
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    doc = build()
    text = json.dumps(doc, indent=2, allow_nan=False, default=report._default) + '\n'
    md = markdown(doc)
    if args.check:
        stale = [str(p) for p, body in ((OUTPUT, text), (MARKDOWN, md))
            if not p.is_file() or p.read_text(encoding='utf-8') != body]
        print('stale: ' + ', '.join(stale) if stale else 'up to date')
        return 1 if stale else 0
    OUTPUT.write_text(text, encoding='utf-8')
    MARKDOWN.write_text(md, encoding='utf-8')
    print('wrote', OUTPUT.relative_to(ROOT), 'and', MARKDOWN.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
