"""Resolve and exercise every magazine-attachment field through the production delta-chain proof.

For every reviewed field on a copy-on-write memory overlay of the retained snapshot (no game process):

1. The current value applies as a guarded no-op (ALREADY_DESIRED, zero writes).
2. A changed in-range value applies through the guarded transaction core, reads back at the delta data
   offset, leaves every other attachment's reviewed bytes untouched, and its guarded inverse restores it.
3. A third-party value at the target is rejected as CONFLICT.
4. Missing acknowledgements and out-of-range values are rejected before any memory access.
5. For the ergonomics modifier, a changed modifier type word is rejected by the live guard.

It also checks that one weapon's magazine options (AR-23 Liberator: Short, Extended, Drum) resolve to
three distinct delta records and can be edited independently in one pass.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources

OUTPUT = ROOT / 'validation/magazine-attachment-snapshot.json'

PROGRAM = r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local b=require('hd2runtime/core/bytes')
local domain=require('hd2runtime/domains/attachment_writes')
local database=require('hd2runtime/domains/attachment_authoring')
local guarded=require('hd2runtime/core/guarded_transaction')
local fingerprint=require('hd2runtime/core/fingerprint')
local json=require('hd2runtime/primary_mapper/json')

local PAGE=4096
local overlay,protection={},{}
local runtime={mode='snapshot-overlay'}
local counts={writes=0,protection_changes=0}
local function original_protect(at)return source.query(at).protect end
function runtime.module(name)return source.module(name)end
function runtime.address(handle)return source.address(handle)end
function runtime.system_info()return source.system_info()end
function runtime.module_hash(handle)return source.module_hash(handle)end
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
local function reset()overlay={};protection={};fingerprint.reset()end

local region
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 region=resolved.region
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan
end
local function request(id,field,expect,value,extra)
 local r={id='attachment-check',allow_shared=true,allow_unverified_effect=true,
  target={resource='weapon_attachment',attachment=id,path='magazine'},field=field,expect=expect,value=value}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return r
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local function changed(field)
 local v=field.currentDefault
 if field.storage=='u32'then return v+1 end
 local candidate=v+0.5
 if field.max and candidate>field.max then candidate=v-0.5 end
 return candidate
end

-- Every reviewed field location, to prove a write touches nothing else.
local ids={};for id in pairs(database.attachments)do ids[#ids+1]=id end;table.sort(ids)
local locations={}
for _,id in ipairs(ids)do
 local names={};for name in pairs(database.attachments[id].fields)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  locations[#locations+1]={id=id,field=name,descriptor=database.attachments[id].fields[name]}
 end
end

local result={status='VALIDATED',attachments=#ids,fieldChecks=0,alreadyDesired=0,changedWrites=0,rollbacks=0,
 isolationChecks=0,conflictRejections=0,acknowledgementRejections=0,rangeRejections=0,guardRejections=0,
 unalignedPackedFields=0,byField={},fixtureFallback='disabled',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME}
local worker=coroutine.create(function()
 reset()
 resolve(domain.validate_patch(request(locations[1].id,locations[1].field,
  locations[1].descriptor.currentDefault,locations[1].descriptor.currentDefault)))
 local baseline={}
 for index,location in ipairs(locations)do baseline[index]=source.read(region.base+location.descriptor.dataOffset,4)end
 for _,location in ipairs(locations)do
  local id,name,field=location.id,location.field,location.descriptor
  reset()
  -- 1. guarded no-op
  local plan=resolve(domain.validate_patch(request(id,name,field.currentDefault,field.currentDefault)))
  local checked=guarded.apply(runtime,plan)
  assert(checked.status=='ALREADY_DESIRED'and checked.writes==0 and checked.protection_changes==0,
   'attachment no-op changed state: '..field.instanceKey)
  result.fieldChecks=result.fieldChecks+1
  result.byField[name]=(result.byField[name]or 0)+1
  if plan.changes[1].already_desired then result.alreadyDesired=result.alreadyDesired+1 end
  if plan.changes[1].offset%4~=0 then result.unalignedPackedFields=result.unalignedPackedFields+1 end
  -- 2. changed value, read-back, isolation, guarded inverse
  local value=changed(field)
  local spec=domain.validate_patch(request(id,name,field.currentDefault,value))
  plan=resolve(spec)
  local change=plan.changes[1]
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.protection_restored
   and applied.non_target_bytes_unchanged,'attachment write failed: '..field.instanceKey..' '..tostring(applied.reason))
  assert(runtime.read(region.base+field.dataOffset,4)==change.desired,'attachment write did not land: '..field.instanceKey)
  for index,other in ipairs(locations)do
   if other~=location then
    assert(runtime.read(region.base+other.descriptor.dataOffset,4)==baseline[index],
     'writing '..field.instanceKey..' changed '..other.descriptor.instanceKey)
   end
  end
  result.isolationChecks=result.isolationChecks+1
  local again=resolve(domain.validate_patch(request(id,name,field.currentDefault,value)))
  assert(again.changes[1].already_desired,'changed value is not recognised as desired: '..field.instanceKey)
  local restored=guarded.apply(runtime,guarded.inverse(plan))
  assert(restored.status=='APPLIED'and runtime.read(region.base+field.dataOffset,4)==change.before,
   'attachment rollback failed: '..field.instanceKey)
  for page in pairs(protection)do error('page protection not restored for '..field.instanceKey)end
  result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
  -- 3. third-party value
  poke(region.base+field.dataOffset,b.encode(field.storage=='u32'and field.currentDefault+7 or field.currentDefault+7.25,
   field.storage))
  rejects(function()resolve(spec)end,'CONFLICT','conflict')
  result.conflictRejections=result.conflictRejections+1
  -- 5. stat modifier type guard
  if field.guard then
   reset()
   poke(region.base+field.guard.dataOffset,b.encode(1,'u32'))
   rejects(function()resolve(spec)end,'no longer Add_Ergonomics','changed modifier type')
   result.guardRejections=result.guardRejections+1
  end
  reset()
  -- 4. acknowledgements and range, before any memory access
  rejects(function()domain.validate_patch(request(id,name,field.currentDefault,value,{allow_unverified_effect=false}))end,
   'allow_unverified_effect','missing effect acknowledgement')
  rejects(function()domain.validate_patch(request(id,name,field.currentDefault,value,{allow_shared=false}))end,
   'allow_shared','missing shared acknowledgement')
  result.acknowledgementRejections=result.acknowledgementRejections+2
  if field.max then
   rejects(function()domain.validate_patch(request(id,name,field.currentDefault,field.max+1))end,'maximum','range')
   rejects(function()domain.validate_patch(request(id,name,field.currentDefault,field.min-1))end,'minimum','range')
   result.rangeRejections=result.rangeRejections+2
  end
 end
 -- One weapon, several magazine definitions: distinct records, independent edits.
 local liberator=database.weapons['AR-23 Liberator']
 local options={}
 for _,option in ipairs(liberator.options)do
  if option.name and option.attachment then options[#options+1]=option end
 end
 assert(#options==3,'AR-23 Liberator no longer resolves three catalog magazine options')
 reset()
 local specs,seen={}, {}
 for index,option in ipairs(options)do
  local entry=database.attachments[option.attachment]
  assert(not seen[entry.settingsIndex],'two options share one delta record');seen[entry.settingsIndex]=true
  local capacity=entry.fields['attachment.magazine_capacity']
  specs[index]={spec=domain.validate_patch(request(option.attachment,'attachment.magazine_capacity',
   capacity.currentDefault,capacity.currentDefault+index)),field=capacity}
 end
 for _,item in ipairs(specs)do
  local applied=guarded.apply(runtime,resolve(item.spec))
  assert(applied.status=='APPLIED'and applied.writes==1,'Liberator option write failed')
 end
 for index,item in ipairs(specs)do
  assert(b.u32(runtime.read(region.base+item.field.dataOffset,4),0)==item.field.currentDefault+index,
   'Liberator option edits interfered')
 end
 result.multiVariant={weapon='AR-23 Liberator',options=#specs,distinctRecords=#specs,independentEdits=true}
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
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
