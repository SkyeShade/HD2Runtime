"""Vehicle and mech component research domain (offline, read-only; nothing is written to the game).

Question: which native members drive vehicle and exosuit movement, suspension/chassis, turrets and durability, which
of them are proven well enough to become authoring fields, and which could support custom vehicles safely.

Method (every step reproducible from the pinned entity file, the pinned type library and the unpacked game.dll of a
retained snapshot; every native relationship is pinned as exact instruction text at an exact RVA):

1. Inventory. Every entity owning a vehicle-domain component table (VehicleComponentData, VehicleMotion,
   VehicleLocomotion, VehicleTracks, FakeTankVehicle, VehicleShuttle, VehicleCrash, Hover, ThrusterGroup) plus the
   enemy walkers/tanks/tripods that drive the same Locomotion/Rotation/Turret tables. Per entity: its components,
   record indices and owner counts (shared type data vs a unique record).
2. Layouts. Flattened record layouts with hidden-name lengths and a layout fingerprint per table (scan.tables).
3. Native record lookups. Every type-record lookup in game.dll loads the settings root (0x346BF98) and then the
   table pointer at root + 0xF12478 + 8 * componentIndex (componentIndex from EntitySettingsHashmap). The lookups are
   found by scanning every rip-relative reference to the root, classified as by-resource / by-pointer lookups and
   resolved (copy-or-type) accessors, i.e. functions that look the instance up in their manager's copy map and tail-jump
   into the type lookup when it has no private copy.
4. Member reads. From every call site of every lookup/accessor the returned record pointer is followed forward
   (register copies, lea offsets, callee arguments to depth 2). Each [record + displacement] operand is a native read
   of that member (an active source); float-domain instructions are marked.
5. Semantics. Reviewed instruction pins for the consumers that give members their meaning: the turret update and its
   creation, the rotation update and its creation, the wheeled/tracked driver-input smoothing, the wheel creation, the
   locomotion creation, and the velocity scaling routine.
6. Lifecycle. Which components have a per-instance copy pool (resolved accessor), which values are copied into the
   manager's instance block at creation, and which are re-read from the type record every update. Retained mission
   snapshots: copy-map occupancy of each manager (no vehicle instance is alive in any retained snapshot).
7. Published values. The scraped wiki vehicle pages: main health/armour/anatomy (cross-check of the existing durability
   fields) and the only movement numbers published (TD-220 Bastion top/reverse/1st-gear speed, neutral-steer speed,
   FRV fuel capacity), searched in every component record the vehicle owns.

Confidence labels follow scripts/scan/report.py CONFIDENCE_RULES. A proposed name is a reviewed semantic name whose
length equals the hidden member-name length; the length is a consistency check, never the source of the meaning.

Output: research/vehicle-mech-components-F5FEE03DCFDB.json. Requires capstone and numpy (research-only packages).
"""
from __future__ import annotations

from collections import defaultdict
import argparse
import json
import math
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from hd2_archive import resource_hash  # noqa: E402
from reference_format import dl_hash  # noqa: E402
from scan import report, tables  # noqa: E402

try:
    import numpy
    from capstone import x86
    from scan import xref
except ImportError as error:  # research dependency only
    raise SystemExit('research_vehicle_mech_components requires capstone and numpy: ' + str(error))

OUTPUT = ROOT / 'research/vehicle-mech-components-F5FEE03DCFDB.json'
ENTITY_RESEARCH = ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json'
VEHICLE_WEAPONS = ROOT / 'research/vehicle-weapons-F5FEE03DCFDB.json'
WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_vehicle_stratagems.json'
MISSION_SNAPSHOTS = ('F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap')
GAME_DLL_SHA256 = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'

SETTINGS_ROOT = 0x346BF98           # global: the loaded entity-settings object
TABLE_BASE = 0xF12478               # root + TABLE_BASE + 8 * componentIndex = component table pointer
DEG = math.pi / 180
INPUT_RATE_OFFSETS = (364, 368, 372, 376, 380)   # VehicleMotion members bound by the driver-input smoothing

# Approved authoring contracts (phase 2). Turret ids are the sentry ids on the same TurretComponent members; sentry
# live evidence does not transfer to vehicles, so every vehicle field needs allow_unverified_effect.
TURRET_RATE_LIFE = ('Copied into the turret instance (and its network creation field) when the mount is created: '
    'applies to vehicles called in after the write; a vehicle already in the world keeps its rate.')
TURRET_LIMIT_LIFE = ('Re-read from the type record on every turret update: applies at once to every live mount of '
    'that weapon.')
ROTATION_LIFE = ('Copied (in radians) into the Rotation instance when the exosuit spawns: applies to exosuits called '
    'in after the write; one already in the world keeps its values.')
STEERING_LIFE = ('Read from the VehicleMotion type record every frame (VehicleMotion has no per-instance copy): applies '
    'at once to every live vehicle of that type.')
TURRET_RATE_RANGE = ('The sentry turret-speed range: 1 degree per second up to two full turns per second (vanilla '
    'vehicle mounts use 20 to 130).')
FIELD_CONTRACTS = {
    'turret.yaw_speed': {'component': 'TurretComponentData', 'offset': 12, 'min': 1, 'max': 720,
        'units': 'degrees_per_second', 'displayName': 'Horizontal turn speed', 'rangeReason': TURRET_RATE_RANGE,
        'lifecycle': TURRET_RATE_LIFE, 'appliesWhen': 'entity_spawn'},
    'turret.pitch_speed': {'component': 'TurretComponentData', 'offset': 8, 'min': 1, 'max': 720,
        'units': 'degrees_per_second', 'displayName': 'Vertical turn speed', 'rangeReason': TURRET_RATE_RANGE,
        'lifecycle': TURRET_RATE_LIFE, 'appliesWhen': 'entity_spawn'},
    'turret.pitch_min': {'component': 'TurretComponentData', 'offset': 20, 'min': -90, 'max': 90,
        'units': 'degrees', 'displayName': 'Lowest aim angle', 'order': ['turret.pitch_min', 'turret.pitch_max'],
        'rangeReason': 'A vertical angle (straight down to straight up); it must stay below turret.pitch_max.',
        'lifecycle': TURRET_LIMIT_LIFE, 'appliesWhen': 'every_update'},
    'turret.pitch_max': {'component': 'TurretComponentData', 'offset': 24, 'min': -90, 'max': 90,
        'units': 'degrees', 'displayName': 'Highest aim angle', 'order': ['turret.pitch_min', 'turret.pitch_max'],
        'rangeReason': 'A vertical angle (straight down to straight up); it must stay above turret.pitch_min.',
        'lifecycle': TURRET_LIMIT_LIFE, 'appliesWhen': 'every_update'},
    'turret.yaw_min': {'component': 'TurretComponentData', 'offset': 28, 'min': -180, 'max': 180,
        'units': 'degrees', 'displayName': 'Left traverse limit', 'order': ['turret.yaw_min', 'turret.yaw_max'],
        'rangeReason': ('A horizontal angle; it must stay below turret.yaw_max. A range of 360 degrees (-180 to 180) '
            'turns freely.'), 'lifecycle': TURRET_LIMIT_LIFE, 'appliesWhen': 'every_update'},
    'turret.yaw_max': {'component': 'TurretComponentData', 'offset': 32, 'min': -180, 'max': 180,
        'units': 'degrees', 'displayName': 'Right traverse limit', 'order': ['turret.yaw_min', 'turret.yaw_max'],
        'rangeReason': ('A horizontal angle; it must stay above turret.yaw_min. A range of 360 degrees (-180 to 180) '
            'turns freely.'), 'lifecycle': TURRET_LIMIT_LIFE, 'appliesWhen': 'every_update'},
    'rotation.turn_speed': {'component': 'RotationComponentData', 'offset': 0, 'min': 1, 'max': 720,
        'units': 'degrees_per_second', 'displayName': 'Body turn speed',
        'rangeReason': 'Like turret turn speeds: 1 degree per second up to two turns per second (exosuits 65, Helldiver 200).',
        'lifecycle': ROTATION_LIFE, 'appliesWhen': 'entity_spawn'},
    'rotation.acceleration': {'component': 'RotationComponentData', 'offset': 4, 'min': 0, 'max': 10000,
        'units': 'degrees_per_second_squared', 'displayName': 'Body turn acceleration',
        'rangeReason': ('0 turns at the full rate at once (every exosuit); enemy walkers use 8 to 180 and the Helldiver '
            '2000. 10000 is effectively instant.'), 'lifecycle': ROTATION_LIFE, 'appliesWhen': 'entity_spawn'},
    'rotation.deceleration': {'component': 'RotationComponentData', 'offset': 8, 'min': 0, 'max': 10000,
        'units': 'degrees_per_second_squared', 'displayName': 'Body turn deceleration',
        'rangeReason': ('0 uses the acceleration (every exosuit); enemy walkers use 180 to 300 and the Helldiver 2000. '
            '10000 is effectively instant.'), 'lifecycle': ROTATION_LIFE, 'appliesWhen': 'entity_spawn'},
    'vehicle.steering_response_speed': {'component': 'VehicleMotionComponentData', 'offset': 364, 'min': 0.05,
        'max': 50, 'units': 'input_units_per_second', 'displayName': 'Steering response speed',
        'rangeReason': ('How fast the steering input (-1 to 1) follows the driver: 0.05 takes 20 s from centre to full '
            'lock, 50 is effectively instant (vanilla 0.5 to 10).'), 'lifecycle': STEERING_LIFE,
        'appliesWhen': 'every_frame'},
}
for _id, _contract in FIELD_CONTRACTS.items():
    _contract.update(storage='f32', apiConstant='hd2.fields.' + _id,
        target={'TurretComponentData': 'mounted weapon (hd2.vehicle(name):weapon(mount))',
            'RotationComponentData': 'exosuit (hd2.vehicle(name))',
            'VehicleMotionComponentData': 'wheeled or tracked vehicle (hd2.vehicle(name))'}[_contract['component']],
        constraints='FP32 in [%g, %g]%s' % (_contract['min'], _contract['max'],
            ', min < max' if _contract.get('order') else ''),
        writeSemantics=_contract['lifecycle'], acknowledgement='allow_unverified_effect')

# Vehicle-domain tables (records the research reads). Order is the report order.
COMPONENTS = ('VehicleComponentData', 'VehicleMotionComponentData', 'VehicleLocomotionComponentData',
    'VehicleTracksComponentData', 'FakeTankVehicleComponentData', 'HoverComponentData', 'ThrusterGroupComponentData',
    'LocomotionComponentData', 'MotionComponentData', 'RotationComponentData', 'TurretComponentData',
    'TargetAimConstraintComponentData', 'SeatCollectionComponentData', 'VehicleCollisionInfoComponentData',
    'VehicleCollisionDamageComponentData', 'VehicleCrashComponentData', 'VehicleElectricsComponentData',
    'NetworkPhysicsComponentData', 'GroundCheckComponentData', 'BuoyancyComponentData', 'VehicleShuttleComponentData',
    'StanceComponentData', 'MountComponentData', 'HealthComponentData')
# Owners of these tables are vehicle-domain entities by construction.
DEFINING = ('VehicleComponentData', 'VehicleMotionComponentData', 'VehicleLocomotionComponentData',
    'VehicleTracksComponentData', 'FakeTankVehicleComponentData', 'VehicleShuttleComponentData',
    'VehicleCrashComponentData', 'HoverComponentData', 'ThrusterGroupComponentData')
# Differential controls driving the same Locomotion/Rotation/Turret tables without a vehicle table.
CONTROL_PATHS = r'fac_cyborgs/vehicles/|fac_illuminate/vehicles/|cha_tripod/cha_tripod|cha_strider/cha_strider$'
# Unnamed entities identified by their structure (mount slots and shared records), see unnamedLeads.
UNNAMED = {
    0x0801B6B3C5D12EBC: ('oil rig variant (unnamed)', 'civilian_vehicle',
        'VehicleMotion/WheelInfo values equal the GATER oil rig; its only mount slot holds the GATER turret '
        '(0x9872EEB31A5F88FD, attach_turret)'),
    0x9076EEED17FCEE35: ('scout walker rocket variant (unnamed)', 'enemy_walker',
        'VehicleLocomotion equal to cyborg_walker_scout; mount slots gun_pitch / turret / rockets_left / rockets_right'),
}
# Published (wiki prose) movement numbers. They are tested against every record the vehicle owns.
PUBLISHED_MOVEMENT = {
    'TD-220 Bastion MK XVI': {'resource': 0x16474112801385B6, 'values': [
        ('top speed (drive gear)', 32.0, 'km/h'), ('reverse speed', 18.0, 'km/h'), ('1st gear top speed', 20.0, 'km/h'),
        ('neutral-steer hull rotation, drive gear', 4.0, 'km/h'), ('neutral-steer hull rotation, 2nd gear', 6.0, 'km/h')]},
    'M-102 Gunner FRV': {'resource': 0xCC21C7FFD3EBEFB9, 'values': [('fuel capacity', 60.0, 'L')]},
}

# Reviewed instruction pins: (rva, exact instruction text, role). Rip-relative operands are additionally checked
# against the expected target in RIP_TARGETS. Any mismatch aborts the run.
PINS = {
    'settingsRoot': [
        (0x510225, 'mov rax, qword ptr [rip + 0x2f5bd6c]', 'Mount type lookup: the settings root (0x346BF98)'),
        (0x51022F, 'mov r10, qword ptr [rax + 0xf12d50]', 'Mount table = root + 0xF12478 + 8 * 283'),
        (0x5102A1, 'imul rax, rcx, 0x78', 'record stride 120 (MountComponent)'),
        (0x5102A5, 'add rax, 0x1440', 'records follow the 324-row index'),
    ],
    'vehicleComponent': [
        (0x4FA39F, 'mov r10, qword ptr [rax + 0xf12750]', 'VehicleComponent table (component index 91)'),
        (0x4FA40C, 'imul rax, rcx, 0xe78', 'record stride 3704'),
        (0x4FA413, 'add rax, 0x280', 'records follow the 40-row index'),
        (0x4FA78E, 'add rax, 0x123e0', 'default VehicleComponent record = record 20 (the unowned one)'),
        (0x4FA7C2, 'mov r11, qword ptr [rip + 0x2e2be9f]', 'resolved accessor: the VehicleComponent manager (0x3326668)'),
        (0x4FA852, 'imul rax, rax, 0xe78', 'private copy stride'),
        (0x4FA859, 'add rax, qword ptr [r11 + 0xc0]', 'private copy pool (manager +0xC0)'),
        (0x4FA86C, 'jmp 0x4fa390', 'no private copy: the shared type record'),
        (0x703B70, 'lea rdx, [rip + 0x1b45969]', '"VehicleComponent" in the manager grow function'),
        (0x703C27, 'imul rdx, rax, 0xe78', 'the grow function sizes the copy pool in records'),
    ],
    'wheelCreation': [
        (0x6FD8CC, 'call 0x4fa7a0', 'vehicle creation: the resolved VehicleComponent'),
        (0x6FD950, 'mov edx, dword ptr [r12 - 8]', 'WheelInfo +24 (rotation node name)'),
        (0x6FD955, 'mov ebx, dword ptr [r12]', 'WheelInfo +32'),
        (0x6FD959, 'mov r14d, dword ptr [r12 - 0x10]', 'WheelInfo +16 (translation node name)'),
        (0x6FD95E, 'mov edi, dword ptr [r12 - 4]', 'WheelInfo +28 (suspension / gear-compression variable)'),
        (0x6FD963, 'mov esi, dword ptr [r12 - 0xc]', 'WheelInfo +20 (steering node name)'),
        (0x6FD9A7, 'movzx eax, byte ptr [r12 - 0x1c]', 'WheelInfo +4 (flag)'),
        (0x6FD9B5, 'movss xmm0, dword ptr [r12 - 0x20]', 'WheelInfo +0 ...'),
        (0x6FD9E0, 'mov dword ptr [rsp + 0x38], 0x3f800000', '... 0 means 1.0'),
        (0x6FD9F7, 'mov rax, qword ptr [rcx + 0x6d8]', 'node names resolved on the vehicle unit (engine unit API +0x6D8)'),
        (0x6FDAAF, 'movss xmm4, dword ptr [r12 + 0x18]', 'WheelInfo +56'),
        (0x6FDAC3, 'add r12, 0x40', 'next WheelInfo (stride 64)'),
    ],
    'vehicleMotion': [
        (0x507AB1, 'mov r11, qword ptr [rax + 0xf12b80]', 'VehicleMotion table (component index 225)'),
        (0x507A98, 'mov rcx, qword ptr [rcx]', 'by-pointer lookup: the instance\'s resource'),
        (0x507B34, 'imul rax, rcx, 0x1c8', 'record stride 456; no resolved accessor and no copy pool exists'),
        (0x71AA95, 'lea rdx, [rip + 0x1b2ec04]', '"VehicleMotionComponent" in the manager grow function'),
        (0x53DFC9, 'imul rcx, rbx, 0x670', 'per-instance state 0x670 bytes (the type record is not copied)'),
    ],
    'driverInputSmoothing': [
        (0x71542D, 'call 0x507a90', 'per frame, per vehicle: the VehicleMotion type record'),
        (0x715449, 'imul r13, rsi, 0x670', 'the instance state block'),
        (0x7153C7, 'movss xmm12, dword ptr [rip + 0x1cb2420]', 'constant 100/s: rising channels 1 and 2'),
        (0x715527, 'movzx edi, byte ptr [rax + 0xe1ad5]', 'global input-mode flag selects the channel 1/2 rates'),
        (0x715902, 'mulss xmm0, dword ptr [r12 + 0x16c]', 'channel 0 step = dt * VehicleMotion +364'),
        (0x71591A, 'minss xmm1, xmm2', 'step clamped to the remaining difference (both directions)'),
        (0x715922, 'movss dword ptr [rsi], xmm1', 'channel 0 (signed steering input) written'),
        (0x715784, 'movss xmm0, dword ptr [rip + 0x1cb2880]', 'assist branch forces channel 0 to -1 ...'),
        (0x71578C, 'movss dword ptr [rsi], xmm0', '... (full lock): channel 0 is the signed steering input'),
        (0x715936, 'comiss xmm4, xmm1', 'channel 1 target vs current'),
        (0x71593B, 'movaps xmm0, xmm12', 'rising: 100/s'),
        (0x715946, 'movss xmm0, dword ptr [r12 + 0x174]', 'falling, flag clear: +372'),
        (0x715952, 'movss xmm0, dword ptr [r12 + 0x170]', 'falling, flag set: +368'),
        (0x71598E, 'movss dword ptr [rsi + 4], xmm1', 'channel 1 written'),
        (0x7159B3, 'movss xmm0, dword ptr [r12 + 0x17c]', 'channel 2 falling, flag clear: +380'),
        (0x7159BF, 'movss xmm0, dword ptr [r12 + 0x178]', 'channel 2 falling, flag set: +376'),
        (0x7159FF, 'movss dword ptr [rsi + 8], xmm1', 'channel 2 written'),
        (0x715808, 'mov dword ptr [rsi + 8], 0x3f800000', 'assist branch forces channel 2 to 1.0'),
    ],
    'velocityScaling': [
        (0x71955F, 'call 0x507a90', 'the VehicleMotion type record'),
        (0x7195A8, 'call qword ptr [rax + 0x80]', 'engine actor API +0x80 (vector A)'),
        (0x7195CA, 'mulss xmm0, dword ptr [rdi + 0x158]', 'components scaled by VehicleMotion +344'),
        (0x719609, 'mulss xmm1, dword ptr [rdi + 0x15c]', 'last component scaled by VehicleMotion +348'),
        (0x71964C, 'call qword ptr [rax + 0x88]', 'written back through the actor API +0x88'),
    ],
    'turretLookup': [
        (0x50B43F, 'mov r10, qword ptr [rax + 0xf12c38]', 'Turret table (component index 248)'),
        (0x50B952, 'imul rax, rax, 0x4c', 'resolved accessor 0x50B8B0: private copy stride 76'),
        (0x50B956, 'add rax, qword ptr [r11 + 0xa8]', 'private copy pool (Turret manager 0x3326D70 +0xA8)'),
        (0x50B969, 'jmp 0x50b430', 'no private copy: the shared type record'),
    ],
    'turretCreation': [
        (0x6E07C9, 'movss dword ptr [rax + rbx*8 + 4], xmm0', 'instance +4 = turn_speed_modifier (from 0x6DE820)'),
        (0x6E07E1, 'mov dword ptr [r15 + rax*8], 0x9611c029', 'creation field turn_speed_modifier'),
        (0x6E07FD, 'call 0x50b8b0', 'the resolved TurretComponent'),
        (0x6E0806, 'mov eax, dword ptr [rax + 0xc]', 'TurretComponent +12 ...'),
        (0x6E0809, 'mov dword ptr [rcx + rbx*8 + 8], eax', '... copied to instance +8 at creation'),
        (0x6E081F, 'mov dword ptr [r15 + rax*8], 0xcc0b45e5', '... and sent as creation field 0xCC0B45E5'),
        (0x6E0844, 'mov eax, dword ptr [rax + 8]', 'TurretComponent +8 ...'),
        (0x6E0847, 'mov dword ptr [rcx + rbx*8 + 0xc], eax', '... copied to instance +12 at creation'),
        (0x6E085A, 'mov dword ptr [r15 + rax*8], 0x9d5d6cc7', '... and sent as creation field 0x9D5D6CC7'),
    ],
    'turretUpdate': [
        (0x6DF46E, 'call 0x50b8b0', 'every update: the resolved TurretComponent'),
        (0x6DF49B, 'movss xmm8, dword ptr [r15 + 8]', 'horizontal rate: the instance copy of +12'),
        (0x6DF4AD, 'movss xmm9, dword ptr [rax + 0x20]', 'TurretComponent +32 (horizontal maximum)'),
        (0x6DF4B6, 'movss xmm6, dword ptr [rip + 0x1ce71a2]', 'pi/180: degrees to radians'),
        (0x6DF4BE, 'movss xmm7, dword ptr [rax + 0x1c]', 'TurretComponent +28 (horizontal minimum)'),
        (0x6DF4E5, 'comiss xmm0, dword ptr [rip + 0x1ce7ffc]', 'max - min >= 6.28219 rad: unrestricted (wrapping)'),
        (0x6DF5AA, 'mulss xmm8, dword ptr [r15 + 4]', 'rate * turn_speed_modifier ...'),
        (0x6DF5B0, 'mulss xmm8, xmm6', '... * pi/180'),
        (0x6DF5F5, 'comiss xmm7, xmm1', 'target clamped to the minimum ...'),
        (0x6DF603, 'minss xmm0, xmm1', '... and to the maximum'),
        (0x6DFBCA, 'movss xmm7, dword ptr [r15 + 0xc]', 'vertical rate: the instance copy of +8'),
        (0x6DFC39, 'mulss xmm7, dword ptr [r15 + 4]', 'rate * turn_speed_modifier'),
        (0x6DFC7F, 'movss xmm6, dword ptr [rsi + 0x14]', 'TurretComponent +20 (vertical minimum) ...'),
        (0x6DFC91, 'movss xmm6, dword ptr [rsi + 0x18]', 'TurretComponent +24 (vertical maximum)'),
        (0x6DFC9F, 'movss dword ptr [rdi + 0x64], xmm6', 'clamped vertical angle stored'),
    ],
    'rotationLookup': [
        (0x513742, 'imul rax, rax, 0x138', 'resolved accessor 0x513690: private copy stride 312'),
        (0x513749, 'add rax, qword ptr [r11 + 0xb8]', 'private copy pool (Rotation manager 0x33264A0 +0xB8)'),
    ],
    'rotationCreation': [
        (0x61D6D1, 'imul r14, r12, 0x298', 'the Rotation instance block (0x298 bytes)'),
        (0x61D6DC, 'call 0x513690', 'the resolved RotationComponent'),
        (0x61D745, 'movss xmm2, dword ptr [rip + 0x1da8f13]', 'pi/180'),
        (0x61D758, 'movss xmm0, dword ptr [r15]', 'RotationComponent +0 ...'),
        (0x61D761, 'movss dword ptr [r14 + 0x30], xmm0', '... in radians to instance +0x30'),
        (0x61D767, 'movss xmm0, dword ptr [r15 + 4]', 'RotationComponent +4 ...'),
        (0x61D771, 'movss dword ptr [r14 + 0x40], xmm0', '... in radians to instance +0x40'),
        (0x61D777, 'movss xmm1, dword ptr [r15 + 8]', 'RotationComponent +8 ...'),
        (0x61D785, 'movss dword ptr [r14 + 0x44], xmm1', '... in radians to instance +0x44'),
    ],
    'rotationUpdate': [
        (0x61F838, 'imul rdx, r8, 0x298', 'the Rotation instance block'),
        (0x61F87D, 'movss xmm7, dword ptr [rdx + 0x40]', 'angular acceleration (instance copy of +4)'),
        (0x61F885, 'jbe 0x61f9e7', '<= 0: rotate at the full rate at once'),
        (0x61F88B, 'movss xmm3, dword ptr [rdx + 0x44]', 'angular deceleration (instance copy of +8)'),
        (0x61F895, 'movaps xmm3, xmm7', '<= 0: the acceleration is used'),
        (0x61F8E3, 'divss xmm0, xmm3', 'stopping time = angular velocity / deceleration'),
        (0x61F913, 'mulss xmm2, dword ptr [rdx + 0x30]', 'target angular velocity = sign(angle) * turn rate'),
        (0x61F94B, 'mulss xmm7, xmm10', 'acceleration * dt'),
        (0x61F97C, 'movss dword ptr [rdx + 0x34], xmm2', 'angular velocity'),
        (0x61FA0C, 'mulss xmm2, dword ptr [rdx + 0x30]', 'instant branch: the full turn rate'),
    ],
    'locomotionCreation': [
        (0x9C6DA7, 'mov eax, dword ptr [rbp + 0x1170]', 'LocomotionComponent +4464 ...'),
        (0x9C6DB9, 'mov dword ptr [rdx + rcx + 0x1c], eax', '... copied into the instance array at creation'),
        (0x9C6DBD, 'mov eax, dword ptr [rbp + 0x1174]', 'LocomotionComponent +4468 ...'),
        (0x9C6DC7, 'mov dword ptr [rdx + rcx + 0x20], eax', '... copied into the instance array at creation'),
        (0x9C7F7B, 'movss xmm0, dword ptr [r12 + 0x1dc]', 'the active LocomotionSet +476 ...'),
        (0x9C7F85, 'movss xmm1, dword ptr [rip + 0x1a0010b]', '... -2 means: use the component default'),
        (0x9C7F94, 'movss xmm0, dword ptr [r15 + 0x1c]', 'component default (+4464)'),
        (0x9C7FB3, 'movss xmm0, dword ptr [r15 + 0x20]', 'component default (+4468)'),
    ],
}
RIP_TARGETS = {0x510225: SETTINGS_ROOT, 0x4FA7C2: 0x3326668, 0x703B70: 0x22494E0, 0x71AA95: 0x22496A0,
    0x7153C7: 0x23C77F0, 0x6DF4B6: 0x23C6660, 0x6DF4E5: 0x23C74E8, 0x61D745: 0x23C6660, 0x9C7F85: 0x23C8098,
    0x715784: 0x23C800C}
RIP_FLOATS = {0x7153C7: 100.0, 0x6DF4B6: DEG, 0x6DF4E5: 6.28219, 0x61D745: DEG, 0x9C7F85: -2.0, 0x715784: -1.0}
MANAGERS = {   # component -> (manager global, resolved accessor or None, copy pool offset, copy-map table offset)
    'VehicleComponentData': (0x3326668, 0x4FA7A0, 0xC0, 0x80),
    'VehicleMotionComponentData': (0x3326458, None, None, None),
    'TurretComponentData': (0x3326D70, 0x50B8B0, 0xA8, 0x68),
    'RotationComponentData': (0x33264A0, 0x513690, 0xB8, 0x78),
    'LocomotionComponentData': (0x3326CF8, 0x513C60, 0xA8, 0x68),
    'ProjectileWeaponComponentData': (0x33266D8, 0x515100, 0xD0, 0x90),   # control: the known Pelican result
}
MANAGER_NAMES = {'VehicleComponentData': 'VehicleComponent', 'VehicleMotionComponentData': 'VehicleMotionComponent',
    'VehicleLocomotionComponentData': 'VehicleLocomotionComponent', 'VehicleTracksComponentData': 'VehicleTracksComponent',
    'FakeTankVehicleComponentData': 'FakeTankVehicleComponent', 'TurretComponentData': 'TurretComponent',
    'SeatCollectionComponentData': 'SeatCollectionComponent', 'VehicleCrashComponentData': 'VehicleCrashComponent',
    'VehicleCollisionDamageComponentData': 'VehicleCollisionDamageComponent',
    'VehicleElectricsComponentData': 'VehicleElectricsComponent', 'BuoyancyComponentData': 'BuoyancyComponent',
    'LocomotionComponentData': 'LocomotionComponent', 'RotationComponentData': 'RotationComponent',
    'MotionComponentData': 'MotionComponent'}
# Network creation-field names: the engine's 32-bit IdString (upper half of Murmur64A). Candidates hashed here.
NETWORK_FIELDS = {0x9611C029: 'turret instance +4 (from 0x6DE820)', 0xCC0B45E5: 'TurretComponent +12 copy',
    0x9D5D6CC7: 'TurretComponent +8 copy', 0xE0A79052: 'turret instance flag byte'}
NETWORK_NAME_CANDIDATES = ('turn_speed_modifier', 'horizontal_turn_speed', 'vertical_turn_speed', 'yaw_speed',
    'pitch_speed', 'traverse_speed', 'elevation_speed', 'turn_speed', 'yaw_turn_speed', 'pitch_turn_speed', 'enabled',
    'active', 'turret_yaw_speed', 'turret_pitch_speed', 'rotation_speed', 'aim_speed')


# ---------------------------------------------------------------------------------------------------------------
# native helpers (game.dll)
# ---------------------------------------------------------------------------------------------------------------
class Native:
    def __init__(self, image: 'xref.CodeImage'):
        self.img = image
        self.data = image.data
        self.lo, self.hi = image.text
        self._root_sites = None
        self._calls = {}

    def decode(self, rva):
        return next(self.img.md.disasm(self.data[rva:rva + 16], rva, 1), None)

    def rip_refs(self, target):
        """Instructions whose rip-relative operand resolves to target (leaf functions included: no .pdata needed)."""
        out = []
        for phase, keys in enumerate(self.img._phase_keys()):
            for hit in numpy.nonzero(keys == target)[0]:
                disp = self.lo + phase + int(hit) * 4
                for back in (3, 2, 4):
                    ins = self.decode(disp - back)
                    if ins and ins.address + ins.size == disp + 4 and self.img.rip_target(ins) == target:
                        out.append(ins)
                        break
        return out

    def root_sites(self):
        if self._root_sites is None:
            self._root_sites = self.rip_refs(SETTINGS_ROOT)
        return self._root_sites

    def branches_to(self, target):
        """(site, 'call'|'jmp') for every rel32 call/jump to target."""
        if target not in self._calls:
            out = []
            for phase, keys in enumerate(self.img._phase_keys()):
                for hit in numpy.nonzero(keys == target)[0]:
                    site = self.lo + phase + int(hit) * 4 - 1
                    if self.data[site] in (0xE8, 0xE9):
                        out.append((site, 'call' if self.data[site] == 0xE8 else 'jmp'))
            self._calls[target] = sorted(out)
        return self._calls[target]

    def function_of(self, rva):
        root = self.img.root(rva)
        if root:
            return root
        at = rva
        while at > self.lo and self.data[at - 1] != 0xCC:
            at -= 1
        return at

    def leaf_start(self, site):
        """Start of the leaf lookup containing a root load: the nearest 'test rcx, rcx' that decodes straight to
        the load without an unconditional jump in between."""
        for back in range(64, 0, -1):
            start = site - back
            if self.data[start:start + 3] != b'\x48\x85\xc9':
                continue
            seq, ok = [], False
            for ins in self.img.md.disasm(self.data[start:site + 8], start):
                if ins.address == site:
                    ok = True
                    break
                if ins.address > site:
                    break
                seq.append(ins)
            if ok and not any(i.mnemonic in ('jmp', 'int3') for i in seq):
                return start, seq
        return None, []

    def lookups(self, table_offset):
        """Type-record lookups of one table and the resolved accessors that fall back to them."""
        out = {'tableLoads': [], 'byResource': [], 'byPointer': [], 'resolved': []}
        for ins in self.root_sites():
            seq = list(self.img.md.disasm(self.data[ins.address:ins.address + 64], ins.address))[:8]
            reg = seq[0].operands[0].reg
            load = next((i for i in seq[1:] if i.mnemonic == 'mov' and any(op.type == x86.X86_OP_MEM and
                op.mem.base == reg and op.mem.disp == table_offset for op in i.operands)), None)
            if load is None:
                continue
            out['tableLoads'].append(load.address)
            start, body = self.leaf_start(ins.address)
            if start is None:
                continue
            text = ' ; '.join(i.mnemonic + ' ' + i.op_str for i in body)
            out['byPointer' if 'mov rcx, qword ptr [rcx]' in text else 'byResource'].append(start)
        for lookup in out['byResource']:
            for site, kind in self.branches_to(lookup):
                if kind == 'jmp' and self.data[site - 3:site] != b'\x48\x8b\x09':
                    start = next((site - back for back in range(0, 0x140)
                        if self.data[site - back:site - back + 4] == b'\x48\x83\xec\x28'), None)
                    if start is not None:
                        out['resolved'].append({'accessor': start, 'tailJump': site})
        return out

    @staticmethod
    def reg64(ins, reg):
        name = ins.reg_name(reg)
        legacy = {'eax': 'rax', 'ecx': 'rcx', 'edx': 'rdx', 'ebx': 'rbx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp',
            'esp': 'rsp'}
        name = legacy.get(name, name)
        if name and name[0] == 'r' and name[-1] in 'dwb' and name[1:-1].isdigit():
            name = name[:-1]
        return name

    def track(self, start, held, depth=2, budget=400, seen=None):
        """Forward data flow of record pointers from start: {reg: record offset}. Returns member accesses."""
        seen = set() if seen is None else seen
        key = (start, tuple(sorted(held.items())))
        if key in seen:
            return []
        seen.add(key)
        chunk = self.img.chunk(start)
        end = chunk[1] if chunk else start + 0x1200
        held, out = dict(held), []
        for ins in self.img.md.disasm(self.data[start:min(end, start + 0x2000)], start):
            budget -= 1
            if budget < 0 or not held:
                break
            mnemonic, ops = ins.mnemonic, ins.operands
            for position, op in enumerate(ops):
                if op.type == x86.X86_OP_MEM and op.mem.base and mnemonic != 'lea':
                    base = self.reg64(ins, op.mem.base)
                    if base in held:
                        out.append({'rva': ins.address, 'asm': mnemonic + ' ' + ins.op_str,
                            'offset': held[base] + op.mem.disp, 'size': op.size, 'indexed': bool(op.mem.index),
                            'write': position == 0 and mnemonic.startswith(('mov', 'vmov', 'add', 'sub', 'and', 'or',
                                'xor', 'inc', 'dec')) and mnemonic not in ('movzx', 'movsx', 'movsxd'),
                            'float': mnemonic.startswith(xref.FLOAT_MNEMONICS)})
            if mnemonic == 'mov' and len(ops) == 2 and ops[0].type == x86.X86_OP_REG:
                dest = self.reg64(ins, ops[0].reg)
                if ops[1].type == x86.X86_OP_REG and self.reg64(ins, ops[1].reg) in held:
                    held[dest] = held[self.reg64(ins, ops[1].reg)]
                else:
                    held.pop(dest, None)
            elif mnemonic == 'lea' and ops[0].type == x86.X86_OP_REG:
                dest, mem = self.reg64(ins, ops[0].reg), ops[1].mem
                base = self.reg64(ins, mem.base) if mem.base else None
                if base in held and not mem.index:
                    held[dest] = held[base] + mem.disp
                else:
                    held.pop(dest, None)
            elif mnemonic == 'add' and len(ops) == 2 and ops[0].type == x86.X86_OP_REG and ops[1].type == x86.X86_OP_IMM:
                dest = self.reg64(ins, ops[0].reg)
                if dest in held:
                    held[dest] += ops[1].imm
            elif mnemonic == 'call':
                if depth > 0 and ops and ops[0].type == x86.X86_OP_IMM:
                    args = {r: held[r] for r in ('rcx', 'rdx', 'r8', 'r9') if r in held}
                    if args:
                        for item in self.track(ops[0].imm, args, depth - 1, 300, seen):
                            item.setdefault('via', []).insert(0, ops[0].imm)
                            out.append(item)
                for reg in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                    held.pop(reg, None)
            elif mnemonic in ('ret', 'int3'):
                break
            elif mnemonic == 'jmp':
                if ops and ops[0].type == x86.X86_OP_IMM and depth > 0 and not (chunk and chunk[0] <= ops[0].imm < chunk[1]):
                    args = {r: held[r] for r in ('rcx', 'rdx', 'r8', 'r9') if r in held}
                    if args:
                        for item in self.track(ops[0].imm, args, depth - 1, 300, seen):
                            item.setdefault('via', []).insert(0, ops[0].imm)
                            out.append(item)
            elif ops and ops[0].type == x86.X86_OP_REG and mnemonic not in ('cmp', 'test', 'push', 'bt'):
                held.pop(self.reg64(ins, ops[0].reg), None)
        return out

    def pin(self, rva, expected, role):
        entry = self.img.pin(rva, role, expected)
        if rva in RIP_TARGETS and entry.get('ripTarget') != RIP_TARGETS[rva]:
            raise ValueError('pin %x: rip target %x, expected %x' % (rva, entry.get('ripTarget', 0), RIP_TARGETS[rva]))
        if rva in RIP_FLOATS:
            value = self.img.f32(entry['ripTarget'])
            if abs(value - RIP_FLOATS[rva]) > 1e-4:
                raise ValueError('pin %x: constant %r, expected %r' % (rva, value, RIP_FLOATS[rva]))
            entry['constant'] = round(value, 6)
        return entry


# ---------------------------------------------------------------------------------------------------------------
# entity-file helpers
# ---------------------------------------------------------------------------------------------------------------
def hexid(value):
    return f'0x{value:016X}'


def jsonable(value):
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else str(value)
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


def thin_value(t, value):
    """Integer member: its thin-hash name when the dictionary knows it (a lead), else the number."""
    if isinstance(value, int) and value > 0xFFFFFF and value <= 0xFFFFFFFF:
        name = t.thin.get(value)
        return name if name else f'0x{value:08X}'
    return jsonable(value)


def component_index(t, name):
    t.entity_rows()
    for index, type_hash in t._index_type.items():
        if type_hash == dl_hash(name):
            return index
    raise KeyError(name)


def member_of(t, component, offset):
    for member in t.component(component).members():
        if member.offset <= offset < member.offset + member.size:
            return member
    return None


def element_value(t, component, record, offset):
    member = member_of(t, component, offset)
    value = tables.decode(member, t.component(component).raw(record))
    if isinstance(value, list):
        width = member.element_size() if member.atom != 'VECTOR' else 4
        value = value[(offset - member.offset) // width]
    return member, value


def catalog_names():
    names = {}
    if ENTITY_RESEARCH.is_file():
        for item in json.loads(ENTITY_RESEARCH.read_text(encoding='utf-8'))['vehicles']:
            names[int(item['resource'], 16)] = item['name']
    return names


def classify(path, components):
    path = path or ''
    if set(components) <= {'ThrusterGroupComponentData'}:
        return 'thruster_projectile'
    if '/turrets/' in path:
        return 'enemy_turret'
    if 'combat_walker' in path:
        return 'exosuit'
    if '/fac_helldivers/vehicles/shuttle' in path:
        return 'shuttle'
    if '/fac_helldivers/vehicles/' in path:
        return 'player_vehicle'
    if '/fac_super_earth/vehicles/' in path:
        return 'civilian_vehicle'
    if 'VehicleShuttleComponentData' in components or 'ThrusterGroupComponentData' in components:
        return 'dropship_or_aircraft'
    if '/fac_cyborgs/vehicles/' in path or '/fac_illuminate/vehicles/' in path:
        return 'enemy_vehicle'
    return 'enemy_character'


def drive_model(components, wheel_nodes):
    if 'VehicleTracksComponentData' in components:
        return 'tracked'
    if 'VehicleMotionComponentData' in components and 'ThrusterGroupComponentData' in components:
        return 'flying_vehicle'
    if 'VehicleMotionComponentData' in components:
        return 'wheeled' if wheel_nodes else 'vehicle_motion'
    if 'VehicleLocomotionComponentData' in components:
        return 'legged_pilot'
    if 'FakeTankVehicleComponentData' in components:
        return 'fake_tank_locomotion'
    if 'HoverComponentData' in components or 'ThrusterGroupComponentData' in components:
        return 'hover_or_thruster'
    if 'LocomotionComponentData' in components:
        return 'character_locomotion'
    return 'none'


def inventory(t, names):
    resources = set()
    for component in DEFINING:
        resources |= set(t.with_component(component))
    resources |= {r for r in t.find(CONTROL_PATHS) if 'HealthComponentData' in t.entity(r)}
    vc = t.component('VehicleComponentData')
    vehicles = []
    for resource in sorted(resources, key=lambda r: (t.name(r) or '~', r)):
        entity = t.entity(resource)
        components = {name: entity[name] for name in COMPONENTS if name in entity}
        path = t.name(resource)
        wheel_nodes = 0
        if 'VehicleComponentData' in components:
            raw = vc.raw(components['VehicleComponentData'])
            wheel_nodes = sum(1 for i in range(32) if struct.unpack_from('<I', raw, 8 + i * 64 + 16)[0])
        label = names.get(resource) or (UNNAMED[resource][0] if resource in UNNAMED else t.label(resource))
        kind = UNNAMED[resource][1] if resource in UNNAMED else classify(path, components)
        records = {}
        for name, record in components.items():
            owners = t.component(name).owners(record)
            records[name] = {'record': record, 'owners': len(owners), 'shared': len(owners) > 1,
                'coOwners': [t.label(o) for o in owners if o != resource][:6]}
        vehicles.append({'label': label, 'resource': hexid(resource), 'path': path, 'kind': kind,
            'catalogName': names.get(resource), 'driveModel': drive_model(components, wheel_nodes),
            'populatedWheels': wheel_nodes, 'components': records,
            'identificationLead': UNNAMED[resource][2] if resource in UNNAMED else None})
    return vehicles


def mounted_turrets(t):
    """Mounted entities that own a TurretComponent: catalog vehicle mounts plus enemy controls."""
    out = {}
    if VEHICLE_WEAPONS.is_file():
        for vehicle in json.loads(VEHICLE_WEAPONS.read_text(encoding='utf-8'))['vehicles']:
            if vehicle.get('carrier'):
                continue
            for slot in vehicle['slots']:
                resource = int(slot['path'], 16)
                if t.component('TurretComponentData').record_of(resource) is not None:
                    out[f"{vehicle['name']} / {slot['name'] or 'slot ' + str(slot['slot'])}"] = resource
    for pattern in (r'cyborg_tank_turret_cannon/cyborg_tank_turret_heavycannon$', r'cyborg_big_walker_turret_cannon$',
            r'shuttle_gunship_turret_hmg$', r'lav_autocannon/lav_autocannon$', r'illuminate_turret_wm_cannon$'):
        for resource in t.find(pattern):
            out['control / ' + t.label(resource)] = resource
    return out


def record_identity(t, component, resource):
    """The exact backing identity a guarded write re-proves: record, index row and every owner."""
    table = t.component(component)
    rows = [(row, record) for row, owner, record in table.rows() if owner == resource]
    if len(rows) != 1:
        return None
    row, record = rows[0]
    owners = table.owners(record)
    return {'component': component, 'recordIndex': record, 'indexRow': row, 'ownerCount': len(owners),
        'uniqueOwner': len(owners) == 1, 'ownerResources': [hexid(o) for o in owners]}


def mount_label(slot):
    """The mounted-weapon key label scripts/generate_vehicle_weapon_authoring.py uses."""
    return slot.get('name') or slot.get('attachNodeName') or f"slot_{slot['slot']}"


def authoring_section(t, names):
    """Phase-2 backings: every (target, field) the generators publish, with its exact record identity and baseline,
    the targets that are not applicable, and the entity-delta check (a delta patching one of these records would
    override a type-record write at creation)."""
    from reference_format import dl_hash as _dl_hash
    import research_magazine_attachments as attachments
    vehicle_fields, mount_fields = [], []
    not_applicable = {'turret': [], 'rotation': [], 'steering': []}
    for resource, name in sorted(names.items(), key=lambda item: item[1]):
        entity = t.entity(resource)
        for field_id, component in (('rotation.turn_speed', 'RotationComponentData'),
                ('rotation.acceleration', 'RotationComponentData'), ('rotation.deceleration', 'RotationComponentData'),
                ('vehicle.steering_response_speed', 'VehicleMotionComponentData')):
            family = 'rotation' if component == 'RotationComponentData' else 'steering'
            if component not in entity:
                if name not in not_applicable[family]:
                    not_applicable[family].append(name)
                continue
            contract = FIELD_CONTRACTS[field_id]
            identity = record_identity(t, component, resource)
            _, value = element_value(t, component, identity['recordIndex'], contract['offset'])
            if not identity['uniqueOwner']:
                raise AssertionError(f'{name}: {component} record is shared; re-prove the scope')
            vehicle_fields.append({'vehicle': name, 'resource': hexid(resource), 'field': field_id,
                'offset': contract['offset'], 'storage': 'f32', 'baseline': jsonable(value), **identity})
    if VEHICLE_WEAPONS.is_file():
        for vehicle in json.loads(VEHICLE_WEAPONS.read_text(encoding='utf-8'))['vehicles']:
            if vehicle.get('carrier'):
                continue
            for slot in vehicle['slots']:
                if not slot['isWeapon']:
                    continue
                key = f"{vehicle['name']} / {mount_label(slot)}"
                resource = int(slot['path'], 16)
                identity = record_identity(t, 'TurretComponentData', resource)
                if identity is None:
                    not_applicable['turret'].append(key)
                    continue
                if not identity['uniqueOwner']:
                    raise AssertionError(f'{key}: TurretComponent record is shared; re-prove the scope')
                for field_id, contract in FIELD_CONTRACTS.items():
                    if contract['component'] != 'TurretComponentData':
                        continue
                    _, value = element_value(t, 'TurretComponentData', identity['recordIndex'], contract['offset'])
                    mount_fields.append({'weapon': key, 'vehicle': vehicle['name'], 'slot': slot['slot'],
                        'resource': slot['path'], 'field': field_id, 'offset': contract['offset'], 'storage': 'f32',
                        'baseline': jsonable(value), **identity})
    t.entity_rows()
    index_of = {type_hash: index for index, type_hash in t._index_type.items()}
    deltas, _ = attachments.entity_deltas((build_profile.datalibrary() / 'generated_entity_deltas.dl_bin').read_bytes())
    touched = {}
    for component in ('TurretComponentData', 'RotationComponentData', 'VehicleMotionComponentData'):
        type_index = index_of[_dl_hash(component)]
        touched[component] = sorted(hexid(resource) for resource, item in deltas.items()
            if any(entry['component'] == type_index for entry in item['entries']))
    targets = {item['resource'].upper() for item in vehicle_fields + mount_fields}
    hit = sorted(r for rows in touched.values() for r in rows if r.upper() in targets)
    if hit:
        raise AssertionError('an entity delta patches a vehicle tuning record: ' + ', '.join(hit))
    return {'vehicleFields': vehicle_fields, 'mountFields': mount_fields, 'notApplicable': not_applicable,
        'fieldContracts': FIELD_CONTRACTS,
        'entityDeltas': {'deltaEntities': len(deltas), 'touching': touched, 'touchingTargets': hit},
        'consumers': 'every backing record has exactly one owner (ownerResources); no entity delta patches any of '
            'them, so a write reaches exactly the named vehicle or mount and needs no allow_shared'}


def published_search(t, code, resource, value, unit):
    """Every float element of every record the entity owns equal to value (km/h also tried in m/s), with an
    assessment: absent, or only coincidental round numbers in members with no movement consumer."""
    forms = [value] + ([value / 3.6] if unit == 'km/h' else [])
    hits = _published_hits(t, resource, forms)
    by_form = {str(round(f, 4)): sum(1 for h in hits if h['form'] == round(f, 4)) for f in forms}
    motion = [h for h in hits if h['component'] == 'VehicleMotionComponentData']
    bound = sorted({'+' + h['path'] for h in motion if int(h['path']) in INPUT_RATE_OFFSETS})
    unbound = sorted({'+' + h['path'] for h in motion if int(h['path']) not in INPUT_RATE_OFFSETS})
    read = [o for o in unbound if code['VehicleMotionComponentData']['reads'].get(int(o[1:]))]
    unread = [o for o in unbound if o not in read]
    notes = ([f"VehicleMotion {', '.join(bound)} are code-bound driver-input rates"] if bound else []) + (
        [f"VehicleMotion {', '.join(read)} are read natively, role not established"] if read
        else []) + ([f"VehicleMotion {', '.join(unread)} have no consumer in the tracked code"] if unread else [])
    assessment = 'absent in every form' if not hits else 'coincidental round numbers in %d members; none is shown to be a speed%s' % (
        len(hits), (' (' + '; '.join(notes) + ')') if notes else '')
    return {'forms': by_form, 'matches': hits, 'assessment': assessment}


def _published_hits(t, resource, forms):
    hits = []
    for component, record in t.entity(resource).items():
        try:
            table = t.component(component)
        except (KeyError, ValueError):
            continue
        raw = table.raw(record)
        for member in table.members():
            if member.kind not in ('float', 'vector'):
                continue
            got = tables.decode(member, raw)
            for index, item in enumerate(got if isinstance(got, list) else [got]):
                for form in forms:
                    if isinstance(item, float) and abs(item - form) <= 1e-3 * max(1.0, abs(form)):
                        hits.append({'component': component, 'path': member.path + (f'[{index}]' if isinstance(got, list) else ''),
                            'nameLength': member.name_length, 'form': round(form, 4)})
    return hits


# ---------------------------------------------------------------------------------------------------------------
# research
# ---------------------------------------------------------------------------------------------------------------
def code_map(t, native):
    """Per component: table offset, lookups, resolved accessors, and every tracked member access."""
    result = {}
    for component in COMPONENTS:
        index = component_index(t, component)
        offset = TABLE_BASE + 8 * index
        found = native.lookups(offset)
        accessors = sorted(set(found['byResource'] + found['byPointer'] + [r['accessor'] for r in found['resolved']]))
        size = t.component(component).record_size
        reads = defaultdict(list)
        sites = set()
        for accessor in accessors:
            for site, kind in native.branches_to(accessor):
                if kind != 'call':
                    continue
                sites.add(site)
                for access in native.track(site + 5, {'rax': 0}, budget=1500):
                    if 0 <= access['offset'] < size:
                        access['function'] = native.function_of(site)
                        access['site'] = site
                        reads[access['offset']].append(access)
        result[component] = {'componentIndex': index, 'tableOffset': offset, 'recordSize': size,
            'lookups': {'byResource': found['byResource'], 'byPointer': found['byPointer'],
                'resolved': found['resolved'], 'tableLoads': found['tableLoads']},
            'callSites': len(sites), 'reads': dict(reads)}
    return result


def member_reads(code, component, offset):
    items = code[component]['reads'].get(offset, [])
    return {'count': len(items), 'float': sum(1 for a in items if a['float']),
        'writes': sum(1 for a in items if a['write']), 'functions': sorted({a['function'] for a in items}),
        'sites': [{'rva': a['rva'], 'asm': a['asm'], 'function': a['function'], **({'via': a['via']} if a.get('via') else {})}
            for a in items[:6]]}


def values_for(t, component, entities, offset):
    table = t.component(component)
    out = {}
    for label, resource in entities.items():
        record = table.record_of(resource)
        if record is None:
            continue
        _, value = element_value(t, component, record, offset)
        out[label] = thin_value(t, value)
    return out


def differential(values):
    numeric = [v for v in values.values() if isinstance(v, (int, float))]
    return len({round(v, 6) for v in numeric}) > 1


def network_names():
    resolved = {}
    for name in NETWORK_NAME_CANDIDATES:
        value = resource_hash(name) >> 32
        if value in NETWORK_FIELDS:
            resolved[f'0x{value:08X}'] = name
    return {'method': 'engine IdString = upper 32 bits of Murmur64A(name); candidates hashed, exact matches kept',
        'fields': {f'0x{h:08X}': {'role': role, 'name': resolved.get(f'0x{h:08X}')} for h, role in NETWORK_FIELDS.items()},
        'candidatesTested': len(NETWORK_NAME_CANDIDATES)}


def snapshot_lifecycle():
    from scan import instances
    directory = build_profile.snapshot_directory()
    out = {}
    for name in MISSION_SNAPSHOTS:
        if not (directory / name).is_file():
            out[name] = {'status': 'absent'}
            continue
        reader = instances.SnapshotReader(name)
        try:
            base = reader.modules['game.dll']['base']
            row = {}
            for component, (manager_global, _, _, map_offset) in MANAGERS.items():
                manager = instances.u64(reader, base + manager_global)
                header = reader.read(manager, 0x100) if manager else None
                if header is None:
                    row[component] = None
                    continue
                if map_offset is None:
                    count = struct.unpack_from('<I', header, 0x2C)[0]   # VehicleMotion: live instance count
                    row[component] = {'liveInstances': count}
                    continue
                table, = struct.unpack_from('<Q', header, map_offset)
                capacity, empty = struct.unpack_from('<II', header, map_offset + 8)
                copies = 0
                raw = reader.read(table, capacity * 8) if table and 0 < capacity < 100000 else None
                if raw:
                    for i in range(capacity):
                        key, index = struct.unpack_from('<Ii', raw, i * 8)
                        if key != empty and index != -1:
                            copies += 1
                row[component] = {'copyMapCapacity': capacity, 'privateCopies': copies}
            vc = instances.u64(reader, base + MANAGERS['VehicleComponentData'][0])
            counters = struct.unpack_from('<III', reader.read(vc + 0x24, 12))
            row['vehicleComponentInstanceCounters'] = list(counters)
            out[name] = row
        finally:
            reader.close()
    return out


def wiki_durability(names):
    if not (WIKI.is_file() and ENTITY_RESEARCH.is_file()):
        return {'status': 'wiki or entity research absent'}
    wiki = {item['name']: item for item in json.loads(WIKI.read_text(encoding='utf-8'))['stratagems']}
    entity = {item['name']: item for item in json.loads(ENTITY_RESEARCH.read_text(encoding='utf-8'))['vehicles']}
    rows = []
    for name, item in sorted(entity.items()):
        page = wiki.get(name)
        anatomy = defaultdict(dict)
        if page:
            for field in page['rawStructuredFields']:
                if field['section'].startswith('Anatomy >') and field['label'] in ('Health1', 'Durable2'):
                    anatomy[field['section'].split('>', 1)[1].strip()][field['label']] = field['raw']
        zones = [z for z in item['health']['zones'] if z.get('populated')]
        matched = []
        for part, stats in anatomy.items():
            raw = (stats.get('Health1') or '').replace(',', '')
            if not raw.isdigit() or part == 'Main':
                continue
            health = int(raw)
            count = re.search(r'\((\d+)\)', part)
            hits = [z['index'] for z in zones if z['health'] == health]
            matched.append({'part': part, 'publishedHealth': health, 'publishedCount': int(count.group(1)) if count else 1,
                'zonesWithEqualHealth': hits})
        published = item.get('wiki') or {}
        rows.append({'vehicle': name, 'mainHealth': item['health']['mainHealth'],
            'publishedMainHealth': published.get('mainHealth'), 'mainArmor': item['health']['defaultArmor'],
            'publishedMainArmor': published.get('mainArmor'), 'populatedZones': len(zones), 'anatomy': matched,
            'published': published.get('mainHealth') is not None})
    return {'source': str(WIKI.relative_to(ROOT.parent)).replace('\\', '/'), 'vehicles': rows}


def candidate(t, code, family, component, offset, entities, *, semantic, units=None, proposed=None, published=False,
              live=False, lifecycle=None, sharing=None, refs=(), notes=(), status='research_only'):
    member, _ = element_value(t, component, 0, offset)
    values = values_for(t, component, entities, offset)
    reads = member_reads(code, component, offset)
    evidence = {'codeRead': reads['count'] > 0, 'publishedExact': published, 'liveTest': live,
        'nameLengthFit': bool(proposed) and member.name_length == len(proposed), 'differential': differential(values)}
    path = member.path
    if member.atom in ('INLINE_ARRAY', 'VECTOR') and member.count > 1:
        width = member.element_size() if member.atom != 'VECTOR' else 4
        path = f'{member.path}[{(offset - member.offset) // width}]'
    return report.candidate(path, offset, member.storage, member.name_length, member.kind, values, evidence, proposed,
        notes, family=family, component=component, semantic=semantic, units=units, lifecycle=lifecycle,
        sharing=sharing, codeReads=reads, codeRefs=list(refs), status=status)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--no-snapshots', action='store_true', help='skip the mission-snapshot lifecycle check')
    args = parser.parse_args(argv)

    t = tables.pinned()
    image = xref.CodeImage.from_snapshot('game.dll')
    if image.sha256 != GAME_DLL_SHA256:
        raise SystemExit('game.dll changed: %s' % image.sha256)
    native = Native(image)
    names = catalog_names()

    # 1-2. inventory and layouts
    vehicles = inventory(t, names)
    by_label = {v['label']: int(v['resource'], 16) for v in vehicles}
    layouts = {}
    for component in COMPONENTS:
        table = t.component(component)
        layouts[component] = {'recordType': table.record_type, 'recordSize': table.record_size, 'records': table.count,
            'indexCapacity': table.capacity, 'fingerprint': t.fingerprint(component),
            'componentIndex': component_index(t, component),
            'sharedRecords': sum(1 for owners in table.owner_map().values() if len(owners) > 1),
            'unownedRecords': [i for i in range(table.count) if not table.owners(i)],
            'members': [{'path': m.path, 'offset': m.offset, 'size': m.size, 'storage': m.storage,
                'nameLength': m.name_length, 'type': m.type_name} for m in table.members()
                if not re.search(r'\[(?:[1-9]|[1-9]\d)\]', m.path)]}   # first element of inline arrays only

    # 3-4. native lookups and member reads
    code = code_map(t, native)
    for component, item in code.items():
        if item['componentIndex'] * 8 + TABLE_BASE != item['tableOffset']:
            raise AssertionError(component)
    if not code['MountComponentData']['lookups']['byResource'] == [0x510220]:
        raise AssertionError('Mount lookup moved: the settings-root derivation needs review')

    # 5. reviewed pins
    pins = {group: [native.pin(rva, asm, role) for rva, asm, role in rows] for group, rows in PINS.items()}
    manager_names = {}
    for component, name in MANAGER_NAMES.items():
        refs = []
        for at in image.find_bytes(name.encode() + b'\0'):
            if at and image.data[at - 1] == 0:
                refs += [{'rva': i.address, 'function': native.function_of(i.address)} for i in native.rip_refs(at)]
        manager_names[component] = refs

    # 6. lifecycle
    lifecycle = {'managers': {c: {'global': g, 'resolvedAccessor': a, 'copyPoolOffset': p, 'copyMapOffset': m}
        for c, (g, a, p, m) in MANAGERS.items()},
        'snapshots': {'status': 'skipped'} if args.no_snapshots else snapshot_lifecycle()}

    # 7. published values
    published = {name: {'resource': hexid(spec['resource']), 'records': len(t.entity(spec['resource'])),
        'values': [{'quantity': q, 'value': v, 'unit': u} | published_search(t, code, spec['resource'], v, u)
            for q, v, u in spec['values']]} for name, spec in PUBLISHED_MOVEMENT.items()}
    bastion = published['TD-220 Bastion MK XVI']
    absent = [f"{x['value']:g} {x['unit']}" for x in bastion['values'] if not x['matches']]
    coincidental = [f"{x['value']:g} {x['unit']}" for x in bastion['values'] if x['matches']]
    durability_cross = wiki_durability(names)

    # -------------------------------------------------------------------------------------------------------
    # families
    # -------------------------------------------------------------------------------------------------------
    def owners_of(component, kinds=None):
        out = {}
        for v in vehicles:
            if component in v['components'] and (kinds is None or v['kind'] in kinds):
                out[v['label']] = int(v['resource'], 16)
        return out

    wheeled = owners_of('VehicleMotionComponentData')
    exo_and_walkers = owners_of('RotationComponentData')
    turrets = mounted_turrets(t)
    loco = owners_of('LocomotionComponentData')
    vmotion_live = 'read every frame from the shared type record through 0x507A90 (VehicleMotion has no copy pool)'
    unique_vm = 'one record per vehicle type (14 records, 14 owners): a write changes every vehicle of that type'

    movement = [
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 364, wheeled,
            semantic='driver steering input slew rate: the signed steering input (channel 0, -1..1) moves toward the '
                     'driver target by at most rate * dt per frame, in both directions',
            units='input units per second', proposed='steering_response_speed', lifecycle=vmotion_live,
            sharing=unique_vm, refs=['driverInputSmoothing'], status='proposed'),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 368, wheeled,
            semantic='channel 1 (non-negative driver input) decrease rate when the global input-mode flag is set; '
                     'increases use a constant 100/s', units='input units per second', lifecycle=vmotion_live,
            sharing=unique_vm, refs=['driverInputSmoothing'],
            notes=['channel identity (throttle vs brake) is inferred from structure; the flag at '
                   '[0x347CF18]+0xE1AD5 is not identified']),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 372, wheeled,
            semantic='channel 1 decrease rate when the input-mode flag is clear', units='input units per second',
            lifecycle=vmotion_live, sharing=unique_vm, refs=['driverInputSmoothing']),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 376, wheeled,
            semantic='channel 2 (non-negative driver input, forced to 1.0 by the assist branch) decrease rate, flag set',
            units='input units per second', lifecycle=vmotion_live, sharing=unique_vm, refs=['driverInputSmoothing']),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 380, wheeled,
            semantic='channel 2 decrease rate, flag clear', units='input units per second', lifecycle=vmotion_live,
            sharing=unique_vm, refs=['driverInputSmoothing']),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 344, wheeled,
            semantic='factor applied to three components of a physics-actor vector read and written back through the '
                     'engine actor API (+0x80/+0x88) by 0x7194C0', lifecycle=vmotion_live, refs=['velocityScaling'],
            notes=['the API slots are not identified, nor is the trigger of 0x7194C0']),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 348, wheeled,
            semantic='factor applied to the fourth component in 0x7194C0', lifecycle=vmotion_live,
            refs=['velocityScaling']),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 4, wheeled,
            semantic='unread in the tracked code; 0.5 only on the M-104 Incinerator FRV (the wiki describes it as '
                     'slower in acceleration, top speed and handling: prose, not a value)',
            notes=['differential lead only']),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 296, wheeled,
            semantic='float compared with 100 at 0x71764F (FRV and cargo car, 150, take another branch than the tanks '
                     'and the oil rig, 20) and passed with +300/+304/+308 as the four float arguments of 0x12A2DB0, '
                     'whose 0..6 result is dispatched by a jump table; role not established',
            notes=['the Bastion value 20 equals its published 1st-gear top speed (20 km/h), but 20 also occurs in 49 '
                   'other Bastion members: a lead for a live test, not evidence']),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 300, wheeled,
            semantic='second float argument of 0x12A2DB0 (FRV and cargo car 250, others 100); role not established'),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 388, wheeled,
            semantic='VehicleOffroadModeInfo +4: divisor of an instance value at 0x717588 when the off-road mode flag '
                     '(+384) is set; role not established'),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 352, wheeled,
            semantic='float read by 0x7196A0 / 0x11A8650 (role not established)'),
        candidate(t, code, 'movement', 'VehicleMotionComponentData', 356, wheeled,
            semantic='float read by 0x719310 / 0x11A8490 (role not established)'),
        candidate(t, code, 'movement', 'RotationComponentData', 0, exo_and_walkers,
            semantic='maximum body turn rate: the rotation update drives the angular velocity toward sign(angle) * '
                     'rate', units='degrees per second', proposed='turn_speed',
            lifecycle='copied (x pi/180) into the Rotation instance block at creation (0x61D640): applies to bodies '
                      'spawned after the write', sharing='one record per entity type', refs=['rotationCreation',
                'rotationUpdate'], status='proposed',
            notes=['enemy walkers drive an animation variable named turn_speed from the same component (+300)']),
        candidate(t, code, 'movement', 'RotationComponentData', 4, exo_and_walkers,
            semantic='angular acceleration toward the turn rate; <= 0 turns at the full rate at once',
            units='degrees per second squared', proposed='acceleration',
            lifecycle='copied (x pi/180) at creation', sharing='one record per entity type',
            refs=['rotationCreation', 'rotationUpdate'], status='proposed'),
        candidate(t, code, 'movement', 'RotationComponentData', 8, exo_and_walkers,
            semantic='angular deceleration used to stop on the target angle (stopping time = velocity / deceleration); '
                     '<= 0 uses the acceleration', units='degrees per second squared', proposed='deceleration',
            lifecycle='copied (x pi/180) at creation', sharing='one record per entity type',
            refs=['rotationCreation', 'rotationUpdate'], status='proposed'),
        candidate(t, code, 'movement', 'LocomotionComponentData', 4464, loco,
            semantic='component default copied at creation into the locomotion instance array (+0x1C); each '
                     'LocomotionSet may override it (+476, -2 = default)', lifecycle='copied at creation',
            refs=['locomotionCreation'], notes=['consumer semantics not established (exosuit 10, walkers 40, '
                'Helldiver 100)']),
        candidate(t, code, 'movement', 'LocomotionComponentData', 4468, loco,
            semantic='second component default (+0x20), overridable by LocomotionSet +480', lifecycle='copied at creation',
            refs=['locomotionCreation']),
        candidate(t, code, 'movement', 'VehicleLocomotionComponentData', 24, owners_of('VehicleLocomotionComponentData'),
            semantic='integer read by 0x712B30 (150 on every owner)'),
        candidate(t, code, 'movement', 'MotionComponentData', 24, exo_and_walkers,
            semantic='vector member (exosuits 0.75/1, walkers 0.25/0.5); unread in the tracked code'),
    ]

    vc_entities = owners_of('VehicleComponentData')
    tracks = owners_of('VehicleTracksComponentData')
    suspension = [
        candidate(t, code, 'suspension', 'VehicleComponentData', 8, vc_entities,
            semantic='WheelInfo +0: read per wheel at vehicle creation (0x6FD830); 0 means 1.0. FRV 0.35, oil rig 0.6, '
                     'tank 0.9, cargo car 1.2, landing gear 0.6/1.0', lifecycle='VehicleComponent has a copy pool; '
                     'read at creation', refs=['wheelCreation'],
            notes=['radius-like magnitudes; no consumer of the stored value was followed: no name proposed']),
        candidate(t, code, 'suspension', 'VehicleComponentData', 16, vc_entities,
            semantic='WheelInfo +8: unread in the tracked code (FRV 0.03, tank/oil rig 0.1, cargo 0.3, gear 0.5)'),
        candidate(t, code, 'suspension', 'VehicleComponentData', 24, vc_entities,
            semantic='WheelInfo +16: wheel translation node name (thin hash, e.g. l_front_translation), resolved on '
                     'the unit at creation', refs=['wheelCreation'], notes=['structural reference: not a tuning value']),
        candidate(t, code, 'suspension', 'VehicleComponentData', 28, vc_entities,
            semantic='WheelInfo +20: steering node name (front wheels only)', refs=['wheelCreation'],
            notes=['structural reference']),
        candidate(t, code, 'suspension', 'VehicleComponentData', 36, vc_entities,
            semantic='WheelInfo +28: suspension/gear-compression variable name (l_front_suspension, l_gear_compression)',
            refs=['wheelCreation'], notes=['structural reference']),
        candidate(t, code, 'suspension', 'VehicleComponentData', 44, vc_entities,
            semantic='WheelInfo +36: 80 on every wheel of every vehicle and in the default record (no differential)'),
        candidate(t, code, 'suspension', 'VehicleComponentData', 48, vc_entities,
            semantic='WheelInfo +40: 20 everywhere (no differential)'),
        candidate(t, code, 'suspension', 'VehicleComponentData', 52, vc_entities,
            semantic='WheelInfo +44: 8 everywhere (no differential)'),
        candidate(t, code, 'suspension', 'VehicleComponentData', 64, vc_entities,
            semantic='WheelInfo +56: read at creation; -0.58/+0.58 alternating on tank and oil-rig wheels (side)',
            refs=['wheelCreation']),
        candidate(t, code, 'suspension', 'VehicleTracksComponentData', 128, tracks,
            semantic='track road-wheel +32 (0.3/0.5 alternating on Bastion/Maelstrom), read as float per wheel by '
                     '0xA2F400 / 0xA2F7F0', notes=['a radius is plausible; not shown']),
        candidate(t, code, 'suspension', 'VehicleTracksComponentData', 1252, tracks,
            semantic='tracks scalar (siege engine 6, Bastion/Maelstrom 22); unread in the tracked code'),
        candidate(t, code, 'suspension', 'BuoyancyComponentData', 8, owners_of('BuoyancyComponentData'),
            semantic='first buoyancy sphere +0, read as float (0x859F40/0x859F80)'),
        candidate(t, code, 'suspension', 'GroundCheckComponentData', 4,
            {k: v for k, v in owners_of('GroundCheckComponentData').items()},
            semantic='ground-check float read by 0x53C880 / 0x909540 / 0xA75FA0'),
    ]

    turret_owner_counts = [len(o) for o in t.component('TurretComponentData').owner_map().values()]
    turret_sharing = ('one record per mounted entity: no TurretComponent record has more than one owner (%d owned '
        'records). Mounts without a TurretComponent: the M-102 / Super Earth FRV gun, the M-104 flamethrower, the '
        'Maelstrom launchers (slots 2-4) and every exosuit arm' % len(turret_owner_counts))
    if max(turret_owner_counts) != 1:
        raise AssertionError('a TurretComponent record became shared: review the sharing scope')
    turret = [
        candidate(t, code, 'turret', 'TurretComponentData', 12, turrets,
            semantic='horizontal (traverse) rate limit of the mount: degrees per second, times the per-instance '
                     'turn_speed_modifier, eased within the last 5 degrees', units='degrees per second',
            proposed='horizontal_turn_speed', lifecycle='copied into the turret instance (+8) and a network creation '
                'field at creation (0x6E06F0): applies to mounts created after the write', sharing=turret_sharing,
            refs=['turretCreation', 'turretUpdate'], status='proposed'),
        candidate(t, code, 'turret', 'TurretComponentData', 8, turrets,
            semantic='vertical (elevation) rate limit of the mount', units='degrees per second',
            proposed='vertical_turn_speed', lifecycle='copied into the turret instance (+12) and a network creation '
                'field at creation', sharing=turret_sharing, refs=['turretCreation', 'turretUpdate'], status='proposed'),
        candidate(t, code, 'turret', 'TurretComponentData', 20, turrets,
            semantic='lowest vertical angle (depression), clamp of the aimed elevation', units='degrees',
            proposed='min_vertical_angle', lifecycle='read from the resolved record every update (0x6DEDB0)',
            sharing=turret_sharing, refs=['turretUpdate'], status='proposed'),
        candidate(t, code, 'turret', 'TurretComponentData', 24, turrets,
            semantic='highest vertical angle (elevation)', units='degrees', proposed='max_vertical_angle',
            lifecycle='read every update', sharing=turret_sharing, refs=['turretUpdate'], status='proposed'),
        candidate(t, code, 'turret', 'TurretComponentData', 28, turrets,
            semantic='lowest horizontal angle; a range of 360 degrees or more is unrestricted (wrapping)',
            units='degrees', proposed='min_horizontal_angle', lifecycle='read every update', sharing=turret_sharing,
            refs=['turretUpdate'], status='proposed'),
        candidate(t, code, 'turret', 'TurretComponentData', 32, turrets,
            semantic='highest horizontal angle', units='degrees', proposed='max_horizontal_angle',
            lifecycle='read every update', sharing=turret_sharing, refs=['turretUpdate'], status='proposed'),
        candidate(t, code, 'turret', 'TurretComponentData', 0, turrets,
            semantic='vertical-rotation node name (elevation / pitch)', notes=['structural reference']),
        candidate(t, code, 'turret', 'TurretComponentData', 4, turrets,
            semantic='horizontal-rotation node name (traverse / yaw)', notes=['structural reference']),
        candidate(t, code, 'turret', 'TurretComponentData', 16, turrets,
            semantic='exponent of the horizontal aim error in the turret update (pow(error_deg, -k) clamped to 0..1); '
                     'role of the result not followed'),
        candidate(t, code, 'turret', 'TurretComponentData', 36, turrets, semantic='0.1 on every turret (no differential)'),
    ]

    health_owners = {v['label']: int(v['resource'], 16) for v in vehicles if v['catalogName']}
    cd = owners_of('VehicleCollisionDamageComponentData')
    durability = [
        candidate(t, code, 'durability', 'HealthComponentData', 0, health_owners,
            semantic='main health (existing field hd2.fields.entity.health; gameplay-proven on the Bastion)',
            published=True, live=True, status='already_promoted', refs=[],
            notes=['published main health matches for every catalog vehicle (see durabilityCrossCheck)']),
        candidate(t, code, 'durability', 'HealthComponentData', 280, health_owners,
            semantic='default-zone armour (existing field hd2.fields.entity.armor)', published=True, live=True,
            status='already_promoted'),
        candidate(t, code, 'durability', 'VehicleCollisionDamageComponentData', 0, cd,
            semantic='float read by 0x6F58F0 / 0x6F7B80 (FRV 1, Incinerator and oil rig 1.5)'),
        candidate(t, code, 'durability', 'VehicleCollisionDamageComponentData', 16, cd,
            semantic='collision-damage scalar (FRV 1000, Incinerator 1500, tanks 2000, oil rig 800); unread in the '
                     'tracked code'),
        candidate(t, code, 'durability', 'VehicleCollisionDamageComponentData', 108, cd,
            semantic='float read by 0x6F7EF0 (FRV 8000, tanks 20000, others 10000)'),
        candidate(t, code, 'durability', 'VehicleCollisionDamageComponentData', 124, cd,
            semantic='float read by 0x13C29E0 (30 everywhere)'),
    ]

    families = {'movement': movement, 'suspension': suspension, 'turret': turret, 'durability': durability}
    for rows in families.values():
        for row in rows:
            row['values'] = {k: jsonable(v) for k, v in row['values'].items()}

    # Phase 2 (approved 2026-10-05): one semantic layer. Vehicle turrets reuse the sentry turret field ids on the
    # same TurretComponent members; the semantic name column keeps the hidden-name-length check.
    proposal_fields = {key: (FIELD_CONTRACTS[field_id]['apiConstant'], FIELD_CONTRACTS[field_id]['constraints'],
        FIELD_CONTRACTS[field_id]['target']) for field_id, key in
        ((field_id, (contract['component'], contract['offset'])) for field_id, contract in FIELD_CONTRACTS.items())}
    kinds = {v['label']: v['kind'] for v in vehicles}
    proposal_targets = {
        'TurretComponentData': {k for k in turrets if not k.startswith('control /')},
        'RotationComponentData': {k for k, kind in kinds.items() if kind == 'exosuit' and k in exo_and_walkers},
        'VehicleMotionComponentData': {k for k, kind in kinds.items() if kind == 'player_vehicle' and k in wheeled},
    }
    proposal, not_promoted = [], []
    for family, rows in families.items():
        for row in rows:
            key = (row['component'], row['offset'])
            if row['status'] == 'proposed':
                field_id, constraint, target = proposal_fields[key]
                if row['confidence'] not in ('STRONG', 'CONFIRMED') or not row['proposedNameLengthFit']:
                    raise AssertionError(f'{field_id}: proposal below the bar ({row["confidence"]})')
                contract = FIELD_CONTRACTS[field_id.removeprefix('hd2.fields.')]
                proposal.append({'fieldId': field_id, 'semanticFieldId': field_id.removeprefix('hd2.fields.'),
                    'family': family, 'component': row['component'],
                    'offset': row['offset'], 'storage': row['storage'], 'nameLength': row['nameLength'],
                    'semanticName': row['proposedName'], 'units': row['units'], 'constraints': constraint,
                    'min': contract['min'], 'max': contract['max'], 'rangeReason': contract['rangeReason'],
                    'order': contract.get('order'), 'lifecycle': contract['lifecycle'],
                    'target': target, 'semantic': row['semantic'], 'confidence': row['confidence'],
                    'writeSemantics': contract['writeSemantics'],
                    'sharing': row['sharing'],
                    'acknowledgement': ['allow_unverified_effect'],
                    'sharedRecord': False,
                    'codeRefs': row['codeRefs'], 'values': {k: v for k, v in row['values'].items()
                        if k in proposal_targets[row['component']]}})
            elif row['status'] != 'already_promoted':
                reasons = []
                if not row['evidence']['codeRead']:
                    reasons.append('no native read found from any record lookup/accessor call site')
                if not row['proposedName']:
                    reasons.append('meaning not established: no reviewed semantic name')
                if not row['evidence']['differential']:
                    reasons.append('no family differential')
                if any('structural' in n for n in row['notes']):
                    reasons.append('structural reference (node/variable name): not an authoring value')
                not_promoted.append({'family': family, 'component': row['component'], 'offset': row['offset'],
                    'path': row['path'], 'nameLength': row['nameLength'], 'confidence': row['confidence'],
                    'semantic': row['semantic'], 'reasons': reasons or ['research only']})
    not_promoted += [
        {'family': 'movement', 'component': None, 'offset': None, 'path': None, 'nameLength': None,
         'confidence': 'UNKNOWN', 'semantic': 'top speed, reverse speed, gear ratios, engine torque, braking force',
         'reasons': ['not in the entity component data: of the published Bastion speeds, %s occur in none of its %d '
             'records (km/h or m/s); %s only coincide with round numbers, none of them shown to be a speed '
             '(publishedMovement). The drivetrain lives outside the DL tables (physics resource or code).'
             % (', '.join(absent), bastion['records'], ', '.join(coincidental))]},
        {'family': 'suspension', 'component': None, 'offset': None, 'path': None, 'nameLength': None,
         'confidence': 'UNKNOWN', 'semantic': 'spring stiffness, damping, rest length, travel, anti-roll, centre of mass',
         'reasons': ['no differential member with a native consumer: the WheelInfo floats that could hold them '
             '(+36 80, +40 20, +44 8, +48 0.1) are identical for every wheel of every vehicle and the default record']},
        {'family': 'movement', 'component': None, 'offset': None, 'path': None, 'nameLength': None,
         'confidence': 'UNKNOWN', 'semantic': 'FRV fuel capacity (60 L published)',
         'reasons': ['the only FRV float equal to 60 is VehicleCollisionDamage +8/+40 (crash damage family)']},
        {'family': 'movement', 'component': 'LocomotionComponentData', 'offset': None, 'path': '0[n].8[m].8',
         'nameLength': 9, 'confidence': 'UNKNOWN', 'semantic': 'exosuit walk speed',
         'reasons': ['exosuit LocomotionSet speed ranges hold 0.2/1 thresholds; exosuit walking is not driven by a '
             'speed member found here (MotionComponent mode 1 for exosuits, 4 for walkers)']},
    ]

    custom = {
        'principle': 'custom vehicles touch only their own instances (instance-local rule): a private copy when the '
            'component has a resolved accessor, never a write to a shared definition',
        'components': {
            'VehicleComponentData': {'privateCopySupported': True, 'accessor': '0x4FA7A0', 'copyStride': 3704,
                'note': 'copy pool exists (manager +0xC0); no copy exists in any retained snapshot; chassis/wheel '
                    'layout and HUD type live here'},
            'TurretComponentData': {'privateCopySupported': True, 'accessor': '0x50B8B0', 'copyStride': 76,
                'note': 'limits are read from the resolved record every update, so a private copy changes one mount '
                    'only; rates are captured at creation, so the copy must exist before the mount is created '
                    '(writing the instance block directly is unexplored)'},
            'RotationComponentData': {'privateCopySupported': True, 'accessor': '0x513690', 'copyStride': 312,
                'note': 'values captured at creation (radians in the 0x298-byte instance block)'},
            'LocomotionComponentData': {'privateCopySupported': True, 'accessor': '0x513C60', 'copyStride': 4624},
            'VehicleMotionComponentData': {'privateCopySupported': False,
                'note': 'no resolved accessor and no copy pool: every reader goes to the type record, so a custom '
                    'vehicle cannot hold private VehicleMotion values; any change is per vehicle type'},
        },
        'safeForCustomVehicles': ['hd2.fields.turret.* through a private TurretComponent copy (limits live, rates at '
            'creation)', 'hd2.fields.rotation.* through a private Rotation copy created before the body spawns',
            'existing mounted-weapon fields (weapon-local records)', 'existing durability fields on a private '
            'HealthComponent copy (Health has a resolved accessor, 0x507920)'],
        'notSafe': ['VehicleMotion (shared per type, read live)', 'WheelInfo node names (bind to the unit model)',
            'drivetrain and suspension physics (not in DL data)'],
    }

    live_tests = [
        {'id': 'turret-traverse-rate', 'field': 'hd2.fields.turret.yaw_speed',
         'setup': 'before calling the M-103 Supply FRV: gun 130 -> 30 (no M-103 available: TD-220 Bastion slot 0, the '
             'cannon, 35 -> 8)',
         'observe': 'a 180-degree traverse of the M-103 gun takes about 6 s instead of about 1.4 s; a vehicle called '
             'before the write keeps the old rate (creation copy)', 'evidence': 'video with on-screen timing; runtime '
             'log of the write'},
        {'id': 'turret-traverse-limits', 'field': 'hd2.fields.turret.yaw_min/yaw_max',
         'setup': 'on a TD-220 Bastion already deployed, slot 0 (cannon): -20/20 -> -5/5',
         'observe': 'immediately (limits are read every update) the cannon arc narrows; also shows what the +/-20 '
             'degree arc governs (gun within the turret, or the turret itself)'},
        {'id': 'turret-elevation-limits', 'field': 'hd2.fields.turret.pitch_min/pitch_max',
         'setup': 'TD-220 Bastion slot 0: -3/25 -> -3/45', 'observe': 'the cannon elevates to 45 degrees'},
        {'id': 'exosuit-turn-rate', 'field': 'hd2.fields.rotation.turn_speed',
         'setup': 'before calling an EXO-45 Patriot: rotation.turn_speed 65 -> 20', 'observe': 'a 180-degree body turn takes 9 s instead '
             'of 2.8 s; then acceleration 0 -> 30 gives a visible ramp-up'},
        {'id': 'frv-steering-response', 'field': 'hd2.fields.vehicle.steering_response_speed',
         'setup': 'on a live M-102 FRV: 3.1 -> 0.5 (allow_shared: every M-102)',
         'observe': 'full lock takes about 2 s instead of 0.3 s, immediately (read every frame)'},
        {'id': 'multiplayer-turret', 'field': 'hd2.fields.turret.yaw_speed',
         'setup': 'host-only write, client gunner', 'observe': 'whether the client gunner sees the host rate (the rate '
             'is a network creation field written by the host)'},
    ]

    open_questions = [
        'Where do the drivetrain (top speed, gears, torque, brakes) and the raycast suspension (spring, damper, rest '
        'length) live? Not in the DL component tables; candidates are the unit physics resource or code constants.',
        'Which input is channel 1 and which is channel 2 of the driver-input smoothing (throttle vs brake), and what '
        'is the global input-mode flag ([0x347CF18]+0xE1AD5)?',
        'Engine actor API slots +0x80/+0x88/+0x90/+0x98 used with VehicleMotion +344/+348 (velocity vs angular '
        'velocity) and the trigger of 0x7194C0.',
        'Names of the turret creation fields 0xCC0B45E5 / 0x9D5D6CC7 and whether clients read them (host-authoritative '
        'turret rates).',
        'LocomotionComponent +4464/+4468 consumers (exosuit 10/30, Helldiver 100/100).',
        'WheelInfo +0 (radius-like) consumer after creation, and WheelInfo +8/+12 (unread here).',
        'The death-explosion link of the M-104 Incinerator fuel tank (wiki: inner 10 m, outer 25 m, 1500 damage).',
        'Which record carries the 360-degree main-turret traverse of the TD-220 Bastion and TD-110 Maelstrom: both of '
        'their TurretComponent mounts (slots 0 and 1) are limited to +/-20 degrees horizontally and -3..25 degrees '
        'vertically; the seat aim constraints (SeatCollection +308) are the lead.',
    ]

    candidates = [row for rows in families.values() for row in rows]
    document = report.document('Vehicle and mech component research domain',
        {'build': build_profile.BUILD_ID, 'gameDllSha256': image.sha256, 'components': list(COMPONENTS),
         'vehicles': len(vehicles), 'settingsRoot': SETTINGS_ROOT, 'tableBase': TABLE_BASE,
         'tableOffsetRule': 'root + 0xF12478 + 8 * componentIndex (EntitySettingsHashmap component index)'},
        candidates,
        schemaVersion=1, writes=0, protectionChanges=0,
        vehicles=vehicles, layouts=layouts,
        codeMap={c: {k: v for k, v in item.items() if k != 'reads'} | {'readMembers': {
            str(off): member_reads(code, c, off) | {'path': (member_of(t, c, off).path if member_of(t, c, off) else None)}
            for off in sorted(item['reads'])}} for c, item in code.items()},
        managerNameReferences=manager_names, pins=pins, networkFieldNames=network_names(), lifecycle=lifecycle,
        publishedMovement=published, durabilityCrossCheck=durability_cross,
        families={name: {'counts': {label: sum(1 for r in rows if r['confidence'] == label) for label in
            report.CONFIDENCE}, 'candidates': rows} for name, rows in families.items()},
        promotionProposal=proposal, authoring=authoring_section(t, names),
        phase2={'approved': '2026-10-05', 'naming': 'one semantic layer: vehicle turrets reuse the sentry turret ids '
            '(turret.yaw_speed/pitch_speed/pitch_min/pitch_max/yaw_min/yaw_max) on the same TurretComponent members; '
            'new ids rotation.turn_speed/acceleration/deceleration and vehicle.steering_response_speed',
            'evidence': 'sentry live evidence does not transfer to vehicle targets: every vehicle field requires '
            'allow_unverified_effect'},
        notPromoted=not_promoted, customVehicleFeasibility=custom, liveTestDesign=live_tests,
        openQuestions=open_questions,
        existingFields={'durability': ['hd2.fields.entity.health', 'hd2.fields.entity.armor', 'hd2.fields.zone.health',
            'hd2.fields.zone.armor', 'hd2.fields.zone.affects_main_health'],
            'mountedWeapons': ['hd2.fields.weapon.fire_rate', 'hd2.fields.weapon.capacity', 'hd2.fields.magazine.*',
                'hd2.fields.reload.duration', 'hd2.fields.heat.*', 'hd2.fields.beam.*', 'hd2.fields.arc.*',
                'hd2.fields.projectile.*', 'hd2.fields.damage.*', 'hd2.fields.explosion.*', 'hd2.fields.mount.weapon'],
            'source': 'sdk/VehicleAuthoringCapabilities.json, sdk/VehicleWeaponCapabilities.json'})
    document['candidates'] = [{'family': r['family'], 'component': r['component'], 'offset': r['offset'],
        'path': r['path'], 'confidence': r['confidence'], 'status': r['status']} for r in candidates]
    report.write(args.output, document)
    print('wrote', args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output)
    print('vehicles', len(vehicles), 'candidates', document['counts'], 'proposed', len(proposal))
    return 0


if __name__ == '__main__':
    sys.exit(main())
