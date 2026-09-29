import json
import sys
import unittest

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_weapon_modes
import generate_weapon_presentation
import validate_packaged_runtime


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


class WeaponModeResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = load('research/weapon-functions-F5FEE03DCFDB.json')
        cls.presentation = load('research/weapon-presentation-F5FEE03DCFDB.json')
        cls.composition = load('research/output-composition-F5FEE03DCFDB.json')
        cls.rows = {(row['kind'], row['weapon']): row for row in cls.functions['weapons']}

    def test_rate_slots_and_selector_model(self):
        layout = {(item['struct'], item['offset']): item['member'] for item in self.functions['typeLibrary']}
        self.assertEqual(layout[('ProjectileWeaponComponent', 4)], 'rounds_per_minute')
        self.assertEqual(layout[('ProjectileWeaponComponent', 576)], 'weapon_function_projectile_type')
        self.assertEqual(layout[('WeaponRoundsAmmoType', 4)], 'alternate_projectile_type')
        proofs = {group: [p['asm'] for p in rows] for group, rows in self.functions['proofs'].items() if isinstance(rows, list)}
        self.assertIn('cmp r9d, 3', proofs['rateOfFireSelector'])
        self.assertIn('mov eax, dword ptr [r13 + 0x240]', proofs['programmableAmmo'])
        self.assertEqual(self.functions['proofs']['weaponFunctionDispatch']['targets']['ROF'], '0x755C7D')
        hmg = self.rows[('support', 'MG-206 Heavy Machine Gun')]['fireRate']
        self.assertEqual((hmg['slots'], hmg['modes'], hmg['state']),
            ({'x': 450.0, 'y': 600.0, 'z': 750.0}, [600.0, 750.0, 450.0], 'selectable'))
        tenderizer = self.rows[('player', 'AR-61 Tenderizer')]['fireRate']
        self.assertEqual((tenderizer['modes'], tenderizer['selectorInput']), ([600.0, 850.0], 'left'))
        liberator = self.rows[('player', 'AR-23 Liberator')]
        self.assertEqual((liberator['fireRate']['state'], liberator['fireRate']['bindableInputs']), ('addable', ['left']))
        self.assertEqual(liberator['fireRate']['overriddenWhenEquipped'], ['Recoil Spring Liberator'])
        # Every built weapon observed in the mission snapshots holds its settings' slots and starts on Y.
        seeded = [r for o in self.functions['observations'] for r in o['rateOfFire'] if r.get('settingsRpm')]
        self.assertGreaterEqual(len(seeded), 20)
        self.assertTrue(all(r['matchesSettings'] and r['index'] == 1 for r in seeded if any(r['rpm'])))

    def test_feeds_and_programmable_ammo(self):
        halt = self.rows[('player', 'SG-20 Halt')]['feeds']
        self.assertEqual((halt['selectorInput'], halt['primary']['ownedBy'], halt['alternate']['ownedBy']),
            ('left', 'SHOTGUN 10g. FLECHETTES', 'SHOTGUN 10g. Stun ALTERNATE'))
        native = {w for (kind, w), row in self.rows.items() if (row.get('functionAmmo') or {}).get('state') == 'native'}
        self.assertEqual(native, {'AC-8 Autocannon', 'GR-8 Recoilless Rifle', 'RL-77 Airburst Rocket Launcher'})
        spear = self.rows[('support', 'S-11 Speargun')]['functionAmmo']
        self.assertEqual((spear['state'], spear['bindableInputs']), ('addable', ['left']))

    def test_presentation_model(self):
        labels = self.presentation['penetrationLabels']
        self.assertEqual({key: value['label'] for key, value in labels.items()}, {
            'light': 'LIGHT ARMOR PENETRATING', 'medium': 'MEDIUM ARMOR PENETRATING', 'heavy': 'HEAVY ARMOR PENETRATING',
            'light_anti_tank': 'LIGHT ANTI-TANK', 'anti_tank': 'ANTI-TANK'})
        self.assertEqual(self.presentation['summary']['sharedLoadoutEntries'], 0)
        builder = [p['asm'] for p in self.presentation['proofs']['traitBuilder']]
        self.assertIn('cmp ebp, 5', builder)
        rows = {(r['kind'], r['weapon']): r for r in self.presentation['weapons']}
        self.assertEqual(rows[('player', 'AR-23C Liberator Concussive')]['armorPenetration'], 'light')
        self.assertEqual(rows[('player', 'SG-20 Halt')]['armorPenetrationState'], 'blocked')

    def test_cross_family_verdicts(self):
        self.assertEqual({v['donor']: v['status'] for v in self.composition['verdicts']},
            {'LAS-5 Scythe': 'blocked', 'LAS-98 Laser Cannon': 'blocked', 'LAS-13 Trident': 'blocked'})
        self.assertEqual(self.composition['membership']['nonZeroGaps'], 0)
        self.assertEqual(self.composition['membership']['host']['slackBytes'], 0)
        ids = {b['id'] for b in self.composition['blockers']}
        self.assertEqual(ids, {'MEMBERSHIP_PACKED', 'COMPONENT_INDEX_HASHED', 'TRIGGER_PREFERS_PROJECTILE',
            'BEAM_IS_ENTITY_STATE', 'NO_PRE_FIRE_HOOK', 'REFERENCE_FAMILY'})
        self.assertEqual([p['weapon'] for p in self.composition['ownership']['magazineFedBeams']], ['40-K Meltagun'])


class WeaponModeCatalogTests(unittest.TestCase):
    def test_generated_outputs_are_current_and_sanitized(self):
        self.assertFalse(generate_weapon_modes.generate(check=True))
        self.assertFalse(generate_weapon_presentation.generate(check=True))
        for path in ('sdk/WeaponFireRateCapabilities.json', 'sdk/WeaponFeedCapabilities.json',
                'sdk/OutputCompositionCapabilities.json', 'sdk/WeaponPresentationCapabilities.json'):
            text = (ROOT / path).read_text(encoding='utf-8')
            self.assertNotIn('0x', text, path)
        rates = load('sdk/WeaponFireRateCapabilities.json')
        self.assertEqual(rates['summary']['writable'], 60)
        self.assertEqual(rates['maxSlots'], 3)
        feeds = load('sdk/WeaponFeedCapabilities.json')['summary']
        self.assertEqual(feeds['roundsDualFeeds'], ['SG-20 Halt'])
        self.assertIn('S-11 Speargun', feeds['programmableAddable'])
        self.assertEqual(feeds['programmableNativeWritable'],
            ['AC-8 Autocannon', 'GR-8 Recoilless Rifle', 'RL-77 Airburst Rocket Launcher'])
        presentation = load('sdk/WeaponPresentationCapabilities.json')
        self.assertEqual([c['value'] for c in presentation['penetrationChoices']],
            ['none', 'light', 'medium', 'heavy', 'light_anti_tank', 'anti_tank'])
        self.assertEqual(presentation['summary']['armorPenetrationWritable'], 100)
        composition = load('sdk/OutputCompositionCapabilities.json')
        self.assertFalse(composition['beamAction']['available'])

    def test_lua_guards_and_api(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local w=require('hd2runtime/domains/player_weapon_writes')
local b=require('hd2runtime/core/bytes')
local F=hd2.fields
local function rejected(fn,needle)
 local ok,why=pcall(fn);assert(not ok,'accepted');assert(tostring(why):find(needle,1,true),tostring(why))
end
local hmg=hd2.support_weapon('MG-206 Heavy Machine Gun')
local modes=hmg:fire_rate_modes()
assert(modes.state=='selectable'and modes.modes[1].rpm==600 and modes.modes[1].slot=='y'and modes.modes[3].slot=='x')
assert(hmg:fire_rate_mode(2).rpm==750)
local spec=w.validate_patch({id='h',target=hmg,field=F.fire_rate.modes,expect={600,750,450},value={200,700,1400},
 allow_unverified_effect=true})
assert(b.hex(spec.changes[1].desired)==b.hex(b.encode(1400,'f32')..b.encode(200,'f32')..b.encode(700,'f32')))
rejected(function()w.validate_patch({id='h',target=hmg,field=F.fire_rate.modes,expect={600,750,450},
 value={1,2,3,4},allow_unverified_effect=true})end,'lists 4 rates')
local lib=hd2.weapon('AR-23 Liberator')
local rates=lib:fire_rate_modes()
assert(rates.state=='addable'and rates.binding.field=='weapon_function.left')
rejected(function()w.validate_patch({id='l',target=lib,field=F.fire_rate.modes,expect={640},value={450,700},
 allow_unverified_effect=true})end,'SELECTOR_REQUIRED')
rejected(function()w.validate_patch({id='l',target=lib,field=F.weapon_function.left,expect='none',
 value='rate_of_fire',allow_unverified_effect=true})end,'SELECTOR_REQUIRED')
rejected(function()w.validate_patch({id='l',target=lib,field=F.weapon_function.left,expect='none',
 value='magazine',allow_unverified_effect=true})end,'cannot bind')
w.validate_transaction({id='l',target=lib,allow_unverified_effect=true,changes={
 {field=F.fire_rate.modes,expect={640},value={450,700,950}},{field=F.weapon_function.left,expect='none',
 value='rate_of_fire'}}})
local spear=hd2.support_weapon('S-11 Speargun')
local source=spear:feed('programmable'):source()
assert(source.writable and source.expect=='none'and source.binding.value=='programmable_ammo')
rejected(function()w.validate_transaction({id='s',target=spear,allow_unverified_effect=true,changes={
 {field=F.weapon_function.left,expect='none',value='programmable_ammo'},
 {field=F.function_ammo.projectile,expect='none',value=hd2.attack_output('GL-52 De-Escalator')}}})end,
 'allow_unverified_reference')
rejected(function()w.validate_transaction({id='s',target=spear,allow_unverified_effect=true,
 allow_unverified_reference=true,changes={{field=F.weapon_function.left,expect='none',value='programmable_ammo'},
 {field=F.function_ammo.projectile,expect='none',value=hd2.attack_output('LAS-98 Laser Cannon')}}})end,
 'INCOMPATIBLE_OUTPUT_FAMILY')
local ac8=hd2.support_weapon('AC-8 Autocannon')
local own=ac8:feed('programmable'):projectile()
assert(own.path=='function_projectile')
w.validate_patch({id='a',target=ac8,field=F.function_ammo.projectile,expect=own,value=own,allow_unverified_effect=true})
local halt=hd2.weapon('SG-20 Halt')
local feeds=halt:feeds()
assert(#feeds==2 and feeds[2]:describe().capacityField=='rounds.feed_capacity_2'and not feeds[2]:source().writable)
assert(feeds[1]:projectile().attack=='feed_primary')
local con=hd2.weapon('AR-23C Liberator Concussive')
local shown=con:presentation()
assert(shown.armorPenetration=='light'and shown.traits[1].label=='LIGHT ARMOR PENETRATING')
local label=w.validate_patch({id='c',target=con,field=F.presentation.armor_penetration,expect='light',value='medium',
 allow_unverified_effect=true})
assert(b.hex(label.changes[1].desired):sub(1,8)=='47c0e2b7')
rejected(function()w.validate_patch({id='c',target=con,field=F.presentation.traits,expect={'light_armor_penetrating'},
 value={'stun','stun'},allow_unverified_effect=true})end,'twice')
rejected(function()w.validate_patch({id='c',target=halt,field=F.presentation.armor_penetration,expect='light',
 value='heavy',allow_unverified_effect=true})end,'read-only')
-- Mod Options: a semantic-name choice and sliders inside a list value are accepted.
local page=hd2.options({id='modes_test',title='Modes Test'})
local choice=page:choice({id='label',label='Label',choices={'Light','Heavy'},values={'light','heavy'}})
assert(choice:get()=='light')
return 'ok'
'''), b'ok')

    def test_validation_and_scenarios(self):
        result = load('validation/weapon-modes-snapshot.json')
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual((result['rates']['checked'], result['rates']['added']), (60, 56))
        self.assertEqual((result['functions']['checked'], result['functions']['native']), (52, 3))
        self.assertEqual((result['presentation']['checked'], result['presentation']['traits']), (100, 103))
        self.assertEqual(result['hmg']['slots'], ['0000e143>0000af44', '00001644>00004843', '00803b44>00002f44'])
        self.assertIn('WeaponDataComponentData+184=02000000', result['liberator']['written'])
        self.assertEqual(result['speargun']['written'],
            ['ProjectileWeaponComponentData+576=de000000', 'WeaponDataComponentData+184=08000000'])
        self.assertEqual(result['concussive']['written'], [{'after': '47c0e2b7', 'before': '1541ef11', 'offset': 12}])
        self.assertTrue(result['overlapRejected'])
        self.assertGreaterEqual(result['adversarialRejections'], 900)
        for name in ('example-hmgfire-rate-modes-test', 'example-added-fire-rate-mode-test',
                'example-speargun-gas-stun-test', 'example-weapon-presentation-test', 'example-halt-feed-test'):
            self.assertIn(name, validate_packaged_runtime.SCENARIOS)
        self.assertEqual(validate_packaged_runtime.EXTRAS['example-speargun-gas-stun-test']['packageRequests'], 3)


if __name__ == '__main__':
    unittest.main()
