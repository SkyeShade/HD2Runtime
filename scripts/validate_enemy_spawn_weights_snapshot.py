"""Exercise enemy spawn weights (runtime/enemy_spawn_weights.lua, docs/enemy-spawns.md) through hd2.enemies on a
copy-on-write memory overlay of the retained mission snapshot (a Terminid mission at difficulty 10; no game process, no
real writes).

- every pin and every roster descriptor proves on the snapshot's game.dll;
- Charger x 2: in every Charger row exactly its ten weights become the vanilla ones x 2 (guarded transaction, no
  protection change), every other byte of the three rosters unchanged; the same mod's x 3 replaces it from those
  bytes; another mod is refused ALREADY_SET;
- the pick model (PickEnemy's own rule: weight at the difficulty / sum of the group's active rows) gives the Charger
  twice its vanilla weight in each of its groups;
- Bile Titan x 0: its weights become 0 at once (it only removes candidates); its restore during the mission is
  deferred (a weight would go from 0 to positive after the mission loaded its packages), then done exactly once the
  game state is the ship;
- opts.difficulties: only the listed difficulty changes;
- a third-party value in a written row is a CONFLICT (logged, never overwritten, and stop() writes nothing);
- refusals: no acknowledgement, an unknown enemy, a multiplier above 10, a changed pin (nothing written).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from validate_entity_authoring_snapshot import lua, sources  # noqa: E402
import validate_projectile_homing_snapshot as homing_validation  # noqa: E402

SNAPSHOT = build_profile.snapshot_directory() / 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'
OUTPUT = ROOT / 'validation/enemy-spawn-weights-snapshot.json'
# The overlay runtime with merging writes (the homing validation's prelude, up to its first module use).
PRELUDE = homing_validation.PROGRAM[:homing_validation.PROGRAM.index("local world_module=require")]

PROGRAM = PRELUDE + r'''
local world_module=require('hd2runtime/runtime/event_world')
world_module.set_runtime(runtime)
local weights=require('hd2runtime/runtime/enemy_spawn_weights')
local api=require('hd2runtime/api/enemy_spawns')
local D=require('hd2runtime/domains/enemy_spawn_weights')
local natives=require('hd2runtime/domains/event_natives')
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(m)lines[#lines+1]=m end
local ACK={allow_unverified_effect=true,owner='validation'}
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,checks={}}
local function check(name,ok,detail)
 result.checks[#result.checks+1]={check=name,ok=ok==true,detail=detail}
 assert(ok,name..(detail and(': '..tostring(detail))or''))
end
local function f(bytes,o)return b.value(bytes,o,'f32')end
local world=assert(world_module.open())
local game=world.game
local function rosters()
 local out={}
 for _,fa in ipairs(D.factions)do out[fa.name]=runtime.read(game+fa.rows,fa.count*D.row.stride)end
 return out
end
local VANILLA=rosters()
local function rows_of(name)
 local list={}
 for _,fa in ipairs(D.factions)do for _,e in ipairs(fa.entries)do
  if e.name==name then list[#list+1]={faction=fa,entry=e}end end end
 return list
end
local function weights_at(fa,index)return runtime.read(game+fa.rows+index*D.row.stride+D.row.weights,40)end
-- Every byte of every roster equals the vanilla one except the weights of the listed rows.
local function only_rows_changed(rows)
 local now=rosters()
 local allowed={}
 for _,r in ipairs(rows)do allowed[r.faction.name..':'..r.entry.index]=true end
 for _,fa in ipairs(D.factions)do
  for i=0,fa.count-1 do
   local at=i*D.row.stride
   local a,c=VANILLA[fa.name]:sub(at+1,at+D.row.stride),now[fa.name]:sub(at+1,at+D.row.stride)
   if a~=c then
    if not allowed[fa.name..':'..i]then return false,fa.name..' row '..i..' changed'end
    local w=D.row.weights
    if a:sub(1,w)~=c:sub(1,w)or a:sub(w+41)~=c:sub(w+41)then return false,fa.name..' row '..i..' changed outside its weights'end
   end
  end
 end
 return true
end
local function scaled(rows,k,only)
 for _,r in ipairs(rows)do
  local now,van=weights_at(r.faction,r.entry.index),b.unhex(r.entry.weights)
  for d=1,10 do
   local want=f(van,(d-1)*4)*((not only or only[d])and k or 1)
   if math.abs(f(now,(d-1)*4)-want)>1e-6 then return false,('%s row %d difficulty %d: %g, want %g'):format(
    r.faction.name,r.entry.index,d,f(now,(d-1)*4),want)end
  end
 end
 return true
end

-- The mission the snapshot holds: Terminids at difficulty 10, with its active subfaction tags.
local manager=world.view.pointer(game+D.manager.global)
local difficulty=world.view.u32(manager+D.manager.difficulty)
check('a Terminid mission at difficulty 10',world.view.u32(manager+D.manager.faction)==2 and difficulty==10,difficulty)

-- Charger x 2.
local chargers=rows_of('Charger')
check('the Charger has roster rows',#chargers>=1,#chargers)
local w0,p0=counts.writes,counts.protection_changes
local charger=api.spawn_weight('Charger',2,ACK)
check('hd2.enemies.spawn_weight applies at once',charger.status=='applied',tostring(charger.status)..' '
 ..tostring(charger.reason))
check('every Charger weight is the vanilla one x 2',scaled(chargers,2))
check('no other roster byte changed',only_rows_changed(chargers))
check('no page protection changed',counts.protection_changes==p0,counts.protection_changes-p0)
result.chargerRows,result.chargerWrites=#chargers,counts.writes-w0

-- The pick model: PickEnemy's rule over the snapshot's active subfaction tags.
local tags={}
local tag_count=world.view.u32(manager+D.manager.tags+0x40)or 0
for i=0,tag_count-1 do tags[world.view.u32(manager+D.manager.tags+i*4)]=true end
-- PickEnemy's rule at difficulty d: the group's rows with active tags and a weight above 0; share = weight / sum.
local function share(group,entity,bytes_of,d)
 local total,mine=0,0
 for _,e in ipairs(D.factions[1].entries)do
  if e.group==group then
   local row=runtime.read(game+D.factions[1].rows+e.index*D.row.stride,D.row.stride)
   local t1,t2=b.u32(row,D.row.tags),b.u32(row,D.row.tags+4)
   local active=(t1==0 or tags[t1])and(t2==0 or tags[t2])
   local w=f(bytes_of(e),(d-1)*4)
   if active and w>0 then total=total+w;if e.entity==entity then mine=mine+w end end
  end
 end
 return total>0 and mine/total or 0,mine,total
end
local shares,exact,positive={},true,0
for _,r in ipairs(chargers)do
 for d=1,10 do
  local before,w,s=share(r.entry.group,r.entry.entity,function(e)return b.unhex(e.weights)end,d)
  local after=share(r.entry.group,r.entry.entity,function(e)return weights_at(D.factions[1],e.index)end,d)
  shares[#shares+1]={group=r.entry.group,difficulty=d,before=before,after=after}
  if w>0 then
   positive=positive+1
   -- Doubling its weight: 2w / (S + w).
   if math.abs(after-2*w/(s+w))>1e-6 or not(after>before or before==1)then exact=false end
  elseif after~=0 then exact=false end
 end
end
result.chargerShares=shares
check('the pick model: at each difficulty where it spawns, the Charger\'s share is 2w / (S + w); where its vanilla '
 ..'weight is 0 it stays 0',exact and positive>0,positive)

-- The same mod's x 3 replaces it; another mod is refused.
local three=api.spawn_weight('Charger',3,ACK)
check('the same mod replaces its own multiplier',three.status=='applied'and scaled(chargers,3))
local other=api.spawn_weight('Charger',5,{allow_unverified_effect=true,owner='another-mod'})
check('another mod is refused ALREADY_SET',other.status=='refused'and other.code=='ALREADY_SET',tostring(other.code))

-- Bile Titan x 0, restored only aboard the ship.
local titans=rows_of('Bile Titan')
local titan=api.spawn_weight('Bile Titan',0,ACK)
check('x 0 applies at once (it only removes candidates)',titan.status=='applied'and scaled(titans,0))
titan:stop()
check('its restore waits while the mission runs',titan.status=='stopping'and scaled(titans,0),titan.status)
local state_object=world.view.pointer(game+natives.state.game)
local state_at=state_object+natives.state.state
poke(state_at,b.encode(3,'u32'))
weights.step()
check('aboard the ship it is restored exactly',titan.status=='stopped'and scaled(titans,1),titan.status)
poke(state_at,b.encode(4,'u32'))

-- Only the listed difficulties.
local hunters=rows_of('hunter_tier_1')
local hunter=api.spawn_weight('hunter_tier_1',2,{allow_unverified_effect=true,owner='validation',difficulties={10}})
check('opts.difficulties changes only those weights',hunter.status=='applied'and scaled(hunters,2,{[10]=true}))
hunter:stop()
check('and stop() restores them',scaled(hunters,1))

-- A third-party value in a written row.
local first=chargers[1]
local addr=game+first.faction.rows+first.entry.index*D.row.stride+D.row.weights
poke(addr,b.encode(7.5,'f32'))
weights.step()
check('another writer\'s value is a CONFLICT',three.status=='conflict'and three.code=='CONFLICT',three.status)
local before_stop=counts.writes
three:stop()
check('stop() after a conflict writes nothing',counts.writes==before_stop)
poke(addr,b.unhex(first.entry.weights):sub(1,4))
for _,r in ipairs(chargers)do poke(game+r.faction.rows+r.entry.index*D.row.stride+D.row.weights,b.unhex(r.entry.weights))end

-- Refusals.
local r1=api.spawn_weight('Charger',2,{owner='validation'})
check('no acknowledgement: ACKNOWLEDGEMENT_REQUIRED',r1.status=='refused'and r1.code=='ACKNOWLEDGEMENT_REQUIRED')
local r2=api.spawn_weight('No Such Bug',2,ACK)
check('an unknown enemy: UNKNOWN_ENEMY',r2.status=='refused'and r2.code=='UNKNOWN_ENEMY')
local r3=api.spawn_weight('Charger',11,ACK)
check('a multiplier above 10: INVALID_MULTIPLIER',r3.status=='refused'and r3.code=='INVALID_MULTIPLIER')
local pin=D.pins[1]
poke(game+pin.rva,string.char((b.unhex(pin.hex):byte(1)+1)%256))
world_module.set_runtime(runtime)
local w2=counts.writes
local r4=api.spawn_weight('Charger',2,ACK)
check('a changed pin: nothing written',r4.status=='unavailable'and counts.writes==w2,r4.status)
r4:stop()
result.writes=counts.writes
result.protectionChanges=counts.protection_changes
result.log=lines
return json.encode(result)
'''


def validate(snapshot):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal SNAPSHOT_NAME='
        + lua(Path(snapshot).name) + '\n' + PROGRAM)
    return json.loads(execute(program.encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', newline='\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'log'}, indent=2))


if __name__ == '__main__':
    main()
