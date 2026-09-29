"""Exercise every throwable field through the production chain proofs on the retained snapshot.

For every reviewed writable field, on a copy-on-write memory overlay of the snapshot (no game process):

1. The live bytes equal the reviewed baseline, and the current value applies as a guarded no-op
   (ALREADY_DESIRED, zero writes).
2. A changed in-range value applies through the guarded transaction core. It reads back at the resolved
   address, is recognised as desired, and its guarded inverse restores the original bytes and page protection.
3. A third-party value at the target is rejected as CONFLICT.
4. The following are rejected before any memory access:
   - a stale expect;
   - missing allow_unverified_effect;
   - missing allow_shared (on shared fields);
   - out-of-range values on either side.

Read-only fields are rejected as read-only. Per target, the proofs must also reject:

- every changed link of the reviewed native chain;
- a changed component ownership (entity index row);
- a different build fingerprint.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources

OUTPUT = ROOT / 'validation/throwable-authoring-snapshot.json'

PROGRAM = r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local b=require('hd2runtime/core/bytes')
local domain=require('hd2runtime/domains/throwable_writes')
local database=require('hd2runtime/domains/throwable_authoring')
local guarded=require('hd2runtime/core/guarded_transaction')
local fingerprint=require('hd2runtime/core/fingerprint')
local json=require('hd2runtime/primary_mapper/json')

-- Copy-on-write overlay with page protections, as in the packaged-runtime validator.
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

local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved
end
local function target_of(name,owned)
 return {resource='throwable',throwable=name,path=owned.path,status=owned.key}
end
local function request(name,owned,field,expect,value,extra)
 local r={id='throwable-check',allow_shared=true,allow_unverified_effect=true,
  target=target_of(name,owned),field=field,expect=expect,value=value}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return r
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
 return true
end
-- A changed value that stays inside the reviewed range and storage.
local function changed(field)
 local v=field.currentDefault;local range=field.range
 local candidate=field.type=='integer'and v+1 or(v==0 and 0.5 or v*1.25)
 if candidate>range.max then candidate=field.type=='integer'and v-1 or (v+range.min)/2 end
 if candidate<range.min then candidate=range.min end
 if field.backing.storage=='f32'then candidate=math.floor(candidate*1024+0.5)/1024 end
 assert(candidate~=v,'no distinct in-range value for '..field.instanceKey)
 return candidate
end
local function f32(v)return b.value(b.encode(v,'f32'),0,'f32')end
local function link_address(resolved,link)
 if link.from=='component'then
  local record=resolved.catalog.record(resolved.candidate,link.component)
  return record.owner.base+record.offset+link.offset
 end
 local root=resolved.roots[link.settings];local record=root.records[link.recordType]
 return root.owner.base+record.offset+link.offset
end

local result={status='VALIDATED',throwables=0,targets=0,fieldChecks=0,readOnlyRejections=0,alreadyDesired=0,
 changedWrites=0,rollbacks=0,conflictRejections=0,staleExpectRejections=0,acknowledgementRejections=0,
 rangeRejections=0,proofRejections={},targetsByPath={},writes=0,protectionChanges=0,fixtureFallback='disabled',
 mode='snapshot-overlay',snapshot=SNAPSHOT_NAME}
local worker=coroutine.create(function()
 local names={};for name in pairs(database.throwables)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  local entry=database.throwables[name];local any=false
  local labels={};for label in pairs(entry.targets)do labels[#labels+1]=label end;table.sort(labels)
  for _,label in ipairs(labels)do
   local owned=entry.targets[label]
   local ids={};for id in pairs(owned.fields)do ids[#ids+1]=id end;table.sort(ids)
   local writable
   for _,id in ipairs(ids)do
    local field=owned.fields[id]
    reset()
    if not field.editable then
     rejects(function()domain.validate_patch(request(name,owned,id,field.currentDefault,field.currentDefault))end,
      'read-only','read-only field')
     result.readOnlyRejections=result.readOnlyRejections+1
    else
     writable=writable or id
     -- 1. reviewed baseline and guarded no-op
     local plan=resolve(domain.validate_patch(request(name,owned,id,field.currentDefault,field.currentDefault)))
     assert(plan.changes[1].before==b.encode(field.currentDefault,field.backing.storage),
      'live bytes differ from the reviewed baseline: '..field.instanceKey)
     local checked=guarded.apply(runtime,plan)
     assert(checked.status=='ALREADY_DESIRED'and checked.writes==0 and checked.protection_changes==0,
      'throwable no-op changed state: '..field.instanceKey)
     result.fieldChecks=result.fieldChecks+1
     if plan.changes[1].already_desired then result.alreadyDesired=result.alreadyDesired+1 end
     -- 2. changed value, read-back, guarded inverse
     local value=changed(field)
     local spec=domain.validate_patch(request(name,owned,id,field.currentDefault,value))
     plan=resolve(spec)
     local change=plan.changes[1]
     local applied=guarded.apply(runtime,plan)
     assert(applied.status=='APPLIED'and applied.writes==1 and applied.protection_restored
      and applied.non_target_bytes_unchanged,'throwable write failed: '..field.instanceKey..' '..tostring(applied.reason))
     assert(runtime.read(change.owner.base+change.offset,field.backing.width)==change.desired,
      'throwable write did not land: '..field.instanceKey)
     local again=resolve(domain.validate_patch(request(name,owned,id,field.currentDefault,value)))
     assert(again.changes[1].already_desired,'changed value is not recognised as desired: '..field.instanceKey)
     local restored=guarded.apply(runtime,guarded.inverse(plan))
     assert(restored.status=='APPLIED'
      and runtime.read(change.owner.base+change.offset,field.backing.width)==change.before,
      'throwable rollback failed: '..field.instanceKey)
     for _ in pairs(protection)do error('page protection not restored for '..field.instanceKey)end
     result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
     -- 3. third-party value at the target
     local third=field.backing.storage=='f32'and b.encode(f32(field.currentDefault)+7,'f32')
      or b.encode(field.currentDefault+7,field.backing.storage)
     poke(change.owner.base+change.offset,third)
     rejects(function()resolve(spec)end,'CONFLICT','conflict')
     result.conflictRejections=result.conflictRejections+1
     reset()
     -- 4. stale expect, acknowledgements and range, before any memory access
     rejects(function()domain.validate_patch(request(name,owned,id,value,value))end,
      'expect differs','stale expect')
     result.staleExpectRejections=result.staleExpectRejections+1
     rejects(function()domain.validate_patch(request(name,owned,id,field.currentDefault,value,
      {allow_unverified_effect=false}))end,'allow_unverified_effect','missing effect acknowledgement')
     result.acknowledgementRejections=result.acknowledgementRejections+1
     if field.shared then
      rejects(function()domain.validate_patch(request(name,owned,id,field.currentDefault,value,
       {allow_shared=false}))end,'allow_shared','missing shared acknowledgement')
      result.acknowledgementRejections=result.acknowledgementRejections+1
     end
     rejects(function()domain.validate_patch(request(name,owned,id,field.currentDefault,field.range.max+1))end,
      'reviewed range','range above')
     rejects(function()domain.validate_patch(request(name,owned,id,field.currentDefault,field.range.min-1))end,
      'reviewed range','range below')
     result.rangeRejections=result.rangeRejections+2
    end
   end
   -- Adversarial ownership, once per target that has a writable field.
   if writable then
    local field=owned.fields[writable]
    local spec=domain.validate_patch(request(name,owned,writable,field.currentDefault,field.currentDefault))
    local function record(kind)result.proofRejections[kind]=(result.proofRejections[kind]or 0)+1 end
    for index,link in ipairs(owned.chain)do
     reset()
     local _,resolved=resolve(spec)
     poke(link_address(resolved,link),b.encode(link.expect+1,'u32'))
     rejects(function()resolve(spec)end,'native link changed','changed chain link '..index)
     record('chainLink')
    end
    reset()
    local _,resolved=resolve(spec)
    local throwable=resolved.catalog.record(resolved.candidate,'ThrowableComponentData')
    local c=profile.components.ThrowableComponentData
    local row_at=resolved.roots.entity.base+c.offset+28+throwable.identity.indexRow*16+8
    poke(row_at,b.encode((throwable.identity.recordIndex+1)%c.records,'u32'))
    rejects(function()resolve(spec)end,'ownership changed','changed component ownership')
    record('componentOwnership')
    reset()
    tamper.hash=string.rep('0',64)
    rejects(function()resolve(spec)end,'unsupported build fingerprint','wrong build')
    record('wrongBuild')
    reset()
   end
   result.targets=result.targets+1;any=true
   result.targetsByPath[owned.path]=(result.targetsByPath[owned.path]or 0)+1
  end
  if any then result.throwables=result.throwables+1 end
 end
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
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
