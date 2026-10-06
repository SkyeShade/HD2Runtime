"""Validate the carrier payload (runtime/bombardment_payload.lua, docs/custom-stratagems.md "Payload stage B") on every
retained snapshot (no game process; game memory is only read).

The production modules run against the snapshot's memory with an adapter whose writes go to a copy-on-write overlay,
whose page protections are simulated per page (the entity region is read-only: the guarded transaction opens a page,
writes and restores it), and whose package requests make a package resident.

On every snapshot, read-only: every reviewed orbital bombardment's record is found by the game's own lookup, owned by
one index slot and by its row only, exactly its vanilla bytes; the compatible carriers are the 380mm, the Napalm and
the Walking Barrage; no instance, private copy or active variant. Aboard the ship (and at the mission end transition)
the write is refused (NOT_IN_MISSION) with nothing written.

In the mission snapshots, with the first unlimited loadout entry seeded as the virtual token (validation seed under the
overlay, never a write; its cooldown end is the snapshot's own, an absolute game time that is NOT 0 on a fresh entry:
0.1.0's live run was refused because the guard expected 0): before the conversion the payload is refused
(NOT_CONVERTED); the payload-filtered discovery
chooses a compatible carrier; the conversion makes the virtual entry that carrier; a wrong-family carrier (a strike) is
refused (NOT_COMPATIBLE); an instance of the carrier's payload (seeded) refuses the write (IN_USE); then the donor's
pattern is applied: exactly the differing words (6 for the 380mm), nothing else of the entity region written, the
record the donor's pattern, the donor's record vanilla, the shell list packed; a seeded running barrage refuses the
restore (IN_USE); the restore writes the words back and the whole record equals its vanilla bytes; every page's
protection is back as it was. Then the proof's own path (stratagem_selector.convert_with_payload, with the proof's
definition and the virtual-slot record a selection leaves): the conversion and the payload in one tick, the carrier
never in the record without its pattern, restored exactly. Then stage C, the same path with the Orbital Gas
Strike as the shell donor: the conversion, the 120mm pattern and the shell list 197, 197, 197 in one tick (1 + 6
writes), the carrier never in the record without them, the 120mm's and the Gas Strike's records and the Gas Strike's
chain (shell 197, explosion 82, damage 447, volume template 16, statuses 42/44) exactly as reviewed, restored exactly.
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

OUTPUT = ROOT / 'validation/bombardment-payload-snapshot.json'

BODY = r'''
local json=require('hd2runtime/primary_mapper/json')
local world_module=require('hd2runtime/runtime/event_world')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/bombardment_payload')
-- The snapshot adapter: a copy-on-write overlay for writes, page protections simulated per page, packages simulated.
local adapter,blocks,next_block,overlay,writes,pages={},{},0x7FFE00000000,{},{},{}
for k,v in pairs(source)do adapter[k]=v end
function adapter.owned_block(size)
 local address=next_block;next_block=next_block+0x1000;blocks[address]=string.rep('\0',size);return address
end
function adapter.owned_write(address,bytes)blocks[address]=bytes;return true end
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
local query=source.query
function adapter.query(at)
 local r=query(at)
 if not r then return nil end
 local page=at-at%4096
 if pages[page]then
  return {base=page,size=4096,allocation_base=r.allocation_base,allocation_protect=r.allocation_protect,state=r.state,
   protect=pages[page],type=r.type}
 end
 return r
end
local protections=0
function adapter.protect(page,size,value)
 local old=pages[page]or(query(page)or{}).protect
 pages[page]=value;protections=protections+1
 return old
end
function adapter.write(address,bytes)writes[#writes+1]={address=address,bytes=bytes};overlay[address]=bytes;return true,nil,#bytes end
world_module.set_runtime(adapter)
local world=assert(world_module.open())
local state=world_module.game_state(world)
local out={mission=state and state.mission or false,records={}}
local payload=require('hd2runtime/runtime/bombardment_payload')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
payload.reset_for_tests();slots.reset_for_tests()
local function settle(handle)
 for _=1,4000 do if handle.status~='pending'then break end;if update then update(0.1)end end
 return handle
end
out.pins=payload.prove(world)==true
-- Read-only: every reviewed orbital bombardment record.
local names={}
for _,record in pairs(D.records)do names[#names+1]=record.name end
table.sort(names)
for _,name in ipairs(names)do
 local r,code,why=payload.inspect(world,name)
 if r then
  out.records[#out.records+1]={name=name,record=r.record,reviewedRecord=r.reviewedRecord,indexRow=r.indexRow,
   reviewedRow=r.reviewedRow,owners=r.owners,rowsListing=#r.rowsListing,rowType=r.rowsListing[1]==r.type,ownRow=r.ownRow,
   vanilla=r.vanilla,shells=r.shells,shellCount=r.shellCount,perSalvo=r.perSalvo,salvos=r.salvos,scatter=r.scatter,
   compatible=r.compatible,differences=#r.differences,instances=r.instances and r.instances.of,
   total=r.instances and r.instances.total,variant=r.variant,size=r.size}
 else out.records[#out.records+1]={name=name,code=code,reason=why}end
end
local item={}
local function entity_writes(first)
 local n=0
 for i=first+1,#writes do n=n+1 end
 return n
end
-- Before any conversion: refused, nothing written.
local first=#writes
local early=settle(payload.apply({carrier='Orbital 380mm HE Barrage'}))
item.early,item.earlyWrites=early.code,#writes-first
local PRECISION=3523620028
local record=slots.local_record(world)
local token_type=loadout.type_of(world,PRECISION)
local seeded
if record and out.mission and token_type then
 for _,entry in ipairs(record.entries)do
  if entry.granted==0 and entry.uses==-1 and not seeded then seeded=entry end
 end
end
if seeded then
 overlay[seeded.address]=string.char(token_type%256,math.floor(token_type/256)%256,0,0)
 item.cooldownEnd=b.u32(source.read(seeded.address+0x18,4),0)
 local present={}
 for _,entry in ipairs(record.entries)do
  local id=loadout.id_of(world,entry.type)
  if id then present[id]=true end
 end
 local found=slots.discover_carriers(world,'Orbital Precision Strike',{present=present,
  exclude={'Orbital 120mm HE Barrage'},payload={donor='Orbital 120mm HE Barrage'}})
 item.chosen=found.chosen and found.chosen.name
 item.eligible={}
 for _,c in ipairs(found.candidates)do if c.eligible then item.eligible[#item.eligible+1]=c.name end end
 item.strikeRejected=false
 for _,c in ipairs(found.candidates)do
  if c.name=='Orbital Airburst Strike'then item.strikeRejected=not c.eligible end
 end
 local order={}
 local picks={}
 for _,entry in ipairs(record.entries)do if entry.granted==0 then picks[#picks+1]=entry end end
 local virtual_at
 for k,entry in ipairs(picks)do
  if entry==seeded then virtual_at=k end
  order[k]=entry==seeded and PRECISION or loadout.id_of(world,entry.type)
 end
 local conv=settle(slots.convert_virtual({definition='orbital_gas_barrage',token='Orbital Precision Strike',
  carrier=item.chosen,slots={virtual_at-1},order=order}))
 item.conversion=conv.status
 -- A wrong-family carrier (a strike): refused before anything.
 first=#writes
 local wrong=settle(payload.apply({carrier='Orbital Airburst Strike'}))
 item.wrongFamily,item.wrongWrites=wrong.code,#writes-first
 -- An instance of the carrier's payload (seeded in the manager): refused.
 local carrier=D.records[tostring(found.chosen.id)]
 local manager=b.pointer(source.read(world.game+D.manager.global,8),0)
 local fake=next_block;next_block=next_block+0x1000
 blocks[fake]=b.unhex(carrier.payload:gsub('^0x','')):reverse()..string.rep('\0',8)
 local list=next_block;next_block=next_block+0x1000
 local function u64(n)
  local out={}
  for k=0,7 do out[k+1]=string.char(math.floor(n/256^k)%256)end
  return table.concat(out)
 end
 blocks[list]=u64(fake)
 local saved_count=source.read(manager+D.manager.instances,4)
 local saved_handles=source.read(manager+D.manager.handles,8)
 overlay[manager+D.manager.instances]=string.char(1,0,0,0)
 overlay[manager+D.manager.handles]=u64(list)
 first=#writes
 local busy=settle(payload.apply({carrier=item.chosen}))
 item.busy,item.busyWrites,item.busyReason=busy.code,#writes-first,busy.reason
 overlay[manager+D.manager.instances]=nil;overlay[manager+D.manager.handles]=nil
 -- The write.
 local inspected=payload.inspect(world,item.chosen)
 local before=world.view.read(inspected.address,192)
 local donor_before=world.view.read(payload.inspect(world,'Orbital 120mm HE Barrage').address,192)
 first=#writes
 local applied=settle(payload.apply({carrier=item.chosen}))
 item.status,item.code,item.reason=applied.status,applied.code,applied.reason
 item.writes=#writes-first
 item.verify=applied.verify
 local outside=0
 for i=first+1,#writes do
  local at=writes[i].address
  if not(at>=inspected.address and at+#writes[i].bytes<=inspected.address+192)then outside=outside+1 end
 end
 item.outside=outside
 local now=payload.inspect(world,item.chosen)
 item.desired,item.shells,item.shellCount=now.desired,now.shells,now.shellCount
 item.shellDelay,item.salvoDelay,item.scatter=now.shellDelay[1],now.salvoDelay[1],now.scatter
 item.donorVanilla=world.view.read(payload.inspect(world,'Orbital 120mm HE Barrage').address,192)==donor_before
 -- A running barrage of the carrier refuses the restore.
 overlay[manager+D.manager.instances]=string.char(1,0,0,0)
 overlay[manager+D.manager.handles]=u64(list)
 first=#writes
 local held=settle(payload.restore())
 item.restoreBusy,item.restoreBusyWrites=held.code,#writes-first
 overlay[manager+D.manager.instances]=nil;overlay[manager+D.manager.handles]=nil
 first=#writes
 local restored=settle(payload.restore())
 item.restore,item.restoreExact,item.restoreWrites=restored.status,restored.exact,#writes-first
 item.identical=world.view.read(inspected.address,192)==before
 item.vanillaAgain=payload.inspect(world,item.chosen).vanilla
 item.donorStill=world.view.read(payload.inspect(world,'Orbital 120mm HE Barrage').address,192)==donor_before
 local back=settle(slots.restore())
 item.conversionRestore=back.status
 -- The proof's own path: the conversion and the payload in one tick (stratagem_selector.convert_with_payload).
 local virtual=require('hd2runtime/runtime/virtual_stratagems')
 local selector=require('hd2runtime/runtime/stratagem_selector')
 virtual.reset_for_tests();selector.reset_for_tests()
 local texts=require('hd2runtime/runtime/text_resources')
 local NAME=texts.handle('gb_name','ORBITAL GAS BARRAGE','mods/validation/payload')
 local ICON=require('hd2runtime/runtime/image_resources').handle('gb_icon','mods/validation/payload')
 virtual.define({id='orbital_gas_barrage',display={name=NAME,description=NAME,icon=ICON},
  selection={token='Orbital Precision Strike'},mission={discover=true,exclude={'Orbital 120mm HE Barrage'}},
  payload={donor='Orbital 120mm HE Barrage'}},'mods/validation/payload')
 selector.set_virtual_slots_for_tests({slots={[virtual_at-1]={definition='orbital_gas_barrage',token=PRECISION,
  type=token_type}},pairs=order})
 local entry_at=seeded.address
 local observed,bad=0,0
 local probe={status='active'}
 function probe.tick()
  if b.u32(adapter.read(entry_at,4),0)==found.chosen.type then
   observed=observed+1
   if not payload.inspect(world,item.chosen).desired then bad=bad+1 end
  end
 end
 require('hd2runtime/runtime/scheduler').attach(probe)
 first=#writes
 local combined=settle(selector.convert_with_payload('orbital_gas_barrage',nil,item.chosen))
 probe.status='complete'
 item.combined,item.combinedCode=combined.status,combined.code
 item.combinedWrites=#writes-first
 item.combinedDesired=payload.inspect(world,item.chosen).desired
 item.combinedObserved,item.combinedBad=observed,bad
 local combined_restore=settle(payload.restore())
 item.combinedRestore,item.combinedExact=combined_restore.status,combined_restore.exact
 item.combinedConversionRestore=settle(slots.restore()).status
 item.combinedVanilla=payload.inspect(world,item.chosen).vanilla
 -- Stage C: the Gas Strike's shell on the 120mm pattern, the same combined step.
 virtual.reset_for_tests();selector.reset_for_tests()
 virtual.define({id='orbital_gas_barrage',display={name=NAME,description=NAME,icon=ICON},
  selection={token='Orbital Precision Strike'},mission={discover=true,exclude={'Orbital 120mm HE Barrage'}},
  payload={donor='Orbital 120mm HE Barrage',shells='Orbital Gas Strike'}},'mods/validation/payload')
 selector.set_virtual_slots_for_tests({slots={[virtual_at-1]={definition='orbital_gas_barrage',token=PRECISION,
  type=token_type}},pairs=order})
 local observed_c,bad_c=0,0
 local probe_c={status='active'}
 function probe_c.tick()
  if b.u32(adapter.read(entry_at,4),0)==found.chosen.type then
   observed_c=observed_c+1
   if not payload.inspect(world,item.chosen,nil,'Orbital Gas Strike').desired then bad_c=bad_c+1 end
  end
 end
 require('hd2runtime/runtime/scheduler').attach(probe_c)
 first=#writes
 local gas=settle(selector.convert_with_payload('orbital_gas_barrage',nil,item.chosen))
 probe_c.status='complete'
 item.gas,item.gasCode,item.gasReason=gas.status,gas.code,gas.reason
 item.gasWrites=#writes-first
 local now_c=payload.inspect(world,item.chosen,nil,'Orbital Gas Strike')
 item.gasShells,item.gasShellCount,item.gasDesired=now_c.shells,now_c.shellCount,now_c.desired
 item.gasShellDelay,item.gasSalvoDelay,item.gasScatter=now_c.shellDelay[1],now_c.salvoDelay[1],now_c.scatter
 item.gasPerSalvo,item.gasSalvos=now_c.perSalvo,now_c.salvos
 item.gasObserved,item.gasBad=observed_c,bad_c
 local donors_c=payload.donors(world,'Orbital Gas Strike')
 item.gasDonors={pattern=donors_c.pattern,shells=donors_c.shells,chain=donors_c.chain}
 local gas_restore=settle(payload.restore())
 item.gasRestore,item.gasExact=gas_restore.status,gas_restore.exact
 item.gasRestoreDonors=gas_restore.donors and{pattern=gas_restore.donors.pattern,shells=gas_restore.donors.shells}
 item.gasConversionRestore=settle(slots.restore()).status
 item.gasVanilla=payload.inspect(world,item.chosen).vanilla
 overlay[seeded.address]=nil
 item.savedCount=saved_count and b.u32(saved_count,0)
end
local reopened=0
for page,value in pairs(pages)do if value~=(query(page)or{}).protect then reopened=reopened+1 end end
item.pagesLeftOpen=reopened
item.protections=protections
out.payload=item
return json.encode(out)
'''


def validate(snapshots=SNAPSHOTS):
    results = {}
    for name in snapshots:
        report = json.loads(snapshot_regions.run_lua(BODY, build_profile.snapshot_directory() / name))
        phase = MISSION.get(name, 'ship')
        problems = []
        if not report['pins']:
            problems.append('the bombardment reader pins do not prove')
        compatible = sorted(r['name'] for r in report['records'] if r.get('compatible'))
        if compatible != ['Orbital 380mm HE Barrage', 'Orbital Napalm Barrage', 'Orbital Walking Barrage']:
            problems.append('compatible carriers %r' % compatible)
        for r in report['records']:
            if not (r.get('record') == r.get('reviewedRecord') and r.get('indexRow') == r.get('reviewedRow')
                    and r.get('owners') == 1 and r.get('rowsListing') == 1 and r.get('rowType') and r.get('ownRow')
                    and r.get('vanilla') and r.get('size') == 192 and r.get('instances') == 0 and r.get('total') == 0
                    and r.get('variant') is False and r.get('shellCount')):
                problems.append('record %r' % r)
        item = report['payload']
        if phase in ('alive', 'reinforced'):
            verify = item.get('verify') or {}
            words = 6 if item.get('chosen') == 'Orbital 380mm HE Barrage' else None
            if not (item['early'] == 'NOT_CONVERTED' and item['earlyWrites'] == 0
                    and item.get('chosen') == 'Orbital 380mm HE Barrage' and item.get('strikeRejected')
                    and item.get('conversion') == 'converted'
                    and item.get('wrongFamily') == 'NOT_COMPATIBLE' and item.get('wrongWrites') == 0
                    and item.get('busy') == 'IN_USE' and item.get('busyWrites') == 0
                    and item.get('status') == 'applied' and item.get('writes') == words and item.get('outside') == 0
                    and verify.get('record') and verify.get('donor') and verify.get('shellCount') == 3
                    and verify.get('nonTarget') and item.get('desired') and item.get('shells') == [194, 137, 137]
                    and item.get('shellCount') == 3 and abs(item.get('shellDelay', 0) - 0.75) < 1e-6
                    and abs(item.get('salvoDelay', 0) - 2) < 1e-6 and abs(item.get('scatter', 0) - 27) < 1e-6
                    and item.get('donorVanilla')
                    and item.get('restoreBusy') == 'IN_USE' and item.get('restoreBusyWrites') == 0
                    and item.get('restore') == 'restored' and item.get('restoreExact') and item.get('restoreWrites') == words
                    and item.get('identical') and item.get('vanillaAgain') and item.get('donorStill')
                    and item.get('conversionRestore') == 'restored' and item.get('pagesLeftOpen') == 0
                    and item.get('cooldownEnd') and item.get('combined') == 'applied'
                    and item.get('combinedWrites') == 1 + words and item.get('combinedDesired')
                    and item.get('combinedBad') == 0 and item.get('combinedRestore') == 'restored'
                    and item.get('combinedExact') and item.get('combinedConversionRestore') == 'restored'
                    and item.get('combinedVanilla')
                    and item.get('gas') == 'applied' and item.get('gasWrites') == 7
                    and item.get('gasShells') == [197, 197, 197] and item.get('gasShellCount') == 3
                    and item.get('gasDesired') and item.get('gasPerSalvo') == 3 and item.get('gasSalvos') == 5
                    and abs(item.get('gasShellDelay', 0) - 0.75) < 1e-6 and abs(item.get('gasSalvoDelay', 0) - 2) < 1e-6
                    and abs(item.get('gasScatter', 0) - 27) < 1e-6 and item.get('gasBad') == 0
                    and item.get('gasDonors') == {'pattern': True, 'shells': True, 'chain': True}
                    and item.get('gasRestore') == 'restored' and item.get('gasExact')
                    and item.get('gasRestoreDonors') == {'pattern': True, 'shells': True}
                    and item.get('gasConversionRestore') == 'restored' and item.get('gasVanilla')):
                problems.append('payload %r' % item)
        elif not (item['early'] in ('NOT_IN_MISSION', 'NOT_CONVERTED') and item['earlyWrites'] == 0
                and item.get('pagesLeftOpen') == 0):
            problems.append('payload outside a mission %r' % item)
        results[name] = {'phase': phase, 'passed': not problems, 'problems': problems,
            'summary': {'compatible': compatible, 'payload': {k: v for k, v in item.items() if k != 'verify'}}}
        print(('PASS' if not problems else 'FAIL'), name, '(%s)' % phase, json.dumps(results[name]['summary'])[:600])
        for problem in problems:
            print('   ', problem[:1500])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='append')
    args = parser.parse_args()
    results = validate(args.snapshot or SNAPSHOTS)
    OUTPUT.write_text(json.dumps(results, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    sys.exit(0 if all(r['passed'] for r in results.values()) else 1)


if __name__ == '__main__':
    main()
