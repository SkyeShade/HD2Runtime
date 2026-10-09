"""0.30.4 beam swaps (research/beam-outputs-F5FEE03DCFDB.json, docs/attack-outputs.md "Beam swaps" and "Lasers
everywhere"). Every BeamWeapon record is inventoried with its owner; every beam a Helldiver-side weapon fires is a
catalogued beam output; a beam host's BeamType reference (its active beam source: its own BeamWeapon +0, or the LAS-5
Scythe's default muzzle delta row) takes any catalogued beam output. Projectile weapons never gain a beam (no component
is added). The snapshot tests resolve and write on a copy-on-write overlay of the retained snapshot."""
import json
import unittest

from support import ROOT, run
from test_multi_mod_composition import build_profile, snapshot_run


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


HOSTS = {'LAS-13 Trident': 'component', 'LAS-7 Dagger': 'component', 'LAS-5 Scythe': 'attachment',
    '40-K Meltagun': 'component', 'LAS-98 Laser Cannon': 'component', 'A/LAS-98 Laser Sentry / weapon': 'component'}
DONORS = {'LAS-13 Trident': 6, 'LAS-7 Dagger': 11, 'LAS-5 Scythe': 8, '40-K Meltagun': 18, 'LAS-98 Laser Cannon': 1,
    'A/LAS-98 Laser Sentry': 10}


class ResearchTests(unittest.TestCase):
    def test_every_beam_weapon_record_is_inventoried(self):
        research = load('research/beam-outputs-F5FEE03DCFDB.json')
        self.assertEqual(research['writes'], 0)
        summary = research['summary']
        # 24 records: 23 owned (one entity each) and the unowned default record.
        self.assertEqual((summary['records'], summary['owners']), (24, 23))
        self.assertEqual(summary['byKind'], {'dropped_root': 2, 'enemy': 5, 'enemy_structure': 2, 'other_root': 1,
            'player_weapon': 3, 'sentry': 1, 'support_weapon': 2, 'unnamed': 6, 'vehicle_weapon': 1})
        owners = {o['name']: (r, o) for r in research['records'] for o in r['owners'] if o['name']}
        for name, beam in (('LAS-13 Trident', 6), ('LAS-7 Dagger', 11), ('40-K Meltagun', 18),
                ('LAS-98 Laser Cannon', 1), ('A/LAS-98 Laser Sentry', 10)):
            record, owner = owners[name]
            self.assertEqual((record['beamType'], owner['status'], owner['defaultCustomization']),
                (beam, 'ACTIVE_DIRECT', []), name)
        # The Scythe's default muzzle patches BeamWeapon +0 at weapon build: the delta row is its active source.
        record, scythe = owners['LAS-5 Scythe']
        self.assertEqual((scythe['status'], scythe['activeSource']['item'], scythe['activeSource']['value'],
            scythe['activeSource']['baseAgrees']), ('INDIRECT', 'Laser. Standard Prism', 8, True))
        # The Rover drone gun defaults to the same muzzle, whose BeamType (8) differs from its record's (25): which one
        # a drone fires is not proven (the delta application is live-proven for player weapons only).
        record, rover = owners['AX/LAS-5 Rover / gun']
        self.assertEqual((record['beamType'], rover['status'], rover['activeSource']['value']), (25, 'AMBIGUOUS', 8))
        # Five entity deltas patch BeamWeapon, each in its own 4-byte +0 row.
        self.assertEqual(summary['beamDeltas'], 5)
        self.assertTrue(all(p['beamTypeOwnRow'] for p in research['beamDeltas']))
        # The Trident's row is the only pulse row a weapon fires; every donor's package lists its beam resources.
        self.assertEqual(research['beamTypes']['6']['pulseRowFlag'], 1)
        for name in DONORS:
            _, owner = owners[name]
            self.assertTrue(any(p['listsBeamResources'] for p in owner['packages']), name)


class CatalogTests(unittest.TestCase):
    def test_beam_outputs_and_hosts(self):
        catalog = load('sdk/AttackOutputCapabilities.json')
        beams = {o['owner']['name']: o for o in catalog['outputs'] if o['family'] == 'beam'}
        donors = {name: o['beamType'] for name, o in beams.items() if o['selectableAsBeamReference']}
        self.assertEqual(donors, DONORS)
        for name in DONORS:
            self.assertFalse(beams[name]['selectableAsProjectileReference'])
            self.assertTrue(beams[name]['package']['known'] and beams[name]['package']['listsBeamResources'])
        self.assertFalse(beams['AX/LAS-5 Rover / gun']['selectableAsBeamReference'])
        enemy = [o for o in beams.values() if o['owner']['kind'] == 'enemy']
        self.assertEqual(len(enemy), 5)
        self.assertTrue(all('no catalogued package' in o['blockedReason'] for o in enemy))
        hosts = {h['weapon']: h for h in catalog['beamSources']}
        self.assertEqual({k: h['mechanism'] for k, h in hosts.items() if h['writable']}, HOSTS)
        self.assertEqual(hosts['LAS-5 Scythe']['sharedWithWeapons'], ['AX/LAS-5 Rover / gun'])
        self.assertFalse(hosts['AX/LAS-5 Rover / gun']['writable'])
        self.assertEqual((catalog['summary']['beamDonors'], catalog['summary']['beamHosts']), (6, 6))
        public = load('sdk/VehicleWeaponCapabilities.json')
        self.assertEqual([h['stratagem'] for h in public['stratagemBeamHosts']], ['A/LAS-98 Laser Sentry'])

    def test_api(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local function swap(source,value,extra)
 local r={id='b',target=source.target,field=hd2.fields.attack.beam,expect=source.expect,value=value,
  allow_unverified_reference=true,allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return patches.validate(r)
end
local trident=hd2.weapon('LAS-13 Trident'):beam_source()
assert(trident.writable and trident.mechanism=='component'and trident.target.path=='weapon'and trident.field=='attack.beam')
local scythe=hd2.weapon('LAS-5 Scythe'):beam_source()
assert(scythe.writable and scythe.mechanism=='attachment'and scythe.target.path=='beam_attachment'
 and scythe.item=='Laser. Standard Prism'and scythe.acknowledgements[1]=='allow_shared')
local las98=hd2.support_weapon('LAS-98 Laser Cannon'):beam_source()
local sentry=hd2.stratagem('A/LAS-98 Laser Sentry'):attack('primary'):beam_source()
assert(las98.writable and sentry.writable and sentry.target.weapon=='A/LAS-98 Laser Sentry / weapon')
local rover=hd2.backpack('AX/LAS-5 Rover'):drone():weapon():beam_source()
assert(not rover.writable and rover.status=='AMBIGUOUS')
-- A projectile weapon has no beam source: Runtime never adds a BeamWeapon.
local liberator=hd2.weapon('AR-23 Liberator'):beam_source()
assert(not liberator.writable and liberator.reason:find('never adds one',1,true))
rejects(function()return hd2.weapon('AR-23 Liberator'):beam()end,'fires no beam')
-- Donors: an output or another beam weapon's own handle; each loads its owner's package first.
local spec=swap(scythe,hd2.attack_output('LAS-13 Trident'),{allow_shared=true})
assert(spec.asset_dependencies[1].key=='player_weapon/LAS-13 Trident')
spec=swap(trident,hd2.weapon('LAS-7 Dagger'):beam())
assert(spec.changes[1].desired_selector.output=='output/v1/beam/las-7-dagger'
 and spec.asset_dependencies[1].key=='player_weapon/LAS-7 Dagger#2')
spec=swap(las98,hd2.attack_output('40-K Meltagun'))
assert(spec.asset_dependencies[1].key=='support_weapon/40-K Meltagun')
spec=swap(sentry,hd2.attack_output('LAS-13 Trident'))
assert(spec.kind=='vehicle_weapon'and spec.mount_chain.stratagem.name=='A/LAS-98 Laser Sentry')
spec=swap(hd2.weapon('LAS-7 Dagger'):beam_source(),hd2.attack_output('A/LAS-98 Laser Sentry'))
assert(spec.asset_dependencies[1].key=='support_weapon/LAS-98 Laser Cannon#2')
-- Restoring the host's own beam needs no acknowledgement (the muzzle's still needs allow_shared).
assert(swap(trident,trident.expect,{allow_unverified_reference=false,allow_unverified_effect=false})
 .changes[1].self_reference)
assert(swap(scythe,scythe.expect,{allow_unverified_reference=false,allow_unverified_effect=false,allow_shared=true})
 .changes[1].self_reference)
-- Refusals.
rejects(function()swap(trident,hd2.weapon('LAS-5 Scythe'):beam(),{allow_unverified_reference=false})end,
 'allow_unverified_reference')
rejects(function()swap(trident,hd2.weapon('LAS-5 Scythe'):beam(),{allow_unverified_effect=false})end,
 'allow_unverified_effect')
rejects(function()swap(scythe,hd2.attack_output('LAS-13 Trident'))end,'allow_shared')
rejects(function()swap(trident,hd2.attack_output('LAS-58 Talon'))end,'INCOMPATIBLE_OUTPUT_FAMILY')
rejects(function()swap(trident,hd2.attack_output('Illuminate tripod beam'))end,'not selectable as a beam')
rejects(function()swap(trident,hd2.attack_output('AX/LAS-5 Rover / gun'))end,'not selectable as a beam')
rejects(function()swap(trident,hd2.backpack('AX/LAS-5 Rover'):drone():weapon():beam())end,'UNKNOWN_DONOR')
rejects(function()swap(trident,hd2.weapon('LAS-7 Dagger'):beam(),{expect=hd2.weapon('LAS-7 Dagger'):beam()})end,
 'expect must be the target weapon current beam handle')
-- The Scythe's own record member is dormant (its muzzle delta overwrites it): read-only with the redirect.
rejects(function()patches.validate{id='x',target=hd2.weapon('LAS-5 Scythe'),field=hd2.fields.attack.beam,
 expect=hd2.weapon('LAS-5 Scythe'):beam(),value=hd2.attack_output('LAS-13 Trident'),allow_unverified_reference=true,
 allow_unverified_effect=true}end,'DORMANT_BEAM_REFERENCE')
-- A beam is never a projectile: projectile hosts refuse beam outputs with the reason.
local reprimand=hd2.weapon('SMG-32 Reprimand'):attack('primary')
rejects(function()patches.validate{id='x',target=reprimand,field=hd2.fields.attack.projectile,
 expect=reprimand:projectile(),value=hd2.attack_output('LAS-13 Trident'),allow_unverified_reference=true,
 allow_unverified_effect=true}end,'projectile host references only ProjectileType')
local described=hd2.attack_output('LAS-13 Trident'):describe()
assert(described.selectableAs=='beam'and described.beamClass=='pulsed'and described.beamType==6)
-- Lasers on projectile weapons are laser bolts: the projectile outputs of the LAS-58 Talon, LAS-16 Sickle and LAS-12
-- Sai (plain bolts, the same class as a rifle bullet) and the LAS-99 Quasar (an explosive bolt, cross-class).
for _,name in ipairs({'LAS-58 Talon','LAS-16 Sickle','LAS-12 Sai'})do
 local spec=patches.validate{id='bolt',target=reprimand,field=hd2.fields.attack.projectile,expect=reprimand:projectile(),
  value=hd2.attack_output(name)}
 assert(not spec.changes[1].cross_class,name)
end
rejects(function()patches.validate{id='bolt',target=reprimand,field=hd2.fields.attack.projectile,
 expect=reprimand:projectile(),value=hd2.attack_output('LAS-99 Quasar Cannon')}end,'allow_unverified_reference')
-- The Double-Edge Sickle's bolts are chosen by its heat levels: not a donor.
rejects(function()patches.validate{id='bolt',target=reprimand,field=hd2.fields.attack.projectile,
 expect=reprimand:projectile(),value=hd2.attack_output('LAS-17 Double-Edge Sickle'),allow_unverified_reference=true,
 allow_unverified_effect=true}end,'not selectable')
-- The Liberator's own control: Talon bolts through its default ammunition (the live-proven ammunition source).
local liberator=hd2.weapon('AR-23 Liberator'):projectile_source()
patches.validate{id='bolt',target=liberator.target,field=hd2.fields.ammunition.projectile,expect=liberator.expect,
 value=hd2.attack_output('LAS-58 Talon'),allow_shared=true}
return 'ok'
'''), b'ok')


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class SnapshotTests(unittest.TestCase):
    def test_beam_swaps_land_on_the_active_source(self):
        result = snapshot_run(r'''
update=update or function()end
local function swap(source,value,extra)
 local r={id='b',target=source.target,field=F.attack.beam,expect=source.expect,value=value,
  allow_unverified_reference=true,allow_unverified_effect=true}
 for k,v in pairs(extra or{})do r[k]=v end
 return r
end
local scythe=hd2.weapon('LAS-5 Scythe'):beam_source()
local las98=hd2.support_weapon('LAS-98 Laser Cannon'):beam_source()
local sentry=hd2.stratagem('A/LAS-98 Laser Sentry'):attack('primary'):beam_source()
local trident=hd2.weapon('LAS-13 Trident'):beam_source()
-- Each swap resolves to exactly one u32: the host's active beam source, from its reviewed BeamType to the donor's.
local cases={
 {'scythe <- trident',swap(scythe,hd2.attack_output('LAS-13 Trident'),{allow_shared=true}),8,6},
 {'las98 <- scythe',swap(las98,hd2.weapon('LAS-5 Scythe'):beam()),1,8},
 {'sentry <- trident',swap(sentry,hd2.attack_output('LAS-13 Trident')),10,6},
 {'trident <- dagger',swap(trident,hd2.weapon('LAS-7 Dagger'):beam()),6,11},
}
local where={}
for _,case in ipairs(cases)do
 local found=resolve('patch',case[2])
 check(#found==1,case[1]..': one member, got '..#found)
 check(found[1].before==b.encode(case[3],'u32')and found[1].desired==b.encode(case[4],'u32'),case[1]..' bytes')
 where[case[1]]=found[1].at
end
-- The Scythe's swap writes the muzzle's delta row, not its (dormant) BeamWeapon record.
local record=resolve('patch',{id='r',target=hd2.weapon('LAS-5 Scythe'),allow_unverified_effect=true,
 field=F.beam.fire_mode,expect=4,value=6})[1]
check(record.at~=where['scythe <- trident'],'the Scythe beam swap must not land on its BeamWeapon record')
-- Restoring the Scythe's own beam resolves to its reviewed type, with no donor acknowledgement.
local back=resolve('patch',{id='b',target=scythe.target,field=F.attack.beam,expect=scythe.expect,value=scythe.expect,
 allow_shared=true})
check(#back==1 and back[1].at==where['scythe <- trident']and back[1].desired==b.encode(8,'u32'),'restore bytes')
check(counts.writes==0 and next(overlay)==nil,'resolution wrote')
-- Apply two through hd2.ensure: the Scythe fires the Trident's beam, the LAS-98 the Scythe's. Each is gated on its
-- donor's package (asserted in CatalogTests.test_api); a snapshot overlay cannot load packages, so the gate is stubbed
-- ready here, after checking it does gate the write.
local assets=require('hd2runtime/core/assets')
local gate=assets.gate(runtime,{id='g',asset_dependencies=assets.collect(patches.validate(cases[1][2]))})
check(#gate.dependencies==1 and gate.dependencies[1].key=='player_weapon/LAS-13 Trident','scythe swap gate')
check(gate.tick(1)=='failed'and gate.reason:find('ASSET_UNAVAILABLE',1,true),'the gate holds the write back')
assets.gate=function()return {state='ready',dependencies={},tick=function()return 'ready'end}end
local h={}
events.run_as('mods/test/beam_swaps',function()
 h.scythe=hd2.ensure({patch=cases[1][2]})
 h.las98=hd2.ensure({patch=cases[2][2]})
end)
settle({h.scythe,h.las98})
check(h.scythe.runs>=1 and h.scythe.result.status=='APPLIED','scythe '..tostring(h.scythe.error))
check(h.las98.runs>=1 and h.las98.result.status=='APPLIED','las98 '..tostring(h.las98.error))
check(runtime.read(where['scythe <- trident'],4)==b.encode(6,'u32'),'scythe muzzle now names the Trident beam')
check(runtime.read(where['las98 <- scythe'],4)==b.encode(8,'u32'),'LAS-98 now names the Scythe beam')
local n=0
for _ in pairs(overlay)do n=n+1 end
check(n==2,'exactly two members written: '..n)
-- After the swap the Scythe's own beam row fields follow its active source: a plain edit of its old row is refused.
local ok,why=pcall(resolve,'patch',{id='l',target=hd2.weapon('LAS-5 Scythe'),field=F.beam.length,expect=1000,value=500})
check(not ok and tostring(why):find('COMPOSITION_TARGET_CHANGED',1,true),'stale beam row edit: '..tostring(why))
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
