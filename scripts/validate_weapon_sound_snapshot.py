"""Exercise the weapon firing-sound field (weapon.sound; docs/weapon-sounds.md) on a copy-on-write overlay of the
retained snapshot. Offline only: nothing here is live-tested.

For each player and support weapon whose weapon.sound is writable:

1. Restoring its own catalogued sound (expect = value = its own name) needs no acknowledgement and is a guarded
   ALREADY_DESIRED no-op: the reviewed baseline (+252..+263 and the +237 MIDI flag) is exactly the snapshot's record.
2. Another sound without allow_unverified_effect is refused.

Pinned writes (exact bytes, read back, then rolled back exactly):

- MG-43 Machine Gun (a MIDI shot) taking support/mg206 (a MIDI shot): only +260 changes;
- MG-43 Machine Gun taking sentry/gatling (a loop): +252/+256 the loop's start/stop, +260 = 0, +237 1 -> 0;
- GL-15 Evictor (a plain shot) taking vehicle/maelstrom/main_gun (a MIDI shot): +260 and +237 0 -> 1;
- M-1000 Maxigun (a loop) taking support/mg206: the loop cleared, +260 the event, +237 0 -> 1.

And: a third-party per-shot event or MIDI flag is a CONFLICT; an ensure-owned earlier sound (change.owned) is a
transition back to the weapon's own sound; every write's spec names its sound bank's package (asset_dependencies), and
the asset gate refuses a runtime that cannot request packages (no write); resident-only and unknown sounds, a wrong
expect and refused weapons (fire mode 4/7, suppressed, no ProjectileWeapon record) are rejected.
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

OUTPUT = ROOT / 'validation/weapon-sound-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local domain=require('hd2runtime/domains/player_weapon_writes')
local players=require('hd2runtime/domains/player_weapon_authoring')
local supports=require('hd2runtime/domains/support_weapon_authoring')
local sounds=require('hd2runtime/runtime/weapon_sounds')
local assets=require('hd2runtime/core/assets')
local SOUND='weapon.sound'
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local function field_of(weapon)
 for _,item in ipairs(weapon.fields or{})do if item.semanticFieldId==SOUND then return item end end
end
local result={status='VALIDATED',checked={player=0,support=0},noops=0,acknowledgementRejections=0,
 conflictRejections=0,adversarialRejections=0,rollbacks=0,pins={},fixtureFallback='disabled',mode='snapshot-overlay',
 snapshot=SNAPSHOT_NAME}
local function patch(kind,name,expect,value,extra)
 local request={id='weapon-sound-check',target={resource=kind,path='weapon',weapon=name},field=SOUND,expect=expect,
  value=value,allow_unverified_effect=true}
 for key,item in pairs(extra or{})do request[key]=item end
 if request.allow_unverified_effect==false then request.allow_unverified_effect=nil end
 return domain.validate_patch(request)
end
-- The bytes a plan's parts hold now: the +252..+263 block and the +237 flag, by field offset.
local function bytes_of(plan)
 local out={}
 for _,part in ipairs(plan.changes)do
  out['+'..part.field_offset]=b.hex(runtime.read(part.owner.base+part.offset,#part.desired))
 end
 return out
end
local function before_of(plan)
 local out={}
 for _,part in ipairs(plan.changes)do out['+'..part.field_offset]=b.hex(part.before)end
 return out
end
-- Apply, read back the exact bytes, roll back and verify the originals.
local function write_and_restore(spec,label)
 local plan=resolve(spec)
 local changed=0
 for _,part in ipairs(plan.changes)do if part.before~=part.desired then changed=changed+1 end end
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==changed and applied.non_target_bytes_unchanged,
  label..' write failed: '..tostring(applied.reason))
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.desired)==part.desired,label..' write did not land')
 end
 local after=bytes_of(plan)
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED',label..' rollback failed')
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,label..' rollback did not restore')
 end
 result.rollbacks=result.rollbacks+1
 return plan,after,changed
end
local worker=coroutine.create(function()
 for _,set in ipairs({{kind='player_weapon',key='player',db=players},{kind='support_weapon',key='support',db=supports}})do
  local names={};for name in pairs(set.db.weapons)do names[#names+1]=name end;table.sort(names)
  for _,name in ipairs(names)do
   local weapon=set.db.weapons[name]
   local field=field_of(weapon)
   if field and field.editable and not weapon.ordinaryWritesBlocked then
    reset()
    local own=field.currentDefault
    -- 1. Its own sound: no acknowledgement, a guarded no-op on the snapshot's own record.
    local spec=patch(set.kind,name,own,own,{allow_unverified_effect=false})
    assert(#spec.asset_dependencies==0,name..' own sound declared a package')
    local plan=resolve(spec)
    assert(#plan.changes==4,name..' sound plan has '..#plan.changes..' parts')
    local checked=guarded.apply(runtime,plan)
    assert(checked.status=='ALREADY_DESIRED'and checked.writes==0,name..' own sound is not the snapshot record')
    result.noops=result.noops+1
    -- 2. Another sound needs the acknowledgement.
    local other=own=='sentry/gatling'and'support/mg206'or'sentry/gatling'
    rejects(function()patch(set.kind,name,own,other,{allow_unverified_effect=false})end,'allow_unverified_effect',
     name..' acknowledgement')
    result.acknowledgementRejections=result.acknowledgementRejections+1
    result.checked[set.key]=result.checked[set.key]+1
   end
  end
 end
 -- Pinned writes.
 local function pin(kind,name,own,value,label)
  reset()
  local spec=patch(kind,name,own,value)
  local plan,after,changed=write_and_restore(spec,label)
  local deps={}
  for index,dependency in ipairs(spec.asset_dependencies)do deps[index]=dependency.name end
  local entry=select(2,sounds.resolve(value))
  result.pins[label]={weapon=name,from=own,to=value,kind=entry.kind,before=before_of(plan),after=after,
   changedParts=changed,packages=deps,stratagem=entry.stratagem,record=plan.changes[1].identity.record_index}
  return spec,plan
 end
 local mg43_spec,mg43_plan=pin('support_weapon','MG-43 Machine Gun','support/mg43','support/mg206','mg43_mg206')
 local loop_spec,loop_plan=pin('support_weapon','MG-43 Machine Gun','support/mg43','sentry/gatling','mg43_gatling')
 pin('player_weapon','GL-15 Evictor','primary/gl15','vehicle/maelstrom/main_gun','gl15_maelstrom')
 pin('support_weapon','M-1000 Maxigun','support/m1000','support/mg206','maxigun_mg206')
 -- A third-party per-shot event, or a third-party MIDI flag, is a CONFLICT.
 reset()
 local event_part,midi_part
 for _,part in ipairs(mg43_plan.changes)do
  if part.field_offset==260 then event_part=part end
  if part.field_offset==237 then midi_part=part end
 end
 poke(event_part.owner.base+event_part.offset,b.encode(0x12345678,'u32'))
 rejects(function()resolve(mg43_spec)end,'CONFLICT','third-party event')
 reset()
 poke(midi_part.owner.base+midi_part.offset,string.char(0))
 rejects(function()resolve(mg43_spec)end,'CONFLICT','third-party MIDI flag')
 result.conflictRejections=result.conflictRejections+2
 reset()
 -- An option-bound ensure owns the sound it applied: moving back to the weapon's own sound is a transition.
 local applied=guarded.apply(runtime,resolve(loop_spec))
 assert(applied.status=='APPLIED')
 local back=patch('support_weapon','MG-43 Machine Gun','support/mg43','support/mg43',{allow_unverified_effect=false})
 rejects(function()resolve(back)end,'CONFLICT','restore over an unowned sound')
 back.changes[1].owned=loop_spec.changes[1].desired
 local transition=guarded.apply(runtime,resolve(back))
 assert(transition.status=='APPLIED','owned transition failed: '..tostring(transition.reason))
 for _,part in ipairs(loop_plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,'transition did not restore the record')
 end
 result.ownedTransition=true
 reset()
 -- The asset gate: the loop names the Gatling Sentry's call-in package; a runtime that cannot request packages is
 -- refused before any write, and the weapon's own sound needs no package.
 local gate=assets.gate({mode='snapshot-overlay'},loop_spec,nil)
 assert(gate.state=='waiting'and#gate.dependencies==#loop_spec.asset_dependencies)
 local state,reason=gate.tick(1)
 assert(state=='failed'and tostring(reason):find('ASSET_UNAVAILABLE',1,true),'asset gate did not refuse: '
  ..tostring(state))
 assert(assets.gate({mode='snapshot-overlay'},back,nil).state=='ready')
 result.assetGate={dependencies=#loop_spec.asset_dependencies,refused=reason:match('^[^:]+')}
 -- Refusals.
 rejects(function()patch('support_weapon','MG-43 Machine Gun','support/mg43','primary/ar23')end,
  'RESIDENT_ONLY_SOUND','resident-only sound')
 rejects(function()patch('support_weapon','MG-43 Machine Gun','support/mg43','pelican/chin_autocannon')end,
  'RESIDENT_ONLY_SOUND','the Pelican chin sound')
 rejects(function()patch('support_weapon','MG-43 Machine Gun','support/mg43','sentry/nothing')end,'UNKNOWN_SOUND',
  'unknown sound')
 rejects(function()patch('support_weapon','MG-43 Machine Gun','support/mg206','sentry/gatling')end,
  'expect differs','wrong expect')
 rejects(function()patch('support_weapon','MG-43 Machine Gun','support/mg43',7)end,'catalogued sound name',
  'raw id value')
 rejects(function()patch('support_weapon','MGX-42 Bullet Storm','support/mgx42','sentry/gatling')end,
  'Fire mode 4 / 7','fire mode 4/7')
 rejects(function()patch('player_weapon','AR-59 Suppressor','primary/ar59','sentry/gatling')end,'suppressed',
  'suppressed weapon')
 rejects(function()patch('support_weapon','FLAM-40 Flamethrower','support/flam40','sentry/gatling')end,
  'no ProjectileWeapon record','no ProjectileWeapon record')
 rejects(function()patch('player_weapon','SG-20 Halt','primary/sg20','sentry/gatling')end,'event-override',
  'event-override table')
 result.adversarialRejections=9
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
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
