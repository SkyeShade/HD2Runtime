"""Validate the carrier weapon clone (runtime/weapon_clone.lua, domains/weapon_clone.lua) on every retained snapshot
(no game process; game memory is only read; writes go to a copy-on-write overlay with page protection emulated).

The production modules run against the snapshot's real entity region, game.dll and Spottable instances:

* the pins prove on the real game.dll; the game's type tables for every clone component point into the entity region;
* in a mission, for each clone host (EAT-700, EAT-411) and each level (presentation, model, full): the conversion
  applies through one guarded transaction on the real allocation (its region, PAGE_READONLY protection and bytes): every
  written member reads exactly the donor's reviewed value (or the borrowed presentation value), every other byte of the
  carrier's records and of the whole entity region is unchanged, every written record had one owner, the page
  protection is back to read-only; the restore writes exactly the captured bytes back and every record is its native
  bytes again (FNV-1a), the overlay byte-identical to the snapshot;
* the guards: a third-party change to a converted member is a CONFLICT on restore (nothing written); a carrier record
  that is not its native bytes refuses the conversion (NOT_NATIVE, nothing written); an entity of the carrier type in the
  world refuses it (CARRIER_PRESENT); aboard the ship and after the mission it is refused (NOT_IN_MISSION);
* the ROUND override (the RL-77 Airburst round on the EAT-17 clone): the engine's package list read by core/assets
  state() finds the mission package resident in a live mission (and not aboard the ship); as the snapshot is (nobody
  brought an RL-77) the round's own package is not resident: ROUND_NOT_RESIDENT, nothing written; with that package
  simulated resident (the definition's asset gate) every level on each host converts with ProjType = the round, every
  other member as without it, and restores exactly; one byte of the real projectile row changed is ROUND_CHANGED and the
  round's package absent is ROUND_NOT_RESIDENT, nothing written.
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

OUTPUT = ROOT / 'validation/weapon-clone-snapshot.json'

BODY = r'''
local json=require('hd2runtime/primary_mapper/json')
local world_module=require('hd2runtime/runtime/event_world')
local clone=require('hd2runtime/runtime/weapon_clone')
local D=require('hd2runtime/domains/weapon_clone')
local b=require('hd2runtime/core/bytes')
local images=require('hd2runtime/runtime/image_resources')
local PAGE=4096
local adapter,overlay,protection,writes={},{},{},{}
local counts={writes=0,protections=0}
for k,v in pairs(source)do adapter[k]=v end
local function original_protect(at)return source.query(at).protect end
function adapter.query(at)
 local r,why=source.query(at)
 if not r or r.allocation_base==0 then return r,why end
 if next(protection)==nil then return r end
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
function adapter.read(at,n)
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
function adapter.protect(page,size,value)
 assert(page%PAGE==0 and size==PAGE,'overlay protect extent')
 counts.protections=counts.protections+1
 local old=protection[page] or original_protect(page)
 if value==original_protect(page)then protection[page]=nil else protection[page]=value end
 return old
end
function adapter.write(at,bytes)
 assert((protection[at-at%PAGE] or original_protect(at-at%PAGE))==4,'overlay write without a writable page')
 counts.writes=counts.writes+1;writes[#writes+1]={address=at,bytes=bytes}
 -- Coalesce: a write over an earlier overlay entry of the same address replaces it.
 overlay[at]=bytes
 return true,nil,#bytes
end
local function settle(job)for _=1,4000 do if job.status~='pending'then break end;update(0.1)end;return job end
world_module.set_runtime(adapter)
local world,why=world_module.open()
assert(world,why)
local out={carriers={}}
local proven,pwhy=clone.prove(world)
out.pins={proven=proven==true,reason=pwhy,count=#D.pins}
local game=world_module.game_state(world)
out.mission=game and game.mission==true or false
out.players=#(world_module.players(world)or{})
-- The entity region: from the game's own type table pointers.
local em=b.pointer(source.read(world.game+D.entityManager,8),0)
local region_base
local tables={}
for name,c in pairs(D.components)do
 local at=b.pointer(source.read(em+c.slot,8),0)
 local base=at-c.offset-28
 region_base=region_base or base
 tables[name]=base==region_base and base%PAGE==0
end
out.tablesInRegion=tables
local region=source.query(region_base)
out.region={protect=region.protect,type=region.type,size=region.size}
local function record_at(name,index)
 local c=D.components[name]
 return region_base+c.offset+28+c.record_offset+index*c.stride,c.stride
end
local function records_of(carrier)
 local list={}
 for name,r in pairs(D.carriers[carrier].records)do
  local at,size=record_at(name,r.recordIndex)
  list[#list+1]={name=name,at=at,size=size,fnv=r.fnv1a}
 end
 table.sort(list,function(a,c)return a.at<c.at end)
 return list
end
local function native_all(carrier)
 for _,r in ipairs(records_of(carrier))do
  if clone.fnv1a(adapter.read(r.at,r.size))~=r.fnv then return false,r.name end
 end
 return true
end
local function reset()overlay={};protection={};writes={};counts.writes=0;counts.protections=0;clone.reset_for_tests()end
local multiplayer=out.players>1 or nil
for _,carrier in ipairs(clone.pool('EAT-17 Expendable Anti-Tank'))do
 local c=D.carriers[carrier]
 local entry={native=native_all(carrier),records={},levels={}}
 for _,r in ipairs(records_of(carrier))do entry.records[r.name]={offset=r.at-region_base,size=r.size}end
 entry.instances=clone.instances(world,c.entity)
 for _,level in ipairs(D.levels)do
  reset()
  local before={}
  for _,r in ipairs(records_of(carrier))do before[r.name]=adapter.read(r.at,r.size)end
  local h=settle(clone.apply({carrier=carrier,donor='EAT-17 Expendable Anti-Tank',level=level,multiplayer=multiplayer}))
  local lv={status=h.status,code=h.code,reason=h.reason,writes=#writes,expected=clone.writes_at(carrier,level),
   borrowedName=h.borrowed and h.borrowed.name~=nil,borrowedIcon=h.borrowed and h.borrowed.icon~=nil}
  if h.status=='applied'then
   -- Every member of this level reads the donor's value; nothing else in the records changed.
   local allowed={}
   local function expect(name,offset,width,value)
    local at=record_at(name,c.records[name].recordIndex)+offset
    for k=0,width-1 do allowed[at+k]=true end
    if adapter.read(at,width)~=value then lv.mismatch=(lv.mismatch or 0)+1 end
   end
   for _,p in ipairs(c.presentation)do expect(p.component,p.offset,p.width,b.unhex(p.donor))end
   for _,w in ipairs(c.writes)do
    if clone.LEVELS[w.level]<=clone.LEVELS[level]then expect(w.component,w.offset,w.width,b.unhex(w.donor))end
   end
   local outside=0
   for _,write in ipairs(writes)do
    for k=0,#write.bytes-1 do if not allowed[write.address+k]then outside=outside+1 end end
   end
   lv.outside=outside
   local changed_bytes=0
   for _,r in ipairs(records_of(carrier))do
    local now=adapter.read(r.at,r.size)
    for k=1,r.size do
     if now:byte(k)~=before[r.name]:byte(k)and not allowed[r.at+k-1]then changed_bytes=changed_bytes+1 end
    end
   end
   lv.otherBytesChanged=changed_bytes
   lv.protectionRestored=next(protection)==nil
   lv.markerKind=b.u32(adapter.read(record_at('SpottableComponentData',c.records.SpottableComponentData.recordIndex)+0x40,4),0)
   local applied_writes=#writes
   local r=settle(clone.restore(nil,carrier))
   lv.restore={status=r.status,code=r.code,exact=r.verify and r.verify.exact,writes=#writes-applied_writes}
   lv.nativeAfter=native_all(carrier)
   local identical=true
   for _,rec in ipairs(records_of(carrier))do if adapter.read(rec.at,rec.size)~=before[rec.name]then identical=false end end
   lv.identical=identical and next(protection)==nil
  end
  entry.levels[level]=lv
 end
 -- CONFLICT on restore: a third party changed a converted member.
 reset()
 local h=settle(clone.apply({carrier=carrier,donor='EAT-17 Expendable Anti-Tank',level='full',multiplayer=multiplayer}))
 if h.status=='applied'then
  local st=clone.state(carrier)
  local ch=st.changes[1]
  overlay[ch.owner.base+ch.offset]=string.rep('\0',#ch.desired)
  local w0=#writes
  local refused=settle(clone.restore(nil,carrier))
  local none=#writes==w0
  overlay[ch.owner.base+ch.offset]=ch.desired
  local back=settle(clone.restore(nil,carrier))
  entry.conflict={status=refused.status,code=refused.code,writesWhileRefused=none,
   thenRestored=back.status,exact=back.verify and back.verify.exact}
 else entry.conflict={status=h.status,code=h.code,reason=h.reason}end
 -- NOT_NATIVE: a byte of a carrier record (not a member) changed before the mission.
 reset()
 local rec=records_of(carrier)[1]
 overlay[rec.at+rec.size-1]=string.char((adapter.read(rec.at+rec.size-1,1):byte()+1)%256)
 local nn=settle(clone.apply({carrier=carrier,donor='EAT-17 Expendable Anti-Tank',level='full',multiplayer=multiplayer}))
 entry.notNative={status=nn.status,code=nn.code,writes=#writes}
 -- CARRIER_PRESENT: an entity of the carrier type already in the world (one Spottable handle's type overlaid).
 reset()
 local S=D.spottableInstances
 local manager=b.pointer(source.read(world.game+S.global,8),0)
 local count=manager~=0 and b.u32(source.read(manager+S.count,4),0)or 0
 if count>0 then
  local handles=b.pointer(source.read(manager+S.handles,8),0)
  local handle=b.pointer(source.read(handles,8),0)
  local hex=c.entity:gsub('^0x','')
  local hi,lo=tonumber(hex:sub(1,8),16),tonumber(hex:sub(9,16),16)
  local function u32le(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
  overlay[handle+S.handleType]=u32le(lo)..u32le(hi)
  local cp=settle(clone.apply({carrier=carrier,donor='EAT-17 Expendable Anti-Tank',level='full',multiplayer=multiplayer}))
  entry.present={status=cp.status,code=cp.code,writes=#writes,counted=clone.instances(world,c.entity)}
 end
 reset()
 out.carriers[carrier]=entry
end
-- The round override (domains/weapon_clone.lua rounds): the snapshot's real rows and the real engine package list.
local core_assets=require('hd2runtime/core/assets')
local DONOR,ROUND='EAT-17 Expendable Anti-Tank','RL-77 Airburst Rocket Launcher'
local R=D.rounds[DONOR][ROUND]
local UNIT,MISSION_PACKAGE=R.packages.unit.id,R.packages.mission.id
local function real_state(id)
 local hook=adapter.package_state;adapter.package_state=nil
 local ok,state=pcall(core_assets.state,adapter,id)
 adapter.package_state=hook
 return ok and state or('error: '..tostring(state))
end
local function projtype(carrier)
 return b.u32(adapter.read(record_at('ProjectileWeaponComponentData',
  D.carriers[carrier].records.ProjectileWeaponComponentData.recordIndex),4),0)
end
out.rounds={unitPackage=real_state(UNIT),missionPackage=real_state(MISSION_PACKAGE),carriers={}}
if out.mission then
 -- As the snapshot is: the round's own package is resident only when someone brought an RL-77.
 reset()
 local asis=settle(clone.apply({carrier='EAT-700 Expendable Napalm',donor=DONOR,level='full',round=ROUND,
  multiplayer=multiplayer}))
 out.rounds.asIs={status=asis.status,code=asis.code,reason=asis.reason,writes=#writes}
 if asis.status=='applied'then settle(clone.restore(nil,'EAT-700 Expendable Napalm'))end
 -- The round's own package resident (as the definition's asset gate makes it); the mission package as the snapshot is.
 local unit_state='resident'
 adapter.package_state=function(id)if id==UNIT then return unit_state end;return real_state(id)end
 for _,carrier in ipairs(clone.pool(DONOR))do
  local c=D.carriers[carrier]
  local entry={levels={}}
  for _,level in ipairs(D.levels)do
   reset()
   local before={}
   for _,r in ipairs(records_of(carrier))do before[r.name]=adapter.read(r.at,r.size)end
   local h=settle(clone.apply({carrier=carrier,donor=DONOR,level=level,round=ROUND,multiplayer=multiplayer}))
   local lv={status=h.status,code=h.code,reason=h.reason,writes=#writes,expected=clone.writes_at(carrier,level,ROUND)}
   if h.status=='applied'then
    local allowed={}
    local function expect(name,offset,width,value)
     local at=record_at(name,c.records[name].recordIndex)+offset
     for k=0,width-1 do allowed[at+k]=true end
     if adapter.read(at,width)~=value then lv.mismatch=(lv.mismatch or 0)+1 end
    end
    for _,p in ipairs(c.presentation)do expect(p.component,p.offset,p.width,b.unhex(p.donor))end
    for _,w in ipairs(c.writes)do
     if w.component=='ProjectileWeaponComponentData'and w.offset==0 then
      expect(w.component,w.offset,w.width,b.encode(R.type,'u32'))
     elseif clone.LEVELS[w.level]<=clone.LEVELS[level]then expect(w.component,w.offset,w.width,b.unhex(w.donor))end
    end
    local outside=0
    for _,write in ipairs(writes)do
     for k=0,#write.bytes-1 do if not allowed[write.address+k]then outside=outside+1 end end
    end
    lv.outside=outside
    local changed_bytes=0
    for _,r in ipairs(records_of(carrier))do
     local now=adapter.read(r.at,r.size)
     for k=1,r.size do
      if now:byte(k)~=before[r.name]:byte(k)and not allowed[r.at+k-1]then changed_bytes=changed_bytes+1 end
     end
    end
    lv.otherBytesChanged=changed_bytes
    lv.protectionRestored=next(protection)==nil
    lv.projtype=projtype(carrier)
    local applied_writes=#writes
    local r=settle(clone.restore(nil,carrier))
    lv.restore={status=r.status,code=r.code,exact=r.verify and r.verify.exact,writes=#writes-applied_writes}
    lv.nativeAfter=native_all(carrier)
    local identical=true
    for _,rec in ipairs(records_of(carrier))do
     if adapter.read(rec.at,rec.size)~=before[rec.name]then identical=false end
    end
    lv.identical=identical and next(protection)==nil
   end
   entry.levels[level]=lv
  end
  -- ROUND_CHANGED: one byte of the round's projectile row (its proximity member) differs.
  reset()
  local row=R.rows[1]
  local at=b.pointer(source.read(world.game+row.table+row.id*8,8),0)+0x94
  overlay[at]=string.char((adapter.read(at,1):byte()+1)%256)
  local rc=settle(clone.apply({carrier=carrier,donor=DONOR,level='full',round=ROUND,multiplayer=multiplayer}))
  entry.changed={status=rc.status,code=rc.code,writes=#writes}
  -- ROUND_NOT_RESIDENT: the round's own package not resident.
  reset()
  unit_state='absent'
  local nr=settle(clone.apply({carrier=carrier,donor=DONOR,level='presentation',round=ROUND,multiplayer=multiplayer}))
  unit_state='resident'
  entry.notResident={status=nr.status,code=nr.code,writes=#writes}
  out.rounds.carriers[carrier]=entry
 end
 adapter.package_state=nil
end
-- A Runtime icon that is not loaded is never written: the donor's marker icon is borrowed.
reset()
images.reset_for_tests()
local icon=images.handle('eat17g','mods/validation/weapon_clone')
local hi=settle(clone.apply({carrier='EAT-700 Expendable Napalm',donor='EAT-17 Expendable Anti-Tank',level='presentation',
 icon=icon,multiplayer=multiplayer}))
out.iconNotLoaded={status=hi.status,code=hi.code,borrowedIcon=hi.borrowed and hi.borrowed.icon}
if hi.status=='applied'then settle(clone.restore(nil,'EAT-700 Expendable Napalm'))end
reset()
return json.encode(out)
'''


def round_problems(rounds: dict, phase: str, live: bool) -> list[str]:
    """The round override's checks: the mission package as the engine lists it (resident in a live mission, never
    aboard the ship), the snapshot as it is (the round's own package resident or ROUND_NOT_RESIDENT), and with that
    package resident each level on each host (ProjType = the round, every other member as without it, exact restore),
    ROUND_CHANGED and ROUND_NOT_RESIDENT with nothing written."""
    problems = []
    if phase == 'ship' and rounds['missionPackage'] == 'resident':
        problems.append('round: the mission package is resident aboard the ship')
    if not live:
        return problems
    if rounds['missionPackage'] != 'resident':
        problems.append('round: the mission package is %s in a live mission' % rounds['missionPackage'])
    asis = rounds['asIs']
    if rounds['unitPackage'] != 'resident' and not (asis['status'] == 'refused' and asis['code'] ==
            'ROUND_NOT_RESIDENT' and asis['writes'] == 0):
        problems.append('round: the snapshot as it is: %r' % asis)
    for carrier, entry in rounds['carriers'].items():
        for level, lv in entry['levels'].items():
            if lv['status'] != 'applied':
                problems.append('round %s %s: %r' % (carrier, level, lv))
                continue
            if lv['projtype'] != 312 or lv['writes'] < lv['expected'] or lv.get('mismatch') or lv['outside'] \
                    or lv['otherBytesChanged'] or not lv['protectionRestored']:
                problems.append('round %s %s: the conversion: %r' % (carrier, level, lv))
            if not (lv['restore']['status'] == 'restored' and lv['restore']['exact'] and lv['nativeAfter']
                    and lv['identical']):
                problems.append('round %s %s: the restore: %r' % (carrier, level, lv['restore']))
        for key, code in (('changed', 'ROUND_CHANGED'), ('notResident', 'ROUND_NOT_RESIDENT')):
            r = entry[key]
            if not (r['status'] == 'refused' and r['code'] == code and r['writes'] == 0):
                problems.append('round %s: %s: %r' % (carrier, key, r))
    return problems


def validate(snapshots=SNAPSHOTS):
    results = {}
    for name in snapshots:
        report = json.loads(snapshot_regions.run_lua(BODY, build_profile.snapshot_directory() / name))
        phase = MISSION.get(name, 'ship')
        problems = []
        if not report['pins']['proven']:
            problems.append('pins: %s' % report['pins']['reason'])
        if not all(report['tablesInRegion'].values()):
            problems.append('a type table is outside the entity region: %r' % report['tablesInRegion'])
        if report['region']['protect'] != 2 or report['region']['type'] != 0x20000:
            problems.append('the entity region is not private read-only: %r' % report['region'])
        live = phase in ('alive', 'reinforced')
        for carrier, entry in report['carriers'].items():
            if not entry['native']:
                problems.append(carrier + ': not native in the snapshot')
            if entry['instances'] != 0:
                problems.append(carrier + ': entities of the carrier type exist (%r)' % entry['instances'])
            for level, lv in entry['levels'].items():
                if not live:
                    if lv['status'] != 'refused' or lv['code'] != 'NOT_IN_MISSION' or lv['writes']:
                        problems.append('%s %s outside a live mission: %r' % (carrier, level, lv))
                    continue
                if lv['status'] != 'applied':
                    problems.append('%s %s: %r' % (carrier, level, lv))
                    continue
                if lv['writes'] < lv['expected'] or lv.get('mismatch') or lv['outside'] or lv['otherBytesChanged'] \
                        or not lv['protectionRestored'] or lv['markerKind'] != 2:
                    problems.append('%s %s: the conversion: %r' % (carrier, level, lv))
                if not (lv['restore']['status'] == 'restored' and lv['restore']['exact'] and lv['nativeAfter']
                        and lv['identical']):
                    problems.append('%s %s: the restore: %r' % (carrier, level, lv['restore']))
                if not (lv['borrowedName'] and lv['borrowedIcon']):
                    problems.append('%s %s: no name / icon given must borrow the donor\'s' % (carrier, level))
            if live:
                cf = entry['conflict']
                if not (cf.get('status') == 'refused' and cf.get('code') == 'CONFLICT' and cf['writesWhileRefused']
                        and cf['thenRestored'] == 'restored' and cf['exact']):
                    problems.append(carrier + ': conflict: %r' % cf)
                nn = entry['notNative']
                if not (nn['status'] == 'refused' and nn['code'] == 'NOT_NATIVE' and nn['writes'] == 0):
                    problems.append(carrier + ': not native: %r' % nn)
                cp = entry.get('present')
                if not (cp and cp['status'] == 'refused' and cp['code'] == 'CARRIER_PRESENT' and cp['writes'] == 0
                        and cp['counted'] == 1):
                    problems.append(carrier + ': carrier present: %r' % cp)
        if live:
            icon = report['iconNotLoaded']
            if not (icon['status'] == 'applied' and icon['borrowedIcon']):
                problems.append('an unloaded Runtime icon: %r' % icon)
        problems += round_problems(report['rounds'], phase, live)
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
    OUTPUT.write_text(json.dumps(summary, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    for name, result in results.items():
        print(('PASS ' if result['passed'] else 'FAIL ') + name + ' (' + result['phase'] + ')' + ('' if result['passed']
            else ': ' + '; '.join(result['problems'])))
    if not summary['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
