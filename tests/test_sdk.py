import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import os

from support import ROOT, execute, lua, modules, run
import generate_sdk
import build_release

spec=importlib.util.spec_from_file_location('sdk_cli',ROOT/'sdk/hd2.py')
sdk=importlib.util.module_from_spec(spec);spec.loader.exec_module(sdk)


def archive_sources(path):
    with zipfile.ZipFile(path) as z:
        data=z.read(next(n for n in z.namelist() if n.endswith('.patch_0')))
    count=struct.unpack_from('<I',data,8)[0];found={}
    for i in range(count):
        row=struct.unpack_from('<7Q6I',data,104+i*80)
        length,version=struct.unpack_from('<II',data,row[2]);assert version==2
        found[row[0]]=data[row[2]+8:row[2]+8+length]
    return found


class SDKTests(unittest.TestCase):
    def test_generated_outputs_are_current_and_deterministic(self):
        self.assertEqual(generate_sdk.outputs(),generate_sdk.outputs())
        generate_sdk.generate(check=True)
        self.assertEqual(sdk.database()['runtime_version'],(ROOT/'VERSION').read_text().strip())

    def test_all_fields_preserve_evidence_access_and_unknown_ranges(self):
        schema=sdk.database();count=0
        for r in schema['resources'].values():
            for name,f in r['fields'].items():
                count+=1
                self.assertEqual(name,f['name'])
                self.assertIn(f['domain'],schema['types'])
                self.assertIn('semantic_range',f);self.assertIn('enum',f)
                self.assertFalse(f['evidence']['current_live_ownership_proven'])
                self.assertFalse(f['evidence']['native_consumer_proven'])
                self.assertTrue(set(schema['evidence_categories'])<=set(f['evidence']))
        self.assertEqual(count,104)
        self.assertIsNone(schema['resources']['jar5']['fields']['standard_damage']['semantic_range'])
        self.assertFalse(schema['resources']['maelstrom']['fields']['main_health']['evidence']['prior_live_confirmation'])

    def test_stub_chains_constants_and_contracts_are_generated_and_nonexecuting(self):
        body=(ROOT/'sdk/stubs/mods/skyeshade/hd2runtime.lua').read_text()
        for t in sdk.database()['types'].values():self.assertIn('---@class '+t['class'],body)
        self.assertIn('---@return HD2Projectile\nfunction HD2Weapon:projectile()',body)
        self.assertIn('---@return HD2DamageProfile\nfunction HD2Projectile:damage()',body)
        self.assertIn('---@field armor_penetration "armor_penetration"',body)
        self.assertIn('---@param request HD2EnsureRequest',body)
        self.assertIn('---@class HD2PlanRequest',body)
        self.assertIn('function hd2.plan(request)',body)
        execute(('local body='+lua(body)+";CowboyBingusModLoader={};local chunk=assert(loadstring(body));local ok,why=pcall(chunk);assert(not ok and why:find('authoring%-only'));return 'ok'").encode())

    def test_typed_builders_use_only_existing_mappings_and_no_native_access(self):
        execute((modules()+'''
package.preload['ffi']=function()error('unexpected native access')end
local hd2=require('hd2runtime/api/hd2')
local damage=hd2.weapon('JAR-5 Dominator'):projectile():damage()
assert(damage:describe().fields[hd2.fields.damage.armor_penetration].writable)
assert(damage:read_target().resource=='jar5')
assert(hd2.vehicle('Bastion'):health():describe().fields.main_health.expected==8000)
assert(hd2.stratagem('Shield Relay'):shield():describe().fields.radius.expected==15)
assert(hd2.stratagem('Shield Relay'):payload():describe().fields.lifetime.expected==40)
assert(hd2.stratagem('Orbital Laser'):damage():describe().fields.standard_damage.expected==60)
assert(hd2.stratagem('Orbital Laser'):orbital():describe().fields.interval.expected==0.1)
assert(hd2.equipment('Jump Pack'):recharge():describe().fields.recharge.expected==15)
assert(hd2.equipment('Jump Pack'):jumppack():describe().fields.vertical_launch_velocity.expected==40)
assert(hd2.weapon('AMR'):describe().fields.crosshair_type.expected==3)
assert(not pcall(function()hd2.weapon('AMR'):projectile()end))
assert(not pcall(function()hd2.weapon('Unknown')end))
assert(hd2.enums.projectile_type.jar5==177)
assert(hd2.resources.bastion=='bastion')
return 'ok'
''').encode())

    def test_all_typed_read_targets_resolve_existing_fixture(self):
        run('''
local targets={hd2.weapon('JAR-5 Dominator'):projectile():damage():read_target(),
hd2.weapon('AMR'):read_target(),hd2.vehicle('Bastion'):health():read_target(),
hd2.vehicle('Maelstrom'):health():read_target(),hd2.stratagem('Shield Relay'):read_target(),
hd2.stratagem('Orbital Laser'):read_target(),hd2.equipment('Jump Pack'):read_target()}
local job=hd2.read{targets=targets};for _=1,3000 do if job.step()then break end end
assert(job.status=='complete',job.error);assert(#job.result.targets==7)
assert(job.result.writes==0 and job.result.protection_changes==0)
return 'ok'
''')

    def test_metadata_writes_match_guarded_allowlists_and_constants(self):
        schema=sdk.database();expected={('jar5','armor_penetration'),('shield_relay','radius'),
            ('shield_relay','durability'),('shield_relay','lifetime'),('shield_relay','cooldown')}
        actual={(key,name) for key,r in schema['resources'].items() for name,f in r['fields'].items() if f['writable']}
        self.assertEqual(actual,expected)
        execute((modules()+'local schema='+lua(schema)+'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local c=schema.contracts.patch
patches.validate{id='test',target=hd2.weapon(c.resource):projectile():damage(),field=c.field,expect=c.expect,value=c.value}
local changes={}
for name,f in pairs(schema.contracts.transaction.fields)do changes[#changes+1]={field=name,expect=f.expect,value=f.value}end
local spec=transactions.validate{id='test',target=hd2.stratagem('Shield Relay'),changes=changes}
for _,change in ipairs(spec.changes)do
local field=schema.resources.shield_relay.fields[change.field]
assert(change.component==field.component and change.offset==field.offset and field.expected==change.expect)
end
return 'ok'
''').encode())

    def test_inspection_cli_is_offline_and_reports_access_evidence(self):
        for kind,name in [('weapon','JAR-5 Dominator'),('vehicle','Bastion'),('type','DamageProfile')]:
            result=sdk.inspect(kind,name)
            self.assertFalse(result['current_process_read'])
            self.assertIn('offline schema',sdk.format_inspection(result))
        fields=sdk.inspect('weapon','JAR-5 Dominator')['resources'][0]['fields']
        self.assertTrue(fields['armor_penetration']['writable'])
        self.assertFalse(fields['durable_damage']['writable'])
        with self.assertRaises(ValueError):sdk.inspect('weapon','Unknown')
        authoring=sdk.inspect('weapon','AR-23C Liberator Concussive')
        self.assertEqual(authoring['authoringWeapon']['name'],'AR-23C Liberator Concussive')
        self.assertIn('weapon.fire_rate',sdk.format_inspection(authoring))
        aliases=sdk.format_inspection(sdk.inspect('weapon','P-113 Verdict'))
        self.assertIn('weapon.capacity  integer  deprecated alias; write accepted',aliases)
        self.assertIn('alias_of=magazine.capacity',aliases)
        run=subprocess.run([sys.executable,'-B',str(ROOT/'sdk/hd2.py'),'inspect','type','DamageProfile','--json'],capture_output=True,text=True,check=True)
        self.assertEqual(len(json.loads(run.stdout)['resources']),2)

    def test_generated_mod_has_no_runtime_or_stub_implementation(self):
        from hd2_archive import resource_hash
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            project=sdk.new_project(Path(folder)/'MyMod','mods/test_sdk/my_mod')
            self.assertEqual({p.relative_to(project).as_posix() for p in project.rglob('*.lua')},{'src/addon.lua'})
            path=sdk.build_project(project);sources=archive_sources(path)
            self.assertEqual(set(sources),{resource_hash('mods/test_sdk/my_mod')})
            body=next(iter(sources.values()))
            self.assertIn(b'hd2.fields.damage.armor_penetration',body)
            for forbidden in (b'VirtualProtect',b'VirtualQuery',b'WriteProcessMemory',b'package.preload',b'---@meta',b'function update'):
                self.assertNotIn(forbidden,body)
            config=json.loads((project/'.luarc.json').read_text())
            self.assertEqual((project/config['workspace.library'][0]).resolve(),ROOT/'sdk/stubs')
            with self.assertRaises(ValueError):sdk.new_project(project,'mods/test_sdk/my_mod')
            (project/'src/stubs.lua').write_text('---@meta\nreturn {}')
            with self.assertRaises(ValueError):sdk.build_project(project)

    def test_reserved_resources_and_invalid_package_versions_are_rejected(self):
        for name in (sdk.MODULE,sdk.MODULE+'/copy','mods/codex/loader','../escape','mods/test/'+('x'*250)):
            self.assertFalse(sdk.valid_resource(name))
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            project=sdk.new_project(Path(folder)/'Mod','mods/test_sdk/bad_version')
            (project/'VERSION').write_text('../../escape')
            with self.assertRaises(ValueError):sdk.build_project(project)

    def test_sdk_tools_work_from_an_isolated_copy_without_source_or_game(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            isolated=Path(folder)/'SDK'
            shutil.copytree(ROOT/'sdk',isolated,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            project=Path(folder)/'IndependentMod'
            subprocess.run([sys.executable,'-B',str(isolated/'hd2.py'),'new',str(project),
                            '--name','mods/test_sdk/isolated'],check=True,capture_output=True)
            subprocess.run([sys.executable,'-B',str(project/'build.py')],check=True,capture_output=True)
            sdk_path=(project/json.loads((project/'hd2runtime.json').read_text())['sdk']).resolve()
            self.assertEqual(sdk_path,isolated)
            self.assertEqual(len(archive_sources(project/'build/IndependentMod-0.1.0.zip')),1)

    def test_configuration_preserves_other_ide_settings(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            project=sdk.new_project(Path(folder)/'Mod','mods/test_sdk/config')
            config=json.loads((project/'.luarc.json').read_text())
            config['workspace.library'].append('other-library');config['diagnostics.globals']=['custom_global']
            (project/'.luarc.json').write_text(json.dumps(config))
            sdk.configure(project);sdk.configure(project)
            after=json.loads((project/'.luarc.json').read_text())
            self.assertEqual(after['workspace.library'].count('other-library'),1)
            self.assertEqual(len(after['workspace.library']),2)
            self.assertEqual(after['diagnostics.globals'],['custom_global'])

    def test_standalone_runtime_has_one_entry_no_presets_and_loads_lazily_once(self):
        sources=build_release.runtime_resources()
        self.assertFalse(any('/examples/' in name or '/proof/' in name for name in sources))
        self.assertEqual([n for n,b in sources.items() if b.startswith(b'-- HD2-Addon:')],[sdk.MODULE])
        execute(('local sources='+lua(sources)+'''
for name,body in pairs(sources)do package.preload[name]=function()return assert(loadstring(body,name))()end end
package.preload['ffi']=function()error('native access on load')end
CowboyBingusModLoader={api=1,version=16}
local a=require('mods/skyeshade/hd2runtime')
local b=assert(loadstring(sources['mods/skyeshade/hd2runtime']))()
assert(a==b and a.version=='0.22.0' and update==nil)
return 'ok'
''').encode())

    def test_runtime_and_gameplay_fail_clearly_for_missing_dependencies(self):
        sources=build_release.runtime_resources()
        execute(('local body='+lua(sources[sdk.MODULE])+'''
local ok,why=pcall(assert(loadstring(body)))
assert(not ok and why:find('requires Bingus',1,true));return 'ok'
''').encode())
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            project=sdk.new_project(Path(folder)/'Missing','mods/test_sdk/missing')
            body=next(iter(archive_sources(sdk.build_project(project)).values()))
            for version in ('0.4.0','invalid'):
                execute(('local body='+lua(body)+"\nCowboyBingusModLoader={api=1,version=16}\npackage.preload['mods/skyeshade/hd2runtime']=function()return {version="+lua(version)+",api_version=1}end\nlocal ok,why=pcall(assert(loadstring(body)));assert(not ok and why:find('HD2Runtime'));return 'ok'").encode())

    def test_separate_shield_mod_runs_with_either_discovery_order(self):
        from hd2_archive import resource_hash
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            project=sdk.new_project(Path(folder)/'Shield','mods/test_sdk/shield','shield')
            body=archive_sources(sdk.build_project(project))[resource_hash('mods/test_sdk/shield')]
            sources=build_release.runtime_resources();sources['mods/test_sdk/shield']=body
            for runtime_first in (False,True):
                run((ROOT/'tests/transaction_memory.lua').read_text()+'\nlocal bodies='+lua(sources)+'''
for name,body in pairs(bodies)do
    package.preload[name]=function()return assert(loadstring(body,name))()end
    package.loaded[name]=nil
end
CowboyBingusModLoader={api=1,version=16}
package.preload['hd2runtime/runtime/windows_write']=function()return {create=function()return runtime end}end
package.preload['hd2runtime/runtime/log']=function()return {emit=function(line)logs[#logs+1]=line end}end
'''+('require("mods/skyeshade/hd2runtime")\n' if runtime_first else '')+'''
local state=require('mods/test_sdk/shield')
for _=1,3000 do update(0.1);if state.runs==1 then break end end
assert(state.runs==1 and state.status=='waiting',state.error)
assert_values('new');protection_is(2);assert(#writes==4)
local api=require('mods/skyeshade/hd2runtime')
assert(assert(loadstring(bodies['mods/skyeshade/hd2runtime']))()==api)
assert(assert(loadstring(bodies['mods/test_sdk/shield']))()==state)
assert(#writes==4);state.cancel();update(0);assert(update==nil)
return 'ok'
''')

    def test_standalone_starter_inventory_and_bundled_stub(self):
        version=(ROOT/'VERSION').read_text().strip()
        path=build_release.build_starter(version)
        with zipfile.ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()),{
                'VERSION','README.md','hd2runtime.json','.luarc.json','.gitignore',
                'build.cmd','build.ps1','src/addon.lua',
                'stubs/mods/skyeshade/hd2runtime.lua'})
            config=json.loads(archive.read('.luarc.json'))
            self.assertEqual(config['workspace.library'],['./stubs'])
            stub=archive.read('stubs/mods/skyeshade/hd2runtime.lua')
            self.assertEqual(stub,(ROOT/'sdk/stubs/mods/skyeshade/hd2runtime.lua').read_bytes())
            self.assertIn(b'HD2DamageProfile',stub)
            self.assertIn(b'---@field armor_penetration "armor_penetration"',stub)
            source=archive.read('src/addon.lua')
            self.assertIn(b"require('mods/skyeshade/hd2runtime')",source)
            self.assertNotIn(b'VirtualProtect',source)
            self.assertNotIn(b'python',archive.read('build.cmd').lower())
            self.assertNotIn(b'python.exe',archive.read('build.ps1').lower())
            self.assertNotIn(b'py -',archive.read('build.ps1').lower())

    def test_clean_starter_builds_with_powershell_and_cmd_without_python_on_path(self):
        from hd2_archive import resource_hash
        version=(ROOT/'VERSION').read_text().strip()
        starter=build_release.build_starter(version)
        windows=Path(os.environ.get('WINDIR',r'C:\Windows'))
        clean_path=os.pathsep.join([str(windows/'System32'),
            str(windows/'System32/WindowsPowerShell/v1.0'),str(windows/'System32/Wbem')])
        environment={**os.environ,'PATH':clean_path,'PYTHONHOME':'','PYTHONPATH':''}
        for command in ('powershell','cmd'):
            with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
                project=Path(folder)/'Starter';project.mkdir()
                with zipfile.ZipFile(starter) as archive:archive.extractall(project)
                config=json.loads((project/'hd2runtime.json').read_text())
                config['name']='Starter Test';config['resource']='mods/test_starter/clean_build'
                (project/'hd2runtime.json').write_text(json.dumps(config,indent=2))
                if command=='powershell':
                    invocation=[str(windows/'System32/WindowsPowerShell/v1.0/powershell.exe'),
                        '-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',str(project/'build.ps1')]
                else:
                    invocation=[str(windows/'System32/cmd.exe'),'/d','/c',str(project/'build.cmd')]
                result=subprocess.run(invocation,cwd=project,env=environment,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
                output=project/'build/Starter-Test-0.1.0.zip'
                self.assertTrue(output.is_file())
                with zipfile.ZipFile(output) as package:
                    self.assertIsNone(package.testzip())
                    self.assertEqual(set(package.namelist()),{'manifest.json','hd2runtime.json',
                        'build-report.json','README.md','mod/9ba626afa44a3aa3.patch_0',
                        'mod/9ba626afa44a3aa3.patch_0.stream',
                        'mod/9ba626afa44a3aa3.patch_0.gpu_resources'})
                    report=json.loads(package.read('build-report.json'))
                    self.assertFalse(report['runtime_bundled']);self.assertFalse(report['sdk_stubs_bundled'])
                    dependency=json.loads(package.read('hd2runtime.json'))
                    self.assertEqual(dependency['requires']['bingus'],{'min_release':15,'api':1})
                    self.assertEqual(dependency['requires']['hd2runtime']['module'],sdk.MODULE)
                sources=archive_sources(output)
                self.assertEqual(set(sources),{resource_hash('mods/test_starter/clean_build')})
                body=next(iter(sources.values()))
                self.assertIn(b"require('mods/skyeshade/hd2runtime')",body)
                self.assertIn(b'hd2.fields.damage.armor_penetration',body)
                for forbidden in (b'VirtualProtect',b'VirtualQuery',b'WriteProcessMemory',
                                  b'package.preload',b'---@meta',b'hd2runtime/core/'):
                    self.assertNotIn(forbidden,body)


if __name__=='__main__':unittest.main()
