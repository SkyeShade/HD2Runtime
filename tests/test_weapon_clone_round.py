"""The carrier weapon clone's ROUND override (runtime/weapon_clone.lua `round`, domains/weapon_clone.lua `rounds`,
scripts/research_clone_rounds.py; build/test-artifacts/airburst-research/airburst.md option (b)): an EAT-17 clone on
the EAT-700 or EAT-411 carrier type fires the RL-77 Airburst round 312 natively (ProjectileWeapon +0 ProjType := 312
at every level).
  * the generated round: its chain rows, pins, packages and semantics as the research reviewed them;
  * the API: M.round / M.rounds / M.writes_at with a round;
  * an offline fixture (synthetic memory with the reviewed rows, pins and the hosts' native records; the entity
    catalogue, the world and package residency simulated): the round write at presentation, model and full on both
    hosts (one more write below full, the same count at full, ProjType 312, every other member as without a round),
    the exact restore, CONFLICT when another writer changed ProjType, ROUND_CHANGED when one byte of a reviewed row
    differs (a masked relocated word may), ROUND_NOT_RESIDENT when either package is not resident (or unreadable),
    UNSUPPORTED_BUILD when a round pin differs, INVALID / UNREVIEWED_ROUND for anything but a reviewed round's name;
    nothing written on any refusal; the round-less path unchanged;
  * on every retained snapshot (when present): scripts/validate_weapon_clone_snapshot.py's round overlay (the real
    rows and the real engine package list: the mission package is found resident in the live mission snapshots)."""
import importlib.util
import json
import unittest

from support import ROOT, run

import build_profile

DONOR, ROUND = 'EAT-17 Expendable Anti-Tank', 'RL-77 Airburst Rocket Launcher'
EAT700, EAT411 = 'EAT-700 Expendable Napalm', 'EAT-411 Leveller'

FIXTURE = r"""
local json=require('hd2runtime/primary_mapper/json')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/weapon_clone')
local world_module=require('hd2runtime/runtime/event_world')
local discover=require('hd2runtime/runtime/discover')
local entity_catalog=require('hd2runtime/core/entity_catalog')
local fingerprint=require('hd2runtime/core/fingerprint')
local native_view=require('hd2runtime/runtime/native_view')
local clone=require('hd2runtime/runtime/weapon_clone');clone.reset_for_tests()
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(text)lines[#lines+1]=tostring(text)end
local function said(text)for _,l in ipairs(lines)do if l:find(text,1,true)then return l end end end
local DONOR,ROUND='EAT-17 Expendable Anti-Tank','RL-77 Airburst Rocket Launcher'
local EAT700,EAT411='EAT-700 Expendable Napalm','EAT-411 Leveller'
local R=D.rounds[DONOR][ROUND]
local PAGE,G32=4096,4294967296
local GAME,REGION,EM,SPOT,ROWS=0x7FF6*G32,0x200*G32,0x210*G32,0x220*G32,0x230*G32
local function record_at(component,index)
    local c=D.components[component]
    return c.offset+28+c.record_offset+index*c.stride,c.stride
end
local REGION_SIZE=0
for _,c in pairs(D.carriers)do
    for component,r in pairs(c.records)do
        local offset,stride=record_at(component,r.recordIndex)
        REGION_SIZE=math.max(REGION_SIZE,offset+stride)
    end
end
REGION_SIZE=REGION_SIZE-REGION_SIZE%PAGE+2*PAGE
local OWNER={base=REGION,size=REGION_SIZE,type=0x20000,protect=2}
-- Sparse paged memory: regions, pages (lazily zero), per-page protection.
local regions={{base=GAME,size=0x4800000,protect=2,type=0x1000000},
    {base=REGION,size=REGION_SIZE,protect=2,type=0x20000},{base=EM,size=0x1000000,protect=4,type=0x20000},
    {base=SPOT,size=PAGE,protect=4,type=0x20000},{base=ROWS,size=0x10000,protect=4,type=0x20000}}
local function region_of(at)for _,r in ipairs(regions)do if at>=r.base and at<r.base+r.size then return r end end end
local ZERO=string.rep('\0',PAGE)
local pages,protection={},{}
local counts={writes=0}
local function page_of(at)return at-at%PAGE end
local function read(at,n)
    local r=region_of(at)
    if not r or at+n>r.base+r.size then return nil end
    local parts,cursor,left={},at,n
    while left>0 do
        local p=page_of(cursor)
        local off=cursor-p
        local take=math.min(left,PAGE-off)
        parts[#parts+1]=(pages[p]or ZERO):sub(off+1,off+take)
        cursor,left=cursor+take,left-take
    end
    return table.concat(parts)
end
local function poke(at,bytes)
    local cursor,i=at,1
    while i<=#bytes do
        local p=page_of(cursor)
        local off=cursor-p
        local take=math.min(#bytes-i+1,PAGE-off)
        local page=pages[p]or ZERO
        pages[p]=page:sub(1,off)..bytes:sub(i,i+take-1)..page:sub(off+take+1)
        cursor,i=cursor+take,i+take
    end
end
local resident={}
local runtime={mode='fixture'}
function runtime.read(at,n)return read(at,n)end
function runtime.query(at)
    local r=region_of(at)
    if not r then return {base=page_of(at),size=PAGE,allocation_base=0,state=0x10000,type=0,protect=1}end
    local p=page_of(at)
    return {base=p,size=PAGE,allocation_base=r.base,state=0x1000,type=r.type,protect=protection[p]or r.protect}
end
function runtime.protect(page,size,value)
    assert(page%PAGE==0 and size==PAGE,'fixture protect extent')
    local r=region_of(page)
    local old=protection[page]or r.protect
    if value==r.protect then protection[page]=nil else protection[page]=value end
    return old
end
function runtime.write(at,bytes)
    assert((protection[page_of(at)]or region_of(at).protect)==4,'fixture write without a writable page')
    counts.writes=counts.writes+1
    poke(at,bytes)
    return true,nil,#bytes
end
function runtime.system_info()return PAGE,2^47 end
function runtime.package_state(id)return resident[id]or'absent'end
local function u64(n)return b.encode(n%G32,'u32')..b.encode(math.floor(n/G32),'u32')end
-- game.dll: the clone's and the round's pins, the entity manager's type tables, the Spottable manager (no instance),
-- the round's chain rows through their tables.
for _,pin in ipairs(D.pins)do poke(GAME+pin.rva,b.unhex(pin.hex))end
for _,pin in ipairs(R.pins)do poke(GAME+pin.rva,b.unhex(pin.hex))end
local row_at={}
for k,row in ipairs(R.rows)do
    local at=ROWS+(k-1)*512
    poke(at,b.unhex(row.reviewed))
    poke(GAME+row.table+row.id*8,u64(at))
    row_at[k]=at
end
poke(GAME+D.entityManager,u64(EM))
for _,c in pairs(D.components)do poke(EM+c.slot,u64(REGION+c.offset+28))end
poke(GAME+D.spottableInstances.global,u64(SPOT))
-- Each host's records: its reviewed native bytes at every member written (zero elsewhere); the fixture's record is the
-- native one (its FNV-1a; the real records' reviewed FNV-1a is the snapshot validation's).
for _,c in pairs(D.carriers)do
    for component,r in pairs(c.records)do
        local offset,stride=record_at(component,r.recordIndex)
        local bytes=string.rep('\0',stride)
        local function put(o,hex)local v=b.unhex(hex);bytes=bytes:sub(1,o)..v..bytes:sub(o+#v+1)end
        for _,w in ipairs(c.writes)do if w.component==component then put(w.offset,w.native)end end
        for _,p in ipairs(c.presentation)do if p.component==component then put(p.offset,p.native)end end
        poke(REGION+offset,bytes)
        r.fnv1a=clone.fnv1a(bytes)
    end
end
-- The world, the entity catalogue and the build fingerprint, simulated.
fingerprint.require=function()end
discover.locate=function()return {entity={base=REGION}}end
entity_catalog.capture=function()
    local candidates={}
    for name,c in pairs(D.carriers)do
        candidates[#candidates+1]={resourceHash=c.entity,entityRow=1,diagnostics={},carrier=name}
    end
    return {candidates=candidates,record=function(candidate,component)
        local r=D.carriers[candidate.carrier].records[component]
        local offset,stride=record_at(component,r.recordIndex)
        return {bytes=read(REGION+offset,stride),owner=OWNER,offset=offset,index=r.recordIndex,
            identity={recordIndex=r.recordIndex,indexRow=r.indexRow,ownerCount=1,uniqueOwner=true}}
    end}
end
local world={runtime=runtime,view=native_view.new(runtime),game=GAME,exe=GAME,key='fixture'}
world_module.open=function()return world end
world_module.game_state=function()return {mission=true,state=0,name='mission'}end
world_module.players=function()return {}end
local INITIAL={}
for k,v in pairs(pages)do INITIAL[k]=v end
local function reset()
    pages={}
    for k,v in pairs(INITIAL)do pages[k]=v end
    protection={};counts.writes=0;lines={}
    resident={[R.packages.unit.id]='resident',[R.packages.mission.id]='resident'}
    clone.reset_for_tests()
end
local function initial()
    for k,v in pairs(pages)do if(INITIAL[k]or ZERO)~=v then return false end end
    for k,v in pairs(INITIAL)do if(pages[k]or ZERO)~=v then return false end end
    return next(protection)==nil
end
local function settle(job)for _=1,4000 do if job.status~='pending'then break end;update(0.1)end;return job end
local function projtype_at(carrier)
    return REGION+record_at('ProjectileWeaponComponentData',D.carriers[carrier].records.ProjectileWeaponComponentData
        .recordIndex)
end
local function projtype(carrier)return b.u32(read(projtype_at(carrier),4),0)end
-- The memory as an apply found it (a test may have changed it on purpose first).
local before_apply
local function apply(carrier,level,round)
    before_apply={}
    for k,v in pairs(pages)do before_apply[k]=v end
    return settle(clone.apply({carrier=carrier,donor=DONOR,level=level,round=round}))
end
local function untouched()
    for k,v in pairs(pages)do if(before_apply[k]or ZERO)~=v then return false end end
    for k,v in pairs(before_apply)do if(pages[k]or ZERO)~=v then return false end end
    return next(protection)==nil
end
-- A refusal: what it said, and whether anything was written (the fixture's write count, the memory and protection).
local function refusal(h)
    return {status=h.status,code=h.code,reason=h.reason,writes=counts.writes,applied=clone.applied(),
        untouched=untouched()}
end
"""


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lua(body):
    return json.loads(run(FIXTURE + body))


class WeaponCloneRoundDomainTests(unittest.TestCase):
    def test_the_generated_round(self):
        generator = load('generate_weapon_clone', 'scripts/generate_weapon_clone.py')
        self.assertEqual(generator.generate(check=True), [])
        domain = generator.build()
        r = domain['rounds'][DONOR][ROUND]
        self.assertEqual(list(domain['rounds']), [DONOR])
        self.assertEqual(list(domain['rounds'][DONOR]), [ROUND])
        self.assertEqual((r['type'], r['impact'], r['expiry'], r['proximity'], r['arming'], r['lifetime'], r['speed']),
            (312, 325, 325, 2.0, 1.0, 1.5, 250.0))
        self.assertEqual(r['direct'], {'standard': 350, 'armorPenetration': 3})
        self.assertEqual(r['submunition'], {'count': 25, 'projectile': 78, 'explosion': 7})
        self.assertEqual(r['assetKey'], 'support_weapon/RL-77 Airburst Rocket Launcher')
        self.assertEqual(r['packages'], {
            'unit': {'id': '0xF7646E79610C124D', 'name': 'packages/generated/loadout/airburst_rocket_launcher'},
            'mission': {'id': '0x7ED1F941859987B4', 'name': None}})
        self.assertEqual([(x['kind'], x['id'], x['stride'], x['masked']) for x in r['rows']], [
            ('projectile', 312, 272, []), ('damage', 380, 76, []), ('explosion', 325, 152, [40, 44]),
            ('damage', 277, 76, []), ('projectile', 78, 272, []), ('explosion', 7, 152, [40, 44]),
            ('damage', 335, 76, [])])
        self.assertEqual({x['table'] for x in r['rows']}, {0x37C7670, 0x37CC920, 0x37C60C0})
        p312 = bytes.fromhex(r['rows'][0]['reviewed'])
        self.assertEqual(p312[0x90:0xA4].hex(), '45010000' '00000040' 'cdcc4c3e' '45010000' '0000803f')
        x325 = bytes.fromhex(r['rows'][2]['reviewed'])
        self.assertEqual(x325[0x50:0x58].hex(), '190000004e000000')     # 25 x projectile 78
        rvas = {p['rva'] for p in r['pins']}
        for rva in (0x13AA486, 0x13AA493, 0x13ABE3A, 0x13ABFB7, 0x13AC0D8, 0x13AC50C, 0x13AED2A, 0x13AB751,
                0x13B0BB9):
            self.assertIn(rva, rvas)
        self.assertIn('25 x bomblet 78', r['summary'])

    def test_the_api(self):
        result = lua(r"""
local rounds=clone.rounds(DONOR)
local r=clone.round(DONOR,ROUND)
r.direct_ap=r.direct.armor_penetration
local counts={}
for _,carrier in ipairs({EAT700,EAT411})do
    counts[carrier]={}
    for _,level in ipairs(D.levels)do
        counts[carrier][level]={clone.writes_at(carrier,level),clone.writes_at(carrier,level,ROUND)}
    end
end
r.copy=clone.round(DONOR,ROUND)~=clone.round(DONOR,ROUND)
return json.encode({rounds=rounds,none=#clone.rounds('MG-43 Machine Gun'),round=r,
    gr8=clone.round(DONOR,'GR-8 Recoilless Rifle')==nil,other=clone.round('MG-43 Machine Gun',ROUND)==nil,
    counts=counts,unreviewed=clone.writes_at(EAT700,'full','GR-8 Recoilless Rifle')==nil,
    outside=clone.writes_at('MG-43 Machine Gun','full',ROUND)==nil})
""")
        self.assertEqual(result['rounds'], [ROUND])
        self.assertEqual(result['none'], 0)
        r = result['round']
        self.assertEqual((r['name'], r['type'], r['asset_key'], r['impact'], r['expiry']),
            (ROUND, 312, 'support_weapon/RL-77 Airburst Rocket Launcher', 325, 325))
        self.assertEqual(r['packages'], {'unit': '0xF7646E79610C124D', 'mission': '0x7ED1F941859987B4'})
        self.assertEqual(r['package_names']['unit'], 'packages/generated/loadout/airburst_rocket_launcher')
        self.assertEqual(r['submunition'], {'count': 25, 'projectile': 78, 'explosion': 7})
        self.assertEqual((r['direct']['standard'], r['direct_ap'], r['proximity'], r['arming'], r['lifetime']),
            (350, 3, 2.0, 1.0, 1.5))
        self.assertTrue(r['copy'])
        self.assertTrue(result['gr8'] and result['other'] and result['unreviewed'] and result['outside'])
        # One more write below full; the same count at full (the round replaces the donor's ProjType).
        self.assertEqual(result['counts'][EAT700], {'presentation': [3, 4], 'model': [14, 15], 'full': [22, 22]})
        for carrier in (EAT700, EAT411):
            c = result['counts'][carrier]
            self.assertEqual(c['presentation'][1], c['presentation'][0] + 1)
            self.assertEqual(c['model'][1], c['model'][0] + 1)
            self.assertEqual(c['full'][1], c['full'][0])


class WeaponCloneRoundFixtureTests(unittest.TestCase):
    def test_every_level_on_both_hosts_and_the_exact_restore(self):
        result = lua(r"""
local out={}
for _,carrier in ipairs(clone.pool(DONOR))do
    out[carrier]={}
    for _,level in ipairs(D.levels)do
        -- The same conversion without the round, for its write count (a member crossing a page is two writes).
        reset()
        local plain=apply(carrier,level)
        settle(clone.restore(nil,carrier))
        reset()
        local native=projtype(carrier)
        local h=apply(carrier,level,ROUND)
        local e={status=h.status,code=h.code,reason=h.reason,writes=h.writes,fixtureWrites=counts.writes,round=h.round,
            plainWrites=plain.writes,
            expected=clone.writes_at(carrier,level,ROUND),projtype=projtype(carrier),native=native,
            changes=h.status=='applied'and#clone.state(carrier).changes or nil,stateRound=clone.state(carrier)
            and clone.state(carrier).round,logged=said('it fires round 312 (RL-77 Airburst Rocket Launcher')~=nil}
        -- Every other member: the donor's at its level, else its native bytes.
        local c=D.carriers[carrier]
        local mismatched=0
        for _,w in ipairs(c.writes)do
            local at=REGION+record_at(w.component,c.records[w.component].recordIndex)+w.offset
            local want=clone.LEVELS[w.level]<=clone.LEVELS[level]and w.donor or w.native
            if w.component=='ProjectileWeaponComponentData'and w.offset==0 then want=b.hex(b.encode(312,'u32'))end
            if read(at,w.width)~=b.unhex(want)then mismatched=mismatched+1 end
        end
        e.mismatched=mismatched
        local w0=counts.writes
        local r=settle(clone.restore(nil,carrier))
        e.restore={status=r.status,code=r.code,exact=r.verify and r.verify.exact,writes=counts.writes-w0}
        e.after=projtype(carrier)
        e.initial=initial()
        out[carrier][level]=e
    end
end
-- The round-less path is unchanged: the donor's rocket at full, the carrier's own below.
local plain={}
for _,level in ipairs(D.levels)do
    reset()
    local h=apply(EAT700,level)
    plain[level]={status=h.status,writes=h.writes,projtype=projtype(EAT700),round=h.round,
        expected=clone.writes_at(EAT700,level),fires=said('it fires')~=nil,applied=said('APPLIED (')~=nil}
    settle(clone.restore(nil,EAT700))
    plain[level].initial=initial()
end
return json.encode({levels=out,plain=plain})
""")
        natives = {EAT700: 259, EAT411: 34}
        for carrier in (EAT700, EAT411):
            for level in ('presentation', 'model', 'full'):
                e = result['levels'][carrier][level]
                where = '%s %s: %r' % (carrier, level, e)
                self.assertEqual(e['status'], 'applied', where)
                self.assertEqual(e['round'], ROUND, where)
                self.assertEqual(e['stateRound'], ROUND, where)
                self.assertEqual(e['native'], natives[carrier], where)
                self.assertEqual(e['projtype'], 312, where)
                # One more write than without the round below full, the same at full (a member crossing a page is
                # written as 4-byte words: at least writes_at).
                self.assertEqual(e['writes'], e['plainWrites'] + (0 if level == 'full' else 1), where)
                self.assertGreaterEqual(e['writes'], e['expected'], where)
                self.assertEqual(e['changes'], e['writes'], where)
                self.assertEqual(e['fixtureWrites'], e['writes'], where)
                self.assertEqual(e['mismatched'], 0, where)
                self.assertTrue(e['logged'], where)
                self.assertEqual(e['restore']['status'], 'restored', where)
                self.assertTrue(e['restore']['exact'], where)
                self.assertEqual(e['restore']['writes'], e['writes'], where)
                self.assertEqual(e['after'], natives[carrier], where)
                self.assertTrue(e['initial'], where)
        for level, projtype in (('presentation', 259), ('model', 259), ('full', 132)):
            p = result['plain'][level]
            self.assertEqual((p['status'], p['projtype']), ('applied', projtype), p)
            self.assertGreaterEqual(p['writes'], p['expected'], p)
            self.assertNotIn('round', p)
            self.assertFalse(p['fires'])
            self.assertTrue(p['applied'] and p['initial'], p)

    def test_conflict_when_another_writer_changed_projtype(self):
        result = lua(r"""
local out={}
for _,level in ipairs({'presentation','full'})do
    reset()
    local h=apply(EAT411,level,ROUND)
    poke(projtype_at(EAT411),b.encode(132,'u32'))
    local w0=counts.writes
    local refused=settle(clone.restore(nil,EAT411))
    local none=counts.writes==w0
    local still=clone.applied(EAT411)
    poke(projtype_at(EAT411),b.encode(312,'u32'))
    local back=settle(clone.restore(nil,EAT411))
    out[level]={applied=h.status,status=refused.status,code=refused.code,reason=refused.reason,nothingWritten=none,
        stillHeld=still,thenRestored=back.status,exact=back.verify and back.verify.exact,initial=initial()}
end
return json.encode(out)
""")
        for level, c in result.items():
            self.assertEqual((c['applied'], c['status'], c['code']), ('applied', 'refused', 'CONFLICT'), c)
            self.assertIn('(round)', c['reason'])
            self.assertTrue(c['nothingWritten'] and c['stillHeld'], c)
            self.assertEqual(c['thenRestored'], 'restored', c)
            self.assertTrue(c['exact'] and c['initial'], c)

    def test_round_changed_when_a_reviewed_row_differs(self):
        result = lua(r"""
local out={changed={}}
for k,row in ipairs(R.rows)do
    reset()
    local at=row_at[k]+4
    poke(at,string.char((read(at,1):byte()+1)%256))
    local h=apply(EAT700,'full',ROUND)
    out.changed[k]=refusal(h)
    out.changed[k].row=row.kind..' '..row.id
end
-- A row no longer in its table.
reset()
poke(GAME+R.rows[5].table+R.rows[5].id*8,string.rep('\0',8))
out.missing=refusal(apply(EAT700,'presentation',ROUND))
-- A masked (relocated) word may differ.
reset()
for k,row in ipairs(R.rows)do for _,o in ipairs(row.masked)do poke(row_at[k]+o,'\1\2\3\4')end end
local h=apply(EAT700,'model',ROUND)
out.masked={status=h.status,projtype=projtype(EAT700)}
settle(clone.restore(nil,EAT700))
return json.encode(out)
""")
        self.assertEqual(len(result['changed']), 7)
        for c in result['changed']:
            self.assertEqual((c['status'], c['code'], c['writes'], c['applied'], c['untouched']),
                ('refused', 'ROUND_CHANGED', 0, False, True), c)
            self.assertIn(c['row'], c['reason'])
            self.assertIn('nothing written', c['reason'])
        m = result['missing']
        self.assertEqual((m['status'], m['code'], m['writes'], m['untouched']), ('refused', 'ROUND_CHANGED', 0, True),
            m)
        self.assertIn('projectile 78', m['reason'])
        self.assertEqual(result['masked'], {'status': 'applied', 'projtype': 312})

    def test_round_not_resident(self):
        result = lua(r"""
local out={}
for _,case in ipairs({{'unit','absent'},{'mission','absent'},{'unit','loading'},{'mission','queued'}})do
    reset()
    resident[R.packages[case[1]].id]=case[2]
    local e=refusal(apply(EAT411,'presentation',ROUND))
    e.case=case[1]..' '..case[2]
    out[#out+1]=e
end
-- The residency read fails: closed.
reset()
local saved=runtime.package_state
runtime.package_state=function()error('ASSET_UNAVAILABLE: package state unreadable',0)end
local e=refusal(apply(EAT700,'full',ROUND))
runtime.package_state=saved
e.case='unreadable'
out[#out+1]=e
-- A round-less clone does not need them.
reset()
resident={}
local h=apply(EAT700,'full')
out[#out+1]={case='round-less',status=h.status}
settle(clone.restore(nil,EAT700))
return json.encode(out)
""")
        for e in result[:-1]:
            self.assertEqual((e['status'], e['code'], e['writes'], e['applied'], e['untouched']),
                ('refused', 'ROUND_NOT_RESIDENT', 0, False, True), e)
        self.assertIn('unit package packages/generated/loadout/airburst_rocket_launcher is absent', result[0]['reason'])
        self.assertIn('mission package 0x7ED1F941859987B4 is absent', result[1]['reason'])
        self.assertIn('is loading', result[2]['reason'])
        self.assertIn('is queued', result[3]['reason'])
        self.assertIn('unreadable', result[4]['reason'])
        self.assertEqual(result[5], {'case': 'round-less', 'status': 'applied'})

    def test_refusals_before_any_write(self):
        result = lua(r"""
local out={}
for _,round in ipairs({312,{name=ROUND},'GR-8 Recoilless Rifle','rl-77 airburst rocket launcher'})do
    reset()
    local e=refusal(apply(EAT700,'full',round))
    e.round=type(round)=='string'and round or type(round)
    out[#out+1]=e
end
-- A round pin no longer proves.
reset()
local pin=R.pins[1]
poke(GAME+pin.rva,string.char((read(GAME+pin.rva,1):byte()+1)%256))
out[#out+1]=refusal(apply(EAT411,'model',ROUND))
return json.encode(out)
""")
        codes = [(e['status'], e['code']) for e in result]
        self.assertEqual(codes, [('refused', 'INVALID'), ('refused', 'INVALID'), ('refused', 'UNREVIEWED_ROUND'),
            ('refused', 'UNREVIEWED_ROUND'), ('refused', 'UNSUPPORTED_BUILD')])
        for e in result:
            self.assertEqual((e['writes'], e['applied'], e['untouched']), (0, False, True), e)
        self.assertIn('round research no longer matches', result[4]['reason'])


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot absent')
class WeaponCloneRoundSnapshotTests(unittest.TestCase):
    def test_every_retained_snapshot(self):
        module = load('validate_weapon_clone_snapshot', 'scripts/validate_weapon_clone_snapshot.py')
        names = [n for n in module.SNAPSHOTS if (build_profile.snapshot_directory() / n).is_file()]
        results = module.validate(tuple(names))
        live = 0
        for name, result in results.items():
            self.assertTrue(result['passed'], name + ': ' + '; '.join(result['problems']))
            if result['phase'] not in ('alive', 'reinforced'):
                continue
            live += 1
            rounds = result['report']['rounds']
            self.assertEqual(rounds['missionPackage'], 'resident', name)
            self.assertEqual(rounds['unitPackage'], 'absent', name)        # nobody brought an RL-77
            for carrier in (EAT700, EAT411):
                for level in ('presentation', 'model', 'full'):
                    lv = rounds['carriers'][carrier]['levels'][level]
                    self.assertEqual((lv['status'], lv['projtype']), ('applied', 312), (name, carrier, level, lv))
        self.assertTrue(live, 'no live mission snapshot validated')


if __name__ == '__main__':
    unittest.main()
