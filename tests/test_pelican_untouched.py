"""An untouched Pelican gun (2026-10-07; runtime/pelican_gunship.lua M.plain / M.untouched, runtime/custom_mp_pelican.lua):
gun = {round = 'native'} and nothing else leaves the chin turret exactly as the game spawned it, on every machine. Live,
the host's private weapon copy (its default 600 RPM) gave six-round bursts where the other machines saw the vanilla
three, so:
  * which guns are untouched: the native round alone; any other option (spread, recoil, sound, ammunition, a blast, the
    Gatling AI) still configures its own copy;
  * the gunship: no weapon copy, rate, refill or AI change, no Gatling package requested; only the kill credit (the
    no-credit tag on its own Tag mask) and the armed event saying untouched;
  * every other machine: the mirror copies nothing (its own autocannon there too)."""
import unittest

from support import run
from support import lua as lua_literal
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
from test_pelican_gunship import GUNSHIP


def gunship_lua(body):
    return run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
        + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
        + HEADING + PROOF + GUNSHIP + body + '\nend)()\n')


class UntouchedGunTests(unittest.TestCase):
    def test_which_guns_are_untouched(self):
        self.assertEqual(gunship_lua(r"""
assert(gunship.untouched({round='native'}))
assert(not gunship.untouched({}),'the default round is the standard one, configured')
assert(not gunship.untouched({round='standard'}))
for _,extra in ipairs({{spread=15},{recoil=false},{unlimited_ammo=true},{sound='sentry/ems_mortar'},
        {impact_explosion='Pelican chin autocannon'},{behave_as='gatling_sentry'}})do
    local gun={round='native'}
    for k,v in pairs(extra)do gun[k]=v end
    local ok=gunship.check_gun(gun)
    assert(ok==nil or not gunship.untouched(gun),next(extra))
end
assert(gunship.plain(gunship.check_gun({round='native'})))
-- Its own firing sound named explicitly is still its own: untouched.
assert(gunship.untouched({round='native',sound='pelican/chin_autocannon'}))
return 'ok'
"""), b'ok')

    def test_the_gunship_leaves_the_chin_turret_alone(self):
        self.assertEqual(gunship_lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local configured,refilled,assets,credited=false,0,0,{}
weapon.configure=function()configured=true;return nil,'TEST','must not be called'end
weapon.refill_step=function()refilled=refilled+1 end
local assets_fn=weapon.assets
weapon.assets=function(...)assets=assets+1;return assets_fn(...)end
weapon.configure_credit=function(world,turret,label)credited[#credited+1]=turret
    return {applied=true,writes=1}end
local events={}
assert(gunship.arm(9501,{gun={round='native'},credit=true,label='cannon'},function(e)events[#events+1]=e end))
tick(16)
assert(not configured,'no weapon copy, no rate')
assert(refilled==0,'no refill')
assert(assets==0,'no Gatling package for an untouched gun')
assert(#credited==1,'only the kill credit')
local armed
for _,e in ipairs(events)do if e.kind=='armed'then armed=e end end
assert(armed and armed.untouched and armed.round=='native'and armed.projectile==120 and armed.credit==true)
assert(n('UNTOUCHED: the Pelican\'s own autocannon (projectile 120) with its own rate, bursts, aim, ammunition and AI')==1,
    table.concat(logged,' | '))
-- Without credit: nothing at all is written.
gunship.reset_for_tests()
credited={}
assert(gunship.arm(9501,{gun={round='native'},label='cannon2'},function()end))
tick(16)
assert(#credited==0 and not configured)
return 'ok'
"""), b'ok')

    def test_every_other_machine_mirrors_nothing(self):
        self.assertEqual(run(WORLD + r"""
local mirror=require('hd2runtime/runtime/custom_mp_pelican')
local weapon=require('hd2runtime/runtime/pelican_weapon')
local called=false
weapon.mirror_configure=function()called=true;return nil,'TEST','must not be called'end
local h=mirror.mirror({turret=8102,pelican=8101,network=401,gun={round='native'},label='remote cannon'})
assert(h.status=='complete'and h.untouched and h.describe():find('nothing mirrored',1,true))
assert(not called)
-- A configured gun still mirrors (its handle stays active).
local h2=mirror.mirror({turret=8102,pelican=8101,network=401,gun={round='native',spread=15},label='remote cas'})
assert(h2.status=='active'and not h2.untouched)
h2.cancel()
return 'ok'
"""), b'ok')


if __name__ == '__main__':
    unittest.main()
