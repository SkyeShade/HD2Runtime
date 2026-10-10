"""Team-reload support weapons: where their ammunition lives and how the game reloads them. Read-only.

Question (stats editor, 0.30.4): can the GR-8 Recoilless Rifle (and the other team-reload weapons) carry spare
ammunition of its own, and which of its backpack's ammunition members can be authored?

Proven on build F5FEE03DCFDB from the pinned entity tables, the type library, the unpacked game.dll in the retained
snapshots (exact instruction pins) and the engine's loaded network configuration:

1. Identity. Every weapon owning a WeaponAssistedReloadComponentData record (six: the five team-reload support weapons
   and the C4 detonator) is paired with the one backpack whose DepositComponent assisted_reload_weapon_path is the
   weapon's resource; the call-in rack delivers both. Each deposit record has one owner. Scraped wiki stats are
   fingerprints only (backpack capacity = published spare, refill = published from-supply).
2. The weapon's own spare count is real. The reload gate (0x775580) first asks the weapon's own spare total
   (0x744180: magazine spare magazines, or rounds-feed spare rounds, plus a mounted shared deposit) and lets the
   wielder reload when it is above zero; only when it is zero does it ask whether the worn backpack can feed the
   weapon (0x73B440: equipment type 17, assisted_reload_weapon_path equals the weapon or is empty, live amount at
   least the assisted record's +20). The reload itself (0x7768F0) consumes the weapon's own spares first (one
   magazine; or the reload amount +92 of rounds, without a lower bound) and the backpack deposit only when the own
   total is zero. A teammate's assisted reload (0x11A28E0) always consumes a backpack deposit.
   Own rounds below zero (0.31.0 rc2): 3 rounds left and a 5-round reload store -2 in the live row, but the queued
   field write points at that row and every flush validates it with clamp = 1 before setting the field, so the engine
   writes 0 back in place by the end of the frame (helldivers2.exe validator 0x34BAB0, signed clamp). Until then the
   gate reads it signed (no own reload) and nothing serialises it. The vanilla P-69 Veto (6-round clips, 52 starting
   rounds) reaches the same partial last reload. Harmless: the AC-8's own rounds are offered.
3. Spawn and resupply read the weapon's own record. At spawn the own spare count is min(start, maximum) (magazines:
   +140 and +148; rounds: +88 and +80, the maximum rounded up to a multiple of the reload amount). Resupply
   (0x880E20) refills every carried weapon (0x757F70: magazines +144, rounds +84, at least 1, capped at the maximum)
   and then the worn backpack's deposit. Natively every team-reload weapon has maximum 0, so its start and refill
   are clamped to 0: that is why it keeps no ammunition of its own.
4. Limits. The weapon's live spare magazines travel as the network field magazines_remaining (int, 5 bits: 0..31);
   spare rounds as field 0x9A34C336 (int, 9 bits: 0..511). Both are written through the same owner-only queue whose
   flush clamps the value in place (research/deposit-limits-F5FEE03DCFDB.json).
5. Backpack visuals. node_hiding_order (+44, 20 entries) is walked to the first empty entry, at most 20; a node is
   shown while the live amount is above its index, so a capacity above the node count only keeps every node shown.

Nothing here writes memory. Requires the research-only packages capstone and numpy.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_deposit_limits as limits  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
import snapshot_image  # noqa: E402
import snapshot_regions  # noqa: E402
from hd2_archive import resource_hash  # noqa: E402

OUTPUT = ROOT / 'research/team-reload-ammo-F5FEE03DCFDB.json'
SUPPORT_RESEARCH = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
STRATAGEMS = ROOT / 'schemas/stratagem_authoring_catalog.json'
WIKI = ROOT / 'data/wiki_support_weapons.json'
ASSISTED, DEPOSIT, MAGAZINE, ROUNDS, RELOAD, RACK, EQUIPMENT = ('WeaponAssistedReloadComponentData',
    'DepositComponentData', 'WeaponMagazineComponentData', 'WeaponRoundsComponentData', 'WeaponReloadComponentData',
    'HellpodRackComponentData', 'EquipmentComponentData')
RACK_SLOTS, RACK_STRIDE = 8, 64
BACKPACK_EQUIPMENT_TYPE = 17   # 0x73B5B0: cmp eax, 0x11 on the worn backpack's equipment type
FIELD_MAGAZINES = 'magazines_remaining'
FIELD_ROUNDS_HASH = 0x9A34C336  # spare rounds network field; its name is not resolved (cited by hash only)

# game.dll globals
MAGAZINE_MANAGER, ROUNDS_MANAGER, HEAT_MANAGER = 0x3326648, 0x3326CF0, 0x3326D48
ASSISTED_MANAGER, WEAPON_MANAGER, DEPOSIT_MANAGER = 0x3326BE8, 0x3326660, 0x33265E8

# (rva, exact instruction text, role). Every entry is decoded and must match exactly.
DLL_PROOF = {
    'definitionTables': [
        (0x4F72C4, 'cmp eax, 0xb', 'WeaponAssistedReloadComponentData lookup: 12 index rows ...'),
        (0x4F72CB, 'cmp r9d, 0xc', ''),
        (0x4F72DC, 'imul rax, rcx, 0x68', '... records of 104 bytes'),
        (0x4F72E0, 'add rax, 0xc0', 'records follow the 12 x 16-byte index'),
        (0x4F3762, 'mov r11, qword ptr [rip + 0x2e32edf]', 'magazine definition: per-instance copy first (manager) ...'),
        (0x4F3354, 'cmp eax, 0x21b', '... else WeaponMagazineComponentData: 540 index rows ...'),
        (0x4F335D, 'cmp r9d, 0x21c', ''),
        (0x4F3375, 'lea rax, [rcx + rcx*4]', '... records of 160 bytes'),
        (0x4F3379, 'shl rax, 5', ''),
        (0x4FDD42, 'mov r11, qword ptr [rip + 0x2e28fa7]', 'rounds definition: per-instance copy first (rounds manager) ...'),
        (0x4FDDDC, 'jmp 0x4fd8e0', '... else the WeaponRoundsComponentData table'),
        (0x4FD944, 'cmp eax, 0x31', 'WeaponRoundsComponentData: 50 index rows ...'),
        (0x4FD94B, 'cmp r9d, 0x32', ''),
        (0x4FD95C, 'imul rax, rcx, 0x88', '... records of 136 bytes'),
        (0x4FD242, 'mov r11, qword ptr [rip + 0x2e29827]', 'reload definition: per-instance copy first ...'),
        (0x4FD2DD, 'jmp 0x4fce20', '... else WeaponReloadComponentData'),
        (0x4FCE84, 'cmp eax, 0x1f1', 'WeaponReloadComponentData: 498 index rows'),
        (0x4FCE8D, 'cmp r9d, 0x1f2', ''),
    ],
    'ownSpareTotal': [
        (0x744223, 'mov rcx, qword ptr [r10 + 0x50]', 'weapon type flags (weapon manager rows, 40 bytes)'),
        (0x74422B, 'bt r9d, 9', 'bit 9: heat weapon (spare heatsinks)'),
        (0x744236, 'mov r11, qword ptr [rip + 0x2be2b0b]', 'heat manager'),
        (0x7442BD, 'test r9b, r9b', 'bit 7: magazine weapon'),
        (0x7442C6, 'mov r11, qword ptr [rip + 0x2be237b]', 'magazine manager'),
        (0x744335, 'mov rax, qword ptr [r11 + 0x50]', 'magazine instance rows, 12 bytes'),
        (0x74433D, 'mov ebx, dword ptr [rax + r8*4]', '+0 = the weapon\'s own spare magazines'),
        (0x744341, 'call 0x7761d0', 'plus the mounted shared deposit'),
        (0x74434D, 'bt r9d, 8', 'bit 8: rounds-feed weapon'),
        (0x744354, 'mov r11, qword ptr [rip + 0x2be2995]', 'rounds manager'),
        (0x7443B5, 'mov ebx, dword ptr [rax + r8*4]', '+0 = the weapon\'s own spare rounds (rows of 20 bytes)'),
        (0x77626C, 'call 0x4fd220', 'shared deposit: reload definition ...'),
        (0x776271, 'cmp byte ptr [rax + 0x3c], r14b', '... only with has_shared_deposit (+60); else 0'),
    ],
    'reloadGate': [
        (0x775987, 'mov rcx, qword ptr [rip + 0x2bb0cd2]', 'weapon manager'),
        (0x775990, 'call 0x744180', 'own spare total'),
        (0x775997, 'setg r14b', 'above zero: the wielder may reload'),
        (0x77599D, 'jg 0x7759f5', 'and the backpack is not asked'),
        (0x7759A7, 'mov rdi, qword ptr [rip + 0x2bb123a]', 'else, for a weapon with an assisted-reload record ...'),
        (0x775B6E, 'call 0x73b440', '... the worn backpack must be able to feed it'),
        (0x775B7B, 'mov r14b, 1', ''),
    ],
    'backpackCanFeed': [
        (0x73B4F7, 'call 0x4f7260', 'the weapon\'s assisted-reload record'),
        (0x73B509, 'call 0x9a9cc0', 'the helldiver\'s worn backpack'),
        (0x73B51A, 'mov r15, qword ptr [rip + 0x2beb0c7]', 'deposit manager'),
        (0x73B594, 'call 0x502710', 'the backpack\'s deposit definition'),
        (0x73B599, 'mov rsi, qword ptr [rax + 0x88]', 'assisted_reload_weapon_path (+136)'),
        (0x73B5AB, 'call 0x8c27f0', 'equipment type of the backpack'),
        (0x73B5B0, 'cmp eax, 0x11', 'must be 17'),
        (0x73B5B9, 'test rsi, rsi', 'an empty path feeds any assisted weapon'),
        (0x73B5C6, 'cmp rsi, qword ptr [rcx]', 'else it must be this weapon\'s resource'),
        (0x73B629, 'mov eax, dword ptr [rax + 0x14]', 'assisted record +20 ...'),
        (0x73B62C, 'cmp dword ptr [rcx + rdx*8], eax', '... at most the live deposit amount'),
    ],
    'reloadConsume': [
        (0x776F8E, 'mov rax, qword ptr [rip + 0x2bafc53]', 'a weapon with an assisted-reload record:'),
        (0x777095, 'call 0x744180', 'own spare total ...'),
        (0x77709A, 'test eax, eax', ''),
        (0x77709C, 'jne 0x7771cc', '... above zero: consume the weapon\'s own spares'),
        (0x7770AD, 'call 0x9a9cc0', 'zero: the worn backpack'),
        (0x7770D1, 'call 0x4f7260', 'assisted record'),
        (0x7771AE, 'cmp dword ptr [rax + rcx*8], 0', 'deposit not empty'),
        (0x7771B8, 'mov r8d, dword ptr [r14 + 0x14]', 'cost: assisted record +20'),
        (0x7771C2, 'call 0x87f970', 'consumed from the backpack deposit'),
        (0x777294, 'mov rbp, qword ptr [rip + 0x2baf3ad]', 'own magazine spares:'),
        (0x777431, 'sub dword ptr [rcx + r8*4], 1', 'one magazine'),
        (0x777449, 'mov edx, 0xec64918b', 'network field magazines_remaining'),
        (0x777451, 'call 0xfd97e0', 'queued write (owning peer only)'),
        (0x777488, 'call 0x4fdd20', 'own rounds spares: rounds definition'),
        (0x7774E4, 'mov ebx, dword ptr [rax + rcx*4]', 'spare rounds'),
        (0x7774E7, 'sub ebx, dword ptr [rbp + 0x5c]', 'minus the reload amount (+92); no lower bound'),
        (0x7774EA, 'mov dword ptr [rax + rcx*4], ebx', ''),
        (0x7774FD, 'mov edx, 0x9a34c336', 'network field (spare rounds)'),
    ],
    'teamReload': [
        (0x11A2991, 'call 0x73b000', 'a backpack that can feed the weapon (the reloader\'s, else the wielder\'s)'),
        (0x11A29CB, 'call 0x4f7260', 'assisted record'),
        (0x11A2C85, 'mov r8d, dword ptr [rax + 0x14]', 'cost: +20'),
        (0x11A2C89, 'call 0x87f970', 'always consumed from that backpack deposit'),
        (0x73B019, 'mov rbp, qword ptr [rip + 0x2bebbc8]', 'assisted manager'),
        (0x73B03B, 'call 0x73b440', 'first backpack checked'),
        (0x73B069, 'call 0x73b440', 'second backpack checked'),
    ],
    'spawnMagazines': [
        (0x76DAF2, 'call 0x4f3740', 'magazine definition'),
        (0x76DB05, 'mov ecx, dword ptr [rax + 0x8c]', 'starting magazines (+140)'),
        (0x76DB0B, 'mov esi, dword ptr [rax + 0x94]', 'maximum (+148)'),
        (0x76DC5B, 'mov ecx, dword ptr [rcx + 0x94]', 'maximum scaled by weapon stat 12 (ceil, per 10000)'),
        (0x76DC7E, 'add ebx, eax', 'start + (scaled - native maximum)'),
        (0x76DC87, 'js 0x76dc91', 'negative: 0'),
        (0x76DC8B, 'cmovg ebx, esi', 'start = min(start, maximum)'),
    ],
    'spawnRounds': [
        (0x77992F, 'mov ebx, dword ptr [rax + 0x58]', 'starting rounds (+88)'),
        (0x779944, 'mov esi, dword ptr [rax + 0x50]', 'maximum (+80)'),
        (0x779A49, 'call 0x779cc0', 'scaled maximum'),
        (0x779A65, 'cmova ebx, esi', 'start = min(start, maximum)'),
        (0x779CF1, 'mov r8d, dword ptr [rax + 0x5c]', 'reload amount (+92) ...'),
        (0x779CF5, 'mov ecx, dword ptr [rcx + 0x50]', 'maximum (+80) ...'),
        (0x779D19, 'div r8d', '... rounded up to a multiple of the reload amount'),
    ],
    'resupply': [
        (0x880EDC, 'call 0x757f70', 'inventory +0x00 weapon refill'),
        (0x880FA5, 'call 0x757f70', 'inventory +0x04 weapon refill'),
        (0x8810AD, 'call 0x8c27f0', 'worn backpack (+0x0C) equipment type'),
        (0x8810B2, 'cmp eax, 0x17', 'not the Supply Pack'),
        (0x8810BD, 'call 0x87fd70', 'backpack deposit refill'),
        (0x8810DD, 'call 0x757f70', 'inventory +0x08 (support weapon) refill'),
        (0x7580B8, 'jmp 0x76e6d0', 'weapon refill: magazine weapons'),
        (0x7580E4, 'jmp 0x77a430', 'weapon refill: rounds-feed weapons'),
        (0x76E770, 'mov edx, dword ptr [rax + 0x90]', 'magazines from supply (+144)'),
        (0x76E789, 'mulss xmm0, xmm6', 'x the caller\'s scale'),
        (0x76E7AC, 'maxss xmm2, xmm1', 'at least 1'),
        (0x76E7B0, 'call 0x76e000', 'maximum'),
        (0x76E04F, 'mov ecx, dword ptr [rdi + 0x94]', 'maximum = +148 (scaled)'),
        (0x76E7C9, 'cmovb edi, eax', 'spare = min(spare + refill, maximum)'),
        (0x76E7DC, 'mov edx, 0xec64918b', 'magazines_remaining'),
        (0x77A4C0, 'mov edx, dword ptr [rax + 0x54]', 'rounds from supply (+84)'),
        (0x77A4F7, 'cmovle ebp, eax', 'at least 1'),
        (0x77A510, 'call 0x779cc0', 'maximum'),
        (0x77A525, 'cmovb edi, eax', 'spare = min(spare + refill, maximum)'),
        (0x77A539, 'mov edx, 0x9a34c336', 'spare rounds field'),
    ],
    'backpackNodes': [
        (0x880660, 'call 0x502710', 'deposit definition'),
        (0x88067A, 'lea rdi, [rax + 0x2c]', 'node_hiding_order (+44)'),
        (0x880684, 'test edx, edx', 'ends at the first empty entry'),
        (0x8806D5, 'cmp r15d, ebx', 'live amount above the index: shown'),
        (0x8806FB, 'cmp ebx, 0x14', 'at most 20 nodes'),
    ],
    # 0.31.0 rc2: what happens when the own spare rounds are not a multiple of the reload amount (3 left, reload 5).
    'roundsBelowZero': [
        (0x7769A7, 'test byte ptr [rcx + 0x14], 1', 'reload completion: only an instance this peer owns (+0x14 bit 0) ...'),
        (0x7769AB, 'je 0x7775df', '... a remote copy does no bookkeeping'),
        (0x776BFE, 'add ebp, dword ptr [rax + 0x5c]', 'rounds fill: the magazine gets the full reload amount (+92) ...'),
        (0x776CA6, 'call 0x7422b0', '... whatever the spare count'),
        (0x7772E5, 'mov rsi, qword ptr [rip + 0x2bafa04]', 'rounds manager'),
        (0x7774DA, 'mov rax, qword ptr [rsi + 0x58]', 'its live rows (manager +0x58) ...'),
        (0x7774E0, 'lea rcx, [rdx + rdx*4]', '... 20 bytes each; +0 = the own spare rounds (int32)'),
        (0x7774EA, 'mov dword ptr [rax + rcx*4], ebx', 'spare - reload amount stored unbounded (3 - 5 = -2)'),
        (0x7774F1, 'lea r8, [rax + rcx*4]', 'the queued value pointer is that live row itself'),
        (0x777505, 'call 0xfd97e0', 'queued field write 0x9A34C336'),
        (0x77750A, 'test ebx, ebx', 'exactly 0: the out-of-ammo cue (0x777512) ...'),
        (0x77750C, 'jne 0x7775ba', '... a negative count skips it'),
    ],
    'readersOfANegativeCount': [
        (0x775995, 'test eax, eax', 'reload gate: own total ...'),
        (0x775997, 'setg r14b', '... signed: a negative total does not allow an own reload (the backpack is asked)'),
        (0x77709A, 'test eax, eax', 'reload payment: own total ...'),
        (0x77709C, 'jne 0x7771cc', '... any nonzero, a negative too, pays from the own rounds (only if it survived to a '
            'later completion)'),
        (0x77A51D, 'mov edx, dword ptr [rcx + rsi*4]', 'resupply: live own rounds ...'),
        (0x77A520, 'lea edi, [rdx + rbp]', '... + refill ...'),
        (0x77A523, 'cmp eax, edi', '... vs the maximum ...'),
        (0x77A525, 'cmovb edi, eax', '... unsigned: a negative sum would read as huge and give the maximum'),
    ],
    'fieldQueueAndFlush': [
        (0xFD9801, 'cmp byte ptr [rsi + 0x301d], 0', 'queue closed ...'),
        (0xFD9808, 'jne 0xfd98ae', '... only while the world is torn down (0xFDD0C0 sets, 0xFDD10C clears)'),
        (0xFD9846, 'call rbx', 'net API +0x168: owned by this peer'),
        (0xFD984A, 'jle 0xfd98a4', 'not owned: not queued'),
        (0xFD985A, 'mov qword ptr [rsp + 0x28], r14', 'entry +8 = the caller\'s value pointer'),
        (0xFD986F, 'cmp byte ptr [rsi + 0x301c], 0', 'not batching ...'),
        (0xFD9876, 'je 0xfd987f', '... flush now'),
        (0xFD9878, 'cmp eax, 0x800', 'batch full (2048 entries): flush now'),
        (0xFD9892, 'call 0xfddec0', 'flush'),
        (0xFDDF0C, 'mov byte ptr [rsp + 0x20], 1', 'flush: clamp = 1 ...'),
        (0xFDDF15, 'mov r10, qword ptr [r8 + 0xa0]', '... net API +0xA0 validates and clamps through the pointer ...'),
        (0xFDDF3F, 'call qword ptr [r10 + 0xb8]', '... and only then +0xB8 sets the field'),
        (0xFDC79E, 'call 0xfde060', 'sync point 0xFDC780: flush every batched entry ...'),
        (0xFDE0FC, 'mov byte ptr [rsp + 0x20], 1', '... with clamp = 1 ...'),
        (0xFDE113, 'call r10', '... validate (net API +0xA0) ...'),
        (0xFDE12F, 'call qword ptr [r10 + 0xb8]', '... then set'),
        (0xFDAF17, 'call 0xfdc780', 'world update: sync before the update phases ...'),
        (0xFDAF25, 'mov byte ptr [rax + 0x301c], 1', '... batching on ...'),
        (0xFDAF3C, 'call 0x570730', '... update phases ...'),
        (0xFDAF6C, 'call 0xfdc780', '... sync after them: everything queued this frame is clamped and sent'),
        (0xAB5EE6, 'call 0xfdc780', 'the inlined copy of the world update syncs at the same point'),
        (0xFDC8A3, 'test byte ptr [rdx + 0x14], 1', 'an instance without a game object: +0x14 bit 0 stands in for the '
            'owned check'),
    ],
}
# helldivers2.exe: the engine's field validator (net API +0xA0 -> 0x34C220 -> 0x34BAB0), research/deposit-limits.
EXE_PROOF = {
    'validatorIntClamp': [
        (0x34BB72, 'mov r12d, dword ptr [r8]', 'value (through the caller\'s pointer)'),
        (0x34BB78, 'mov r14d, dword ptr [rdi + 0x10]', 'field minimum (0)'),
        (0x34BB85, 'sub edx, r14d', 'value - min ...'),
        (0x34BB8A, 'cmp edx, eax', '... vs 1 << bits (512) ...'),
        (0x34BB8C, 'jb 0x34c1e6', '... unsigned: -2 is out of range'),
        (0x34BB99, 'add edi, r8d', 'max = min + 2^bits - 1 (511)'),
        (0x34BBD6, 'cmp byte ptr [rsp + 0xd8], bpl', 'clamp flag (1 from the flush)'),
        (0x34BBE6, 'cmp eax, edi', 'signed: above max ...'),
        (0x34BBE8, 'jg 0x34bbf3', '... max'),
        (0x34BBEF, 'cmovl edi, r14d', 'signed: below min: min (0)'),
        (0x34BBF3, 'mov dword ptr [rsi], edi', 'written back into the live row'),
    ],
}
GLOBALS = {('definitionTables', 0x4F3762): MAGAZINE_MANAGER, ('definitionTables', 0x4FDD42): ROUNDS_MANAGER,
    ('ownSpareTotal', 0x744236): HEAT_MANAGER, ('ownSpareTotal', 0x7442C6): MAGAZINE_MANAGER,
    ('ownSpareTotal', 0x744354): ROUNDS_MANAGER, ('reloadGate', 0x775987): WEAPON_MANAGER,
    ('reloadGate', 0x7759A7): ASSISTED_MANAGER, ('backpackCanFeed', 0x73B51A): DEPOSIT_MANAGER,
    ('reloadConsume', 0x776F8E): ASSISTED_MANAGER, ('reloadConsume', 0x777294): MAGAZINE_MANAGER,
    ('teamReload', 0x73B019): ASSISTED_MANAGER, ('roundsBelowZero', 0x7772E5): ROUNDS_MANAGER}


def hexid(value: int) -> str:
    return f'0x{value:016X}'


def network_fields() -> list[dict]:
    """The spare-count network fields in every retained snapshot: type kind, bits and minimum."""
    wanted = {resource_hash(FIELD_MAGAZINES) >> 32: FIELD_MAGAZINES, FIELD_ROUNDS_HASH: '0x%08X' % FIELD_ROUNDS_HASH}
    out = []
    for path in limits.SNAPSHOTS:
        memory = limits.Memory(path)
        config = memory.ptr(memory.ptr(memory.exe + limits.NETWORK_CONFIG_SLOT))
        types = memory.ptr(config + 0x18)
        count, objects = memory.u32(config + 0x70), memory.ptr(config + 0x78)
        table = memory.read(objects, count * 0x50)
        found = {}
        for index in range(count):
            row = table[index * 0x50:(index + 1) * 0x50]
            fields = struct.unpack_from('<I', row, 0x18)[0]
            if not fields:
                continue
            hashes = struct.unpack('<%dI' % fields, memory.read(struct.unpack_from('<Q', row, 0x38)[0], fields * 4))
            kinds = struct.unpack('<%dI' % fields, memory.read(struct.unpack_from('<Q', row, 0x20)[0], fields * 4))
            for value, kind in zip(hashes, kinds):
                if value in wanted:
                    raw = memory.read(types + kind * 0x18, 0x18)
                    key = (wanted[value], kind, raw[12], raw[13], struct.unpack_from('<i', raw, 16)[0])
                    found[key] = found.get(key, 0) + 1
        memory.snap.close()
        for (name, kind, form, bits, low), objects_count in sorted(found.items()):
            out.append({'snapshot': path.name, 'field': name, 'fieldType': kind, 'kind': form, 'bits': bits, 'min': low,
                'max': low + (1 << bits) - 1, 'objectTypes': objects_count})
    return out


def build() -> dict:
    native = entity_research.Native()
    base = snapshot_image.Snapshot(snapshot_regions.SNAPSHOT)
    if base.game_dll_sha256 != limits.PROFILE_DLL_SHA or base.executable_sha256 != limits.PROFILE_EXE_SHA:
        raise ValueError('snapshot game.dll or executable differs from the pinned profile')
    _, dll = base.module_image('game.dll')
    _, exe = base.module_image(limits.EXE)
    base.close()
    image = limits.Image(dll)
    proof = image.prove(DLL_PROOF, {})
    exe_proof = limits.Image(exe).prove(EXE_PROOF, {})
    rows = {(group, row['rva']): row for group, items in proof.items() for row in items}
    for key, value in GLOBALS.items():
        if rows[key].get('ripTarget') != value:
            raise ValueError('%s %x no longer targets %x' % (key[0], key[1], value))

    # Table shapes the pinned getters rely on.
    shapes = {}
    for name in (ASSISTED, MAGAZINE, ROUNDS, RELOAD):
        _, capacity, _, size, count = native.table(name)
        shapes[name] = {'indexRows': capacity, 'recordSize': size, 'records': count}
    if (shapes[ASSISTED]['indexRows'], shapes[ASSISTED]['recordSize']) != (12, 104) \
            or (shapes[MAGAZINE]['indexRows'], shapes[MAGAZINE]['recordSize']) != (540, 160) \
            or (shapes[ROUNDS]['indexRows'], shapes[ROUNDS]['recordSize']) != (50, 136) \
            or shapes[RELOAD]['indexRows'] != 498:
        raise ValueError('component table shapes changed: %s' % shapes)

    support = json.loads(SUPPORT_RESEARCH.read_text())['weapons']
    catalog_name = {int(h, 16): w['catalogIdentity'] for w in support for h in w['resourceHashes']}
    roots = json.loads(STRATAGEMS.read_text())['stratagems']
    wiki = {w['name']: w for w in json.loads(WIKI.read_text(encoding='utf-8'))['weapons']}
    racks = {}
    for record, owners in native.owners(RACK).items():
        raw = native.record(RACK, record)
        items = [struct.unpack_from('<Q', raw, slot * RACK_STRIDE)[0] for slot in range(RACK_SLOTS)]
        for owner in owners:
            racks[owner] = {'recordIndex': record, 'items': items}
    deposits = {}
    for record, owners in native.owners(DEPOSIT).items():
        body = native.record(DEPOSIT, record)
        path = struct.unpack_from('<Q', body, 136)[0]
        if path:
            deposits.setdefault(path, []).append((record, owners, body))
    weapons = []
    for record, owners in sorted(native.owners(ASSISTED).items()):
        if len(owners) != 1:
            raise ValueError('assisted-reload record %d has %d owners' % (record, len(owners)))
        weapon = owners[0]
        assisted = native.record(ASSISTED, record)
        components = {c['name']: c for c in native.report(hexid(weapon))['components'] if c.get('resolved')}
        candidates = deposits.get(weapon, [])
        delivered = []
        for deposit_record, deposit_owners, body in candidates:
            for backpack in deposit_owners:
                rack = [(owner, info) for owner, info in racks.items() if weapon in info['items'] and backpack in info['items']]
                delivered.append({'backpack': backpack, 'record': deposit_record, 'owners': deposit_owners, 'body': body,
                    'racks': rack})
        delivered_with_rack = [item for item in delivered if item['racks']]
        if len(delivered_with_rack) != 1 or len(delivered_with_rack[0]['racks']) != 1:
            raise ValueError('%s: %d delivered backpacks' % (hexid(weapon), len(delivered_with_rack)))
        chosen = delivered_with_rack[0]
        backpack, body = chosen['backpack'], chosen['body']
        rack, rack_info = chosen['racks'][0]
        capacity, start, refill = struct.unpack_from('<IiI', body, 0)
        nodes = [value for value in struct.unpack_from('<20I', body, 44)]
        node_count = next((index for index, value in enumerate(nodes) if not value), 20)
        equipment = native.component(hexid(backpack), EQUIPMENT)
        equipment_type = struct.unpack_from('<I', native.record(EQUIPMENT, equipment['record_index']), 128)[0] \
            if equipment else None
        if equipment_type != BACKPACK_EQUIPMENT_TYPE:
            raise ValueError('%s: backpack equipment type %s' % (hexid(backpack), equipment_type))
        if set(rack_info['items']) - {0, weapon, backpack}:
            raise ValueError('%s: the rack also delivers another item' % hexid(weapon))
        name = catalog_name.get(weapon)
        entry = {'weaponResource': hexid(weapon), 'weaponPath': native.path(weapon), 'supportWeapon': name,
            'weaponEntityRow': native.entity_row(weapon),
            'assistedReload': {'recordIndex': record, 'indexRow': components[ASSISTED]['index_row'],
                'plus16': struct.unpack_from('<I', assisted, 16)[0], 'depositCost': struct.unpack_from('<i', assisted, 20)[0],
                'depositCostOffset': 20, 'abilities': list(struct.unpack_from('<II', assisted, 0))},
            'backpackResource': hexid(backpack), 'backpackPath': native.path(backpack),
            'backpackEntityRow': native.entity_row(backpack), 'backpackEquipmentType': equipment_type,
            'rack': {'resource': hexid(rack), 'recordIndex': rack_info['recordIndex'],
                'indexRow': native.component(hexid(rack), RACK)['index_row'],
                'weaponSlot': rack_info['items'].index(weapon), 'backpackSlot': rack_info['items'].index(backpack),
                'items': [hexid(value) for value in rack_info['items']]},
            'deposit': {'component': DEPOSIT, 'recordIndex': chosen['record'],
                'indexRow': native.component(hexid(backpack), DEPOSIT)['index_row'],
                'ownerCount': len(chosen['owners']), 'uniqueOwner': len(chosen['owners']) == 1,
                'recordSha256': entity_research.sha(body),
                'values': {'0': capacity, '4': start, '8': refill}, 'startIsFullSentinel': start < 0,
                'refillStyle': struct.unpack_from('<I', body, 128)[0], 'nodeHidingOrderCount': node_count},
            'otherDepositsForThisWeapon': [{'recordIndex': item['record'],
                'owners': [native.path(o) or hexid(o) for o in item['owners']],
                'values': dict(zip(('0', '4', '8'), struct.unpack_from('<IiI', item['body'], 0))),
                'deliveredByARackWithTheWeapon': bool(item['racks'])} for item in delivered if item is not chosen]}
        if name:
            root = roots[name]['root']
            if int(root['payloads'][0], 16) != rack:
                raise ValueError(name + ': call-in primary payload is not the delivering rack')
            entry['callIn'] = {'stratagem': name, 'rootId': root['id'], 'primaryPayload': hexid(rack)}
        if MAGAZINE in components:
            raw = native.record(MAGAZINE, components[MAGAZINE]['record_index'])
            entry['ammoKind'] = 'magazine'
            entry['weaponAmmo'] = {'component': MAGAZINE, 'recordIndex': components[MAGAZINE]['record_index'],
                'capacity': struct.unpack_from('<I', raw, 136)[0], 'startingMagazines': struct.unpack_from('<I', raw, 140)[0],
                'magazinesFromSupply': struct.unpack_from('<I', raw, 144)[0],
                'spareMagazines': struct.unpack_from('<I', raw, 148)[0]}
        elif ROUNDS in components:
            raw = native.record(ROUNDS, components[ROUNDS]['record_index'])
            entry['ammoKind'] = 'rounds'
            entry['weaponAmmo'] = {'component': ROUNDS, 'recordIndex': components[ROUNDS]['record_index'],
                'spareRounds': struct.unpack_from('<I', raw, 80)[0], 'roundsFromSupply': struct.unpack_from('<I', raw, 84)[0],
                'startingRounds': struct.unpack_from('<I', raw, 88)[0], 'reloadAmount': struct.unpack_from('<I', raw, 92)[0]}
        reload = native.record(RELOAD, components[RELOAD]['record_index'])
        entry['reload'] = {'recordIndex': components[RELOAD]['record_index'], 'duration': struct.unpack_from('<f', reload, 56)[0],
            'hasSharedDeposit': bool(reload[60])}
        if name and name in wiki:
            stats = wiki[name]['normalizedFields']['weaponStats']

            def stat(key):
                value = stats.get(key)
                return value.get('value') if isinstance(value, dict) else value
            spare, supply = stat('spareMagazines'), stat('magsFromSupply')
            entry['fingerprint'] = {'wikiSpareMagazines': spare, 'wikiMagsFromSupply': supply,
                'backpackCapacity': capacity, 'backpackRefill': refill,
                'exact': (spare == capacity and supply == refill) if entry['ammoKind'] == 'magazine'
                    else (supply == refill * entry['weaponAmmo']['reloadAmount']),
                'basis': 'magazine weapons: wiki spare = backpack capacity, wiki from supply = backpack refill; '
                    'rounds weapons: wiki rounds from supply = backpack refill x reload amount'}
        weapons.append(entry)

    # Every rounds-feed record whose reload loads more than one round: a native one whose start or supply is not a
    # multiple of its reload amount reaches a partial last reload (and the same transient below zero) in vanilla play.
    partial = []
    for record, owners in sorted(native.owners(ROUNDS).items()):
        spare, supply, start, amount = struct.unpack_from('<IIII', native.record(ROUNDS, record), 80)
        if amount > 1:
            partial.append({'recordIndex': record, 'owners': [native.path(o) or hexid(o) for o in owners],
                'spareRounds': spare, 'roundsFromSupply': supply, 'startingRounds': start, 'reloadAmount': amount,
                'nonMultiple': bool(start % amount or supply % amount or spare % amount)})
    vanilla = [item for item in partial if item['nonMultiple']]
    if not any(owner.endswith('pistol_broomhandle') for item in vanilla for owner in item['owners']):
        raise ValueError('the P-69 Veto precedent (52 starting rounds, 6-round clips) changed: %s' % partial)
    below_zero = {
        'question': 'own spare rounds not a multiple of the reload amount (3 left, reload 5): what reads the -2?',
        'storage': 'rounds manager (0x3326CF0) live rows at +0x58, 20 bytes each, +0 = own spare rounds (int32)',
        'sequence': [
            'reload completion (owner only, +0x14 bit 0): the magazine gets the full reload amount (0x776BFE) and the '
            'row becomes 3 - 5 = -2 (0x7774EA); the queued write 0x9A34C336 points at that live row (0x7774F1)',
            'the queue accepts it (owned; closed only during world teardown) and, while the world update batches, '
            'flushes it at the next sync point 0xFDC780: after the update phases of this frame (0xFDAF6C, 0xAB5EE6), at '
            'the latest at the start of the next world update (0xFDAF17); unbatched writes flush at once (0xFD9876)',
            'the flush validates with clamp = 1 before it sets the field: the engine validator sees -2 out of range '
            '(unsigned value - min >= 512) and writes the signed clamp, 0, back through the pointer into the live row '
            '(0x34BBEF, 0x34BBF3). Values above 511 saturate at 511 the same way; nothing wraps',
            'so the network field never carries a negative, and a remote copy never runs the subtraction'],
        'readersBeforeTheClamp': {
            'reloadGate': 'signed (setg): -2 does not allow an own reload; the worn backpack is asked, as at 0',
            'reloadPayment': 'jne would pay a later reload from the own rounds, but the next completion is a whole '
                'reload duration later, long after the flush of that frame wrote 0',
            'resupply': 'unsigned (cmovb): a negative sum would give the maximum, but a resupply would have to land '
                'in the same frame as the reload completion, and it is still capped at the maximum',
            'outOfAmmoCue': 'the exactly-0 cue (0x77750A) is skipped for a negative count',
            'hud': 'not traced; at most one frame'},
        'effect': 'harmless: the last partial reload loads a full clip (at most reload amount - 1 extra rounds, 4 on '
            'the AC-8) and the count is 0 by the end of the frame; no wrap, no free ammunition beyond that, no '
            'network desync',
        'vanillaPrecedent': vanilla,
        'roundsWithReloadAmountAboveOne': partial,
        'decision': 'AC-8 rounds.spare_rounds, starting_rounds and rounds_from_supply become real fields (0..511, the '
            'network field), allow_unverified_effect; multiples of 5 recommended, not required'}

    fields = network_fields()
    if {(f['field'], f['bits']) for f in fields} != {(FIELD_MAGAZINES, 5), ('0x%08X' % FIELD_ROUNDS_HASH, 9)}:
        raise ValueError('spare-count network field types changed: %s' % fields)
    report = {'schemaVersion': 2, 'sourceSnapshot': snapshot_regions.SNAPSHOT.name,
        'modules': {'gameDll': {'sha256': limits.PROFILE_DLL_SHA, 'unpackedImageSha256': limits.sha(dll)},
            'executable': {'sha256': limits.PROFILE_EXE_SHA, 'unpackedImageSha256': limits.sha(exe)}},
        'pinnedReferences': {'entities': entity_research.sha(native.entities), 'typelib': entity_research.sha(native.typelib)},
        'gameDll': {'magazineManager': MAGAZINE_MANAGER, 'roundsManager': ROUNDS_MANAGER, 'heatManager': HEAT_MANAGER,
            'assistedReloadManager': ASSISTED_MANAGER, 'weaponManager': WEAPON_MANAGER, 'depositManager': DEPOSIT_MANAGER,
            'functions': {'ownSpareTotal': 0x744180, 'reloadGate': 0x775580, 'backpackCanFeed': 0x73B440,
                'reloadConsume': 0x7768F0, 'teamReload': 0x11A28E0, 'spawnMagazines': 0x76DA90, 'spawnRounds': 0x7798D0,
                'weaponRefill': 0x757F70, 'magazineRefill': 0x76E6D0, 'roundsRefill': 0x77A430, 'resupplyAll': 0x880E20,
                'backpackNodes': 0x8805D0},
            'proof': proof},
        'executable': {'validator': limits.VALIDATOR, 'proof': exe_proof},
        'ownRoundsBelowZero': below_zero,
        'tableShapes': shapes,
        'networkFields': fields,
        'model': [
            'reload gate: the weapon\'s own spare total (magazines or rounds, + a mounted shared deposit) above 0 lets '
            'the wielder reload; only at 0 is the worn backpack asked (type 17, assisted path = weapon or empty, '
            'live amount >= assisted record +20)',
            'self reload: own spares first (1 magazine; or reload amount +92 rounds, no lower bound), the worn '
            'backpack deposit (assisted +20) only when the own total is 0',
            'own rounds below 0 (3 left, reload 5): stored for the rest of the frame, then the clamp of the flush writes 0 '
            'into the live row before the field is set; a full clip was loaded (at most reload amount - 1 extra)',
            'team (assisted) reload: always a backpack deposit (the reloader\'s or the wielder\'s)',
            'spawn: own spares = min(start, maximum) (magazines +140/+148; rounds +88/+80, maximum rounded up to a '
            'multiple of the reload amount); the maximum is scaled by weapon stat 12',
            'resupply: every carried weapon gets min(spare + max(1, from_supply x scale), maximum) (magazines +144, '
            'rounds +84), then the worn backpack deposit gets its refill_amount',
            'natively every team-reload weapon has maximum 0, so start and refill clamp to 0: it keeps nothing',
            'live spare magazines: network field magazines_remaining, int 5 bits (0..31); spare rounds 0x9A34C336, '
            'int 9 bits (0..511); the owner\'s queued write clamps in place',
            'backpack nodes: at most 20, shown while the live amount is above their index'],
        'teamReloadWeapons': weapons, 'writes': 0}
    return report


def main() -> None:
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    for item in report['teamReloadWeapons']:
        print(item['supportWeapon'] or item['weaponPath'], item['ammoKind'], item['weaponAmmo'], item['deposit']['values'],
            item['deposit']['nodeHidingOrderCount'], item.get('fingerprint', {}).get('exact'))
    print(json.dumps(report['networkFields'][:2]))


if __name__ == '__main__':
    main()
