"""Expendable LIFECYCLE members vs per-donor CLONE COMPATIBILITY (docs/research/expendable-carriers-F5FEE03DCFDB.md,
research/expendable-carriers-F5FEE03DCFDB.json, scripts/research_expendable_carriers.py; runtime/weapon_clone.lua,
runtime/weapon_carriers.lua, domains/weapon_clone.lua):
  * the research is read-only, its pins identical in every snapshot, both auto-drop gates identified (WeaponReload,
    SeatCollection);
  * the five lifecycle members are derived from all 27 support weapons (no name decides): EAT-17, EAT-700, EAT-411,
    MLS-4X Commando, MGX-42 Bullet Storm; none reloadable;
  * only the EAT-700 and the EAT-411 are EAT-17 clone carriers, in that order; the Commando (extra guidance components)
    and the Bullet Storm (no Backblast) are members with their own one-weapon classes;
  * magazines, pods and the round-count override verdicts (type level refused, instance level a hypothesis);
  * the Lua classification matches, and the EAT-17 pool / allocation stay EAT-700 then EAT-411."""
import json
import unittest

from support import ROOT, run

RESEARCH = json.loads((ROOT / 'research/expendable-carriers-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
EAT17, EAT700, EAT411 = 'EAT-17 Expendable Anti-Tank', 'EAT-700 Expendable Napalm', 'EAT-411 Leveller'
COMMANDO, STORM = 'MLS-4X Commando', 'MGX-42 Bullet Storm'
MEMBERS = [EAT17, EAT700, EAT411, COMMANDO, STORM]


class ExpendableCarriersResearchTests(unittest.TestCase):
    def test_read_only_and_pinned(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        rvas = {p['rva'] for rows in RESEARCH['pins'].values() for p in rows}
        for rva in (0x753BBF, 0x753C23, 0x569161, 0x633ED3, 0x510E81, 0x753C2F, 0x57417F):
            self.assertIn(rva, rvas)
        gates = RESEARCH['gates']
        self.assertEqual(gates['gate1']['component'], 'WeaponReloadComponentData')
        self.assertEqual(gates['gate2']['component'], 'SeatCollectionComponentData')
        self.assertIn('WeaponMagazineComponentData', gates['magazineCopy']['reads'])
        checks = RESEARCH['checks']
        self.assertTrue(checks['gateManagersInEverySnapshot'])
        self.assertTrue(checks['typeTablesAsPinnedInEverySnapshot'])

    def test_lifecycle_members_from_data(self):
        checks = RESEARCH['checks']
        self.assertEqual(checks['lifecycleMembers'], MEMBERS)
        self.assertEqual(checks['lifecycleMembersDerivedFromAll27'], sorted(MEMBERS))
        self.assertTrue(checks['noMemberHasAGateComponent'])
        self.assertTrue(checks['noSupportWeaponHasSeatCollection'])
        self.assertTrue(all(checks['membersEveryRecordExclusive'].values()))
        for name in MEMBERS:
            w = RESEARCH['weapons'][name]
            self.assertTrue(w['expendableMember'], name)
            self.assertFalse(w['reload']['reloadable'], name)
            self.assertFalse(w['reload']['WeaponReload'], name)
            self.assertNotEqual(w['lifecycle']['autoDropAbility'], 0, name)
            self.assertEqual((w['magazine']['magazines'], w['magazine']['magazinesMax']), (0, 0), name)
            self.assertEqual(w['magazine']['owners'], 1, name)
        for name, other in RESEARCH['otherSupportWeapons'].items():
            self.assertFalse(other['expendableMember'], name)
        # Outside the 27: a second unnamed EAT-17 type and the Solo Silo remote, never carriers.
        self.assertEqual(len(checks['autoDropOutsideThe27']), 2)

    def test_the_bullet_storm_exists(self):
        storm = RESEARCH['weapons'][STORM]
        self.assertEqual(storm['entity'], 'expendable_machinegun')
        self.assertEqual(storm['stratagem'], {'name': STORM, 'stableId': 3288352984,
            'nativeType': 'Expendable_Machinegun'})
        self.assertEqual(storm['pod']['rack'], 'content/fac_helldivers/hellpod/weapon_rack/weapon_rack_expendable_machinegun')
        self.assertEqual(RESEARCH['weapons'][COMMANDO]['entity'], 'laser_guided_missile_launcher')
        self.assertEqual(RESEARCH['weapons'][COMMANDO]['stratagem']['stableId'], 2232989803)

    def test_clone_compatibility_with_the_eat17(self):
        checks = RESEARCH['checks']
        self.assertEqual(checks['eat17CloneCompatible'], [EAT700, EAT411])
        self.assertEqual(checks['cloneClasses'][EAT700], sorted([EAT17, EAT700, EAT411]))
        self.assertEqual(checks['cloneClasses'][COMMANDO], [COMMANDO])
        self.assertEqual(checks['cloneClasses'][STORM], [STORM])
        commando = RESEARCH['weapons'][COMMANDO]
        self.assertFalse(commando['eat17Clone']['compatible'])
        self.assertEqual(commando['componentSet']['missingVsEat17'], [])
        self.assertEqual(commando['componentSet']['extraVsEat17'], ['FactionComponentData',
            'GuidanceTargetComponentData', 'LaserDesignatorComponentData', 'SensorEyeComponentData',
            'WeaponLinkerComponentData'])
        self.assertIn('Equipment 0x88', [c['member'] for c in commando['eat17Contract']])   # DropMode 1 vs 2
        storm = RESEARCH['weapons'][STORM]
        self.assertFalse(storm['eat17Clone']['compatible'])
        self.assertEqual(storm['componentSet']['missingVsEat17'], ['BackblastComponentData'])
        self.assertEqual(storm['componentSet']['extraVsEat17'], [])
        for name in (EAT700, EAT411):
            w = RESEARCH['weapons'][name]
            self.assertTrue(w['eat17Clone']['compatible'], name)
            self.assertEqual(w['eat17Contract'], [], name)

    def test_magazines_and_pods(self):
        w = RESEARCH['weapons']
        mags = {n: (w[n]['magazine']['capacity'], w[n]['magazine']['chambered'], w[n]['magazine']['type'])
            for n in MEMBERS}
        self.assertEqual(mags, {EAT17: (1, 0, 0), EAT700: (1, 0, 0), EAT411: (1, 0, 0), COMMANDO: (4, 0, 0),
            STORM: (300, 1, 1)})
        self.assertEqual(RESEARCH['checks']['podCapacity'], {EAT17: 2, EAT700: 2, EAT411: 2, COMMANDO: 1, STORM: 2})
        self.assertTrue(w[EAT700]['podVerdict']['two'].startswith('CLEAN'))
        self.assertTrue(w[STORM]['podVerdict']['two'].startswith('CLEAN'))
        self.assertTrue(w[EAT411]['podVerdict']['two'].startswith('POSSIBLE'))
        self.assertTrue(w[COMMANDO]['podVerdict']['two'].startswith('REFUSED'))
        self.assertFalse(w[EAT17]['pod']['exclusiveCarrierRack'])

    def test_round_count_override_verdicts(self):
        for name in MEMBERS:
            o = RESEARCH['weapons'][name]['overrides']
            self.assertEqual((o['roundsTypeLevel']['possible'], o['roundsTypeLevel']['status']), (False, 'REFUSED'))
            self.assertEqual(o['roundsInstanceLevel']['status'], 'HYPOTHESIS')
            self.assertTrue(o['roundsInstanceLevel']['possible'])


class ExpendableClassificationTests(unittest.TestCase):
    def test_the_groups_catalogue_lists_the_lifecycle_members_for_modbuilder(self):
        self.assertEqual(run(r"""
local g=require('hd2runtime/runtime/carrier_groups')
local names={}
for k,e in ipairs(g.catalogue())do names[k]=e.name end
assert(table.concat(names,',')=='orbital,any_red,any,support,support_pod,expendable,weapon,sentry,emplacement,eagle')
local by={}
for _,e in ipairs(g.catalogue())do
    if e.name=='weapon'then
        -- the weapon group: each variant host is its own (and only) carrier
        assert(#e.members==1 and e.members[1].name=='M-1000 Maxigun'and e.members[1].carries[1]=='M-1000 Maxigun')
    elseif e.name~='expendable'then assert(e.members==nil,e.name..' gained members')end
    if e.name=='expendable'then for _,m in ipairs(e.members or{})do by[m.name]=m end end
end
local EAT17='EAT-17 Expendable Anti-Tank'
assert(by['EAT-700 Expendable Napalm'].carries[1]==EAT17 and by['EAT-411 Leveller'].carries[1]==EAT17)
assert(#by['MLS-4X Commando'].carries==0 and by['MLS-4X Commando'].rounds==4 and by['MLS-4X Commando'].pod_capacity==1)
assert(#by['MGX-42 Bullet Storm'].carries==0 and by['MGX-42 Bullet Storm'].rounds==300)
assert(by['MLS-4X Commando'].refused[1]:find('GuidanceTarget',1,true)and by['MGX-42 Bullet Storm'].refused[1]:find(
    'missing Backblast',1,true))
return 'ok'
"""), b'ok')

    def test_the_lua_classification(self):
        out = run(r"""
local clone=require('hd2runtime/runtime/weapon_clone')
local carriers=require('hd2runtime/runtime/weapon_carriers')
local json=require('hd2runtime/primary_mapper/json')
local E='EAT-17 Expendable Anti-Tank'
local out={members=clone.expendables(),pool=clone.pool(E),compatible={},reasons={},classes={},list={}}
for _,name in ipairs({'EAT-17 Expendable Anti-Tank','EAT-700 Expendable Napalm','EAT-411 Leveller','MLS-4X Commando',
    'MGX-42 Bullet Storm','AC-8 Autocannon'})do
    local ok,why=clone.compatible(E,name)
    out.compatible[name]=ok
    out.reasons[name]=why or''
    out.classes[name]=clone.clone_class(name)or false
end
for _,m in ipairs(carriers.members())do
    out.list[#out.list+1]={name=m.name,stable=m.stable_id,capacity=m.pod_capacity,rounds=m.rounds,
        eat17=m.compatible[E]==true}
end
local pool={}
for _,c in ipairs(carriers.pool(E))do pool[#pool+1]=c.name end
out.weapon_pool=pool
local a=carriers.allocate({{id='b',donor=E},{id='a',donor=E},{id='c',donor=E}},{})
out.alloc={a=a.assignments.a and a.assignments.a.weapon,b=a.assignments.b and a.assignments.b.weapon,
    c=a.refused.c}
local ok,why=clone.compatible('MLS-4X Commando','EAT-700 Expendable Napalm')
out.not_donor=why
return json.encode(out)
""")
        r = json.loads(out)
        self.assertEqual(r['members'], MEMBERS)
        self.assertEqual(r['pool'], [EAT700, EAT411])
        self.assertEqual(r['weapon_pool'], [EAT700, EAT411])
        self.assertEqual(r['compatible'], {EAT17: False, EAT700: True, EAT411: True, COMMANDO: False, STORM: False,
            'AC-8 Autocannon': False})
        self.assertIn('LaserDesignator', r['reasons'][COMMANDO])
        self.assertIn('missing Backblast', r['reasons'][STORM])
        self.assertIn('not an expendable lifecycle member', r['reasons']['AC-8 Autocannon'])
        self.assertIn('the donor itself', r['reasons'][EAT17])
        self.assertEqual(r['classes'][COMMANDO], [COMMANDO])
        self.assertEqual(r['classes'][STORM], [STORM])
        self.assertEqual(r['classes'][EAT411], [EAT17, EAT700, EAT411])
        self.assertFalse(r['classes']['AC-8 Autocannon'])
        listed = {m['name']: m for m in r['list']}
        self.assertEqual([m['name'] for m in r['list']], MEMBERS)
        self.assertEqual((listed[COMMANDO]['rounds'], listed[COMMANDO]['capacity'], listed[COMMANDO]['eat17']),
            (4, 1, False))
        self.assertEqual((listed[STORM]['rounds'], listed[STORM]['capacity'], listed[STORM]['eat17'],
            listed[STORM]['stable']), (300, 2, False, 3288352984))
        self.assertTrue(listed[EAT700]['eat17'] and listed[EAT411]['eat17'])
        # The allocation is unchanged: ids in order, EAT-700 then EAT-411, the third refused.
        self.assertEqual((r['alloc']['a'], r['alloc']['b']), (EAT700, EAT411))
        self.assertIn('UNAVAILABLE', r['alloc']['c'])
        self.assertIn('not a reviewed clone donor', r['not_donor'])


if __name__ == '__main__':
    unittest.main()
