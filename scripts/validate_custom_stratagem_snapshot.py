"""Validate the custom stratagem P0 write on every retained snapshot (no game process; game memory is only read).

For each snapshot the production modules (runtime/event_world.lua, runtime/custom_stratagem.lua, core/stratagem.lua,
core/guarded_transaction.lua) run exactly as in game against the snapshot's memory, with an adapter whose writes go to
a copy-on-write overlay and whose Runtime-owned blocks are a Lua overlay at addresses no module maps:

* the calldown reader pins prove on the snapshot's game.dll;
* the Orbital 120mm HE Barrage row resolves from its catalogue id: StratagemType 136, its native code Right Right
  Down Left Right Down, its array inside the StratagemSettings allocation;
* in a mission as host with a local avatar, P0 applies through the guarded transaction on the real allocation (its
  real region, protection and bytes): exactly two writes (+0x48 = 4, then +0x40 = the Runtime-owned block), the row
  reads back Up Up Down Down, and nothing else in the 80 KB of settings changes;
* restore writes the original pointer, then the original count, and the settings are byte-identical again;
* the same before the Helldiver exists: with the local player's avatar network id overlaid as none (the member the
  HUD's stratagem list gates on), P0 applies with the same two writes, reports no avatar at the write, and restores
  byte-identical; nothing in the write depends on the avatar;
* aboard the ship and after the mission, P0 is refused (NOT_IN_MISSION) and nothing is written, with or without an
  avatar.
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

OUTPUT = ROOT / 'validation/custom-stratagem-snapshot.json'

BODY = r'''
local json=require('hd2runtime/primary_mapper/json')
local world_module=require('hd2runtime/runtime/event_world')
local custom=require('hd2runtime/runtime/custom_stratagem')
local scheduler=require('hd2runtime/runtime/scheduler')
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
local function settle(job)for _=1,400 do if job.status~='pending'then break end;update(0.1)end;return job end
world_module.set_runtime(adapter)
local world,why=world_module.open()
assert(world,why)
-- The StratagemSettings allocation as the game holds it.
local base=b.pointer(source.read(world.game+profile.stratagem.buffer_rva,8),0)
local region=source.query(base)
local function settings()return adapter.read(base,profile.stratagem.size)end
local out={}
local proven,reason=custom.prove(world)
out.pins={proven=proven==true,reason=reason}
local read=settle(custom.read())
out.read={status=read.status,code=read.code,reason=read.reason,type=read.type,id=read.id,count=read.count,
 sequence=read.sequence and custom.names(read.sequence),insideSettings=read.pointer and read.pointer>=base
  and read.pointer<base+region.size}
out.region={protect=region.protect,type=region.type,size=region.size}
local before=settings()
-- P0 before the Helldiver exists: the local player's avatar network id reads as none (0x7FFF, an overlay on the member
-- the HUD's stratagem list gates on), every other byte as in the snapshot.
local natives=require('hd2runtime/domains/event_natives')
local P,A=natives.players,natives.playerAvatars
local avatar_slot
for _,player in ipairs(world_module.players(world))do
 if player['local']then
  avatar_slot=b.pointer(source.read(world.game+P.global,8),0)+A.avatarId+player.slot*A.avatarIdStride
 end
end
out.beforeAvatar={hidden=avatar_slot~=nil,avatarBefore=custom.local_avatar(world).present}
if avatar_slot then overlay[avatar_slot]=string.char(0xFF,0x7F,0,0)end
out.beforeAvatar.avatarHidden=custom.local_avatar(world).present
local early=settle(custom.apply())
out.beforeAvatar.status,out.beforeAvatar.code,out.beforeAvatar.reason=early.status,early.code,early.reason
out.beforeAvatar.avatarAtWrite=early.avatar and early.avatar.present
out.beforeAvatar.writes={}
for _,item in ipairs(writes)do out.beforeAvatar.writes[#out.beforeAvatar.writes+1]={offset=item.address-base,
 width=#item.bytes,value=b.hex(item.bytes)}end
if early.status=='applied'then
 out.beforeAvatar.readBack=custom.names(settle(custom.read()).sequence)
 local restored=settle(custom.restore())
 out.beforeAvatar.restored=restored.status
end
out.beforeAvatar.totalWrites=#writes
out.beforeAvatar.identical=settings()==before
-- Then the same snapshot as it is (the Helldiver exists in the mission snapshots): the original P0 case.
if avatar_slot then overlay[avatar_slot]=nil end
for index=#writes,1,-1 do writes[index]=nil end
local applied=settle(custom.apply())
out.apply={status=applied.status,code=applied.code,reason=applied.reason,
 avatarAtWrite=applied.avatar and applied.avatar.present}
if applied.status=='applied'then
 local row=applied.original and nil
 out.apply.writes={}
 for _,item in ipairs(writes)do out.apply.writes[#out.apply.writes+1]={offset=item.address-base,width=#item.bytes,
  value=b.hex(item.bytes)}end
 out.apply.blockOwned=blocks[applied.custom.pointer]~=nil
 out.apply.report={status=applied.report.status,writes=applied.report.writes,
  nonTarget=applied.report.non_target_bytes_unchanged,protectionRestored=applied.report.protection_restored}
 local after=settle(custom.read())
 out.apply.readBack=custom.names(after.sequence)
 out.apply.runtimeOwned=after.runtime_owned
 local now,differing=settings(),{}
 for i=1,#now do if now:byte(i)~=before:byte(i)then differing[#differing+1]=i-1 end end
 out.apply.differing=differing
 out.apply.rowOffset=custom.state().row_address-base
 local restored=settle(custom.restore())
 out.restore={status=restored.status,code=restored.code,reason=restored.reason,writes=#writes,
  identical=settings()==before}
 out.restore.order={}
 for index=3,#writes do out.restore.order[#out.restore.order+1]={offset=writes[index].address-base,
  width=#writes[index].bytes}end
else
 out.apply.writes=#writes
end
-- The HUD refresh on the real stratagem list. The 120mm is not in these loadouts, so the first catalogued stratagem
-- in the list gets a Runtime-owned code through P0's own apply; its slot is redrawn, then restored and redrawn back.
local hud_module=require('hd2runtime/runtime/stratagem_hud')
local H=require('hd2runtime/domains/stratagem_calldown').hud
local catalog=require('hd2runtime/domains/stratagem_authoring')
local proven_hud,why_hud=hud_module.prove(world)
out.hud={pins={proven=proven_hud==true,reason=why_hud}}
local state_now=world_module.game_state(world)
if not(state_now and state_now.mission)then
 local located,code=hud_module.locate(world,136)
 out.hud.locate=located and'located'or code
else
 local hud=b.pointer(source.read(world.game+H.global,8),0)
 local chosen
 for index=0,H.slots.count-1 do
  local kind=b.u32(source.read(hud+H.pathOffset+index*H.slots.stride+H.slots.type,4),0)
  if not chosen and kind~=0 then
   local row=b.pointer(source.read(world.game+profile.stratagem.table_rva+kind*8,8),0)
   local id=b.u32(source.read(row+4,4),0)
   local names={}
   for name,entry in pairs(catalog.stratagems)do if entry.root and entry.root.id==id then names[#names+1]=name end end
   table.sort(names)
   if names[1]then chosen={name=names[1],kind=kind,row=row,index=index}end
  end
 end
 local native=chosen and settle(custom.read(nil,chosen.name)).sequence
 local code={1,1,3,3}
 if native and custom.names(native)=='Up Up Down Down'then code={3,3,1,1}end
 out.hud.stratagem=chosen and chosen.name;out.hud.type=chosen and chosen.kind
 local applied2=chosen and native and settle(custom.apply({stratagem=chosen.name,sequence=code,expected=native}))
 out.hud.apply=applied2 and applied2.status
 if applied2 and applied2.status=='applied'then
  local located=assert(hud_module.locate(world,chosen.kind))
  local allowed={[located.slot+H.slots.relayout]=true}
  for _,item in ipairs(located.ancestors)do allowed[item.address]=true end
  local first=located.slot+H.sprites.offset
  local last=first+H.sprites.count*H.sprites.stride
  local before=#writes
  local refreshed=settle(custom.refresh_hud())
  out.hud.slot=located.index;out.hud.ancestors=#located.ancestors
  out.hud.refresh={status=refreshed.status,code=refreshed.code,reason=refreshed.reason,
   before=refreshed.before and custom.names(refreshed.before),after=refreshed.after and custom.names(refreshed.after),
   writes=refreshed.writes and#refreshed.writes,guard=refreshed.report and refreshed.report.status}
  local outside={}
  for index=before+1,#writes do
   local at=writes[index].address
   if not((at>=first and at+#writes[index].bytes<=last)or allowed[at])then outside[#outside+1]=at end
  end
  out.hud.refresh.outside=#outside
  out.hud.refresh.drawn=custom.names(assert(hud_module.locate(world,chosen.kind)).shows)
  out.hud.native=custom.names(native);out.hud.code=custom.names(code)
  local restored2=settle(custom.restore())
  local back=settle(custom.refresh_hud())
  out.hud.back={restore=restored2.status,status=back.status,code=back.code,reason=back.reason,
   after=back.after and custom.names(back.after),writes=back.writes and#back.writes}
  local again=settle(custom.refresh_hud())
  out.hud.again=again.status
 end
end
out.protections=protections
return json.encode(out)
'''


def validate(snapshots=SNAPSHOTS):
    results = {}
    for name in snapshots:
        report = json.loads(snapshot_regions.run_lua(BODY, build_profile.snapshot_directory() / name))
        phase = MISSION.get(name, 'ship')
        problems = []
        if not report['pins']['proven']:
            problems.append('calldown reader pins: %s' % report['pins']['reason'])
        read = report['read']
        if read['status'] != 'read' or read['type'] != 136 or read['id'] != 1063322614 or read['count'] != 6 \
                or read['sequence'] != 'Right Right Down Left Right Down' or not read['insideSettings']:
            problems.append('the 120mm row: %r' % read)
        if report['region']['protect'] != 4 or report['region']['type'] != 0x20000:
            problems.append('the StratagemSettings allocation is not private read-write: %r' % report['region'])
        applied = report['apply']
        early = report['beforeAvatar']
        if phase in ('alive', 'reinforced'):
            row = applied.get('rowOffset')
            early_writes = [(w['offset'], w['width']) for w in early.get('writes') or []]
            if not (early['hidden'] and early['avatarBefore'] is True and early['avatarHidden'] is False):
                problems.append('the local avatar could not be hidden: %r' % early)
            elif early['status'] != 'applied' or early['avatarAtWrite'] is not False:
                problems.append('P0 before the Helldiver: %s %s (avatar at the write %r)' % (early.get('code'),
                    early.get('reason'), early.get('avatarAtWrite')))
            elif early_writes[:2] != [(row + 0x48, 4), (row + 0x40, 8)] or early['writes'][0]['value'] != '04000000' \
                    or early['readBack'] != 'Up Up Down Down':
                problems.append('P0 before the Helldiver wrote %r' % early['writes'])
            elif len(early_writes) != 2 or early['restored'] != 'restored' or not early['identical'] \
                    or early['totalWrites'] != 4:
                problems.append('the restore after P0 before the Helldiver: %r' % early)
            if applied.get('avatarAtWrite') is not True:
                problems.append('the snapshot\'s own Helldiver was not seen at the write')
            writes = applied.get('writes') or []
            if applied['status'] != 'applied':
                problems.append('P0 did not apply: %s %s' % (applied.get('code'), applied.get('reason')))
            elif not (len(writes) == 2 and writes[0]['offset'] == row + 0x48 and writes[0]['value'] == '04000000'
                    and writes[1]['offset'] == row + 0x40 and writes[1]['width'] == 8):
                problems.append('the P0 writes: %r' % writes)
            elif applied['readBack'] != 'Up Up Down Down' or not applied['runtimeOwned'] or not applied['blockOwned']:
                problems.append('the row does not read back the Runtime-owned Up Up Down Down')
            elif any(not (row + 0x40 <= o < row + 0x4C) for o in applied['differing']):
                problems.append('settings bytes outside +0x40..+0x4B changed: %r' % applied['differing'][:8])
            elif applied['report'] != {'status': 'APPLIED', 'writes': 2, 'nonTarget': True, 'protectionRestored': True}:
                problems.append('the guard report: %r' % applied['report'])
            restore = report.get('restore') or {}
            if applied['status'] == 'applied' and not (restore.get('status') == 'restored' and restore['identical']
                    and restore['writes'] == 4 and restore['order'] == [{'offset': row + 0x40, 'width': 8},
                    {'offset': row + 0x48, 'width': 4}]):
                problems.append('the restore: %r' % restore)
        elif applied['status'] != 'refused' or applied['code'] != 'NOT_IN_MISSION' or applied['writes']:
            problems.append('P0 outside a mission: %r' % applied)
        elif early['status'] != 'refused' or early['code'] != 'NOT_IN_MISSION' or early['writes'] \
                or not early['identical']:
            problems.append('P0 outside a mission without an avatar: %r' % early)
        hud = report['hud']
        if not hud['pins']['proven']:
            problems.append('HUD pins: %s' % hud['pins']['reason'])
        if phase in ('alive', 'reinforced'):
            refresh, back = hud.get('refresh') or {}, hud.get('back') or {}
            if hud.get('apply') != 'applied':
                problems.append('no catalogued stratagem in the HUD list took a custom code: %r' % hud)
            elif not (refresh.get('status') == 'refreshed' and refresh['before'] == hud['native']
                    and refresh['after'] == hud['code'] and refresh['drawn'] == hud['code']
                    and refresh['guard'] == 'APPLIED' and refresh['writes'] and refresh['outside'] == 0):
                problems.append('the HUD refresh: %r' % refresh)
            elif not (back.get('restore') == 'restored' and back.get('status') == 'refreshed'
                    and back['after'] == hud['native'] and hud.get('again') == 'current'):
                problems.append('the HUD refresh back: %r' % back)
        elif hud.get('locate') != 'NOT_IN_MISSION':
            problems.append('the HUD outside a mission: %r' % hud)
        if report['protections']:
            problems.append('a page protection changed on a read-write allocation')
        results[name] = {'phase': phase, 'passed': not problems, 'problems': problems, 'report': report}
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
        print(('PASS ' if result['passed'] else 'FAIL ') + name + ' (' + result['phase'] + ')' + ('' if result['passed']
            else ': ' + '; '.join(result['problems'])))
    if not summary['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
