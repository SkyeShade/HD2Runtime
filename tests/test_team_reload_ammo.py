"""0.30.4 (research/team-reload-ammo-F5FEE03DCFDB.json, docs/support-weapon-api.md "Team-reload weapons"): the GR-8,
RL-77, FAF-14, StA-X3 and AC-8 reload from the weapon's own spares first and from their backpack's deposit once those
are spent. The magazine weapons' own spare rows are real fields (0..31, allow_unverified_effect); the AC-8's own rounds
are not offered (the reload subtracts 5 with no lower bound); every team-reload backpack's deposit is authorable
(start -1 = full kept). The snapshot test writes on a copy-on-write overlay of the retained snapshot."""
import json
import unittest

from support import ROOT, run
from test_multi_mod_composition import build_profile, snapshot_run

RESEARCH = json.loads((ROOT / 'research/team-reload-ammo-F5FEE03DCFDB.json').read_text())
MAGAZINE_WEAPONS = ('GR-8 Recoilless Rifle', 'RL-77 Airburst Rocket Launcher', 'FAF-14 Spear',
    'StA-X3 W.A.S.P. Launcher')


class ResearchTests(unittest.TestCase):
    def test_the_game_reads_own_spares_before_the_backpack(self):
        self.assertEqual(RESEARCH['writes'], 0)
        proof = RESEARCH['gameDll']['proof']
        asm = {(group, row['rva']): row['asm'] for group, rows in proof.items() for row in rows}
        # The gate: own spare total above 0 lets the wielder reload; only at 0 is the backpack asked.
        self.assertEqual(asm[('reloadGate', 0x775990)], 'call 0x744180')
        self.assertEqual(asm[('reloadGate', 0x775B6E)], 'call 0x73b440')
        # The payment: own spares first (one magazine), the backpack (its +20 cost) only at 0.
        self.assertEqual(asm[('reloadConsume', 0x77709C)], 'jne 0x7771cc')
        self.assertEqual(asm[('reloadConsume', 0x777431)], 'sub dword ptr [rcx + r8*4], 1')
        self.assertEqual(asm[('reloadConsume', 0x7774E7)], 'sub ebx, dword ptr [rbp + 0x5c]')
        # Spawn and resupply clamp to the maximum (+148).
        self.assertEqual(asm[('spawnMagazines', 0x76DB0B)], 'mov esi, dword ptr [rax + 0x94]')
        self.assertEqual(asm[('resupply', 0x76E7C9)], 'cmovb edi, eax')
        fields = {(f['field'], f['bits']) for f in RESEARCH['networkFields']}
        self.assertEqual(fields, {('magazines_remaining', 5), ('0x9A34C336', 9)})

    def test_every_team_reload_weapon_and_its_backpack(self):
        weapons = {item['supportWeapon']: item for item in RESEARCH['teamReloadWeapons']}
        self.assertEqual(set(weapons), set(MAGAZINE_WEAPONS) | {'AC-8 Autocannon', None})
        for name in MAGAZINE_WEAPONS:
            item = weapons[name]
            self.assertEqual(item['ammoKind'], 'magazine', name)
            # Natively the maximum is 0: the start and every resupply are clamped away.
            self.assertEqual(item['weaponAmmo']['spareMagazines'], 0, name)
            self.assertEqual(item['weaponAmmo']['magazinesFromSupply'], 6, name)
            self.assertEqual(item['deposit']['values']['4'], -1, name)
            self.assertTrue(item['deposit']['uniqueOwner'] and item['fingerprint']['exact'], name)
            self.assertEqual(item['backpackEquipmentType'], 17, name)
            self.assertEqual(item['assistedReload']['depositCost'], 1, name)
        ac8 = weapons['AC-8 Autocannon']
        self.assertEqual((ac8['ammoKind'], ac8['weaponAmmo']['reloadAmount'], ac8['deposit']['values']),
            ('rounds', 5, {'0': 10, '4': -1, '8': 5}))
        self.assertEqual(weapons['GR-8 Recoilless Rifle']['deposit']['values'], {'0': 5, '4': -1, '8': 3})


class CatalogueTests(unittest.TestCase):
    def test_rows_say_what_they_do(self):
        support = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())
        rows = {(f['supportWeapon'], f['semanticFieldId']): f for f in support['fieldInstances']}
        for name in MAGAZINE_WEAPONS:
            for field in ('magazine.spare_magazines', 'magazine.starting_magazines', 'magazine.magazines_from_supply'):
                row = rows[(name, field)]
                self.assertNotIn('noEffect', row, (name, field))
                self.assertEqual(row['operation']['acknowledgement'], 'allow_unverified_effect')
                self.assertEqual((row['teamReload']['min'], row['teamReload']['max']), (0, 31))
                self.assertTrue(row['teamReload']['ownSpares'])
        for field in ('rounds.spare_rounds', 'rounds.starting_rounds', 'rounds.rounds_from_supply'):
            row = rows[('AC-8 Autocannon', field)]
            self.assertIn('noEffect', row)
            self.assertFalse(row['teamReload']['ownSpares'])
        self.assertEqual(rows[('AC-8 Autocannon', 'rounds.spare_rounds')]['teamReload']['max'], 0)
        backpacks = json.loads((ROOT / 'sdk/BackpackAuthoringCapabilities.json').read_text())
        start = next(f for f in backpacks['fieldInstances'] if f['target']['backpack'] == 'GR-8 Recoilless Rifle Backpack'
            and f['semanticFieldId'] == 'deposit.start_amount')
        self.assertEqual((start['currentDefault'], start['min'], start['max']), (-1, -1, 1023))
        self.assertEqual(start['sentinels'][0]['value'], -1)
        self.assertEqual(start['evidence']['tier'], 'native_consumer_proven')

    def test_lua_guards(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(request,text)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local F=hd2.fields
rejects({id='a',target=gr8,field=F.magazine.spare_magazines,expect=0,value=3},'allow_unverified_effect')
patches.validate{id='a',target=gr8,allow_unverified_effect=true,field=F.magazine.spare_magazines,expect=0,value=3}
rejects({id='b',target=gr8,allow_unverified_effect=true,field=F.magazine.spare_magazines,expect=0,value=32},
 'magazines_remaining (5 bits)')
rejects({id='c',target=hd2.support_weapon('AC-8 Autocannon'),field=F.rounds.spare_rounds,expect=0,value=20},
 'no lower bound')
patches.validate{id='d',target=hd2.support_weapon('AC-8 Autocannon'),field=F.rounds.spare_rounds,expect=0,value=0}
local pack=gr8:backpack()
assert(pack.backpack=='GR-8 Recoilless Rifle Backpack' and pack:weapon().weapon=='GR-8 Recoilless Rifle')
patches.validate{id='e',target=pack,allow_unverified_effect=true,field=F.deposit.start_amount,expect=-1,value=-1}
patches.validate{id='f',target=pack,allow_unverified_effect=true,field=F.deposit.capacity,expect=5,value=12}
rejects({id='g',target=pack,allow_unverified_effect=true,field=F.deposit.start_amount,expect=-1,value=-2},
 'reviewed range')
rejects({id='h',target=pack,field=F.deposit.capacity,expect=5,value=12},'allow_unverified_effect')
return 'ok'
'''), b'ok')


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class SnapshotTests(unittest.TestCase):
    def test_gr8_own_spares_and_a_bigger_backpack(self):
        result = snapshot_run(r'''
update=update or function()end
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local pack=gr8:backpack()
local spares={{field='magazine.spare_magazines',expect=0,value=3},{field='magazine.starting_magazines',expect=0,value=3},
    {field='magazine.magazines_from_supply',expect=6,value=3}}
local where=resolve('transaction',{id='w',target=gr8,allow_unverified_effect=true,changes=spares})
check(#where==3,'three members of the GR-8 magazine record: '..#where)
local deposit={{field='deposit.capacity',expect=5,value=12},{field='deposit.refill_amount',expect=3,value=6}}
local bag=resolve('transaction',{id='b',target=pack,allow_unverified_effect=true,changes=deposit})
check(#bag==2,'two members of the GR-8 backpack deposit: '..#bag)
local h={}
events.run_as('mods/test/team_reload',function()
    h.weapon=hd2.ensure({transaction={id='gr8-own-spares',target=gr8,allow_unverified_effect=true,changes=spares}})
    h.pack=hd2.ensure({transaction={id='gr8-backpack',target=pack,allow_unverified_effect=true,changes=deposit}})
end)
settle({h.weapon,h.pack})
check(h.weapon.runs>=1 and h.weapon.result.status=='APPLIED','weapon '..tostring(h.weapon.error))
check(h.pack.runs>=1 and h.pack.result.status=='APPLIED','backpack '..tostring(h.pack.error))
for _,item in ipairs(where)do check(runtime.read(item.at,4)==b.encode(3,'u32'),item.label..' written')end
check(runtime.read(bag[1].at,4)==b.encode(12,'u32'),'capacity 12 written')
local n=0
for _ in pairs(overlay)do n=n+1 end
check(n==5,'exactly five members written: '..n)
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
