import json
import unittest

from support import ROOT, run


class BackpackAmmoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/backpack-ammo-F5FEE03DCFDB.json').read_text())
        cls.backpacks = json.loads((ROOT / 'sdk/BackpackAuthoringCapabilities.json').read_text())
        cls.support = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())

    def test_native_ammunition_owner(self):
        fed = {item['supportWeapon']: item for item in self.research['backpackFedWeapons']}
        self.assertEqual(set(fed), {'M-1000 Maxigun', 'B/FLAM-80 Cremator', 'GL-28 Belt-Fed Grenade Launcher'})
        self.assertTrue(all(self.research['liveEquality'].values()))
        self.assertEqual(self.research['typeLibrary']['inventorySlotBackpack'], 6)
        maxigun = fed['M-1000 Maxigun']
        self.assertEqual(maxigun['backpackPath'],
            'content/fac_helldivers/equipment/backpacks/minigun_backpack/minigun_backpack')
        self.assertEqual(maxigun['deposit']['values'], {'0': 1000, '4': 1000, '8': 500})
        self.assertEqual(maxigun['deposit']['refillStyle'], 'Ammo')
        self.assertEqual((maxigun['rack']['weaponSlot'], maxigun['rack']['backpackSlot']), (0, 1))
        self.assertEqual(maxigun['callIn']['primaryPayload'], maxigun['rack']['resource'])
        for item in fed.values():
            self.assertTrue(item['fingerprintExact'], item['supportWeapon'])
            self.assertFalse(item['weaponOwnsMagazine'], item['supportWeapon'])
            self.assertTrue(item['deposit']['uniqueOwner'])
            self.assertEqual(item['tagCarriers'], [item['backpackResource']])
            self.assertEqual(item['linkedAmmo']['inventorySlot'], 'Backpack')

    def test_catalogs_link_weapon_and_backpack(self):
        summary = self.backpacks['summary']
        self.assertEqual((summary['backpacks'], summary['weaponFedBackpacks'], summary['backpackAmmoWritable']),
            (16, 3, 9))
        by_name = {item['name']: item for item in self.backpacks['backpacks']}
        maxigun = by_name['M-1000 Maxigun Backpack']
        self.assertEqual(maxigun['feeds']['supportWeapon'], 'M-1000 Maxigun')
        self.assertEqual((maxigun['ammo']['capacity'], maxigun['ammo']['startAmount'], maxigun['ammo']['refillAmount']),
            (1000, 1000, 500))
        self.assertFalse(maxigun['ammo']['fromAmmoBox']['writable'])
        fields = [x for x in self.backpacks['fieldInstances'] if x['target']['backpack'] == 'M-1000 Maxigun Backpack']
        self.assertEqual([x['displayName'] for x in fields],
            ['Backpack ammo capacity', 'Starting backpack ammo', 'Backpack ammo from supply'])
        for field in fields:
            self.assertTrue(field['editable'])
            self.assertFalse(field['allowSharedRequired'])
            self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
            self.assertEqual(field['uiGroup'], 'backpack_ammo')
        # Call-in backpack deposits (Supply Pack, drones, Hellbomb) stay read-only.
        supply = [x for x in self.backpacks['fieldInstances'] if x['target']['backpack'] == 'B-1 Supply Pack']
        self.assertTrue(supply and not any(x['editable'] for x in supply))
        weapons = {item['name']: item for item in self.support['weapons']}
        link = weapons['M-1000 Maxigun']['ammoBackpack']
        self.assertEqual((link['backpack'], link['semanticId']), ('M-1000 Maxigun Backpack', maxigun['semanticId']))
        self.assertIn('weapon magazine', [b['field'] for b in weapons['M-1000 Maxigun']['blockedFields']])
        self.assertIsNone(weapons['GR-8 Recoilless Rifle']['ammoBackpack'])

    def test_snapshot_overlay_validation(self):
        result = json.loads((ROOT / 'validation/backpack-ammo-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        for key in ('fields', 'baselineMatches', 'noOps', 'changedWrites', 'rollbacks', 'conflictRejections',
                    'acknowledgementRejections', 'staleExpectRejections', 'rangeRejections'):
            self.assertEqual(result[key], 9, key)
        self.assertEqual(result['chainTamperRejections'], 12)

    def test_lua_api_and_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(request,text)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
local maxigun=hd2.support_weapon('M-1000 Maxigun')
local backpack=maxigun:backpack()
assert(backpack.backpack=='M-1000 Maxigun Backpack')
assert(backpack:describe().feeds.supportWeapon=='M-1000 Maxigun')
assert(backpack:weapon().weapon=='M-1000 Maxigun')
assert(maxigun:describe().ammoBackpack=='M-1000 Maxigun Backpack')
rejects({id='a',target=backpack,field=hd2.fields.deposit.capacity,expect=1000,value=2000},'allow_unverified_effect')
patches.validate{id='a',allow_unverified_effect=true,target=backpack,field=hd2.fields.deposit.capacity,
 expect=1000,value=2000}
rejects({id='b',allow_unverified_effect=true,target=backpack,field=hd2.fields.deposit.capacity,expect=1000,value=0},
 'reviewed range')
rejects({id='c',allow_unverified_effect=true,target=backpack,field=hd2.fields.deposit.capacity,expect=999,value=2000},
 'expect differs')
rejects({id='d',allow_unverified_effect=true,target=hd2.backpack('B-1 Supply Pack'),field=hd2.fields.deposit.capacity,
 expect=4,value=6},'read-only')
assert(not pcall(function()return hd2.support_weapon('GR-8 Recoilless Rifle'):backpack()end))
assert(hd2.support_weapon('B/FLAM-80 Cremator'):backpack().backpack=='B/FLAM-80 Cremator Backpack')
assert(hd2.support_weapon('GL-28 Belt-Fed Grenade Launcher'):backpack().backpack=='GL-28 Belt-Fed Grenade Launcher Backpack')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
