"""Validate the event system's native world on every retained snapshot (read-only; no game process).

For each snapshot the production modules (runtime/event_world.lua, runtime/handles.lua) open the world exactly as in
game: build fingerprint, both image sizes and every pinned instruction of domains/event_natives.lua. Then they read
the game state, the player list with each avatar (through the network-id map), the local avatar's health record and
position, the engine generation check (the live id passes, a stale generation fails), and the local player's stat
totals. A tampered pin must make the world unavailable. Writes: none.

The four in-mission captures (one host session) add: the Mission state with its game_mode, the reinforced avatar,
the corpse that replaced the first avatar (origin 602 -> corpse 851 on the same unit), the per-source stats
(weapon names from the catalog) and the mission-end teardown (PrepareShip, no avatar, stats kept).

Every snapshot also checks: the Hellbomb explosions' settings records, the local player's equipped weapon (the R-36
Eruptor in hand before the death, nothing aboard the ship), the projectile system gate (active only in a mission)
and the status request queue.
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
SHIP = ('F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap')
MISSION = {'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap': 'alive',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap': 'alive',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap': 'reinforced',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap': 'ended'}
SNAPSHOTS = SHIP + tuple(MISSION)

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
local st=avatar and world_module.entity_state(world,avatar.id)
if st then
 out.localAvatar={entity=avatar.id,type=avatar.type,health=st.health,maxHealth=st.max_health,life=st.life,
  unit=st.descriptor.unit,owned=st.descriptor.owned,
  existsLive=world_module.entity_exists(world,avatar.id),existsStale=world_module.entity_exists(world,avatar.id+4194304)}
 local pos=world_module.unit_position(world,st.descriptor.unit)
 out.localAvatar.position=pos and{pos.x,pos.y,pos.z}or false
else out.localAvatar=false end
out.stats={}
for name,key in pairs(natives.stats.keys)do
 out.stats[name]=world_module.stat_total(world,out.players[1].entity,key,world.view.slot())
end
local K=natives.stats.keys
local breakdown=world_module.stat_breakdown(world,out.players[1].entity,{K.projectiles_fired,K.dealt_kills},world.view.slot())
out.sources={}
for type_hex,values in pairs(breakdown and breakdown.sources or{})do
 out.sources[#out.sources+1]={type=type_hex,name=world_module.source_name(type_hex),shots=values[K.projectiles_fired],
  kills=values[K.dealt_kills]}
end
table.sort(out.sources,function(a,c)return a.type<c.type end)
local corpses=world_module.corpses(world,world.view.slot())
out.corpses={count=corpses and corpses.count}
local index=corpses and corpses.origins[602]
out.corpses.of602=index and world_module.corpse_entity(world,corpses,index,4194863)or false
out.corpses.wrongUnit=index and world_module.corpse_entity(world,corpses,index,4194864)or false
old=handles.entity({id=602,type='4D1C334D294DFA97'})
out.handle602={valid=old:is_valid(),reason=old:describe().reason,semantic_id=old.semantic_id}
-- Explosion identity: every weapon explosion hd2.explosions can request has a settings record carrying its type.
out.explosions={}
for _,item in ipairs(natives.explosion.weapons)do
 out.explosions[#out.explosions+1]={weapon=item.weapon,type=item.type,
  settings=world_module.explosion_settings(world,item.type)~=nil}
end
out.explosionQueue=world.view.u32(world.view.pointer(world.game+natives.explosion.queue)+natives.explosion.count)
-- The named explosions (Hellbombs) have settings records too.
out.namedExplosions={}
for _,item in ipairs(natives.explosion.named)do
 out.namedExplosions[#out.namedExplosions+1]={name=item.name,type=item.type,
  settings=world_module.explosion_settings(world,item.type)~=nil}
end
-- What the local player holds (wielder slot 0 + inventory selection), through the production reader.
local me=handles.local_player()
local weapon,weapon_why
if me then weapon,weapon_why=me:equipped_weapon()end
out.equipped=weapon and{name=weapon.name,type=weapon.type,entity=weapon.entity_id,slot=weapon.slot,
 slotProven=weapon.slot_proven,selection=weapon.selection}or{reason=tostring(weapon_why)}
if avatar then
 local raw=world_module.equipped(world,avatar.id)
 out.equippedRaw=raw and{entity=raw.entity,selection=raw.selection,slot=raw.slot}or false
end
-- Projectile system gate and status queue as the actions read them.
local system=world.view.pointer(world.game+natives.projectile.system)
local flag=system and world.view.read(system+natives.projectile.active,1)
out.projectileSystemActive=flag and flag:byte()or false
out.statusQueue=world.view.u32(world.view.pointer(world.game+natives.status.queue)+natives.status.count)
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
        phase = MISSION.get(name, 'ship')
        expected_state = {'ship': ('Ship', False), 'ended': ('PrepareShip', False)}.get(phase, ('Mission', True))
        if (report['gameState']['name'], report['gameState']['mission']) != expected_state:
            problems.append('expected the %s state' % expected_state[0])
        local = [p for p in report['players'] if p['isLocal']]
        avatar = report['localAvatar']
        if phase == 'ended':
            if avatar or len(local) != 1 or local[0].get('avatar') is not None:
                problems.append('an avatar survived the mission end')
        else:
            if not avatar or len(local) != 1 or local[0]['avatar'] != avatar['entity']:
                problems.append('the local player does not resolve to the owned avatar')
            elif (avatar['life'], avatar['owned']) != (0, True) or (phase == 'ship' and (avatar['health'],
                    avatar['maxHealth']) != (125, 125)):
                problems.append('local avatar health record')
            elif not avatar['existsLive'] or avatar['existsStale']:
                problems.append('engine generation check')
            elif not avatar['position'] or any(abs(v) > 100000 for v in avatar['position']):
                problems.append('avatar position')
        if any(value is None for value in report['stats'].values()):
            problems.append('stat totals unreadable')
        if report['corpses']['count'] is None:
            problems.append('corpse manager unreadable')
        if not all(item['settings'] for item in report['explosions']) or report['explosionQueue'] is None:
            problems.append('explosion settings or queue unreadable')
        if report['handle602']['semantic_id'] != 'entity/v1/helldivers/avatar_helldiver':
            problems.append('avatar semantic id')
        if phase == 'reinforced':
            if report['corpses']['of602'] != 851 or report['corpses']['wrongUnit']:
                problems.append('the first avatar is not linked to its corpse on its own unit')
            if report['handle602']['valid'] or avatar['entity'] != 852:
                problems.append('the handle to the first avatar is still valid, or the new avatar did not resolve')
            named = {s['name']: s for s in report['sources']}
            if (named.get('R-36 Eruptor') or {}).get('kills') != 13 or (named.get('P-113 Verdict') or {}).get(
                    'shots') != 20:
                problems.append('per-source stats')
        if not all(item['settings'] for item in report['namedExplosions']):
            problems.append('Hellbomb explosion settings missing')
        if report['statusQueue'] is None:
            problems.append('status queue unreadable')
        if phase == 'alive':
            if (report['equipped'].get('name'), report['equipped'].get('slot'), report['equipped'].get('slotProven')) != (
                    'R-36 Eruptor', 'primary', True) or report['projectileSystemActive'] != 1:
                problems.append('the R-36 Eruptor in hand or the active projectile system was not read')
        elif phase == 'ship':
            if report['equipped'].get('reason') != 'nothing in hand' or report['projectileSystemActive'] != 0:
                problems.append('something in hand, or an active projectile system, aboard the ship')
        elif phase == 'reinforced':
            # The capture recorded the held entity before the entity table saw it (non-atomic capture): the reader
            # finds no descriptor for it and reports nothing in hand instead of guessing.
            if report['equippedRaw'] and report['equippedRaw'].get('entity') is not None:
                problems.append('an unresolvable held entity was reported as held')
        elif phase == 'ended':
            if report['projectileSystemActive'] != 0:
                problems.append('the projectile system is active after the mission')
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
