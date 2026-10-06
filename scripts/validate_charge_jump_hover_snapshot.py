"""Exercise the charge fields (scripts/charge_fields.py) and the jump / hover movement fields
(scripts/jump_hover_fields.py) on a copy-on-write snapshot overlay of the retained snapshot.

For every new or renamed field on every weapon or pack that offers it:

1. the live bytes equal the reviewed baseline, and a no-op applies as ALREADY_DESIRED with no write;
2. a changed value writes exactly the field (one write of the field width, every other byte of the record unchanged),
   reads back, restores the page protection, and the inverse plan restores the original bytes;
3. a third-party change of the field is rejected as CONFLICT;
4. a missing allow_unverified_effect, a stale expect, an out-of-range value, a non-finite number and (for flags) a
   non-boolean are rejected.

Plus: the deprecated charge ids write exactly the bytes of their canonical ids (same record, offset and value) and emit
their deprecation notice once; on arc and beam weapons they stay writable with a dormant notice; the three charge
times are meant to stay minimum < full < overcharge (a lone write that breaks the order is accepted, writes exactly its
field and logs one "CHARGE ORDER" notice; the same values written together apply without one); the overcharge explosion of another weapon needs allow_unverified_reference, declares that weapon's package
and writes its explosion type; an explosion whose package is unknown is refused.

  py scripts/validate_charge_jump_hover_snapshot.py   # writes validation/charge-jump-hover-snapshot.json
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

OUTPUT = ROOT / 'validation/charge-jump-hover-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]
CHARGE_WEAPONS = ('RS-422 Railgun', 'PLAS-45 Epoch', 'ARC-3 Arc Thrower', '40-K Meltagun')
PACKS = ('LIFT-850 Jump Pack', 'LIFT-860 Hover Pack')

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local entity=require('hd2runtime/domains/entity_writes')
local weapons=require('hd2runtime/domains/player_weapon_writes')
local entity_db=require('hd2runtime/domains/entity_authoring')
local support_db=require('hd2runtime/domains/support_weapon_authoring')
local notices=require('hd2runtime/core/field_notices')
local CHARGE_WEAPONS={''' + ','.join(lua(name) for name in CHARGE_WEAPONS) + r'''}
local PACKS={''' + ','.join(lua(name) for name in PACKS) + r'''}
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
 fields=0,baselineMatches=0,noOps=0,changedWrites=0,isolatedWrites=0,protectionRestored=0,rollbacks=0,
 conflictRejections=0,acknowledgementRejections=0,staleExpectRejections=0,rangeRejections=0,nonFiniteRejections=0,
 booleanRejections=0,aliasEquivalences=0,deprecationNotices=0,dormantNotices=0,chargeOrderNotices=0,
 chargeOrderTransactions=0,referenceSwaps=0,referenceRejections=0,byFamily={},checked={}}
-- A value inside the reviewed range that differs from the baseline (and, for charge times, keeps their order).
local function times_of(weapon)
 local t={};for _,f in ipairs(weapon.fields)do if f.chargeTime then t[f.backing.offset]=f.currentDefault end end
 return t
end
local function changed(field,weapon)
 if field.type=='boolean'then return not field.currentDefault end
 if field.type=='overcharge_explosion_reference'then
  for _,name in ipairs(field.allowedValues)do if name~=field.currentDefault then return name end end
 end
 local v=field.currentDefault
 if field.chargeTime then
  local t=times_of(weapon)
  if field.backing.offset==0 then return t[0]*0.5 end
  if field.backing.offset==24 then return (t[24]+t[48])/2 end
  return t[48]+1
 end
 local value=v+1
 if field.type=='integer'then value=math.floor(value)end
 if field.max and value>field.max then value=((field.min or 0)+v)/2 end
 assert(value~=v and(not field.min or value>=field.min)and(not field.max or value<=field.max),'no changed value')
 return value
end
local function stale(field)
 if field.type=='boolean'then return not field.currentDefault end
 if field.type=='overcharge_explosion_reference'then return changed(field)end
 return field.currentDefault+1
end
local function foreign(field)
 if field.backing.storage=='u8'then return string.char(7)end
 if field.type=='overcharge_explosion_reference'then return b.encode(99,'u32')end
 return b.encode(field.currentDefault+3,field.backing.storage)
end
-- One field: baseline, no-op, changed write (isolated, protection restored) and rollback, conflict, rejections.
local function exercise(family,domain,target,field,weapon)
 local label=family..' '..(target.backpack or target.weapon)..' '..field.semanticFieldId
 local reference=field.type=='overcharge_explosion_reference'
 local function request(expect,value,ack)
  return {id='charge-hover',target=target,field=field.semanticFieldId,expect=expect,value=value,
   allow_unverified_effect=ack or nil,allow_unverified_reference=reference or nil}
 end
 reset()
 local plan,resolved=resolve(domain,domain.validate_patch(request(field.currentDefault,field.currentDefault,true)))
 local part=plan.changes[1]
 local width=field.backing.width
 assert(#part.before==width,label..' width')
 result.baselineMatches=result.baselineMatches+1
 local checked=guarded.apply(runtime,plan)
 assert(checked.status=='ALREADY_DESIRED'and checked.writes==0 and checked.protection_changes==0,label..' no-op')
 result.noOps=result.noOps+1
 local value=changed(field,weapon)
 local spec=domain.validate_patch(request(field.currentDefault,value,true))
 plan=resolve(domain,spec);part=plan.changes[1]
 local base=part.owner.base+part.offset-part.field_offset
 local record_before=runtime.read(base,part.field_offset+width+64)
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==1 and applied.bytes_written==width
  and applied.non_target_bytes_unchanged,label..' write failed: '..tostring(applied.reason))
 assert(applied.protection_restored,label..' page protection not restored')
 for _ in pairs(protection)do error(label..' overlay page protection left changed')end
 result.protectionRestored=result.protectionRestored+1
 local record_after=runtime.read(base,part.field_offset+width+64)
 assert(record_after:sub(1,part.field_offset)==record_before:sub(1,part.field_offset)
  and record_after:sub(part.field_offset+width+1)==record_before:sub(part.field_offset+width+1),
  label..' changed a byte outside the field')
 assert(record_after:sub(part.field_offset+1,part.field_offset+width)==part.desired,label..' read-back failed')
 result.isolatedWrites=result.isolatedWrites+1
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED'and runtime.read(part.owner.base+part.offset,width)==part.before
  and restored.protection_restored,label..' rollback failed')
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
 if field.max and not field.legacyContract then
  rejects(function()domain.validate_patch(request(field.currentDefault,field.max+1,true))end,'reviewed',
   label..' above range')
  rejects(function()domain.validate_patch(request(field.currentDefault,field.min-1,true))end,'reviewed',
   label..' below range')
  result.rangeRejections=result.rangeRejections+2
 end
 if field.type=='boolean'then
  rejects(function()domain.validate_patch(request(field.currentDefault,1,true))end,'must be boolean',label..' number')
  result.booleanRejections=result.booleanRejections+1
 elseif not reference then
  rejects(function()domain.validate_patch(request(field.currentDefault,0/0,true))end,'finite',label..' NaN')
  rejects(function()domain.validate_patch(request(field.currentDefault,1/0,true))end,'finite',label..' infinity')
  result.nonFiniteRejections=result.nonFiniteRejections+2
 end
 result.fields=result.fields+1
 result.byFamily[family]=(result.byFamily[family]or 0)+1
 result.checked[#result.checked+1]={family=family,owner=target.backpack or target.weapon,field=field.semanticFieldId,
  baseline=field.currentDefault,changedTo=value,component=part.identity.component,fieldOffset=part.field_offset,
  width=width,before=b.hex(part.before),desired=b.hex(part.desired)}
 return part
end
local LEGACY={['charge.minimum_seconds']='charge.speed_multiplier_min',
 ['charge.maximum_seconds']='charge.speed_multiplier_overcharge'}
local worker=coroutine.create(function()
 -- Charge fields on every charge support weapon.
 for _,name in ipairs(CHARGE_WEAPONS)do
  local weapon=support_db.weapons[name]
  local target={resource='support_weapon',path='weapon',weapon=name}
  local parts={}
  for _,field in ipairs(weapon.fields)do
   if field.backing.component=='WeaponChargeComponentData'then
    parts[field.semanticFieldId]={field=field,part=exercise('charge',weapons,target,field,weapon)}
   end
  end
  -- A deprecated id writes exactly its canonical id's bytes (or, on arc and beam weapons, stays a dormant write), and
  -- its notice is emitted once.
  local legacy_ids={};for legacy in pairs(LEGACY)do legacy_ids[#legacy_ids+1]=legacy end;table.sort(legacy_ids)
  for _,legacy in ipairs(legacy_ids)do
   local canonical=LEGACY[legacy]
   local old=assert(parts[legacy],name..' lost '..legacy)
   local field=old.field
   local value=field.currentDefault+0.25
   notices.reset()
   local legacy_spec=weapons.validate_patch({id='legacy',target=target,field=legacy,expect=field.currentDefault,
    value=value})
   local lines=notices.warn(legacy_spec,'patch','ChargeValidation',nil)
   assert(lines[1]and lines[1]:find('DEPRECATED',1,true)and lines[1]:find('speed multiplier',1,true),
    name..' '..legacy..' deprecation notice: '..table.concat(lines,' | '))
   assert(#notices.warn(legacy_spec,'patch','ChargeValidation',nil)==0,name..' '..legacy..' notice repeated')
   result.deprecationNotices=result.deprecationNotices+1
   -- The legacy contract: no acknowledgement and no range on the deprecated id.
   weapons.validate_patch({id='legacy-wide',target=target,field=legacy,expect=field.currentDefault,value=25})
   if field.dormant then
    assert(#lines==2 and lines[2]:find('DORMANT',1,true),name..' '..legacy..' dormant notice')
    assert(not parts[canonical],name..' offers '..canonical..' without a projectile')
    result.dormantNotices=result.dormantNotices+1
   else
    local new=assert(parts[canonical],name..' lost '..canonical)
    local canon_spec=weapons.validate_patch({id='canonical',target=target,field=canonical,
     expect=new.field.currentDefault,value=value,allow_unverified_effect=true})
    reset();local a=resolve(weapons,legacy_spec).changes[1]
    reset();local c=resolve(weapons,canon_spec).changes[1]
    assert(a.owner.base+a.offset==c.owner.base+c.offset and a.desired==c.desired and a.before==c.before
     and #a.desired==4,name..' '..legacy..' does not write the bytes of '..canonical)
    result.aliasEquivalences=result.aliasEquivalences+1
   end
  end
  -- Charge times: a lone write that breaks minimum < full < overcharge is accepted (the ids are older than the rule),
  -- writes exactly its field and carries one CHARGE ORDER notice; together the same values apply without one.
  local t=times_of(weapon)
  local lone=weapons.validate_patch({id='order',target=target,field='charge.level_2',expect=t[24],value=t[48]+1})
  notices.reset()
  local order_lines=notices.warn(lone,'patch','ChargeValidation',nil)
  assert(#order_lines==1 and order_lines[1]:find('CHARGE ORDER',1,true),name..' charge order notice: '
   ..table.concat(order_lines,' | '))
  assert(#notices.warn(lone,'patch','ChargeValidation',nil)==0,name..' charge order notice repeated')
  reset()
  local lone_plan=resolve(weapons,lone)
  local lone_applied=guarded.apply(runtime,lone_plan)
  assert(lone_applied.status=='APPLIED'and lone_applied.writes==1 and lone_applied.non_target_bytes_unchanged
   and lone_applied.protection_restored,name..' mis-ordered charge time not applied: '..tostring(lone_applied.reason))
  assert(guarded.apply(runtime,guarded.inverse(lone_plan)).status=='APPLIED',name..' mis-ordered charge time rollback')
  reset()
  result.chargeOrderNotices=result.chargeOrderNotices+1
  local spec=weapons.validate_transaction({id='order-ok',target=target,changes={
   {field='charge.level_2',expect=t[24],value=t[48]+1},{field='charge.level_3',expect=t[48],value=t[48]+2}}})
  assert(#notices.warn(spec,'transaction','ChargeValidation',nil)==0,name..' ordered times logged a notice')
  reset()
  local plan=resolve(weapons,spec)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==2 and applied.non_target_bytes_unchanged
   and applied.protection_restored,name..' ordered charge times failed: '..tostring(applied.reason))
  assert(guarded.apply(runtime,guarded.inverse(plan)).status=='APPLIED',name..' ordered charge times rollback')
  reset()
  result.chargeOrderTransactions=result.chargeOrderTransactions+1
  -- The overcharge explosion of another weapon: its package, its explosion type, the reference acknowledgement.
  local explosion=parts['charge.overcharge_explosion']
  if explosion then
   local field=explosion.field
   local donor=changed(field)
   local function swap(extra)
    local r={id='swap',target=target,field=field.semanticFieldId,expect=field.currentDefault,value=donor,
     allow_unverified_effect=true}
    for k,v in pairs(extra or{})do r[k]=v end
    return weapons.validate_patch(r)
   end
   rejects(function()swap()end,'allow_unverified_reference',name..' explosion swap without reference acknowledgement')
   local swapped=swap({allow_unverified_reference=true})
   assert(swapped.asset_dependencies[1]and swapped.asset_dependencies[1].key=='support_weapon/'..donor,
    name..' explosion swap does not load the donor package')
   reset()
   local swap_plan=resolve(weapons,swapped)
   assert(b.u32(swap_plan.changes[1].desired,0)==field.explosionOptions[donor].explosionType,
    name..' explosion swap writes the wrong explosion')
   local assets=require('hd2runtime/core/assets');local real=assets.dependency
   assets.dependency=function(key)if key==field.explosionOptions[donor].dependencyKey then return nil end
    return real(key)end
   local ok,why=pcall(swap,{allow_unverified_reference=true})
   assets.dependency=real
   assert(not ok and tostring(why):find('UNKNOWN_EXPLOSION_PACKAGE',1,true),name..' unknown package: '..tostring(why))
   rejects(function()swap({allow_unverified_reference=true,value='LAS-99 Quasar Cannon'})end,
    'no catalogued overcharge explosion',name..' uncatalogued explosion')
   result.referenceSwaps=result.referenceSwaps+1;result.referenceRejections=result.referenceRejections+3
  end
 end
 -- Jump and hover movement fields on both packs.
 for _,name in ipairs(PACKS)do
  local entry=entity_db.backpacks[name]
  local target={resource='backpack',backpack=name,path='backpack'}
  for _,field in ipairs(entry.fields)do
   local id=field.semanticFieldId
   if(id:find('^jump%.')or id:find('^hover%.'))and field.editable and field.target.path=='backpack'then
    exercise(name=='LIFT-850 Jump Pack'and'jump_pack'or'hover_pack',entity,target,field,nil)
   end
  end
 end
 -- The Hover Pack launch thrust write is dormant and says so once.
 notices.reset()
 local dormant=entity.validate_patch({id='hover-launch',target={resource='backpack',backpack='LIFT-860 Hover Pack',
  path='backpack'},field='jump.vertical_launch_velocity',expect=40,value=80,allow_unverified_effect=true})
 local lines=notices.warn(dormant,'patch','ChargeValidation',nil)
 assert(#lines==1 and lines[1]:find('DORMANT',1,true),'hover launch dormant notice')
 assert(#notices.warn(dormant,'patch','ChargeValidation',nil)==0,'hover launch notice repeated')
 result.dormantNotices=result.dormantNotices+1
 result.writes=counts.writes;result.protectionChanges=counts.protection_changes
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
