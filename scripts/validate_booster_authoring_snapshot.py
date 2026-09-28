"""Resolve and exercise every Booster field through the production chain proofs on the retained snapshot.

For every reviewed field on a copy-on-write memory overlay of the snapshot (no game process):

1. The current value applies as a guarded no-op (ALREADY_DESIRED, zero writes).
2. A changed in-range value applies through the guarded transaction core, reads back at the
   resolved address, and its guarded inverse restores the original bytes.
3. A third-party value at the target is rejected as CONFLICT.
4. Missing acknowledgements and out-of-range values are rejected before any memory access.

Per target, the live proofs must also reject: a changed gate/consumer/selector instruction byte,
a changed Booster enum name, a changed definition-table row identity, a different game.dll
fingerprint, and a relocated game.dll base.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources

OUTPUT = ROOT / 'validation/booster-authoring-snapshot.json'

PROGRAM = r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local b=require('hd2runtime/core/bytes')
local domain=require('hd2runtime/domains/booster_writes')
local database=require('hd2runtime/domains/booster_authoring')
local guarded=require('hd2runtime/core/guarded_transaction')
local fingerprint=require('hd2runtime/core/fingerprint')
local json=require('hd2runtime/primary_mapper/json')
local native=database.native

-- Copy-on-write overlay with page protections, as in the packaged-runtime validator.
local PAGE=4096
local overlay,protection={},{}
local runtime={mode='snapshot-overlay'}
local tamper={}
local counts={writes=0,protection_changes=0}
local function original_protect(at)return source.query(at).protect end
function runtime.module(name)return tamper.module and tamper.module(name) or source.module(name)end
function runtime.address(handle)return source.address(handle)end
function runtime.system_info()return source.system_info()end
function runtime.module_hash(handle)
 if tamper.hash then return tamper.hash end
 if tamper.shift and handle==source.module('game.dll')+tamper.shift then handle=handle-tamper.shift end
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
 return plan
end
local function request(name,path,field,expect,value,extra)
 local r={id='booster-check',allow_shared=true,allow_unverified_effect=true,
  target={resource='booster',booster=name,path=path},field=field,expect=expect,value=value}
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
 local candidate
 if field.type=='integer'then candidate=v+1 else candidate=v*1.25 end
 if range then
  if candidate>range.max then candidate=range.integer and v-1 or (v+range.min)/2 end
  if candidate<range.min then candidate=range.min end
 end
 if field.backing.storage=='f32'then candidate=math.floor(candidate*1024+0.5)/1024 end
 assert(candidate~=v,'no distinct in-range value for '..field.instanceKey)
 return candidate
end
local function f32(v)return b.value(b.encode(v,'f32'),0,'f32')end

local result={status='VALIDATED',boosters=0,targets=0,fieldChecks=0,alreadyDesired=0,
 changedWrites=0,rollbacks=0,conflictRejections=0,acknowledgementRejections=0,rangeRejections=0,
 proofRejections={},writes=0,protectionChanges=0,dataSectionProtectionChanges=0,
 fixtureFallback='disabled',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME}
local worker=coroutine.create(function()
 local names={};for name in pairs(database.boosters)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  local entry=database.boosters[name];local any=false
  local paths={};for path in pairs(entry.targets)do paths[#paths+1]=path end;table.sort(paths)
  for _,path in ipairs(paths)do
   local owned=entry.targets[path]
   local ids={};for id in pairs(owned.fields)do ids[#ids+1]=id end;table.sort(ids)
   for _,id in ipairs(ids)do
    local field=owned.fields[id]
    reset()
    -- 1. guarded no-op
    local plan=resolve(domain.validate_patch(request(name,path,id,field.currentDefault,field.currentDefault)))
    local checked=guarded.apply(runtime,plan)
    assert(checked.status=='ALREADY_DESIRED'and checked.writes==0 and checked.protection_changes==0,
     'booster no-op changed state: '..field.instanceKey)
    result.fieldChecks=result.fieldChecks+1
    if plan.changes[1].already_desired then result.alreadyDesired=result.alreadyDesired+1 end
    -- 2. changed value, read-back, guarded inverse
    local value=changed(field)
    local spec=domain.validate_patch(request(name,path,id,field.currentDefault,value))
    plan=resolve(spec)
    local change=plan.changes[1]
    local before=counts.protection_changes
    local applied=guarded.apply(runtime,plan)
    assert(applied.status=='APPLIED'and applied.writes==1 and applied.protection_restored
     and applied.non_target_bytes_unchanged,'booster write failed: '..field.instanceKey..' '..tostring(applied.reason))
    assert(runtime.read(change.owner.base+change.offset,4)==change.desired,'booster write did not land: '..field.instanceKey)
    if path=='tuning'then
     assert(change.owner.type==0x1000000 and change.offset==native.tableRva+field.backing.row*native.stride+8,
      'tuning write resolved outside the definition table')
     result.dataSectionProtectionChanges=result.dataSectionProtectionChanges+counts.protection_changes-before
    end
    local again=resolve(domain.validate_patch(request(name,path,id,field.currentDefault,value)))
    assert(again.changes[1].already_desired,'changed value is not recognised as desired: '..field.instanceKey)
    local restored=guarded.apply(runtime,guarded.inverse(plan))
    assert(restored.status=='APPLIED'and runtime.read(change.owner.base+change.offset,4)==change.before,
     'booster rollback failed: '..field.instanceKey)
    for page in pairs(protection)do error('page protection not restored for '..field.instanceKey)end
    result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
    -- 3. third-party value
    local third=field.backing.storage=='f32'and b.encode(f32(field.currentDefault)+7,'f32')
     or b.encode(field.currentDefault+7,field.backing.storage)
    poke(change.owner.base+change.offset,third)
    rejects(function()resolve(spec)end,'CONFLICT','conflict')
    result.conflictRejections=result.conflictRejections+1
    reset()
    -- 4. acknowledgements and range, before any memory access
    rejects(function()domain.validate_patch(request(name,path,id,field.currentDefault,value,
     {allow_unverified_effect=false}))end,'allow_unverified_effect','missing effect acknowledgement')
    result.acknowledgementRejections=result.acknowledgementRejections+1
    if field.shared then
     rejects(function()domain.validate_patch(request(name,path,id,field.currentDefault,value,
      {allow_shared=false}))end,'allow_shared','missing shared acknowledgement')
     result.acknowledgementRejections=result.acknowledgementRejections+1
    end
    if field.range then
     rejects(function()domain.validate_patch(request(name,path,id,field.currentDefault,field.range.max+1))end,
      'reviewed range','range')
     result.rangeRejections=result.rangeRejections+1
    end
   end
   -- Proof rejections, once per target.
   local id=ids[1];local field=owned.fields[id]
   local spec=domain.validate_patch(request(name,path,id,field.currentDefault,field.currentDefault))
   local dll=source.module('game.dll')
   local function record(kind)result.proofRejections[kind]=(result.proofRejections[kind]or 0)+1 end
   if owned.proofs then
    for index,proof in ipairs(owned.proofs)do
     reset()
     local at=dll+proof.rva+#proof.bytes/2-1
     poke(at,string.char((source.read(at,1):byte()+1)%256))
     rejects(function()resolve(spec)end,'native consumer changed','changed instruction byte')
     record('instructionByte')
    end
   end
   if path~='deployed_entity'then
    reset()
    local value=entry.enumValue
    poke(dll+native.nameStrings[value+1],'X')
    rejects(function()resolve(spec)end,'booster enum name changed','changed enum name')
    record('enumName')
    reset()
    local other=(value+1)%native.rows
    poke(dll+native.tableRva+other*native.stride,'\255\255\255\255')
    rejects(function()resolve(spec)end,'row identity changed','changed table row identity')
    record('tableRowIdentity')
    reset()
    poke(dll+native.gateFunction.rva,'\204')
    rejects(function()resolve(spec)end,'native consumer changed','changed IsBoosterActive')
    record('gateFunction')
    reset()
    -- A stale/relocated base keeps the fingerprint but no longer owns the pinned image.
    tamper.shift=0x10000
    tamper.module=function(module)
     if module=='game.dll'then return dll+tamper.shift end
     return source.module(module)
    end
    rejects(function()resolve(spec)end,'ownership','relocated game.dll base')
    record('relocatedModule')
   end
   reset()
   tamper.hash=string.rep('0',64)
   rejects(function()resolve(spec)end,'unsupported build fingerprint','wrong build')
   record('wrongBuild')
   reset()
   result.targets=result.targets+1;any=true
  end
  if any then result.boosters=result.boosters+1 end
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
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
