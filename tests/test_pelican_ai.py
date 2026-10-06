"""runtime/pelican_weapon.lua switch_ai and proof/PelicanGatlingAIProof 0.2.0 (docs/research/pelican-cas-F5FEE03DCFDB.md
section 18): one Runtime Pelican's own chin turret gets the Gatling Sentry's AI through the game's own SetBehaviour
(0x843EA0) with behaviour 213, while it is quiet (645 stage 1 or 4, nothing pending), on the offline Pelican world of
tests/test_pelicans.py with the turret fixture of tests/test_pelican_gatling.py. SetBehaviour is simulated as the
research found it (the id becomes 213 and the new behaviour enters its stage 1); the guards, the read-back and the
refusal are the Runtime's own."""
import json
import unittest

from support import ROOT, run, lua as lua_literal
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_weapon import WEAPON
from test_pelican_readonly_probes import addon, HARNESS

AI = r"""
local AI,SB=GD.ai,GD.setBehaviour
W.write(W.GAME+AI.table+4*644,b.unhex(AI.entry645));W.write(W.GAME+AI.table+4*212,b.unhex(AI.entry213))
W.write(W.GAME+SB.rva,b.unhex(SB.prologue))
local TS=PE.targetSet
-- The chin turret's Behavior record (index 1): at rest (nothing pending, no transition), a stage, a target; its
-- perceiver is itself.
local function ai(stage_,target_)
    stage(1,stage_,0)
    W.write(record(1)+AI.pending,W.u32(4294967295)..W.u32(4294967295))
    W.write(record(1)+AI.target,W.u32(target_ or 0))
    W.write(record(1)+TS.record.perceiver,W.u32(8102))
end
-- Its perception (research "targetSet"): the perceiver record of 8102 (one sensor, sense bit 3; faction mask 1); the
-- faction component (enemies: mask 2, hostile); the entity flags; list A entries, perceived or not.
W.write(W.GAME+TS.setter.rva,b.unhex(TS.setter.prologue))
local PRC=TS.perception
local PCOMP_,pckey=manager(PRC)
local PRECS=W.alloc(PRC.stride);W.write(PCOMP_+PRC.records,W.u64(PRECS))
pckey(8102,0)
W.write(PRECS+PRC.sensors,W.u32(1)..W.u32(8102)..W.u32(3))
W.write(PRECS+PRC.factionMask,W.u32(1))
-- (The faction and entity-flag (Tag) components are tests/test_pelican_gatling.py's: faction(), tags().)
local LA=PRC.lists[1]
-- An enemy in list A at (x, y, z), perceived (`seen`) or not; its faction mask (default 2: hostile to 1).
local function perceive(entity,x,y,z,seen,mask)
    local count=b.u32(W.read(PRECS+LA.count,4),0)
    local slot=count
    for i=0,count-1 do if b.u32(W.read(PRECS+LA.entries+i*PRC.entryStride,4),0)==entity then slot=i end end
    local at=PRECS+LA.entries+slot*PRC.entryStride
    W.write(at,W.u32(entity)..f32(x)..f32(y)..f32(z))
    W.write(at+PRC.entrySense,W.u32(seen==false and 0 or 8))
    if slot==count then
        W.write(PRECS+LA.count,W.u32(count+1))
        faction(entity,mask or 2)
    end
    return at
end
local function flag(entity,n)tags(entity,n<32 and 2^n or 0,n>=32 and 2^(n-32)or 0)end
-- The game's target setter, simulated as the research found it: the entry copied into P+0x10..0x5F, P+0x70 = 1, the
-- previous target P+0x68.
W.runtime.native_set_target=function(entry,handle,state,candidate)
    GX.calls[#GX.calls+1]={'set_target',entry,handle,state,candidate}
    if GX.set_target_ignored then return true end
    W.write(state+0x10,W.read(candidate,0x50));W.write(state+0x70,'\1');W.write(state+0x68,W.read(candidate,4))
    return true
end
local function behaviour_id()return b.u32(W.read(record(1),4),0)end
local function n(text)local k=0;for _,line in ipairs(logged)do if line:find(text,1,true)then k=k+1 end end;return k end
-- The game's SetBehaviour, simulated: the id becomes the new behaviour, which enters its own stage 1.
W.runtime.native_set_behaviour=function(entry,manager_,entity,behaviour)
    GX.calls[#GX.calls+1]={'set_behaviour',entry,manager_,entity,behaviour}
    if GX.set_ignored then return true end
    W.write(record(1),W.u32(behaviour));stage(1,1,0)
    return true
end
"""


# The no-target release: a switched chin turret (the AI changed while quiet), a step at a game clock.
RELEASE = r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
ai(4)
assert(in_update(function()return weapon.switch_ai(world,9501,'test')end))
local function pending()return b.value(W.read(record(1)+AI.pending,4),0,'i32')end
-- One controller step at a game clock: its events, and their kinds as a string.
local function step(t)BOMB.set_clock(t);return in_update(function()return weapon.target_step(world,8102,'test')end)end
local function kinds(list)local k={};for i,e in ipairs(list)do
    k[i]=e.kind..(e.kind=='released'and e.reason and(':'..e.reason)or'')end
    return table.concat(k,',')end
local AID=PE.ai213
local function repick()local raw=W.read(record(1)+AID.repick,8);return b.u32(raw,0)+b.u32(raw,4)*4294967296 end
-- Two enemies with health and a unit position, 30 m and 40 m from the turret.
W.add{entity=5555,type='73F8498BFFDCF415',unit=7555,health=500};W.unit(7555,90,70,12)
W.add{entity=6666,type='73F8498BFFDCF415',unit=7666,health=500};W.unit(7666,60,110,12)
"""


class PelicanAITests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + AI + body
            + '\nend)()\n'), b'ok')

    def test_the_research(self):
        research = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        pinned = {p['rva'] for p in research['pins']['pelicanAI']}
        # The behaviour id read every update; creation's pending stage 1; 645 stage 4 = the turret inactive; the game's
        # own SetBehaviour: exit through the old transition (stage 0), the id replicated, the new one's stage 1.
        self.assertTrue({0x8434C9, 0x472FAC, 0x842462, 0x478DC6, 0x6E0291, 0x450C27, 0x197D8D, 0x843F67, 0x843F7A,
            0x843F8A, 0x843FA2} <= pinned)
        g = research['gatling']
        self.assertEqual(g['setBehaviour']['rva'], 0x843EA0)
        self.assertEqual(g['ai']['stages645']['4'], 'turret inactive')

    def test_the_adapter_is_narrow(self):
        source = (ROOT / 'runtime/windows_write.lua').read_text(encoding='utf-8')
        self.assertIn('function runtime.native_set_behaviour(', source)
        self.assertIn("behaviour==213,'unsupported behaviour call'", source)

    def test_set_behaviour_from_stage_4(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
ai(4)                                                          -- the turret not active (the approach)
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.switch_ai(world,9501,'test')end)
assert(r and r.before==645 and r.after==213 and r.stage_after==1,tostring(code)..' '..tostring(reason))
local c=GX.calls[#GX.calls]
assert(c[1]=='set_behaviour'and c[2]==W.GAME+SB.rva and c[3]==BCOMP and c[4]==8102 and c[5]==213)
assert(behaviour_id()==213 and #W.runtime.writes==writes)       -- the game's routine wrote it, not the Runtime
assert(n('behaviour BEFORE = 645 (the field at +0x0')==1
    and n('behaviour BEFORE = 645, behaviour AFTER = 213 (read back from the field)')==1)
assert(select(2,in_update(function()return weapon.switch_ai(world,9501,'test')end))=='ALREADY_SWITCHED')
return 'ok'
""")

    def test_from_stage_1_and_not_while_aiming_or_firing(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
for _,s in ipairs({2,3})do
    ai(s)
    local r,code=in_update(function()return weapon.switch_ai(world,9501,'test')end)
    assert(r==nil and code=='NOT_QUIET'and #GX.calls==0 and behaviour_id()==645,tostring(code))
end
ai(1);W.write(record(1)+AI.pending,W.u32(3))                   -- a stage pending: not quiet
assert(select(2,in_update(function()return weapon.switch_ai(world,9501,'test')end))=='NOT_QUIET'and #GX.calls==0)
ai(1)
local r=in_update(function()return weapon.switch_ai(world,9501,'test')end)
assert(r and r.after==213 and behaviour_id()==213)
return 'ok'
""")

    def test_refusals_and_the_read_back(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
ai(4)
-- Outside the update; the routine's bytes changed; the jump table changed; not a Runtime Pelican.
assert(select(2,weapon.switch_ai(world,9501,'test'))=='NOT_GAME_THREAD')
W.write(W.GAME+SB.rva,'\204')
assert(select(2,in_update(function()return weapon.switch_ai(world,9501,'test')end))=='UNSUPPORTED_BUILD')
W.write(W.GAME+SB.rva,b.unhex(SB.prologue))
W.write(W.GAME+AI.table+4*212,'\0\0\0\0')
assert(select(2,in_update(function()return weapon.switch_ai(world,9501,'test')end))=='UNSUPPORTED_BUILD')
W.write(W.GAME+AI.table+4*212,b.unhex(AI.entry213))
assert(select(2,in_update(function()return weapon.switch_ai(world,8102,'test')end))=='NOT_RUNTIME_PELICAN')
assert(#GX.calls==0)
-- The routine is called but the field does not read 213 afterwards: a failure, reported as such.
GX.set_ignored=true
local r,code,reason=in_update(function()return weapon.switch_ai(world,9501,'test')end)
assert(r==nil and code=='NOT_APPLIED'and behaviour_id()==645,tostring(code))
assert(n('AI SWITCH FAILED (test): chin turret 8102: behaviour AFTER = 645 (read back), not the requested 213')==1)
return 'ok'
""")


class PelicanTargetControllerTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + AI + RELEASE
            + body + '\nend)()\n'), b'ok')

    def test_the_research(self):
        research = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        # Stage 12's two exits, the pending stage through 213's own transition, stage 5's 3 degrees; the re-pick timer.
        self.assertTrue({0x285704, 0x285722, 0x285739, 0x285746, 0x28574E, 0x285861, 0x285869, 0x8434B7, 0x4963B8,
            0x48FE62, 0x283E02, 0x28408D} <= {p['rva'] for p in research['pins']['ai213']})
        self.assertTrue({0x2846DF, 0x284798, 0x28479F, 0x2847CF, 0x284F82, 0x4AF41C, 0x4AF4A2}
            <= {p['rva'] for p in research['pins']['targetChoice']})
        a = research['ai213']
        self.assertEqual((a['pending'], a['releaseStage'], a['fireStage'], a['repick'], a['lastSeen']),
            (0xC, 4, 12, 0x98, 0x28))
        # The setter as the AI's own pick calls it, the update's context, the perceiver's lists, perceived, hostile,
        # the entity flags, the 100 m range.
        self.assertTrue({0x8431C7, 0x8431F6, 0x8431FB, 0x2847DD, 0x284A4D, 0x284B5B, 0x284F77, 0x284F82, 0x4AF4FA,
            0x4AF504, 0x4AF50A, 0x4AF53D, 0x4AF718, 0x4AF39F, 0x889954, 0x889976, 0x889995, 0x885A7A, 0x4B507A,
            0x8D5591, 0x8D559F, 0x4A979B} <= {p['rva'] for p in research['pins']['targetSet']})
        t = research['targetSet']
        self.assertEqual((t['setter']['rva'], t['context']['state'], t['record']['perceiver'], t['perception']['stride'],
            [x['count'] for x in t['perception']['lists']], t['range']), (0x4AF4E0, 8, 0x68, 0x13F8, [0x310, 0x818, 0xD20],
            100.0))
        self.assertTrue(any(v['listed'] for v in t['observed'].values()))

    def test_the_setter_adapter_is_narrow(self):
        source = (ROOT / 'runtime/windows_write.lua').read_text(encoding='utf-8')
        self.assertIn('function runtime.native_set_target(entry,handle,state,candidate)', source)
        self.assertIn("address(candidate),'unsupported target call'", source)

    def test_a_lock_is_held_while_it_is_hit_and_released_when_it_cannot_be(self):
        self.check(r"""
ai(12,5555)
local e=step(T0)
assert(kinds(e)=='locked'and e[1].target==5555 and e[1].state.alive and math.abs(e[1].state.distance-30)<1,kinds(e))
assert(repick()==T0+2000000 and pending()==-1)                -- the re-pick held 2 s ahead: no re-score, no switch
assert(kinds(step(T0+500000))=='retained')
assert(#step(T0+700000)==0 and repick()==T0+2000000)          -- more than 1.25 s left: nothing written
W.set(5555,{health=400});assert(#step(T0+1000000)==0 and repick()==T0+3000000)   -- hit; held again
W.set(5555,{health=300});step(T0+2500000)
-- It is never hit again for 3 s while firing (M.RELEASE_SECONDS): not hittable: released, the AI's own exit queued, not
-- locked again.
e=step(T0+4500000)
assert(not kinds(e):find('released',1,true),kinds(e))           -- 2 s: still held
e=step(T0+5500000)
assert(kinds(e)=='released:not hittable'and e[1].exit and pending()==4,kinds(e))
assert(n('PELICAN WEAPON TARGET EXIT (test): chin turret 8102: firing at entity 5555')==1)
assert(#step(T0+5600000)==0)                                  -- queued: nothing more
ai(5,5555)                                                    -- the game took it: stage 4, then 5
e=step(T0+5700000)
assert(kinds(e)=='exit_ran'and e[1].stage==5,kinds(e))
-- The AI picks it again and fires: out again at once, never locked.
ai(12,5555);step(T0+6200000)
-- The second exit is queued and counted; TARGET EXIT is logged once per turret (verbose logs each).
assert(pending()==4 and n('TARGET EXIT (test)')==1 and weapon.quiet_counts(8102).exits==2)
ai(5,5555);step(T0+6300000)
-- 5 s later it may be locked again.
ai(12,5555);e=step(T0+11000000)
assert(kinds(e)=='locked',kinds(e))
return 'ok'
""")

    def test_dead_out_of_sight_switched_and_no_target(self):
        self.check(r"""
ai(12,5555);step(T0)
-- Dead: released at once and out of firing.
W.set(5555,{health=0});local e=step(T0+300000)
assert(kinds(e)=='released:dead'and pending()==4,kinds(e))
ai(5,0);step(T0+400000)
-- A new lock; it drops out of sight (no longer its target, alive, not perceived): 0.5 s of grace, then released; no
-- candidate near it: the AI's own exit and pick.
ai(12,6666);assert(kinds(step(T0+500000))=='locked,transition')
ai(12,0)
assert(#step(T0+800000)==0 and #step(T0+1200000)==0)
e=step(T0+1400000)
assert(kinds(e)=='released:out of sight'and pending()==4 and e[1].plan:find('none within 50 m',1,true),kinds(e))
ai(5,0);step(T0+2000000)
-- A lock replaced by the game's own re-pick while out of its sight: reported, let go; the AI's pick is the lock.
W.set(5555,{health=500})
ai(12,6666);step(T0+2300000)
ai(12,5555);e=step(T0+2500000)
assert(kinds(e)=='switched,released:out of sight,locked,transition'and e[1].from==6666 and e[1].to==5555
    and e[1].lock_valid and e[4].from==6666 and e[4].to==5555 and math.abs(e[4].between-50)<0.01,kinds(e))
-- No lock, firing at nothing for 3 s (M.RELEASE_SECONDS): out of firing.
W.set(5555,{health=0});step(T0+2600000);ai(5,0);step(T0+2700000)
ai(12,0)
assert(#step(T0+2800000)==0 and #step(T0+5700000)==0)
e=step(T0+5900000)
assert(kinds(e)=='released:no target'and pending()==4,kinds(e))
return 'ok'
""")

    def test_the_lock_range_is_the_muzzles_not_the_transform(self):
        # 0.4.1 live: the turret's transform record keeps its creation point (a mounted child is placed by the scene
        # graph), ~250 m from every target, so nothing ever locked. The muzzle follows the turret.
        self.check(r"""
position(1,160,206,91)                                          -- the transform record: where the Pelican spawned
ai(12,5555)
local e=step(T0)
assert(kinds(e)=='locked'and math.abs(e[1].state.distance-30)<0.01,kinds(e))
return 'ok'
""")

    def test_a_dead_lock_is_replaced_by_the_nearest_through_the_setter(self):
        self.check(r"""
-- 5555 (locked) at (90, 70, 12); 7777 11.2 m from it; 6666 50 m from it; 8888 near it but not perceived; 9999 near it
-- but friendly; 4444 near it but flagged 35. The turret points at 5555.
local AW=AIMD.weaponData
W.write(WDRECS+AW.aim,f32(90)..f32(70)..f32(12))
W.add{entity=7777,type='73F8498BFFDCF415',unit=7777,health=500};W.unit(7777,100,75,12)
W.add{entity=8888,type='73F8498BFFDCF415',unit=7888,health=500};W.unit(7888,92,70,12)
W.add{entity=9999,type='73F8498BFFDCF415',unit=7999,health=500};W.unit(7999,91,71,12)
W.add{entity=4444,type='73F8498BFFDCF415',unit=7444,health=500};W.unit(7444,91,69,12)
perceive(5555,90,70,12);perceive(6666,60,110,12);local at7=perceive(7777,100,75,12);perceive(8888,92,70,12,false)
perceive(9999,91,71,12,true,1);perceive(4444,91,69,12);flag(4444,35)
ai(12,5555);step(T0)
local writes=#W.runtime.writes
W.set(5555,{health=0})
local e=step(T0+200000)
assert(kinds(e)=='released:dead,locked,transition',kinds(e))
assert(e[1].replacement.entity==7777 and e[1].replacement.radius==25 and e[1].plan=='installed now'and e[1].candidates==2
    and not e[1].exit,e[1].plan)
assert(e[2].target==7777 and e[2].how=='spatial')
local x=e[3]
assert(x.from==5555 and x.to==7777 and math.abs(x.between-math.sqrt(125))<0.01 and math.abs(x.yaw-math.deg(math.atan2(5,40)))<0.01
    and math.abs(x.turn-math.deg(math.atan2(5,40)))<0.01,tostring(x.yaw))
-- The game's setter: the update's context (the turret's handle record, P) and 7777's live entry; it is the AI's target.
local c=GX.calls[#GX.calls]
assert(c[1]=='set_target'and c[2]==W.GAME+PE.targetSet.setter.rva and c[3]==b.pointer(W.read(BHANDLES+8,8),0)
    and c[4]==record(1)+8 and c[5]==at7,'the call')
assert(b.u32(W.read(record(1)+AI.target,4),0)==7777 and pending()==-1 and repick()>T0+200000,'the target')
assert(n('PELICAN WEAPON TARGET SET (test): chin turret 8102: entity 7777 (list A entry')==1,'the log')
-- Still firing: no exit; the Runtime wrote nothing (the re-pick still held; the setter changed the target).
assert(#W.runtime.writes==writes,tostring(#W.runtime.writes-writes))
return 'ok'
""")

    def test_a_far_turn_goes_through_the_exit_and_stage_5(self):
        self.check(r"""
local AW=AIMD.weaponData
W.write(WDRECS+AW.aim,f32(90)..f32(70)..f32(12))
W.add{entity=7777,type='73F8498BFFDCF415',unit=7777,health=500};W.unit(7777,80,90,12)
perceive(5555,90,70,12);local at7=perceive(7777,80,90,12)
ai(12,5555);step(T0)
W.set(5555,{health=0})
local e=step(T0+200000)
-- 7777 is 22 m from it but a 51 degree turn: out of firing first.
assert(kinds(e)=='released:dead'and e[1].exit and pending()==4 and e[1].plan:find('exit',1,true),kinds(e))
assert(#GX.calls==0 or GX.calls[#GX.calls][1]~='set_target')
-- The AI aims again (stage 5) at its own pick (6666): 7777 installed there.
ai(5,6666)
e=step(T0+300000)
assert(kinds(e)=='exit_ran,locked,transition'and e[2].target==7777 and e[2].how=='spatial',kinds(e))
assert(GX.calls[#GX.calls][1]=='set_target'and GX.calls[#GX.calls][5]==at7)
assert(b.u32(W.read(record(1)+AI.target,4),0)==7777)
return 'ok'
""")

    def test_restored_after_a_re_pick_and_after_a_moment_out_of_sight(self):
        self.check(r"""
perceive(5555,90,70,12);perceive(6666,60,110,12)
ai(12,5555);step(T0)
-- A stage entry's re-pick took 6666; 5555 is alive and in sight: back through the setter.
ai(12,6666)
local e=step(T0+100000)
assert(kinds(e)=='restored'and e[1].target==5555 and e[1].from==6666,kinds(e))
assert(b.u32(W.read(record(1)+AI.target,4),0)==5555)
-- Lost for a moment (the AI cleared it; not perceived): within the grace nothing; perceived again: restored.
perceive(5555,90,70,12,false);ai(12,0)
assert(#step(T0+700000)==0)
perceive(5555,90,70,12,true)
e=step(T0+900000)
assert(kinds(e)=='restored'and e[1].from==nil,kinds(e))
-- Not more often than every 0.5 s: a re-pick right after waits for the next chance.
ai(12,6666)
assert(#step(T0+1000000)==0)
e=step(T0+1400000)
assert(kinds(e)=='restored',kinds(e))
return 'ok'
""")

    def test_aiming_without_firing_is_released(self):
        self.check(r"""
ai(5,5555)
assert(kinds(step(T0))=='locked')
assert(kinds(step(T0+1000000))=='retained')
-- Aiming 1.5 s without firing (M.AIM_SECONDS): let go.
local e=step(T0+1600000)
assert(kinds(e)=='released:cannot fire'and not e[1].exit,kinds(e))
-- Not locked again for 5 s.
assert(#step(T0+3200000)==0)
return 'ok'
""")

    def test_the_setter_refuses(self):
        self.check(r"""
perceive(5555,90,70,12);perceive(6666,60,110,12,false)
ai(12,5555)
local function set(entity)return in_update(function()return weapon.set_target(world,8102,entity,'test')end)end
assert(select(2,weapon.set_target(world,8102,5555,'test'))=='NOT_GAME_THREAD')
assert(select(2,in_update(function()return weapon.set_target(world,1234,5555,'test')end))=='NOT_SWITCHED')
assert(select(2,set(6666))=='NOT_A_CANDIDATE')                 -- not perceived
W.add{entity=3333,type='73F8498BFFDCF415',unit=7333,health=500};W.unit(7333,60,70,200)
perceive(3333,60,70,200)
assert(select(2,set(3333))=='NOT_A_CANDIDATE')                 -- 188 m from the muzzle
ai(4,0)
assert(select(2,set(5555))=='NOT_QUIET')
ai(12,5555);W.write(record(1)+AI.pending,W.u32(4))
assert(select(2,set(5555))=='NOT_QUIET')
ai(12,0)
W.write(W.GAME+PE.targetSet.setter.rva,'\204')
assert(select(2,set(5555))=='UNSUPPORTED_BUILD')
W.write(W.GAME+PE.targetSet.setter.rva,b.unhex(PE.targetSet.setter.prologue))
local saved=W.runtime.native_set_target;W.runtime.native_set_target=nil
assert(select(2,set(5555))=='UNAVAILABLE')
W.runtime.native_set_target=saved
assert(#GX.calls==0 or GX.calls[#GX.calls][1]~='set_target')
local r=set(5555)
assert(r and r.installed and r.target==5555)
-- Once per turret and reason (8 refusals, 6 reasons); verbose logs each.
assert(n('TARGET SET REFUSED (test)')==6,tostring(n('TARGET SET REFUSED (test)')))
weapon.verbose=true
assert(select(2,set(6666))=='NOT_A_CANDIDATE')
assert(n('TARGET SET REFUSED (test)')==7)
weapon.verbose=false
assert(weapon.quiet_counts(8102).set_refusals==8 and weapon.quiet_counts(1234).set_refusals==1)
return 'ok'
""")

    def test_never_while_pending_never_outside_the_update_never_unswitched(self):
        self.check(r"""
ai(12,5555)
W.write(record(1)+AI.pending,W.u32(3))                          -- a stage pending: nothing written
local w0=#W.runtime.writes
step(T0);step(T0+5000000)
assert(pending()==3 and #W.runtime.writes==w0)
ai(12,5555)
BOMB.set_clock(T0+9000000)
local e=weapon.target_step(world,8102,'test')
assert(e[1].kind=='refused'and e[1].code=='NOT_GAME_THREAD')
assert(#in_update(function()return weapon.target_step(world,1234,'test')end)==0)
return 'ok'
""")


class PelicanGatlingAIProofTests(unittest.TestCase):
    def lua(self, body):
        resource, wrapped, _ = addon(ROOT / 'proof/PelicanGatlingAIProof')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + '\n'
            + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI + body + '\nend)()\n'), b'ok')

    def test_the_source(self):
        _, _, body = addon(ROOT / 'proof/PelicanGatlingAIProof')
        code = '\n'.join(line.split('--')[0] for line in body.splitlines())
        self.assertIn("local BUILD='0.2.0 GATLING-AI SET-BEHAVIOUR BUILD'", body)
        self.assertEqual((ROOT / 'proof/PelicanGatlingAIProof/VERSION').read_text(encoding='utf-8').strip(), '0.2.0')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction',
                'native_', 'hd2.ensure', 'hd2.patch', 'hold_fire', 'gatling_turrets.replace', 'gatling_turrets.weapon',
                'GATLING-AI TRANSPLANT BUILD'):
            self.assertNotIn(forbidden, code, forbidden)

    def test_from_stage_4_and_the_sequence(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
scene()
stage(0,2,0)                                                   -- the Pelican approaching
ai(4)                                                          -- its chin turret not active
tick(16)
assert(n('AI FIELD (#1): Pelican 9501 (stage 2), chin turret 8102')==1 and n('= 645; behaviour 645, stage 4 (turret '
    ..'inactive)')==1,lines('AI FIELD'))
assert(n('AI RESULT (#1): chin turret 8102: behaviour BEFORE = 645, behaviour AFTER = 213 (read back), stage 1')==1,
    lines('AI RESULT'))
assert(n('requested 213 (the Gatling Sentry')>=1 and n('AI requested 213')>=1,lines('requested'))
-- The Gatling AI: search, a target, firing; the target lost, back to search; another target; firing again.
ai(2);tick(4)
ai(12,5555);tick(4)
ai(2,0);tick(4)
ai(12,6666);tick(4)
assert(n('AI STAGE (#1)')>=5 and n('behaviour 213, stage 12 (FIRING)')>=2 and n('behaviour 213, stage 2 (search)')>=2,
    lines('AI STAGE'))
assert(n('acquired entity 5555')==1 and n('LOST entity 5555')==1 and n('acquired entity 6666')==1,lines('AI TARGET'))
drop_entity(9501);tick(8)
assert(n('AI SUMMARY (#1): chin turret 8102')==1 and n('behaviour field after the change 213; behaviour field at the '
    ..'end 213')==1 and n('2 targets acquired, 1 lost')==1,lines('AI SUMMARY'))
return 'ok'
""")

    def test_waits_while_firing_natively(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
scene()
ai(3,4444)                                                     -- the native AI firing: not quiet
tick(16)
assert(n('AI RESULT')==0 and behaviour_id()==645,lines('AI RESULT'))
ai(1)                                                          -- idle: now
tick(4)
assert(n('behaviour BEFORE = 645, behaviour AFTER = 213 (read back), stage 1')==1,lines('AI RESULT'))
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
