import json
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def test_only_own_gameplay_resources_are_bundled(self):
        subprocess.run([sys.executable,'-B',str(ROOT/'build.py')],check=True)
        spec=json.loads((ROOT/'hd2runtime.json').read_text())
        path=ROOT/'build'/(ROOT.name+'-'+(ROOT/'VERSION').read_text().strip()+'.zip')
        with zipfile.ZipFile(path) as archive:
            report=json.loads(archive.read('build-report.json'))
            self.assertFalse(report['runtime_bundled'])
            self.assertFalse(report['sdk_stubs_bundled'])
            self.assertTrue(all(r==spec['resource'] or r.startswith(spec['resource']+'/') for r in report['resources']))
        self.assertFalse((ROOT/'src/hd2runtime').exists())


if __name__=='__main__':unittest.main()
