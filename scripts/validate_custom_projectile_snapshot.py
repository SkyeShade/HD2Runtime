"""Validate Runtime-owned custom projectile rows on every retained snapshot (read-only; no game process).

For each snapshot the production modules (runtime/event_world.lua, runtime/custom_projectiles.lua,
core/projectile_rows.lua) run exactly as in game against the snapshot's memory: the world opens (build fingerprint,
image sizes, every event pin), every projectile row pin of domains/projectile_rows.lua is proven, the development
proof definition (custom_projectiles.DEVELOPMENT_PROOF) is built from the snapshot's live LAS-58 Talon, PLAS-1
Scorcher and RS-422 Railgun rows into a Runtime-owned block (an overlay of the adapter; never game memory), and the
guarded SpawnProjectile path runs inside a scheduler tick up to the native call, which is recorded and never executed.
Every component proof variant (custom_projectiles.DEVELOPMENT_VARIANTS) is built from the snapshot's real rows too: each
must be VALID and differ from row 144 only inside the members its components own.
The poses the development proof aims with are read too: the avatar's root pose must be an upright rotation and a held
weapon's pose must read; whether the weapon is in the hands (the proof's rule) is recorded.

Checks: the definition is a VALID hybrid whose only differences from row 144 are the three proof members; the three
vanilla rows are byte-identical before and after; in a mission the recorded call carries SpawnProjectile, the active
system, the Runtime-owned row, kind 2, the local avatar as source and owner and the local peer as creditor; aboard the
ship and after the mission the spawn is refused as NOT_IN_MISSION; a Runtime-owned row with a changed late-lookup
member (+0xF4) is INVALID and refused before any call (HYBRID_INCOMPATIBLE in a mission); a tampered projectile row pin refuses custom spawns. Writes: none.
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

OUTPUT = ROOT / 'validation/custom-projectile-snapshot.json'

BODY = r'''
local json=require('hd2runtime/primary_mapper/json')
local world_module=require('hd2runtime/runtime/event_world')
local custom=require('hd2runtime/runtime/custom_projectiles')
local rows=require('hd2runtime/core/projectile_rows')
local rows_domain=require('hd2runtime/domains/projectile_rows')
local scheduler=require('hd2runtime/runtime/scheduler')
local handles=require('hd2runtime/runtime/handles')
local natives=require('hd2runtime/domains/event_natives')
local b=require('hd2runtime/core/bytes')
-- The snapshot adapter plus Runtime-owned blocks (a Lua overlay at addresses no module maps) and a recorder in place
-- of the game's SpawnProjectile. Game memory is only ever read.
local adapter,blocks,next_block,calls,game_writes={},{},0x7FFE00000000,{},0
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
 return source.read(address,size)
end
function adapter.write()game_writes=game_writes+1;error('no game memory is written')end
function adapter.native_spawn_projectile(entry,system,row,x,y,z,dx,dy,dz,src,own,lo,hi,kind,layout)
 assert(blocks[row],'SpawnProjectile was given a row the Runtime does not own')
 calls[#calls+1]={entry=entry,system=system,row=row,source=src,owner=own,peer=string.format('%08X%08X',hi,lo),
  kind=kind,rowPosition=layout.row,dz=dz}
 return 0
end
local function in_update(fn)
 local out
 local watch={status='waiting'}
 function watch.cancel()watch.status='cancelled'end
 function watch.tick()out={fn()};watch.status='complete'end
 scheduler.attach(watch);update(0.1)
 return unpack(out or{})
end
world_module.set_runtime(adapter)
local world,why=world_module.open()
assert(world,why)
local out={}
local proven,reason=world_module.prove_projectile_rows(world)
out.rowPins={proven=proven==true,reason=reason,count=#rows_domain.pins}
local before={}
for _,kind in ipairs({144,142,186})do before[kind]=world_module.projectile_row(world,kind)end
out.vanillaRows={}
for _,kind in ipairs({144,142,186})do
 out.vanillaRows[tostring(kind)]={resolves=before[kind]~=nil,type=before[kind]and b.u32(before[kind],0)}
end
local def,code,why_define=custom.define(custom.DEVELOPMENT_PROOF)
out.define={ok=def~=nil,code=code,reason=why_define}
if def then
 out.define.line=custom.line(def)
 out.define.compatibility=def.validation.status
 out.define.ownedRow=blocks[def.row.address]~=nil
 local differs={}
 for offset=0,rows.SIZE-1 do
  if def.bytes:byte(offset+1)~=before[144]:byte(offset+1)then differs[#differs+1]=offset end
 end
 out.define.differingBytes=differs
 out.define.changes=custom.describe(def).changes
end
-- The newly permitted ballistics and impact-explosion members on real rows (policy only, no spawn): the Talon with
-- the R-36 Eruptor's impact explosion and the RS-422 Railgun's flight members is a VALID hybrid; a lifetime change
-- (not promoted) is not.
do
 local outputs=require('hd2runtime/domains/attack_outputs').outputs
 local eruptor=world_module.projectile_row(world,outputs['output/v1/projectile/r-36-eruptor'].currentDefault)
 out.composition={eruptorResolves=eruptor~=nil}
 if eruptor and before[186]and before[144]then
  local changes={{member='impact_explosion',bytes=eruptor:sub(0x91,0x94)}}
  for _,label in ipairs({'diameter','speed','mass','drag','gravity','lifetime_variance','penetration_slowdown'})do
   local entry=rows.copied(label)
   changes[#changes+1]={member=label,bytes=before[186]:sub(entry.offset+1,entry.offset+entry.width)}
  end
  local composed=assert(rows.apply(before[144],changes))
  local report=rows.validate(composed,before[144],144)
  out.composition.status=report.status
  out.composition.changes=#report.changes
  out.composition.impact=b.u32(composed,0x90)
  local lifetime=composed:sub(1,0x34)..eruptor:sub(0x35,0x38)..composed:sub(0x39)
  out.composition.lifetimeChange=rows.validate(lifetime,before[144],144).status
 end
end
-- The native layer inside the game update, with the local avatar and the local peer (as the action passes them).
local avatar=handles.local_avatar(world)
local lo,hi=world_module.local_peer(world)
out.avatar=avatar and avatar.id or false
-- What the development proof aims with: the avatar's root pose and, when a weapon is held, its unit pose
-- (runtime/event_world.lua unit_pose / entity_unit), and whether the weapon is in the hands by the proof's rule.
if avatar then
 local state=world_module.entity_state(world,avatar.id)
 local body=state and world_module.unit_pose(world,state.descriptor.unit)
 out.aim={avatarPose=body~=nil,upright=body~=nil and math.abs(body.up.z-1)<1e-3}
 local held=world_module.equipped(world,avatar.id)
 local unit=held and held.entity and world_module.entity_unit(world,held.entity)
 local weapon=unit and world_module.unit_pose(world,unit)
 out.aim.held=held and held.entity or false
 out.aim.weaponPose=weapon~=nil
 if body and weapon then
  local p,q,f=weapon.position,body.position,weapon.forward
  local flat=math.sqrt(f.x^2+f.y^2)
  out.aim.distance=math.sqrt((p.x-q.x)^2+(p.y-q.y)^2+(p.z-q.z)^2)
  out.aim.alignment=flat>1e-3 and(f.x*body.forward.x+f.y*body.forward.y)/flat or -1
  out.aim.inHands=out.aim.distance<=2.5 and out.aim.alignment>=0.5
 end
end
if def and avatar and lo then
 local spec={row=def.row.address,base_type=144,x=1,y=2,z=3,dx=0,dy=0,dz=-1,source=avatar.id,owner=avatar.id,
  peer_lo=lo,peer_hi=hi}
 local outside,outside_why=world_module.spawn_projectile_row(world,spec)
 out.outsideUpdate={ok=outside~=nil,reason=outside_why}
 local result,spawn_why=in_update(function()return world_module.spawn_projectile_row(world,spec)end)
 out.spawn={ok=result~=nil,reason=spawn_why,slot=result and result.slot,compatibility=result and result.report.status,
  baseUnchanged=result and result.base==def.base_row}
 local system=world.view.pointer(world.game+natives.projectile.system)
 local call=calls[#calls]
 out.call=call and{entryIsSpawn=call.entry==world.game+rows_domain.spawn.rva,systemIsGlobal=call.system==system,
  ownedRow=call.row==def.row.address,kind=call.kind,sourceIsAvatar=call.source==avatar.id,
  ownerIsAvatar=call.owner==avatar.id,peerIsLocal=call.peer==world_module.peer_hex(lo,hi),rowPosition=call.rowPosition,
  dz=call.dz}or false
 -- A Runtime-owned row whose late-lookup member differs is refused before any call.
 local tampered=def.bytes:sub(1,0xF4)..'\3\0\0\0'..def.bytes:sub(0xF9)
 local address=adapter.owned_block(rows.SIZE);adapter.owned_write(address,tampered)
 local count=#calls
 spec.row=address
 local refused,refused_why=in_update(function()return world_module.spawn_projectile_row(world,spec)end)
 out.tamperedRow={refused=refused==nil,reason=refused_why,called=#calls~=count,
  validation=rows.validate(tampered,before[144],144).status}
end
-- Every component proof variant, built from this snapshot's real rows: VALID, and different from row 144 only inside
-- the members its components own.
out.variants={}
for _,spec in ipairs(custom.DEVELOPMENT_VARIANTS)do
 local vdef,vcode,vreason=custom.define(spec)
 local item={id=spec.id,ok=vdef~=nil,code=vcode,reason=vreason}
 if vdef then
  local owned={}
  for id in pairs(spec.components)do
   for _,member in ipairs(rows.component(id).members)do
    for o=member.offset,member.offset+member.width-1 do owned[o]=true end
   end
  end
  local outside=0
  for o=0,rows.SIZE-1 do
   if not owned[o]and vdef.bytes:byte(o+1)~=before[144]:byte(o+1)then outside=outside+1 end
  end
  local differing={}
  for _,summary in ipairs(vdef.components)do if summary.differs then differing[#differing+1]=summary.id end end
  item.compatibility=vdef.validation.status
  item.outsideOwned=outside
  item.componentsDiffering=differing
  item.packages=#vdef.dependencies
  item.line=custom.line(vdef)
 end
 out.variants[#out.variants+1]=item
end
out.vanillaRowsUnchanged=true
for _,kind in ipairs({144,142,186})do
 if world_module.projectile_row(world,kind)~=before[kind]then out.vanillaRowsUnchanged=false end
end
out.gameWrites=game_writes
-- A tampered projectile row pin refuses custom spawns (the read overlay flips one byte of the first pin).
local pin=rows_domain.pins[1]
local flipped={}
for k,v in pairs(adapter)do flipped[k]=v end
function flipped.read(address,size)
 local bytes=adapter.read(address,size)
 local at=world.game+pin.rva
 if bytes and address<=at and at<address+size then
  local i=at-address+1
  bytes=bytes:sub(1,i-1)..string.char((bytes:byte(i)+1)%256)..bytes:sub(i+1)
 end
 return bytes
end
world_module.set_runtime(flipped)
local fresh=world_module.open()
local tamper_ok,tamper_why
if fresh then tamper_ok,tamper_why=world_module.prove_projectile_rows(fresh)end
out.tamperedPin={refused=fresh==nil or tamper_ok==nil,reason=tamper_why}
return json.encode(out)
'''


def validate(snapshots=SNAPSHOTS):
    results = {}
    for name in snapshots:
        report = json.loads(snapshot_regions.run_lua(BODY, build_profile.snapshot_directory() / name))
        phase = MISSION.get(name, 'ship')
        problems = []
        if not report['rowPins']['proven']:
            problems.append('projectile row pins: %s' % report['rowPins']['reason'])
        if not all(row['resolves'] and row['type'] == int(kind) for kind, row in report['vanillaRows'].items()):
            problems.append('a proof row does not resolve to its type')
        define = report['define']
        if not define['ok'] or define.get('compatibility') != 'VALID' or not define.get('ownedRow'):
            problems.append('the development proof definition: %s %s' % (define.get('code'), define.get('reason')))
        elif any(not (0x3C <= o < 0x40 or 0x48 <= o < 0x50 or 0x58 <= o < 0x5C) for o in define['differingBytes']):
            problems.append('the proof row differs from row 144 outside +0x3C, +0x48 and +0x58')
        for variant in report.get('variants') or []:
            spec_components = variant.get('componentsDiffering')
            if not variant['ok'] or variant.get('compatibility') != 'VALID' or variant.get('outsideOwned') != 0:
                problems.append('variant %s: %s %s' % (variant['id'], variant.get('code'), variant.get('reason')))
            elif not spec_components:
                problems.append('variant %s changes nothing' % variant['id'])
        if len(report.get('variants') or []) != 5:
            problems.append('expected five component proof variants')
        composition = report.get('composition') or {}
        if composition.get('status') != 'VALID' or not composition.get('impact') \
                or composition.get('lifetimeChange') != 'INVALID':
            problems.append('the real-row ballistics / impact explosion composition: %r' % composition)
        if not report['vanillaRowsUnchanged'] or report['gameWrites']:
            problems.append('a vanilla row changed or game memory was written')
        if not report['tamperedPin']['refused']:
            problems.append('a tampered projectile row pin was not refused')
        aim = report.get('aim')
        if aim and (not aim['avatarPose'] or not aim['upright'] or (aim['held'] and not aim['weaponPose'])):
            problems.append('the avatar or held weapon pose is unreadable or the avatar is not upright')
        if report['avatar'] and define['ok']:
            if report['outsideUpdate']['ok'] or 'NOT_GAME_THREAD' not in str(report['outsideUpdate']['reason']):
                problems.append('a spawn outside the game update was not refused')
            # Refused before any call: by the hybrid validation in a mission, by the inactive system elsewhere; the
            # policy itself rejects the row in every phase.
            tampered = report['tamperedRow']
            expected = 'HYBRID_INCOMPATIBLE' if phase in ('alive', 'reinforced') else 'NOT_IN_MISSION'
            if not tampered['refused'] or tampered['called'] or expected not in str(tampered['reason']) \
                    or tampered['validation'] != 'INVALID':
                problems.append('a row with a changed late-lookup member was not refused before the call')
            if phase in ('alive', 'reinforced'):
                call = report['call']
                if not report['spawn']['ok'] or not call or not all(call[k] for k in ('entryIsSpawn', 'systemIsGlobal',
                        'ownedRow', 'sourceIsAvatar', 'ownerIsAvatar', 'peerIsLocal')) or call['kind'] != 2 \
                        or call['rowPosition'] != 16 or not report['spawn']['baseUnchanged']:
                    problems.append('the in-mission spawn call: %s' % report['spawn'].get('reason'))
            elif report['spawn']['ok'] or 'NOT_IN_MISSION' not in str(report['spawn']['reason']):
                problems.append('a spawn outside a mission was not refused')
        elif phase != 'ended':
            problems.append('no local avatar or definition to spawn with')
        results[name] = {'phase': phase, 'passed': not problems, 'problems': problems, 'report': report}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='append', help='Validate only these snapshot file names')
    args = parser.parse_args()
    results = validate(tuple(args.snapshot) if args.snapshot else SNAPSHOTS)
    summary = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'writes': 0,
        'passed': all(r['passed'] for r in results.values()), 'snapshots': results}
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8', newline='\n')
    for name, result in results.items():
        print(('PASS ' if result['passed'] else 'FAIL ') + name + ('' if result['passed'] else ': '
            + '; '.join(result['problems'])))
    if not summary['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
