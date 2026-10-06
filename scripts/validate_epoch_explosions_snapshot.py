"""Exercise the charge-level shot and overcharge explosion fields (scripts/charge_fields.py,
research/charge-explosions-F5FEE03DCFDB.json) on a copy-on-write overlay of the retained snapshot.

For every field of every charge-level role (PLAS-45 Epoch: primary, primary_impact, full_charge, full_charge_impact,
overcharge_explosion; RS-422 Railgun: overcharge_explosion):

1. the live bytes equal the reviewed baseline, and a no-op applies as ALREADY_DESIRED with no write;
2. a changed value writes exactly the field (one write of the field width, every other byte of the row unchanged),
   reads back, restores the page protection, and the inverse plan restores the original bytes;
3. a third-party change of the field is rejected as CONFLICT;
4. a missing allow_unverified_effect (an operation outside any declared SDK), a missing allow_shared and a stale
   expect are rejected.

Plus the linkage through the weapon's own WeaponCharge record: each role resolves the row its charge level names
(the existing partial-charge rows are the same rows as before); a charge-level selector that no longer names the
reviewed row, or a swapped overcharge explosion (what charge.overcharge_explosion writes), refuses the write instead of
editing another row; the Epoch's full-charge impact explosion and overcharge explosion share one damage row (a write
through one is seen by the other); and the live-test values of examples/projects/EpochExplosionsTest apply.

  py scripts/validate_epoch_explosions_snapshot.py   # writes validation/epoch-explosions-snapshot.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources
from reference_format import lua as lua_table
import validate_attachment_authoring_snapshot as overlay_source

OUTPUT = ROOT / 'validation/epoch-explosions-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]
ROLES = {'PLAS-45 Epoch': ['primary', 'primary_impact', 'full_charge', 'full_charge_impact', 'overcharge_explosion'],
    'RS-422 Railgun': ['overcharge_explosion']}
# The live test's values (examples/projects/EpochExplosionsTest, every option): (weapon, role, target path, public field,
# expect, value).
LIVE_TEST = [
    ['PLAS-45 Epoch', 'overcharge_explosion', 'explosion', 'explosion.damage.standard_damage', 800, 1],
    ['PLAS-45 Epoch', 'overcharge_explosion', 'explosion', 'explosion.damage.durable_damage', 800, 1],
    ['PLAS-45 Epoch', 'overcharge_explosion', 'explosion', 'explosion.damage.push_force', 30, 0],
    ['PLAS-45 Epoch', 'overcharge_explosion', 'explosion', 'explosion.inner_radius', 3, 15],
    ['PLAS-45 Epoch', 'overcharge_explosion', 'explosion', 'explosion.outer_radius', 4, 18],
    ['PLAS-45 Epoch', 'overcharge_explosion', 'explosion', 'explosion.shockwave_radius', 5, 20],
    ['PLAS-45 Epoch', 'primary_impact', 'explosion', 'explosion.inner_radius', 2.299999952316284, 9.2],
    ['PLAS-45 Epoch', 'primary_impact', 'explosion', 'explosion.outer_radius', 3, 12],
    ['PLAS-45 Epoch', 'primary_impact', 'explosion', 'explosion.shockwave_radius', 4, 16],
    ['PLAS-45 Epoch', 'full_charge_impact', 'explosion', 'explosion.inner_radius', 3, 9],
    ['PLAS-45 Epoch', 'full_charge_impact', 'explosion', 'explosion.outer_radius', 4, 12],
    ['PLAS-45 Epoch', 'full_charge_impact', 'explosion', 'explosion.shockwave_radius', 5, 15],
    ['PLAS-45 Epoch', 'full_charge', 'projectile_reference', 'projectile.velocity', 250, 60],
    ['RS-422 Railgun', 'overcharge_explosion', 'explosion', 'explosion.damage.standard_damage', 300, 1],
    ['RS-422 Railgun', 'overcharge_explosion', 'explosion', 'explosion.damage.durable_damage', 300, 1],
    ['RS-422 Railgun', 'overcharge_explosion', 'explosion', 'explosion.damage.push_force', 40, 0],
]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local weapons=require('hd2runtime/domains/player_weapon_writes')
local support_db=require('hd2runtime/domains/support_weapon_authoring')
local ROLES=''' + lua_table(ROLES) + r'''
local LIVE_TEST=''' + lua_table(LIVE_TEST) + r'''
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=weapons.capture(runtime,reader,spec)
 local plan=weapons.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 fields=0,baselineMatches=0,noOps=0,changedWrites=0,isolatedWrites=0,protectionRestored=0,rollbacks=0,
 conflictRejections=0,acknowledgementRejections=0,sharedRejections=0,staleExpectRejections=0,
 selectorRefusals=0,overchargeSwapRefusals=0,sharedRowProofs=0,liveTestWrites=0,byRole={},rows={},checked={}}
-- The public id of a role-qualified field (explosion.overcharge_explosion.inner_radius -> explosion.inner_radius).
local function public(id)return(id:gsub('^(%a+)%.[^.]+%.','%1.',1))end
local function target_of(name,field)
 return {resource='support_weapon',path=field.target.path,weapon=name,attack=field.target.attack}
end
local function changed(field)
 if field.type=='status_reference'then
  for _,value in ipairs(field.allowedValues)do if value~=field.currentDefault then return value end end
 end
 if field.backing.storage=='f32'then return field.currentDefault+0.5 end
 return field.currentDefault+1
end
local function foreign(field)
 if field.type=='status_reference'then return b.encode(99999,'u32')end
 return b.encode(field.currentDefault+3,field.backing.storage)
end
local function request(name,field,expect,value,opts)
 local r={id='epoch-explosions',target=target_of(name,field),field=public(field.semanticFieldId),expect=expect,
  value=value,allow_shared=true,allow_unverified_effect=true}
 for k,v in pairs(opts or{})do if v==false then r[k]=nil else r[k]=v end end
 return r
end
local function exercise(name,field)
 local label=name..' '..field.semanticFieldId
 reset()
 local plan=resolve(weapons.validate_patch(request(name,field,field.currentDefault,field.currentDefault)))
 local part=plan.changes[1];local width=field.backing.width
 assert(#part.before==width,label..' width')
 result.baselineMatches=result.baselineMatches+1
 local checked=guarded.apply(runtime,plan)
 assert(checked.status=='ALREADY_DESIRED'and checked.writes==0 and checked.protection_changes==0,label..' no-op')
 result.noOps=result.noOps+1
 local value=changed(field)
 local spec=weapons.validate_patch(request(name,field,field.currentDefault,value))
 plan=resolve(spec);part=plan.changes[1]
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
 rejects(function()resolve(spec)end,'CONFLICT',label..' conflict')
 result.conflictRejections=result.conflictRejections+1
 reset()
 rejects(function()weapons.validate_patch(request(name,field,field.currentDefault,value,
  {allow_unverified_effect=false}))end,'allow_unverified_effect',label..' without acknowledgement')
 result.acknowledgementRejections=result.acknowledgementRejections+1
 rejects(function()weapons.validate_patch(request(name,field,field.currentDefault,value,{allow_shared=false}))end,
  'allow_shared',label..' without allow_shared')
 result.sharedRejections=result.sharedRejections+1
 local stale=field.type=='status_reference'and value or(field.currentDefault+1)
 rejects(function()weapons.validate_patch(request(name,field,stale,value))end,'expect differs',label..' stale expect')
 result.staleExpectRejections=result.staleExpectRejections+1
 result.fields=result.fields+1
 local role=field.target.attack
 result.byRole[name..'/'..role]=(result.byRole[name..'/'..role]or 0)+1
 local row=field.backing.settings..':'..field.backing.row
 result.rows[name..'/'..role..'/'..field.backing.settings]=field.backing.row
 result.checked[#result.checked+1]={weapon=name,field=field.semanticFieldId,role=role,baseline=field.currentDefault,
  changedTo=value,settings=field.backing.settings,row=field.backing.row,recordType=field.backing.recordType,
  linkage=field.backing.linkage,fieldOffset=part.field_offset,width=width,before=b.hex(part.before),
  desired=b.hex(part.desired)}
 return part
end
local function field_of(name,qualified)
 for _,field in ipairs(support_db.weapons[name].fields)do if field.semanticFieldId==qualified then return field end end
 error('no field '..qualified..' on '..name)
end
local function charge_address(name)
 -- The weapon's own WeaponCharge record, through a charge field's resolved component record.
 local field=field_of(name,'charge.level_1')
 reset()
 local plan=resolve(weapons.validate_patch({id='charge-record',target={resource='support_weapon',path='weapon',
  weapon=name},field='charge.level_1',expect=field.currentDefault,value=field.currentDefault}))
 local part=plan.changes[1]
 return part.owner.base+part.offset-part.field_offset
end
local worker=coroutine.create(function()
 local parts={}
 for name,roles in pairs(ROLES)do
  local wanted={};for _,role in ipairs(roles)do wanted[role]=true end
  for _,field in ipairs(support_db.weapons[name].fields)do
   if field.backing.kind=='settings'and wanted[field.target.attack]then
    parts[name..'/'..field.semanticFieldId]=exercise(name,field)
   end
  end
 end
 -- The partial-charge rows are the same rows as before 0.30.0 (ProjectileWeapon +0 and the partial selector agree).
 local epoch_charge=charge_address('PLAS-45 Epoch')
 assert(b.u32(runtime.read(epoch_charge+4,4),0)==field_of('PLAS-45 Epoch','projectile.primary.velocity').backing.recordType,
  'the partial-charge selector no longer names the reviewed row')
 -- A charge-level selector that no longer names the reviewed row refuses the write (never another row).
 local full=field_of('PLAS-45 Epoch','explosion.full_charge_impact.outer_radius')
 local full_spec=weapons.validate_patch(request('PLAS-45 Epoch',full,full.currentDefault,12))
 local partial_type=field_of('PLAS-45 Epoch','projectile.primary.velocity').backing.recordType
 reset();poke(epoch_charge+28,b.encode(partial_type,'u32'))
 rejects(function()resolve(full_spec)end,'no longer fire one projectile','full-charge selectors disagree')
 reset();poke(epoch_charge+28,b.encode(partial_type,'u32'));poke(epoch_charge+52,b.encode(partial_type,'u32'))
 rejects(function()resolve(full_spec)end,'record identity changed','full-charge selectors name another row')
 local partial=field_of('PLAS-45 Epoch','damage.primary.standard_damage')
 local partial_spec=weapons.validate_patch(request('PLAS-45 Epoch',partial,partial.currentDefault,600))
 reset();poke(epoch_charge+4,b.encode(field_of('PLAS-45 Epoch','projectile.full_charge.velocity').backing.recordType,
  'u32'))
 rejects(function()resolve(partial_spec)end,'record identity changed','partial selector names another row')
 reset();poke(epoch_charge+4,b.encode(0,'u32'))
 rejects(function()resolve(partial_spec)end,'selector absent','partial selector cleared')
 result.selectorRefusals=4
 -- A swapped overcharge explosion (charge.overcharge_explosion) refuses the contents write.
 for name,donor in pairs({['PLAS-45 Epoch']='RS-422 Railgun',['RS-422 Railgun']='PLAS-45 Epoch'})do
  local reference=field_of(name,'charge.overcharge_explosion')
  local other=reference.explosionOptions[donor].explosionType
  local radius=field_of(name,'explosion.overcharge_explosion.outer_radius')
  local damage=field_of(name,'explosion.overcharge_explosion.damage.standard_damage')
  local address=charge_address(name)
  for _,field in ipairs({radius,damage})do
   local spec=weapons.validate_patch(request(name,field,field.currentDefault,field.currentDefault+1))
   reset();poke(address+200,b.encode(other,'u32'))
   rejects(function()resolve(spec)end,'record identity changed',name..' swapped overcharge explosion '..field.semanticFieldId)
   result.overchargeSwapRefusals=result.overchargeSwapRefusals+1
  end
 end
 reset()
 -- The Epoch full-charge impact explosion and the overcharge explosion name one damage row.
 for _,suffix in ipairs({'standard_damage','durable_damage','push_force'})do
  local impact=field_of('PLAS-45 Epoch','explosion.full_charge_impact.damage.'..suffix)
  local over=field_of('PLAS-45 Epoch','explosion.overcharge_explosion.damage.'..suffix)
  local a=parts['PLAS-45 Epoch/'..impact.semanticFieldId];local c=parts['PLAS-45 Epoch/'..over.semanticFieldId]
  assert(a.owner.base+a.offset==c.owner.base+c.offset,'the two explosions no longer share '..suffix)
  reset()
  local plan=resolve(weapons.validate_patch(request('PLAS-45 Epoch',over,over.currentDefault,1)))
  assert(guarded.apply(runtime,plan).status=='APPLIED','shared damage write')
  rejects(function()resolve(weapons.validate_patch(request('PLAS-45 Epoch',impact,impact.currentDefault,
   impact.currentDefault+5)))end,'CONFLICT','full-charge impact after an overcharge damage write')
  result.sharedRowProofs=result.sharedRowProofs+1
 end
 reset()
 -- The live test's values: each one applies as one isolated write.
 for _,item in ipairs(LIVE_TEST)do
  local name,role,path,id,expect,value=item[1],item[2],item[3],item[4],item[5],item[6]
  local spec=weapons.validate_patch({id='live-test',target={resource='support_weapon',path=path,weapon=name,
   attack=role},field=id,expect=expect,value=value,allow_shared=true,allow_unverified_effect=true})
  reset()
  local applied=guarded.apply(runtime,resolve(spec))
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,
   name..' '..role..' '..id..' live-test value: '..tostring(applied.reason))
  result.liveTestWrites=result.liveTestWrites+1
 end
 reset()
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
