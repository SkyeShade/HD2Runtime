"""Resupply as a supported hd2.stratagem target (scripts/research_resupply.py)."""
import json
import unittest

from support import ROOT, run


class ResupplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/resupply-F5FEE03DCFDB.json').read_text())
        cls.internal = json.loads((ROOT / 'schemas/stratagem_authoring_catalog.json').read_text())['stratagems']
        public = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.public = {x['name']: x for x in public['stratagems']}
        cls.pods = json.loads((ROOT / 'sdk/PodPayloadCapabilities.json').read_text())

    def test_native_identity_is_proven_not_named(self):
        item = self.research['stratagem']
        self.assertEqual((item['nativeType'], item['kind'], item['iconKey']), ('AmmoRack', 33, 'StratagemRessuply'))
        self.assertEqual(len(self.research['snapshots']), 7)   # ship and mission, identical rows in each
        root = item['currentRoot']
        self.assertEqual((root['id'], root['group'], root['row']), (867876502, 1, 0))
        self.assertEqual(root['use_count'], 4294967295)       # native unlimited
        delivery = self.research['delivery']
        self.assertEqual(root['payloads'], [delivery['rack'], delivery['hellpod']] * delivery['payloadPairs'])
        self.assertEqual(root['package'], delivery['rackPackage'])
        self.assertEqual(delivery['spawnPayloadSize'], 4)
        self.assertEqual({s['item'] for s in delivery['slots'][:4]}, {delivery['supplyBox']['resource']})
        self.assertEqual(delivery['supplyBox']['interactTypes'], ['PickupSupplies', 'PickupSuppliesFromRack'])
        reward = self.research['rewardVariant']
        self.assertEqual((reward['nativeType'], reward['exposed'], reward['sharesRack']),
            ('AmmoRack_PresidentReward', False, True))

    def test_medal_payload_is_blocked_with_its_reason(self):
        medal = self.research['medal']
        self.assertEqual(medal['verdict'], 'BLOCKED')
        self.assertIsNone(medal['medalPickupEntity'])
        self.assertEqual(medal['explorationReward']['interactTypes'], [50])
        self.assertNotIn(50, range(medal['provenPickupInteractTypes'][0], medal['provenPickupInteractTypes'][1] + 1))
        self.assertFalse([p for p in self.pods['pickups'] if 'medal' in p['name'].lower()])

    def test_catalog_entry_and_pod_link(self):
        root = self.research['stratagem']['currentRoot']
        entry = self.internal['Resupply']
        self.assertEqual(entry['family'], 'mission')
        self.assertEqual(entry['root'], {k: root[k] for k in ('id', 'package', 'payloads', 'group', 'row')})
        fields = {f['semanticFieldId']: f for f in entry['fields']}
        self.assertEqual((fields['stratagem.cooldown']['backing']['offset'], fields['stratagem.cooldown']['currentDefault']),
            (104, 180))
        self.assertEqual(fields['stratagem.max_uses']['backing']['offset'], 80)
        public = self.public['Resupply']
        self.assertTrue(public['cooldownCapability']['writable'])
        self.assertNotIn('liveEvidence', public['cooldownCapability'])   # only Orbital Precision Strike is live-proven
        rack = next(r for r in self.pods['racks'] if r['name'] == 'Resupply pod')
        self.assertEqual(public['delivers']['semanticId'], rack['semanticId'])
        consumer = next(c for c in rack['consumers'] if c['nativeType'] == 'AmmoRack')
        self.assertEqual(consumer['stratagemSemanticId'], public['semanticId'])
        self.assertTrue(rack['shared'])

    def test_lua_api_guards_and_donor_loading(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(r,t) local ok,why=pcall(patches.validate,r);assert(not ok and tostring(why):find(t,1,true),tostring(why)) end
local resupply=hd2.stratagem('Resupply')
local rack=resupply:delivery():rack()
assert(rack.rack=='Resupply pod'and resupply:payload().rack=='Resupply pod')
patches.validate{id='cooldown',target=resupply,field=hd2.fields.stratagem.definition_cooldown,expect=180,value=5}
rejects({id='cooldown-stale',target=resupply,field=hd2.fields.stratagem.definition_cooldown,expect=150,value=5},'')
local supply=rack:slot(1):current();local grenades=hd2.pickup('Grenade Box')
assert(supply.name=='Supply Box')
local swap=patches.validate{id='swap',target=rack:slot(1),field=hd2.fields.payload.entity,expect=supply,value=grenades,
 allow_unverified_reference=true,allow_shared=true}
assert(#swap.asset_dependencies==1,'the grenade box package is a declared dependency')
local vanilla=patches.validate{id='vanilla',target=rack:slot(1),field=hd2.fields.payload.entity,expect=supply,value=supply,
 allow_shared=true}
assert(#vanilla.asset_dependencies==0,'the resident supply box needs no package')
rejects({id='a',target=rack:slot(1),field=hd2.fields.payload.entity,expect=supply,value=grenades,allow_shared=true},
 'allow_unverified_reference')
rejects({id='b',target=rack:slot(1),field=hd2.fields.payload.entity,expect=supply,value=grenades,
 allow_unverified_reference=true},'allow_shared')
rejects({id='c',target=rack:slot(1),field=hd2.fields.payload.entity,expect=supply,value='0x30212B6E5858AEEF',
 allow_unverified_reference=true,allow_shared=true},'not a reviewed pickup')
rejects({id='d',target=rack:slot(1),field=hd2.fields.payload.entity,expect=grenades,value=supply,allow_shared=true},
 'expect differs')
assert(not pcall(hd2.pickup,'Medal'))
assert(not pcall(function()return rack:slot(5)end))
return 'ok'
''').decode().strip().splitlines()[-1], 'ok')

    def test_option_switch_between_payloads_is_an_owned_transition(self):
        # An 8-byte slot reference is written as two dwords; each dword keeps the ensure's owned bytes, so moving an
        # option from one replacement to another (or back to vanilla) is not a conflict. Third-party bytes still are.
        self.assertEqual(run(r'''
local writes=require('hd2runtime/domains/pod_payload_writes')
local A,B,C,D=('\1\0\0\0\2\0\0\0'),('\3\0\0\0\4\0\0\0'),('\5\0\0\0\2\0\0\0'),('\7\0\0\0\8\0\0\0')
local function plan(current,owned)
 local resolved={record={bytes=current..('\0'):rep(56),owner={},offset=0},
  rack={recordIndex=1,shared=true,consumers={1,2},semanticId='pod-rack/test'}}
 return writes.prepare(resolved,{snapshots={}},{changes={{field='payload.entity',canonical_field='payload.entity',
  offset=0,width=8,expected=A,desired=B,owned=owned}}})
end
-- Current bytes are the previously applied replacement C: both dwords resolve against C (the high dword of C
-- equals the vanilla high dword, which is also accepted).
local p=plan(C,C)
assert(#p.changes==2 and p.changes[1].expected==C:sub(1,4)and p.changes[2].expected==C:sub(5,8))
assert(p.changes[1].desired==B:sub(1,4)and p.changes[2].desired==B:sub(5,8))
-- Back to vanilla (desired == expected): still the owned transition.
local ok=pcall(function()
 local resolved={record={bytes=C..('\0'):rep(56),owner={},offset=0},
  rack={recordIndex=1,shared=true,consumers={1,2},semanticId='pod-rack/test'}}
 return writes.prepare(resolved,{snapshots={}},{changes={{field='payload.entity',canonical_field='payload.entity',
  offset=0,width=8,expected=A,desired=A,owned=C}}})
end)
assert(ok,'restoring vanilla from an owned replacement conflicted')
-- Without ownership, or with a third-party value, it stays a conflict.
local refused,why=pcall(plan,C,nil);assert(not refused and tostring(why):find('CONFLICT',1,true),tostring(why))
refused,why=pcall(plan,D,C);assert(not refused and tostring(why):find('CONFLICT',1,true),tostring(why))
return 'ok'
''').decode().strip().splitlines()[-1], 'ok')


if __name__ == '__main__':
    unittest.main()
