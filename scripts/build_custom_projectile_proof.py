"""Build the Runtime-owned custom projectile row development proof (docs/custom-projectile-rows.md). Never deploys or
launches HD2.

Writes to build/test-artifacts/ (never over the published release ZIPs in build/):
* HD2Runtime-<version>-runtime.zip: the runtime exactly as build_release.py packages it, from this working tree;
* CustomProjectileRowProof-<proof version>.zip: the proof mod (proof/CustomProjectileRowProof), built by the SDK like
  any mod that depends on HD2Runtime;
* ReprimandCustomProjectileProof-<proof version>.zip: the weapon projectile replacement proof
  (proof/ReprimandCustomProjectileProof): the SMG-32 Reprimand fires the slow custom projectile;
* ReprimandFireModeProof-<proof version>.zip: the Reprimand with a Normal / Custom projectile mode, three fire rates and
  a 50-round magazine (proof/ReprimandFireModeProof);
* LiberatorConcussiveFireModeProof-<proof version>.zip: the same on the AR-23C Liberator Concussive
  (proof/LiberatorConcussiveFireModeProof);
* PatriotCustomProjectileProof-<proof version>.zip: the EXO-45 Patriot's minigun fires the slow custom projectile
  (proof/PatriotCustomProjectileProof);
* CustomStratagemP0Proof-<proof version>.zip: 0.10.0 is the read-only live check of the custom icon resource family
  (texture + GUI material) with a vanilla control; it writes nothing (proof/CustomStratagemP0Proof, docs/custom-images.md);
* VirtualSlotProof-<proof version>.zip: the mission-time slot conversion (proof/VirtualSlotProof);
* VirtualSelectorProof-<proof version>.zip: the Runtime-owned custom stratagem selector (proof/VirtualSelectorProof);
* RenderOrderProof-<proof version>.zip: the render-order probe, Runtime GUI over the native UI (proof/RenderOrderProof);
* CustomStratagemPanelProof-<proof version>.zip: the Runtime-owned CUSTOM STRATAGEMS panel (proof/CustomStratagemPanelProof).
* SlotHighlightProof-<proof version>.zip: the native loadout slot highlight moved by data (proof/SlotHighlightProof).
* PanelIconProof-<proof version>.zip: the custom panel icon as the game's icon masks, visual only (proof/PanelIconProof).
* SelectionSoundProof-<proof version>.zip: the loadout screen's own UI sound events through the Wwise Lua API, played
  only on a key, to identify the selection sound (proof/SelectionSoundProof).
* SlotTextureProbe-<proof version>.zip: the native slot icon's render-side texture chain, read only
  (proof/SlotTextureProbe).
* SlotOverlayProof-<proof version>.zip: the custom icon drawn by a Runtime GUI over native slot icons (ship loadout and
  mission HUD) for fake virtual slot identities, visual only (proof/SlotOverlayProof).
* GasBarrageMissionProof-<proof version>.zip: the custom stratagem selector's virtual Gas Barrage slots converted to the
  Orbital 120mm HE Barrage carrier in a solo mission, presented as Orbital Gas Barrage (proof/GasBarrageMissionProof).

Every proof ZIP is opened again after the build: the Lua packed in its archive must be exactly the current src/ (the
addon as the SDK wraps it), every images/<id>.png must be in it as the mod's own texture, and its file name and manifest
must carry the project's VERSION, so a stale ZIP is never handed out for a live test.

--only <proof folder name> builds the runtime and that proof alone.

Validate the runtime ZIP with scripts/validate_packaged_runtime.py before a live test.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'sdk'))
import build_release  # noqa: E402
import hd2  # noqa: E402
from tools.hd2_archive import LUA_TYPE, TEXTURE_TYPE, read_archive, resource_hash  # noqa: E402
from tools.hd2_image import MATERIAL_TYPE  # noqa: E402

PROJECTS = [ROOT / 'proof/CustomProjectileRowProof', ROOT / 'proof/ReprimandCustomProjectileProof',
    ROOT / 'proof/ReprimandFireModeProof', ROOT / 'proof/LiberatorConcussiveFireModeProof',
    ROOT / 'proof/PatriotCustomProjectileProof', ROOT / 'proof/CustomStratagemP0Proof', ROOT / 'proof/VirtualSlotProof',
    ROOT / 'proof/VirtualSelectorProof',
    ROOT / 'proof/RenderOrderProof',
    ROOT / 'proof/CustomStratagemPanelProof', ROOT / 'proof/SlotHighlightProof', ROOT / 'proof/PanelIconProof',
    ROOT / 'proof/SelectionSoundProof', ROOT / 'proof/SlotTextureProbe', ROOT / 'proof/SlotOverlayProof',
    ROOT / 'proof/GasBarrageMissionProof', ROOT / 'proof/GasBarragePayloadProof', ROOT / 'proof/GasBarrageCooldownProof',
    ROOT / 'proof/BeaconProbe', ROOT / 'proof/BeaconRedirectProof', ROOT / 'proof/BeaconTimingProof',
    ROOT / 'proof/GasShellProof', ROOT / 'proof/PodProbe', ROOT / 'proof/PelicanProbe',
    ROOT / 'proof/PelicanSpawnProof', ROOT / 'proof/PelicanCasProof',
    ROOT / 'proof/PelicanOrbitProof', ROOT / 'proof/ExtractionPelicanProbe', ROOT / 'proof/PelicanTurretProbe',
    ROOT / 'proof/PelicanGatlingProof', ROOT / 'proof/PelicanWeaponBehaviorProof',
    ROOT / 'proof/PelicanGatlingAIProof',
    # The custom stratagem API examples (docs/custom-stratagem-api.md): the public API only.
    ROOT / 'proof/PelicanCasExample', ROOT / 'proof/GasBarrageExample', ROOT / 'proof/GasEatExample',
    ROOT / 'proof/HmgSentryExample', ROOT / 'proof/EagleStunRocketPodsExample',
    # The Runtime-to-Runtime peer channel's first live proof (research/docs/runtime-peer-messaging-F5FEE03DCFDB.md).
    ROOT / 'proof/RuntimePeerHelloProof']
# proof/CustomStratagemP0Proof 0.10.0 is the read-only custom icon family probe (it writes nothing). Its 0.9.0 (a custom
# icon written into presentation_icon) crashed the game and is kept only in live-2026-10-01-custom-icon-CRASHED.
OUTPUT = ROOT / 'build/test-artifacts'


def packed(path: Path):
    """The Lua resources (name hash -> source) and the icon resources ((type, name hash) -> (main, GPU part)) of the
    archive inside a built mod ZIP, and its manifest."""
    with zipfile.ZipFile(path) as package:
        name = next(name for name in package.namelist() if name.endswith('.patch_0'))
        data, gpu = package.read(name), package.read(name + '.gpu_resources')
        manifest = json.loads(package.read('manifest.json'))
    found, textures = {}, {}
    for (kind, key), (main, part) in read_archive(data, gpu).items():
        if kind in (TEXTURE_TYPE, MATERIAL_TYPE):
            textures[(kind, key)] = (main, part)
            continue
        if kind != LUA_TYPE:
            raise ValueError('%s: unexpected resource type %016X' % (path.name, kind))
        length, version = struct.unpack_from('<II', main, 0)
        if version != 2:
            raise ValueError('%s: unexpected Lua resource version %d' % (path.name, version))
        found[key] = main[8:8 + length]
    return found, textures, manifest


def verify(project: Path, path: Path):
    """The built ZIP holds exactly this project's current sources and VERSION; raises otherwise."""
    spec = json.loads((project / 'hd2runtime.json').read_text(encoding='utf-8'))
    version = (project / 'VERSION').read_text(encoding='utf-8').strip()
    expected = {}
    for source in sorted((project / 'src').rglob('*.lua')):
        relative = source.relative_to(project / 'src').with_suffix('').as_posix()
        resource = spec['resource'] if relative == 'addon' else spec['resource'] + '/' + relative
        body = source.read_text(encoding='utf-8-sig')
        if relative == 'addon':
            body = hd2.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body, spec.get('name'))
        expected[resource_hash(resource)] = body.encode()
    found, textures, manifest = packed(path)
    # The build record of the icons (<resource>/hd2runtime_images): every current PNG's SHA-256 and resource name.
    record = found.pop(resource_hash(spec['resource'] + '/' + hd2.IMAGE_RECORD), None)
    pngs = hd2.project_images(project)
    if pngs:
        text = (record or b'').decode('utf-8', 'replace')
        for image_id, png in pngs.items():
            if (hashlib.sha256(png).hexdigest() not in text or '"%s/images/%s"' % (spec['resource'], image_id) not in text
                    or '"images/%s.png"' % image_id not in text):
                raise ValueError('%s: its icon build record does not name the current images/%s.png' % (path.name,
                    image_id))
    elif record is not None:
        raise ValueError('%s carries an icon build record but %s has no images' % (path.name, project.name))
    if found != expected:
        raise ValueError('%s does not hold the current %s sources' % (path.name, project.name))
    # The icon families compiled from the project's editable PNGs, exactly as the SDK build compiles them (masks
    # prepared automatically; its source-hash cache), and every editable PNG itself beside the manifest.
    images, _, _ = hd2.project_icon_resources(project, spec)
    if textures != images:
        raise ValueError('%s does not hold the current %s images' % (path.name, project.name))
    with zipfile.ZipFile(path) as package:
        shipped = {name[len('images/'):-len('.png')]: package.read(name) for name in package.namelist()
            if name.startswith('images/') and name.endswith('.png')}
    if shipped != hd2.project_images(project):
        raise ValueError('%s does not carry the current editable images/<id>.png of %s' % (path.name, project.name))
    # Every image the addon names (hd2.resources.image('<id>')) is one the ZIP itself packs.
    named = set(re.findall(r"hd2\.resources\.image\('([a-z0-9_]+)'\)",
        (project / 'src/addon.lua').read_text(encoding='utf-8-sig')))
    missing = named - set(hd2.project_images(project))
    if missing:
        raise ValueError('%s names images it does not pack: %s' % (project.name, ', '.join(sorted(missing))))
    if path.name != '%s-%s.zip' % (project.name, version) or manifest.get('Name') != '%s %s' % (spec['name'], version):
        raise ValueError('%s does not carry %s VERSION %s' % (path.name, project.name, version))


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', choices=[project.name for project in PROJECTS])
    only = parser.parse_args().only
    projects = [project for project in PROJECTS if only in (None, project.name)]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for project in projects:
        body = (project / 'src/addon.lua').read_bytes()
        for forbidden in (b'VirtualProtect', b'WriteProcessMemory', b'ffi', b'windows_write', b'.write('):
            if forbidden in body:
                raise ValueError(project.name + ' must not write memory itself: ' + forbidden.decode())
    version = (ROOT / 'VERSION').read_text().strip()
    built = [build_release.build_runtime(version, folder=OUTPUT)]
    for project in projects:
        made = hd2.build_project(project)
        proof = OUTPUT / made.name
        shutil.copyfile(made, proof)
        verify(project, proof)
        built.append(proof)
    for path in built:
        print(path.relative_to(ROOT), hashlib.sha256(path.read_bytes()).hexdigest().upper())


if __name__ == '__main__':
    main()
