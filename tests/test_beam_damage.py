"""Per-weapon beam damage for the EXPERIMENTAL multi-weapon beam swap (runtime/experiment_beam_damage.lua, domains/
beam_swap.lua `damage`; research/docs/beam-damage-per-weapon-F5FEE03DCFDB.md): the Liberator, Talon and Reprimand all
fire BeamWeapon record 23 (the Trident's copy), so one BeamInfo row (6) and one DamageInfo row (508); each gets its own
damage and penetration through its OWN shots' ring entries (the multipliers and DamageInfo id BeamFire copies from the
row), written once per shot, before the shot's first ray query. Branch exp/multi-beam only.

The snapshot tests run on the copy-on-write overlay of the retained current-build snapshot (no game process): the real
game.dll pins, the real beam system, BeamInfo and DamageInfo tables, the real swap (experiment_beam_swap.lua); the shots
are entries written into the real ring as BeamFire leaves them (addresses derived here from the research, never through
the module under test); only the weapon entity types, the mission state and the player count are stand-ins.
"""
import json
import unittest

from support import ROOT, run  # noqa: F401
from test_multi_mod_composition import build_profile, snapshot_run
from test_beam_swap import LOCATE

import sys
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_beam_swap  # noqa: E402

RESEARCH = json.loads((ROOT / 'research/beam-damage-per-weapon-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

# The ring and the rows, from the research's own numbers; shots as BeamFire 0x13B8410 leaves them.
SHOTS = r'''
local G=require('hd2runtime/domains/beam_swap').damage
local BD=require('hd2runtime/runtime/experiment_beam_damage')
BD.reset_for_tests()
runtime.package_state=function()return'resident'end
X.set_hooks_for_tests({assets=function()return'resident','forced by the test'end})
local S=ptr(game+0x347CED0)
check(S==ptr(game+0x3326340)+0x2563C48,'the beam system is not world + 0x2563C48')
local RING=S+0x170
local ROW6=ptr(game+0x37C8250+6*8)
local ROW6B=runtime.read(ROW6,0x70)
check(b.u32(ROW6B,0)==6 and b.u32(ROW6B,0xC)==508,'BeamInfo row 6 is not the Trident\'s')
local DMG508=ptr(game+0x37C60C0+508*8)
local DMG508B=runtime.read(DMG508,0x4C)
local DMG501B=runtime.read(ptr(game+0x37C60C0+501*8),0x4C)
local RING_BEFORE=runtime.read(RING,64*0x168)
local TYPES={[7001]='968211C0033DCE64',[7002]='416D053372C4E433',[7003]='94BD931B5FB4EE95',[7004]='3C86E871923F3970'}
local hk={mission=true,players=1}
BD.set_hooks_for_tests({entity_type=function(_,e)return TYPES[e]end,players=function()return hk.players end,
 game_state=function()return{mission=hk.mission}end,assets=function()return hk.assets or'resident'end})
local shot_serial=0
local CUTS={{0,0x24},{0x24,4},{0x28,4},{0x2C,4},{0x30,4},{0x34,4},{0x38,0x168-0x38}}
-- A shot in ring slot k fired by entity e: BeamFire's copies of BeamInfo row 6 (or `copies`), alive, not applied.
local function shoot(k,e,opts)
 opts=opts or{}
 shot_serial=shot_serial+1
 local at=RING+k*0x168
 local entry=b.encode(shot_serial,'f32')..string.rep('\0',0x168-4)
 local function put(off,bytes)entry=entry:sub(1,off)..bytes..entry:sub(off+#bytes+1)end
 put(0x18,b.encode(6,'u32'))
 put(0x1C,opts.copies or ROW6B:sub(0x10+1,0x28))
 put(0x34,ROW6B:sub(0xC+1,0x10))
 put(0x54,b.encode(e,'u32'));put(0x68,b.encode(e,'u32'))
 put(0x110,'\1');put(0x160,'\1');put(0x161,opts.applied and'\1'or'\0')
 if opts.rays then put(0x154,b.encode(opts.rays,'u32'))end
 -- Overlay pieces that never overlap the module's 4-byte writes (the overlay merges overlapping pieces unordered).
 for _,cut in ipairs(CUTS)do overlay[at+cut[1]]=entry:sub(cut[1]+1,cut[1]+cut[2])end
 return at
end
local function clear(k)for _,cut in ipairs(CUTS)do overlay[RING+k*0x168+cut[1]]=nil end end
local function f(at)return b.value(runtime.read(at,4),0,'f32')end
local function u(at)return b.u32(runtime.read(at,4),0)end
local function shot(at)return{dn=f(at+0x24),df=f(at+0x28),pn=f(at+0x2C),pf=f(at+0x30),id=u(at+0x34)}end
-- Every byte of the ring that differs from `ref` outside the listed (slot, field) pairs.
local function stray(ref,allowed)
 local now=runtime.read(RING,64*0x168)
 local out={}
 for i=1,#now do
  if now:byte(i)~=ref:byte(i)then
   local k=math.floor((i-1)/0x168);local off=(i-1)%0x168
   local ok=false
   for _,a in ipairs(allowed)do if a[1]==k and off>=a[2]and off<a[2]+a[3]then ok=true end end
   if not ok then out[#out+1]=('slot %d +0x%X'):format(k,off)end
  end
 end
 return out
end
local function tick(n)for _=1,n or 1 do BD.step(1/60)end end
'''


class BeamDamageResearchTests(unittest.TestCase):
    def test_the_research_verdicts(self):
        r = RESEARCH
        self.assertEqual((r['writes'], r['protectionChanges']), (0, 0))
        self.assertEqual(len(r['pinnedBytesMismatchPerSnapshot']), 9)
        self.assertFalse(any(r['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(sum(len(v) for v in r['proofs'].values()), 117)
        # The world update: submit (0xAB55AF) -> fire (0xAB5EC9) -> process (0xAB5FCB); never submit after fire.
        self.assertTrue(r['order']['fireReachesHitProcessing'])
        self.assertFalse(r['order']['fireReachesRaySubmission'])
        self.assertEqual(r['soleCallers']['0x13BAE20'], ['0x13F7654'])
        self.assertEqual(r['soleCallers']['0x13F73F0'], ['0xAB55AF'])
        # The shot's copies: written only by BeamFire, read only by the hit processing.
        writers = sorted(a['rva'] for a in r['entryCensus']['accesses'] if a['write'])
        self.assertEqual(writers, ['0x13B96C2', '0x13B96DA', '0x13B96E2', '0x13B96EA', '0x13B96F2'])
        # Both id tables are full (slot 0 is the default): no Runtime-owned id can exist without a code change.
        for o in r['observations']:
            self.assertEqual((o['beamTableNullSlots'], o['damageTableNullSlots']), ([0], [0]))
            self.assertTrue(o['afterDamageTableIsDefaultRow'])
        self.assertEqual(r['typedReferences']['tridentBeamTypeReferences'],
                         ['component BeamWeaponComponentData record 18 0'])
        self.assertEqual(r['typedReferences']['tridentDamageReferences'], ['settings beam row 26 (type 6) 12'])
        row6 = r['observations'][0]['tridentBeamRow']
        self.assertEqual((row6['damageInfo'], row6['falloff'], row6['damageMultipliers'],
                          row6['penetrationMultipliers'], row6['pulseFlag']), (508, [0.0, 0.0], [1.0, 1.0], [1.0, 1.0], 1))

    def test_the_domain_section_is_the_research(self):
        self.assertEqual(generate_beam_swap.generate(check=True), [])
        g = generate_beam_swap.build()['damage']
        self.assertEqual(g['entry']['damageInfo'], 0x34)
        self.assertEqual((g['entry']['damageNear'], g['entry']['penetrationFar'], g['entry']['weaponEntity']),
                         (0x24, 0x30, 0x54))
        self.assertEqual(g['ring'], {'base': 0x170, 'stride': 0x168, 'slots': 64, 'read': 0x168, 'write': 0x16C})
        self.assertEqual([d['label'] for d in g['donors']], ['LAS-13 Trident', 'LAS-5 Scythe'])
        self.assertEqual((g['donors'][0]['damageInfo'], g['donors'][0]['standard'], g['donors'][0]['durable'],
                          g['donors'][0]['armorPenetration']), (508, 60, 6, [2, 2, 2, 0]))
        self.assertEqual(g['donors'][1]['damageInfo'], 501)
        self.assertEqual(len(g['pins']), 118)

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
    def test_every_damage_pin_is_the_game_image_bytes(self):
        from scan import xref
        _, data, sha = xref.load_image('game.dll')
        g = generate_beam_swap.build()['damage']
        self.assertEqual(sha, g['source']['gameDllSha256'])
        for pin in g['pins']:
            expected = bytes.fromhex(pin['hex'])
            self.assertEqual(data[pin['rva']:pin['rva'] + len(expected)], expected, hex(pin['rva']))


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class BeamDamageSnapshotTests(unittest.TestCase):
    def test_each_weapon_gets_its_own_damage_and_nothing_else_changes(self):
        result = snapshot_run(LOCATE + SHOTS + r'''
-- Not swapped yet: refused.
local early=BD.set('liberator',{damage_multiplier=10})
check(not early.ok and early.reason:find('not swapped',1,true),'set before the swap: '..tostring(early.reason))
check(X.apply().ok,'apply')
local REC23=hexat(RECORD,120)
check(BD.set('liberator',{damage_multiplier=10}).ok,'liberator')
check(BD.set('reprimand',{armor_penetration=6}).ok,'reprimand')
-- One shot of each swapped weapon and one of the real Trident.
local lib=shoot(0,7001)
local tal=shoot(1,7002)
local rep=shoot(2,7003)
local tri=shoot(3,7004)
local before=runtime.read(RING,64*0x168)
local w0=counts.writes
tick()
local L,T,R,Tr=shot(lib),shot(tal),shot(rep),shot(tri)
check(L.dn==10 and L.df==10 and L.pn==1 and L.pf==1 and L.id==508,'liberator shot '..json.encode(L))
check(T.dn==1 and T.df==1 and T.pn==1 and T.pf==1 and T.id==508,'talon shot changed '..json.encode(T))
check(R.dn==1 and R.df==1 and R.pn==3 and R.pf==3 and R.id==508,'reprimand shot '..json.encode(R))
check(Tr.dn==1 and Tr.pn==1 and Tr.id==508,'the Trident\'s shot changed')
local s1=stray(before,{{0,0x24,8},{2,0x2C,8}})
check(#s1==0,'bytes outside the targets changed: '..table.concat(s1,', '))
local first=counts.writes-w0
-- Written once: another update leaves them.
local w1=counts.writes
tick(3)
check(counts.writes==w1,'a second update wrote')
-- Independence: the Talon now gets its own; only its next shot changes, the others keep theirs.
check(BD.set('talon',{damage=6}).ok,'talon')
local tal2=shoot(4,7002)
local lib2=shoot(5,7001)
local before2=runtime.read(RING,64*0x168)
tick()
local T2,L2=shot(tal2),shot(lib2)
check(math.abs(T2.dn-0.1)<1e-6 and T2.pn==1,'talon shot 2 '..json.encode(T2))
check(L2.dn==10,'liberator shot 2 '..json.encode(L2))
local s2=stray(before2,{{4,0x24,8},{5,0x24,8}})
check(#s2==0,'bytes outside the targets changed: '..table.concat(s2,', '))
-- No row, no record changed: BeamInfo 6, DamageInfo 508, record 23 (the swap's copy).
check(runtime.read(ROW6,0x70)==ROW6B and runtime.read(DMG508,0x4C)==DMG508B and hexat(RECORD,120)==REC23,
 'a row or the record changed')
check(next(protection)==nil,'a page protection was left changed')
local st=BD.status()
local summary={}
for _,w in ipairs(st.weapons)do summary[w.id]={active=w.active,shots=w.shots,written=w.written,
 before_rays=w.before_rays}end
-- Restore forgets every weapon's damage.
for k=0,5 do clear(k)end
check(X.restore().ok,'restore')
local after=BD.status()
local forgotten=true
for _,w in ipairs(after.weapons)do forgotten=forgotten and not w.active end
local logged={}
for _,line in ipairs(LINES)do if line:find('^MULTI BEAM DAMAGE:')then logged[#logged+1]=line end end
return json.encode({first=first,summary=summary,forgotten=forgotten,logged=logged})
''')
        self.assertEqual(result['first'], 4)        # 2 floats for the Liberator, 2 for the Reprimand
        self.assertEqual(result['summary']['liberator'], {'active': True, 'shots': 2, 'written': 2, 'before_rays': 2})
        self.assertEqual(result['summary']['reprimand'], {'active': True, 'shots': 1, 'written': 1, 'before_rays': 1})
        self.assertEqual(result['summary']['talon'], {'active': True, 'shots': 1, 'written': 1, 'before_rays': 1})
        self.assertTrue(result['forgotten'])
        logged = ' | '.join(result['logged'])
        self.assertIn('AR-23 Liberator: first shot written (ring slot 0, before its first ray query): DamageInfo 508: '
                      '600 / 60 damage (x10), AP 2/2/2/0 (x1)', logged)
        self.assertIn('SMG-32 Reprimand: first shot written (ring slot 2, before its first ray query): DamageInfo 508: '
                      '60 / 6 damage (x1), AP 6/6/6/0 (x3)', logged)
        self.assertIn('its swap was restored', logged)

    def test_a_damage_row_and_every_guard(self):
        result = snapshot_run(LOCATE + SHOTS + r'''
check(X.apply({'liberator','talon'}).ok,'apply')
-- A damage row needs its weapon's package: refused while it is not resident.
hk.assets='absent'
local r0=BD.set('liberator',{damage_row='LAS-5 Scythe'})
check(not r0.ok and r0.reason:find('package',1,true),'package gate: '..tostring(r0.reason))
hk.assets=nil
check(BD.set('liberator',{damage_row='LAS-5 Scythe',armor_penetration=4}).ok,'scythe row')
-- Validation.
check(not BD.set('talon',{damage=10,damage_multiplier=2}).ok,'exclusive damage settings accepted')
check(not BD.set('talon',{armor_penetration=2.5}).ok,'a fractional AP accepted')
check(not BD.set('talon',{damage_multiplier=1000}).ok,'an out-of-range multiplier accepted')
check(not BD.set('talon',{damage_row='LAS-7 Dagger'}).ok,'an unknown damage row accepted')
check(not BD.set('reprimand',{damage_multiplier=2}).ok,'a weapon that is not swapped accepted')
check(BD.set('talon',{damage_multiplier=2}).ok,'talon')
local a=shoot(0,7001)
tick()
local A=shot(a)
check(A.id==501 and A.dn==1 and A.pn==2,'scythe row shot '..json.encode(A))
-- Guards: each shot stays as fired.
local missed=shoot(1,7002,{applied=true})                                -- already hit
local odd=shoot(2,7002,{copies=b.encode(2,'f32')..ROW6B:sub(0x14+1,0x28)})  -- copies not the row's (offset +0x1C)
local before=runtime.read(RING,64*0x168)
tick()
check(f(missed+0x24)==1 and u(missed+0x161)%256==1,'an applied shot was written')
check(#stray(before,{})==0,'a guarded shot was written')
hk.players=2
local solo=shoot(3,7002)
tick()
check(f(solo+0x24)==1,'a shot was written with two players')
hk.players=1
-- After a ray query without a hit (still not applied): written.
local late=shoot(4,7002,{rays=77})
tick()
check(f(late+0x24)==2,'a not-yet-applied shot after a ray query was not written')
-- Not in a mission: nothing written.
hk.mission=false
tick()
local idle=shoot(5,7002)
BD.step(1)
check(f(idle+0x24)==1,'written outside a mission')
hk.mission=true
-- A pin differs: unavailable, nothing written.
BD.reset_for_tests()
BD.set_hooks_for_tests({entity_type=function(_,e)return TYPES[e]end,players=function()return 1 end,
 game_state=function()return{mission=true}end,assets=function()return'resident'end})
check(BD.set('talon',{damage_multiplier=2}).ok,'talon again')
local pin=G.pins[1]
overlay[game+pin.rva]=string.rep('\144',#pin.hex/2)
local blocked=shoot(6,7002)
tick()
check(f(blocked+0x24)==1,'written with a changed pin')
overlay[game+pin.rva]=nil
local st=BD.status()
local refused
for _,w in ipairs(st.weapons)do if w.id=='talon'then refused=w.refused end end
local logged={}
for _,line in ipairs(LINES)do if line:find('^MULTI BEAM DAMAGE:')then logged[#logged+1]=line end end
return json.encode({logged=logged,unavailable=st.unavailable})
''')
        logged = ' | '.join(result['logged'])
        self.assertIn('first shot written (ring slot 0, before its first ray query): DamageInfo 501: 350 / 70 damage '
                      '(x1), AP 4/4/4/0 (x2)', logged)
        self.assertIn('MISSED: the pulse had already hit', logged)
        self.assertIn('UNEXPECTED_STATE: its damage copies differ from BeamInfo row 6', logged)
        self.assertIn('NOT_SOLO: 2 players', logged)
        self.assertIn('after a ray query without a hit', logged)
        self.assertIn('native code not as reviewed', result['unavailable'])
        self.assertIn('REFUSED: the LAS-5 Scythe\'s package (laser_rifle) is absent', logged)


if __name__ == '__main__':
    unittest.main()
