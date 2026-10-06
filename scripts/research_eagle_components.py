"""Offline research: every Eagle-related structure of build F5FEE03DCFDB, compared across ALL Eagles
(docs/research/eagle-components-F5FEE03DCFDB.md -> research/eagle-components-F5FEE03DCFDB.json).

Read-only and reproducible: the pinned entity file and type library (scripts/scan/tables), the settings rows
(scripts/scan/settings), the game.dll image and the seven retained snapshots (scripts/scan/xref, instances). Nothing is
written to the game; no protection is changed. Research only: the report proposes promotions, it never promotes.

What it establishes (each with instruction pins, every pin re-checked byte for byte in all seven snapshots):

1. EagleComponentData (152 bytes, 36 members): one UNIQUE record per jet resource (10 jets, 11 records, record 10
   unowned). The per-Eagle matrix, the hidden-name lengths, the enum value names (alias-length match against the
   type-name dictionary), and which stratagem rows (and the DSS Eagle Storm spawner) name each jet.
2. The two native read paths:
   * the resolver 0x514B40 (strike, update, flight, init, removal): a per-entity copy in the Eagle manager
     (+0x70 map, +0xB0 array of 0x98-byte records) when one exists, otherwise the loaded type record;
   * the type lookup 0x514640 (dispatch-time planner 0x89EF70 and target acquisition 0x8A01A0, through 0x89EE70):
     ALWAYS the loaded type record (component world + 0xF12E78), never a per-entity copy.
   No clear-code routine inserts a per-entity copy (only removal, move, reserve and free touch the copy store) and no
   snapshot holds one: the "+0x70 per-jet copy" lead stays UNKNOWN for the Runtime's purposes.
3. Member semantics from the code that reads them (strike 0x8A4410, planner 0x89EF70, acquisition 0x8A01A0, init
   0x8A1920, tracking 0x8A37D0, update 0x8A7A90, stage 0x8A2990, removal 0x8A7D30), the native landing-pattern table
   (game.dll 0x328CF20: 8 patterns x {count, 12 XY offsets}), the per-entity extra-bomb stat (id 7, default 0) and
   the payload weapons (every jet's own 23 mm gun; the 110mm's two rocket pods and their magazine pattern).
4. Exact published checks against the wiki import (uses, cooldown, rearm, strike projectile rows, Strafing Run 100
   rounds / 25 HE / 4000 rpm / capacity 2000, Airstrike capacity 6 = its pattern's 6 points).
5. Ownership / lifecycle / safety classification, a promotion proposal and the not-promoted list.

Run: py scripts/research_eagle_components.py   (needs the datalibrary, the game.dll cache/snapshots)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from reference_format import dl_hash  # noqa: E402
from scan import compare, report, settings, tables, xref  # noqa: E402
from capstone import x86  # noqa: E402

OUTPUT = ROOT / 'research/eagle-components-F5FEE03DCFDB.json'
WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_offensive_stratagems.json'
CUSTOM_PAYLOADS = ROOT / 'research/custom-payloads-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap', 'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']

EAGLE_MANAGER = 0x3326650           # EagleComponent manager (research custom-payloads eagleManager)
WORLD = 0x346BF98                   # component world; + 0xF12E78 = the loaded EagleComponentData table
TYPE_TABLE = 0xF12E78
STRATAGEM_TABLE = 0x37CB600         # StratagemInfo rows by type (research stratagem-calldown)
PATTERN_TABLE, PATTERN_STRIDE, PATTERN_SLOTS, PATTERN_COUNT = 0x328CF20, 0x64, 12, 8
STAT_DEFAULTS, EXTRA_BOMB_STAT = 0x2141790, 7
ROW = {'type': 0x0, 'stableId': 0x4, 'deliveryKind': 0x3C, 'uses': 0x50, 'spawnTime': 0x54, 'cooldown': 0x68,
    'payloads': 0x98, 'payloadCount': 0xA0, 'linkedType': 0xC8}
EAGLE_REARM_TYPE = 49
MANAGER = {'capacity': 0x10, 'count': 0x1C, 'active': 0x20, 'partition': 0x24, 'handles': 0x48, 'records': 0x58,
    'recordStride': 0xFC, 'flight': 0x60, 'flightStride': 0x1C, 'copyMap': 0x70, 'copyMapCapacity': 0x78,
    'reverseMap': 0x90, 'copyCapacity': 0xA0, 'copyCount': 0xA8, 'copies': 0xB0, 'copyStride': 0x98}

# The catalogued Eagles (stable ids: research custom-payloads / offensive-stratagem-runtime) and the jets in data.
EAGLES = ['Eagle Strafing Run', 'Eagle Airstrike', 'Eagle Cluster Bomb', 'Eagle Napalm Airstrike',
    'Eagle Smoke Strike', 'Eagle 110mm Rocket Pods', 'Eagle 500kg Bomb', 'Eagle Gas Airstrike']
UNUSED_ROWS = {929878807: 'EAGLE. (NOT USED) ADDITIONAL STRAFING RUNS', 3001049275: 'EAGLE. (NOT USED) AIR-TO-AIR MISSLES'}
PODS = {'pod_right': 0x0E8C2515261E0325, 'pod_left': 0x486522867199D7F3}
GUNPOD, BOMB_RACK, MISSILE_CHILD = 0xFCE722B5EF57E4B6, 0xCE2A6CC6652237FF, 0xEBB32D4A2A4154B6

# ------------------------------------------------------------------------------------------------ instruction pins
# (rva, expected asm, role). Every pin is decoded from the image AND compared byte for byte in all seven snapshots.
PINS = {
    'resolver': [
        (0x514B62, 'mov r11, qword ptr [rip + 0x2e11ae7]', 'resolver: the Eagle manager [game+0x3326650]'),
        (0x514B97, 'mov rdi, qword ptr [r11 + 0x70]', 'resolver: the per-entity copy map (+0x70), keyed by entity'),
        (0x514BE2, 'imul rax, rax, 0x98', 'resolver: a copy is 0x98 bytes = the EagleComponentData record size'),
        (0x514BE9, 'add rax, qword ptr [r11 + 0xb0]', 'resolver: the copy array (+0xB0)'),
        (0x514BFC, 'jmp 0x514640', 'resolver: no copy -> the loaded TYPE record (0x514640)'),
    ],
    'typeLookup': [
        (0x51464F, 'mov r10, qword ptr [rax + 0xf12e78]', 'type lookup: the loaded EagleComponentData table (world+0xF12E78)'),
        (0x5146BC, 'imul rax, rcx, 0x98', 'type lookup: record stride 0x98 (152)'),
        (0x5146C3, 'add rax, 0x140', 'type lookup: records at +0x140 (after 20 index rows): the entity-file layout'),
    ],
    'copyStore': [
        (0x8A9DCE, 'mov dword ptr [rbx + 0xa8], ebp', 'component removal: the copy count (+0xA8) after a swap-remove'),
        (0x8A9DEF, 'mov r9, qword ptr [rbx + 0xb0]', 'component removal: moves the last copy into the removed slot'),
        (0x8A9A1B, 'cmp dword ptr [rbx + 0xa8], eax', 'reserve: rehash the copy map when the copies reach its load'),
    ],
    'strike': [
        (0x8A448D, 'call 0x514b40', 'strike (per active jet): r14 = the resolved EagleComponentData'),
        (0x8A44CF, 'mov eax, dword ptr [rax + 0x30]', '+0x30: the release-prediction tick resets to this interval'),
        (0x8A452F, 'mov eax, dword ptr [r14 + 0x10]', '+0x10: the payload kind selects the strike branch'),
        (0x8A4540, 'mov ecx, dword ptr [r8 + rax*4 + 0x8a59b0]', 'payload switch (jump table 0x8A59B0, kinds 1..6)'),
        (0x8A4561, 'movss xmm2, dword ptr [r14 + 0x78]', '+0x78: kinds 1-4 start the attack within this horizontal distance'),
        (0x8A47DE, 'movss xmm0, dword ptr [r14 + 0x78]', '+0x78: kind 5 (bombs) starts releasing within this distance'),
        (0x8A4D8A, 'cmp ebx, 0x14', 'kind 6 (CarpetBombing, unused): 20 projectiles, hard-coded 500 x 15 m'),
        (0x8A4E96, 'movss xmm0, dword ptr [r14 + 0x6c]', '+0x6C: strafe sweep length (aim walks t * this along the heading)'),
        (0x8A4EA0, 'movss xmm2, dword ptr [r14 + 0x28]', '+0x28: strafe duration (t = elapsed / this)'),
        (0x8A4F5C, 'comiss xmm9, xmm2', 'elapsed >= +0x28 ends the strafe'),
        (0x8A4F7F, 'mov ecx, dword ptr [r14 + 4]', '+0x04: audio event on the attack end'),
        (0x8A4FD6, 'movss xmm0, dword ptr [r14 + 0x74]', '+0x74: per-target dwell enabled when non-zero'),
        (0x8A5123, 'movss xmm1, dword ptr [r14 + 0x70]', '+0x70: a target within this distance of the sweep point is engaged'),
        (0x8A5135, 'divss xmm1, dword ptr [r14 + 0x74]', '+0x74: the engaged target\'s dwell budget falls by dt / this'),
        (0x8A517C, 'cmp ebx, 8', 'at most 8 tracked targets'),
        (0x8A526D, 'movss xmm1, dword ptr [r14 + 0x28]', '+0x28: rocket salvo duration'),
        (0x8A5283, 'divss xmm8, xmm0', 'rockets: the duration is split evenly between the tracked targets'),
        (0x8A5377, 'lea r12, [rip + 0x29e7ba2]', 'bombs: the native landing-pattern table 0x328CF20'),
        (0x8A5380, 'mov eax, dword ptr [r14 + 0x18]', '+0x18: the projectile spawned by EVERY release (read live)'),
        (0x8A5391, 'mov rax, qword ptr [r8 + rax*8 + 0x37c7670]', '+0x18: its ProjectileInfo row'),
        (0x8A53FB, 'movsxd rax, dword ptr [r14 + 0x14]', '+0x14: the landing pattern index (read live per release)'),
        (0x8A541C, 'imul rsi, rax, 0x64', 'pattern entry = 0x64 bytes: {u32 count, 12 x (x, y) metres}'),
        (0x8A5534, 'mov rcx, qword ptr [rsi + rax*8 + 4]', 'release i lands at pattern point i (rotated to the heading)'),
        (0x8A57EB, 'call 0x13a9830', 'SpawnProjectile (the jet is the source)'),
        (0x8A5821, 'inc dword ptr [rdi + 0x68]', 'per-jet release index'),
        (0x8A5824, 'addss xmm2, dword ptr [r14 + 0x2c]', '+0x2C: seconds between releases'),
        (0x8A57F8, 'mov r8d, 7', 'per-entity stat 7 (extra bombs) ...'),
        (0x8A583A, 'call 0xa079b0', '... from the stat manager [game+0x3326AC0] (default 0)'),
        (0x8A5844, 'add eax, dword ptr [rsi]', 'releases stop at pattern count + extra-bomb stat'),
        (0x8A5849, 'jae 0x8a5868', '... then the jet stops attacking'),
    ],
    'planner': [
        (0x6AC431, 'call 0x89ef70', 'the dispatcher (Eagle, delivery kind 0) plans the approach'),
        (0x89EFFF, 'call 0x89ee70', 'planner: a stack copy of the jet\'s TYPE record ...'),
        (0x89EE83, 'call 0x514640', '... from the type lookup (never a per-entity copy)'),
        (0x89F08E, 'mov esi, dword ptr [rbp - 0x60]', '+0x10: payload kind selects the hard-coded clearance height'),
        (0x89F0A4, 'movss xmm1, dword ptr [rip + 0x1b28ac4]', 'kind 6: 500 m (hard-coded)'),
        (0x89F0B8, 'movss xmm1, dword ptr [rip + 0x1b28730]', 'kinds 1-4 (and 5 with flag): 100 m (hard-coded)'),
        (0x89F0C8, 'movss xmm1, dword ptr [rip + 0x1b2862c]', 'kind 5: 50 m (hard-coded)'),
        (0x89F0EA, 'movss xmm10, dword ptr [rbp - 0x3c]', '+0x34: approach distance (minimum of the random range)'),
        (0x89F0FA, 'movss xmm0, dword ptr [rbp - 0x38]', '+0x38: approach distance (maximum)'),
        (0x89F136, 'mulss xmm14, dword ptr [rip + 0x1b273f9]', 'uniform random in [+0x34, +0x38] (LCG / 2^32)'),
        (0x89F109, 'movzx r12d, byte ptr [rbp - 0x50]', '+0x20: half-circle heading search (Eagle Airstrike only)'),
        (0x89F14E, 'movss xmm15, dword ptr [rip + 0x1b28171]', 'search arc pi when +0x20 is set ...'),
        (0x89F159, 'movss xmm15, dword ptr [rip + 0x1b2838a]', '... 2 pi otherwise'),
        (0x89F01D, 'movups xmm9, xmmword ptr [rax + 0x40]', '+0x40: number of approach headings tried'),
        (0x89F067, 'movss xmm0, dword ptr [rbp - 0x28]', '+0x48: the heading count under a world flag (+0x170 bit 1)'),
        (0x89F170, 'divss xmm15, xmm9', 'heading step = arc / count; tried as a, a+s, a-s, a+2s ...'),
        (0x89F1A6, 'movss xmm8, dword ptr [rbp - 0x54]', '+0x1C: approach heading offset ...'),
        (0x89F1B5, 'mulss xmm8, dword ptr [rip + 0x1b274a2]', '... degrees to radians (0.0174533): rotates the thrower->beacon direction'),
        (0x89F284, 'movss xmm1, dword ptr [rbp - 0x34]', '+0x3C: the approach start height ...'),
        (0x89F29A, 'addss xmm0, dword ptr [rdi + 8]', '... above the target point'),
        (0x89F3B9, 'movss xmm0, dword ptr [rbp + 8]', '+0x78: the engagement point probed by the clearance check'),
        (0x89F02E, 'movups xmm1, xmmword ptr [rax + 0x80]', '+0x80..+0x8C copied to [rbp+0x10] ...'),
        (0x89F54D, 'movss xmm11, dword ptr [rbp + 0x10]', '... +0x80: the clearance rays\' lateral offset'),
        (0x89F632, 'movss xmm7, dword ptr [rbp - 0x2c]', '+0x44: the clearance check extent along the approach'),
    ],
    'replan': [
        (0x89FCAD, 'movups xmm0, xmmword ptr [rax + 0x70]', 're-plan 0x89FC50 (type copy): +0x70..+0x7C to [rbp-0x40] ...'),
        (0x89FCE7, 'movss xmm2, dword ptr [rbp - 0x34]', '... +0x7C, used when the world flag (+0x170 bit 1) is set'),
    ],
    'acquisition': [
        (0x8A01F0, 'call 0x89ee70', 'target acquisition (dispatch): a stack copy of the TYPE record'),
        (0x8A0210, 'add ecx, -5', 'skipped for payload kinds 5 and 6 (bombs)'),
        (0x8A02D2, 'movss xmm9, dword ptr [rbp + 4]', '+0x24: the query radius around the beacon'),
        (0x8A02DF, 'mov r8d, 0x200', 'up to 512 query results'),
        (0x8A0310, 'call 0x8d6380', 'the overlap query'),
        (0x8A163D, 'cmp edx, 8', 'kept: the best 8 (insertion sort)'),
        (0x8A18D2, 'call 0xfd9af0', 'the kept targets\' ids are returned'),
    ],
    'init': [
        (0x8A19E1, 'call 0x514b40', 'jet init: resolved EagleComponentData'),
        (0x8A1C7F, 'mov eax, dword ptr [rax + 0xc]', '+0x0C: the flyby timer starts ready'),
        (0x8A1D91, 'movss xmm9, dword ptr [r9 + 0x4c]', '+0x4C: the jet\'s speed ...'),
        (0x8A1D97, 'movss dword ptr [r14 + 0xe0], xmm9', '... its current speed (runtime +0xE0)'),
        (0x8A1EB2, 'movsd qword ptr [r14 + 0xd4], xmm0', '... and initial velocity toward the aim point (runtime +0xD4)'),
        (0x8A1ECC, 'mov r9d, dword ptr [r9 + 0x84]', '+0x84: audio event at spawn'),
        (0x8A1DF0, 'mov eax, dword ptr [r9 + 0x58]', '+0x58 copied to the runtime record +0xE4 ...'),
        (0x8A1DFF, 'mov eax, dword ptr [r9 + 0x5c]', '... +0x5C to +0xE8 (their consumers are not traced)'),
    ],
    'update': [
        (0x8A7B7D, 'call 0x514b40', 'EagleComponent update: resolved data per active jet'),
        (0x8A7BBC, 'call 0x8a4410', '... runs the strike'),
        (0x8A7BE9, 'movss xmm2, dword ptr [r15 + 8]', '+0x08: flyby sound within this distance of the listener'),
        (0x8A7C17, 'comiss xmm3, dword ptr [r15 + 0xc]', '+0x0C: ... at most once per this many seconds'),
        (0x8A7C7D, 'mov ecx, dword ptr [r15]', '+0x00: the flyby sound event (0 for every Eagle)'),
    ],
    'tracking': [
        (0x8A383E, 'call 0x514b40', 'aim tracking: resolved EagleComponentData'),
        (0x8A3869, 'mov ecx, dword ptr [rax + 0x18]', '+0x18: the strike projectile ...'),
        (0x8A3887, 'movss xmm6, dword ptr [rcx + 0x20]', '... its velocity leads moving targets'),
        (0x8A3BCA, 'call 0x1741ea0', 'intercept solve'),
        (0x8A3CA2, 'mulss xmm11, dword ptr [rip + 0x1b237f9]', 'aim point follows at min(1, 5 dt) (hard-coded)'),
        (0x8A3E11, 'movss xmm10, dword ptr [rax + 0x6c]', '+0x6C / +0x28: the sweep point for the attack effect'),
        (0x8A3E1B, 'movss xmm7, dword ptr [rax + 0x28]', '+0x28'),
    ],
    'stage': [
        (0x8A2DEA, 'mov eax, dword ptr [rcx + 0x54]', '+0x54: speed in one stage (100)'),
        (0x8A2FA7, 'mov eax, dword ptr [rcx + 0x50]', '+0x50: speed in another stage (300)'),
        (0x8A2A67, 'mov rax, qword ptr [rdx + 0x90]', '+0x90: a resource used by the stage machine'),
        (0x8A61DA, 'movss xmm12, dword ptr [rdi + 0x80]', '+0x80: read by the flight model 0x8A59E0'),
    ],
    'removal': [
        (0x8A7DF1, 'call 0x514b40', 'component removal: resolved data'),
        (0x8A7DF9, 'mov r9d, dword ptr [rax + 0x88]', '+0x88: audio event at removal'),
    ],
    'attackSwitch': [
        (0x8A4DF6, 'mov ecx, dword ptr [r8 + rax*4 + 0x8a59c8]', 'attack phase switch (jump table 0x8A59C8): kinds '
            '1-2 strafe 0x8A4E03, 3 missile 0x8A530C, 4 rockets 0x8A525C, 5 bombs 0x8A535B, 6 stop'),
        (0x8A4E03, 'movsd xmm6, qword ptr [rdi + 0xd4]', 'strafe branch (kinds 1-2): the only strike reader of +0x6C'),
        (0x8A525C, 'mov eax, dword ptr [rdi + 0x10]', 'rocket branch (kind 4): reads +0x28 and the target count only'),
    ],
    'initArea': [
        (0x8A2539, 'call 0xa16a70', 'jet init calls the attack-area helper 0xA16A70 once per jet'),
        (0xA16AE4, 'call 0x514b40', 'attack-area helper: resolved EagleComponentData'),
        (0xA16AF3, 'mov ecx, dword ptr [rax + 0x18]', '+0x18: the strike projectile ...'),
        (0xA16B0B, 'mov eax, dword ptr [rcx + 0x90]', '... its impact explosion ...'),
        (0xA16B36, 'movss xmm6, dword ptr [rdi + 0x14]', '... whose outer radius ...'),
        (0xA16B3E, 'addss xmm6, dword ptr [rip + 0x19b08ca]', '... + 4 m is the area width'),
        (0xA16B79, 'movss xmm14, dword ptr [r14 + 0x6c]', '+0x6C: the area length along the attack line (none if 0)'),
        (0xA16B8E, 'comiss xmm14, xmm7', '+0x6C <= 0: no area (the 500kg)'),
    ],
}

# --------------------------------------------------------------------------------------- member interpretation
# Code-derived semantics. 'name' is a proposed snake_case name whose length MUST equal the hidden-name length (checked);
# None = no name proposed. 'consumers' name the pin groups that read the member. 'lifecycle': when the read happens.
LIVE = 'read live through the resolver (per-entity copy if one exists, else the type record) every update'
DISPATCH = 'read once per call at dispatch from the TYPE record (0x514640 via 0x89EE70); never a per-entity copy'
INIT = 'read once at jet init through the resolver'
SEMANTICS = {
    0x00: dict(name='flyby_sound', unit='audio event id', consumers=['update'], lifecycle=LIVE,
        meaning='flyby audio event played when the jet passes within +0x08 of the listener (0 = none: every Eagle)'),
    0x04: dict(name=None, unit='audio event id', consumers=['strike'], lifecycle=LIVE,
        meaning='audio event posted on the jet\'s emitter when a strafe/rocket attack ends (same value for all)'),
    0x08: dict(name='flyby_distance', unit='m', consumers=['update'], lifecycle=LIVE,
        meaning='horizontal distance from the listener under which the flyby sound plays'),
    0x0C: dict(name='flyby_cooldown', unit='s', consumers=['update', 'init'], lifecycle=LIVE,
        meaning='minimum time between flyby sounds (the timer starts at this value: ready at spawn)'),
    0x10: dict(name='payload', unit='EaglePayload', consumers=['strike', 'planner', 'acquisition', 'init', 'tracking'],
        lifecycle=LIVE + '; also read at dispatch from the type record',
        meaning='attack kind: 1 DoubleStrafe, 2 Strafe, 3 Missile, 4 Rocket, 5 Airstrike (bombs), 6 CarpetBombing'),
    0x14: dict(name='airstrike_pattern', unit='EagleAirstrikePattern', consumers=['strike'], lifecycle=LIVE + ' (per release)',
        meaning='bomb landing pattern: index into the native table 0x328CF20 (count + XY offsets in metres, '
            'rotated to the attack heading around the target); only payload 5 reads it'),
    0x18: dict(name='projectile_type', unit='ProjectileType', consumers=['strike', 'tracking'], lifecycle=LIVE + ' (per release)',
        meaning='the projectile every bomb release spawns (payload 5); its velocity leads targets (tracking). The 110mm\'s '
            'rockets are NOT spawned from it: they come from the mounted pods\' own weapons'),
    0x1C: dict(name='attack_angle', unit='degrees', consumers=['planner'], lifecycle=DISPATCH,
        meaning='approach heading relative to the thrower->beacon direction: 180 = along the throw (strafe, rockets, '
            '500kg), 90 = perpendicular (the bomb lines); the clearance search starts from it'),
    0x20: dict(name='approach_search_half_circle', unit='bool', consumers=['planner'], lifecycle=DISPATCH,
        meaning='heading search arc pi instead of 2 pi (Eagle Airstrike only)'),
    0x24: dict(name='target_radius', unit='m', consumers=['acquisition'], lifecycle=DISPATCH,
        meaning='target acquisition radius around the beacon (best 8 kept); payloads 1-4 only (5/6 skip it)'),
    0x28: dict(name='fire_duration', unit='s', consumers=['strike', 'tracking'], lifecycle=LIVE,
        meaning='strafe: attack duration (the gun fires until elapsed >= this); rockets: salvo duration split between '
            'the tracked targets. Bomb Eagles: read only by the attack-sound tracking'),
    0x2C: dict(name='drop_interval', unit='s', consumers=['strike'], lifecycle=LIVE + ' (per release)',
        meaning='seconds between consecutive bomb releases (payload 5)'),
    0x30: dict(name='release_predict_interval', unit='s', consumers=['strike'], lifecycle=LIVE,
        meaning='interval of the bomb-release check (ballistic prediction of the impact point) for payload 5'),
    0x34: dict(name='approach_distance_min', unit='m', consumers=['planner'], lifecycle=DISPATCH,
        meaning='approach start distance from the target: uniform random in [+0x34, +0x38]'),
    0x38: dict(name='approach_distance_max', unit='m', consumers=['planner'], lifecycle=DISPATCH,
        meaning='upper bound of the approach start distance'),
    0x3C: dict(name='approach_height', unit='m', consumers=['planner'], lifecycle=DISPATCH,
        meaning='approach start height above the target point'),
    0x40: dict(name='approach_attempts', unit='count (f32)', consumers=['planner'], lifecycle=DISPATCH,
        meaning='number of approach headings tried by the clearance search (step = arc / count)'),
    0x44: dict(name=None, unit='m', consumers=['planner'], lifecycle=DISPATCH,
        meaning='clearance check extent along the approach (ray geometry); exact role not isolated'),
    0x48: dict(name=None, unit='count (f32)', consumers=['planner'], lifecycle=DISPATCH,
        meaning='heading count used instead of +0x40 when a world flag (+0x170 bit 1) is set'),
    0x4C: dict(name='initial_velocity', unit='m/s', consumers=['init'], lifecycle=INIT,
        meaning='jet speed at spawn: initial velocity toward the aim point and current speed (runtime +0xE0)'),
    0x50: dict(name=None, unit='m/s', consumers=['stage'], lifecycle=LIVE, meaning='speed set by one stage transition (300)'),
    0x54: dict(name=None, unit='m/s', consumers=['stage'], lifecycle=LIVE, meaning='speed set by another stage transition (100)'),
    0x58: dict(name=None, unit=None, consumers=['init'], lifecycle=INIT, meaning='copied to runtime +0xE4 at init; consumer not traced'),
    0x5C: dict(name=None, unit=None, consumers=['init'], lifecycle=INIT, meaning='copied to runtime +0xE8 at init; consumer not traced'),
    0x60: dict(name=None, unit=None, consumers=[], lifecycle=None, meaning='no reader found in clear code'),
    0x64: dict(name=None, unit=None, consumers=[], lifecycle=None, meaning='no reader found in clear code'),
    0x68: dict(name=None, unit=None, consumers=[], lifecycle=None, meaning='no reader found in clear code'),
    0x6C: dict(name='attack_sweep_length', unit='m', consumers=['strike', 'tracking', 'initArea'], lifecycle=LIVE,
        meaning='strafe (payload 1-2 only): the aim sweeps this far along the heading over +0x28 seconds. Every jet '
            'also sizes an area along its attack line with it once at init (0xA16A70; width = the strike '
            'explosion\'s outer radius + 4 m), and the attack sound follows the sweep point (tracking)'),
    0x70: dict(name='strafe_target_capture_distance', unit='m', consumers=['strike'], lifecycle=LIVE,
        meaning='a tracked target within this distance of the sweep point is engaged'),
    0x74: dict(name='per_target_dwell_time_seconds', unit='s', consumers=['strike'], lifecycle=LIVE,
        meaning='each engaged target\'s dwell budget falls by dt / this (0 disables the budget)'),
    0x78: dict(name='attack_engagement_distance', unit='m', consumers=['strike', 'planner'], lifecycle=LIVE,
        meaning='the attack (strafe, rockets, bomb releases) starts when the jet is within this horizontal distance '
            'of the aim point; also the planner\'s clearance probe point'),
    0x7C: dict(name=None, unit=None, consumers=['replan'], lifecycle=DISPATCH,
        meaning='read by the flagged re-plan 0x89FC50 (world flag +0x170 bit 1); role not isolated'),
    0x80: dict(name=None, unit=None, consumers=['stage', 'planner'], lifecycle=LIVE,
        meaning='flight model 0x8A59E0 and the clearance rays\' lateral offset; role not isolated'),
    0x84: dict(name=None, unit='audio event id', consumers=['init'], lifecycle=INIT, meaning='audio event at spawn'),
    0x88: dict(name=None, unit='audio event id', consumers=['removal'], lifecycle=LIVE, meaning='audio event at removal'),
    0x90: dict(name=None, unit='resource', consumers=['stage'], lifecycle=LIVE, meaning='a resource used by the stage machine'),
}

# Phase A (approved for implementation): the public type-record fields. Per field: the member, its editable payload
# kinds (the native code reads it for them; other Eagles publish it read-only with the reason), the reader and when
# it reads, and an evidence-based range (justification published with it). Values outside are refused.
STRIKE_LIVE = ('the strike 0x8A4410 through the resolver 0x514B40 (no per-entity copy is ever made, so the type '
    'record): read live')
DISPATCH_TYPE = 'read once per call at dispatch, directly from the type record (0x514640 via 0x89EE70)'
PHASE_A = {
    'airstrike_pattern': dict(offset=0x14, storage='i32', type='integer', unit='pattern', min=0, max=7, kinds=(5,),
        reader=STRIKE_LIVE + ' at every bomb release (pin 0x8A53FB)', timing='live',
        range='0..7 are the eight entries of the native landing-pattern table (game.dll 0x328CF20); 8 is '
            'EagleAirstrikePattern_Count and would read past the table, so only 0..7 are accepted (integers)',
        notRead={2: 'The Strafing Run never reads it: the strike reads +0x14 only in its bomb branch (payload 5).',
            4: 'The 110mm Rocket Pods never read it: the strike reads +0x14 only in its bomb branch (payload 5).'}),
    'drop_interval': dict(offset=0x2C, storage='f32', type='number', unit='seconds', min=0.02, max=1.0, kinds=(5,),
        reader=STRIKE_LIVE + ' at every bomb release (pin 0x8A5824)', timing='live',
        range='native values 0.05 to 0.5 s (500kg 0.05, Cluster 0.1, the other bombers 0.2; 0.5 on the non-bomb jets). '
            'The release loop releases again in the same frame while the timer stays <= 0, so the minimum 0.02 s keeps '
            'releases on separate frames at 50 fps; the maximum 1.0 s is twice the largest native value and spreads '
            'an 8-bomb line over 7 s while the jet flies on (each bomb is still aimed at its pattern point)',
        notRead={2: 'The Strafing Run never reads it: +0x2C is read only by the bomb release (payload 5).',
            4: 'The 110mm Rocket Pods never read it: +0x2C is read only by the bomb release (payload 5).'}),
    'fire_duration': dict(offset=0x28, storage='f32', type='number', unit='seconds', min=0.1, max=6.0, kinds=(2, 4),
        reader=STRIKE_LIVE + ' every update of the attack (pins 0x8A4EA0, 0x8A526D)', timing='live',
        range='native 1.5 s (Strafing Run) and 2.0 s (110mm, Smoke); the strike divides by it (t = elapsed / '
            'duration), so it must stay above 0 (minimum 0.1 s, about 7 rounds); the maximum 6 s is 4x the Strafing '
            'Run: 400 rounds of its 2000-round magazine (which would last 30 s). The 110mm pods hold 3 rockets '
            'each, so beyond about 0.75 s the window only re-splits targets',
        notRead={5: 'Not an attack duration for a bomb Eagle: only the attack-sound tracking reads +0x28 for it; the '
            'bomb branch never does.'}),
    'attack_sweep_length': dict(offset=0x6C, storage='f32', type='number', unit='meters', min=0.0, max=200.0,
        kinds=(2,), reader=STRIKE_LIVE + ' every update of the strafe (pin 0x8A4E96); also sizes the init-time attack '
            'area (0xA16A70) of every jet', timing='live',
        range='native 60 m (Strafing Run; 0 on the 500kg, so 0 is a valid native value); the maximum 200 m is 3.3x '
            'the Strafing Run and stays inside its 600 m engagement distance (+0x78), where the strafe starts',
        notRead={4: 'Not a strafe sweep for the 110mm Rocket Pods: the rocket branch never reads +0x6C (it only sizes '
            'the init-time attack area and moves the attack sound).',
            5: 'Not a strafe sweep for a bomb Eagle: the bomb branch never reads +0x6C (it only sizes the init-time '
            'attack area and moves the attack sound).'}),
    'target_radius': dict(offset=0x24, storage='f32', type='number', unit='meters', min=1.0, max=300.0, kinds=(2, 4),
        reader='target acquisition 0x8A01A0 (pin 0x8A02D2), ' + DISPATCH_TYPE, timing='dispatch',
        range='native 20 m (110mm), 60 m (the other Eagles) and 300 m (the unused air-to-air missile jet): the maximum '
            'is the largest native value of the same query; the query returns at most 512 entities and keeps the '
            'best 8; 1 m is the minimum (a smaller radius finds nothing)',
        notRead={5: 'Target acquisition skips bomb Eagles (payload 5 and 6): +0x24 is never read for them.'}),
    'attack_angle': dict(offset=0x1C, storage='f32', type='number', unit='degrees', min=0.0, max=360.0,
        kinds=(2, 4, 5), reader='the approach planner 0x89EF70 (pins 0x89F1A6, 0x89F1B5), ' + DISPATCH_TYPE,
        timing='dispatch',
        range='a heading is meaningful over the full circle: 0..360 degrees relative to the thrower->beacon '
            'direction (native 90 = across the throw, 180 = along it); the planner starts its clearance search at '
            'this heading and turns away from it only when the approach is blocked',
        notRead={}),
}
PAYLOAD_NAMES = {1: 'double_strafe', 2: 'strafe', 3: 'missile', 4: 'rocket', 5: 'airstrike', 6: 'carpet_bombing'}


# Read-only interpretation of the runtime (per-jet, private) state the code uses; documented, never written.
RUNTIME_RECORD = {
    '+0x00': 'reset flag (the update clears it and skips the jet once)', '+0x08': 'stage machine state',
    '+0x0C': 'selected target index (9 = none)', '+0x10': 'tracked target count (<= 8)',
    '+0x14': '8 target entity ids', '+0x34': '8 per-target dwell budgets', '+0x54': 'aim point (x, y, z)',
    '+0x60': 'release timer', '+0x64': 'release-prediction tick timer', '+0x68': 'releases so far',
    '+0x6C': 'attack elapsed', '+0x70': 'attacking flag', '+0x71': 'attack started flag', '+0x72': 'flyby played',
    '+0x74': 'flyby timer', '+0x78': 'jet position', '+0x84': 'jet rotation (quaternion)',
    '+0xD4': 'jet velocity', '+0xE0': 'current speed', '+0xF8': 'audio emitter'}
FLIGHT_RECORD = {'+0x00': 'approach start position (planner output)', '+0x0C': 'target point at the call'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


# ------------------------------------------------------------------------------------------------ enums
def enum_alias_lengths(t: tables.EntityTables, name: str) -> dict[int, int]:
    """Enum value -> hidden alias name length, from the stripped type library (method of research booster)."""
    data = t.typelib_bytes
    header = struct.Struct('<4s8I')
    _, _, types, enums, members, values, aliases, _, _ = header.unpack_from(data)
    msize = t.library.member_size
    enum_hashes = header.size + 4 * types
    type_desc = enum_hashes + 4 * enums
    enum_desc = type_desc + 36 * types
    member_desc = enum_desc + 32 * enums
    values_at = member_desc + msize * members
    aliases_at = values_at + 16 * values
    offsets = set()
    for i in range(types):
        v = struct.unpack_from('<9I', data, type_desc + 36 * i)
        offsets.update(o for o in (v[0], v[8]) if o != 0xFFFFFFFF)
    for i in range(enums):
        v = struct.unpack_from('<IIB3xIIIII', data, enum_desc + 32 * i)
        offsets.update(o for o in (v[0], v[7]) if o != 0xFFFFFFFF)
    for m in range(members):
        offsets.update(o for o in struct.unpack_from('<3I', data, member_desc + msize * m)[:2] if o != 0xFFFFFFFF)
    for j in range(values):
        comment = struct.unpack_from('<IIQ', data, values_at + 16 * j)[1]
        if comment != 0xFFFFFFFF:
            offsets.add(comment)
    for j in range(aliases):
        n = struct.unpack_from('<II', data, aliases_at + 8 * j)[0]
        if n != 0xFFFFFFFF:
            offsets.add(n)
    ordered = sorted(offsets)
    index = {o: i for i, o in enumerate(ordered)}
    target = dl_hash(name)
    for i in range(enums):
        if struct.unpack_from('<I', data, enum_hashes + 4 * i)[0] != target:
            continue
        _, _, _, count, start, _, _, _ = struct.unpack_from('<IIB3xIIIII', data, enum_desc + 32 * i)
        out = {}
        for j in range(start, start + count):
            main, _, value = struct.unpack_from('<IIQ', data, values_at + 16 * j)
            offset = struct.unpack_from('<II', data, aliases_at + 8 * main)[0]
            out[value] = ordered[index[offset] + 1] - offset - 1
        return out
    raise ValueError(f'enum {name} absent')


def enum_names(t: tables.EntityTables, name: str) -> dict:
    """Each value with its alias length and the dictionary names of exactly that length. A value is resolved when
    one dictionary name fits only it, or the dictionary order agrees with the value order for equal lengths."""
    lengths = enum_alias_lengths(t, name)
    dictionary = [n for n in (t.folder.parent / 'hashes/dl_type_names.txt').read_text(encoding='utf-8').splitlines()
        if n.startswith(name + '_')]
    out = {}
    for value, length in sorted(lengths.items()):
        fits = [n for n in dictionary if len(n) == length]
        out[value] = {'aliasLength': length, 'candidates': fits}
    # order rule: if the dictionary lists names in value order, the k-th name of a length goes to the k-th value of it
    by_length = {}
    for value, length in sorted(lengths.items()):
        by_length.setdefault(length, []).append(value)
    for length, vals in by_length.items():
        names = [n for n in dictionary if len(n) == length]
        for k, value in enumerate(vals):
            if len(names) == len(vals):
                out[value]['name'] = names[k]
                out[value]['method'] = 'unique length' if len(vals) == 1 else 'dictionary order (equal lengths)'
            elif len(names) == 1 and len(vals) == 1:
                out[value]['name'] = names[0]
                out[value]['method'] = 'unique length'
            else:
                out[value]['name'] = None
                out[value]['method'] = f'{len(names)} names for {len(vals)} values of length {length}'
    return {str(k): v for k, v in out.items()}


# ------------------------------------------------------------------------------------------------ code helpers
class Code:
    def __init__(self):
        self.img = xref.CodeImage.from_snapshot('game.dll')
        lo, hi = 0x880000, 0xA20000
        sel = self.img.pdata[(self.img.pdata[:, 0] >= lo) & (self.img.pdata[:, 0] < hi)]
        self.roots = sorted(set(int(self.img.root(int(b)) or b) for b in sel[:, 0]))

    def fn_range(self, root):
        nxt = [s for s in self.roots if s > root]
        return root, (nxt[0] if nxt else root + 0x3000)

    def pins(self):
        out = {}
        for group, rows in PINS.items():
            out[group] = []
            for rva, asm, role in rows:
                pin = self.img.pin(rva, role, asm)
                pin['function'] = self.img.root(rva)
                out[group].append(pin)
        return out

    @staticmethod
    def _full(r):
        table = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp'}
        if r in table:
            return table[r]
        if r.startswith('r') and r[-1] in 'dwb' and r[1:-1].isdigit():
            return r[:-1]
        return r

    def _writes(self, ins):
        try:
            _, w = ins.regs_access()
            regs = {self._full(ins.reg_name(r)) for r in w}
        except Exception:
            regs = set()
        if ins.mnemonic == 'call':
            regs |= {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
        return regs

    def resolver_reads(self, root, call, window=60):
        """EagleComponentData member reads after a resolver call: registers aliasing its result, and registers
        reloaded from the stack slots it was spilled to (linear order; reviewed against the pins)."""
        start, end = self.fn_range(root)
        ins = self.img.disasm(start, end)
        k0 = next(k for k, i in enumerate(ins) if i.address == call)
        alias, slots, reads = {'rax'}, set(), set()

        def scan(seq, regs):
            regs = set(regs)
            for j in seq:
                for op in j.operands:
                    if (op.type == x86.X86_OP_MEM and op.mem.base and op.mem.index == 0 and j.mnemonic != 'lea'
                            and self._full(j.reg_name(op.mem.base)) in regs and 0 <= op.mem.disp < 0x98):
                        reads.add((j.address, op.mem.disp, j.mnemonic + ' ' + j.op_str))
                if j.mnemonic == 'mov' and len(j.operands) == 2:
                    d, s = j.operands
                    if d.type == x86.X86_OP_MEM and s.type == x86.X86_OP_REG and self._full(j.reg_name(s.reg)) in regs \
                            and d.mem.base and j.reg_name(d.mem.base) in ('rsp', 'rbp') and d.mem.index == 0:
                        slots.add((j.reg_name(d.mem.base), d.mem.disp))
                    if d.type == x86.X86_OP_REG and s.type == x86.X86_OP_REG and self._full(j.reg_name(s.reg)) in regs:
                        regs.add(self._full(j.reg_name(d.reg)))
                        continue
                regs -= self._writes(j)
                if not regs:
                    break
        scan(ins[k0 + 1:], alias)
        for k, j in enumerate(ins):
            if j.mnemonic == 'mov' and len(j.operands) == 2:
                d, s = j.operands
                if d.type == x86.X86_OP_REG and s.type == x86.X86_OP_MEM and s.mem.base and s.mem.index == 0 \
                        and (j.reg_name(s.mem.base), s.mem.disp) in slots:
                    scan(ins[k + 1:k + 1 + window], {self._full(j.reg_name(d.reg))})
        return sorted(reads)

    def access_scan(self):
        out = []
        for call in self.img.calls_to(0x514B40):
            root = self.img.root(call)
            reads = self.resolver_reads(root, call)
            out.append({'function': root, 'call': call,
                'members': sorted({hex(d) for _, d, _ in reads}, key=lambda x: int(x, 16)),
                'reads': [{'rva': a, 'offset': d, 'asm': s} for a, d, s in reads]})
        return out

    def pattern_table(self):
        raw = self.img.data[PATTERN_TABLE:PATTERN_TABLE + PATTERN_STRIDE * PATTERN_COUNT]
        entries = []
        for p in range(PATTERN_COUNT):
            at = p * PATTERN_STRIDE
            count = struct.unpack_from('<I', raw, at)[0]
            points = struct.unpack_from('<24f', raw, at + 4)
            pts = [[round(points[2 * k], 4), round(points[2 * k + 1], 4)] for k in range(PATTERN_SLOTS)]
            if not 0 < count <= PATTERN_SLOTS:
                raise ValueError(f'pattern {p}: count {count} outside 1..12')
            if any(any(v != 0 for v in pt) for pt in pts[count:]):
                raise ValueError(f'pattern {p}: non-zero point beyond its count')
            used = pts[:count]
            xs = [pt[0] for pt in used]
            ys = [pt[1] for pt in used]
            entries.append({'value': p, 'count': count, 'points': used,
                'alongTrack': [min(xs), max(xs)], 'lateral': [min(ys), max(ys)],
                'lengthMeters': round(max(xs) - min(xs), 4)})
        return {'rva': PATTERN_TABLE, 'stride': PATTERN_STRIDE, 'slots': PATTERN_SLOTS, 'entries': entries,
            'sha256': sha(raw)}

    def stat_default(self):
        return round(self.img.f32(STAT_DEFAULTS + 4 * EXTRA_BOMB_STAT), 6)

    def copy_inserters(self):
        """Clear-code writers of the copy count (+0xA8) and users of the copy array (+0xB0) next to a 0x98 stride:
        the evidence that no clear-code routine creates a per-entity EagleComponentData copy."""
        img = self.img
        lo, hi = img.text
        hits = []
        data = img.data
        at = data.find(b'\xa8\x00\x00\x00', lo, hi)
        eagle_roots = set(img.global_accessors(EAGLE_MANAGER))
        while at >= 0:
            for back in range(2, 8):
                s = at - back
                try:
                    ins = img.insn(s)
                except ValueError:
                    continue
                if s < at and s + ins.size >= at + 4:
                    op = ins.operands[0] if ins.operands else None
                    if op is not None and op.type == x86.X86_OP_MEM and op.mem.disp == 0xA8 \
                            and ins.mnemonic in ('inc', 'add', 'mov') and ins.reg_name(op.mem.base) not in ('rsp', 'rbp'):
                        root = img.root(s)
                        if 0x89E000 <= s < 0x8AE000 or root in eagle_roots:
                            hits.append({'rva': s, 'asm': ins.mnemonic + ' ' + ins.op_str, 'function': root})
                    break
            at = data.find(b'\xa8\x00\x00\x00', at + 1, hi)
        return hits


# ------------------------------------------------------------------------------------------------ snapshots
def snapshot_evidence(t: tables.EntityTables, pins_flat):
    import research_event_state as base
    from research_custom_payloads import rows_of
    eagle = t.component('EagleComponentData')
    table_bytes = eagle.body[:eagle.records_offset + eagle.count * eagle.record_size]
    out, rows_seen = [], None
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        try:
            g = mem.game
            bad = [p['rva'] for p in pins_flat if mem.read(g + p['rva'], len(p['bytes']) // 2).hex() != p['bytes']]
            m = mem.ptr(g + EAGLE_MANAGER)
            head = mem.read(m, 0xC0)
            u = lambda o: struct.unpack_from('<I', head, o)[0]
            world = mem.ptr(g + WORLD)
            table = mem.ptr(world + TYPE_TABLE)
            loaded = mem.read(table, len(table_bytes)) if table else None
            differing = []
            if loaded is not None and loaded != table_bytes:
                for record in range(eagle.count):
                    a = eagle.records_offset + record * eagle.record_size
                    if loaded[a:a + eagle.record_size] != table_bytes[a:a + eagle.record_size]:
                        differing.append(record)
            rows = rows_of(mem)
            catalogue = {}
            for type_, (p, sid) in rows.items():
                raw = mem.read(p, 0xD0)
                count = struct.unpack_from('<I', raw, ROW['payloadCount'])[0]
                lst = mem.ptr(p + ROW['payloads'])
                payloads = ['0x%016X' % mem.u64(lst + 8 * i) for i in range(min(count, 8))] if lst and count else []
                catalogue[type_] = {'stableId': sid, 'deliveryKind': struct.unpack_from('<I', raw, ROW['deliveryKind'])[0],
                    'uses': struct.unpack_from('<i', raw, ROW['uses'])[0],
                    'spawnTime': round(struct.unpack_from('<f', raw, ROW['spawnTime'])[0], 6),
                    'cooldown': round(struct.unpack_from('<f', raw, ROW['cooldown'])[0], 6),
                    'linkedType': struct.unpack_from('<I', raw, ROW['linkedType'])[0], 'payloads': payloads}
            if rows_seen is None:
                rows_seen = catalogue
            elif catalogue != rows_seen:
                raise ValueError(f'{name}: StratagemInfo rows differ from the first snapshot')
            out.append({'snapshot': name, 'pinMismatches': bad,
                'manager': {'capacity': u(MANAGER['capacity']), 'count': u(MANAGER['count']),
                    'active': u(MANAGER['active']), 'copyMapCapacity': u(MANAGER['copyMapCapacity']),
                    'copyCapacity': u(MANAGER['copyCapacity']), 'copyCount': u(MANAGER['copyCount'])},
                'typeTableLocated': table is not None,
                'typeTableEqualsEntityFile': loaded == table_bytes if loaded is not None else None,
                'typeRecordsDiffering': differing})
        finally:
            mem.close()
    return out, rows_seen


# ------------------------------------------------------------------------------------------------ wiki
def wiki_eagles():
    data = json.loads(WIKI.read_text(encoding='utf-8'))
    out = {}
    for s in data['stratagems']:
        if s['family'] != 'Eagle':
            continue
        st = s['stratagem']
        val = lambda k: (st.get(k) or {}).get('value') if isinstance(st.get(k), dict) else st.get(k)
        attacks = []
        for a in s['attacks']:
            p = a.get('projectile') or {}
            aoe = a.get('areaOfEffect') or {}
            v = lambda d, k: (d.get(k) or {}).get('value') if isinstance(d.get(k), dict) else d.get(k)
            attacks.append({'id': a['id'], 'name': a['name'], 'kind': a['wikiKind'],
                'massGrams': v(p, 'massGrams'), 'velocity': v(p, 'initialVelocityMetersPerSecond'),
                'drag': v(p, 'dragFactor'), 'gravity': v(p, 'gravityFactor'), 'lifetime': v(p, 'lifetimeSeconds'),
                'inner': v(aoe, 'innerRadiusMeters'), 'outer': v(aoe, 'outerRadiusMeters'),
                'shockwave': v(aoe, 'shockwaveRadiusMeters'), 'duration': v(aoe, 'durationSeconds'),
                'shrapnelCount': v(aoe, 'shrapnelCount')})
        weapon = {}
        for f in s.get('rawStructuredFields') or []:
            if f['section'].startswith('Detailed Weapon Statistics') and f['label'] in ('Fire Rate', 'Capacity', 'Spread'):
                weapon[f['label']] = f['raw']
        text = json.dumps(s.get('rawSections'), ensure_ascii=False)
        out[s['name']] = {'revision': s['wikiRevisionId'], 'callInTime': val('callInTimeSeconds'),
            'cooldown': val('cooldownSeconds'), 'uses': int(st['uses']) if st.get('uses') else None,
            'rearm': val('rearmTimeSeconds'), 'attacks': attacks, 'weapon': weapon,
            'strafeRoundsText': '100 rounds per use, with 25 of the rounds being high-explosive' in text}
    return out


# ------------------------------------------------------------------------------------------------ main
def main():
    t = tables.pinned()
    sv = settings.SettingsView(t)
    eagle = t.component('EagleComponentData')
    code = Code()
    pins = code.pins()
    pins_flat = [p for rows in pins.values() for p in rows]
    snaps, rows = snapshot_evidence(t, pins_flat)
    if any(s['pinMismatches'] for s in snaps):
        raise ValueError('pinned bytes differ in a snapshot: %r' % {s['snapshot']: s['pinMismatches'] for s in snaps})
    if not all(s['typeTableEqualsEntityFile'] for s in snaps):
        raise ValueError('a loaded EagleComponentData table differs from the entity file')

    # --- the catalogue: which stratagem rows name each jet
    known = json.loads(CUSTOM_PAYLOADS.read_text(encoding='utf-8'))['eagles']
    by_id = {r['stableId']: (type_, r) for type_, r in rows.items()}
    jets = t.with_component('EagleComponentData')
    jet_rows = {j: [] for j in jets}
    for type_, r in sorted(rows.items()):
        for p in r['payloads'][:1]:
            if int(p, 16) in jet_rows:
                jet_rows[int(p, 16)].append(type_)
    catalogue = {}
    index_rows = {resource: row for row, resource, _ in eagle.rows()}
    for name in EAGLES:
        k = known[name]
        type_, r = by_id[k['stableId']]
        jet = int(r['payloads'][0], 16)
        if '0x%016X' % jet != k['payload'].upper().replace('0X', '0x'):
            raise ValueError(f'{name}: payload[0] is not the reviewed jet')
        if r['deliveryKind'] != 0 or r['linkedType'] != EAGLE_REARM_TYPE:
            raise ValueError(f'{name}: not an Eagle row')
        record = eagle.record_of(jet)
        catalogue[name] = {'type': type_, 'stableId': k['stableId'], 'jet': '0x%016X' % jet, 'jetLabel': t.label(jet),
            'record': record, 'indexRow': index_rows[jet], 'ownerCount': len(eagle.owners(record)),
            'recordSha256': hashlib.sha256(eagle.raw(record)).hexdigest().upper(),
            'uses': r['uses'], 'cooldown': r['cooldown'], 'spawnTime': r['spawnTime'],
            'rowsNamingJet': jet_rows[jet]}
    unused = {}
    for sid, debug in UNUSED_ROWS.items():
        type_, r = by_id[sid]
        jet = int(r['payloads'][0], 16)
        unused[debug] = {'type': type_, 'stableId': sid, 'jet': '0x%016X' % jet, 'jetLabel': t.label(jet),
            'uses': r['uses'], 'selectable': False}
    rearm = rows[EAGLE_REARM_TYPE]

    # --- the DSS Eagle Storm spawner (EagleSpawnerComponentData)
    spawner = t.component('EagleSpawnerComponentData')
    spawners = []
    for rec in range(spawner.count):
        d = spawner.decode(rec)
        stype = d['20']
        names = [n for n, c in catalogue.items() if c['type'] == stype] + [n for n, c in unused.items() if c['type'] == stype]
        spawners.append({'record': rec, 'owners': [tables.hexid(o) for o in spawner.owners(rec)],
            'ownerComponents': {tables.hexid(o): sorted(t.entity(o)) for o in spawner.owners(rec)},
            'values': {k: v for k, v in d.items()}, 'stratagemType': stype, 'stratagems': names,
            'jet': rows[stype]['payloads'][0] if stype in rows else None})

    # --- labels: each jet by its stratagem(s)
    label_of = {}
    for j in jets:
        names = [n for n, c in catalogue.items() if int(c['jet'], 16) == j]
        names += [n for n, c in unused.items() if int(c['jet'], 16) == j and not names]
        label_of[j] = (names[0] if names else f'(no row) {t.label(j)}')
    ordered = [int(catalogue[n]['jet'], 16) for n in EAGLES] + sorted(j for j in jets if label_of[j] not in EAGLES)
    family = compare.Family(t, 'EagleComponentData', {label_of[j]: j for j in ordered})
    description = family.describe(include_constant=True)
    labels = description['entities']

    # --- enums
    enums = {n: enum_names(t, n) for n in ('EaglePayload', 'EagleAirstrikePattern', 'EagleStage')}

    # --- pattern table and its users
    patterns = code.pattern_table()
    pattern_names = enums['EagleAirstrikePattern']
    def encoded_count(enum_name):
        suffix = enum_name.split('_', 1)[1]
        if suffix == 'Single':
            return 1
        match = re.match(r'(?:Smoke_)?(\d+)', suffix)
        return int(match.group(1)) if match else None
    for e in patterns['entries']:
        info = pattern_names[str(e['value'])]
        e['name'] = info.get('name')
        e['aliasLength'] = info['aliasLength']
        # The dictionary names encode the bomb count ("6Z", "8line", "4line", "Single"): candidates of the right
        # alias length whose encoded count equals the native table's count.
        fits = [n for n in info['candidates'] if encoded_count(n) == e['count']]
        e['nameCandidatesByCount'] = fits
        if e['name'] is None and len(fits) == 1:
            e['name'], e['nameMethod'] = fits[0], 'alias length + encoded bomb count'
        elif e['name'] is not None:
            e['nameMethod'] = info['method']
            if encoded_count(e['name']) != e['count']:
                raise ValueError(f'pattern {e["value"]}: {e["name"]} does not encode its count {e["count"]}')
        else:
            e['nameMethod'] = (f'ambiguous: {len(fits)} names of length {e["aliasLength"]} encode {e["count"]}'
                if fits else f'no dictionary name of length {e["aliasLength"]} (uncracked)')
        e['usedBy'] = [label for label in labels
            if eagle.decode(family.component.record_of(dict(zip(labels, ordered))[label]))['16'] == 5
            and eagle.decode(family.component.record_of(dict(zip(labels, ordered))[label]))['20'] == e['value']]

    # --- layouts and fingerprints
    layout = [{'offset': m.offset, 'hex': '0x%02X' % m.offset, 'size': m.size, 'storage': m.storage,
        'nameLength': m.name_length, 'type': m.type_name} for m in eagle.members()]
    fingerprints = {c: t.fingerprint(c) for c in ('EagleComponentData', 'EagleSpawnerComponentData', 'MountComponentData',
        'ProjectileWeaponComponentData', 'WeaponMagazineComponentData', 'WeaponDataComponentData')}

    # --- per-Eagle matrix with strike projectile and patterns
    matrix = []
    for m in eagle.members():
        values = {label: family.matrix()[m.path]['values'][i] for i, label in enumerate(labels)}
        sem = SEMANTICS[m.offset]
        matrix.append({'offset': m.offset, 'hex': '0x%02X' % m.offset, 'storage': m.storage, 'nameLength': m.name_length,
            'type': m.type_name, 'values': {k: (round(v, 6) if isinstance(v, float) else v) for k, v in values.items()},
            'distinct': len({repr(v) for v in values.values()}), 'meaning': sem['meaning']})

    # --- payloads: projectile rows, explosions, mounts, weapons
    mount = t.component('MountComponentData')
    pw, mag, wd = (t.component(c) for c in ('ProjectileWeaponComponentData', 'WeaponMagazineComponentData',
        'WeaponDataComponentData'))
    def weapon(res):
        rec_pw, rec_mag, rec_wd = pw.record_of(res), mag.record_of(res), wd.record_of(res)
        out = {}
        if rec_pw is not None:
            raw = pw.raw(rec_pw)
            out['projectileWeapon'] = {'record': rec_pw, 'owners': len(pw.owners(rec_pw)),
                'projectile': struct.unpack_from('<I', raw, 0)[0],
                'rateSlots': [round(x, 3) for x in struct.unpack_from('<3f', raw, 4)]}
        if rec_mag is not None:
            d = mag.decode(rec_mag)
            pattern = [x for x in d['4.0'] if x]
            out['magazine'] = {'record': rec_mag, 'owners': len(mag.owners(rec_mag)), 'mode': d['0'],
                'pattern': pattern, 'altRound': d['4.128'], 'capacity': d['136']}
        if rec_wd is not None:
            raw = wd.raw(rec_wd)
            out['weaponData'] = {'record': rec_wd, 'owners': len(wd.owners(rec_wd)),
                'spread': [round(x, 3) for x in struct.unpack_from('<2f', raw, 84)]}
        return out
    payloads = {}
    for label, j in zip(labels, ordered):
        d = eagle.decode(eagle.record_of(j))
        proj = d['24']
        row = sv.decode('projectile', proj) if proj else None
        mounts = []
        rec = mount.record_of(j)
        if rec is not None:
            md = mount.decode(rec)
            for i in range(5):
                res = md[f'0[{i}].0']
                if res:
                    mounts.append({'slot': i, 'resource': tables.hexid(res), 'label': t.label(res),
                        'node': t.thin.get(md[f'0[{i}].8']), 'side': md[f'0[{i}].12'],
                        'components': sorted(t.entity(res)), 'weapon': weapon(res) or None})
        entry = {'jet': tables.hexid(j), 'jetLabel': t.label(j), 'record': eagle.record_of(j),
            'payload': d['16'], 'payloadName': enums['EaglePayload'][str(d['16'])].get('name'),
            'pattern': d['20'], 'patternName': pattern_names[str(d['20'])].get('name'),
            'patternCount': patterns['entries'][d['20']]['count'] if d['16'] == 5 else None,
            'strikeProjectile': proj, 'jetGun': weapon(j), 'mounts': mounts}
        if row:
            entry['projectileRow'] = {'velocity': round(row['32'], 4), 'mass': round(row['36'], 4),
                'drag': round(row['40'], 4), 'gravity': round(row['44'], 4), 'lifetime': round(row['52'], 4),
                'damage': row['60'], 'impactExplosion': row['144'], 'expiryExplosion': row['156']}
            for key in ('impactExplosion', 'expiryExplosion'):
                x = entry['projectileRow'][key]
                if x:
                    xd = sv.decode('explosion', x)
                    entry['projectileRow'][key + 'Row'] = {'damage': xd['4'], 'inner': round(xd['16'], 4),
                        'outer': round(xd['20'], 4), 'shockwave': round(xd['24'], 4), 'shrapnelCount': xd['80'],
                        'shrapnelProjectile': xd['84'], 'template': xd['100'], 'duration': round(xd['104'], 4)}
        payloads[label] = entry
    pod_rounds = {p: sv.decode('projectile', p) for p in (82, 146)}
    pod_round_rows = {str(p): {'velocity': round(r['32'], 4), 'mass': round(r['36'], 4), 'gravity': round(r['44'], 4),
        'damage': r['60'], 'impactExplosion': r['144'], 'impactRow': {k: (round(v, 4) if isinstance(v, float) else v)
            for k, v in sv.decode('explosion', r['144']).items() if k in ('4', '16', '20', '24')}}
        for p, r in pod_rounds.items()}

    # --- wiki checks
    wiki = wiki_eagles()
    checks = []
    def check(subject, field, native, published, exact, note=''):
        checks.append({'subject': subject, 'field': field, 'native': native, 'published': published,
            'exact': bool(exact), 'note': note})
    for name in EAGLES:
        w, c, p = wiki[name], catalogue[name], payloads[name]
        check(name, 'uses (StratagemInfo +0x50)', c['uses'], w['uses'], c['uses'] == w['uses'])
        check(name, 'cooldown (StratagemInfo +0x68)', c['cooldown'], w['cooldown'], c['cooldown'] == w['cooldown'])
        check(name, 'rearm (Eagle Rearm +0x68)', rearm['cooldown'], w['rearm'], rearm['cooldown'] == w['rearm'])
        first = next((a for a in w['attacks'] if a['kind'] == 'Projectile'), None)
        if name == 'Eagle Strafing Run':
            gun = p['jetGun']
            row16 = sv.decode('projectile', gun['projectileWeapon']['projectile'])
            check(name, 'gun projectile velocity / mass / drag (row of ProjectileWeapon +0)',
                [round(row16['32'], 3), round(row16['36'], 3), round(row16['40'], 3)],
                [first['velocity'], first['massGrams'], first['drag']],
                [round(row16['32'], 3), round(row16['36'], 3), round(row16['40'], 3)] == [first['velocity'], first['massGrams'], first['drag']])
            rpm = gun['projectileWeapon']['rateSlots'][1]
            check(name, 'gun rate (ProjectileWeapon rate slot Y)', rpm, w['weapon'].get('Fire Rate'), w['weapon'].get('Fire Rate') == f'{int(rpm)} rpm')
            check(name, 'gun magazine capacity', gun['magazine']['capacity'], w['weapon'].get('Capacity'),
                str(gun['magazine']['capacity']) == w['weapon'].get('Capacity'))
            dur = eagle.decode(c['record'])['40']
            rounds = dur * rpm / 60.0
            check(name, 'rounds per run = EagleComponentData +0x28 x rate / 60', round(rounds, 4), 100 if w['strafeRoundsText'] else None,
                abs(rounds - 100) < 1e-4 and w['strafeRoundsText'], 'wiki: "fires a burst of 100 rounds per use"')
            he = gun['magazine']['pattern']
            share = sum(1 for x in he if sv.decode('projectile', x)['144']) / len(he)
            check(name, 'high-explosive share = magazine pattern rounds with an impact explosion', share, 0.25,
                abs(share - 0.25) < 1e-9 and w['strafeRoundsText'], 'wiki: "25 of the rounds being high-explosive"')
            check(name, 'gun spread (WeaponData +84/+88)', gun['weaponData']['spread'], w['weapon'].get('Spread'),
                gun['weaponData']['spread'] == [10.0, 10.0] and '10.00' in (w['weapon'].get('Spread') or ''))
        elif first:
            r = p['projectileRow']
            native = [r['velocity'], r['mass'], r['drag'], r['gravity']]
            published = [first['velocity'], first['massGrams'], first['drag'], first['gravity']]
            check(name, 'strike projectile (EagleComponentData +0x18) velocity / mass / drag / gravity',
                native, published, all(abs(a - b) < 1e-3 for a, b in zip(native, published)))
            boom = next((a for a in w['attacks'] if a['kind'] == 'Explosion'), None)
            xrow = r.get('impactExplosionRow') or r.get('expiryExplosionRow')
            if name == 'Eagle 500kg Bomb':
                xrow = r.get('expiryExplosionRow')
            if boom and xrow:
                nat = [xrow['inner'], xrow['outer'], xrow['shockwave']]
                pub = [boom['inner'], boom['outer'], boom['shockwave']]
                check(name, 'its explosion radii (inner / outer / shockwave)', nat, pub,
                    all(abs(a - b) < 1e-3 for a, b in zip(nat, pub)))
                if boom['duration'] is not None:
                    check(name, 'its explosion area duration (explosion +104)', xrow['duration'], boom['duration'],
                        abs(xrow['duration'] - boom['duration']) < 1e-3)
                if boom['shrapnelCount'] is not None:
                    check(name, 'its explosion shrapnel count (explosion +80)', xrow['shrapnelCount'],
                        boom['shrapnelCount'], xrow['shrapnelCount'] == boom['shrapnelCount'])
            if first.get('lifetime') is not None:
                check(name, 'strike projectile lifetime (projectile +52)', r['lifetime'], first['lifetime'],
                    abs(r['lifetime'] - first['lifetime']) < 1e-3)
        if w['weapon'].get('Capacity') and name == 'Eagle Airstrike':
            check(name, 'bombs per strike = native pattern count of EagleComponentData +0x14', p['patternCount'],
                int(w['weapon']['Capacity']), p['patternCount'] == int(w['weapon']['Capacity']),
                'wiki "Detailed Weapon Statistics > Eagle Airstrike > Weapon > Capacity 6"')
    if not all(ch['exact'] for ch in checks):
        raise ValueError('a published check failed: %r' % [c for c in checks if not c['exact']])

    # --- access scan and copy evidence
    accesses = code.access_scan()
    inserters = code.copy_inserters()
    if any(h['asm'].startswith(('inc', 'add')) for h in inserters):
        raise ValueError('a clear-code routine increments the Eagle copy count: %r' % inserters)

    # --- candidates
    candidates = []
    pubs = {0x14: True, 0x18: True, 0x28: True}
    pub_notes = {0x14: 'Eagle Airstrike: wiki capacity 6 = pattern 0 count 6 (exact)',
        0x18: 'every strike projectile row matches the wiki projectile branch (velocity, mass, drag, gravity) exactly',
        0x28: 'Strafing Run: 1.5 s x 4000 rpm / 60 = 100 rounds = the wiki\'s "100 rounds per use" (derived exact)'}
    for row in matrix:
        sem = SEMANTICS[row['offset']]
        name = sem['name']
        values = row['values']
        code_read = bool(sem['consumers']) and sem['lifecycle'] is not None and row['offset'] not in (0x58, 0x5C, 0x60, 0x64, 0x68)
        evidence = {'codeRead': code_read, 'publishedExact': pubs.get(row['offset'], False), 'liveTest': False,
            'nameLengthFit': name is not None and len(name) == row['nameLength'],
            'differential': row['distinct'] > 1}
        if name is not None and len(name) != row['nameLength']:
            raise ValueError(f'proposed name {name} does not fit length {row["nameLength"]}')
        notes = [sem['meaning']]
        if row['offset'] in pub_notes:
            notes.append(pub_notes[row['offset']])
        if row['distinct'] == 1:
            notes.append('constant across every jet: no differential (cannot exceed UNKNOWN by the rules without a '
                'published value or a live test)')
        status = 'code-proven' if code_read else (
            'read (copied to the runtime record), effect not traced' if sem['consumers'] else 'layout-only')
        candidates.append(report.candidate('EagleComponentData+' + row['hex'], row['offset'], row['storage'],
            row['nameLength'], 'enum' if row['storage'].startswith('ENUM') else 'float' if row['storage'] == 'FP32' else 'int',
            values, evidence, ('hd2.fields.eagle.' + name) if name else None, notes,
            semanticStatus=status,
            unit=sem['unit'], lifecycle=sem['lifecycle'], consumers=sem['consumers'],
            proposedLocalName=name))
        candidates[-1]['proposedNameLengthFit'] = evidence['nameLengthFit'] if name else None

    # --- classification
    classification = {
        'EagleComponentData type record': {
            'owner': 'EagleComponentData (152 bytes); one record per jet resource, never shared between jets '
                '(shared records: 0)',
            'sharing': 'unique per jet TYPE, shared by every call of that jet: every player\'s call of the stratagem on '
                'this machine; eagle_base also by the unused DSS strafing row (type 35); gas and napalm also by the DSS '
                'Eagle Storm spawner (EagleSpawnerComponentData records 1 and 2); eagle_base by spawner record 0 '
                '(type 35)',
            'lifecycle': 'loaded verbatim from the entity file (all 7 snapshots: equal bytes); read live by the strike '
                'every update (resolver) and once per call at dispatch (type lookup)',
            'writeSemantics': 'a type-record write changes all FUTURE calls of THAT Eagle stratagem (live fields also '
                'the jets already in flight); never another Eagle',
            'safetyClass': 'type-record write, host machine only, guarded like the other hd2.stratagem fields'},
        'per-entity EagleComponentData copy (manager +0x70/+0xB0)': {
            'owner': 'Eagle manager [game+0x3326650]', 'sharing': 'private per jet entity (if it existed)',
            'lifecycle': 'UNKNOWN: preferred by the resolver, removed with the jet; no clear-code creator; 0 copies in '
                'all 7 snapshots; the dispatch-time readers never use it',
            'writeSemantics': 'none available', 'safetyClass': 'not usable (no proven creation path)'},
        'jet runtime record (manager +0x58, 0xFC per jet)': {
            'owner': 'Eagle manager', 'sharing': 'private per jet entity', 'lifecycle': 'created with the jet, swap-removed',
            'writeSemantics': 'runtime state rewritten every update (aim, timers, targets); not a configuration surface',
            'safetyClass': 'read-only'},
        'jet gun (the jet\'s own ProjectileWeapon / magazine / WeaponData)': {
            'owner': 'ProjectileWeaponComponentData / WeaponMagazineComponentData of the jet resource',
            'sharing': 'unique record per jet type; eagle_base\'s gun also serves the DSS strafing row',
            'lifecycle': 'type record unless a game-made per-instance copy exists (0x61AF10 / 0x770B10, research pelican)',
            'writeSemantics': 'per instance: the reviewed custom_weapons path on the captured jet (game-made private '
                'copies); type record: all future calls of that Eagle',
            'safetyClass': 'per-instance safe (existing reviewed copy routines); only payload 2 (Strafe) fires it'},
        '110mm pods (mounted children, payload_right / payload_left)': {
            'owner': 'ProjectileWeapon / magazine records of 0x0E8C2515261E0325 and 0x486522867199D7F3',
            'sharing': 'unique per pod type; only the 110mm jet mounts them',
            'lifecycle': 'spawned with each jet by the mount component; private per call; no reload component',
            'writeSemantics': 'per instance through the pods the call\'s jet mount record names (custom_eagles '
                'bind_rockets already finds them); type record: all future 110mm calls',
            'safetyClass': 'per-instance safe via the existing weapon/magazine copy routines'},
        'pattern table (game.dll 0x328CF20)': {
            'owner': 'game.dll read-only data', 'sharing': 'global: every bomb Eagle', 'lifecycle': 'static',
            'writeSemantics': 'never written (code image)', 'safetyClass': 'read-only; selecting a different entry via '
                '+0x14 is the safe lever'},
        'extra-bomb stat (stat 7, manager [game+0x3326AC0])': {
            'owner': 'per-entity stat modifiers', 'sharing': 'private per jet', 'lifecycle': 'per entity; default 0',
            'writeSemantics': 'none proven (creation of a stat record is native)', 'safetyClass': 'lead only'},
        'StratagemInfo row': {
            'owner': 'StratagemInfo by type (game.dll table 0x37CB600)', 'sharing': 'unique per stratagem; Eagle Rearm '
                'row shared by all Eagles', 'lifecycle': 'type data', 'writeSemantics': 'existing reviewed fields',
            'safetyClass': 'existing (stratagem.cooldown, eagle.uses_per_rearm, eagle.rearm_time allow_shared)'},
    }

    # --- proposal
    bombers = [n for n in EAGLES if payloads[n]['payload'] == 5]
    def field(local, offset, typ, unit, constraints, applies, write, ack, phase, expected, extra=None):
        cand = next(c for c in candidates if c['offset'] == offset)
        if cand['confidence'] != expected:
            raise ValueError(f'{local}: computed confidence {cand["confidence"]} != reviewed {expected}')
        if cand['proposedLocalName'] != local:
            raise ValueError(f'{local}: not the candidate\'s proposed name {cand["proposedLocalName"]}')
        item = {'id': 'hd2.fields.eagle.' + local, 'native': {'component': 'EagleComponentData', 'offset': offset,
            'hex': '0x%02X' % offset, 'storage': cand['storage'], 'hiddenNameLength': cand['nameLength']},
            'nameLengthFit': len(local) == cand['nameLength'], 'type': typ, 'unit': unit,
            'appliesTo': applies, 'constraints': constraints, 'writeSemantics': write, 'acknowledgements': ack,
            'phase': phase, 'confidence': cand['confidence'], 'evidence': cand['evidence'],
            'lifecycle': cand['lifecycle'], 'consumers': cand['consumers'],
            'pins': [p['rva'] for group in cand['consumers'] for p in pins.get(group, [])
                if re.search(r'(?<![\w\[])\+0x%02X(?![0-9A-Fa-f])' % offset, p['role'])],
            'vanilla': {n: cand['values'][n] for n in applies}}
        if extra:
            item.update(extra)
        if not item['nameLengthFit']:
            raise ValueError(item['id'] + ' does not fit its hidden-name length')
        if not item['pins'] and phase != 'read-only':
            raise ValueError(item['id'] + ' has no instruction pin naming its member')
        return item
    type_write = ('type-record write: every future call of THAT Eagle stratagem on this machine (all players\' calls of '
        'it, and for live fields the jets already in flight); no other Eagle is affected')
    phase_ack = ['allow_unverified_effect (until a live test passes)',
        'allow_shared only for the shared jets (Strafing Run, Gas, Napalm: see publication.eagles[].otherConsumers)']
    def phase_a(local, typ, unit, expected, extra=None):
        policy = PHASE_A[local]
        applies = [n for n in EAGLES if payloads[n]['payload'] in policy['kinds']]
        constraints = {'min': policy['min'], 'max': policy['max'], 'reason': policy['range']}
        write = type_write if policy['timing'] == 'live' else type_write.replace(
            'and for live fields the jets already in flight', 'read at dispatch only')
        return field(local, policy['offset'], typ, unit, constraints, applies, write, phase_ack, 'A', expected, extra)
    proposal = [
        phase_a('airstrike_pattern', 'integer enum', 'EagleAirstrikePattern (0..7)', 'CONFIRMED',
            {'derived': {'eagle.bombs_per_strike': 'read-only: the selected pattern\'s count (+ the per-jet extra-bomb '
                'stat, default 0)'}}),
        phase_a('drop_interval', 'number', 'seconds', 'STRONG'),
        phase_a('fire_duration', 'number', 'seconds', 'CONFIRMED',
            {'derived': {'eagle.strafe_rounds_per_run': 'read-only: fire_duration x the jet gun\'s rate / 60 (100)'}}),
        phase_a('attack_sweep_length', 'number', 'meters', 'STRONG'),
        phase_a('target_radius', 'number', 'meters', 'STRONG'),
        phase_a('attack_angle', 'number', 'degrees', 'STRONG'),
        field('projectile_type', 0x18, 'enum', 'ProjectileType (catalogued strike projectiles only)',
            {'values': 'the strike projectile of a catalogued Eagle whose package is loaded this mission',
                'reason': 'the projectile\'s unit/effects must be loaded; a raw id is refused (custom-payloads rule)'},
            bombers, type_write, ['allow_shared', 'package check (loaded)'], 'B', 'CONFIRMED',
            {'note': 'the 110mm reads it only to lead targets; its rockets come from the pods'}),
        field('approach_distance_min', 0x34, 'number', 'meters', {'min': 300.0, 'max': 2000.0,
            'rule': 'min <= max; min > attack_engagement_distance'}, EAGLES,
            type_write.replace('and for live fields the jets already in flight', 'read at dispatch only'),
            ['allow_shared', 'allow_unverified_effect'], 'C', 'STRONG'),
        field('approach_distance_max', 0x38, 'number', 'meters', {'min': 300.0, 'max': 2000.0}, EAGLES,
            type_write.replace('and for live fields the jets already in flight', 'read at dispatch only'),
            ['allow_shared', 'allow_unverified_effect'], 'C', 'STRONG'),
        field('approach_height', 0x3C, 'number', 'meters', {'min': 100.0, 'max': 2000.0}, EAGLES,
            type_write.replace('and for live fields the jets already in flight', 'read at dispatch only'),
            ['allow_shared', 'allow_unverified_effect'], 'C', 'STRONG'),
        field('attack_engagement_distance', 0x78, 'number', 'meters', {'min': 50.0, 'max': 1000.0,
            'rule': '< approach_distance_min'}, EAGLES, type_write, ['allow_shared', 'allow_unverified_effect'], 'C', 'STRONG'),
        field('payload', 0x10, 'enum (read-only)', 'EaglePayload', {'writable': False,
            'reason': 'the kind selects the jet\'s mounts and branches; a jet lacks the other kinds\' children'},
            EAGLES, 'read-only', [], 'read-only', 'STRONG'),
    ]
    per_instance = [
        {'id': 'custom Eagle (Strafing Run donor): the jet\'s own gun', 'path': 'custom_weapons.configure on the captured '
            'jet (ProjectileWeapon / magazine / WeaponData world record)', 'fields': ['projectile', 'rpm',
            'magazine pattern off / chambered round', 'spread'],
            'why': 'the jet carries a ProjectileWeapon component; the reviewed copy routines make private copies (live '
                'proven on sentries and the Pelican); only payload 2 fires it',
            'status': 'proposal; needs the coordinator (runtime/custom_eagles.lua is out of scope here)'},
        {'id': 'custom Eagle (110mm donor): the call\'s two pods', 'path': 'custom_weapons.configure on the pods the '
            'captured jet\'s mount record names', 'fields': ['projectile', 'rpm', 'magazine pattern off', 'capacity '
            '(rockets per pod)'],
            'why': 'private per call (spawned with the jet); the existing bind_rockets already identifies them; fixes '
                'the 146/146/82 pattern lead below',
            'status': 'proposal; live test required'},
    ]
    not_promoted = []
    for c in candidates:
        local = c.get('proposedLocalName')
        if local in [p['id'].rsplit('.', 1)[1] for p in proposal]:
            continue
        reason = []
        if c['semanticStatus'] == 'layout-only':
            reason.append('no reader found in clear code (layout only)')
        if not c['evidence']['differential']:
            reason.append('constant across every jet (no differential, no published value)')
        if c['unit'] == 'audio event id' or c['unit'] == 'resource':
            reason.append('presentation/audio hash, not a gameplay value')
        if c['offset'] in (0x20, 0x40, 0x44, 0x48, 0x7C, 0x80):
            reason.append('internal clearance-search parameter of the planner; no author-facing meaning')
        if c['offset'] in (0x50, 0x54):
            reason.append('stage-machine speed whose stage is not identified')
        not_promoted.append({'member': c['path'], 'confidence': c['confidence'], 'reasons': reason or ['not requested']})
    not_promoted += [
        {'member': 'per-entity EagleComponentData copy', 'confidence': 'UNKNOWN',
            'reasons': ['no clear-code creator; never present in a snapshot; dispatch readers ignore it']},
        {'member': 'call-in time', 'confidence': 'UNKNOWN', 'reasons': ['StratagemInfo +0x54 (spawn time) is 0 for '
            'every Eagle: the wiki call-in time is emergent (approach distance, speed, engagement distance, fall time)']},
        {'member': 'Eagle cooldown / rearm per instance', 'confidence': 'CONFIRMED',
            'reasons': ['already exposed as type fields (stratagem.cooldown, eagle.rearm_time allow_shared); no '
                'per-instance surface']},
        {'member': 'pattern points (game.dll 0x328CF20)', 'confidence': 'CONFIRMED',
            'reasons': ['code image data: never written; choose a pattern through airstrike_pattern instead']},
        {'member': 'CarpetBombing (payload 6)', 'confidence': 'CONFIRMED',
            'reasons': ['no Eagle uses it; its 20 projectiles and 500 x 15 m carpet are hard-coded']},
        {'member': 'EagleSpawnerComponentData (DSS Eagle Storm)', 'confidence': 'PLAUSIBLE',
            'reasons': ['not a player stratagem; owners are unnamed DSS entities (LoadoutPackage + DangerWarning)']},
    ]
    leads = [
        {'id': '110mm pod magazine pattern', 'confidence': 'STRONG',
            'finding': 'both pods\' magazines are in pattern mode (+0 = 1) with rounds [146, 146, 82] and capacity 3. '
                'The pattern mechanism is code-proven (research pelican: the chambered round follows the pattern after '
                'every shot). So each pod plausibly fires 146, 146, 82: 4 of the 6 rockets are projectile 146 (impact '
                'explosion 109, same damage 403 and radii as 229). The custom Eagle (custom-payloads section 8) converts '
                'only projectile 82.',
            'evidence': {'pods': payloads['Eagle 110mm Rocket Pods']['mounts'], 'rounds': pod_round_rows},
            'next': 'live trace of one vanilla 110mm call: count rockets by type and source pod'},
        {'id': 'extra-bomb stat 7', 'confidence': 'STRONG',
            'finding': 'bomb releases stop at pattern count + stat 7 of the jet entity (default 0; only the Eagle strike '
                'reads stat 7). Matches the XXL Weapons Bay text (+1 bomb for multi-bomb Eagles); extra bombs land on '
                'the zero points after the pattern\'s count (the target point)', 'statDefault': code.stat_default()},
        {'id': 'Eagle Smoke Strike pattern', 'confidence': 'CONFIRMED',
            'finding': 'its record selects pattern 3 (8line_ClusterBomb geometry, 8 bombs over 35 m) although the '
                'table has a dedicated Smoke_6Z (value 1, 6 bombs over 41 m) that no Eagle uses'},
        {'id': 'per-jet copy +0x70', 'confidence': 'UNKNOWN',
            'finding': 'resolver prefers it; only removal/move/reserve/free touch the store in clear code; the creator, if '
                'any, is registered indirectly (likely in protected code). Not usable.', 'clearCodeCopyCountWriters': inserters},
        {'id': 'DSS Eagle Storm', 'confidence': 'PLAUSIBLE',
            'finding': 'EagleSpawnerComponentData (3 records: 30/45, 3/5/160 and StratagemType 35/126/133) spawns '
                'strafing (eagle_base), gas and napalm Eagles: their type records are also read by those strikes'},
    ]
    live_tests = [
        {'id': 'eagle.airstrike_pattern', 'setup': 'Eagle Airstrike, airstrike_pattern 0 -> 2 (8Z), host solo',
            'expect': '8 bombs instead of 6, spaced 3 m in a tight zigzag (pattern 2 points)', 'vanillaControl': 'pattern 0: 6'},
        {'id': 'eagle.drop_interval', 'setup': 'Eagle Napalm Airstrike drop_interval 0.2 -> 0.6',
            'expect': 'the 4 napalm bombs release visibly further apart in time; landing points unchanged (aimed)'},
        {'id': 'eagle.fire_duration', 'setup': 'Eagle Strafing Run fire_duration 1.5 -> 3.0',
            'expect': '200 rounds (50 HE) along a 60 m sweep taking twice as long'},
        {'id': 'eagle.target_radius', 'setup': '110mm target_radius 20 -> 60 with enemies 30-50 m from the beacon',
            'expect': 'rockets now engage the farther enemies'},
        {'id': '110mm round types (lead)', 'setup': 'vanilla 110mm, Runtime trace of projectiles whose owner is the jet',
            'expect': 'either six 82s, or 146/146/82 per pod (confirms the pattern lead)'},
    ]

    # --- Phase A publication: exactly what scripts/generate_stratagem_authoring.py publishes (one reviewed source)
    publication_eagles = {}
    for name in EAGLES:
        c, p = catalogue[name], payloads[name]
        decoded = eagle.decode(c['record'])
        others = []
        for type_ in c['rowsNamingJet']:
            if type_ == c['type']:
                continue
            row = rows[type_]
            debug = UNUSED_ROWS.get(row['stableId'])
            if debug is None:
                raise ValueError(f'{name}: an unreviewed stratagem row {type_} names its jet')
            others.append({'kind': 'stratagem_row', 'stratagemType': type_, 'stableId': row['stableId'],
                'debugName': debug, 'selectable': False,
                'reason': 'an unused, non-selectable stratagem row (' + debug + ') names this jet as its payload, so '
                    'its calls would read the same record'})
        for s in spawners:
            if s['jet'] == c['jet']:
                others.append({'kind': 'eagle_spawner', 'record': s['record'], 'owner': s['owners'][0],
                    'stratagemType': s['stratagemType'],
                    'reason': 'the DSS Eagle Storm spawner (EagleSpawnerComponentData record %d) calls stratagem type %d, '
                        'whose jet is this one: its strikes read the same record' % (s['record'], s['stratagemType'])})
        values = {}
        for local, policy in PHASE_A.items():
            value = decoded[str(policy['offset'])]
            values[local] = round(value, 6) if isinstance(value, float) else value
        gun = (p.get('jetGun') or {}).get('projectileWeapon') or {}
        publication_eagles[name] = {'jet': c['jet'], 'recordIndex': c['record'], 'indexRow': c['indexRow'],
            'ownerCount': c['ownerCount'], 'uniqueOwner': c['ownerCount'] == 1, 'recordSha256': c['recordSha256'],
            'payload': p['payload'], 'payloadName': PAYLOAD_NAMES[p['payload']], 'values': values,
            'derived': {'bombsPerStrike': p['patternCount'] if p['payload'] == 5 else None,
                'strafeRoundsPerRun': round(values['fire_duration'] * gun['rateSlots'][1] / 60.0)
                    if p['payload'] == 2 else None,
                'gunRate': gun['rateSlots'][1] if p['payload'] == 2 else None},
            'otherConsumers': others, 'shared': bool(others)}
    shared_names = sorted(n for n, e in publication_eagles.items() if e['shared'])
    if shared_names != ['Eagle Gas Airstrike', 'Eagle Napalm Airstrike', 'Eagle Strafing Run']:
        raise ValueError('the shared Eagle jets changed: %r' % shared_names)
    publication = {'contract': 'hd2runtime.research.eagle_fields.v1', 'phase': 'A',
        'fields': {local: {'id': 'eagle.' + local, 'offset': policy['offset'], 'storage': policy['storage'],
            'type': policy['type'], 'unit': policy['unit'], 'min': policy['min'], 'max': policy['max'],
            'rangeJustification': policy['range'], 'editablePayloads': list(policy['kinds']),
            'reader': policy['reader'], 'timing': policy['timing'],
            'notRead': {str(k): v for k, v in policy['notRead'].items()},
            'confidence': next(c['confidence'] for c in candidates if c['offset'] == policy['offset'])}
            for local, policy in PHASE_A.items()},
        'patterns': [{'value': e['value'], 'name': e['name'], 'bombs': e['count'], 'lengthMeters': e['lengthMeters'],
            'lateralMeters': [e['lateral'][0], e['lateral'][1]], 'usedBy': e['usedBy']} for e in patterns['entries']],
        'extraBombStatDefault': code.stat_default(),
        'recordProof': {'offset': 0x10, 'storage': 'i32', 'member': 'payload',
            'reason': 'the attack kind is never written: it re-proves that the record still is this Eagle\'s'},
        'eagles': publication_eagles}

    counts_named = sum(1 for c in candidates if c['proposedName'])
    doc = report.document('Eagle components: every Eagle-related structure, compared across all Eagles',
        {'components': ['EagleComponentData', 'EagleSpawnerComponentData', 'MountComponentData (jets)',
            'ProjectileWeapon/WeaponMagazine/WeaponData (jets, pods)', 'projectile and explosion rows',
            'StratagemInfo rows'], 'eagles': EAGLES, 'unusedRows': list(UNUSED_ROWS.values()),
            'snapshots': SNAPSHOTS, 'gameDll': code.img.describe()},
        candidates,
        layout={'EagleComponent': {'size': eagle.record_size, 'records': eagle.count, 'indexCapacity': eagle.capacity,
            'members': layout}, 'fingerprints': fingerprints},
        enums=enums,
        catalogue=catalogue, unusedRows=unused, eagleRearm={'type': EAGLE_REARM_TYPE, 'cooldown': rearm['cooldown'],
            'uses': rearm['uses']},
        ownership={'family': description['ownership'], 'sharedTypeReport': compare.shared_type_report(t, 'EagleComponentData'),
            'unownedRecords': [r for r in range(eagle.count) if not eagle.owners(r)],
            'rowsNamingJet': {label_of[j]: jet_rows[j] for j in ordered}, 'spawners': spawners},
        matrix={'labels': labels, 'members': matrix, 'clusters': description['clusters']},
        patternTable=patterns,
        payloads=payloads, podRounds=pod_round_rows,
        nativeModel={'manager': MANAGER, 'runtimeRecord': RUNTIME_RECORD, 'flightRecord': FLIGHT_RECORD,
            'readPaths': {'resolver 0x514B40': 'per-entity copy if present, else the type record',
                'typeLookup 0x514640': 'the loaded type record (planner 0x89EF70, acquisition 0x8A01A0 via 0x89EE70)'},
            'extraBombStat': {'id': EXTRA_BOMB_STAT, 'default': code.stat_default(), 'lookup': 0xA079B0,
                'manager': 0x3326AC0}},
        pins=pins, accessScan=accesses, snapshotEvidence=snaps, wikiChecks=checks,
        classification=classification, promotionProposal={'typeRecordFields': proposal, 'perInstance': per_instance},
        publication=publication,
        notPromoted=not_promoted, leads=leads, liveTestDesign=live_tests,
        summary={'jets': len(jets), 'records': eagle.count, 'sharedRecords': 0, 'pins': len(pins_flat),
            'snapshots': len(snaps), 'wikiChecks': len(checks), 'namedCandidates': counts_named,
            'proposedTypeRecordFields': len([p for p in proposal if p['phase'] != 'read-only'])},
        writes=0, protectionChanges=0)
    report.write(OUTPUT, doc)
    print(json.dumps({'output': str(OUTPUT.relative_to(ROOT)), 'counts': doc['counts'], 'summary': doc['summary'],
        'proposal': [(p['id'], p['phase'], p['confidence']) for p in proposal]}, indent=1))


if __name__ == '__main__':
    main()
