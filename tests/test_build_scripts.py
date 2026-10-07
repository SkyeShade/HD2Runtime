"""How a project finds the SDK and reports a failed build (GitHub issue #2: an example extracted into the SDK folder
failed with a wrong path, and a double-clicked build closed before its error could be read):
  * every example's build.py is the SDK template's;
  * the template finds the SDK through HD2RUNTIME_SDK, the configured path, the project's folder or one above it being
    the SDK, or a subfolder named sdk or ending in -sdk beside one of them; with none it says what to do and exits 1;
  * the shipped examples' hd2runtime.json points at an SDK extracted beside the example-projects ZIP, and the ZIP's
    README explains that layout;
  * the ModTemplate's build.cmd keeps a failed build's exit status (and pauses only when it owns its window)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from support import ROOT
import build_release

TEMPLATE = ROOT / 'sdk/templates/build.py'


def make_project(folder, sdk_path='no-such-sdk'):
    folder.mkdir(parents=True)
    shutil.copy(TEMPLATE, folder / 'build.py')
    (folder / 'hd2runtime.json').write_text(json.dumps({'sdk': sdk_path}))
    return folder


def make_sdk(folder):
    folder.mkdir(parents=True)
    (folder / 'metadata.json').write_text('{}')
    # A stand-in hd2.py: reports the SDK it was run from and the project it was given.
    (folder / 'hd2.py').write_text('import sys\nfrom pathlib import Path\n'
        'print("built", Path(__file__).resolve().parent.name, Path(sys.argv[2]).name)\n')
    return folder


def run_build(project, env=None):
    environment = {k: v for k, v in os.environ.items() if k != 'HD2RUNTIME_SDK'}
    environment.update(env or {})
    return subprocess.run([sys.executable, '-B', str(project / 'build.py')], capture_output=True, text=True,
        stdin=subprocess.DEVNULL, env=environment, timeout=60)


class ExampleBuildScriptTests(unittest.TestCase):
    def test_every_example_uses_the_sdk_template(self):
        scripts = sorted((ROOT / 'examples').glob('*/*/build.py'))
        self.assertGreater(len(scripts), 100)
        for path in scripts:
            self.assertEqual(path.read_bytes(), TEMPLATE.read_bytes(), path)

    def test_the_sdk_is_found_wherever_the_issue_put_it(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            root = Path(folder)
            # The issue's layout: the example inside the extracted SDK, its configured ../../../sdk pointing nowhere.
            sdk = make_sdk(root / 'HD2 Mods/SDK shi/SDK')
            result = run_build(make_project(sdk / 'KillStackDamageTest', '../../../sdk'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('built SDK KillStackDamageTest', result.stdout)
            # Side by side, the release layout: a sibling folder ending in -sdk.
            make_sdk(root / 'side/HD2Runtime-9.9.9-sdk')
            result = run_build(make_project(root / 'side/HD2Runtime-9.9.9-example-projects/KillHealTest'))
            self.assertIn('built HD2Runtime-9.9.9-sdk KillHealTest', result.stdout)
            # A folder named sdk above the project.
            make_sdk(root / 'up/sdk')
            result = run_build(make_project(root / 'up/a/b/c/Mod'))
            self.assertIn('built sdk Mod', result.stdout)
            # The configured path wins over the search, and HD2RUNTIME_SDK over both.
            make_sdk(root / 'up/a/Configured')
            result = run_build(make_project(root / 'up/a/b/Other', '../../Configured'))
            self.assertIn('built Configured Other', result.stdout)
            named = make_sdk(root / 'Named')
            result = run_build(root / 'up/a/b/Other', {'HD2RUNTIME_SDK': str(named)})
            self.assertIn('built Named Other', result.stdout)

    def test_no_sdk_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as folder:
            project = make_project(Path(folder) / 'Lonely')
            # A folder named sdk without hd2.py and metadata.json is not an SDK.
            (Path(folder) / 'sdk').mkdir()
            result = run_build(project)
            self.assertEqual(result.returncode, 1)
            self.assertIn('HD2Runtime SDK not found', result.stderr)
            self.assertIn('hd2.py configure "' + str(project) + '" --sdk <SDK>', result.stderr)
            self.assertIn('HD2RUNTIME_SDK', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_a_failing_sdk_build_keeps_its_status_without_a_window(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            sdk = make_sdk(Path(folder) / 'sdk')
            (sdk / 'hd2.py').write_text('import sys\nsys.exit(3)\n')
            result = run_build(make_project(Path(folder) / 'Mod'))
            self.assertEqual(result.returncode, 3)
            self.assertNotIn('Press Enter', result.stdout)


class ShippedExampleTests(unittest.TestCase):
    def test_shipped_configs_point_beside_the_examples_zip(self):
        data = (ROOT / 'examples/projects/KillHealTest/hd2runtime.json').read_bytes()
        shipped = json.loads(build_release.example_config(data, '1.2.3'))
        original = json.loads(data)
        self.assertEqual(shipped['sdk'], '../../HD2Runtime-1.2.3-sdk')
        self.assertEqual(shipped['ide_library'], '../../HD2Runtime-1.2.3-sdk/stubs')
        self.assertEqual({k: v for k, v in shipped.items() if k not in ('sdk', 'ide_library')},
            {k: v for k, v in original.items() if k not in ('sdk', 'ide_library')})
        readme = build_release.examples_readme('1.2.3').decode()
        for text in ('HD2Runtime-1.2.3-sdk/', 'HD2Runtime-1.2.3-example-projects/', 'python build.py',
                'HD2RUNTIME_SDK', 'hd2.py configure <example folder> --sdk <SDK>'):
            self.assertIn(text, readme)


@unittest.skipUnless(os.name == 'nt', 'Windows batch file')
class StarterBuildCmdTests(unittest.TestCase):
    def test_a_failed_build_keeps_its_status(self):
        windows = Path(os.environ.get('WINDIR', r'C:\Windows'))
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            project = Path(folder) / 'Starter'
            shutil.copytree(ROOT / 'starter', project, ignore=shutil.ignore_patterns('build'))
            config = json.loads((project / 'hd2runtime.json').read_text())
            config['resource'] = 'not a mod id'
            (project / 'hd2runtime.json').write_text(json.dumps(config))
            result = subprocess.run([str(windows / 'System32/cmd.exe'), '/d', '/c', str(project / 'build.cmd')],
                capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('resource must be mods/author/mod_id', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()


class ProjectThumbnailTests(unittest.TestCase):
    """hd2runtime.json "thumbnail": the mod manager logo (HD2 Arsenal) beside the manifest, as the runtime ZIP ships its
    own: the manifest's IconPath and the option's Image; refused outside the project, in images/ or not a PNG."""

    def test_the_thumbnail_becomes_the_manifest_logo(self):
        import importlib.util
        import zipfile
        loader = importlib.util.spec_from_file_location('hd2_sdk_cli', ROOT / 'sdk/hd2.py')
        sdk = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(sdk)
        logo = (ROOT / 'proof/CustomStratagemPack/thumbnail.png').read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / 'LogoMod'
            (project / 'src').mkdir(parents=True)
            (project / 'src/addon.lua').write_text('return true\n', encoding='utf-8')
            (project / 'VERSION').write_text('0.1.0\n')
            (project / 'README.md').write_text('logo test\n')
            (project / 'logo.png').write_bytes(logo)
            spec = {'format': 1, 'name': 'LogoMod', 'resource': 'mods/test/logo_mod',
                'guid': '3e686447-3622-5619-bd50-e59e276bfe8e', 'thumbnail': 'logo.png',
                'requires': {'bingus': {'min_release': 15, 'api': 1}, 'hd2runtime': {'min_version': '0.30.0',
                    'api': 1, 'module': 'mods/skyeshade/hd2runtime'}}}
            (project / 'hd2runtime.json').write_text(json.dumps(spec))
            with zipfile.ZipFile(sdk.build_project(project)) as z:
                manifest = json.loads(z.read('manifest.json'))
                self.assertEqual(z.read('thumbnail.png'), logo)
            self.assertEqual((manifest['IconPath'], manifest['Options'][0]['Image']), ('thumbnail.png', 'thumbnail.png'))
            for bad in ('../logo.png', 'images/x.png', 'README.md', 'missing.png'):
                (project / 'images').mkdir(exist_ok=True)
                if bad == 'images/x.png':
                    (project / 'images/x.png').write_bytes(logo)
                spec['thumbnail'] = bad
                (project / 'hd2runtime.json').write_text(json.dumps(spec))
                with self.assertRaises(ValueError, msg=bad):
                    sdk.project_thumbnail(project, spec)
            shutil.rmtree(project / 'images')

    def test_the_pack_ships_its_logo(self):
        spec = json.loads((ROOT / 'proof/CustomStratagemPack/hd2runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(spec['thumbnail'], 'thumbnail.png')
