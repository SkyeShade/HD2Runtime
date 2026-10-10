"""The EXPERIMENTAL, SOLO-ONLY Runtime-owned relocated BeamWeapon table (runtime/experiment_beam_table.lua,
core/owned_tables.lua, domains/beam_table.lua; research/docs/beam-table-relocation-F5FEE03DCFDB.md) and the multi-weapon
beam swap's 'owned table' path on top of it (runtime/experiment_beam_swap.lua 0.3.0): the AR-23 Liberator, LAS-58 Talon
and SMG-32 Reprimand each fire their OWN BeamWeapon record (24, 25, 26) in a never-freed copy the game is switched to
read, with their own rate of fire and pulse. Branch exp/multi-beam only.

The snapshot tests run on the copy-on-write overlay of the retained current-build snapshot (no game process), with a
stand-in for the adapter's permanent blocks (Lua memory at addresses the snapshot does not map); every address is
re-derived here from the research's formulas, never through the module under test.
"""
import json
import struct
import unittest

from support import ROOT, run  # noqa: F401
from test_multi_mod_composition import build_profile, snapshot_run
from test_beam_swap import LOCATE

import sys
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_beam_table  # noqa: E402

RESEARCH = json.loads((ROOT / 'research/beam-table-relocation-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

# Permanent blocks (runtime/windows_write.lua permanent_block): committed private pages, read-only after the fill,
# never freed. Here: Lua memory at 0x7FFE00000000.., with its own protection (the transaction opens and restores it).
OWNED = r'''
local BLOCKS,next_block={},0x7FFE00000000
counts.permanent_blocks=0;counts.owned_writes=0
local base_query,base_read,base_write,base_protect=runtime.query,runtime.read,runtime.write,runtime.protect
local function block_of(at)
 for address,blk in pairs(BLOCKS)do if at>=address and at<address+blk.size then return address,blk end end
end
function runtime.permanent_block(bytes)
 assert(type(bytes)=='string'and#bytes>0 and#bytes<=65536,'permanent block size')
 local address=next_block;next_block=next_block+0x10000
 local size=#bytes+(4096-#bytes%4096)%4096
 BLOCKS[address]={bytes=bytes..string.rep('\0',size-#bytes),size=size,protect=2}
 counts.permanent_blocks=counts.permanent_blocks+1
 return address
end
function runtime.query(at)
 local address,blk=block_of(at)
 if address then return {base=address,size=blk.size,state=0x1000,type=0x20000,allocation_base=address,
  protect=blk.protect,allocation_protect=4}end
 return base_query(at)
end
function runtime.read(at,n)
 local address,blk=block_of(at)
 if address then
  if at+n>address+blk.size then return nil end
  return blk.bytes:sub(at-address+1,at-address+n)
 end
 return base_read(at,n)
end
function runtime.write(at,bytes,packed)
 local address,blk=block_of(at)
 if address then
  assert(blk.protect==4,'owned write without writable page')
  counts.writes=counts.writes+1;counts.owned_writes=counts.owned_writes+1
  blk.bytes=blk.bytes:sub(1,at-address)..bytes..blk.bytes:sub(at-address+#bytes+1)
  return true,nil,#bytes
 end
 return base_write(at,bytes,packed)
end
function runtime.protect(page,size,value)
 local address,blk=block_of(page)
 if address then counts.protection_changes=counts.protection_changes+1;local old=blk.protect;blk.protect=value;return old end
 return base_protect(page,size,value)
end
local TB=require('hd2runtime/runtime/experiment_beam_table')
local OT=require('hd2runtime/core/owned_tables')
local T=require('hd2runtime/domains/beam_table')
local SLOT=manager+0xF12478+8*270
local OWN={liberator=24,talon=25,reprimand=26}
local function slot()return ptr(SLOT)end
local TRIDENT_RECORD=runtime.read(TABLE+0x2E0+18*0x78,0x78)
local FILE=runtime.read(TABLE-32,32+0x2E0+24*0x78)
-- The copy the game reads now (rows + records 0..26), or nil when it reads the file's table.
local function copy()
 local at=slot()
 if at==TABLE then return nil end
 return runtime.read(at,0x2E0+27*0x78),at
end
local function record_of(rows,index)return rows:sub(0x2E0+index*0x78+1,0x2E0+(index+1)*0x78)end
local function lookups_in(rows,resources)
 local out={}
 for i,r in ipairs(resources)do out[i]=lookup(rows,r[1],r[2])end
 return out
end
local function blocks()local n=0 for _ in pairs(BLOCKS)do n=n+1 end return n end
'''


class DomainTests(unittest.TestCase):
    def test_the_domain_is_generated_from_the_research(self):
        self.assertEqual(generate_beam_table.generate(check=True), [])
        domain = generate_beam_table.build()
        self.assertEqual(domain['slot'], {'index': 270, 'offset': 0xF12CE8})
        self.assertEqual(domain['records'], {'liberator': 24, 'talon': 25, 'reprimand': 26})
        self.assertEqual(domain['layout']['size'], 4040)
        self.assertEqual([(s['id'], s['offset'], s['storage'], s['min'], s['max']) for s in domain['settings']],
                         [('fire_rate', 104, 'i32', 1, 6000), ('pulse_beams', 108, 'i32', 1, 8),
                          ('pulse_seconds', 112, 'f32', 0, 10)])

    def test_every_reader_of_the_table_pointer_is_classified(self):
        census = RESEARCH['slotCensus']
        self.assertEqual(sorted(census['slot270']['sites']), ['0x50E88F', '0x50ECA7', '0x841BC9'])
        self.assertEqual(len(census['slot270']['rawHits']), 3)
        self.assertEqual(census['slotArrayBase']['sites'], {
            '0x4F2FDF': 'slot 0', '0x4F3091': 'slot 0', '0x56953B': 'slot 29', '0x569B78': 'slot 271',
            '0x747FEC': 'slot 271', '0x9F1E24': 'slot 29', '0xFDB636': 'the loader store'})
        self.assertFalse(census['otherWindowValuesAddressingASlot'])
        self.assertEqual(RESEARCH['entryPoints']['0xFDB860']['callsOrJumps'], [])
        self.assertEqual(RESEARCH['entryPoints']['0xFDB440']['callsOrJumps'], ['0xAE0D8B', '0xFDB880'])
        self.assertFalse(RESEARCH['lookup']['recordIndexBounded'])
        self.assertTrue(RESEARCH['unloadStoresNoSlot'])
        self.assertEqual(len(RESEARCH['observations']), 9)
        for o in RESEARCH['observations']:
            self.assertGreaterEqual(o['resourcesChecked'], 1909, o['snapshot'])
            self.assertEqual(o['answersChanged'], ['0x416D053372C4E433=25', '0x94BD931B5FB4EE95=26',
                                                   '0x968211C0033DCE64=24'], o['snapshot'])
            self.assertTrue(o['otherRecordsByteIdentical'] and o['defaultRecordUnchanged'], o['snapshot'])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
    def test_every_pin_is_the_game_image_bytes(self):
        from scan import xref
        _, data, sha = xref.load_image('game.dll')
        domain = generate_beam_table.build()
        self.assertEqual(sha, domain['source']['gameDllSha256'])
        self.assertGreaterEqual(len(domain['pins']), 20)
        for pin in domain['pins']:
            expected = bytes.fromhex(pin['hex'])
            self.assertEqual(data[pin['rva']:pin['rva'] + len(expected)], expected, hex(pin['rva']))


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class OwnedTableSnapshotTests(unittest.TestCase):
    def test_copy_switch_apply_and_restore_every_lookup_byte_identical_but_the_three(self):
        result = snapshot_run(LOCATE + OWNED + r'''
local resources=all_resources()
check(#resources>=1900,'resources '..#resources)
local file_rows=runtime.read(TABLE,0x2E0+24*0x78)
local before=lookups_in(file_rows,resources)
local st=X.status()
check(st.ok and st.path=='none'and st.table=='in_place'and st.owned_available,'status '..tostring(st.reason))
-- Apply all three: the owned path (the default when available).
local order,stop=writes_log()
local r=X.apply()
check(r.ok and r.path=='owned','apply '..tostring(r.reason))
local rows,at=copy()
check(rows,'the game does not read a copy')
check(blocks()==1 and counts.permanent_blocks==1,'one copy built')
-- The copy: framing, rows (the file's but the three), records 0..23 the file's, 24..26 the Trident's, the trailer.
check(runtime.read(at-32,32)==FILE:sub(1,32),'copy framing')
local own_rows={}
for id,w in pairs(W)do own_rows[(w.row-TABLE)/16]=id end
for n=0,45 do
 local c,f=rows:sub(n*16+1,n*16+16),file_rows:sub(n*16+1,n*16+16)
 if own_rows[n]then
  local id=own_rows[n]
  check(c==b.unhex(W[id].key)..b.encode(OWN[id],'u32')..b.encode(0,'u32'),'own row of the '..id)
  check(f==string.rep('\0',16),'the file row of the '..id..' was written')
 else check(c==f,'copy row '..n..' differs')end
end
for k=0,23 do check(record_of(rows,k)==record_of(file_rows,k),'copy record '..k..' differs')end
for id,k in pairs(OWN)do check(record_of(rows,k)==TRIDENT_RECORD,'record '..k..' is not the Trident record')end
check(runtime.read(at+0x2E0+27*0x78,16)=='HD2RT-OWNED-BEAM','trailer')
-- The file's table is untouched: the only entity-file bytes changed are the lists and magazine bytes; the slot.
check(runtime.read(TABLE,0x2E0+24*0x78)==file_rows,'the file table was written')
local out,n_changed=changed()
for address in pairs(out)do
 local t=inside(address)
 check((t and(t:find('%.list$')or t:find('%.magazine$')))or(address>=SLOT and address<SLOT+8),
  ('a byte outside the lists, magazines and slot changed: %X (%s)'):format(address,tostring(t)))
end
-- Every resource's lookup through the copy: the file's record bytes except the three.
local after=lookups_in(rows,resources)
local answers={}
for i,res in ipairs(resources)do
 if before[i]~=after[i]then answers[#answers+1]=('0x%08X%08X=%s'):format(res[2],res[1],tostring(after[i]))
 elseif after[i]then
  check(record_of(rows,after[i])==record_of(file_rows,before[i]),'record bytes differ for a resource')
 end
end
table.sort(answers)
-- The write order: slot first, then lists and magazines.
local sequence={}
for _,o in ipairs(order)do
 local t=(o.at>=SLOT and o.at<SLOT+8)and'slot'or o.t or'outside'
 if sequence[#sequence]~=t then sequence[#sequence+1]=t end
end
-- The registry, the reviewed edits, the status, the per-weapon damage module.
local e=OT.get('BeamWeaponComponentData')
check(e and e.table==at and e.original==TABLE and e.records==27,'registry')
for id,w in pairs(W)do check(edits.get(w.res)and edits.get(w.res).stage=='applied',id..' not recorded')end
local st2=X.status()
check(st2.ok and st2.path=='owned table'and st2.table=='owned','status after '..tostring(st2.reason))
for _,w in ipairs(st2.weapons)do
 check(w.state=='applied'and w.path=='owned table'and w.settings.fire_rate==300 and w.settings.pulse_beams==2,w.name)
end
local BD=require('hd2runtime/runtime/experiment_beam_damage')
BD.reset_for_tests()
local d=BD.set('liberator',{damage_multiplier=10})
check(d.ok,'beam damage on the owned path: '..tostring(d.reason))
-- A second apply writes nothing.
local n=#order
check(X.apply().ok and#order==n,'a second apply wrote')
-- Restore: lists back, then the slot; every overlay byte back; the copy stays (never freed) but is forgotten.
local m=#order
local back=X.restore()
check(back.ok and back.slot_restored,'restore '..tostring(back.reason))
local rsequence={}
for i=m+1,#order do
 local o=order[i]
 local t=(o.at>=SLOT and o.at<SLOT+8)and'slot'or o.t or'outside'
 if rsequence[#rsequence]~=t then rsequence[#rsequence+1]=t end
end
stop()
local _,left=changed()
check(left==0,left..' bytes still differ from the snapshot after the restore')
check(slot()==TABLE and OT.get('BeamWeaponComponentData')==nil and blocks()==1,'slot / registry / copy after restore')
for id,w in pairs(W)do check(vanilla_of(id)and edits.get(w.res)==nil,id..' after restore')end
check(next(protection)==nil,'a page protection was left changed')
local logged={}
for _,line in ipairs(LINES)do if line:find('^MULTI BEAM:')or line:find('^BEAM TABLE:')then logged[#logged+1]=line end end
return json.encode({answers=answers,sequence=sequence,rsequence=rsequence,changed=n_changed,count=#resources,
 owned_writes=counts.owned_writes,logged=logged})
''')
        self.assertEqual(result['answers'], ['0x416D053372C4E433=25', '0x94BD931B5FB4EE95=26',
                                             '0x968211C0033DCE64=24'])
        self.assertEqual(result['sequence'], ['slot', 'liberator.list', 'liberator.magazine', 'talon.list',
                                              'reprimand.list', 'reprimand.magazine'])
        self.assertEqual(result['rsequence'], ['reprimand.magazine', 'reprimand.list', 'talon.list',
                                               'liberator.magazine', 'liberator.list', 'slot'])
        self.assertEqual(result['owned_writes'], 0)       # the copy was built with its rows: no write into it
        self.assertTrue(any('APPLIED [owned table]' in line for line in result['logged']))
        self.assertTrue(any('copy 1 built' in line for line in result['logged']))

    def test_per_weapon_settings_land_in_each_weapons_own_record(self):
        result = snapshot_run(LOCATE + OWNED + r'''
-- Range checks (the 0.30.4 beam pulse field ranges), nothing written.
local bad={{'liberator',{fire_rate=0}},{'liberator',{fire_rate=6001}},{'talon',{fire_rate=150.5}},
 {'talon',{pulse_beams=9}},{'reprimand',{pulse_seconds=10.5}},{'reprimand',{pulse_seconds=-1}},
 {'reprimand',{rate=600}},{'nope',{fire_rate=600}}}
for _,c in ipairs(bad)do check(not X.configure(c[1],c[2]).ok,'accepted '..c[1]..' '..json.encode(c[2]))end
check(counts.writes==0,'a refused setting wrote')
-- Before the apply: kept (pending).
local p=X.configure('liberator',{fire_rate=600})
check(p.ok and p.pending and counts.writes==0,'pending '..tostring(p.reason))
check(X.configure('talon',{fire_rate=150}).ok,'talon')
check(X.apply().ok,'apply')
local rows=copy()
local function member(id,offset,kind)return b.value(record_of(rows,OWN[id]),offset,kind)end
local applied={liberator=member('liberator',104,'i32'),talon=member('talon',104,'i32'),
 reprimand=member('reprimand',104,'i32')}
-- Live: one transaction on the copy only (the Reprimand 900 rpm, 3 beams per pulse, 0.3 s).
local writes=counts.writes
local file_before=runtime.read(TABLE,0x2E0+24*0x78)
local r=X.configure('reprimand',{fire_rate=900,pulse_beams=3,pulse_seconds=0.3})
check(r.ok and r.writes==3 and counts.owned_writes==3 and counts.writes==writes+3,'live settings '..tostring(r.reason))
rows=copy()
local live={fire_rate=member('reprimand',104,'i32'),pulse_beams=member('reprimand',108,'i32'),
 pulse_seconds=member('reprimand',112,'f32')}
check(runtime.read(TABLE,0x2E0+24*0x78)==file_before,'the file table changed')
-- Every other byte of every own record is the Trident's.
for id,k in pairs(OWN)do
 local rec=record_of(rows,k)
 check(rec:sub(1,104)==TRIDENT_RECORD:sub(1,104)and rec:sub(117)==TRIDENT_RECORD:sub(117),id..' record bytes')
end
-- Back to the Trident's (nil): one transaction.
check(X.configure('liberator',nil).ok,'reset liberator')
rows=copy()
local reset=member('liberator',104,'i32')
local st=X.status()
local shown={}
for _,w in ipairs(st.weapons)do shown[w.id]=w.settings end
check(X.restore().ok,'restore')
local _,left=changed()
check(left==0,'restore left bytes')
return json.encode({applied=applied,live=live,reset=reset,shown=shown})
''')
        self.assertEqual(result['applied'], {'liberator': 600, 'talon': 150, 'reprimand': 300})
        self.assertEqual(result['live']['fire_rate'], 900)
        self.assertEqual(result['live']['pulse_beams'], 3)
        self.assertAlmostEqual(result['live']['pulse_seconds'], 0.3, places=6)
        self.assertEqual(result['reset'], 300)
        self.assertEqual(result['shown']['talon']['fire_rate'], 150)
        self.assertEqual(result['shown']['reprimand']['pulse_beams'], 3)

    def test_guard_accepts_exactly_the_owned_pointer_and_typed_writes_land_in_the_copy(self):
        result = snapshot_run(LOCATE + OWNED + r'''
local trident=hd2.weapon('LAS-13 Trident')
local body={id='t',target=trident,allow_unverified_effect=true,field='beam.fire_rate',expect=300,value=600}
local where=resolve('patch',body)
check(#where==1 and where[1].at==TABLE+0x2E0+18*0x78+104,'in place: the file record 18 +104')
check(X.apply().ok,'apply')
local rows,at=copy()
-- While owned: the same typed field resolves into the copy.
where=resolve('patch',body)
local in_copy=where[1].at==at+0x2E0+18*0x78+104
-- A real write lands in the copy; the file keeps 300.
local h={}
events.run_as('mods/test/trident_rate',function()h.a=hd2.ensure({patch=body})end)
settle({h.a})
check(h.a.result and h.a.result.status=='APPLIED','typed write '..tostring(h.a.error))
rows=copy()
local copy_rate=b.value(record_of(rows,18),104,'i32')
local file_rate=b.value(runtime.read(TABLE+0x2E0+18*0x78+104,4),0,'i32')
-- hd2.inspect reads the copy: the written field is the mod's ('runtime'), another field 'vanilla', never 'foreign'.
local job=hd2.inspect({target=trident,fields={'beam.fire_rate','beam.pulse_beams'}})
settle({job})
local inspected={rate=job.result.by_field['beam.fire_rate'].state,pulse=job.result.by_field['beam.pulse_beams'].state}
local moved_lines=0
for _,l in ipairs(LINES)do if l:find('COMPONENT TABLE MOVED',1,true)then moved_lines=moved_lines+1 end end
-- The final restore refuses while record 18 differs in the copy (the game would lose the write).
local refused=X.restore()
-- Undo the write (as the mod's own restore would: the copy's +104 back to 300), then the restore goes ahead.
do
 local address=at-32
 local blk=BLOCKS[address]
 local off=at+0x2E0+18*0x78+104-address
 blk.bytes=blk.bytes:sub(1,off)..b.encode(300,'i32')..blk.bytes:sub(off+5)
end
local ok=X.restore()
-- A foreign pointer in the slot: refused by the guard and by the experiment (never chained onto).
overlay[SLOT]=b.encode((TABLE+8)%4294967296,'u32')..b.encode(math.floor((TABLE+8)/4294967296),'u32')
local foreign_ok,foreign_why=pcall(resolve,'patch',body)
local st=X.status()
local ap=X.apply()
overlay[SLOT]=nil
-- A registry entry whose original is not this capture's table: the moved pointer is still foreign.
check(X.apply({'talon'}).ok,'talon')
local e=OT.get('BeamWeaponComponentData')
OT.set('BeamWeaponComponentData',{owner=e.owner,index=e.index,table=e.table,allocation=e.allocation,size=e.size,
 original=e.original+16,records=e.records})
local mismatch_ok,mismatch_why=pcall(resolve,'patch',body)
OT.set('BeamWeaponComponentData',e)
check(X.restore().ok,'restore talon')
return json.encode({in_copy=in_copy,copy_rate=copy_rate,file_rate=file_rate,refused=refused.ok,
 refused_reason=refused.reason,restored=ok.ok,foreign_ok=foreign_ok,foreign_why=tostring(foreign_why),
 status_ok=st.ok,status_reason=st.reason,apply_reason=ap.reason,mismatch_ok=mismatch_ok,
 mismatch_why=tostring(mismatch_why),inspected=inspected,moved_lines=moved_lines})
''')
        self.assertEqual(result['inspected'], {'rate': 'runtime', 'pulse': 'vanilla'})
        self.assertEqual(result['moved_lines'], 0)
        self.assertTrue(result['in_copy'])
        self.assertEqual((result['copy_rate'], result['file_rate']), (600, 300))
        self.assertFalse(result['refused'])
        self.assertIn('record 18', result['refused_reason'])
        self.assertTrue(result['restored'])
        self.assertFalse(result['foreign_ok'])
        self.assertIn('another mod moved it', result['foreign_why'])
        self.assertFalse(result['status_ok'])
        self.assertIn('never chains onto a foreign copy', result['status_reason'])
        self.assertIn('never chains onto a foreign copy', result['apply_reason'])
        self.assertFalse(result['mismatch_ok'])
        self.assertIn('another mod moved it', result['mismatch_why'])

    def test_subsets_add_and_remove_rows_in_the_live_copy(self):
        result = snapshot_run(LOCATE + OWNED + r'''
local order,stop=writes_log()
check(X.apply({'talon'}).ok,'talon')
local rows,at=copy()
local talon_only=rows:sub(11*16+1,11*16+16)~=string.rep('\0',16)and rows:sub(21*16+1,21*16+16)==string.rep('\0',16)
local function seq(from)
 local out={}
 for i=from,#order do
  local o=order[i]
  local t=(o.at>=SLOT and o.at<SLOT+8)and'slot'or(o.at>=at and o.at<at+4096)and'copy'or o.t or'outside'
  if out[#out]~=t then out[#out+1]=t end
 end
 return out
end
local n=#order
check(X.configure('liberator',{fire_rate=600}).ok,'liberator setting')
check(X.apply({'liberator','reprimand'}).ok,'liberator + reprimand')
local second=seq(n+1)
check(blocks()==1,'a second copy was built')
n=#order
check(X.restore({'talon'}).ok,'restore talon')
local third=seq(n+1)
rows=copy()
check(rows and rows:sub(11*16+1,11*16+16)==string.rep('\0',16),'the talon row left the copy')
check(vanilla_of('talon')and edits.get(W.talon.res)==nil,'talon vanilla')
n=#order
check(X.restore().ok,'restore')
local fourth=seq(n+1)
stop()
local _,left=changed()
check(left==0,'left '..left)
-- A new apply after the full restore builds a new copy (the old one is never freed).
check(X.apply({'reprimand'}).ok and blocks()==2 and slot()~=at,'second copy')
check(X.restore().ok,'restore 2')
return json.encode({talon_only=talon_only,second=second,third=third,fourth=fourth})
''')
        self.assertTrue(result['talon_only'])
        # Liberator: its 600 rpm record member is written before its row, then its row (record, key), list, magazine.
        self.assertEqual(result['second'], ['copy', 'liberator.list', 'liberator.magazine', 'copy', 'reprimand.list',
                                            'reprimand.magazine'])
        self.assertEqual(result['third'], ['talon.list', 'copy'])
        self.assertEqual(result['fourth'], ['reprimand.magazine', 'reprimand.list', 'liberator.magazine',
                                            'liberator.list', 'slot'])

    def test_reload_detection_and_an_orphaned_list(self):
        result = snapshot_run(LOCATE + OWNED + r'''
check(X.apply().ok,'apply')
-- A loader reload: the slot back to the file's table and every list as the file has it.
local saved={}
for address,value in pairs(overlay)do saved[address]=value end
for address in pairs(saved)do overlay[address]=nil end
local st=X.status()
local reload_state={}
for _,w in ipairs(st.weapons)do reload_state[w.id]=w.state end
local registry_cleared=OT.get('BeamWeaponComponentData')==nil
local reload_logged=false
for _,line in ipairs(LINES)do if line:find('RELOAD DETECTED',1,true)then reload_logged=true end end
-- Another program put the slot back while the lists stay swapped: orphaned; the restore puts the lists back.
X.reset_for_tests()
check(X.apply().ok,'apply 2')
overlay[SLOT]=nil
local st2=X.status()
local orphan={}
for _,w in ipairs(st2.weapons)do orphan[w.id]=w.state end
local refused_apply=X.apply()
local r=X.restore()
local _,left=changed()
return json.encode({reload_state=reload_state,registry_cleared=registry_cleared,reload_logged=reload_logged,
 path=st.path,orphan=orphan,refused_apply=refused_apply.reason,restored=r.ok,left=left})
''')
        self.assertEqual(result['reload_state'], {'liberator': 'vanilla', 'talon': 'vanilla', 'reprimand': 'vanilla'})
        self.assertTrue(result['registry_cleared'] and result['reload_logged'])
        self.assertEqual(result['path'], 'none')
        self.assertEqual(result['orphan'], {'liberator': 'orphaned', 'talon': 'orphaned', 'reprimand': 'orphaned'})
        self.assertIn('restore it first', result['refused_apply'])
        self.assertTrue(result['restored'])
        self.assertEqual(result['left'], 0)

    def test_refusals_live_instances_and_the_shared_fallback(self):
        result = snapshot_run(LOCATE + OWNED + r'''
local slotd=free_descriptor()
local function live(id)return b.unhex(W[id].key)..b.encode(0x00400123,'u32')end
-- A live Talon: the owned apply of all three refuses before any copy is built; nothing written.
overlay[slotd]=live('talon')
local r=X.apply()
local refused_live=not r.ok and r.reason:find('1 live LAS-58 Talon',1,true)~=nil
local built_before=counts.permanent_blocks
local writes_before=counts.writes
overlay[slotd]=nil
-- Applied; a live Liberator refuses the final restore (the slot stays the copy).
check(X.apply().ok,'apply')
overlay[slotd]=live('liberator')
local rr=X.restore()
local restore_refused=not rr.ok and slot()~=TABLE
overlay[slotd]=nil
check(X.restore().ok,'restore')
-- No permanent blocks (an older adapter): the shared record path runs, as before.
local pb=runtime.permanent_block
runtime.permanent_block=nil
local forced=X.apply(nil,{path='owned'})
local shared=X.apply()
local st=X.status()
local rec23=hexat(RECORD,120)==D.beam.recordAfter
-- Settings refuse on the shared path (one record for every weapon), and the owned path waits for a full restore.
local cfg=X.configure('talon',{fire_rate=150})
runtime.permanent_block=pb
local mixed=X.apply({'talon'},{path='owned'})
check(X.restore().ok,'restore shared')
local _,left=changed()
return json.encode({refused_live=refused_live,built_before=built_before,writes_before=writes_before,
 restore_refused=restore_refused,forced=forced.reason,shared_path=shared.path,status_path=st.path,rec23=rec23,
 cfg=cfg.reason,mixed=mixed.ok,left=left})
''')
        self.assertTrue(result['refused_live'])
        self.assertEqual((result['built_before'], result['writes_before']), (0, 0))
        self.assertTrue(result['restore_refused'])
        self.assertIn('owned table is unavailable', result['forced'])
        self.assertEqual((result['shared_path'], result['status_path']), ('shared', 'shared record'))
        self.assertTrue(result['rec23'])
        self.assertIn('shared record path', result['cfg'])
        self.assertTrue(result['mixed'])     # the Talon joins the active shared path (already applied: no write)
        self.assertEqual(result['left'], 0)

    def test_the_liberator_proof_waits_for_the_owned_copy(self):
        result = snapshot_run(LOCATE + OWNED + r'''
local LB=require('hd2runtime/runtime/experiment_liberator_beam')
LB.reset_for_tests()
check(X.apply({'talon'}).ok,'owned talon')
local s=LB.status()
check(X.restore().ok,'restore')
local s2=LB.status()
return json.encode({during=s.ok,why=s.reason,after=s2.ok})
''')
        self.assertFalse(result['during'])
        self.assertIn('owned BeamWeapon copy', result['why'])
        self.assertTrue(result['after'])


if __name__ == '__main__':
    unittest.main()
