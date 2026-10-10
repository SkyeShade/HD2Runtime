"""0.31.0 (research/docs/las-beam-overhaul-comparison.md): the firing charge (wind-up) of heat weapons
(WeaponHeat +148/+152/+156/+160) and the Trident's pulsed beam (BeamWeapon +100 fire mode, +104 rate, +108 beams per
pulse, +112 pulse seconds) as fields of each weapon's own records. A Trident-like beam blast on another beam weapon is
one transaction on its own BeamWeapon record; no component is added. Every field needs allow_unverified_effect until
the live tests pass. The snapshot test writes on a copy-on-write overlay of the retained snapshot."""
import unittest

from support import run
from test_multi_mod_composition import build_profile, snapshot_run


class CatalogueTests(unittest.TestCase):
    def test_fields_where_the_records_have_them(self):
        self.assertEqual(run(r'''
local W=require('hd2runtime/domains/player_weapon_authoring').weapons
local S=require('hd2runtime/domains/support_weapon_authoring').weapons
local function field(e,id)for _,f in ipairs(e.fields)do if f.semanticFieldId==id then return f end end end
-- The wind-up: 100 charge on the Sickles, the Scythe, the Dagger, the LAS-98 and the Quasar; 0 on the Sai and Trident.
for _,n in ipairs({'LAS-16 Sickle','LAS-17 Double-Edge Sickle','LAS-5 Scythe','LAS-7 Dagger'})do
    local f=assert(field(W[n],'heat.firing_charge'),n)
    assert(f.currentDefault==100 and f.editable and f.acknowledgement=='allow_unverified_effect',n)
    assert(f.backing.component=='WeaponHeatComponentData'and f.backing.offset==148 and f.writeScope=='weapon_local',n)
end
assert(field(W['LAS-12 Sai'],'heat.firing_charge').currentDefault==0)
assert(field(S['LAS-99 Quasar Cannon'],'heat.reset_charge_after_shot').currentDefault==true)
assert(field(W['LAS-16 Sickle'],'heat.charge_gain_per_second').currentDefault==200)
-- The pulse: the Trident in mode 6 (300 rpm, 2 beams, 0.15 s); the Scythe and the Dagger continuous (mode 4).
local t=W['LAS-13 Trident']
assert(field(t,'beam.fire_mode').currentDefault==6 and field(t,'beam.fire_rate').currentDefault==300
    and field(t,'beam.pulse_beams').currentDefault==2 and math.abs(field(t,'beam.pulse_seconds').currentDefault-0.15)<1e-6)
for _,n in ipairs({'LAS-5 Scythe','LAS-7 Dagger'})do
    assert(field(W[n],'beam.fire_mode').currentDefault==4 and field(W[n],'beam.pulse_beams').currentDefault==1,n)
end
assert(field(S['40-K Meltagun'],'beam.fire_mode').currentDefault==5)
-- The Sickle fires projectiles: no beam fields (no BeamWeapon component; adding one is refused by design).
assert(not field(W['LAS-16 Sickle'],'beam.fire_mode'))
-- The acknowledgement is required.
local patches=require('hd2runtime/domains/patches')
local hd2=require('hd2runtime/api/hd2')
local ok,why=pcall(patches.validate,{id='a',target=hd2.weapon('LAS-5 Scythe'),field='beam.fire_mode',expect=4,value=6})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),tostring(why))
ok,why=pcall(patches.validate,{id='a',target=hd2.weapon('LAS-5 Scythe'),allow_unverified_effect=true,
    field='beam.fire_mode',expect=4,value=7})
assert(not ok,'mode 7 is outside the observed modes')
return 'ok'
'''), b'ok')


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class SnapshotTests(unittest.TestCase):
    def test_a_trident_like_scythe_and_a_sickle_without_wind_up(self):
        result = snapshot_run(r'''
update=update or function()end
local reviewed=require('hd2runtime/api/inspect').reviewed
local scythe,sickle=hd2.weapon('LAS-5 Scythe'),hd2.weapon('LAS-16 Sickle')
local rate=reviewed(scythe,'beam.fire_rate')
local changes={{field='beam.fire_mode',expect=4,value=6},{field='beam.fire_rate',expect=rate,value=300},
    {field='beam.pulse_beams',expect=1,value=2},{field='beam.pulse_seconds',expect=0,value=0.15}}
local where=resolve('transaction',{id='w',target=scythe,allow_unverified_effect=true,changes=changes})
check(#where==4,'four members of the Scythe BeamWeapon record: '..#where)
local h={}
events.run_as('mods/test/beam_blast',function()
    h.scythe=hd2.ensure({transaction={id='trident-scythe',target=scythe,allow_unverified_effect=true,changes=changes}})
    h.sickle=hd2.ensure({patch={id='sickle-instant',target=sickle,allow_unverified_effect=true,
        field='heat.firing_charge',expect=100,value=0}})
end)
settle({h.scythe,h.sickle})
check(h.scythe.runs>=1 and h.scythe.result.status=='APPLIED','scythe '..tostring(h.scythe.error))
check(h.sickle.runs>=1 and h.sickle.result.status=='APPLIED','sickle '..tostring(h.sickle.error))
check(runtime.read(where[1].at,4)==b.encode(6,'u32'),'mode 6 written')
local n=0
for _ in pairs(overlay)do n=n+1 end
check(n==5,'exactly five members written: '..n)
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
