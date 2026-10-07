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

    def test_stun_field_donors(self):
        """A stun field is an explosion's persistent status volume (StaticField); only the EMS Mortar shell is a
        donor a ProgrammableAmmo host can fire; the G-23 is an entity, the orbital shell a Bombardment member."""
        research = load('research/stun-field-donors-F5FEE03DCFDB.json')
        members = {(m['struct'], m['offset']): m for m in research['typeLibrary']}
        self.assertEqual((members[('ExplosionInfo', 100)]['member'], members[('ExplosionInfo', 100)]['type']),
            ('persistent_status_volume', 'StatusEffectTemplateType'))
        self.assertEqual(members[('ExplosionInfo', 104)]['storage'], 'FP32')
        self.assertEqual(research['templates']['15'], 'StaticField')
        decisions = {c['id']: c['decision'] for c in research['candidates']}
        self.assertEqual(decisions, {'speargun_gas': 'control', 'ems_mortar': 'supported', 'orbital_ems': 'blocked',
            'artillery_ems': 'blocked', 'unowned_static_field': 'blocked', 'g23_stun': 'not_a_projectile',
            'emp_grenade': 'not_a_projectile', 'gl52_arc': 'supported_not_a_field'})
        candidates = {c['id']: c for c in research['candidates']}
        gas = [c for c in candidates['speargun_gas']['chain'] if c['volume']]
        self.assertEqual((gas[0]['volume'], gas[0]['volumeSeconds']), ('Gas', 10))
        self.assertEqual(candidates['g23_stun']['explosion']['volume'], None)
        [donor] = research['donors']
        self.assertEqual((donor['name'], donor['projectileType'], donor['field']['volume'], donor['field']['volumeSeconds'],
            donor['field']['radii'][1]), ('A/M-23 EMS Mortar Sentry', 154, 'StaticField', 7, 10))
        self.assertEqual(donor['field']['damage']['status'], [{'status': 'stun_medium', 'strength': 100}])
        self.assertTrue(donor['componentIdentity']['uniqueOwner'] and donor['package']['inBundleDatabase'])
        self.assertEqual(donor['package']['name'], 'packages/generated/loadout/mortar_turret_staticfield')

    def test_mode_presentation_model(self):
        """Weapon-function mode labels and icons are the fired projectile's ProjectileInfo +12 / +16: every native
        mode reads as them, and unlabelled projectiles share the placeholder label and the skull icon."""
        modes = self.presentation['modes']
        layout = {m['offset']: (m['nameLength'], m['storage']) for m in modes['typeLibrary']}
        self.assertEqual(layout, {4: (10, 'UINT32'), 8: (10, 'UINT32'), 12: (10, 'UINT32'), 16: (8, 'UINT64')})
        projectiles = modes['projectiles']
        self.assertEqual([(projectiles[t]['label'], projectiles[t]['icon']) for t in ('115', '284', '153', '36',
            '183', '191')], [('aphet', 'ammo_aphet'), ('flak', 'ammo_flak'), ('heat', 'ammo_heat'), ('he', 'ammo_he'),
            ('flechettes', 'ammo_flechettes'), ('stun', 'ammo_stun')])
        self.assertEqual((projectiles['125']['label'], projectiles['125']['icon']), (None, 'default'))
        self.assertEqual((projectiles['154']['label'], projectiles['154']['icon']), (None, 'default'))
        self.assertEqual(modes['placeholderLabel'], 'F1CD5269')
        labels = {l['semanticId']: l for l in modes['labels']}
        self.assertEqual((labels['gas']['nativeId'], labels['gas']['nativeUse'], labels['gas']['languages']),
            ('ED94AE1A', False, 15))
        self.assertEqual(labels['stun']['nativeId'], '7C0337D9')
        self.assertFalse(labels['stun_18af731b']['offered'])
        icons = {i['semanticId']: i for i in modes['icons'] if i['semanticId']}
        self.assertEqual(icons['default']['path'], 'content/ui/shared/misc/skull_icon')
        self.assertEqual(len(icons), 15)

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
        self.assertEqual(rates['summary']['writable'], 61)   # the wind-up Maxigun included
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
-- Weapon-menu order: the slots X, Y, Z; the default is Y and the selector visits Y -> Z -> X.
assert(modes.state=='selectable'and#modes.modes==3 and#modes.slots==3)
assert(modes.modes[1].rpm==450 and modes.modes[1].slot=='x'and modes.modes[1].menu==1 and modes.modes[1].presses==2)
assert(modes.modes[2].rpm==600 and modes.modes[2].default and modes.modes[2].presses==0)
assert(modes.modes[3].slot=='z'and modes.modes[3].presses==1 and modes.default.slot=='y')
assert(table.concat(modes.selectorOrder,',')=='y,z,x'and table.concat(modes.expect,',')=='450,600,750')
assert(hmg:fire_rate_mode(3).rpm==750 and hmg:fire_rate_mode('x').rpm==450)
local spec=w.validate_patch({id='h',target=hmg,field=F.fire_rate.modes,expect={450,600,750},value={1400,200,700},
 allow_unverified_effect=true})
assert(b.hex(spec.changes[1].desired)==b.hex(b.encode(1400,'f32')..b.encode(200,'f32')..b.encode(700,'f32')))
rejected(function()w.validate_patch({id='h',target=hmg,field=F.fire_rate.modes,expect={450,600,750},
 value={1,2,3,4},allow_unverified_effect=true})end,'got 4 entries')
rejected(function()w.validate_patch({id='h',target=hmg,field=F.fire_rate.modes,expect={600,750,450},
 value={450,600,750},allow_unverified_effect=true})end,'weapon-menu order')
rejected(function()w.validate_patch({id='h',target=hmg,field=F.fire_rate.modes,expect={450,600,750},
 value={450,0,750},allow_unverified_effect=true})end,'cannot be empty')
-- An empty X or Z is a mode the menu and the selector skip.
w.validate_patch({id='h',target=hmg,field=F.fire_rate.modes,expect={450,600,750},value={0,600,750},
 allow_unverified_effect=true})
local tenderizer=hd2.weapon('AR-61 Tenderizer'):fire_rate_modes()
assert(#tenderizer.modes==2 and tenderizer.modes[1].slot=='y'and tenderizer.modes[1].menu==1
 and tenderizer.modes[2].presses==1 and not tenderizer.slots[1].enabled and tenderizer.slots[1].menu==nil)
local lib=hd2.weapon('AR-23 Liberator')
local rates=lib:fire_rate_modes()
assert(rates.state=='addable'and rates.binding.field=='weapon_function.left')
assert(table.concat(rates.expect,',')=='0,640,0'and#rates.modes==1 and rates.modes[1].slot=='y')
rejected(function()w.validate_patch({id='l',target=lib,field=F.fire_rate.modes,expect={0,640,0},value={450,700,0},
 allow_unverified_effect=true})end,'SELECTOR_REQUIRED')
rejected(function()w.validate_patch({id='l',target=lib,field=F.weapon_function.left,expect='none',
 value='rate_of_fire',allow_unverified_effect=true})end,'SELECTOR_REQUIRED')
rejected(function()w.validate_patch({id='l',target=lib,field=F.weapon_function.left,expect='none',
 value='magazine',allow_unverified_effect=true})end,'cannot bind')
w.validate_transaction({id='l',target=lib,allow_unverified_effect=true,changes={
 {field=F.fire_rate.modes,expect={0,640,0},value={450,700,950}},{field=F.weapon_function.left,expect='none',
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
-- Mode presentation (domains/output_writes.lua): native labels and icons on attack outputs.
local presenter=require('hd2runtime/domains/output_writes')
local gas_output=hd2.attack_output('S-11 Speargun')
local mode=presenter.validate_transaction({id='m',target=gas_output,allow_unverified_effect=true,changes={
 {field=F.presentation.mode_label,expect='none',value='gas'},{field=F.presentation.mode_icon,expect='default',
 value='ammo_stun'}}})
assert(b.hex(mode.changes[1].desired)=='1aae94ed'and b.hex(mode.changes[2].desired)=='0e42b97f9068922d')
-- GAS on the Speargun is live-proven (weapon_mode_presentation); any other label keeps the acknowledgement.
presenter.validate_patch({id='m',target=gas_output,field=F.presentation.mode_label,expect='none',value='gas'})
rejected(function()presenter.validate_patch({id='m',target=gas_output,field=F.presentation.mode_label,expect='none',
 value='smoke'})end,'allow_unverified_effect')
rejected(function()presenter.validate_patch({id='m',target=gas_output,field=F.presentation.mode_label,expect='none',
 value='GAS!',allow_unverified_effect=true})end,'native mode label')
rejected(function()presenter.validate_patch({id='m',target=gas_output,field=F.presentation.mode_icon,expect='default',
 value='content/ui/my_icon',allow_unverified_effect=true})end,'native weapon-function icon')
rejected(function()presenter.validate_patch({id='m',target=hd2.attack_output('AC-8 Autocannon'),
 field=F.presentation.mode_label,expect='aphet',value='stun',allow_unverified_effect=true})end,'allow_shared')
rejected(function()presenter.validate_patch({id='m',target=hd2.attack_output('LAS-98 Laser Cannon'),
 field=F.presentation.mode_label,expect='none',value='stun',allow_unverified_effect=true})end,'no writable presentation')
assert(#gas_output:mode_icons()==16 and gas_output:describe().presentation.fields.label=='presentation.mode_label')
-- Icon fallback: exact native icons where a native mode shows one, else the generic ammunition icon; "auto" resolves
-- deterministically from the label in the same operation, an explicit icon is kept.
assert(gas_output:mode_icon_for('stun').icon=='ammo_stun'and gas_output:mode_icon_for('stun').source=='exact_native')
assert(gas_output:mode_icon_for('gas').icon=='ammo_slug'and gas_output:mode_icon_for('gas').source=='generic_fallback')
assert(gas_output:mode_icon_for('sabot').icon=='ammo_flechettes')
local auto=presenter.validate_transaction({id='m',target=gas_output,allow_unverified_effect=true,changes={
 {field=F.presentation.mode_label,expect='none',value='gas'},{field=F.presentation.mode_icon,expect='default',
 value='auto'}}})
assert(auto.changes[2].value=='ammo_slug'and b.hex(auto.changes[2].desired)=='4ff6a560a22f81b7')
local changes={{field=F.presentation.mode_label,expect='none',value='stun'},{field=F.presentation.mode_icon,
 expect='default',value='auto'}}
local stun_auto=presenter.validate_transaction({id='m',target=gas_output,allow_unverified_effect=true,changes=changes})
assert(stun_auto.changes[2].value=='ammo_stun'and changes[2].value=='auto')
local explicit=presenter.validate_transaction({id='m',target=gas_output,allow_unverified_effect=true,changes={
 {field=F.presentation.mode_label,expect='none',value='gas'},{field=F.presentation.mode_icon,expect='default',
 value='ammo_stun'}}})
assert(explicit.changes[2].value=='ammo_stun')
local feed=spear:feed('primary'):describe().presentation
assert(feed.output=='output/v1/projectile/s-11-speargun'and feed.icon=='default'and feed.displayName=='Primary')
local halt_alt=halt:feed('alternate'):describe().presentation
assert(halt_alt.label=='stun'and halt_alt.icon=='ammo_stun'and halt_alt.displayName=='STUN')
-- The EMS stun-field donor: a function projectile only, with the turret's own package.
local ems_spec=w.validate_transaction({id='s',target=spear,allow_unverified_effect=true,allow_unverified_reference=true,
 changes={{field=F.weapon_function.left,expect='none',value='programmable_ammo'},
 {field=F.function_ammo.projectile,expect='none',value=hd2.attack_output('A/M-23 EMS Mortar Sentry')}}})
assert(ems_spec.asset_dependencies[1].key=='stratagem_weapon/A/M-23 EMS Mortar Sentry')
-- Mod Options: a semantic-name choice and sliders inside a list value are accepted.
local page=hd2.options({id='modes_test',title='Modes Test'})
local choice=page:choice({id='label',label='Label',choices={'Light','Heavy'},values={'light','heavy'}})
assert(choice:get()=='light')
return 'ok'
'''), b'ok')

    def test_validation_and_scenarios(self):
        result = load('validation/weapon-modes-snapshot.json')
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual((result['rates']['checked'], result['rates']['added']), (61, 57))
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
        self.assertEqual(validate_packaged_runtime.EXTRAS['example-speargun-gas-stun-test']['packageRequests'], 1)
        # The EMS stun-field donor and the Speargun mode labels (GAS, STUN with the stun icon) are pinned.
        self.assertEqual(result['speargunEms']['written'],
            ['ProjectileWeaponComponentData+576=9a000000', 'WeaponDataComponentData+184=08000000'])
        self.assertEqual(result['speargunEms']['assetDependency']['name'],
            'packages/generated/loadout/mortar_turret_staticfield')
        gas = result['modePresentation']['output/v1/projectile/s-11-speargun']
        self.assertEqual((gas['label'], gas['iconValue'], gas['icon']), ('1aae94ed', 'ammo_slug', '4ff6a560a22f81b7'))
        ems = result['modePresentation']['output/v1/projectile/a-m-23-ems-mortar-sentry']
        self.assertEqual((ems['label'], ems['icon']), ('d937037c', '0e42b97f9068922d'))
        # 66 weapon outputs, the EMS shell, the Speargun spare twin and 12 mounted-weapon outputs.
        self.assertEqual(result['presentation']['outputs'], 80)



class WindUpRateTests(unittest.TestCase):
    """Rate-of-fire modes on a wind-up projectile weapon (the M-1000 Maxigun; docs/fire-rate-modes.md "Wind-up
    weapons"): authorable like any other weapon, but only with allow_unverified_effect, whose reason names the unproven
    wind-up trigger path. Other special triggers stay blocked. Offline only."""

    @classmethod
    def setUpClass(cls):
        cls.fire_modes = {(r['kind'], r['weapon']): r for r in load('research/weapon-fire-modes-F5FEE03DCFDB.json')[
            'weapons']}
        cls.functions = {(r['kind'], r['weapon']): r for r in load('research/weapon-functions-F5FEE03DCFDB.json')[
            'weapons']}
        cls.rates = {(r['kind'], r['weapon']): r for r in load('sdk/WeaponFireRateCapabilities.json')['weapons']}

    def test_research(self):
        # The fire-mode research keeps the Maxigun's fire modes blocked and records its trigger without the wind-up.
        maxigun = self.fire_modes[('support', 'M-1000 Maxigun')]
        self.assertEqual((maxigun['state'], maxigun['windUp']), ('blocked', {'stateWithoutWindUp': 'single_mode'}))
        self.assertEqual([key for key, row in self.fire_modes.items() if 'windUp' in row],
            [('support', 'M-1000 Maxigun')])
        rate = self.functions[('support', 'M-1000 Maxigun')]['fireRate']
        self.assertEqual((rate['state'], rate['maxModes'], rate['bindableInputs'], rate['dormantSlots']),
            ('addable', 3, ['left', 'right'], ['x', 'z']))
        self.assertIn('wind-up trigger path fires at the selected rate slot is not', rate['windUp']['reason'])
        self.assertEqual(self.functions[('support', 'M-1000 Maxigun')]['functionAmmo']['state'], 'blocked')
        # Every other special trigger stays blocked or absent, and no other weapon is flagged wind-up.
        for key, row in self.functions.items():
            if set(row['families']) & {'charge', 'beam', 'arc', 'spray', 'melee'}:
                self.assertIn((row.get('fireRate') or {}).get('state'), ('blocked', 'absent'), key)
            if key != ('support', 'M-1000 Maxigun'):
                self.assertNotIn('windUp', row.get('fireRate') or {}, key)

    def test_published_capability(self):
        maxigun = self.rates[('support', 'M-1000 Maxigun')]
        self.assertEqual((maxigun['state'], maxigun['writable'], maxigun['acknowledgements']),
            ('addable', True, ['allow_unverified_effect']))
        self.assertEqual(maxigun['expect'], [1500.0, 1500.0, 1500.0])
        self.assertEqual([m['slot'] for m in maxigun['modes']], ['y'])   # X and Z are dormant: no menu lists them
        self.assertEqual(maxigun['windUp']['dormantSlots'], ['x', 'z'])
        self.assertIsNone(maxigun['liveEvidence'])
        # Other dormant-slot or special-trigger weapons are unchanged.
        for key in (('support', 'LAS-99 Quasar Cannon'), ('support', 'MGX-42 Bullet Storm'),
                ('player', 'PLAS-39 Accelerator Rifle'), ('support', 'RS-422 Railgun'), ('player', 'PLAS-101 Purifier')):
            self.assertFalse(self.rates[key]['writable'], key)
            self.assertNotIn('windUp', self.rates[key], key)

    def test_lua(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local w=require('hd2runtime/domains/player_weapon_writes')
local F=hd2.fields
local function rejected(fn,needle)
 local ok,why=pcall(fn);assert(not ok,'accepted');assert(tostring(why):find(needle,1,true),tostring(why))
end
local maxigun=hd2.support_weapon('M-1000 Maxigun')
local view=maxigun:fire_rate_modes()
assert(view.state=='addable'and view.writable and#view.modes==1 and view.modes[1].slot=='y')
assert(view.slots[1].dormant and view.slots[3].dormant and not view.slots[1].enabled)
assert(view.binding.field=='weapon_function.left'and view.acknowledgements[1]=='allow_unverified_effect')
assert(view.windUp and view.windUp.reason:find('wind-up trigger path',1,true))
local menu={{field=F.fire_rate.modes,expect={1500,1500,1500},value={750,1500,2500}},
 {field=F.weapon_function.left,expect='none',value='rate_of_fire'}}
-- Authorable with the acknowledgement, refused without it (the reason names the wind-up path).
local spec=w.validate_transaction({id='m',target=maxigun,changes=menu,allow_unverified_effect=true})
assert(#spec.changes==2)
rejected(function()w.validate_transaction({id='m',target=maxigun,changes=menu})end,'wind-up trigger path')
rejected(function()w.validate_patch({id='m',target=maxigun,field=F.weapon_function.left,expect='none',
 value='rate_of_fire'})end,'allow_unverified_effect')
-- Dormant X and Z: the rate alone clears them; rates in X or Z need the binding; the reviewed slots are a no-op.
w.validate_patch({id='m',target=maxigun,field=F.fire_rate.modes,expect={1500,1500,1500},value={0,1200,0},
 allow_unverified_effect=true})
rejected(function()w.validate_patch({id='m',target=maxigun,field=F.fire_rate.modes,expect={1500,1500,1500},
 value={1500,1200,1500},allow_unverified_effect=true})end,'SELECTOR_REQUIRED')
w.validate_patch({id='m',target=maxigun,field=F.fire_rate.modes,expect={1500,1500,1500},value={1500,1500,1500},
 allow_unverified_effect=true})
rejected(function()w.validate_patch({id='m',target=maxigun,field=F.weapon_function.left,expect='none',
 value='rate_of_fire',allow_unverified_effect=true})end,'SELECTOR_REQUIRED')
-- Its fire modes and function projectile stay unauthored.
rejected(function()w.validate_patch({id='m',target=maxigun,field=F.function_ammo.projectile,expect='none',
 value='none',allow_unverified_effect=true})end,'not exposed')
-- Other special triggers stay blocked (charge), as do other dormant-slot weapons (the Quasar).
for _,item in ipairs({{hd2.weapon('PLAS-39 Accelerator Rifle'),{0,550,0}},{hd2.support_weapon('RS-422 Railgun'),
  {0,60,0}},{hd2.support_weapon('LAS-99 Quasar Cannon'),{0,10,10}}})do
 local ok=pcall(w.validate_patch,{id='b',target=item[1],field=F.fire_rate.modes,expect=item[2],value=item[2],
  allow_unverified_effect=true})
 assert(not ok)
end
return 'ok'
'''), b'ok')

    def test_snapshot_validation(self):
        result = load('validation/weapon-modes-snapshot.json')
        self.assertEqual(result['rates']['windUp'], ['M-1000 Maxigun'])
        self.assertEqual(result['maxigun'], {'acknowledgementRequired': True, 'menu': [750, 1500, 2500]})
        self.assertEqual(result['blockedRejections'], 9)


if __name__ == '__main__':
    unittest.main()
