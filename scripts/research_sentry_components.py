"""Sentry component catalogue (research only; read-only; build F5FEE03DCFDB).

Every component the ten sentry stratagems' deployed entities own is compared member by member across the sentries and
structural controls (emplacements, enemy turrets, the Pelican chin turret, cameras, the SEAF gun, Guard Dog drones),
and the members a sentry's behaviour depends on are tied to the native code that reads them:

* TurretComponentData: the turret system update (0x6DEDB0) reads its settings through the turret settings resolver
  (0x50B8B0: the entity's own settings copy if one exists, else the shared type record) every frame; the turn speeds
  are copied into the turret instance at spawn (0x6E06F0, replicated) and multiplied by a per-instance factor;
* SensorEyeComponentData: copied into the sensor instance at spawn (0x64C4C0 / 0x64C3C0, times a per-instance
  scale); the vision test (0x64C6F0) blends front/side/rear ranges for type-1 sensors (every sentry) and uses the
  cone half-angles only for type-2 sensors;
* SensorProximityComponentData: read live by the perception update (0x887760 -> 0x886A70 -> 0x64FD20): any candidate
  within its radius is marked perceived without a line-of-sight ray (the three mortars own it);
* TargetingComponentData: the targeting update (0x6BBDC0) reads it every frame (aim spring, node selection);
* WeaponDataComponentData: recoil blocks and spread are copied into the weapon instance at creation (0x752370) and
  read by every shot (spread 0x615BAB, recoil 0x784CAC/0x784CCF) - the same members the player/support weapons expose;
* WeaponWindUpComponentData (Gatling Sentry): read by the wind-up routine (0x78A420);
* the sentry behaviours (BehaviorComponentData +0): each turret AI is compiled code whose engagement distances, fire
  cones and re-pick times are constants, not data.

Inputs: the pinned entity file and type library (scripts/scan/tables.py), the game.dll image of a retained snapshot
(scripts/scan/xref.py), the imported wiki (../HD2WikiImporter/output/wiki_non_offensive_stratagems.json), Filediver Go
leads (scripts/scan/golib.py) and, when present, the four retained mission snapshots (read-only, a few KB each).
Output: research/sentry-components-F5FEE03DCFDB.json (scan report format, scripts/scan/report.py). Nothing is ever
written to the game; no field is promoted here (promotionProposal is a proposal for review).
"""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from scan import compare, golib, report, tables, xref  # noqa: E402
from scan.tables import decode, hexid  # noqa: E402

OUTPUT = ROOT / 'research/sentry-components-F5FEE03DCFDB.json'
WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_non_offensive_stratagems.json'
MISSION_SNAPSHOTS = ('F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap')
GAME_DLL_SHA256 = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'

# The ten sentry stratagems' deployed entities (research/defensive-stratagem-runtime-F5FEE03DCFDB.json) and the
# behaviour id each one's BehaviorComponent +0 names.
SENTRIES = {
    'MG43': ('A/MG-43 Machine Gun Sentry', 0x37CDE43876BA26BB, 312),
    'G16': ('A/G-16 Gatling Sentry', 0xEF85D6CF58E31D70, 213),
    'AC8': ('A/AC-8 Autocannon Sentry', 0x54D86057F5DACFB9, 5),
    'M12': ('A/M-12 Mortar Sentry', 0x51A0812E3BCE2D74, 319),
    'MLS4X': ('A/MLS-4X Rocket Sentry', 0x37079568DC86E9C6, 611),
    'TESLA': ('A/ARC-3 Tesla Tower', 0x74599E56F72F9D7E, 661),
    'M23': ('A/M-23 EMS Mortar Sentry', 0xB2053A1838092F8B, 323),
    'LAS98': ('A/LAS-98 Laser Sentry', 0x56070F36CFFFA8A8, 308),
    'FLAM40': ('A/FLAM-40 Flame Sentry', 0x820CC3BAFE962858, 207),
    'GM17': ('A/GM-17 Gas Mortar Sentry', 0x299C0D3DFD2F0994, 320),
}
TURRETED = [k for k in SENTRIES if k != 'TESLA']
# Sentries whose attack is a ProjectileWeapon shot: the path whose spread/recoil reads are pinned (0x615BAB, 0x784CAC).
PROJECTILE_SENTRIES = ['MG43', 'G16', 'AC8', 'M12', 'MLS4X', 'M23', 'GM17']
# Structural controls: same component kinds, different owners (resources resolved by exact path, or a fixed hash).
CONTROLS = {
    'HMG_EMPLACEMENT': 0x0E977C49DB7604F9, 'AT_EMPLACEMENT': 0x2B11C9E4980EC479, 'GL_BATTLEMENT': 0x0C8257D1C0255593,
    'PELICAN_CHIN': 'content/fac_helldivers/vehicles/shuttle_gunship/turrets/shuttle_gunship_turret_hmg',
    'POWERED_GATLING': 'content/fac_helldivers/hellpod/turret/power_generated_gatling_turret',
    'TUTORIAL_TURRET': 'content/fac_helldivers/hellpod/turret/tutorial_turret',
    'SEAF_GUN': 'content/objectives/obj_common/seaf_gun/seaf_gun',
    'SAM_SITE': 'content/objectives/obj_common/sam_site/sam_site',
    'CCTV': 'content/env_super_earth/military_base/utilities/cctv_camera',
    'CY_TURRET_BASE': 'content/fac_cyborgs/turrets/cyborg_turret_base',
    'CY_AUTOCANNONS': 'content/fac_cyborgs/turrets/cyborg_tank_turret_autocannons/cyborg_turret_autocannons',
    'CY_MORTAR': 'content/fac_cyborgs/turrets/cyborg_tank_turret_mortar/cyborg_turret_mortar',
    'CY_BUNKER_HMG': 'content/fac_cyborgs/turrets/cyborg_turret_command_bunker_hmg/cyborg_turret_command_bunker_hmg',
    'CY_SIEGE_ENGINE': 'content/fac_cyborgs/vehicles/cyborg_siege_engine/cyborg_siege_engine',
    'IL_TURRET': 'content/env_illuminate/gameplay/il_turret_01',
    'IL_WM_CANNON': 'content/fac_illuminate/vehicles/armaments/illuminate_turret_warmachine/illuminate_turret_wm_cannon',
    'LAV_AUTOCANNON': 'content/fac_helldivers/vehicles/lav/armaments/lav_autocannon/lav_autocannon',
    'GUARD_DOG_STUN': 'content/fac_helldivers/equipment/backpacks/guard_dog_stun_backpack/drone_stun',
    'ROVER': 'content/fac_helldivers/equipment/backpacks/drone_weapons/drone_laser_rifle/drone_laser_rifle',
}

# Layout guards: tables.fingerprint() of every component this research names a member of.
FINGERPRINTS = {
    'TurretComponentData': '2EFCE47D6E14A574A3A034D36B49A6B36111465D30834073CAAFFA4D84C33663',
    'SensorEyeComponentData': '8F8F0016BFB5359A454ACA08CF9A0D7EECF4BB9CBD629D377010588D5484B8ED',
    'SensorProximityComponentData': '2DD1FD1EEBB95D4EB3712CD10DF90CC450E3C5496FCB06BC13D28447B99A4DE0',
    'TargetingComponentData': '0DDFA544DE6DDB31AAD091AC0B66A8B35D11499AC0074AD9ECA984132B97485F',
    'DetectorComponentData': 'A6E08A893A422DCA4E63D82F2C551A8A17EBE59DD601BA7C23DCC1FDB6FF98F8',
    'WeaponDataComponentData': 'D159A1DB7550E5BBA5523462C403BE0514DD321C12524DEBC3037E91C175391E',
    'WeaponWindUpComponentData': '02B86BF48BBAD21DCE2575D4D4817CE5E0AC37E3E0146AC293BCDDCB4135E1BA',
    'HellpodPayloadComponentData': '5F7D6805C9E6E1C300836AA71B3A79BB71F5BF306EA4FF86F161289177F74E33',
    'BehaviorComponentData': 'EC7156BE35C71CF7BEDA2A9B78DCD03B5B804EF8C49D148E33C9A9D19F17CC35',
    'ProjectileWeaponComponentData': '3ED23773B461DF518C810B8F351D24BED2787357CBD011401875FA37AE149206',
    'WeaponMagazineComponentData': '6DE67C4DA641210912D1AF9B06ED08D2996140925ADFD55B6B60E9E0BF797333',
    'HealthComponentData': '1C5C3FFDC16B415C48170EED586A7CBCB54E04E61C35B1484BF1CD9FABC74A4A',
    'WeaponHeatComponentData': 'DF4002B36E3579A8409182FF69326EE2C585B041546724D63E849D4C64D946F8',
    'BeamWeaponComponentData': 'D64D63E3CBB53E023B3FA46677BFD8B784C8F2500C6AAA1EB30046B032753211',
}

# The component world (entity manager game+0x346BF98) type-table slots of the sentry components, found in a retained
# mission snapshot by matching each table's exact index bytes; every one is also the displacement of the native code
# that looks up a record by resource (pins below).
TYPE_TABLE_SLOTS = {'TurretComponentData': 0xF12C38, 'SensorEyeComponentData': 0xF12A70,
    'SensorProximityComponentData': 0xF12A90, 'TargetingComponentData': 0xF12BC8, 'WeaponDataComponentData': 0xF12BD8,
    'ProjectileWeaponComponentData': 0xF12E80, 'WeaponWindUpComponentData': 0xF126A8,
    'HellpodPayloadComponentData': 0xF12998, 'BehaviorComponentData': 0xF12D58, 'DetectorComponentData': 0xF12D48}

# Reviewed instruction pins (rva, exact instruction, role). Every run re-decodes them from the unpacked game.dll image.
PINS = {
    'turretSettings': ('The TurretComponentData settings resolver: the entity\'s own settings copy (turret manager '
        'game+0x3326D70, map +0x68, copies +0xA8, 0x4C bytes each) if one exists, else the shared type record found by '
        'resource in the type table (entity manager +0xF12C38, 146 slots, records +0x920, 0x4C each).', [
        (0x50B43F, 'mov r10, qword ptr [rax + 0xf12c38]', 'type lookup: the TurretComponentData type table'),
        (0x50B4B1, 'imul rax, rcx, 0x4c', '... record stride 0x4C (76 bytes = the type-library record size) ...'),
        (0x50B4B5, 'add rax, 0x920', '... records after the 146-slot index'),
        (0x50B8D2, 'mov r11, qword ptr [rip + 0x2e1b497]', 'resolver: the turret manager game+0x3326D70 ...'),
        (0x50B952, 'imul rax, rax, 0x4c', '... the entity\'s own settings copy (0x4C) ...'),
        (0x50B956, 'add rax, qword ptr [r11 + 0xa8]', '... in the manager\'s copies (+0xA8) ...'),
        (0x50B969, 'jmp 0x50b430', '... else the shared type record'),
        (0x6E247A, 'mov edx, 0x4c', 'the copy maker: allocates a 0x4C settings copy ...'),
        (0x6E249F, 'mov rax, qword ptr [rcx + 0xf12c38]', '... from the type record (no direct caller: virtual)'),
    ]),
    'turretSpawnCopy': ('Turret instance creation: the per-instance 16-byte record (manager +0x58) gets +0 active, '
        '+4 a speed factor (0x6DE820: ship-module modifiers, 1.0 by default), +8 = settings +12 (horizontal turn '
        'speed), +0xC = settings +8 (vertical turn speed); each is registered as a replicated network field.', [
        (0x542C89, 'call 0x6e06f0', 'the turret component\'s creation callback'),
        (0x6E0792, 'mov byte ptr [rcx + rbx*8], 1', 'instance +0: active'),
        (0x6E07C0, 'call 0x6de820', 'the speed factor ...'),
        (0x6E07C9, 'movss dword ptr [rax + rbx*8 + 4], xmm0', '... into instance +4'),
        (0x6E07FD, 'call 0x50b8b0', 'the settings ...'),
        (0x6E0806, 'mov eax, dword ptr [rax + 0xc]', '... +12 (horizontal turn speed) ...'),
        (0x6E0809, 'mov dword ptr [rcx + rbx*8 + 8], eax', '... copied into instance +8'),
        (0x6E081F, 'mov dword ptr [r15 + rax*8], 0xcc0b45e5', '... replicated (network key 0xCC0B45E5)'),
        (0x6E083B, 'call 0x50b8b0', 'the settings ...'),
        (0x6E0844, 'mov eax, dword ptr [rax + 8]', '... +8 (vertical turn speed) ...'),
        (0x6E0847, 'mov dword ptr [rcx + rbx*8 + 0xc], eax', '... copied into instance +0xC'),
        (0x6E085A, 'mov dword ptr [r15 + rax*8], 0x9d5d6cc7', '... replicated (network key 0x9D5D6CC7)'),
    ]),
    'turretUpdate': ('The turret system update (0x6DEDB0, called by the systems pass 0x5733F3) per turret: yaw then '
        'pitch toward the targeting direction; turn speeds from the instance copy, limits/exponent/events from the '
        'settings resolved every frame.', [
        (0x5733F3, 'call 0x6dedb0', 'the systems pass runs the turret update'),
        (0x6DEF01, 'add r15, qword ptr [r13 + 0x58]', 'r15: the instance record (16 bytes)'),
        (0x6DF46E, 'call 0x50b8b0', 'the settings, resolved every frame'),
        (0x6DF49B, 'movss xmm8, dword ptr [r15 + 8]', 'yaw: instance horizontal speed (0 = no yaw)'),
        (0x6DF4AD, 'movss xmm9, dword ptr [rax + 0x20]', 'yaw limit max: settings +32 ...'),
        (0x6DF4BE, 'movss xmm7, dword ptr [rax + 0x1c]', 'yaw limit min: settings +28 ...'),
        (0x6DF4D0, 'mulss xmm9, xmm6', '... degrees to radians'),
        (0x6DF4E5, 'comiss xmm0, dword ptr [rip + 0x1ce7ffc]', 'max-min >= 6.2821855 rad (359.94 deg) ...'),
        (0x6DF4F3, 'setae r12b', '... selects the wrapping (unlimited) yaw path'),
        (0x6DF58D, 'mulss xmm0, xmm14', '|yaw error| x 57.2958 ...'),
        (0x6DF592, 'mulss xmm0, xmm5', '... x 0.2: full speed only beyond 5 degrees of error (hard-coded)'),
        (0x6DF5AA, 'mulss xmm8, dword ptr [r15 + 4]', 'speed x the instance speed factor'),
        (0x6DF5B0, 'mulss xmm8, xmm6', '... degrees to radians'),
        (0x6DF698, 'movss dword ptr [rdi + 0x68], xmm6', 'the new yaw, clamped to the limits'),
        (0x6DF703, 'movss xmm1, dword ptr [rsi + 0x10]', 'settings +16 ...'),
        (0x6DF708, 'mulss xmm1, dword ptr [rip + 0x1ce88fc]', '... negated (x -1.0) ...'),
        (0x6DF713, 'call 0x2109e10', '... pow(|remaining yaw error in degrees|, -settings+16) ...'),
        (0x6DF732, 'minss xmm0, xmm1', '... clamped to [0, 1] ...'),
        (0x6DF736, 'movss dword ptr [rsp + 0x20], xmm0', '... the pitch factor'),
        (0x6DFBCA, 'movss xmm7, dword ptr [r15 + 0xc]', 'pitch: instance vertical speed (0 = no pitch)'),
        (0x6DFC39, 'mulss xmm7, dword ptr [r15 + 4]', '... x the instance speed factor ...'),
        (0x6DFC73, 'mulss xmm7, xmm6', '... x the pitch factor from settings +16'),
        (0x6DFC7F, 'movss xmm6, dword ptr [rsi + 0x14]', 'pitch limit min: settings +20 ...'),
        (0x6DFC91, 'movss xmm6, dword ptr [rsi + 0x18]', 'pitch limit max: settings +24 ...'),
        (0x6DFC9F, 'movss dword ptr [rdi + 0x64], xmm6', '... the new pitch, clamped'),
        (0x6DFE49, 'comiss xmm0, dword ptr [rsi + 0x24]', 'yaw event timer vs settings +36 (debounce)'),
        (0x6DFE69, 'mov ecx, dword ptr [rsi + 0x2c]', 'yaw start audio event: settings +44'),
        (0x6DFE7C, 'mov ecx, dword ptr [rsi + 0x30]', 'yaw stop audio event: settings +48'),
        (0x6DFEC0, 'mov edx, dword ptr [rsi + 0x34]', 'yaw start animation event: settings +52'),
        (0x6DFED3, 'mov edx, dword ptr [rsi + 0x38]', 'yaw stop animation event: settings +56'),
        (0x6DFF0F, 'comiss xmm0, dword ptr [rsi + 0x28]', 'pitch event timer vs settings +40 (debounce)'),
        (0x6DFF3B, 'mov ecx, dword ptr [rsi + 0x3c]', 'pitch start audio event: settings +60'),
        (0x6DFF75, 'mov ecx, dword ptr [rsi + 0x40]', 'pitch stop audio event: settings +64'),
    ]),
    'sensorEye': ('SensorEyeComponentData: copied into the sensor instance at spawn (manager game+0x3326520, '
        'records +0x58, 0x28 each); the vision test reads the instance.', [
        (0x50378F, 'mov r10, qword ptr [rax + 0xf12a70]', 'type lookup: the SensorEye type table'),
        (0x503801, 'imul rax, rcx, 0x2c', '... record stride 0x2C (44)'),
        (0x64C554, 'call 0x503bc0', 'sensor creation: the settings ...'),
        (0x64C563, 'mov edx, dword ptr [rax + 0x14]', '... +20 the sensor node name'),
        (0x64C61A, 'movss xmm1, dword ptr [rbp + 0xc]', '... +12 ...'),
        (0x64C61F, 'mulss xmm1, dword ptr [rip + 0x1d7a039]', '... degrees to radians ...'),
        (0x64C627, 'movss dword ptr [r14 + rbx*8 + 0x18], xmm1', '... instance +0x18 (cone half-angle, horizontal)'),
        (0x64C62E, 'movss xmm0, dword ptr [rbp + 0x10]', '... +16 ...'),
        (0x64C63B, 'movss dword ptr [r14 + rbx*8 + 0x1c], xmm0', '... instance +0x1C (cone half-angle, vertical)'),
        (0x64C642, 'mov eax, dword ptr [rbp + 0x20]', '... +32 the sensor shape type ...'),
        (0x64C645, 'mov dword ptr [r14 + rbx*8 + 0x24], eax', '... instance +0x24'),
        (0x64C675, 'jmp 0x64c3c0', 'then the ranges:'),
        (0x64C468, 'mulss xmm0, dword ptr [rax]', '+0 range x the instance scale ...'),
        (0x64C46C, 'movss dword ptr [rdi + rbx*8 + 0xc], xmm0', '... instance +0xC (front range)'),
        (0x64C472, 'movss xmm1, dword ptr [rax + 4]', '+4 (negative: the front range) ...'),
        (0x64C483, 'movss dword ptr [rdi + rbx*8 + 0x10], xmm1', '... instance +0x10 (side range)'),
        (0x64C489, 'movss xmm3, dword ptr [rax + 8]', '+8 (negative: the front range) ...'),
        (0x64C4A0, 'movss dword ptr [rdi + rbx*8 + 0x14], xmm0', '... instance +0x14 (rear range)'),
        (0x64C991, 'mov ecx, dword ptr [r14 + rbp*8 + 0x24]', 'vision test: by shape type (1, 2, 3)'),
        (0x64CBC0, 'movss xmm0, dword ptr [r14 + rbp*8 + 0x18]', 'type 2 only: |horizontal angle| < +0x18 ...'),
        (0x64CBF2, 'movss xmm0, dword ptr [r14 + rbp*8 + 0x1c]', '... and |vertical angle| < +0x1C'),
        (0x64CDB1, 'movss xmm0, dword ptr [r14 + rbp*8 + 0xc]', 'type 1: in front (dot > 0) the front range ...'),
        (0x64CDBA, 'movss xmm0, dword ptr [r14 + rbp*8 + 0x14]', '... behind the rear range ...'),
        (0x64CDCD, 'subss xmm6, xmm7', '... (1 - |cos|) ...'),
        (0x64CDD7, 'mulss xmm7, xmm0', '... |cos| x front-or-rear ...'),
        (0x64CDDD, 'mulss xmm6, dword ptr [r14 + rbp*8 + 0x10]', '... + (1 - |cos|) x side range'),
    ]),
    'sensorProximity': ('SensorProximityComponentData +0: the perception update marks every candidate within this '
        'radius of the sensor as perceived (sense bit), with no line-of-sight ray on this path.', [
        (0x64FE43, 'mov r10, qword ptr [rcx + 0xf12a90]', 'type lookup: the SensorProximity type table (8 slots)'),
        (0x64FE89, 'add rdi, 0x20', '... records after the index (record index x 4) ...'),
        (0x64FEB4, 'movss xmm1, dword ptr [rdi]', '... +0 the radius ...'),
        (0x64FEC8, 'mulss xmm1, xmm1', '... squared ...'),
        (0x64FED0, 'comiss xmm1, xmm3', '... against the squared distance to the candidate'),
        (0x886BAE, 'call 0x64fd20', 'the proximity sensor handler, per perceiver sensor'),
        (0x886BFD, 'or dword ptr [rdi + 0x4c], eax', 'within: the perception entry\'s sense bit is set'),
        (0x886C17, 'and dword ptr [rdi + 0x4c], eax', 'outside: the bit is cleared'),
        (0x887BE2, 'call 0x886a70', 'the perception update dispatches proximity sensors'),
    ]),
    'targeting': ('TargetingComponentData: the targeting update (0x6BBDC0, manager game+0x3326D30) looks the record '
        'up by resource every frame (590 slots, records +0x24E0, 0x40 each).', [
        (0x5731FA, 'call 0x6bbdc0', 'the systems pass runs the targeting update'),
        (0x6BC4F4, 'mov r10, qword ptr [rax + 0xf12bc8]', 'type lookup: the Targeting type table'),
        (0x6BC597, 'lea rcx, [r10 + 0x24e0]', '... records +0x24E0 ...'),
        (0x6BC5A3, 'shl rax, 6', '... 0x40 each'),
        (0x6BC9B1, 'mov edx, dword ptr [rcx + 0x1c]', '+28: the aim node name'),
        (0x6BCF33, 'cmp byte ptr [rdi + 0x19], 0', '+25 set (the mortars): skips the aim-node/lead section'),
        (0x6BD7C1, 'movss xmm10, dword ptr [rdi + 0x14]', '+20: angle (deg) below which the aim is smoothed'),
        (0x6BDA3F, 'movss xmm13, dword ptr [rdi + 0xc]', '+12: the aim spring stiffness ...'),
        (0x6BDCCD, 'movss xmm2, dword ptr [rdi + 8]', '+8: the aim spring damping ...'),
        (0x6BDCFC, 'mulss xmm6, xmm13', '... error x stiffness ...'),
        (0x6BDD06, 'subss xmm6, xmm0', '... - angular velocity x damping ...'),
        (0x6BDD0E, 'mulss xmm6, xmm7', '... x dt ...'),
        (0x6BDD2D, 'movss dword ptr [r14 + r13 + 0x70], xmm6', '... the new angular velocity (yaw)'),
        (0x6BDC9F, 'mulss xmm0, dword ptr [rdi + 0x28]', '+40: decay rate of an aim offset weight'),
        (0x6BDEA9, 'mulss xmm6, dword ptr [rdi + 0x10]', '+16: the aim angular speed cap (deg/s)'),
    ]),
    'weaponData': ('WeaponDataComponentData: the instance record is built once, at creation (0x752370), from the '
        'type: the two recoil blocks (type +0 drift, +28 climb) times the instance multipliers, the spread (type '
        '+84/+88) times the instance multipliers; every shot then reads the instance (Pelican research, pinned again).', [
        (0x54026D, 'jmp 0x752370', 'WeaponData\'s post-create callback builds the instance'),
        (0x7525AB, 'movups xmm0, xmmword ptr [r15]', 'type +0 (recoil drift block) ...'),
        (0x7525BF, 'movups xmmword ptr [rbp + 0x1c], xmm0', '... into instance +0x1C (block A)'),
        (0x7525CC, 'movups xmm0, xmmword ptr [r15 + 0x20]', 'type +0x20.. (climb block: +28 horizontal, +32 '
            'vertical) ...'),
        (0x7525D1, 'movups xmmword ptr [rbp + 0x3c], xmm0', '... the 60-byte copy: type +N lands at instance +0x1C+N'),
        (0x75260A, 'mulss xmm1, dword ptr [rbp + 0x1c]', 'drift horizontal x the instance multiplier ...'),
        (0x752629, 'mulss xmm3, dword ptr [rbp + 0x38]', 'climb horizontal x the instance multiplier ...'),
        (0x75263D, 'movsd xmm0, qword ptr [r15 + 0x54]', 'type +84/+88 (spread) ...'),
        (0x752643, 'movsd qword ptr [rbp + 0x58], xmm0', '... into instance +0x58 ...'),
        (0x752621, 'movss xmm1, dword ptr [rbp + 0x3e0]', '... x the instance multipliers (+0x3E0 ...'),
        (0x75264C, 'movss xmm0, dword ptr [rbp + 0x3e8]', '... +0x3E8)'),
        (0x615BAB, 'lea r9, [rdi + 0x58]', 'each shot: the instance spread ...'),
        (0x615BBA, 'call 0x759740', '... turns the shot by up to half of it each way (milliradians)'),
        (0x784CAC, 'lea rdx, [rdi + 0x1c]', 'each shot: recoil block A ...'),
        (0x784CCF, 'lea rdx, [rdi + 0x38]', '... and block B ...'),
        (0x784CE2, 'lea r8, [rbx + 0x14]', '... kick the wielder\'s aim (a turret wields itself)'),
    ]),
    'windUp': ('WeaponWindUpComponentData: the wind-up routine (0x78A420) advances the spin progress by dt / '
        'settings +0 while the trigger is held; on release settings +4 <= 0 resets it at once, any positive +4 lets it '
        'fall by dt / settings +0 (0x78A52C: the wind-up time, not +4).', [
        (0x78A492, 'call 0x4f8090', 'the settings (resolver; the type record unless a copy exists)'),
        (0x78A4D4, 'movss xmm1, dword ptr [rbp]', '+0 wind-up time ...'),
        (0x78A4EC, 'divss xmm0, xmm1', '... progress += dt / wind-up time'),
        (0x78A519, 'comiss xmm7, dword ptr [rbp + 4]', 'released: +4 wind-down time <= 0 -> progress 0'),
        (0x78A52C, 'divss xmm0, dword ptr [rbp]', 'released, +4 > 0: progress -= dt / +0 (the wind-up time)'),
        (0x78A679, 'mulss xmm3, dword ptr [rbp + 0xc]', '+12: the barrel-spin RPM multiplier'),
    ]),
    'behaviour': ('Behaviour (AI) dispatch: BehaviorComponent +0 (the behaviour id) selects compiled code; the '
        'engagement constants below are immediates/rodata of that code, not component data.', [
        (0x472FAC, 'mov eax, dword ptr [r8 + rax*4 + 0x4795c4]', 'the behaviour jump table (id - 1)'),
        (0x47523E, 'mov ecx, dword ptr [r8 + rax*4 + 0x47a1a4]', '213 (G-16): its stage table'),
        (0x476380, 'mov ecx, dword ptr [r8 + rax*4 + 0x47a208]', '312 (MG-43): its stage table'),
        (0x473157, 'mov ecx, dword ptr [r8 + rax*4 + 0x47a098]', '5 (AC-8): its stage table'),
        (0x284B5B, 'mov qword ptr [rbp + 0x18], 0x42c80000', 'G-16 target score: distance curve ends (100 m, 0)'),
        (0x284BE5, 'comiss xmm1, dword ptr [rip + 0x2142c04]', '... beyond 100 m: the floor score'),
        (0x283DE4, 'movss xmm2, dword ptr [rip + 0x2143494]', 'G-16 stage 5 fires only within 3.0 degrees'),
        (0x285739, 'add rdx, 0xf4240', 'G-16 stage 12: 1 s (target-lost exit)'),
        (0x33096B, 'mov qword ptr [rbp + 0x18], 0x42c80000', 'MG-43: distance curve ends at 100 m'),
        (0x32FC17, 'movss xmm2, dword ptr [rip + 0x2097661]', 'MG-43: fire cone 3.0 degrees'),
        (0xC0308, 'mov qword ptr [rbp + 0x38], 0x42c80000', 'AC-8: distance curve ends at 100 m'),
        (0xC0758, 'movss xmm2, dword ptr [rip + 0x23069b0]', 'AC-8: fire cone 2.0 degrees'),
        (0x277DAD, 'mov qword ptr [rbp + 0x18], 0x42480000', 'FLAM-40: distance curve ends at 50 m'),
        (0x276EC6, 'movss xmm2, dword ptr [rip + 0x2150686]', 'FLAM-40: fire cone 10.0 degrees'),
        (0x326C4E, 'mov qword ptr [rbp - 0x20], 0x42c80000', 'LAS-98: distance curve ends at 100 m'),
        (0x329A4C, 'movss xmm2, dword ptr [rip + 0x209db00]', 'LAS-98: fire cone 10.0 degrees'),
        (0x339ED7, 'mov edx, dword ptr [rcx + rax*4 + 0x33a188]', 'M-12 (319): its stage switch'),
    ]),
}
POW, ANGLE_APPROACH = 0x2109E10, 0x173C620
# Per-behaviour engagement constants re-derived from code every run (see behaviour_constants()).
BEHAVIOUR_STAGE_TABLES = {'MG43': 0x47A208, 'G16': 0x47A1A4, 'AC8': 0x47A098, 'FLAM40': 0x47A174, 'LAS98': 0x47A1D4}
BARREL_CHECK = 0x4B54D0
EXPECTED_DIRECT_FIRE = {   # distance score curve points (m, score) and the stage-5 fire cone (degrees)
    'MG43': ((5.0, 1.0), (40.0, 0.8), (100.0, 0.0), 3.0), 'G16': ((5.0, 1.0), (40.0, 0.8), (100.0, 0.0), 3.0),
    'AC8': ((5.0, 1.0), (40.0, 0.8), (100.0, 0.0), 2.0), 'FLAM40': ((5.0, 1.0), (25.0, 0.8), (50.0, 0.0), 10.0),
    'LAS98': ((5.0, 1.0), (80.0, 0.8), (100.0, 0.0), 10.0)}
MORTAR_SWITCHES = {'M12': 0x339EA0, 'GM17': 0x340910, 'M23': 0x3511A0}
EXPECTED_MORTAR_CURVES = {   # (x0, y0, x1, y1) four-float curve segments loaded by the stage-2 (search) function
    'M12': {(75.0, 1.0, 125.0, 0.0), (25.0, 0.0, 26.0, 0.9), (50.0, 1.0, 51.0, 0.0), (0.0, 1.0, 45.0, 1.0)},
    'GM17': {(75.0, 1.0, 125.0, 0.0), (14.0, 0.0, 15.0, 0.9), (40.0, 1.0, 70.0, 0.0), (0.0, 1.0, 45.0, 0.9),
        (0.0, 1.0, 1.0, 0.0)},
    'M23': {(75.0, 1.0, 125.0, 0.0), (14.0, 0.0, 15.0, 0.9), (40.0, 1.0, 70.0, 0.0), (0.0, 1.0, 45.0, 0.9)}}

# Live-proven fields (docs/live-evidence.md, 2026-09-29): SentryTurnSpeed (AC-8 yaw/pitch speed) and
# SentryDetectionRange (MG-43 targeting range).
LIVE = {('TurretComponentData', 8), ('TurretComponentData', 12), ('SensorEyeComponentData', 0)}


def r6(value):
    return round(value, 6) if isinstance(value, float) else value


# -- inputs ------------------------------------------------------------------------------------------------------
def resolve_controls(t) -> dict:
    out = {}
    for label, ref in CONTROLS.items():
        if isinstance(ref, int):
            resource = ref
        else:
            found = [r for r in t.find('^' + re.escape(ref) + '$')]
            if len(found) != 1:
                raise ValueError('control %s resolves to %d entities' % (label, len(found)))
            resource = found[0]
        if resource not in t.entity_rows():
            raise ValueError('control %s absent' % label)
        out[label] = resource
    return out


def check_fingerprints(t) -> dict:
    for component, expected in FINGERPRINTS.items():
        got = t.fingerprint(component)
        if got != expected:
            raise ValueError('%s layout fingerprint changed: %s' % (component, got))
    return dict(FINGERPRINTS)


def wiki_rows() -> dict:
    """Per sentry: the detailed weapon-statistics rows the native members are compared with."""
    if not WIKI.is_file():
        return {}
    data = json.loads(WIKI.read_text(encoding='utf-8'))
    out = {}
    names = {v[0]: k for k, v in SENTRIES.items()}
    for item in data['stratagems']:
        label = names.get(item['name'])
        if not label:
            continue
        rows = {}
        for field in item.get('rawStructuredFields') or []:
            section = field.get('section') or ''
            if not section.startswith('Detailed Weapon Statistics'):
                continue
            part = section.split(' > ')[-1]
            kind = 'weapon' if part == 'Weapon' else 'swp' if part.startswith('SWP ') else 'heat' \
                if part == 'Heat Data' else None
            if kind:
                rows[(kind, field['label'])] = field['raw']
        out[label] = rows
    return out


# Reviewed wiki sentences stating a sentry's targeting range (scripts/research_defensive_stratagem_authoring.py).
RANGE_STATEMENTS = {
    'MG43': ('Like most direct fire sentries, the MG-43 Sentry has a range of 75m', 75.0),
    'G16': ('The Gatling Sentry has a range of 75m', 75.0),
    'AC8': ('The Autocannon Sentry has a maximum range of 100m', 100.0),
    'MLS4X': ('with a 100m engagement distance', 100.0),
    'M23': ('The EMS mortar has a range of 125 meters', 125.0),
    'LAS98': ('The Laser Sentry has a targeting range of 50m', 50.0),
    'GM17': ('potential maximum targeting range of 125-meters', 125.0),
}


def wiki_statements() -> dict:
    """label -> (sentence, value) for every reviewed range sentence still present verbatim on its page."""
    if not WIKI.is_file():
        return {}
    data = json.loads(WIKI.read_text(encoding='utf-8'))
    names = {v[0]: k for k, v in SENTRIES.items()}
    out = {}
    for item in data['stratagems']:
        label = names.get(item['name'])
        if label in RANGE_STATEMENTS:
            text = ' '.join((section.get('text') or '') for section in item.get('rawSections') or [])
            sentence, stated = RANGE_STATEMENTS[label]
            if sentence not in text:
                raise ValueError('reviewed range sentence no longer on the wiki page: ' + label)
            out[label] = {'sentence': sentence, 'value': stated}
    return out


def number(text):
    found = re.findall(r'-?\d+(?:\.\d+)?', text or '')
    return float(found[0]) if found else None


def wiki_values(rows: dict) -> dict:
    get = lambda kind, label: rows.get((kind, label))
    result = {}
    for key, kind, label in (('horizontalTurnSpeed', 'weapon', 'Horizontal Turn Speed'),
            ('verticalTurnSpeed', 'weapon', 'Vertical Turn Speed'), ('lifetime', 'weapon', 'Lifetime'),
            ('mainHealth', 'weapon', 'Main Health'), ('fireRate', 'swp', 'Fire Rate'), ('recoil', 'swp', 'Recoil'),
            ('horizontalRecoil', 'swp', 'Horizontal Recoil'), ('verticalRecoil', 'swp', 'Vertical Recoil'),
            ('sway', 'swp', 'Sway'), ('ergonomics', 'swp', 'Ergonomics'), ('capacity', 'swp', 'Capacity'),
            ('beamFireRate', 'heat', 'Beam Fire Rate'), ('overheatsAt', 'heat', 'Overheats at'),
            ('heatPerSecond', 'heat', 'Heat Per Second')):
        value = get(kind, label)
        if value is not None and number(value) is not None:
            result[key] = number(value)
    limit = get('weapon', 'Vertical Limit')
    if limit:
        result['verticalLimit'] = [float(v) for v in re.findall(r'\((-?[\d.]+)\)', limit)]
    spread = get('swp', 'Spread')
    if spread:
        values = [float(v) for v in re.findall(r'\[(-?[\d.]+)\]', spread)]
        if len(values) == 2:
            result['spread'] = values
    cool = get('heat', 'Cool Per Sec')
    if cool:
        result['coolPerSecond'] = [float(v) for v in re.findall(r'[\d.]+', cool)]
    return result


# -- native values -----------------------------------------------------------------------------------------------
def value(t, component: str, resource: int, path_or_offset):
    table = t.component(component)
    record = table.record_of(resource)
    if record is None:
        return None
    member = table.member(path_or_offset)
    return r6(decode(member, table.raw(record)))


def ownership(t, component: str, resource: int) -> dict | None:
    table = t.component(component)
    record = table.record_of(resource)
    if record is None:
        return None
    owners = table.owners(record)
    return {'record': record, 'owners': len(owners), 'unique': len(owners) == 1,
        'coOwners': [t.label(o) for o in owners if o != resource][:8]}


def wiki_checks(t, wiki: dict) -> dict:
    """Native members against the wiki's detailed tables, per sentry (exact float equality)."""
    out = {}
    statements = wiki_statements()
    for label, (name, resource, _) in SENTRIES.items():
        w = wiki.get(label) or {}
        checks = {}

        def check(key, native, published):
            if published is None or native is None:
                return
            if isinstance(published, list):
                exact = isinstance(native, list) and len(native) == len(published) and all(
                    abs(a - b) <= 1e-4 for a, b in zip(native, published))
            else:
                exact = abs(native - published) <= 1e-4
            checks[key] = {'native': native, 'wiki': published, 'exact': exact}
        stated = (statements.get(label) or {}).get('value')
        check('targeting.range', value(t, 'SensorEyeComponentData', resource, 0), stated)
        proximity = value(t, 'SensorProximityComponentData', resource, 0)
        if proximity is not None and stated is not None:
            # The same sentence equals SensorProximity +0 on the mortars: recorded, but it does not tell the two apart.
            checks['targeting.proximity_range (ambiguous with targeting.range)'] = {'native': proximity,
                'wiki': stated, 'exact': abs(proximity - stated) <= 1e-4, 'ambiguous': True}
        check('turret.yaw_speed', value(t, 'TurretComponentData', resource, 12), w.get('horizontalTurnSpeed'))
        check('turret.pitch_speed', value(t, 'TurretComponentData', resource, 8), w.get('verticalTurnSpeed'))
        if value(t, 'TurretComponentData', resource, 20) is not None:
            check('turret.pitch_min/max', [value(t, 'TurretComponentData', resource, 20),
                value(t, 'TurretComponentData', resource, 24)], w.get('verticalLimit'))
        check('payload.lifetime', value(t, 'HellpodPayloadComponentData', resource, 4), w.get('lifetime'))
        check('entity.health', value(t, 'HealthComponentData', resource, 0), w.get('mainHealth'))
        if 'spread' in w:
            check('weapon.horizontal_spread/vertical_spread', [value(t, 'WeaponDataComponentData', resource, '84.0'),
                value(t, 'WeaponDataComponentData', resource, '84.4')], w['spread'])
        drift_h, drift_v = value(t, 'WeaponDataComponentData', resource, '0.0.0'), value(
            t, 'WeaponDataComponentData', resource, '0.0.4')
        climb_h, climb_v = value(t, 'WeaponDataComponentData', resource, '0.28.0'), value(
            t, 'WeaponDataComponentData', resource, '0.28.4')
        if None not in (drift_h, drift_v, climb_h, climb_v):
            # The player/support weapon mapping (schemas/player_weapon_fields.json): the published horizontal and
            # vertical recoil are the means of drift and climb, and the published recoil is their mean.
            horizontal, vertical = (drift_h + climb_h) / 2, (drift_v + climb_v) / 2
            check('weapon.horizontal_recoil (mean of drift/climb)', r6(horizontal), w.get('horizontalRecoil'))
            check('weapon.vertical_recoil (mean of drift/climb)', r6(vertical), w.get('verticalRecoil'))
            check('weapon.recoil (mean)', r6((horizontal + vertical) / 2), w.get('recoil'))
        check('weapon.sway', value(t, 'WeaponDataComponentData', resource, 104), w.get('sway'))
        check('weapon.ergonomics', value(t, 'WeaponDataComponentData', resource, 356), w.get('ergonomics'))
        rpm = value(t, 'ProjectileWeaponComponentData', resource, 4)     # rounds_per_minute (x, y, z): y = default
        if rpm is not None and 'fireRate' in w:
            check('weapon.fire_rate (rate slot Y)', r6(rpm[1]), w['fireRate'])
        check('magazine.capacity', value(t, 'WeaponMagazineComponentData', resource, 136), w.get('capacity'))
        check('beam.fire_rate', value(t, 'BeamWeaponComponentData', resource, 104), w.get('beamFireRate'))
        check('heat.capacity', value(t, 'WeaponHeatComponentData', resource, 96), w.get('overheatsAt'))
        check('heat.heat_per_second', value(t, 'WeaponHeatComponentData', resource, 120), w.get('heatPerSecond'))
        out[label] = checks
    return out


def member_catalogue(t, component: str, controls: dict, paths=None) -> dict:
    """Every member: layout, hidden-name length, per-sentry values, control values and the distinct values over all
    owners of the table (the family differential)."""
    table = t.component(component)
    owners = table.owner_map()
    sentry_records = {k: table.record_of(v[1]) for k, v in SENTRIES.items()}
    control_records = {k: table.record_of(v) for k, v in controls.items()}
    rows = []
    for member in table.members():
        if paths is not None and member.path not in paths:
            continue
        everywhere = Counter()
        for record in range(table.count):
            everywhere[json.dumps(r6(decode(member, table.raw(record))))] += len(owners.get(record, []))
        rows.append({'path': member.path, 'offset': member.offset, 'size': member.size, 'storage': member.storage,
            'atom': member.atom, 'nameLength': member.name_length, 'type': member.type_name,
            'sentries': {k: r6(decode(member, table.raw(r))) for k, r in sentry_records.items() if r is not None},
            'controls': {k: r6(decode(member, table.raw(r))) for k, r in control_records.items() if r is not None},
            'distinctOverAllOwners': len(everywhere),
            'commonValues': [[json.loads(k), n] for k, n in everywhere.most_common(6)]})
    return {'component': component, 'recordType': table.record_type, 'recordSize': table.record_size,
        'records': table.count, 'layoutFingerprint': t.fingerprint(component),
        'typeTableSlot': TYPE_TABLE_SLOTS.get(component), 'members': rows}


# -- code ---------------------------------------------------------------------------------------------------------
def verify_pins(image) -> dict:
    out = {}
    for group, (summary, rows) in PINS.items():
        out[group] = {'summary': summary, 'pins': [image.pin(rva, role, asm) for rva, asm, role in rows]}
    return out


def float_bits(value: int) -> float:
    return struct.unpack('<f', struct.pack('<I', value & 0xFFFFFFFF))[0]


def curve_points(image, function: int):
    """(head four floats, tail pair) of every piecewise curve a function builds on its stack: movaps xmm0 of a
    16-byte rodata constant, then (optionally) a mov qword [rbp+x], imm64 holding the last point."""
    from capstone import x86
    insns = image.function_insns(function)
    out = []
    for n, ins in enumerate(insns):
        if ins.mnemonic == 'movaps' and 'xmmword ptr [rip' in ins.op_str:
            target = image.rip_target(ins)
            head = tuple(round(v, 4) for v in struct.unpack_from('<4f', image.data, target))
            tail = None
            for nxt in insns[n + 1:n + 5]:
                if nxt.mnemonic == 'mov' and nxt.operands and nxt.operands[0].type == x86.X86_OP_MEM and \
                        len(nxt.operands) == 2 and nxt.operands[1].type == x86.X86_OP_IMM and nxt.operands[1].size == 8:
                    imm = nxt.operands[1].imm & 0xFFFFFFFFFFFFFFFF
                    tail = (round(float_bits(imm), 4), round(float_bits(imm >> 32), 4))
                    break
            out.append({'rva': ins.address, 'head': head, 'tail': tail})
    return out


def fire_cone(image, function: int):
    """The rodata float a stage passes (xmm2) to the barrel-angle check 0x4B54D0."""
    insns = image.function_insns(function)
    for n, ins in enumerate(insns):
        if ins.mnemonic == 'call' and ins.op_str == hex(BARREL_CHECK):
            for prev in reversed(insns[max(0, n - 16):n]):
                if prev.mnemonic == 'movss' and prev.op_str.startswith('xmm2, dword ptr [rip'):
                    return {'callRva': ins.address, 'degrees': round(image.f32(image.rip_target(prev)), 4)}
    return None


def behaviour_constants(image) -> dict:
    """Engagement constants compiled into the sentry behaviours (not data). Direct-fire template: stage 2 (search)
    scores candidates with a piecewise distance curve, stage 5 (aim) fires only within a cone; mortars: their
    search stage's curve segments."""
    direct = {}
    for label, table in BEHAVIOUR_STAGE_TABLES.items():
        stages = {}
        for stage in range(12):
            entry = image.u32(table + 4 * stage)
            calls = [i.operands[0].imm for i in image.disasm(entry, entry + 0x40)[:10]
                if i.mnemonic == 'call' and i.operands and i.operands[0].type == 2]
            stages[stage + 1] = calls[0] if calls else None
        search, aim = stages[2], stages[5]
        curves = [c for c in curve_points(image, search) if c['tail']]
        if not curves:
            raise ValueError('%s: no distance curve in the search stage' % label)
        head, tail = curves[0]['head'], curves[0]['tail']
        points = ((head[0], head[1]), (head[2], head[3]), tail)
        cone = fire_cone(image, aim)
        expected = EXPECTED_DIRECT_FIRE[label]
        if tuple((round(a, 4), round(b, 4)) for a, b in points) != tuple((round(a, 4), round(b, 4)) for a, b in
                expected[:3]) or not cone or abs(cone['degrees'] - expected[3]) > 1e-4:
            raise ValueError('%s behaviour constants changed: %r %r' % (label, points, cone))
        direct[label] = {'behaviour': SENTRIES[label][2], 'stageTable': table,
            'stageFunctions': {str(k): v for k, v in stages.items() if v},
            'distanceScoreCurve': {'points': [list(p) for p in points], 'rva': curves[0]['rva'],
                'meaning': 'score falls linearly between the points; at or beyond the last distance the candidate '
                    'gets the floor score (0), so it is never picked'},
            'fireConeDegrees': cone['degrees'], 'fireConeCheckRva': cone['callRva']}
    mortars = {}
    for label, switch in MORTAR_SWITCHES.items():
        insns = image.disasm(switch, switch + 0x60)
        table = next(i.operands[1].mem.disp for i in insns if i.mnemonic == 'mov' and '*4 +' in i.op_str)
        entry = image.u32(table + 4)          # stage 2
        calls = [i.operands[0].imm for i in image.disasm(entry, entry + 0x40)[:10]
            if i.mnemonic == 'call' and i.operands and i.operands[0].type == 2]
        segments = {tuple(round(v, 1) for v in c['head']) for c in curve_points(image, calls[0])}
        if segments != {tuple(round(v, 1) for v in s) for s in EXPECTED_MORTAR_CURVES[label]}:
            raise ValueError('%s mortar curves changed: %r' % (label, segments))
        mortars[label] = {'behaviour': SENTRIES[label][2], 'stageSwitch': switch, 'searchFunction': calls[0],
            'curveSegments': sorted([list(s) for s in segments]),
            'reading': 'score 0 below the step (25 m M-12; 14 m EMS/Gas) and falling to 0 at 125 m: a hard-coded '
                'minimum and maximum engagement distance (the role of the middle segment is not established)'}
    return {'directFire': direct, 'mortars': mortars,
        'notData': 'Every value here is an immediate or rodata constant of the behaviour\'s own code; no component '
            'member feeds it, so no data write can change it.'}


# -- snapshots ------------------------------------------------------------------------------------------------------
def snapshot_evidence(t) -> dict:
    """Per-instance copies in the retained mission snapshots: turret instance speeds equal their type's (+12, +8),
    sensor instance ranges equal their type's +0 x the instance scale. No player sentry was deployed in any of them."""
    directory = build_profile.snapshot_directory()
    if not all((directory / name).is_file() for name in MISSION_SNAPSHOTS):
        return {'state': 'snapshots_absent'}
    import research_event_state as base
    turret, eye = t.component('TurretComponentData'), t.component('SensorEyeComponentData')
    sentry_resources = {v[1] for v in SENTRIES.values()}
    out = {'state': 'read', 'snapshots': {}}
    for name in MISSION_SNAPSHOTS:
        m = base.Mem(name)
        try:
            entry = {}
            mgr = m.ptr(m.game + 0x3326D70)
            count = m.u32(mgr + 0x18) if mgr else 0
            handles, records = (m.ptr(mgr + 0x40), m.ptr(mgr + 0x58)) if mgr else (None, None)
            turrets = []
            for i in range(count or 0):
                handle = m.ptr(handles + 8 * i)
                resource = m.u64(handle)
                active, factor, yaw, pitch = struct.unpack('<B3x3f', m.read(records + 16 * i, 16))
                record = turret.record_of(resource)
                type_yaw = r6(decode(turret.member(12), turret.raw(record))) if record is not None else None
                type_pitch = r6(decode(turret.member(8), turret.raw(record))) if record is not None else None
                turrets.append({'entity': t.label(resource), 'active': active, 'speedFactor': r6(factor),
                    'instanceYawSpeed': r6(yaw), 'instancePitchSpeed': r6(pitch), 'typeYawSpeed': type_yaw,
                    'typePitchSpeed': type_pitch, 'copyMatchesType': (r6(yaw), r6(pitch)) == (type_yaw, type_pitch),
                    'sentry': resource in sentry_resources})
            entry['turrets'] = turrets
            entry['turretSettingsCopies'] = m.u32(mgr + 0xA0) if mgr else None
            emgr = m.ptr(m.game + 0x3326520)
            matched = total = 0
            if emgr:
                ehandles, erecords = m.ptr(emgr + 0x48), m.ptr(emgr + 0x58)
                for i in range(m.u32(emgr + 0x18) or 0):
                    handle = m.ptr(ehandles + 8 * i)
                    if not handle:
                        break
                    record = eye.record_of(m.u64(handle))
                    if record is None:
                        continue
                    data = m.read(erecords + 0x28 * i, 0x28)
                    total += 1
                    scale = struct.unpack_from('<f', data, 0x20)[0]
                    matched += abs(struct.unpack_from('<f', data, 0xC)[0] -
                        decode(eye.member(0), eye.raw(record)) * scale) < 1e-3
            entry['sensorEyeInstances'] = {'instances': total, 'rangeEqualsTypeTimesScale': matched}
            out['snapshots'][name] = entry
        finally:
            m.close()
    out['sentryInstancesPresent'] = any(x['sentry'] for s in out['snapshots'].values() for x in s['turrets'])
    return out


# -- candidates ------------------------------------------------------------------------------------------------------
def sentry_values(t, component, path):
    return {k: value(t, component, v[1], path) for k, v in SENTRIES.items()
        if t.component(component).record_of(v[1]) is not None}


def differential(t, component, path) -> bool:
    table = t.component(component)
    member = table.member(path)
    return len({json.dumps(r6(decode(member, table.raw(r)))) for r in range(table.count)}) > 1


# (component, path, native-name candidate fitting the hidden-name length or None, semantic id or None, code group or
#  None, published check key or None, role, lifecycle, promote?)
SPECS = [
    ('TurretComponentData', 12, 'horizontal_turn_speed', 'turret.yaw_speed', 'turretSpawnCopy', 'turret.yaw_speed',
     'horizontal (yaw) turn speed, degrees per second', 'copied into the turret instance at spawn (x the speed factor, '
     'replicated); later type writes do not reach deployed sentries', 'existing'),
    ('TurretComponentData', 8, 'vertical_turn_speed', 'turret.pitch_speed', 'turretSpawnCopy', 'turret.pitch_speed',
     'vertical (pitch) turn speed, degrees per second', 'copied into the turret instance at spawn (x the speed factor, '
     'replicated)', 'existing'),
    ('TurretComponentData', 16, 'pitch_exponent', 'turret.pitch_yaw_coupling', 'turretUpdate', None,
     'pitch speed factor exponent: each frame pitch speed x min(1, |remaining yaw error, degrees| ^ -value) (only '
     'when the error exceeds 0.01 deg); 1 on direct-fire sentries, 4 on the mortars (barrel waits for traverse), 0 on '
     'enemy turrets (independent axes)', 'read from the type record every frame (no instance copy exists unless '
     'created): immediate on deployed sentries', 'propose'),
    ('TurretComponentData', 20, 'vertical_limit_min', 'turret.pitch_min', 'turretUpdate', 'turret.pitch_min/max',
     'lowest pitch, degrees (clamp)', 'read every frame: immediate', 'existing'),
    ('TurretComponentData', 24, 'vertical_limit_max', 'turret.pitch_max', 'turretUpdate', 'turret.pitch_min/max',
     'highest pitch, degrees (clamp)', 'read every frame: immediate', 'existing'),
    ('TurretComponentData', 28, 'horizontal_limit_min', 'turret.yaw_min', 'turretUpdate', None,
     'yaw limit min, degrees; a span >= 359.94 deg selects the unlimited (wrapping) yaw path', 'read every frame: '
     'immediate', 'existing'),
    ('TurretComponentData', 32, 'horizontal_limit_max', 'turret.yaw_max', 'turretUpdate', None,
     'yaw limit max, degrees', 'read every frame: immediate', 'existing'),
    ('TurretComponentData', 36, 'yaw_rotation_event_threshold', None, 'turretUpdate', None,
     'yaw rotation event debounce (s): start/stop audio/animation events fire only after the moving state held this '
     'long', 'read every frame', 'no: presentation'),
    ('TurretComponentData', 40, 'pitch_rotation_event_time', None, 'turretUpdate', None,
     'pitch rotation event debounce (s)',
     'read every frame', 'no: presentation'),
    ('TurretComponentData', 44, 'rotation_start_sound', None, 'turretUpdate', None,
     'yaw rotation start audio event (Wwise id)',
     'read every frame', 'no: presentation'),
    ('TurretComponentData', 48, 'rotation_stop_sound', None, 'turretUpdate', None,
     'yaw rotation stop audio event (Wwise id)',
     'read every frame', 'no: presentation'),
    ('TurretComponentData', 60, 'pitch_start_sound', None, 'turretUpdate', None,
     'pitch rotation start audio event (Wwise id)',
     'read every frame', 'no: presentation'),
    ('TurretComponentData', 64, 'pitch_stop_sound', None, 'turretUpdate', None,
     'pitch rotation stop audio event (Wwise id)',
     'read every frame', 'no: presentation'),
    ('SensorEyeComponentData', 0, 'distance', 'targeting.range', 'sensorEye', 'targeting.range',
     'front sensing range, metres', 'copied into the sensor instance at spawn (x the instance scale)', 'existing'),
    ('SensorEyeComponentData', 4, 'perpendicular_range', 'targeting.side_range', 'sensorEye', None,
     'sensing range across the sensor node\'s forward axis, metres; negative = the front range (every sentry: -1, '
     'i.e. 360-degree sensing)', 'copied into the sensor instance at spawn (x scale)', 'propose'),
    ('SensorEyeComponentData', 8, 'reverse_range', 'targeting.rear_range', 'sensorEye', None,
     'sensing range behind the sensor node, metres; negative = the front range', 'copied into the sensor instance at '
     'spawn (x scale)', 'propose'),
    ('SensorEyeComponentData', 12, 'horizontal_angle', None, 'sensorEye', None,
     'cone half-angle (deg), used only by shape-type 2 sensors (no sentry)', 'copied at spawn',
     'no: unused by every sentry (shape type 1)'),
    ('SensorEyeComponentData', 16, 'vertical_angle', None, 'sensorEye', None,
     'cone vertical half-angle (deg), shape-type 2 only', 'copied at spawn', 'no: unused by every sentry'),
    ('SensorProximityComponentData', 0, 'range', 'targeting.proximity_range', 'sensorProximity', None,
     'proximity sensing radius, metres: candidates inside are perceived without a line-of-sight ray (mortars only)',
     'read from the type table by every perception update: immediate on deployed mortars', 'propose'),
    ('TargetingComponentData', 8, 'dampener', None, 'targeting', None, 'aim spring damping (1/s); 0.5 on every sentry',
     'read every frame', 'no: constant across sentries; sentry effect unproven'),
    ('TargetingComponentData', 12, 'aim_spring_stiffness', None, 'targeting', None, 'aim spring stiffness; 5.0 on every sentry',
     'read every frame', 'no: constant across sentries; sentry effect unproven'),
    ('TargetingComponentData', 16, 'angular_speed_limit', None, 'targeting', None, 'aim angular speed cap (deg/s); 90 on every sentry',
     'read every frame', 'no: constant across sentries; sentry effect unproven'),
    ('TargetingComponentData', 20, 'max_smoothing_angle', None, 'targeting', None, 'smoothing gate angle (deg); 180 on every sentry',
     'read every frame', 'no: constant across sentries'),
    ('TargetingComponentData', 40, 'aim_offset_recovery', None, 'targeting', None, 'aim offset weight decay rate (1/s); 1.0',
     'read every frame', 'no: constant across sentries'),
    ('TargetingComponentData', 0, None, None, None, None, 'no native reader located (25 / 0.1 mortars / 5 MLS-4X)',
     'unknown', 'no: no active source'),
    ('TargetingComponentData', 4, None, None, None, None, 'no native reader located (0.5 everywhere on sentries)',
     'unknown', 'no: no active source'),
    ('WeaponDataComponentData', '84.0', 'horizontal', 'weapon.horizontal_spread', 'weaponData', 'spread',
     'horizontal spread, full width in milliradians', 'copied into the weapon instance at creation (x the instance '
     'multiplier); deployed sentries keep their copy', 'propose'),
    ('WeaponDataComponentData', '84.4', 'vertical', 'weapon.vertical_spread', 'weaponData', 'spread',
     'vertical spread, full width in milliradians', 'copied at creation', 'propose'),
    ('WeaponDataComponentData', '0.0.0', 'horizontal_recoil', 'weapon.recoil_drift_horizontal', 'weaponData', 'recoil',
     'recoil drift, horizontal (block A)', 'copied at creation (x the instance multiplier)', 'propose'),
    ('WeaponDataComponentData', '0.0.4', 'vertical_recoil', 'weapon.recoil_drift_vertical', 'weaponData', 'recoil',
     'recoil drift, vertical (block A)', 'copied at creation', 'propose'),
    ('WeaponDataComponentData', '0.28.0', 'horizontal_recoil', 'weapon.recoil_climb_horizontal', 'weaponData', 'recoil',
     'recoil climb, horizontal (block B)', 'copied at creation', 'propose'),
    ('WeaponDataComponentData', '0.28.4', 'vertical_recoil', 'weapon.recoil_climb_vertical', 'weaponData', 'recoil',
     'recoil climb, vertical (block B; the Pelican research: kicks a turret\'s aim per shot)', 'copied at creation',
     'propose'),
    ('WeaponWindUpComponentData', 0, 'wind_up_time', 'windup.wind_up_seconds', 'windUp', None,
     'barrel wind-up time, seconds (Gatling Sentry only)', 'resolved every update (type record)', 'propose'),
    ('WeaponWindUpComponentData', 4, 'wind_down_time', 'windup.wind_down_seconds', 'windUp', None,
     'barrel spin-down switch: <= 0 stops at once, > 0 spins down over the wind-up time (its magnitude is not read)',
     'resolved every update', 'propose'),
    ('BeamWeaponComponentData', 104, 'fire_rate_in_rpm', 'beam.fire_rate', None, 'beam.fire_rate',
     'beam fire rate (damage ticks per minute), Laser Sentry', 'type record (same member as the player beam weapons)',
     'propose'),
    ('HellpodPayloadComponentData', 0, 'remove_time', None, None, None,
     'Go lead: time between the retraction animation and removal (2.5 s; 3.5 s Gatling)', 'unknown', 'no: low value '
     '(despawn timing)'),
]


def build_candidates(t, code_ok: dict, checks: dict, go_leads: dict) -> list:
    out = []
    for component, path, native, semantic, code, published, role, lifecycle, promote in SPECS:
        table = t.component(component)
        member = table.member(path)
        values = sentry_values(t, component, path)
        if published == 'spread':
            key = 'weapon.horizontal_spread/vertical_spread'
        elif published == 'recoil':
            key = 'recoil-means'
        else:
            key = published
        if key == 'recoil-means':
            relevant = [c for label in checks for name, c in checks[label].items() if 'recoil' in name]
        elif key:
            relevant = [checks[label][key] for label in checks if key in checks[label]]
        else:
            relevant = []
        published_exact = bool(relevant) and all(c['exact'] for c in relevant)
        evidence = {'codeRead': bool(code and code_ok.get(code)), 'publishedExact': published_exact,
            'liveTest': (component, member.offset) in LIVE,
            'nameLengthFit': native is not None and member.name_length == len(native),
            'differential': differential(t, component, path)}
        lead = go_leads.get((component, member.offset))
        notes = [lifecycle]
        if published == 'recoil':
            notes.append('Published only as the means the player/support mapping already derives '
                '(horizontal = mean(drift, climb), vertical likewise, recoil = their mean); every sentry agrees.')
        if component == 'SensorProximityComponentData':
            notes.append('The wiki\'s 125 m statements (M-23, GM-17) equal this member and SensorEye +0 alike; they '
                'do not distinguish the two, so they are not counted as an exact published value here.')
        out.append(report.candidate(str(path), member.offset, member.storage, member.name_length, member.kind,
            values, evidence, proposed=native, notes=notes, component=component, semanticFieldId=semantic,
            role=role, lifecycle=lifecycle, promotion=promote, codeGroup=code, publishedChecks=len(relevant),
            goLead=lead))
    return out


def go_lead_map(t) -> dict:
    go = golib.default_library()
    out = {}
    for component in ('WeaponWindUpComponentData', 'HellpodPayloadComponentData', 'ProjectileWeaponComponentData',
            'WeaponHeatComponentData'):
        record_type = t.component(component).record_type
        for offset, lead in golib.leads_for(t, go, record_type).items():
            out[(component, offset)] = {'label': lead['label'], 'strength': lead['strength']}
    return out


# -- proposals ---------------------------------------------------------------------------------------------------
TESLA_SENSOR = ('the Tesla Tower\'s SensorEye is shape type 3 (+32 = 3): its vision test (0x64C9C7) reads only the '
    'front range (instance +0xC) and never the side/rear ranges')
PROXIMITY_DEFERRED = ('deferred from the first implementation pass: writing it needs SensorProximityComponentData in the '
    'runtime profile (schemas/current.lua), which is not part of that pass')
# The reviewed publication the stratagem generator reads (scripts/generate_stratagem_authoring.py, sentry block): per
# field the member, range, read timing, native reader and the structural rule deciding which sentries get it; per
# sentry the record ownership and the baseline of every published field.
PUBLICATION_FIELDS = {
    'weapon.horizontal_spread': ('WeaponDataComponentData', 84, 'f32', 0, 500, 'spawn', 'projectile',
        'the instance build 0x752370 copies it (x the instance multiplier); every shot reads the copy (0x615BAB)',
        'up to 500 mrad full width (+-14.3 degrees); the widest native sentry spread is 100'),
    'weapon.vertical_spread': ('WeaponDataComponentData', 88, 'f32', 0, 500, 'spawn', 'projectile',
        'the instance build 0x752370 copies it; every shot reads the copy (0x615BAB)',
        'up to 500 mrad full width; the widest native sentry spread is 100'),
    'weapon.recoil_drift_horizontal': ('WeaponDataComponentData', 0, 'f32', 0, 100, 'spawn', 'projectile',
        'the instance build copies recoil block A (0x7525AB); each shot applies it to the turret\'s aim (0x784CAC)',
        'the player-weapon recoil scale; the largest native sentry value is 20'),
    'weapon.recoil_drift_vertical': ('WeaponDataComponentData', 4, 'f32', 0, 100, 'spawn', 'projectile',
        'recoil block A, copied at creation (0x7525AB), applied per shot (0x784CAC)',
        'the player-weapon recoil scale; native sentry values 0..10'),
    'weapon.recoil_climb_horizontal': ('WeaponDataComponentData', 28, 'f32', 0, 100, 'spawn', 'projectile',
        'recoil block B, copied at creation (0x7525CC), applied per shot (0x784CCF)',
        'the player-weapon recoil scale; native sentry values 0..2.5'),
    'weapon.recoil_climb_vertical': ('WeaponDataComponentData', 32, 'f32', 0, 100, 'spawn', 'projectile',
        'recoil block B, copied at creation (0x7525CC), applied per shot (0x784CCF)',
        'the player-weapon recoil scale; native sentry values 0..10'),
    'windup.wind_up_seconds': ('WeaponWindUpComponentData', 0, 'f32', 0, 30, 'live', 'windup',
        'the wind-up routine 0x78A420 resolves the record every update (0x78A492) and reads it (0x78A4D4)',
        '0 = instant; 30 s is far beyond any native value (0.5)'),
    'windup.wind_down_seconds': ('WeaponWindUpComponentData', 4, 'f32', 0, 30, 'live', 'windup',
        'the wind-up routine reads it every update on release (0x78A519) as a switch: > 0 spins down over '
        'windup.wind_up_seconds (0x78A52C divides by the wind-up time)', '0 = instant stop; any positive value '
        'behaves the same (native 1.0)'),
    'beam.fire_rate': ('BeamWeaponComponentData', 104, 'i32', 1, 3000, 'unverified', 'beam',
        'the same member and published value as the seven player beam weapons (research/equipment-coverage); the '
        'sentry\'s own reader is not located, so write it before the sentry is deployed', 'the player beam range'),
    'turret.pitch_yaw_coupling': ('TurretComponentData', 16, 'f32', 0, 10, 'live', 'turret',
        'the turret update 0x6DEDB0 reads it every frame through the settings resolver 0x50B8B0 (0x6DF703) as '
        'pow(|remaining yaw error, degrees|, -value), clamped to 1, multiplying the pitch step (0x6DFC73)',
        'native values across all 73 turret owners: 0..10'),
    'targeting.side_range': ('SensorEyeComponentData', 4, 'f32', 0, 500, 'spawn', 'sensor_type_1',
        'copied into the sensor instance at spawn (0x64C472 -> instance +0x10); the type-1 vision test blends it '
        '(0x64CDDD)', 'the targeting.range scale (1-500 m); -1 = use targeting.range (every native sentry)'),
    'targeting.rear_range': ('SensorEyeComponentData', 8, 'f32', 0, 500, 'spawn', 'sensor_type_1',
        'copied into the sensor instance at spawn (0x64C489 -> instance +0x14); the type-1 vision test uses it '
        'behind the sensor node (0x64CDBA)', 'the targeting.range scale; -1 = use targeting.range'),
}
EXISTING_TIMING = {'turret.yaw_speed': 'spawn', 'turret.pitch_speed': 'spawn', 'turret.pitch_min': 'live',
    'turret.pitch_max': 'live', 'turret.yaw_min': 'live', 'turret.yaw_max': 'live', 'targeting.range': 'spawn'}
TIMING_TEXT = {'spawn': 'copied into the sentry instance when it spawns: a write applies to sentries deployed after it; '
        'sentries already deployed keep their copy',
    'live': 'read from the type record every update: a write also changes sentries already deployed',
    'unverified': 'when the game reads it is not established: write it before the sentry is deployed'}


def publication(t, behaviour: dict) -> dict:
    """The reviewed source of the generated sentry fields: structural applicability, ownership and baselines."""
    rules = {'projectile': lambda r: t.component('ProjectileWeaponComponentData').record_of(r) is not None,
        'windup': lambda r: t.component('WeaponWindUpComponentData').record_of(r) is not None,
        'beam': lambda r: t.component('BeamWeaponComponentData').record_of(r) is not None,
        'turret': lambda r: t.component('TurretComponentData').record_of(r) is not None,
        'sensor_type_1': lambda r: value(t, 'SensorEyeComponentData', r, 32) == 1}
    exclusions = {'projectile': {'LAS98': 'beam attack: its WeaponData spread/recoil equal the wiki, but no read on '
            'the beam path is shown', 'FLAM40': 'spray attack: its WeaponData spread/recoil equal the wiki, but no '
            'read on the spray path is shown', 'TESLA': 'arc attack (the arc.* fields cover its spread)'},
        'sensor_type_1': {'TESLA': TESLA_SENSOR}}
    fields = {}
    sentries = {name: {'label': label, 'resource': hexid(resource), 'components': {}, 'values': {}}
        for label, (name, resource, _) in SENTRIES.items()}
    for field_id, (component, offset, storage, low, high, timing, rule, reader, justification) in \
            PUBLICATION_FIELDS.items():
        applies = [label for label, (_, resource, _) in SENTRIES.items() if rules[rule](resource)]
        fields[field_id] = {'component': component, 'offset': offset, 'storage': storage, 'min': low, 'max': high,
            'sentinelValues': [-1] if field_id.startswith('targeting.') else [], 'readTiming': timing,
            'readTimingNote': TIMING_TEXT[timing], 'nativeReader': reader, 'rangeJustification': justification,
            'appliesTo': [SENTRIES[label][0] for label in applies],
            'excluded': {SENTRIES[label][0]: reason for label, reason in exclusions.get(rule, {}).items()},
            'path': {'WeaponDataComponentData': 'weapon', 'WeaponWindUpComponentData': 'weapon',
                'BeamWeaponComponentData': 'weapon', 'TurretComponentData': 'turret',
                'SensorEyeComponentData': 'targeting'}[component]}
        for label in applies:
            name, resource, _ = SENTRIES[label]
            raw = value(t, component, resource, offset)
            if raw is None:
                raise ValueError('%s: %s has no %s' % (field_id, label, component))
            sentries[name]['values'][field_id] = raw
            if component not in sentries[name]['components']:
                sentries[name]['components'][component] = ownership(t, component, resource)
    for name, item in sentries.items():
        for component, own in item['components'].items():
            if not own['unique']:
                raise ValueError('%s %s is shared: the publication assumes one owner' % (name, component))
    derived = {'weapon.horizontal_recoil': 'mean of weapon.recoil_drift_horizontal and weapon.recoil_climb_horizontal',
        'weapon.vertical_recoil': 'mean of weapon.recoil_drift_vertical and weapon.recoil_climb_vertical',
        'weapon.recoil': 'mean of weapon.horizontal_recoil and weapon.vertical_recoil'}
    for name, item in sentries.items():
        v = item['values']
        if 'weapon.recoil_drift_horizontal' in v:
            horizontal = r6((v['weapon.recoil_drift_horizontal'] + v['weapon.recoil_climb_horizontal']) / 2)
            vertical = r6((v['weapon.recoil_drift_vertical'] + v['weapon.recoil_climb_vertical']) / 2)
            item['derived'] = {'weapon.horizontal_recoil': horizontal, 'weapon.vertical_recoil': vertical,
                'weapon.recoil': r6((horizontal + vertical) / 2)}
    engagement = {}
    for label, item in behaviour['directFire'].items():
        engagement[SENTRIES[label][0]] = {'scoreCutoffMeters': item['distanceScoreCurve']['points'][-1][0],
            'source': 'behaviour %d distance score curve (0 at this distance): hard-coded' % item['behaviour']}
    for label, item in behaviour['mortars'].items():
        minimum = next(seg[0] for seg in item['curveSegments'] if seg[1] == 0.0 and seg[3] > 0.5)
        engagement[SENTRIES[label][0]] = {'scoreCutoffMeters': 125.0, 'minimumMeters': minimum,
            'source': 'behaviour %d search score curve: hard-coded' % item['behaviour'],
            'proximitySensor': {'component': 'SensorProximityComponentData', 'offset': 0,
                'radiusMeters': value(t, 'SensorProximityComponentData', SENTRIES[label][1], 0),
                'note': 'perceives every candidate within the radius with no line-of-sight ray; '
                    'targeting.range alone does not shrink the acquisition of a mortar (targeting.proximity_range: '
                    'deferred)'}}
    return {'contract': 'hd2runtime.research.sentry_fields.v1', 'evidenceFamily': 'sentry_component_fields',
        'engagement': engagement, 'fields': fields, 'derived': derived, 'sentries': sentries, 'existingTiming': EXISTING_TIMING,
        'timingText': TIMING_TEXT,
        'deferred': [{'field': 'targeting.proximity_range', 'component': 'SensorProximityComponentData', 'offset': 0,
            'appliesTo': [SENTRIES[k][0] for k in ('M12', 'M23', 'GM17')], 'reason': PROXIMITY_DEFERRED}],
        'acknowledgement': 'allow_unverified_effect on every field until a live test (family sentry_component_fields)'}


def proposals(candidates: list, snaps: dict, behaviour: dict) -> tuple[list, list, list]:
    by = {(c['component'], c['offset']): c for c in candidates}

    def conf(component, offset):
        return by[(component, offset)]['confidence']
    promote = [
        {'fieldId': 'hd2.fields.weapon.horizontal_spread', 'semanticFieldId': 'weapon.horizontal_spread',
         'target': 'hd2.stratagem(sentry):deployed_entity():weapon()', 'appliesTo': PROJECTILE_SENTRIES,
         'excluded': {'LAS98': 'beam attack; its WeaponData spread (5/5) matches the wiki but no beam read is shown',
             'FLAM40': 'spray attack; spread 50/25 matches the wiki but no spray read is shown',
             'TESLA': 'arc attack (arc.* fields already cover its spread)'},
         'backing': {'component': 'WeaponDataComponentData', 'offset': 84, 'storage': 'f32'},
         'type': 'number', 'unit': 'milliradians (full width)', 'range': [0, 500],
         'confidence': conf('WeaponDataComponentData', 84),
         'writeSemantics': 'expect/value on the sentry type record; takes effect for sentries deployed after the write '
             '(the instance copies type x multiplier at creation); deployed sentries keep their copy',
         'acknowledgement': 'allow_unverified_effect (until a sentry live test; per-instance spread writes on the '
             'Gatling chassis are already live-used by the custom sentry and the Pelican chin gun)',
         'ownership': 'one owner per sentry type (unique WeaponData record)'},
        {'fieldId': 'hd2.fields.weapon.vertical_spread', 'semanticFieldId': 'weapon.vertical_spread',
         'backing': {'component': 'WeaponDataComponentData', 'offset': 88, 'storage': 'f32'},
         'sameAs': 'hd2.fields.weapon.horizontal_spread', 'confidence': conf('WeaponDataComponentData', 88)},
        {'fieldId': 'hd2.fields.weapon.recoil_drift_horizontal / recoil_drift_vertical / recoil_climb_horizontal / '
             'recoil_climb_vertical',
         'semanticFieldId': ['weapon.recoil_drift_horizontal', 'weapon.recoil_drift_vertical',
             'weapon.recoil_climb_horizontal', 'weapon.recoil_climb_vertical'],
         'target': 'hd2.stratagem(sentry):deployed_entity():weapon()', 'appliesTo': PROJECTILE_SENTRIES,
         'backing': {'component': 'WeaponDataComponentData', 'offsets': [0, 4, 28, 32], 'storage': 'f32'},
         'type': 'number', 'unit': 'as the player weapons (degrees per second)', 'range': [0, 100],
         'derivedReadOnly': ['weapon.recoil', 'weapon.horizontal_recoil', 'weapon.vertical_recoil'],
         'confidence': [conf('WeaponDataComponentData', o) for o in (0, 4, 28, 32)],
         'writeSemantics': 'expect/value; effect from the next deployed sentry (copied at creation); a turret\'s '
             'recoil kicks its own aim, so 0 tightens grouping and large values walk the aim off target',
         'acknowledgement': 'allow_unverified_effect (until live)'},
        {'fieldId': 'hd2.fields.turret.pitch_yaw_coupling', 'semanticFieldId': 'turret.pitch_yaw_coupling',
         'target': 'hd2.stratagem(sentry):deployed_entity():turret()', 'appliesTo': TURRETED,
         'backing': {'component': 'TurretComponentData', 'offset': 16, 'storage': 'f32'},
         'nativeNameCandidate': 'pitch_exponent (14 = hidden length; a fit, not a recovered name)',
         'type': 'number', 'unit': 'exponent (unitless)', 'range': [0, 10],
         'semantics': 'pitch speed is multiplied by min(1, e^-value) where e = the yaw error (degrees) left after this '
             'frame\'s yaw step; 0 = pitch independent of yaw; 4 (mortars) = barely pitches until aligned',
         'confidence': conf('TurretComponentData', 16),
         'writeSemantics': 'expect/value; read every frame from the type record: immediate on deployed sentries',
         'acknowledgement': 'allow_unverified_effect'},
        {'fieldId': 'hd2.fields.targeting.side_range', 'semanticFieldId': 'targeting.side_range',
         'target': 'hd2.stratagem(sentry):deployed_entity():targeting()', 'appliesTo': TURRETED,
         'excluded': {'TESLA': TESLA_SENSOR},
         'backing': {'component': 'SensorEyeComponentData', 'offset': 4, 'storage': 'f32'},
         'nativeNameCandidate': 'perpendicular_range (19; a fit)', 'type': 'number', 'unit': 'meters',
         'range': [0, 500], 'sentinel': {'value': -1, 'meaning': 'same as targeting.range (360-degree sensing)'},
         'semantics': 'effective range = |cos| x (front range ahead, rear range behind) + (1 - |cos|) x side range, '
             'the angle measured from the sensor node\'s forward axis (on the turret head); sentries: shape type 1',
         'confidence': conf('SensorEyeComponentData', 4),
         'writeSemantics': 'expect/value; copied into the sensor instance at spawn: effect from the next deployed '
             'sentry', 'acknowledgement': 'allow_unverified_effect'},
        {'fieldId': 'hd2.fields.targeting.rear_range', 'semanticFieldId': 'targeting.rear_range',
         'backing': {'component': 'SensorEyeComponentData', 'offset': 8, 'storage': 'f32'},
         'nativeNameCandidate': 'reverse_range (13; a fit)', 'sameAs': 'hd2.fields.targeting.side_range',
         'confidence': conf('SensorEyeComponentData', 8)},
        {'fieldId': 'hd2.fields.targeting.proximity_range', 'semanticFieldId': 'targeting.proximity_range',
         'status': 'deferred', 'deferredReason': PROXIMITY_DEFERRED,
         'target': 'hd2.stratagem(sentry):deployed_entity():targeting()', 'appliesTo': ['M12', 'M23', 'GM17'],
         'backing': {'component': 'SensorProximityComponentData', 'offset': 0, 'storage': 'f32'},
         'nativeNameCandidate': 'range (5; a fit)', 'type': 'number', 'unit': 'meters', 'range': [0, 500],
         'semantics': 'any hostile candidate within this radius is perceived with no line-of-sight ray; on the '
             'mortars it equals targeting.range (125 m), so targeting.range alone cannot shrink a mortar\'s '
             'acquisition', 'confidence': conf('SensorProximityComponentData', 0),
         'writeSemantics': 'expect/value; read live: immediate on deployed mortars; values above 125 m add nothing '
             '(the mortar behaviour\'s score curve reaches 0 at 125 m)',
         'acknowledgement': 'allow_unverified_effect', 'ownership': 'one owner per mortar type'},
        {'fieldId': 'hd2.fields.windup.wind_up_seconds / wind_down_seconds',
         'semanticFieldId': ['windup.wind_up_seconds', 'windup.wind_down_seconds'],
         'target': 'hd2.stratagem(\'A/G-16 Gatling Sentry\'):deployed_entity():weapon()', 'appliesTo': ['G16'],
         'backing': {'component': 'WeaponWindUpComponentData', 'offsets': [0, 4], 'storage': 'f32'},
         'type': 'number', 'unit': 'seconds', 'range': [0, 30],
         'confidence': [conf('WeaponWindUpComponentData', 0), conf('WeaponWindUpComponentData', 4)],
         'writeSemantics': 'expect/value; resolved every update (immediate)',
         'acknowledgement': 'allow_unverified_effect (whether the AI waits for the wind-up before firing is not '
             'established; the effect may be the barrel spin only)'},
        {'fieldId': 'hd2.fields.beam.fire_rate', 'semanticFieldId': 'beam.fire_rate',
         'target': 'hd2.stratagem(\'A/LAS-98 Laser Sentry\'):deployed_entity():weapon()', 'appliesTo': ['LAS98'],
         'backing': {'component': 'BeamWeaponComponentData', 'offset': 104, 'storage': 'i32'}, 'type': 'integer',
         'unit': 'rpm', 'range': [1, 3000], 'confidence': conf('BeamWeaponComponentData', 104),
         'writeSemantics': 'expect/value (the same member and semantics as the player beam weapons)',
         'acknowledgement': 'allow_unverified_effect (until a sentry live test)'},
    ]
    evidence_upgrades = [
        {'fieldId': 'hd2.fields.turret.yaw_min / yaw_max', 'change': 'native read now shown (turret update '
            '0x6DF4AD/0x6DF4BE, every frame): STRONG; keep allow_unverified_effect until live', 'semantics': 'a span '
            '>= 359.94 degrees keeps the wrapping (unlimited) yaw; anything narrower is clamped and cannot wrap',
         'confidence': conf('TurretComponentData', 28)},
        {'fieldId': 'hd2.fields.turret.pitch_min / pitch_max', 'change': 'native read (0x6DFC7F/0x6DFC91) plus the '
            'wiki\'s Vertical Limit on nine sentries: CONFIRMED by the confidence rules; still not live-tested',
         'confidence': conf('TurretComponentData', 20)},
        {'fieldId': 'hd2.fields.turret.yaw_speed / pitch_speed', 'change': 'lifecycle: copied into the turret '
            'instance at spawn (0x6E0806/0x6E0844) and multiplied by a per-instance speed factor (0x6DE820, ship '
            'modules): a write affects sentries deployed after it, not deployed ones; snapshot controls show the '
            'copy (cctv_camera 80/60, seaf_gun 240/60)', 'confidence': conf('TurretComponentData', 12)},
        {'fieldId': 'hd2.fields.targeting.range', 'change': 'lifecycle: copied into the sensor instance at spawn (x '
            'scale; 44 of 44 snapshot instances); engagement is also capped by the behaviour\'s hard-coded distance '
            'score (100 m MG-43/G-16/AC-8/LAS-98, 50 m FLAM-40, 125 m mortars): values above the cap do not extend '
            'engagement; mortars also sense through targeting.proximity_range', 'confidence':
            conf('SensorEyeComponentData', 0)},
    ]
    not_promoted = [
        {'member': 'TurretComponentData +36/+40 (len 28/25, 0.1)', 'reason': 'yaw/pitch rotation event debounce '
            '(s): code-read (0x6DFE49/0x6DFF0F) but presentation only (audio/animation start/stop events)'},
        {'member': 'TurretComponentData +44/+48/+60/+64, +52/+56', 'reason': 'Wwise start/stop events of yaw and '
            'pitch rotation and yaw animation events; presentation'},
        {'member': 'TurretComponentData +0/+4/+72', 'reason': 'node names (pitch: pitch/elevation/head_pitch; yaw: '
            'yaw/traverse/head_yaw); structural, resolved at creation'},
        {'member': 'TurretComponentData +68 (len 13)', 'reason': 'read outside the turret update (0x1121330, '
            '0x11CB870) as a 32-bit id; role not established'},
        {'member': 'SensorEyeComponentData +12/+16 (len 16/14; 20/20, AC-8 360/360)', 'reason': 'cone half-angles '
            'used only by shape-type 2 sensors; every sentry is shape type 1 (360 degrees with -1 side/rear), so the '
            'AC-8\'s 360 changes nothing; no sentry effect'},
        {'member': 'SensorEyeComponentData +20/+24/+28/+32', 'reason': 'sensor node, node-orientation flag, an enum '
            'and the sensor shape type (Tesla 3); structural'},
        {'member': 'SensorEyeComponentData +36/+40 (8.0 / 0.5)', 'reason': 'identical on all 313 owners (no '
            'differential); read by 0x64D1D0 as radii in a zone test'},
        {'member': 'TargetingComponentData +8/+12/+16/+20/+40', 'reason': 'the targeting aim spring (damping, '
            'stiffness, angular speed cap, gate angle, offset decay): code-proven but identical on every sentry and '
            'its coupling to the turret solve is not shown; not the "search/retarget intervals" the earlier note '
            'guessed'},
        {'member': 'TargetingComponentData +0/+4/+24/+32/+36/+44/+48/+60', 'reason': 'no native reader located; the '
            '+0 differential (25, mortars 0.1, MLS-4X 5) is unexplained'},
        {'member': 'TargetingComponentData +25/+26/+28/+61/+62/+63', 'reason': 'structural switches and the aim node '
            '(+25 set on mortars skips the aim-node/lead section)'},
        {'member': 'DetectorComponentData (0.4/0.5/1/4/1)', 'reason': 'identical on every sentry; no reader located '
            '(no type-table access in code)'},
        {'member': 'BehaviorComponentData +0 (behaviour id)', 'reason': 'selects the compiled AI; changing it '
            'swaps the whole AI (the Pelican research uses the game\'s SetBehaviour per instance only)'},
        {'member': 'Behaviour constants (distance score curve, fire cone, re-pick 1 s, initial wait 2 s, alert 7 s, '
            'mortar minimum distances)', 'reason': 'compiled constants, not data: target re-acquisition, switching '
            'hysteresis (x0.9 / AC-8 x1.1), aim tolerance and minimum/maximum engagement distance cannot be changed '
            'by a data write', 'values': {k: {'curve': v['distanceScoreCurve']['points'], 'fireCone':
                v['fireConeDegrees']} for k, v in behaviour['directFire'].items()}},
        {'member': 'WeaponDataComponentData sway (+104 = 1) / ergonomics (+356 = 65)', 'reason': 'exact published '
            'values, but player handling members with no consumer on the AI path'},
        {'member': 'ProjectileWeaponComponentData +144 spinup_time (0) / +124 speed_multiplier (1) / +36 '
            'infinite_ammo (0)', 'reason': 'Go leads fit (len 11/16/13) but constant on every sentry and not '
            'code-read here; speed overlaps projectile.velocity'},
        {'member': 'HellpodPayloadComponentData +0 remove_time (2.5 s; 3.5 s Gatling)', 'reason': 'Go lead fits '
            '(len 11), despawn/retraction timing only'},
        {'member': 'HealthComponentData +21500 ElementDamage[4] (Flame Sentry: element 1 x 0.05)', 'reason':
            'code-proven by research/event-combat (ApplyDamage multiplies by it), but entity-wide and the element '
            'names are Filediver leads; belongs to the entity/enemy authoring track (per-slot element id + '
            'multiplier), not a sentry field'},
        {'member': 'Unit +16 radius (Tesla 0.5)', 'reason': 'unit radius; structural'},
        {'member': 'Wiki "Stratagem Statistics > Turn Rate" (96/160, 32/48)', 'reason': 'matches no native member '
            'and is inconsistent with the detailed tables (which match exactly); ignored'},
    ]
    return promote, evidence_upgrades, not_promoted


def build() -> dict:
    t = tables.pinned()
    controls = resolve_controls(t)
    fingerprints = check_fingerprints(t)
    image = xref.CodeImage.from_snapshot('game.dll')
    if image.sha256 != GAME_DLL_SHA256:
        raise ValueError('game.dll image changed: %s' % image.sha256)
    code = verify_pins(image)
    code_ok = {group: True for group in code}
    for rva, role in ((POW, 'pow'), (ANGLE_APPROACH, 'angle approach')):
        if image.chunk(rva) is None:
            raise ValueError('%s function missing at %x' % (role, rva))
    behaviour = behaviour_constants(image)
    wiki = {k: wiki_values(v) for k, v in wiki_rows().items()}
    checks = wiki_checks(t, wiki)
    for label in TURRETED:
        for key in ('turret.yaw_speed', 'turret.pitch_speed', 'turret.pitch_min/max'):
            if not checks[label].get(key, {}).get('exact'):
                raise ValueError('%s: %s no longer equals the wiki' % (label, key))
    presence = compare.presence(t, {k: v[1] for k, v in SENTRIES.items()})
    behaviours = {k: value(t, 'BehaviorComponentData', v[1], 0) for k, v in SENTRIES.items()}
    if behaviours != {k: v[2] for k, v in SENTRIES.items()}:
        raise ValueError('sentry behaviour ids changed: %r' % behaviours)
    components = presence['common'] + list(presence['partial'])
    own = {k: {c: ownership(t, c, v[1]) for c in components if t.component(c).record_of(v[1]) is not None}
        for k, v in SENTRIES.items()}
    shared = sorted({(k, c) for k, row in own.items() for c, o in row.items() if o and not o['unique']})
    catalogue = {c: member_catalogue(t, c, controls) for c in ('TurretComponentData', 'SensorEyeComponentData',
        'SensorProximityComponentData', 'TargetingComponentData', 'DetectorComponentData', 'WeaponWindUpComponentData',
        'HellpodPayloadComponentData', 'BehaviorComponentData')}
    catalogue['WeaponDataComponentData'] = member_catalogue(t, 'WeaponDataComponentData', controls,
        {'0.0.0', '0.0.4', '0.28.0', '0.28.4', '84.0', '84.4', '104', '132', '140', '144', '148', '152', '356'})
    catalogue['ProjectileWeaponComponentData'] = member_catalogue(t, 'ProjectileWeaponComponentData', controls,
        {'0', '4', '36', '52.0', '52.4', '52.8', '52.12', '104', '124', '144'})
    catalogue['WeaponMagazineComponentData'] = member_catalogue(t, 'WeaponMagazineComponentData', controls,
        {'0', '136', '140', '144', '148', '152', '156'})
    catalogue['HealthComponentData'] = member_catalogue(t, 'HealthComponentData', controls,
        {'0', '64.216', '21500[0].0', '21500[0].4'})
    families = {}
    for component in ('TurretComponentData', 'SensorEyeComponentData', 'TargetingComponentData',
            'WeaponDataComponentData', 'ProjectileWeaponComponentData', 'HellpodPayloadComponentData'):
        entities = {k: v[1] for k, v in SENTRIES.items()}
        entities.update(controls)
        family = compare.Family(t, component, entities)
        families[component] = {'entities': family.labels, 'missing': family.missing,
            'varyingElements': len(family.varying()), 'clusters': family.clusters()}
    go_leads = go_lead_map(t)
    candidates = build_candidates(t, code_ok, checks, go_leads)
    snaps = snapshot_evidence(t)
    promote, upgrades, not_promoted = proposals(candidates, snaps, behaviour)
    scope = {'sentries': {k: {'name': v[0], 'resource': hexid(v[1]), 'path': t.name(v[1]), 'behaviour': v[2]}
            for k, v in SENTRIES.items()},
        'controls': {k: {'resource': hexid(v), 'path': t.name(v)} for k, v in controls.items()},
        'gameDllSha256': image.sha256, 'writes': 0, 'protectionChanges': 0,
        'method': 'type library layout + family differential over all owners + Filediver leads + native readers '
            '(type-table lookups, resolvers, consumers) + wiki detailed tables + retained mission snapshots'}
    return report.document('Sentry components: catalogue, native readers and promotion proposal', scope, candidates,
        layoutFingerprints=fingerprints, typeTableSlots={k: v for k, v in TYPE_TABLE_SLOTS.items()},
        presence=presence, ownership=own, sharedRecords=[list(x) for x in shared], wiki=wiki, wikiChecks=checks,
        perSentryMatrix=catalogue, clusters=families, codeReferences=code,
        functions={'turretTypeLookup': 0x50B430, 'turretSettingsResolver': 0x50B8B0, 'turretCopyMaker': 0x6E23F0,
            'turretSpawnInit': 0x6E06F0, 'turretSpeedFactor': 0x6DE820, 'turretUpdate': 0x6DEDB0,
            'sensorEyeLookup': 0x503780, 'sensorEyeResolver': 0x503BC0, 'sensorEyeInit': 0x64C4C0,
            'sensorEyeRanges': 0x64C3C0, 'visionTest': 0x64C6F0, 'perceptionUpdate': 0x887760,
            'proximityHandler': 0x886A70, 'proximityTest': 0x64FD20, 'targetingUpdate': 0x6BBDC0,
            'weaponDataBuild': 0x752370, 'windUpUpdate': 0x78A420, 'behaviourDispatch': 0x472F60,
            'instanceCopySwitch': 0x5740B0, 'pow': POW},
        behaviourConstants=behaviour, snapshotEvidence=snaps, promotionProposal=promote,
        evidenceUpgrades=upgrades, notPromoted=not_promoted, writes=0, publication=publication(t, behaviour),
        nameFitPolicy='proposedName is a descriptive snake_case candidate whose length equals the hidden member-name '
            'length (the type library ships lengths only). It shows the reading is consistent with the layout; it is '
            'not a recovered name and is never published as an id without review. Public ids are semanticFieldId.')


def main() -> None:
    data = build()
    report.write(OUTPUT, data)
    counts = data['counts']
    print(json.dumps({'output': str(OUTPUT.relative_to(ROOT)), 'candidates': len(data['candidates']),
        'counts': counts, 'proposals': len(data['promotionProposal']),
        'snapshot': data['snapshotEvidence'].get('state'), 'writes': 0}, indent=2))


if __name__ == '__main__':
    main()
