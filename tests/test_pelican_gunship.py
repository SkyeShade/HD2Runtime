"""runtime/pelican_gunship.lua (docs/custom-stratagem-api.md, "Pelican gunship"): the live-proven PelicanGatlingProof
0.5.0 chin gun lifecycle as a Runtime module, on the offline Pelican world and turret fixture of
tests/test_pelican_gatling_proof.py: the frozen configuration (the MG-206's AP4 round 275 at 2x the Gatling Sentry's
rate, 100 mrad, no aim recoil, the Gatling casing, the 2047-round magazine), its kills credited (its own no-credit tag
cleared), the Gatling AI, the orbit requested with its proven shape, the target lock, the refill, the body facing and
one summary; the gun spec rules; a Pelican that leaves ends it. Its log is transitions only."""
import unittest

from support import run, lua as lua_literal
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_weapon import WEAPON
from test_pelican_ai import AI
from test_pelican_heading import HEADING
from test_pelican_readonly_probes import HARNESS
from test_pelican_gatling_proof import PROOF

GUNSHIP = r"""
local gunship=require('hd2runtime/runtime/pelican_gunship');gunship.reset_for_tests()
require('hd2runtime/runtime/spawned_instances').reset_for_tests()
local FROZEN={behave_as='gatling_sentry',rate_multiplier=2,round='ap4',spread=100,recoil=false,unlimited_ammo=true,
    face_target=true}
"""


class PelicanGunshipTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + body + '\nend)()\n'), b'ok')

    def test_the_gun_spec_rules(self):
        self.lua(r"""
local function bad(gun,text)
    local ok,why=gunship.check_gun(gun)
    assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
assert(gunship.check_gun(FROZEN))
bad({round='ap5'},"gun.round must be 'standard', 'native', 'ap4', 'strafing_run' or 'strafing_run_pattern'")
bad({behave_as='tank'},"gun.behave_as must be 'gatling_sentry'")
bad({rate_multiplier=3,behave_as='gatling_sentry'},'gun.rate_multiplier must be 1, 1.5 or 2')
bad({rate_multiplier=2},'it needs behave_as')
bad({spread=101},'gun.spread is a width in mrad')
bad({recoil=true},'gun.recoil can only be false')
bad({face_target=true},'gun.face_target follows the Runtime target lock')
bad({colour='red'},'unsupported gun option: colour')
assert(gunship.check_orbit({radius=40,altitude=60,duration=55}))
assert(select(2,gunship.check_orbit({radius=400}))=='orbit.radius must be 5 to 150')
assert(select(2,gunship.check_orbit({entry=60,duration=55})):find('orbit.entry must be shorter',1,true))
return 'ok'
""")

    def test_a_call_run_for_another_player_credits_every_round_to_that_player(self):
        # r6 live-proven caller attribution (a client-requested Pelican): the turret's own network creditor is the host;
        # the Runtime rewrites each round's pool creditor to the requester (projectile_impact bind_credit). Kept by the
        # 0.30 provenance consolidation: this pins the link from the arm spec to that binding.
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local impacts=require('hd2runtime/runtime/projectile_impact')
local credited
impacts.bind_credit=function(spec,cb)credited=spec;return {status='active',cancel=function()end}end
local events={}
local g=assert(gunship.arm(9501,{gun=FROZEN,credit_peer='5555666677778888',
    label='pelican_close_air_support#1@5555666677778888 Pelican 9501'},function(e)events[#events+1]=e end))
tick(16)
assert(credited and credited.credit_to=='5555666677778888'and credited.sources[1]==8102 and credited.projectiles[1]==275,
    'every round of its own chin turret credits the requester: '..tostring(credited and credited.credit_to))
local armed
for _,e in ipairs(events)do if e.kind=='armed'then armed=e end end
assert(armed and armed.credit_peer=='5555666677778888'and armed.credit_written==true,tostring(armed and armed.credit_peer))
return 'ok'
""")

    def test_the_frozen_gun_its_credit_ai_orbit_lock_refill_facing_and_summary(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local events={}
local g=assert(gunship.arm(9501,{gun=FROZEN,orbit={radius=40,altitude=60,duration=55},credit=true,
    label='pelican_close_air_support#1 Pelican 9501'},function(e)events[#events+1]=e end))
tick(16)
local armed
for _,e in ipairs(events)do if e.kind=='armed'then armed=e end end
assert(armed and armed.turret==8102 and armed.projectile==275 and armed.round=='ap4'and armed.rpm==3200 and armed.credit
    and armed.verified,'armed: '..tostring(armed and armed.projectile))
assert(n('pelican gunship pelican_close_air_support#1 Pelican 9501: ARMED: chin turret 8102: projectile 275 (ap4), 3200 '
    ..'RPM, spread 100 mrad, aim recoil zero, magazine 2047, credit to the caller (the host)')==1,lines('ARMED'))
-- Its own records only: the spread, the recoil, the credit tag.
assert(b.value(W.read(WDRECS+PE.spread.instance,4),0,'f32')==100)
assert(b.value(W.read(WDRECS+AIMD.weaponData.recoilB,4),0,'f32')==0)
assert(b.u32(W.read(TAGVALS,4),0)==0x02000004,'the no-credit tag')
assert(n('pelican gunship pelican_close_air_support#1 Pelican 9501: AI: chin turret 8102: behaviour 645 -> 213')==1,
    lines('AI'))
assert(#orbits==1 and orbits[1].spec.radius==40 and orbits[1].spec.altitude==60 and orbits[1].spec.duration==55
    and orbits[1].spec.mode=='sweep'and orbits[1].spec.interval==0.25 and orbits[1].spec.period==30
    and orbits[1].spec.entry==15,'the orbit request')
-- The hold; an enemy; the AI fires at it: the lock; the body turns.
local world=world_module.open()
held(world)
W.add{entity=5555,type='73F8498BFFDCF415',unit=7555,health=500};W.unit(7555,100,70,0)
BOMB.set_clock(T0+1000000);ai(12,5555);tick(4)
assert(g.locks==1,'locks '..g.locks)
assert(desired()>0.1,'the body turned toward the target')
-- The refill below 1500.
W.write(MGENTS+AMD.entryRounds,W.u32(1400));W.write(MGRECS,W.u32(1400))
tick(4)
assert(g.refills==1,'refills '..g.refills)
-- It leaves: one summary line; the end event.
local before=#logged
drop_entity(9501);tick(8)
assert(n('pelican gunship pelican_close_air_support#1 Pelican 9501: SUMMARY: the Pelican left; chin turret 8102;')==1
    and n('1 refills; 1 targets locked')==1,lines('SUMMARY'))
assert(events[#events].kind=='ended'and gunship.of(9501)==nil)
-- Transitions only: nothing per tick from the gunship itself.
local gun_lines=0
for _,line in ipairs(logged)do if line:find('pelican gunship',1,true)then gun_lines=gun_lines+1 end end
assert(gun_lines<=4,'gunship lines '..gun_lines)
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
