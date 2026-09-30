"""Exercise the equipment coverage fields (research/equipment-coverage-F5FEE03DCFDB.json) on a copy-on-write
snapshot overlay: SH-32 recharge, the SH-51 body and energy barrier, the Warp Pack, the Hover Pack, the Guard Dog
backpacks, drones and drone weapons, the LAS-17 heat levels, the LAS-98 beam fire rate and the Maxigun recoil
multipliers.

For every field:

1. the live bytes equal the reviewed baseline, and a no-op applies as ALREADY_DESIRED,
2. a changed value writes exactly the field (one write of the field width), reads back, and rolls back,
3. a third-party change is rejected as CONFLICT,
4. a missing allow_unverified_effect, a stale expect and an out-of-range value are rejected.

Every new link is re-proven on every write; each one is tampered with and must be refused: the backpack -> drone
link (DepositComponent +24), the backpack -> barrier link (ShieldControllerComponent +0), a linked damage zone's
identity, a Warp Pack injury entry's limb, and a drone weapon's carrier link and drone mount slot. Read-only
members (the drone and barrier default-zone armor, the barrier radius) must refuse writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources
import validate_attachment_authoring_snapshot as overlay_source

OUTPUT = ROOT / 'validation/equipment-coverage-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]
NEW_BACKPACK_FIELDS = ('shield.recharge_delay', 'shield.broken_recharge_delay', 'shield.recharge_rate',
    'warp.distance', 'warp.upward_bias', 'warp.downward_bias', 'warp.safe_heat_threshold',
    'warp.unsafe_heat_threshold', 'warp.heat_per_use', 'warp.heat_cooldown_per_second', 'warp.head_injury_damage',
    'warp.left_arm_injury_damage', 'warp.right_arm_injury_damage', 'warp.left_leg_injury_damage',
    'warp.right_leg_injury_damage', 'hover.duration')
NEW_WEAPON_FIELDS = ('heat.level_1_threshold', 'heat.level_2_threshold', 'heat.level_3_threshold',
    'heat.level_1_self_status', 'heat.level_2_self_status', 'heat.level_3_self_status', 'heat.overheat_lock',
    'beam.fire_rate', 'weapon.recoil_multiplier_horizontal', 'weapon.recoil_multiplier_vertical')

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local entity=require('hd2runtime/domains/entity_writes')
local weapons=require('hd2runtime/domains/player_weapon_writes')
local entity_db=require('hd2runtime/domains/entity_authoring')
local vehicle_db=require('hd2runtime/domains/vehicle_weapon_authoring')
local player_db=require('hd2runtime/domains/player_weapon_authoring')
local support_db=require('hd2runtime/domains/support_weapon_authoring')
local NEW_BACKPACK={}''' + ''.join('NEW_BACKPACK[' + lua(f) + ']=true;' for f in NEW_BACKPACK_FIELDS) + r'''
local NEW_WEAPON={}''' + ''.join('NEW_WEAPON[' + lua(f) + ']=true;' for f in NEW_WEAPON_FIELDS) + r'''
local function resolve(domain,spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local function copy(t)local r={};for k,v in pairs(t)do r[k]=v end;return r end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 fields=0,baselineMatches=0,noOps=0,changedWrites=0,rollbacks=0,conflictRejections=0,acknowledgementRejections=0,
 staleExpectRejections=0,rangeRejections=0,readOnlyRejections=0,chainTamperRejections=0,byFamily={},checked={}}
local function changed(field)
 if field.type=='boolean'then return not field.currentDefault end
 if field.type=='status_reference'then
  for _,value in ipairs(field.allowedValues or{})do if value~=field.currentDefault then return value end end
  return 'none'
 end
 local value=field.currentDefault+1
 if field.max and value>field.max then value=field.currentDefault-1 end
 return value
end
local function stale(field)
 if field.type=='boolean'then return not field.currentDefault end
 if field.type=='status_reference'then return changed(field)end
 return field.currentDefault+1
end
local function foreign(field)
 local storage=field.backing.storage
 if storage=='u8'then return string.char(7)end
 if field.type=='status_reference'then return b.encode(99,'u32')end
 return b.encode(field.currentDefault+3,storage)
end
-- One field: baseline, no-op, changed write and rollback, conflict, acknowledgement, stale expect, range.
local function exercise(family,domain,target,field,extra)
 local label=family..' '..(target.backpack or target.weapon)..' '..field.semanticFieldId
 -- Attack fields are addressed by their public id on the attack target ('arc.range' on attack 'primary').
 local public=target.attack and field.semanticFieldId:gsub('^(%a+)%.'..target.attack..'%.','%1.')or field.semanticFieldId
 local function request(expect,value,ack)
  local r=copy(extra or{});r.id='equipment';r.target=target;r.field=public;r.expect=expect;r.value=value
  r.allow_unverified_effect=ack or nil;return r
 end
 reset()
 local plan=resolve(domain,domain.validate_patch(request(field.currentDefault,field.currentDefault,true)))
 local part=plan.changes[1]
 local width=field.backing.width
 assert(#part.before==width,label..' width')
 result.baselineMatches=result.baselineMatches+1
 local checked=guarded.apply(runtime,plan)
 assert(checked.status=='ALREADY_DESIRED'and checked.writes==0,label..' no-op changed state')
 result.noOps=result.noOps+1
 local value=changed(field)
 local spec=domain.validate_patch(request(field.currentDefault,value,true))
 plan=resolve(domain,spec);part=plan.changes[1]
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==1 and applied.bytes_written==width
  and applied.non_target_bytes_unchanged,label..' write failed: '..tostring(applied.reason))
 assert(runtime.read(part.owner.base+part.offset,width)==part.desired,label..' read-back failed')
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED'and runtime.read(part.owner.base+part.offset,width)==part.before,label..' rollback failed')
 result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
 poke(part.owner.base+part.offset,foreign(field))
 rejects(function()resolve(domain,spec)end,'CONFLICT',label..' conflict')
 result.conflictRejections=result.conflictRejections+1
 reset()
 if field.acknowledgement=='allow_unverified_effect'then
  rejects(function()domain.validate_patch(request(field.currentDefault,value,nil))end,'allow_unverified_effect',
   label..' without acknowledgement')
  result.acknowledgementRejections=result.acknowledgementRejections+1
 end
 rejects(function()domain.validate_patch(request(stale(field),value,true))end,'expect differs',label..' stale expect')
 result.staleExpectRejections=result.staleExpectRejections+1
 if field.max then
  rejects(function()domain.validate_patch(request(field.currentDefault,field.max+1,true))end,'reviewed',
   label..' out of range')
  result.rangeRejections=result.rangeRejections+1
 end
 result.fields=result.fields+1
 result.byFamily[family]=(result.byFamily[family]or 0)+1
 result.checked[#result.checked+1]={family=family,owner=target.backpack or target.weapon,field=field.semanticFieldId,
  path=target.path,linked=target.linked,zone=target.zone,baseline=field.currentDefault,changedTo=value,
  component=part.identity.component,fieldOffset=part.field_offset,before=b.hex(part.before)}
end
local worker=coroutine.create(function()
 -- Backpacks: new fields, and every field of a linked entity (drone, barrier) or an equipment backpack.
 local names={};for name in pairs(entity_db.backpacks)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  local entry=entity_db.backpacks[name]
  for _,field in ipairs(entry.fields)do
   local t=field.target
   local target={resource='backpack',backpack=name,path=t.path,zone=t.zone,linked=t.linked}
   local new=NEW_BACKPACK[field.semanticFieldId]or t.linked~=nil
    or(field.semanticFieldId:find('^deposit%.')and entry.linked and entry.linked.drone)
    or name=='SH-51 Directional Shield'and t.path=='backpack'
    or name=='LIFT-860 Hover Pack'and field.semanticFieldId=='jump.vertical_launch_velocity'
   if new and field.editable then exercise('backpack',entity,target,field)
   elseif new then
    rejects(function()entity.validate_patch({id='ro',target=target,field=field.semanticFieldId,expect=field.currentDefault,
     value=field.currentDefault,allow_unverified_effect=true})end,'read-only',name..' '..field.semanticFieldId..' read-only')
    result.readOnlyRejections=result.readOnlyRejections+1
   end
  end
  -- Linked-entity links and linked zone identities.
  for linked,link in pairs(entry.linked or{})do
   local field
   for _,item in ipairs(entry.fields)do if item.target.linked==linked and item.target.path=='linked'and item.editable
    then field=item;break end end
   local target={resource='backpack',backpack=name,path='linked',linked=linked}
   local spec=entity.validate_patch({id='chain',target=target,field=field.semanticFieldId,expect=field.currentDefault,
    value=field.currentDefault,allow_unverified_effect=true})
   reset()
   local _,resolved=resolve(entity,spec)
   local via=resolved.catalog.record(resolved.candidate,link.via.component)
   reset();poke(via.owner.base+via.offset+link.via.offset,string.rep('\0',8))
   rejects(function()resolve(entity,spec)end,'no longer links the reviewed '..linked,name..' '..linked..' link')
   result.chainTamperRejections=result.chainTamperRejections+1
   for zone,info in pairs(link.zones or{})do
    local zfield
    for _,item in ipairs(entry.fields)do if item.target.linked==linked and item.target.zone==zone and item.editable
     then zfield=item;break end end
    local zspec=entity.validate_patch({id='zone',target={resource='backpack',backpack=name,path='damage_zone',
     linked=linked,zone=zone},field=zfield.semanticFieldId,expect=zfield.currentDefault,value=zfield.currentDefault,
     allow_unverified_effect=true})
    reset()
    local zplan,zres=resolve(entity,zspec)
    local record=zres.catalog.record(zres.linked[linked],zfield.backing.component)
    local guard=zfield.backing.guards[1]
    reset();poke(record.owner.base+record.offset+guard.offset,b.encode(123456789,'u32'))
    rejects(function()resolve(entity,zspec)end,'entity zone identity changed',name..' '..linked..' '..zone..' identity')
    result.chainTamperRejections=result.chainTamperRejections+1
   end
  end
 end
 -- Warp Pack injury entries are named by their native limb.
 local warp=entity_db.backpacks['LIFT-182 Warp Pack']
 for _,field in ipairs(warp.fields)do if field.semanticFieldId=='warp.head_injury_damage'then
  local target={resource='backpack',backpack='LIFT-182 Warp Pack',path='backpack'}
  local spec=entity.validate_patch({id='limb',target=target,field=field.semanticFieldId,expect=field.currentDefault,
   value=field.currentDefault,allow_unverified_effect=true})
  reset()
  local _,resolved=resolve(entity,spec)
  local record=resolved.catalog.record(resolved.candidate,'DisplacementComponentData')
  reset();poke(record.owner.base+record.offset+field.backing.guards[1].offset,b.encode(1,'u32'))
  rejects(function()resolve(entity,spec)end,'entity zone identity changed','Warp Pack head injury limb')
  result.chainTamperRejections=result.chainTamperRejections+1
 end end
 -- Weapons: LAS-17 heat levels, LAS-98 beam fire rate, Maxigun recoil multipliers.
 for _,item in ipairs({{player_db,'player_weapon','LAS-17 Double-Edge Sickle'},{support_db,'support_weapon','LAS-98 Laser Cannon'},
   {support_db,'support_weapon','M-1000 Maxigun'}})do
  local weapon=item[1].weapons[item[3]]
  for _,field in ipairs(weapon.fields)do
   if NEW_WEAPON[field.semanticFieldId]then
    exercise(item[2],weapons,{resource=item[2],path='weapon',weapon=item[3]},field)
   end
  end
 end
 -- Guard Dog drone weapons: every weapon-local field, one shared attack row each, and the carrier chain.
 local keys={};for key,weapon in pairs(vehicle_db.weapons)do if weapon.carrier then keys[#keys+1]=key end end
 table.sort(keys)
 for _,key in ipairs(keys)do
  local weapon=vehicle_db.weapons[key]
  local shared_done=false
  for _,field in ipairs(weapon.fields)do
   local t=field.target
   -- (The drone gun's projectile reference is exercised by the vehicle weapon and projectile builder validators.)
   if field.editable and field.writeScope=='weapon_local'and field.type~='projectile_reference'then
    exercise('drone_weapon',weapons,{resource='vehicle_weapon',path='weapon',weapon=key},field)
   elseif field.editable and not shared_done and(field.semanticFieldId:find('^arc%.')or field.semanticFieldId:find('^beam%.')
     or field.semanticFieldId=='damage.primary.stagger')then
    shared_done=true
    exercise('drone_weapon',weapons,{resource='vehicle_weapon',path=t.path,weapon=key,attack=t.attack},field,
     {allow_shared=true})
   end
  end
  local chain=weapon.mountChain
  local first
  for _,field in ipairs(weapon.fields)do if field.writeScope=='weapon_local'and field.editable then first=field;break end end
  local spec=weapons.validate_patch({id='carrier',target={resource='vehicle_weapon',path='weapon',weapon=key},
   field=first.semanticFieldId,expect=first.currentDefault,value=first.currentDefault,allow_unverified_effect=true})
  reset()
  local _,resolved=resolve(weapons,spec)
  local catalog=resolved.catalog
  local function candidate(resource)for _,c in ipairs(catalog.candidates)do if c.resourceHash==resource then return c end end end
  local link=catalog.record(candidate(chain.carrier.backpackResource),'DepositComponentData')
  reset();poke(link.owner.base+link.offset+chain.carrier.link.offset,string.rep('\0',8))
  rejects(function()resolve(weapons,spec)end,'the backpack no longer deploys the reviewed drone',key..' carrier link')
  local mount=catalog.record(candidate(chain.vehicleResource),'MountComponentData')
  reset();poke(mount.owner.base+mount.offset+chain.slot*24,string.rep('\0',8))
  rejects(function()resolve(weapons,spec)end,'vehicle mount chain changed',key..' drone mount slot')
  result.chainTamperRejections=result.chainTamperRejections+2
  reset()
 end
 source.close()
 return result
end)
local ok,out
repeat ok,out=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,out);return json.encode(out)
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
    print(json.dumps({k: v for k, v in result.items() if k != 'checked'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
