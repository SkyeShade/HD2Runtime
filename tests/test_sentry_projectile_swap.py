"""Sentry and emplacement projectile swaps (0.30.2): research/sentry-projectile-hosts-F5FEE03DCFDB.json classifies every
stratagem deployed entity that carries its own ProjectileWeapon record by the same rules as player, support and mounted
hosts; the ACTIVE_DIRECT ones publish a projectile reference on the mounted-weapon host model
(domains/vehicle_weapon_authoring.lua '<stratagem> / weapon'), reached through
hd2.stratagem(name):attack('primary'):projectile_source(). The MG-43 and Gatling sentries name each round in a magazine
pattern and stay blocked. The writer re-proves the stratagem payload link instead of a vehicle mount."""
import json
import unittest

from support import ROOT, run

WRITABLE = {'A/AC-8 Autocannon Sentry', 'A/M-12 Mortar Sentry', 'A/MLS-4X Rocket Sentry', 'A/M-23 EMS Mortar Sentry',
    'A/GM-17 Gas Mortar Sentry', 'E/MG-101 HMG Emplacement', 'E/AT-12 Anti-Tank Emplacement'}
PATTERN = {'A/MG-43 Machine Gun Sentry', 'A/G-16 Gatling Sentry'}


def load(relative):
    return json.loads((ROOT / relative).read_text())


class ResearchTests(unittest.TestCase):
    def test_every_projectile_sentry_is_classified_by_the_host_rules(self):
        research = load('research/sentry-projectile-hosts-F5FEE03DCFDB.json')
        self.assertEqual((research['writes'], research['fixtureFallback']), (0, 'disabled'))
        hosts = {h['weapon']: h for h in research['hosts']}
        self.assertEqual(set(hosts), WRITABLE | PATTERN)
        for name in WRITABLE:
            host = hosts[name]
            self.assertEqual((host['status'], host['selectors'], host['defaultCustomization']), ('ACTIVE_DIRECT', [], []))
            self.assertEqual(host['magazinePattern']['entries'], 0)
            self.assertTrue(host['componentIdentity']['uniqueOwner'])
            self.assertEqual(host['output']['type'], host['base']['projType'])
        for name in PATTERN:
            self.assertEqual(hosts[name]['status'], 'BLOCKED')
            self.assertEqual(hosts[name]['magazinePattern']['entries'], 5)
        # The stratagem's own payload list names each host (the writer's ownership chain).
        roots = {s['name']: s['currentRoot'] for s in load('research/defensive-stratagem-runtime-F5FEE03DCFDB.json')[
            'stratagems']}
        for name, host in hosts.items():
            self.assertIn(host['resource'], roots[name]['payloads'])


class CatalogTests(unittest.TestCase):
    def test_hosts_publish_one_reference_field(self):
        public = load('sdk/VehicleWeaponCapabilities.json')
        hosts = {h['stratagem']: h for h in public['stratagemHosts']}
        self.assertEqual(public['stratagemHostSummary'], {'hosts': 9, 'writable': 7})
        self.assertEqual({k for k, h in hosts.items() if h['writable']}, WRITABLE)
        for name in PATTERN:
            self.assertIn('pattern', hosts[name]['reason'])
        for host in hosts.values():
            self.assertEqual((host['field'], host['acknowledgement']), ('hd2.fields.attack.projectile',
                'allow_unverified_effect'))
            self.assertEqual(host['api'], "hd2.stratagem('" + host['stratagem'] + "'):attack('primary'):projectile_source()")
        # The mounted vehicles are unchanged: the hosts are a separate list.
        self.assertFalse(any('Sentry' in v['vehicle'] or 'Emplacement' in v['vehicle'] for v in public['vehicles']))


class ApiTests(unittest.TestCase):
    def test_swaps_validate_with_the_acknowledgement_and_refuse_blocked_hosts(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local source=hd2.stratagem('A/AC-8 Autocannon Sentry'):attack('primary'):projectile_source()
assert(source.writable and source.status=='ACTIVE_DIRECT'and source.mechanism=='component',source.reason)
assert(source.field=='attack.projectile'and source.target.resource=='vehicle_weapon'
    and source.target.weapon=='A/AC-8 Autocannon Sentry / weapon')
assert(source.acknowledgements[1]=='allow_unverified_effect'and#source.acknowledgements==1)
local function swap(src,value,extra)
    local request={id='s',target=src.target,field=hd2.fields.attack.projectile,expect=src.expect,value=value,
        allow_unverified_effect=true,allow_unverified_reference=true}
    for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
    return patches.validate(request)
end
-- A same-class donor (explosive impact): the donor's package is a dependency.
local spec=swap(source,hd2.weapon('R-36 Eruptor'):attack('primary'):projectile())
assert(spec.asset_dependencies and#spec.asset_dependencies>=1,'donor package dependency missing')
-- Restoring the host's own round is its reviewed baseline: no acknowledgement.
assert(swap(source,source.expect,{allow_unverified_effect=false,allow_unverified_reference=false})
    .changes[1].self_reference)
-- Every donor needs allow_unverified_effect (no type-level sentry swap is live-tested).
rejects(function()swap(source,hd2.weapon('R-36 Eruptor'):attack('primary'):projectile(),
    {allow_unverified_effect=false})end,'allow_unverified_effect')
-- The emplacements are hosts too.
local hmg=hd2.stratagem('E/MG-101 HMG Emplacement'):attack('primary'):projectile_source()
assert(hmg.writable)
swap(hmg,hd2.weapon('LAS-58 Talon'):attack('primary'):projectile())
-- The pattern-fed sentries stay blocked, with the reason.
for _,name in ipairs({'A/MG-43 Machine Gun Sentry','A/G-16 Gatling Sentry'})do
    local blocked=hd2.stratagem(name):attack('primary'):projectile_source()
    assert(not blocked.writable and blocked.reason:find('pattern',1,true),name)
    rejects(function()patches.validate{id='x',target={resource='vehicle_weapon',path='attack',weapon=name..' / weapon',
        attack='primary'},field=hd2.fields.attack.projectile,expect={resource='vehicle_weapon',
        path='projectile_reference',weapon=name..' / weapon',attack='primary'},
        value=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile(),allow_unverified_effect=true,
        allow_unverified_reference=true}end,'read-only')
end
-- A stratagem without a host answers with a reason, never a target.
local none=hd2.stratagem('A/LAS-98 Laser Sentry'):attack('primary'):projectile_source()
assert(not none.writable and none.target==nil)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
