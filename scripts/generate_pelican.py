"""Generate domains/pelican.lua: the transport Pelican's components (Transport, Behavior, transform, clock), its flight
members and timings, and the pinned code the development Pelican module (runtime/pelicans.lua) re-proves first, from
research/pelican-F5FEE03DCFDB.json (research/docs/pelican-cas-F5FEE03DCFDB.md).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/pelican-F5FEE03DCFDB.json'
# The chin gun's firing sound (research/docs/pelican-maelstrom-sound-F5FEE03DCFDB.md): its own research and pins.
SOUND_RESEARCH = ROOT / 'research/pelican-maelstrom-sound-F5FEE03DCFDB.json'
SOUND_GROUPS = ('soundShot', 'soundOverride', 'soundMidi', 'soundSource', 'soundUpdate', 'soundRelease', 'soundCreation')
OUTPUT = ROOT / 'domains/pelican.lua'
# The code the runtime reads through (the airlift and dispatcher groups are research only).
GROUPS = ('behavior', 'transport', 'bearer', 'clock', 'stages', 'systemOrder', 'spawn', 'anchor', 'targetPush',
    'retarget', 'variants', 'extraction', 'turretComponents', 'pose', 'attachment', 'turretWeapon', 'gatlingTurret', 'pelicanWeapon', 'pelicanAI',
    'casing', 'firstShot', 'rateSeed', 'ai213', 'ammo', 'ammoNetwork', 'heading', 'targetChoice', 'aim', 'targetSet', 'spread', 'attribution')


def sound(profile: str) -> dict:
    """The firing-sound layout of a chin turret's own ProjectileWeapon copy: the record's firing-sound block, the
    instance value the game derives from it, the chin turret's own values (what a fresh copy holds) and the pins of the
    sound path. The sounds it may name are the weapon sound catalogue's (scripts/generate_weapon_sounds.py,
    domains/weapon_sounds.lua), which replaced the r7 allowlist."""
    research = json.loads(SOUND_RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('the Pelican sound research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned sound instruction differs between retained snapshots')
    if research['gameDll']['sha256'] not in profile:
        raise ValueError('the Pelican sound research covers another build than schemas/current.lua')
    unique = {}
    for group in SOUND_GROUPS:
        for pin in research['pins'][group]:
            unique.setdefault(pin['rva'], {'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes']})
    record = research['record']
    return {'source': {'research': SOUND_RESEARCH.name, 'build': research['build']},
        'record': {k: record[k] for k in ('stride', 'midi', 'loopStart', 'loopStop', 'single', 'blocks', 'span')},
        'instance': research['instance'],
        'chin': {k: research['chin'][k] for k in ('resource', 'midi', 'event', 'blockBytes')},
        'pins': sorted(unique.values(), key=lambda pin: pin['rva'])}


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('Pelican research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in profile:
        raise ValueError('the Pelican research covers another build than schemas/current.lua')
    unique = {}
    for group in GROUPS:
        for pin in research['pins'][group]:
            unique.setdefault(pin['rva'], {'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes']})
    components = {}
    for name, layout in research['components'].items():
        components[name] = {k: (int(v, 16) if k == 'global' else v) for k, v in layout.items()}
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDll']['sha256']},
        # The transport Pelican's entity resource (hex: 64-bit ids exceed double precision) and package.
        'entity': research['pelican']['entity'][2:], 'package': research['pelican']['package'],
        'packageId': research['pelican']['packageId'],
        # Every vehicle row: [the vehicle, the Pelican]; the vehicle is the Pelican's cargo.
        'vehicles': {name: {'type': v['type'], 'vehicle': v['vehicle'][2:]} for name, v in research['vehicles'].items()},
        'components': components,
        # The flight, in P (the Behavior record + context): stage, timestamps (microseconds), target, flags.
        'flight': {k: v for k, v in research['flight'].items() if k != 'stages'},
        # The spawn request (M.spawn): its entry and exact bytes, the descriptor the dispatcher builds, the world's own
        # default spawn context (all zero in every retained snapshot) and the entity settings table that proves the
        # Pelican's entity is loaded.
        'spawn': {k: (int(v, 16) if k == 'world' else v) for k, v in research['spawn'].items()
            if k != 'defaultsPerSnapshot'},
        # The hover anchor: the drop-position component's record, set from the spawn context's +0x610 at creation.
        'anchor': {k: (int(v, 16) if k == 'global' else v) for k, v in research['anchor'].items()
            if k not in ('readBy', 'replicated')},
        # Read-only diagnostics: the flight component holding the pushed target, and the two movers pushed natively.
        'flightTarget': {k: (int(v, 16) if k == 'global' else v) for k, v in research['flightTarget'].items()},
        'nativeMovers': {name: {k: (int(v, 16) if k == 'global' else v) for k, v in layout.items()}
            for name, layout in research['nativeMovers'].items()},
        # The behaviour each Pelican variant and turret gets from its entity type (read-only diagnostics).
        'variants': {'settings': {k: (int(v, 16) if k == 'offset' else v)
                for k, v in research['variants']['settings'].items()}, 'override': research['variants']['override'],
            'byType': {name: {'resource': v['resource'][2:], 'behaviour': v['behaviour'], 'path': v['path']}
                for name, v in research['variants']['byType'].items()},
            'extract': research['variants']['extract']},
        'extraction': research['extraction'],
        # A root's pose and a mounted child's link (read-only diagnostics).
        'pose': {'rotation': research['pose']['rotation'], 'position': research['pose']['position']},
        'attachment': {k: (int(v, 16) if k == 'global' else v) for k, v in research['attachment'].items()
            if k != 'observedPair'},
        # The weapon-side component managers (read-only diagnostics): each entity map at `map` (keys, capacity +8,
        # empty +0xC, multiplier +0x10).
        'turretComponents': {name: {'global': int(v['global'], 16), 'map': v['map']}
            for name, v in research['turretComponents'].items()},
        # What a turret fires and what of it is per instance (read-only diagnostics): the weapon record flags, the
        # projectile weapon's per-instance records and resolved copies, the magazine record, the heat and wind-up
        # components; and the chin turret's and Gatling Sentry's type values observed in the mission snapshots.
        'turretWeapon': {**{name: {k: (int(v, 16) if k == 'global' else v) for k, v in layout.items()}
                for name, layout in research['turretWeapon'].items()
                if name in ('weapon', 'projectileWeapon', 'magazine', 'heat', 'windUp')},
            'observed': research['turretWeapon']['observed']},
        # The Gatling turret experiment (runtime/pelican_gatling.lua): the game routines it may call (entry bytes), the
        # mount record, and the resources.
        'gatling': {k: (int(v, 16) if k == 'world' else
                {kk: (int(vv, 16) if kk == 'global' else vv) for kk, vv in v.items()} if k == 'mount' else
                {kk: (int(vv, 16) if kk == 'manager' else vv) for kk, vv in v.items()} if k == 'setBehaviour' else v)
            for k, v in research['gatling'].items()},
        # The ejected casing (section 19): the resolved ProjectileWeapon's casing particles and parameters, its ejector
        # nodes, the weapon's instance record that keeps the pooled casing effect from its first shot; both types'.
        'casing': {**{k: v for k, v in research['casing'].items() if k not in ('observed', 'gatlingPackageLists', 'rule')},
            'observed': {name: {'particles': v['particles'], 'parameters': v['parameters'], 'nodes': v['nodes'],
                'muzzleFlash': v['muzzleFlash']} for name, v in research['casing']['observed'].items()}},
        # A new weapon's rate: its resolved RPM times this factor while the mission modifier is active.
        'rateSeed': research['rateSeed'],
        # The Gatling AI's firing stage and how it is left (section 19d); the magazine's live rounds and capacity (19e).
        'ai213': {k: v for k, v in research['ai213'].items() if k != 'rule'},
        # The body's heading in the hold (section 20e): the hover controller's desired facing.
        'heading': {k: (int(v, 16) if k == 'global' else v) for k, v in research['heading'].items() if k != 'rule'},
        # Where the bullets go (section 20b): the targeting point, the weapon's own aim and recoil, the muzzle.
        'aim': {**{name: {k: (int(v, 16) if k == 'global' else v) for k, v in layout.items()}
                for name, layout in research['aim'].items() if name in ('weaponData', 'targeting', 'wielder')},
            'projectileSpeed': research['aim']['projectileSpeed'], 'observed': research['aim']['observed']},
        'targetSet': {k: ({kk: (int(vv, 16) if kk == 'global' else vv) for kk, vv in v.items()}
                if k in ('perception', 'faction', 'entityFlags') else v)
            for k, v in research['targetSet'].items() if k not in ('rule', 'observed')},
        'spread': {k: v for k, v in research['spread'].items() if k not in ('rule', 'observed', 'unit')},
        'apDonor': {k: v for k, v in research['apDonor'].items() if k not in ('rule', 'observed', 'alternatives')},
        'attribution': {k: ({kk: (int(vv, 16) if kk == 'global' else vv) for kk, vv in v.items()}
                if k in ('wieldable', 'tags') else v)
            for k, v in research['attribution'].items() if k not in ('rule', 'observed')},
        'ammo': {**{k: v for k, v in research['ammo'].items() if k != 'rule'},
            'roundsMax': research['ammoNetwork']['roundsMax']},
        # The chin gun's firing sound (runtime/pelican_weapon.lua; its pins are proven only when a sound is asked for).
        'sound': sound(profile),
        'pins': sorted(unique.values(), key=lambda pin: pin['rva'])}


def outputs() -> dict[str, str]:
    return {'domains/pelican.lua': '-- Generated by scripts/generate_pelican.py; do not edit.\n'
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
        raise RuntimeError('Stale Pelican domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
