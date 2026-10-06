"""Command line for the research scanner toolkit (research only; never writes game memory).

Examples (run from the repository root):
  py scripts/scan/cli.py components                          # every component table: records, sharing
  py scripts/scan/cli.py entity "turret_machinegun_gpmg"     # an entity's components and record indices
  py scripts/scan/cli.py family TurretComponentData --match "gatling_turret|rocket_turret|mortar_turret"
  py scripts/scan/cli.py family TurretComponentData --all --json build/scan/turret.json
  py scripts/scan/cli.py layout JumppackComponent            # flattened layout with hidden-name lengths
  py scripts/scan/cli.py golib WeaponChargeComponent         # Filediver Go leads aligned with the type library
  py scripts/scan/cli.py value 6.0 --kinds float             # every element equal to a published value
  py scripts/scan/cli.py xref-global 0x3326688               # functions that reference a global
  py scripts/scan/cli.py xref-fields 0x38ADD0 --offsets 20,412   # displacement accesses in a function
  py scripts/scan/cli.py strides <hexfile>                   # stride discovery in a raw dump
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from scan import compare, golib, report, strides, tables  # noqa: E402


def _int(text: str) -> int:
    return int(text, 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('components')
    entity = sub.add_parser('entity')
    entity.add_argument('pattern')
    family = sub.add_parser('family')
    family.add_argument('component')
    family.add_argument('--match', default=None, help='regular expression over resource paths')
    family.add_argument('--all', action='store_true', help='every entity owning the component')
    family.add_argument('--constant', action='store_true', help='include constant members')
    family.add_argument('--json', type=Path)
    layout = sub.add_parser('layout')
    layout.add_argument('type')
    go = sub.add_parser('golib')
    go.add_argument('type')
    value = sub.add_parser('value')
    value.add_argument('value', type=float)
    value.add_argument('--kinds', default='float')
    value.add_argument('--component', action='append')
    xg = sub.add_parser('xref-global')
    xg.add_argument('rva', type=_int)
    xg.add_argument('--module', default='game.dll')
    xf = sub.add_parser('xref-fields')
    xf.add_argument('rva', type=_int)
    xf.add_argument('--offsets', default=None)
    xf.add_argument('--module', default='game.dll')
    st = sub.add_parser('strides')
    st.add_argument('file', type=Path)
    args = parser.parse_args(argv)

    t = tables.pinned()
    if args.command == 'components':
        for component in t.components():
            print(json.dumps(component.describe()))
    elif args.command == 'entity':
        for resource in t.find(args.pattern):
            print(t.name(resource), json.dumps(t.entity(resource)))
    elif args.command == 'family':
        resources = t.with_component(args.component) if args.all or not args.match else [
            r for r in t.find(args.match) if t.component(args.component).record_of(r) is not None]
        fam = compare.Family(t, args.component, resources)
        description = fam.describe(include_constant=args.constant)
        if args.json:
            report.write(args.json, description)
            print('wrote', args.json)
        else:
            print(report.family_markdown(description))
            for cluster in description['clusters']:
                print(json.dumps(cluster))
    elif args.command == 'layout':
        for member in t.flatten(tables.dl_hash(args.type)):
            print(json.dumps(member.describe()))
    elif args.command == 'golib':
        print(json.dumps(golib.align_tree(t, golib.default_library(), args.type), indent=1))
    elif args.command == 'value':
        for hit in compare.find_value(t, args.value, tuple(args.kinds.split(',')), components=args.component):
            print(json.dumps(hit))
    elif args.command in ('xref-global', 'xref-fields'):
        from scan import xref
        image = xref.CodeImage.from_snapshot(args.module)
        if args.command == 'xref-global':
            for root, sites in sorted(image.global_accessors(args.rva).items()):
                print(f'{root:#x}', [f'{s:#x}' for s in sites])
        else:
            offsets = [int(x, 0) for x in args.offsets.split(',')] if args.offsets else None
            for hit in image.field_accesses(args.rva, offsets):
                print(f"{hit['rva']:#x}", hit['asm'], 'W' if hit['write'] else 'R', 'float' if hit['float'] else '')
    elif args.command == 'strides':
        raw = bytes.fromhex(args.file.read_text().strip()) if args.file.suffix == '.hex' else args.file.read_bytes()
        for item in strides.score_strides(raw):
            print(json.dumps(item))
    return 0


if __name__ == '__main__':
    sys.exit(main())
