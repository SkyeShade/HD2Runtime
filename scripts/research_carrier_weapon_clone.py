"""Can an unused vanilla support weapon TYPE be turned into a full EAT-17 clone for one mission (a "carrier weapon
clone"), and which carriers can host it? (research/docs/carrier-weapon-clone-F5FEE03DCFDB.md). Read-only, offline.

Proves on build F5FEE03DCFDB, from the pinned entity tables, the game.dll image, the seven retained snapshots and the
game's archives:

1. Component sets. An entity's component SET is fixed by its type. The 27 support weapons fall into 17 classes of
   identical component sets; the EAT-17 (lat_oneshot) shares its set only with the EAT-700 (expendable_napalm_launcher)
   and the EAT-411 (expendable_massive_rocket_launcher). The AC-8 (automatic_cannon) lacks Backblast and
   WeaponMagazine and has WeaponReload, WeaponRounds and WeaponAssistedReload.
2. What defines each aspect:
   - 3D model: UnitComponent +0 (UnitPath, a unit resource; it carries its own bones, physics and state machine in
     the weapon's generated loadout package) plus WeaponCustomization +0x4 (default optics option) / +0x78
     (OpticsPath: the EAT-17's lat_oneshot_sight unit). Node-name members (fire node, sight nodes, effect nodes) live
     in WeaponData / ProjectileWeapon / Attachable / Interactable.
   - Animations: the wielder side is a set of animation-event thin hashes (Equipment +0x48..+0x7C, GripType +0xC0,
     Wieldable +4..+0x14, WeaponData +0x398..+0x3A8, FireAbility +0x3AC) consumed by the always-resident Helldiver
     state machines; the weapon side is the unit's own state machine.
   - Expendable: WeaponData +0x1CC (auto_drop_ability, 17 chars) is read by the out-of-ammo handler 0x753A10, which
     plays it on the wielder ONLY if the weapon has no WeaponReload instance (G+0x3326A70 = component world
     +0x7571C8, the WeaponReload manager; proven in all seven snapshots). Equipment +0x88 DropMode (2 =
     InfiniteIfNonEmpty) decides what happens to the dropped launcher.
3. Lifecycle. The type tables are read in place. The per-component dispatcher 0x5740B0 makes a private copy only
   for an entity created WITH an entity delta on that component (snapshots: 0 UnitComponent copies in missions with
   spawned support weapons). So a carrier's type records must be converted before its first spawn and restored only
   after the mission (never mid-mission while a carrier instance exists).
4. The carrier ranking for an EAT-17 clone: the EAT-700 (19 member copies, all in exclusively owned records,
   identical magazine, backblast, auto-drop and drop mode), then the EAT-411; the AC-8 cannot be an expendable EAT.
5. The round overrides (`roundOverrides`, scripts/research_clone_rounds.py): a reviewed round a donor's clone may fire
   instead of the donor's own (the EAT-17 clone firing the RL-77 Airburst round 312): its rows, code pins, packages.

Output: research/carrier-weapon-clone-F5FEE03DCFDB.json. Nothing is written to the game.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from capstone import x86  # noqa: E402

import hd2_game_data  # noqa: E402
import research_event_state as base  # noqa: E402
import research_clone_rounds  # noqa: E402
import research_magazine_attachments as attachments  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
import research_support_item_presentation as presentation  # noqa: E402
from reference_format import dl_hash  # noqa: E402
from scan import compare, golib, tables, xref  # noqa: E402

OUTPUT = ROOT / 'research/carrier-weapon-clone-F5FEE03DCFDB.json'
CACHE = ROOT / 'build/scan-cache/carrier-weapon-clone-resources.pkl'
PRESENTATION = ROOT / 'research/support-item-presentation-F5FEE03DCFDB.json'
SUPPORT_RUNTIME = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
EQUIPMENT_LINKS = ROOT / 'research/support-equipment-links-F5FEE03DCFDB.json'
MISSION = [s for s in SNAPSHOTS if 'mission' in s]

ENTITY_MANAGER = 0x346BF98
SLOT_BASE = 0xF12478            # entity manager +SLOT_BASE + 8 * component index = that component's type table
KNOWN_SLOTS = {'BehaviorComponentData': 0xF12D58, 'DetectorComponentData': 0xF12D48,
    'EncyclopediaEntryComponentData': 0xF126D8, 'EquipmentComponentData': 0xF12BC0,
    'HellpodPayloadComponentData': 0xF12998, 'InteractableComponentData': 0xF12C18,
    'LoadoutEntryComponentData': 0xF12560, 'ProjectileWeaponComponentData': 0xF12E80,
    'SpottableComponentData': 0xF12860, 'TargetingComponentData': 0xF12BC8, 'WeaponDataComponentData': 0xF12BD8,
    'WeaponWindUpComponentData': 0xF126A8}  # pinned by earlier research scripts
DISPATCHER = (0x5740B0, 0x577400)  # the entity-delta dispatcher (research_pelican: runs at creation over the deltas)
WEAPON_DATA_MANAGER_GLOBAL, WEAPON_DATA_MANAGER = 0x3326CE0, 0xE9FB80   # component world + 0xE9FB80
MANAGER_GLOBALS = {0x3326A70: 'auto-drop gate 1', 0x3326D88: 'auto-drop gate 2'}
COPY_COUNTS = {'UnitComponentData': (0x1B4170, 0xB8), 'WeaponDataComponentData': (0xE9FB80, 0xA8),
    'ProjectileWeaponComponentData': (0xF0B3B8, 0xC8)}
DONOR = 0x80932FA0ED6901D3            # EAT-17 (lat_oneshot)
FOCUS = {'EAT-700': 'expendable_napalm_launcher', 'EAT-411': 'expendable_massive_rocket_launcher',
    'AC-8': 'automatic_cannon', 'MLS-4X': 'laser_guided_missile_launcher', 'GR-8': 'recoilless_rifle',
    'RL-77': 'air_burst_rocket_launcher', 'MGX-42': 'expendable_machinegun', 'LAS-99': 'laser_pulse_cannon',
    'FAF-14': 'faf_missile_launcher', 'APW-1': 'sniper_rifle'}
AVATAR_STATE_MACHINES = {'thirdPerson': 'content/fac_helldivers/cha_avatar/avatar_helldiver',
    'firstPerson': 'content/fac_helldivers/fp_cha_avatar/fp_cha_avatar'}
RESOURCE_TYPES = ('unit', 'package', 'state_machine', 'bones', 'physics', 'animation', 'material', 'texture',
    'particles', 'wwise_bank', 'wwise_dep', 'wwise_stream')
PRESENTATION_ONLY = {'EncyclopediaEntryComponentData', 'SpottableComponentData', 'LoadoutEntryComponentData'}

# Aspect of every member a clone may differ in: (component, first offset, end offset, aspect, policy, label).
# policy: 'copy' (donor value into the carrier's own record), 'presentation' (support-item-presentation design),
# 'identical' (must already be equal: the expendable contract of the clone class), 'never' (never written).
ASPECTS = [
    ('UnitComponentData', 0x0, 0x8, 'model', 'copy', 'UnitPath (unit resource)'),
    ('UnitComponentData', 0x8, 0x88, 'model', 'copy', 'scale / radius / visibility groups'),
    ('WeaponCustomizationComponentData', 0x0, 0x8, 'model', 'copy', 'DefaultCustomizations[0] (slot, option)'),
    ('WeaponCustomizationComponentData', 0x8, 0x78, 'model', 'never', 'customization slots (ship UI)'),
    ('WeaponCustomizationComponentData', 0x78, 0x80, 'model', 'copy', 'OpticsPath (sight unit)'),
    ('WeaponCustomizationComponentData', 0x80, 0x1308, 'model', 'never', 'customization data (ship UI)'),
    ('EquipmentComponentData', 0x0, 0x38, 'animation', 'copy', 'wield / holster nodes and offsets'),
    ('EquipmentComponentData', 0x38, 0x44, 'animation', 'copy', 'holster / wield / pickup durations'),
    ('EquipmentComponentData', 0x44, 0x80, 'animation', 'copy', 'wielder and self animation events'),
    ('EquipmentComponentData', 0x80, 0x84, 'identity', 'identical', 'EquipmentType (AI category)'),
    ('EquipmentComponentData', 0x84, 0x88, 'animation', 'copy', 'unknown bool (18)'),
    ('EquipmentComponentData', 0x88, 0x8C, 'expendable', 'identical', 'DropMode'),
    ('EquipmentComponentData', 0x8C, 0x98, 'sound', 'copy', 'drop audio'),
    ('EquipmentComponentData', 0x98, 0xA0, 'presentation', 'never', 'DropIconUi'),
    ('EquipmentComponentData', 0xA0, 0xB8, 'sound', 'copy', 'pickup / switch audio'),
    ('EquipmentComponentData', 0xB8, 0xC0, 'expendable', 'identical', 'Pickup / DropAbility'),
    ('EquipmentComponentData', 0xC0, 0xC4, 'animation', 'copy', 'GripType (wielder pose)'),
    ('EquipmentComponentData', 0xC4, 0xC8, 'animation', 'copy', 'one-handed / ship / pickup widget'),
    ('EquipmentComponentData', 0xC8, 0xD0, 'model', 'copy', 'HolsterUnit'),
    ('EquipmentComponentData', 0xD0, 0xD8, 'identity', 'never', 'hint ids'),
    ('EquipmentComponentData', 0xD8, 0xE8, 'sound', 'copy', 'wwise indices'),
    ('WieldableComponentData', 0x0, 0x4, 'animation', 'copy', 'AllowAds'),
    ('WieldableComponentData', 0x4, 0xC, 'animation', 'copy', 'wielder enter / exit events'),
    ('WieldableComponentData', 0xC, 0x10, 'sound', 'copy', 'WieldStateAudioEvent'),
    ('WieldableComponentData', 0x10, 0x20, 'animation', 'copy', 'self wielder events'),
    ('WeaponDataComponentData', 0x0, 0xCC, 'handling', 'copy', 'recoil, spread, sway, zoom, fire modes, crosshair'),
    ('WeaponDataComponentData', 0xCC, 0x130, 'model', 'copy', 'FireNodes / AimSourceNode (unit nodes)'),
    ('WeaponDataComponentData', 0x130, 0x184, 'handling', 'copy', 'scope / ergonomics / unknown handling'),
    ('WeaponDataComponentData', 0x184, 0x18C, 'animation', 'copy', 'start / stop firing anim events'),
    ('WeaponDataComponentData', 0x18C, 0x194, 'handling', 'copy', 'crosshair type'),
    ('WeaponDataComponentData', 0x194, 0x1CC, 'model', 'copy', 'first-person sight / camera / optic nodes'),
    ('WeaponDataComponentData', 0x1CC, 0x1D0, 'expendable', 'identical', 'AutoDropAbility'),
    ('WeaponDataComponentData', 0x1D0, 0x1F0, 'sound', 'copy', 'aim audio events'),
    ('WeaponDataComponentData', 0x1F0, 0x1F8, 'animation', 'copy', 'rounds-remaining anim variable'),
    ('WeaponDataComponentData', 0x1F8, 0x378, 'effects', 'copy', 'OnFireRoundEffects (effect + node)'),
    ('WeaponDataComponentData', 0x378, 0x398, 'model', 'copy', 'OnFireRoundNodeScales (unit nodes)'),
    ('WeaponDataComponentData', 0x398, 0x3B0, 'animation', 'copy', 'fire anim events, FireAbility'),
    ('WeaponDataComponentData', 0x3B0, 0x3B8, 'animation', 'copy', 'unknown abilities'),
    ('WeaponDataComponentData', 0x3B8, 0x3BC, 'expendable', 'identical', 'InfiniteAmmo'),
    ('WeaponDataComponentData', 0x3BC, 0x4D0, 'handling', 'copy', 'stat modifiers, ammo icons, fire-mode functions'),
    ('ProjectileWeaponComponentData', 0x0, 0x4, 'firing', 'copy', 'ProjType (the round)'),
    ('ProjectileWeaponComponentData', 0x4, 0x6C, 'firing', 'copy', 'rate, zeroing, heat, shakes, low-ammo count'),
    ('ProjectileWeaponComponentData', 0x6C, 0x78, 'sound', 'copy', 'low-ammo / last-bullet audio and VO'),
    ('ProjectileWeaponComponentData', 0x78, 0x98, 'firing', 'copy', 'wind, speed, damage / AP addends, sync'),
    ('ProjectileWeaponComponentData', 0x98, 0xE0, 'effects', 'copy', 'CasingEject (effect + unit nodes)'),
    ('ProjectileWeaponComponentData', 0xE0, 0xE8, 'effects', 'copy', 'MuzzleFlash'),
    ('ProjectileWeaponComponentData', 0xE8, 0xFC, 'firing', 'copy', 'shockwave, midi timing'),
    ('ProjectileWeaponComponentData', 0xFC, 0x120, 'sound', 'copy', 'fire audio events'),
    ('ProjectileWeaponComponentData', 0x120, 0x130, 'handling', 'copy', 'fire-loop camera shake'),
    ('ProjectileWeaponComponentData', 0x130, 0x21C, 'firing', 'copy', 'unnamed fire settings'),
    ('ProjectileWeaponComponentData', 0x21C, 0x220, 'model', 'copy', 'fire node (unit node)'),
    ('ProjectileWeaponComponentData', 0x220, 0x268, 'firing', 'copy', 'unnamed fire settings'),
    ('BackblastComponentData', 0x0, 0x40, 'expendable', 'identical', 'backblast'),
    ('WeaponMagazineComponentData', 0x0, 0xA0, 'expendable', 'identical', 'single-shot magazine'),
    ('AnimationComponentData', 0x0, 0x70, 'animation', 'copy', 'spawn animation variables'),
    ('AttachableComponentData', 0x0, 0x40, 'model', 'copy', 'actors, attach anims'),
    ('MeleeAttackComponentData', 0x0, 0x10, 'animation', 'copy', 'melee override ability'),
    ('LoadoutPackageComponentData', 0x0, 0x20, 'identity', 'never', 'package / audio resource (residency)'),
    ('EncyclopediaEntryComponentData', 0x0, 0x38, 'presentation', 'presentation', 'name / image'),
    ('SpottableComponentData', 0x0, 0x48, 'presentation', 'presentation', 'marker icon'),
    ('LoadoutEntryComponentData', 0x0, 0x10000, 'identity', 'never', 'loadout identity'),
]
DEFAULT_ASPECT = ('unreviewed', 'never', 'no reviewed role')

EXTRA_COMPONENT_EFFECT = {
    'WeaponReloadComponentData': 'reloadable: the out-of-ammo handler 0x753A10 exits when the weapon has a WeaponReload '
        'instance, so AutoDropAbility is never played (no expendable drop); keeps the reload ability and animations',
    'WeaponRoundsComponentData': 'round/clip ammunition (no WeaponMagazine): the magazine, chambered-type and '
        'single-shot contract of the EAT does not apply',
    'WeaponAssistedReloadComponentData': 'team (assisted) reload from a backpack stays available',
    'FactionComponentData': 'laser guidance chain (faction)', 'GuidanceTargetComponentData': 'guidance target',
    'LaserDesignatorComponentData': 'a visible laser designator stays', 'SensorEyeComponentData': 'sensor (guidance)',
    'WeaponLinkerComponentData': 'links fired missiles to the weapon (guidance)',
    'WeaponChargeComponentData': 'charge-up before firing', 'WeaponHeatComponentData': 'heat / overheat',
    'BeamWeaponComponentData': 'beam output', 'ArcWeaponComponentData': 'arc output',
    'SprayWeaponComponentData': 'spray output', 'WeaponLinkedAmmoComponentData': 'backpack-fed ammo',
    'TwoPointChainAttachTargetComponentData': 'ammo belt to a backpack', 'WeaponWindUpComponentData': 'spin-up',
    'EffectReferenceComponentData': 'persistent effects', 'StatusEffectReceiverComponentData': 'status effects',
}
MISSING_COMPONENT_EFFECT = {
    'BackblastComponentData': 'no backblast (cone damage and effect)',
    'WeaponMagazineComponentData': 'no magazine: no single-shot magazine, no chambered round',
    'ProjectileWeaponComponentData': 'cannot fire a projectile at all',
}

# Reviewed instruction pins: (rva, exact instruction, rip target or None, role).
PINS = {
    'deltaDispatcher': [
        (0x57477B, 'lea rcx, [r13 + 0x1b4170]', None, 'UnitComponent manager = component world +0x1B4170 ...'),
        (0x574788, 'call 0x6eac90', None, '... its delta copy routine'),
        (0x575ABE, 'lea rcx, [r13 + 0xe9fb80]', None, 'WeaponData manager = component world +0xE9FB80 ...'),
        (0x575ACB, 'call 0x75f080', None, '... its delta copy routine'),
        (0x574C42, 'lea rcx, [r13 + 0x7571c8]', None, 'WeaponReload manager = component world +0x7571C8 ...'),
        (0x574C4F, 'call 0x779410', None, '... its delta copy routine'),
        (0x57417F, 'call 0x770b10', None, 'WeaponMagazine delta copy'),
        (0x57454C, 'call 0x4f7420', None, 'Backblast delta case'),
        (0x575A0E, 'call 0x508e90', None, 'Equipment delta case'),
        (0x576AB4, 'call 0x61af10', None, 'ProjectileWeapon delta copy'),
        (0x5764B4, 'call 0x7512e0', None, 'WeaponCustomization delta copy'),
        (0x574492, 'call 0x9c5d20', None, 'LoadoutPackage delta case'),
        (0x5744A9, 'call 0x75fa60', None, 'MeleeAttack delta case'),
        (0x574D3C, 'call 0x77d610', None, 'WeaponRounds delta copy'),
    ],
    'unitCopy': [
        (0x6EAD30, 'imul rcx, rax, 0x88', None, 'an existing 0x88-byte UnitComponent copy ...'),
        (0x6EAD74, 'call 0x4f95c0', None, '... else the TYPE record (lookup by type hash) ...'),
        (0x6EAD85, 'mov rax, qword ptr [r8 + 0xf12738]', None, '... (default record of the UnitComponent table) ...'),
        (0x6EADED, 'call 0x515540', None, '... patched by the entity delta, then stored'),
    ],
    'weaponDataCopy': [
        (0x75F109, 'imul rcx, rax, 0x4d0', None, 'an existing 0x4D0-byte WeaponData copy ...'),
        (0x75F14D, 'call 0x509570', None, '... else the TYPE record ...'),
        (0x75F15E, 'mov rax, qword ptr [r8 + 0xf12bd8]', None, '... (WeaponData type table)'),
        (0x509AE2, 'imul rax, rax, 0x4d0', None, 'WeaponData resolver 0x509A40: the entity\'s copy ...'),
        (0x509AE9, 'add rax, qword ptr [r11 + 0xb0]', None, '... in the copy array (manager +0xB0) ...'),
        (0x509AFC, 'jmp 0x509570', None, '... else the TYPE record (read in place)'),
    ],
    'autoDrop': [
        (0x753A97, 'call 0x509a40', None, 'out-of-ammo handler 0x753A10: the weapon\'s WeaponData (copy or type)'),
        (0x753B33, 'mov rcx, qword ptr [rip + 0x2bd2f36]', 0x3326A70, 'gate 1: the WeaponReload manager ...'),
        (0x753BB9, 'cmp dword ptr [r11 + r8*8 + 4], -1', None, '... has this weapon a WeaponReload instance ...'),
        (0x753BBF, 'jne 0x753d89', None, '... then NO auto drop (return)'),
        (0x753BD5, 'mov rax, qword ptr [rip + 0x2bd31ac]', 0x3326D88, 'gate 2: manager component world +0xEEF730 ...'),
        (0x753C29, 'jne 0x753d89', None, '... an instance there: no auto drop either'),
        (0x753C2F, 'mov esi, dword ptr [r13 + 0x1cc]', None, 'WeaponData +0x1CC auto_drop_ability ...'),
        (0x753C36, 'test esi, esi', None, '... 0 = not expendable ...'),
        (0x753C38, 'je 0x753d89', None, '... return'),
        (0x753C40, 'call 0x7cbe60', None, 'the wielder\'s current ability (not already dropping)'),
        (0x753CE4, 'mov r8d, dword ptr [r13 + 0x1cc]', None, 'the ability id ...'),
        (0x753CFA, 'call 0x7caf40', None, '... played on the wielder (the discard)'),
        (0x828C89, 'call 0x509a40', None, 'other reader: WeaponData ...'),
        (0x828C8E, 'cmp dword ptr [rax + 0x1cc], r13d', None, '... "is an auto-drop weapon" predicate'),
        (0x9A92ED, 'call 0x509a40', None, 'other reader: WeaponData ...'),
        (0x9A92F2, 'cmp dword ptr [rax + 0x1cc], ebp', None, '... auto-drop weapons take another path'),
        (0xA93B74, 'call 0x509a40', None, 'other reader: WeaponData ...'),
        (0xA93B79, 'cmp dword ptr [rax + 0x1cc], 0', None, '... auto-drop weapons take another path'),
    ],
    'dropMode': [
        (0x8BFE82, 'cmp dword ptr [rsi + 0x88], r15d', None, 'Equipment +0x88 DropMode readers (equipment system)'),
        (0x8C06B3, 'cmp dword ptr [rax + 0x88], r14d', None, '...'),
        (0x8C1F1F, 'mov r8d, dword ptr [rax + 0x88]', None, '...'),
        (0x8C2A0A, 'cmp dword ptr [rax + 0x88], 0', None, '...'),
    ],
    # The pickup prompt's icon (consumer proof for a Runtime icon in Spottable +0x38 or a pod row's StratagemInfo
    # +0xB0): both paths fill the SAME prompt entry {+0x10 name, +0x18 kind}; the widget setter 0x1868700 picks a FIXED
    # vanilla template material by kind (0x144F800 is never called with the icon name) and resolves the icon NAME only
    # through GUI API +0xD8 (exe 0x30F960: the MATERIAL resource of that name, its slot 0x3AA8B87E texture name), then
    # binds that texture (or the atlas sprite) into the template. A custom family = GUI material N whose slot names
    # texture N: exactly what that lookup needs, the same precondition the live-proven loadout grid has.
    'promptIcon': [
        (0xFFC404, 'mov rcx, qword ptr [rax + 0x38]', None, 'an Item: icon = Spottable +0x38 of its TYPE ...'),
        (0xFFC341, 'mov qword ptr [rsi + rbx + 0x10], rcx', None, '... prompt entry +0x10 (name)'),
        (0xFFC34F, 'mov dword ptr [rsi + rbx + 0x18], eax', None, '... prompt entry +0x18 (kind = Spottable +0x40)'),
        (0xFFC719, 'mov qword ptr [r15 + r12 + 0x10], rax', None, 'a hellpod rack: StratagemInfo[rack +0x28] +0xB0 ...'),
        (0xFFC71E, 'mov dword ptr [r15 + r12 + 0x18], 2', None, '... the same entry, kind 2'),
        (0xFFCBE1, 'imul r8, rcx, 0x38', None, 'the entry (0x38 bytes) ...'),
        (0xFFCBEC, 'add r8, 8', None, '... from +8 ...'),
        (0xFFCBFD, 'call 0x1868700', None, '... to the prompt widget setter'),
        (0x186874F, 'mov rbp, r8', None, 'rbp = entry +8'),
        (0x1868824, 'mov eax, dword ptr [rbp + 0x10]', None, 'kind (entry +0x18) ...'),
        (0x186883D, 'movabs rdx, 0xc0f3797849262087', None, '... kind 2: a FIXED vanilla template material ...'),
        (0x186884D, 'call 0x144f800', None, '... set by its fixed name (never the icon name)'),
        (0x1868908, 'mov rax, qword ptr [rip + 0x1abd9f9]', 0x3326308, 'the GUI API ...'),
        (0x186890F, 'mov edx, 0x3aa8b87e', None, '... slot 0x3AA8B87E (the icon material\'s image slot) ...'),
        (0x1868918, 'mov rax, qword ptr [rcx + 0xd8]', None, '... GUI API +0xD8: the MATERIAL of that name, its slot ...'),
        (0x186891F, 'mov rcx, qword ptr [rbp + 8]', None, '... of the icon name (entry +0x10) ...'),
        (0x1868923, 'call rax', None, '... -> the slot\'s texture name'),
        (0x1868950, 'call 0x1449a70', None, 'bound into the template (texture by name / atlas sprite)'),
    ],
    # The Spottable instance manager: one instance per live entity with a Spottable component (every support weapon):
    # count +0x10, handle array +0x38, a handle's +0 its type, +8 its entity. Read before a conversion: no instance of
    # the carrier type may exist yet.
    'spottableInstances': [
        (0x67D92A, 'mov rbx, qword ptr [rip + 0x2ca8b1f]', 0x3326450, 'Spottable instance add: the manager'),
        (0x67D954, 'mov r8d, dword ptr [rbx + 0x10]', None, '... the instance count'),
        (0x67D97B, 'mov rax, qword ptr [rbx + 0x38]', None, '... the handle array'),
        (0x67D98A, 'mov qword ptr [rax + r8*8], rdi', None, '... handle[count] = the new handle'),
        (0x67D98E, 'mov edx, dword ptr [rdi + 8]', None, '... whose +8 is the entity'),
        (0xFFC2D2, 'mov rsi, qword ptr [rip + 0x232a177]', 0x3326450, 'the prompt reads the same manager'),
    ],
}


def hexid(value: int) -> str:
    return '0x%016X' % value


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


# ------------------------------------------------------------------------------------------------- tables
def slot_of(t: tables.EntityTables, component: str) -> int:
    t.entity_rows()
    index = {v: k for k, v in t._index_type.items()}[dl_hash(component)]  # noqa: SLF001 - research access
    return SLOT_BASE + 8 * index


def prove_slot_rule(t: tables.EntityTables) -> dict:
    derived = {name: slot_of(t, name) for name in KNOWN_SLOTS}
    if derived != KNOWN_SLOTS:
        raise ValueError('type-table slot rule failed: %r' % derived)
    return {'rule': 'entity manager +0x%X + 8 * component index' % SLOT_BASE, 'checkedAgainst': len(KNOWN_SLOTS)}


def names_by_path() -> dict:
    links = json.loads(EQUIPMENT_LINKS.read_text(encoding='utf-8'))['supportWeapons']
    out = {}
    for name, rows in links.items():
        for row in rows:
            path = row.get('path') or ''
            if '/support_weapons/' in path:
                out[path.rsplit('/', 1)[-1]] = name
    return out


def component_classes(t: tables.EntityTables, weapons: list[int], names: dict) -> dict:
    sets = {r: frozenset(t.entity(r)) for r in weapons}
    classes = {}
    for r, s in sets.items():
        classes.setdefault(s, []).append(names.get(t.label(r), t.label(r)))
    donor = sets[DONOR]
    presence = compare.presence(t, weapons)
    return {
        'supportWeapons': len(weapons),
        'classes': sorted(([sorted(v), len(k)] for k, v in classes.items()), key=lambda c: (-len(c[0]), c[0])),
        'eat17Components': sorted(donor),
        'common': sorted(set.intersection(*map(set, sets.values()))),
        'presenceMarkers': {k: v for k, v in presence.items() if k != 'entities'},
        'perWeapon': {names.get(t.label(r), t.label(r)): {
            'missingVsEat17': sorted(donor - s), 'extraVsEat17': sorted(s - donor)} for r, s in sets.items()},
    }


def aspect_of(component: str, offset: int):
    for comp, lo, hi, aspect, policy, label in ASPECTS:
        if comp == component and lo <= offset < hi:
            return aspect, policy, label
    return DEFAULT_ASPECT


def describe_value(t: tables.EntityTables, member, value):
    if isinstance(value, int) and member.size == 8 and value > 0xFFFF:
        return {'value': hexid(value), 'resource': t.paths.get(value)}
    if isinstance(value, int) and member.size == 4 and value > 0xFFFF and member.storage == 'UINT32':
        return {'value': '0x%08X' % value, 'thin': t.thin.get(value)}
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [round(v, 6) if isinstance(v, float) else v for v in value]
    return value


def member_diff(t: tables.EntityTables, go, donor: int, carrier: int) -> dict:
    """Every member of the shared components whose bytes differ, with its aspect and write policy."""
    a, b = t.entity(donor), t.entity(carrier)
    rows, owners = [], {}
    for component in sorted(set(a) & set(b)):
        comp = t.component(component)
        owners[component] = {'donor': len(comp.owners(a[component])), 'carrier': len(comp.owners(b[component])),
            'carrierRecord': b[component]}
        ra, rb = comp.raw(a[component]), comp.raw(b[component])
        if ra == rb:
            continue
        leads = golib.leads_for(t, go, comp.record_type)
        for member in comp.members():
            lo, hi = member.offset, member.offset + member.size
            if member.atom == 'BITFIELD':
                lo, hi = member.offset, member.offset + member.size
            if ra[lo:hi] == rb[lo:hi]:
                continue
            if member.atom == 'BITFIELD':
                da, db = tables.decode(member, ra), tables.decode(member, rb)
                if da == db:
                    continue
            else:
                da, db = tables.decode(member, ra), tables.decode(member, rb)
            aspect, policy, label = aspect_of(component, member.offset)
            lead = leads.get(member.offset)
            rows.append({'component': component, 'offset': '0x%X' % member.offset, 'path': member.path,
                'size': member.size, 'storage': member.storage, 'nameLength': member.name_length,
                'lead': lead['goField'] if lead else None, 'leadStrength': lead['strength'] if lead else None,
                'aspect': aspect, 'policy': policy, 'role': label,
                'donor': describe_value(t, member, da), 'carrier': describe_value(t, member, db)})
    by_aspect = {}
    for row in rows:
        by_aspect.setdefault(row['aspect'], 0)
        by_aspect[row['aspect']] += 1
    return {'members': rows, 'byAspect': by_aspect, 'owners': owners,
        'componentsOnlyDonor': sorted(set(a) - set(b)), 'componentsOnlyCarrier': sorted(set(b) - set(a))}


def carrier_candidates(t: tables.EntityTables, go, weapons: list[int], names: dict) -> list[dict]:
    pres = {c['weapon']: c for c in json.loads(PRESENTATION.read_text(encoding='utf-8'))['carrierCandidates']}
    runtime = {}
    for row in json.loads(SUPPORT_RUNTIME.read_text(encoding='utf-8'))['weapons']:
        runtime[row.get('catalogIdentity')] = row
    wd = t.component('WeaponDataComponentData')
    eq = t.component('EquipmentComponentData')
    donor_set = set(t.entity(DONOR))
    out = []
    for r in weapons:
        if r == DONOR:
            continue
        label = t.label(r)
        name = names.get(label, label)
        comps = set(t.entity(r))
        diff = member_diff(t, go, DONOR, r)
        missing, extra = sorted(donor_set - comps), sorted(comps - donor_set)
        auto_drop = struct.unpack_from('<I', wd.raw(wd.record_of(r)), 0x1CC)[0]
        drop_mode = struct.unpack_from('<i', eq.raw(eq.record_of(r)), 0x88)[0]
        written = [c for c in comps & donor_set if c not in PRESENTATION_ONLY]
        exclusive = all(diff['owners'][c]['carrier'] == 1 for c in written if c in diff['owners'])
        p = pres.get(label, {})
        identical_contract = [m for m in diff['members'] if m['policy'] == 'identical']
        aspects = {
            'presentation': 'feasible (EncyclopediaEntry / Spottable present; support-item-presentation design)',
            'model': 'feasible' if 'ProjectileWeaponComponentData' in comps else 'no fire node consumer: refused',
            'animation': 'feasible (wielder events are avatar state-machine events; component set fixed)',
            'expendable': ('native (identical)' if not identical_contract and 'WeaponReloadComponentData' not in comps
                and 'WeaponMagazineComponentData' in comps else
                'impossible: WeaponReload present (0x753A10 gate)' if 'WeaponReloadComponentData' in comps else
                'impossible: no WeaponMagazine' if 'WeaponMagazineComponentData' not in comps else
                'would need contract writes (refused: clone class only)'),
            'backblast': 'native (identical)' if 'BackblastComponentData' in comps and not any(
                m['component'] == 'BackblastComponentData' for m in diff['members']) else
                'impossible: no Backblast component' if 'BackblastComponentData' not in comps else
                'contract differs (refused)',
            'firing': 'feasible' if 'ProjectileWeaponComponentData' in comps and not (set(extra) & {
                'WeaponChargeComponentData', 'BeamWeaponComponentData', 'ArcWeaponComponentData',
                'SprayWeaponComponentData', 'WeaponHeatComponentData', 'WeaponWindUpComponentData'})
                else 'refused: the fire path differs by component',
        }
        exact = not missing and not extra
        eligible = exact and exclusive and not p.get('inWorldLoot') and p.get('deliveredBy') == [name] and not \
            identical_contract
        out.append({
            'weapon': name, 'entity': label, 'resource': hexid(r),
            'componentRelation': 'identical' if exact else 'superset' if not missing else
                'subset' if not extra else 'different',
            'missingComponents': [{'component': c, 'effect': MISSING_COMPONENT_EFFECT.get(c, 'unreviewed')}
                for c in missing],
            'extraComponents': [{'component': c, 'effect': EXTRA_COMPONENT_EFFECT.get(c, 'unreviewed')}
                for c in extra],
            'autoDropAbility': auto_drop, 'dropMode': drop_mode,
            'everyWrittenRecordExclusive': exclusive,
            'inWorldLoot': p.get('inWorldLoot'), 'deliveredBy': p.get('deliveredBy'),
            'backpackDependent': (runtime.get(name) or {}).get('backpackDependent'),
            'differingMembers': len(diff['members']), 'differingByAspect': diff['byAspect'],
            'contractDifferences': [m['component'] + ' ' + m['offset'] for m in identical_contract],
            'aspects': aspects,
            'eat17CloneHost': eligible,
        })
    rank = {'identical': 0, 'superset': 1, 'subset': 2, 'different': 3}
    out.sort(key=lambda c: (not c['eat17CloneHost'], rank[c['componentRelation']],
        bool(c['contractDifferences']), c['differingMembers'], c['weapon']))
    return out


# ------------------------------------------------------------------------------------------------- archives
def read_resources(t: tables.EntityTables, labels: dict) -> dict:
    """Packages, units, bones, physics and state machines of the focus weapons; the avatar state machines."""
    types = {n: hd2_game_data.murmur64(n.encode()) for n in RESOURCE_TYPES}
    uc, lp = t.component('UnitComponentData'), t.component('LoadoutPackageComponentData')
    wanted = {}
    for key, resource in labels.items():
        unit = struct.unpack_from('<Q', uc.raw(uc.record_of(resource)), 0)[0]
        package = struct.unpack_from('<Q', lp.raw(lp.record_of(resource)), 8)[0]
        wanted[(unit, types['unit'])] = key + '.unit'
        wanted[(package, types['package'])] = key + '.package'
        for kind in ('bones', 'physics', 'state_machine'):
            wanted[(unit, types[kind])] = key + '.' + kind
    sight = hd2_game_data.murmur64(b'content/fac_helldivers/equipment/support_weapons/lat_oneshot/lat_oneshot_sight')
    wanted[(sight, types['unit'])] = 'EAT-17.sightUnit'
    for key, path in AVATAR_STATE_MACHINES.items():
        wanted[(hd2_game_data.murmur64(path.encode()), types['state_machine'])] = 'avatar.' + key
    signature = sha(repr(sorted(wanted.items())).encode())
    if CACHE.is_file():
        cached = pickle.loads(CACHE.read_bytes())
        if cached.get('signature') == signature:
            return {'types': types, 'blobs': cached['blobs']}
    data = hd2_game_data.Data()
    found = data.find(set(wanted))
    blobs = {wanted[key]: data.read(archive, main) for key, (archive, main, _stream, _gpu) in found.items()}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps({'signature': signature, 'blobs': blobs}))
    return {'types': types, 'blobs': blobs}


def package_contents(t: tables.EntityTables, blob: bytes, types: dict) -> dict:
    names = {v: k for k, v in types.items()}
    count = struct.unpack_from('<I', blob, 8)[0]
    rows = {}
    for i in range(count):
        kind, name = struct.unpack_from('<QQ', blob, 16 + 16 * i)
        rows.setdefault(names.get(kind, '0x%016X' % kind), []).append(t.paths.get(name) or hexid(name))
    return {k: (sorted(v) if k in ('unit', 'state_machine', 'bones', 'physics', 'animation', 'wwise_bank')
        else len(v)) for k, v in sorted(rows.items())}


def node_presence(t: tables.EntityTables, blobs: dict, labels: dict) -> dict:
    """Every thin-hash member of each focus weapon that names something in a unit-side resource, and where it
    occurs (the unit, its bones / physics, the EAT-17 unit). A byte search: PLAUSIBLE evidence of a node name."""
    out = {}
    for key, resource in labels.items():
        own = b''.join(blobs.get(key + '.' + k, b'') for k in ('unit', 'bones', 'physics'))
        donor_unit = blobs['EAT-17.unit'] + blobs.get('EAT-17.bones', b'') + blobs.get('EAT-17.physics', b'')
        rows = []
        for component, record in sorted(t.entity(resource).items()):
            comp = t.component(component)
            raw = comp.raw(record)
            for member in comp.members():
                if member.storage != 'UINT32':
                    continue
                for j in range(member.size // 4):
                    value = struct.unpack_from('<I', raw, member.offset + 4 * j)[0]
                    name = t.thin.get(value)
                    if value <= 0xFFFF or not name:
                        continue
                    needle = struct.pack('<I', value)
                    if needle in own or needle in donor_unit:
                        rows.append({'component': component, 'offset': '0x%X' % (member.offset + 4 * j),
                            'name': name, 'inOwnUnit': needle in own, 'inEat17Unit': needle in donor_unit})
        out[key] = rows
    return out


ANIMATION_MEMBERS = [('EquipmentComponentData', o, n) for o, n in ((0x48, 'WieldAnimation'),
    (0x4C, 'PickupAnimation'), (0x50, 'HolsterAnimation'), (0x54, 'DropAnimation'), (0x58, 'AmmocheckAnimation'),
    (0x6C, 'OnHolsterAnimationEvent'), (0x70, 'WieldAnimationSelf'), (0x74, 'PickupAnimationSelf'),
    (0x78, 'HolsterAnimationSelf'))] + [('WieldableComponentData', o, n) for o, n in ((4, 'WielderEnterAnimationEvent'),
    (8, 'WielderExitAnimationEvent'), (0x10, 'SelfWielderEnterAnimationEvent'), (0x14, 'SelfWielderExitAnimationEvent'))] \
    + [('WeaponDataComponentData', o, n) for o, n in ((0x184, 'start firing anim event (42)'),
    (0x188, 'stop firing anim event (41)'), (0x1F0, 'OnFireRoundsRemainingAnimationVariable'),
    (0x398, 'OnFireRoundAnimEvent'), (0x39C, 'OnFireLastRoundAnimEvent'), (0x3A0, 'OnFireRoundWielderAnimEvent'),
    (0x3A4, 'OnFireModeChangedAnimVariable'), (0x3A8, 'OnFireModeChangedWielderAnimEvent'))]


def animation_events(t: tables.EntityTables, blobs: dict, labels: dict) -> dict:
    tp, fp = blobs['avatar.thirdPerson'], blobs['avatar.firstPerson']
    out = {}
    for key, resource in labels.items():
        rows = []
        for component, offset, name in ANIMATION_MEMBERS:
            comp = t.component(component)
            value = struct.unpack_from('<I', comp.raw(comp.record_of(resource)), offset)[0]
            if not value:
                continue
            needle = struct.pack('<I', value)
            side = 'weapon' if 'Self' in name or name in ('OnFireRoundAnimEvent', 'OnFireLastRoundAnimEvent',
                'OnFireRoundsRemainingAnimationVariable', 'OnFireModeChangedAnimVariable') else 'wielder'
            rows.append({'member': '%s +0x%X %s' % (component.replace('ComponentData', ''), offset, name), 'side': side,
                'value': '0x%08X' % value, 'thin': t.thin.get(value), 'avatarThirdPerson': needle in tp,
                'avatarFirstPerson': needle in fp, 'ownStateMachine': needle in blobs.get(key + '.state_machine', b''),
                'eat17StateMachine': needle in blobs['EAT-17.state_machine']})
        grip = struct.unpack_from('<I', t.component('EquipmentComponentData').raw(
            t.component('EquipmentComponentData').record_of(resource)), 0xC0)[0]
        fire_ability = struct.unpack_from('<I', t.component('WeaponDataComponentData').raw(
            t.component('WeaponDataComponentData').record_of(resource)), 0x3AC)[0]
        out[key] = {'gripType': grip, 'fireAbility': fire_ability, 'events': rows}
    return out


def customization_options(t: tables.EntityTables, labels: dict) -> dict:
    items = attachments.customization_items(
        (attachments.DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes())
    deltas, _ = attachments.entity_deltas((attachments.DATALIB / 'generated_entity_deltas.dl_bin').read_bytes())
    t.entity_rows()
    by_index = {k: t.type_name(v) for k, v in t._index_type.items()}  # noqa: SLF001
    wc = t.component('WeaponCustomizationComponentData')
    out = {}
    for key, resource in labels.items():
        raw = wc.raw(wc.record_of(resource))
        slot, option = struct.unpack_from('<II', raw, 0)
        optics = struct.unpack_from('<Q', raw, 0x78)[0]
        item = next((i for i in items if i['optionId'] == option), None) if option else None
        patches = []
        if item:
            for e in deltas.get(item['addPath'], {}).get('entries', []):
                value = int.from_bytes(e['bytes'], 'little')
                patches.append({'component': by_index.get(e['component'], e['component']),
                    'offset': '0x%X' % e['offset'], 'size': e['size'], 'bytes': e['bytes'].hex(),
                    'resource': t.paths.get(value) if e['size'] == 8 else None})
        out[key] = {'defaultSlot': slot, 'defaultOption': '0x%08X' % option if option else None,
            'optionInCustomizationTable': item is not None, 'optionDebugName': item['debugName'] if item else None,
            'opticsPath': t.paths.get(optics) if optics else None, 'deltaPatches': patches}
    return out


# ------------------------------------------------------------------------------------------------- code
def prove_pins(image: xref.CodeImage) -> dict:
    out = {}
    for group, rows in PINS.items():
        out[group] = []
        for rva, asm, target, role in rows:
            pin = image.pin(rva, role, asm)
            if target is not None and pin.get('ripTarget') != target:
                raise ValueError('pin %x: rip target %r, expected %x' % (rva, pin.get('ripTarget'), target))
            out[group].append(pin)
    return out


def dispatcher_cases(image: xref.CodeImage, t: tables.EntityTables) -> dict:
    """Which component lookups / copy routines the entity-delta dispatcher reaches (direct calls)."""
    readers = {}
    for name in sorted(set(t.entity(DONOR)) | {'WeaponReloadComponentData', 'WeaponRoundsComponentData',
            'WeaponAssistedReloadComponentData'}):
        for row in presentation.raw_slot_readers(image, slot_of(t, name)):
            readers.setdefault(row['function'], name)
    lo, hi = DISPATCHER
    covered = {}
    for ins in image.md.disasm(image.data[lo:hi], lo):
        if ins.mnemonic == 'call' and ins.operands[0].type == x86.X86_OP_IMM and ins.operands[0].imm in readers:
            covered.setdefault(readers[ins.operands[0].imm], []).append('0x%X' % ins.address)
    return {'componentsWithADeltaCase': covered,
        'typeTableReaders': {name: sorted({'0x%X' % f for f, n in readers.items() if n == name})
            for name in sorted(set(readers.values()))},
        'meaning': 'a component listed here gets a private per-entity copy ONLY when the entity is created with an '
            'entity delta on it (research_pelican: the dispatcher runs over the creation descriptor\'s delta list); '
            'every other read resolves the TYPE record in place'}


def census(image: xref.CodeImage) -> dict:
    out = {}
    for function, label, offsets in ((0x4F95C0, 'UnitComponent type lookup', None),
            (0x509A40, 'WeaponData resolver (copy, else type)', [0x1CC]),
            (0x5092B0, 'Equipment resolver (copy, else type)', [0x88, 0xC0, 0x48, 0x50]),
            (0x508E90, 'Equipment type lookup', [0x88, 0xC0, 0x48, 0x50])):
        callers = sorted({image.root(r.address) for r in image.references(function) if image.root(r.address)})
        row = {'callers': len(callers), 'callerFunctions': ['0x%X' % c for c in callers]}
        if offsets:
            hits = image.displacement_scan(callers, offsets)
            row['memberReaders'] = {'+0x%X' % o: sorted('0x%X' % f for f, h in hits.items()
                if any(x['disp'] == o for x in h)) for o in offsets}
        out['0x%X %s' % (function, label)] = row
    return out


# ------------------------------------------------------------------------------------------------- snapshots
def snapshot_facts(t: tables.EntityTables) -> dict:
    written = ['UnitComponentData', 'EquipmentComponentData', 'WieldableComponentData', 'WeaponDataComponentData',
        'ProjectileWeaponComponentData', 'WeaponCustomizationComponentData', 'EncyclopediaEntryComponentData',
        'SpottableComponentData']
    out = {}
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        try:
            world = mem.ptr(mem.game + WEAPON_DATA_MANAGER_GLOBAL) - WEAPON_DATA_MANAGER
            gates = {('0x%X' % g): '0x%X' % (mem.ptr(mem.game + g) - world) for g in MANAGER_GLOBALS}
            copies = {c: mem.u32(world + m + count) for c, (m, count) in COPY_COUNTS.items()}
            em = mem.ptr(mem.game + ENTITY_MANAGER)
            in_place = {c: mem.read(mem.ptr(em + slot_of(t, c)), len(t.component(c).body)) == t.component(c).body
                for c in written}
            out[name] = {'autoDropGateManagers': gates, 'deltaCopies': copies, 'typeTableInPlace': in_place}
        finally:
            mem.close()
    return out


# ------------------------------------------------------------------------------------------------- domain data
# What runtime/weapon_clone.lua needs (scripts/generate_weapon_clone.py turns it into domains/weapon_clone.lua): the
# component tables as they sit in the entity region, the donor's reviewed values, each clone host's own records (row,
# record, owner count, an FNV-1a of its native bytes) and every member to copy, by level.
DOMAIN_COMPONENTS = ('UnitComponentData', 'EquipmentComponentData', 'WieldableComponentData', 'WeaponDataComponentData',
    'ProjectileWeaponComponentData', 'WeaponCustomizationComponentData', 'EncyclopediaEntryComponentData',
    'SpottableComponentData')
LEVEL_OF = {'model': 'model', 'animation': 'model', 'sound': 'full', 'firing': 'full', 'handling': 'full',
    'effects': 'full'}
PRESENTATION_MEMBERS = (('EncyclopediaEntryComponentData', 0x8, 4, 'name'),
    ('EncyclopediaEntryComponentData', 0x30, 8, 'image'), ('SpottableComponentData', 0x38, 8, 'icon'))
WIDTHS = (1, 4, 8, 12)


def fnv1a(data: bytes) -> str:
    h = 2166136261
    for byte in data:
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return '%08X' % h


def schema_of(t: tables.EntityTables, name: str) -> dict:
    comp = t.component(name)
    offset = comp.frame_offset
    if offset + 28 > len(t.entities):
        raise ValueError(name + ': frame outside the entity file')
    return {'offset': offset, 'header': t.entities[offset:offset + 28].hex(),
        'index': struct.unpack_from('<I', t.entities, offset - 4)[0], 'indices': comp.capacity, 'records': comp.count,
        'record_offset': comp.records_offset, 'stride': comp.record_size, 'type': dl_hash(name),
        'slot': slot_of(t, name)}


def copy_writes(t: tables.EntityTables, diff: dict) -> list[dict]:
    """Every member to copy (policy copy), as transaction-sized writes: a whole member when its width is one the
    guarded transaction takes, else its differing 4-byte words. Bitfield leaves sharing one byte become one write."""
    out, seen = [], set()
    for m in diff['members']:
        if m['policy'] != 'copy':
            continue
        comp = t.component(m['component'])
        offset = int(m['offset'], 16)
        rec_a = comp.raw(t.entity(DONOR)[m['component']])
        rec_b = comp.raw(diff['carrierRecords'][m['component']])
        width = m['size']
        parts = [(offset, width)] if width in WIDTHS else [(offset + k, 4) for k in range(0, width, 4)]
        for at, w in parts:
            key = (m['component'], at)
            if key in seen or rec_a[at:at + w] == rec_b[at:at + w]:
                continue
            seen.add(key)
            if w not in WIDTHS or at % min(w, 4):
                raise ValueError('unsupported write width/alignment: %s +0x%X (%d)' % (m['component'], at, w))
            out.append({'component': m['component'], 'offset': at, 'width': w, 'native': rec_b[at:at + w].hex(),
                'donor': rec_a[at:at + w].hex(), 'aspect': m['aspect'], 'level': LEVEL_OF[m['aspect']],
                'label': (m['lead'] or m['role']) + (' (+%d)' % (at - offset) if at != offset else '')})
    out.sort(key=lambda w: (w['component'], w['offset']))
    return out


def domain_data(t: tables.EntityTables, image: xref.CodeImage, candidates: list[dict], names: dict) -> dict:
    hosts = [c for c in candidates if c['eat17CloneHost']]
    by_name = {v: k for k, v in names.items()}
    comps = {name: schema_of(t, name) for name in DOMAIN_COMPONENTS}
    donor_rows = t.entity(DONOR)

    def member(resource, component, offset, width):
        comp = t.component(component)
        return comp.raw(t.entity(resource)[component])[offset:offset + width]
    donor = {'name': 'EAT-17 Expendable Anti-Tank', 'entity': hexid(DONOR), 'projectile': struct.unpack_from('<I',
        member(DONOR, 'ProjectileWeaponComponentData', 0, 4))[0],
        'presentation': {role: member(DONOR, c, o, w).hex() for c, o, w, role in PRESENTATION_MEMBERS},
        'pool': [h['weapon'] for h in hosts]}
    carriers = {}
    for h in hosts:
        resource = int(h['resource'], 16)
        rows = t.entity(resource)
        diff = member_diff(t, golib.default_library(), DONOR, resource)
        diff['carrierRecords'] = rows
        writes = copy_writes(t, diff)
        records = {}
        written = {w['component'] for w in writes} | {c for c, *_ in PRESENTATION_MEMBERS}
        for component in sorted(written):
            comp = t.component(component)
            record = rows[component]
            owners = comp.owners(record)
            if owners != [resource]:
                raise ValueError('%s %s is not exclusively owned: %r' % (h['weapon'], component, owners))
            index_row = next(row for row, res, rec in comp.rows() if res == resource)
            records[component] = {'indexRow': index_row, 'recordIndex': record, 'ownerCount': len(owners),
                'fnv1a': fnv1a(comp.raw(record))}
        kind = struct.unpack_from('<I', member(resource, 'SpottableComponentData', 0x40, 4))[0]
        donor_kind = struct.unpack_from('<I', member(DONOR, 'SpottableComponentData', 0x40, 4))[0]
        if kind != donor_kind:
            raise ValueError(h['weapon'] + ': marker texture kind differs from the donor\'s')
        carriers[h['weapon']] = {'entity': h['resource'], 'stratagem': h['weapon'],
            'projectile': struct.unpack_from('<I', member(resource, 'ProjectileWeaponComponentData', 0, 4))[0],
            'records': records, 'writes': writes, 'markerKind': kind,
            'presentation': [{'component': c, 'offset': o, 'width': w, 'role': role,
                'native': member(resource, c, o, w).hex(), 'donor': member(DONOR, c, o, w).hex()}
                for c, o, w, role in PRESENTATION_MEMBERS],
            'levels': {lvl: sum(1 for w in writes if w['level'] == lvl) for lvl in ('model', 'full')}}
    readers = []
    for name in DOMAIN_COMPONENTS:
        for row in presentation.raw_slot_readers(image, slot_of(t, name)):
            pin = image.pin(row['rva'], name + ' type table read')
            readers.append({'rva': pin['rva'], 'hex': pin['bytes'], 'label': pin['role']})
    pins = []
    for group in ('promptIcon', 'spottableInstances'):
        for rva, asm, _target, role in PINS[group]:
            pin = image.pin(rva, role, asm)
            pins.append({'rva': pin['rva'], 'hex': pin['bytes'], 'label': group + ': ' + role})
    return {'build': 'F5FEE03DCFDB', 'entityManager': ENTITY_MANAGER, 'slotBase': SLOT_BASE,
        'spottableInstances': {'global': 0x3326450, 'count': 0x10, 'handles': 0x38, 'handleType': 0, 'handleEntity': 8},
        'components': comps, 'donors': {donor['name']: donor}, 'carriers': carriers,
        'pins': sorted(readers + pins, key=lambda p: p['rva']), 'levels': ['presentation', 'model', 'full'],
        'catalogNames': {k: v for k, v in by_name.items() if k in [h['weapon'] for h in hosts] + [donor['name']]}}


# ------------------------------------------------------------------------------------------------- main
def main():
    t = tables.pinned()
    go = golib.default_library()
    image = xref.CodeImage.from_snapshot('game.dll')
    pins = prove_pins(image)
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    slots = prove_slot_rule(t)
    names = names_by_path()
    weapons = t.find('equipment/support_weapons/')
    classes = component_classes(t, weapons, names)
    labels = {'EAT-17': DONOR}
    labels.update({k: t.find('support_weapons/%s/' % v)[0] for k, v in FOCUS.items()})
    candidates = carrier_candidates(t, go, weapons, names)
    focus_diffs = {k: member_diff(t, go, DONOR, labels[k]) for k in ('EAT-700', 'EAT-411', 'AC-8', 'MLS-4X')}
    res = read_resources(t, {k: labels[k] for k in ('EAT-17', 'EAT-700', 'EAT-411', 'AC-8', 'MLS-4X', 'GR-8')})
    blobs = res['blobs']
    packages = {k.split('.')[0]: package_contents(t, v, res['types']) for k, v in blobs.items()
        if k.endswith('.package')}
    focus_labels = {k: labels[k] for k in ('EAT-17', 'EAT-700', 'EAT-411', 'AC-8', 'MLS-4X', 'GR-8')}
    nodes = node_presence(t, blobs, focus_labels)
    anims = animation_events(t, blobs, focus_labels)
    options = customization_options(t, focus_labels)
    code = {'dispatcher': dispatcher_cases(image, t), 'census': census(image)}
    snaps = snapshot_facts(t)
    hosts = [c['weapon'] for c in candidates if c['eat17CloneHost']]
    eat700 = focus_diffs['EAT-700']
    checks = {
        'eat17CloneClass': next(c[0] for c in classes['classes'] if 'EAT-17 Expendable Anti-Tank' in c[0]),
        'eat17CloneHosts': hosts,
        'eat700DifferingMembers': len(eat700['members']),
        'eat700CopyMembersByAspect': {asp: sum(1 for m in eat700['members'] if m['policy'] == 'copy' and
            m['aspect'] == asp) for asp in sorted({m['aspect'] for m in eat700['members'] if m['policy'] == 'copy'})},
        'eat700ContractIdentical': not any(m['policy'] == 'identical' for m in eat700['members']),
        'eat700EveryRecordExclusive': all(v['carrier'] == 1 for v in eat700['owners'].values()),
        'eat700NeverPolicyMembers': [m['component'] + ' ' + m['offset'] for m in eat700['members']
            if m['policy'] == 'never'],
        'autoDropWeapons': {c['weapon']: c['autoDropAbility'] for c in candidates if c['autoDropAbility']},
        'autoDropOnlyWithoutWeaponReload': all('WeaponReloadComponentData' not in t.entity(int(c['resource'], 16))
            for c in candidates if c['autoDropAbility']),
        'weaponReloadGateIsWeaponReloadManager': all(v['autoDropGateManagers']['0x3326A70'] == '0x7571C8'
            for v in snaps.values()),
        'noUnitComponentCopiesInMissions': all(snaps[n]['deltaCopies']['UnitComponentData'] == 0 for n in MISSION),
        'writtenTypeTablesInPlace': {n: all(v['typeTableInPlace'].values()) for n, v in snaps.items()},
        'eat17WielderEventsInAvatar': all(e['avatarThirdPerson'] for e in anims['EAT-17']['events']
            if e['side'] == 'wielder'),
        'eat17WeaponEventsInEat17StateMachine': all(e['eat17StateMachine'] for e in anims['EAT-17']['events']
            if e['side'] == 'weapon'),
    }
    result = {
        'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0,
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'typeTableSlots': slots,
        'componentClasses': classes,
        'carrierCandidates': candidates,
        'focusDiffs': focus_diffs,
        'resources': {'packages': packages, 'nodeNames': nodes, 'animationEvents': anims,
            'customization': options, 'bytes': {k: len(v) for k, v in sorted(blobs.items())}},
        'code': code,
        'snapshots': snaps,
        'checks': checks,
        'domain': domain_data(t, image, candidates, names),
        'roundOverrides': research_clone_rounds.round_overrides(t, image, labels, hosts),
        'verdicts': VERDICTS,
        'design': DESIGN,
        'stagedTests': STAGED_TESTS,
        'openQuestions': OPEN_QUESTIONS,
        'conclusion': CONCLUSION,
    }
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; hosts', hosts, '; EAT-700 members',
        len(eat700['members']), '; checks', {k: v for k, v in checks.items() if k not in ('autoDropWeapons',)})


VERDICTS = {
    'model': {'defines': 'UnitComponent +0 UnitPath (unit resource; its bones, physics, state machine and materials '
        'come with it from the weapon\'s generated loadout package) + WeaponCustomization +0x4 default optics option '
        'and +0x78 OpticsPath (the EAT-17 sight is the separate unit lat_oneshot_sight); node names in WeaponData '
        '(+0xCC fire nodes, +0x194.. sight nodes, +0x378 node scales), ProjectileWeapon, Attachable and Interactable',
        'typeOrInstance': 'type, read in place at spawn (a copy exists only for an entity created with a delta on '
            'that component; none observed for UnitComponent)',
        'readTiming': 'when the entity is created: convert before the first carrier spawns',
        'swapAlone': 'safe only when every node-name member already matches: true for EAT-700 -> EAT-17 (all '
            'node members identical to the EAT-17\'s own), false for the AC-8 (attach_muzzle / eject absent '
            'from the EAT-17 unit)',
        'confidence': 'STRONG (code + data + snapshots; the unit consumer class is the one the EAT-17 itself uses; '
            'not live)'},
    'animations': {'defines': 'wielder side: Equipment +0x48..+0x58 / +0x6C..+0x7C animation events, +0xC0 '
        'GripType (21 = LAT), durations +0x38..+0x68, Wieldable +4/+8/+0x10/+0x14, WeaponData +0x398..+0x3A8 and '
        'FireAbility +0x3AC; weapon side: the unit\'s own state machine (comes with UnitPath)',
        'typeOrInstance': 'type (Equipment / WeaponData copies only with a delta; Wieldable has no delta case)',
        'consumers': 'the always-resident Helldiver state machines (third and first person) hold every EAT-17 '
            'wielder event; weapon-side events are in the EAT-17 unit\'s own state machine',
        'confidence': 'STRONG (data identity with the vanilla EAT-17; not live)'},
    'expendable': {'defines': 'WeaponData +0x1CC auto_drop_ability (96 for EAT-17/700/411 and MLS-4X, 97 for the '
        'MGX-42), played on the wielder by the out-of-ammo handler 0x753A10 only when the weapon has NO '
        'WeaponReload instance (and none in the manager at component world +0xEEF730); Equipment +0x88 DropMode '
        '(2 InfiniteIfNonEmpty for the EATs); single-shot WeaponMagazine (capacity 1, 0 spare magazines); no '
        'WeaponReload component',
        'typeOrInstance': 'WeaponData resolved per entity (copy, else type); Equipment likewise',
        'componentRequirement': 'WeaponMagazine present, WeaponReload ABSENT: a component-set property, so only '
            'the EAT class (and other auto-drop types) can be expendable',
        'confidence': 'CONFIRMED in code for the reader and the WeaponReload gate (pins + the gate manager '
            'identified in all seven snapshots); STRONG for the DropMode role (Filediver lead, STRONG name fit, '
            'equipment-system readers)'},
    'backblastAndSingleShot': {'defines': 'BackblastComponent (64 bytes, identical EAT-17 / EAT-700 / EAT-411), '
        'WeaponMagazine (identical), ProjectileWeapon +0 ProjType (132 EAT-17 rocket, 259 EAT-700, 34 EAT-411)',
        'confidence': 'CONFIRMED (records), STRONG (roles)'},
    'ac8ToEat': {'verdict': 'NOT an EAT clone. The AC-8 keeps WeaponReload (blocks the auto drop in 0x753A10: '
        'it can never discard itself), WeaponRounds (clip ammunition instead of a single-shot magazine) and '
        'WeaponAssistedReload (team reload); it has no Backblast and no WeaponMagazine. Components cannot be '
        'added or removed. A model / animation / rocket re-skin is technically possible but would be a reloadable, '
        'backblast-free launcher that looks like an EAT: refused as an "EAT clone"',
        'confidence': 'CONFIRMED (component sets) / CONFIRMED (gate in code)'},
    'bestCarrier': {'verdict': 'EAT-700 Expendable Napalm: the same component set, every record exclusively '
        'owned, the same magazine / backblast / auto-drop / drop mode, delivered only by its own rack, in no loot '
        'table; 19 non-presentation members to copy (model 3, animation 8, sound 3, firing 1, handling 4). '
        'Second: EAT-411 Leveller (more differences, no default optics option)',
        'confidence': 'STRONG'},
    'promptIconConsumer': {'verdict': 'the pickup prompt consumes an item\'s Spottable +0x38 and a rack\'s StratagemInfo '
        '+0xB0 through the SAME prompt entry {+0x10 name, +0x18 kind}; its widget setter 0x1868700 sets a FIXED vanilla '
        'template material per kind (0x144F800 is never called with the icon name) and resolves the icon name only '
        'through GUI API +0xD8 (exe 0x30F960: the MATERIAL resource of that name, its slot 0x3AA8B87E texture name), '
        'then binds that texture into the template. A Runtime icon family is exactly a GUI material N whose slot '
        '0x3AA8B87E names texture N: the lookup finds it; image_resources.icon_ready proves it loaded and exact before '
        'any write (the precondition under which the no-fallback loadout grid drew the family live in 0.11.0)',
        'confidence': 'CONFIRMED (code path, pins promptIcon) / STRONG (the custom family drawn there: live stage A)'},
    'multiplayer': {'verdict': 'consistent without a protocol change: type data is local memory and each machine '
        'spawns the replicated carrier entity from its own type tables, so every compatible Runtime applies the '
        'same conversion from the registered (hash-covered) definition at mission start; eligibility is the '
        'existing native_present; the carrier-weapon signature folds into the carrier-map hash input',
        'confidence': 'STRONG (design), UNKNOWN for join-in-progress timing'},
}

DESIGN = {
    'name': 'carrier weapon clone (development capability of custom stratagems)',
    'apiSketch': "delivery={family='support', items={{clone=hd2.support_weapon('EAT-17 Expendable Anti-Tank'), "
        "carrier='auto', presentation={name=<text>, icon=hd2.resources.image('eat17g'), "
        "image='EAT-17 Expendable Anti-Tank'}, modify={impact_explosion='Orbital Gas Strike'}}}}",
    'semantics': [
        'clone names the donor; the Runtime picks an unused carrier from the donor\'s clone class (identical '
        'component set, exclusive records, own rack only, no loot) unless carrier= names one from that class',
        'the delivery is the carrier\'s own vanilla rack (row redirect as today); the captured items are carrier '
        'entities',
        'at mission start, before any carrier spawns, every member whose policy is copy is set to the donor\'s '
        'reviewed vanilla value in the carrier\'s own type records, presentation per the presentation design; '
        'restored byte for byte on the ship before the armory / loadout UI',
        'modify keeps its instance-local meaning (the call\'s own entities only)',
    ],
    'safetyContract': [
        'donor records are only read (pinned research values, never a live entity)',
        'the carrier type must not be in any lobby member\'s loadout (native_present), not in loot, delivered only '
        'by its own rack, and claimed by at most one custom definition per mission',
        'component sets must be identical (clone class); members with policy identical must already be equal',
        'every written record has exactly one owner (the carrier entity)',
        'every written member is checked against its reviewed carrier value first (CONFLICT = refuse)',
        'the donor package (units, sight, bones, physics, state machine, effects, bank) is made resident through '
        'the asset loader before the first write; failure = refuse, nothing written',
        'one guarded transaction per carrier (PAGE_READONLY handling of the live-proven LoadoutEntry writes), '
        'read-back and non-target verification',
        'no restore mid-mission while a carrier instance exists (read-in-place members would desynchronise a '
        'live entity); restore on the ship with a finalizer',
        'build pins (this script\'s) re-proved; any mismatch = unavailable',
    ],
    'refused': [
        'a carrier outside the donor\'s clone class (missing or extra components), e.g. AC-8 -> EAT',
        'writing the donor\'s (or any loadout / loot weapon\'s) records',
        'policy never members: LoadoutEntry, LoadoutPackage (package / audio resource), EncyclopediaEntry +0 / '
        '+0x14 / +0x24 / +0x28, Spottable +0x14 / +0x40, Equipment +0x98 drop icon, EquipmentType, hint ids, '
        'customization slots / data',
        'partial frankenstein clones in the public API (aspects are staged internally only)',
        'changing an entity\'s type hash, adding or removing components, native patches',
        'a carrier present natively in the session; a second definition claiming the same carrier',
    ],
}

STAGED_TESTS = [
    {'stage': 'A', 'what': 'presentation only on the EAT-700 carrier (support-item-presentation stage A/B/C)',
        'writes': 'EncyclopediaEntry +8 / +0x30, Spottable +0x38',
        'pass': 'prompt, minimap, HUD panel show the EAT-17G; real EAT-17 unaffected; armory EAT-700 after restore'},
    {'stage': 'B', 'what': 'model', 'writes': 'UnitComponent +0 := lat_oneshot unit; WeaponCustomization +0x4 := '
        '0xD9AA7E19 (EAT-17 option, no delta) and +0x78 := lat_oneshot_sight',
        'needs': 'EAT-17 package resident (asset loader) before the write',
        'pass': 'pod rack, dropped, held, holstered and back-mounted models are the EAT-17; sight present; muzzle '
            'flash at the muzzle; pickup works; no crash on pickup / drop / hot-join; restore verified'},
    {'stage': 'C', 'what': 'animations', 'writes': 'Equipment +0x38 / +0x48 / +0x50 / +0x58 / +0x60 / +0x68 / '
        '+0xC0, WeaponData +0x3AC FireAbility',
        'pass': 'LAT grip, draw / holster / ammo-check / fire animations in first and third person'},
    {'stage': 'D', 'what': 'expendable logic (verification only for the EAT class: identical contract)',
        'writes': 'none', 'pass': 'after the shot the launcher is discarded (ability 96), the empty launcher decays '
            '(DropMode 2), a loaded dropped launcher stays'},
    {'stage': 'E', 'what': 'gameplay', 'writes': 'ProjectileWeapon +0 := 132, its audio members; Wieldable +0xC; '
        'WeaponData handling members (+0x148 / +0x168 / +0x16C / +0x178)', 'then': 'instance-local modify (gas)',
        'pass': 'the EAT-17 rocket and sound; the gas modification on the call\'s own projectile'},
    {'stage': 'F', 'what': 'multiplayer', 'writes': 'every machine, same set',
        'pass': 'both machines show and fire the clone; a member bringing the EAT-700 => refusal everywhere'},
]

OPEN_QUESTIONS = [
    'Join in progress: does a joining Runtime convert the carrier before the host\'s existing carrier entities are '
    'created locally? If not, refuse the clone for joiners (they see a vanilla EAT-700).',
    'Gate 2 of the auto drop (component world +0xEEF730) is unidentified; it does not matter for the EAT class.',
    'The LoadoutPackage +0x10 audio resource is not written: does the EAT-17 fire sound play from the resident '
    'EAT-17 package alone (stage E)?',
    'Default optics option 0xD9AA7E19 has no customization item / delta: confirm the hellpod path applies (or '
    'skips) DefaultCustomizations the same way for the carrier (stage B).',
    'Avatar LAT clips: they are referenced by the always-resident avatar state machines; confirm no extra package '
    'is needed when no player brings an EAT-17 (stage C).',
    'Reverse lookups by unit resource (two entity types spawning the same unit): none found among the 19 callers '
    'of the UnitComponent lookup, but not proven absent engine-wide.',
    'Should the carrier rule (vanilla carrier, mission-scoped, restored) be extended from StratagemInfo rows to '
    'weapon type records? It is the only route for model and presentation (no instance path before spawn).',
]

CONCLUSION = ('Any unused support weapon type can be re-presented, but only a type with the donor\'s exact component '
    'set can become a clone, because components are fixed per type and the expendable behaviour is a component '
    'property: the out-of-ammo handler plays WeaponData +0x1CC on the wielder only when the weapon has no '
    'WeaponReload. For the EAT-17 the clone class is {EAT-700, EAT-411}; the EAT-700 already has the EAT-17\'s '
    'magazine, backblast, auto-drop ability and drop mode, so an EAT-17 clone is 19 member copies into its own, '
    'exclusively owned type records (model 3, animation 8, sound 3, firing 1, handling 4) plus the three '
    'presentation members, applied at mission start before the first spawn and restored on the ship. The AC-8 '
    'cannot become an EAT: it keeps its reload (no discard), its clip ammunition and its team reload, and has no '
    'backblast.')


if __name__ == '__main__':
    main()
