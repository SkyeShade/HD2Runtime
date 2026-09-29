"""Prove the native state an event system can POLL (no code patching): game/mission state, players,
entity/unit identity and per-player mission statistics. Read-only research; nothing writes.

The on-disk game.dll and helldivers2.exe are packed; the retained snapshots hold the unpacked images the
game runs. This script re-derives every chain from those images and pins each hop as exact instruction
bytes at exact RVAs (game.dll or exe) so the runtime can re-verify them live, then reads the chains in all
three retained ship snapshots (three different module bases) with small targeted reads.

Nothing here trusts a community offset by address alone: each global is proven from the code that stores
it and the code that consumes it, and each structure layout from the code that creates it.
Requires the research-only packages capstone and numpy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

try:
    import capstone
except ImportError as error:  # research dependency only; never needed at runtime or in tests
    raise SystemExit('research_event_state requires capstone: ' + str(error))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile
import snapshot_image

OUTPUT = ROOT / 'research/event-state-F5FEE03DCFDB.json'
PROFILE_DLL_SHA = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
PROFILE_EXE_SHA = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06'
IMAGE_SIZE = 0x4744000
EXE_IMAGE_SIZE = 0x39E8000
TEXT = (0x1000, 0x1000 + 0x210FA93)
DATA = (0x263C000, 0x263C000 + 0x119B5FC)
EXE_TEXT = (0x1000, 0x1000 + 0x13F364C)
SNAPSHOTS = ['F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap']

# ---------------------------------------------------------------------------------------------- globals
# game.dll .data globals (RVA). Every one is re-proven below from its store site and its consumers.
G_GAME = 0x3326340            # Game object (state machine + entity manager live inside it)
G_ENTITY_MANAGER = 0x346BF98  # game entity manager = Game + 0xE49F0
G_COMPONENT_WORLD = 0x346BFC8 # = entity manager + 0x40; every component manager lives inside it
G_GAME_MODE = 0x33266A0       # "game_mode" component manager (capacity 1)
G_GAME_MODE_MISSION = 0x3326D60
G_PLAYER = 0x3326468          # "player" component manager (capacity 4)
G_AVATAR = 0x3326D20          # "avatar" component manager (capacity 8) = the community "actor list"
G_SCORE = 0x3326AE0           # "score" component manager (capacity 4): per-player mission statistics
G_HEALTH = 0x3326688          # "health" component manager (covered elsewhere; only the dead test is used)
G_SESSION = 0x347CEF0         # network session; +0xB398 = local peer id
STATE_NAMES_RVA = 0x2147F30   # const char *[] GameState names
GAME_MODE_NAMES_RVA = 0x21496D0
# helldivers2.exe globals (RVA)
X_UNIT_REGISTRY = 0x1A100F0
X_ENTITY_MANAGER = 0x1B135B8
X_UNIT_LUA_INDEX_BASE = 0x190829C
X_UNIT_GET_SCENE_GRAPH = 0x2BD870   # unit class vtable slot +0xE8: lea rax,[rcx+0x60]; ret
X_UNIT_VTABLE = 0x1676D80

GAME_STATES = {1: 'Splash', 2: 'TitleScreen', 3: 'Ship', 4: 'Mission', 5: 'PrepareShip', 6: 'PrepareMission'}
STATE_CLASS = {1: 'StateSplash', 2: 'StateTitleScreen', 3: 'StateShip', 4: 'StateGame', 5: 'StatePrepareShip',
    6: 'StatePrepareMission'}

# Pinned instructions: (rva, expected asm with the RIP displacement written as {rip}, rip target or None, role).
GAME_PROOFS = {
    'gameStateMachine': [
        (0x4EE564, 'mov qword ptr [rip + {rip}], rbx', G_GAME, 'Game object pointer stored once during game init'),
        (0xAB8C48, 'add rcx, 0xe49f0', None, 'entity manager is constructed inside the Game object (Game+0xE49F0)'),
        (0x541402, 'mov rax, qword ptr [rip + {rip}]', G_GAME, 'reader loads the Game object'),
        (0x541409, 'cmp dword ptr [rax + 0xac21c], 4', None, 'reader tests current state == 4 (Mission)'),
        (0xAB2FB8, 'lea r15, [rip - 0xab2fbf]', 0, 'change_state: r15 = image base'),
        (0xAB2FC2, 'lea rdx, [rip + {rip}]', 0x2254530, 'log format "on game state change, Exit: %s, Enter: %s"'),
        (0xAB2FC9, 'mov r8d, dword ptr [rcx + 0xac21c]', None, 'old state'),
        (0xAB2FDA, 'lea r14, [rbx*8 + 0x2147f30]', None, 'new state indexes the GameState name table'),
        (0xAB2FE6, 'mov r8, qword ptr [r15 + r8*8 + 0x2147f30]', None, 'old state indexes the GameState name table'),
        (0xAB3013, 'mov eax, dword ptr [rdi + 0xac21c]', None, 'exit dispatch reads current state'),
        (0xAB301B, 'cmp eax, 5', None, 'handled states are 1..6'),
        (0xAB3020, 'mov ecx, dword ptr [r15 + rax*4 + 0xab3314]', None, 'exit jump table'),
        (0xAB309C, 'mov dword ptr [rdi + 0xac21c], ebx', None, 'the state write (one of two writers)'),
        (0xAB30DE, 'mov ecx, dword ptr [r15 + rax*4 + 0xab332c]', None, 'enter jump table'),
        (0xAB3123, 'lea rcx, [rdi + 0x1fa08]', None, 'StateGame block'),
        (0xAB312A, 'mov r8d, 0x8c810', None, 'StateGame block (0x8C810 bytes) is zeroed on every Mission enter'),
        (0xAB3130, 'call 0x208aaa0', None, 'memset'),
        (0xAB499B, 'mov dword ptr [rdi + 0xac21c], 1', None, 'initial state = Splash (the other writer)'),
    ],
    'componentWorld': [
        (0xFDA352, 'lea rcx, [rbx + 0x40]', None, 'component world = entity manager + 0x40'),
        (0xFDA356, 'mov qword ptr [rip + {rip}], rbx', G_ENTITY_MANAGER, 'entity manager global'),
        (0xFDA360, 'mov qword ptr [rip + {rip}], rcx', G_COMPONENT_WORLD, 'component world global'),
        (0xFDA375, 'call 0x551b60', None, 'component world construction'),
        (0x551B7D, 'call 0x568230', None, 'assigns every component-manager global'),
        (0x568236, 'mov rbx, rcx', None, 'rbx = component world'),
        (0x5682A4, 'lea rax, [rbx + 0x898]', None, 'game_mode manager = world + 0x898'),
        (0x5682AB, 'mov qword ptr [rip + {rip}], rax', G_GAME_MODE, 'game_mode global'),
        (0x568D40, 'lea rax, [rbx + 0x771468]', None, 'game_mode_mission manager = world + 0x771468'),
        (0x568D47, 'mov qword ptr [rip + {rip}], rax', G_GAME_MODE_MISSION, 'game_mode_mission global'),
        (0x568DF6, 'lea rax, [rbx + 0x7c6230]', None, 'health manager = world + 0x7C6230'),
        (0x568DFD, 'mov qword ptr [rip + {rip}], rax', G_HEALTH, 'health global'),
        (0x568E12, 'lea rax, [rbx + 0x7c7368]', None, 'score manager = world + 0x7C7368'),
        (0x568E19, 'mov qword ptr [rip + {rip}], rax', G_SCORE, 'score global'),
        (0x568E66, 'lea rax, [rbx + 0x956128]', None, 'avatar manager = world + 0x956128'),
        (0x568E6D, 'mov qword ptr [rip + {rip}], rax', G_AVATAR, 'avatar global'),
        (0x568EC8, 'lea rax, [rbx + 0xea0818]', None, 'player manager = world + 0xEA0818'),
        (0x568ECF, 'mov qword ptr [rip + {rip}], rax', G_PLAYER, 'player global'),
        (0xFDB083, 'mov qword ptr [rip + {rip}], rcx', G_ENTITY_MANAGER, 're-point: entity manager global (no static caller)'),
        (0xFDB08A, 'add rcx, 0x40', None, 're-point: component world'),
        (0xFDB08E, 'mov qword ptr [rip + {rip}], rcx', G_COMPONENT_WORLD, 're-point: component world global'),
        (0xFDB09F, 'jmp 0x568230', None, 're-point: every component-manager global follows'),
    ],
    'gameMode': [
        (0x8F4530, 'mov r9, qword ptr [rip + {rip}]', G_GAME_MODE, 'game_mode add component'),
        (0x8F4537, 'mov eax, dword ptr [r9 + 4]', None, 'total'),
        (0x8F453D, 'cmp eax, 1', None, 'capacity 1'),
        (0x8F4567, 'inc dword ptr [r9 + 8]', None, 'live count +8'),
        (0x8F4576, 'cmova ecx, dword ptr [r9]', None, 'max (debug "max") at +0'),
        (0x8F4581, 'mov qword ptr [r9 + r8*8 + 0x38], rdx', None, 'entity descriptor pointer at +0x38'),
        (0x8F4600, 'mov r9d, dword ptr [rcx]', None, 'debug print reads max at +0'),
        (0x8F460C, 'lea r8, [rip + {rip}]', 0x224C830, '"game_mode" : { "max" : %u, "capacity" : 1 }'),
        (0xAD4C2A, 'mov rax, qword ptr [rip + {rip}]', G_GAME_MODE, 'StateGame on_mission_start'),
        (0xAD4C31, 'lea rbx, [rip - 0xad4c38]', 0, 'rbx = image base'),
        (0xAD4C49, 'mov ecx, dword ptr [rax + 0x40]', None, 'game mode type at +0x40'),
        (0xAD4C53, 'mov rax, qword ptr [rbx + rcx*8 + 0x21496d0]', None, 'type indexes the game-mode name table'),
        (0xACC715, 'mov rax, qword ptr [rip + {rip}]', G_GAME_MODE, 'host-side respawn management gate'),
        (0xACC723, 'cmp dword ptr [rax + 8], edi', None, 'a game mode exists'),
        (0xACC728, 'mov rcx, qword ptr [rax + 0x38]', None, 'its descriptor'),
        (0xACC731, 'test byte ptr [rcx + 0x14], 1', None, 'this peer has authority over the game mode'),
    ],
    'gameModeMission': [
        (0x8FB845, 'mov rdi, qword ptr [rip + {rip}]', G_GAME_MODE_MISSION, 'game_mode_mission add component'),
        (0x8FB857, 'cmp eax, 1', None, 'capacity 1'),
        (0x8FB8ED, 'inc dword ptr [rdi + 0x50]', None, 'live count +0x50'),
        (0x8FB8F9, 'cmova ecx, dword ptr [rdi + 0x48]', None, 'max +0x48'),
        (0x8FB904, 'mov qword ptr [rdi + rdx*8 + 0x80], rbp', None, 'descriptor pointer +0x80'),
        (0x8FBB70, 'mov r9d, dword ptr [rcx + 0x48]', None, 'debug print reads max +0x48'),
        (0x8FBB7D, 'lea r8, [rip + {rip}]', 0x224C898, '"game_mode_mission" : { "max" : %u, "capacity" : 1 }'),
    ],
    'playerManager': [
        (0x60CA8A, 'mov rbx, qword ptr [rip + {rip}]', G_PLAYER, 'player add component'),
        (0x60CA94, 'mov eax, dword ptr [rbx + 0x80]', None, 'total'),
        (0x60CA9C, 'cmp eax, 4', None, 'capacity 4'),
        (0x60CAAC, 'cmp byte ptr [r8], 0', None, 'spawn-info authority byte selects the owned partition'),
        (0x60CADC, 'mov dword ptr [rbx + 0x88], eax', None, 'owned-partition count +0x88 (owned instances first)'),
        (0x60CB2B, 'imul rax, rdx, 0x38', None, 'per-player block stride 0x38'),
        (0x60CB32, 'movups xmmword ptr [rax + rbx + 0x2c8], xmm0', None, 'per-player block at +0x2C8'),
        (0x60CB62, 'inc dword ptr [rbx + 0x84]', None, 'live count +0x84'),
        (0x60CB77, 'cmova ecx, dword ptr [rbx + 0x7c]', None, 'max +0x7C'),
        (0x60CB7E, 'lea rcx, [rbx + 0xd0]', None, 'entity -> index map at +0xD0'),
        (0x60CB85, 'mov qword ptr [rbx + rdx*8 + 0xe8], rdi', None, 'descriptor pointers at +0xE8 + i*8'),
        (0x60CE80, 'mov r9d, dword ptr [rcx + 0x7c]', None, 'debug print reads max +0x7C'),
        (0x60CE8D, 'lea r8, [rip + {rip}]', 0x2247520, '"player" : { "max" : %u, "capacity" : 4 }'),
        (0x62C71A, 'mov rcx, qword ptr [rip + {rip}]', G_PLAYER, 'score index by peer id'),
        (0x62C724, 'mov r10d, dword ptr [rcx + 0x84]', None, 'loop bound = live count'),
        (0x62C730, 'lea r9, [rcx + 0x2c8]', None, 'peer id of player 0'),
        (0x62C737, 'cmp rdx, qword ptr [r9]', None, 'u64 peer id compare'),
        (0x62C73E, 'add r9, 0x38', None, 'next player'),
        (0x62C751, 'mov rcx, qword ptr [rcx + rax*8 + 0xe8]', None, 'matching player descriptor'),
        (0xAD4C9C, 'mov r8, qword ptr [rip + {rip}]', G_SESSION, 'session'),
        (0xAD4CAA, 'lea rdx, [rip + {rip}]', 0x2254E88, '"on_mission_start - peer_id: %llx (self), loadout: %s"'),
        (0xAD4CB8, 'mov r8, qword ptr [r8 + 0xb398]', None, 'the (self) peer id = session+0xB398'),
        (0x1347BE2, 'mov rax, qword ptr [rdx + r13 + 0x2c8]', None, 'telemetry: player peer id'),
        (0x1347BEA, 'cmp rax, qword ptr [rdi + 0xb398]', None, 'telemetry: is it the local peer'),
        (0xACC28A, 'mov r14, qword ptr [rip + {rip}]', G_PLAYER, 'StateGame per-player loop'),
        (0xACC665, 'shl rax, 5', None, 'avatar block stride 0x20'),
        (0xACC66C, 'mov edx, dword ptr [rax + r14 + 0x3a8]', None, 'avatar network id of player i'),
        (0xACC674, 'call 0xfd9ba0', None, 'network id -> avatar entity id'),
        (0x4DB76B, 'mov rax, qword ptr [rip + {rip}]', G_PLAYER, 'local avatar entity'),
        (0x4DB775, 'cmp dword ptr [rax + 0x88], 0', None, 'a locally-owned player exists'),
        (0x4DB77E, 'mov edx, dword ptr [rax + 0x3a8]', None, 'player 0 avatar network id'),
        (0x6078C1, 'imul r12, rax, 0x70', None, 'set_player_avatar: owned block stride 0x70'),
        (0x6079B5, 'mov dword ptr [r12 + rbp + 0x108], ebx', None, 'avatar entity id at +0x108 + i*0x70'),
        (0x6079CF, 'call 0xfd9af0', None, 'entity id -> network id'),
        (0x6079D4, 'mov dword ptr [rdi + 0x3a8], eax', None, 'avatar network id at +0x3A8 + i*0x20'),
        (0x60C6F2, 'mov dword ptr [rbx + rbp + 0x3a8], 0x7fff', None, 'avatar cleared: network id 0x7FFF'),
        (0x608B2C, 'imul rax, rcx, 0x38', None, 'set_player_state'),
        (0x608B4C, 'mov dword ptr [rax + r9 + 0x2e0], ebx', None, 'player lifecycle state at +0x2E0 + i*0x38'),
        (0xACC65B, 'lea r12, [rax + 0x2c8]', None, 'stuck check: per-player block'),
        (0xACC773, 'mov ecx, dword ptr [r12 + 0x18]', None, 'lifecycle state (+0x2E0)'),
        (0xACC789, 'sub ecx, 1', None, 'state 2 ->'),
        (0xACC78C, 'je 0xacc81d', None, '... WaitingForRespawnTimer branch'),
        (0xACC792, 'cmp ecx, 1', None, 'state 3 ->'),
        (0xACC7F1, 'lea rdx, [rip + {rip}]', 0x2254B90, '"Player %llx stuck in Spawned state while dead ..." (state 3)'),
        (0xACC80F, 'mov dword ptr [r12 + 0x18], 1', None, 'forced recovery to state 1'),
        (0xACC850, 'lea rdx, [rip + {rip}]', 0x2254B30, '"... stuck in WaitingForRespawnTimer state ..." (state 2)'),
        (0xACC700, 'mov rcx, qword ptr [rip + {rip}]', G_HEALTH, 'dead test on the avatar'),
        (0xACC707, 'call 0x927050', None, 'health is_dead(avatar)'),
        (0x9270E4, 'imul rcx, rax, 0x1b8', None, 'health record stride'),
        (0x9270EB, 'mov rax, qword ptr [r10 + 0x1058]', None, 'health records'),
        (0x9270F2, 'cmp dword ptr [rcx + rax + 0x19c], 2', None, 'dead = record +0x19C >= 2'),
    ],
    'avatarManager': [
        (0x83AF08, 'mov rsi, qword ptr [rip + {rip}]', G_AVATAR, 'avatar add component'),
        (0x83AF15, 'mov eax, dword ptr [rsi + 0x68]', None, 'total'),
        (0x83AF1A, 'cmp eax, 8', None, 'capacity 8'),
        (0x83AF2A, 'cmp byte ptr [r8], r15b', None, 'spawn-info authority byte'),
        (0x83AF4F, 'mov dword ptr [rsi + 0x70], eax', None, 'owned-partition count +0x70'),
        (0x83B030, 'inc dword ptr [rsi + 0x6c]', None, 'live count +0x6C'),
        (0x83B03C, 'cmova ecx, dword ptr [rsi + 0x64]', None, 'max +0x64'),
        (0x83B043, 'lea rcx, [rsi + 0xf8]', None, 'entity -> index map at +0xF8'),
        (0x83B04A, 'mov qword ptr [rsi + rdi*8 + 0x110], r14', None, 'descriptor pointers at +0x110 + i*8'),
        (0x83B450, 'mov r9d, dword ptr [rcx + 0x64]', None, 'debug print reads max +0x64'),
        (0x83B45D, 'lea r8, [rip + {rip}]', 0x224B2F8, '"avatar" : { "max" : %u, "capacity" : 8 }'),
        (0x289F36, 'mov rdx, qword ptr [rip + {rip}]', G_AVATAR, 'iteration'),
        (0x289F4E, 'cmp dword ptr [rdx + 0x6c], ebx', None, 'bound = live count +0x6C'),
        (0x289F97, 'mov rcx, qword ptr [rdx + rbx*8 + 0x110]', None, 'descriptor i'),
        (0x4B0E3F, 'mov rdx, qword ptr [rip + {rip}]', G_AVATAR, 'entity -> avatar index'),
        (0x4B0E4C, 'mov r10d, dword ptr [rdx + 0x100]', None, 'map capacity'),
        (0x4B0E53, 'mov ebx, dword ptr [rdx + 0x108]', None, 'map multiplier'),
        (0x4B0E59, 'imul ebx, eax', None, 'hash = key * multiplier'),
        (0x4B0E65, 'mov rdi, qword ptr [rdx + 0xf8]', None, 'map slots {u32 key, u32 index}'),
        (0x4B0E6C, 'mov esi, dword ptr [rdx + 0x104]', None, 'empty key'),
        (0x4B0E82, 'lea edx, [r8 + rbx]', None, 'probe'),
        (0x4B0E86, 'and rdx, rcx', None, '& (capacity - 1)'),
    ],
    'entityManager': [
        (0xFDC191, 'mov r15d, dword ptr [rsi + 0xf32f14]', None, 'free record cursor'),
        (0xFDC198, 'lea rcx, [rsi + 0xf1aeb0]', None, 'entity id -> record map'),
        (0xFDC1A4, 'lea r14, [r15*2 + 0x1e65e3]', None, 'record = em + 0xF32F18 + slot*24'),
        (0xFDC1AC, 'add r14, r15', None, ''),
        (0xFDC1AF, 'lea r14, [rsi + r14*8]', None, ''),
        (0xFDC1BB, 'mov dword ptr [r14 + 8], ebx', None, 'descriptor +8 = entity id'),
        (0xFDC1BF, 'mov dword ptr [r14 + 0xc], r9d', None, 'descriptor +0xC = unit id (0 until spawned)'),
        (0xFDC1C3, 'mov qword ptr [r14], rdi', None, 'descriptor +0 = entity type hash (u64)'),
        (0xFDC1C9, 'mov dword ptr [r14 + 0x10], eax', None, 'descriptor +0x10 = network id (0x7FFF none)'),
        (0xFDC1CD, 'mov dword ptr [r14 + 0x14], r9d', None, 'descriptor +0x14 flags'),
        (0xFDC1D1, 'cmp byte ptr [rbp], r9b', None, 'spawn-info authority byte'),
        (0xFDC1D7, 'mov dword ptr [r14 + 0x14], 1', None, 'flags bit0 = created with authority'),
        (0xFDC20D, 'cmp eax, 0x800', None, '2048 records'),
        (0xFDC263, 'cmp edx, 0x7fff', None, 'no network id'),
        (0xFDC26B, 'lea rcx, [rsi + 0xf22ec8]', None, 'network id -> record map'),
        (0xFDBCE6, 'or dword ptr [rsi + 0x14], 1', None, 'authority gained'),
        (0xFDBF85, 'and dword ptr [rsi + 0x14], 0xfffffffe', None, 'authority lost'),
        (0xFD9BA4, 'mov r11, qword ptr [rip + {rip}]', G_ENTITY_MANAGER, 'network id -> entity id'),
        (0xFD9BB1, 'cmp edx, 0x7fff', None, '0x7FFF = none'),
        (0xFD9BC9, 'mov r10d, dword ptr [r11 + 0xf22ed0]', None, 'map capacity'),
        (0xFD9BD7, 'mov ebx, dword ptr [r11 + 0xf22ed8]', None, 'map multiplier'),
        (0xFD9BF9, 'mov rdi, qword ptr [r11 + 0xf22ec8]', None, 'map slots'),
        (0xFD9C00, 'mov esi, dword ptr [r11 + 0xf22ed4]', None, 'empty key'),
        (0xFD9C49, 'mov eax, dword ptr [rax + 4]', None, 'record slot'),
        (0xFD9C50, 'lea rax, [rax + 0x1e65e4]', None, 'em + 0xF32F20 + slot*24 = descriptor +8'),
        (0xFD9C5B, 'mov eax, dword ptr [rax]', None, 'entity id'),
    ],
    'score': [
        (0x631B9A, 'mov rbx, qword ptr [rip + {rip}]', G_SCORE, 'score add component'),
        (0x631BA4, 'mov eax, dword ptr [rbx + 0x37d08]', None, 'total'),
        (0x631BAC, 'cmp eax, 4', None, 'capacity 4'),
        (0x631BFC, 'lea rax, [rdx + rdx*4]', None, 'record stride 0x28'),
        (0x631C00, 'movups xmmword ptr [rbx + rax*8 + 0x37d98], xmm0', None, 'stat record zeroed on component add'),
        (0x631C18, 'inc dword ptr [rbx + 0x37d0c]', None, 'live count +0x37D0C'),
        (0x631C35, 'mov dword ptr [rbx + 0x37d04], ecx', None, 'max +0x37D04'),
        (0x631C3B, 'lea rcx, [rbx + 0x37d58]', None, 'entity -> index map'),
        (0x631C42, 'mov qword ptr [rbx + rdx*8 + 0x37d70], rdi', None, 'descriptor pointers (the PLAYER entity)'),
        (0x631E30, 'mov r9d, dword ptr [rcx + 0x37d04]', None, 'debug print reads max'),
        (0x62C764, 'mov r9d, dword ptr [r11 + 0x37d60]', None, 'player entity -> score index (map capacity)'),
        (0x62C78C, 'mov rdi, qword ptr [r11 + 0x37d58]', None, 'map slots'),
        (0x62CD3F, 'mov rsi, qword ptr [rip + {rip}]', G_SCORE, 'get_stat(peer, key, include_sources)'),
        (0x62CD50, 'call 0x62c710', None, 'peer -> score index'),
        (0x62CD70, 'add rax, 0x1657', None, 'record = score + 0x37D98 + i*0x28'),
        (0x62CD7D, 'lea rax, [rax + rax*4]', None, ''),
        (0x62CD81, 'lea rsi, [rsi + rax*8]', None, ''),
        (0x62CD88, 'call 0x1731a60', None, 'main table lookup'),
        (0x62CD96, 'mov edi, dword ptr [rax + 4]', None, 'int value at entry +4'),
        (0x62CDA2, 'mov r9, qword ptr [rsi + 0x18]', None, 'source array at record +0x18'),
        (0x62CDD0, 'mov eax, dword ptr [rcx - 4]', None, 'source entry key (block +8 + e*0x14)'),
        (0x62CDDB, 'add edi, dword ptr [rcx]', None, 'source int value summed'),
        (0x62CDDF, 'add rcx, 0x14', None, 'source entry stride'),
        (0x62CDE3, 'cmp edx, 0x10', None, '16 entries per source'),
        (0x6303AA, 'add r13, 0x148', None, 'source block stride'),
        (0x6303B1, 'cmp r12d, 0x40', None, '64 source blocks'),
        (0x1731A6A, 'mov r8d, dword ptr [rcx + 8]', None, 'table capacity'),
        (0x1731A70, 'mov r10d, dword ptr [rcx + 0x10]', None, 'table multiplier'),
        (0x1731A77, 'imul r10d, edx', None, 'hash = key * multiplier'),
        (0x1731A84, 'mov r11, qword ptr [rcx]', None, 'table entries'),
        (0x1731A87, 'mov ebx, dword ptr [rcx + 0xc]', None, 'empty key'),
        (0x1731A96, 'and rdx, rcx', None, '& (capacity - 1)'),
        (0x1731A99, 'lea rcx, [rdx + rdx*4]', None, 'entry stride 0x14'),
        (0x62C9CD, 'add dword ptr [rax + 4], ebp', None, 'add_stat: unattributed amount into the main table'),
        (0x62C9E6, 'mov r11, qword ptr [rdi + rcx*8 + 0x37db0]', None, 'add_stat: attributed amount into a source'),
        (0x62CA3A, 'add dword ptr [r8 + 4], ebp', None, ''),
        (0x6317B6, 'mov edx, 0x62048502', None, '"alive" stat key'),
        (0x631801, 'mov byte ptr [rax + 0xc], 0', None, 'alive = 0'),
        (0x6318C6, 'mov edx, 0x62048502', None, '"alive" stat key'),
        (0x631911, 'mov byte ptr [rax + 0xc], 1', None, 'alive = 1'),
    ],
}

EXE_PROOFS = {
    'engineEntity': [
        (0x86A92, 'call 0x604170', None, 'engine EntityManager constructor'),
        (0x86A97, 'mov qword ptr [rip + {rip}], rax', X_ENTITY_MANAGER, 'engine EntityManager global'),
        (0x604160, 'shl edx, 0x16', None, 'make_entity(index, generation)'),
        (0x604163, 'lea eax, [rdx + rcx]', None, 'id = index + (generation << 22)'),
        (0x6046A6, 'lea r14, [rcx + 0x80]', None, 'generation array {u32 size, u32 cap, u8 *data}'),
        (0x6046ED, 'mov byte ptr [rcx + rax], 0', None, 'new index starts at generation 0'),
        (0x604755, 'mov rax, qword ptr [rbx + 0x88]', None, 'create: generation bytes'),
        (0x604763, 'shl edx, 0x16', None, 'create: generation << 22'),
        (0x604766, 'add edx, r8d', None, 'create: + index'),
        (0x604793, 'and edx, 0x3fffff', None, 'destroy: index = id & 0x3FFFFF'),
        (0x6047A2, 'shr eax, 0x16', None, 'destroy: generation = id >> 22'),
        (0x6047A5, 'cmp dl, al', None, 'destroy: 8-bit generation compare (stale handle ignored)'),
        (0x6047CF, 'inc byte ptr [rax + rbx]', None, 'destroy: generation++ invalidates every copy of the id'),
    ],
    'unitRegistry': [
        (0x86A65, 'call 0x170640', None, 'unit registry constructor'),
        (0x86A75, 'mov qword ptr [rip + {rip}], rax', X_UNIT_REGISTRY, 'unit registry global'),
        (0x9D8CF, 'mov rsi, qword ptr [rip + {rip}]', X_UNIT_REGISTRY, 'unit_from_id'),
        (0x9D8D8, 'lea rcx, [rsi + 0xd0]', None, 'registry lock (shared)'),
        (0x9D8E7, 'and eax, 0x3fffff', None, 'index = id & 0x3FFFFF'),
        (0x9D8EC, 'cmp eax, dword ptr [rsi + 0x98]', None, 'index < count (+0x98)'),
        (0x9D8FA, 'mov rax, qword ptr [rsi + 0xa0]', None, 'generation bytes (+0xA0)'),
        (0x9D901, 'shr ebx, 0x16', None, 'generation = id >> 22'),
        (0x9D904, 'cmp byte ptr [rcx + rax], bl', None, '8-bit generation compare'),
        (0x9D909, 'mov rax, qword ptr [rsi + 0x88]', None, 'unit objects (+0x88)'),
        (0x9D910, 'mov rbx, qword ptr [rax + rcx*8]', None, 'unit object'),
        (0x407683, 'lea rdx, [rip + {rip}]', 0x1669180, 'Lua table "Unit"'),
        (0x407692, 'lea rdx, [rip + {rip}]', 0x16818B8, 'Lua name "world_position"'),
        (0x4076A2, 'lea rdx, [rip + {rip}]', 0x407810, 'Unit.world_position implementation'),
        (0x40784E, 'shr edi, 2', None, 'Lua unit reference = unit id << 2'),
        (0x407851, 'sub ebx, dword ptr [rip + {rip}]', X_UNIT_LUA_INDEX_BASE, 'node index - Lua base (1)'),
        (0x407859, 'call 0x9d8c0', None, 'unit_from_id'),
        (0x407864, 'call qword ptr [rdx + 0xe8]', None, 'scene graph = vtable[+0xE8](unit)'),
        (0x40786D, 'shl rdx, 6', None, 'node * 64 (float4x4)'),
        (0x407871, 'mov rcx, qword ptr [rax + 0x28]', None, 'world poses = scene graph +0x28'),
        (0x407875, 'add rcx, 0x30', None, 'translation row at +0x30'),
    ],
}

# The two sites of the native Booster research style: enum-name tables.
GAME_MODE_NAMES = ['None', 'Mission', 'Horde', 'Opportunity', 'Tutorial', 'Blitz', 'Gloom', 'Infiltration']


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class Image:
    def __init__(self, data: bytes, base: int, text: tuple[int, int]):
        self.data, self.base, self.text = data, base, text
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def insn(self, rva):
        found = next(self.md.disasm(self.data[rva:rva + 16], rva), None)
        if found is None:
            raise ValueError('undecodable instruction at %x' % rva)
        return found

    def cstr(self, rva):
        return self.data[rva:self.data.index(b'\0', rva)].decode('latin-1')

    def pointer_rva(self, rva):
        value = struct.unpack_from('<Q', self.data, rva)[0]
        return value - self.base if self.base <= value < self.base + len(self.data) else None

    def prove(self, rva, expected, target, role):
        insn = self.insn(rva)
        text = insn.mnemonic + (' ' + insn.op_str if insn.op_str else '')
        match = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', text)
        resolved = None
        if match:
            resolved = rva + insn.size + int(match.group(2), 16) * (1 if match.group(1) == '+' else -1)
            text = text[:match.start()] + '[rip + {rip}]' + text[match.end():]
            if expected.find('{rip}') < 0 and 'rip' in expected:  # literal rip form (e.g. image base lea)
                text = insn.mnemonic + ' ' + insn.op_str
        if text != expected:
            raise ValueError('instruction at %x changed: %r != %r' % (rva, text, expected))
        if target is not None and resolved != target:
            raise ValueError('instruction at %x resolves to %s, expected %x' % (rva, resolved, target))
        out = {'rva': rva, 'bytes': self.data[rva:rva + insn.size].hex(), 'asm': insn.mnemonic + ' ' + insn.op_str,
            'role': role}
        if resolved is not None:
            out['ripTarget'] = resolved
        return out

    def sweep(self):
        """Linear sweep of .text, one instruction at a time (streamed; bounded memory)."""
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.skipdata = True
        yield from md.disasm_lite(self.data[self.text[0]:self.text[1]], self.text[0])


def rip_of(rva, size, operands):
    match = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', operands)
    if not match:
        return None
    return rva + size + int(match.group(2), 16) * (1 if match.group(1) == '+' else -1)


# ------------------------------------------------------------------------------------------- snapshots
class Mem:
    """Targeted reads from one retained snapshot (never loads the whole file)."""

    def __init__(self, name):
        self.name = name
        self.s = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        self.game = self.s.modules['game.dll']['base']
        self.exe_name = [k for k in self.s.modules if k.endswith('.exe')][0]
        self.exe = self.s.modules[self.exe_name]['base']

    def read(self, address, size):
        region = self.s.region(address)
        if region is None or region['status'] != 1 or address + size > region['base'] + region['size']:
            return None
        self.s.handle.seek(region['data_offset'] + address - region['base'])
        return self.s.handle.read(size)

    def u32(self, address):
        data = self.read(address, 4)
        return None if data is None else struct.unpack('<I', data)[0]

    def u64(self, address):
        data = self.read(address, 8)
        return None if data is None else struct.unpack('<Q', data)[0]

    def ptr(self, address):
        value = self.u64(address)
        return value if value and 0x10000 <= value < 0x800000000000 else None

    def close(self):
        self.s.close()


def descriptor(mem, pointer):
    data = pointer and mem.read(pointer, 24)
    if not data:
        return None
    kind, entity, unit, net, flags = struct.unpack('<QIIII', data)
    return {'type': '%016X' % kind, 'entity': entity, 'entityIndex': entity & 0x3FFFFF, 'entityGeneration': entity >> 22,
        'unit': unit, 'networkId': net, 'flags': flags, 'authority': bool(flags & 1)}


def map_lookup(mem, header, key):
    """The game's open-addressing map: {u64 slots, u32 capacity, u32 empty, u32 multiplier}, slot = {u32 key, u32 value}."""
    raw = mem.read(header, 20)
    slots, capacity, empty, multiplier = struct.unpack('<QIII', raw)
    if not capacity or capacity & (capacity - 1):
        return None
    table = mem.read(slots, capacity * 8)
    start = (key * multiplier) & 0xFFFFFFFF
    for probe in range(capacity):
        k, value = struct.unpack_from('<II', table, ((start + probe) & (capacity - 1)) * 8)
        if k == key:
            return None if value == 0xFFFFFFFF else value
        if k == empty:
            return None
    return None


def stat_table(mem, record, key_names):
    data, capacity, empty, multiplier = struct.unpack('<QIII', mem.read(record, 20))
    sources = mem.u64(record + 0x18)
    entries = {}
    raw = mem.read(data, capacity * 0x14) if capacity else b''
    for slot in range(capacity):
        key, integer, real, flag = struct.unpack_from('<IIfB', raw, slot * 0x14)
        if key != empty:
            entries[key_names.get(key, '%08X' % key)] = {'key': key, 'int': integer, 'float': round(real, 4), 'bool': flag}
    used = []
    if sources:
        block = mem.read(sources, 0x40 * 0x148)
        for index in range(0x40):
            source = struct.unpack_from('<Q', block, index * 0x148)[0]
            if source:
                values = {}
                for entry in range(16):
                    key, integer, real = struct.unpack_from('<IIf', block, index * 0x148 + 8 + entry * 0x14)
                    if not key:
                        break
                    values[key_names.get(key, '%08X' % key)] = {'int': integer, 'float': round(real, 4)}
                used.append({'block': index, 'source': '%016X' % source, 'entries': values})
    return {'table': {'capacity': capacity, 'emptyKey': empty, 'multiplier': multiplier}, 'mainEntries': entries,
        'sourceBlocksInUse': used}


def observe(name, stat_keys, key_names):
    mem = Mem(name)
    out = {'snapshot': name, 'gameDllBase': '%X' % mem.game, 'exeBase': '%X' % mem.exe}
    game = mem.ptr(mem.game + G_GAME)
    state = mem.u32(game + 0xAC21C)
    names = [mem.read(mem.ptr(mem.game + STATE_NAMES_RVA + 8 * i), 24).split(b'\0')[0].decode() for i in range(9)]
    out['gameState'] = {'value': state, 'name': names[state], 'gameObjectMinusEntityManager':
        '%X' % (mem.ptr(mem.game + G_ENTITY_MANAGER) - game)}
    em = mem.ptr(mem.game + G_ENTITY_MANAGER)
    world = mem.ptr(mem.game + G_COMPONENT_WORLD)
    managers = {'game_mode': (G_GAME_MODE, 0x898), 'game_mode_mission': (G_GAME_MODE_MISSION, 0x771468),
        'health': (G_HEALTH, 0x7C6230), 'score': (G_SCORE, 0x7C7368), 'avatar': (G_AVATAR, 0x956128),
        'player': (G_PLAYER, 0xEA0818)}
    out['componentWorld'] = {'worldMinusEntityManager': world - em, 'managersAtProvenOffsets':
        all(mem.ptr(mem.game + g) == world + o for g, o in managers.values())}
    gm = mem.ptr(mem.game + G_GAME_MODE)
    out['gameMode'] = {'count': mem.u32(gm + 8), 'type': mem.u32(gm + 0x40), 'descriptor': descriptor(mem, mem.ptr(gm + 0x38))}
    gmm = mem.ptr(mem.game + G_GAME_MODE_MISSION)
    out['gameModeMission'] = {'count': mem.u32(gmm + 0x50), 'descriptor': descriptor(mem, mem.ptr(gmm + 0x80))}
    local_peer = mem.u64(mem.ptr(mem.game + G_SESSION) + 0xB398)
    pm = mem.ptr(mem.game + G_PLAYER)
    block = mem.read(pm, 0x430)
    count, owned = struct.unpack_from('<II', block, 0x84)
    players = []
    for i in range(count):
        d = descriptor(mem, struct.unpack_from('<Q', block, 0xE8 + 8 * i)[0])
        peer = struct.unpack_from('<Q', block, 0x2C8 + 0x38 * i)[0]
        net = struct.unpack_from('<I', block, 0x3A8 + 0x20 * i)[0]
        slot = None if net == 0x7FFF else map_lookup(mem, em + 0xF22EC8, net)
        avatar = mem.u32(em + 0xF32F20 + 24 * slot) if slot is not None else None
        players.append({'index': i, 'descriptor': d, 'peerId': '%016X' % peer, 'isLocalPeer': peer == local_peer,
            'ownedPartition': i < owned, 'lifecycleState': struct.unpack_from('<I', block, 0x2E0 + 0x38 * i)[0],
            'avatarNetworkId': net, 'avatarEntityViaNetworkId': avatar,
            'avatarEntityOwnedBlock': struct.unpack_from('<I', block, 0x108 + 0x70 * i)[0] if i < owned else None,
            'avatarFlagsWord': '%08X' % struct.unpack_from('<I', block, 0x3AC + 0x20 * i)[0]})
    out['players'] = {'max': struct.unpack_from('<I', block, 0x7C)[0], 'total': struct.unpack_from('<I', block, 0x80)[0],
        'count': count, 'ownedPartition': owned, 'localPeerId': '%016X' % local_peer, 'players': players}
    am = mem.ptr(mem.game + G_AVATAR)
    header = mem.read(am, 0x150)
    a_count, a_owned = struct.unpack_from('<II', header, 0x6C)
    ureg = mem.ptr(mem.exe + X_UNIT_REGISTRY)
    u_count = mem.u32(ureg + 0x98)
    avatars = []
    for i in range(a_count):
        d = descriptor(mem, struct.unpack_from('<Q', header, 0x110 + 8 * i)[0])
        index = map_lookup(mem, am + 0xF8, d['entity'])
        unit = d['unit']
        uidx, ugen = unit & 0x3FFFFF, (unit >> 22) & 0xFF
        entry = {'index': i, 'descriptor': d, 'mapIndex': index}
        if uidx < u_count and mem.read(mem.ptr(ureg + 0xA0) + uidx, 1)[0] == ugen:
            obj = mem.ptr(mem.ptr(ureg + 0x88) + 8 * uidx)
            method = mem.ptr(mem.ptr(obj) + 0xE8)
            poses = mem.ptr(obj + 0x60 + 0x28)
            matrix = struct.unpack('<16f', mem.read(poses, 64))
            entry['unit'] = {'objectUnitId': mem.u32(obj + 8), 'vtableRva': '%X' % (mem.ptr(obj) - mem.exe),
                'sceneGraphMethodRva': '%X' % (method - mem.exe), 'sceneGraphMethodBytes': mem.read(method, 5).hex(),
                'sceneGraphWord10Unproven': mem.u32(obj + 0x60 + 0x10), 'rootTranslation': [round(v, 4) for v in matrix[12:15]],
                'rootRotationRows': [[round(v, 4) for v in matrix[r * 4:r * 4 + 3]] for r in range(3)],
                'finite': all(v == v and abs(v) < 1e5 for v in matrix)}
        avatars.append(entry)
    out['avatars'] = {'max': struct.unpack_from('<I', header, 0x64)[0], 'total': struct.unpack_from('<I', header, 0x68)[0],
        'count': a_count, 'ownedPartition': a_owned, 'avatars': avatars}
    sm = mem.ptr(mem.game + G_SCORE)
    s_max, s_total, s_count, s_owned = struct.unpack('<IIII', mem.read(sm + 0x37D04, 16))
    scores = []
    for i in range(s_count):
        d = descriptor(mem, mem.ptr(sm + 0x37D70 + 8 * i))
        scores.append({'index': i, 'playerEntity': d['entity'], 'descriptor': d,
            'stats': stat_table(mem, sm + 0x37D98 + 0x28 * i, key_names)})
    out['score'] = {'max': s_max, 'total': s_total, 'count': s_count, 'ownedPartition': s_owned, 'players': scores}
    # Entity identity across every live game entity record, validated against the ENGINE generation bytes.
    eem = mem.ptr(mem.exe + X_ENTITY_MANAGER)
    g_size = mem.u32(eem + 0x80)
    gens = mem.read(mem.ptr(eem + 0x88), g_size)
    u_gens = mem.read(mem.ptr(ureg + 0xA0), u_count)
    records = mem.read(em + 0xF32F18, 0x800 * 24)
    live = ok = units = units_ok = nonzero = 0
    for slot in range(0x800):
        _, entity, unit, _, _ = struct.unpack_from('<QIIII', records, slot * 24)
        if not entity:
            continue
        live += 1
        ok += (entity & 0x3FFFFF) < g_size and gens[entity & 0x3FFFFF] == (entity >> 22) & 0xFF
        nonzero += entity >> 22 != 0
        if unit:
            units += 1
            units_ok += (unit & 0x3FFFFF) < u_count and u_gens[unit & 0x3FFFFF] == (unit >> 22) & 0xFF
    out['identity'] = {'liveEntityRecords': live, 'entityGenerationMatches': ok, 'entitiesWithNonzeroGeneration': nonzero,
        'engineEntityIndices': g_size, 'recordsWithUnit': units, 'unitGenerationMatches': units_ok, 'unitRegistryCount': u_count,
        'recordCursor': mem.u32(em + 0xF32F14)}
    # Pinned code bytes are identical at every base (relocation-invariant RIP-relative code).
    mem.close()
    return out


def verify_pins_live(name, game_pins, exe_pins):
    mem = Mem(name)
    bad = [p['rva'] for p in game_pins if mem.read(mem.game + p['rva'], len(p['bytes']) // 2).hex() != p['bytes']]
    bad += [('exe', p['rva']) for p in exe_pins if mem.read(mem.exe + p['rva'], len(p['bytes']) // 2).hex() != p['bytes']]
    mem.close()
    return bad


# ------------------------------------------------------------------------------------ structural proofs
def jump_table(image, table, count=6):
    return [struct.unpack_from('<I', image.data, table + 4 * i)[0] for i in range(count)]


def state_handlers(image):
    """Both jump tables of change_state, each entry resolved to the called function and its log category."""
    result = {}
    for kind, table in (('exit', 0xAB3314), ('enter', 0xAB332C)):
        rows = {}
        for index, target in enumerate(jump_table(image, table), start=1):
            call = None
            for rva, size, mnemonic, operands in image.md.disasm_lite(image.data[target:target + 64], target):
                if mnemonic == 'call' and operands.startswith('0x') and int(operands, 16) != 0x208AAA0:
                    call = int(operands, 16)
                    break
            category = message = None
            for rva, size, mnemonic, operands in image.md.disasm_lite(image.data[call:call + 0x400], call):
                if mnemonic == 'lea' and rip_of(rva, size, operands):
                    text = image.cstr(rip_of(rva, size, operands)) if TEXT[1] < rip_of(rva, size, operands) < DATA[0] else None
                    if text and text.startswith('State') and operands.startswith('rcx'):
                        category = text
                        break
                    if text and operands.startswith('rdx'):
                        message = text
            rows[index] = {'block': target, 'function': call, 'logCategory': category, 'logMessage': message}
        result[kind] = rows
    for value, name in STATE_CLASS.items():
        if result['enter'][value]['logCategory'] != name:
            raise ValueError('enter handler %d is not %s' % (value, name))
    return result


def telemetry_struct(image):
    """Key names and struct offsets of the per-player mission summary (telemetry serializer at 0xBF9810)."""
    fields, key = {}, None
    for rva, size, mnemonic, operands in image.md.disasm_lite(image.data[0xBF9810:0xBF9D1E], 0xBF9810):
        target = rip_of(rva, size, operands)
        if mnemonic == 'lea' and operands.startswith('rax') and target:
            key = image.cstr(target).strip(',"').rstrip('":')
            continue
        match = re.fullmatch(r'(?:r8d|xmm2|eax), (?:dword|byte) ptr \[rdi(?: \+ (0x[0-9a-f]+|\d+))?\]', operands)
        if key and match and mnemonic in ('mov', 'movss', 'movzx'):
            fields[int(match.group(1) or '0', 0)] = key
            key = None
    return fields


def stat_keys(image):
    """Stat-key hash -> summary-struct offset, from the aggregator at 0x630130 (main table and source loop).
    Every `cmp <key reg/entry>, KEY` followed by je/jne is resolved along its matching path (following at most two
    unconditional jumps) to the first store into the summary struct [rbx + X]."""
    lo, hi = 0x630130, 0x6308F0
    listing = list(image.md.disasm_lite(image.data[lo:hi], lo))
    at = {row[0]: n for n, row in enumerate(listing)}

    def first_store(start):
        n, jumps = at.get(start), 0
        for _ in range(16):
            if n is None or n >= len(listing):
                return None
            rva, size, mnemonic, operands = listing[n]
            store = re.fullmatch(r'(?:dword|byte) ptr \[rbx(?: \+ (0x[0-9a-f]+|\d+))?\], \w+', operands)
            if store and mnemonic in ('mov', 'movss', 'add'):
                return int(store.group(1) or '0', 0)
            if mnemonic == 'jmp' and jumps < 2:
                n, jumps = at.get(int(operands, 16)), jumps + 1
                continue
            if mnemonic == 'ret':
                return None
            n += 1
        return None

    mapping = {}
    for n, (rva, size, mnemonic, operands) in enumerate(listing[:-2]):
        compare = re.fullmatch(r'(?:eax|dword ptr \[rax\]), (0x[0-9a-f]{6,8})', operands)
        if mnemonic != 'cmp' or not compare:
            continue
        key = int(compare.group(1), 16)
        following = listing[n + 1]
        if following[2] == 'ja':
            following = listing[n + 2]
        if following[2] == 'je':
            offset = first_store(int(following[3], 16))
        elif following[2] == 'jne':
            offset = first_store(following[0] + following[1])
        else:
            continue
        if offset is not None:
            if mapping.get(key, offset) != offset:
                raise ValueError('stat key %08X maps to two summary offsets' % key)
            mapping[key] = offset
    return mapping


def sweep_facts(image):
    """One streamed pass over game.dll .text: state writers, state readers, global stores, add_stat call sites."""
    state_writes, state_reads, stores, stat_calls = [], 0, {}, []
    watch = {G_GAME, G_ENTITY_MANAGER, G_COMPONENT_WORLD, G_GAME_MODE, G_GAME_MODE_MISSION, G_PLAYER, G_AVATAR, G_SCORE,
        G_HEALTH, G_SESSION}
    recent = []
    for rva, size, mnemonic, operands in image.sweep():
        recent.append((rva, mnemonic, operands))
        if len(recent) > 16:
            recent.pop(0)
        if '+ 0xac21c]' in operands:
            if '0xac21c]' in operands.split(',')[0] and mnemonic not in ('cmp', 'test'):
                state_writes.append(rva)
            else:
                state_reads += 1
        target = rip_of(rva, size, operands)
        if target in watch and mnemonic == 'mov' and operands.startswith('qword ptr [rip'):
            stores.setdefault(target, []).append(rva)
        if mnemonic == 'call' and operands == '0x62c930':
            key = None
            for _, m, o in reversed(recent[:-1]):
                literal = re.fullmatch(r'r8d, (0x[0-9a-f]+)', o)
                if m == 'mov' and literal:
                    key = int(literal.group(1), 16)
                    break
                if m in ('call', 'ret'):
                    break
            stat_calls.append({'rva': rva, 'key': key})
    return state_writes, state_reads, stores, stat_calls


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != PROFILE_DLL_SHA or snap.executable_sha256.upper() != PROFILE_EXE_SHA:
        raise ValueError('snapshot fingerprints differ from the pinned profile')
    base, data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    image, exe = Image(data, base, TEXT), Image(exe_data, exe_base, EXE_TEXT)
    for blob, size in ((data, IMAGE_SIZE), (exe_data, EXE_IMAGE_SIZE)):
        if struct.unpack_from('<I', blob, struct.unpack_from('<I', blob, 60)[0] + 80)[0] != size:
            raise ValueError('SizeOfImage changed')

    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    exe_proofs = {group: [exe.prove(*row) for row in rows] for group, rows in EXE_PROOFS.items()}

    # GameState names (indexed by the same table change_state logs from) and the two jump tables.
    state_names = [image.cstr(image.pointer_rva(STATE_NAMES_RVA + 8 * i)) for i in range(9)]
    if state_names[:7] != ['None'] + [GAME_STATES[i] for i in range(1, 7)]:
        raise ValueError('GameState name table changed: %r' % state_names)
    handlers = state_handlers(image)
    game_modes = [image.cstr(image.pointer_rva(GAME_MODE_NAMES_RVA + 8 * i)) for i in range(len(GAME_MODE_NAMES))]
    if game_modes != GAME_MODE_NAMES:
        raise ValueError('game-mode name table changed: %r' % game_modes)
    strings = {rva: image.cstr(rva) for rva in (0x2254530, 0x2254B30, 0x2254B90, 0x2254E88, 0x224C830, 0x224C898,
        0x2247520, 0x224B2F8)}

    # Unit scene-graph accessor: exe vtable slot and method bytes.
    method = exe.pointer_rva(X_UNIT_VTABLE + 0xE8)
    if method != X_UNIT_GET_SCENE_GRAPH or exe.data[method:method + 5] != bytes.fromhex('488d4160c3'):
        raise ValueError('unit scene-graph accessor changed')
    if struct.unpack_from('<I', exe.data, X_UNIT_LUA_INDEX_BASE)[0] != 1:
        raise ValueError('Lua index base is not 1')

    # Statistics: telemetry names x aggregator keys.
    telemetry = telemetry_struct(image)
    keys = stat_keys(image)
    stats = []
    for key, offset in sorted(keys.items(), key=lambda kv: kv[1]):
        stats.append({'key': '%08X' % key, 'summaryOffset': offset, 'telemetryName': telemetry.get(offset)})
    key_names = {int(s['key'], 16): s['telemetryName'] for s in stats if s['telemetryName']}
    for required in ('dealt_kills', 'received_deaths', 'projectiles_fired', 'projectiles_hit', 'alive'):
        if required not in key_names.values():
            raise ValueError('stat key for %s not derived' % required)

    state_writes, state_reads, stores, stat_calls = sweep_facts(image)
    if sorted(state_writes) != [0xAB309C, 0xAB499B]:
        raise ValueError('unexpected writers of the game state: %s' % [hex(r) for r in state_writes])
    for call in stat_calls:
        call['name'] = key_names.get(call['key']) if call['key'] is not None else None
        call['key'] = None if call['key'] is None else '%08X' % call['key']

    all_game_pins = [p for rows in proofs.values() for p in rows]
    all_exe_pins = [p for rows in exe_proofs.values() for p in rows]
    observations, relocation = [], {}
    for name in SNAPSHOTS:
        observations.append(observe(name, keys, key_names))
        relocation[name] = verify_pins_live(name, all_game_pins, all_exe_pins)
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    chains = {
        'gameState': {'read': 'u32 at ptr(game+0x3326340)+0xAC21C', 'values': {str(k): v for k, v in GAME_STATES.items()},
            'nameTable': 'const char* at game+0x2147F30 + 8*value (0..8 observed: %s)' % state_names,
            'transitions': 'written only by change_state (0xAB309C) and game init (0xAB499B); enter handlers are the '
                'StateX classes; StateGame block (Game+0x1FA08, 0x8C810 bytes) is zeroed on every enter of 4'},
        'inMission': {'read': 'gameState == 4 and u32 ptr(game+0x33266A0)+8 == 1 (game_mode component present)'},
        'gameModeType': {'read': 'u32 ptr(game+0x33266A0)+0x40', 'names': GAME_MODE_NAMES},
        'isHost': {'read': 'u32 flags at ptr(ptr(game+0x33266A0)+0x38)+0x14 bit0 (authority over the game-mode entity); '
            'only valid while game_mode count == 1'},
        'players': {'manager': 'ptr(game+0x3326468)', 'count': '+0x84', 'ownedPartition': '+0x88 (owned instances are '
            'stored first)', 'descriptor': 'ptr at +0xE8 + 8*i -> {u64 type, u32 entity, u32 unit, u32 networkId, u32 flags}',
            'peerId': 'u64 at +0x2C8 + 0x38*i', 'lifecycleState': 'u32 at +0x2E0 + 0x38*i (2 WaitingForRespawnTimer, '
            '3 Spawned; 0/1 unnamed)', 'avatarNetworkId': 'u32 at +0x3A8 + 0x20*i (0x7FFF none)',
            'avatarEntity': 'u32 at +0x108 + 0x70*i (written by set_player_avatar)', 'entityToIndexMap': '+0xD0',
            'isLocal': 'peerId == u64 ptr(game+0x347CEF0)+0xB398'},
        'avatars': {'manager': 'ptr(game+0x3326D20)', 'count': '+0x6C', 'ownedPartition': '+0x70',
            'descriptor': 'ptr at +0x110 + 8*i', 'entityToIndexMap': '+0xF8 {u64 slots, u32 cap, u32 empty, u32 mult}'},
        'networkIdToEntity': 'em=ptr(game+0x346BF98); slot = map(em+0xF22EC8)[networkId]; entity = u32 em+0xF32F20+24*slot',
        'entityId': 'index = id & 0x3FFFFF, generation = (id >> 22) & 0xFF; engine destroy increments the generation byte; '
            'alive iff u8 ptr(ptr(exe+0x1B135B8)+0x88)[index] == generation. 0 = invalid.',
        'unitId': 'same packing; unit object = ptr(ptr(exe+0x1A100F0)+0x88)[index] iff index < u32 +0x98 and '
            'u8 ptr(+0xA0)[index] == generation; object+8 == unit id',
        'unitPosition': 'poses = ptr(object+0x88) (scene graph object+0x60, +0x28); node n matrix at poses + 64*n; '
            'translation floats at +0x30; node 0 = root. Guard: vtable[+0xE8] bytes 48 8D 41 60 C3',
        'stats': {'manager': 'ptr(game+0x3326AE0)', 'playerToIndex': 'map(+0x37D58)[player entity id] (player descriptor '
            '+8)', 'record': '+0x37D98 + 0x28*i = {u64 entries, u32 cap, u32 empty, u32 mult, pad, u64 sources}',
            'entry': '0x14 bytes {u32 key, i32 value, f32 value, u8 flag}; slot = (key*mult + probe) & (cap-1)',
            'sources': '0x40 blocks x 0x148 bytes: {u64 source id; 16 x {u32 key, i32, f32}} from +8',
            'value': 'int value = main[key] + sum(source entries with key) (get_stat 0x62CD30 with include_sources)'},
    }
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'referenceSnapshot': SNAPSHOTS[0],
        'gameDll': {'sha256': PROFILE_DLL_SHA, 'imageSize': IMAGE_SIZE, 'unpackedImageSha256': sha(data),
            'textSha256': sha(data[TEXT[0]:TEXT[1]])},
        'exe': {'sha256': PROFILE_EXE_SHA, 'imageSize': EXE_IMAGE_SIZE, 'textSha256': sha(exe_data[EXE_TEXT[0]:EXE_TEXT[1]])},
        'globals': {'game': {'Game': G_GAME, 'EntityManager': G_ENTITY_MANAGER, 'ComponentWorld': G_COMPONENT_WORLD,
            'game_mode': G_GAME_MODE, 'game_mode_mission': G_GAME_MODE_MISSION, 'player': G_PLAYER, 'avatar': G_AVATAR,
            'score': G_SCORE, 'health': G_HEALTH, 'Session': G_SESSION}, 'exe': {'UnitRegistry': X_UNIT_REGISTRY,
            'EntityManager': X_ENTITY_MANAGER}},
        'globalStoreSites': {'%X' % k: v for k, v in stores.items()},
        'chains': chains, 'gameStateNames': state_names, 'stateHandlers': handlers, 'gameModeNames': game_modes,
        'strings': {'%X' % k: v for k, v in strings.items()},
        'stateMemberWrites': state_writes, 'stateMemberOtherUses': state_reads,
        'statKeys': stats, 'telemetrySummaryFields': {'%X' % k: v for k, v in sorted(telemetry.items())},
        'addStatCallSites': stat_calls,
        'proofs': proofs, 'exeProofs': exe_proofs,
        'unitSceneGraphAccessor': {'vtableRva': X_UNIT_VTABLE, 'slot': 0xE8, 'methodRva': method, 'bytes': '488d4160c3'},
        'observations': observations, 'pinnedBytesMismatchPerSnapshot': relocation,
        'communityHints': {
            'actorList(game+0x3326D20)': 'is the "avatar" component manager (capacity 8). Live count is +0x6C; +0x70 is '
                'the authority partition size (equal to the count only when every avatar is locally owned).',
            'descriptorFlags&3==1': 'bit0 = this peer has authority over the entity (set at creation / authority gain, '
                'cleared on loss). No code tests bit1 on player/avatar descriptors; its meaning is unproven.',
            'unitRegistry(exe+0x1A100F0)': 'confirmed: count +0x98, generation bytes +0xA0, objects +0x88, id = index | '
                'generation << 22 (8-bit generation compare), object+8 = id, poses ptr(object+0x88), translation +0x30.',
            'pm+0xE8 as local player': 'only index 0 and only when +0x88 (owned partition) >= 1; prefer the peer-id test.',
        },
        'perTickReadCost': {
            'gameState': '2 reads (8 B + 4 B)', 'gameMode': '2-3 reads (manager header 0x48 B, descriptor 24 B)',
            'players': '1 read of 0x430 B (player manager) + 1 read per player descriptor (24 B) + 2 reads local peer',
            'avatars': '1 read of 0x150 B + 1 per descriptor (24 B)',
            'networkIdToEntity': '2 reads (map header 20 B, slot table cap*8 B) + 1 read (4 B) per player',
            'unitPosition': '5-6 reads (registry header, generation byte, object pointer, object id, poses, 64 B)',
            'stats': 'per player: 2 reads (record 0x28 B, table cap*0x14 = 0x500 B); +1 read 0x5200 B when source '
                'totals (kills/shots) are needed',
        },
        'unproven': [
            'Per-mission reset of the score tables: tables are zeroed when the score component is added to the player '
                'entity (0x631C00), but whether the player entity/score component is recreated for every mission (and on '
                'restart) was not observable; all snapshots are aboard the ship (distance_traveled already accumulates '
                'there).',
            'Mission restart detection: no change_state call site targets 6 directly and no mission snapshot exists; '
                'whether a restart passes through a state other than 4 or recreates the game_mode entity is unproven. '
                'The game_mode entity id (descriptor +8, generation-checked) is the candidate instance key.',
            'Mission-unique id/seed: Game+0x1FA10 is a PCG RNG state (advanced in place at 0x6C794C), not a mission id; '
                'no stable per-mission id was proven.',
            'Mission sub-phase (drop/extraction/summary): game_mode_mission fields beyond count/descriptor '
                '(+0xAA8..+0xADB) were not decoded.',
            'Host semantics: authority over the game-mode entity gates host-side respawn management (0xACC715..0xACC731); '
                'equating it with "host" is inferred, not live-verified.',
            'Whether add_stat (kills/deaths/shots) runs on every peer or only on the authority for that event; which '
                'peers see remote players\' stats.',
            'Player lifecycle values 0 and 1 have no name in the binary; replication of the lifecycle state to clients '
                'is unproven (the avatar network id IS replicated: property 0x0F27C68E at 0x6079E9/0x60C708).',
            'Stable HUD slot (0-3) per player: the manager index is not stable (owned-first partition, swap removal); '
                'no slot field was located.',
            'Whether the avatar entity is destroyed at death or only on respawn (the stuck check shows a dead avatar '
                'can remain assigned in state 3); avatar entity id change on reinforce follows from set_player_avatar '
                'writing a new entity, not from an observation.',
            'Descriptor flags bit1 meaning.',
            'GameState names 7/8 (PrepareTestLevel, PrepareDebugMission) have no enter/exit handlers; where the name '
                'table ends is not framed by a Count entry.',
            'Manager globals can be re-pointed at run time: 0xFDB080 stores a new entity manager and re-runs the '
                'global assignment (0x568230); it has no static caller (called through a runtime table), so when it '
                'runs is unknown. Runtime must re-read every global each tick and must not cache manager pointers.',
            'The engine takes a shared lock around unit_from_id (exe 0x9D8D8); Runtime reads without it, so a '
                'concurrent registry grow can yield a stale object pointer (ReadProcessMemory still cannot fault).',
        ],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'state': [o['gameState'] for o in observations], 'players': [o['players']['players'] for o in
        observations][0], 'avatarUnit': observations[0]['avatars']['avatars'][0].get('unit'),
        'stats': observations[0]['score']['players'][0]['stats']['mainEntries'], 'identity': [o['identity'] for o in
        observations], 'addStatSites': len(stat_calls)}, indent=1))


if __name__ == '__main__':
    main()
