"""runtime/pelican_weapon.lua and proof/PelicanWeaponBehaviorProof 0.1.0 (docs/research/pelican-cas-F5FEE03DCFDB.md section
17): one Runtime Pelican's own chin turret with its own weapon record (projectile, RPM), continuous fire (its fire window
held open on each stage-3 entry) and optionally the Gatling ammo pattern (its own magazine record), on the offline Pelican
world of tests/test_pelicans.py with the turret fixture of tests/test_pelican_gatling.py. The game's routines are
simulated; the guards, the guarded writes and the read-back are the Runtime's own."""
import json
import unittest

from support import ROOT, run, lua as lua_literal
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_readonly_probes import addon, HARNESS

WEAPON = r"""
local weapon=require('hd2runtime/runtime/pelican_weapon')
weapon.reset()
local MC,B6=GD.magazineCopy,GD.behaviour645
W.write(W.GAME+MC.rva,b.unhex(MC.prologue))
-- The magazine manager's copies: capacity 128, none yet; the game's copy routine simulated.
local MGCOPIES=W.alloc(0x1000);W.write(MGCOMP+MC.records,W.u64(MGCOPIES))
W.write(MGCOMP+MC.capacity,W.u32(128));W.write(MGCOMP+MC.count,W.u32(0))
local mckey=map(MGCOMP,mapof(MC.map))
local MAGTAB=b.pointer(W.read(CW+GD.magazineTypes.offset,8),0)
W.runtime.native_magazine_copy=function(entry,manager_,handle)
    GX.calls[#GX.calls+1]={'magazine_copy',entry,manager_,handle}
    local entity=b.u32(W.read(handle+8,4),0)
    mckey(entity,0)
    W.write(MGCOPIES,W.read(MAGTAB+GD.magazineTypes.records,MC.stride))   -- the chin turret's type record (index 0)
    W.write(MGCOMP+MC.count,W.u32(1))
    return true
end
-- The chin turret's fire control: its Behavior record (index 1) stage and fire-window start (P+0x180).
local function fire(stage_,start_us)
    stage(1,stage_,0)
    if start_us then W.write(record(1)+P+B6.fireStart,W.u64(start_us))end
end
local function fire_start()local raw=W.read(record(1)+P+B6.fireStart,8);return b.u32(raw,0)+b.u32(raw,4)*4294967296 end
local function n(text)local k=0;for _,line in ipairs(logged)do if line:find(text,1,true)then k=k+1 end end;return k end
"""


class PelicanWeaponTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + body
            + '\nend)()\n'), b'ok')

    def test_the_research(self):
        research = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        pinned = {p['rva'] for p in research['pins']['pelicanWeapon']}
        # The 0.5 s fire window and 1.5 s re-aim of behaviour 645, the trigger, the Gatling's held trigger, the magazine
        # copy routine and the record the game derives.
        self.assertTrue({0x478E10, 0x478E1E, 0x450806, 0x450C41, 0x450C62, 0x450B0E, 0x2846E6, 0x285869, 0x57417F,
            0x770CBD, 0x76D943, 0x76DA2E} <= pinned)
        g = research['gatling']
        self.assertEqual((g['behaviour645']['fireWindow'], g['behaviour645']['aimMinimum']), (500000, 1500000))
        self.assertEqual((g['magazineCopy']['rva'], g['magazineCopy']['stride']), (0x770B10, 160))

    def test_the_casing_first_shot_rate_and_ammunition_research(self):
        research = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        pins = research['pins']
        # The casing: the fire effects read the RESOLVED ProjectileWeapon (copy or type), +0xB0 at the ejector nodes,
        # the pooled effect kept in the instance record +0x90 from the first shot.
        self.assertTrue({0x6122CC, 0x61244A, 0x6124AF, 0x61248E, 0x6124BA, 0x6124BF, 0x13024DD, 0x612A13, 0x6151F8,
            0x612120, 0x612167} <= {p['rva'] for p in pins['casing']})
        # The first shot: the round chambered before the copy; the rate a new weapon starts with; the rounds and capacity.
        self.assertTrue({0x6149EC, 0x7447D4, 0x74480B, 0x74481C} <= {p['rva'] for p in pins['firstShot']})
        self.assertTrue({0x611C20, 0x611C4C} <= {p['rva'] for p in pins['rateSeed']})
        self.assertTrue({0x742A9B, 0x74353E, 0x4F3794, 0x76E34B, 0x745CE2, 0x774D1B} <= {p['rva'] for p in pins['ammo']})
        c = research['casing']
        self.assertEqual((c['particles'], c['nodes'], c['parameters'], c['instanceCasing']), (0xB0, 0xB8, 0xD4, 0x90))
        self.assertEqual(c['observed']['gatlingSentry']['particles'], 'F6F679E12742E627')
        self.assertEqual(c['observed']['chinTurret']['particles'], 'ACB12C0D0900FB34')
        self.assertEqual(c['ejectorNode'], '789B7D63')
        self.assertTrue(all(c['gatlingPackageLists'].values()))
        a = research['ammo']['observed']
        self.assertEqual((a['gatlingSentry']['capacity'], a['gatlingSentry']['spareMagazines'],
            a['gatlingSentry']['reloadAnimation']), (500, 0, None))
        self.assertEqual((a['chinTurret']['capacity'], a['chinTurret']['reloadAnimation']), (500, 0))

    def test_the_development_modules_run_interpreted_and_the_jit_stays_on(self):
        # The game's LuaJIT 2.1.0-alpha lost the last fields of a sunk table at a trace exit
        # (tests/test_pelican_gatling_proof.py failed with the JIT on); these modules opt out, nothing else does.
        for name in ('runtime/pelican_weapon.lua', 'runtime/pelican_gatling.lua'):
            self.assertIn("if rawget(_G,'jit')then jit.off(true,true)end", (ROOT / name).read_text(encoding='utf-8'))
        self.check(r"""
require('hd2runtime/runtime/pelican_gatling')
assert(jit.status()==true,'the JIT was turned off globally')
return 'ok'
""")

    def test_the_adapter_is_narrow(self):
        source = (ROOT / 'runtime/windows_write.lua').read_text(encoding='utf-8')
        self.assertIn('function runtime.native_magazine_copy(', source)
        for path in (ROOT / 'api').glob('*.lua'):
            self.assertNotIn('pelican_weapon', path.read_text(encoding='utf-8'), path.name)

    def test_configure_projectile_and_rate(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600},'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(r.turret==8102 and r.writes==2 and #W.runtime.writes==writes+2)
assert(#GX.calls==1 and GX.calls[1][1]=='copy'and GX.calls[1][4]==b.pointer(W.read(BHANDLES+8,8),0))
local w=pelicans.weapon_config(world,8102)
assert(w.copy.projectileType==148 and w.currentRpm==600 and not w.magazine.pattern)
-- Its type records are unchanged.
assert(b.u32(W.read(PWTAB+GD.pwTypes.records,4),0)==120)
-- Refusals: again (configured), outside the update, an invalid rate.
assert(select(2,in_update(function()return weapon.configure(world,9501,{rpm=600},'test')end))=='ALREADY_CONFIGURED')
assert(select(2,weapon.configure(world,9501,{rpm=600},'test'))=='NOT_GAME_THREAD')
assert(select(2,in_update(function()return weapon.configure(world,9501,{rpm=5},'test')end))=='INVALID')
return 'ok'
""")

    def test_configure_with_the_gatling_pattern(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=1600,pattern=true},
    'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(r.writes==10,'writes '..tostring(r.writes))                     -- 2 weapon + mode + 5 entries + 2 record
assert(GX.calls[2][1]=='magazine_copy'and GX.calls[2][2]==W.GAME+MC.rva and GX.calls[2][3]==MGCOMP)
-- Its own magazine copy holds the pattern; its own record the mode and length; its type record is unchanged.
local copy=W.read(MGCOPIES,0x18)
assert(b.u32(copy,0)==1 and b.u32(copy,4)==148 and b.u32(copy,16)==242 and b.u32(copy,20)==148)
local w=pelicans.weapon_config(world,8102)
assert(w.magazine.pattern and w.magazine.length==5 and w.magazine.copy)
assert(b.u32(W.read(MAGTAB+GD.magazineTypes.records,4),0)==0)
return 'ok'
""")

    def test_the_gatling_rate_and_casing(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
-- The frozen configuration (pinned research), and the game's type records it is compared with (read-only diagnostics).
local F=weapon.FROZEN
assert(F.projectile==148 and F.rpm==1600 and F.chin.rpm==300 and F.magazine.capacity==500 and F.spread.x==10)
assert(weapon.hex(F.casing.particles)==CSD.observed.gatlingSentry.particles and b.u32(F.casing.parameters,0)==41)
local ref=weapon.reference(world)
assert(ref.projectile==F.projectile and ref.rpm==F.rpm and ref.chin.rpm==F.chin.rpm and ref.sentry==nil)
assert(ref.casing.particles==F.casing.particles and ref.casing.parameters==F.casing.parameters)
assert(weapon.hex(ref.casing.particles)==CSD.observed.gatlingSentry.particles)
assert(weapon.hex(ref.chin.casing.particles)==CSD.observed.chinTurret.particles)
local c=weapon.casing_state(world,8102,GD.chinTurretResource)
assert(c.from=='type'and c.cached==0 and weapon.hex(c.particles)==CSD.observed.chinTurret.particles)
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm='gatling',casing=true},
    'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
-- projectile, current RPM, rate slot, casing particles and two of its three parameters (the third is 0 in both): one
-- transaction.
assert(r.writes==6 and #W.runtime.writes==writes+6,'writes '..tostring(r.writes))
assert(r.spec.rpm==1600 and r.rpm_source:find('frozen Gatling rate 1600',1,true)and r.casing.applied
    and r.verify.rate_slot)
local copy=W.read(PCOPIES,PW.copyStride)
assert(b.u32(copy,0)==148 and b.value(copy,8,'f32')==1600)
assert(weapon.hex(copy:sub(CSD.particles+1,CSD.particles+8))==CSD.observed.gatlingSentry.particles)
assert(b.u32(copy,CSD.parameters)==41 and b.u32(copy,CSD.parameters+4)==0 and b.u32(copy,CSD.parameters+8)==0)
-- Its nodes stay the chin turret's (the same "ejector"); its own casing state reads the copy, nothing kept yet.
assert(b.u32(copy,CSD.nodes)==b.u32(b.unhex(CSD.ejectorNode):reverse(),0))
c=weapon.casing_state(world,8102,GD.chinTurretResource)
assert(c.from=='copy'and c.cached==0 and weapon.hex(c.particles)==CSD.observed.gatlingSentry.particles)
-- The type records are unchanged (the whole records compared).
assert(r.verify.shared and b.u32(W.read(PWTAB+GD.pwTypes.records+CSD.parameters,4),0)==42)
return 'ok'
""")

    def test_the_casing_waits_for_no_shot_and_the_rate_follows_the_game(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
-- It has fired: its casing effect is kept (instance +0x90). The casing is not applied; the rest is.
W.write(PINST+CSD.instanceCasing,W.u32(77))
-- The mission fire-rate modifier was active when it was made: 0.9 x its type's 300.
W.write(PCUR+PW.currentRpm,f32(270))
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm='gatling',casing=true},
    'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(not r.casing.applied and r.casing.reason:find('fired',1,true)and r.writes==3,tostring(r.writes))
assert(r.spec.rpm==b.value(b.encode(1600*PE.rateSeed.factor,'f32'),0,'f32'))
assert(weapon.hex(W.read(PCOPIES+CSD.particles,8))==CSD.observed.chinTurret.particles)
assert(n('CASING NOT APPLIED (test): chin turret 8102: it has fired already')==1)
return 'ok'
""")

    def test_a_rate_the_game_does_not_give_is_refused(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
W.write(PCUR+PW.currentRpm,f32(450))                           -- 1.5 x: no rate the game gives
assert(select(2,in_update(function()return weapon.configure(world,9501,{rpm='gatling'},'test')end))=='RATE_UNEXPECTED')
assert(#GX.calls==0)
return 'ok'
""")

    def test_a_deployed_custom_sentry_is_never_the_pelicans_reference(self):
        # The live regression (2026-10-04): a Pelican called after the custom HMG Sentry was refused, RATE_UNEXPECTED
        # ("the deployed Gatling Sentry ... runs 540.00 RPM, not 1440.00"). The configuration is frozen: a deployed
        # sentry of the Gatling's type with its own private changes (round 275, 540 RPM), and even the Gatling Sentry's
        # TYPE records changed by another mod, change nothing in what the Pelican's chin gun receives, and nothing of
        # theirs is written.
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
-- The custom sentry: the Gatling's type, behaviour 213, its OWN rate 540 and its own round 275.
transport(5,9701,{resource=GAT,behaviour=213});stage(5,2,0)
W.write(b.pointer(W.read(BHANDLES+5*8,8),0),GAT..W.u32(9701)..W.u32(0x400100)..W.u32(0x7fff))
weapon_entity(9701,1,{resource=GAT,rpm=540,pattern=false,chambered=275})
-- Another mod changed the Gatling Sentry's type: 999 RPM, another casing.
local gat_type=PWTAB+GD.pwTypes.records+PW.copyStride
W.write(gat_type+8,f32(999));W.write(gat_type+CSD.particles,W.u32(0x11111111)..W.u32(0x22222222))
local sentry_before=pelicans.weapon_config(world,9701)
local gat_before=W.read(gat_type,PW.copyStride)
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=275,rpm='gatling',
    rate_factor=2,casing=true},'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
-- Exactly the frozen configuration: 1600 x its own factor (1) x 2 in the copy's rate slot and its current RPM, the
-- frozen Gatling casing.
assert(r.spec.rpm==3200 and r.rpm_source:find('frozen Gatling rate 1600',1,true)and not r.rpm_source:find('deployed',1,true))
local copy=W.read(PCOPIES,PW.copyStride)
assert(b.u32(copy,0)==275 and b.value(copy,8,'f32')==3200)
assert(weapon.hex(copy:sub(CSD.particles+1,CSD.particles+8))==CSD.observed.gatlingSentry.particles)
-- Nothing of the sentry's, nothing of the Gatling's type: every write was the chin turret's own.
local sentry_after=pelicans.weapon_config(world,9701)
assert(sentry_after.currentRpm==540 and sentry_after.currentRpm==sentry_before.currentRpm)
assert(W.read(gat_type,PW.copyStride)==gat_before)
for k=writes+1,#W.runtime.writes do
    local a=W.runtime.writes[k].address
    assert(not(a>=gat_type and a<gat_type+PW.copyStride),'a write to the Gatling type record')
end
assert(n('deployed Gatling')==0)
return 'ok'
""")

    def test_the_safe_maximum_ammunition_and_the_refill(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
-- As the game spawned it: 499 rounds and one chambered (its type's 500), 6 spare magazines.
local a0=weapon.ammo_state(world,8102)
assert(a0.rounds==499 and a0.working==499 and a0.chambered==120 and a0.capacity==500 and a0.from=='type'and a0.spares==6)
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,ammo=true},'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
-- The safe maximum, the rounds' 11-bit network field (2047), as its own magazine's capacity and both round counts (a
-- round chambered), one magazine transaction after the game's magazine copy routine.
assert(weapon.AMMO_MAX==2047 and r.ammo.applied and r.ammo.reference==500 and r.ammo.capacity==2047 and r.ammo.rounds==2047)
assert(r.writes==5 and #W.runtime.writes==writes+5,'writes '..tostring(r.writes))
assert(GX.calls[2][1]=='magazine_copy'and GX.calls[2][2]==W.GAME+MC.rva and GX.calls[2][3]==MGCOMP)
local a=weapon.ammo_state(world,8102)
assert(a.from=='copy'and a.capacity==2047 and a.rounds==2047 and a.working==2047 and a.chambered==120 and a.spares==6)
-- The refill: nothing above 1500; below it, both counts back to 2047 (the working count first), once per 2 s.
local function rounds(nr)W.write(MGENTS+AMD.entryRounds,W.u32(nr));W.write(MGRECS+MG.rounds,W.u32(nr))end
rounds(1600)
assert(in_update(function()return weapon.refill_step(world,8102,'test')end)==nil)
rounds(1499)
local w0=#W.runtime.writes
local e=in_update(function()return weapon.refill_step(world,8102,'test')end)
assert(e and e.kind=='refilled'and e.old==1499 and e.new==2047 and #W.runtime.writes==w0+2,tostring(e and e.kind))
assert(W.runtime.writes[w0+1].address==MGRECS+MG.rounds and W.runtime.writes[w0+2].address==MGENTS+AMD.entryRounds,
    'the working count first')
a=weapon.ammo_state(world,8102)
assert(a.rounds==2047 and a.working==2047 and a.chambered==120 and a.capacity==2047 and a.spares==6)
assert(n('PELICAN WEAPON AMMO REFILL (test): chin turret 8102: 1499 -> 2047')==1)
rounds(1000)
assert(in_update(function()return weapon.refill_step(world,8102,'test')end)==nil)          -- within 2 s
BOMB.set_clock(T0+3000000)
W.write(MGRECS+MG.chambered,W.u32(0))                                                    -- dry: left to the game
e=in_update(function()return weapon.refill_step(world,8102,'test')end)
assert(e and e.kind=='refused'and e.code=='DRY'and weapon.ammo_state(world,8102).rounds==1000)
-- Both type records keep 500.
assert(b.u32(W.read(MAGTAB+GD.magazineTypes.records+AMD.capacity,4),0)==500)
assert(b.u32(W.read(MAGTAB+GD.magazineTypes.records+GD.magazineTypes.stride+AMD.capacity,4),0)==500)
assert(r.verify.shared)
return 'ok'
""")

    def test_the_ammunition_needs_a_chambered_round_and_the_hosts_turret(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
W.write(MGRECS+MG.chambered,W.u32(0))                          -- no round chambered
local r=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,ammo=true},'test')end)
assert(r and r.verified and not r.ammo.applied and r.ammo.reason=='no round is chambered'and r.writes==2)
assert(#GX.calls==1 and n('AMMO NOT APPLIED (test): chin turret 8102: no round is chambered')==1)
return 'ok'
""")
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
W.write(b.pointer(W.read(BHANDLES+8,8),0)+0x14,W.u32(0))       -- not created here
local r=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,ammo=true,pattern=true},'test')end)
assert(r and r.verified and not r.ammo.applied and r.ammo.reason:find('not the host',1,true))
-- The pattern still goes through its own magazine copy: 2 weapon + 8 pattern writes.
assert(r.writes==10 and r.verify.pattern)
return 'ok'
""")

    def test_the_gatling_aim_recoil_and_the_aim_diagnostic(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,recoil=true},'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
-- Its own aim recoil (block B): 2.5 sideways and 10 up a shot -> the Gatling Sentry's 0 and 3; only those two floats
-- change; both type records whole.
assert(r.recoil.applied and r.recoil.before.x==2.5 and r.recoil.before.y==10 and r.recoil.after.x==0 and r.recoil.after.y==3)
assert(r.writes==4 and r.verify.shared,tostring(r.writes))
assert(n('PELICAN WEAPON RECOIL (test): chin turret 8102: its own aim recoil (WeaponData block B) 2.5, 10 -> the '
    ..'frozen Gatling Sentry\'s 0, 3')==1)
-- The aim diagnostic: T 30 m east of the muzzle; the turret points 1 m above it; the muzzle moves 8 m/s north.
local AW,AT,AL=AIMD.weaponData,AIMD.targeting,AIMD.wielder
W.write(TGRECS+AT.target,W.u32(5555));W.write(TGRECS+AT.point,f32(90)..f32(70)..f32(12))
W.write(WDRECS+AW.aim,f32(90)..f32(70)..f32(13))
W.write(WDRECS+AW.muzzle,f32(60)..f32(70)..f32(12));W.write(WDRECS+AW.muzzleVelocity,f32(0)..f32(8)..f32(0))
W.write(WLRECS+AL.recoil,f32(math.rad(0.9))..f32(0))
local st=weapon.aim_state(world,8102)
assert(st.target==5555 and st.point.x==90 and st.aim.z==13 and math.abs(st.recoil.x-0.9)<1e-4)
local e=weapon.aim_error(st,{x=90,y=70,z=11})
assert(math.abs(e.distance-30)<1e-4 and math.abs(e.vertical-1)<1e-4 and e.horizontal<1e-4)
assert(math.abs(e.lead-30*8/820)<1e-4 and math.abs(e.lead_vertical)<1e-6 and math.abs(e.node_height-1)<1e-6)
return 'ok'
""")

    def test_the_spread_modes(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local SPR=PE.spread
local function spread()local raw=W.read(WDRECS+SPR.instance,12);return b.value(raw,0,'f32'),b.value(raw,4,'f32'),b.u32(raw,8)end
-- Mild: halfway between its own 1 mrad and the frozen Gatling Sentry's 10; two fields change; nothing shared.
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,spread='mild'},'test')end)
assert(r and r.verified and r.spread.applied,tostring(code)..' '..tostring(reason))
local x,y,w=spread()
assert(x==5.5 and y==5.5 and w==0 and r.spread.before.x==1 and r.spread.gatling.x==10 and r.spread.writes==2
    and r.verify.shared,tostring(r.spread.writes))
assert(n('PELICAN WEAPON SPREAD (test): chin turret 8102: its own spread (WeaponData +0x58) 1, 1 mrad -> MILD: 5.5, 5.5 '
    ..'mrad (the frozen Gatling Sentry\'s 10, 10); distribution word 0 -> 0; 2 writes; read back true')==1)
-- No longer its type's (5.5 already): refused, nothing written; outside the update: refused.
local w0=#W.runtime.writes
local s=in_update(function()return weapon.configure_spread(world,8102,'test','gatling')end)
assert(not s.applied and s.reason=='its spread is not its type\'s'and #W.runtime.writes==w0,tostring(s.reason))
assert(weapon.configure_spread(world,8102,'test','gatling').reason:find('NOT_GAME_THREAD',1,true))
-- Its type's again: Gatling exactly; Precise writes nothing.
W.write(WDRECS+SPR.instance,f32(1)..f32(1))
s=in_update(function()return weapon.configure_spread(world,8102,'test','gatling')end)
x,y=spread()
assert(s.applied and x==10 and y==10 and s.writes==2)
W.write(WDRECS+SPR.instance,f32(1)..f32(1))
w0=#W.runtime.writes
s=in_update(function()return weapon.configure_spread(world,8102,'test','precise')end)
assert(s.applied and s.writes==0 and #W.runtime.writes==w0 and spread()==1)
-- Its own multipliers count (a customised weapon's spread is its type's times them).
W.write(WDRECS+SPR.multipliers[1],f32(2));W.write(WDRECS+SPR.instance,f32(2)..f32(1))
s=in_update(function()return weapon.configure_spread(world,8102,'test','mild')end)
x,y=spread()
assert(s.applied and x==6 and y==5.5,tostring(x))
return 'ok'
""")

    def test_tuning_widths_and_the_rate_factor(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local SPR=PE.spread
-- 2x the Gatling rate read from the game: its own current RPM and its copy's rate slot both 3200; 50 mrad both ways.
local function cfg(spec)return in_update(function()return weapon.configure(world,9501,spec,'test')end)end
assert(select(2,cfg({projectile=148,rpm='gatling',rate_factor=3}))=='INVALID')
assert(select(2,cfg({projectile=148,rpm=600,rate_factor=2}))=='INVALID')
local r,code,reason=cfg({projectile=148,rpm='gatling',rate_factor=2,spread=50})
assert(r and r.verified and r.verify.rate_slot and r.spread.applied,tostring(code)..' '..tostring(reason))
local w=pelicans.weapon_config(world,8102)
assert(w.currentRpm==3200 and r.spec.rpm==3200 and r.spec.rate_factor==2 and r.rpm_source:find('x 2 (the tuning)',1,true),
    tostring(w.currentRpm))
local raw=W.read(WDRECS+SPR.instance,12)
assert(b.value(raw,0,'f32')==50 and b.value(raw,4,'f32')==50 and b.u32(raw,8)==0 and r.spread.name=='50 mrad')
assert(n('-> 50 mrad: 50, 50 mrad')==1)
-- A width out of range is refused, nothing written.
W.write(WDRECS+SPR.instance,f32(1)..f32(1))
local w0=#W.runtime.writes
local s=in_update(function()return weapon.configure_spread(world,8102,'test',101)end)
assert(not s.applied and s.reason:find('INVALID',1,true)and #W.runtime.writes==w0)
return 'ok'
""")

    def test_the_ap4_round(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local function cfg(spec)return in_update(function()return weapon.configure(world,9501,spec,'test')end)end
-- The donor's row must read as the catalogued MG-206 round: refused otherwise, nothing written.
W.write(ROW275+0x3C,W.u32(206))
local w0=#W.runtime.writes
assert(select(2,cfg({projectile=275,rpm='gatling'}))=='DONOR_UNEXPECTED'and #W.runtime.writes==w0)
W.write(ROW275+0x3C,W.u32(205))
local row148,row275=W.read(ROW148,272),W.read(ROW275,272)
local r,code,reason=cfg({projectile=275,rpm='gatling',casing=true,ammo=true})
assert(r and r.verified and r.verify.rows and r.verify.shared,tostring(code)..' '..tostring(reason))
local w=pelicans.weapon_config(world,8102)
assert(w.copy.projectileType==275 and r.donor.projectile==275 and r.donor.damage==205 and r.donor.velocity==980
    and r.donor.mass==52 and r.donor.ap.apDirect==4)
-- Only its own copy names it: neither row was written.
assert(W.read(ROW148,272)==row148 and W.read(ROW275,272)==row275)
assert(weapon.AP4.standard.ap.apDirect==3 and weapon.AP4.assetKey=='support_weapon/MG-206 Heavy Machine Gun')
return 'ok'
""")

    def test_the_kill_credit(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local function cfg(spec)return in_update(function()return weapon.configure(world,9501,spec,'test')end)end
local function credit()return in_update(function()return weapon.configure_credit(world,8102,'test')end)end
local function mask()local raw=W.read(TAGVALS,8);return b.u32(raw,0),b.u32(raw,4)end
-- Its own Tag mask: the no-credit tag cleared, every other bit kept; one 8-byte write, read back.
local r,code,reason=cfg({projectile=275,rpm='gatling',credit=true})
local why={};for k,v in pairs(r and r.verify or{})do why[#why+1]=k..'='..tostring(v)end
assert(r and r.verified and r.credit.applied and r.verify.credit,tostring(code)..' '..tostring(reason)..' '
    ..tostring(r and r.credit and r.credit.reason)..' '..table.concat(why,','))
local lo,hi=mask()
assert(lo==0x02000004 and hi==0 and r.credit.writes==1 and r.credit.before.no_credit and not r.credit.after.no_credit
    and r.credit.after.wielder==8102 and r.credit.after.faction==1 and r.credit.after.network==701,tostring(lo))
assert(n('PELICAN WEAPON CREDIT (test): chin turret 8102: its own Tag mask 0x0000000012000004 -> 0x0000000002000004 (the '
    ..'no-credit tag 0x10000000 cleared, every other bit kept)')==1,'the log')
-- Nothing left to clear: no write.
local w0=#W.runtime.writes
local c=credit()
assert(c.applied and c.already and #W.runtime.writes==w0,'already')
-- Refused unless it wields itself, has faction bit 0 and a network id; outside the update.
tags(8102,0x12000004)
W.write(WIELDERS,W.u32(9501))
assert(tostring(credit().reason):find('WIELDER_UNEXPECTED',1,true),'wielder')
W.write(WIELDERS,W.u32(8102));faction(8102,2)
assert(tostring(credit().reason):find('FACTION_UNEXPECTED',1,true),'faction')
faction(8102,1)
local handle=b.pointer(W.read(BHANDLES+8,8),0)
W.write(handle+0x10,W.u32(0x7FFF))
assert(tostring(credit().reason):find('NO_NETWORK',1,true),'network '..tostring(credit().reason))
W.write(handle+0x10,W.u32(701))
assert(weapon.configure_credit(world,8102,'test').reason:find('NOT_GAME_THREAD',1,true))
assert(#W.runtime.writes==w0 and mask()==0x12000004,'unchanged')
-- A victim's last hit (its health record +0x30 owner, +0x38 creditor), read-only.
W.add{entity=5555,type='73F8498BFFDCF415',unit=7555,health=500}
local st=world_module.entity_state(world,5555)
W.write(st.header.records+st.index*440+0x30,W.u32(8102)..W.u32(0)..W.u32(0x11223344)..W.u32(0x55667788))
local h=weapon.last_hit(world,5555)
assert(h.owner==8102 and h.creditor_lo==0x11223344 and h.creditor_hi==0x55667788 and h.health==500)
return 'ok'
""")

    def test_hold_fire(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
assert(in_update(function()return weapon.configure(world,9501,{rpm=600},'test')end))
-- Aiming (stage 2): nothing to do.
fire(2,T0-1000000)
assert(in_update(function()return weapon.hold_fire(world,8102,'test')end)=='idle')
-- It starts firing (stage 3, 0.1 s ago): its fire window is held 1 h ahead, one guarded write.
local writes=#W.runtime.writes
fire(3,T0-100000)
assert(in_update(function()return weapon.hold_fire(world,8102,'test')end)=='held')
assert(fire_start()==T0+3600000000 and #W.runtime.writes==writes+1)
-- Held already: nothing more; still in stage 3 a minute later: nothing more.
assert(in_update(function()return weapon.hold_fire(world,8102,'test')end)=='idle')
BOMB.set_clock(T0+60000000)
assert(in_update(function()return weapon.hold_fire(world,8102,'test')end)=='idle'and #W.runtime.writes==writes+1)
-- Its AI left the stage and fires again later: held again.
fire(3,T0+60000000-200000)
assert(in_update(function()return weapon.hold_fire(world,8102,'test')end)=='held'and #W.runtime.writes==writes+2)
-- Outside the update: refused; an unconfigured entity: refused.
assert(select(2,weapon.hold_fire(world,8102,'test'))=='NOT_GAME_THREAD')
assert(select(2,in_update(function()return weapon.hold_fire(world,1234,'test')end))=='NOT_CONFIGURED')
return 'ok'
""")


class PelicanWeaponBehaviorProofTests(unittest.TestCase):
    def lua(self, body):
        resource, wrapped, _ = addon(ROOT / 'proof/PelicanWeaponBehaviorProof')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + '\n'
            + 'return (function()\n' + HARNESS + GATLING + WEAPON + body + '\nend)()\n'), b'ok')

    def test_the_source(self):
        _, _, body = addon(ROOT / 'proof/PelicanWeaponBehaviorProof')
        code = '\n'.join(line.split('--')[0] for line in body.splitlines())
        self.assertIn("local BUILD='0.1.0 CHIN TURRET CONTINUOUS-FIRE BUILD'", body)
        self.assertEqual((ROOT / 'proof/PelicanWeaponBehaviorProof/VERSION').read_text(encoding='utf-8').strip(), '0.1.0')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction',
                'native_', 'hd2.ensure', 'hd2.patch', 'pelican_gatling', 'pelicans.hold', 'pelicans.spawn'):
            self.assertNotIn(forbidden, code, forbidden)

    def test_the_proof_configures_holds_and_measures(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
scene()
fire(2,T0)
tick(60)
assert(n('assets for pelican-weapon requested: 1 package(s)')==1 and n('assets for pelican-weapon resident')==1,
    lines('assets for'))
assert(n('WEAPON SEEN (#1): Runtime Pelican 9501; projectile 148, 600 RPM, continuous on, pattern off')==1,lines('SEEN'))
assert(n('WEAPON RESULT (#1): applied on Pelican 9501: chin turret 8102: projectile 148, 600 RPM')==1,lines('RESULT'))
-- It starts firing: held; rounds go: measured.
local now=T0+8000000
BOMB.set_clock(now);fire(3,now-100000)
tick(8)
assert(n('PELICAN WEAPON HOLD (')==1 and fire_start()>now,lines('HOLD'))
W.write(MGRECS,W.u32(489)..W.u32(0)..W.u32(148)..W.u32(0))   -- 10 of its 499
tick(20)
assert(n('WEAPON FIRE (#1)')>=1 and n('firing stage YES')>=1,lines('WEAPON FIRE'))
-- The Pelican leaves: the summary.
drop_entity(9501);tick(8)
assert(n('WEAPON SUMMARY (#1): chin turret 8102 (projectile 148, 600 RPM, continuous on, pattern off): 10 rounds')==1,
    lines('SUMMARY'))
return 'ok'
""")

    def test_continuous_off_never_holds(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
local input=require('hd2runtime/runtime/input')
chord('F9')
""".replace("chord('F9')", "keys[0x11]=true;keys[input.keys['F9']]=true;tick();keys[input.keys['F9']]=false;keys[0x11]=false;tick()") + r"""
assert(n('Ctrl+F9 [0.1.0 CHIN TURRET CONTINUOUS-FIRE BUILD]: continuous fire OFF')==1,lines('Ctrl+F9'))
scene()
tick(60)
local now=T0+8000000
BOMB.set_clock(now);fire(3,now-100000)
tick(20)
assert(n('WEAPON SEEN (#1): Runtime Pelican 9501; projectile 148, 600 RPM, continuous off')==1,lines('SEEN'))
assert(n('PELICAN WEAPON HOLD')==0 and fire_start()==now-100000,lines('HOLD'))
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
