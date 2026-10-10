"""0.31.0 (research/team-reload-ammo-F5FEE03DCFDB.json, docs/support-weapon-api.md "Team-reload weapons"): the GR-8,
RL-77, FAF-14, StA-X3 and AC-8 reload from the weapon's own spares first and from their backpack's deposit once those
are spent. The magazine weapons' own spare rows are real fields (0..31, allow_unverified_effect), and so are the AC-8's
own rounds (0..511; rc2: its reload subtracts 5 with no lower bound, but the flush clamps a negative to 0 in place the
same frame, ownRoundsBelowZero); every team-reload backpack's deposit is authorable (start -1 = full kept). Older-SDK
mods write the own rows without the acknowledgement. The snapshot tests write on a copy-on-write overlay of the
retained snapshot."""
import json
import unittest

from support import ROOT, run
from test_legacy_sdk_compatibility import legacy_lines, modbuilder_wrap, only, run_mods
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

    def test_own_rounds_below_zero_are_clamped_in_place(self):
        # rc2: 3 own rounds and a 5-round reload store -2 in the live row; the queued write points at that row and the
        # flush validates it with clamp = 1 before setting the field, so the engine writes 0 back the same frame.
        proof = RESEARCH['gameDll']['proof']
        asm = {(group, row['rva']): row['asm'] for group, rows in proof.items() for row in rows}
        self.assertEqual(asm[('roundsBelowZero', 0x7774EA)], 'mov dword ptr [rax + rcx*4], ebx')
        self.assertEqual(asm[('roundsBelowZero', 0x7774F1)], 'lea r8, [rax + rcx*4]')
        self.assertEqual(asm[('roundsBelowZero', 0x7769A7)], 'test byte ptr [rcx + 0x14], 1')
        self.assertEqual(asm[('readersOfANegativeCount', 0x775997)], 'setg r14b')
        self.assertEqual(asm[('fieldQueueAndFlush', 0xFDDF0C)], 'mov byte ptr [rsp + 0x20], 1')
        self.assertEqual(asm[('fieldQueueAndFlush', 0xFDAF6C)], 'call 0xfdc780')
        self.assertEqual(asm[('fieldQueueAndFlush', 0xFDC79E)], 'call 0xfde060')
        clamp = {row['rva']: row['asm'] for row in RESEARCH['executable']['proof']['validatorIntClamp']}
        self.assertEqual(clamp[0x34BBEF], 'cmovl edi, r14d')
        self.assertEqual(clamp[0x34BBF3], 'mov dword ptr [rsi], edi')
        below = RESEARCH['ownRoundsBelowZero']
        self.assertTrue(below['effect'].startswith('harmless'))
        veto, = below['vanillaPrecedent']
        self.assertTrue(veto['owners'][0].endswith('pistol_broomhandle'))
        self.assertEqual((veto['startingRounds'], veto['reloadAmount']), (52, 6))

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
            self.assertNotIn('noEffect', row, field)
            self.assertEqual(row['operation']['acknowledgement'], 'allow_unverified_effect')
            self.assertEqual((row['teamReload']['min'], row['teamReload']['max']), (0, 511))
            self.assertIn('network field of 9 bits', row['teamReload']['rangeReason'])
            self.assertTrue(row['teamReload']['ownSpares'])
            self.assertNotIn('underflow', json.dumps(row))
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
local ac8=hd2.support_weapon('AC-8 Autocannon')
rejects({id='c',target=ac8,field=F.rounds.spare_rounds,expect=0,value=20},'allow_unverified_effect')
patches.validate{id='c',target=ac8,allow_unverified_effect=true,field=F.rounds.spare_rounds,expect=0,value=20}
-- not a multiple of the 5-round clip: harmless (the last partial reload ends at 0), so accepted
patches.validate{id='c',target=ac8,allow_unverified_effect=true,field=F.rounds.spare_rounds,expect=0,value=23}
patches.validate{id='c',target=ac8,allow_unverified_effect=true,field=F.rounds.starting_rounds,expect=0,value=511}
patches.validate{id='c',target=ac8,allow_unverified_effect=true,field=F.rounds.rounds_from_supply,expect=0,value=7}
rejects({id='c',target=ac8,allow_unverified_effect=true,field=F.rounds.spare_rounds,expect=0,value=512},
 'network field of 9 bits')
rejects({id='c',target=ac8,allow_unverified_effect=true,field=F.rounds.starting_rounds,expect=0,value=-1},
 'reviewed minimum')
patches.validate{id='d',target=ac8,allow_unverified_effect=true,field=F.rounds.spare_rounds,expect=0,value=0}
local pack=gr8:backpack()
assert(pack.backpack=='GR-8 Recoilless Rifle Backpack' and pack:weapon().weapon=='GR-8 Recoilless Rifle')
patches.validate{id='e',target=pack,allow_unverified_effect=true,field=F.deposit.start_amount,expect=-1,value=-1}
patches.validate{id='f',target=pack,allow_unverified_effect=true,field=F.deposit.capacity,expect=5,value=12}
rejects({id='g',target=pack,allow_unverified_effect=true,field=F.deposit.start_amount,expect=-1,value=-2},
 'reviewed range')
rejects({id='h',target=pack,field=F.deposit.capacity,expect=5,value=12},'allow_unverified_effect')
return 'ok'
'''), b'ok')


AC8_OWN_ROUNDS = ("hd2.ensure({transaction={id='ac8-own-rounds',target=hd2.support_weapon('AC-8 Autocannon'),"
    "changes={{field=hd2.fields.rounds.spare_rounds,expect=0,value=20},"
    "{field=hd2.fields.rounds.starting_rounds,expect=0,value=20}}}})")


class LegacyTests(unittest.TestCase):
    def test_a_0_30_3_mod_keeps_writing_ac8_own_rounds(self):
        # 0.30.3 accepted these rows without an acknowledgement (flagged "no effect"); rc1 refused any nonzero
        # maximum. A mod that declares SDK 0.30.3 writes them as a logged legacy operation; one that declares 0.31.0
        # needs allow_unverified_effect.
        results = run_mods([
            ('sdk-0303', modbuilder_wrap('mods/test/ac8_0303', '0.30.3', AC8_OWN_ROUNDS)),
            ('sdk-0310', modbuilder_wrap('mods/test/ac8_0310', '0.31.0', AC8_OWN_ROUNDS)),
            ('sdk-0310-ack', modbuilder_wrap('mods/test/ac8_0310_ack', '0.31.0',
                AC8_OWN_ROUNDS.replace("changes=", "allow_unverified_effect=true,changes="))),
        ])
        op = only(results['sdk-0303'])
        self.assertNotEqual(op['status'], 'rejected', op.get('error'))
        self.assertEqual(sorted((item['target'], item['field'], item['since']) for item in op['legacy']),
            [('AC-8 Autocannon', 'rounds.spare_rounds', '0.31.0'), ('AC-8 Autocannon', 'rounds.starting_rounds',
             '0.31.0')])
        self.assertEqual(len(legacy_lines(results['sdk-0303'])), 2)
        refused = only(results['sdk-0310'])
        self.assertEqual(refused['status'], 'rejected')
        self.assertIn('field requires allow_unverified_effect=true', refused['error'])
        current = only(results['sdk-0310-ack'])
        self.assertNotEqual(current['status'], 'rejected', current.get('error'))
        self.assertFalse(current['legacy'])


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

    def test_ac8_own_rounds(self):
        # The AC-8 carries 20 rounds (4 clips) of its own: maximum, start and supply in its rounds record (+80/+88/+84).
        result = snapshot_run(r'''
update=update or function()end
local ac8=hd2.support_weapon('AC-8 Autocannon')
local rounds={{field='rounds.spare_rounds',expect=0,value=20},{field='rounds.starting_rounds',expect=0,value=20},
    {field='rounds.rounds_from_supply',expect=0,value=20}}
local where=resolve('transaction',{id='w',target=ac8,allow_unverified_effect=true,changes=rounds})
check(#where==3,'three members of the AC-8 rounds record: '..#where)
local h={}
events.run_as('mods/test/team_reload_ac8',function()
    h.weapon=hd2.ensure({transaction={id='ac8-own-rounds',target=ac8,allow_unverified_effect=true,changes=rounds}})
end)
settle({h.weapon})
check(h.weapon.runs>=1 and h.weapon.result.status=='APPLIED','weapon '..tostring(h.weapon.error))
for _,item in ipairs(where)do check(runtime.read(item.at,4)==b.encode(20,'u32'),item.label..' written')end
local n=0
for _ in pairs(overlay)do n=n+1 end
check(n==3,'exactly three members written: '..n)
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
