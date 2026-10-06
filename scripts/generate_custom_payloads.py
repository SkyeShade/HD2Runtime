"""Generate domains/custom_payloads.lua: the Eagle jet and its rockets, the Eagle rows and Eagle Rearm, and the reviewed
explosion donors beyond the Gas Strike, which the custom stratagem payload families (runtime/custom_eagles.lua,
runtime/explosion_donors.lua; development) read and re-prove first, from research/custom-payloads-F5FEE03DCFDB.json
(docs/research/custom-payloads-F5FEE03DCFDB.md).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/custom-payloads-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/custom_payloads.lua'


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('custom payload research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in profile:
        raise ValueError('the custom payload research covers another build than schemas/current.lua')
    E = research['eagleLayout']
    asm = [pin['asm'] for rows in research['proofs'].values() for pin in rows]

    def requires(text):
        if not any(text in line for line in asm):
            raise ValueError('custom payloads: %s is not a pinned instruction' % text)
    requires('mov eax, dword ptr [rdi + 0x%x]' % E['count'])
    requires('imul rcx, rbx, 0x%x' % E['stride'])
    requires('add rcx, qword ptr [rdi + 0x%x]' % E['records'])
    requires('mov rax, qword ptr [rdi + 0x%x]' % E['handles'])
    requires('mov eax, dword ptr [r14 + 0x%x]' % E['strikeProjectile'])
    requires('mov eax, dword ptr [r13 + %d]' % E['handleEntity'])
    requires('mov rax, qword ptr [rdi + 0x%x]' % research['weaponHandle']['handles'])
    # The active region the EagleComponent update strikes over, and the explosion request queue's layout.
    requires('cmp dword ptr [r14 + 0x%x], r12d' % E['active'])
    Q = research['explosionQueue']
    requires('mov eax, dword ptr [rcx + 0x%x]' % Q['count'])
    requires('imul rdi, r10, 0x%x' % Q['stride'])
    requires('movsd qword ptr [rdi + rcx + 0x%x], xmm0' % (Q['entries'] + Q['position']))
    requires('mov dword ptr [rdi + rcx + 0x%x], r8d' % (Q['entries'] + Q['type']))
    requires('mov dword ptr [rdi + rbx + 0x%x], r9d' % (Q['entries'] + Q['source']))
    requires('mov dword ptr [rdi + rbx + 0x%x], ecx' % (Q['entries'] + Q['owner']))
    requires('mov qword ptr [rdi + rbx + 0x%x], rax' % (Q['entries'] + Q['creditor']))
    M = research['mount']
    requires('mov rax, qword ptr [rbp + 0x%x]' % M['children'])
    requires('mov ecx, dword ptr [rax + rdx*4]')
    sentries = research['sentryWeapons']
    if sentries['A/MG-43 Machine Gun Sentry']['rateSelectorBound'] or not sentries['MG-206 Heavy Machine Gun'][
            'rateSelectorBound']:
        raise ValueError('the reviewed weapon-function observations changed')
    pods = research['eagles']['Eagle 110mm Rocket Pods']
    if pods['strikeProjectile'] != 82 or pods['rocket'] != {'impact': 229, 'expiry': 0}:
        raise ValueError('the 110mm rocket is not the reviewed projectile 82 (impact 229)')
    ems = research['explosionDonors']['Orbital EMS Strike']
    if ems['explosion'] != 188 or ems['shell'] != 74 or ems['rows'][0]['kind'] != 'explosion':
        raise ValueError('the EMS donor is not the reviewed shell 74 / explosion 188')
    automatic = {name: (d['round'], d['explosion'], d['asset'] or d.get('assetKey'))
        for name, d in research['explosionDonors'].items()
        if d.get('automatic') is True and d['rows'][0]['kind'] == 'explosion' and d['packages']}
    if automatic != {'Pelican chin autocannon': (120, 234, None), '66mm Missile Mk2': (272, 170, 'MLS-4X Commando'),
            'Automaton explosion 27': (302, 27, None), 'Illuminate explosion 392': (166, 392, None),
            'Strafing run cannon': (16, 50, 'Eagle Strafing Run'),
            'Exploding crossbow': (249, 59, 'player_weapon/CB-9 Exploding Crossbow'),
            'Assault walker cannon': (301, 397, None)}:
        raise ValueError('the automatic donors are not the reviewed four: %r' % automatic)
    slow = {name: (d['round'], d['explosion'], d['asset'] or d.get('assetKey'), d['maxRpm'], d['volume']['template'],
            d['volume']['seconds'])
        for name, d in research['explosionDonors'].items()
        if d.get('slow') is True and d['rows'][0]['kind'] == 'explosion' and d['packages']}
    if slow != {'EMS mortar field': (154, 180, 'A/M-23 EMS Mortar Sentry', 60, 15, 7.0),
            'Gas grenade cloud': (None, 177, 'throwable/G-4 Gas', 60, 16, 15.0),
            'Gas mortar cloud': (342, 185, 'A/GM-17 Gas Mortar Sentry', 60, 16, 15.0)}:
        raise ValueError('the slow donors are not the reviewed three: %r' % slow)
    carriers = research['impactCarriers']
    if carriers['base'] != 144 or carriers['flagsOffset'] != 0xF0 or sorted(carriers['types']) != ['148', '275'] or any(
            c != {'impact': 0, 'expiry': 0, 'flags': carriers['baseFlags']} for c in carriers['types'].values()):
        raise ValueError('the impact carriers are not the reviewed explosion-less Pelican rounds')
    aim = research['pelicanAim']
    if (aim['global'], aim['records'], aim['stride'], aim['t'], aim['mode'], aim['curveA'], aim['curveB'], aim['advance'],
            aim['networkBits'], aim['linearMode'], aim['on'], aim['off']) != (0x3326D30, 0x178, 0xD0, 0x50, 0x60, 0x20, 0x2C,
            0x6C, 0x10, 2, 1.0, -1.0):
        raise ValueError('the targeting aim override is not the reviewed layout')
    requires('movsd qword ptr [rcx + r13 + 8], xmm0')
    requires('movss xmm0, dword ptr [r14 + r13 + 0x50]')
    aim_pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes']} for pin in research['proofs']['pelicanAim']]
    idle = research['pelicanIdle']
    if (idle['repick'], idle['fireCheck'], idle['searchStage'], idle['alertStage'], idle['aimStage']) != (0x98, 0xB0, 2, 3, 5):
        raise ValueError('the behaviour 213 timers are not the reviewed layout')
    requires('cmp qword ptr [rcx + 0xa8], rax')
    requires('mov qword ptr [rcx + 0xa8], rax')
    idle_pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes']} for pin in research['proofs']['pelicanIdle']]
    strafing = research['pelicanRounds']['strafing_run']
    if (strafing['projectile'], strafing['plain'], strafing['pattern'], strafing['explosion'], strafing['asset']) != (
            16, 27, [16, 27, 27, 27], 50, 'Eagle Strafing Run'):
        raise ValueError('the Eagle Strafing Run rounds are not the reviewed 16 / 27')
    pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes']}
        for rows in research['proofs'].values() for pin in rows]
    eagles = {}
    for name, e in research['eagles'].items():
        eagles[name] = {'stableId': e['stableId'], 'jet': e['payload'], 'strikeProjectile': e['strikeProjectile'],
            'rocket': e['rocket'], 'uses': e['uses'], 'cooldown': e['cooldown'], 'mounts': e['mounts']}
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDll']['sha256']},
        # The Eagle manager (EagleComponent): its jets' handles (+0 resource, +8 entity, +0x10 network id) and records.
        'eagle': E,
        # A projectile weapon's own world record: the ProjectileWeapon manager's handles (+0x68 by its index).
        'weaponHandle': research['weaponHandle'],
        # StratagemInfo members the custom Eagle path reads: the delivery kind (0 = Eagle), uses, cooldown, linked type.
        'row': research['row'],
        # Eagle Rearm: its type and its own cooldown (the default rearm time of a custom Eagle without it in the record).
        'eagleRearm': research['eagleRearm'],
        # Every catalogued Eagle: its stable id, its jet (payload[0]), its strike projectile and that row's explosions.
        'eagles': eagles,
        # Reviewed explosion donors (the Gas Strike's is research/bombardment-payload's gasChain): the donor's shell, its
        # impact explosion and every row of the chain exactly as reviewed (relocated words masked).
        'explosionDonors': research['explosionDonors'],
        # Rounds with no explosion of their own (the Pelican CAS rounds) whose impact explosion copy may take an
        # automatic donor's: each type's reviewed row members, with the flags of the live-verified Talon base.
        'impactCarriers': carriers,
        # A round of another weapon the Pelican's chin gun may fire on its own copy: the Eagle Strafing Run's HE round,
        # its plain twin and its pattern, the identity members compared before use, and its asset.
        # The targeting record's aim override (one Pelican chin turret's aim point, lowered): its layout, the values the
        # Runtime writes, and its own pins (proven before the first write).
        'pelicanAim': dict({k: v for k, v in aim.items() if k != 'observed'}, pins=sorted(aim_pins, key=lambda p: p['rva'])),
        # Behaviour 213's re-pick and fire-check timers (the gunship makes them due sooner), with their own pins.
        'pelicanIdle': dict(idle, pins=sorted(idle_pins, key=lambda p: p['rva'])),
        'pelicanRounds': {name: {k: v for k, v in r.items() if k != 'packages'}
            for name, r in research['pelicanRounds'].items()},
        'projectileExplosions': research['projectileExplosions'],
        # The game's explosion request queue [game+global] (RequestExplosion): count, entries and each request's
        # members. Read-only (the custom Eagle diagnostics).
        'explosionQueue': research['explosionQueue'],
        # The weapon-function inputs of a WeaponData type record (+184 left, +188 right; 2 = the rate-of-fire selector)
        # and the sentry donors' own weapon types (rate slots, magazine, spread, inputs).
        'weaponFunction': research['weaponFunction'],
        # The mount component (each mounted child entity, six per mount at +0x48): the jet's pods.
        'mount': research['mount'],
        'sentryWeapons': sentries,
        'pins': sorted(pins, key=lambda pin: pin['rva'])}


def outputs() -> dict[str, str]:
    return {'domains/custom_payloads.lua': '-- Generated by scripts/generate_custom_payloads.py; do not edit.\n'
        'return ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale custom payload domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
