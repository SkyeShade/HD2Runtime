"""Exercise every catalogued explosion (domains/explosion_catalogue.lua) through the production write path on the
retained snapshot, on a copy-on-write memory overlay (no game process).

For every catalogued explosion:

1. Identity: one transaction of every editable field at its reviewed value resolves through the live settings
   allocations (the explosion row by type, group, row and settings type; the DamageInfo row through the +4 link), every
   live value equals the catalogue, and the guarded core applies it as a no-op (ALREADY_DESIRED, zero writes).
2. A changed in-range inner radius (and, with a damage row, standard damage) applies through the guarded transaction
   core, reads back, is recognised as desired, and its guarded inverse restores the bytes and page protection.
3. A third-party value at the target is rejected as CONFLICT.

Once (EXTRAS): a changed row type (EXPLOSION_ROW_ABSENT), a changed damage link (CONFLICT), a different build
fingerprint; and the payloads: the R-36 Eruptor's terminal impact explosion re-pointed to catalogued explosions (a
stratagem call-in package donor and a mission-effects donor) and an attack output's impact-explosion slot, each applied,
read back and rolled back.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources  # noqa: E402
import parallel  # noqa: E402
import sharded_validation  # noqa: E402

OUTPUT = ROOT / 'validation/explosion-catalogue-snapshot.json'

PROGRAM = r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local b=require('hd2runtime/core/bytes')
local domain=require('hd2runtime/domains/explosion_writes')
local catalogue=require('hd2runtime/domains/explosion_catalogue')
local guarded=require('hd2runtime/core/guarded_transaction')
local fingerprint=require('hd2runtime/core/fingerprint')
local json=require('hd2runtime/primary_mapper/json')

local PAGE=4096
local overlay,protection={},{}
local runtime={mode='snapshot-overlay'}
local tamper={}
local counts={writes=0,protection_changes=0}
local function original_protect(at)return source.query(at).protect end
function runtime.module(name)return source.module(name)end
function runtime.address(handle)return source.address(handle)end
function runtime.system_info()return source.system_info()end
function runtime.module_hash(handle)
 if tamper.hash then return tamper.hash end
 return source.module_hash(handle)
end
function runtime.query(at)
 local r,why=source.query(at)
 if not r or r.allocation_base==0 then return r,why end
 local low,high=r.base,r.base+r.size
 if next(protection)==nil then return r end
 local pages={}
 for page in pairs(protection)do if page>=low and page<high then pages[#pages+1]=page end end
 if #pages==0 then return r end
 table.sort(pages)
 for _,page in ipairs(pages)do
  if at>=page and at<page+PAGE then r.base=page;r.size=PAGE;r.protect=protection[page];return r end
  if page>at then high=math.min(high,page)else low=math.max(low,page+PAGE)end
 end
 r.base=low;r.size=high-low;return r
end
function runtime.read(at,n)
 local bytes,why=source.read(at,n)
 if not bytes then return nil,why end
 for address,value in pairs(overlay)do
  if address<at+n and address+#value>at then
   local first=math.max(address,at);local last=math.min(address+#value,at+n)
   bytes=bytes:sub(1,first-at)..value:sub(first-address+1,last-address)..bytes:sub(last-at+1)
  end
 end
 return bytes
end
function runtime.protect(page,size,value)
 assert(page%PAGE==0 and size==PAGE,'overlay protect extent')
 counts.protection_changes=counts.protection_changes+1
 local old=protection[page] or original_protect(page)
 if value==original_protect(page)then protection[page]=nil else protection[page]=value end
 return old
end
function runtime.write(at,bytes)
 assert((protection[at-at%PAGE] or original_protect(at-at%PAGE))==4,'overlay write without writable page')
 counts.writes=counts.writes+1;overlay[at]=bytes
 return true,nil,#bytes
end
local function poke(at,bytes)overlay[at]=bytes end
local function reset()overlay={};protection={};tamper={};fingerprint.reset()end

local function resolve(spec,module)
 local d=module or domain
 local reader=Reader.new(runtime)
 local resolved=d.capture(runtime,reader,spec)
 local plan=d.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
 return true
end
local function target(id)return {resource='explosion',explosion=id}end
local function changed(field)
 local v=field.currentDefault;local range=field.range
 local candidate=field.type=='integer'and v+1 or(v==0 and 0.5 or v*1.25)
 if candidate>range.max then candidate=field.type=='integer'and v-1 or(v+range.min)/2 end
 if field.backing.storage=='f32'then candidate=math.floor(candidate*1024+0.5)/1024 end
 assert(candidate~=v,'no distinct in-range value')
 return candidate
end
-- One full write cycle of one field: apply, read back, desired again, inverse, protection restored, conflict.
local function cycle(id,field_id,result)
 local entry=catalogue.explosions[id]
 local field=domain.descriptor(entry,id,field_id)
 local value=changed(field)
 local spec=domain.validate_patch({id='explosion-check',target=target(id),field=field_id,expect=field.currentDefault,
  value=value,allow_shared=true,allow_unverified_effect=true})
 reset()
 local plan=resolve(spec);local change=plan.changes[1]
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==1 and applied.protection_restored
  and applied.non_target_bytes_unchanged,'explosion write failed: '..id..' '..field_id..' '..tostring(applied.reason))
 assert(runtime.read(change.owner.base+change.offset,4)==change.desired,'explosion write did not land: '..id)
 local again=resolve(spec)
 assert(again.changes[1].already_desired,'changed value is not recognised as desired: '..id..' '..field_id)
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED'and runtime.read(change.owner.base+change.offset,4)==change.before,
  'explosion rollback failed: '..id..' '..field_id)
 for _ in pairs(protection)do error('page protection not restored for '..id)end
 result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
 poke(change.owner.base+change.offset,b.encode(field.backing.storage=='f32'and 777.25 or 7777,field.backing.storage))
 rejects(function()resolve(spec)end,'CONFLICT','conflict '..id)
 result.conflictRejections=result.conflictRejections+1
 reset()
end

local result={status='VALIDATED',explosions=0,identityProofs=0,fieldsProven=0,changedWrites=0,rollbacks=0,
 conflictRejections=0,proofRejections={},payloadWrites=0,payloadRollbacks=0,byFamily={},writes=0,protectionChanges=0,
 fixtureFallback='disabled',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME}
local worker=coroutine.create(function()
 local ids=shard(catalogue.order)
 for _,id in ipairs(ids)do
  local entry=catalogue.explosions[id]
  -- 1. identity: every editable field at its reviewed value, one no-op transaction.
  local changes={}
  for _,field in ipairs(catalogue.fields)do
   local descriptor=domain.descriptor(entry,id,field.id)
   if descriptor.editable then
    changes[#changes+1]={field=field.id,expect=descriptor.currentDefault,value=descriptor.currentDefault}
   end
  end
  reset()
  local spec=domain.validate_transaction({id='explosion-identity',target=target(id),changes=changes,allow_shared=true,
   allow_unverified_effect=true})
  local plan=resolve(spec)
  for index,change in ipairs(plan.changes)do
   assert(change.before==spec.changes[index].expected,'live value differs from the catalogue: '..id..' '
    ..change.label)
  end
  local checked=guarded.apply(runtime,plan)
  assert(checked.status=='ALREADY_DESIRED'and checked.writes==0 and checked.protection_changes==0,
   'identity no-op changed state: '..id)
  result.identityProofs=result.identityProofs+1;result.fieldsProven=result.fieldsProven+#plan.changes
  -- 2./3. a changed radius, and a changed standard damage where the row links one.
  cycle(id,'explosion.inner_radius',result)
  if entry.damage then cycle(id,'explosion.damage.standard_damage',result)end
  result.explosions=result.explosions+1
  result.byFamily[entry.family]=(result.byFamily[entry.family]or 0)+1
 end
 if EXTRAS then
  local function record(kind)result.proofRejections[kind]=(result.proofRejections[kind]or 0)+1 end
  local id='weapon/cb9_exploding_crossbow/impact'
  local entry=catalogue.explosions[id]
  local field=domain.descriptor(entry,id,'explosion.damage.standard_damage')
  local spec=domain.validate_patch({id='explosion-proof',target=target(id),field=field.semanticFieldId,
   expect=field.currentDefault,value=field.currentDefault,allow_unverified_effect=true})
  reset()
  local _,resolved=resolve(spec)
  local row=resolved.roots.explosion.records[entry.type]
  poke(resolved.roots.explosion.owner.base+row.offset+4,b.encode(entry.damage.type+1,'u32'))
  rejects(function()resolve(spec)end,'CONFLICT','changed damage link')
  record('damageLink')
  reset()
  _,resolved=resolve(spec)
  row=resolved.roots.explosion.records[entry.type]
  poke(resolved.roots.explosion.owner.base+row.offset,b.encode(423,'u32'))
  rejects(function()resolve(spec)end,'EXPLOSION_ROW_ABSENT','changed row type')
  record('rowType')
  reset()
  tamper.hash=string.rep('0',64)
  rejects(function()resolve(spec)end,'unsupported build fingerprint','wrong build')
  record('wrongBuild')
  reset()
  -- Payloads: the R-36 Eruptor's impact explosion re-pointed to catalogued explosions.
  local hd2=require('hd2runtime/api/hd2')
  local weapons=require('hd2runtime/domains/player_weapon_writes')
  local terminal=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile():terminal_action('impact')
  for _,donor in ipairs({'stratagem/orbital_gas_strike/shell_impact','weapon/plas15_loyalist/impact'})do
   local donor_entry=catalogue.explosions[donor]
   local wspec=weapons.validate_patch({id='payload-check',target=terminal,field='terminal.explosion',
    expect=terminal:explosion(),value=hd2.explosion(donor),allow_unverified_reference=true,
    allow_unverified_effect=true,allow_shared=true})
   reset()
   local wplan=resolve(wspec,weapons)
   local change=wplan.changes[1]
   assert(b.u32(change.desired,0)==donor_entry.type,'payload desired type')
   local applied=guarded.apply(runtime,wplan)
   assert(applied.status=='APPLIED'and applied.writes==1,'payload write failed: '..donor..' '..tostring(applied.reason))
   assert(runtime.read(change.owner.base+change.offset,4)==change.desired,'payload write did not land')
   local restored=guarded.apply(runtime,guarded.inverse(wplan))
   assert(restored.status=='APPLIED'and runtime.read(change.owner.base+change.offset,4)==change.before,
    'payload rollback failed')
   result.payloadWrites=result.payloadWrites+1;result.payloadRollbacks=result.payloadRollbacks+1
   -- The donor row is re-proven: a changed donor row type refuses.
   reset()
   local _,wresolved=resolve(wspec,weapons)
   local drow=wresolved.roots.explosion.records[donor_entry.type]
   poke(wresolved.roots.explosion.owner.base+drow.offset,b.encode(423,'u32'))
   rejects(function()resolve(wspec,weapons)end,'EXPLOSION_ROW_ABSENT','changed donor row')
   record('donorRow')
   reset()
  end
  -- An attack output's impact explosion slot.
  local outputs=require('hd2runtime/domains/output_writes')
  local base=hd2.attack_output('LAS-58 Talon')
  local ospec=outputs.validate_patch({id='slot-check',target=base,field='projectile.impact_explosion',expect='none',
   value=hd2.explosion('stratagem/orbital_gas_strike/shell_impact'),allow_unverified_effect=true,allow_shared=true,
   allow_unverified_reference=true})
  reset()
  local oplan=resolve(ospec,outputs)
  local ochange=oplan.changes[1]
  local applied=guarded.apply(runtime,oplan)
  assert(applied.status=='APPLIED'and applied.writes==1,'slot write failed: '..tostring(applied.reason))
  assert(runtime.read(ochange.owner.base+ochange.offset,4)==ochange.desired,'slot write did not land')
  local restored=guarded.apply(runtime,guarded.inverse(oplan))
  assert(restored.status=='APPLIED','slot rollback failed')
  result.payloadWrites=result.payloadWrites+1;result.payloadRollbacks=result.payloadRollbacks+1
  reset()
 end
 result.writes=counts.writes;result.protectionChanges=counts.protection_changes
 source.close()
 return result
end)
local ok,out
repeat ok,out=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,out);return json.encode(out)
'''


def validate(snapshot, jobs=None):
    """Explosions are independent (every check starts from a reset overlay): split across parallel Lua states."""
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    head = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal SNAPSHOT_NAME='
        + lua(Path(snapshot).name) + '\n')
    return sharded_validation.run(head, PROGRAM, jobs, extras=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parallel.add_argument(parser)
    args = parser.parse_args()
    parallel.configure(args.jobs)
    result = validate(args.snapshot, args.jobs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8', newline='') as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
