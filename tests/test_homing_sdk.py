import json,sys,unittest
from homing_test_support import ROOT
sys.path.insert(0,str(ROOT/'scripts'))
import generate_events

class HomingSdkTests(unittest.TestCase):
    def test_generated_types_catalogue_and_docs_match_the_source_contract(self):
        classes='\n'.join(generate_events.stub_lines()[0])
        for prefix in ('sdk','starter'):
            self.assertIn(classes,(ROOT/prefix/'stubs/mods/skyeshade/hd2runtime.lua').read_text())
        schema=json.loads((ROOT/'schemas/events.json').read_text())
        catalog=json.loads((ROOT/'sdk/EventCatalog.json').read_text())
        self.assertEqual(schema['api'],catalog['api'])
        for doc in ('projectile-homing.md','homing-lock-on.md'):
            self.assertEqual((ROOT/'docs'/doc).read_bytes(),(ROOT/'sdk/docs'/doc).read_bytes())
