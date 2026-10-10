"""The EXPERIMENTAL, SOLO-ONLY multi-weapon beam swap (runtime/experiment_beam_swap.lua, domains/beam_swap.lua;
research/docs/multi-beam-swap-F5FEE03DCFDB.md): the AR-23 Liberator, LAS-58 Talon and SMG-32 Reprimand fire LAS-13
Trident pulses, together or in any subset, sharing BeamWeapon record 23. Branch exp/multi-beam only.

The snapshot tests run on the copy-on-write overlay of the retained current-build snapshot (no game process): every
address is re-derived here independently of the module, from the research's formulas.
"""
import json
import unittest

from support import ROOT, run  # noqa: F401
from test_multi_mod_composition import build_profile, snapshot_run

import sys
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_beam_swap  # noqa: E402
import generate_liberator_beam  # noqa: E402

MULTI = json.loads((ROOT / 'research/multi-beam-swap-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

# The research's own addresses, derived in the test (never through the module under test).
LOCATE = r'''
local X=require('hd2runtime/runtime/experiment_beam_swap')
X.reset_for_tests()
local edits=require('hd2runtime/core/reviewed_edits')
local D=require('hd2runtime/domains/beam_swap')
runtime.package_state=function()return'resident'end
update=update or function()end
local function ptr(at)return b.pointer(runtime.read(at,8),0)end
local game=runtime.address(runtime.module('game.dll'))
local manager=ptr(game+0x346BF98)
local TABLE=ptr(manager+0xF12478+8*270)
local ESH=ptr(manager+0xF12EA0)
local MAGTABLE=ptr(manager+0xF12478+8*5)
local RECORD=TABLE+0xDA8
local DESCRIPTORS=manager+0xF32F18
local INVALID=b.u32(runtime.read(game+0x348456C,4),0)
local W={
 liberator={res='0x968211C0033DCE64',key='64ce3d03c0118296',row=TABLE+16*21,esh=3686,mag=MAGTABLE+8640+160*201+156,
  magrow=MAGTABLE+16*246},
 talon={res='0x416D053372C4E433',key='33e4c47233056d41',row=TABLE+16*11,esh=1075},
 reprimand={res='0x94BD931B5FB4EE95',key='95eeb45f1b93bd94',row=TABLE+16*25,esh=3734,mag=MAGTABLE+8640+160*139+156,
  magrow=MAGTABLE+16*514},
}
local BYID={}
for _,w in ipairs(D.weapons)do BYID[w.id]=w end
local TARGETS={{RECORD,120,'record'}}
for id,w in pairs(W)do
 check(b.resource(runtime.read(ESH+32*w.esh,8),0)==w.res,'entity map row '..w.esh..' is not the '..id)
 w.list=ptr(ESH+32*w.esh+8)
 w.count=b.u32(runtime.read(ESH+32*w.esh+16,4),0)
 TARGETS[#TARGETS+1]={w.row,16,id..'.row'}
 TARGETS[#TARGETS+1]={w.list,w.count*2+2,id..'.list'}      -- +2: the Talon's 12-byte window keeps 2 bytes of the next list
 if w.mag then TARGETS[#TARGETS+1]={w.mag,4,id..'.magazine'}end
end
local function hexat(at,n)return b.hex(runtime.read(at,n))end
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
 for at in pairs(out)do check(inside(at),('a byte outside the targets changed: %X'):format(at))end
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
 runtime.write=function(at,bytes,packed)order[#order+1]={at=at,n=#bytes,t=inside(at)};return write(at,bytes,packed)end
 return order,function()runtime.write=write end
end
local function sequence(order,from)
 local out={}
 for i=from or 1,#order do
  local t=order[i].t or'outside'
  if out[#out]~=t then out[#out+1]=t end
 end
 return out
end
local function state_of(id)return hexat(W[id].row,16)==BYID[id].beam.rowAfter and hexat(W[id].list,W[id].count*2)
 ==BYID[id].membership.after and(not W[id].mag or hexat(W[id].mag,4)=='00000000')end
local function vanilla_of(id)return hexat(W[id].row,16)==string.rep('0',32)and hexat(W[id].list,W[id].count*2)
 ==BYID[id].membership.before and(not W[id].mag or hexat(W[id].mag,4)=='01000000')end
-- The game's BeamWeapon lookup 0x50E880 over the table's current bytes: resource -> record index or false.
local TWO32=4294967296
local function lookup(rows,lo,hi)
 local at=((hi%46)*(TWO32%46)+lo%46)%46
 for _=1,46 do
  local klo,khi=b.u32(rows,at*16),b.u32(rows,at*16+4)
  if klo==lo and khi==hi then return b.u32(rows,at*16+8)end
  if klo==0 and khi==0 then return false end
  at=(at+1)%46
 end
 return false
end
local function all_resources()
 local out,seen={},{}
 local esh=runtime.read(ESH,32*4096)
 for n=0,4095 do
  local lo,hi=b.u32(esh,n*32),b.u32(esh,n*32+4)
  if lo~=0 or hi~=0 then local k=lo..':'..hi;if not seen[k]then seen[k]=true;out[#out+1]={lo,hi}end end
 end
 local rows=runtime.read(TABLE,46*16)
 for n=0,45 do
  local lo,hi=b.u32(rows,n*16),b.u32(rows,n*16+4)
  if lo~=0 or hi~=0 then local k=lo..':'..hi;if not seen[k]then seen[k]=true;out[#out+1]={lo,hi}end end
 end
 return out
end
local function lookups(resources)
 local rows=runtime.read(TABLE,46*16)
 local out={}
 for i,r in ipairs(resources)do out[i]=lookup(rows,r[1],r[2])end
 return out
end
'''


class DomainTests(unittest.TestCase):
    def test_the_domain_is_generated_from_the_research(self):
        self.assertEqual(generate_beam_swap.generate(check=True), [])
        domain = generate_beam_swap.build()
        self.assertEqual(domain['order'], ['liberator', 'talon', 'reprimand'])
        self.assertEqual([w['beam']['row'] for w in domain['weapons']], [21, 11, 25])
        self.assertEqual(domain['beam']['recordOffset'], 0xDA8)
        rows = {w['id']: w for w in domain['weapons']}
        self.assertEqual(rows['talon']['beam']['rowAfter'], '33e4c47233056d411700000000000000')
        self.assertEqual(rows['reprimand']['beam']['rowAfter'], '95eeb45f1b93bd941700000000000000')
        self.assertIsNone(rows['talon']['magazine'])
        self.assertEqual((rows['reprimand']['magazine']['row'], rows['reprimand']['magazine']['record'],
                          rows['reprimand']['magazine']['windowOffset']), (514, 139, 0x793C))
        self.assertEqual((rows['talon']['membership']['firstChanged'], rows['talon']['membership']['endChanged']),
                         (40, 48))
        # The Liberator entry is the live-proven write set; every proven pin is kept.
        proven = generate_liberator_beam.build()
        self.assertEqual(rows['liberator']['beam']['rowAfter'], proven['beam']['rowAfter'])
        self.assertEqual(rows['liberator']['membership']['after'], proven['membership']['after'])
        self.assertEqual(domain['beam']['recordAfter'], proven['beam']['recordAfter'])
        self.assertTrue({p['rva'] for p in proven['pins']} <= {p['rva'] for p in domain['pins']})
        multi_pins = {p['rva'] for rows_ in MULTI['pins'].values() for p in rows_}
        self.assertEqual(len(multi_pins), 32)
        self.assertTrue(multi_pins <= {p['rva'] for p in domain['pins']})
        # The research: no vanilla table shares a record; record 23's only readers; every subset of the overlay.
        self.assertEqual(MULTI['sharedRecord']['vanillaCensus']['recordsSharedByTwoOrMoreRows'], 0)
        self.assertEqual(MULTI['sharedRecord']['slot270ReadSites'], ['0x50E88F', '0x50ECA7', '0x841BC9'])
        self.assertEqual(len(MULTI['overlay']['subsets']), 8)
        self.assertEqual(MULTI['overlay']['resourcesChecked'], 1909)
        self.assertEqual(MULTI['weapons']['talon']['afterNotInTrident'], [])
        self.assertEqual(MULTI['weapons']['reprimand']['afterNotInMeltagun'], [])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
    def test_every_pin_is_the_game_image_bytes(self):
        from scan import xref
        _, data, sha = xref.load_image('game.dll')
        domain = generate_beam_swap.build()
        self.assertEqual(sha, domain['source']['gameDllSha256'])
        for pin in domain['pins']:
            expected = bytes.fromhex(pin['hex'])
            self.assertEqual(data[pin['rva']:pin['rva'] + len(expected)], expected, hex(pin['rva']))


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class BeamSwapSnapshotTests(unittest.TestCase):
    def test_all_three_in_one_transaction_exact_bytes_order_and_full_restore(self):
        result = snapshot_run(LOCATE + r'''
for id in pairs(W)do check(vanilla_of(id),'the snapshot does not hold the '..id..' before bytes')end
check(hexat(RECORD,120)==D.beam.recordBefore,'record 23 is not the file\'s')
local st=X.status()
check(st.ok and st.record=='vanilla'and#st.weapons==3,'status '..tostring(st.reason))
for _,w in ipairs(st.weapons)do check(w.state=='vanilla'and w.live==0,w.name..' '..tostring(w.state))end
check(counts.writes==0 and counts.protection_changes==0,'status wrote')
local order,stop=writes_log()
local r=X.apply()
check(r.ok,'apply '..tostring(r.reason))
for id in pairs(W)do check(state_of(id),id..' not applied')end
check(hexat(RECORD,120)==D.beam.recordAfter,'record 23 is not the Trident copy')
local applied_bytes=only_targets()
local apply_sequence=sequence(order)
local row_writes={}
for _,o in ipairs(order)do
 for id,w in pairs(W)do if o.at>=w.row and o.at<w.row+16 then row_writes[#row_writes+1]=id..'+'..(o.at-w.row)end end
end
local list_writes={}
for _,o in ipairs(order)do
 for id,w in pairs(W)do if o.at>=w.list-2 and o.at<w.list+w.count*2 then list_writes[id]={o.at-w.list,o.n}end end
end
for id,w in pairs(W)do check(edits.get(w.res)and edits.get(w.res).stage=='applied',id..' not recorded')end
check(next(protection)==nil,'a page protection was left changed')
-- Applying again writes nothing.
local n=#order
check(X.apply().ok and#order==n,'a second apply wrote')
-- Restore: one transaction, reverse order, record 23 last; every byte returns.
local m=#order
local back=X.restore()
check(back.ok and back.record_restored,'restore '..tostring(back.reason))
local restore_sequence=sequence(order,m+1)
stop()
local _,left=changed()
check(left==0,left..' bytes still differ from the snapshot after the restore')
for id,w in pairs(W)do
 check(vanilla_of(id),id..' not vanilla after the restore')
 check(edits.get(w.res)==nil,id..' still recorded')
end
check(next(protection)==nil,'a page protection was left changed after the restore')
local logged={}
for _,line in ipairs(LINES)do if line:find('^MULTI BEAM:')then logged[#logged+1]=line end end
return json.encode({applied_bytes=applied_bytes,apply_sequence=apply_sequence,row_writes=row_writes,
 list_writes=list_writes,restore_sequence=restore_sequence,writes=r.writes,logged=logged})
''')
        self.assertEqual(result['apply_sequence'], [
            'record', 'liberator.row', 'liberator.list', 'liberator.magazine', 'talon.row', 'talon.list',
            'reprimand.row', 'reprimand.list', 'reprimand.magazine'])
        self.assertEqual(result['row_writes'], ['liberator+8', 'liberator+0', 'talon+8', 'talon+0',
                                                'reprimand+8', 'reprimand+0'])
        self.assertEqual(result['list_writes'], {'liberator': [38, 8], 'talon': [38, 12], 'reprimand': [38, 8]})
        self.assertEqual(result['restore_sequence'], [
            'reprimand.magazine', 'reprimand.list', 'reprimand.row', 'talon.list', 'talon.row',
            'liberator.magazine', 'liberator.list', 'liberator.row', 'record'])
        rec = MULTI['sharedRecord']['beamRecord']
        record_diff = sum(1 for a, c in zip(bytes.fromhex(rec['before']), bytes.fromhex(rec['after'])) if a != c)
        rows_diff = sum(sum(1 for c in bytes.fromhex(MULTI['weapons'][k]['beam']['after']) if c)
                        for k in ('liberator', 'talon', 'reprimand'))
        # Lists: Liberator / Reprimand 3 entries (3 bytes differ each), Talon 4 entries; magazines 1 byte each.
        lists_diff = 0
        for k in ('liberator', 'talon', 'reprimand'):
            m = MULTI['weapons'][k]['membership']
            lists_diff += sum(1 for a, c in zip(bytes.fromhex(m['beforeHex']), bytes.fromhex(m['afterHex'])) if a != c)
        self.assertEqual(result['applied_bytes'], record_diff + rows_diff + lists_diff + 2)
        self.assertTrue(any('LAS-58 Talon APPLIED' in line for line in result['logged']))
        self.assertTrue(any('RESTART THE GAME' in line for line in result['logged']))

    def test_every_other_lookup_is_unchanged(self):
        result = snapshot_run(LOCATE + r'''
local resources=all_resources()
local before=lookups(resources)
local function diff(after)
 local out={}
 for i,r in ipairs(resources)do
  if before[i]~=after[i]then out[#out+1]=('0x%08X%08X=%s'):format(r[2],r[1],tostring(after[i]))end
 end
 table.sort(out)
 return out
end
check(X.apply({'talon'}).ok,'talon')
local talon=diff(lookups(resources))
check(X.apply().ok,'all')
local all=diff(lookups(resources))
check(X.restore({'talon'}).ok,'restore talon')
local two=diff(lookups(resources))
check(hexat(RECORD,120)==D.beam.recordAfter,'record 23 restored while rows still name it')
check(X.restore().ok,'restore')
local none=diff(lookups(resources))
return json.encode({count=#resources,talon=talon,all=all,two=two,none=none})
''')
        self.assertGreaterEqual(result['count'], 1900)
        self.assertEqual(result['talon'], ['0x416D053372C4E433=23'])
        self.assertEqual(result['all'], ['0x416D053372C4E433=23', '0x94BD931B5FB4EE95=23', '0x968211C0033DCE64=23'])
        self.assertEqual(result['two'], ['0x94BD931B5FB4EE95=23', '0x968211C0033DCE64=23'])
        self.assertFalse(result['none'])

    def test_subsets_share_the_record_and_restore_it_last(self):
        result = snapshot_run(LOCATE + r'''
local order,stop=writes_log()
check(X.apply({'reprimand'}).ok,'reprimand')
local first=sequence(order)
local n=#order
check(X.apply({'liberator','talon'}).ok,'liberator + talon')
local second=sequence(order,n+1)
n=#order
check(X.restore({'liberator'}).ok,'restore liberator')
local third=sequence(order,n+1)
check(hexat(RECORD,120)==D.beam.recordAfter and state_of('talon')and state_of('reprimand')and vanilla_of('liberator'),
 'a partial restore touched another weapon')
check(edits.get(W.liberator.res)==nil and edits.get(W.talon.res).stage=='applied','edits after the partial restore')
n=#order
check(X.restore().ok,'restore')
local fourth=sequence(order,n+1)
stop()
local _,left=changed()
check(left==0,left..' bytes differ')
return json.encode({first=first,second=second,third=third,fourth=fourth})
''')
        self.assertEqual(result['first'], ['record', 'reprimand.row', 'reprimand.list', 'reprimand.magazine'])
        self.assertEqual(result['second'], ['liberator.row', 'liberator.list', 'liberator.magazine', 'talon.row',
                                            'talon.list'])
        self.assertEqual(result['third'], ['liberator.magazine', 'liberator.list', 'liberator.row'])
        self.assertEqual(result['fourth'], ['reprimand.magazine', 'reprimand.list', 'reprimand.row', 'talon.list',
                                            'talon.row', 'record'])

    def test_any_before_byte_mismatch_refuses_and_writes_nothing(self):
        result = snapshot_run(LOCATE + r'''
local cases={
 {W.talon.row+3,'the Talon row'},{W.reprimand.row+9,'the Reprimand row'},{W.liberator.row,'the Liberator row'},
 {RECORD+60,'record 23'},{W.talon.list+44,'the Talon list'},{W.talon.list+2,'the Talon list (an unchanged entry)'},
 {W.reprimand.list+42,'the Reprimand list'},{W.reprimand.mag,'the Reprimand chamber byte'},
 {W.reprimand.mag+1,'the byte after the Reprimand chamber flag'},{W.liberator.mag,'the Liberator chamber byte'},
 {W.reprimand.magrow+8,'the Reprimand magazine row'},
 {TABLE+0x2E0+18*0x78+104,'the Trident record (the copy source)'},{TABLE+20*16+8,'the Trident row'},
}
local seen={}
for _,c in ipairs(cases)do
 local original=runtime.read(c[1],1)
 overlay[c[1]]=string.char((original:byte()+1)%256)
 local r=X.apply()
 local r2=X.apply({'talon'})
 check(not r.ok and not r2.ok,c[2]..' changed but the apply went ahead')
 seen[#seen+1]=c[2]..': '..r.reason
 overlay[c[1]]=nil
end
check(counts.writes==0 and counts.protection_changes==0,'a refused apply wrote')
-- Another row naming record 23, or naming one of the weapons.
local free
for n=0,45 do if n~=21 and n~=11 and n~=25 and b.hex(runtime.read(TABLE+16*n,8))==string.rep('0',16)then free=n;break end end
overlay[TABLE+16*free]=b.unhex('0100000000000080')..b.encode(23,'u32')..b.encode(0,'u32')
local r=X.apply()
check(not r.ok and r.reason:find('names record 23',1,true),tostring(r.reason))
overlay[TABLE+16*free]=b.unhex(W.talon.key)..b.encode(7,'u32')..b.encode(0,'u32')
r=X.apply({'liberator'})
check(not r.ok and r.reason:find('names the LAS-58 Talon',1,true),tostring(r.reason))
overlay[TABLE+16*free]=nil
check(counts.writes==0,'a refused apply wrote')
-- A changed pin (native code): unproven, refused.
X.reset_for_tests();runtime.package_state=function()return'resident'end
local pin=D.pins[#D.pins]
overlay[game+pin.rva]=string.char((b.unhex(pin.hex):byte()+1)%256)
r=X.apply()
check(not r.ok and r.reason:find('UNPROVEN',1,true),tostring(r.reason))
overlay[game+pin.rva]=nil
X.reset_for_tests();runtime.package_state=function()return'resident'end
-- The Trident package not resident: the apply is refused; a restore needs no package.
check(X.apply({'talon'}).ok,'talon')
runtime.package_state=function()return'absent'end
r=X.apply()
check(not r.ok and r.reason:find('package is absent',1,true),tostring(r.reason))
check(vanilla_of('liberator')and vanilla_of('reprimand'),'wrote without the package')
check(X.restore().ok,'a restore needs no package')
runtime.package_state=function()return'resident'end
-- A foreign state of an applied weapon: refused both ways, every weapon.
check(X.apply().ok,'all')
overlay[W.talon.list+44]=string.char(0x7F)
check(not X.restore().ok and not X.apply().ok and not X.restore({'reprimand'}).ok,'a foreign state was written over')
overlay[W.talon.list+44]=nil
check(X.restore().ok,'restore after the foreign byte went away')
return json.encode(seen)
''')
        self.assertEqual(len(result), 13)
        for line in result:
            self.assertTrue('state the experiment did not make' in line or 'CONFLICT' in line
                            or 'not row' in line, line)

    def test_a_live_instance_of_a_written_weapon_refuses(self):
        result = snapshot_run(LOCATE + r'''
local slot=free_descriptor()
check(slot,'no free descriptor')
local function live(id)return b.unhex(W[id].key)..b.encode(0x00400123,'u32')end
overlay[slot]=live('talon')
local st=X.status()
local talon_live
for _,w in ipairs(st.weapons)do if w.id=='talon'then talon_live=w.live end end
check(talon_live==1,'census '..tostring(talon_live))
local r=X.apply()
check(not r.ok and r.reason:find('1 live LAS-58 Talon',1,true),'all with a live Talon: '..tostring(r.reason))
check(counts.writes==0 and counts.protection_changes==0,'a refused apply wrote')
-- A weapon that is not written is not gated: the Liberator alone goes ahead with a live Talon.
check(X.apply({'liberator','reprimand'}).ok,'Liberator + Reprimand with a live Talon')
-- A live Reprimand refuses the restore of the Reprimand (and of everything with it); nothing is written.
overlay[slot]=live('reprimand')
local writes=counts.writes
r=X.restore()
check(not r.ok and r.reason:find('live SMG-32 Reprimand',1,true),'restore with a live Reprimand: '..tostring(r.reason))
check(counts.writes==writes,'a refused restore wrote')
check(state_of('reprimand')and state_of('liberator'),'the bytes moved')
-- Restoring the Liberator alone is not gated by the Reprimand.
check(X.restore({'liberator'}).ok,'Liberator restore with a live Reprimand')
-- A free descriptor (the invalid entity id) is not counted.
overlay[slot]=b.unhex(W.reprimand.key)..b.encode(INVALID,'u32')
check(X.restore().ok,'restore after the Reprimand was destroyed')
local _,left=changed()
overlay[slot]=nil
return json.encode({ok=true})
''')
        self.assertEqual(result, {'ok': True})

    def test_a_failed_write_rolls_back_every_weapon(self):
        result = snapshot_run(LOCATE + r'''
local write=runtime.write
-- The Reprimand's chamber byte (the last write of the transaction) fails: everything written before is rolled back.
runtime.write=function(at,bytes,packed)
 if at==W.reprimand.mag and bytes==string.rep('\0',4)then return false,'test failure',0 end
 return write(at,bytes,packed)
end
local r=X.apply()
runtime.write=write
check(not r.ok and r.reason:find('rollback',1,true),tostring(r.reason))
for id in pairs(W)do check(vanilla_of(id),id..' not vanilla after the rollback')end
check(hexat(RECORD,120)==D.beam.recordBefore,'record 23 not rolled back')
check(next(protection)==nil,'a page protection was left changed')
for id,w in pairs(W)do check(edits.get(w.res)==nil,id..' recorded after a failed apply')end
local st=X.status()
for _,w in ipairs(st.weapons)do check(w.state=='vanilla',w.name..' '..w.state)end
-- The same failure on the restore: everything stays applied.
check(X.apply().ok,'apply')
runtime.write=function(at,bytes,packed)
 if at==W.talon.row then return false,'test failure',0 end
 return write(at,bytes,packed)
end
r=X.restore()
runtime.write=write
check(not r.ok,'restore went ahead')
for id in pairs(W)do check(state_of(id),id..' not applied after the failed restore')end
check(hexat(RECORD,120)==D.beam.recordAfter,'record 23 changed by a failed restore')
check(X.restore().ok,'restore')
local _,left=changed()
check(left==0,left..' bytes differ')
return json.encode({reason=r.reason})
''')
        self.assertIn('rollback', result['reason'])

    def test_the_liberator_proof_states(self):
        result = snapshot_run(LOCATE + r'''
local L=require('hd2runtime/runtime/experiment_liberator_beam')
L.reset_for_tests()
-- LiberatorBeamProof L1 / L2: part-swapped, refused here with the hint.
check(L.apply('L1').ok,'L1')
local r=X.apply({'talon'})
check(not r.ok and r.reason:find('part-swapped',1,true)and r.reason:find('LiberatorBeamProof',1,true),tostring(r.reason))
check(L.apply('L2').ok,'L2')
r=X.restore()
check(not r.ok and r.reason:find('part-swapped',1,true),tostring(r.reason))
-- L2b is exactly this experiment's Liberator state: recognised and restorable here.
check(L.apply('L2b').ok,'L2b')
local st=X.status()
local lib
for _,w in ipairs(st.weapons)do if w.id=='liberator'then lib=w.state end end
check(lib=='applied','L2b seen as '..tostring(lib))
check(X.apply().ok,'the Talon and Reprimand join the Liberator')
-- The Liberator proof refuses a table it did not make (other rows name record 23).
local l=L.status()
check(not l.ok and l.reason:find('names record 23',1,true),tostring(l.reason))
check(X.restore().ok,'restore all')
local _,left=changed()
check(left==0,left..' bytes differ')
-- And the proven path still runs alone.
check(L.apply('L2b').ok and L.restore().ok,'LiberatorBeamProof L2b + restore')
_,left=changed()
check(left==0,left..' bytes differ after the Liberator-only path')
L.reset_for_tests()
return json.encode({ok=true})
''')
        self.assertEqual(result, {'ok': True})

    def test_another_lobby_member_refuses(self):
        result = snapshot_run(LOCATE + r'''
local real=package.loaded['hd2runtime/runtime/peer_channel']
package.loaded['hd2runtime/runtime/peer_channel']={prove=function()return true end,
 lobby=function()return {members={{peer='A',['local']=true},{peer='B'}}}end}
local r=X.apply()
check(not r.ok and r.reason:find('solo only: 2 lobby members',1,true),tostring(r.reason))
package.loaded['hd2runtime/runtime/peer_channel']={prove=function()return true end,
 lobby=function()return nil,'UNREADABLE','the member list'end}
r=X.apply()
check(not r.ok and r.reason:find('lobby state is unreadable',1,true),tostring(r.reason))
check(counts.writes==0,'wrote without a proven solo lobby')
package.loaded['hd2runtime/runtime/peer_channel']=real
check(X.apply().ok and X.restore().ok,'solo again')
return json.encode({ok=true})
''')
        self.assertEqual(result, {'ok': True})

    def test_guards_stay_quiet_and_only_the_dormant_fields_are_refused(self):
        result = snapshot_run(LOCATE + r'''
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local catalog=require('hd2runtime/core/entity_catalog')
local NAMES={'BeamWeaponComponentData','ProjectileWeaponComponentData','WeaponDataComponentData',
 'WeaponMagazineComponentData','WeaponHeatComponentData'}
local function capture()
 local out={}
 local co=coroutine.create(function()
  local reader=Reader.new(runtime)
  local roots=discover.locate(runtime,reader,profile,{entity=true})
  local cat=catalog.capture(reader,roots.entity,profile,NAMES)
  local tables=0;for _ in pairs(cat.tables)do tables=tables+1 end
  out.strays=#cat.strays;out.tables=tables;out.weapons={}
  for _,c in ipairs(cat.candidates)do
   for id,w in pairs(W)do
    if c.resourceHash==w.res then
     local refused={};for k in pairs(c.refused or{})do refused[#refused+1]=k end;table.sort(refused)
     local e={diagnostics=c.diagnostics,refused=refused,
      beam=c.ownership.BeamWeaponComponentData and c.ownership.BeamWeaponComponentData.recordIndex}
     local ok,why=pcall(cat.record,c,'ProjectileWeaponComponentData');e.projectile=ok and'read'or tostring(why)
     e.weapon_data=pcall(cat.record,c,'WeaponDataComponentData')
     if w.mag then e.magazine=pcall(cat.record,c,'WeaponMagazineComponentData')end
     if id=='talon'then e.heat=pcall(cat.record,c,'WeaponHeatComponentData')end
     out.weapons[id]=e
    end
   end
  end
 end)
 repeat local ok,why=coroutine.resume(co);check(ok,why)until coroutine.status(co)=='dead'
 return out
end
local before=capture()
check(X.apply().ok,'apply')
local after=capture()
local h={}
local function ensure(id,target,field,expect,value,shared)
 local handle
 events.run_as('mods/test/multibeam',function()
  handle=hd2.ensure({patch={id=id,target=target,field=field,expect=expect,value=value,allow_shared=shared}})
 end)
 settle({handle})
 return {status=handle.status,result=handle.result and handle.result.status,error=handle.error and tostring(handle.error)}
end
h.talon_rate=ensure('talon-rate',hd2.weapon('LAS-58 Talon'),F.weapon.fire_rate,750,800)
h.reprimand_rate=ensure('reprimand-rate',hd2.weapon('SMG-32 Reprimand'),F.weapon.fire_rate,490,520)
h.liberator_ergo=ensure('liberator-ergo',hd2.weapon('AR-23 Liberator'),F.weapon.ergonomics,65,70)
-- Without the record (another program made the same edit): every write to that weapon is refused.
local saved=edits.get(W.talon.res)
edits.clear(W.talon.res)
local unrecorded=capture()
edits.set(W.talon.res,saved)
check(X.restore().ok,'restore')
local restored=capture()
return json.encode({before=before,after=after,unrecorded=unrecorded,restored=restored,h=h})
''')
        for state in ('before', 'after', 'unrecorded', 'restored'):
            self.assertEqual(result[state]['strays'], 0, state)
            self.assertEqual(result[state]['tables'], 0, state)
        for wid in ('liberator', 'talon', 'reprimand'):
            self.assertFalse(result['before']['weapons'][wid]['diagnostics'], wid)
            a = result['after']['weapons'][wid]
            self.assertFalse(a['diagnostics'], (wid, a['diagnostics']))
            self.assertEqual(a['refused'], ['BeamWeaponComponentData', 'ProjectileWeaponComponentData'], wid)
            self.assertEqual(a['beam'], 23, wid)
            self.assertIn('MULTI BEAM EXPERIMENT', a['projectile'], wid)
            self.assertTrue(a['weapon_data'], wid)
            self.assertFalse(result['restored']['weapons'][wid]['diagnostics'], wid)
            self.assertFalse(result['restored']['weapons'][wid]['refused'], wid)
        self.assertTrue(result['after']['weapons']['reprimand']['magazine'])
        self.assertTrue(result['after']['weapons']['talon']['heat'])
        self.assertEqual(result['unrecorded']['weapons']['talon']['diagnostics'],
                         ['ProjectileWeaponComponentData membership absent'])
        h = result['h']
        for name in ('talon_rate', 'reprimand_rate'):
            self.assertEqual(h[name]['status'], 'rejected', (name, h[name]))
            self.assertIn('MULTI BEAM EXPERIMENT', h[name]['error'], name)
        self.assertEqual(h['liberator_ergo']['result'], 'APPLIED', h['liberator_ergo'])


if __name__ == '__main__':
    unittest.main()
