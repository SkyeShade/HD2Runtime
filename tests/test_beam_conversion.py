"""Beam conversions (runtime/beam_conversion.lua, domains/beam_conversion_writes.lua, domains/beam_conversion.lua;
docs/beam-conversion.md; research/docs/beam-conversion-coverage-F5FEE03DCFDB.md): a projectile weapon fires LAS-13
Trident pulses, solo only, through hd2.weapon(name):beam_conversion() and a guarded transaction.

The snapshot tests run on the copy-on-write overlay of the retained current-build snapshot (no game process), with a
per-page stand-in for the adapter's permanent blocks; every address is re-derived here from the research's formulas.
"""
import json
import struct
import sys
import unittest

from support import ROOT, run  # noqa: F401
from test_multi_mod_composition import build_profile, snapshot_run

sys.path.insert(0, str(ROOT / 'scripts'))
import generate_beam_conversion  # noqa: E402

COVERAGE = json.loads((ROOT / 'research/beam-conversion-coverage-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

PRELUDE = r'''
update=update or function()end
local E=require('hd2runtime/runtime/beam_conversion')
local C=require('hd2runtime/domains/beam_conversion')
local edits=require('hd2runtime/core/reviewed_edits')
local OT=require('hd2runtime/core/owned_tables')
E.reset_for_tests()
require('hd2runtime/runtime/beam_conversion_watch').reset_for_tests()
local assets=require('hd2runtime/core/assets')
assets.gate=function()return {state='ready',dependencies={},tick=function()return 'ready'end}end
local LIVE,LOBBY={}, {solo=true}
E.set_hooks_for_tests({census=function()
  local by={};for k,v in pairs(LIVE)do by[k]=v end
  return {live=0,tridents=0,by=by}end,
 solo=function()return LOBBY.solo,LOBBY.solo and'test: alone'or'test: 2 lobby members'end,
 assets=function()return'resident','test'end})
-- Permanent blocks (runtime/windows_write.lua): committed private pages, read-only after the fill, never freed, each
-- page with its own protection (VirtualProtect is per page).
local BLOCKS,next_block={},0x7FFE00000000
counts.permanent_blocks=0
local base_query,base_read,base_write,base_protect=runtime.query,runtime.read,runtime.write,runtime.protect
local function block_of(at)
 for address,blk in pairs(BLOCKS)do if at>=address and at<address+blk.size then return address,blk end end
end
function runtime.permanent_block(bytes)
 assert(type(bytes)=='string'and#bytes>0 and#bytes<=65536,'permanent block size')
 local address=next_block;next_block=next_block+0x100000
 local size=#bytes+(4096-#bytes%4096)%4096
 local blk={bytes=bytes..string.rep('\0',size-#bytes),size=size,protect={}}
 for p=0,size/4096-1 do blk.protect[p]=2 end
 BLOCKS[address]=blk;counts.permanent_blocks=counts.permanent_blocks+1
 return address
end
function runtime.query(at)
 local address,blk=block_of(at)
 if address then
  local p=math.floor((at-address)/4096);local value=blk.protect[p]
  local first,last=p,p
  while first>0 and blk.protect[first-1]==value do first=first-1 end
  while blk.protect[last+1]==value do last=last+1 end
  return {base=address+first*4096,size=(last-first+1)*4096,state=0x1000,type=0x20000,allocation_base=address,
   protect=value,allocation_protect=4}
 end
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
  assert(blk.protect[math.floor((at-address)/4096)]==4,'owned write without a writable page')
  counts.writes=counts.writes+1
  blk.bytes=blk.bytes:sub(1,at-address)..bytes..blk.bytes:sub(at-address+#bytes+1)
  return true,nil,#bytes
 end
 return base_write(at,bytes,packed)
end
function runtime.protect(page,size,value)
 local address,blk=block_of(page)
 if address then
  counts.protection_changes=counts.protection_changes+1
  local p=math.floor((page-address)/4096);local old=blk.protect[p];blk.protect[p]=value;return old
 end
 return base_protect(page,size,value)
end
local function ptr(at)return b.pointer(runtime.read(at,8),0)end
local game=runtime.address(runtime.module('game.dll'))
local manager=ptr(game+C.manager.global)
local SLOT=manager+C.manager.slotBase+8*270
local TABLE=ptr(SLOT)
local ESH=ptr(manager+C.manager.eshSlot)
local MAGTABLE=ptr(manager+C.manager.slotBase+8*5)
local FILE_ROWS=runtime.read(TABLE,46*16)
local TWO32=4294967296
-- The game's BeamWeapon lookup 0x50E880 over rows: resource '0x...' -> record index or false.
local function lookup(rows,resource)
 local hi,lo=tonumber(resource:sub(3,10),16),tonumber(resource:sub(11,18),16)
 local at=((hi%46)*(TWO32%46)+lo%46)%46
 for _=1,46 do
  local klo,khi=b.u32(rows,at*16),b.u32(rows,at*16+4)
  if klo==lo and khi==hi then return b.u32(rows,at*16+8)end
  if klo==0 and khi==0 then return false end
  at=(at+1)%46
 end
 return false
end
local function rows_now()return runtime.read(ptr(SLOT),46*16)end
local function weapon(name)for _,w in ipairs(C.weapons)do if w.name==name then return w end end end
-- Every byte the overlay holds that differs from the snapshot.
local function changed()
 local count=0
 for address,value in pairs(overlay)do
  local original=source.read(address,#value)
  for i=1,#value do if value:byte(i)~=original:byte(i)then count=count+1 end end
 end
 return count
end
-- The list the root's entity map row names now (its pointer and count) and the file's own list.
local function row_of(root)return ESH+32*root.membership.row end
local function list_of(root)
 local r=row_of(root)
 return b.hex(runtime.read(ptr(r+8),b.u32(runtime.read(r+16,4),0)*2))
end
local function file_list_of(root)
 return b.hex(runtime.read(ESH+root.membership.listOffsetInBody,root.membership.count*2))
end
local PTABLE=ptr(manager+C.manager.slotBase+8*321)
local function pw_of(root)
 return runtime.read(PTABLE+C.projectile.recordBase+root.projectile.record*C.projectile.recordStride,12)
end
local function added(root)return ptr(row_of(root)+8)~=ESH+root.membership.listOffsetInBody end
-- Settles a handle to an end state (a transaction resolves over several updates).
local function done(h,limit)
 local n=0
 while(h.status=='waiting'or h.status=='queued'or h.status=='resolving'or h.status=='running'
  or h.status=='waiting_for_assets')and n<(limit or 600)do frames(1);n=n+1 end
 return h
end
local function tx(id,name,changes,opts)
 opts=opts or{}
 local request={id=id,target=hd2.beam_conversion(name),changes=changes,
  allow_component_swap=opts.ack~=false and true or nil,allow_unverified_effect=opts.ack~=false and true or nil}
 local ok,h=pcall(hd2.transaction,request)
 if not ok then return {status='invalid',error=tostring(h)}end
 done(h,opts.limit)
 return h
end
-- A gate that is not clear: the transaction waits (a bounded retry) with the reason, or is rejected with it.
local function waiting(h,needle)
 local text=tostring(h.last_transient or'')..' '..tostring(h.error or'')
 local ok=(h.status=='retry_wait'or h.status=='rejected')and text:find(needle,1,true)~=nil
 if h.cancel then h.cancel()end
 return ok
end
local function writable(at,bytes)
 local page=at-at%4096
 local old=runtime.protect(page,4096,4);runtime.write(at,bytes);runtime.protect(page,4096,old)
end
local function invalid(h,needle)
 return(h.status=='invalid'or h.status=='rejected')and tostring(h.error):find(needle,1,true)~=nil
end
local function enable(id,name,extra)
 local changes={{field=F.beam_conversion.enabled,expect=false,value=true}}
 for _,c in ipairs(extra or{})do changes[#changes+1]=c end
 return tx(id,name,changes)
end
local function disable(id,name)return tx(id,name,{{field=F.beam_conversion.enabled,expect=false,value=false}})end
local function converted_ok(w)
 local rows=rows_now()
 for _,root in ipairs(w.roots)do
  if added(root)then
   -- The add layout: the row names the grown list; the file list, the neighbours, stay as shipped.
   if list_of(root)~=root.add.listHex then return false,'grown list of '..root.resource end
   if file_list_of(root)~=root.membership.before then return false,'file list of '..root.resource end
   if b.hex(pw_of(root):sub(1,4))~='00000000'then return false,'projectile type of '..root.resource end
  elseif list_of(root)~=root.membership.after then return false,'list of '..root.resource end
  if lookup(rows,root.resource)~=(ptr(SLOT)==TABLE and 23 or w.record)then return false,'row of '..root.resource end
  if root.magazine and b.hex(runtime.read(MAGTABLE+root.magazine.windowOffset,4))~='00000000'then
   return false,'magazine of '..root.resource end
 end
 return true
end
local function vanilla_ok(w)
 local rows=rows_now()
 for _,root in ipairs(w.roots)do
  if added(root)or list_of(root)~=root.membership.before then return false,'list of '..root.resource end
  if root.add and(b.hex(pw_of(root):sub(1,4))~=root.add.typeBefore or b.hex(pw_of(root):sub(9,12))~=root.add.rateBefore)
  then return false,'projectile record of '..root.resource end
  if lookup(rows,root.resource)then return false,'row of '..root.resource end
  if root.magazine and b.hex(runtime.read(MAGTABLE+root.magazine.windowOffset,4))~='01000000'then
   return false,'magazine of '..root.resource end
 end
 return true
end
'''


class DomainTests(unittest.TestCase):
    def test_the_domain_is_generated_from_the_research(self):
        self.assertEqual(generate_beam_conversion.generate(check=True), [])
        domain = generate_beam_conversion.build()
        by = {w['name']: w for w in domain['weapons']}
        self.assertEqual(len(domain['weapons']), 115)
        # The projectile LAS weapons: the swap verdict, and the add layout where it takes them.
        for name, layout, verdict, code, swap_code in (
                ('LAS-16 Sickle', 'add', 'supported_with_caveats', 'ADD_LAYOUT', 'HEAT_PULSE'),
                ('LAS-17 Double-Edge Sickle', 'swap', 'supported_with_caveats', 'HEAT_PULSE', 'HEAT_PULSE'),
                ('LAS-12 Sai', 'add', 'supported_with_caveats', 'ADD_LAYOUT', 'HEAT_PULSE'),
                ('LAS-58 Talon', 'add', 'supported_with_caveats', 'ADD_LAYOUT', 'LIVE_PROVEN'),
                ('LAS-99 Quasar Cannon', 'swap', 'supported_with_caveats', 'HEAT_PULSE', 'HEAT_PULSE'),
                ('PLAS-101 Purifier', None, 'refused', 'CHARGE_WEAPON', 'CHARGE_WEAPON')):
            w = by[name]
            self.assertEqual((w['layout'], w['verdict'], w['reasonCode'], w['swap']['reasonCode']),
                             (layout, verdict, code, swap_code), name)
        self.assertEqual(by['LAS-17 Double-Edge Sickle']['add']['reasonCode'], 'HEAT_STAGE_PROJECTILES')
        self.assertEqual(by['LAS-99 Quasar Cannon']['add']['reasonCode'], 'NETWORKED_SHOTS')
        for name in ('AR-23 Liberator', 'LAS-58 Talon', 'SMG-32 Reprimand'):
            self.assertTrue(by[name]['liveProven'] and by[name]['supported'] and by[name]['liveProvenLayout'] == 'swap',
                            name)
        # Coverage re-classification (research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md section 6).
        layouts = {}
        for w in domain['weapons']:
            layouts[w['layout']] = layouts.get(w['layout'], 0) + 1
        self.assertEqual(layouts, {'add': 42, 'swap': 24, None: 49})
        add_refusals = {}
        for w in domain['weapons']:
            if w['layout'] == 'swap':
                add_refusals[w['add']['reasonCode']] = add_refusals.get(w['add']['reasonCode'], 0) + 1
        self.assertEqual(add_refusals, {'AMMUNITION_SETS_PROJECTILE': 8, 'NETWORKED_SHOTS': 9, 'FUNCTION_AMMO': 3,
                                        'ROUND_LIST_MAGAZINE': 2, 'HEAT_STAGE_PROJECTILES': 1, 'PROJECTILE_HOOK': 1})
        self.assertEqual(by['AR-23 Liberator']['add']['reasonCode'], 'AMMUNITION_SETS_PROJECTILE')
        for w in domain['weapons']:
            if w['layout'] == 'add':
                self.assertFalse(w['restartAfterUse'], w['name'])
                for code in ('RESTART_AFTER_USE', 'OPTION_LEAKS_PROJECTILE_COPY', 'WINDOW_CROSSES_PAGE'):
                    self.assertNotIn(code, [c['code'] for c in w['caveats']], w['name'])
            if w['layout'] is None:
                self.assertFalse(w['supported'], w['name'])
        # Every add root: its own list plus BeamWeapon, sorted and unique, ProjectileWeapon kept; the slots are packed
        # 4-aligned in one block after the magic.
        slots, end = [], domain['lists']['framing']
        for w in domain['weapons']:
            if w['layout'] != 'add':
                continue
            for r in w['roots']:
                a = r['add']
                before = bytes.fromhex(r['membership']['before'])
                after = bytes.fromhex(a['listHex'])
                eb = [int.from_bytes(before[i:i + 2], 'little') for i in range(0, len(before), 2)]
                ea = [int.from_bytes(after[i:i + 2], 'little') for i in range(0, len(after), 2)]
                self.assertEqual(ea, sorted(eb + [270]), w['name'])
                self.assertEqual(a['count'], r['membership']['count'] + 1)
                self.assertEqual(a['slot'] % 4, 0)
                self.assertNotEqual(a['typeBefore'], '00000000', w['name'])
                slots.append((a['slot'], a['slot'] + 2 * a['count']))
        slots.sort()
        for (a0, a1), (b0, _) in zip(slots, slots[1:]):
            self.assertLessEqual(a1, b0)
        self.assertGreaterEqual(slots[0][0], domain['lists']['framing'])
        self.assertLessEqual(slots[-1][1], domain['lists']['bytes'])
        self.assertLessEqual(domain['lists']['bytes'], 4096)
        self.assertEqual((domain['projectile']['recordBase'], domain['projectile']['recordStride']), (8672, 616))
        self.assertEqual(by['SG-8 Punisher']['reasonCode'], 'ROUNDS_NO_BEAM_RELOAD')
        self.assertEqual(by['M-1000 Maxigun']['reasonCode'], 'LINKED_AMMO_NO_BEAM_RELOAD')
        self.assertEqual(by['LAS-13 Trident']['reasonCode'], 'ALREADY_BEAM')
        self.assertEqual(len(by['M-105 Stalwart']['roots']), 4)
        # Every supported weapon has its own record (24..), each root its own resource.
        records = [w['record'] for w in domain['weapons'] if w['supported']]
        self.assertEqual(records, list(range(24, 24 + len(records))))
        self.assertEqual(domain['copy']['records'], 24 + len(records))
        settings = {s['id']: (s['offset'], s['storage'], s['min'], s['max']) for s in domain['settings']}
        self.assertEqual(settings, {'fire_rate': (104, 'i32', 1, 900), 'pulse_beams': (108, 'i32', 1, 8),
                                    'pulse_seconds': (112, 'f32', 0.0334, 2)})
        fields = {f['id']: f for f in domain['fields']}
        self.assertEqual(fields['beam.fire_rate']['default'], 300)
        self.assertEqual(fields['beam.pulse_beams']['default'], 2)
        self.assertAlmostEqual(fields['beam.pulse_seconds']['default'], 0.15, places=6)
        self.assertIn('limits the fire rate', fields['beam.pulse_seconds']['displayName'])
        self.assertEqual(domain['acknowledgements'], ['allow_component_swap', 'allow_unverified_effect'])

    def test_a_shared_chamber_magazine_or_projectile_record_is_refused_by_the_generator(self):
        w = next(x for x in COVERAGE['weapons'] if x['name'] == 'AR-23 Liberator')
        root = json.loads(json.dumps(w['rootsToSwap'][0]))
        root['magazine']['owners'].append('0x0000000000000001')
        with self.assertRaisesRegex(ValueError, 'chamber magazine record is shared'):
            generate_beam_conversion._root(w, root)
        root = json.loads(json.dumps(w['rootsToSwap'][0]))
        root['projectileRowKept']['owners'].append('0x0000000000000001')
        with self.assertRaisesRegex(ValueError, 'ProjectileWeapon record is shared'):
            generate_beam_conversion._root(w, root)

    def test_capabilities_list_every_weapon_with_its_target(self):
        caps = json.loads((ROOT / 'sdk/BeamConversionCapabilities.json').read_text(encoding='utf-8'))
        self.assertEqual(caps['summary']['weapons'], 115)
        sickle = next(w for w in caps['weapons'] if w['name'] == 'LAS-16 Sickle')
        self.assertEqual(sickle['target'], 'hd2.weapon("LAS-16 Sickle"):beam_conversion()')
        quasar = next(w for w in caps['weapons'] if w['name'] == 'LAS-99 Quasar Cannon')
        self.assertTrue(quasar['target'].startswith('hd2.support_weapon('))

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
    def test_every_pin_is_the_game_image_bytes(self):
        from scan import xref
        _, data, sha = xref.load_image('game.dll')
        domain = generate_beam_conversion.build()
        self.assertEqual(sha, domain['source']['gameDllSha256'])
        self.assertGreaterEqual(len(domain['pins']), 200)
        for pin in domain['pins']:
            expected = bytes.fromhex(pin['hex'])
            self.assertEqual(data[pin['rva']:pin['rva'] + len(expected)], expected, hex(pin['rva']))


class RowAlgorithmTests(unittest.TestCase):
    def test_insert_and_linear_probing_deletion_keep_every_lookup(self):
        result = json.loads(run(r'''
local json=require('hd2runtime/primary_mapper/json')
local E=require('hd2runtime/runtime/beam_conversion')
local C=require('hd2runtime/domains/beam_conversion')
local b=require('hd2runtime/core/bytes')
local rows=b.unhex(C.beam.vanillaRowsHex)
local function key(resource)return b.unhex(resource:sub(3)):reverse()end
local function look(r,resource)
 local at=E.home(resource,46)
 for _=1,46 do
  local k=r:sub(at*16+1,at*16+8)
  if k==key(resource)then return at end
  if k==string.rep('\0',8)then return nil end
  at=(at+1)%46
 end
end
local vanilla={}
for row=0,45 do local k=rows:sub(row*16+1,row*16+8)if k~=string.rep('\0',8)then
 vanilla[#vanilla+1]=b.resource(rows,row*16)end end
-- Insert the roots of every supported weapon in catalogue order until one row is left.
local placed,order={},{}
for _,w in ipairs(C.weapons)do if w.supported then for _,root in ipairs(w.roots)do
 local free=0;for row=0,45 do if rows:sub(row*16+1,row*16+8)==string.rep('\0',8)then free=free+1 end end
 if free>1 then
  local at=E.insert_row(rows,root.resource)
  rows=rows:sub(1,at*16)..key(root.resource)..b.encode(w.record,'u32')..b.encode(0,'u32')..rows:sub(at*16+17)
  placed[root.resource]=true;order[#order+1]=root.resource
 end
end end end
local ok,why=true,nil
local function all_found(r)
 for _,v in ipairs(vanilla)do if not look(r,v)then return false,'vanilla '..v end end
 for res in pairs(placed)do if not look(r,res)then return false,'placed '..res end end
 return true
end
assert(all_found(rows))
local moves=0
-- Delete them in an interleaved order; every remaining key stays findable after each delete.
for i=1,#order,2 do
 local res=order[i]
 local at=look(rows,res)
 local plan=E.delete_plan(rows,at,function(r)return placed[r]~=nil end)
 moves=moves+#plan.moves
 rows=E.apply_delete(rows,plan);placed[res]=nil
 local good,w=all_found(rows)
 if not good then ok,why=false,w;break end
end
for i=2,#order,2 do
 local res=order[i]
 local plan=E.delete_plan(rows,look(rows,res),function(r)return placed[r]~=nil end)
 moves=moves+#plan.moves
 rows=E.apply_delete(rows,plan);placed[res]=nil
 local good,w=all_found(rows)
 if not good then ok,why=false,w;break end
end
return json.encode({ok=ok,why=why,placed=#order,moves=moves,back=b.hex(rows)==C.beam.vanillaRowsHex})
'''))
        self.assertTrue(result['ok'], result.get('why'))
        self.assertEqual(result['placed'], 22)
        self.assertGreater(result['moves'], 0)
        self.assertTrue(result['back'])

    def test_pulse_fit(self):
        result = json.loads(run(r'''
local json=require('hd2runtime/primary_mapper/json')
local E=require('hd2runtime/runtime/beam_conversion')
local out={}
for _,rate in ipairs({150,300,450,600,750,900})do
 local p,fitted=E.fitted_pulse(rate,nil)
 out[#out+1]={rate=rate,pulse=p,fitted=fitted,at60=E.effective_rate(rate,p,60),at144=E.effective_rate(rate,p,144),
  gate60=E.effective_rate(rate,0.0001,60),gate144=E.effective_rate(rate,0.0001,144),gate30=E.effective_rate(rate,0.0001,30),
  at30=E.effective_rate(rate,p,30)}
end
return json.encode(out)'''))
        for item in result:
            self.assertGreaterEqual(item['pulse'], 0.0334 - 1e-9)
            if item['rate'] <= 300:
                self.assertFalse(item['fitted'])
                self.assertAlmostEqual(item['pulse'], 0.15, places=6)
            # The pulse never decides the interval: the rate is the shot gate's (whole updates) from 30 fps up.
            self.assertEqual(item['at60'], item['gate60'], str(item))
            self.assertEqual(item['at144'], item['gate144'], str(item))
            if item['rate'] <= 600:  # 20 x fps: a pulse that hits allows at most 600 rpm at 30 fps
                self.assertEqual(item['at30'], item['gate30'], str(item))


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class ConversionSnapshotTests(unittest.TestCase):
    def test_sickle_converts_with_its_own_rate_and_restores_byte_exact(self):
        result = snapshot_run(PRELUDE + r'''
local sickle=weapon('LAS-16 Sickle')
check(sickle.layout=='add','the Sickle takes the add layout')
local root=sickle.roots[1]
local resources={}
for row=0,45 do local k=b.resource(FILE_ROWS,row*16)if k~='0x0000000000000000'then resources[#resources+1]=k end end
-- Every entity map row and list before (the neighbours of the converted row must stay byte-identical).
local MAP_ROWS=runtime.read(ESH,4096*32)
local h=enable('sickle','LAS-16 Sickle',{{field=F.beam.fire_rate,expect=300,value=600}})
check(h.status=='complete'and h.result.status=='APPLIED','apply '..tostring(h.error))
check(ptr(SLOT)~=TABLE,'the slot names the copy')
local ok,why=converted_ok(sickle);check(ok,why)
-- The add layout's writes in the entity allocation: only the row's pointer and count and the record's +0 / +8.
local R0=row_of(root)
local PW=PTABLE+C.projectile.recordBase+root.projectile.record*C.projectile.recordStride
local allowed={}
for i=8,19 do allowed[R0+i]=true end
for i=0,3 do allowed[PW+i]=true;allowed[PW+8+i]=true end
for i=0,7 do allowed[SLOT+i]=true end
for address,value in pairs(overlay)do
 local original=source.read(address,#value)
 for i=1,#value do
  if value:byte(i)~=original:byte(i)then check(allowed[address+i-1],('a byte outside the write set changed: %X')
   :format(address+i-1))end
 end
end
local rows_after=runtime.read(ESH,4096*32)
for row=0,4095 do
 if row~=root.membership.row then
  check(rows_after:sub(row*32+1,row*32+32)==MAP_ROWS:sub(row*32+1,row*32+32),'entity map row '..row..' changed')
 end
end
check(b.u32(runtime.read(R0+16,4),0)==root.add.count,'count N+1')
-- The heat bound: the Sickle's projectile rate is below its slowest pulse cadence.
local rate=b.value(pw_of(root),8,'f32')
local pulse=b.value(runtime.read(ptr(SLOT)+0x2E0+sickle.record*0x78+112,4),0,'f32')
check(rate==E.heat_projectile_rate(600,pulse),'heat bound '..rate)
for fps=30,240 do check(rate<=E.effective_rate(600,pulse,fps),'bound at '..fps)end
check(rate<=0.9*E.effective_rate(600,pulse,30)+1,'a 10 % margin')
check(OT.get_list(root.resource)and OT.get_list(root.resource).count==root.add.count,'owned list registered')
check(not E.restart_required(),'the add layout needs no restart')
local rows=rows_now()
for _,r in ipairs(resources)do check(lookup(rows,r)==lookup(FILE_ROWS,r),'lookup of '..r..' changed')end
-- Its own record: the Trident's but for +104 = 600 and the fitted +112.
local copy=ptr(SLOT)
local rec=runtime.read(copy+0x2E0+sickle.record*0x78,0x78)
local donor=b.unhex(C.trident.recordHex)
check(b.value(rec,104,'i32')==600 and math.abs(b.value(rec,112,'f32')-0.0666667)<1e-5,'settings')
check(rec:sub(1,104)==donor:sub(1,104)and rec:sub(117)==donor:sub(117),'record outside the settings')
check(OT.get('BeamWeaponComponentData').owner==E.OWNER,'owned registry')
check(edits.get(sickle.roots[1].resource).owner==E.OWNER,'reviewed edit recorded')
local st=hd2.beam_conversion('LAS-16 Sickle'):status()
check(st.state=='converted'and st.settings.fire_rate==600,'status')
-- A settings-only change: its record and, on this heat weapon, its projectile rate (the new bound), no gate.
LIVE[sickle.roots[1].resource]=1
local h2=tx('sickle-pulse','LAS-16 Sickle',{{field=F.beam.pulse_seconds,expect=0.15,value=0.05}})
check(h2.status=='complete','settings with a live weapon: '..tostring(h2.error))
rec=runtime.read(copy+0x2E0+sickle.record*0x78,0x78)
check(math.abs(b.value(rec,112,'f32')-0.05)<1e-6 and b.value(rec,104,'i32')==600,'pulse written, rate kept')
check(b.value(pw_of(root),8,'f32')==E.heat_projectile_rate(600,b.value(rec,112,'f32')),'the heat bound follows')
-- The restore waits for zero live Sickles.
local h3=disable('sickle-off','LAS-16 Sickle')
check(waiting(h3,'BUSY'),'live sickle: '..tostring(h3.status))
LIVE[sickle.roots[1].resource]=nil
h3=disable('sickle-off2','LAS-16 Sickle')
check(h3.status=='complete','restore '..tostring(h3.error))
check(ptr(SLOT)==TABLE,'slot back to the file table')
ok,why=vanilla_ok(sickle);check(ok,why)
check(changed()==0,'every snapshot byte vanilla again: '..changed())
check(OT.get('BeamWeaponComponentData')==nil,'registry cleared')
check(edits.get(sickle.roots[1].resource)==nil,'edit cleared')
check(OT.get_list(root.resource)==nil,'owned list cleared')
check(not E.restart_required(),'no restart notice')
-- The swap layout (the Liberator) still asks for the restart.
check(enable('lib','AR-23 Liberator').status=='complete','liberator')
check(disable('liboff','AR-23 Liberator').status=='complete','liberator off')
check(E.restart_required()and changed()==0,'swap: restart notice')
return json.encode({ok=true})''')
        self.assertTrue(result['ok'])

    def test_every_supported_weapon_converts_and_restores(self):
        result = snapshot_run(PRELUDE + r'''
local out={}
for _,w in ipairs(C.weapons)do if w.supported then
 local h=enable('on-'..w.id,w.name)
 local ok,why=h.status=='complete',h.error
 if ok then ok,why=converted_ok(w)end
 local h2=disable('off-'..w.id,w.name)
 local ok2,why2=h2.status=='complete',h2.error
 if ok2 then ok2,why2=vanilla_ok(w)end
 out[#out+1]={name=w.name,on=ok,why=why and tostring(why)or nil,off=ok2,why2=why2 and tostring(why2)or nil,
  back=changed()==0 and ptr(SLOT)==TABLE}
end end
return json.encode(out)''')
        self.assertEqual(len(result), 66)
        for item in result:
            self.assertTrue(item['on'], (item['name'], item.get('why')))
            self.assertTrue(item['off'], (item['name'], item.get('why2')))
            self.assertTrue(item['back'], item['name'])

    def test_many_at_once_then_restored_in_another_order(self):
        result = snapshot_run(PRELUDE + r'''
local names={}
for _,w in ipairs(C.weapons)do if w.supported and#names<12 then names[#names+1]=w.name end end
for i,name in ipairs(names)do
 local h=enable('on'..i,name,{{field=F.beam.fire_rate,expect=300,value=100+i*50}})
 check(h.status=='complete',name..': '..tostring(h.error))
end
for _,name in ipairs(names)do local ok,why=converted_ok(weapon(name));check(ok,name..': '..tostring(why))end
for i=#names,1,-2 do local h=disable('offa'..i,names[i]);check(h.status=='complete',names[i]..' '..tostring(h.error))end
for _,name in ipairs(names)do
 local ok=weapon(name)and(converted_ok(weapon(name))or vanilla_ok(weapon(name)))
 check(ok,'state of '..name)
end
for i=#names-1,1,-2 do local h=disable('offb'..i,names[i]);check(h.status=='complete',names[i]..' '..tostring(h.error))end
check(ptr(SLOT)==TABLE and changed()==0,'vanilla again')
return json.encode({ok=true,n=#names})''')
        self.assertTrue(result['ok'])

    def test_refusals(self):
        result = snapshot_run(PRELUDE + r'''
local out={}
-- A refused weapon (rounds-fed: it could never reload a beam).
local h=enable('punisher','SG-8 Punisher')
out.refused=invalid(h,'ROUNDS_NO_BEAM_RELOAD')
-- Missing acknowledgements.
h=tx('noack','LAS-16 Sickle',{{field=F.beam_conversion.enabled,expect=false,value=true}},{ack=false})
out.ack=invalid(h,'allow_component_swap')
-- Above 900 rpm.
h=enable('fast','LAS-16 Sickle',{{field=F.beam.fire_rate,expect=300,value=1200}})
out.range=invalid(h,'900')
-- A pulse below the one-frame floor.
h=enable('short','LAS-16 Sickle',{{field=F.beam.pulse_seconds,expect=0.15,value=0.01}})
out.floor=invalid(h,'0.0334')
-- Settings on a weapon that is not converted.
h=tx('rate-only','LAS-16 Sickle',{{field=F.beam.fire_rate,expect=300,value=600}})
out.not_converted=h.status=='rejected'and tostring(h.error):find('NOT_CONVERTED',1,true)~=nil
-- A live instance: waits (TARGET_UNAVAILABLE BUSY), writes nothing.
local lib=weapon('AR-23 Liberator')
LIVE[lib.roots[1].resource]=1
h=enable('busy','AR-23 Liberator')
out.busy=waiting(h,'BUSY')and changed()==0
LIVE[lib.roots[1].resource]=nil
-- Another player in the lobby.
LOBBY.solo=false
h=enable('mp','AR-23 Liberator')
out.not_solo=waiting(h,'NOT_SOLO')and changed()==0
LOBBY.solo=true
-- A plan cannot carry a conversion.
local okp,hp=pcall(hd2.plan,{id='p',operations={{id='x',target=hd2.beam_conversion('LAS-16 Sickle'),
 changes={{field=F.beam_conversion.enabled,expect=false,value=true}},allow_unverified_effect=true}}})
out.plan=not okp and tostring(hp):find('not a plan operation',1,true)~=nil
 or okp and type(hp)=='table'and tostring(hp.error):find('not a plan operation',1,true)~=nil
-- A foreign table: another mod moved the BeamWeapon slot.
local fake=runtime.permanent_block(runtime.read(TABLE-32,32+0x2E0+24*0x78))
writable(SLOT,b.encode((fake+32)%TWO32,'u32')..b.encode(math.floor((fake+32)/TWO32),'u32'))
h=enable('foreign','AR-23 Liberator')
out.foreign=h.status=='rejected'and tostring(h.error):find('CONFLICT',1,true)~=nil
writable(SLOT,b.encode(TABLE%TWO32,'u32')..b.encode(math.floor(TABLE/TWO32),'u32'))
-- A row another mod wrote into the file table.
local row=TABLE+16*1
writable(row,string.rep('\1',8))
h=enable('foreignrow','AR-23 Liberator')
out.foreign_row=h.status=='rejected'and tostring(h.error):find('CONFLICT',1,true)~=nil
writable(row,string.rep('\0',8))
out.clean=changed()==0
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))

    def test_converted_weapons_refuse_their_dormant_projectile_fields_and_the_shared_fallback(self):
        result = snapshot_run(PRELUDE + r'''
local out={}
local h=enable('lib','AR-23 Liberator')
check(h.status=='complete',tostring(h.error))
-- Its ProjectileWeapon is dormant: a typed fire-rate write is refused; its ergonomics still writable.
local w=hd2.ensure and nil
local r1=hd2.transaction({id='rate',target=hd2.weapon('AR-23 Liberator'),changes={
 {field=F.weapon.fire_rate,expect=640,value=700}}})
done(r1)
out.dormant=r1.status=='rejected'and tostring(r1.error):find('BEAM CONVERSION',1,true)~=nil
local r2=hd2.transaction({id='ergo',target=hd2.weapon('AR-23 Liberator'),changes={
 {field=F.weapon.ergonomics,expect=65,value=70}}})
done(r2)
out.other_fields=r2.status=='complete'
-- The Trident's own typed write lands in the copy while it is live; the last restore then keeps the copy (drift).
local r3=hd2.transaction({id='trident',target=hd2.weapon('LAS-13 Trident'),allow_unverified_effect=true,changes={
 {field=F.beam.fire_rate,expect=300,value=310}}})
done(r3)
out.trident=r3.status=='complete'and b.value(runtime.read(ptr(SLOT)+0x2E0+18*0x78+104,4),0,'i32')==310
 and b.value(runtime.read(TABLE+0x2E0+18*0x78+104,4),0,'i32')==300
h=disable('liboff','AR-23 Liberator')
out.drift_kept=h.status=='complete'and ptr(SLOT)~=TABLE and vanilla_ok(weapon('AR-23 Liberator'))
-- Undo the Trident write (as its mod's ensure restore would: the copy's record 18 back to 300) and the ergonomics.
writable(ptr(SLOT)+0x2E0+18*0x78+104,b.encode(300,'i32'))
local lib_data=require('hd2runtime/domains/player_weapon_authoring').weapons['AR-23 Liberator']
for _,f in ipairs(lib_data.fields)do if f.semanticFieldId=='weapon.ergonomics'then
 local bk=f.backing
 for address,value in pairs(overlay)do
  if source.read(address,#value)~=value and b.value(value,0,'f32')==70 then writable(address,b.encode(65,'f32'))end
 end
end end
h=enable('lib2','AR-23 Liberator');check(h.status=='complete','lib2 '..tostring(h.status)..' '..tostring(h.error)..' '..tostring(h.last_transient))
h=disable('lib2off','AR-23 Liberator')
out.slot_back=h.status=='complete'and ptr(SLOT)==TABLE
-- The shared fallback: no permanent blocks -> record 23 in the file table, Trident settings only.
local pb=runtime.permanent_block;runtime.permanent_block=nil
h=enable('shared','SMG-32 Reprimand',{{field=F.beam.fire_rate,expect=300,value=600}})
out.shared_refuses_settings=h.status=='rejected'and tostring(h.error):find('SHARED_RECORD_FALLBACK',1,true)~=nil
h=enable('shared2','SMG-32 Reprimand')
out.shared=h.status=='complete'and ptr(SLOT)==TABLE and converted_ok(weapon('SMG-32 Reprimand'))
 and b.hex(runtime.read(TABLE+0xDA8,0x78))==C.trident.recordHex
h=disable('shared2off','SMG-32 Reprimand')
out.shared_back=h.status=='complete'and vanilla_ok(weapon('SMG-32 Reprimand'))
 and b.hex(runtime.read(TABLE+0xDA8,0x78))==C.beam.vanillaRecord23Hex
runtime.permanent_block=pb
out.clean=changed()==0
if not out.clean then
 for address,value in pairs(overlay)do local o=source.read(address,#value)if o~=value then out[('changed %X'):format(address)]=b.hex(o)..'>'..b.hex(value)end end
end
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))

    def test_the_experiment_copy_is_never_mixed(self):
        result = snapshot_run(PRELUDE + r'''
local X=require('hd2runtime/runtime/experiment_beam_swap')
X.reset_for_tests()
X.set_hooks_for_tests({census=function()return {live=0,tridents=0,liberator=0,talon=0,reprimand=0}end,
 solo=function()return true,'test'end,assets=function()return'resident','test'end})
local r=X.apply({'talon'})
check(r.ok,'experiment apply '..tostring(r.reason))
local h=enable('mix','LAS-16 Sickle')
local out={refused=h.status=='rejected'and tostring(h.error):find('experiment',1,true)~=nil}
X.restore({'talon'})
h=enable('after','LAS-16 Sickle')
out.after=h.status=='complete'
h=disable('afteroff','LAS-16 Sickle')
out.off=h.status=='complete'
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))

    def test_per_weapon_damage_ap_and_range_through_borrowed_rows(self):
        result = snapshot_run(PRELUDE + r'''
local RWS=C.rows
local beam_slots,damage_slots=game+RWS.beamTable.rva,game+RWS.damageTable.rva
local VAN={}
for i,p in ipairs(RWS.pairs)do VAN[i]={ptr(beam_slots+8*p.beamType),ptr(damage_slots+8*p.damageInfo)}end
local out={}
-- The Liberator: 10x damage (600 / 60) and AP 4; the Reprimand: range 100 m.
local h=enable('lib','AR-23 Liberator',{{field=F.damage.player_standard_damage,expect=60,value=600},
 {field=F.damage.player_durable_damage,expect=6,value=60},{field=F.damage.ap_direct,expect=2,value=4}})
out.lib=h.status=='complete'
local lib=weapon('AR-23 Liberator')
local rec=runtime.read(ptr(SLOT)+0x2E0+lib.record*0x78,0x78)
local k=b.u32(rec,0)
out.own_beamtype=k==RWS.pairs[1].beamType
local row=ptr(beam_slots+8*k)
local d=b.u32(runtime.read(row,0x70),12)
out.own_damage_id=d==RWS.pairs[1].damageInfo
local drow=runtime.read(ptr(damage_slots+8*d),0x4C)
out.damage_values=b.u32(drow,0)==d and b.value(drow,4,'i32')==600 and b.value(drow,8,'i32')==60
 and b.u32(drow,12)==4 and b.u32(drow,16)==2
out.vanilla_rows_untouched=b.hex(runtime.read(VAN[1][1],0x70))==RWS.pairs[1].beamHex
 and b.hex(runtime.read(VAN[1][2],0x4C))==RWS.pairs[1].damageHex
out.trident_untouched=b.hex(runtime.read(ptr(beam_slots+8*6),0x70))==RWS.tridentBeamHex
h=enable('rep','SMG-32 Reprimand',{{field=F.beam.length,expect=200,value=100}})
out.rep=h.status=='complete'
local rep=weapon('SMG-32 Reprimand')
local rk=b.u32(runtime.read(ptr(SLOT)+0x2E0+rep.record*0x78,4),0)
out.rep_pair2=rk==RWS.pairs[2].beamType and b.value(runtime.read(ptr(beam_slots+8*rk),0x70),8,'f32')==100
local st=hd2.beam_conversion('AR-23 Liberator'):status()
out.status=st.rows['damage.standard_damage']==600 and st.pair.beamType==k
-- A value change on a converted weapon: only its own row, at once (a live Liberator is fine).
LIVE[lib.roots[1].resource]=1
h=tx('lib-stagger','AR-23 Liberator',{{field=F.damage.stagger,expect=10,value=50}})
out.live_value=h.status=='complete'and b.u32(runtime.read(ptr(damage_slots+8*d),0x4C),32)==50
 and b.u32(runtime.read(ptr(damage_slots+8*d),0x4C),12)==4
-- Another operation's value is a CONFLICT (the AP 4 above, expected 2).
h=tx('lib-ap','AR-23 Liberator',{{field=F.damage.ap_direct,expect=2,value=6}})
out.conflict=invalid(h,'CONFLICT')

-- A live shot of its borrowed BeamType holds the restore back (one pulse).
LIVE[lib.roots[1].resource]=nil
local S=ptr(game+RWS.ring.global)
local E0=S+RWS.ring.base
local entry=runtime.read(E0,RWS.ring.stride)
writable(E0+RWS.ring.alive,'\1');writable(E0+RWS.ring.beamType,b.encode(k,'u32'))
h=disable('lib-off','AR-23 Liberator')
out.ring_wait=waiting(h,'live beam shot')
writable(E0+RWS.ring.alive,entry:sub(RWS.ring.alive+1,RWS.ring.alive+1))
writable(E0+RWS.ring.beamType,entry:sub(RWS.ring.beamType+1,RWS.ring.beamType+4))
h=disable('lib-off2','AR-23 Liberator')
out.lib_off=h.status=='complete'and ptr(beam_slots+8*k)==VAN[1][1]and ptr(damage_slots+8*d)==VAN[1][2]
-- The pair is free again and reused first.
h=enable('sickle','LAS-16 Sickle',{{field=F.beam.length,expect=200,value=50}})
out.reuse=h.status=='complete'and b.u32(runtime.read(ptr(SLOT)+0x2E0+weapon('LAS-16 Sickle').record*0x78,4),0)
 ==RWS.pairs[1].beamType
for i,n in ipairs({'LAS-16 Sickle','SMG-32 Reprimand'})do check(disable('off'..i,n).status=='complete','off '..n)end
out.clean=changed()==0 and ptr(SLOT)==TABLE
for i,p in ipairs(RWS.pairs)do
 if ptr(beam_slots+8*p.beamType)~=VAN[i][1]or ptr(damage_slots+8*p.damageInfo)~=VAN[i][2]then out.clean=false end
end
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))

    def test_rows_full_shared_path_and_another_build_refuse_per_weapon_rows(self):
        result = snapshot_run(PRELUDE + r'''
local out={}
local names={}
for _,w in ipairs(C.weapons)do if w.supported and#names<7 then names[#names+1]=w.name end end
for i=1,6 do
 local h=enable('r'..i,names[i],{{field=F.damage.player_standard_damage,expect=60,value=100+i}})
 if h.status~='complete'then out['six_'..i]=false;out.err=tostring(h.error)..' '..tostring(h.last_transient) end
end
local h=enable('r7',names[7],{{field=F.damage.player_standard_damage,expect=60,value=200}})
out.full=invalid(h,'ROWS_FULL')
-- Without own rows the seventh still converts.
h=enable('r7b',names[7])
out.seventh_plain=h.status=='complete'
for i=1,7 do disable('o'..i,names[i])end
out.clean=changed()==0
-- Another game build: the borrowed rows are build-scoped.
local saved=C.rows.gameDllSha256
C.rows.gameDllSha256=string.rep('0',64)
require('hd2runtime/runtime/beam_conversion_rows').reset_for_tests()
h=enable('build','LAS-16 Sickle',{{field=F.beam.length,expect=200,value=50}})
out.other_build=invalid(h,'BORROWED_ROWS_UNVERIFIED_BUILD')
h=enable('build2','LAS-16 Sickle')
out.other_build_plain=h.status=='complete'
disable('build2off','LAS-16 Sickle')
C.rows.gameDllSha256=saved
-- The shared fallback has no own rows.
local pb=runtime.permanent_block;runtime.permanent_block=nil
h=enable('sh','LAS-16 Sickle',{{field=F.damage.player_standard_damage,expect=60,value=90}})
out.shared=invalid(h,'SHARED_RECORD_FALLBACK')
runtime.permanent_block=pb
out.clean2=changed()==0
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))

    def test_the_catalogue_accepts_exactly_its_own_lists_and_nothing_else_changes(self):
        result = snapshot_run(PRELUDE + r'''
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local catalog=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local NAMES={'BeamWeaponComponentData','ProjectileWeaponComponentData','WeaponDataComponentData',
 'WeaponMagazineComponentData','WeaponHeatComponentData'}
-- Every candidate of the catalogue: its diagnostics, refused components and ownership, by resource.
local function capture()
 local out={strays={},by={}}
 local co=coroutine.create(function()
  local reader=Reader.new(runtime)
  local roots=discover.locate(runtime,reader,profile,{entity=true})
  local cat=catalog.capture(reader,roots.entity,profile,NAMES)
  for _,x in ipairs(cat.strays)do out.strays[#out.strays+1]=x.resource..': '..x.reason end
  for _,c in ipairs(cat.candidates)do
   local own={}
   for _,name in ipairs(NAMES)do
    local o=c.ownership[name]
    if o then own[#own+1]=name..'='..o.indexRow..'/'..o.recordIndex end
   end
   local refused={};for k in pairs(c.refused or{})do refused[#refused+1]=k end;table.sort(refused)
   out.by[c.resourceHash]={own=table.concat(own,','),diag=table.concat(c.diagnostics,'|'),
    refused=table.concat(refused,','),heat=c.ownership.WeaponHeatComponentData and pcall(cat.record,c,
     'WeaponHeatComponentData')or nil}
  end
 end)
 repeat local ok,why=coroutine.resume(co);check(ok,why)until coroutine.status(co)=='dead'
 return out
end
local sickle,talon=weapon('LAS-16 Sickle'),weapon('LAS-58 Talon')
local before=capture()
check(#before.strays==0,'no stray row before')
check(enable('sickle','LAS-16 Sickle').status=='complete','sickle')
check(enable('talon','LAS-58 Talon').status=='complete','talon')
local after=capture()
local out={}
out.no_stray=#after.strays==0
local mine={[sickle.roots[1].resource]=true,[talon.roots[1].resource]=true}
local same=true
for resource,c in pairs(before.by)do
 local a=after.by[resource]
 if not mine[resource]and not(a and a.own==c.own and a.diag==c.diag and a.refused==c.refused)then
  same=false;out['changed '..resource]=tostring(a and(a.own..' / '..a.diag))
 end
end
out.others_unchanged=same
-- The converted roots: no diagnostic (their lists are accepted), BeamWeapon owned in the copy, the ProjectileWeapon
-- and BeamWeapon records refused (their conversion's), the heat record still readable.
for resource in pairs(mine)do
 local a=after.by[resource]
 out['clean '..resource]=a.diag==''and a.refused=='BeamWeaponComponentData,ProjectileWeaponComponentData'and a.heat
 out['beam '..resource]=a.own:find('BeamWeaponComponentData=',1,true)~=nil
end
-- Typed writes: the Sickle's heat goes ahead, its fire rate is refused; another weapon writes as before. (Their bytes
-- are put back afterwards from the overlay as it was: a transaction's expect is the shipped value.)
local kept={}
for address,value in pairs(overlay)do kept[address]=value end
local r=hd2.transaction({id='heat',target=hd2.weapon('LAS-16 Sickle'),changes={
 {field=F.heat.heat_per_shot,expect=1.15,value=1.2}}})
done(r);out.heat_write=r.status=='complete'
r=hd2.transaction({id='rate',target=hd2.weapon('LAS-16 Sickle'),changes={{field=F.weapon.fire_rate,expect=750,value=700}}})
done(r);out.rate_refused=r.status=='rejected'and tostring(r.error):find('add layout',1,true)~=nil
r=hd2.transaction({id='ergo',target=hd2.weapon('AR-23 Liberator'),changes={{field=F.weapon.ergonomics,expect=65,value=70}}})
done(r);out.other_weapon=r.status=='complete'
for address,value in pairs(overlay)do
 if kept[address]~=value then writable(address,kept[address]or source.read(address,#value))end
end
-- Another program changes a byte of HD2Runtime's list block: the row is no longer accepted (stray, its own resource
-- only) and the conversion is refused until it is back.
local blk=require('hd2runtime/runtime/beam_conversion').list_block_bytes()
local root=sickle.roots[1]
local at=ptr(row_of(root)+8)
local old=runtime.read(at,2)
writable(at,'\255\255')
local t=capture()
local stray_only=#t.strays==1 and t.strays[1]:find(root.resource,1,true)~=nil
 and t.strays[1]:find('not as HD2Runtime built it',1,true)~=nil
out.tampered_block_stray=stray_only
local h=tx('touch','LAS-16 Sickle',{{field=F.beam.fire_rate,expect=300,value=310}})
out.tampered_block_refused=h.status=='rejected'
writable(at,old)
-- Another program repoints the row to an identical list elsewhere: not HD2Runtime's pointer, refused.
local fake=runtime.permanent_block(runtime.read(at,2*root.add.count))
writable(row_of(root)+8,b.encode(fake%TWO32,'u32')..b.encode(math.floor(fake/TWO32),'u32'))
t=capture()
out.repointed_stray=#t.strays==1 and t.strays[1]:find(root.resource,1,true)~=nil
h=disable('repointed','LAS-16 Sickle')
out.repointed_conflict=h.status=='rejected'and tostring(h.error):find('CONFLICT',1,true)~=nil
writable(row_of(root)+8,b.encode(at%TWO32,'u32')..b.encode(math.floor(at/TWO32),'u32'))
-- Restored: the lists are the file's again, nothing registered, every byte vanilla.
check(disable('off1','LAS-16 Sickle').status=='complete','sickle off')
check(disable('off2','LAS-58 Talon').status=='complete','talon off')
local final=capture()
out.back=#final.strays==0 and not OT.lists_active()and changed()==0
for resource,c in pairs(before.by)do
 local a=final.by[resource]
 if not(a and a.own==c.own and a.diag==c.diag)then out.back=false end
end
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))

    def test_a_loader_reload_and_a_foreign_list_are_detected(self):
        result = snapshot_run(PRELUDE + r'''
local out={}
local sickle=weapon('LAS-16 Sickle')
local root=sickle.roots[1]
check(enable('sickle','LAS-16 Sickle').status=='complete','sickle')
-- The entity loader reloads the file (0xFDB860): the row names the file's list again (as shipped); the BeamWeapon row
-- and the record's type 0 are left: orphaned, restored as a whole.
local slot_at=ptr(row_of(root)+8)
local file=ESH+root.membership.listOffsetInBody
writable(row_of(root)+8,b.encode(file%TWO32,'u32')..b.encode(math.floor(file/TWO32),'u32'))
writable(row_of(root)+16,b.encode(root.membership.count,'u32'))
local st=hd2.beam_conversion('LAS-16 Sickle'):status()
out.orphaned=st.state=='orphaned'
local h=enable('again','LAS-16 Sickle')
out.enable_refused=h.status=='rejected'and tostring(h.error):find('disable the conversion first',1,true)~=nil
h=disable('off','LAS-16 Sickle')
out.restored=h.status=='complete'and vanilla_ok(sickle)and changed()==0
-- The list block is reused by the next conversion (one per game process; only a new BeamWeapon copy is built).
local blocks=counts.permanent_blocks
check(enable('sickle2','LAS-16 Sickle').status=='complete','sickle again')
out.reused=ptr(row_of(root)+8)==slot_at and counts.permanent_blocks==blocks+1
check(disable('off2','LAS-16 Sickle').status=='complete','off2')
-- Another mod grows the list itself (a bigger list elsewhere, count + 1, as True Lasgun Beam Overhaul does): the
-- conversion never chains onto it.
local grown=runtime.permanent_block(runtime.read(file,2*root.membership.count)..'')
writable(row_of(root)+8,b.encode(grown%TWO32,'u32')..b.encode(math.floor(grown/TWO32),'u32'))
writable(row_of(root)+16,b.encode(root.membership.count+1,'u32'))
h=enable('foreign','LAS-16 Sickle')
out.foreign=h.status=='rejected'and tostring(h.error):find('another membership list',1,true)~=nil
writable(row_of(root)+8,b.encode(file%TWO32,'u32')..b.encode(math.floor(file/TWO32),'u32'))
writable(row_of(root)+16,b.encode(root.membership.count,'u32'))
-- A heat weapon whose fire rate another write changed: the add layout pins it.
local PW=PTABLE+C.projectile.recordBase+root.projectile.record*C.projectile.recordStride
writable(PW+8,b.encode(700,'f32'))
h=enable('pinned','LAS-16 Sickle')
out.rate_pinned=h.status=='rejected'and tostring(h.error):find('fire rate is not its vanilla value',1,true)~=nil
writable(PW+8,b.unhex(root.add.rateBefore))
-- Another projectile type in its record: foreign.
writable(PW,b.encode(1,'u32'))
h=enable('type','LAS-16 Sickle')
out.type_foreign=h.status=='rejected'and tostring(h.error):find('CONFLICT',1,true)~=nil
writable(PW,b.unhex(root.add.typeBefore))
-- Without permanent blocks (and no block yet) the add layout falls back to the swap layout, solo only.
E.reset_for_tests()
E.set_hooks_for_tests({census=function()return {live=0,tridents=0,by={}}end,solo=function()return true,'test'end,
 assets=function()return'resident','test'end})
local pb=runtime.permanent_block;runtime.permanent_block=nil
h=enable('fallback','SMG-32 Reprimand')
out.fallback_swap=h.status=='complete'and list_of(weapon('SMG-32 Reprimand').roots[1])==
 weapon('SMG-32 Reprimand').roots[1].membership.after
check(disable('fallbackoff','SMG-32 Reprimand').status=='complete','fallback off')
runtime.permanent_block=pb
out.clean=changed()==0
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))

    def test_a_join_after_apply_restores_idle_conversions_and_warns(self):
        result = snapshot_run(PRELUDE + r'''
local W=require('hd2runtime/runtime/beam_conversion_watch')
local sickle,lib=weapon('LAS-16 Sickle'),weapon('AR-23 Liberator')
check(enable('sickle','LAS-16 Sickle').status=='complete','sickle')
check(enable('lib','AR-23 Liberator').status=='complete','liberator')
-- The swap-converted Liberator is in use (live), the add-converted Sickle is not; then another player joins and no
-- lobby value can be read.
LIVE[lib.roots[1].resource]=1
LOBBY.solo=false
W.tick_for_tests(6)
local out={}
out.live_swap_kept=converted_ok(lib)
out.warned=W.status().warned~=nil
out.add_kept_while_pending=converted_ok(sickle)
-- After the pending window, the idle add conversion is restored too (nothing could be read: fail closed).
for _=1,7 do W.tick_for_tests(5)end
out.add_restored_after_window=vanilla_ok(sickle)
-- The Liberator is restored once it is no longer live.
LIVE[lib.roots[1].resource]=nil
W.tick_for_tests(6)
out.later_restored=vanilla_ok(lib)and ptr(SLOT)==TABLE
out.watch_done=not W.status().active or#W.status().converted==0
-- Apply waits while not solo: the swap layout NOT_SOLO, the add layout NOT_AGREED.
out.swap_waits=waiting(enable('again','AR-23 Liberator'),'NOT_SOLO')
out.add_waits=waiting(enable('again2','LAS-16 Sickle'),'NOT_AGREED')
LOBBY.solo=true
out.clean=changed()==0
return json.encode(out)''')
        for key, value in result.items():
            self.assertTrue(value, (key, result))


if __name__ == '__main__':
    unittest.main()
