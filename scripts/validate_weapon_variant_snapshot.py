"""Validate the weapon VARIANT (runtime/weapon_clone.lua variant_body, domains/weapon_variants.lua) on every retained
snapshot (no game process; game memory is only read; writes go to a copy-on-write overlay with page protection
emulated: the adapter of scripts/validate_weapon_clone_snapshot.py).

The production module runs against the snapshot's real entity region, game.dll and resource table:

* the clone pins and the UnitPath consumer pins prove on the real game.dll; the M-1000 Maxigun's four records are where
  the research found them, one owner each, their exact native bytes;
* in a live mission: the presentation-only variant applies through one guarded transaction (the members read the
  native values when no name / icon is given: nothing changes), then restores exactly;
* the ROUND (the LAS-58 Talon's 144): as the snapshot is, its package is resident only when someone brought a Talon
  (ROUND_NOT_RESIDENT, nothing written); with it simulated resident ProjType = 144, every other byte of the records
  unchanged, exact restore;
* the MODEL: as the snapshot is, the mod's unit is not loaded (MODEL_NO_BUILD_RECORD / MODEL_NOT_RESIDENT, nothing
  written); with a build record and the three resources simulated loaded, UnitPath = the model's unit name hash, every
  other byte unchanged, exact restore;
* the guards: CONFLICT on restore, NOT_NATIVE, CARRIER_PRESENT; aboard the ship NOT_IN_MISSION.
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
import validate_weapon_clone_snapshot as clone_validator  # noqa: E402

OUTPUT = ROOT / 'validation/weapon-variant-snapshot.json'
_ADAPTER = clone_validator.BODY[:clone_validator.BODY.index('world_module.set_runtime(adapter)')]

BODY = _ADAPTER + r'''
world_module.set_runtime(adapter)
local V=require('hd2runtime/domains/weapon_variants')
local models=require('hd2runtime/runtime/model_resources')
local core_assets=require('hd2runtime/core/assets')
local world,why=world_module.open()
assert(world,why)
local HOST='M-1000 Maxigun'
local c=V.hosts[HOST]
local out={}
local proven,pwhy=clone.prove(world)
local uproven,uwhy=clone.prove_model_consumers(world)
out.pins={proven=proven==true,reason=pwhy,unit=uproven==true,unitReason=uwhy,unitCount=#V.unitPins}
local game=world_module.game_state(world)
out.mission=game and game.mission==true or false
out.players=#(world_module.players(world)or{})
local em=b.pointer(source.read(world.game+D.entityManager,8),0)
local region_base
for name,comp in pairs(D.components)do
 local at=b.pointer(source.read(em+comp.slot,8),0)
 region_base=region_base or(at-comp.offset-28)
end
local function record_at(name,index)
 local comp=D.components[name]
 return region_base+comp.offset+28+comp.record_offset+index*comp.stride,comp.stride
end
local function records()
 local list={}
 for name,r in pairs(c.records)do
  local at,size=record_at(name,r.recordIndex)
  list[#list+1]={name=name,at=at,size=size,fnv=r.fnv1a}
 end
 table.sort(list,function(a,x)return a.at<x.at end)
 return list
end
local function native_all()
 for _,r in ipairs(records())do if clone.fnv1a(adapter.read(r.at,r.size))~=r.fnv then return false,r.name end end
 return true
end
local function reset()overlay={};protection={};writes={};counts.writes=0;counts.protections=0;clone.reset_for_tests()end
local function snapshot_records()
 local before={}
 for _,r in ipairs(records())do before[r.name]=adapter.read(r.at,r.size)end
 return before
end
local function member_at(member)return record_at(member.component,c.records[member.component].recordIndex)+member.offset end
-- What one conversion changed: every member in `expect` reads its value, nothing else of the records changed.
local function check(before,expect)
 local res={writes=#writes}
 local allowed={}
 for _,e in ipairs(expect)do
  for k=0,#e.value-1 do allowed[e.at+k]=true end
  if adapter.read(e.at,#e.value)~=e.value then res.mismatch=(res.mismatch or 0)+1 end
 end
 local outside,other=0,0
 for _,w in ipairs(writes)do for k=0,#w.bytes-1 do if not allowed[w.address+k]then outside=outside+1 end end end
 for _,r in ipairs(records())do
  local now=adapter.read(r.at,r.size)
  for k=1,r.size do if now:byte(k)~=before[r.name]:byte(k)and not allowed[r.at+k-1]then other=other+1 end end
 end
 res.outside,res.otherBytesChanged,res.protectionRestored=outside,other,next(protection)==nil
 local applied=#writes
 local r=settle(clone.restore(nil,HOST))
 res.restore={status=r.status,code=r.code,exact=r.verify and r.verify.exact,writes=#writes-applied}
 res.nativeAfter=native_all()
 local identical=true
 for _,rec in ipairs(records())do if adapter.read(rec.at,rec.size)~=before[rec.name]then identical=false end end
 res.identical=identical and next(protection)==nil
 return res
end
local multiplayer=out.players>1 or nil
out.native=native_all()
out.instances=clone.instances(world,c.entity)
-- 1. Presentation only (no name / icon given: the native values; nothing to write).
reset()
local before=snapshot_records()
local h=settle(clone.apply({carrier=HOST,variant=true,multiplayer=multiplayer}))
out.presentation={status=h.status,code=h.code,reason=h.reason,writes=#writes}
if h.status=='applied'then
 local e={}
 for _,p in ipairs(c.presentation)do e[#e+1]={at=member_at(p),value=b.unhex(p.native)}end
 for k,v in pairs(check(before,e))do out.presentation[k]=v end
end
-- 2. The Talon round: as the snapshot is, then with its package resident.
local A=require('hd2runtime/domains/attack_outputs')
local talon=A.outputs['output/v1/projectile/las-58-talon']
local dep=core_assets.dependency(talon.dependencyKey)
local ROUND={type=talon.currentDefault,package=dep.package,label='LAS-58 Talon'}
local function real_state(id)
 local hook=adapter.package_state;adapter.package_state=nil
 local ok,state=pcall(core_assets.state,adapter,id)
 adapter.package_state=hook
 return ok and state or('error: '..tostring(state))
end
out.round={type=ROUND.type,packageState=real_state(ROUND.package)}
if out.mission then
 reset()
 local asis=settle(clone.apply({carrier=HOST,variant=true,round=ROUND,multiplayer=multiplayer}))
 out.round.asIs={status=asis.status,code=asis.code,writes=#writes}
 if asis.status=='applied'then settle(clone.restore(nil,HOST))end
 adapter.package_state=function(id)if id==ROUND.package then return'resident'end;return real_state(id)end
 reset()
 before=snapshot_records()
 local hr=settle(clone.apply({carrier=HOST,variant=true,round=ROUND,multiplayer=multiplayer}))
 out.round.resident={status=hr.status,code=hr.code,reason=hr.reason}
 if hr.status=='applied'then
  out.round.resident.projtype=b.u32(adapter.read(member_at(c.round),4),0)
  local e={{at=member_at(c.round),value=b.encode(ROUND.type,'u32')}}
  for k,v in pairs(check(before,e))do out.round.resident[k]=v end
 end
 adapter.package_state=nil
end
-- 3. The model: as the snapshot is (not loaded), then a build record and its resources simulated loaded.
local OWNER='mods/validation/laser_maxigun'
package.loaded[OWNER..'/hd2runtime_models']=nil
models.reset_for_tests()
local handle=models.handle('laser_maxigun',OWNER)
out.model={unit=models.unit_hex(handle)}
if out.mission then
 reset()
 local asis=settle(clone.apply({carrier=HOST,variant=true,model=handle,multiplayer=multiplayer}))
 out.model.asIs={status=asis.status,code=asis.code,writes=#writes}
 local names=models.names(OWNER,'laser_maxigun')
 package.loaded[OWNER..'/hd2runtime_models']={format=1,models={laser_maxigun={base=HOST,archive=V.models[HOST].archive,
  build=V.source.build,baseUnit=c.model.unit,baseUnitSha256=V.models[HOST].unit.mainSha256,unit=names.unit,
  material=names.material,lut=names.lut,palette='debug',sha256={unit='x',material='x',lut='x'}}}}
 models.reset_for_tests()
 local real_loaded=images.loaded
 local loaded={[names.unit]=true,[names.material]=true,[names.lut]=true}
 -- Only the model's three names are simulated loaded; the real resource table is read first (it must be readable).
 images.loaded=function(runtime,kind,name)
  local ok,why=real_loaded(runtime,kind,name)
  if loaded[name]then return true end
  return ok,why
 end
 local notloaded=settle(clone.apply({carrier=HOST,variant=true,model=handle,multiplayer=multiplayer}))
 out.model.realTable={status=notloaded.status,code=notloaded.code}
 if notloaded.status=='applied'then settle(clone.restore(nil,HOST))end
 reset()
 before=snapshot_records()
 local hm=settle(clone.apply({carrier=HOST,variant=true,model=handle,multiplayer=multiplayer}))
 out.model.loaded={status=hm.status,code=hm.code,reason=hm.reason}
 if hm.status=='applied'then
  out.model.loaded.unitPath=string.format('0x%08X%08X',b.u32(adapter.read(member_at(c.model)+4,4),0),
   b.u32(adapter.read(member_at(c.model),4),0))
  local e={{at=member_at(c.model),value=models.unit_bytes(handle)}}
  for k,v in pairs(check(before,e))do out.model.loaded[k]=v end
 end
 -- Round and model together.
 adapter.package_state=function(id)if id==ROUND.package then return'resident'end;return real_state(id)end
 reset()
 before=snapshot_records()
 local hb=settle(clone.apply({carrier=HOST,variant=true,round=ROUND,model=handle,multiplayer=multiplayer}))
 out.both={status=hb.status,code=hb.code,reason=hb.reason}
 if hb.status=='applied'then
  local e={{at=member_at(c.round),value=b.encode(ROUND.type,'u32')},{at=member_at(c.model),value=models.unit_bytes(handle)}}
  for k,v in pairs(check(before,e))do out.both[k]=v end
 end
 -- CONFLICT on restore: a third party changed the written UnitPath.
 reset()
 local hc=settle(clone.apply({carrier=HOST,variant=true,round=ROUND,model=handle,multiplayer=multiplayer}))
 if hc.status=='applied'then
  local st=clone.state(HOST)
  local ch=st.changes[#st.changes]
  overlay[ch.owner.base+ch.offset]=string.rep('\0',#ch.desired)
  local w0=#writes
  local refused=settle(clone.restore(nil,HOST))
  local none=#writes==w0
  overlay[ch.owner.base+ch.offset]=ch.desired
  local back=settle(clone.restore(nil,HOST))
  out.conflict={status=refused.status,code=refused.code,writesWhileRefused=none,thenRestored=back.status,
   exact=back.verify and back.verify.exact}
 else out.conflict={status=hc.status,code=hc.code,reason=hc.reason}end
 adapter.package_state=nil
 images.loaded=real_loaded
 -- NOT_NATIVE: one byte of a record (not a member) changed before the mission.
 reset()
 local rec=records()[1]
 overlay[rec.at+rec.size-1]=string.char((adapter.read(rec.at+rec.size-1,1):byte()+1)%256)
 local nn=settle(clone.apply({carrier=HOST,variant=true,multiplayer=multiplayer}))
 out.notNative={status=nn.status,code=nn.code,writes=#writes}
 -- CARRIER_PRESENT: an entity of the Maxigun type already in the world.
 reset()
 local S=D.spottableInstances
 local manager=b.pointer(source.read(world.game+S.global,8),0)
 local count=manager~=0 and b.u32(source.read(manager+S.count,4),0)or 0
 if count>0 then
  local handles=b.pointer(source.read(manager+S.handles,8),0)
  local h0=b.pointer(source.read(handles,8),0)
  local hex=c.entity:gsub('^0x','')
  local hi,lo=tonumber(hex:sub(1,8),16),tonumber(hex:sub(9,16),16)
  local function u32le(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
  overlay[h0+S.handleType]=u32le(lo)..u32le(hi)
  local cp=settle(clone.apply({carrier=HOST,variant=true,multiplayer=multiplayer}))
  out.present={status=cp.status,code=cp.code,writes=#writes}
 end
end
reset()
return json.encode(out)
'''


def problems_of(report: dict, phase: str) -> list[str]:
    problems = []
    if not report['pins']['proven']:
        problems.append('clone pins: %s' % report['pins']['reason'])
    if not report['pins']['unit']:
        problems.append('UnitPath consumer pins: %s' % report['pins']['unitReason'])
    if not report['native']:
        problems.append('the Maxigun records are not native in the snapshot')
    live = phase in ('alive', 'reinforced')
    p = report['presentation']
    if not live:
        if not (p['status'] == 'refused' and p['code'] == 'NOT_IN_MISSION' and p['writes'] == 0):
            problems.append('outside a live mission: %r' % p)
        return problems
    if report['instances'] != 0:
        problems.append('Maxigun entities exist in the snapshot (%r)' % report['instances'])

    def ok(res, label, writes):
        if res.get('status') != 'applied':
            problems.append('%s: %r' % (label, res))
            return
        if res['writes'] < writes or res.get('mismatch') or res['outside'] or res['otherBytesChanged'] \
                or not res['protectionRestored']:
            problems.append('%s: the conversion: %r' % (label, res))
        if not (res['restore']['status'] == 'restored' and res['restore']['exact'] and res['nativeAfter']
                and res['identical']):
            problems.append('%s: the restore: %r' % (label, res['restore']))
    ok(p, 'presentation', 0)
    r = report['round']
    if r['packageState'] != 'resident' and not (r['asIs']['status'] == 'refused' and r['asIs']['code'] ==
            'ROUND_NOT_RESIDENT' and r['asIs']['writes'] == 0):
        problems.append('round as the snapshot is: %r' % r['asIs'])
    ok(r['resident'], 'round', 1)
    if r['resident'].get('projtype') != 144:
        problems.append('round: ProjType %r' % r['resident'].get('projtype'))
    m = report['model']
    if not (m['asIs']['status'] == 'refused' and m['asIs']['code'] == 'MODEL_NO_BUILD_RECORD' and m['asIs']['writes'] == 0):
        problems.append('model as the snapshot is: %r' % m['asIs'])
    ok(m['loaded'], 'model', 1)
    if m['loaded'].get('unitPath') != m['unit']:
        problems.append('model: UnitPath %r, expected %r' % (m['loaded'].get('unitPath'), m['unit']))
    ok(report['both'], 'round and model', 2)
    cf = report['conflict']
    if not (cf.get('status') == 'refused' and cf.get('code') == 'CONFLICT' and cf['writesWhileRefused']
            and cf['thenRestored'] == 'restored' and cf['exact']):
        problems.append('conflict: %r' % cf)
    nn = report['notNative']
    if not (nn['status'] == 'refused' and nn['code'] == 'NOT_NATIVE' and nn['writes'] == 0):
        problems.append('not native: %r' % nn)
    cp = report.get('present')
    if cp and not (cp['status'] == 'refused' and cp['code'] == 'CARRIER_PRESENT' and cp['writes'] == 0):
        problems.append('carrier present: %r' % cp)
    return problems


def validate(snapshots=SNAPSHOTS):
    results = {}
    for name in snapshots:
        report = json.loads(snapshot_regions.run_lua(BODY, build_profile.snapshot_directory() / name))
        phase = MISSION.get(name, 'ship')
        problems = problems_of(report, phase)
        results[name] = {'phase': phase, 'passed': not problems, 'problems': problems, 'report': report}
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('snapshots', nargs='*')
    args = parser.parse_args(argv)
    names = tuple(args.snapshots) or tuple(n for n in SNAPSHOTS if (build_profile.snapshot_directory() / n).is_file())
    results = validate(names)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=1) + '\n', encoding='utf-8')
    for name, r in results.items():
        print(('PASS' if r['passed'] else 'FAIL'), r['phase'], name, '; '.join(r['problems']))
    if not all(r['passed'] for r in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
