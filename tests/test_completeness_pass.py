"""Movement restrictions, Cremator / EAT-17 identity and damage, and mine / defensive stratagem coverage."""
import importlib.util
import json
import re
import sys
import unittest

from support import ROOT, run

sys.path.insert(0, str(ROOT / 'scripts'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WeaponMovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/weapon-movement-F5FEE03DCFDB.json').read_text())
        cls.catalog = json.loads((ROOT / 'sdk/WeaponMovementCapabilities.json').read_text())
        cls.weapons = {w['name']: w for w in cls.research['weapons']}

    def test_generated_catalog_is_current_and_sanitized(self):
        self.assertFalse(load('generate_weapon_movement').generate(check=True))
        self.assertEqual(self.catalog['contract'], 'hd2runtime.weapon_movement.v1')
        self.assertNotRegex(json.dumps(self.catalog), re.compile(r'0x[0-9a-fA-F]{8,}'))
        self.assertFalse(self.catalog['liveTested'])
        self.assertEqual(self.catalog['summary']['weapons'], 114)   # 7 more (0.30.2: the seven DUPLICATE weapons resolved to their proven roots, research/weapon-roots)
        self.assertEqual(self.catalog['summary']['writable'], 112)

    def test_native_model(self):
        summary = self.research['summary']
        self.assertEqual(summary['stationaryWhileFiring'], ['M-1000 Maxigun'])
        self.assertEqual(summary['braceEvents'], ['GL-28 Belt-Fed Grenade Launcher', 'M-1000 Maxigun'])
        self.assertEqual(summary['withWeaponData'], 112)
        self.assertEqual(summary['uniqueWeaponDataOwners'], 112)
        fingerprint = {(m['offset'], m['size'], m['storage'], m['nameLength'])
            for m in self.research['model']['fingerprint']}
        self.assertIn((387, 1, 'UINT8', 23), fingerprint)
        self.assertIn((388, 4, 'UINT32', 42), fingerprint)
        code = self.research['codeEvidence']
        self.assertEqual((code['stationaryReader']['count'], code['stationaryReader']['actionBit']), (1, 55))
        # The Cremator's exclusive flag is audio, not movement: read inside the weapon RTPC update.
        audio = code['audioFlagReader']
        self.assertTrue(audio['readsWeaponDataFromSameGetter'])
        self.assertIn('weapon_rpm', audio['rtpcStrings'])
        self.assertTrue(self.weapons['B/FLAM-80 Cremator']['audioFlag1220'])
        self.assertFalse(self.weapons['B/FLAM-80 Cremator']['stationaryWhileFiring'])
        # Maxigun and GL-28 differ in movement-related data only by the stationary flag.
        maxigun, gl28 = self.weapons['M-1000 Maxigun'], self.weapons['GL-28 Belt-Fed Grenade Launcher']
        for key in ('firingStartEvent', 'firingStopEvent', 'perShotWielderAnimation'):
            self.assertEqual(maxigun[key], gl28[key], key)
        self.assertEqual((maxigun['firingStartEvent'], maxigun['firingStopEvent']), ('brace', 'brace_exit'))
        states = [s['state'] for s in self.research['avatarLocomotionStates']]
        self.assertEqual(states, ['stand', 'crouch', 'prone', 'stand_limp', 'crouch_limp', 'swim', 'march',
            'land_heavy'])
        unavailable = {item['behaviour'] for item in self.catalog['model']['unavailable']}
        self.assertIn('movement speed multiplier while firing', unavailable)
        self.assertIn('Cremator slowdown', unavailable)

    def test_field_baselines_transitions_and_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local F=hd2.fields.weapon.stationary_while_firing
assert(F=='weapon.stationary_while_firing')
local function rejects(request,needle)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(needle,1,true),tostring(why))
end
local maxigun=hd2.support_weapon('M-1000 Maxigun')
-- stationary -> unrestricted (GL-28-style weapon data)
local spec=patches.validate{id='mobile',target=maxigun,field=F,expect=true,value=false,allow_unverified_effect=true}
local backing=spec.changes[1].descriptor.backing
assert(backing.component=='WeaponDataComponentData' and backing.offset==387 and backing.storage=='u8')
rejects({id='mobile-ack',target=maxigun,field=F,expect=true,value=false},'allow_unverified_effect')
rejects({id='mobile-conflict',target=maxigun,field=F,expect=false,value=true,allow_unverified_effect=true},'')
rejects({id='mobile-type',target=maxigun,field=F,expect=true,value=0,allow_unverified_effect=true},'boolean')
-- slowed (GL-28) and unrestricted weapons start false; making them stationary is a supported transition
patches.validate{id='gl28',target=hd2.support_weapon('GL-28 Belt-Fed Grenade Launcher'),field=F,
 expect=false,value=true,allow_unverified_effect=true}
patches.validate{id='liberator',target=hd2.weapon('AR-23 Liberator'),field=F,expect=false,value=true,
 allow_unverified_effect=true}
-- code-driven behaviour has no field
assert(hd2.fields.weapon.movement_multiplier==nil and hd2.fields.weapon.can_dive==nil)
return 'ok'
''')

    def test_weapon_local_ownership(self):
        player = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
        fields = [f for w in player['weapons'] for f in w['fields']
            if f['semanticFieldId'] == 'weapon.stationary_while_firing']
        self.assertEqual(len(fields), 80)
        self.assertTrue(all(f['writeScope'] == 'weapon_local' and f['acknowledgement'] == 'allow_unverified_effect'
            for f in fields))
        support = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())
        fields = {f['supportWeapon']: f for f in support['fieldInstances']
            if f['semanticFieldId'] == 'weapon.stationary_while_firing'}
        self.assertEqual(len(fields), 32)
        self.assertTrue(fields['M-1000 Maxigun']['value']['baseline'])
        self.assertFalse(fields['B/FLAM-80 Cremator']['value']['baseline'])
        self.assertEqual(fields['M-1000 Maxigun']['operation']['acknowledgement'], 'allow_unverified_effect')


class CrematorAndEatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.support = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())
        cls.delivery = json.loads((ROOT / 'research/support-weapon-coverage-F5FEE03DCFDB.json').read_text())[
            'deliveryResolution']

    def fields(self, weapon):
        return {(f['target']['attackRole'] or 'weapon', f['semanticFieldId']): f for f in self.support['fieldInstances']
            if f['supportWeapon'] == weapon}

    def test_identity_is_structural(self):
        cremator = self.delivery['B/FLAM-80 Cremator']
        paths = cremator['structuralConfirmation']['paths']
        self.assertIn('heavy_flamethrower', paths[cremator['deliveredRoot']])
        self.assertTrue(any('combat_walker_flamethrower' in (p or '') for r, p in paths.items()
            if r != cremator['deliveredRoot']))
        self.assertIn('lat_oneshot', self.delivery['EAT-17 Expendable Anti-Tank']['structuralConfirmation']['paths'][
            self.delivery['EAT-17 Expendable Anti-Tank']['deliveredRoot']])

    def test_cremator_damage_chain(self):
        fields = self.fields('B/FLAM-80 Cremator')
        expected = {('primary', 'damage.standard_damage'): 3, ('primary', 'damage.durable_damage'): 3,
            ('primary', 'damage.ap_direct'): 4, ('primary_status_5', 'status.strength'): 3,
            ('primary_status_5', 'status.duration'): 3}
        for key, value in expected.items():
            self.assertEqual(fields[key]['value']['baseline'], value, key)
        duration = fields[('primary_status_5', 'status.duration')]
        consumers = {c['weapon'] for c in duration['sharedScope']['affectedSemanticConsumers']}
        self.assertEqual(consumers, {'B/FLAM-80 Cremator', 'EAT-700 Expendable Napalm', 'FLAM-40 Flamethrower',
            'LAS-98 Laser Cannon'})
        self.assertTrue(duration['sharedScope']['requiresAcknowledgement'])
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local attack=hd2.support_weapon('B/FLAM-80 Cremator'):attack('primary')
assert(not pcall(patches.validate,{id='c',target=attack,field=hd2.fields.damage.player_standard_damage,expect=3,value=5}))
patches.validate{id='c2',target=attack,allow_shared=true,field=hd2.fields.damage.player_standard_damage,expect=3,value=5}
return 'ok'
''')

    def test_eat17_projectile_and_explosion(self):
        fields = self.fields('EAT-17 Expendable Anti-Tank')
        expected = {('primary', 'projectile.velocity'): 200, ('primary', 'projectile.mass'): 2500,
            ('primary', 'damage.standard_damage'): 2000, ('primary', 'damage.durable_damage'): 2000,
            ('primary', 'damage.ap_direct'): 6, ('primary', 'damage.ap_extreme'): 3,
            ('primary_impact', 'explosion.inner_radius'): 1.5, ('primary_impact', 'explosion.outer_radius'): 3,
            ('primary_impact', 'explosion.damage.standard_damage'): 150}
        for key, value in expected.items():
            self.assertEqual(fields[key]['value']['baseline'], value, key)
        by_name = {w['name']: w for w in self.support['weapons']}
        branches = {b['name']: b for b in by_name['EAT-17 Expendable Anti-Tank']['attackBranches']}
        self.assertEqual(branches['EAT-17 BACKBLAST E']['state'], 'PARTIAL')   # BackblastComponent not mapped
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local eat=hd2.support_weapon('EAT-17 Expendable Anti-Tank')
patches.validate{id='e',target=eat:attack('primary_impact'):explosion(),allow_shared=true,
 field=hd2.fields.explosion.outer_radius,expect=3,value=5}
patches.validate{id='e2',target=eat:attack('primary'):projectile(),allow_shared=true,
 field=hd2.fields.damage.player_standard_damage,expect=2000,value=3000}
return 'ok'
''')


class DefensiveStratagemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.research = json.loads((ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json').read_text())

    def fields(self, stratagem):
        return {(f['target'].get('attack') or f['target']['path'], f['semanticFieldId']): f
            for f in self.catalog['fieldInstances'] if f['target'].get('stratagem') == stratagem}

    def test_mine_chains(self):
        chains = {s['name']: s['mineChain'] for s in self.research['stratagems'] if s.get('mineChain')}
        self.assertEqual(set(chains), {'MD-6 Anti-Personnel Minefield', 'MD-I4 Incendiary Mines',
            'MD-17 Anti-Tank Mines', 'MD-8 Gas Mines'})
        for name, chain in chains.items():
            self.assertTrue(chain['minefield']['uniqueOwner'], name)
            mine = chain['thrownMine']
            if mine['entityDefined']:
                self.assertEqual(mine['explosive']['explosionType'], chain['minefield']['explosionType'], name)
                self.assertEqual(mine['explosive']['explosionDelay'], 0.002, name)
        self.assertFalse(chains['MD-17 Anti-Tank Mines']['thrownMine']['entityDefined'])
        self.assertIn('reason', chains['MD-6 Anti-Personnel Minefield']['readOnlyObservations'])

    def test_representative_minefield(self):
        fields = self.fields('MD-6 Anti-Personnel Minefield')
        self.assertEqual(fields[('mine', 'explosion.outer_radius')]['currentDefault'], 5.0)
        self.assertEqual(fields[('mine_damage', 'explosion.damage.standard_damage')]['currentDefault'], 700)
        self.assertEqual(fields[('deployed_entity', 'entity.health')]['currentDefault'], 250)
        self.assertTrue(fields[('mine', 'explosion.outer_radius')]['allowSharedRequired'])
        consumers = fields[('mine', 'explosion.outer_radius')]['sharedConsumers']
        self.assertTrue(any(c.get('path') == 'ExplosiveComponentData+36' for c in consumers))
        gas = self.fields('MD-8 Gas Mines')
        self.assertEqual(gas[('mine_damage_status_1', 'status.strength')]['currentDefault'], 100.0)
        at = self.fields('MD-17 Anti-Tank Mines')
        self.assertEqual(at[('mine_damage', 'explosion.damage.standard_damage')]['currentDefault'], 2000)
        blocked = {b['field'] for s in self.catalog['stratagems'] if s['name'] == 'MD-6 Anti-Personnel Minefield'
            for b in s['deployedEntity']['blockedFields']}
        self.assertIn('mine count / spacing', blocked)
        self.assertIn('mine trigger radius / arming time', blocked)
        self.assertEqual(self.catalog['summary']['mineExplosionsResolved'], 4)

    def test_turret_emplacement_health_ammo_fire_rate(self):
        mortar = self.fields('A/M-12 Mortar Sentry')
        self.assertEqual(mortar[('deployed_entity', 'entity.health')]['currentDefault'], 400)
        self.assertEqual(mortar[('deployed_entity', 'entity.armor')]['currentDefault'], 2)
        self.assertIn(('primary_impact', 'explosion.outer_radius'), mortar)
        hmg = self.fields('E/MG-101 HMG Emplacement')
        self.assertIn(('deployed_entity', 'entity.health'), hmg)
        self.assertTrue(any(key[1] in ('weapon.capacity', 'weapon.fire_rate') for key in hmg))

    def test_runtime_root_link_is_published(self):
        run(r'''
local db=require('hd2runtime/domains/stratagem_authoring')
local entry=db.stratagems['MD-6 Anti-Personnel Minefield']
local link=assert(entry.rootComponentLink)
assert(link.component=='MinefieldComponentData' and link.offset==24 and link.expect==366
 and link.node=='mine:primary/attack:mine')
assert(db.stratagems['A/M-12 Mortar Sentry'].rootComponentLink==nil)
return 'ok'
''')


class MigrationTests(unittest.TestCase):
    def test_mine_root_links_are_relationships(self):
        from migration import source
        tables = source.load_tables(source.resolve_ref('current'))
        links = [link for link in source.relationships(tables) if link['kind'] == 'component_value']
        mines = [link for link in links if link['key'].startswith('stratagem-component-link:')]
        self.assertEqual(len(mines), 4)
        self.assertEqual({link['component'] for link in mines}, {'MinefieldComponentData'})
        # The other component values guard ammunition sources: each weapon's default customization must still name
        # the ammunition whose delta owns its fired projectile. 0.30.4: and the LAS-5 Scythe's beam attachment source
        # (its default muzzle Laser. Standard Prism, whose delta owns its fired beam).
        beams = [link for link in links if link['key'].startswith('beam-attachment-default:')]
        self.assertEqual([link['key'] for link in beams], ['beam-attachment-default:player_weapon:LAS-5 Scythe'])
        self.assertEqual(beams[0]['component'], 'WeaponCustomizationComponentData')
        ammunition = [link for link in links if link not in mines and link not in beams]
        self.assertEqual(len(ammunition), 6)
        self.assertTrue(all(link['key'].startswith('ammunition-default:')
            and link['component'] == 'WeaponCustomizationComponentData' for link in ammunition))

    def test_component_value_fails_closed(self):
        from migration import engine

        class Table:
            def __init__(self, member):
                self.layout = type('L', (), {'member_at': lambda _, offset: member})()

        class View:
            def __init__(self, value, member):
                self.value, self.table = value, Table(member)

            def record(self, component, resource):
                return {'bytes': bytes(24) + self.value.to_bytes(4, 'little') + bytes(16)}

            def component(self, name):
                return self.table

        member = {'offset': 24, 'size': 4, 'storage': 'ENUM_UINT32', 'nameLength': 14}
        check = engine.Engine.__new__(engine.Engine)
        check.S = View(366, member)
        link = {'component': 'MinefieldComponentData', 'resource': 1, 'offset': 24, 'expect': 366}
        self.assertEqual(check._rel_component_value(View(366, member), link)[0], 'INTACT')
        self.assertEqual(check._rel_component_value(View(358, member), link)[0], 'BROKEN')
        moved = dict(member, nameLength=15)
        self.assertEqual(check._rel_component_value(View(366, moved), link)[0], 'BROKEN')


if __name__ == '__main__':
    unittest.main()
