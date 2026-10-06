"""Generate domains/stratagem_selector.lua: the loadout screen, its local record and slot repaint, the game's menu input
actions, the engine font and the pinned code that runtime/stratagem_selector.lua (development) re-proves first, from
research/runtime-stratagem-ui-F5FEE03DCFDB.json (docs/custom-stratagems.md, "A Runtime-owned custom stratagem
selector").
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/runtime-stratagem-ui-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/stratagem_selector.lua'


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('selector research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDllSha256'] not in profile or research['exeSha256'] not in profile:
        raise ValueError('the selector research covers another build than schemas/current.lua')
    if not all(s['font'] == 'present' and s['fontMaterial'] == 'present' for s in research['snapshots'].values()):
        raise ValueError('the engine font is not proven resident in every snapshot')
    if not all(s['cameraUnit'] == 'present' and s['shadingEnvironment'] == 'present'
            for s in research['snapshots'].values()):
        raise ValueError('the camera unit and shading environment are not proven resident in every snapshot')
    if not all(s['slotIconAtlas']['samePage'] for s in research['snapshots'].values()):
        raise ValueError('the slot icon example is not on the atlas page of the token icon in every snapshot')
    if research['iconShader']['template'] != '0x3461FF0D' or research['iconShader']['passLayer']             != research['iconShader']['transparentLayer']:
        raise ValueError('the icon shader research no longer matches the icon material template')
    passes = research['renderConfig']['uiWorldViewport']['passes']
    if passes.index('generator noesis') < passes.index('layer transparent -> ui_target'):
        raise ValueError('the render config no longer draws world GUIs before the Noesis UI')
    pins = []
    for module, groups in research['pins'].items():
        for rows in groups.values():
            pins += [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': module} for pin in rows]
    unique = {}
    for pin in pins:
        unique.setdefault((pin['module'], pin['rva']), pin)
    layout = research['layout']
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDllSha256'], 'exeSha256': research['exeSha256']},
        # ui = [[game + ownerGlobal] + root]; the local record ui + records + [ui + localRecordIndex] * recordStride.
        'loadout': layout['loadoutUi'],
        # The native stratagem grid (the card list at ui + list): its rows and realized card widgets, and the GUI element
        # geometry the game's own hit test reads (element contains-point 0x144D320).
        'grid': layout['grid'],
        # [game + ownerGlobal] + states + (group * groupActions + action) * stride, byte 0: triggered this frame.
        'input': layout['inputActions'],
        # The engine's own font and its material (resident in every retained snapshot).
        'font': {'name': layout['font'], 'type': '0x9EFE0A916AAE7880', 'materialType': '0xEAC0B497876ADEDF'},
        # The development render-order probe (runtime/render_probe.lua): the script world's camera unit and shading
        # environment (resident in every retained snapshot), the overlay viewport, and the layer ranges.
        'render': layout['render'],
        # A slot widget's icon element: the image-element fields the game's image setter writes (slot-local icons).
        'slotIcon': layout['slotIcon'],
        # The native slot highlight (research slotFocus): the panel focus, the widget flags and the frame-flash byte
        # the panel update consumes.
        'slotFocus': layout['slotFocus'],
        # The render-side copy of a slot icon element's material (research slotTexture; read only).
        'slotTexture': layout['slotTexture'],
        # UI sounds through the exposed Wwise Lua API (research uiSound).
        'uiSound': layout['uiSound'],
        # The game's own selection close (research selectorClose): the close handler (ui), the bytes re-proved before
        # each call, and what it leaves at once.
        'selectorClose': layout['selectorClose'],
        # Slot icon overlays drawn in the Ui World (research slotOverlay, worldOrder).
        'slotOverlay': layout['slotOverlay'],
        # The icon shader's mask colours as the native loadout slot sets them (research iconShader): c0 from the colour
        # set table (game + table + set * stride), c1 and c2 at game + c1 / c2; c3 stays zero.
        'iconColours': layout['iconColours'],
        'pins': sorted(unique.values(), key=lambda pin: (pin['module'], pin['rva']))}


def outputs() -> dict[str, str]:
    return {'domains/stratagem_selector.lua': '-- Generated by scripts/generate_stratagem_selector.py; do not edit.\n'
        'return ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale stratagem selector domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
