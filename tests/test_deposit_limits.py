"""The 1023 deposit limit: research proof, published bounds, runtime refusal and examples agree."""
import json
from pathlib import Path
import re
import unittest

from support import ROOT, run

RESEARCH = json.loads((ROOT / 'research/deposit-limits-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
BACKPACKS = json.loads((ROOT / 'sdk/BackpackAuthoringCapabilities.json').read_text(encoding='utf-8'))


class DepositLimitTests(unittest.TestCase):
    def test_the_research_proves_a_ten_bit_field(self):
        limit = RESEARCH['liveAmountLimit']
        self.assertEqual((limit['fieldType'], limit['field'], limit['bits'], limit['min']),
            ('deposit_value', 'remaining', 10, 0))
        self.assertEqual(limit['max'], limit['min'] + 2 ** limit['bits'] - 1)
        self.assertIsNone(limit['writableControl'])
        self.assertEqual(RESEARCH['writes'], 0)
        # The same type in every retained snapshot, on every object type that carries the live amount.
        self.assertEqual(len(RESEARCH['networkConfig']), 7)
        for config in RESEARCH['networkConfig']:
            self.assertEqual({carrier['remainingType'] for carrier in config['remainingCarriers']}, {472})

    def test_every_published_deposit_field_is_bounded_by_it(self):
        fields = [field for field in RESEARCH['exposedDepositFields'] if field['editable']]
        # Maxigun, Cremator and GL-28 (ammunition), and the five Guard Dog backpacks (drone magazines, the same
        # deposit_value network field): capacity, start, refill.
        self.assertEqual(len(fields), 24)
        self.assertFalse([f for f in RESEARCH['exposedDepositFields'] if f['sdkMaxExceedsLiveLimit']])
        published = self._deposit_fields()
        # 0.31.0: + the five team-reload backpacks (research/team-reload-ammo-F5FEE03DCFDB.json), three fields each,
        # bounded by the same 10-bit network field.
        self.assertEqual(len(published), 24 + 15)
        for field in published:
            self.assertEqual(field['max'], RESEARCH['liveAmountLimit']['max'], field['instanceKey'])
            self.assertIn('deposit_value (10 bits)', field['rangeReason'])

    def _deposit_fields(self):
        found = []

        def walk(value):
            if isinstance(value, dict):
                if str(value.get('semanticFieldId', '')).startswith('deposit.') and value.get('editable'):
                    found.append(value)
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(BACKPACKS)
        return list({field['instanceKey']: field for field in found}.values())

    def test_runtime_refuses_a_value_above_the_limit_with_the_reason(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local writes=require('hd2runtime/domains/entity_writes')
local backpack=hd2.support_weapon('M-1000 Maxigun'):backpack()
local ok,why=pcall(writes.validate_patch,{id='over',target=backpack,allow_unverified_effect=true,
 field=hd2.fields.deposit.capacity,expect=1000,value=1024})
assert(not ok and tostring(why):find('(1 to 1023): the live deposit amount is the engine network field',1,true),tostring(why))
local at=writes.validate_patch{id='at',target=backpack,allow_unverified_effect=true,
 field=hd2.fields.deposit.capacity,expect=1000,value=1023}
assert(at.changes or at.field)
return 'ok'
'''), b'ok')

    def test_no_shipped_example_exceeds_it(self):
        pattern = re.compile(r'deposit\.(?:capacity|start_amount|refill_amount),expect=\d+,value=(\d+)')
        for path in (ROOT / 'examples').rglob('*.lua'):
            for value in pattern.findall(path.read_text(encoding='utf-8')):
                self.assertLessEqual(int(value), 1023, path)


if __name__ == '__main__':
    unittest.main()
