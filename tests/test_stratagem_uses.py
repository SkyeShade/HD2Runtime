import json
import unittest

from support import ROOT, run


class StratagemUsesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.fields = [x for x in cls.catalog['fieldInstances'] if x['semanticFieldId'] == 'stratagem.max_uses']

    def test_catalog_wide_native_use_model(self):
        summary = self.catalog['summary']
        self.assertEqual(summary['maxUsesWritable'], 85)
        self.assertEqual(summary['maxUsesByMode'], {'eagle_per_rearm': 8, 'finite': 5, 'unlimited': 80})
        self.assertEqual(summary['maxUsesGameplayProven'], 4)
        for field in self.fields:
            self.assertEqual(field['backingObjectKind'], 'StratagemDefinition')
            if field['usesMode'] is None:
                self.assertFalse(field['editable'])
                continue
            self.assertTrue(field['editable'])
            # The native unlimited value is published as 'unlimited', never as a large count.
            self.assertEqual(field['currentDefault'] == 'unlimited', field['usesMode'] == 'unlimited')
            self.assertEqual(field['nativeUnlimited'], 4294967295)
            self.assertEqual((field['min'], field['max']), (1, 100))
            self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
        by_name = {x['name']: x for x in self.catalog['stratagems']}
        for name in ('EXO-45 Patriot Exosuit', 'EXO-49 Emancipator Exosuit', 'EXO-55 Breakthrough Exosuit',
                     'EXO-51 Lumberer Exosuit'):
            uses = by_name[name]['maxUses']
            self.assertEqual((uses['value'], uses['mode'], uses['gameplayProvenValues']), (3, 'finite', ['unlimited']))
            self.assertEqual(uses['transitions'], ['finite_to_unlimited', 'finite_to_finite'])
        self.assertEqual(by_name['Orbital Laser']['maxUses']['gameplayProvenValues'], [])
        self.assertEqual(by_name['M-102 Gunner FRV']['maxUses']['mode'], 'unlimited')
        self.assertFalse(by_name['Eagle Airstrike']['maxUses']['writable'])

    def test_transitions_and_acknowledgements(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local function rejects(request,text)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
local f=hd2.fields.stratagem.max_uses
-- Gameplay-proven: Exosuit 3 -> unlimited needs no effect acknowledgement.
local plan=patches.validate{id='exo',target=hd2.stratagem('EXO-45 Patriot Exosuit'),field=f,expect=3,value='unlimited'}
assert(plan.changes[1].desired=='\255\255\255\255' and plan.changes[1].expected=='\3\0\0\0','encoded use count')
-- finite -> different finite and unlimited -> finite are not gameplay-proven.
rejects({id='exo5',target=hd2.stratagem('EXO-45 Patriot Exosuit'),field=f,expect=3,value=5},'allow_unverified_effect')
plan=patches.validate{id='exo5',allow_unverified_effect=true,target=hd2.stratagem('EXO-45 Patriot Exosuit'),
 field=f,expect=3,value=5}
assert(plan.changes[1].desired=='\5\0\0\0','encoded use count')
rejects({id='frv',target=hd2.stratagem('M-102 Gunner FRV'),field=f,expect='unlimited',value=2},
 'allow_unverified_effect')
plan=patches.validate{id='frv',allow_unverified_effect=true,target=hd2.stratagem('M-102 Gunner FRV'),
 field=f,expect='unlimited',value=2}
assert(plan.changes[1].expected=='\255\255\255\255' and plan.changes[1].desired=='\2\0\0\0','encoded use count')
transactions.validate{id='laser',allow_unverified_effect=true,target=hd2.stratagem('Orbital Laser'),
 changes={{field=f,expect=3,value='unlimited'}}}
-- Guards: stale expectations, no fake unlimited, range, Eagles.
rejects({id='stale',target=hd2.stratagem('EXO-45 Patriot Exosuit'),field=f,expect='unlimited',value=3},
 'reviewed current value')
rejects({id='huge',allow_unverified_effect=true,target=hd2.stratagem('EXO-45 Patriot Exosuit'),field=f,
 expect=3,value=4294967295},'unlimited')
rejects({id='zero',allow_unverified_effect=true,target=hd2.stratagem('EXO-45 Patriot Exosuit'),field=f,
 expect=3,value=0},'from 1 to 100')
rejects({id='frac',allow_unverified_effect=true,target=hd2.stratagem('EXO-45 Patriot Exosuit'),field=f,
 expect=3,value=2.5},'from 1 to 100')
rejects({id='eagle',allow_unverified_effect=true,target=hd2.stratagem('Eagle Airstrike'),field=f,
 expect=2,value=3},'read-only')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
