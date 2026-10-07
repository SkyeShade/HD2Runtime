"""What a Helldiver holds and wears, the worn backpack's own values, and the Supply Pack's self-use (research for
player:loadout(), player:backpack(), player:ammo() and hd2.actions.resupply_from_pack).

Read-only. Proves on build F5FEE03DCFDB, from the unpacked game.dll in the retained snapshots and the pinned entity
tables (research/docs/player-equipment-F5FEE03DCFDB.md):

1. Inventory record (manager global game+0x3326738; hash +0x28; descriptors +0x40; records +0x50, stride 0x30;
   counts +0x58, stride 8). The game's own consumers name the slots: get_backpack (0x9A9CC0) returns record +0x0C;
   resupply_all (0x880E20) refills the weapons at +0x00, +0x04 and +0x08 and the deposit of the backpack at +0x0C (but
   never a Supply Pack from itself); the throwable refill (0x9ADAB0) reads the throwable RESOURCE at +0x28 (u64) and
   writes its count at counts +0 with a network field. +0x1C is the selection (research/event-wielder).
2. Deposit instance (manager game+0x33265E8): live amount at +0x50 (stride 8) as research/deposit-limits proved. Its
   definition (DepositComponentData, 0x98 bytes) comes from 0x502710: a per-instance override (+0x60 hash, +0xA0
   records), else the per-type table the entity manager keeps at +0xF12A00 (58 entries of 16 bytes, type % 58, linear
   probing; definitions follow at +0x3A0). The Supply Pack's definition carries two AbilityId members: +0x20 (2628,
   used when a teammate takes supplies from it) and +0x24 (2629, the wearer's own use).
3. The self-use. The avatar's input step (0xA433F0, from the avatar update 0xA3E620 with the action context at avatar
   record +0x870) reads the worn backpack (get_backpack), asks can_use(deposit, backpack, wearer, &reason) (0x880190:
   'NO AMMO' with no supplies, 'NO ROOM' with nothing to refill), writes definition +0x24 into context +4 and calls
   start_action (0xA438E0), which starts ability 2629 on the avatar through start_ability (0x7CAF40, mode 1: the owner
   replicates it). The game's own helper try_start_action (0xA431D0: not busy, may act, start_action(context, request))
   starts an action from a request {ability, target, extra}; a teammate's use goes through the same three steps
   (0x97EEA2..0x97EEBE). Ability 2629's handler (0x1125210) consumes one supply from the worn backpack (0x11A3860 ->
   consume 0x87F970) and resupplies the wearer (0x11AFFC0 -> resupply_all 0x880E20) on its animation event 0x22.
   The input path also sends behavior event 0x453F0C5F to the backpack; the Supply Pack entity owns no
   BehaviorComponent, so that event has no receiver.
4. Ammunition. Weapon magazine instances (manager game+0x3326648; hash +0x20; descriptors +0x38; records +0x50,
   stride 12): +0 spare magazines (the refill writes it with its network field), +4 rounds in the magazine (the game's
   rounds getter 0x742900 returns it).
5. can_use's Supply Pack branch first asks 0x9AD7D0(user): does a weapon of the user (+0x00, +0x04, +0x08) or a
   non-Supply-Pack backpack take ammunition. Its whole call tree (16 functions) writes no memory and has no indirect
   call: a pure query Runtime may call.

Observations: in the mission snapshots the local avatar carries the R-36 Eruptor (+0x00) and the P-113 Verdict
(+0x04), no support weapon and no backpack, and G-4 Gas throwables (resource at +0x28, count 4). Aboard the ship it
carries the JAR-5 Dominator and the P-113 Verdict. No retained snapshot shows a worn backpack: the backpack slot is
proven from code (STRONG), not observed. The Supply Pack's deposit definition (2628 / 2629, capacity 4) is resident in
the per-type table of every snapshot and equals the pinned DepositComponentData record 5.
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
import research_event_wielder as wielder  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/player-equipment-F5FEE03DCFDB.json'
SNAPSHOTS = wielder.SHIP + wielder.MISSION
INVENTORY, DEPOSIT, MAGAZINE, AVATAR, ABILITY = 0x3326738, 0x33265E8, 0x3326648, 0x3326D20, 0x3326640
ENTITY_MANAGER, EQUIPMENT, BEHAVIOR = 0x346BF98, 0x3326DC0, 0x3326740
SUPPLY_PACK = '4EF9A47109239A58'
SELF_ABILITY, OTHER_ABILITY = 2629, 2628
DISPATCH_TABLE = 0x115C784
TRY_START_ACTION, NEEDS_AMMO = 0xA431D0, 0x9AD7D0
NO_TARGET = 0x3483C5C

GAME_PROOFS = {
    'inventory': [
        (0x9A9CDB, 'mov r11, qword ptr [rip + {rip}]', INVENTORY, 'get_backpack(avatar) loads the inventory manager'),
        (0x9A9CE4, 'mov r10d, dword ptr [r11 + 0x30]', None, 'inventory hash capacity +0x30'),
        (0x9A9CEB, 'mov ebx, dword ptr [r11 + 0x38]', None, 'inventory hash multiplier +0x38'),
        (0x9A9CFC, 'mov rdi, qword ptr [r11 + 0x28]', None, 'inventory hash buckets +0x28'),
        (0x9A9D00, 'mov esi, dword ptr [r11 + 0x34]', None, 'inventory hash empty key +0x34'),
        (0x9A9D5E, 'lea rcx, [rax + rax*2]', None, 'record index * 3'),
        (0x9A9D62, 'mov rax, qword ptr [r11 + 0x50]', None, 'inventory records +0x50'),
        (0x9A9D66, 'add rcx, rcx', None, 'record index * 6 (stride 0x30)'),
        (0x9A9D69, 'mov ecx, dword ptr [rax + rcx*8 + 0xc]', None, 'get_backpack returns record +0x0C: the worn backpack'),
        (0x880E2E, 'mov r9, qword ptr [rip + {rip}]', INVENTORY, 'resupply_all(avatar) loads the inventory manager'),
        (0x880ECB, 'add rdi, qword ptr [r9 + 0x50]', None, "resupply_all: the avatar's inventory record"),
        (0x880ECF, 'cmp dword ptr [rdi], eax', None, 'record +0x00 (primary) checked'),
        (0x880ED7, 'mov edx, dword ptr [rdi]', None, 'record +0x00 refilled'),
        (0x880EDC, 'call 0x757f70', None, 'weapon refill (primary)'),
        (0x880F96, 'cmp dword ptr [rdi + 4], eax', None, 'record +0x04 (secondary) checked'),
        (0x880F9F, 'mov edx, dword ptr [rdi + 4]', None, 'record +0x04 refilled'),
        (0x88103E, 'mov eax, dword ptr [rdi + 0xc]', None, 'record +0x0C (backpack) read'),
        (0x8810AD, 'call 0x8c27f0', None, 'its equipment type'),
        (0x8810B2, 'cmp eax, 0x17', None, 'equipment type 0x17 (Supply Pack) is not refilled from itself'),
        (0x8810B7, 'mov edx, dword ptr [rdi + 0xc]', None, 'record +0x0C deposit refilled'),
        (0x8810BD, 'call 0x87fd70', None, 'deposit refill'),
        (0x8810D2, 'cmp dword ptr [rdi + 8], eax', None, 'record +0x08 (support weapon) checked'),
        (0x8810D7, 'mov edx, dword ptr [rdi + 8]', None, 'record +0x08 refilled'),
        (0x8810E7, 'call 0x9adab0', None, 'throwable refill'),
        (0x9ADABF, 'mov rdi, qword ptr [rip + {rip}]', INVENTORY, 'throwable refill loads the inventory manager'),
        (0x9ADB46, 'mov rax, qword ptr [rdi + 0x40]', None, 'inventory descriptors +0x40'),
        (0x9ADB4E, 'test byte ptr [rcx + 0x14], 1', None, 'only the owner refills its counts'),
        (0x9ADB65, 'add rbp, qword ptr [rdi + 0x50]', None, 'inventory records +0x50'),
        (0x9ADB69, 'cmp qword ptr [rbp + 0x28], 0', None, 'record +0x28: the throwable resource (u64)'),
        (0x9ADB97, 'call 0x50cd90', None, 'the throwable definition of that resource'),
        (0x9ADBA8, 'mov rdx, qword ptr [rdi + 0x58]', None, 'inventory counts +0x58'),
        (0x9ADBBD, 'mov r12d, dword ptr [rdx + rsi*8]', None, 'counts row +0 (stride 8): the throwable count'),
        (0x9ADC7D, 'mov edx, 0xd92082f9', None, 'network field of the throwable count'),
        (0x9ADC82, 'mov dword ptr [rax + rsi*8], ebp', None, 'throwable count written'),
    ],
    'deposit': [
        (0x87F99F, 'mov r10d, dword ptr [rcx + 0x28]', None, 'deposit hash capacity +0x28'),
        (0x87F9A3, 'mov r11d, dword ptr [rcx + 0x30]', None, 'deposit hash multiplier +0x30'),
        (0x87F9C6, 'mov r8, qword ptr [rcx + 0x20]', None, 'deposit hash buckets +0x20'),
        (0x87F9CA, 'mov r9d, dword ptr [rcx + 0x2c]', None, 'deposit hash empty key +0x2C'),
        (0x87FA13, 'mov rax, qword ptr [r15 + 0x38]', None, 'deposit descriptors +0x38'),
        (0x87FA1B, 'test byte ptr [rcx + 0x14], 1', None, 'owner check (descriptor +0x14 bit 0)'),
        (0x87FA25, 'mov rax, qword ptr [r15 + 0x50]', None, 'deposit live state +0x50'),
        (0x87FA3D, 'mov ecx, dword ptr [rcx + r13*8]', None, 'live amount (stride 8)'),
        (0x502732, 'mov r11, qword ptr [rip + {rip}]', DEPOSIT, 'definition lookup loads the deposit manager'),
        (0x50274B, 'mov r9d, dword ptr [r11 + 0x68]', None, 'per-instance definition hash capacity +0x68'),
        (0x50274F, 'mov ebx, dword ptr [r11 + 0x70]', None, 'per-instance definition hash multiplier +0x70'),
        (0x502764, 'mov rdi, qword ptr [r11 + 0x60]', None, 'per-instance definition hash buckets +0x60'),
        (0x502768, 'mov esi, dword ptr [r11 + 0x6c]', None, 'per-instance definition hash empty key +0x6C'),
        (0x5027B2, 'imul rax, rax, 0x98', None, 'definition stride 0x98'),
        (0x5027B9, 'add rax, qword ptr [r11 + 0xa0]', None, 'per-instance definitions +0xA0'),
        (0x5027C5, 'mov rcx, qword ptr [r10]', None, 'otherwise the entity type (descriptor +0)'),
        (0x5027CC, 'jmp 0x502210', None, 'per-type lookup'),
        (0x502215, 'mov rax, qword ptr [rip + {rip}]', ENTITY_MANAGER, 'per-type lookup loads the entity manager'),
        (0x50221F, 'mov r10, qword ptr [rax + 0xf12a00]', None, 'deposit settings table (entity manager +0xF12A00)'),
        (0x502226, 'movabs rax, 0x1a7b9611a7b9611b', None, 'type modulo 58 (magic)'),
        (0x502243, 'imul eax, eax, 0x3a', None, '... * 58'),
        (0x502253, 'shl rax, 4', None, 'entry stride 16'),
        (0x502274, 'cmp eax, 0x39', None, '58 buckets (wrap at 57)'),
        (0x50227B, 'cmp r9d, 0x3a', None, 'at most 58 probes'),
        (0x50228C, 'imul rax, rcx, 0x98', None, 'definition stride 0x98'),
        (0x502293, 'add rax, 0x3a0', None, 'definitions follow the 58 entries (+0x3A0)'),
    ],
    'selfUse': [
        (0xA4360B, 'call 0x9a9cc0', None, 'the self-use input reads the worn backpack (get_backpack)'),
        (0xA437E0, 'call 0x880190', None, 'can_use(deposit, backpack, wearer, &reason)'),
        (0xA43853, 'call 0x502710', None, "the backpack's deposit definition"),
        (0xA4385A, 'mov ecx, dword ptr [rax + 0x24]', None, 'definition +0x24: the self-use ability'),
        (0xA4385D, 'mov dword ptr [r13 + 4], ecx', None, 'into the avatar action context +4'),
        (0xA43864, 'call 0xa438e0', None, 'start_action(context, NULL)'),
        (0x97EE08, 'mov r14d, dword ptr [rax + 0x20]', None, "a teammate's use: definition +0x20 (the use-on-other "
            'ability)'),
        (0x8802C5, 'call 0x9ad7d0', None, 'can_use, Supply Pack branch: does the user need weapon ammunition'),
        (0x8802D0, 'call 0x9b1520', None, '... or what 0x9B1520 reports'),
        (0x8802E2, 'call 0x9adcd0', None, '... or throwables'),
        (0x8802EB, 'mov dword ptr [r14], 0xf9fe9e90', None, "'Use Backpack' prompt text (can use)"),
        (0x880314, 'mov dword ptr [r14], 0xf58bec4a', None, "'NO ROOM' (nothing to refill)"),
        (0x8802B7, 'mov dword ptr [r14], 0xf604ecc3', None, "'NO AMMO' (no supplies left)"),
    ],
    'actionContext': [
        (0x97EE5F, 'mov r14, qword ptr [rip + {rip}]', AVATAR, 'the interaction start loads the avatar manager'),
        (0x97EE6F, 'lea rcx, [r14 + 0xf8]', None, 'avatar hash +0xF8'),
        (0x97EE8E, 'lea rdi, [r14 + 0x53e170]', None, 'action context = avatar manager + 0x53E170'),
        (0x97EE95, 'imul rcx, rax, 0x1238', None, '+ avatar index * 0x1238'),
        (0x97EEA2, 'call 0xa43100', None, 'busy?'),
        (0x97EEAE, 'call 0xa43250', None, 'may act?'),
        (0x97EEBE, 'call 0xa438e0', None, 'start_action(context, request)'),
        (0xA431E0, 'call 0xa43100', None, 'try_start_action: busy?'),
        (0xA431EC, 'call 0xa43250', None, 'try_start_action: may act?'),
        (0xA431FB, 'call 0xa438e0', None, 'try_start_action: start_action(context, request)'),
        (0xA43200, 'mov al, 1', None, 'try_start_action returns true'),
        (0xA4311B, 'mov r10, qword ptr [rip + {rip}]', AVATAR, 'busy check loads the avatar manager'),
        (0xA4312B, 'mov r9d, dword ptr [r10 + 0x100]', None, 'avatar hash capacity +0x100'),
        (0xA4313A, 'mov ebx, dword ptr [r10 + 0x108]', None, 'avatar hash multiplier +0x108'),
        (0xA4315B, 'mov rdi, qword ptr [r10 + 0xf8]', None, 'avatar hash buckets +0xF8'),
        (0xA43162, 'mov esi, dword ptr [r10 + 0x104]', None, 'avatar hash empty key +0x104'),
        (0xA431AA, 'imul rax, rcx, 0x1238', None, 'avatar record stride 0x1238'),
        (0xA431B1, 'mov eax, dword ptr [rax + r10 + 0x53e888]', None, 'avatar flags +0x53E888'),
        (0xA431B9, 'shr rax, 0x15', None, 'bit 21'),
        (0xA431BD, 'and al, 1', None, '... is busy'),
        (0xA43301, 'movabs rcx, 0x1f9d9af7875b0200', None, 'may-act mask on +0x53E888'),
        (0xA4330B, 'test qword ptr [rax + r11 + 0x53e888], rcx', None, 'no blocking flag at +0x53E888'),
        (0xA43313, 'mov rdx, qword ptr [rax + r11 + 0x53e880]', None, 'flags +0x53E880'),
        (0xA4331B, 'movabs rax, 0x100010000', None, 'no blocking flag at +0x53E880'),
        (0xA43332, 'test dl, 2', None, 'and bit 1 of +0x53E880 set'),
        (0xA4398C, 'mov r13, qword ptr [rdi + rdx*8 + 0x110]', None, 'avatar descriptors +0x110'),
        (0xA43B1F, 'test r12, r12', None, 'a request given?'),
        (0xA43B24, 'mov eax, dword ptr [r12 + 4]', None, 'request +4 ...'),
        (0xA43B29, 'mov dword ptr [r14 + 8], eax', None, '... -> context +8 (target)'),
        (0xA43B2D, 'mov eax, dword ptr [r12 + 8]', None, 'request +8 ...'),
        (0xA43B32, 'mov dword ptr [r14 + 0xc], eax', None, '... -> context +0xC'),
        (0xA43B36, 'mov r8d, dword ptr [r12]', None, 'request +0 ...'),
        (0xA43B3A, 'mov dword ptr [r14 + 4], r8d', None, '... -> context +4 (ability)'),
        (0xA43569, 'mov eax, dword ptr [rip + {rip}]', NO_TARGET, 'the input step: the no-target value ...'),
        (0xA4356F, 'cmp dword ptr [r13 + 8], eax', None, '... compared with context +8 (target)'),
        (0xA43C62, 'mov eax, dword ptr [rip + {rip}]', NO_TARGET, 'start_action: no target ...'),
        (0xA43C68, 'cmp dword ptr [r14 + 8], eax', None, '... is the self use (context +8)'),
        (0xA43B70, 'mov r9d, 1', None, 'mode 1 (replicated from the owner)'),
        (0xA43B76, 'mov edx, dword ptr [r13 + 8]', None, 'the avatar entity'),
        (0xA43B7A, 'mov rcx, qword ptr [rip + {rip}]', ABILITY, 'the ability manager'),
        (0xA43B87, 'call 0x7caf40', None, 'start_ability(manager, avatar, ability, 1, 1.0)'),
    ],
    'ability': [
        (0x7CAF88, 'mov r8d, dword ptr [rcx + 0x20]', None, 'ability hash capacity +0x20'),
        (0x7CAF8C, 'mov r9d, dword ptr [rcx + 0x28]', None, 'ability hash multiplier +0x28'),
        (0x7CAF9F, 'mov r10, qword ptr [rsi + 0x18]', None, 'ability hash buckets +0x18'),
        (0x7CAFA3, 'mov r11d, dword ptr [rsi + 0x24]', None, 'ability hash empty key +0x24'),
        (0x7CAFDA, 'mov rbp, qword ptr [rsi + 0x38]', None, 'ability records +0x38'),
        (0x7CAFEA, 'imul rdi, r14, 0xe0', None, 'record stride 0xE0'),
        (0x7CB0FD, 'mov dword ptr [rdi + rbp], ebx', None, 'record +0: the running ability id'),
        (0x7CB115, 'mov byte ptr [rdi + rbp + 0x10], 1', None, 'record +0x10: active'),
        (0x7CB145, 'call 0x11509e0', None, 'enter the ability state'),
        (0x11509E7, 'dec edx', None, 'ability dispatch: id - 1'),
        (0x11509E9, 'cmp edx, 0xb32', None, 'ability ids 1..2867'),
        (0x11509FC, 'mov edx, dword ptr [r10 + rdx*4 + 0x115c784]', None, 'ability dispatch table'),
        (0x115B7A2, 'call 0x1125150', None, 'ability 2628 (use on other): handler'),
        (0x115B7B3, 'call 0x1125210', None, 'ability 2629 (self use): handler'),
        (0x1125283, 'call 0x11a3860', None, 'self use, animation event 0x22: consume one supply from the worn backpack'),
        (0x112528B, 'call 0x11affc0', None, '... then resupply the target (the wearer)'),
        (0x11A3AC9, 'call 0x87f970', None, 'consume(deposit, backpack, 1)'),
        (0x11B016C, 'call 0x880e20', None, 'resupply_all(target)'),
    ],
    'magazine': [
        (0x742A42, 'mov r9, qword ptr [rip + {rip}]', MAGAZINE, 'rounds getter loads the weapon magazine manager'),
        (0x742A4B, 'mov r8d, dword ptr [r9 + 0x28]', None, 'magazine hash capacity +0x28'),
        (0x742A4F, 'mov r10d, dword ptr [r9 + 0x30]', None, 'magazine hash multiplier +0x30'),
        (0x742A60, 'mov r11, qword ptr [r9 + 0x20]', None, 'magazine hash buckets +0x20'),
        (0x742A64, 'mov edi, dword ptr [r9 + 0x2c]', None, 'magazine hash empty key +0x2C'),
        (0x742AAF, 'mov rax, qword ptr [r9 + 0x50]', None, 'magazine records +0x50'),
        (0x742AB3, 'lea rdx, [rcx + rcx*2]', None, 'index * 3 (stride 12)'),
        (0x742AB7, 'mov ebp, dword ptr [rax + rdx*4 + 4]', None, 'record +4: rounds in the magazine'),
        (0x76E75A, 'mov rcx, qword ptr [rbp + 0x38]', None, 'magazine descriptors +0x38'),
        (0x76E770, 'mov edx, dword ptr [rax + 0x90]', None, 'definition +0x90: magazines from supply'),
        (0x76E7B5, 'mov rcx, qword ptr [rbp + 0x50]', None, 'magazine records +0x50'),
        (0x76E7B9, 'lea rsi, [r14 + r14*2]', None, 'index * 3'),
        (0x76E7DC, 'mov edx, 0xec64918b', None, 'network field of the spare magazines'),
        (0x76E7E1, 'mov dword ptr [rax + rsi*4], edi', None, 'record +0: spare magazines written (refill)'),
    ],
    'needsAmmo': [
        (0x9AD7E4, 'mov r10, qword ptr [rip + {rip}]', INVENTORY, 'needs_ammo(user) loads the inventory manager'),
        (0x9AD863, 'add rbx, qword ptr [r10 + 0x50]', None, "the user's inventory record"),
        (0x9AD86D, 'call 0x757aa0', None, 'primary takes ammunition?'),
        (0x9AD888, 'call 0x757aa0', None, 'secondary takes ammunition?'),
        (0x9AD8A3, 'call 0x757aa0', None, 'support weapon takes ammunition?'),
        (0x9AD94A, 'cmp eax, 0x17', None, 'a Supply Pack never counts as a backpack that takes ammunition'),
        (0x9AD965, 'mov al, 1', None, 'true'),
    ],
}
# Research-only leads (not used by Runtime): other worn backpacks' instance values.
LEADS = {
    'shield': [
        (0x4BBB81, 'mov r10, qword ptr [rip + {rip}]', 0x3326630, 'shield manager'),
        (0x4BBBEC, 'mov rdi, qword ptr [r10 + 0x58]', None, 'shield instance records +0x58'),
        (0x4BBBF0, 'lea rbx, [rax + rax*4]', None, 'stride 20'),
        (0x4BBC06, 'cvttss2si rax, dword ptr [rax + 0x4c]', None, 'ShieldComponent +76: capacity (150 on the SH-32)'),
        (0x4BBC24, 'cvttss2si rax, dword ptr [rdi + rbx*4 + 4]', None, 'instance +4: current shield health (float)'),
    ],
    'recharge': [
        (0x9ED53A, 'mov r10, qword ptr [rip + {rip}]', 0x3326768, 'recharge manager'),
        (0x9ED5B4, 'mov rax, qword ptr [r10 + 0x48]', None, 'recharge instance floats +0x48 (stride 4)'),
        (0x9ED5B8, 'comiss xmm0, dword ptr [rax + rcx*4]', None, 'ready when the instance value is 0 or less'),
    ],
}


def probe(mem, header, key):
    return wielder.probe(mem, mem.ptr(header), mem.u32(header + 8), mem.u32(header + 12), mem.u32(header + 16), key)


def descriptor_at(mem, pointer):
    return base.descriptor(mem, pointer) if pointer else None


def purity(image, root):
    """The call tree of root: every function, every non-stack memory write, every indirect call or jump."""
    from capstone import x86
    seen, writes, indirect = [], [], []

    def walk(rva):
        if rva in seen:
            return
        seen.append(rva)
        for ins in image.function_insns(rva):
            if ins.mnemonic in ('call', 'jmp') and ins.operands:
                op = ins.operands[0]
                if op.type == x86.X86_OP_IMM:
                    chunk = image.chunk(op.imm)
                    if ins.mnemonic == 'call' or (chunk and chunk[0] == op.imm):
                        walk(op.imm)
                else:
                    indirect.append({'function': rva, 'rva': ins.address, 'asm': ins.mnemonic + ' ' + ins.op_str})
                continue
            if ins.mnemonic.startswith('nop') or not ins.operands or ins.operands[0].type != x86.X86_OP_MEM:
                continue
            if ins.mnemonic in ('cmp', 'test', 'bt', 'push', 'comiss', 'ucomiss'):
                continue
            mem = ins.operands[0].mem
            if mem.base and ins.reg_name(mem.base) == 'rsp':
                continue
            writes.append({'function': rva, 'rva': ins.address, 'asm': ins.mnemonic + ' ' + ins.op_str})
    walk(root)
    return {'root': root, 'functions': seen, 'writes': writes, 'indirect': indirect,
        'pure': not writes and not indirect}


def deposit_settings(mem):
    """Every entry of the per-type deposit definition table: {type: {capacity, startAmount, refillAmount, ...}}."""
    em = mem.ptr(mem.game + ENTITY_MANAGER)
    table = mem.ptr(em + 0xF12A00)
    out = {}
    for slot in range(58):
        kind, index = struct.unpack('<QI', mem.read(table + 16 * slot, 12))
        if kind:
            record = mem.read(table + 0x3A0 + index * 0x98, 0x98)
            capacity, start, refill = struct.unpack_from('<IiI', record, 0)
            other, own = struct.unpack_from('<II', record, 0x20)
            out['%016X' % kind] = {'slot': slot, 'index': index, 'capacity': capacity, 'startAmount': start,
                'refillAmount': refill, 'otherAbility': other, 'selfAbility': own,
                'probe': (kind % 58 - slot) % 58}
    return out


def observe(name, items):
    mem = base.Mem(name)
    players = mem.ptr(mem.game + wielder.PLAYERS)
    inventory, magazine = mem.ptr(mem.game + INVENTORY), mem.ptr(mem.game + MAGAZINE)
    avatar_manager, abilities = mem.ptr(mem.game + AVATAR), mem.ptr(mem.game + ABILITY)
    out = {'snapshot': name, 'players': [], 'depositSettings': deposit_settings(mem),
        'sentinels': {'invalidEntity': mem.u32(mem.game + 0x3483C20), 'invalidTarget': mem.u32(mem.game + 0x3483C5C)}}
    for index in range(mem.u32(players + 0x84)):
        avatar = mem.u32(players + 0x108 + 0x70 * index)
        player = {'avatar': avatar}
        record = probe(mem, inventory + 0x28, avatar)
        if record is not None:
            desc = descriptor_at(mem, mem.ptr(mem.ptr(inventory + 0x40) + 8 * record))
            raw = mem.read(mem.ptr(inventory + 0x50) + record * 0x30, 0x30)
            counts = struct.unpack('<2I', mem.read(mem.ptr(inventory + 0x58) + record * 8, 8))
            slots = dict(zip(('primary', 'secondary', 'support', 'backpack', 'held'), struct.unpack_from('<5I', raw, 0)))
            throwable = '%016X' % struct.unpack_from('<Q', raw, 0x28)[0]
            resolved = {}
            for slot, entity in slots.items():
                kind = wielder.entity_type(mem, entity) if entity else None
                resolved[slot] = {'entity': entity, 'type': kind, 'name': (items.get(kind) or {}).get('name')}
                if kind and slot in ('primary', 'secondary', 'support'):
                    mag = probe(mem, magazine + 0x20, entity)
                    if mag is not None:
                        spare, rounds, third = struct.unpack('<3I', mem.read(mem.ptr(magazine + 0x50) + mag * 12, 12))
                        owner = descriptor_at(mem, mem.ptr(mem.ptr(magazine + 0x38) + 8 * mag))
                        resolved[slot]['magazine'] = {'index': mag, 'spare': spare, 'rounds': rounds, 'third': third,
                            'descriptorEntity': owner and owner['entity']}
            player.update({'inventoryRecord': record, 'descriptorEntity': desc and desc['entity'],
                'owned': desc and desc['authority'], 'slots': resolved, 'selection': struct.unpack_from('<I', raw, 0x1C)[0],
                'throwable': {'type': throwable, 'name': (items.get(throwable) or {}).get('name'),
                    'count': counts[0]}, 'countsRow': list(counts)})
        slot = probe(mem, avatar_manager + 0xF8, avatar)
        if slot is not None:
            context = avatar_manager + 0x53E170 + slot * 0x1238
            flags = struct.unpack('<3Q', mem.read(avatar_manager + 0x53E880 + slot * 0x1238, 24))
            desc = descriptor_at(mem, mem.ptr(avatar_manager + 0x110 + 8 * slot))
            player['actionContext'] = {'index': slot, 'fields': list(struct.unpack('<4I', mem.read(context, 16))),
                'descriptorEntity': desc and desc['entity'], 'busy': bool((flags[1] >> 21) & 1),
                'mayAct': not (flags[1] & 0x1F9D9AF7875B0200) and not (flags[0] & 0x100010000) and bool(flags[0] & 2)}
        running = probe(mem, abilities + 0x18, avatar)
        if running is not None:
            raw = mem.read(mem.ptr(abilities + 0x38) + running * 0xE0, 0x14)
            player['ability'] = {'index': running, 'id': struct.unpack_from('<I', raw, 0)[0], 'active': raw[0x10]}
        out['players'].append(player)
    mem.close()
    return out


def catalog():
    """Item type (16 hex digits) -> {name, kind, api}: the catalogs mods already name things by."""
    items = {}

    def add(resource, name, kind, api, **extra):
        key = '%016X' % int(resource, 16)
        if key not in items:
            items[key] = dict({'name': name, 'kind': kind, 'api': api}, **extra)
    ammo = {w['name']: w['fields'] for w in json.loads((ROOT / 'research/player-weapon-ammo-F5FEE03DCFDB.json')
        .read_text(encoding='utf-8'))['weapons']}
    for weapon in json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text(encoding='utf-8'))['weapons']:
        fields = ammo.get(weapon['name']) or {}
        magazine = {'capacity': fields['capacity']['value'], 'maxSpare': fields['spareMagazines']['value']} if (
            'capacity' in fields and 'spareMagazines' in fields) else None
        for resource in weapon['resources']:
            add(resource, weapon['name'], weapon['slot'], 'hd2.weapon', magazine=magazine)
    support = json.loads((ROOT / 'sdk/SupportWeaponCapabilities.json').read_text(encoding='utf-8'))['weapons']
    support_names = {}
    for weapon in support.values():
        for resource in [weapon.get('canonicalResourceHash')] + list(weapon.get('resourceHashes') or []):
            if resource:
                add(resource, weapon['catalogIdentity'], 'support', 'hd2.support_weapon')
                support_names['%016X' % int(resource, 16)] = weapon['catalogIdentity']
    for item in json.loads((ROOT / 'research/throwable-authoring-F5FEE03DCFDB.json').read_text(encoding='utf-8'))['catalog']:
        if item['identity'].get('resource'):
            add(item['identity']['resource'], item['name'], 'throwable', 'hd2.throwable')
    backpack_names = {b['name'] for b in json.loads((ROOT / 'sdk/BackpackAuthoringCapabilities.json')
        .read_text(encoding='utf-8'))['backpacks']}
    for item in json.loads((ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json').read_text(
            encoding='utf-8'))['backpacks']:
        add(item['resource'], item['name'], 'backpack', 'hd2.backpack')
    for item in json.loads((ROOT / 'research/backpack-ammo-F5FEE03DCFDB.json').read_text(encoding='utf-8'))[
            'backpackFedWeapons']:
        name = item['supportWeapon'] + ' Backpack'
        if name not in backpack_names:
            raise ValueError('weapon-fed backpack missing from the backpack catalog: ' + name)
        add(item['backpackResource'], name, 'backpack', 'hd2.backpack', feeds=item['supportWeapon'])
    links = json.loads((ROOT / 'research/support-equipment-links-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    for rack in links['rackItems'].values():
        weapons = [support_names.get('%016X' % int(i['resource'], 16)) for i in rack
            if (i.get('loadoutEntry') or {}).get('itemType') == 'SupportWeapon']
        weapons = sorted({w for w in weapons if w})
        for i in rack:
            if (i.get('loadoutEntry') or {}).get('itemType') == 'Backpack' and len(weapons) == 1:
                add(i['resource'], weapons[0] + ' backpack', 'backpack', None, carries=weapons[0])
    return items


def table_facts(items):
    """From the pinned entity tables: equipment type and deposit definition of every catalogued backpack, and whether
    it owns a behavior (the receiver of the input path's backpack event)."""
    from scan import tables
    entity_tables = tables.pinned()
    equipment, deposit = entity_tables.component('EquipmentComponentData'), entity_tables.component('DepositComponentData')
    facts = {}
    for key, item in items.items():
        if item['kind'] != 'backpack':
            continue
        components = entity_tables.entity(int(key, 16))
        fact = {'components': sorted(components)}
        if 'EquipmentComponentData' in components:
            fact['equipmentType'] = equipment.decode(components['EquipmentComponentData'])['128']
        if 'DepositComponentData' in components:
            values = deposit.decode(components['DepositComponentData'])
            fact['deposit'] = {'record': components['DepositComponentData'], 'capacity': values['0'],
                'startAmount': values['4'], 'refillAmount': values['8'], 'otherAbility': values['32'],
                'selfAbility': values['36']}
        fact['behavior'] = 'BehaviorComponentData' in components
        facts[key] = fact
    members = {m.offset: (m.type_name, m.name_length) for m in deposit.members() if m.offset in (32, 36)}
    equipment_member = {m.offset: (m.type_name, m.name_length) for m in equipment.members() if m.offset == 128}
    return facts, {'depositAbilityMembers': members, 'equipmentTypeMember': equipment_member}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / wielder.MISSION[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    leads = {group: [image.prove(*row) for row in rows] for group, rows in LEADS.items()}
    data_pins = []
    for ability, case in ((OTHER_ABILITY, 0x115B79F), (SELF_ABILITY, 0x115B7B0)):
        rva = DISPATCH_TABLE + 4 * (ability - 1)
        if struct.unpack_from('<I', data, rva)[0] != case:
            raise ValueError('ability %d no longer dispatches to %X' % (ability, case))
        data_pins.append({'rva': rva, 'bytes': data[rva:rva + 4].hex(),
            'role': 'ability dispatch table entry %d -> 0x%X' % (ability, case)})
    natives = {}
    for name, rva in (('tryStartAction', TRY_START_ACTION), ('needsAmmo', NEEDS_AMMO)):
        natives[name] = {'rva': rva, 'prologue': data[rva:rva + 16].hex()}
    pins = [p for rows in proofs.values() for p in rows]
    pins += [{'rva': n['rva'], 'bytes': n['prologue']} for n in natives.values()] + data_pins
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    from scan import xref
    code = xref.CodeImage(data, image_base, 'game.dll', base.PROFILE_DLL_SHA)
    needs_ammo = purity(code, NEEDS_AMMO)
    if not needs_ammo['pure']:
        raise ValueError('needs_ammo writes memory or calls indirectly: %r' % needs_ammo)
    items = catalog()
    facts, members = table_facts(items)
    supply = facts[SUPPLY_PACK]
    if (supply['equipmentType'], supply['deposit']['selfAbility'], supply['deposit']['otherAbility'],
            supply['deposit']['capacity'], supply['behavior']) != (23, SELF_ABILITY, OTHER_ABILITY, 4, False):
        raise ValueError('the Supply Pack table facts changed: %r' % supply)
    observations = [observe(name, items) for name in SNAPSHOTS]
    by = {o['snapshot']: o for o in observations}
    for o in observations:
        resident = o['depositSettings'].get(SUPPLY_PACK)
        if not resident or (resident['selfAbility'], resident['otherAbility'], resident['capacity']) != (
                SELF_ABILITY, OTHER_ABILITY, 4):
            raise ValueError('the Supply Pack definition is not resident in ' + o['snapshot'])
    for name in wielder.MISSION[:2]:
        local = by[name]['players'][0]
        names = {slot: local['slots'][slot]['name'] for slot in local['slots']}
        if (names['primary'], names['secondary'], names['support'], names['backpack']) != (
                'R-36 Eruptor', 'P-113 Verdict', None, None) or local['throwable']['name'] != 'G-4 Gas':
            raise ValueError('the mission loadout is not observed in ' + name + ': %r' % names)
        magazine = local['slots']['primary']['magazine']
        if not (0 < magazine['rounds'] <= items[local['slots']['primary']['type']]['magazine']['capacity']):
            raise ValueError('the Eruptor magazine is not plausible in ' + name)
        context = local['actionContext']
        if context['fields'][0] != local['avatar'] or context['fields'][2] != 0 or context['busy']:
            raise ValueError('the idle action context is not observed in ' + name)
    if by[wielder.SHIP[0]]['players'][0]['slots']['primary']['name'] != 'JAR-5 Dominator':
        raise ValueError('the ship loadout is not observed')
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'inventory': {'global': INVENTORY, 'hash': 0x28, 'descriptors': 0x40, 'records': 0x50, 'stride': 0x30,
            'slots': {'primary': 0x00, 'secondary': 0x04, 'support': 0x08, 'backpack': 0x0C, 'held': 0x10},
            'selection': 0x1C, 'throwable': 0x28, 'counts': 0x58, 'countStride': 8, 'throwableCount': 0},
        'deposit': {'global': DEPOSIT, 'hash': 0x20, 'descriptors': 0x38, 'live': 0x50, 'liveStride': 8,
            'amount': 0, 'drone': 4, 'overrideHash': 0x60, 'overrideRecords': 0xA0, 'definitionStride': 0x98,
            'settings': {'entityManager': ENTITY_MANAGER, 'table': 0xF12A00, 'buckets': 58, 'entryStride': 16,
                'records': 0x3A0},
            'definition': {'capacity': 0, 'startAmount': 4, 'refillAmount': 8, 'otherAbility': 0x20,
                'selfAbility': 0x24}},
        'magazine': {'global': MAGAZINE, 'hash': 0x20, 'descriptors': 0x38, 'records': 0x50, 'stride': 12,
            'spare': 0, 'rounds': 4},
        'avatar': {'global': AVATAR, 'hash': 0xF8, 'descriptors': 0x110, 'context': 0x53E170, 'stride': 0x1238,
            'contextFields': {'entity': 0, 'ability': 4, 'target': 8, 'extra': 0xC},
            'flags': 0x53E880, 'busyBit': 21, 'noTarget': NO_TARGET, 'mayActMaskHigh': '0x1F9D9AF7875B0200',
            'mayActMaskLow': '0x100010000', 'mayActRequired': 2},
        'ability': {'global': ABILITY, 'hash': 0x18, 'descriptors': 0x30, 'records': 0x38, 'stride': 0xE0, 'id': 0,
            'active': 0x10},
        'supplyPack': {'type': SUPPLY_PACK, 'name': items[SUPPLY_PACK]['name'], 'equipmentType': 23,
            'selfAbility': SELF_ABILITY, 'otherAbility': OTHER_ABILITY, 'capacity': 4,
            'depositRecord': supply['deposit']['record']},
        'natives': natives, 'proofs': proofs, 'dataPins': data_pins, 'leads': leads,
        'purity': {'needsAmmo': needs_ammo}, 'catalog': items, 'tableFacts': facts,
        'tableMembers': {k: {str(o): list(v) for o, v in m.items()} for k, m in members.items()},
        'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'findings': [
            {'item': 'inventory +0x00 / +0x04 primary and secondary weapon', 'confidence': 'CONFIRMED',
                'evidence': 'resupply_all refills them as weapons; the weapon switch selects them (event-wielder); '
                    'every retained snapshot holds the expected catalogued weapons there'},
            {'item': 'inventory +0x08 support weapon', 'confidence': 'STRONG',
                'evidence': 'resupply_all and needs_ammo treat it as a weapon; selection 3; no snapshot carries one'},
            {'item': 'inventory +0x0C worn backpack', 'confidence': 'STRONG',
                'evidence': 'get_backpack (0x9A9CC0) returns it to the self-use input, the teammate interaction and '
                    'resupply_all; consume and refill treat it as the backpack deposit; no snapshot wears one'},
            {'item': 'inventory +0x28 throwable resource, counts +0 throwable count', 'confidence': 'CONFIRMED',
                'evidence': 'the throwable refill reads and writes them; G-4 Gas and 4 in every mission snapshot'},
            {'item': 'deposit live amount and definition (capacity, abilities)', 'confidence': 'CONFIRMED',
                'evidence': 'consume / refill / definition lookup code; the resident Supply Pack definition equals the '
                    'pinned DepositComponentData record 5 in every snapshot'},
            {'item': 'magazine record +0 spare magazines, +4 rounds', 'confidence': 'CONFIRMED',
                'evidence': 'the refill writes +0 with its network field; the rounds getter returns +4; the Eruptor '
                    'reads 6 spare (published maximum 6) and 4 then 3 rounds of 5 between two snapshots'},
            {'item': 'Supply Pack self-use = ability 2629 through try_start_action(context, request)',
                'confidence': 'STRONG',
                'evidence': 'input path and teammate path code; ability dispatch; handler consumes one supply and '
                    'resupplies the wearer; not yet live-tested'},
            {'item': 'needs_ammo (0x9AD7D0) is a pure query', 'confidence': 'CONFIRMED',
                'evidence': 'its whole call tree has no memory write and no indirect call'},
        ],
        'researchOnly': {
            'shieldCharge': {'confidence': 'PLAUSIBLE', 'lead': 'shield manager game+0x3326630, instance records +0x58 '
                'stride 20, +4 current shield health (float) compared against ShieldComponent +76 capacity; no '
                'snapshot wears a shield pack'},
            'jumpPackRecharge': {'confidence': 'PLAUSIBLE', 'lead': 'recharge manager game+0x3326768, instance floats '
                '+0x48 stride 4; ready when the value is 0 or less (remaining seconds, inference); no snapshot wears '
                'a jump pack'},
            'guardDogAmmo': {'confidence': 'CONFIRMED (read through the deposit)', 'lead': 'the Guard Dog backpacks '
                'keep the drone ammunition in their deposit: player:backpack().deposit.amount; live state +4 is the '
                "drone's network id"},
            'depositWrites': {'confidence': 'not implemented', 'reason': 'a direct write to the live amount is local '
                'to one backpack but bypasses the network field queue the owner uses (consume 0x87F970 / refill '
                '0x87FD70 queue field "remaining"); other peers would keep the old value until the next game write. '
                'The game\'s own refill is the safe future path.'},
            'remotePlayers': {'confidence': 'UNKNOWN', 'reason': 'all retained snapshots are solo: no remote avatar '
                'has an inventory record to observe; Runtime reads only the local player'},
        },
        'writes': 0, 'nativeCalls': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    for o in observations:
        for p in o['players']:
            print(o['snapshot'][13:], p['avatar'], {k: v['name'] for k, v in (p.get('slots') or {}).items()},
                (p.get('throwable') or {}).get('name'), (p.get('throwable') or {}).get('count'))


if __name__ == '__main__':
    main()
