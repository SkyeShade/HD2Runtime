"""Offline research for the custom stratagem payload families (docs/research/custom-payloads-F5FEE03DCFDB.md):
the Eagle (its jet, its strike projectile, its rockets' source), the reviewed explosion donors beyond the Gas Strike
(the Orbital EMS Strike's static field), and the Eagle use and rearm facts the custom Eagle path relies on.

Nothing is written. game.dll F5FEE03DCFDB and the retained mission snapshots:

1. The Eagle manager [game+0x3326650] (EagleComponent; its growth routine 0x8A9730 logs "EagleComponent"): the create
   callback (0x5510A0) appends a 0xFC-byte record at +0x58, the entity's handle (+0 resource, +8 entity, +0x10 network
   id) at +0x48[index], and the count at +0x1C. A per-instance type copy map sits at +0x70 (0x514B40).
2. The dispatcher's Eagle branch (delivery kind 0, 0x6AC007) spawns payload[0] itself, the Eagle jet (0x6ABFF7), and
   plans its flight through the Eagle manager (0x6AC3C3 -> 0x89EF70).
3. The jet's strike (0x8A4410, per jet index): r13 = its handle (+0x48[index]), r14 = its resolved EagleComponentData
   (0x514B40), its strike projectile type = EagleComponentData +0x18 (0x8A4591), the row from the projectile table
   (0x8A45A2), and every projectile it spawns goes through SpawnProjectile (0x13A9830) with the descriptor's source =
   the jet's own entity (handle +8: 0x8A4CFE/0x8A4D05, 0x8A572C/0x8A5748). A stack copy of the row is passed, and no
   instruction of the strike writes its impact explosion (+0x90): each rocket's own impact explosion copy is the row's.
   So one jet's rockets are exactly the pool slots whose source is that jet.
4. The donor chain of the Orbital EMS Strike's shell 74: its impact explosion 188 (a StaticField volume, stun), the
   explosion's damage row (+4), its volume template (+0x64) and the statuses both name, each row exactly as in every
   snapshot (relocated words masked), as the Gas Strike's chain is reviewed (research/bombardment-payload).
5. Every catalogued Eagle: its row's delivery kind (+0x3C = 0), uses (+0x50), linked type (+0xC8 = 49, Eagle Rearm),
   cooldown (+0x68), its payload list's jet (payload[0]) and the jet's strike projectile from the offensive stratagem
   research (EagleComponentData path [24]), with that projectile row's impact and expiry explosions.
6. A projectile weapon's own world record: the ProjectileWeapon manager [game+0x33266D8]'s create callback (0x551220)
   stores each entity's handle (the world record every component handle points at: +0 resource, +8 entity, +0x10
   network id, +0x14 flags) at +0x68[index] and maps the entity to that index (+0x50). The game's own caller of the
   ProjectileWeapon copy routine passes exactly such a handle (0x576AB1 -> 0x61AF10). So a delivered weapon or a sentry
   (with or without an AI) is reached by its ProjectileWeapon index, never by a type.
7. Who fires a jet's rockets (eagleUpdate): the EagleComponent update (0x8A7A90, called with the component world +
   0xF0B300 at 0x573F68/0x573F72, the manager the global names) walks the manager's ACTIVE entries [0, +0x20) and runs
   the strike (0x8A4410) for each with that entry's index; the strike takes the entry's own handle. So a rocket's source
   is always an entity that is in the Eagle manager's active region at that moment. The component's removal
   (0x8A9CB0) swaps the last entry into the removed index: an entry's INDEX is not stable, its entity is.
8. The game's explosion request queue (explosionQueue; RequestExplosion 0x13C0A80, research event-natives): its count
   at +0x20 (at most 0x100), and each request 0x98 bytes from +0x28: the position (+0, three f32), the explosion type
   (+0xC), the source entity (+0x10), the owner entity (+0x14), the creditor peer (+0x18, u64). Read-only.
9. The sentry donors' own weapons (sentryWeapons; type tables of the component world [game+0x346BF98]): each sentry's
   ProjectileWeapon (projectile, the rate slots X/Y/Z), magazine (pattern, capacity) and WeaponData (spread, aim
   recoil block B, the weapon-function inputs +184/+188: research weapon-functions, 2 = the rate-of-fire selector).
   A sentry whose inputs bind no rate-of-fire selector never changes slot: its X and Z rates are dormant.
10. Who fires the 110mm's rockets (eagleMount; live 2026-10-04): the rockets' pool SOURCE is not the jet but one of the
   two payload pods MOUNTED on it, and their OWNER is the jet (call #1: jet 1019, sources 1020 / 1021, owner 1019; call
   #2: jet 1160, sources 1161 / 1162, owner 1160). The jet's MountComponentData (research entity-authoring
   mountRecords[116]) mounts 0x0E8C2515261E0325 at "payload_right" (slot 0) and 0x486522867199D7F3 at "payload_left"
   (slot 1): both projectile weapons. The mount component [game+0x3326438] keeps each mounted child entity in its record
   +0x48, six per mount (index * 6 + slot) (pins re-proven here; research/pelican "gatlingTurret"). So a rocket of one
   call is a projectile whose owner is the call's jet and whose source is that jet's mounted child in the slot the
   jet's type mounts that resource in. (The strike's own SpawnProjectile path, descriptor +0x18 = the jet, is the
   source of what a strike spawns itself; the 110mm's rockets do not come from it.)
11. The AUTOMATIC donors (AUTOMATIC_DONORS): plain blasts a round requests natively on impact, each chain (explosion and
   damage row; no volume template, no status; the projectile-components catalogue: no submunition, no volume, no arc)
   exactly as in every snapshot (relocated words masked), reviewed for an automatic weapon:
   - Pelican chin autocannon: the chin turret's own round (research/pelican turretWeapon: 120) -> 234;
   - 66mm Missile Mk2: round 272 (the game's own label for it; no catalogued weapon fires it) -> 170;
   - Assault walker cannon: the Automaton assault walker's cannon round 301 -> 397 (research/enemy-attacks);
   - Exploding crossbow: the CB-9 Exploding Crossbow's bolt 249 -> 59 (its package, a primary weapon's, through the
     catalogue key player_weapon/CB-9 Exploding Crossbow);
   - Automaton explosion 27: round 302 -> 27; Illuminate explosion 392: round 166 -> 392 (no weapon in any retained
     snapshot fires these rounds: their units were never loaded).
   Each explosion row's +0x38 is its particle effect. The installed game data's archives say which packages ship it
   (scripts/hd2_game_data.py): 234's is in loadout_shared (and 20 more), 170's in the MLS-4X Commando's call-in
   package (and 21 more), 27's ONLY in packages/content/cyborgs and 392's ONLY in packages/content/illuminate (the
   Automaton and Illuminate faction content). A blast is usable only while one of its packages is resident.
12. The explosion-less carriers of that donor (impactCarriers): the Pelican CAS rounds (the standard 148, the AP4 275:
   runtime/pelican_weapon.lua) have no impact and no expiry explosion, and their flags +0xF0 (the impact-time late
   lookup, bit 12, research/projectile-rows) equal the LAS-58 Talon row 144's: the base whose Runtime-owned row with
   +0x90 = 158 exploded live (docs/custom-projectile-rows.md, F10). SpawnProjectile copies +0x90 into the hit record
   +0x7C and hit processing reads only that copy (research/projectile-pool census: SpawnProjectile is its only store),
   so one of these rounds whose copy is written before its first step reaches the same explosion step.
13. The Eagle Strafing Run's own rounds (pelicanRounds): its payload's ProjectileWeapon fires the 23mm HE cannon round
   16 (it explodes by its own row as explosion 50, the 'Strafing run cannon' automatic donor), and its magazine pattern
   is 16, 27, 27, 27 (research/offensive-stratagem-runtime). 27 is 16's plain twin: the same row but its type, its impact
   explosion (0) and the unnamed +0xD0/+0xD4. The round's spawn effect and the blast's effect both ship in the Strafing
   Run's call-in package (eagle_base). The Pelican's chin gun may fire them on its own copies.
14. The targeting system's per-instance AIM OVERRIDE (pelicanAim; build/test-artifacts/aim-research/aim-point.md): the
   targeting update 0x6BBDC0 runs every systems pass; on an instance's full path, after the target's aim node (each
   target type's single primary node: T is not "nearest" in practice) and before T = Q (0x6BCF27), it replaces Q by
   the record's curve while t (+0x50) >= 0 (mode 2 at +0x60: linear from A +0x20 to B +0x2C; +0x6C = 0: t stays). The
   aim point is Q plus the lead, into the wielder, WeaponData +0, the turret solve and the shot in the same pass. Its
   only writers are creation, init (t = -1), behaviour 50's setup / stop / speed and the action dispatcher: behaviour
   213 never reaches them. The network bits (+0x10 of the 24-byte entry) must be 0 or the full path skips it. Every
   live targeting record of every retained snapshot has it off (t = -1).
15. Behaviour 213 when it is NOT firing (pelicanIdle; build/test-artifacts/ai-research/idle-ai.md): every stage re-scores
   on the same timer, record +0x98 (P+0x90): 0.25 s, or 1 s once stages 2 / 3 reset P+0x58 to 0x20 while idle; stage 3
   (alert) re-scores every candidate and returns to 2 after 7 s; stage 4 runs one update and goes to 5; stage 5 fires
   only within 3 degrees, checked every 0.5 s on record +0xB0 (P+0xA8; its only writer 0x283D70), and has no timeout;
   nothing 100 m or more away scores. Making either timer due now (the same guarded 8-byte write the target lock uses)
   lets the game's own logic act at once.
16. The SLOW donors (SLOW_DONORS; build/test-artifacts/payload-research/payload-donors.md): a damage-over-time volume a
   slow gun's round may request on impact, each chain exactly as in every snapshot, its volume the template, seconds and
   statuses reviewed, a package of the game data shipping its effect: the EMS Mortar Sentry shell 154's expiry 180 (a
   7 s StaticField, stun), the G-4 Gas grenade's 177 (a 15 s cloud, 3 damage) and the Gas Mortar Sentry shell 342's
   impact 185 (the same cloud, no damage). At most maxRpm (60) a minute: the game holds 4096 status volumes and checks
   no count before adding one.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/custom-payloads-F5FEE03DCFDB.json'
# Every retained snapshot of this build (several sessions: a relocated word of a donor row differs between them and is
# masked); the mission ones also show the Eagle manager in a mission.
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
EAGLE_MANAGER = 0x3326650
TABLE = 0x37CB600                     # StratagemInfo rows by type
PROJECTILES = 0x37C7670               # ProjectileInfo rows by type
EXPLOSIONS, DAMAGES, TEMPLATES, STATUSES = 0x37CC920, 0x37C60C0, 0x37C5E90, 0x37C5C50
STRIDES = {'explosion': 152, 'damage': 76, 'template': 40, 'status': 152}
TABLES = {'explosion': EXPLOSIONS, 'damage': DAMAGES, 'template': TEMPLATES, 'status': STATUSES}
ROW = {'type': 0x0, 'stableId': 0x4, 'deliveryKind': 0x3C, 'uses': 0x50, 'cooldown': 0x68, 'payloads': 0x98,
    'payloadCount': 0xA0, 'linkedType': 0xC8}
EAGLE_REARM = 0x31
PROJECTILE_EXPLOSIONS = {'impact': 0x90, 'expiry': 0x9C}
PROJECTILE_FLAGS = 0xF0               # u16; bit 12 is read through the stored type on impact (research/projectile-rows)
PELICAN_CARRIERS = (148, 275)         # the Pelican CAS rounds: standard, AP4 (runtime/pelican_weapon.lua)
TALON_BASE = 144                      # the base of the live-verified impact-explosion row (custom-projectile-rows F10)
# The automatic donors (item 11): a plain blast that a round requests on impact natively. name -> that round ('chin':
# the Pelican chin turret's own, research/pelican), the explosion it must request, and the stratagem whose call-in
# package the Runtime may load to make the blast's effect resident (None: only the game loads it).
AUTOMATIC_DONORS = {
    'Pelican chin autocannon': {'round': 'chin', 'explosion': 234, 'asset': None},
    '66mm Missile Mk2': {'round': 272, 'explosion': 170, 'asset': 'MLS-4X Commando'},
    'Automaton explosion 27': {'round': 302, 'explosion': 27, 'asset': None},
    'Illuminate explosion 392': {'round': 166, 'explosion': 392, 'asset': None},
    'Strafing run cannon': {'round': 16, 'explosion': 50, 'asset': 'Eagle Strafing Run'},
    # A primary weapon is no stratagem: its package is a catalogue dependency key (core/assets) the asset loader takes.
    'Exploding crossbow': {'round': 249, 'explosion': 59, 'asset': None,
        'assetKey': 'player_weapon/CB-9 Exploding Crossbow'},
    # The Automaton assault walker's two cannons (research/enemy-attacks class assault_walker: round 301).
    'Assault walker cannon': {'round': 301, 'explosion': 397, 'asset': None},
}
# The SLOW donors (item 16): a damage-over-time volume (an EMS field, a gas cloud) a slow gun's round may request on
# impact, at most maxRpm rounds a minute (the game holds 4096 status volumes and checks no count before adding one:
# build/test-artifacts/payload-research/payload-donors.md). name -> the explosion, the round that requests it natively
# and how (None: a thrown entity's explosive detonates it), the reviewed volume (the template the Orbital EMS Strike's
# 188 or the Orbital Gas Strike's 82 uses, its seconds, its statuses), and the asset that makes its effect resident.
SLOW_DONORS = {
    # The A/M-23 EMS Mortar Sentry's shell 154 bursts into it when it expires (its impact is a plain blast, 150).
    'EMS mortar field': {'explosion': 180, 'round': 154, 'role': 'expiry', 'template': 15, 'seconds': 7.0,
        'statuses': [38], 'maxRpm': 60, 'asset': 'A/M-23 EMS Mortar Sentry'},
    # The G-4 Gas grenade (a thrown entity, no round): its explosive detonates 177 at the end of its fuse.
    'Gas grenade cloud': {'explosion': 177, 'round': None, 'role': None, 'template': 16, 'seconds': 15.0,
        'statuses': [42, 44], 'maxRpm': 60, 'asset': None, 'assetKey': 'throwable/G-4 Gas'},
    # The A/GM-17 Gas Mortar Sentry's shell 342 on impact: the same cloud with no damage.
    'Gas mortar cloud': {'explosion': 185, 'round': 342, 'role': 'impact', 'template': 16, 'seconds': 15.0,
        'statuses': [42, 44], 'maxRpm': 60, 'asset': 'A/GM-17 Gas Mortar Sentry'},
}
# The Eagle Strafing Run's own rounds (item 13), a round the Pelican's chin gun may fire on its own weapon copy: its
# payload's ProjectileWeapon fires the HE round, and its magazine pattern alternates it with its plain twin.
STRAFING_RUN = 'Eagle Strafing Run'
ROUND_MEMBERS = {'velocity': 0x20, 'mass': 0x24, 'damage': 0x3C}
EXPLOSION_EFFECT = 0x38               # an explosion row's particle effect resource (archive type 'particles')
PARTICLES = 0xA8193123526FAD64        # murmur64('particles')
# The targeting manager and its per-instance record (item 14): the aim override members the Runtime writes for one
# Pelican chin turret, and the network entry whose bits (+0x10) must be 0 (else the full path skips the override).
# Behaviour 213's timers the Runtime may make due (item 15): the re-pick (record +0x98) in stages 2/3, the fire check
# (record +0xB0) in stage 5.
IDLE_AI = {'repick': 0x98, 'fireCheck': 0xB0, 'searchStage': 2, 'alertStage': 3, 'leaveStage': 4, 'aimStage': 5,
    'fireStage': 12, 'repickPeriod': 0.25, 'idleRepickPeriod': 1.0, 'fireCheckPeriod': 0.5, 'aimDegrees': 3.0,
    'scoreCutoff': 100.0}
TARGETING = {'global': 0x3326D30, 'count': 0x140, 'map': 0x150, 'records': 0x178, 'stride': 0xD0, 'network': 0x180,
    'networkStride': 0x18, 'networkBits': 0x10, 'target': 0x0, 'point': 0x8, 'aimPoint': 0x14, 'curveA': 0x20,
    'curveB': 0x2C, 't': 0x50, 'mode': 0x60, 'advance': 0x6C, 'linearMode': 2, 'on': 1.0, 'off': -1.0}
# Package names the archive scan recognises by their murmur64 (beyond every packages/... path the repo names).
EXTRA_PACKAGE_NAMES = ['packages/content/cyborgs', 'packages/content/illuminate']
LAYOUT = {'global': EAGLE_MANAGER, 'capacity': 0x10, 'count': 0x1C, 'active': 0x20, 'handles': 0x48, 'records': 0x58,
    'stride': 0xFC,
    'typeCopies': 0x70, 'handleResource': 0x0, 'handleEntity': 0x8, 'handleNetwork': 0x10,
    'strikeProjectile': 0x18}

PROOFS = {
    'eagleManager': [
        (0x5510B4, 'mov rdi, qword ptr [rip + {rip}]', EAGLE_MANAGER, 'the Eagle manager (EagleComponent) ...'),
        (0x5510C1, 'mov eax, dword ptr [rdi + 0x1c]', None, '... its count (+0x1C) ...'),
        (0x551055, 'imul rcx, rbx, 0xfc', None, '... a record is 0xFC bytes ...'),
        (0x551062, 'add rcx, qword ptr [rdi + 0x58]', None, '... at +0x58 ...'),
        (0x55106B, 'mov rax, qword ptr [rdi + 0x48]', None, '... the entity handles at +0x48 ...'),
        (0x551076, 'mov qword ptr [rax + rbx*8], rbp', None, '... one per record'),
        (0x551082, 'inc dword ptr [rdi + 0x1c]', None, 'a jet appended'),
        (0x514B62, 'mov r11, qword ptr [rip + {rip}]', EAGLE_MANAGER, 'the resolver of a jet\'s EagleComponentData ...'),
        (0x514B97, 'mov rdi, qword ptr [r11 + 0x70]', None, '... prefers a per-instance copy (+0x70)'),
    ],
    'eagleStrike': [
        (0x8A445B, 'mov rax, qword ptr [rcx + 0x48]', None, 'a jet\'s strike: the manager\'s handles ...'),
        (0x8A4477, 'mov r13, qword ptr [rax + rsi*8]', None, '... the jet\'s own handle ...'),
        (0x8A448D, 'call 0x514b40', None, '... its resolved EagleComponentData ...'),
        (0x8A4492, 'imul rdi, rsi, 0xfc', None, '... its record ...'),
        (0x8A44A8, 'add rdi, qword ptr [rbx + 0x58]', None, '... at +0x58'),
        (0x8A4591, 'mov eax, dword ptr [r14 + 0x18]', None, 'the strike projectile type (EagleComponentData +0x18) ...'),
        (0x8A45A2, 'mov rax, qword ptr [r8 + rax*8 + 0x37c7670]', None, '... its row (a stack copy is passed)'),
        (0x8A4CFE, 'mov eax, dword ptr [r13 + 8]', None, 'the descriptor\'s source: the jet\'s entity ...'),
        (0x8A4D05, 'mov dword ptr [rbp + 0x58], eax', None, '... (descriptor +0x18) ...'),
        (0x8A4D83, 'call 0x13a9830', None, '... SpawnProjectile'),
        (0x8A572C, 'mov ecx, dword ptr [r13 + 8]', None, 'the other release: the jet\'s entity ...'),
        (0x8A5748, 'mov dword ptr [rbp + 0x88], ecx', None, '... as the source (descriptor +0x18) ...'),
        (0x8A57EB, 'call 0x13a9830', None, '... SpawnProjectile'),
    ],
    'eagleDispatch': [
        (0x6ABFF7, 'mov rdi, qword ptr [rdi]', None, 'the dispatcher: payload[0] ...'),
        (0x6AC007, 'cmp dword ptr [r14 + 0x3c], r15d', None, '... an Eagle (delivery kind 0) spawns it itself'),
        (0x6AC3C3, 'mov rcx, qword ptr [rip + {rip}]', EAGLE_MANAGER, 'the Eagle branch plans the jet\'s flight ...'),
        (0x6AC431, 'call 0x89ef70', None, '... through the Eagle manager'),
    ],
    'weaponHandle': [
        (0x551234, 'mov rdi, qword ptr [rip + {rip}]', 0x33266D8, 'the ProjectileWeapon manager\'s create ...'),
        (0x55123E, 'mov esi, dword ptr [rdi + 0x38]', None, '... its count (+0x38) is the new index ...'),
        (0x55128F, 'mov rax, qword ptr [rdi + 0x68]', None, '... its handles (+0x68) ...'),
        (0x55129A, 'mov qword ptr [rax + rbx*8], rbp', None, '... hold the entity\'s own world record ...'),
        (0x55129E, 'mov edx, dword ptr [rbp + 8]', None, '... whose +8 is the entity ...'),
        (0x5512A6, 'inc dword ptr [rdi + 0x38]', None, '... one more'),
        (0x576AB1, 'mov rdx, r12', None, 'the copy routine is given such a handle ...'),
        (0x576AB4, 'call 0x61af10', None, '... by the game itself'),
    ],
    'eagleUpdate': [
        (0x573F68, 'lea rcx, [rdi + 0xf0b300]', None, 'the Eagle manager (component world + 0xF0B300) ...'),
        (0x573F72, 'call 0x8a7a90', None, '... is updated (EagleComponent update) ...'),
        (0x8A7B25, 'cmp dword ptr [r14 + 0x20], r12d', None, '... over its ACTIVE entries [0, +0x20) ...'),
        (0x8A7B70, 'mov rax, qword ptr [r14 + 0x48]', None, '... each entry\'s handle ...'),
        (0x8A7B76, 'mov r13, qword ptr [rax + rbx*8]', None, '... (index rbx) ...'),
        (0x8A7BBC, 'call 0x8a4410', None, '... runs its strike: rockets come only from an active entry'),
        (0x8A9CCE, 'mov r8d, dword ptr [rbx + 0x20]', None, 'removal: the active bound ...'),
        (0x8A9CEF, 'call 0x8a8940', None, '... the last entry swapped into the removed index'),
    ],
    'explosionQueue': [
        (0x13C0A86, 'mov eax, dword ptr [rcx + 0x20]', None, 'RequestExplosion: the queue\'s count (+0x20) ...'),
        (0x13C0A8F, 'cmp eax, 0x100', None, '... at most 0x100 ...'),
        (0x13C0AC0, 'imul rdi, r10, 0x98', None, '... a request is 0x98 bytes ...'),
        (0x13C0AD1, 'movsd qword ptr [rdi + rcx + 0x28], xmm0', None, '... from +0x28: the position ...'),
        (0x13C0ADB, 'mov dword ptr [rdi + rcx + 0x34], r8d', None, '... +0xC the explosion type ...'),
        (0x13C0B0F, 'mov qword ptr [rdi + rbx + 0x40], rax', None, '... +0x18 the creditor peer ...'),
        (0x13C0B25, 'mov dword ptr [rdi + rbx + 0x38], r9d', None, '... +0x10 the source entity ...'),
        (0x13C0B34, 'mov dword ptr [rdi + rbx + 0x3c], ecx', None, '... +0x14 the owner entity'),
    ],
    'eagleMount': [
        (0x5AB438, 'mov rbx, qword ptr [rip + {rip}]', 0x3326438, 'the mount component ...'),
        (0x5A802B, 'call 0xfdc140', None, '... spawns each mounted child with the entity creation ...'),
        (0x5A8D0B, 'mov dword ptr [r14 + rbp*4], r8d', None, '... and keeps it in the mount record +0x48 (per slot)'),
        (0x5A851C, 'mov rax, qword ptr [rbp + 0x48]', None, 'the mount record +0x48 ...'),
        (0x5A8520, 'lea rdx, [r15 + rcx*2]', None, '... six per mount (index * 6 + slot) ...'),
        (0x5A8524, 'mov ecx, dword ptr [rax + rdx*4]', None, '... names the child entity'),
    ],
    'impactCopy': [
        (0x13AA646, 'mov ecx, dword ptr [rax + 0x90]', None, 'SpawnProjectile: the row\'s impact explosion (+0x90) ...'),
        (0x13AD7FD, 'cmp dword ptr [r14 + 0x7c], 0', None, '... the impact reads the projectile\'s own copy'),
        (0x13C2AF8, 'mov eax, dword ptr [r14 + 4]', None, 'an explosion\'s damage (+4)'),
        (0x13C28F0, 'mov rdx, qword ptr [rbx + rdx*8 + 0x37c5e90]', None, 'its volume template (+0x64) row'),
    ],    # The targeting system's per-instance aim override (item 14; build/test-artifacts/aim-research/aim-point.md): the
    # targeting update, its aim override (t >= 0: Q = the curve; mode 2: linear A to B), T = Q, the lead, the aim point
    # into the wielder, the override's only writers, the record swap and the systems-pass order.
    'pelicanAim': [
        (0x5731FA, 'call 0x6bbdc0', None, 'systems pass: targeting update 0x6BBDC0'),
        (0x573209, 'call 0x77faf0', None, 'systems pass: wielder update 0x77FAF0'),
        (0x5733F3, 'call 0x6dedb0', None, 'systems pass: turret solve 0x6DEDB0'),
        (0x57397A, 'call 0x843040', None, 'systems pass: behaviour update 0x843040'),
        (0x573F81, 'call 0x617550', None, 'systems pass: projectile weapons 0x617550'),
        (0x6BBE8E, 'cmp dword ptr [rax + rdi*8 + 0x10], 0', None, 'loop 1 skipped while network bits (+0x10) != 0'),
        (0x6BBF88, 'cmp byte ptr [rbx + 0x78], 0', None, 'AI hasTarget (Behavior record +0x78)'),
        (0x6BBFD7, 'test byte ptr [rbx + 0x60], 1', None, 'AI entry flag bit 0 (record +0x60): track the entity'),
        (0x6BBFE0, 'mov dword ptr [r15], eax', None, 'targeting +0 = the AI target entity'),
        (0x6BC08E, 'movsd xmm0, qword ptr [rbx + 0x1c]', None, 'else: the AI position (record +0x1C)'),
        (0x6BC1AA, 'call 0x8d5670', None, '... or the primary aim node (0x8D5670)'),
        (0x6BC0BD, 'movsd qword ptr [rcx + rdi*8 + 4], xmm0', None, '... into the network entry position (+4), replicated 0x7A4BDBBE'),
        (0x6BC3A8, 'mov dword ptr [rbx + rdi + 4], ecx', None, 'loop 2: the replicated target id -> targeting +4'),
        (0x6BC3D2, 'mov dword ptr [rbx + rdi], ecx', None, '... and the target entity (+0)'),
        (0x6BC4F4, 'mov r10, qword ptr [rax + 0xf12bc8]', None, 'type settings (TargetingComponentData) looked up every update'),
        (0x6BC5CA, 'cmp byte ptr [rcx + 0x3f], al', None, 'out of the frame slice and settings +0x3F == 0: light path (no T)'),
        (0x6BC87B, 'movsd xmm0, qword ptr [r14 + r13 + 8]', None, 'Q starts as the current T (+8)'),
        (0x6BC95B, 'mov eax, dword ptr [r12 + r15*8 + 0x10]', None, 'network bits (+0x10) ...'),
        (0x6BC994, 'jne 0x6be4ef', None, '... != 0: skip target and curve'),
        (0x6BC9B1, 'mov edx, dword ptr [rcx + 0x1c]', None, 'the turret aim node name (settings +0x1C)'),
        (0x6BC9B9, 'cmp byte ptr [r12 + r15*8 + 0x14], 0', None, 'AI-position flag (+0x14) ...'),
        (0x6BC9CC, 'movsd xmm0, qword ptr [r12 + r15*8 + 4]', None, '... Q = the replicated position'),
        (0x6BCBA9, 'cmp byte ptr [rax + 0x3d], 0', None, 'settings +0x3D: nearest aim node mode'),
        (0x6BCBEB, 'call 0x8d5830', None, 'Q = the target aim node nearest the turret aim node (0x8D5830)'),
        (0x6BCC32, 'call 0x8d5670', None, 'else Q = primary aim node (0x8D5670)'),
        (0x6BCCAA, 'movsd xmm1, qword ptr [r14 + r13 + 8]', None, 'target without an aim component: Q stays T'),
        (0x6BCCE6, 'movss xmm0, dword ptr [r14 + r13 + 0x50]', None, 'aim curve: t (+0x50) ...'),
        (0x6BCCF1, 'comiss xmm0, xmm11', None, '... >= 0 ...'),
        (0x6BCD16, 'call 0x6bf4c0', None, '... Q = curve(t) (0x6BF4C0)'),
        (0x6BCF27, 'movsd qword ptr [rcx + r13 + 8], xmm0', None, 'T (+8) = Q'),
        (0x6BCF2E, 'mov dword ptr [rcx + r13 + 0x10], eax', None, '...'),
        (0x6BD530, 'movss xmm12, dword ptr [rbx + rax*4 + 0xfc]', None, 'lead: the muzzle (WeaponData +0xFC)'),
        (0x6BD5DC, 'movss xmm7, dword ptr [r14 + 0x20]', None, 'lead: the projectile speed (+0x20)'),
        (0x6BD5FC, 'addss xmm9, dword ptr [rbx + rax*4 + 0x21c]', None, 'lead: the muzzle velocity (WeaponData +0x21C)'),
        (0x6BD707, 'movss dword ptr [rbp - 0x4c], xmm7', None, 'lead offset (z)'),
        (0x6BE4F4, 'test al, 2', None, 'bits path: bit 2 keeps Q = T (no target, no curve, no lead)'),
        (0x6BE648, 'call 0x6b9d10', None, 'T to the look-at component 0x33266B8 (0x6B9D10)'),
        (0x6BEAE3, 'addss xmm3, dword ptr [rbp - 0x54]', None, 'aim point = Q + lead (x)'),
        (0x6BEC29, 'movsd qword ptr [rdx + rax], xmm1', None, 'aim point into the wielder (0x3326420 +0x50, 0x3C each)'),
        (0x6BEEE6, 'movsd qword ptr [rcx + r13 + 0x14], xmm1', None, 'aim point into targeting +0x14'),
        (0x6BF4FF, 'cmp byte ptr [rdx + 0x6c], 0', None, 'curve: advance only when +0x6C'),
        (0x6BF505, 'mulss xmm0, dword ptr [rdx + 0x68]', None, '... t += dt * rate (+0x68)'),
        (0x6BF511, 'movss xmm0, dword ptr [rdx + 0x50]', None, '... else t = +0x50'),
        (0x6BF52B, 'minss xmm3, xmm0', None, '... clamp to 1'),
        (0x6BF551, 'movss dword ptr [rdx + 0x50], xmm3', None, '... t stored back'),
        (0x6BF556, 'mov ecx, dword ptr [rdx + 0x60]', None, 'curve mode (+0x60)'),
        (0x6BF602, 'mulss xmm0, dword ptr [rdx + 0x30]', None, 'mode 2: t * B (+0x2C..)'),
        (0x6BF614, 'mulss xmm12, dword ptr [rdx + 0x20]', None, 'mode 2: (1 - t) * A (+0x20..)'),
        (0x6BF639, 'movss dword ptr [rbx], xmm3', None, 'mode 2: Q.x'),
        (0x6BF934, 'mov al, 1', None, 'curve evaluator returns 1'),
        (0x6BB8A2, 'mov dword ptr [rax + rbp + 0x50], 0xbf800000', None, 'targeting init: t = -1 (curve off)'),
        (0x6C0F4F, 'mov dword ptr [rdx + rax + 0x50], 0xbf800000', None, 'curve stop: t = -1'),
        (0x6C0441, 'mov byte ptr [rdi + 0x6c], 0', None, 'curve setup: +0x6C = 0'),
        (0x6C0449, 'mov dword ptr [rdi + 0x50], 0', None, 'curve setup: t = 0'),
        (0x6C057B, 'mov dword ptr [rdi + 0x60], 2', None, 'curve setup: mode 2'),
        (0x6BFA1B, 'movss dword ptr [rax + 0x68], xmm0', None, 'curve speed: rate = 1 / duration'),
        (0x6BFA20, 'mov byte ptr [rax + 0x6c], 1', None, 'curve speed: +0x6C = 1'),
        (0x6C15E0, 'imul r8, r14, 0xd0', None, 'targeting records are swapped (0xD0 each)'),
        (0x4AF3CF, 'test byte ptr [rbx + 0x58], 1', None, 'AI refresh: entry bit 0 ...'),
        (0x4AF3F2, 'movsd qword ptr [rbx + 0x14], xmm0', None, '... P+0x14 = target root (node 0), every update'),
        (0x283DC0, 'call 0x4bc5d0', None, '213 stage 5: turret root ...'),
        (0x283DDF, 'call 0x4b0c40', None, '... the AI aim point (0x4B0C40) ...'),
        (0x283E02, 'call 0x4b54d0', None, '... barrel within 3 degrees'),
        (0x4B0D3B, 'call 0x8d5830', None, 'AI aim point: nearest aim node'),
        (0x4B0D4C, 'call 0x8d5670', None, '... or primary aim node'),
        (0x8D5728, 'mov edx, dword ptr [rcx + rax]', None, 'primary aim node index (record +0)'),
        (0x8D5929, 'cmp dword ptr [rbx + rdx + 0x50], edi', None, 'extra aim nodes: count +0x50'),
        (0x8D4785, 'mov dword ptr [rdi], eax', None, 'creation: record +0 = node of the type +0xC name'),
        (0x8D47B7, 'inc dword ptr [rdi + 0x50]', None, 'creation: count of extra aim nodes'),
        (0x782456, 'call 0x755080', None, 'wielder update: WeaponData +0 (0x755080)'),
        (0x75511F, 'movsd qword ptr [rcx], xmm0', None, 'WeaponData +0 written'),
        (0x6DF123, 'movsd xmm6, qword ptr [rbp]', None, 'turret solve reads WeaponData +0'),
        (0x6DFABA, 'movsd qword ptr [rbp], xmm0', None, 'turret solve writes back the achieved pointing'),
    ],
    # Behaviour 213 when it is not firing (item 15; build/test-artifacts/ai-research/idle-ai.md): its stage dispatch, the
    # stage 2/3 re-pick timer (P+0x90, record +0x98: 0.25 s or 1 s), stage 4 and 5 transitions, the stage 5 fire check
    # (P+0xA8, record +0xB0: every 0.5 s, within 3 degrees) and its only writer, the scoring cutoff.
    'pelicanIdle': [
        (0x47523E, 'mov ecx, dword ptr [r8 + rax*4 + 0x47a1a4]', None, '213 update: stage jump table 0x47A1A4 (stages 1..12)'),
        (0x475259, 'add rcx, 0x1e8480', None, 'stage 1: P+0x180 + 2 s ...'),
        (0x47526A, 'mov edx, 6', None, '... then stage 6'),
        (0x475282, 'call 0x2809a0', None, 'stage 2 handler'),
        (0x475292, 'call 0x281bc0', None, 'stage 3 handler'),
        (0x47529F, 'call 0x282d20', None, 'stage 4 handler'),
        (0x4752AF, 'call 0x2833e0', None, 'stage 5 handler'),
        (0x47535F, 'call 0x2846f0', None, 'stage 12 handler'),
        (0x8431CB, 'test byte ptr [r14 + 0x14], 2', None, 'Behavior update skips a handle with flags bit 1 (value 2)'),
        (0x843210, 'cmp byte ptr [rsi + rbp + 0x78], 0', None, 'with a target (P+0x70) ...'),
        (0x843220, 'call 0x889320', None, '... the target entry copy P+0x10.. is refreshed from the live perception entry every update'),
        (0x8432B0, 'call 0x4af390', None, 'then the target refresh (validity, last seen)'),
        (0x8434A0, 'cmp dword ptr [rsi + rbp + 0xc], -1', None, 'a pending stage (record +0xC) ...'),
        (0x8434C4, 'call 0x48ee50', None, '... is applied through the behaviour transition ...'),
        (0x8434D4, 'call 0x472f60', None, '... and the (new) stage update runs in the same frame'),
        (0x285847, 'mov dword ptr [rax + 8], edx', None, '0x285810: transitioning = new stage'),
        (0x2858A6, 'mov ecx, dword ptr [rdx + rbx*4 + 0x285f94]', None, 'stage-entry jump table 0x285F94'),
        (0x285F6B, 'mov dword ptr [rax + 8], 0xffffffff', None, 'transitioning = -1 at the end'),
        (0x2859FF, 'mov qword ptr [rdx + 0x90], rcx', None, 'entering 2: re-pick due now'),
        (0x285A9F, 'mov qword ptr [rcx + 0x90], rax', None, 'entering 3: re-pick due now'),
        (0x285AB1, 'mov qword ptr [rcx + 0x178], rax', None, 'entering 3: P+0x178 = now (replicated 0x800000)'),
        (0x285B18, 'mov qword ptr [rcx + 0x188], rax', None, 'entering 3 with flag bit 2 clear: alert start P+0x188 = now'),
        (0x285B4E, 'mov qword ptr [rdx + 0x90], rcx', None, 'entering 4: re-pick due now'),
        (0x285B66, 'and ecx, 0xfffffffd', None, 'entering 4: flag bit 1 cleared'),
        (0x285B8E, 'call 0x4bc9e0', None, 'entering 4: trigger released'),
        (0x285B93, 'mov edx, 0x9e6', None, 'entering 4: event 0x9E6 (0x4C3210)'),
        (0x285BB4, 'mov qword ptr [rdx + 0x90], rcx', None, 'entering 5: ONLY the re-pick is made due (P+0xA8 untouched)'),
        (0x285F58, 'mov qword ptr [rdx + 0x90], rcx', None, 'entering 12: re-pick due now'),
        (0x285F62, 'call 0x4bc940', None, 'entering 12: trigger pulled'),
        (0x280AC0, 'cmp qword ptr [rcx + 0x90], rdx', None, 'stage 2: re-pick only when P+0x90 <= now'),
        (0x280ACD, 'cmp dword ptr [rcx + 0x58], r13d', None, 'interval: P+0x58 (target entry flags) == 0 ...'),
        (0x280AD3, 'movss xmm0, dword ptr [rip + 0x2145de5]', None, '... 0.25 s, else 1.0 s ...'),
        (0x280AE1, 'mulss xmm0, dword ptr [rip + 0x21473d7]', None, '... x 1e6 us'),
        (0x280AF8, 'mov qword ptr [rcx + 0x90], rax', None, 'stage 2: next re-pick'),
        (0x281CDF, 'cmp qword ptr [rcx + 0x90], rdx', None, 'stage 3: same timer'),
        (0x281D17, 'mov qword ptr [rcx + 0x90], rax', None, 'stage 3: next re-pick'),
        (0x282E39, 'cmp qword ptr [rcx + 0x90], rdx', None, 'stage 4: same timer'),
        (0x2834D1, 'cmp qword ptr [rcx + 0x90], rdx', None, 'stage 5: same timer'),
        (0x283508, 'mov qword ptr [rcx + 0x90], rax', None, 'stage 5: next re-pick'),
        (0x2847CF, 'mov qword ptr [rcx + 0x90], rax', None, 'stage 12: next re-pick (same rule)'),
        (0x281408, 'mov dword ptr [rax + 0x58], 0x20', None, 'stage 2 idle reset: P+0x58 = 0x20 (so the idle period is 1 s)'),
        (0x2825F4, 'mov dword ptr [rax + 0x58], 0x20', None, 'stage 3 idle reset: P+0x58 = 0x20'),
        (0x280B23, 'mov ecx, dword ptr [r8 + 0xd20]', None, 'candidates: list C ...'),
        (0x280B2A, 'add ecx, dword ptr [r8 + 0x818]', None, '... + B ...'),
        (0x280B31, 'add ecx, dword ptr [r8 + 0x310]', None, '... + A (+ up to 3 extra slots)'),
        (0x280BBC, 'movups xmmword ptr [rcx + 0x10], xmm0', None, 'each candidate copied into P+0x10 while scored'),
        (0x280BF3, 'call 0x8859c0', None, 'factor: perceived (entry sense bits x sensors) 0/1'),
        (0x280BFF, 'call 0x4b4fd0', None, 'factor: hostile 0/1'),
        (0x280C0B, 'call 0x4b1e80', None, 'factor: 1 - dead'),
        (0x280C17, 'call 0x4b4cb0', None, 'factor: has a health record 0/1'),
        (0x280C26, 'call 0x4b4250', None, 'factor: targetable (component 0x3326D20) 0/1'),
        (0x280CE6, 'call 0x7582d0', None, 'factor input: barrel angle (deg) to the target'),
        (0x280DBE, 'mov dword ptr [rbp + 0x18], 0x43340000', None, 'angle curve (0,1)(45,0.9)(180 -> ...'),
        (0x280DC5, 'mov dword ptr [rbp + 0x1c], 0x3f4ccccd', None, '... 0.8): never below 0.8'),
        (0x280E9E, 'mov qword ptr [rbp - 0x20], 0x42c80000', None, 'distance curve (5,1)(40,0.8)(100,0): 0 at >= 100 m'),
        (0x280F52, 'cmp esi, dword ptr [rbx + 0x68]', None, 'previous target (P+0x68) x1.0, others x0.9'),
        (0x280D55, 'call 0x4b25b0', None, 'class 3 -> 0'),
        (0x280D68, 'call 0x4b25b0', None, 'class 2 -> x0.5'),
        (0x280D7E, 'bt rax, 0x23', None, 'entity flag 35 -> 0'),
        (0x2812F3, 'call 0x4af4e0', None, 'stage 2: the best (> 0) through the setter'),
        (0x28130B, 'mov dword ptr [rax + 0x58], r13d', None, 'none: target cleared (P+0x58 = 0 ...)'),
        (0x2819F8, 'mov edx, 4', None, 'the current target scores > 0: stage 4 (same update)'),
        (0x281A0B, 'movss xmm2, dword ptr [rip + 0x2145a91]', None, 'idle sweep: barrel within 5 deg of the look point ...'),
        (0x281AA0, 'add rax, 0x1e8480', None, '... then 2 s ...'),
        (0x281AB5, 'mov edx, 6', None, '... stage 6 (new look direction via 7/8/9)'),
        (0x280A26, 'mov edx, 0xa', None, 'no rounds and no spares: stage 10'),
        (0x2824DD, 'call 0x4af4e0', None, 'stage 3 re-scores ALL candidates (not only the last position)'),
        (0x282618, 'mov rcx, qword ptr [rax + 0x188]', None, 'alert start P+0x188 ...'),
        (0x282626, 'add rcx, 0x6acfc0', None, '... + 7 s with no valid target ...'),
        (0x282671, 'mov edx, 2', None, '... stage 2'),
        (0x282B3F, 'mov edx, 4', None, 'the current target scores > 0: stage 4'),
        (0x282DF1, 'movups xmmword ptr [rax + 0x10], xmm0', None, 'stage 4 zeroes the target block P+0x10..0x5F ...'),
        (0x282E17, 'mov byte ptr [rax + 0x70], sil', None, '... P+0x70 = 0 ...'),
        (0x282E26, 'mov dword ptr [rcx + 0x68], eax', None, '... previous target = invalid'),
        (0x28308D, 'mov dword ptr [rbp - 0x10], 0x433e0000', None, 'stage-4 angle curve (0,0)(185,0)(190,1): nothing in 0..180 deg scores'),
        (0x283312, 'mov edx, 0xd', None, '(unreachable) stage 13'),
        (0x28335A, 'mov edx, 5', None, 'otherwise stage 5, at once (one update, no timer)'),
        (0x283D12, 'call 0x4af4e0', None, 'stage 5: the best through the setter'),
        (0x283D5D, 'cmp qword ptr [rcx + 0xa8], rax', None, 'fire check only when P+0xA8 <= now ...'),
        (0x283D6A, 'add rax, 0x7a120', None, '... every 0.5 s ...'),
        (0x283D70, 'mov qword ptr [rcx + 0xa8], rax', None, '... P+0xA8 = now + 0.5 s (its only writer)'),
        (0x283DE4, 'movss xmm2, dword ptr [rip + 0x2143494]', None, 'barrel within 3.0 deg ...'),
        (0x283E02, 'call 0x4b54d0', None, '... of the target aim point'),
        (0x283F15, 'comiss xmm2, xmm8', None, 'lose score (no target / not perceived / not hostile / dead) beats fire ...'),
        (0x28405B, 'mov qword ptr [r8 + 0x188], rcx', None, '... alert start = now ...'),
        (0x284079, 'mov edx, 3', None, '... stage 3'),
        (0x284088, 'mov edx, 0xc', None, 'fire score 1: stage 12'),
        (0x4AF4FA, 'mov r8, qword ptr [rcx + 8]', None, 'setter reads P only'),
        (0x4AF718, 'jmp 0x4af390', None, 'setter: no replication call; tail-calls the refresh'),
        (0x885A71, 'mov r10d, dword ptr [r14 + 0x4c]', None, 'perceived: the COPY P+0x5C (entry +0x4C) ...'),
        (0x885A7A, 'bt r10d, edx', None, '... has a sensor bit'),
        (0x887836, 'mov rcx, qword ptr [r15 + 0x13d8]', None, 'perceiver refresh only when +0x13D8 (next) <= now ...'),
        (0x887893, 'mov qword ptr [r15 + 0x13d8], rax', None, '... next = now + uniform(S+0, S+4) s (type settings)'),
        (0x887340, 'mov ecx, dword ptr [rbx + 0x13ac]', None, 'candidate gather: round-robin cursor over all faction entities ...'),
        (0x8875B4, 'cmp dword ptr [rbx + 0x1368], 8', None, '... at most 8 candidates per refresh'),
        (0x510191, 'mov r11, qword ptr [rax + 0xf12d48]', None, 'perception type settings: world +0xF12D48 ...'),
        (0x5101A9, 'imul eax, edx, 0x27e', None, '... 0x27E slots, 0x18-byte records from +0x27E0'),
        (0x50378F, 'mov r10, qword ptr [rax + 0xf12a70]', None, 'vision type settings: world +0xF12A70 ...'),
        (0x5037B3, 'imul eax, eax, 0x272', None, '... 0x272 slots ...'),
        (0x503801, 'imul rax, rcx, 0x2c', None, '... 0x2C-byte records ...'),
        (0x503805, 'add rax, 0x2720', None, '... from +0x2720'),
        (0x64C46C, 'movss dword ptr [rdi + rbx*8 + 0xc], xmm0', None, 'instance range +0xC = type range x instance multiplier'),
        (0x64C9AC, 'sub ecx, 1', None, 'sensor type 1 ...'),
        (0x64CDB1, 'movss xmm0, dword ptr [r14 + rbp*8 + 0xc]', None, '... front range ...'),
        (0x64CDBA, 'movss xmm0, dword ptr [r14 + rbp*8 + 0x14]', None, '... rear range ...'),
        (0x64CDDD, 'mulss xmm6, dword ptr [r14 + rbp*8 + 0x10]', None, '... side range (blended by the horizontal angle; no cone test)'),
        (0x64CE45, 'comiss xmm6, xmm10', None, 'in range: range > distance'),
        (0x64C8B2, 'movss xmm3, dword ptr [rax + 0x78af9dc]', None, 'a mission-wide sight limit (-1 = none in the snapshots)'),
        (0x7584F9, 'mulss xmm0, dword ptr [rip + 0x1c6f22f]', None, 'barrel angle = acos(dot) x 57.2958: 0..180 deg'),
    ],
}


# The component world's entity-type tables (research/pelican "turretWeapon", "aim"): offset, slots, records, stride.
WORLD = 0x346BF98
TYPE_TABLES = {'projectileWeapon': (0xF12E80, 542, 0x21E0, 0x268), 'magazine': (0xF124A0, 540, 0x21C0, 0xA0),
    'weaponData': (0xF12BD8, 730, 0x2DA0, 0x4D0)}
WEAPON_FUNCTION = {'left': 184, 'right': 188, 'rateOfFire': 2}
SENTRY_WEAPONS = {'A/MG-43 Machine Gun Sentry': 0x37CDE43876BA26BB, 'A/G-16 Gatling Sentry': 0xEF85D6CF58E31D70,
    'MG-206 Heavy Machine Gun': 0x085C1EDB038EC24E}
EXPLOSION_QUEUE = {'global': 0x346D558, 'count': 0x20, 'capacity': 0x100, 'entries': 0x28, 'stride': 0x98,
    'position': 0x0, 'type': 0xC, 'source': 0x10, 'owner': 0x14, 'creditor': 0x18}


def type_lookup(mem, table, slots, key):
    i = key % slots
    for _ in range(slots):
        k, index = struct.unpack('<QQ', mem.read(table + 16 * i, 16))
        if k == key:
            return index & 0xFFFFFFFF
        if k == 0:
            return None
        i = 0 if i == slots - 1 else i + 1
    return None


def sentry_weapons(name):
    """The sentry donors' own weapon type records (and the MG-206's, whose rate-of-fire selector is bound)."""
    mem = base.Mem(name)
    world = mem.ptr(mem.game + WORLD)
    out = {}
    for label, resource in SENTRY_WEAPONS.items():
        rec = {}
        for kind, (off, slots, records, stride) in TYPE_TABLES.items():
            table = mem.ptr(world + off)
            i = type_lookup(mem, table, slots, resource)
            rec[kind] = mem.read(table + records + stride * i, stride) if i is not None else None
        pw, mag, wd = rec['projectileWeapon'], rec['magazine'], rec['weaponData']
        out[label] = {'resource': '%016X' % resource, 'projectile': struct.unpack_from('<I', pw, 0)[0],
            'rateSlots': [round(v, 3) for v in struct.unpack_from('<3f', pw, 4)],
            'magazinePattern': struct.unpack_from('<I', mag, 0)[0] != 0,
            'capacity': struct.unpack_from('<I', mag, 0x88)[0],
            'spread': [round(v, 3) for v in struct.unpack_from('<2f', wd, 84)],
            'spreadWord': struct.unpack_from('<I', wd, 92)[0],
            'recoilB': [round(v, 4) for v in struct.unpack_from('<2f', wd, 28)],
            'inputs': list(struct.unpack_from('<2I', wd, WEAPON_FUNCTION['left']))}
        out[label]['rateSelectorBound'] = WEAPON_FUNCTION['rateOfFire'] in out[label]['inputs']
    mem.close()
    return out


def rows_of(mem):
    """Every StratagemInfo row: {type: (row address, stable id)}."""
    out = {}
    for i in range(1, 160):
        p = mem.ptr(mem.game + TABLE + 8 * i)
        if p and mem.u32(p + ROW['type']) == i:
            out[i] = (p, mem.u32(p + ROW['stableId']))
    return out


def chain_of(mem, explosion):
    """The donor chain of an explosion: [(kind, id, bytes)] - the explosion, its damage row, its volume template and
    every status the damage row or the template names."""
    g = mem.game
    def row(kind, ident):
        p = mem.ptr(g + TABLES[kind] + 8 * ident)
        return mem.read(p, STRIDES[kind]) if p else None
    out = []
    x = row('explosion', explosion)
    if not x or struct.unpack_from('<I', x, 0)[0] != explosion:
        raise ValueError('explosion %d is not its row' % explosion)
    out.append(('explosion', explosion, x))
    damage = struct.unpack_from('<I', x, 4)[0]
    template = struct.unpack_from('<I', x, 0x64)[0]
    d = row('damage', damage)
    out.append(('damage', damage, d))
    statuses = []
    for o in range(0x2C, 0x4C, 8):
        s = struct.unpack_from('<I', d, o)[0]
        if s:
            statuses.append(s)
    if template:
        t = row('template', template)
        out.append(('template', template, t))
        for o in range(4, 0x24, 8):
            s = struct.unpack_from('<I', t, o)[0]
            if s and s not in statuses:
                statuses.append(s)
    for s in statuses:
        out.append(('status', s, row('status', s)))
    return out, {'damage': damage, 'template': template, 'seconds': struct.unpack_from('<f', x, 0x68)[0],
        'statuses': statuses}


MOUNT = {'global': 0x3326438, 'map': 32, 'children': 0x48, 'slots': 6, 'stride': 24}


def eagle_mounts(eagles):
    """Each Eagle jet's mounted children (research/entity-authoring mountRecords: the jet's MountComponentData)."""
    data = json.loads((ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    out = {}
    for name, e in eagles.items():
        records = [r for r in data['mountRecords'] if e['payload'].upper() in [o.upper() for o in r.get('owners', [])]]
        if len(records) != 1:
            raise ValueError('%s: %d mount records' % (name, len(records)))
        out[name] = [{'slot': s['slot'], 'resource': s['path'][2:].upper(), 'node': s['attachNodeName']}
            for s in records[0]['slots']]
        for item in out[name]:
            child = data['mountedEntities'].get('0x' + item['resource'])
            item['weapon'] = bool(child and child.get('weapon'))
    return out


def offensive_eagles():
    """The catalogued Eagles and their jets' strike projectile (research/offensive-stratagem-runtime: the payload's
    EagleComponentData path [24])."""
    data = json.loads((ROOT / 'research/offensive-stratagem-runtime-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    out = {}
    for s in data['stratagems']:
        if s.get('family') != 'Eagle':
            continue
        strike = None
        for p in s.get('payloadReports') or []:
            for c in p['components']:
                if c['name'] == 'EagleComponentData':
                    for ref in c.get('typedReferences') or []:
                        if ref['path'] == [24] and ref['referenceClass'] == 'ProjectileType':
                            strike = ref['values'][0]
        out[s['name']] = {'stableId': s['currentRoot']['id'], 'payload': s['historicalIdentity']['payloads'][0],
            'strikeProjectile': strike, 'uses': s['currentRoot']['use_count'], 'cooldown': s['currentRoot']['cooldown']}
    return out


def pelican_round():
    """The chin turret's own round: research/pelican's observed type projectile (the same in every mission snapshot)."""
    data = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    kinds = {s['types']['chinTurret']['projectileType'] for s in data['turretWeapon']['snapshots'].values()}
    if kinds != {data['turretWeapon']['observed']['chinTurret']['projectileType']} or len(kinds) != 1:
        raise ValueError('the chin turret\'s round differs between the Pelican research snapshots: %r' % kinds)
    return kinds.pop()


def catalogued_explosion(explosion):
    """The projectile-components catalogue's definition of an impact explosion (its submunition, volume and arc)."""
    data = json.loads((ROOT / 'research/projectile-components-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    for group in data['components']['impact_explosion']['groups']:
        if group['values'].get('impact_explosion') == explosion:
            return group.get('definition')
    raise ValueError('explosion %d is not in the projectile-components catalogue' % explosion)


# The radii and damage members of an explosion's chain rows (the explosion: inner / outer / shockwave radii; its damage
# row: standard, durable, the four armour penetrations), checked against the catalogue on every automatic donor.
EXPLOSION_RADII = (0x10, 0x14, 0x18)
DAMAGE_MEMBERS = {'standard': 0x4, 'durable': 0x8, 'armorPenetration': 0xC}


def chain_definition(chain):
    """(radii, damage) of an explosion's chain [(kind, id, hex)] from its rows (EXPLOSION_RADII, DAMAGE_MEMBERS)."""
    rows = {kind: bytes.fromhex(raw) for kind, _, raw in chain if kind in ('explosion', 'damage')}
    x, d = rows['explosion'], rows['damage']
    radii = [round(struct.unpack_from('<f', x, o)[0], 3) for o in EXPLOSION_RADII]
    damage = {'standard': struct.unpack_from('<I', d, DAMAGE_MEMBERS['standard'])[0],
        'durable': struct.unpack_from('<I', d, DAMAGE_MEMBERS['durable'])[0],
        'armorPenetration': list(struct.unpack_from('<4I', d, DAMAGE_MEMBERS['armorPenetration']))}
    return radii, damage


def effect_packages(effects):
    """{effect resource: [{id, name}]}: every package of the installed game data that ships that particles resource
    (scripts/hd2_game_data.py, read-only), named when a known package path hashes to it."""
    import glob
    import re
    import hd2_game_data
    names = set(EXTRA_PACKAGE_NAMES)
    for path in glob.glob(str(ROOT / 'research/*.json')) + glob.glob(str(ROOT / 'domains/*.lua')):
        names.update(re.findall(r'packages/[A-Za-z0-9_/\-\.]+', Path(path).read_text(encoding='utf-8', errors='ignore')))
    by_hash = {hd2_game_data.murmur64(n.encode()): n for n in names}
    out = {effect: [] for effect in effects}
    for archive, rname, rtype, _main, _stream, _gpu in hd2_game_data.Data().tables():
        if rname in out and rtype == PARTICLES:
            package = int(archive, 16)
            out[rname].append({'id': '0x%016X' % package, 'name': by_hash.get(package)})
    for effect in out:
        out[effect].sort(key=lambda p: p['id'])
    return out


def targeting_overrides(mem):
    """Every live targeting record's aim override state: {instances, t values by count, modes} (None outside a world)."""
    mgr = mem.ptr(mem.game + TARGETING['global'])
    if not mgr:
        return None
    count = mem.u32(mgr + TARGETING['count']) or 0
    records = mem.ptr(mgr + TARGETING['records'])
    if not records or count > 4096:
        return None
    ts, modes = {}, {}
    for i in range(count):
        raw = mem.read(records + i * TARGETING['stride'], TARGETING['stride'])
        t = round(struct.unpack_from('<f', raw, TARGETING['t'])[0], 3)
        mode = struct.unpack_from('<I', raw, TARGETING['mode'])[0]
        ts[str(t)] = ts.get(str(t), 0) + 1
        modes[str(mode)] = modes.get(str(mode), 0) + 1
    return {'instances': count, 't': ts, 'modes': modes}


def strafing_rounds():
    """The Eagle Strafing Run payload's own rounds (research/offensive-stratagem-runtime: its ProjectileWeapon's round
    and its magazine pattern)."""
    data = json.loads((ROOT / 'research/offensive-stratagem-runtime-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    for s in data['stratagems']:
        if s['name'] != STRAFING_RUN:
            continue
        out = {}
        for p in s.get('payloadReports') or []:
            for c in p['components']:
                for ref in c.get('typedReferences') or []:
                    if ref['referenceClass'] != 'ProjectileType':
                        continue
                    if c['name'] == 'ProjectileWeaponComponentData' and ref['path'] == [0]:
                        out['projectile'] = ref['values'][0]
                    if c['name'] == 'WeaponMagazineComponentData' and ref['path'] == [4, 0, 0]:
                        out['pattern'] = list(ref['values'])
        return out
    raise ValueError('no Eagle Strafing Run in the offensive stratagem research')


def round_row(mem, kind):
    """A ProjectileInfo row's identity members (type, velocity, mass, damage record), its explosions and its bytes."""
    r = mem.ptr(mem.game + PROJECTILES + 8 * kind)
    raw = mem.read(r, 272) if r else None
    if not raw or struct.unpack_from('<I', raw, 0)[0] != kind:
        return None
    return {'type': kind, 'velocity': struct.unpack_from('<f', raw, ROUND_MEMBERS['velocity'])[0],
        'mass': struct.unpack_from('<f', raw, ROUND_MEMBERS['mass'])[0],
        'damage': struct.unpack_from('<I', raw, ROUND_MEMBERS['damage'])[0],
        'impact': struct.unpack_from('<I', raw, PROJECTILE_EXPLOSIONS['impact'])[0],
        'expiry': struct.unpack_from('<I', raw, PROJECTILE_EXPLOSIONS['expiry'])[0], 'raw': raw.hex()}


def projectile_explosions(mem, kind):
    """A ProjectileInfo row's impact and expiry explosions and its flags +0xF0, or None."""
    r = mem.ptr(mem.game + PROJECTILES + 8 * kind)
    if not r or mem.u32(r) != kind:
        return None
    return {'impact': mem.u32(r + PROJECTILE_EXPLOSIONS['impact']), 'expiry': mem.u32(r + PROJECTILE_EXPLOSIONS['expiry']),
        'flags': struct.unpack_from('<H', mem.read(r + PROJECTILE_FLAGS, 2))[0]}


def observe(name, eagles, rounds, strafing_types=()):
    mem = base.Mem(name)
    g = mem.game
    m = mem.ptr(g + EAGLE_MANAGER)
    count, capacity = mem.u32(m + LAYOUT['count']), mem.u32(m + LAYOUT['capacity'])
    jets = []
    handles = mem.ptr(m + LAYOUT['handles'])
    for i in range(min(count or 0, 64)):
        h = mem.ptr(handles + 8 * i)
        jets.append({'resource': '0x%016X' % mem.u64(h), 'entity': mem.u32(h + 8)} if h else None)
    rows = rows_of(mem)
    by_id = {sid: (t, p) for t, (p, sid) in rows.items()}
    seen = {}
    for ename, e in eagles.items():
        t, p = by_id[e['stableId']]
        count_ = mem.u32(p + ROW['payloadCount'])
        jet = '0x%016X' % mem.u64(mem.ptr(p + ROW['payloads'])) if count_ else None
        rocket = None
        if e['strikeProjectile']:
            r = mem.ptr(g + PROJECTILES + 8 * e['strikeProjectile'])
            if r and mem.u32(r) == e['strikeProjectile']:
                rocket = {'impact': mem.u32(r + PROJECTILE_EXPLOSIONS['impact']),
                    'expiry': mem.u32(r + PROJECTILE_EXPLOSIONS['expiry'])}
        seen[ename] = {'type': t, 'deliveryKind': mem.u32(p + ROW['deliveryKind']),
            'uses': struct.unpack_from('<i', mem.read(p + ROW['uses'], 4))[0],
            'linkedType': mem.u32(p + ROW['linkedType']), 'cooldown': struct.unpack_from('<f', mem.read(p + ROW['cooldown'], 4))[0],
            'jet': jet, 'rocket': rocket}
    rearm = rows.get(EAGLE_REARM)
    chain, links = chain_of(mem, 188)
    # Each automatic donor's round, its explosion's chain and effect, and the explosion-less carriers with the Talon base.
    automatic = {}
    for dname, kind in rounds.items():
        r = projectile_explosions(mem, kind)
        explosion = r and r['impact']
        dchain, dlinks = chain_of(mem, explosion) if explosion else ([], None)
        x = mem.ptr(g + TABLES['explosion'] + 8 * explosion) if explosion else None
        automatic[dname] = {'round': r, 'chain': [(k, i, b.hex()) for k, i, b in dchain], 'links': dlinks,
            'effect': mem.u64(x + EXPLOSION_EFFECT) if x else None}
    slow = {}
    for dname, spec in SLOW_DONORS.items():
        dchain, dlinks = chain_of(mem, spec['explosion'])
        x = mem.ptr(g + TABLES['explosion'] + 8 * spec['explosion'])
        slow[dname] = {'round': projectile_explosions(mem, spec['round']) if spec['round'] else None,
            'chain': [(k, i, b.hex()) for k, i, b in dchain], 'links': dlinks, 'effect': mem.u64(x + EXPLOSION_EFFECT)}
    carriers = {kind: projectile_explosions(mem, kind) for kind in (TALON_BASE,) + PELICAN_CARRIERS}
    strafing = {kind: round_row(mem, kind) for kind in strafing_types}
    shell74 = mem.ptr(g + PROJECTILES + 8 * 74)
    out = {'snapshot': name, 'eagleManager': {'count': count, 'capacity': capacity, 'jets': jets}, 'eagles': seen,
        'eagleRearm': {'type': EAGLE_REARM, 'stableId': rearm[1] if rearm else None,
            'cooldown': struct.unpack_from('<f', mem.read(rearm[0] + ROW['cooldown'], 4))[0] if rearm else None},
        'shell74': {'impact': mem.u32(shell74 + PROJECTILE_EXPLOSIONS['impact']),
            'expiry': mem.u32(shell74 + PROJECTILE_EXPLOSIONS['expiry'])} if shell74 else None,
        'emsChain': [(k, i, b.hex()) for k, i, b in chain], 'emsLinks': links,
        'automatic': automatic, 'slow': slow, 'carriers': carriers, 'strafing': strafing,
        'targeting': targeting_overrides(mem)}
    mem.close()
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    # No strike instruction writes the row copy's impact explosion: the copy sits at rbp+0x220 or rbp+0x330.
    strike = list(image.md.disasm(data[0x8A4410:0x8A59B0], 0x8A4410))
    stores = [i for i in strike if i.op_str.split(',')[0].strip() in ('dword ptr [rbp + 0x2b0]', 'dword ptr [rbp + 0x3c0]')]
    if stores:
        raise ValueError('the strike writes its row copy\'s impact explosion: %r' % [hex(i.address) for i in stores])
    eagles = offensive_eagles()
    mounts = eagle_mounts(eagles)
    if mounts['Eagle 110mm Rocket Pods'] != [
            {'slot': 0, 'resource': '0E8C2515261E0325', 'node': 'payload_right', 'weapon': True},
            {'slot': 1, 'resource': '486522867199D7F3', 'node': 'payload_left', 'weapon': True}]:
        raise ValueError('the 110mm jet no longer mounts its two rocket pods: %r' % mounts['Eagle 110mm Rocket Pods'])
    chin_round = pelican_round()
    rounds = {name: chin_round if d['round'] == 'chin' else d['round'] for name, d in AUTOMATIC_DONORS.items()}
    strafing_spec = strafing_rounds()
    strafing_types = tuple(sorted({strafing_spec['projectile']} | set(strafing_spec['pattern'])))
    observations = [observe(name, eagles, rounds, strafing_types) for name in SNAPSHOTS]
    from research_pelican import MISSION_SNAPSHOTS
    sentries = [sentry_weapons(name) for name in MISSION_SNAPSHOTS]
    if any(o != sentries[0] for o in sentries[1:]):
        raise ValueError('the sentry weapon types differ between mission snapshots')
    sentries = sentries[0]
    mg43, gatling, mg206 = (sentries[n] for n in SENTRY_WEAPONS)
    if not (mg43['projectile'] == 148 and mg43['rateSlots'][1] == 630.0 and not mg43['rateSelectorBound']
            and gatling['rateSlots'] == [0.0, 1600.0, 0.0] and not gatling['rateSelectorBound']
            and mg206['projectile'] == 275 and mg206['rateSelectorBound']):
        raise ValueError('the sentry donors\' weapons changed: %r' % sentries)
    first = observations[0]
    for o in observations[1:]:
        if o['eagles'] != first['eagles'] or o['eagleRearm'] != first['eagleRearm']:
            raise ValueError('the Eagle rows differ between snapshots')
        if o['emsLinks'] != first['emsLinks']:
            raise ValueError('the EMS chain links differ between snapshots')
        for dname in rounds:
            a, b0 = o['automatic'][dname], first['automatic'][dname]
            if (a['round'], a['links'], a['effect']) != (b0['round'], b0['links'], b0['effect']):
                raise ValueError('%s: its round, explosion chain or effect differs between snapshots' % dname)
        for dname in SLOW_DONORS:
            a, b0 = o['slow'][dname], first['slow'][dname]
            if (a['round'], a['links'], a['effect']) != (b0['round'], b0['links'], b0['effect']):
                raise ValueError('%s: its round, explosion chain or effect differs between snapshots' % dname)
        if o['carriers'] != first['carriers']:
            raise ValueError('the carrier rows differ between snapshots')
        if {k: dict(v, raw=None) for k, v in o['strafing'].items()} != {k: dict(v, raw=None)
                for k, v in first['strafing'].items()}:
            raise ValueError('the Eagle Strafing Run rounds differ between snapshots')
    for ename, e in first['eagles'].items():
        if e['deliveryKind'] != 0 or e['linkedType'] != EAGLE_REARM:
            raise ValueError('%s is not an Eagle row (delivery %r, linked %r)' % (ename, e['deliveryKind'], e['linkedType']))
        if e['jet'] != eagles[ename]['payload']:
            raise ValueError('%s\'s payload[0] is not its jet' % ename)
    pods = first['eagles']['Eagle 110mm Rocket Pods']
    if eagles['Eagle 110mm Rocket Pods']['strikeProjectile'] != 82 or not pods['rocket'] or pods['rocket']['expiry'] != 0:
        raise ValueError('the 110mm rocket is not projectile 82 with an impact explosion only: %r' % pods)
    if first['shell74'] != {'impact': 188, 'expiry': 0}:
        raise ValueError('the Orbital EMS Strike shell 74 does not explode as 188 on impact: %r' % first['shell74'])
    # The automatic donors: each round explodes on impact only, as its reviewed explosion with no damage-over-time volume,
    # no status, no submunition and no arc (one blast per round: reviewed for an automatic weapon). Its effect, and every
    # package of the game data that ships it: the blast is usable only while one of them is resident.
    effects = effect_packages({first['automatic'][dname]['effect'] for dname in rounds})
    automatic = {}
    for dname, spec in AUTOMATIC_DONORS.items():
        a = first['automatic'][dname]
        r = a['round']
        if not r or r['impact'] != spec['explosion'] or r['expiry'] != 0:
            raise ValueError('%s: round %d does not explode as %d on impact only: %r' % (dname, rounds[dname],
                spec['explosion'], r))
        if a['links']['template'] != 0 or a['links']['statuses']:
            raise ValueError('%s: the explosion has a volume template or statuses: %r' % (dname, a['links']))
        definition = catalogued_explosion(r['impact'])
        if not definition or definition.get('submunition') or definition.get('volume') or definition.get('arc'):
            raise ValueError('%s: not a plain blast in the projectile-components catalogue: %r' % (dname, definition))
        packages = effects.get(a['effect']) or []
        if not packages:
            raise ValueError('%s: no package of the game data ships its effect %016X' % (dname, a['effect']))
        automatic[dname] = {'round': rounds[dname], 'explosion': r['impact'], 'links': a['links'],
            'automatic': True, 'radii': definition.get('radii'), 'asset': spec['asset'],
            'assetKey': spec.get('assetKey'),
            'damage': {'standard': definition['damage']['standard'], 'durable': definition['damage']['durable'],
                'armorPenetration': definition['damage']['armorPenetration']},
            'effect': '0x%016X' % a['effect'], 'packages': packages}
    for dname, d in automatic.items():
        radii, damage = chain_definition(first['automatic'][dname]['chain'])
        if [round(v, 3) for v in d['radii']] != radii or damage != d['damage']:
            raise ValueError('%s: the radii / damage members disagree with the catalogue: %r %r vs %r %r' % (dname,
                radii, damage, d['radii'], d['damage']))
    named = {dname: {p['name'] for p in d['packages']} for dname, d in automatic.items()}
    if 'packages/content/loadout_shared' not in named['Pelican chin autocannon']:
        raise ValueError('the Pelican chin explosion\'s effect is no longer in loadout_shared: %r' % named)
    if named['Automaton explosion 27'] != {'packages/content/cyborgs'} or named['Illuminate explosion 392'] != {
            'packages/content/illuminate'} or named['Assault walker cannon'] != {'packages/content/cyborgs'}:
        raise ValueError('explosions 27 / 392 are no longer faction content only: %r' % named)
    if 'packages/generated/loadout/laser_guided_missile_launcher' not in named['66mm Missile Mk2']:
        raise ValueError('the MLS-4X Commando\'s package no longer ships explosion 170\'s effect: %r' % named)
    if 'packages/generated/loadout/crossbow_greyfax' not in named['Exploding crossbow']:
        raise ValueError('the CB-9 Exploding Crossbow\'s package no longer ships explosion 59\'s effect: %r' % named)
    if 'packages/generated/loadout/eagle_base' not in named['Strafing run cannon']:
        raise ValueError('the Eagle Strafing Run\'s package no longer ships explosion 50\'s effect: %r' % named)
    # The slow donors: each explosion is the volume reviewed (the Orbital EMS / Gas Strike's template, its seconds and
    # statuses), its round (when it has one) requests it as reviewed, and a package of the game data ships its effect.
    slow_effects = effect_packages({first['slow'][dname]['effect'] for dname in SLOW_DONORS})
    slow = {}
    for dname, spec in SLOW_DONORS.items():
        a = first['slow'][dname]
        links = a['links']
        if (links['template'], links['seconds'], links['statuses']) != (spec['template'], spec['seconds'],
                spec['statuses']):
            raise ValueError('%s: explosion %d is not the reviewed volume: %r' % (dname, spec['explosion'], links))
        if spec['round'] is not None and (a['round'] or {}).get(spec['role']) != spec['explosion']:
            raise ValueError('%s: round %d does not request %d on %s: %r' % (dname, spec['round'], spec['explosion'],
                spec['role'], a['round']))
        # Not catalogued (no weapon's impact requests it): the radii and damage from its own rows.
        radii, damage = chain_definition(a['chain'])
        packages = slow_effects.get(a['effect']) or []
        if not packages:
            raise ValueError('%s: no package of the game data ships its effect %016X' % (dname, a['effect']))
        slow[dname] = {'round': spec['round'], 'roundRole': spec['role'], 'explosion': spec['explosion'],
            'links': links, 'slow': True, 'maxRpm': spec['maxRpm'],
            'volume': {'template': links['template'], 'seconds': links['seconds'], 'statuses': links['statuses']},
            'radii': radii, 'asset': spec['asset'], 'assetKey': spec.get('assetKey'), 'damage': damage,
            'effect': '0x%016X' % a['effect'], 'packages': packages}
    sl = {dname: {p['name'] for p in d['packages']} for dname, d in slow.items()}
    if 'packages/generated/loadout/mortar_turret_staticfield' not in sl['EMS mortar field'] or \
            'packages/generated/loadout/gas_grenade' not in sl['Gas grenade cloud'] or \
            'packages/generated/loadout/mortar_turret_gas' not in sl['Gas mortar cloud']:
        raise ValueError('the slow donors\' effects are no longer in their assets\' packages: %r' % sl)
    # The Eagle Strafing Run's own rounds: the HE round explodes as the 'Strafing run cannon' blast; its plain twin is
    # the same row but its type and impact explosion (and the unnamed +0xD0/+0xD4); the pattern names only the two.
    he = strafing_spec['projectile']
    plain = sorted({k for k in strafing_spec['pattern'] if k != he})
    rows_ = first['strafing']
    if len(plain) != 1 or strafing_spec['pattern'][0] != he:
        raise ValueError('the Eagle Strafing Run pattern is not its HE round then its plain twin: %r' % strafing_spec)
    plain = plain[0]
    a, b_ = bytes.fromhex(rows_[he]['raw']), bytes.fromhex(rows_[plain]['raw'])
    differ = [o for o in range(0, len(a), 4) if a[o:o + 4] != b_[o:o + 4]]
    if differ != [0x0, 0x90, 0xD0, 0xD4] or rows_[he]['impact'] != AUTOMATIC_DONORS['Strafing run cannon']['explosion'] \
            or rows_[plain]['impact'] != 0 or rows_[he]['expiry'] != 0 or rows_[plain]['expiry'] != 0:
        raise ValueError('the Eagle Strafing Run rounds are not the reviewed HE / plain twins: %r' % [hex(o) for o in differ])
    spawn_effect = struct.unpack_from('<Q', a, 0x48)[0]
    tracer = effect_packages({spawn_effect})[spawn_effect]
    if 'packages/generated/loadout/eagle_base' not in {p['name'] for p in tracer}:
        raise ValueError('the Eagle Strafing Run\'s package no longer ships its round\'s effect')
    # The aim override: off (t = -1) on every live targeting record of every snapshot (nothing in these missions used it).
    targeting = {o['snapshot']: o['targeting'] for o in observations}
    for name, t in targeting.items():
        if t and set(t['t']) - {str(TARGETING['off'])}:
            raise ValueError('%s: a targeting record has its aim override on: %r' % (name, t))
    if not any(t and t['instances'] for t in targeting.values()):
        raise ValueError('no snapshot has live targeting records')
    pelican_rounds = {'strafing_run': {'projectile': he, 'plain': plain, 'pattern': strafing_spec['pattern'],
        'name': 'Eagle Strafing Run 23mm HE cannon', 'asset': STRAFING_RUN, 'explosion': rows_[he]['impact'],
        'velocity': rows_[he]['velocity'], 'mass': rows_[he]['mass'], 'damage': rows_[he]['damage'],
        'rowVelocity': ROUND_MEMBERS['velocity'], 'rowMass': ROUND_MEMBERS['mass'], 'rowDamage': ROUND_MEMBERS['damage'],
        'spawnEffect': '0x%016X' % spawn_effect, 'packages': tracer}}
    # The explosion-less carriers: no impact or expiry explosion, and the Talon base's impact-time flags.
    carriers = first['carriers']
    talon = carriers[TALON_BASE]
    if talon['impact'] != 0 or talon['expiry'] != 0:
        raise ValueError('the Talon base row now has an explosion: %r' % talon)
    for kind in PELICAN_CARRIERS:
        c = carriers[kind]
        if c['impact'] != 0 or c['expiry'] != 0 or c['flags'] != talon['flags']:
            raise ValueError('carrier %d is not explosion-less with the Talon base\'s flags: %r vs %r' % (kind, c, talon))

    # A chain's rows: each row's bytes, the words that differ between snapshots masked (relocated pointers).
    def reviewed_chain(get):
        out = []
        for k, (kind, ident, raw) in enumerate(get(first)):
            rows = [bytes.fromhex(get(o)[k][2]) for o in observations]
            masked = [o for o in range(0, len(rows[0]), 4) if len({r[o:o + 4] for r in rows}) != 1]
            out.append({'kind': kind, 'id': ident, 'table': '0x%X' % TABLES[kind], 'stride': STRIDES[kind],
                'reviewed': raw, 'masked': masked})
        return out
    chain = reviewed_chain(lambda o: o['emsChain'])
    for dname in automatic:
        automatic[dname]['rows'] = reviewed_chain(lambda o, dname=dname: o['automatic'][dname]['chain'])
    for dname in slow:
        slow[dname]['rows'] = reviewed_chain(lambda o, dname=dname: o['slow'][dname]['chain'])
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'eagleLayout': LAYOUT, 'row': ROW, 'eagleRearm': first['eagleRearm'],
        'weaponHandle': {'global': 0x33266D8, 'count': 0x38, 'handles': 0x68, 'handleResource': 0x0, 'handleEntity': 0x8,
            'handleNetwork': 0x10, 'handleFlags': 0x14, 'createdHere': 1},
        'eagles': {name: dict(eagles[name], mounts=mounts[name], **{k: v for k, v in e.items() if k != 'jet'})
            for name, e in first['eagles'].items()},
        'mount': MOUNT,
        'explosionDonors': dict({'Orbital EMS Strike': {'shell': 74, 'explosion': 188, 'links': first['emsLinks'],
            'rows': chain}}, **automatic, **slow),
        # The targeting record's aim override (item 14): its layout, the values the Runtime writes, the live records.
        'pelicanAim': dict(TARGETING, observed=targeting),
        # Behaviour 213's re-pick and fire-check timers (item 15).
        'pelicanIdle': IDLE_AI,
        # The rounds of another weapon the Pelican's chin gun may fire on its own copy (item 13).
        'pelicanRounds': pelican_rounds,
        # Rounds with no explosion of their own whose impact explosion copy may take an automatic donor's.
        'impactCarriers': {'base': TALON_BASE, 'baseFlags': talon['flags'], 'flagsOffset': PROJECTILE_FLAGS,
            'types': {str(kind): carriers[kind] for kind in PELICAN_CARRIERS}},
        'projectileExplosions': PROJECTILE_EXPLOSIONS,
        'explosionQueue': EXPLOSION_QUEUE,
        'weaponFunction': WEAPON_FUNCTION,
        'sentryWeapons': sentries,
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation,
        'observations': [{'snapshot': o['snapshot'], 'eagleManager': o['eagleManager']} for o in observations],
        'semantics': {
            'jet': 'the Eagle dispatch (delivery kind 0) spawns the stratagem\'s payload[0], the jet, at the beacon\'s '
                'activation; its EagleComponent record and handle are appended to the Eagle manager',
            'rockets': 'the 110mm\'s rockets (live 2026-10-04): their source is one of the payload pods mounted on '
                'the jet (its mount record, the slot its type mounts that resource in) and their owner is the jet; each '
                'carries its own impact explosion copy from the strike projectile\'s row. What the strike spawns itself '
                '(SpawnProjectile, descriptor +0x18 = the jet) names the jet as its source',
            'uses': 'a converted Eagle slot is a fleet member (its row links Eagle Rearm): the game decrements its own '
                'uses at each call while they are neither -1 nor 0, and a native rearm resets them to its row\'s +0x50',
            'emsDonor': 'shell 74\'s impact explosion 188: no damage, stun (the statuses), a StaticField volume for '
                '+0x68 seconds',
            'rocketSource': 'the EagleComponent update walks the manager\'s active entries [0, +0x20) and strikes per '
                'entry with that entry\'s own handle: a rocket\'s source is an entity in the active region then',
            'dormantRates': 'a weapon whose inputs bind no rate-of-fire selector (WeaponData +184/+188 != 2) never '
                'changes rate slot: its Y slot is its rate, X and Z are dormant',
            'slowDonors': 'a damage-over-time volume (an EMS field, a gas cloud) a slow gun\'s round may request on '
                'impact, at most maxRpm rounds a minute: the game holds 4096 status volumes (0x347CF20 +0x120038) and '
                'checks no count before adding one (a full id map leaves a null slot pointer); 180: the EMS Mortar '
                'Sentry shell 154\'s expiry (a 7 s StaticField, stun); 177: the G-4 Gas grenade\'s (a 15 s cloud, 3 '
                'damage); 185: the Gas Mortar Sentry shell 342\'s impact (the same cloud, no damage)',
            'automaticDonors': 'a round that natively explodes on impact as a plain blast (no volume, status, '
                'submunition or arc); its explosion row +0x38 is the particle effect, usable while a package that '
                'ships it is resident (234: loadout_shared; 170: the MLS-4X Commando\'s; 27: the Automaton faction '
                'content only; 392: the Illuminate faction content only)',
            'impactCarriers': 'a carrier has no impact or expiry explosion and the Talon base\'s flags +0xF0 (the '
                'impact-time late lookup); SpawnProjectile copies +0x90 into the hit record +0x7C, the only store, and '
                'hit processing reads only that copy: a carrier whose copy is written before its first step reaches '
                'the explosion step as the live-verified Talon-based row with +0x90 = 158 did'},
        'unproven': ['A custom Eagle live: the redirect (live: works), the jet capture (live: works), the rockets\' '
            'pods and owner (live: observed) and their conversion by mount and owner (not yet live).',
            'Whether explosion 188 requested by a 110mm rocket produces the EMS field and the stun (only live).',
            'Whether the explosion request queue still holds a request when the Runtime update reads it (the game '
            'drains it; an empty read proves nothing).',
            'The creditor of a jet\'s rockets (the projectile conversion refuses any but the local peer).',
            'The Runtime rearm of a custom Eagle without Eagle Rearm in the record.',
            'A Pelican CAS round (148 / 275) written to the chin autocannon\'s explosion live: whether it explodes, '
            'its cost at the CAS rate, and what other machines show (each converts its own copy).'],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'eagles': {n: (e['type'], e['uses'], e['strikeProjectile'], e['rocket'])
        for n, e in report['eagles'].items()}, 'rearm': report['eagleRearm'], 'ems': first['emsLinks'],
        'observations': report['observations']}, indent=1))


if __name__ == '__main__':
    main()
