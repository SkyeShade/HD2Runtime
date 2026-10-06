"""The Runtime bombardment executor (runtime/bombardment_executor.lua; docs/research/beacon-redirect-F5FEE03DCFDB.md,
"The Runtime bombardment executor"): the Orbital 120mm HE Barrage's pattern (read from its live, vanilla record), fired as
the Orbital Gas Strike's shell 197 through the game's projectile wrapper from the host's avatar: 5 salvos of 3, 0.75 s
between shells, 2.0 s between salvos, a +-27 square scatter, each shell 3000 above its aim, straight down. Every guard
refuses before anything is fired. No game data is written. Offline: the payload world (its projectile table holds the
reviewed shell rows)."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD

EXECUTOR = r"""
local executor=require('hd2runtime/runtime/bombardment_executor')
-- A deterministic random function (the game's LCG, top 32 bits).
local function lcg(seed)
    local s=seed
    return function()s=(s*1103515245+12345)%2147483648;return s/2147483648 end
end
local function shells()local n=0;for _,p in ipairs(W.runtime.projectiles)do if p.type==197 then n=n+1 end end;return n end
-- The host's avatar (entity 100). The payload world's bombardment object sits at the component-world global, which the
-- avatar lookup also reads in the real game, so this offline world resolves no avatar: the lookup is stubbed here.
local function host_avatar()
    W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
    require('hd2runtime/runtime/handles').local_avatar=function()return {id=100}end
end
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + EXECUTOR + body)


class BombardmentExecutorTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_120mm_pattern_of_gas_shells(self):
        self.check(r'''
pworld();host_avatar()
local p=executor.pattern_of('Orbital 120mm HE Barrage')
assert(p.shells_per_salvo==3 and p.salvos==5 and p.shell_delay==0.75 and p.salvo_delay==2 and p.scatter==27
    and p.distance==3000 and p.start_delay==0)
local writes=#W.runtime.writes
local events={}
local h,code,why=executor.start({target={x=100,y=200,z=10},random=lcg(7),label='test'},function(e)events[#events+1]=e end)
assert(h,tostring(code)..' '..tostring(why))
assert(events[1].kind=='started'and events[1].shell==197 and events[1].shells==15)
tick(200)
assert(shells()==15,'shells '..shells())
local times={}
for _,e in ipairs(events)do if e.kind=='shell'then times[#times+1]=e.seconds end end
-- Salvo k's shells at 3.5 k, +0.75, +1.5 s (within one 0.125 s update).
for k=0,4 do for j=0,2 do
    local want=3.5*k+0.75*j
    local got=times[k*3+j+1]
    assert(got>=want and got<want+0.125+1e-6,('shell %d at %.3f, wanted %.3f'):format(k*3+j+1,got,want))
end end
for _,s in ipairs(W.runtime.projectiles)do
    assert(s.type==197 and s.dx==0 and s.dy==0 and s.dz==-1 and math.abs(s.z-3010)<1e-6)
    assert(math.abs(s.x-100)<=27 and math.abs(s.y-200)<=27,'outside the scatter')
    assert(s.entity==100,'fired by the host avatar')
end
assert(events[#events].kind=='ended'and events[#events].shells==15 and events[#events].salvos==5)
assert(#W.runtime.writes==writes,'nothing is written')
return 'ok'
''')

    def test_every_guard_fires_nothing(self):
        self.check(r'''
pworld();host_avatar()
local function refused(code,spec,prepare)
    local undo=prepare and prepare()
    local before=#W.runtime.projectiles
    local h,got,why=executor.start(spec or{target={x=1,y=2,z=3}})
    assert(not h and got==code,code..' expected, got '..tostring(got)..': '..tostring(why))
    assert(#W.runtime.projectiles==before)
    if undo then undo()end
end
refused('INVALID_TARGET',{target={x=1,y=2}})
refused('INVALID_TARGET',{target={x=0/0,y=2,z=3}})
refused('NOT_HOST',nil,function()W.state(4,{host=false})return function()W.state(4)end end)
refused('NOT_IN_MISSION',nil,function()W.state(3)return function()W.state(4)end end)
-- The shell row is not its reviewed row.
local row=BOMB.shell_row(197)
local original=W.read(row,4)
refused('SHELL_CHANGED',nil,function()W.write(row,W.u32(198))return function()W.write(row,original)end end)
-- The pattern donor's record is not vanilla.
local rec=BOMB.record(BIG_ID)
local word=W.read(rec+0x24,4)
refused('PATTERN_CHANGED',nil,function()W.write(rec+0x24,b.encode(5,'f32'))return function()W.write(rec+0x24,word)end end)
-- The Gas Strike's call-in package is not resident.
local assets=require('hd2runtime/core/assets')
local PACKAGE=assets.dependency_for_stratagem(GAS_ID,'x').package
W.runtime.packages[PACKAGE]='absent'
refused('SHELL_NOT_RESIDENT')
W.runtime.packages[PACKAGE]=nil
-- A mission that ends mid-barrage ends it: the shells already fired, no more.
local events={}
local h=assert(executor.start({target={x=1,y=2,z=3},random=lcg(3)},function(e)events[#events+1]=e end))
tick(10)
local fired=shells()
assert(fired>=1 and fired<15)
W.state(3);tick(40)
assert(shells()==fired and events[#events].kind=='refused'and events[#events].code=='NOT_IN_MISSION')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
