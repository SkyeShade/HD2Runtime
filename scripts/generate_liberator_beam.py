"""Generate domains/liberator_beam.lua: the EXPERIMENTAL, SOLO-ONLY Liberator component swap (AR-23 Liberator fires
LAS-13 Trident pulses) that runtime/experiment_liberator_beam.lua applies for the LiberatorBeamProof live test.

Sources (read-only research, never trusted at run time without re-proof):
  * research/component-swap-liberator-beam-F5FEE03DCFDB.json (research/docs/component-swap-liberator-beam.md): the 63
    code pins, the write set (exact before/after bytes), the membership row and the snapshot checks;
  * research/liberator-beam-chamber-F5FEE03DCFDB.json (research/docs/component-swap-liberator-beam-chamber.md, after
    the first live L2 test could not fire): the 69 chamber / can-fire / reload pins and the L2b write, the Liberator's
    magazine record 201 +156 (a chamber weapon) 1 -> 0, the 40-K Meltagun's model;
  * research/component-membership-F5FEE03DCFDB.json: the entity file loader, spawn and destroy pins (the
    EntitySettingsHashmap slot, its lookup and the entity descriptor table the zero-live-Liberator census reads).
The three EXTRA pins below are the whole functions the module re-derives addresses from (the BeamWeapon type lookup,
the EntitySettings lookup, the descriptor writes and the invalid-entity sentinel), copied from the game.dll image of
the retained snapshots; tests/test_liberator_beam.py re-proves them against that image and on the snapshot overlay.

NOT a Runtime feature: not exported by api/hd2.lua, not part of the 0.30.x line (branch exp/liberator-beam only).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

SWAP = ROOT / 'research/component-swap-liberator-beam-F5FEE03DCFDB.json'
CHAMBER = ROOT / 'research/liberator-beam-chamber-F5FEE03DCFDB.json'
MEMBERSHIP = ROOT / 'research/component-membership-F5FEE03DCFDB.json'
TABLES = ROOT / 'research/entity-component-table-pointers-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/liberator_beam.lua'

LIBERATOR = '0x968211C0033DCE64'      # content/fac_helldivers/equipment/primary_weapons/assault_rifle (AR-23 Liberator)
TRIDENT = '0x3C86E871923F3970'        # laser_shotgun (LAS-13 Trident), BeamWeapon row 20, record 18
MEMBERSHIP_GROUPS = ('loader 0xFDB440 (generated_entities.dl_bin, in-place load)',
                     'spawn 0xFDC140 -> 0x581320 (create) / 0x581780 (post-create)',
                     'destroy 0xFDC820 (iterates the CURRENT list)')
EXTRA_PINS = [
    {'rva': 0x50E880, 'label': 'BeamWeapon type lookup 0x50E880 whole: slot 270 (+0xF12CE8), home = resource mod 46 '
        '(imul 0x2E), 16-byte rows from the table start, key 0 stops, record = table + 0x2E0 + 0x78 x index',
     'hex': '4885c9746c488b050cd7f502448bc14c8b90e82cf10048b8c94216b290852c6448f7e1488bc1482bc248d1e84803c248c1e805'
            '6bc02e442bc04533c90f1f4000418bc048c1e0044903c2488b10483bd174224885d2741a418bc0418d50014533c041ffc183f8'
            '2d440f45c24183f92e72cf33c0c34885c074f88b4808486bc1784805e00200004903c2c3'},
    {'rva': 0x5817A0, 'label': 'EntitySettings lookup in post-create: [manager + 0xF12EA0], home = resource & 0xFFF, '
        '32-byte rows, key 0 stops, linear probe bounded by 0x1000',
     'hex': '4c8b0df1a7ee024d8be8488b024c8be2488bf94d8b99a02ef100448bc84181e1ff0f000033db448bd30f1f8000000000458bc149'
            'c1e0054d03c3498b084885c97428483bc8742641ffc2418d51014181f9ff0f00004c8bc3448bcb440f45ca4181fa0010000072'
            'c8eb034c8bc3'},
    {'rva': 0xFDC1A4, 'label': 'spawn 0xFDC140: entity descriptor = manager + 0xF32F18 + 24 x slot, +0 resource, +8 '
        'entity; a free descriptor holds the invalid entity id [game.dll + 0x348456C]',
     'hex': '4e8d347de3651e004d03f74e8d34f6e8d83575004533c941895e0845894e0c49893e8b45044189461045894e1444384d007408'
            '41c74614010000008b86142ff300458bc10f1f8400000000008bc8488d14498b0d70834a02398cd6202ff300'},
]


def _pins(swap: dict, membership: dict, chamber: dict) -> list[dict]:
    pins: dict[int, dict] = {}

    def add(rva: int, hexbytes: str, label: str) -> None:
        if rva in pins:
            if pins[rva]['hex'] != hexbytes:
                raise ValueError(f'conflicting pin bytes at 0x{rva:X}')
            return
        pins[rva] = {'rva': rva, 'hex': hexbytes, 'label': label}

    for group, rows in swap['pins'].items():
        for pin in rows:
            add(pin['rva'], pin['bytes'], group + ': ' + pin['role'])
    for group, rows in chamber['pins'].items():
        for pin in rows:
            add(pin['rva'], pin['bytes'], 'chamber: ' + group + ': ' + pin['role'])
    for group in MEMBERSHIP_GROUPS:
        for pin in membership['pins'][group]:
            add(pin['rva'], pin['bytes'], group + ': ' + pin['role'])
    for pin in EXTRA_PINS:
        add(pin['rva'], pin['hex'], pin['label'])
    return [pins[rva] for rva in sorted(pins)]


def build() -> dict:
    swap = json.loads(SWAP.read_text(encoding='utf-8'))
    membership = json.loads(MEMBERSHIP.read_text(encoding='utf-8'))
    tables = json.loads(TABLES.read_text(encoding='utf-8'))
    chamber = json.loads(CHAMBER.read_text(encoding='utf-8'))
    for name, research in (('component swap', swap), ('component membership', membership), ('chamber', chamber)):
        if research['writes'] or research['protectionChanges']:
            raise ValueError(name + ' research must be read-only')
        if research['build'] != 'F5FEE03DCFDB':
            raise ValueError(name + ' research covers another build')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    dll_sha = tables['gameDll']['sha256']
    if dll_sha not in profile:
        raise ValueError('the research covers another game.dll than schemas/current.lua')
    for name, mismatches in swap['pinnedBytesMismatchPerSnapshot'].items():
        if mismatches:
            raise ValueError('a pin differs in snapshot ' + name)
    for name, snap in swap['snapshots'].items():
        if not (snap['listAsBefore'] and snap['record23IsFile'] and snap['row21'] == '0' * 32
                and snap['listPointerInsideTableAllocation'] and snap['protect'] == '0x2'):
            raise ValueError('snapshot ' + name + ' does not hold the reviewed before state')
    overlay = swap['overlay']
    if not (overlay['onlyLiberatorChanges'] and overlay['otherRecordsByteIdentical']
            and overlay['liberatorRecordAfter'] == 23):
        raise ValueError('the offline overlay does not prove a Liberator-only change')
    ws, mem, beam = swap['writeSet'], swap['membership'], swap['beamIndex']
    if not (mem['sortedAfter'] and mem['uniqueAfter'] and mem['countUnchanged'] and mem['count'] == 23):
        raise ValueError('the membership after-list is not sorted, unique and of the same count')
    if ws['membershipList']['before'] != mem['beforeHex'] or ws['membershipList']['after'] != mem['afterHex']:
        raise ValueError('membership write set disagrees with the membership section')
    if len(ws['record']['before']) != 240 or len(ws['record']['after']) != 240 or len(ws['indexRow']['after']) != 32:
        raise ValueError('write set extents changed')
    if ws['indexRow']['after'][:16] != bytes.fromhex(LIBERATOR[2:])[::-1].hex():
        raise ValueError('the new BeamWeapon row does not name the Liberator')
    if beam['liberatorHome'] != 20 or beam['firstEmptyOnPath'] != 21 or beam['occupiedOnPath'][0]['key'] != TRIDENT:
        raise ValueError('the BeamWeapon probe path changed')
    if int(LIBERATOR, 16) % beam['capacity'] != beam['liberatorHome']:
        raise ValueError('the Liberator home row is not resource mod capacity')
    if int(LIBERATOR, 16) & 0xFFF != mem['home']:
        raise ValueError('the Liberator EntitySettings home row is not resource & 0xFFF')
    for name, mismatches in chamber['pinnedBytesMismatchPerSnapshot'].items():
        if mismatches:
            raise ValueError('a chamber pin differs in snapshot ' + name)
    mag, cws = chamber['magazine'], chamber['writeSet']
    if not (mag['component'] == 'WeaponMagazineComponentData' and mag['index'] == 5 and mag['capacity'] == 540
            and mag['rowStride'] == 16 and mag['recordBase'] == 8640 and mag['recordStride'] == 160):
        raise ValueError('the magazine table schema changed')
    if mag['recordOwners'] != [LIBERATOR] or mag['probe'][-1]['row'] != mag['row'] or mag['home'] != int(LIBERATOR, 16) % 540:
        raise ValueError('the Liberator magazine row / record is not its own')
    if mag['rowBytes'] != bytes.fromhex(LIBERATOR[2:])[::-1].hex() + mag['record'].to_bytes(4, 'little').hex() + '0' * 8:
        raise ValueError('the magazine row bytes do not name the Liberator and its record')
    window = mag['recordBase'] + mag['recordStride'] * mag['record'] + 156
    if not (int(cws['offset'], 16) == window and cws['before'] == '01000000' and cws['after'] == '00000000'):
        raise ValueError('the L2b write set changed')
    if mag['liberatorRecord']['+156'] != 1 or mag['meltagunRecord']['+156'] != 0:
        raise ValueError('the chamber flag values changed')
    if any(d['bytes'] != '00' for d in mag['deltasTouching156']):
        raise ValueError('an entity delta sets the chamber flag')
    if chamber['compositions']['liberatorL2NotInMeltagun']:
        raise ValueError('the swapped Liberator is no longer a subset of the Meltagun')
    for name, snap in chamber['snapshots'].items():
        if not (snap['row'] == mag['rowBytes'] and snap['window'] == cws['before'] and snap['protect'] == '0x2'):
            raise ValueError('snapshot ' + name + ' does not hold the reviewed magazine bytes')
    pins = _pins(swap, membership, chamber)
    return {
        'source': {'research': SWAP.name, 'membership': MEMBERSHIP.name, 'chamber': CHAMBER.name,
                   'build': swap['build'], 'gameDllSha256': dll_sha},
        'experimental': True,
        'resources': {'liberator': LIBERATOR, 'trident': TRIDENT},
        # [game.dll + global] = the entity manager; + slotBase + 8 x index = a component's table; + eshSlot = the
        # EntitySettingsHashmap (entity allocation + 28); + descriptors = 0x800 descriptors of 24 bytes.
        'manager': {'global': 0x346BF98, 'slotBase': 0xF12478, 'eshSlot': 0xF12EA0, 'descriptors': 0xF32F18,
                    'descriptorStride': 24, 'descriptorCount': 0x800, 'descriptorEntity': 8,
                    'invalidEntity': 0x348456C},
        'beam': {'component': 'BeamWeaponComponentData', 'index': 270, 'capacity': beam['capacity'], 'rowStride': 16,
                 'records': 24, 'recordBase': 0x2E0, 'recordStride': 0x78, 'home': beam['liberatorHome'],
                 'tridentRow': 20, 'tridentRecord': 18,
                 'row': ws['indexRow']['row'], 'rowOffset': int(ws['indexRow']['offset'], 16),
                 'rowBefore': ws['indexRow']['before'], 'rowAfter': ws['indexRow']['after'],
                 'record': ws['record']['record'], 'recordOffset': int(ws['record']['offset'], 16),
                 'recordBefore': ws['record']['before'], 'recordAfter': ws['record']['after']},
        'membership': {'rows': 4096, 'rowStride': 32, 'row': mem['entitySettingsRow'], 'home': mem['home'],
                       'count': mem['count'], 'networkType': int(mem['networkType'], 16),
                       'listOffsetInBody': mem['listOffsetInBody'], 'before': mem['beforeHex'],
                       'after': mem['afterHex']},
        # The Liberator's ProjectileWeapon row must stay (0x744690 dereferences it without a NULL test).
        'projectile': {'component': 'ProjectileWeaponComponentData', 'index': 321, 'row': ws['projectileRowKept']['row'],
                       'record': ws['projectileRowKept']['record']},
        # L2b: the Liberator's own magazine record 201 +156 (a chamber weapon: its chambered round's type is filled
        # only by a ProjectileWeapon instance, so after L2 it can never fire) 1 -> 0, the 40-K Meltagun's value.
        'magazine': {'component': mag['component'], 'index': mag['index'], 'capacity': mag['capacity'],
                     'rowStride': mag['rowStride'], 'records': mag['records'], 'recordBase': mag['recordBase'],
                     'recordStride': mag['recordStride'], 'home': mag['home'], 'row': mag['row'],
                     'rowBytes': mag['rowBytes'], 'record': mag['record'], 'window': 156,
                     'windowOffset': window, 'before': cws['before'], 'after': cws['after']},
        'pins': pins,
    }


def outputs() -> dict[str, str]:
    return {'domains/liberator_beam.lua': '-- Generated by scripts/generate_liberator_beam.py; do not edit.\n'
            '-- EXPERIMENTAL, SOLO-ONLY (branch exp/liberator-beam): not a Runtime feature.\n'
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
        raise RuntimeError('Stale Liberator beam experiment domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
