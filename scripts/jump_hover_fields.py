"""LIFT-850 Jump Pack and LIFT-860 Hover Pack movement fields (JumppackComponentData) from
research/hoverpack-components-F5FEE03DCFDB.json. Used by scripts/generate_entity_authoring.py.

Every member below is read by the jump-pack flight code (game.dll 0x9B4790 launch / sustain / air control / hover,
0x9B4110 sustain gate, 0x9B5EC0 timers, 0xA63F20 take-off) through the record resolver 0x50D830, which returns the
backpack's own type record (no customization and no per-instance copy exists): a write takes effect on the next
frame, mid-flight included.

A field is offered only on the pack whose code path reads it:

* the Jump Pack (+153 = 0) runs the launch (+0, +24, +32), the sustain (+36..+56), air control (+60, +176) and the
  take-off hop (+208..+216, because +152 = 0);
* the Hover Pack (+153 = +154 = 1) sets the replicated hover-launch flag at activation, which skips the launch thrust
  (+0, +32; +24 only times an ability) and the earliest-sustain check (+48), and skips the take-off hop (+152 = 1). It
  runs the hover model (+156..+204), the sustain (+36, +40, +44, +52, +56) and air control (+60; +176 is also its
  hover speed).

The Dark Fluid vessel backpack (record 2) shares the component but is not a catalogued call-in backpack: excluded.
Behaviour switches (+144, +145, +152..+155, +64) and members whose meaning is not decoded (+4, +8, +20, +28) are not
offered.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/hoverpack-components-F5FEE03DCFDB.json'
PACKS = {'LIFT-850 Jump Pack': 'jump', 'LIFT-860 Hover Pack': 'hover'}

# field id, research path, record offset, packs that read it, (min, max), meaning
SPECS = (
    ('jump.launch_duration', '24', 24, ('jump',), (0.0, 5.0),
        'Seconds the launch thrust lasts after activation (the launch window).'),
    ('jump.launch_forward_ratio', '32', 32, ('jump',), (0.0, 1.0),
        'Share of the launch thrust along the travel direction; the rest pushes up (0 = straight up, 1 = flat).'),
    ('jump.sustain_thrust', '36', 36, ('jump', 'hover'), (0.0, 500.0),
        'Peak thrust of the sustain phase (m/s^2, tapering as 1 - t^2 over jump.sustain_duration).'),
    ('jump.sustain_duration', '40', 40, ('jump', 'hover'), (0.0, 10.0),
        'Seconds the sustain thrust lasts (0 disables the sustain phase).'),
    ('jump.sustain_forward_ratio', '44', 44, ('jump', 'hover'), (0.0, 1.0),
        'Share of the sustain thrust along the travel direction; the rest pushes up.'),
    ('jump.sustain_start_delay', '48', 48, ('jump',), (0.0, 10.0),
        'Seconds of launch before the sustain phase may start.'),
    ('jump.sustain_start_speed', '52', 52, ('jump', 'hover'), (0.0, 100.0),
        'Minimum speed (m/s) to start the sustain phase (a forward probe must also be clear).'),
    ('jump.sustain_cutoff_speed', '56', 56, ('jump', 'hover'), (0.0, 100.0),
        'The sustain phase ends, and the pack deactivates, below this speed (m/s).'),
    ('jump.air_control_acceleration', '60', 60, ('jump', 'hover'), (0.0, 200.0),
        'Mid-air steering: acceleration (m/s^2) along the movement input.'),
    ('jump.air_control_max_speed', '176[0]', 176, ('jump',), (0.0, 100.0),
        'Air control applies only below this horizontal speed (m/s; 0 = no limit).'),
    ('jump.takeoff_forward_speed', '208', 208, ('jump',), (0.0, 50.0),
        'Forward impulse (m/s) of the take-off hop when moving.'),
    ('jump.takeoff_speed', '212', 212, ('jump',), (0.0, 50.0),
        'Upward impulse (m/s) of the take-off hop: vertical speed = clamp(max(vz, 0) + value, 0.75 x value, 1.1 x '
        'value).'),
    ('jump.takeoff_speed_alternate_stance', '216', 216, ('jump',), (0.0, 50.0),
        'Upward take-off impulse (m/s) in the alternate stance (character stance state 4 or above).'),
    ('hover.max_horizontal_speed', '176[0]', 176, ('hover',), (0.0, 50.0),
        'Hover horizontal target speed (m/s); also the air-control speed limit of the Hover Pack.'),
    ('hover.max_vertical_speed', '176[1]', 180, ('hover',), (0.0, 50.0),
        'Hover climb target speed (m/s); no climb acceleration at it.'),
    ('hover.vertical_acceleration_low_speed', '160[1].0', 168, ('hover',), (0.0, 200.0),
        'Vertical acceleration (m/s^2) toward the climb target at low vertical speed (blended to the high-speed '
        'value over 0..hover.vertical_speed_range_end).'),
    ('hover.vertical_acceleration_high_speed', '160[1].4', 172, ('hover',), (0.0, 200.0),
        'Vertical acceleration (m/s^2) at the end of the vertical speed range.'),
    ('hover.vertical_speed_range_end', '184[1].4', 196, ('hover',), (0.01, 100.0),
        'Vertical speed (m/s) over which the vertical acceleration and the fuel rate blend from their low-speed to '
        'their high-speed value (must stay above the range start, 0).'),
    ('hover.fuel_rate_low_speed', '200[0]', 200, ('hover',), (-1.0, 10.0),
        'Extra hover fuel use at low vertical speed: each hovering second fills the recharge cooldown by 1 + this '
        'value seconds (capped at recharge.time; -1 = no fuel use).'),
    ('hover.fuel_rate_high_speed', '200[1]', 204, ('hover',), (-1.0, 10.0),
        'Extra hover fuel use at the end of the vertical speed range (see hover.fuel_rate_low_speed).'),
)
NOT_OFFERED = {
    'jump': [
        {'field': 'hover.*', 'reason': 'The Jump Pack does not run the hover model (+153 = 0).'},
        {'field': 'alternate launch window (+28)', 'reason': 'Used while a replicated mode toggle is set; which '
            'player action sets the toggle is not identified.'}],
    'hover': [
        {'field': 'jump.launch_duration / jump.launch_forward_ratio', 'reason': 'The Hover Pack sets the '
            'hover-launch flag at activation, which skips the launch thrust.'},
        {'field': 'jump.sustain_start_delay', 'reason': 'Skipped for the Hover Pack (hover-launch flag).'},
        {'field': 'jump.takeoff_*', 'reason': 'The Hover Pack skips the take-off hop (+152 = 1).'},
        {'field': 'hover horizontal acceleration (+160/+164)', 'reason': 'Blended over a zero-width speed range '
            '(+184/+188 = 0): a write to one end divides by zero in the flight code; a safe write needs both ends and '
            'the range together.'}],
    'both': [
        {'field': 'behaviour switches (+64, +144, +145, +152..+155)', 'reason': 'Flight-model switches; changing them '
            'swaps the pack model. Not offered.'},
        {'field': 'unknown members (+4, +8, +20)', 'reason': 'Readers found, meaning not decoded.'},
        {'field': 'presentation (abilities, indicator, visual sway +220..+276)', 'reason': 'Presentation only.'}],
}
DORMANT_LAUNCH = ('jump.vertical_launch_velocity writes the launch thrust (+0), which the Hover Pack never reads: '
    'its activation sets the hover-launch flag that skips the launch thrust (research/hoverpack-components-'
    'F5FEE03DCFDB.json). The write is kept for compatibility and has no effect on the Hover Pack.')
EFFECT = {'activeSource': 'LIVE_TYPE_RECORD', 'activeSourceProven': True, 'appliesWhen': 'next_frame',
    'instantiationOnly': False, 'gameplayEffectProven': False,
    'lifecycle': ("Read live every frame from the backpack's own JumppackComponent record (one owner): a write takes "
        'effect on the next frame, including a pack already worn and mid-flight.')}


def load():
    return json.loads(RESEARCH.read_text(encoding='utf-8'))


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def build(builder, name, target, jump_component, backing, research):
    """Field instance keys for one pack; backing(offset) -> the component backing of the pack's own record."""
    pack = PACKS.get(name)
    if not pack:
        return [], []
    record = next(item for item in research['records'] if item['label'] == name)
    assert record['record'] == jump_component['recordIndex'] and jump_component['uniqueOwner'], \
        name + ': JumppackComponent record identity changed'
    candidates = {item['path']: item for item in research['candidates']}
    keys = []
    for field_id, path, offset, packs, (low, high), meaning in SPECS:
        if pack not in packs:
            continue
        candidate = candidates[path]
        assert candidate['offset'] == offset and candidate['evidence']['codeRead'], field_id + ': research changed'
        differential = bool(candidate['evidence']['differential'])
        reason = meaning + ' Read live by the flight code; not yet shown in game.'
        if not differential:
            reason += (' The meaning is proven from the code, but no value differs between the packs (no '
                'differential), so the magnitude has no independent confirmation.')
        extra = {'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': reason,
            'min': low, 'max': high, 'effect': EFFECT,
            'evidence': {'tier': 'native_consumer_proven', 'referenceMod': None, 'proof': None, 'provenOn': [],
                'sharedTypedSchema': False, 'differential': differential,
                'codeReadCount': len(candidate['codeRefs']),   # instruction pins: research JSON only
                'research': 'research/hoverpack-components-F5FEE03DCFDB.json'}}
        value = f32(research['matrix'][path][name])
        keys.append(builder.add(name, target, field_id, value, backing(offset), extra=extra)['instanceKey'])
    blocked = NOT_OFFERED[pack] + NOT_OFFERED['both']
    return keys, blocked
