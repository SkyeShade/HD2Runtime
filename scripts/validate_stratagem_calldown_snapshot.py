"""Validate hd2.fields.stratagem.calldown_code on every retained snapshot (no game process; game memory is only read).

For each snapshot the production modules run exactly as in game against the snapshot's memory, with an adapter whose
writes go to a copy-on-write overlay and whose Runtime-owned arrays are a Lua overlay at addresses no module maps.
Every one of the 94 call-in stratagems, one operation at a time, through the production write path
(domains/stratagem_writes.lua: validate_patch, capture_many, prepare; core/guarded_transaction.lua):

* gets a new code (the same length, shorter or longer, never equal to another stratagem's native code) and is written
  with exactly its count (when the length changes) and its pointer, to a Runtime-owned array; the row reads back the
  new code, no other StratagemSettings byte changes, the reader pins prove;
* is restored by the transaction's own inverse, and the settings are byte-identical again.

In the mission snapshots that have a filled HUD stratagem list, every listed stratagem's slot follows automatically
(runtime/calldown_codes.lua): after the write the slot draws the new code, after the restore the original, and no
HUD byte outside that slot's arrow sprites, its layout parents and its relayout flag is written.

The presentation (runtime/stratagem_presentation.lua): the 120mm presents as the Orbital Gas Strike (4 writes: name,
cased name, description, icon), its type and stable id unchanged, then as itself again (the settings byte-identical).

Custom images (runtime/image_resources.lua): the game's texture lookup is proven and read as the game reads it; the
fallback texture is found loaded and the proof's image (not installed when the snapshots were taken) is not. Every
vanilla icon value is its exact GUI icon material plus an atlas sprite. presentation_icon accepts the proof's image at
registration and refuses it before any write (ASSET_UNAVAILABLE: its family is not loaded in these snapshots).

Custom text (runtime/text_resources.lua, development path runtime/stratagem_presentation.lua apply_text): on the
snapshot's real text registry the proof's three texts are registered (the Runtime table after the game's tables: the
slot, then the count) and written to the 120mm's name, cased name and description, each verified to resolve exactly;
the restore writes the native ids back and takes the table out: the settings and the registry are as they were.

The loadout reader (runtime/stratagem_loadout.lua, read-only) reads the saved ship loadout on every snapshot; in the
mission snapshots each saved stratagem is the local player's record entry of the same type and is drawn by the HUD slot
of the same index.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import snapshot_regions  # noqa: E402
from validate_event_world_snapshot import MISSION, SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'validation/stratagem-calldown-snapshot.json'

BODY = r'''
local json=require('hd2runtime/primary_mapper/json')
local world_module=require('hd2runtime/runtime/event_world')
local domain=require('hd2runtime/domains/stratagem_writes')
local database=require('hd2runtime/domains/stratagem_authoring')
local calldown=require('hd2runtime/runtime/calldown_codes')
local C=require('hd2runtime/domains/stratagem_calldown')
local hud=require('hd2runtime/runtime/stratagem_hud')
local transaction=require('hd2runtime/core/guarded_transaction')
local Reader=require('hd2runtime/runtime/reader')
local profile=require('hd2runtime/schemas/current')
local b=require('hd2runtime/core/bytes')
-- The snapshot adapter, a copy-on-write overlay for writes, and Runtime-owned blocks.
local adapter,blocks,next_block,overlay,writes,protections={},{},0x7FFE00000000,{},{},0
for k,v in pairs(source)do adapter[k]=v end
function adapter.owned_block(size)
 local address=next_block;next_block=next_block+0x1000;blocks[address]=string.rep('\0',size);return address
end
function adapter.owned_write(address,bytes)
 assert(blocks[address]and#blocks[address]==#bytes,'not a whole Runtime-owned block');blocks[address]=bytes;return true
end
function adapter.permanent_block(bytes)
 local address=next_block;next_block=next_block+0x10000;blocks[address]=bytes;return address
end
-- The game's package system, simulated: a requested package is resident (the request itself is recorded).
local package_requests={}
function adapter.package_request(entry,instance,id)package_requests[#package_requests+1]=id;return true end
function adapter.package_state(hex)
 for _,id in ipairs(package_requests)do
  local h={};for k=8,1,-1 do h[#h+1]=string.format('%02X',id:byte(k))end
  if '0x'..table.concat(h)==hex then return 'resident' end
 end
 return 'absent'
end
function adapter.read(address,size)
 for at,bytes in pairs(blocks)do
  if address>=at and address+size<=at+#bytes then return bytes:sub(address-at+1,address-at+size)end
 end
 local bytes=source.read(address,size)
 if not bytes then return nil end
 for at,value in pairs(overlay)do
  if at<address+size and at+#value>address then
   local first=math.max(at,address);local last=math.min(at+#value,address+size)
   bytes=bytes:sub(1,first-address)..value:sub(first-at+1,last-at)..bytes:sub(last-address+1)
  end
 end
 return bytes
end
function adapter.write(address,bytes)writes[#writes+1]={address=address,bytes=bytes};overlay[address]=bytes;return true,nil,#bytes end
function adapter.protect()protections=protections+1;return 4 end
world_module.set_runtime(adapter)
local world=assert(world_module.open())
local state=world_module.game_state(world)
local base=b.pointer(source.read(world.game+profile.stratagem.buffer_rva,8),0)
local function settings()return adapter.read(base,profile.stratagem.size)end
local out={mission=state and state.mission or false,pins=calldown.prove(adapter)==true,stratagems={},hud={}}
-- Every native code, to keep the new codes unique.
local taken={}
for _,code in pairs(C.nativeCodes)do taken[table.concat(code,',')]=true end
local function pick(native,index)
 local candidates={}
 local reversed={};for i=#native,1,-1 do reversed[#reversed+1]=native[i]end
 local shorter={};for i=1,#native-1 do shorter[i]=native[#native+1-i]end
 local longer={};for i=1,#native do longer[i]=native[i]end;longer[#longer+1]=native[1]%4+1
 local order=index%3==0 and{reversed,shorter,longer}or index%3==1 and{shorter,longer,reversed}or{longer,reversed,shorter}
 for _,code in ipairs(order)do
  if#code>=1 and#code<=9 and not taken[table.concat(code,',')]then return code end
 end
 for shift=1,3 do
  local rotated={};for i,v in ipairs(native)do rotated[i]=(v+shift-1)%4+1 end
  if not taken[table.concat(rotated,',')]then return rotated end
 end
end
local names={}
for name,entry in pairs(database.stratagems)do
 for _,field in ipairs(entry.fields)do
  if field.semanticFieldId=='stratagem.calldown_code'and field.editable then names[#names+1]=name end
 end
end
table.sort(names)
-- The loadout, read-only (runtime/stratagem_loadout.lua), before any write: the saved ship loadout by stable id; in a
-- mission, the local player's record and, per saved stratagem, its record entry and the HUD slot that draws it.
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local saved,saved_code=loadout.saved(world)
out.loadout={saved=saved and saved.saved,pairs={},code=saved_code}
local record=out.mission and loadout.record(world)
out.loadout.record=record and #record or nil
for _,pair in ipairs(saved and saved.pairs or{})do
 local item={id=pair.id,type=pair.type,uses=pair.uses}
 for _,entry in ipairs(record or{})do
  if entry.id==pair.id then item.recordIndex=entry.index;item.recordType=entry.type end
 end
 if item.recordIndex then
  local located=hud.locate(world,item.recordType)
  item.hudIndex=located and located.index
 end
 out.loadout.pairs[#out.loadout.pairs+1]=item
end
-- The presentation (runtime/stratagem_presentation.lua): the 120mm presents as the Orbital Gas Strike, then as itself
-- again. Only its name, cased name, description and icon bytes change; its type and stable id never do.
local presentation=require('hd2runtime/runtime/stratagem_presentation')
local function settle(handle)
 for _=1,4000 do if handle.status~='pending'then break end;if update then update(0.1)end end
 return handle
end
do
 local before,first=settings(),#writes
 local applied=settle(presentation.apply({carrier='Orbital 120mm HE Barrage',donor='Orbital Gas Strike'}))
 local item={status=applied.status,code=applied.code,reason=applied.reason,writes=#writes-first,outside=0}
 local state=presentation.state()
 if state then
  local row
  for kind=1,profile.stratagem.entries-1 do
   local at=b.pointer(source.read(world.game+profile.stratagem.table_rva+kind*8,8),0)
   if b.u32(adapter.read(at,8),4)==1063322614 then row=at end
  end
  local allowed={}
  for _,field in ipairs(state.fields)do
   local f=C.presentation.fields[field.name]
   for i=0,f.width-1 do allowed[row+f.offset+i]=true end
  end
  local now=settings()
  for i=1,#now do if now:byte(i)~=before:byte(i)and not allowed[base+i-1]then item.outside=item.outside+1 end end
  item.type,item.id=b.u32(adapter.read(row,4),0),b.u32(adapter.read(row+4,4),0)
  if out.mission and hud.populated(world)then
   local record=loadout.record(world)
   for _,entry in ipairs(record or{})do if entry.id==1063322614 then item.recordType=entry.type end end
  end
 end
 local restored=settle(presentation.restore())
 item.restore=restored.status
 item.identical=settings()==before
 out.presentation=item
end
-- Custom images (runtime/image_resources.lua): the game's texture lookup is proven, then read as the game reads it
-- (the fallback texture is loaded; the proof's image, not installed when the snapshots were taken, is not). A custom
-- image is refused for presentation_icon at registration whether or not it is loaded: the loadout grid draws an icon
-- as a GUI material of its name (research/stratagem-icon-consumers-F5FEE03DCFDB.json).
do
 local images=require('hd2runtime/runtime/image_resources')
 images.reset_for_tests()
 local item={pins=images.prove(adapter)~=nil}
 local ok,loaded,why=pcall(images.resident_name,adapter,'core/fallback_resources/missing_texture')
 item.missingTexture=ok and loaded==true or tostring(loaded)
 local icon=images.handle('orbital_gas_barrage_icon','mods/skyeshade/hd2runtime_custom_stratagem_p0_proof')
 ok,loaded,why=pcall(images.resident,adapter,icon)
 item.proofImage=ok and(loaded and'loaded'or tostring(why))or tostring(loaded)
 -- The icon family reader (research/stratagem-icon-family-F5FEE03DCFDB.json) on real memory: every reviewed vanilla
 -- icon value is its exact GUI icon material (byte for byte, with the loader's fix-ups and object) plus an atlas sprite;
 -- the proof's family is not loaded.
 local seen,values,exact,sprites,textures={},0,0,0,0
 for _,v in pairs(C.presentation.values)do
  local value=v.icon
  if value~='0x0000000000000000'and not seen[value]then
   seen[value]=true;values=values+1
   local f=images.family_of(adapter,tonumber(value:sub(3,10),16),tonumber(value:sub(11,18),16))
   if f.material==true then exact=exact+1 end
   if f.sprite then sprites=sprites+1 end
   if f.texture==true then textures=textures+1 end
  end
 end
 item.vanillaIcons={values=values,materialExact=exact,sprites=sprites,textures=textures}
 local family=images.family(adapter,icon)
 item.proofFamily={complete=family.complete,material=tostring(family.material),texture=tostring(family.texture)}
 -- The public field: the image is accepted at registration; before the write every icon consumer pin proves on this
 -- snapshot and, without the family, it is refused with nothing written.
 local before,first=settings(),#writes
 local accepted,spec=pcall(domain.validate_patch,{id='custom_icon',target={resource='stratagem',
  stratagem='Orbital 120mm HE Barrage',path='stratagem'},field='stratagem.presentation.icon',
  expect='Orbital 120mm HE Barrage',value=icon})
 item.accepted=accepted
 local prepared,refusal=false,tostring(spec)
 if accepted then
  local reader=Reader.new(adapter)
  local ok,why=pcall(function()
   local resolved=domain.capture_many(adapter,reader,{spec})[1]
   domain.prepare(resolved,reader,spec)
  end)
  prepared,refusal=ok,tostring(why)
 end
 item.refused=accepted and not prepared
 item.reason=refusal
 item.writes=#writes-first
 item.identical=settings()==before
 out.images=item
end
-- Custom text (runtime/text_resources.lua; the development path): the proof's texts on the real registry.
do
 local texts=require('hd2runtime/runtime/text_resources')
 local D=require('hd2runtime/domains/text_resources')
 texts.reset_for_tests();presentation.reset_for_tests()
 local RESOURCE='mods/skyeshade/hd2runtime_custom_stratagem_p0_proof'
 local name=texts.handle('orbital_gas_barrage_name','ORBITAL GAS BARRAGE',RESOURCE)
 local cased=texts.handle('orbital_gas_barrage_name_cased','Orbital Gas Barrage',RESOURCE)
 local desc=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',RESOURCE)
 local exe=adapter.address(adapter.module(nil))
 local function reg()
  local list=b.pointer(adapter.read(exe+D.registry.global,8),0)
  local head=adapter.read(list,16)
  local count,capacity=b.u32(head,0),b.u32(head,4)
  return {count=count,capacity=capacity,slots=adapter.read(b.pointer(head,8),capacity*8)}
 end
 local item={probe=texts.inspect(adapter)}
 local registry_before,before,first=reg(),settings(),#writes
 local job=settle(presentation.apply_text({carrier='Orbital 120mm HE Barrage',name=name,nameCased=cased,description=desc}))
 item.status,item.code,item.reason=job.status,job.code,job.reason and tostring(job.reason)
 item.writes=#writes-first
 item.verify=job.verify
 local registry_after=reg()
 item.registry={before=registry_before.count,after=registry_after.count,capacity=registry_after.capacity,
  gameTablesUnchanged=registry_after.slots:sub(1,registry_before.count*8)==registry_before.slots:sub(1,registry_before.count*8)}
 item.resolves=texts.resolves(adapter,name)==true and texts.resolves(adapter,cased)==true and texts.resolves(adapter,desc)==true
 local now,outside=settings(),0
 local kind=loadout.type_of(world,1063322614)
 local row=kind and world.view.pointer(world.game+profile.stratagem.table_rva+kind*8)
 for i=1,#now do
  local at=base+i-1
  if now:byte(i)~=before:byte(i)and not(row and at>=row+0x28 and at<row+0x34)then outside=outside+1 end
 end
 item.outside=outside
 local restored=settle(presentation.restore())
 item.restore=restored.status
 item.restoreWrites=#writes-first-item.writes
 item.identical=settings()==before
 item.registryRestored=reg().count==registry_before.count
 out.text=item
end
-- The carrier DISCOVERY on every snapshot (read-only, from what this account owns; no fixed list): ready (the token
-- shows as owned), every candidate's checks, the first eligible one not in the saved loadout (the donor excluded).
do
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 local item={}
 local saved=loadout.saved(world)
 local present={}
 for _,pair in ipairs(saved and saved.pairs or{})do present[pair.id]=true end
 local found=slots.discover_carriers(world,'Orbital Precision Strike',{present=present,exclude={'Orbital 120mm HE Barrage'}})
 item.ready,item.reason=found.ready,found.reason
 item.chosen=found.chosen and found.chosen.name
 item.chosenClass=found.chosen and found.chosen.class
 item.chosenInLoadout=found.chosen and found.chosen.inLoadout
 item.eligible={}
 for _,c in ipairs(found.candidates)do if c.eligible then item.eligible[#item.eligible+1]=c.name end end
 item.notOwned=0
 for _,c in ipairs(found.candidates)do if c.selectable and not c.owned then item.notOwned=item.notOwned+1 end end
 item.donorExcluded=false
 for _,c in ipairs(found.candidates)do
  if c.name=='Orbital 120mm HE Barrage'then item.donorExcluded=not c.eligible end
 end
 out.carrier_discovery=item
end
-- The custom stratagem selector's conversion (convert_virtual) to a carrier that is NOT the donor: the carrier is
-- DISCOVERED from what the account owns (the first eligible one not in the record). In a mission, the first unlimited loadout entry is seeded as the virtual Orbital Precision Strike and the
-- last one as a NATIVE Precision Strike (validation seeds under the overlay, never a write), recorded in the loadout's own
-- order: a different recorded order is refused with nothing written; the exact one converts ONLY the virtual entry to
-- the carrier (its package requested and loaded first) and back, the native Precision Strike staying one. Aboard the
-- ship it is refused.
do
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 slots.reset_for_tests()
 local PRECISION=3523620028
 local item={mission=out.mission}
 local record=slots.local_record(world)
 local token_type=loadout.type_of(world,PRECISION)
 local present={}
 for _,entry in ipairs(record and record.entries or{})do
  local id=loadout.id_of(world,entry.type)
  if id then present[id]=true end
 end
 local found=slots.discover_carriers(world,'Orbital Precision Strike',{present=present,exclude={'Orbital 120mm HE Barrage'}})
 local chosen=found.chosen and found.chosen.name
 item.carrier=chosen
 item.carrierType=found.chosen and found.chosen.type
 local spec={definition='orbital_gas_barrage',token='Orbital Precision Strike',carrier=chosen or'Orbital Napalm Barrage',
  slots={0},order={PRECISION}}
 local seeds,native={},nil
 if record and out.mission and token_type then
  local picks,unlimited={},{}
  for _,entry in ipairs(record.entries)do
   if entry.granted==0 then
    picks[#picks+1]=entry
    if entry.uses==-1 then unlimited[#unlimited+1]=#picks end
   end
  end
  if #unlimited>=2 then
   local virtual_at,native_at=unlimited[1],unlimited[#unlimited]
   spec.slots,spec.order={virtual_at-1},{}
   for k,entry in ipairs(picks)do
    local is_seed=k==virtual_at or k==native_at
    if is_seed then
     overlay[entry.address]=string.char(token_type%256,math.floor(token_type/256)%256,0,0)
     seeds[#seeds+1]=entry
     if k==native_at then native=entry end
    end
    spec.order[k]=is_seed and PRECISION or loadout.id_of(world,entry.type)
   end
  end
 end
 item.seeded=#seeds
 -- Payload stage A: the Gas Barrage code UP UP DOWN DOWN on the discovered carrier through the production write path
 -- (the carrier's native code as the expect), before the conversion; then every entry of the (seeded) record checked
 -- against it: no equal code, none that starts with it or is its start. Restored after the conversion.
 local code_plan,code_before,code_row
 local function row_code(row)
  local bytes=row and adapter.read(row,profile.stratagem.stride)
  if not bytes then return nil end
  local pointer,count=b.pointer(bytes,0x40),b.u32(bytes,0x48)
  if count<1 or count>16 then return nil end
  return calldown.decode(adapter.read(pointer,count*4))
 end
 local function kind_row(kind)return b.pointer(source.read(world.game+profile.stratagem.table_rva+kind*8,8),0)end
 if chosen then
  local field
  for _,f in ipairs(database.stratagems[chosen].fields)do
   if f.semanticFieldId=='stratagem.calldown_code'then field=f end
  end
  code_row=kind_row(item.carrierType)
  item.carrierNativeCode=calldown.text(row_code(code_row)or{})
  item.carrierReviewedCode=calldown.text(C.nativeCodes[tostring(found.chosen.id)]or{})
  code_before=settings()
  local spec_code=domain.validate_patch{id='gas_barrage_code',target={resource='stratagem',stratagem=chosen,
   path='stratagem'},field='stratagem.calldown_code',expect=field.currentDefault,value={'up','up','down','down'}}
  local reader=Reader.new(adapter)
  local resolved=domain.capture_many(adapter,reader,{spec_code})[1]
  code_plan=domain.prepare(resolved,reader,spec_code)
  reader.verify()
  local code_first=#writes
  local report=transaction.apply(adapter,code_plan)
  item.codeStatus,item.codeWrites,item.codeNonTarget=report.status,#writes-code_first,report.non_target_bytes_unchanged
  item.codeReadBack=calldown.text(row_code(code_row)or{})
  local now=settings()
  item.codeOutsideRow=0
  for i=1,#now do
   if now:byte(i)~=code_before:byte(i)and not(base+i-1>=code_row+0x40 and base+i-1<code_row+0x4C)then
    item.codeOutsideRow=item.codeOutsideRow+1
   end
  end
  local token_row,donor_row=kind_row(token_type or 0),kind_row(loadout.type_of(world,1063322614)or 0)
  item.tokenCodeNative=calldown.same(row_code(token_row),C.nativeCodes['3523620028'])
  item.donorCodeNative=calldown.same(row_code(donor_row),C.nativeCodes['1063322614'])
  local related={}
  for _,entry in ipairs((slots.local_record(world)or{}).entries or{})do
   local values=row_code(kind_row(entry.type))
   local relation=values and entry.type~=item.carrierType and calldown.relation({1,1,3,3},values)
   if relation then related[#related+1]=entry.index..':'..relation end
  end
  item.recordRelated=related
 end
 local first=#writes
 -- Not the recorded order (its last loadout slot differs): refused, nothing written.
 local wrong={}
 for k,id in ipairs(spec.order)do wrong[k]=id end
 if #wrong>=2 then wrong[#wrong]=0 end
 local refused=settle(slots.convert_virtual({definition=spec.definition,token=spec.token,carrier=spec.carrier,
  slots=spec.slots,order=#seeds>0 and wrong or spec.order}))
 item.wrongCode,item.wrongWrites=refused.code,#writes-first
 local before=record and adapter.read(record.state+0x188,0x604)
 first=#writes
 local requests=#package_requests
 local job=settle(slots.convert_virtual(spec))
 item.status,item.code,item.reason=job.status,job.code,job.reason and tostring(job.reason)
 item.writes=#writes-first
 item.verify=job.verify
 item.packageRequests=#package_requests-requests
 item.package=job.package
 if job.status=='converted'then
  local after=slots.local_record(world)
  item.indices,item.slots=job.indices,job.slots
  item.types={}
  for k,index in ipairs(job.indices)do item.types[k]=after.entries[index+1].type end
  item.nativeStays=native~=nil and after.entries[native.index+1].type==token_type
  -- The converted entry's type calls in with the carrier row's code: the Gas Barrage code.
  item.convertedCode=calldown.text(row_code(kind_row(item.types[1]))or{})
  local now=adapter.read(record.state+0x188,0x604)
  local outside=0
  for i=1,#now do
   local at,inside=i-1,false
   for _,index in ipairs(job.indices)do if at>=index*0x30 and at<index*0x30+4 then inside=true end end
   if now:byte(i)~=before:byte(i)and not inside then outside=outside+1 end
  end
  item.outside=outside
  local restored=settle(slots.restore())
  item.restore=restored.status
  item.restoreExact=restored.exact
  item.identical=adapter.read(record.state+0x188,0x604)==before
 end
 for _,entry in ipairs(seeds)do overlay[entry.address]=nil end
 if code_plan then
  local restored=transaction.apply(adapter,transaction.inverse(code_plan))
  item.codeRestore=restored.status
  item.codeIdentical=settings()==code_before
 end
 out.virtual_conversion=item
end
-- Mission-time slot conversion (runtime/stratagem_slot_conversion.lua, development): in a mission, a loadout entry is
-- made a duplicate of the one before it (validation seed under the overlay, never a write), then the later duplicate
-- becomes the Orbital 120mm HE Barrage (its call-in package requested first) and back; aboard the ship it is refused.
do
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 local SLOTS=require('hd2runtime/domains/stratagem_slots')
 slots.reset_for_tests()
 local item={mission=out.mission}
 local record=slots.local_record(world)
 local token_type,token_name,seeded
 if record and out.mission then
  local previous
  for _,entry in ipairs(record.entries)do
   if entry.granted==0 and entry.uses==-1 then
    local row=world.view.pointer(world.game+profile.stratagem.table_rva+entry.type*8)
    local max=row and b.u32(adapter.read(row+SLOTS.row.maxUses,4),0)
    if previous and not seeded and max==4294967295 then
     overlay[entry.address]=string.char(previous.type%256,math.floor(previous.type/256)%256,0,0)
     seeded=entry.index;token_type=previous.type
    end
    if max==4294967295 then previous=entry end
   end
  end
  local id=loadout.id_of(world,token_type)
  for name,entry in pairs(database.stratagems)do if entry.root.id==id then token_name=name end end
 end
 item.seeded,item.token=seeded,token_name
 local spec={token=token_name or'Orbital Precision Strike',carrier='Orbital 120mm HE Barrage'}
 local before,first=record and adapter.read(record.state+0x188,0x604),#writes
 local requests=#package_requests
 local job=settle(slots.convert(spec))
 item.status,item.code,item.reason=job.status,job.code,job.reason and tostring(job.reason)
 item.writes=#writes-first
 item.verify=job.verify
 item.packageRequests=#package_requests-requests
 if job.status=='converted'then
  local after=slots.local_record(world)
  item.index=job.index
  item.entryType=after.entries[job.index+1].type
  local now=adapter.read(record.state+0x188,0x604)
  local outside=0
  for i=1,#now do
   local at=i-1
   if now:byte(i)~=before:byte(i)and not(at>=job.index*0x30 and at<job.index*0x30+4)then outside=outside+1 end
  end
  item.outside=outside
  item.saveUnchanged=true
  local restored=settle(slots.restore())
  item.restore=restored.status
  item.restoreExact=restored.exact
  item.identical=adapter.read(record.state+0x188,0x604)==before
 end
 if seeded then overlay[record.entries[seeded+1].address]=nil end
 out.slots_conversion=item
end
-- The HUD list before anything (mission snapshots).
local listed={}
local filled=out.mission and hud.populated(world)
out.slots={}
if filled then
 local list=world.view.pointer(world.game+C.hud.global)+C.hud.pathOffset
 for index=0,C.hud.slots.count-1 do
  local kind=world.view.u32(list+index*C.hud.slots.stride+C.hud.slots.type)
  if kind~=0 then out.slots[#out.slots+1]=kind end
 end
end
for index,name in ipairs(names)do
 local entry=database.stratagems[name]
 local field
 for _,item in ipairs(entry.fields)do if item.semanticFieldId=='stratagem.calldown_code'then field=item end end
 local native=calldown.values(field.currentDefault)
 local code=assert(pick(native,index),'no unique code for '..name)
 local spec=domain.validate_patch{id='calldown_'..index,target={resource='stratagem',stratagem=name,path='stratagem'},
  field='stratagem.calldown_code',expect=field.currentDefault,value=calldown.names(code)}
 local before=settings()
 local reader=Reader.new(adapter)
 local resolved=domain.capture_many(adapter,reader,{spec})[1]
 local plan=domain.prepare(resolved,reader,spec)
 reader.verify()
 local first=#writes
 local report=transaction.apply(adapter,plan)
 local item={name=name,native=calldown.text(native),code=calldown.text(code),status=report.status,id=entry.root.id,
  writes=#writes-first,nonTarget=report.non_target_bytes_unchanged}
 local row=nil
 for _,change in ipairs(plan.changes)do row=row or change.owner.base+change.offset-(change.field_offset or 0)end
 local rowbytes=adapter.read(row,profile.stratagem.stride)
 local pointer,count=b.pointer(rowbytes,0x40),b.u32(rowbytes,0x48)
 item.readBack=calldown.text(calldown.decode(adapter.read(pointer,count*4)))
 item.owned=calldown.owned(pointer,count)~=nil
 local now,differing=settings(),{}
 for i=1,#now do if now:byte(i)~=before:byte(i)then differing[#differing+1]=i-1 end end
 item.outsideRow=0
 for _,offset in ipairs(differing)do
  if not(base+offset>=row+0x40 and base+offset<row+0x4C)then item.outsideRow=item.outsideRow+1 end
 end
 item.expectedWrites=(#code==#native)and 1 or 2
 -- The HUD, in a mission with a filled list: the slot follows the row.
 local kind=b.u32(rowbytes,0)
 item.type=kind
 local located=filled and hud.locate(world,kind)
 if located then
  local hud_first=#writes
  calldown.check_now(false)
  local after=hud.locate(world,kind)
  local allowed={[located.slot+C.hud.slots.relayout]=true}
  for _,parent in ipairs(located.ancestors)do allowed[parent.address]=true end
  local first_sprite=located.slot+C.hud.sprites.offset
  local last_sprite=first_sprite+C.hud.sprites.count*C.hud.sprites.stride
  local outside=0
  for i=hud_first+1,#writes do
   local at=writes[i].address
   if not((at>=first_sprite and at+#writes[i].bytes<=last_sprite)or allowed[at])then outside=outside+1 end
  end
  listed[#listed+1]={name=name,slot=located.index,before=calldown.text(located.shows),
   after=after and calldown.text(after.shows),writes=#writes-hud_first,outside=outside}
 end
 -- Restore through the transaction's own inverse.
 local inverse=transaction.inverse(plan)
 local restored=transaction.apply(adapter,inverse)
 item.restore=restored.status
 item.identical=settings()==before
 if located then
  local hud_first=#writes
  calldown.check_now(false)
  local back=hud.locate(world,kind)
  listed[#listed].back=back and calldown.text(back.shows)
  listed[#listed].backWrites=#writes-hud_first
 end
 out.stratagems[#out.stratagems+1]=item
end
out.hud=listed
out.protections=protections
return json.encode(out)
'''


def validate(snapshots=SNAPSHOTS):
    results = {}
    for name in snapshots:
        report = json.loads(snapshot_regions.run_lua(BODY, build_profile.snapshot_directory() / name))
        phase = MISSION.get(name, 'ship')
        problems = []
        if not report['pins']:
            problems.append('the calldown reader pins do not prove')
        if len(report['stratagems']) != 94:
            problems.append('%d stratagems, not 94' % len(report['stratagems']))
        for item in report['stratagems']:
            if not (item['status'] == 'APPLIED' and item['nonTarget'] and item['writes'] == item['expectedWrites']
                    and item['readBack'] == item['code'] and item['owned'] and item['outsideRow'] == 0
                    and item['restore'] == 'APPLIED' and item['identical']):
                problems.append('%s: %r' % (item['name'], item))
        if phase in ('alive', 'reinforced'):
            # Every filled slot of a catalogued stratagem follows; the others (no catalogued row) are not touched.
            types = {x['type']: x['name'] for x in report['stratagems']}
            expected = sorted(types[k] for k in report['slots'] if k in types)
            if not expected or sorted(x['name'] for x in report['hud']) != expected:
                problems.append('HUD slots %r, exercised %r' % (expected, [x['name'] for x in report['hud']]))
            for item in report['hud']:
                if not (item['after'] == next(x['code'] for x in report['stratagems'] if x['name'] == item['name'])
                        and item['back'] == item['before'] and item['writes'] > 0 and item['outside'] == 0):
                    problems.append('HUD %s: %r' % (item['name'], item))
        elif report['hud']:
            problems.append('a HUD slot was redrawn outside a mission')
        if report['protections']:
            problems.append('a page protection changed on a read-write allocation')
        item = report['presentation']
        if not (item['status'] == 'applied' and item['writes'] == 4 and item['outside'] == 0 and item['type'] == 136
                and item['id'] == 1063322614 and item['restore'] == 'restored' and item['identical']):
            problems.append('presentation %r' % item)
        # Custom images: the lookup proves, the fallback texture is found, the proof's image is not; presentation_icon
        # accepts the image at registration and refuses it before any write (its family is not loaded here).
        item = report['images']
        if not (item['pins'] and item['missingTexture'] is True and item['proofImage'] == "not in the game's textures"
                and item['accepted'] and item['refused'] and 'ASSET_UNAVAILABLE' in item['reason']
                and "FAMILY_INCOMPLETE: material: not in the game's materials" in item['reason'] and item['writes'] == 0
                and item['identical'] and item['vanillaIcons']['values'] == item['vanillaIcons']['materialExact']
                == item['vanillaIcons']['sprites'] > 100 and item['vanillaIcons']['textures'] == 0
                and item['proofFamily'] == {'complete': False, 'material': "not in the game's materials",
                    'texture': "not in the game's textures"}):
            problems.append('images %r' % item)
        # Mission-time slot conversion: in a mission the seeded later duplicate becomes the 120mm (its package requested
        # first, 1 write) and back (1 write), nothing else in the record changes; aboard the ship it is refused.
        item = report['slots_conversion']
        if phase in ('alive', 'reinforced'):
            verify = item.get('verify') or {}
            if not (item['status'] == 'converted' and item['writes'] == 1 and item['entryType'] == 136
                    and verify and all(verify.values()) and item['outside'] == 0 and item['packageRequests'] == 1
                    and item['restore'] == 'restored' and item['restoreExact'] and item['identical']):
                problems.append('slot conversion %r' % item)
        elif not (item['status'] == 'refused' and item['code'] == 'NOT_IN_MISSION' and item['writes'] == 0):
            problems.append('slot conversion outside a mission %r' % item)
        # The carrier discovery: ready on every snapshot (the token shows as owned), the donor excluded, a carrier
        # chosen (an orbital bombardment, class 1) that is not in the saved loadout.
        item = report['carrier_discovery']
        if not (item['ready'] and item['donorExcluded'] and item.get('chosen') and item.get('chosenClass') == 1
                and item.get('chosenInLoadout') is False and item['chosen'] in item['eligible']):
            problems.append('carrier discovery %r' % item)
        # The identity conversion to a carrier that is not the donor: the discovered carrier; a wrong recorded order refused with nothing
        # written; ONLY the virtual entry becomes the carrier (1 write; its package requested and loaded first) and
        # back, the native Precision Strike staying one, nothing else in the record changing; aboard the ship refused.
        item = report['virtual_conversion']
        # Payload stage A on every snapshot: the carrier's native code read from its row equals the reviewed one; the
        # Gas Barrage code written with its count and pointer only (2 writes: the length changes), read back, nothing
        # else in the settings changed, the token's and the donor's codes native; no record entry related to it; the
        # restore exact.
        if not (item.get('carrierNativeCode') and item['carrierNativeCode'] == item.get('carrierReviewedCode')
                and item.get('codeStatus') == 'APPLIED' and item.get('codeNonTarget') and item.get('codeWrites') == 2
                and item.get('codeReadBack') == 'up up down down' and item.get('codeOutsideRow') == 0
                and item.get('tokenCodeNative') is True and item.get('donorCodeNative') is True
                and item.get('recordRelated') in ([], {}) and item.get('codeRestore') == 'APPLIED'
                and item.get('codeIdentical') is True):
            problems.append('carrier code (stage A) %r' % item)
        if phase in ('alive', 'reinforced'):
            verify = item.get('verify') or {}
            if not (item['seeded'] == 2 and item['wrongCode'] == 'IDENTITY_CHANGED' and item['wrongWrites'] == 0
                    and item.get('carrier') and item['status'] == 'converted' and item['writes'] == 1
                    and item.get('types') == [item.get('carrierType')]
                    and item.get('nativeStays') is True and verify and all(verify.values()) and item['outside'] == 0
                    and item['packageRequests'] == 1 and str(item.get('package')).startswith('loaded')
                    and item['restore'] == 'restored' and item['restoreExact'] and item['identical']
                    and item.get('convertedCode') == 'up up down down'):
                problems.append('virtual slot conversion %r' % item)
        elif not (item['status'] == 'refused' and item['code'] == 'NOT_IN_MISSION' and item['writes'] == 0
                and item['wrongWrites'] == 0):
            problems.append('virtual slot conversion outside a mission %r' % item)
        # Custom text: registered after the game's tables (2 writes), the 3 members written and verified; the restore
        # writes them back and takes the table out (4 writes): settings and registry as they were.
        item = report['text']
        verify = item.get('verify') or {}
        if not (item['status'] == 'applied' and item['writes'] == 5 and verify and all(verify.values())
                and item['resolves'] and item['outside'] == 0 and item['registry']['after'] == item['registry']['before'] + 1
                and item['registry']['gameTablesUnchanged'] and not item['probe']['collisions']
                and item['restore'] == 'restored' and item['restoreWrites'] == 4 and item['identical']
                and item['registryRestored']):
            problems.append('text %r' % item)
        # The saved loadout reads on every snapshot; in a mission each saved stratagem is the local player's record
        # entry of the same type, drawn by the HUD slot of the same index.
        loadout = report['loadout']
        if not (loadout['saved'] and 1 <= len(loadout['pairs']) <= 4 and all(p['type'] for p in loadout['pairs'])):
            problems.append('saved loadout %r' % loadout)
        if phase in ('alive', 'reinforced'):
            for pair in loadout['pairs']:
                if not (pair.get('recordType') == pair['type'] and pair.get('hudIndex') == pair.get('recordIndex')
                        and pair.get('recordIndex') is not None):
                    problems.append('saved stratagem not in the record/HUD: %r' % pair)
        results[name] = {'phase': phase, 'passed': not problems, 'problems': problems[:20],
            'summary': {'stratagems': len(report['stratagems']), 'filledSlots': len(report['slots']),
                'savedLoadout': [p['type'] for p in report['loadout']['pairs']],
                'presentation': '%s, %d writes, restore %s' % (report['presentation']['status'],
                    report['presentation']['writes'], report['presentation']['restore']),
                'iconFamilies': 'vanilla icons: %(materialExact)d/%(values)d exact GUI materials, %(sprites)d sprites, '
                    '%(textures)d standalone textures' % report['images']['vanillaIcons'],
                'images': 'lookup %s, fallback texture %s, proof image %s, icon write %s (%d writes)' % (
                    'proven' if report['images']['pins'] else 'NOT proven', report['images']['missingTexture'],
                    report['images']['proofImage'], 'refused before writing' if report['images']['refused'] else 'ALLOWED',
                    report['images']['writes']),
                'slotConversion': '%s %s%s' % (report['slots_conversion']['status'],
                    report['slots_conversion'].get('code') or '', (' entry %s -> type %s, restore %s' % (
                    report['slots_conversion'].get('index'), report['slots_conversion'].get('entryType'),
                    report['slots_conversion'].get('restore'))) if report['slots_conversion']['status'] == 'converted'
                    else ''),
                'carrierDiscovery': 'ready %s, chosen %s; %d eligible: %s; %d selectable not owned' % (
                    report['carrier_discovery']['ready'], report['carrier_discovery'].get('chosen'),
                    len(report['carrier_discovery']['eligible']), ', '.join(report['carrier_discovery']['eligible']),
                    report['carrier_discovery']['notOwned']),
                'virtualConversion': '%s %s%s' % (report['virtual_conversion']['status'],
                    report['virtual_conversion'].get('code') or '', (' loadout slot %s = entry %s -> type %s (package '
                    '%s) the carrier %s, native Precision Strike stays %s, restore %s; wrong order %s' % (
                    report['virtual_conversion'].get('slots'), report['virtual_conversion'].get('indices'),
                    report['virtual_conversion'].get('types'), report['virtual_conversion'].get('package'),
                    report['virtual_conversion'].get('carrier'), report['virtual_conversion'].get('nativeStays'), report['virtual_conversion'].get('restore'),
                    report['virtual_conversion'].get('wrongCode')))
                    if report['virtual_conversion']['status'] == 'converted' else ''),
                'text': 'registry %d -> %d of %d, %s, %d + %d writes, restore %s' % (
                    report['text']['registry']['before'], report['text']['registry']['after'],
                    report['text']['registry']['capacity'], report['text']['status'], report['text']['writes'],
                    report['text']['restoreWrites'], report['text']['restore']),
                'hudSlots': len(report['hud']),
                'rowWrites': sum(x['writes'] for x in report['stratagems']),
                'hudWrites': sum(x['writes'] + x.get('backWrites', 0) for x in report['hud'])},
            'report': report}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='append', help='Validate only these snapshot file names')
    args = parser.parse_args()
    results = validate(tuple(args.snapshot) if args.snapshot else SNAPSHOTS)
    summary = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameWrites': 0,
        'passed': all(r['passed'] for r in results.values()), 'snapshots': results}
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8', newline='\n')
    for name, result in results.items():
        print(('PASS ' if result['passed'] else 'FAIL ') + name + ' (' + result['phase'] + ') ' + json.dumps(
            result['summary']) + ('' if result['passed'] else ': ' + '; '.join(result['problems'][:3])))
    if not summary['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
