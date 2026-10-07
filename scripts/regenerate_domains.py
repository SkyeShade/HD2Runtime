"""Regenerate every generated runtime domain table and SDK metadata file, in the release build's order.

  py scripts/regenerate_domains.py          # write
  py scripts/regenerate_domains.py --check  # fail if anything is stale (what scripts/build_release.py runs)

Each domain generator passes its runtime table through the build-migration overlay hook
(scripts/migration/overlay.py): with no schemas/build_migration.json, or one for a different build than
schemas/current.lua, the output is exactly the reviewed tables.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ORDER = ('apply_projectile_residency', 'generate_live_evidence', 'generate_stratagem_calldown', 'generate_image_resources', 'generate_text_resources', 'generate_stratagem_slots', 'generate_support_delivery', 'generate_custom_payloads', 'generate_bombardment_payload', 'generate_slot_cooldown', 'generate_beacon_redirect', 'generate_pelican', 'generate_weapon_sounds', 'generate_sound_events', 'generate_wwise_plugin', 'generate_stratagem_selector', 'generate_stratagem_blocking', 'generate_peer_messaging', 'generate_matchmaking_safety', 'generate_player_equipment','generate_status_catalog', 'generate_weapon_composition', 'generate_support_weapon_sdk',
    'generate_support_weapon_authoring', 'generate_entity_authoring', 'generate_attachment_authoring',
    'generate_booster_authoring',
    'generate_stratagem_authoring', 'generate_weapon_authoring', 'generate_fire_mode_authoring',
    'generate_vehicle_weapon_authoring', 'generate_pod_payload_authoring', 'generate_throwable_authoring',
    'generate_package_residency', 'generate_explosion_catalogue', 'generate_weapon_movement', 'generate_enemy_authoring', 'generate_attack_outputs', 'generate_weapon_modes',
    'generate_weapon_presentation', 'generate_carrier_pod_items', 'generate_custom_stratagem_schema',
    'generate_legacy_acknowledgements', 'generate_projectile_homing', 'generate_enemy_spawn_weights', 'generate_teammate_hud', 'generate_sdk')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    import importlib
    from migration import overlay
    active = overlay.load()
    print('build-migration overlay:', 'applied (target ' + active['target']['buildId'] + ')' if active else
        'none for this build')
    for name in ORDER:
        importlib.import_module(name).generate(check=args.check)
        print(('checked ' if args.check else 'generated ') + name)


if __name__ == '__main__':
    main()
