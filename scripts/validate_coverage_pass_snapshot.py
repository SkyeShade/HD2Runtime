"""Exercise the coverage-pass mappings through the production write domains on the retained snapshot.

On a copy-on-write memory overlay of the snapshot (no game process, no real writes):

Status slots (DamageInfo status references):
- attach Stun Medium (strength 2, the AR-32 Pacifier / SMG-72 Pummeler value) to the M-1000 Maxigun's bullets and
  Fire (strength 2, the AR-2 Coyote value) to the AR-23 Liberator's bullets: the type and strength land in the first
  empty slot, the inverse restores both, and the rest of the row is untouched;
- swap a used slot's status (Coyote fire -> stun_small), clear the last used slot (FLAM-40 fire_panic -> none);
- reject: a status no player-side attack applies, clearing a slot that is not the last used one, a missing
  allow_unverified_effect, a hole in the slot packing (slot 1 emptied by a third party) and a stale status catalog
  (the live row no longer carries the catalogued name).

Enemies and structures: every writable enemy field resolves as a guarded no-op against the live table; Charger main
health and head armor, the base fabricator's health and the Warrior's head health round-trip; a third-party value is a
CONFLICT; missing acknowledgement, out-of-range values, stale expects and sentinel zones are rejected.

Mine deployers: MD-6 salvos 6 -> 2 and MD-17 mines per salvo 3 -> 1 round-trip; increases (past the launch sockets)
and missing acknowledgements are rejected.
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

OUTPUT = ROOT / 'validation/coverage-pass-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local weapons=require('hd2runtime/domains/player_weapon_writes')
local status_catalog=require('hd2runtime/domains/status_catalog')
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
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 statusSlots={attached={},swapped={},cleared={},rejections={}}}
local function target(resource,weapon,path)
 return {resource=resource,path=path or'projectile_reference',weapon=weapon,attack='primary'}
end
local function transaction(t,changes,extra)
 local request={id='coverage-status',target=t,changes=changes,allow_shared=true,allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return weapons.validate_transaction(request)
end
-- Apply, read back, verify the untouched bytes of the row, and restore through the guarded inverse.
local function round_trip(spec,label)
 local plan=resolve(weapons,spec)
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.non_target_bytes_unchanged,label..' write failed: '..tostring(applied.reason))
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.desired)==part.desired,label..' write did not land')
 end
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED',label..' rollback failed')
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,label..' rollback did not restore')
 end
 return plan,applied
end
local worker=coroutine.create(function()
 local s=result.statusSlots
 -- Attachment into the first empty slot.
 for _,case in ipairs({
   {key='maxigun_stun',resource='support_weapon',weapon='M-1000 Maxigun',type='damage.status_1_type',
    strength='damage.status_1_strength',status='stun_medium',value=2},
   {key='liberator_fire',resource='player_weapon',weapon='AR-23 Liberator',type='damage.status_1_type',
    strength='damage.status_1_strength',status='fire',value=2}})do
  reset()
  local spec=transaction(target(case.resource,case.weapon),{
   {field=case.type,expect='none',value=case.status},{field=case.strength,expect=0,value=case.value}})
  local plan,applied=round_trip(spec,case.key)
  local type_part,strength_part=plan.changes[1],plan.changes[2]
  assert(b.u32(type_part.desired,0)==status_catalog.statuses[case.status].nativeType,case.key..' type encoding')
  assert(strength_part.offset==type_part.offset+4,case.key..' strength is not the slot companion')
  s.attached[case.key]={weapon=case.weapon,status=case.status,strength=case.value,writes=applied.writes,
   slot=1,before=b.hex(type_part.before..strength_part.before),after=b.hex(type_part.desired..strength_part.desired)}
  -- Projectile direct-hit rows are live-proven (schemas/live_evidence.json): the write needs no acknowledgement.
  transaction(target(case.resource,case.weapon),{{field=case.type,expect='none',value=case.status}},
   {allow_unverified_effect=false})
  s.liveProvenWithoutAcknowledgement=(s.liveProvenWithoutAcknowledgement or 0)+1
 end
 -- Rows outside the live-proven family (here a melee row) still need allow_unverified_effect.
 rejects(function()transaction({resource='player_weapon',path='weapon',weapon='CQC-5 Combat Hatchet'},
  {{field='damage.status_1_type',expect='none',value='fire'}},{allow_unverified_effect=false})end,
  'allow_unverified_effect','melee status acknowledgement')
 s.rejections.acknowledgement=1
 -- Swapping a used slot's status.
 reset()
 local coyote=target('player_weapon','AR-2 Coyote')
 local plan=round_trip(transaction(coyote,{{field='damage.status_1_type',expect='fire',value='stun_small'}}),'coyote swap')
 s.swapped.coyote={from='fire',to='stun_small',writes=#plan.changes}
 -- Clearing the last used slot; clearing an earlier one is rejected.
 reset()
 local flamer=target('support_weapon','FLAM-40 Flamethrower','attack')
 plan=round_trip(transaction(flamer,{{field='damage.status_3_type',expect='fire_panic',value='none'}}),'flamer clear')
 s.cleared.flamethrower={slot=3,from='fire_panic'}
 rejects(function()transaction(flamer,{{field='damage.status_1_type',expect='fire',value='none'}})end,
  'cannot be cleared','clearing a middle slot')
 s.rejections.middleSlotClear=1
 -- A status that is never attachable (schemas/status_attachment_policy.json neverAttachable; since 0.30.2 electric is
 -- an attachable other_system status, so it is no longer the example).
 rejects(function()transaction(coyote,{{field='damage.status_1_type',expect='fire',value='smoke_covered'}})end,
  'not attachable','smoke_covered')
 s.rejections.notAttachable=1
 -- A hole in the packing: a third party empties slot 1 before slot 2 is attached.
 reset()
 local spec=transaction(coyote,{{field='damage.status_2_type',expect='none',value='gas'}})
 local _,resolved=resolve(weapons,spec)
 local slot_field
 for _,field in ipairs(require('hd2runtime/domains/player_weapon_authoring').weapons['AR-2 Coyote'].fields)do
  if field.semanticFieldId=='damage.status_2_type'then slot_field=field end
 end
 local row=assert(resolved.roots.damage.records[slot_field.backing.recordType],'Coyote DamageInfo absent')
 poke(resolved.roots.damage.owner.base+row.offset+44,b.encode(0,'u32'))
 rejects(function()resolve(weapons,spec)end,'CONFLICT: status slot 1 is now empty','packing hole')
 s.rejections.packingHole=1
 reset()
 -- A stale catalog: the live row must still carry the catalogued name.
 local name=status_catalog.statuses.fire.name
 status_catalog.statuses.fire.name='Not Fire'
 local ok,why=pcall(function()resolve(weapons,transaction(coyote,{{field='damage.status_1_type',expect='fire',
  value='stun_small'}}))end)
 status_catalog.statuses.fire.name=name
 assert(not ok and tostring(why):find('status catalog is stale',1,true),'stale catalog accepted: '..tostring(why))
 s.rejections.staleCatalog=1
 reset()
 -- Enemies and structures: every published field resolves as a guarded no-op against the live table.
 local enemies=require('hd2runtime/domains/enemy_writes')
 local enemy_db=require('hd2runtime/domains/enemy_authoring')
 local e={classes=0,fields=0,readOnly=0,roundTrips={},rejections={}}
 result.enemies=e
 local names={};for name in pairs(enemy_db.enemies)do names[#names+1]=name end;table.sort(names)
 local specs={}
 for _,name in ipairs(names)do
  local entry=enemy_db.enemies[name];e.classes=e.classes+1
  local groups,order={},{}
  for _,field in ipairs(entry.fields)do
   if field.editable==false then e.readOnly=e.readOnly+1 else
    local key=field.path..':'..tostring(field.zone)..':'..tostring(field.attack)
    if not groups[key]then groups[key]={id='enemy-noop',target={resource='enemy',enemy=name,path=field.path,
     zone=field.zone,attack=field.attack},allow_shared=true,allow_unverified_effect=true,changes={}}
     order[#order+1]=key end
    if field.attack then e.attackFields=(e.attackFields or 0)+1 end
    local changes=groups[key].changes
    changes[#changes+1]={field=field.id,expect=field.currentDefault,value=field.currentDefault}
   end
  end
  for _,key in ipairs(order)do specs[#specs+1]=enemies.validate_transaction(groups[key])end
 end
 local reader=Reader.new(runtime)
 local resolved=enemies.capture_many(runtime,reader,specs)
 for index,spec in ipairs(specs)do
  local plan=enemies.prepare(resolved[index],reader,spec)
  for _,part in ipairs(plan.changes)do
   assert(part.already_desired,spec.enemy..' '..part.label..' live value differs from the reviewed baseline')
  end
  e.fields=e.fields+#spec.changes
 end
 reader.verify()
 -- Representative writes: the change lands, reads back and rolls back; conflicts and guards reject.
 local function enemy_round_trip(key,target,field,expect,value,extra)
  reset()
  local request={id='enemy-'..key,target=target,field=field,expect=expect,value=value}
  for k,v in pairs(extra or{})do request[k]=v end
  local spec=enemies.validate_patch(request)
  local plan=resolve(enemies,spec)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,key..' write failed')
  local part=plan.changes[1]
  assert(runtime.read(part.owner.base+part.offset,#part.desired)==part.desired,key..' write did not land')
  assert(guarded.apply(runtime,guarded.inverse(plan)).status=='APPLIED',key..' rollback failed')
  assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,key..' rollback did not restore')
  -- A third-party value at the target is a CONFLICT.
  poke(part.owner.base+part.offset,b.encode(expect+7,spec.changes[1].descriptor.backing.storage))
  rejects(function()resolve(enemies,spec)end,'CONFLICT',key..' conflict')
  reset()
  e.roundTrips[key]={field=field,from=expect,to=value}
 end
 local charger={resource='enemy',enemy='Charger',path='entity'}
 enemy_round_trip('charger_health',charger,'entity.health',2400,240)
 enemy_round_trip('charger_head_armor',{resource='enemy',enemy='Charger',path='damage_zone',zone='zone_0'},
  'zone.armor',4,1)
 local fabricator={resource='enemy',enemy='spawner_factory_conscript_base',path='entity'}
 enemy_round_trip('fabricator_health',fabricator,'entity.health',1500,150,{allow_unverified_effect=true})
 -- Structure health is offline-proven only (inconclusive live test): it needs allow_unverified_effect.
 rejects(function()enemies.validate_patch({id='x',target=fabricator,field='entity.health',expect=1500,value=150})end,
  'allow_unverified_effect','structure health acknowledgement')
 e.rejections.structureAcknowledgement=1
 enemy_round_trip('warrior_head_health',{resource='enemy',enemy='warrior_base',path='damage_zone',zone='zone_0'},
  'zone.health',enemy_db.enemies.warrior_base.fields[7].currentDefault,1)
 rejects(function()enemies.validate_patch({id='x',target=charger,field='entity.constitution',expect=750,value=0})end,
  'allow_unverified_effect','constitution acknowledgement');e.rejections.acknowledgement=1
 rejects(function()enemies.validate_patch({id='x',target=charger,field='entity.health',expect=2400,value=0})end,
  'reviewed range','health range');e.rejections.range=1
 rejects(function()enemies.validate_patch({id='x',target=charger,field='entity.health',expect=2000,value=10})end,
  'expect differs','stale expect');e.rejections.staleExpect=1
 local sentinel
 for _,field in ipairs(enemy_db.enemies.Charger.fields)do
  if field.id=='zone.health'and field.editable==false then sentinel=field end
 end
 rejects(function()enemies.validate_patch({id='x',target={resource='enemy',enemy='Charger',path='damage_zone',
  zone=sentinel.zone},field='zone.health',expect=-1,value=100})end,'read-only','uses-main-health zone')
 e.rejections.sentinel=1
 -- Attacks: shared DamageInfo rows reached through the class's own mount chain.
 local rockets={resource='enemy',enemy='Gunship',path='attack',attack='slot_0'}
 enemy_round_trip('gunship_rocket_damage',rockets,'damage.standard_damage',30,3,
  {allow_shared=true,allow_unverified_effect=true})
 enemy_round_trip('bile_bombard_explosion_damage',{resource='enemy',enemy='boomer',path='attack',
  attack='slot_1_impact'},'damage.standard_damage',200,20,{allow_shared=true,allow_unverified_effect=true})
 local function baseline(enemy,attack,field_id)
  for _,field in ipairs(enemy_db.enemies[enemy].fields)do
   if field.attack==attack and field.id==field_id then return field.currentDefault end
  end
 end
 local bombard_velocity=baseline('Rupture Spewer','slot_1_projectile','projectile.velocity')
 enemy_round_trip('bile_bombard_velocity',{resource='enemy',enemy='Rupture Spewer',path='attack',
  attack='slot_1_projectile'},'projectile.velocity',bombard_velocity,bombard_velocity/2,
  {allow_shared=true,allow_unverified_effect=true})
 local blast=baseline('Gunship','slot_0_impact_explosion','explosion.outer_radius')
 enemy_round_trip('gunship_rocket_blast_radius',{resource='enemy',enemy='Gunship',path='attack',
  attack='slot_0_impact_explosion'},'explosion.outer_radius',blast,blast*2,{allow_shared=true,allow_unverified_effect=true})
 rejects(function()enemies.validate_patch({id='x',target=rockets,allow_unverified_effect=true,
  field='damage.standard_damage',expect=30,value=3})end,'allow_shared','attack allow_shared')
 e.rejections.attackShared=1
 rejects(function()enemies.validate_patch({id='x',target=rockets,allow_shared=true,
  field='damage.standard_damage',expect=30,value=3})end,'allow_unverified_effect','attack acknowledgement')
 e.rejections.attackAcknowledgement=1
 -- A third party repointing the Gunship's mount slot breaks the chain: the write is refused before any byte moves.
 reset()
 local spec=enemies.validate_patch({id='chain',target=rockets,allow_shared=true,allow_unverified_effect=true,
  field='damage.standard_damage',expect=30,value=3})
 local _,resolved=resolve(enemies,spec)
 local mount=resolved.catalog.record(resolved.candidate,'MountComponentData')
 poke(mount.owner.base+mount.offset,string.rep('\0',8))
 rejects(function()resolve(enemies,spec)end,'no longer holds the reviewed weapon','broken mount chain')
 e.rejections.brokenMountChain=1
 reset()
 -- Player projectile penetration slowdown / lifetime: every published field resolves as a guarded no-op.
 local pp={fields=0,weapons=0}
 result.playerProjectileMembers=pp
 local player_specs={}
 local player_db=require('hd2runtime/domains/player_weapon_authoring').weapons
 local player_names={};for weapon_name in pairs(player_db)do player_names[#player_names+1]=weapon_name end
 table.sort(player_names)
 for _,weapon_name in ipairs(player_names)do
  local weapon=player_db[weapon_name];weapon.name=weapon.name or weapon_name
  local changes={}
  for _,field in ipairs(weapon.fields)do
   local id=field.semanticFieldId
   if field.editable and id:match('^projectile%.')and(id:match('%.penetration_slowdown$')or id:match('%.lifetime$'))then
    changes[#changes+1]={field=id,expect=field.currentDefault,value=field.currentDefault}
   end
  end
  if #changes>0 then
   player_specs[#player_specs+1]=transaction(target('player_weapon',weapon.name),changes)
   pp.weapons=pp.weapons+1;pp.fields=pp.fields+#changes
  end
 end
 for _,spec in ipairs(player_specs)do
  local plan=resolve(weapons,spec)
  for _,part in ipairs(plan.changes)do
   assert(part.already_desired,spec.weapon..' '..part.label..' live value differs from the reviewed baseline')
  end
 end
 -- A real change lands and rolls back (Liberator penetration slowdown 0.25 -> 0.5).
 reset()
 round_trip(transaction(target('player_weapon','AR-23 Liberator'),
  {{field='projectile.penetration_slowdown',expect=0.25,value=0.5}}),'liberator slowdown')
 pp.roundTrip={weapon='AR-23 Liberator',field='projectile.penetration_slowdown',from=0.25,to=0.5}
 reset()
 -- Mine deployer counts: a reduction lands and rolls back; an increase past the launch sockets is rejected.
 local stratagems=require('hd2runtime/domains/stratagem_writes')
 local m={roundTrips={},rejections={}}
 result.minefield=m
 for _,case in ipairs({{'MD-6 Anti-Personnel Minefield','minefield.salvos',6,2},
   {'MD-17 Anti-Tank Mines','minefield.mines_per_salvo',3,1}})do
  local mine={resource='stratagem',stratagem=case[1],path='minefield',entity='main'}
  local spec=stratagems.validate_patch({id='mine-count',target=mine,allow_unverified_effect=true,
   field=case[2],expect=case[3],value=case[4]})
  local plan=resolve(stratagems,spec)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,case[1]..' write failed')
  local part=plan.changes[1]
  assert(runtime.read(part.owner.base+part.offset,4)==b.encode(case[4],'u32'),case[1]..' write did not land')
  assert(guarded.apply(runtime,guarded.inverse(plan)).status=='APPLIED',case[1]..' rollback failed')
  assert(runtime.read(part.owner.base+part.offset,4)==b.encode(case[3],'u32'),case[1]..' rollback did not restore')
  m.roundTrips[case[1]]={field=case[2],from=case[3],to=case[4]}
  rejects(function()stratagems.validate_patch({id='x',target=mine,allow_unverified_effect=true,field=case[2],
   expect=case[3],value=case[3]+1})end,'range','increase')
  if case[2]=='minefield.salvos'then
   -- Live-proven (MinefieldSalvos): no acknowledgement needed.
   stratagems.validate_patch({id='x',target=mine,field=case[2],expect=case[3],value=case[4]})
   m.liveProvenWithoutAcknowledgement=case[2]
  else
   rejects(function()stratagems.validate_patch({id='x',target=mine,field=case[2],expect=case[3],value=case[4]})end,
    'allow_unverified_effect','acknowledgement')
  end
 end
 m.rejections={increase=2,acknowledgement=1}
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
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
