"""The EXPERIMENTAL, SOLO-ONLY Liberator beam swap (runtime/experiment_liberator_beam.lua, domains/liberator_beam.lua,
core/reviewed_edits.lua; research/docs/component-swap-liberator-beam.md). Branch exp/liberator-beam only.

The snapshot tests run on the copy-on-write overlay of the retained current-build snapshot (no game process): every
address is re-derived here independently of the module, from the research's formulas.
"""
import json
import unittest

from support import ROOT, run
from test_multi_mod_composition import build_profile, snapshot_run

import sys
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_liberator_beam  # noqa: E402

SWAP = json.loads((ROOT / 'research/component-swap-liberator-beam-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
CHAMBER = json.loads((ROOT / 'research/liberator-beam-chamber-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

# The research's own addresses, derived in the test (never through the module under test).
LOCATE = r'''
local X=require('hd2runtime/runtime/experiment_liberator_beam')
X.reset_for_tests()
local edits=require('hd2runtime/core/reviewed_edits')
local D=require('hd2runtime/domains/liberator_beam')
runtime.package_state=function()return'resident'end
local function ptr(at)return b.pointer(runtime.read(at,8),0)end
local game=runtime.address(runtime.module('game.dll'))
local manager=ptr(game+0x346BF98)
local TABLE=ptr(manager+0xF12478+8*270)
local ESH=ptr(manager+0xF12EA0)
local ROW=TABLE+0x150
local RECORD=TABLE+0xDA8
local LIST=ptr(ESH+32*3686+8)
local MAGTABLE=ptr(manager+0xF12478+8*5)
local MAGROW=MAGTABLE+16*246
local MAGWIN=MAGTABLE+8640+160*201+156
local DESCRIPTORS=manager+0xF32F18
local INVALID=b.u32(runtime.read(game+0x348456C,4),0)
check(b.resource(runtime.read(ESH+32*3686,8),0)=='0x968211C0033DCE64','row 3686 is not the Liberator')
local TARGETS={{ROW,16,'row'},{RECORD,120,'record'},{LIST,46,'list'},{MAGWIN,4,'magazine'}}
local function now(t)return b.hex(runtime.read(t[1],t[2]))end
local function source_bytes(at,n)return source.read(at,n)end
-- Every byte the overlay holds that differs from the snapshot, as {address = true}.
local function changed()
 local out,count={},0
 for address,value in pairs(overlay)do
  local original=source.read(address,#value)
  for i=1,#value do
   if value:byte(i)~=original:byte(i)then out[address+i-1]=true;count=count+1 end
  end
 end
 return out,count
end
local function inside(at)
 for _,t in ipairs(TARGETS)do if at>=t[1]and at<t[1]+t[2]then return t[3]end end
end
local function only_targets()
 local out,count=changed()
 for at in pairs(out)do check(inside(at),('a byte outside the four targets changed: %X'):format(at))end
 return count
end
local function free_descriptor()
 for k=0,0x7FF do
  local raw=runtime.read(DESCRIPTORS+24*k,24)
  if b.u32(raw,8)==INVALID then return DESCRIPTORS+24*k end
 end
end
local function writes_log()
 local order={}
 local write=runtime.write
 runtime.write=function(at,bytes,packed)order[#order+1]={at=at,n=#bytes};return write(at,bytes,packed)end
 return order,function()runtime.write=write end
end
'''


class DomainTests(unittest.TestCase):
    def test_the_domain_is_generated_from_the_research(self):
        self.assertEqual(generate_liberator_beam.generate(check=True), [])
        domain = generate_liberator_beam.build()
        ws = SWAP['writeSet']
        self.assertEqual(domain['beam']['rowOffset'], 0x150)
        self.assertEqual(domain['beam']['recordOffset'], 0xDA8)
        self.assertEqual(domain['beam']['rowAfter'], '64ce3d03c01182961700000000000000')
        self.assertEqual(domain['beam']['recordAfter'], ws['record']['after'])
        self.assertEqual(domain['membership']['before'], ws['membershipList']['before'])
        self.assertEqual(domain['membership']['after'], ws['membershipList']['after'])
        self.assertEqual(domain['membership']['row'], 3686)
        swap_pins = {pin['rva'] for rows in SWAP['pins'].values() for pin in rows}
        self.assertEqual(len(swap_pins), 63)
        self.assertTrue(swap_pins <= {pin['rva'] for pin in domain['pins']})
        # L2b (research/docs/component-swap-liberator-beam-chamber.md): the Liberator's own magazine record 201 +156.
        mag = domain['magazine']
        self.assertEqual((mag['row'], mag['record'], mag['home'], mag['windowOffset']), (246, 201, 244, 0x9FFC))
        self.assertEqual(mag['windowOffset'], mag['recordBase'] + 160 * 201 + 156)
        self.assertEqual((mag['before'], mag['after']), ('01000000', '00000000'))
        self.assertEqual(mag['rowBytes'], '64ce3d03c0118296c900000000000000')
        chamber_pins = {pin['rva'] for rows in CHAMBER['pins'].values() for pin in rows}
        self.assertEqual(len(chamber_pins), 69)
        self.assertTrue(chamber_pins <= {pin['rva'] for pin in domain['pins']})
        for rva in (0x76DA64, 0x744D9C, 0x83E41E, 0x76F1B0, 0x776B1F):   # the root cause, pinned
            self.assertIn(rva, chamber_pins)
        self.assertEqual(CHAMBER['compositions']['liberatorL2NotInMeltagun'], [])
        self.assertEqual(CHAMBER['magazine']['meltagunRecord']['+156'], 0)

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
    def test_the_extra_pins_are_the_game_image_bytes(self):
        from scan import xref
        _, data, sha = xref.load_image('game.dll')
        self.assertEqual(sha, generate_liberator_beam.build()['source']['gameDllSha256'])
        for pin in generate_liberator_beam.EXTRA_PINS:
            expected = bytes.fromhex(pin['hex'])
            self.assertEqual(data[pin['rva']:pin['rva'] + len(expected)], expected, hex(pin['rva']))

    def test_reviewed_edits_drop_only_their_own_diagnostics(self):
        self.assertEqual(run(r'''
local edits=require('hd2runtime/core/reviewed_edits')
edits.reset()
local function candidate(diagnostics)
 return {resourceHash='0x968211C0033DCE64',diagnostics=diagnostics,
  ownership={BeamWeaponComponentData={indexRow=21,recordIndex=23},ProjectileWeaponComponentData={indexRow=4,recordIndex=192}}}
end
-- No entry: nothing changes.
local c=candidate({'ProjectileWeaponComponentData membership absent'})
edits.review(c,'list')
assert(#c.diagnostics==1 and c.refused==nil)
edits.set('0x968211C0033DCE64',{owner='test',stage='L2',membership='list',
 rows={BeamWeaponComponentData={row=21,record=23}},absent={ProjectileWeaponComponentData=true},
 refuse={ProjectileWeaponComponentData='dormant'}})
-- The recorded state: its own diagnostic dropped, any other kept, the dormant component refused.
c=candidate({'ProjectileWeaponComponentData membership absent','WeaponDataComponentData membership absent'})
edits.review(c,'list')
assert(#c.diagnostics==1 and c.diagnostics[1]=='WeaponDataComponentData membership absent',c.diagnostics[1])
assert(c.refused.ProjectileWeaponComponentData=='dormant')
-- A third list state, or another row: foreign, every write refused.
c=candidate({'ProjectileWeaponComponentData membership absent'})
edits.review(c,'other')
assert(#c.diagnostics==2 and c.diagnostics[2]:find('not in its recorded state',1,true)and c.refused==nil)
c=candidate({})
c.ownership.BeamWeaponComponentData.indexRow=22
edits.review(c,'list')
assert(#c.diagnostics==1 and c.diagnostics[1]:find('BeamWeaponComponentData index row',1,true))
-- Another resource is never touched.
c=candidate({'ProjectileWeaponComponentData membership absent'});c.resourceHash='0x3C86E871923F3970'
edits.review(c,'list')
assert(#c.diagnostics==1 and c.refused==nil)
edits.reset()
return 'ok'
'''), b'ok')


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class LiberatorBeamSnapshotTests(unittest.TestCase):
    def test_l1_then_l2_write_exactly_the_research_bytes_and_restore_returns_every_byte(self):
        result = snapshot_run(LOCATE + r'''
update=update or function()end
check(now(TARGETS[1])==D.beam.rowBefore and now(TARGETS[2])==D.beam.recordBefore and now(TARGETS[3])==D.membership.before,
 'the snapshot does not hold the before bytes')
local status=X.status()
check(status.ok and status.state=='vanilla'and status.live_liberators==0 and status.solo==true,
 'status '..tostring(status.reason))
check(counts.writes==0 and counts.protection_changes==0,'status wrote')
local order,stop=writes_log()
-- L1: record 23 then row 21 (its record index, then its key); the list is untouched.
local r1=X.apply('L1')
check(r1.ok and r1.state=='L1','L1 '..tostring(r1.reason))
check(now(TARGETS[1])=='64ce3d03c01182961700000000000000','row 21 after L1 '..now(TARGETS[1]))
check(now(TARGETS[2])==D.beam.recordAfter,'record 23 after L1')
check(now(TARGETS[3])==D.membership.before,'the list changed in L1')
local l1_bytes=only_targets()
local l1_order={}
for _,w in ipairs(order)do l1_order[#l1_order+1]=inside(w.at)..'+'..(w.at-(inside(w.at)=='row'and ROW or RECORD))end
check(edits.get('0x968211C0033DCE64').stage=='L1','L1 not recorded')
-- L2: the list (bytes 40..45: 271, 290, 321 -> 270, 271, 290).
local n=#order
local r2=X.apply('L2')
check(r2.ok and r2.state=='L2','L2 '..tostring(r2.reason))
check(now(TARGETS[3])==D.membership.after,'list after L2 '..now(TARGETS[3]))
check(now(TARGETS[1])=='64ce3d03c01182961700000000000000'and now(TARGETS[2])==D.beam.recordAfter,'L1 bytes moved')
local l2_bytes=only_targets()
local list_writes={}
for i=n+1,#order do list_writes[#list_writes+1]={inside(order[i].at),order[i].at-LIST,order[i].n}end
check(edits.get('0x968211C0033DCE64').stage=='L2','L2 not recorded')
check(next(protection)==nil,'a page protection was left changed')
-- Restore: list, then row 21 (key first), then record 23. Every byte returns.
local m=#order
local r3=X.restore()
check(r3.ok and r3.state=='vanilla','restore '..tostring(r3.reason))
local restore_order={}
for i=m+1,#order do restore_order[#restore_order+1]=inside(order[i].at)or'outside'end
stop()
local _,left=changed()
check(left==0,left..' bytes still differ from the snapshot after the restore')
check(now(TARGETS[1])==D.beam.rowBefore and now(TARGETS[2])==D.beam.recordBefore and now(TARGETS[3])==D.membership.before,
 'not vanilla after the restore')
check(next(protection)==nil,'a page protection was left changed after the restore')
check(edits.get('0x968211C0033DCE64')==nil,'the edit is still recorded')
local logged={}
for _,line in ipairs(LINES)do if line:find('^LIBERATOR BEAM:')then logged[#logged+1]=line end end
return json.encode({l1_bytes=l1_bytes,l2_bytes=l2_bytes,l1_order=l1_order,list_writes=list_writes,
 restore_order=restore_order,list_mod4=LIST%4,logged=logged})
''')
        ws = SWAP['writeSet']
        record_diff = sum(1 for a, c in zip(bytes.fromhex(ws['record']['before']), bytes.fromhex(ws['record']['after']))
                          if a != c)
        row_diff = sum(1 for c in bytes.fromhex(ws['indexRow']['after']) if c)
        self.assertEqual(result['l1_bytes'], record_diff + row_diff)
        self.assertEqual(result['l2_bytes'], record_diff + row_diff + 3)
        # Record chunks first (ascending), then row 21's record index, then its key.
        order = result['l1_order']
        self.assertEqual(order[-2:], ['row+8', 'row+0'])
        self.assertTrue(all(o.startswith('record+') for o in order[:-2]))
        self.assertEqual([int(o.split('+')[1]) for o in order[:-2]], sorted(int(o.split('+')[1]) for o in order[:-2]))
        # One 8-byte, 4-aligned write over the three changed entries.
        self.assertEqual(len(result['list_writes']), 1)
        self.assertEqual(result['list_writes'][0][0], 'list')
        self.assertIn(result['list_writes'][0][1], (38, 40))
        self.assertEqual(result['list_writes'][0][2], 8)
        restore = result['restore_order']
        self.assertEqual(restore[0], 'list')
        self.assertEqual(restore[1:3], ['row', 'row'])
        self.assertTrue(all(r == 'record' for r in restore[3:]))
        self.assertTrue(any('L2 APPLIED' in line for line in result['logged']))
        self.assertTrue(any('RESTART THE GAME' in line for line in result['logged']))

    def test_l2b_writes_the_chamber_byte_after_the_list_and_restores_it_first(self):
        result = snapshot_run(LOCATE + r'''
update=update or function()end
check(now(TARGETS[4])=='01000000','the snapshot magazine window is not 01000000: '..now(TARGETS[4]))
check(b.hex(runtime.read(MAGROW,16))=='64ce3d03c0118296c900000000000000','magazine row 246')
local order,stop=writes_log()
-- From vanilla: L1, L2 and the byte in one call, in that order.
local r=X.apply('L2b')
check(r.ok and r.state=='L2b','L2b '..tostring(r.reason))
check(now(TARGETS[4])=='00000000','magazine window after L2b '..now(TARGETS[4]))
check(now(TARGETS[3])==D.membership.after and now(TARGETS[2])==D.beam.recordAfter,'L1/L2 bytes')
local sequence={}
for _,w in ipairs(order)do
 local t=inside(w.at)
 if sequence[#sequence]~=t then sequence[#sequence+1]=t end
end
local magazine_writes={}
for _,w in ipairs(order)do if inside(w.at)=='magazine'then magazine_writes[#magazine_writes+1]={w.at-MAGWIN,w.n}end end
local bytes=only_targets()
check(edits.get('0x968211C0033DCE64').stage=='L2b','L2b not recorded')
check(next(protection)==nil,'a page protection was left changed')
local st=X.status()
check(st.ok and st.state=='L2b'and st.detail:find('magazine chamber 0',1,true),tostring(st.detail))
-- Applying L2 or L1 again in L2b writes nothing.
local n=#order
check(X.apply('L2').ok and X.apply('L1').ok and #order==n,'a lower stage wrote over L2b')
-- Restore: the byte first, then the list, the row, the record.
local m=#order
local back=X.restore()
check(back.ok and back.state=='vanilla','restore '..tostring(back.reason))
local restore_sequence={}
for i=m+1,#order do
 local t=inside(order[i].at)
 if restore_sequence[#restore_sequence]~=t then restore_sequence[#restore_sequence+1]=t end
end
stop()
local _,left=changed()
check(left==0,left..' bytes still differ after the restore')
check(edits.get('0x968211C0033DCE64')==nil,'the edit is still recorded')
local logged={}
for _,line in ipairs(LINES)do if line:find('^LIBERATOR BEAM:')then logged[#logged+1]=line end end
return json.encode({sequence=sequence,magazine_writes=magazine_writes,bytes=bytes,restore=restore_sequence,
 logged=logged})
''')
        self.assertEqual(result['sequence'], ['record', 'row', 'list', 'magazine'])
        self.assertEqual(result['magazine_writes'], [[0, 4]])
        ws = SWAP['writeSet']
        record_diff = sum(1 for a, c in zip(bytes.fromhex(ws['record']['before']), bytes.fromhex(ws['record']['after']))
                          if a != c)
        row_diff = sum(1 for c in bytes.fromhex(ws['indexRow']['after']) if c)
        self.assertEqual(result['bytes'], record_diff + row_diff + 3 + 1)
        self.assertEqual(result['restore'], ['magazine', 'list', 'row', 'record'])
        self.assertTrue(any('L2b APPLIED' in line for line in result['logged']))
        self.assertTrue(any('L2b RESTORED' in line for line in result['logged']))

    def test_the_magazine_targets_are_proven_before_any_write(self):
        result = snapshot_run(LOCATE + r'''
update=update or function()end
local seen={}
-- The chamber byte in a third value, the row, another row naming record 201: refused, nothing written.
local cases={{MAGWIN,string.char(2),'the chamber byte'},{MAGROW+8,string.char(0xCA),'the magazine row'},
 {MAGWIN+1,string.char(1),'the byte after the chamber flag'}}
for _,c in ipairs(cases)do
 overlay[c[1]]=c[2]
 local r=X.apply('L2b')
 check(not r.ok,c[3]..' changed but L2b went ahead')
 seen[#seen+1]=c[3]..': '..r.reason
 overlay[c[1]]=nil
end
local free
for k=0,539 do if b.u32(runtime.read(MAGTABLE+16*k,8),0)==0 and b.u32(runtime.read(MAGTABLE+16*k,8),4)==0 then free=k;break end end
overlay[MAGTABLE+16*free]=b.unhex('0100000000000080')..b.encode(201,'u32')..b.encode(0,'u32')
local r=X.apply('L2b')
check(not r.ok and r.reason:find('names record 201',1,true),tostring(r.reason))
overlay[MAGTABLE+16*free]=nil
check(counts.writes==0 and counts.protection_changes==0,'a refused apply wrote')
-- L2 applied by the 0.1.0 key, then a third chamber value: restore refused, L2b refused.
check(X.apply('L2').ok,'L2')
overlay[MAGWIN]=string.char(2)
check(not X.restore().ok and not X.apply('L2b').ok,'a foreign chamber byte was written over')
overlay[MAGWIN]=nil
check(X.apply('L2b').ok and X.restore().ok,'L2 -> L2b -> vanilla')
return json.encode(seen)
''')
        self.assertEqual(len(result), 3)
        self.assertTrue('state the experiment did not make' in result[0], result[0])
        self.assertTrue('CONFLICT' in result[1] or 'not row' in result[1], result[1])
        self.assertTrue('state the experiment did not make' in result[2], result[2])

    def test_a_live_liberator_refuses_the_write_and_the_restore(self):
        result = snapshot_run(LOCATE + r'''
update=update or function()end
local slot=free_descriptor()
check(slot,'no free descriptor')
local live=b.unhex('64ce3d03c0118296')..b.encode(0x00400123,'u32')
overlay[slot]=live
local st=X.status()
check(st.live_liberators==1,'census '..tostring(st.live_liberators))
local r=X.apply('L1')
check(not r.ok and r.reason:find('1 live AR-23 Liberator',1,true),'L1 with a live Liberator: '..tostring(r.reason))
check(counts.writes==0 and counts.protection_changes==0,'a refused apply wrote')
-- Applied with none, then a Liberator appears: the restore is refused and the bytes stay as they are.
overlay[slot]=nil
check(X.apply('L2').ok,'L2 without a Liberator')
overlay[slot]=live
local writes=counts.writes
local back=X.restore()
check(not back.ok and back.reason:find('live AR-23 Liberator',1,true),'restore with a live Liberator: '..tostring(back.reason))
check(counts.writes==writes,'a refused restore wrote')
check(now(TARGETS[3])==D.membership.after,'the list changed')
-- A free descriptor (the invalid entity id) is not counted.
overlay[slot]=b.unhex('64ce3d03c0118296')..b.encode(INVALID,'u32')
check(X.restore().ok,'restore after the Liberator was destroyed')
return json.encode({ok=true})
''')
        self.assertEqual(result, {'ok': True})

    def test_another_lobby_member_refuses_the_write(self):
        result = snapshot_run(LOCATE + r'''
update=update or function()end
local real=package.loaded['hd2runtime/runtime/peer_channel']
package.loaded['hd2runtime/runtime/peer_channel']={prove=function()return true end,
 lobby=function()return {members={{peer='A',['local']=true},{peer='B'}}}end}
local r=X.apply('L1')
check(not r.ok and r.reason:find('solo only: 2 lobby members',1,true),tostring(r.reason))
check(counts.writes==0,'wrote with another lobby member')
-- An unreadable lobby fails closed too.
package.loaded['hd2runtime/runtime/peer_channel']={prove=function()return true end,
 lobby=function()return nil,'UNREADABLE','the member list'end}
r=X.apply('L1')
check(not r.ok and r.reason:find('lobby state is unreadable',1,true),tostring(r.reason))
-- Unproven lobby pins fail closed.
package.loaded['hd2runtime/runtime/peer_channel']={prove=function()return false,'changed'end,lobby=real.lobby}
r=X.apply('L1')
check(not r.ok and r.reason:find('cannot be proven',1,true),tostring(r.reason))
check(counts.writes==0,'wrote without a proven solo lobby')
package.loaded['hd2runtime/runtime/peer_channel']=real
check(X.apply('L1').ok,'solo again')
return json.encode({ok=true})
''')
        self.assertEqual(result, {'ok': True})

    def test_any_before_byte_mismatch_refuses(self):
        result = snapshot_run(LOCATE + r'''
update=update or function()end
local cases={
 {ROW+3,'row 21'},{RECORD+60,'record 23'},{LIST+44,'the list'},{LIST+2,'the list (an unchanged entry)'},
 {TABLE+0x2E0+18*0x78+104,'the Trident record (the copy source)'},{TABLE+20*16+8,'the Trident row'},
}
local seen={}
for _,c in ipairs(cases)do
 local original=runtime.read(c[1],1)
 overlay[c[1]]=string.char((original:byte()+1)%256)
 local r=X.apply('L1')
 local r2=X.apply('L2')
 check(not r.ok and not r2.ok,c[2]..' changed but the apply went ahead')
 seen[#seen+1]=c[2]..': '..r.reason
 overlay[c[1]]=nil
end
check(counts.writes==0 and counts.protection_changes==0,'a refused apply wrote')
-- A changed pin (native code): unproven, refused.
X.reset_for_tests();runtime.package_state=function()return'resident'end
local pin=D.pins[1]
overlay[game+pin.rva]=string.char((b.unhex(pin.hex):byte()+1)%256)
local r=X.apply('L1')
check(not r.ok and r.reason:find('UNPROVEN',1,true),tostring(r.reason))
overlay[game+pin.rva]=nil
X.reset_for_tests();runtime.package_state=function()return'resident'end
-- The Trident package not resident: L1 goes ahead, L2 is refused.
runtime.package_state=function()return'absent'end
check(X.apply('L1').ok,'L1 needs no package')
r=X.apply('L2')
check(not r.ok and r.reason:find('package is absent',1,true),tostring(r.reason))
check(now(TARGETS[3])==D.membership.before,'the list changed without the package')
-- A foreign state of an applied edit: refused both ways.
overlay[RECORD+60]=string.char((runtime.read(RECORD+60,1):byte()+1)%256)
check(not X.restore().ok and not X.apply('L2').ok,'a foreign state was written over')
return json.encode(seen)
''')
        self.assertEqual(len(result), 6)
        for line in result:
            self.assertTrue('state the experiment did not make' in line or 'CONFLICT' in line, line)

    def test_guards_stay_quiet_and_only_the_dormant_fields_are_refused(self):
        result = snapshot_run(LOCATE + r'''
update=update or function()end
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local catalog=require('hd2runtime/core/entity_catalog')
local NAMES={'BeamWeaponComponentData','ProjectileWeaponComponentData','WeaponDataComponentData',
 'WeaponMagazineComponentData'}
local function capture()
 local out
 local co=coroutine.create(function()
  local reader=Reader.new(runtime)
  local roots=discover.locate(runtime,reader,profile,{entity=true})
  local cat=catalog.capture(reader,roots.entity,profile,NAMES)
  local lib
  for _,c in ipairs(cat.candidates)do if c.resourceHash=='0x968211C0033DCE64'then lib=c end end
  local tables=0;for _ in pairs(cat.tables)do tables=tables+1 end
  local refused={};for k in pairs(lib.refused or{})do refused[#refused+1]=k end;table.sort(refused)
  out={strays=#cat.strays,tables=tables,diagnostics=lib.diagnostics,refused=refused,
   beam=lib.ownership.BeamWeaponComponentData and lib.ownership.BeamWeaponComponentData.recordIndex}
  local ok,why=pcall(cat.record,lib,'ProjectileWeaponComponentData')
  out.projectile_record=ok and'read'or tostring(why)
  ok=pcall(cat.record,lib,'WeaponDataComponentData')
  out.weapon_data_record=ok
  ok=pcall(cat.record,lib,'WeaponMagazineComponentData')
  out.magazine_record=ok
  out.magazine=lib.ownership.WeaponMagazineComponentData and lib.ownership.WeaponMagazineComponentData.recordIndex
 end)
 repeat local ok,why=coroutine.resume(co);check(ok,why)until coroutine.status(co)=='dead'
 return out
end
local lib=hd2.weapon('AR-23 Liberator')
local before=capture()
local h={}
local function ensure(id,field,expect,value,shared)
 local handle
 events.run_as('mods/test/liberator',function()
  handle=hd2.ensure({patch={id=id,target=lib,field=field,expect=expect,value=value,allow_shared=shared}})
 end)
 settle({handle})
 return {status=handle.status,result=handle.result and handle.result.status,error=handle.error and tostring(handle.error)}
end
-- L1: the BeamWeapon row is recorded as the experiment's; the Liberator's ProjectileWeapon is still live.
check(X.apply('L1').ok,'L1')
local l1=capture()
h.l1_rate=ensure('rate-l1',F.weapon.fire_rate,640,700)
check(X.apply('L2').ok,'L2')
local l2=capture()
h.ergonomics=ensure('ergonomics',F.weapon.ergonomics,65,70)
h.rate=ensure('rate',F.weapon.fire_rate,640,750)
h.velocity=ensure('velocity','projectile.velocity',900,950,true)
h.damage=ensure('damage','damage.standard_damage',90,95,true)
-- L2b: the magazine row is part of the recorded state, its record stays readable (its capacity is owned by the
-- default magazine attachment, read-only either way).
check(X.apply('L2b').ok,'L2b')
local l2b=capture()
-- Without the record (another program made the same edit): every write to the Liberator is refused.
local saved=edits.get('0x968211C0033DCE64')
edits.clear('0x968211C0033DCE64')
local unrecorded=capture()
h.unrecorded=ensure('ergonomics-2',F.weapon.recoil_climb_vertical,20,25)
edits.set('0x968211C0033DCE64',saved)
return json.encode({before=before,l1=l1,l2=l2,l2b=l2b,unrecorded=unrecorded,h=h})
''')
        for state in ('before', 'l1', 'l2', 'l2b', 'unrecorded'):
            self.assertEqual(result[state]['strays'], 0, state)   # the 0.30.3 stray-row check stays quiet
            self.assertEqual(result[state]['tables'], 0, state)   # the 0.30.4 component-table guard stays quiet
        self.assertFalse(result['before']['diagnostics'])
        self.assertFalse(result['l1']['diagnostics'])
        self.assertEqual(result['l1']['refused'], ['BeamWeaponComponentData'])
        self.assertEqual(result['l1']['beam'], 23)
        self.assertEqual(result['l1']['projectile_record'], 'read')
        self.assertFalse(result['l2']['diagnostics'])
        self.assertEqual(result['l2']['refused'], ['BeamWeaponComponentData', 'ProjectileWeaponComponentData'])
        self.assertIn('LIBERATOR BEAM EXPERIMENT', result['l2']['projectile_record'])
        self.assertTrue(result['l2']['weapon_data_record'])
        self.assertFalse(result['l2b']['diagnostics'])
        self.assertEqual(result['l2b']['refused'], ['BeamWeaponComponentData', 'ProjectileWeaponComponentData'])
        self.assertEqual(result['l2b']['magazine'], 201)
        self.assertTrue(result['l2b']['magazine_record'])
        self.assertEqual(result['unrecorded']['diagnostics'], ['ProjectileWeaponComponentData membership absent'])
        h = result['h']
        self.assertEqual(h['l1_rate']['result'], 'APPLIED', h['l1_rate'])
        self.assertEqual(h['ergonomics']['result'], 'APPLIED', h['ergonomics'])
        for name in ('rate', 'velocity', 'damage'):
            self.assertEqual(h[name]['status'], 'rejected', (name, h[name]))
            self.assertIn('LIBERATOR BEAM EXPERIMENT', h[name]['error'], name)
        self.assertEqual(h['unrecorded']['status'], 'rejected', h['unrecorded'])
        self.assertIn('membership absent', h['unrecorded']['error'])


if __name__ == '__main__':
    unittest.main()
