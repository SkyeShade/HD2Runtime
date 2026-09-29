"""Validate the event system's native world on every retained snapshot (read-only; no game process).

For each snapshot the production modules (runtime/event_world.lua, runtime/handles.lua) open the world exactly as in
game: build fingerprint, both image sizes and every pinned instruction of domains/event_natives.lua. Then they read
the game state, the player list with each avatar (through the network-id map), the local avatar's health record and
position, the engine generation check (the live id passes, a stale generation fails), and the local player's stat
totals. A tampered pin must make the world unavailable. Writes: none.
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

OUTPUT = ROOT / 'validation/event-world-snapshot.json'
SNAPSHOTS = ('F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap')

BODY = r'''
local json=require('hd2runtime/primary_mapper/json')
local world_module=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local natives=require('hd2runtime/domains/event_natives')
world_module.set_runtime(source)
local world,why=world_module.open()
assert(world,why)
local out={pins=#natives.pins}
local state=world_module.game_state(world)
out.gameState={state=state.state,name=state.name,mission=state.mission}
out.players={}
for _,p in ipairs(world_module.players(world,true))do
 out.players[#out.players+1]={peer=p.peer,isLocal=p['local'],entity=p.entity,lifecycle=p.lifecycle,avatar=p.avatar}
end
local avatar=handles.local_avatar(world)
local st=world_module.entity_state(world,avatar.id)
out.localAvatar={entity=avatar.id,type=avatar.type,health=st.health,maxHealth=st.max_health,life=st.life,
 unit=st.descriptor.unit,owned=st.descriptor.owned,
 existsLive=world_module.entity_exists(world,avatar.id),existsStale=world_module.entity_exists(world,avatar.id+4194304)}
local pos=world_module.unit_position(world,st.descriptor.unit)
out.localAvatar.position=pos and{pos.x,pos.y,pos.z}or false
out.stats={}
for name,key in pairs(natives.stats.keys)do
 out.stats[name]=world_module.stat_total(world,out.players[1].entity,key,world.view.slot())
end
-- A tampered pin: the proof must fail (the read overlay flips one byte of the first pinned instruction).
local pin=natives.pins[1]
local base=pin.module=='exe'and world.exe or world.game
local tampered={}
for k,v in pairs(source)do tampered[k]=v end
function tampered.read(address,size)
 local bytes=source.read(address,size)
 if bytes and address<=base+pin.rva and base+pin.rva<address+size then
  local at=base+pin.rva-address+1
  bytes=bytes:sub(1,at-1)..string.char((bytes:byte(at)+1)%256)..bytes:sub(at+1)
 end
 return bytes
end
world_module.set_runtime(tampered)
local refused,reason=world_module.open()
out.tamperRefused=refused==nil and tostring(reason):find('native event structure changed',1,true)~=nil
out.reads=world.view.reads
return json.encode(out)
'''


def validate(snapshots=SNAPSHOTS):
    results = {}
    for name in snapshots:
        path = build_profile.snapshot_directory() / name
        report = json.loads(snapshot_regions.run_lua(BODY, path))
        problems = []
        if report['gameState']['name'] != 'Ship':
            problems.append('expected the ship state')
        local = [p for p in report['players'] if p['isLocal']]
        if len(local) != 1 or local[0]['avatar'] != report['localAvatar']['entity']:
            problems.append('the local player does not resolve to the owned avatar')
        avatar = report['localAvatar']
        if (avatar['health'], avatar['maxHealth'], avatar['life'], avatar['owned']) != (125, 125, 0, True):
            problems.append('local avatar health record')
        if not avatar['existsLive'] or avatar['existsStale']:
            problems.append('engine generation check')
        if not avatar['position'] or any(abs(v) > 100000 for v in avatar['position']):
            problems.append('avatar position')
        if any(value is None for value in report['stats'].values()):
            problems.append('stat totals unreadable')
        if not report['tamperRefused']:
            problems.append('a tampered pin was not refused')
        results[name] = dict(report, passed=not problems, problems=problems)
    value = {'contract': 'hd2runtime.event_world_snapshot.v1', 'build': build_profile.BUILD_ID,
        'snapshots': results, 'passed': all(r['passed'] for r in results.values()), 'writes': 0}
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    value = validate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({name: (r['passed'], r['problems']) for name, r in value['snapshots'].items()}, indent=1))
    if not value['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
