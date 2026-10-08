"""Regression tests against the built runtime ZIP, not the source tree.

Source-tree tests preload every module, which hid a module first required at apply
time (hd2runtime/core/fingerprint) that the engine can no longer resolve after
startup. These tests read the shipped archive and emulate that lookup window.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from support import ROOT
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'sdk'))
import build_release
import hd2
from hd2_archive import ARCHIVE_NAME, make_archive, resource_hash, lua_resource
import validate_packaged_runtime as packaged
from tools.lua_runner import execute

VERSION = (ROOT/'VERSION').read_text().strip()
# 0.23.1 library entry: requires the API directly, capturing nothing.
UNCAPTURED_ENTRY = b'''-- HD2-Addon: mods/skyeshade/hd2runtime
local loader=rawget(_G,'CowboyBingusModLoader')
assert(loader and loader.api==1 and type(loader.version)=='number' and loader.version>=16,
    'HD2Runtime requires Bingus Shared Loader v15+ / API 1')
local existing=rawget(_G,'HD2RuntimeLibraryApi1')
if existing then return existing end
local hd2=require('hd2runtime/api/hd2')
rawset(_G,'HD2RuntimeLibraryApi1',hd2)
return hd2
'''


def runtime_zip_with(resources, folder):
    path = Path(folder)/'runtime.zip'
    archive = make_archive({resource_hash(k): lua_resource(v) for k, v in resources.items()})
    hd2.zip_files(path, {'runtime/'+ARCHIVE_NAME: archive})
    return path


class PackagedRuntimeStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            cls.resources = packaged.archive_resources(build_release.build_runtime(VERSION, folder=folder))
        cls.scan = packaged.static_scan(cls.resources)

    def test_every_referenced_internal_module_resolves_from_the_artifact(self):
        self.assertEqual(self.scan['unresolved'], [])
        self.assertGreater(self.scan['referencedModules'], 40)
        for name in ('hd2runtime/core/fingerprint', 'hd2runtime/runtime/metrics',
                     'hd2runtime/domains/player_weapon_writes', 'hd2runtime/domains/attachment_writes'):
            self.assertIn(resource_hash(name), self.resources, name)

    def test_package_module_list_covers_every_shipped_module(self):
        self.assertTrue(self.scan['packageModuleList'])
        listed = {resource_hash(name) for name in self.scan['names']
                  if name != packaged.PACKAGE_MODULES}
        shipped = set(self.resources) - {resource_hash(packaged.ENTRY), resource_hash(packaged.PACKAGE_MODULES)}
        self.assertEqual(listed & shipped, shipped)
        self.assertEqual(self.scan['unnamedResources'], 0)

    def test_every_source_require_literal_is_shipped(self):
        # Catches a stale path or an unpackaged folder before any artifact is built.
        shipped = set(build_release.runtime_resources())
        for folder in ('api', 'core', 'runtime', 'schemas', 'domains'):
            for path in sorted((ROOT/folder).glob('*.lua')):
                if path.name == 'addon.lua':
                    continue
                for match in packaged.REFERENCE.finditer(path.read_bytes()):
                    if match.group(1).decode() in packaged.INSTALL_OPTION_RESOURCES:
                        continue        # shipped in its install option's own archive (the manifest test)
                    self.assertIn(match.group(1).decode(), shipped, str(path.relative_to(ROOT)))

    def test_entry_captures_loaders_at_startup_without_running_modules(self):
        names = [name for name in self.scan['names'] if name not in packaged.INSTALL_OPTION_RESOURCES]
        table = {name: self.resources[resource_hash(name)] for name in names + [packaged.ENTRY]}
        program = ('local RESOURCES={' + ','.join('[' + packaged.lua(k) + ']=' + packaged.lua_bytes(v)
            for k, v in table.items()) + '}\n' + r'''
local open=true
local function engine(name)
 local body=RESOURCES[name]
 if not body then return '\n\tno resource '..name end
 if not open then return '\n\tno resource '..name..' (startup package unloaded)' end
 return assert(loadstring(body,'@'..name..'.lua'))
end
local keep=package.loaders[1]
for i=#package.loaders,1,-1 do package.loaders[i]=nil end
package.loaders[1]=keep;package.loaders[2]=engine
rawset(_G,'CowboyBingusModLoader',{api=1,version=16,open_log=function()return nil end})
require('mods/skyeshade/hd2runtime')
open=false
local ran_early=package.loaded['hd2runtime/core/fingerprint']~=nil
local captured=0
for _,name in ipairs(require('hd2runtime/runtime/package_modules'))do
 if package.loaded[name]==nil then assert(type(package.preload[name])=='function',name);captured=captured+1 end
end
local fingerprint=require('hd2runtime/core/fingerprint')
assert(type(fingerprint.matches)=='function')
return (ran_early and 'early' or 'lazy')..' '..captured
''')
        state, captured = execute(program.encode()).decode().split()
        self.assertEqual(state, 'lazy')
        self.assertGreater(int(captured), 10)


@unittest.skipUnless(packaged.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class PackagedRuntimeManifestTests(unittest.TestCase):
    def test_the_runtime_zip_carries_the_logo_for_the_mod_manager(self):
        import zipfile
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(build_release.build_runtime(VERSION, folder=folder)) as z:
                manifest = json.loads(z.read('manifest.json'))
                thumbnail = z.read('thumbnail.png')
                setting = z.read(build_release.WHEEL_HOOK_OFF_FOLDER + '/' + ARCHIVE_NAME)
        self.assertEqual(manifest['IconPath'], 'thumbnail.png')
        self.assertEqual([o['Image'] for o in manifest['Options']], ['thumbnail.png', 'thumbnail.png'])
        # 0.30.2: the second option (the mod manager's choice) also deploys the "mouse wheel hook off" setting.
        self.assertEqual([o['Include'] for o in manifest['Options']],
            [['runtime'], ['runtime', build_release.WHEEL_HOOK_OFF_FOLDER]])
        self.assertIn('GameGuard', manifest['Options'][1]['Name'])
        from hd2_archive import read_archive
        resources = read_archive(setting, b'')
        self.assertEqual([h for _, h in resources], [resource_hash('hd2runtime/settings/wheel_hook_off')])
        self.assertIn(b'return true', list(resources.values())[0][0])
        self.assertEqual(thumbnail, (ROOT / 'packaging/thumbnail.png').read_bytes())
        self.assertEqual(thumbnail[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(int.from_bytes(thumbnail[16:20], 'big'), 512)


class PackagedRuntimeSnapshotTests(unittest.TestCase):
    def test_built_artifact_applies_every_domain_with_late_lookups_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            result = packaged.validate(build_release.build_runtime(VERSION, folder=folder))
        self.assertEqual(set(result['scenarios']), set(packaged.SCENARIOS))
        for name, item in result['scenarios'].items():
            self.assertTrue(item['passed'], name)
            self.assertEqual(item['lateLookupsMissing'], [], name)
            self.assertLessEqual(item['moduleHashes'], 2, name)
            if packaged.EXTRAS.get(name, {}).get('readOnly'):
                self.assertEqual(item['overlayWrites'], 0, name)   # event-only mods observe, never write
            elif packaged.EXTRAS.get(name, {}).get('missionOnly'):
                self.assertEqual(item['overlayWrites'], 0, name)   # aboard the ship: nothing applies (see below)
            else:
                self.assertGreater(item['overlayWrites'], 0, name)

    def test_mission_only_scenarios_write_on_a_retained_mission_snapshot(self):
        import build_profile
        mission = build_profile.snapshot_directory() / 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'
        if not mission.is_file():
            self.skipTest('no retained mission snapshot')
        names = sorted(name for name, extra in packaged.EXTRAS.items() if extra.get('missionOnly'))
        self.assertIn('client-write-proof', names)
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            result = packaged.validate(build_release.build_runtime(VERSION, folder=folder), mission, names)
        for name in names:
            item = result['scenarios'][name]
            self.assertTrue(item['passed'], name)
            self.assertGreater(item['overlayWrites'], 0, name)       # the expected writes happened

    def test_a_refused_or_skipped_write_fails_its_scenario_from_the_built_artifact(self):
        # One operation applies; another is refused at registration and the addon keeps no handle for it; a third is
        # refused only when it applies (its expect is stale). The resulting state holds the one good write, which is
        # what the validator used to look at; now each refused operation fails the scenario by name.
        addon = r'''local hd2=require('mods/skyeshade/hd2runtime')
hd2.ensure({patch={id='silently-refused',target=hd2.weapon('PLAS-101 Purifier'):attack('primary'):projectile(),
    allow_shared=true,field=hd2.fields.projectile.drag,expect=1.5,value=0.8}})
hd2.patch({id='stale-expect',target=hd2.weapon('AR-23 Liberator'),field=hd2.fields.weapon.fire_rate,expect=1,
    value=2})
return hd2.patch({id='concussive-fire-rate',target=hd2.weapon('AR-23C Liberator Concussive'),
    field=hd2.fields.weapon.fire_rate,expect=400,value=1100})
'''
        packaged.SCENARIOS['silent-refusal'] = lambda: addon
        try:
            with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
                with self.assertRaises(AssertionError) as caught:
                    packaged.validate(build_release.build_runtime(VERSION, folder=folder), scenarios=['silent-refusal'])
        finally:
            del packaged.SCENARIOS['silent-refusal']
        message = str(caught.exception)
        self.assertIn('silent-refusal: silently-refused: rejected unexpectedly', message)
        self.assertIn('required since SDK 0.28.0', message)   # a bare addon declares no SDK: the current rule
        self.assertIn('silent-refusal: stale-expect: rejected unexpectedly', message)
        self.assertNotIn('concussive-fire-rate:', message)

    def test_validator_reproduces_the_uncaptured_entry_failure(self):
        resources = build_release.runtime_resources()
        resources[hd2.MODULE] = UNCAPTURED_ENTRY
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            with self.assertRaises(AssertionError) as caught:
                packaged.validate(runtime_zip_with(resources, folder), scenarios=['player-weapon-patch'])
        message = str(caught.exception)
        self.assertIn("module 'hd2runtime/core/fingerprint' not found", message)
        self.assertIn('player_weapon_writes.lua', message)


if __name__ == '__main__':
    unittest.main()
