"""Exercise attack-output composition through the production player-weapon write domain on the retained snapshot.

On a copy-on-write memory overlay of the snapshot (no game process, no real writes). Byte round trips prove the guarded
write mechanics only: whether a host's firing path reads the written member comes from its active projectile source
(research/active-projectile-sources-F5FEE03DCFDB.json, checked against the live controls), which every scenario
asserts first.

- Reprimand (live PASS control, ACTIVE_DIRECT): the Talon projectile through attack.projectile, exactly as the live
  mod wrote it; its ProjectileWeapon +0 changes and the guarded inverse restores it.
- Liberator (live FAIL control, INDIRECT): attack.projectile is refused as DORMANT_PROJECTILE_REFERENCE. Its active
  source is the RIFLE 5,5x50mm. FULL METAL JACKET ammunition delta: Vanilla is an already-desired no-op there; the
  Talon (same class), EAT-700 napalm rocket and GL-52 arc grenade (cross-class) land in the ammunition delta data
  while the dormant ProjectileWeapon +0 stays untouched, each with its package as the asset dependency, and each
  rolls back exactly. After a swap, edits to the Liberator's projectile follow the active source
  (COMPOSITION_TARGET_CHANGED); a plain patch meeting another output is a CONFLICT.
- Rejections: beam and arc outputs (INCOMPATIBLE_OUTPUT_FAMILY), missing allow_shared / allow_unverified_reference /
  allow_unverified_effect, an ammunition target on a weapon without one (NO_AMMUNITION_SOURCE), the wrong expect
  handle, a weapon whose default customization no longer names the ammunition (AMMUNITION_SOURCE_CHANGED), a stale
  output source and a host whose magazine pattern starts selecting other projectiles.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources  # noqa: E402
import validate_attachment_authoring_snapshot as overlay_source  # noqa: E402

OUTPUT = ROOT / 'validation/attack-output-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local weapons=require('hd2runtime/domains/player_weapon_writes')
local outputs=require('hd2runtime/domains/attack_outputs')
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
local function attack(name)return {resource='player_weapon',path='attack',weapon=name,attack='primary'}end
local function projectile(name)return {resource='player_weapon',path='projectile_reference',weapon=name,attack='primary'}end
local function output(name)return {resource='attack_output',output=outputs.aliases[name]}end
local HOST,CONTROL='AR-23 Liberator','SMG-32 Reprimand'
local ammo={resource='player_weapon',path='ammunition',weapon=HOST}
local ammo_projectile={resource='player_weapon',path='ammunition_projectile',weapon=HOST}
local function ammo_patch(value,extra)
 local request={id='attack-output',target=ammo,field='ammunition.projectile',expect=ammo_projectile,value=value,
  allow_shared=true,allow_unverified_reference=true,allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return weapons.validate_patch(request)
end
local function u32_at(record)return b.u32(runtime.read(record.owner.base+record.offset,4),0)end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 proofScope='guarded write mechanics; the host firing path is the active projectile source, not these bytes',
 controls={},compositions={},rejections={}}
local worker=coroutine.create(function()
 -- The live controls' active sources.
 local direct,indirect=outputs.sources[CONTROL].primary,outputs.sources[HOST].primary
 assert(direct.status=='ACTIVE_DIRECT'and direct.mechanism=='component','Reprimand is no longer ACTIVE_DIRECT')
 assert(indirect.status=='INDIRECT'and indirect.mechanism=='ammunition','Liberator is no longer INDIRECT')
 assert(outputs.hosts[CONTROL].mechanism=='component'and outputs.hosts[HOST].mechanism=='ammunition',
  'host mechanisms changed')
 local ammo_source=outputs.ammunition[HOST]

 -- Reprimand -> Talon (the live PASS operation): its own member is the fired projectile.
 local spec=weapons.validate_patch({id='reprimand-talon',target=attack(CONTROL),field='attack.projectile',
  expect=projectile(CONTROL),value=projectile('LAS-58 Talon')})
 local plan,resolved=resolve(spec)
 local part=plan.changes[1]
 local base=resolved.catalog.record(resolved.candidate,'ProjectileWeaponComponentData')
 assert(part.owner.base+part.offset==base.owner.base+base.offset,'Reprimand write is not its ProjectileWeapon +0')
 local before=part.before
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,'Reprimand write failed')
 assert(u32_at(base)==144,'Reprimand did not receive the Talon projectile')
 assert(guarded.apply(runtime,guarded.inverse(plan)).status=='APPLIED'and runtime.read(base.owner.base+base.offset,4)
  ==before,'Reprimand rollback did not restore its projectile')
 result.controls[CONTROL]={status=direct.status,mechanism=direct.mechanism,written='ProjectileWeapon +0',
  from=b.u32(before,0),to=144,live='PASS'}
 reset()

 -- Liberator: the dormant member is not writable, whatever the value.
 for _,value in ipairs({projectile('LAS-58 Talon'),output('EAT-700 Expendable Napalm')})do
  rejects(function()weapons.validate_patch({id='x',target=attack(HOST),field='attack.projectile',expect=projectile(HOST),
   value=value,allow_unverified_reference=true,allow_unverified_effect=true})end,'DORMANT_PROJECTILE_REFERENCE',
   'Liberator attack.projectile')
 end
 result.rejections.dormantMember='DORMANT_PROJECTILE_REFERENCE'

 -- Liberator Vanilla: its ammunition projectile is already the live one.
 local plan=resolve(ammo_patch(ammo_projectile,{allow_unverified_reference=false}))
 local part=plan.changes[1]
 assert(#plan.changes==1 and part.already_desired and b.u32(part.before,0)==ammo_source.currentDefault.projectileType,
  'Liberator ammunition is not the live baseline')
 assert(part.offset==ammo_source.dataOffset and part.packed==true,'ammunition write is not the reviewed delta data')
 local baseline=part.before
 result.controls[HOST]={status=indirect.status,mechanism=indirect.mechanism,ammunition=ammo_source.item,
  written='ammunition delta data (ProjectileWeapon +0 patch)',baseline=b.u32(baseline,0),live='FAIL on the dormant member'}

 -- Every Liberator choice lands in the ammunition delta; the dormant base member never moves.
 for _,choice in ipairs({{'LAS-58 Talon',projectile('LAS-58 Talon'),144},
   {'EAT-700 Expendable Napalm',output('EAT-700 Expendable Napalm')},{'GL-52 De-Escalator',output('GL-52 De-Escalator')}})do
  reset()
  local name,value=choice[1],choice[2]
  local expected=choice[3]or outputs.outputs[outputs.aliases[name]].currentDefault
  local spec=ammo_patch(value)
  local plan,resolved=resolve(spec)
  local part=plan.changes[1]
  local base=resolved.catalog.record(resolved.candidate,'ProjectileWeaponComponentData')
  local dormant=runtime.read(base.owner.base+base.offset,4)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,name..' write failed')
  assert(b.u32(runtime.read(part.owner.base+part.offset,4),0)==expected,name..' did not land in the ammunition delta')
  assert(runtime.read(base.owner.base+base.offset,4)==dormant,name..' touched the dormant ProjectileWeapon +0')
  -- The Liberator's projectile object now resolves through its new active projectile.
  rejects(function()resolve(weapons.validate_patch({id='x',target=projectile(HOST),field='damage.status_1_type',
   expect='none',value='fire',allow_shared=true}))end,'COMPOSITION_TARGET_CHANGED',name..' projectile follow')
  local other=name=='EAT-700 Expendable Napalm'and'GL-52 De-Escalator'or'EAT-700 Expendable Napalm'
  rejects(function()resolve(ammo_patch(output(other)))end,'CONFLICT',name..' ownership conflict')
  assert(guarded.apply(runtime,guarded.inverse(plan)).status=='APPLIED',name..' rollback failed')
  assert(runtime.read(part.owner.base+part.offset,4)==baseline,name..' rollback did not restore the ammunition')
  local dependency=spec.asset_dependencies and spec.asset_dependencies[1]
  result.compositions[name]={target='ammunition',projectile=expected,crossClass=spec.changes[1].cross_class==true,
   package=dependency and dependency.name or nil,writes=applied.writes,dormantMemberUnchanged=true}
 end
 reset()
 -- Before any swap the Liberator's projectile edits resolve through the ammunition delta (the same bullet).
 local plan=resolve(weapons.validate_patch({id='x',target=projectile(HOST),field='damage.status_1_type',
  expect='none',value='fire',allow_shared=true}))
 assert(#plan.changes==1,'Liberator projectile edit did not resolve')

 -- Rejections.
 for _,name in ipairs({'LAS-98 Laser Cannon','LAS-13 Trident','ARC-3 Arc Thrower'})do
  rejects(function()ammo_patch(output(name))end,'INCOMPATIBLE_OUTPUT_FAMILY',name)
  result.rejections[name]='INCOMPATIBLE_OUTPUT_FAMILY'
 end
 rejects(function()ammo_patch(output('EAT-700 Expendable Napalm'),{allow_unverified_reference=false})end,
  'allow_unverified_reference','cross-class reference acknowledgement')
 rejects(function()ammo_patch(projectile('LAS-58 Talon'),{allow_unverified_effect=false})end,
  'allow_unverified_effect','ammunition effect acknowledgement')
 rejects(function()ammo_patch(projectile('LAS-58 Talon'),{allow_shared=false})end,'allow_shared',
  'ammunition shared acknowledgement')
 result.rejections.acknowledgements=3
 rejects(function()weapons.validate_patch({id='x',target={resource='player_weapon',path='ammunition',weapon=CONTROL},
  field='ammunition.projectile',expect={resource='player_weapon',path='ammunition_projectile',weapon=CONTROL},
  value=projectile('LAS-58 Talon'),allow_shared=true,allow_unverified_effect=true})end,'NO_AMMUNITION_SOURCE',
  'Reprimand ammunition')
 rejects(function()weapons.validate_patch({id='x',target=ammo,field='ammunition.projectile',expect=projectile(HOST),
  value=projectile('LAS-58 Talon'),allow_shared=true,allow_unverified_effect=true})end,
  'expect must be the weapon ammunition','ammunition expect handle')
 result.rejections.noAmmunitionSource=CONTROL
 -- The weapon's default customization no longer naming its ammunition.
 local spec=ammo_patch(projectile('LAS-58 Talon'))
 local _,resolved=resolve(spec)
 local custom=resolved.catalog.record(resolved.candidate,'WeaponCustomizationComponentData')
 poke(custom.owner.base+custom.offset+ammo_source.defaultCustomization.offset+4,b.encode(0x12345678,'u32'))
 rejects(function()resolve(spec)end,'AMMUNITION_SOURCE_CHANGED','stale default ammunition')
 reset()
 -- Stale output source: the EAT-700's own reference no longer names the catalogued projectile.
 local spec=ammo_patch(output('EAT-700 Expendable Napalm'))
 local _,resolved=resolve(spec)
 local source_record=resolved.catalog.record(resolved.reference_sources[spec.changes[1].canonical_field],
  'ProjectileWeaponComponentData')
 poke(source_record.owner.base+source_record.offset,b.encode(276,'u32'))
 rejects(function()resolve(spec)end,'source projectile reference changed','stale output source')
 reset()
 -- Host proof: a magazine pattern entry would select other projectiles for some rounds.
 local _,resolved2=resolve(spec)
 local magazine=resolved2.catalog.record(resolved2.candidate,'WeaponMagazineComponentData')
 poke(magazine.owner.base+magazine.offset+4,b.encode(7,'u32'))
 rejects(function()resolve(spec)end,'CROSS_CLASS_HOST_REJECTED','host magazine pattern')
 result.rejections.staleDefaultAmmunition=1;result.rejections.staleSource=1;result.rejections.hostMagazinePattern=1
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
