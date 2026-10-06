"""Validate the player equipment reads (runtime/player_equipment.lua) on every retained snapshot (read-only; no game
process; no native call).

The production modules open the world exactly as in game, prove every pin of domains/player_equipment.lua, then read
the local player's loadout (every inventory slot, the throwable and its count), the weapon in hand, the primary's
ammunition and the worn backpack. Each snapshot's result must equal what research/player-equipment-F5FEE03DCFDB.json
observed in the same snapshot with the Python reader. The Supply Pack self-use is asked outside the game update and
must be refused (NOT_GAME_THREAD) with a native adapter that fails the run if anything is called; inside an update it
must be refused NO_BACKPACK (no snapshot wears one). A tampered pin must make the reads unavailable. Writes: none.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import snapshot_regions  # noqa: E402

OUTPUT = ROOT / 'validation/player-equipment-snapshot.json'
RESEARCH = ROOT / 'research/player-equipment-F5FEE03DCFDB.json'

BODY = r'''
local json=require('hd2runtime/primary_mapper/json')
local world_module=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local equipment=require('hd2runtime/runtime/player_equipment')
local scheduler=require('hd2runtime/runtime/scheduler')
local D=require('hd2runtime/domains/player_equipment')
world_module.set_runtime(source)
equipment.install(handles.Player)
local world=assert(world_module.open())
local out={}
local ok,why=equipment.prove(world)
out.proven=ok==true;out.why=why
local player=handles.local_player()
local function item(i)return i and{name=i.name,kind=i.kind,entity=i.entity_id} end
if player then
 local l,reason=player:loadout()
 if l then
  out.loadout={primary=item(l.primary),secondary=item(l.secondary),support=item(l.support),backpack=item(l.backpack),
   held=item(l.held),selection=l.selection,throwable=l.throwable and{name=l.throwable.name,count=l.throwable.count}
   }
 else out.loadout=reason end
 local held,why_held=player:held_weapon()
 out.held=held and{name=held.name ,slot=held.slot,entity=held.entity_id}or why_held
 local ammo,why_ammo=player:ammo('primary')
 out.ammo=ammo and{feed=ammo.feed,rounds=ammo.rounds,spare=ammo.spare_magazines,capacity=ammo.capacity }
  or why_ammo
 local pack,why_pack=player:backpack()
 out.backpack=pack and pack.name or why_pack
 local avatar=handles.local_avatar(world)
 equipment.set_adapter({needs_ammo=function()error('needs_ammo called')end,
  start_action=function()error('start_action called')end})
 if avatar then
  local _,outside=equipment.resupply_self(world,avatar.id)
  out.outside=outside
  local watch={status='active'};function watch.cancel()watch.status='cancelled'end
  function watch.tick()local _,inside=equipment.resupply_self(world,avatar.id);out.inside=inside;watch.status='complete'end
  scheduler.attach(watch)
  update(0.1)
 end
end
-- A tampered pin: the proof fails and every read refuses.
equipment.reset_for_tests()
local pin=D.pins[1]
local real=source.read
source.read=function(address,size)
 local bytes=real(address,size)
 if bytes and address<=world.game+pin.rva and world.game+pin.rva<address+size then
  local at=world.game+pin.rva-address+1
  bytes=bytes:sub(1,at-1)..'\204'..bytes:sub(at+1)
 end
 return bytes
end
local tampered,why_tampered=equipment.prove(world)
out.tampered=tampered==true;out.tamperedWhy=why_tampered
local l2,why2
if player then l2,why2=player:loadout()end
out.tamperedLoadout=player and(l2 and'read'or why2)or'no local player'
source.read=real
return json.encode(out)
'''


def expected(research):
    by = {o['snapshot']: o for o in research['observations']}
    out = {}
    for name, observation in by.items():
        if not observation['players'] or not observation['players'][0].get('slots'):
            out[name] = None
            continue
        local = observation['players'][0]
        out[name] = {slot: local['slots'][slot]['name'] for slot in ('primary', 'secondary', 'support', 'backpack')}
        out[name]['throwable'] = (local['throwable']['name'], local['throwable']['count'])
        out[name]['selection'] = local['selection']
        magazine = local['slots']['primary'].get('magazine')
        out[name]['ammo'] = magazine and (magazine['rounds'], magazine['spare'])
    return out


def validate(snapshots=None):
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    wanted = expected(research)
    results = {}
    for name in snapshots or list(wanted):
        report = json.loads(snapshot_regions.run_lua(BODY, build_profile.snapshot_directory() / name))
        problems = []
        if not report['proven']:
            problems.append('a pin did not prove: %s' % report.get('why'))
        if report['tampered'] or not any(text in str(report.get('tamperedLoadout')) for text in (
                'native equipment structure changed', 'no local player')):
            problems.append('a tampered pin did not refuse the reads')
        want = wanted[name]
        loadout = report.get('loadout')
        if want is None:
            if isinstance(loadout, dict):
                problems.append('a loadout was read where the research saw none')
        else:
            if not isinstance(loadout, dict):
                problems.append('no loadout: %s' % loadout)
            else:
                got = {slot: (loadout.get(slot) or {}).get('name') for slot in ('primary', 'secondary', 'support',
                    'backpack')}
                for slot in got:
                    if got[slot] != want[slot]:
                        problems.append('%s: %r != %r' % (slot, got[slot], want[slot]))
                throwable = loadout.get('throwable') or {}
                if (throwable.get('name'), throwable.get('count')) != want['throwable']:
                    problems.append('throwable %r != %r' % (throwable, want['throwable']))
                if loadout.get('selection') != want['selection']:
                    problems.append('selection')
            ammo = report.get('ammo')
            if want['ammo'] and (not isinstance(ammo, dict) or (ammo['rounds'], ammo['spare']) != want['ammo']
                    or ammo['feed'] != 'magazine'):
                problems.append('primary ammunition %r != %r' % (ammo, want['ammo']))
            if 'NO_BACKPACK' not in str(report.get('backpack')):
                problems.append('a backpack was read where none is worn')
            if 'NOT_GAME_THREAD' not in str(report.get('outside')):
                problems.append('the self-use was not refused outside the update: %r' % report.get('outside'))
            if report.get('inside') is not None and 'NO_BACKPACK' not in str(report.get('inside')):
                problems.append('the self-use was not refused for want of a backpack: %r' % report.get('inside'))
        results[name] = {'status': 'VALIDATED' if not problems else 'FAILED', 'problems': problems, 'report': report}
    failed = sorted(name for name, item in results.items() if item['status'] != 'VALIDATED')
    return {'status': 'VALIDATED' if not failed else 'FAILED', 'snapshots': len(results), 'failed': failed,
        'writes': 0, 'nativeCalls': 0, 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='append')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    for name, item in sorted(result['results'].items()):
        print(item['status'], name, '; '.join(item['problems']))
    print(result['status'], len(result['failed']), 'failed of', result['snapshots'])
    if result['status'] != 'VALIDATED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
