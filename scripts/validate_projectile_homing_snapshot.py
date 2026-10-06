"""Exercise projectile homing (runtime/projectile_homing.lua, docs/projectile-homing.md) through hd2.projectiles.homing on
a copy-on-write memory overlay of the retained mission snapshot (no game process, no real writes).

The snapshot holds no projectile in flight, so the validation plants one: the next pool slot gets the local player's
own shot of the weapon in hand (its type, that weapon entity as the source, the local peer as creditor, the avatar as
owner, in flight, 20 degrees off a living enemy) and the spawn counter advances by one, as SpawnProjectile leaves them.

- every homing and pool pin proves on the snapshot's game.dll;
- the incremental enemy scan finishes a pass and lists living catalogued enemies with positions;
- the planted shot is followed and locks on the enemy with the smallest angle off its direction;
- each update writes exactly that shot's velocity (12 bytes, one guarded transaction, no protection change): turned by
  exactly turn_rate x dt toward the aim point, the same speed; every other byte of its flight, hit, source, type and flag
  records unchanged; once it points at the target there is no further write;
- refusals and non-actions: another peer's shot (untouched), a unit-driven shot (UNIT_DRIVEN), the same type from
  another entity (another weapon), no target inside the cone, a 'friendly' target with nobody else in the game, a shot
  whose distance travelled went backwards (its slot was reused), and a changed pin (every shot flies straight).
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
import validate_attachment_authoring_snapshot as overlay_source  # noqa: E402

SNAPSHOT = build_profile.snapshot_directory() / 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'
OUTPUT = ROOT / 'validation/projectile-homing-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')].replace(
    "local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '')

PROGRAM = OVERLAY + r'''
-- Overlay writes merge into every overlapping overlay entry (a planted record and a later write to part of it read
-- back as the write, whatever order the entries are visited in).
local function put(at,bytes)
 for address,value in pairs(overlay)do
  if address<at+#bytes and address+#value>at then
   local first=math.max(address,at);local last=math.min(address+#value,at+#bytes)
   overlay[address]=value:sub(1,first-address)..bytes:sub(first-at+1,last-at)..value:sub(last-address+1)
  end
 end
 if overlay[at]==nil then overlay[at]=bytes end
end
function poke(at,bytes)put(at,bytes)end
function runtime.write(at,bytes)
 assert((protection[at-at%PAGE] or original_protect(at-at%PAGE))==4,'overlay write without writable page')
 counts.writes=counts.writes+1;put(at,bytes)
 return true,nil,#bytes
end
local world_module=require('hd2runtime/runtime/event_world')
world_module.set_runtime(runtime)
local homing=require('hd2runtime/runtime/projectile_homing')
local api=require('hd2runtime/api/homing')
local D=require('hd2runtime/domains/projectile_homing')
local PO=require('hd2runtime/domains/projectile_rows').pool
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(m)lines[#lines+1]=m end
log_module.debug=true
local F,H=D.flight,PO.hit
local DT=1/60
local function f32(v)return b.encode(v,'f32')end
local function u32(v)return b.encode(v,'u32')end
local function rf(at)return b.value(runtime.read(at,4),0,'f32')end
local function len(x,y,z)return math.sqrt(x*x+y*y+z*z)end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,checks={}}
local function check(name,ok,detail)
 result.checks[#result.checks+1]={check=name,ok=ok==true,detail=detail}
 assert(ok,name..(detail and(': '..tostring(detail))or''))
end

local world=assert(world_module.open())
check('every homing and pool pin proves',homing.prove(world)==true)
result.pins=#D.pins
local game=assert(world_module.game_state(world))
check('a mission snapshot',game.mission==true)
local counter,system=world_module.projectile_counter(world)
check('the projectile pool is readable',counter~=nil)
local lo,hi=world_module.local_peer(world)
local me
for _,p in ipairs(world_module.players(world,true))do if p['local']then me=p end end
check('the local avatar resolves',me and me.avatar~=nil)
local held=world_module.equipped(world,me.avatar)
check('the local player holds a weapon',held and held.entity~=nil)
local weapon
for _,w in ipairs(D.weapons)do for _,s in ipairs(w.sources)do if s==held.type then weapon=w end end end
check('the weapon in hand is a homing weapon',weapon~=nil,held.type)
result.weapon,result.weaponTypes=weapon.name,weapon.types
local kind=weapon.types[1]
local origin=world_module.unit_position(world,world_module.entity_unit(world,me.avatar))
check('the avatar has a position',origin~=nil)

local handle=api.homing(weapon.name,{target='enemy',turn_rate=90,cone=60,range=400,arm_distance=2,owner='validation'})
check('hd2.projectiles.homing accepts the weapon',handle.status=='active',handle.reason)

-- Warm: the weapon in hand keeps the enemy scan running.
for _=1,400 do homing.step(DT)end
local enemies,complete=homing.enemies()
check('the enemy scan finished a pass',complete==true)
local listed=0
for _,e in ipairs(enemies)do if e.at then listed=listed+1 end end
check('living catalogued enemies are listed with positions',listed>0,listed)
result.enemies=listed
local start={x=origin.x,y=origin.y,z=origin.z+1.5}
local nearest,nearest_d
for _,e in ipairs(enemies)do
 if e.at then
  local d=len(e.x-start.x,e.y-start.y,e.z+1-start.z)
  if d>5 and d<400 and(not nearest_d or d<nearest_d)then nearest,nearest_d=e,d end
 end
end
check('an enemy within 400 m',nearest~=nil)
result.nearest={name=nearest.name,distance=nearest_d}

local current=counter
local function plant(spec)
 local slot=current%PO.slots
 local flight={}
 local function put(offset,bytes)flight[#flight+1]={offset,bytes}end
 local record=string.rep('\0',PO.flight.stride)
 local function set(s,offset,bytes)return s:sub(1,offset)..bytes..s:sub(offset+#bytes+1)end
 local v=spec.velocity
 record=set(record,F.position,f32(spec.position.x)..f32(spec.position.y)..f32(spec.position.z))
 record=set(record,F.velocity,f32(v.x)..f32(v.y)..f32(v.z))
 record=set(record,F.speed,f32(len(v.x,v.y,v.z)))
 record=set(record,F.distance,f32(spec.distance or 3))
 record=set(record,F.lifetime,f32(5))
 record=set(record,F.unit,u32(spec.unit or 0))
 local hit=string.rep('\0',H.stride)
 hit=set(hit,H.creditor,u32(spec.lo or lo)..u32(spec.hi or hi))
 hit=set(hit,H.owner,u32(me.avatar))
 poke(system+PO.flight.base+slot*PO.flight.stride,record)
 poke(system+H.base+slot*H.stride,hit)
 poke(system+PO.source.base+slot*PO.source.stride+PO.source.entity,u32(spec.source or held.entity))
 poke(system+PO.types.base+slot*PO.types.stride,u32(spec.type or kind))
 poke(system+PO.flags.base+slot*PO.flags.stride,string.char(PO.flags.inFlight,0))
 current=current+1
 poke(system+PO.counter,u32(current))
 return slot
end
local function records(slot)
 return {flight=runtime.read(system+PO.flight.base+slot*PO.flight.stride,PO.flight.stride),
  hit=runtime.read(system+H.base+slot*H.stride,H.stride),
  source=runtime.read(system+PO.source.base+slot*PO.source.stride,PO.source.stride),
  type=runtime.read(system+PO.types.base+slot*PO.types.stride,PO.types.stride),
  flags=runtime.read(system+PO.flags.base+slot*PO.flags.stride,PO.flags.stride)}
end
local function velocity(slot)
 local at=system+PO.flight.base+slot*PO.flight.stride+F.velocity
 return {x=rf(at),y=rf(at+4),z=rf(at+8)}
end
-- 20 degrees off the nearest enemy's aim point, about +Z, at 200 m/s.
local tx,ty,tz=nearest.x-start.x,nearest.y-start.y,nearest.z+1-start.z
local d=len(tx,ty,tz);tx,ty,tz=tx/d,ty/d,tz/d
local a=math.rad(20)
local dx,dy=tx*math.cos(a)-ty*math.sin(a),tx*math.sin(a)+ty*math.cos(a)
local n=len(dx,dy,tz);dx,dy,dz=dx/n,dy/n,tz/n
local SPEED=200

-- The steered shot.
local slot=plant({position=start,velocity={x=dx*SPEED,y=dy*SPEED,z=dz*SPEED}})
local before=records(slot)
local writes0=counts.writes
homing.step(DT)
local tracked=homing.tracked()
local shot=tracked[slot]
check('the planted shot is followed',shot~=nil,json.encode({stats=handle:stats(),log=lines,slot=slot,counter=counter,
 players=#world_module.players(world,true),types=world_module.projectile_types(world,system,counter,1)}))
check('it locked on a target',shot.target~=nil)
result.locked={name=shot.target.name,entity=shot.target.entity}
local aim={x=shot.target.x,y=shot.target.y,z=shot.target.z+1}
local after=velocity(slot)
local wrote=counts.writes-writes0
check('one guarded transaction wrote the velocity',wrote>=1 and wrote<=2,wrote)
check('no page protection changed',counts.protection_changes==0,counts.protection_changes)
local s1=len(after.x,after.y,after.z)
check('the speed is kept',math.abs(s1-SPEED)<1e-3,s1)
local want_x,want_y,want_z=aim.x-start.x,aim.y-start.y,aim.z-start.z
local wl=len(want_x,want_y,want_z);want_x,want_y,want_z=want_x/wl,want_y/wl,want_z/wl
local ex,ey,ez,between=homing.turn_toward(dx,dy,dz,want_x,want_y,want_z,math.rad(90)*DT)
local err=len(after.x/SPEED-ex,after.y/SPEED-ey,after.z/SPEED-ez)
check('turned exactly turn_rate x dt toward the aim point',err<1e-5,err)
result.firstTurnDegrees=math.deg(math.min(between,math.rad(90)*DT))
local now=records(slot)
local vf,vl=F.velocity+1,F.velocity+12
check('nothing else of the flight record changed',now.flight:sub(1,vf-1)==before.flight:sub(1,vf-1)
 and now.flight:sub(vl+1)==before.flight:sub(vl+1))
check('the hit, source, type and flag records are unchanged',now.hit==before.hit and now.source==before.source
 and now.type==before.type and now.flags==before.flags)

-- It keeps turning, by turn_rate x dt each update, until it points at the aim point; then nothing is written.
local steps,last=1,counts.writes
for _=1,400 do
 homing.step(DT)
 if counts.writes==last then break end
 last=counts.writes;steps=steps+1
end
local final=velocity(slot)
local fl=len(final.x,final.y,final.z)
local angle=math.deg(math.acos(math.min(1,(final.x*want_x+final.y*want_y+final.z*want_z)/fl)))
check('it converges on the aim point and stops writing',angle<0.1,angle)
check('in about 20 / (90 x dt) updates',steps>=12 and steps<=15,steps)
result.convergence={updates=steps,residualDegrees=angle,speed=fl}
local writes_now=counts.writes
homing.step(DT);homing.step(DT)
check('no write once on target',counts.writes==writes_now)

-- A reused slot: the distance travelled went backwards.
poke(system+PO.flight.base+slot*PO.flight.stride+F.distance,f32(1))
homing.step(DT)
check('a shot whose distance went backwards is dropped',homing.tracked()[slot]==nil)

local function quiet(spec,label)
 local w=counts.writes
 local s=plant(spec)
 homing.step(DT);homing.step(DT)
 check(label..': not steered',counts.writes==w and homing.tracked()[s]==nil)
 return s
end
local stats0=handle:stats()
quiet({position=start,velocity={x=dx*SPEED,y=dy*SPEED,z=dz*SPEED},lo=(lo+1)%4294967296},'another peer\'s shot')
check('counted as not this player\'s',handle:stats().others==stats0.others+1)
quiet({position=start,velocity={x=dx*SPEED,y=dy*SPEED,z=dz*SPEED},unit=12345},'a unit-driven shot')
check('refused UNIT_DRIVEN',(handle:stats().refused.UNIT_DRIVEN or 0)==1)
quiet({position=start,velocity={x=dx*SPEED,y=dy*SPEED,z=dz*SPEED},source=me.avatar},'the same type from another entity')
check('counted as another weapon\'s',handle:stats().other_sources==stats0.other_sources+1)
local w=counts.writes
local up=plant({position=start,velocity={x=0,y=0,z=SPEED}})
for _=1,3 do homing.step(DT)end
check('no target inside the cone: followed, not written',homing.tracked()[up]~=nil and counts.writes==w)

-- 'friendly' with nobody else in the game: nothing to home on.
local friendly=api.homing(weapon.name,{target='friendly',turn_rate=90,cone=60,range=400,owner='validation'})
check('the same mod reconfigures the weapon',friendly.status=='active'and handle.configs[1].status=='replaced')
w=counts.writes
local f=plant({position=start,velocity={x=dx*SPEED,y=dy*SPEED,z=dz*SPEED}})
for _=1,3 do homing.step(DT)end
check('friendly, solo: followed, no target, no write',homing.tracked()[f]~=nil and counts.writes==w)
local other=api.homing(weapon.name,{owner='another-mod'})
check('another mod is refused ALREADY_HOMING',other.status=='refused'and other.code=='ALREADY_HOMING')

-- A changed pin: every shot flies straight.
local pin=D.pins[1]
poke(world.game+pin.rva,string.char((b.unhex(pin.hex):byte(1)+1)%256))
world_module.set_runtime(runtime)
friendly:stop()
local again=api.homing(weapon.name,{target='enemy',owner='validation'})
w=counts.writes
local p=plant({position=start,velocity={x=dx*SPEED,y=dy*SPEED,z=dz*SPEED}})
for _=1,3 do homing.step(DT)end
check('a changed pin: nothing followed, nothing written',homing.tracked()[p]==nil and counts.writes==w)
local unavailable=false
for _,line in ipairs(lines)do if line:find('UNAVAILABLE',1,true)then unavailable=true end end
check('and the log says homing is unavailable',unavailable)
again:stop()
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
    summary = {k: v for k, v in result.items() if k != 'log'}
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
