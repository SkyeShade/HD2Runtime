"""Validate the carrier pod rack write (runtime/carrier_pod.lua, domains/carrier_pod_items.lua) on every retained
snapshot (no game process; game memory is only read; writes go to a copy-on-write overlay with page protection
emulated; package residency is simulated through the reader's offline package_state hook).

The production module runs against the snapshot's real entity region, game.dll and stratagem table:

* in a mission, for each case (the EAT-411 Leveller with two clone launchers: its EMPTY slot 1 at attach_1 written;
  the EAT-700 with two: nothing to write; the AC-8 with an MG-43 and a B-1 Supply Pack: both slots rewritten and its
  leftover slots 2 and 3 (items outside the spawn count) written EMPTY; the
  RL-77 with one MG-43: slot 0 rewritten, its backpack slot 1 and its leftover slots 2 and 3 (items outside the spawn
  count) written EMPTY): the write applies through one guarded transaction on the real allocation (PAGE_READONLY
  handling, read-back): every slot reads exactly its planned item, every other byte of the rack record and of the region
  is unchanged (nodes, sides, apply_deltas, the sizes), the record had one owner and one consumer row, the protection is
  read-only again; the restore writes exactly the captured bytes back (the overlay byte-identical to the snapshot);
* the guards: a third-party change to a written slot is a CONFLICT on restore (nothing written), then the restore
  succeeds once it holds what was written again; a slot that is not its vanilla bytes before the mission refuses the
  write (NOT_NATIVE, nothing written); a pod of the carrier type already in the world refuses it (CARRIER_CALLED,
  nothing written: never written after a call); a non-resident item package refuses it (ASSET_UNAVAILABLE); a shared
  rack (the EAT-17's) has no exclusive record (NO_EXCLUSIVE_RACK); too many items (CAPACITY) and a backpack in a weapon
  slot (ROLE) are refused by the plan; aboard the ship and after the mission it is refused (NOT_IN_MISSION).
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

OUTPUT = ROOT / 'validation/carrier-pod-snapshot.json'

BODY = r'''
local json=require('hd2runtime/primary_mapper/json')
local world_module=require('hd2runtime/runtime/event_world')
local pod=require('hd2runtime/runtime/carrier_pod')
local D=require('hd2runtime/domains/carrier_pod_items')
local b=require('hd2runtime/core/bytes')
local PAGE=4096
local adapter,overlay,protection,writes={},{},{},{}
local counts={writes=0,protections=0}
for k,v in pairs(source)do adapter[k]=v end
local resident=true
function adapter.package_state()return resident and'resident'or'absent'end
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
 overlay[at]=bytes
 return true,nil,#bytes
end
local function settle(job)for _=1,4000 do if job.status~='pending'then break end;update(0.1)end;return job end
world_module.set_runtime(adapter)
local world,why=world_module.open()
assert(world,why)
local out={cases={}}
local game=world_module.game_state(world)
out.mission=game and game.mission==true or false
out.players=#(world_module.players(world)or{})
local multiplayer=out.players>1 or nil
local function reset()overlay={};protection={};writes={};counts.writes=0;counts.protections=0;resident=true
 pod.reset_for_tests()end
local function u64(resource)
 local hex=tostring(resource):gsub('^0x','')
 local o={}
 for i=15,1,-2 do o[#o+1]=string.char(tonumber(hex:sub(i,i+1),16))end
 return table.concat(o)
end
local function hex_of(bytes)return('0x%08X%08X'):format(b.u32(bytes,4),b.u32(bytes,0))end
local function item(key)
 local e=assert(D.items[key],key)
 return {role=D.kinds[e.kind].role,resource=e.resource,label=e.label,key=key}
end
local CASES={
 {name='EAT-411 Leveller x2 clones',carrier='EAT-411 Leveller',items={
   {role='weapon',resource=D.racks['EAT-411 Leveller'].slots[1].item,label='the clone'},
   {role='weapon',resource=D.racks['EAT-411 Leveller'].slots[1].item,label='the clone'}},expectSlots=1},
 {name='EAT-700 x2 clones',carrier='EAT-700 Expendable Napalm',items={
   {role='weapon',resource=D.racks['EAT-700 Expendable Napalm'].slots[1].item,label='the clone'},
   {role='weapon',resource=D.racks['EAT-700 Expendable Napalm'].slots[1].item,label='the clone'}},expectSlots=0},
 {name='AC-8: MG-43 + B-1',carrier='AC-8 Autocannon',items={item('support_weapon/MG-43 Machine Gun'),
   item('backpack/B-1 Supply Pack')},expectSlots=4},
 {name='RL-77: one MG-43 (leftovers emptied)',carrier='RL-77 Airburst Rocket Launcher',
   items={item('support_weapon/MG-43 Machine Gun')},expectSlots=4},
}
for _,case in ipairs(CASES)do
 reset()
 local entry={carrier=case.carrier}
 local rack=D.racks[case.carrier]
 local plan,pcode,preason=pod.plan(case.carrier,case.items)
 entry.plan={ok=plan~=nil,code=pcode,reason=preason,writes=plan and plan.writes,expected=case.expectSlots}
 local inspect,icode,ireason=pod.inspect(world,case.carrier)
 entry.inspect={native=inspect and inspect.native,code=icode,reason=ireason}
 local h=settle(pod.apply({carrier=case.carrier,items=case.items,label=case.name,multiplayer=multiplayer}))
 entry.apply={status=h.status,code=h.code,reason=h.reason,writes=#writes,slots=h.slots}
 if h.status=='applied'then
  local st=pod.state(case.carrier)
  local rec=st.record
  local now=adapter.read(rec.owner.base+rec.offset,rec.size)
  local exact,other=true,0
  local allowed={}
  for _,slot in ipairs(rack.slots)do
   local at=slot.index*64
   if hex_of(now:sub(at+1,at+8))~=plan.desired[slot.index]then exact=false end
   if plan.desired[slot.index]~=slot.item then for k=0,7 do allowed[at+k]=true end end
  end
  for k=1,rec.size do if now:byte(k)~=rec.bytes:byte(k)and not allowed[k-1]then other=other+1 end end
  local outside=0
  for _,w in ipairs(writes)do
   for k=0,#w.bytes-1 do
    local off=w.address+k-rec.owner.base-rec.offset
    if not allowed[off]then outside=outside+1 end
   end
  end
  entry.apply.exact=exact
  entry.apply.otherBytesChanged=other
  entry.apply.outside=outside
  entry.apply.protectionRestored=next(protection)==nil
  local applied=#writes
  local r=settle(pod.restore(nil,case.carrier))
  local back=adapter.read(rec.owner.base+rec.offset,rec.size)
  entry.restore={status=r.status,code=r.code,exact=r.verify and r.verify.exact,writes=#writes-applied,
   identical=back==rec.bytes and next(protection)==nil}
  -- CONFLICT: a third party changed a written slot (only when something was written).
  if plan.writes>0 then
   reset()
   local h2=settle(pod.apply({carrier=case.carrier,items=case.items,label=case.name,multiplayer=multiplayer}))
   if h2.status=='applied'then
    local s2=pod.state(case.carrier)
    local ch=s2.changes[1]
    local addr=ch.owner.base+ch.offset
    overlay[addr]=string.rep('\255',#ch.desired)
    local w0=#writes
    local refused=settle(pod.restore(nil,case.carrier))
    local none=#writes==w0
    overlay[addr]=ch.desired
    local again=settle(pod.restore(nil,case.carrier))
    entry.conflict={status=refused.status,code=refused.code,writesWhileRefused=none,thenRestored=again.status,
     exact=again.verify and again.verify.exact}
   end
  end
  -- NOT_NATIVE: a slot item is not its vanilla bytes before the mission.
  reset()
  local slot0=rec.owner.base+rec.offset
  overlay[slot0]=u64('0x1111111111111111')
  local nn=settle(pod.apply({carrier=case.carrier,items=case.items,label=case.name,multiplayer=multiplayer}))
  entry.notNative={status=nn.status,code=nn.code,writes=#writes}
  -- ASSET_UNAVAILABLE: an item package not resident.
  reset()
  resident=false
  local na=settle(pod.apply({carrier=case.carrier,items=case.items,label=case.name,multiplayer=multiplayer}))
  entry.assets={status=na.status,code=na.code,writes=#writes}
  -- CARRIER_CALLED: a pod of the carrier type already exists (the Transport list read is replaced in Lua only).
  reset()
  local sp=require('hd2runtime/runtime/support_pods')
  local real=sp.pods
  local loadout=require('hd2runtime/runtime/stratagem_loadout')
  local kind=loadout.type_of(world,rack.stableId)
  sp.pods=function()return {{index=0,entity=4242,network=7,type=kind,beacon_network=8}}end
  local cc=settle(pod.apply({carrier=case.carrier,items=case.items,label=case.name,multiplayer=multiplayer}))
  sp.pods=real
  entry.called={status=cc.status,code=cc.code,writes=#writes}
 end
 reset()
 out.cases[#out.cases+1]=entry
end
-- The plan's refusals (static).
local _,c1=pod.plan('EAT-17 Expendable Anti-Tank',{{role='weapon',resource='0x80932FA0ED6901D3',label='x'}})
local _,c2=pod.plan('EAT-411 Leveller',{{role='weapon',resource='0x1',label='a'},{role='weapon',resource='0x1',label='b'},
 {role='weapon',resource='0x1',label='c'}})
local _,c3=pod.plan('EAT-411 Leveller',{{role='backpack',resource='0x4EF9A47109239A58',label='B-1'}})
out.planRefusals={shared=c1,capacity=c2,role=c3}
return json.encode(out)
'''


def validate(snapshots=SNAPSHOTS):
    results = {}
    for name in snapshots:
        report = json.loads(snapshot_regions.run_lua(BODY, build_profile.snapshot_directory() / name))
        phase = MISSION.get(name, 'ship')
        problems = []
        live = phase in ('alive', 'reinforced')
        r = report['planRefusals']
        if (r['shared'], r['capacity'], r['role']) != ('NO_EXCLUSIVE_RACK', 'CAPACITY', 'ROLE'):
            problems.append('the plan refusals: %r' % r)
        for case in report['cases']:
            label = case['carrier']
            if not case['plan']['ok'] or case['plan']['writes'] != case['plan']['expected']:
                problems.append('%s: the plan: %r' % (label, case['plan']))
            if not case['inspect']['native']:
                problems.append('%s: not native / not exclusive in the snapshot: %r' % (label, case['inspect']))
            a = case['apply']
            if not live:
                if a['status'] != 'refused' or a['code'] != 'NOT_IN_MISSION' or a['writes']:
                    problems.append('%s outside a live mission: %r' % (label, a))
                continue
            if a['status'] != 'applied':
                problems.append('%s: %r' % (label, a))
                continue
            if not a['exact'] or a['otherBytesChanged'] or a['outside'] or not a['protectionRestored'] \
                    or a['slots'] != case['plan']['expected'] or (a['slots'] == 0) != (a['writes'] == 0):
                problems.append('%s: the write: %r' % (label, a))
            rs = case['restore']
            if not (rs['status'] == 'restored' and rs['exact'] and rs['identical']):
                problems.append('%s: the restore: %r' % (label, rs))
            if case['plan']['expected'] > 0:
                cf = case.get('conflict') or {}
                if not (cf.get('status') == 'refused' and cf.get('code') == 'CONFLICT' and cf.get('writesWhileRefused')
                        and cf.get('thenRestored') == 'restored' and cf.get('exact')):
                    problems.append('%s: conflict: %r' % (label, cf))
            for key, code in (('notNative', 'NOT_NATIVE'), ('assets', 'ASSET_UNAVAILABLE'), ('called', 'CARRIER_CALLED')):
                g = case[key]
                if not (g['status'] == 'refused' and g['code'] == code and g['writes'] == 0):
                    problems.append('%s: %s: %r' % (label, key, g))
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
