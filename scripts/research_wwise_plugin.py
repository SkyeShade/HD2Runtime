"""The Wwise plugin's Lua bindings (docs/research/wwise-plugin-bindings-F5FEE03DCFDB.md): every module function and
constant the plugin registers, the Lua API table offsets the bindings call, and for each binding the exact argument
order, how each argument is read, defaults, guards, the native routine it reaches, the values it returns and whether
it acts on one source / playing id (local), on every source of the world (world) or on the whole sound engine
(global). Read-only and offline: the plugin DLL on disk (not encrypted) and, for the metadata layout check, the game's
own bundles. Nothing is written to the game.

The bindings check no argument types except where noted: a wrong value is read natively and pcall cannot catch it.
Every claim cites instruction RVAs (pins); the script refuses to run when a pinned instruction changed.

Evidence tags: [C] code (pinned instructions), [O] observed in the game data, [I] inference (a matching signature or
layout, not a proof).

Output: research/wwise-plugin-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

import capstone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

DLL = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\bin\plugins\wwise_pluginw64_release.dll')
OUTPUT = ROOT / 'research/wwise-plugin-F5FEE03DCFDB.json'
RESEARCH_SHA256 = 'c78a9fa4eb3e93a07fd65aec26eaa86c909470210012327ae747b5d5615410b3'
REGISTRATION = (0xFD20, 0x103EA)  # the registration function (pdata bounds)
API_HOLDER = 0x64D9C0  # every binding: mov rax, [API_HOLDER]; mov rX, [rax + 8] = the Lua API table

# Pins: group -> [(rva, instruction bytes hex, capstone asm, role)]; DATA_PINS: key -> (rva, bytes hex, role).
PINS = {
    'apiHolder': [
        (0x103F0, '488b0df1d46300', 'mov rcx, qword ptr [rip + 0x63d4f1]',
            'the registration entry: rcx = [0x64D8E8], the Lua API table, passed to the registration 0xFD20'),
        (0x103F7, '488d05e2d46300', 'lea rax, [rip + 0x63d4e2]', 'the API holder object 0x64D8E0 ...'),
        (0x103FE, '488905bbd56300', 'mov qword ptr [rip + 0x63d5bb], rax',
            '... stored at 0x64D9C0; every binding loads [0x64D9C0] and then the API table at +8'),
        (0x10405, 'e916f9ffff', 'jmp 0xfd20', 'tail call into the registration 0xFD20'),
    ],
    'registration': [
        (0xFD26, '488bd9', 'mov rbx, rcx', 'the registration keeps the Lua API table in rbx'),
        (0xFD44, 'ff5338', 'call qword ptr [rbx + 0x38]',
            'api+0x38 called with (module, key, xmm2 double): sets a module number constant (Wwise.LISTENER_0 = '
            '0)'),
        (0xFE89, 'ff13', 'call qword ptr [rbx]',
            'api+0x00 called with (module, name, function): registers a module function '
            '(WwiseWorld.add_soundscape_listener)'),
        (0x103E7, '48ffe0', 'jmp rax', 'the last registration (WwiseWorld.enabled) is a tail jump through api+0x00'),
    ],
    'apiOffsets': [
        (0xB37B, '4533c0', 'xor r8d, r8d', 'tolstring(L, 1, NULL): r8 = 0 (no length out) ...'),
        (0xB386, '41ff9128010000', 'call qword ptr [r9 + 0x128]', '... api+0x128 = tolstring'),
        (0xB476, '803c1000', 'cmp byte ptr [rax + rdx], 0', "load_bank: the api+0x128 result is strlen'd (a C string)"),
        (0xBEE2, 'ff9310010000', 'call qword ptr [rbx + 0x110]', 'api+0x110 = tonumber ...'),
        (0xBEF0, 'f2480f2cf0', 'cvttsd2si rsi, xmm0', '... its result is the double in xmm0'),
        (0xC4A8, 'ff9318010000', 'call qword ptr [rbx + 0x118]', 'api+0x118 = tointeger ...'),
        (0xC4B5, '488b742440', 'mov rsi, qword ptr [rsp + 0x40]', '... its result is the integer in eax/rax'),
        (0xAB96, '448d70ff', 'lea r14d, [rax - 1]', 'make_source: tointeger(3) - 1 (a 1-based node number)'),
        (0xCB39, 'ff9320010000', 'call qword ptr [rbx + 0x120]', 'api+0x120 = toboolean ...'),
        (0xCB46, '410f95c0', 'setne r8b', '... its int result tested (setne)'),
        (0xB2B2, '41ff9040010000', 'call qword ptr [r8 + 0x140]', 'api+0x140 = touserdata: arg 1 ...'),
        (0xB2B9, '488b08', 'mov rcx, qword ptr [rax]',
            '... the userdata block holds a pointer: [result] is the object'),
        (0xB811, 'f2480f2ac9', 'cvtsi2sd xmm1, rcx', 'position_type: an integer converted to a double ...'),
        (0xB819, 'ff9260010000', 'call qword ptr [rdx + 0x160]', '... and pushed by api+0x160 = pushnumber'),
        (0xDA8B, '8bd0', 'mov edx, eax', 'trigger_event: the u32 playing id ...'),
        (0xDA90, '41ff9668010000', 'call qword ptr [r14 + 0x168]', '... pushed by api+0x168 = pushinteger'),
        (0xC7A3, 'ba01000000', 'mov edx, 1', 'has_source: 1 ...'),
        (0xC7AF, 'ff9698010000', 'call qword ptr [rsi + 0x198]', '... pushed by api+0x198 = pushboolean'),
        (0xA6E6, 'ff9788000000', 'call qword ptr [rdi + 0x88]',
            'api+0x88 = gettop: the resolver compares it with the argument index'),
        (0xAB7F, 'ff96c8000000', 'call qword ptr [rsi + 0xc8]',
            'api+0xC8 = isnumber: tested before tointeger of the same index'),
        (0xB2D2, 'ba08000000', 'mov edx, 8', 'wwise_world: 8 bytes ...'),
        (0xB2D7, 'ff97d8010000', 'call qword ptr [rdi + 0x1d8]',
            '... api+0x1D8 = newuserdata; the WwiseWorld pointer is stored in it'),
        (0xB2E4, 'baf0d8ffff', 'mov edx, 0xffffd8f0', 'LUA_REGISTRYINDEX (-10000) ...'),
        (0xB2EF, 'ff97b8010000', 'call qword ptr [rdi + 0x1b8]',
            '... api+0x1B8 = getfield(L, REGISTRY, "WwiseWorld") (the metatable)'),
        (0xB2F5, 'bafeffffff', 'mov edx, 0xfffffffe', '-2 ...'),
        (0xB2FD, 'ff9710020000', 'call qword ptr [rdi + 0x210]', '... api+0x210 = setmetatable(L, -2)'),
        (0xA715, '41ff9068040000', 'call qword ptr [r8 + 0x468]',
            'api+0x468: a type test on the source argument (true -> the unit path)'),
        (0xA731, 'ff9728040000', 'call qword ptr [rdi + 0x428]',
            'api+0x428: returns a pointer or NULL for the unit argument ...'),
        (0xA742, '488d15bf774e00', 'lea rdx, [rip + 0x4e77bf]',
            '... NULL = "WwisePlugin: Attempted to access a deleted unit as a source."'),
        (0xA749, 'ff9760030000', 'call qword ptr [rdi + 0x360]',
            "api+0x360: (L, message [, format args]) - the plugin's message routine"),
        (0xF3C6, '488d15e3314e00', 'lea rdx, [rip + 0x4e31e3]',
            'api+0x360 also takes a format with arguments ("... Defaulting to sphere shape") ...'),
        (0xF3D6, 'c744242800000000', 'mov dword ptr [rsp + 0x28], 0',
            '... and the code continues after it (shape set to 0)'),
        (0xA78D, 'ff97c8030000', 'call qword ptr [rdi + 0x3c8]',
            'api+0x3C8: the unit node argument, read when isnumber; an int (index form unproven)'),
        (0xA7DE, 'ff9760040000', 'call qword ptr [rdi + 0x460]', 'api+0x460: a type test (true -> api+0x420) ...'),
        (0xA7F8, '41ff9020040000', 'call qword ptr [r8 + 0x420]',
            '... api+0x420 returns a pose used as a Matrix4x4 (passed where set_source_position builds a 4x4)'),
        (0xA812, 'ff9748040000', 'call qword ptr [rdi + 0x448]', 'api+0x448: a type test (true -> api+0x408) ...'),
        (0xA860, '41ff9008040000', 'call qword ptr [r8 + 0x408]', '... api+0x408 returns 3 floats (Vector3) ...'),
        (0xA86D, 'f20f1000', 'movsd xmm0, qword ptr [rax]', '... x,y read as 8 bytes ...'),
        (0xA871, '8b4008', 'mov eax, dword ptr [rax + 8]',
            '... z at +8, stored as the translation row of an identity 4x4'),
        (0xA87E, 'ff9750040000', 'call qword ptr [rdi + 0x450]',
            'api+0x450: a type test on the next argument (true -> api+0x418) ...'),
        (0xA8E1, 'ff9718040000', 'call qword ptr [rdi + 0x418]',
            '... api+0x418 returns 4 floats (a quaternion turned into the rotation rows) ...'),
        (0xA905, 'f30f10700c', 'movss xmm6, dword ptr [rax + 0xc]', '... the fourth float at +0xC'),
    ],
    'resolver': [
        (0xA6E6, 'ff9788000000', 'call qword ptr [rdi + 0x88]',
            'the source resolver 0xA6C0(world, L, index): gettop ...'),
        (0xA6F5, '4103c1', 'add eax, r9d', '... gettop + 1 - index ...'),
        (0xA6FA, '7f09', 'jg 0xa705', '... > 0: the argument exists (an explicit nil counts) ...'),
        (0xA6FC, '488b8548410000', 'mov rax, qword ptr [rbp + 0x4148]',
            '... absent: the world default source world+0x4148'),
        (0xA715, '41ff9068040000', 'call qword ptr [r8 + 0x468]', 'unit? (api+0x468)'),
        (0xA731, 'ff9728040000', 'call qword ptr [rdi + 0x428]', 'the unit (api+0x428) ...'),
        (0xA74F, 'b8ffffffff', 'mov eax, 0xffffffff', '... NULL (deleted unit): -1'),
        (0xA77D, 'ff97c8000000', 'call qword ptr [rdi + 0xc8]', 'the next argument (node) when a number ...'),
        (0xA78D, 'ff97c8030000', 'call qword ptr [rdi + 0x3c8]',
            '... read by api+0x3C8; absent = node 0 (r15d = 0 at 0xA77A)'),
        (0xA796, '80bd2841000000', 'cmp byte ptr [rbp + 0x4128], 0', 'world disabled (world+0x4128): -1'),
        (0xA7B7, 'e864990400', 'call 0x54120',
            'enabled: 0x54120(world, unit, node) finds or makes the unit node source'),
        (0xA7D1, 'c684cd6141000001', 'mov byte ptr [rbp + rcx*8 + 0x4161], 1', '... slot byte world+0x4161 set to 1'),
        (0xA7DE, 'ff9760040000', 'call qword ptr [rdi + 0x460]', 'not a unit: Matrix4x4? ...'),
        (0xA808, 'e8e3950400', 'call 0x53df0', '... a new position source 0x53DF0(world, pose, 0)'),
        (0xA812, 'ff9748040000', 'call qword ptr [rdi + 0x448]', 'Vector3? ...'),
        (0xA87E, 'ff9750040000', 'call qword ptr [rdi + 0x450]',
            '... with an optional Quaternion as the next argument ...'),
        (0xAA91, 'e85a930400', 'call 0x53df0', '... a new position source 0x53DF0(world, pose, 0)'),
        (0xAA9B, 'ff97c8000000', 'call qword ptr [rdi + 0xc8]', 'a number? ...'),
        (0xAAAA, 'ff9718010000', 'call qword ptr [rdi + 0x118]', '... tointeger: used as the source id unchecked here'),
        (0xAAB5, '488d158c744e00', 'lea rdx, [rip + 0x4e748c]',
            'anything else (also an explicit nil): "WwisePlugin: Bad Source Id parameter" ...'),
        (0xAAC2, 'b8ffffffff', 'mov eax, 0xffffffff', '... and -1'),
    ],
    'sourceTable': [
        (0x13FB3, '488d0526195600', 'lea rax, [rip + 0x561926]',
            "the manager's game-object table is the static 0x5758E0 ..."),
        (0x13FC1, '498986c8010000', 'mov qword ptr [r14 + 0x1c8], rax',
            '... at manager+0x1C8; 4096 entries of 0xD8 end at 0x64D8E0, the API holder object (0x103F7)'),
        (0xC778, '8bc1', 'mov eax, ecx', 'source ids index it by id & 0xFFF ...'),
        (0xC77F, '4869d0d8000000', 'imul rdx, rax, 0xd8', '... stride 0xD8'),
        (0x1B2D0, 'b8ffffffff', 'mov eax, 0xffffffff', 'the manager validity check 0x1B2D0: id != -1 ...'),
        (0x1B2DA, '4885d2', 'test rdx, rdx', '... id != 0 ...'),
        (0x1B2F5, '41807c004000', 'cmp byte ptr [r8 + rax + 0x40], 0', '... the slot is live (+0x40) ...'),
        (0x1B2FD, '4939540038', 'cmp qword ptr [r8 + rax + 0x38], rdx',
            '... and holds this exact id (+0x38): a stale id fails'),
        (0xCB65, '488b94ce50410000', 'mov rdx, qword ptr [rsi + rcx*8 + 0x4150]',
            'the world source table world+0x4150 (stride 0x18, index id & 0xFFF) ...'),
        (0xCB6D, '483bd5', 'cmp rdx, rbp', '... valid only when the slot holds this exact id'),
    ],
    'triggerEvent': [
        (0xD9ED, '41ff9640010000', 'call qword ptr [r14 + 0x140]', 'trigger_event: arg 1 touserdata -> WwiseWorld'),
        (0xDA04, '418d5002', 'lea edx, [r8 + 2]', 'arg 2 ...'),
        (0xDA0C, '41ff9128010000', 'call qword ptr [r9 + 0x128]', '... tolstring: the event name'),
        (0xDA13, '41b803000000', 'mov r8d, 3', 'arg 3 onward: the source resolver (index 3)'),
        (0xDA22, 'e899ccffff', 'call 0xa6c0', 'resolver call'),
        (0xDA2F, '483bf8', 'cmp rdi, rax', 'source -1: the invalid playing id [0x64D9B8] ...'),
        (0xDA34, '80bd2841000000', 'cmp byte ptr [rbp + 0x4128], 0', '... world disabled: the invalid playing id'),
        (0xDA44, '4885db', 'test rbx, rbx', 'name NULL: 0'),
        (0xDA49, '4885ff', 'test rdi, rdi', 'source 0: 0'),
        (0xDA66, 'e805700c00', 'call 0xd4a70', 'the name hashed by 0xD4A70 (FNV-1, lower-case) ...'),
        (0xDA6B, '85c0', 'test eax, eax', '... hash 0: 0'),
        (0xDA7A, 'e8311b0100', 'call 0x1f5b0', 'post 0x1F5B0(manager, event id, source, 0)'),
        (0xDA85, '8b052dff6300', 'mov eax, dword ptr [rip + 0x63ff2d]',
            'the invalid playing id: [0x64D9B8] (zero-initialised, never written)'),
        (0xDA90, '41ff9668010000', 'call qword ptr [r14 + 0x168]', 'return 1: the playing id (integer)'),
        (0xDA97, '488bd7', 'mov rdx, rdi', 'return 2: the resolved source id ...'),
        (0xDA9D, '41ff9668010000', 'call qword ptr [r14 + 0x168]', '... pushed as an integer (also when -1)'),
        (0xDAA9, 'b802000000', 'mov eax, 2', 'two results'),
    ],
    'postEvent': [
        (0x1F5CA, '4d85c0', 'test r8, r8', 'post 0x1F5B0: source 0: 0 ...'),
        (0x1F5D3, '85d2', 'test edx, edx', '... event id 0: 0 ...'),
        (0x1F5E0, '4c3bc0', 'cmp r8, rax', '... source -1: 0 ...'),
        (0x1F5FF, '807c024000', 'cmp byte ptr [rdx + rax + 0x40], 0',
            '... a stale or unknown source (manager table, live + exact id): 0'),
        (0x1F60A, '4c39440238', 'cmp qword ptr [rdx + rax + 0x38], r8', '...'),
        (0x1F639, '8b1dc5e36200', 'mov ebx, dword ptr [rip + 0x62e3c5]',
            'off the audio thread: a plugin playing id from the counter 0x64DA04 ...'),
        (0x1F70C, 'e8efb0ffff', 'call 0x1a800', '... and the post queued'),
        (0x1F790, 'e82b000000', 'call 0x1f7c0', 'on the audio thread: posted now (0x1F7C0)'),
        (0x1F7AF, '33c0', 'xor eax, eax', 'any check failed: 0'),
        (0x1F85F, '4c8d0d7aceffff', 'lea r9, [rip - 0x3186]', '0x1F7C0: the end-of-event callback 0x1C6E0 ...'),
        (0x1F86A, '41b805001000', 'mov r8d, 0x100005', '... flags 0x100005 ...'),
        (0x1F883, 'e878770b00', 'call 0xd7000',
            '... posted by 0xD7000(event id, game object, flags, callback, cookie, 0, 0, 0)'),
        (0x1F88A, '85c0', 'test eax, eax', 'a 0 result ...'),
        (0x1F88C, '0f8428010000', 'je 0x1f9ba', '... returns 0'),
        (0x1F8DD, '8b1d21e16200', 'mov ebx, dword ptr [rip + 0x62e121]',
            'otherwise the returned id is a plugin id from the counter 0x64DA04 ...'),
        (0x1F8C3, '8bd7', 'mov edx, edi', '... while the playing record is keyed by the id 0xD7000 returned (edi) ...'),
        (0x1F8CD, 'e84eecffff', 'call 0x1e520', '... 0x1E520'),
        (0x1E5E5, '488d8df8030000', 'lea rcx, [rbp + 0x3f8]', '0x1E520 stores it in the map manager+0x3F8 ...'),
        (0x1E5F1, '488d9424b8000000', 'lea rdx, [rsp + 0xb8]', '... under that id'),
        (0x1F9B8, '8bc3', 'mov eax, ebx', '0x1F7C0 returns the plugin id'),
    ],
    'playingLookup': [
        (0x1FE9A, '488d99f8030000', 'lea rbx, [rcx + 0x3f8]',
            '0x1FE90(manager, id): a lookup in the map manager+0x3F8 ...'),
        (0x1FF04, '33c0', 'xor eax, eax', '... not found: NULL'),
        (0x204D4, 'e8b7a9ffff', 'call 0x1ae90', 'stop 0x204C0: a lookup 0x1AE90 by the id ...'),
        (0x204DC, '0f8492010000', 'je 0x20674', '... not found: only a pending-list search, nothing stopped'),
    ],
    'stopEvent': [
        (0xDB72, 'ff9740010000', 'call qword ptr [rdi + 0x140]', 'stop_event: arg 1 world'),
        (0xDB83, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'arg 2 tonumber: the playing id'),
        (0xDB89, '80bb2841000000', 'cmp byte ptr [rbx + 0x4128], 0', 'world disabled: nothing'),
        (0xDB9E, '0f57d2', 'xorps xmm2, xmm2', 'fade 0 ...'),
        (0xDBA3, 'e818290100', 'call 0x204c0', '... 0x204C0(manager, id, 0)'),
        (0xDBAD, '33c0', 'xor eax, eax', 'no results'),
    ],
    'pauseResume': [
        (0xDCA3, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'pause_event: arg 2 tonumber: the playing id'),
        (0xDCA9, '80bb2841000000', 'cmp byte ptr [rbx + 0x4128], 0', 'world disabled: nothing'),
        (0xDCB7, '85ff', 'test edi, edi', 'id 0: nothing'),
        (0xDCC4, 'e8c7210100', 'call 0x1fe90', 'lookup 0x1FE90 ...'),
        (0xDCC9, '4885c0', 'test rax, rax', '... unknown id: nothing'),
        (0xDCCE, '80782100', 'cmp byte ptr [rax + 0x21], 0', '... flagged (+0x21): nothing'),
        (0xDCE9, '418d5101', 'lea edx, [r9 + 1]', 'action 1 ...'),
        (0xDCED, 'e83e5c0c00', 'call 0xd3930', '... 0xD3930(event id, 1, game object, 0, 4, playing id)'),
        (0xDE39, '418d5102', 'lea edx, [r9 + 2]', 'resume_event: action 2 ...'),
        (0xDE3D, 'e8ee5a0c00', 'call 0xd3930', '... 0xD3930'),
        (0xDE14, 'e877200100', 'call 0x1fe90', 'resume_event: the same lookup'),
    ],
    'isPlaying': [
        (0xE1D3, 'ff9610010000', 'call qword ptr [rsi + 0x110]', 'is_playing: arg 2 tonumber'),
        (0xE1D9, '80bb2841000000', 'cmp byte ptr [rbx + 0x4128], 0', 'world disabled: false'),
        (0xE1F4, 'e8971c0100', 'call 0x1fe90', 'lookup 0x1FE90 ...'),
        (0xE1FE, '0f95c2', 'setne dl', '... found = true'),
        (0xE204, 'ff9698010000', 'call qword ptr [rsi + 0x198]', 'pushboolean'),
    ],
    'elapsed': [
        (0xE2C1, 'ba02000000', 'mov edx, 2', 'get_playing_elapsed: no world read; arg 2 ...'),
        (0xE2CD, 'ff9710010000', 'call qword ptr [rdi + 0x110]', '... tonumber: the playing id'),
        (0xE2D8, '85c0', 'test eax, eax', 'id 0: pushes 0'),
        (0xE2DC, '41b001', 'mov r8b, 1', 'extrapolate = true ...'),
        (0xE2E6, 'e8656f0c00', 'call 0xd5250', '... 0xD5250(id, &ms, 1)'),
        (0xE2EB, '83f801', 'cmp eax, 1', 'result != 1 ...'),
        (0xE2F4, '83f8ff', 'cmp eax, -1', '... or ms == -1: no results'),
        (0xE304, 'ff9760010000', 'call qword ptr [rdi + 0x160]', 'pushnumber(ms)'),
        (0xD5262, 'b866000000', 'mov eax, 0x66', '0xD5250: not initialised -> 0x66 ...'),
        (0xD5272, 'b81f000000', 'mov eax, 0x1f', '... NULL out -> 0x1F'),
    ],
    'sourceParameter': [
        (0xD4B2, 'ff9740010000', 'call qword ptr [rdi + 0x140]', 'set_source_parameter: arg 1 world'),
        (0xD4C3, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'arg 2 tonumber: the source id'),
        (0xD4E3, '41ff9128010000', 'call qword ptr [r9 + 0x128]', 'arg 3 tolstring: the parameter name'),
        (0xD4F5, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'arg 4 tonumber: the value'),
        (0xD4FB, '80bb2841000000', 'cmp byte ptr [rbx + 0x4128], 0', 'world disabled: nothing'),
        (0xD505, 'f20f5af0', 'cvtsd2ss xmm6, xmm0', 'value as float'),
        (0xD515, '7430', 'je 0xd547', 'name NULL: nothing'),
        (0xD531, 'e83a750c00', 'call 0xd4a70', 'name hashed 0xD4A70'),
        (0xD542, 'e809e30000', 'call 0x1b850', '0x1B850(manager, source, parameter id, value)'),
        (0x1B87D, '483bd0', 'cmp rdx, rax', '0x1B850: source -1 ...'),
        (0x1B886, '4885d2', 'test rdx, rdx', '... 0 ...'),
        (0x1B8A5, '807c034000', 'cmp byte ptr [rbx + rax + 0x40], 0', '... not live ...'),
        (0x1B8B0, '4839540338', 'cmp qword ptr [rbx + rax + 0x38], rdx',
            '... or not this exact id: nothing (a stale id is ignored)'),
        (0x1B8F3, 'e808efffff', 'call 0x1a800', 'off the audio thread: queued'),
        (0x1BA19, '4c8bc7', 'mov r8, rdi', 'otherwise the source game object ...'),
        (0x1BA1C, 'c744242004000000', 'mov dword ptr [rsp + 0x20], 4', '... curve 4 ...'),
        (0x1BA2A, 'e841150c00', 'call 0xdcf70',
            '... 0xDCF70(parameter id, value, game object, 0, 4, 0): only this source'),
    ],
    'globalParameter': [
        (0xD659, 'ff9328010000', 'call qword ptr [rbx + 0x128]', 'set_global_parameter: arg 2 tolstring: the name'),
        (0xD66A, 'ff9310010000', 'call qword ptr [rbx + 0x110]', 'arg 3 tonumber: the value'),
        (0xD68A, '41ff9040010000', 'call qword ptr [r8 + 0x140]', 'arg 1 world: only its disabled byte is read'),
        (0xD694, '80b92841000000', 'cmp byte ptr [rcx + 0x4128], 0', 'world disabled: nothing'),
        (0xD69D, '4885f6', 'test rsi, rsi', 'name NULL: nothing'),
        (0xD6AD, 'c744242004000000', 'mov dword ptr [rsp + 0x20], 4', 'curve 4'),
        (0xD6B8, '4d8d41ff', 'lea r8, [r9 - 1]', 'game object -1 (no game object: the global value) ...'),
        (0xD6BC, 'e8dff80c00', 'call 0xdcfa0', '... 0xDCFA0(name, value, -1, 0, 4, 0)'),
        (0xDCFC0, '41bac59d1c81', 'mov r10d, 0x811c9dc5', '0xDCFA0 hashes the name itself (FNV-1 offset basis) ...'),
        (0xDCFD8, '4569d293010001', 'imul r10d, r10d, 0x1000193', '... prime 0x1000193'),
        (0xDD01E, 'e85d290000', 'call 0xdf980', '... then the id form 0xDF980'),
    ],
    'setSwitch': [
        (0xE4CB, 'ff9740010000', 'call qword ptr [rdi + 0x140]', 'set_switch: arg 1 world'),
        (0xE4E9, '41ff9128010000', 'call qword ptr [r9 + 0x128]', 'arg 2 tolstring: the switch group'),
        (0xE508, '41ff9128010000', 'call qword ptr [r9 + 0x128]', 'arg 3 tolstring: the switch'),
        (0xE51A, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'arg 4 tonumber: the source id'),
        (0xE520, '80bb2841000000', 'cmp byte ptr [rbx + 0x4128], 0', 'world disabled: nothing'),
        (0xE541, '7455', 'je 0xe598', 'group NULL: nothing'),
        (0xE546, '7450', 'je 0xe598', 'switch NULL: nothing'),
        (0xE565, 'e806650c00', 'call 0xd4a70', 'group hashed 0xD4A70'),
        (0xE581, 'e8ea640c00', 'call 0xd4a70', 'switch hashed 0xD4A70'),
        (0xE593, 'e8e8d50000', 'call 0x1bb80', '0x1BB80(manager, group id, switch id, source)'),
        (0x1BBA0, '85d2', 'test edx, edx', '0x1BB80: group id 0 ...'),
        (0x1BBA8, '4585c0', 'test r8d, r8d', '... switch id 0 ...'),
        (0x1BBCB, 'e800f7ffff', 'call 0x1b2d0', '... source not valid (0x1B2D0): nothing'),
        (0x1BC68, 'e8431b0c00', 'call 0xdd7b0', '0xDD7B0(group id, switch id, game object): only this source'),
    ],
    'postTrigger': [
        (0xE6C2, 'ff9340010000', 'call qword ptr [rbx + 0x140]', 'post_trigger: arg 1 world'),
        (0xE6D3, 'ff9310010000', 'call qword ptr [rbx + 0x110]', 'arg 2 tonumber: the source id'),
        (0xE6F3, '41ff9128010000', 'call qword ptr [r9 + 0x128]', 'arg 3 tolstring: the trigger name'),
        (0xE6FA, '80bf2841000000', 'cmp byte ptr [rdi + 0x4128], 0', 'world disabled: nothing'),
        (0xE708, '4885c0', 'test rax, rax', 'name NULL: nothing'),
        (0xE717, '85db', 'test ebx, ebx', 'source 0: nothing'),
        (0xE737, '42807c014000', 'cmp byte ptr [rcx + r8 + 0x40], 0', 'source not live ...'),
        (0xE73F, '4a39540138', 'cmp qword ptr [rcx + r8 + 0x38], rdx', '... or not this exact id: nothing'),
        (0xE749, 'e832970c00', 'call 0xd7e80', '0xD7E80(name, game object): only this source'),
        (0xD7E8F, '41b8c59d1c81', 'mov r8d, 0x811c9dc5', '0xD7E80 hashes the name itself (FNV-1)'),
    ],
    'makeSource': [
        (0xC853, '4533c9', 'xor r9d, r9d', 'make_auto_source: kind 0 ...'),
        (0xC85C, 'e86fe2ffff', 'call 0xaad0', '... 0xAAD0(world, L, 0)'),
        (0xC867, 'ff9368010000', 'call qword ptr [rbx + 0x168]', 'pushinteger: the source id'),
        (0xC903, '41b101', 'mov r9b, 1', 'make_manual_source: kind 1 ...'),
        (0xC90C, 'e8bfe1ffff', 'call 0xaad0', '... 0xAAD0(world, L, 1)'),
        (0xC917, 'ff9368010000', 'call qword ptr [rbx + 0x168]', 'pushinteger: the source id'),
        (0xAB10, 'ff9688000000', 'call qword ptr [rsi + 0x88]', '0xAAD0: gettop ...'),
        (0xAB16, 'ffc8', 'dec eax', '... minus 1 ...'),
        (0xAB1C, '488bbd48410000', 'mov rdi, qword ptr [rbp + 0x4148]', '... no arg 2: the world default source'),
        (0xAB3B, '41ff9068040000', 'call qword ptr [r8 + 0x468]', 'arg 2 unit? ...'),
        (0xAB52, 'ff9628040000', 'call qword ptr [rsi + 0x428]', '... the unit ...'),
        (0xAB70, '498bc5', 'mov rax, r13', '... NULL: -1'),
        (0xAB7F, 'ff96c8000000', 'call qword ptr [rsi + 0xc8]', 'arg 3 a number? ...'),
        (0xAB96, '448d70ff', 'lea r14d, [rax - 1]', '... node = arg 3 - 1 (1-based), else 0'),
        (0xABA3, 'e848930400', 'call 0x53ef0', 'an existing source for this unit node (0x53EF0) is reused ...'),
        (0xABD9, 'e8d2920400', 'call 0x53eb0', '... else made (0x53EB0)'),
        (0xABE3, 'ff9660040000', 'call qword ptr [rsi + 0x460]', 'arg 2 Matrix4x4? ...'),
        (0xAC03, 'ff9648040000', 'call qword ptr [rsi + 0x448]', 'arg 2 Vector3? ...'),
        (0xAC68, 'ff9650040000', 'call qword ptr [rsi + 0x450]', '... arg 3 Quaternion?'),
        (0xAE6C, 'e87f8f0400', 'call 0x53df0', 'a new position source 0x53DF0'),
        (0xAEA0, '4488a4cd61410000', 'mov byte ptr [rbp + rcx*8 + 0x4161], r12b',
            'slot byte world+0x4161 = kind (0 auto, 1 manual)'),
        (0xAEAA, '488d156f714e00', 'lea rdx, [rip + 0x4e716f]',
            'anything else: "WwisePlugin: Bad Game Source parameter", -1'),
        (0x53F13, '488b8120410000', 'mov rax, qword ptr [rcx + 0x4120]',
            "0x53EF0: the unit's id from the engine unit API (world+0x4120 +0x40, fn 1) ..."),
        (0x53F6A, '39b95c410000', 'cmp dword ptr [rcx + 0x415c], edi', '... matched with the node (slot +0xC)'),
        (0x54152, '488b8120410000', 'mov rax, qword ptr [rcx + 0x4120]', '0x54120: the same unit id ...'),
        (0x54352, '4589742408', 'mov dword ptr [r12 + 8], r14d', '... stored in the slot (+8) ...'),
        (0x54357, '418974240c', 'mov dword ptr [r12 + 0xc], esi',
            '... with the node (+0xC); the unit pointer itself is not kept'),
        (0x5438A, 'ff10', 'call qword ptr [rax]', "the unit's scene graph (unit API fn 0) ..."),
        (0x54395, '41ff10', 'call qword ptr [r8]',
            '... the node pose (world+0x4120 +0x60, fn 0) with the node index unchecked by the plugin'),
    ],
    'destroySource': [
        (0xC9E3, 'ff9318010000', 'call qword ptr [rbx + 0x118]',
            'destroy_manual_source: arg 2 tointeger: the source id'),
        (0xC9E9, 'f30f101527934e00', 'movss xmm2, dword ptr [rip + 0x4e9327]', 'fade 1.0 ...'),
        (0xC9FF, 'e8ac7b0400', 'call 0x545b0', '... 0x545B0(world, id, 1.0, 1, 1)'),
        (0x545B6, '80b92841000000', 'cmp byte ptr [rcx + 0x4128], 0', '0x545B0: world disabled: nothing'),
        (0x545F4, '483bd0', 'cmp rdx, rax', 'the world slot must hold this exact id (stale: nothing)'),
        (0x54611, '83bcf96441000000', 'cmp dword ptr [rcx + rdi*8 + 0x4164], 0',
            'slot +0x14 non-zero: only byte +0x11 cleared ...'),
        (0x54642, 'e8795afcff', 'call 0x1a0c0', '... else stopped (0x1A0C0) ...'),
        (0x54652, 'e8696bfcff', 'call 0x1b1c0', '... unregistered (0x1B1C0) ...'),
        (0x54703, '4c89a4fb50410000', 'mov qword ptr [rbx + rdi*8 + 0x4150], r12',
            '... and the slot freed (no kind check: any source of the world, the default too)'),
    ],
    'lifetimeUnlink': [
        (0xCB28, 'ff9318010000', 'call qword ptr [rbx + 0x118]', 'set_source_lifetime: arg 2 tointeger: source id'),
        (0xCB39, 'ff9320010000', 'call qword ptr [rbx + 0x120]', 'arg 3 toboolean'),
        (0xCB4F, '80be2841000000', 'cmp byte ptr [rsi + 0x4128], 0', 'world disabled: nothing'),
        (0xCB6D, '483bd5', 'cmp rdx, rbp', 'exact id only'),
        (0xCB7C, '448884ce61410000', 'mov byte ptr [rsi + rcx*8 + 0x4161], r8b', 'slot byte world+0x4161 = arg 3'),
        (0xCC53, 'ff9318010000', 'call qword ptr [rbx + 0x118]', 'unlink_source: arg 2 tointeger'),
        (0xCC5E, '483bc1', 'cmp rax, rcx', 'only -1 rejected'),
        (0xCC69, 'e882980400', 'call 0x564f0', '0x564F0(world, id)'),
        (0x56509, '4181e3ff0f0000', 'and r11d, 0xfff', '0x564F0: slot = id & 0xFFF with no id compare ...'),
        (0x56528, '66c787604100000000', 'mov word ptr [rdi + 0x4160], 0', '... its flags cleared ...'),
        (0x565D3, '48c7875841000000000000', 'mov qword ptr [rdi + 0x4158], 0',
            '... and its unit link cleared (a stale id hits whichever source holds the slot)'),
    ],
    'sourcePose': [
        (0xCE48, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'set_source_position: arg 2 tonumber: source id'),
        (0xCE8B, 'ff9708040000', 'call qword ptr [rdi + 0x408]', 'arg 3 read by api+0x408 (Vector3) with no type test'),
        (0xCE91, '80bd2841000000', 'cmp byte ptr [rbp + 0x4128], 0', 'world disabled: nothing'),
        (0xCED0, '483bd1', 'cmp rdx, rcx', 'exact id only'),
        (0xCEE1, 'e83ae50000', 'call 0x1b420', '0x1B420(manager, id, 4x4 with the translation)'),
        (0xD018, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'set_source_pose: arg 2 tonumber: source id'),
        (0xD02B, 'ff9720040000', 'call qword ptr [rdi + 0x420]',
            'arg 3 read by api+0x420 (Matrix4x4) with no type test'),
        (0xD062, '493bd0', 'cmp rdx, r8', 'exact id only'),
        (0xD071, 'e8aae30000', 'call 0x1b420', '0x1B420(manager, id, pose)'),
        (0x1B46A, '807c034000', 'cmp byte ptr [rbx + rax + 0x40], 0',
            '0x1B420 also checks the manager table (live ...'),
        (0x1B475, '4839540338', 'cmp qword ptr [rbx + rax + 0x38], rdx', '... exact id)'),
    ],
    'hasSource': [
        (0xC753, 'ff9610010000', 'call qword ptr [rsi + 0x110]', 'has_source: arg 2 tonumber'),
        (0xC759, '80bb2841000000', 'cmp byte ptr [rbx + 0x4128], 0', 'world disabled: false'),
        (0xC771, '7437', 'je 0xc7aa', '-1: false'),
        (0xC776, '7432', 'je 0xc7aa', '0: false'),
        (0xC794, '42807c024000', 'cmp byte ptr [rdx + r8 + 0x40], 0', 'not live: false'),
        (0xC79C, '4a394c0238', 'cmp qword ptr [rdx + r8 + 0x38], rcx', 'not this exact id: false'),
        (0xC7AF, 'ff9698010000', 'call qword ptr [rsi + 0x198]', 'pushboolean'),
    ],
    'sourceListeners': [
        (0xD185, 'ff9710010000', 'call qword ptr [rdi + 0x110]',
            'add_source_listeners: arg 2 tonumber: source id (the world is not used)'),
        (0xD196, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'arg 3 tonumber: listener index'),
        (0xD1C1, '478b440124', 'mov r8d, dword ptr [r9 + r8 + 0x24]', "the slot's mask read by id & 0xFFF ..."),
        (0xD1C9, 'e8226b0400', 'call 0x53cf0', '... 0x53CF0(-, source, mask)'),
        (0x53D08, '483bd0', 'cmp rdx, rax', '0x53CF0: only -1 ...'),
        (0x53D10, '745b', 'je 0x53d6d', '... and 0 rejected ...'),
        (0x53D2A, '4589440224', 'mov dword ptr [r10 + rax + 0x24], r8d',
            '... the mask written into slot id & 0xFFF with no live/exact-id check'),
    ],
    'worldAll': [
        (0xDF4E, 'e84d700400', 'call 0x54fa0', 'stop_all: 0x54FA0(world)'),
        (0x54FA9, '80b92841000000', 'cmp byte ptr [rcx + 0x4128], 0', '0x54FA0: world disabled: nothing'),
        (0x54FDE, '4c8db150410000', 'lea r14, [rcx + 0x4150]', 'every world source slot ...'),
        (0x54FE9, '41bf00100000', 'mov r15d, 0x1000', '... 4096 of them ...'),
        (0x55053, '48396908', 'cmp qword ptr [rcx + 8], rbp', '... every playing record on that source ...'),
        (0x55061, 'e87ab6fcff', 'call 0x206e0', '... stopped (0x206E0, fade 0)'),
        (0x550B4, 'e83787fcff', 'call 0x1d7f0', 'and the world default source (0x1D7F0)'),
        (0xE003, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'pause_all: arg 2 tonumber: fade seconds'),
        (0xE013, 'e8e8710400', 'call 0x55200', '0x55200(world, fade)'),
        (0x55259, 'f30f103d2f0b4a00', 'movss xmm7, dword ptr [rip + 0x4a0b2f]', '0x55200: fade x 1000 (ms) ...'),
        (0x552F1, 'ba01000000', 'mov edx, 1', '... action 1 ...'),
        (0x5530B, 'e820e60700', 'call 0xd3930', '... 0xD3930 for every playing record on every world source'),
        (0xE0E3, 'e8d8720400', 'call 0x553c0', 'resume_all: 0x553C0(world, fade)'),
        (0x554B1, 'ba02000000', 'mov edx, 2', '0x553C0: action 2 ...'),
        (0x554CB, 'e860e40700', 'call 0xd3930', '... 0xD3930'),
    ],
    'environment': [
        (0xE92A, '41ff9128010000', 'call qword ptr [r9 + 0x128]', 'set_environment: arg 2 tolstring: aux bus name'),
        (0xE93C, 'ff9310010000', 'call qword ptr [rbx + 0x110]', 'arg 3 tonumber: send value'),
        (0xE966, 'e805610c00', 'call 0xd4a70', 'name hashed 0xD4A70'),
        (0xE977, 'e8c46f0400', 'call 0x55940', '0x55940(world, id, value)'),
        (0x55A85, 'be00100000', 'mov esi, 0x1000', '0x55940: applied to all 4096 world source slots ...'),
        (0x55AA1, 'e8fab2fcff', 'call 0x20da0', '... via 0x20DA0'),
        (0xEA43, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'set_dry_environment: arg 2 tonumber'),
        (0xEA53, 'e878700400', 'call 0x55ad0', '0x55AD0(world, value): every world source'),
        (0xEACE, 'e8dd700400', 'call 0x55bb0', 'reset_aux_environment: 0x55BB0(world): every world source'),
        (0xEC3E, 'ff9718010000', 'call qword ptr [rdi + 0x118]',
            'set_environment_for_source: arg 2 tointeger: source id'),
        (0xEC5C, '41ff9128010000', 'call qword ptr [r9 + 0x128]', 'arg 3 tolstring: aux bus name'),
        (0xEC6E, 'ff9710010000', 'call qword ptr [rdi + 0x110]', 'arg 4 tonumber: send value'),
        (0xECA2, 'f30f1035d6704e00', 'movss xmm6, dword ptr [rip + 0x4e70d6]', 'clamped to [0, 16] ...'),
        (0xECE6, 'e8b5200100', 'call 0x20da0', '... 0x20DA0(manager, id, aux id, value)'),
        (0x20DB9, '25ff0f0000', 'and eax, 0xfff', '0x20DA0: slot id & 0xFFF, only 0 rejected (no live/exact-id check)'),
        (0xEE28, 'ff9718010000', 'call qword ptr [rdi + 0x118]', 'set_dry_environment_for_source: arg 2 tointeger'),
        (0xEE65, '25ff0f0000', 'and eax, 0xfff', 'slot id & 0xFFF with no live/exact-id check'),
        (0xEFC1, '81e2ff0f0000', 'and edx, 0xfff',
            'reset_environment_for_source: slot id & 0xFFF with no live/exact-id check'),
    ],
    'listenerEnable': [
        (0xC20B, 'ff9548040000', 'call qword ptr [rbp + 0x448]',
            'set_listener: arg 3 Vector3? (else Matrix4x4 at 0xC3C7)'),
        (0xC281, 'ff9518010000', 'call qword ptr [rbp + 0x118]', 'arg 2 tointeger: listener index ...'),
        (0xC2B7, '488b8cdef80c0000', 'mov rcx, qword ptr [rsi + rbx*8 + 0xcf8]',
            '... used as manager+0xCF8+8*index with no range check'),
        (0xC4BC, '09af24a20200', 'or dword ptr [rdi + 0x2a224], ebp',
            'add_default_listeners: world+0x2A224 |= 1 << arg 2'),
        (0xFC33, 'ff9720010000', 'call qword ptr [rdi + 0x120]', 'set_enabled: arg 2 toboolean ...'),
        (0xFC43, '888328410000', 'mov byte ptr [rbx + 0x4128], al',
            '... world+0x4128 = not arg 2: world+0x4128 is the disabled byte'),
        (0xFCEB, '41389028410000', 'cmp byte ptr [r8 + 0x4128], dl', 'enabled: pushes world+0x4128 == 0'),
    ],
    'wwiseModule': [
        (0xB2BC, 'e89f9c0300', 'call 0x44f60', 'wwise_world: 0x44F60(world pointer) ...'),
        (0x44FC9, '418b4008', 'mov eax, dword ptr [r8 + 8]',
            '... a world not in the map yields the end slot, unchecked'),
        (0xB39C, 'e89fb60000', 'call 0x16a40', 'set_language: 0x16A40(manager, name)'),
        (0xB47F, 'e87cbfffff', 'call 0x7400', 'load_bank: murmur64 0x7400 of the name ...'),
        (0xB49A, 'e851080100', 'call 0x1bcf0', '... 0x1BCF0(manager, -, &hash)'),
        (0x7408, '48bb95e9d15b93a7a4c6', 'movabs rbx, 0xc6a4a7935bd1e995',
            '0x7400 is MurmurHash64A (m = 0xC6A4A7935BD1E995) ...'),
        (0x7427, '4c0fafc3', 'imul r8, rbx', '... seed 0: h = len * m'),
        (0xB52C, 'e86f0a0100', 'call 0x1bfa0', 'unload_bank: 0x1BFA0(manager, name)'),
        (0xD85E, 'e80d720c00', 'call 0xd4a70', 'has_event: name hashed 0xD4A70 ...'),
        (0xD873, 'e848c9ffff', 'call 0xa1c0', '... looked up in the metadata map (0xA1C0)'),
        (0xBE0E, '41ff9128010000', 'call qword ptr [r9 + 0x128]', 'set_state: arg 2 tolstring ...'),
        (0xBE25, 'e866180d00', 'call 0xdd690', '... 0xDD690(group name, state name): no world, no game object'),
        (0xDD6A9, '41bac59d1c81', 'mov r10d, 0x811c9dc5', '0xDD690 hashes both names itself (FNV-1)'),
        (0xBEF5, 'ff9310010000', 'call qword ptr [rbx + 0x110]', 'set_panning_rule: two numbers ...'),
        (0xBF13, 'e8280e0d00', 'call 0xdcd40', '... 0xDCD40'),
    ],
    'hash': [
        (0xD4A70, '4c8bd1', 'mov r10, rcx', '0xD4A70(name): NULL -> 0'),
        (0xD4A7E, 'b8c59d1c81', 'mov eax, 0x811c9dc5', 'FNV-1 offset basis 0x811C9DC5'),
        (0xD4A98, '80e941', 'sub cl, 0x41', 'A..Z ...'),
        (0xD4A9B, '69c093010001', 'imul eax, eax, 0x1000193', '... prime 0x1000193 (multiply before xor: FNV-1) ...'),
        (0xD4AAC, '450f47c1', 'cmova r8d, r9d', '... lower-cased'),
        (0xD4AB4, '33c1', 'xor eax, ecx', 'xor'),
    ],
    'metadata': [
        (0xB75C, 'b802000000', 'mov eax, 2', 'position_type: 2 when the manager is absent'),
        (0xB784, 'e8e7920c00', 'call 0xd4a70', 'name hashed 0xD4A70'),
        (0xB798, '4183b95002000000', 'cmp dword ptr [r9 + 0x250], 0',
            'the metadata map manager+0x240 (entries of 32 bytes, key at +0) ...'),
        (0xB7F8, '488d15e1c25500', 'lea rdx, [rip + 0x55c2e1]', '... not found: the default record 0x567AD0 ...'),
        (0xB82A, '488d5114', 'lea rdx, [rcx + 0x14]', '... found: the value at entry+0x14'),
        (0xB953, 'e8e8e8ffff', 'call 0xa240', 'max_attenuation: 0xA240 ...'),
        (0xA2B1, 'f30f10440804', 'movss xmm0, dword ptr [rax + rcx + 4]', '... entry+0x4 (float)'),
        (0xA2A8, 'f30f100520d85500', 'movss xmm0, dword ptr [rip + 0x55d820]', '... default [0x567AD0]'),
        (0xBBE3, 'e8d8e6ffff', 'call 0xa2c0', 'max_duration: 0xA2C0 ...'),
        (0xA331, 'f30f10440808', 'movss xmm0, dword ptr [rax + rcx + 8]', '... entry+0x8 (float)'),
        (0xBD23, 'e818e6ffff', 'call 0xa340', 'min_duration: 0xA340 ...'),
        (0xA3B1, 'f30f1044080c', 'movss xmm0, dword ptr [rax + rcx + 0xc]', '... entry+0xC (float)'),
        (0xA3A8, 'f30f100528d75500', 'movss xmm0, dword ptr [rip + 0x55d728]', '... default [0x567AD8]'),
        (0xBA93, 'e828e9ffff', 'call 0xa3c0', 'duration_type: 0xA3C0 ...'),
        (0xA430, '428b440110', 'mov eax, dword ptr [rcx + r8 + 0x10]', '... entry+0x10 (u32)'),
        (0xA429, '8b05add65500', 'mov eax, dword ptr [rip + 0x55d6ad]', '... default [0x567ADC]'),
        (0xBA59, '0f57c9', 'xorps xmm1, xmm1', 'duration_type: 0 when the manager is absent'),
        (0xA219, '443b0408', 'cmp r8d, dword ptr [rax + rcx]', 'has_event: the key compared ...'),
        (0xA231, '0f95c0', 'setne al', '... found = true'),
        (0x169E8, '498d8f30020000', 'lea rcx, [r15 + 0x230]',
            'the loader is given the map object manager+0x230 (entries pointer at +0x10 = manager+0x240)'),
        (0x39ABF, '488b0dea3e6100', 'mov rcx, qword ptr [rip + 0x613eea]',
            'loader 0x39AA0: the resource type [0x64D9B0] ...'),
        (0x39AE4, 'ff5740', 'call qword ptr [rdi + 0x40]', '... the resource data ...'),
        (0x39AEA, '83780400', 'cmp dword ptr [rax + 4], 0', '... u32 at +4 = the byte length of the records'),
        (0x39B28, '49b89324499224499224', 'movabs r8, 0x2492492492492493',
            'length / 28 (multiply by 1/7, shift by 4): records of 28 bytes'),
        (0x39BB2, 'c744242c000080bf', 'mov dword ptr [rsp + 0x2c], 0xbf800000',
            'every entry first reset to min_duration -1.0 ...'),
        (0x39BBF, 'c744243003000000', 'mov dword ptr [rsp + 0x30], 3', '... duration_type 3 ...'),
        (0x39BC7, 'c744243402000000', 'mov dword ptr [rsp + 0x34], 2', '... position_type 2'),
        (0x39C2D, '498d7708', 'lea rsi, [r15 + 8]', 'records start at +8'),
        (0x39C4E, 'e81d040000', 'call 0x3a070', "the record's u32 at +0 is the key (0x3A070 finds or inserts) ..."),
        (0x39C40, '0f103f', 'movups xmm7, xmmword ptr [rdi]', '... its bytes +4..+0x13 ...'),
        (0x39C49, 'f20f107710', 'movsd xmm6, qword ptr [rdi + 0x10]', '... and +0x14..+0x1B ...'),
        (0x39C5B, '0f1138', 'movups xmmword ptr [rax], xmm7', '... copied to the entry value ...'),
        (0x39C5E, 'f20f117010', 'movsd qword ptr [rax + 0x10], xmm6', '...'),
        (0x39C53, '4883c61c', 'add rsi, 0x1c', 'next record (+0x1C)'),
        (0x3A175, '4883c004', 'add rax, 4', '0x3A070 returns entry+4: record offset k is entry offset k'),
    ],
    'playingIdMap': [
        (0x131F2, 'ba90cf0100', 'mov edx, 0x1cf90', 'the manager is a 0x1CF90-byte allocation ...'),
        (0x13203, 'e868080000', 'call 0x13a70', '... built by 0x13A70 ...'),
        (0x13208, '488905d9255600', 'mov qword ptr [rip + 0x5625d9], rax',
            '... and its pointer stored in the global 0x5757E8'),
        (0x1324D, '48c7059025560000000000', 'mov qword ptr [rip + 0x562590], 0', 'shutdown clears 0x5757E8 to 0'),
        (0xDB97, '488b0d4a7c5600', 'mov rcx, qword ptr [rip + 0x567c4a]', 'stop_event loads the manager from 0x5757E8'),
        (0xDCBB, '488b0d267b5600', 'mov rcx, qword ptr [rip + 0x567b26]',
            'pause_event loads the manager from 0x5757E8'),
        (0xDE0B, '488b0dd6795600', 'mov rcx, qword ptr [rip + 0x5679d6]',
            'resume_event loads the manager from 0x5757E8'),
        (0xE1EB, '488b0df6755600', 'mov rcx, qword ptr [rip + 0x5675f6]', 'is_playing loads the manager from 0x5757E8'),
        (0x14293, '488d3d46966300', 'lea rdi, [rip + 0x639646]', 'manager+0x568 = the API holder 0x64D8E0 ...'),
        (0x142D8, '4989be68050000', 'mov qword ptr [r14 + 0x568], rdi', '...'),
        (0x42F1A, 'b920000000', 'mov ecx, 0x20', 'holder+0xA0 (0x64D980) = get_api(0x20) ...'),
        (0x42F2D, '4889054caa6000', 'mov qword ptr [rip + 0x60aa4c], rax', '...'),
        (0x1F615, '488b8168050000', 'mov rax, qword ptr [rcx + 0x568]', 'post 0x1F5B0: holder ...'),
        (0x1F61C, '488b88a0000000', 'mov rcx, qword ptr [rax + 0xa0]', '... +0xA0 api ...'),
        (0x1F623, 'ff91d0000000', 'call qword ptr [rcx + 0xd0]', '... its +0xD0 test ...'),
        (0x1F62B, '0f8532010000', 'jne 0x1f763', '... true: post now (0x1F7C0); false: queue'),
        (0x1AE90, '4c8d8170ce0100', 'lea r8, [rcx + 0x1ce70]',
            'lookup 0x1AE90(manager, counter id): map M = manager+0x1CE70'),
        (0x1AE9A, '4183782000', 'cmp dword ptr [r8 + 0x20], 0', 'M+0x20 (live entries) == 0: not found'),
        (0x1AEA1, '4d8b5010', 'mov r10, qword ptr [r8 + 0x10]', 'M+0x10: the entry array (16-byte entries)'),
        (0x1AEA7, '4169c195e9d15b', 'imul eax, r9d, 0x5bd1e995', 'hash: h = key * 0x5BD1E995 (u32) ...'),
        (0x1AEB0, 'c1e918', 'shr ecx, 0x18', '... h ^= h >> 24 ...'),
        (0x1AEB3, '33c8', 'xor ecx, eax', '...'),
        (0x1AEB5, '69c195e9d15b', 'imul eax, ecx, 0x5bd1e995', '... h *= 0x5BD1E995 (u32) ...'),
        (0x1AEBB, '41f77024', 'div dword ptr [r8 + 0x24]', '... slot = h % M+0x24 (u32) ...'),
        (0x1AEC1, '4803c0', 'add rax, rax', '... entry = M+0x10 + slot * 16 ...'),
        (0x1AEC4, '41837cc20cfe', 'cmp dword ptr [r10 + rax*8 + 0xc], -2',
            '... its next (+0xC) == -2: empty bucket, not found'),
        (0x1AECC, '81faffffff7f', 'cmp edx, 0x7fffffff', '...'),
        (0x1AED9, '453b0cc2', 'cmp r9d, dword ptr [r10 + rax*8]', 'the key (+0) compared ...'),
        (0x1AEDF, '418b54c20c', 'mov edx, dword ptr [r10 + rax*8 + 0xc]', '... else follow next (+0xC) ...'),
        (0x1AEE4, '81faffffff7f', 'cmp edx, 0x7fffffff', '... until 0x7FFFFFFF (end of chain)'),
        (0x1AF37, '4883c004', 'add rax, 4', 'found: returns entry+4 ...'),
        (0x1AF3B, '48c1e104', 'shl rcx, 4', '... (16-byte stride)'),
        (0x204E2, '8b5004', 'mov edx, dword ptr [rax + 4]', 'stop: [entry+8] = the Wwise playing id ...'),
        (0x204E5, '85d2', 'test edx, edx', '... 0: not posted yet (queued/held) ...'),
        (0x204ED, '8b00', 'mov eax, dword ptr [rax]', '... [entry+4] = the state ...'),
        (0x204F1, '0f8466010000', 'je 0x2065d', '... state 0 ...'),
        (0x2066F, 'e96c000000', 'jmp 0x206e0', '... stops the Wwise id through 0x206E0'),
        (0x1ABB9, '4c8b742478', 'mov r14, qword ptr [rsp + 0x78]',
            '0x1ABA0(manager, counter, Wwise id, state, flag, lock): the optional lock ...'),
        (0x1ABC9, '4d85f6', 'test r14, r14', '... taken only when non-NULL ...'),
        (0x1ABD1, 'ff1539f44100', 'call qword ptr [rip + 0x41f439]', '... EnterCriticalSection'),
        (0x1ABD7, '488dbb70ce0100', 'lea rdi, [rbx + 0x1ce70]', 'M = manager+0x1CE70'),
        (0x1AC41, '4881c3a0ce0100', 'add rbx, 0x1cea0',
            'the reverse map manager+0x1CEA0 (Wwise id -> counter, 12-byte entries)'),
        (0x1ACB8, '44897c2478', 'mov dword ptr [rsp + 0x78], r15d', 'value = state ...'),
        (0x1ACBD, '8974247c', 'mov dword ptr [rsp + 0x7c], esi', '... and Wwise id'),
        (0x1AD8D, 'e8aed10000', 'call 0x27f40', 'find-or-insert the counter ...'),
        (0x1AD97, '488910', 'mov qword ptr [rax], rdx', '... entry+4 = state, entry+8 = Wwise id (one qword store)'),
        (0x1ADB1, '8928', 'mov dword ptr [rax], ebp',
            'reverse[Wwise id] = counter (when the id is not 0 and the state not 3)'),
        (0x1ADBB, 'ff156ff24100', 'call qword ptr [rip + 0x41f26f]', 'LeaveCriticalSection when locked'),
        (0x1F776, '48c744242800000000', 'mov qword ptr [rsp + 0x28], 0',
            "the bindings' post passes NO lock to 0x1F7C0 ..."),
        (0x1F888, '8bf8', 'mov edi, eax', '0x1F7C0: the Wwise id from 0xD7000 ...'),
        (0x1F8EE, '4032f6', 'xor sil, sil', '... state 0 ...'),
        (0x1F8FC, '48894c2428', 'mov qword ptr [rsp + 0x28], rcx', "... the caller's lock (none from a binding) ..."),
        (0x1F901, '448bc7', 'mov r8d, edi', '...'),
        (0x1F907, '440fb6ce', 'movzx r9d, sil', '...'),
        (0x1F90B, '8bd3', 'mov edx, ebx', '... counter id ...'),
        (0x1F914, 'e887b2ffff', 'call 0x1aba0', '... 0x1ABA0: M[counter] = (0, Wwise id)'),
        (0x1FA88, '40b601', 'mov sil, 1', 'held (virtual) path: state 1 ...'),
        (0x1FAB5, '33ff', 'xor edi, edi', '... with Wwise id 0'),
        (0x1F8AB, '488b8424b8000000', 'mov rax, qword ptr [rsp + 0xb8]',
            'the same lock is forwarded to 0x1E520 (the +0x3F8 insert) ...'),
        (0x1F8B6, '4889442438', 'mov qword ptr [rsp + 0x38], rax', '...'),
        (0x2228D, '451bf6', 'sbb r14d, r14d',
            'shared-instance path 0x21FF0: state 3 (joined an existing instance) or 4 (new) ...'),
        (0x223CB, '448b462c', 'mov r8d, dword ptr [rsi + 0x2c]', "... with that instance's Wwise id ..."),
        (0x223CF, '458d4e04', 'lea r9d, [r14 + 4]', '...'),
        (0x223E6, 'e8b587ffff', 'call 0x1aba0', '... 0x1ABA0'),
        (0x1F645, '4c8d8570ce0100', 'lea r8, [rbp + 0x1ce70]', 'queued path: M ...'),
        (0x1F6C2, '48c744244002000000', 'mov qword ptr [rsp + 0x40], 2', '... state 2, Wwise id 0 ...'),
        (0x1F6DC, 'e85f880000', 'call 0x27f40', '... find-or-insert ...'),
        (0x1F6E6, '488908', 'mov qword ptr [rax], rcx', '... stored WITHOUT any lock ...'),
        (0x1F70C, 'e8efb0ffff', 'call 0x1a800', '... then the command queued (0x1A800)'),
        (0x1A814, '488db100ce0100', 'lea rsi, [rcx + 0x1ce00]', '0x1A800: the queue lock manager+0x1CE00 ...'),
        (0x1A824, 'ff15e6f74100', 'call qword ptr [rip + 0x41f7e6]', '... EnterCriticalSection'),
        (0x42CB1, '488d0508140000', 'lea rax, [rip + 0x1408]',
            'the plugin update 0x440C0 is a plugin API callback ...'),
        (0x42CB8, '48890561b46000', 'mov qword ptr [rip + 0x60b461], rax', '... stored at 0x64E120'),
        (0x44197, 'e8a444fdff', 'call 0x18640', '0x440C0 calls the manager update 0x18640'),
        (0x1866C, '488d8e00ce0100', 'lea rcx, [rsi + 0x1ce00]', 'update: the queue lock ...'),
        (0x18673, 'ff1597194200', 'call qword ptr [rip + 0x421997]', '... EnterCriticalSection'),
        (0x18706, '4c89642428', 'mov qword ptr [rsp + 0x28], r12', 'queued post: no lock to 0x1F7C0 ...'),
        (0x1870B, '89442420', 'mov dword ptr [rsp + 0x20], eax', '... the pre-allocated counter id ...'),
        (0x1870F, 'e8ac700000', 'call 0x1f7c0', '... posted now: M[counter] = (state, Wwise id)'),
        (0x1871B, '448d4002', 'lea r8d, [rax + 2]', 'post failed: remove the state-2 entry ...'),
        (0x18722, 'e829280000', 'call 0x1af50', '... 0x1AF50'),
        (0x18751, 'ff15d9184200', 'call qword ptr [rip + 0x4218d9]', 'LeaveCriticalSection'),
        (0x192BC, 'ff15660d4200', 'call qword ptr [rip + 0x420d66]',
            '"Start virtual events": a local critical section ...'),
        (0x192CA, '488945e7', 'mov qword ptr [rbp - 0x19], rax', '... put in the job context ...'),
        (0x192E4, '488d15e5030000', 'lea rdx, [rip + 0x3e5]', '... job 0x196D0 ...'),
        (0x19307, '41ff92e8000000', 'call qword ptr [r10 + 0xe8]',
            '... dispatched through get_api(0x20) +0xE8 (worker jobs)'),
        (0x19707, '4889442428', 'mov qword ptr [rsp + 0x28], rax', 'job 0x196D0 passes the local lock ...'),
        (0x19712, 'e8a9600000', 'call 0x1f7c0', '... to 0x1F7C0: worker threads mutate M and +0x3F8 under it'),
        (0x19355, '41b801000000', 'mov r8d, 1', 'after the dispatch the update removes state-1 entries ...'),
        (0x19372, 'e8d91b0000', 'call 0x1af50', '... without that lock (0x1AF50): the dispatch must have completed'),
        (0x19620, 'ff151a0a4200', 'call qword ptr [rip + 0x420a1a]', 'DeleteCriticalSection'),
        (0x189E5, 'e8b6520000', 'call 0x1dca0', 'update: the end-of-event drain 0x1DCA0'),
        (0x1F85F, '4c8d0d7aceffff', 'lea r9, [rip - 0x3186]', 'posts register the callback 0x1C6E0 ...'),
        (0x1C717, '83fb01', 'cmp ebx, 1', '0x1C6E0: AK_EndOfEvent (1) ...'),
        (0x1C72F, '8b6f10', 'mov ebp, dword ptr [rdi + 0x10]', '... the playing id from the callback info (+0x10) ...'),
        (0x1C732, '488dbbf0040000', 'lea rdi, [rbx + 0x4f0]', '... lock manager+0x4F0 ...'),
        (0x1C73C, 'ff15ced84100', 'call qword ptr [rip + 0x41d8ce]', '...'),
        (0x1C742, '4881c340040000', 'add rbx, 0x440', '... appended to the list manager+0x440 ...'),
        (0x1C789, '892c90', 'mov dword ptr [rax + rdx*4], ebp', '...'),
        (0x1C78E, 'ff159cd84100', 'call qword ptr [rip + 0x41d89c]', '... unlock: the callback touches neither map'),
        (0x1DCCE, '4881c1f0040000', 'add rcx, 0x4f0', 'drain 0x1DCA0: lock manager+0x4F0 ...'),
        (0x1DCE9, 'ff1521c34100', 'call qword ptr [rip + 0x41c321]', '...'),
        (0x1DCF7, '8bb740040000', 'mov esi, dword ptr [rdi + 0x440]', '... take the list ...'),
        (0x1DF40, 'ff15eac04100', 'call qword ptr [rip + 0x41c0ea]', '... unlock ...'),
        (0x1E0E3, 'e898030100', 'call 0x2e480', '... for each ended Wwise id: erase its +0x3F8 record (0x2E480) ...'),
        (0x1E0EE, 'e8edccffff', 'call 0x1ade0', '... the counter from the reverse map (0x1ADE0) ...'),
        (0x1E0F7, '4533c0', 'xor r8d, r8d', '... and remove M[counter] if its state is 0 (0x1AF50)'),
        (0x1E0FF, 'e84cceffff', 'call 0x1af50', '...'),
        (0x1AF5A, '4c8d9170ce0100', 'lea r10, [rcx + 0x1ce70]', '0x1AF50(manager, counter, state): M'),
        (0x1AFE5, '44395cc804', 'cmp dword ptr [rax + rcx*8 + 4], r11d',
            "removes only when the entry's state equals the argument"),
        (0x1AFF0, '8b44c808', 'mov eax, dword ptr [rax + rcx*8 + 8]', 'its Wwise id ...'),
        (0x1B002, '488d8ba0ce0100', 'lea rcx, [rbx + 0x1cea0]', '... removed from the reverse map'),
        (0x1B06C, 'c7400cfeffffff', 'mov dword ptr [rax + 0xc], 0xfffffffe', 'slot marked empty (-2)'),
        (0x1B092, 'ff8b90ce0100', 'dec dword ptr [rbx + 0x1ce90]', 'M+0x20 live count decremented'),
        (0x1ADE0, '4c8d81a0ce0100', 'lea r8, [rcx + 0x1cea0]',
            '0x1ADE0(manager, Wwise id): reverse map manager+0x1CEA0 ...'),
        (0x1AE0F, '488d0c52', 'lea rcx, [rdx + rdx*2]', '... 12-byte entries ...'),
        (0x1AE29, '453b0c8a', 'cmp r9d, dword ptr [r10 + rcx*4]', '... key +0'),
        (0x1FE9A, '488d99f8030000', 'lea rbx, [rcx + 0x3f8]', '0x1FE90(manager, id): map P = manager+0x3F8'),
        (0x1FEA3, '837b2000', 'cmp dword ptr [rbx + 0x20], 0', 'P+0x20 == 0: not found'),
        (0x1FEB2, 'ba04000000', 'mov edx, 4', 'hash: murmur64 (0x7400) of the 4-byte key ...'),
        (0x1FEB7, 'e84475feff', 'call 0x7400', '...'),
        (0x1FEC2, '48c1e820', 'shr rax, 0x20', '... high 32 bits ...'),
        (0x1FEC6, 'f77324', 'div dword ptr [rbx + 0x24]', '... % P+0x24'),
        (0x1FECB, '486bc838', 'imul rcx, rax, 0x38', '0x38-byte entries'),
        (0x1FECF, '42837c0930fe', 'cmp dword ptr [rcx + r9 + 0x30], -2', 'next +0x30 == -2: empty'),
        (0x1FEE6, '423b3c09', 'cmp edi, dword ptr [rcx + r9]', 'key +0'),
        (0x1FEEC, '428b540930', 'mov edx, dword ptr [rcx + r9 + 0x30]', 'next +0x30'),
        (0x1FF4F, '4883c008', 'add rax, 8', 'returns entry+8 (the record)'),
        (0x1E558, '488bb424e8000000', 'mov rsi, qword ptr [rsp + 0xe8]',
            "0x1E520 (insert into P) takes the caller's lock ..."),
        (0x1E571, '4885f6', 'test rsi, rsi', '... when non-NULL'),
        (0x1E5E5, '488d8df8030000', 'lea rcx, [rbp + 0x3f8]', 'P = manager+0x3F8 ...'),
        (0x1E5F1, '488d9424b8000000', 'lea rdx, [rsp + 0xb8]', '... keyed by the Wwise id'),
        (0xDCD4, '4c8b00', 'mov r8, qword ptr [rax]', 'pause: record+0 = game object ...'),
        (0xDCDA, '8b4808', 'mov ecx, dword ptr [rax + 8]', '... record+8 = event id ...'),
        (0xDCDD, '897c2428', 'mov dword ptr [rsp + 0x28], edi', '... and the Lua argument as the playing id'),
    ],
    'sourceLifetime': [
        (0x4415A, 'e8a11e0100', 'call 0x56000',
            'the plugin update 0x440C0 calls the per-world update 0x56000 for every world'),
        (0x56008, '80b92841000000', 'cmp byte ptr [rcx + 0x4128], 0', '0x56000: a disabled world (world+0x4128) ...'),
        (0x56012, '0f8517020000', 'jne 0x5622f', '... frees nothing'),
        (0x5601C, '4c8d0d7dfc4900', 'lea r9, [rip + 0x49fc7d]', '"WwiseWorldInterface::mark_delete_sources" ...'),
        (0x56027, '488d15a2020000', 'lea rdx, [rip + 0x2a2]', '... job 0x562D0 ...'),
        (0x56039, 'bf00100000', 'mov edi, 0x1000', '... over all 4096 world source slots ...'),
        (0x5607F, '41ff92e8000000', 'call qword ptr [r10 + 0xe8]', '... dispatched through get_api(0x20) +0xE8'),
        (0x562F6, '483bd0', 'cmp rdx, rax', '0x562D0(slot): an unused slot (-1) is skipped'),
        (0x562FB, '807b1100', 'cmp byte ptr [rbx + 0x11], 0', 'rule 1: slot byte +0x11 == 0 ...'),
        (0x56301, '837b1400', 'cmp dword ptr [rbx + 0x14], 0', '... and slot u32 +0x14 == 0 ...'),
        (0x5630E, 'e8cd71fcff', 'call 0x1d4e0', '... and 0x1D4E0(manager, id) ...'),
        (0x56313, '85c0', 'test eax, eax', '... == 0 (no playing or queued event on it) ...'),
        (0x56317, 'c6431301', 'mov byte ptr [rbx + 0x13], 1', '... -> delete mark +0x13 = 1'),
        (0x56326, '807b1000', 'cmp byte ptr [rbx + 0x10], 0', 'rule 2: slot byte +0x10 (unit link) set ...'),
        (0x5632C, '8b4b08', 'mov ecx, dword ptr [rbx + 8]', '... the unit id (+8) ...'),
        (0x56333, '488b8720410000', 'mov rax, qword ptr [rdi + 0x4120]', '... holder (world+0x4120) ...'),
        (0x5633A, '488b5048', 'mov rdx, qword ptr [rax + 0x48]', '... +0x48 = get_api(0xE) ...'),
        (0x5633E, 'ff12', 'call qword ptr [rdx]', '... fn 0(unit id) ...'),
        (0x56340, '4885c0', 'test rax, rax', '... NULL (the unit is gone) ...'),
        (0x56345, 'c6431302', 'mov byte ptr [rbx + 0x13], 2', '... -> delete mark +0x13 = 2'),
        (0x1D52D, '418b5c302c', 'mov ebx, dword ptr [r8 + rsi + 0x2c]',
            '0x1D4E0: manager slot +0x2C (queued posts) ...'),
        (0x1D532, '41035c3028', 'add ebx, dword ptr [r8 + rsi + 0x28]', '... + manager slot +0x28 (playing events)'),
        (0x1E59F, '41ff4228', 'inc dword ptr [r10 + 0x28]', 'a post that reaches Wwise: +0x28 += 1 (0x1E520)'),
        (0x1E027, '8d42ff', 'lea eax, [rdx - 1]', 'the end-of-event drain: +0x28 -= 1 ...'),
        (0x1E02A, '4389440c28', 'mov dword ptr [r12 + r9 + 0x28], eax', '...'),
        (0x1A84B, 'ff402c', 'inc dword ptr [rax + 0x2c]', 'a queued post: +0x2C += 1 (0x1A800) ...'),
        (0x18727, '44016f2c', 'add dword ptr [rdi + 0x2c], r13d', '... -= 1 when the update drains it'),
        (0x5608E, '488d9e63410000', 'lea rbx, [rsi + 0x4163]', 'then, per slot, the mark +0x13 ...'),
        (0x560AD, '0fb603', 'movzx eax, byte ptr [rbx]', '...'),
        (0x560F2, '3c01', 'cmp al, 1', 'mark 1: no stop ...'),
        (0x56114, '3c02', 'cmp al, 2', 'mark 2 ...'),
        (0x5611B, 'e870e6ffff', 'call 0x54790', '... 0x54790(world, unit id): every source of that unit destroyed'),
        (0x56126, '4533c9', 'xor r9d, r9d', 'mark 1 (and others) ...'),
        (0x56129, 'c644242001', 'mov byte ptr [rsp + 0x20], 1', '...'),
        (0x5612E, 'e87de4ffff', 'call 0x545b0', '... 0x545B0(world, id): unregistered and the slot freed'),
        (0x53E29, 'e82260fcff', 'call 0x19e50', 'position source 0x53DF0: a manager object from 0x19E50 ...'),
        (0x53E31, '4885c0', 'test rax, rax', '... none (table full) ...'),
        (0x53E34, '7468', 'je 0x53e9e', '...'),
        (0x53EA3, 'b8ffffffff', 'mov eax, 0xffffffff', '... -> -1'),
        (0x53E4A, '488984cf58410000', 'mov qword ptr [rdi + rcx*8 + 0x4158], rax', 'new slot: +0x8 = 0 ...'),
        (0x53E52, '488984cf60410000', 'mov qword ptr [rdi + rcx*8 + 0x4160], rax',
            '... and +0x10..+0x17 = 0 (so +0x10 unit link 0, +0x11 0, +0x14 0)'),
        (0xA808, 'e8e3950400', 'call 0x53df0', 'resolver Matrix4x4: 0x53DF0 ...'),
        (0xA80D, 'e94affffff', 'jmp 0xa75c', '... returned as is (byte +0x11 stays 0)'),
        (0xAA91, 'e85a930400', 'call 0x53df0', 'resolver Vector3 [+Quaternion]: 0x53DF0 ...'),
        (0xAA96, 'e9c1fcffff', 'jmp 0xa75c', '... returned as is (byte +0x11 stays 0)'),
        (0xA7D1, 'c684cd6141000001', 'mov byte ptr [rbp + rcx*8 + 0x4161], 1',
            'resolver Unit: byte +0x11 = 1 (rule 1 never applies)'),
        (0x54342, '6641c74424100100', 'mov word ptr [r12 + 0x10], 1',
            'unit source 0x54120: +0x10 = 1 (unit link), +0x11 = 0'),
        (0xAEA0, '4488a4cd61410000', 'mov byte ptr [rbp + rcx*8 + 0x4161], r12b',
            'make_auto_source / make_manual_source: byte +0x11 = 0 / 1'),
        (0x443E4, '488d15f5946000', 'lea rdx, [rip + 0x6094f5]', 'the world is built with the API holder 0x64D8E0 ...'),
        (0x443EB, 'e890e30000', 'call 0x52780', '... 0x52780 ...'),
        (0x52863, '48899f20410000', 'mov qword ptr [rdi + 0x4120], rbx', '... stored at world+0x4120'),
        (0x42E80, 'b90e000000', 'mov ecx, 0xe', 'holder+0x48 (0x64D928) = get_api(0xE) ...'),
        (0x42E93, '4889058eaa6000', 'mov qword ptr [rip + 0x60aa8e], rax', '...'),
        (0x19E62, 'e899feffff', 'call 0x19d00', '0x19E50: a free index from 0x19D00 ...'),
        (0x19E6F, '4c3bc8', 'cmp r9, rax', '... none ...'),
        (0x19E77, '488d150a9a4d00', 'lea rdx, [rip + 0x4d9a0a]',
            '... "Too many sound source objects, skipping object `%s`" ...'),
        (0x19E9D, '33c0', 'xor eax, eax', '... returns 0'),
        (0x19D04, '448b91ec0c0000', 'mov r10d, dword ptr [rcx + 0xcec]',
            '0x19D00: the free-index count (manager+0xCEC) ...'),
        (0x19D13, 'b8ffffffff', 'mov eax, 0xffffffff', '... 0: -1 (no slot is ever overwritten) ...'),
        (0x19D47, '448b1c90', 'mov r11d, dword ptr [rax + rdx*4]',
            '... else pop the next free index (ring manager+0xCD8) ...'),
        (0x19D6C, '8981ec0c0000', 'mov dword ptr [rcx + 0xcec], eax', '... count - 1 ...'),
        (0x19D84, '41898c80500d0000', 'mov dword ptr [r8 + rax*4 + 0xd50], ecx',
            "... and bump that index's generation (manager+0xD50): a reused slot gets a new id"),
    ],
}
DATA_PINS = {
    'defaults': (0x567AD0, '0000000000000000000080bf0300000002000000',
        'the default metadata record: max_attenuation 0, max_duration 0, min_duration -1, duration 3, position 2'),
    'fade1000': (0x4F5D90, '00007a44',
        'pause_all/resume_all fade multiplier 1000.0'),
    'clamp16': (0x4F5D80, '00008041',
        'per-source aux send clamp 16.0'),
    'one': (0x4F5D18, '0000803f',
        'destroy_manual_source fade 1.0'),
}

# The Lua 5.1 C API in lua.h declaration order. In the plugin's API table every offset the bindings use from 0x88 to
# 0x210 sits at 0x68 + 8 * (its lua.h index) and its usage matches that function (API_OFFSETS) [C usage + I order].
LUA51 = ['newstate', 'close', 'newthread', 'atpanic', 'gettop', 'settop', 'pushvalue', 'remove', 'insert', 'replace',
    'checkstack', 'xmove', 'isnumber', 'isstring', 'iscfunction', 'isuserdata', 'type', 'typename', 'equal',
    'rawequal', 'lessthan', 'tonumber', 'tointeger', 'toboolean', 'tolstring', 'objlen', 'tocfunction', 'touserdata',
    'tothread', 'topointer', 'pushnil', 'pushnumber', 'pushinteger', 'pushlstring', 'pushstring', 'pushvfstring',
    'pushfstring', 'pushcclosure', 'pushboolean', 'pushlightuserdata', 'pushthread', 'gettable', 'getfield', 'rawget',
    'rawgeti', 'createtable', 'newuserdata', 'getmetatable', 'getfenv', 'settable', 'setfield', 'rawset', 'rawseti',
    'setmetatable', 'setfenv']
LUA51_BASE = 0x68

# Every API table offset the plugin's Lua code uses, what it is and the evidence ([C] usage, pinned).
API_OFFSETS = {
    0x000: ('add_module_function', 'C', '(module, name, lua_CFunction): registers WwiseWorld/Wwise functions',
        [('registration', 0xFE89)]),
    0x038: ('set_module_number', 'C', '(module, key, double in xmm2): registers the LISTENER_*/SHAPE_*/... constants',
        [('registration', 0xFD44)]),
    0x088: ('gettop', 'C', 'its result is compared with the argument index by the source resolver',
        [('resolver', 0xA6E6), ('resolver', 0xA6F5)]),
    0x0C8: ('isnumber', 'C', 'a test gating tointeger/0x3C8 of the same index', [('apiOffsets', 0xAB7F)]),
    0x110: ('tonumber', 'C', 'the result is the double in xmm0 (cvttsd2si / cvtsd2ss follow)',
        [('apiOffsets', 0xBEE2), ('apiOffsets', 0xBEF0)]),
    0x118: ('tointeger', 'C', 'the result is the integer in rax (node = result - 1 at 0xAB96)',
        [('apiOffsets', 0xC4A8), ('apiOffsets', 0xC4B5), ('apiOffsets', 0xAB96)]),
    0x120: ('toboolean', 'C', 'an int result tested for non-zero', [('apiOffsets', 0xCB39), ('apiOffsets', 0xCB46)]),
    0x128: ('tolstring', 'C', 'called with r8 = NULL; the result is a C string (strlen\'d, hashed)',
        [('apiOffsets', 0xB37B), ('apiOffsets', 0xB386), ('apiOffsets', 0xB476)]),
    0x140: ('touserdata', 'C', 'arg 1 of every WwiseWorld binding; [result] is the WwiseWorld object (no type check)',
        [('apiOffsets', 0xB2B2), ('apiOffsets', 0xB2B9)]),
    0x150: ('topointer', 'I', 'by the Lua 5.1 order; used only by the audio-input bindings '
        '(NULL -> "Null StreamSource")', []),
    0x160: ('pushnumber', 'C', 'pushes the double in xmm1', [('apiOffsets', 0xB811), ('apiOffsets', 0xB819)]),
    0x168: ('pushinteger', 'C', 'pushes the integer in rdx (playing ids, source ids)',
        [('apiOffsets', 0xDA8B), ('apiOffsets', 0xDA90)]),
    0x198: ('pushboolean', 'C', 'pushes the int in edx', [('apiOffsets', 0xC7A3), ('apiOffsets', 0xC7AF)]),
    0x1B8: ('getfield', 'C', '(L, LUA_REGISTRYINDEX = -10000, "WwiseWorld"): the metatable',
        [('apiOffsets', 0xB2E4), ('apiOffsets', 0xB2EF)]),
    0x1D8: ('newuserdata', 'C', '(L, 8): the block that holds the WwiseWorld pointer',
        [('apiOffsets', 0xB2D2), ('apiOffsets', 0xB2D7)]),
    0x210: ('setmetatable', 'C', '(L, -2)', [('apiOffsets', 0xB2F5), ('apiOffsets', 0xB2FD)]),
    0x360: ('message', 'C', '(L, format, ...): the plugin\'s error/warning text; the code continues after it '
        '("... Defaulting to sphere shape"); whether it raises a Lua error is UNPROVEN',
        [('apiOffsets', 0xA749), ('apiOffsets', 0xF3C6), ('apiOffsets', 0xF3D6)]),
    0x3C8: ('index from a number', 'C', 'an int from a number argument (the unit node in the resolver); whether it '
        'converts a 1-based index is UNPROVEN (make_*_source subtracts 1 itself at 0xAB96)', [('apiOffsets', 0xA78D)]),
    0x408: ('Vector3', 'C', 'returns a pointer to 3 floats', [('apiOffsets', 0xA860), ('apiOffsets', 0xA86D),
        ('apiOffsets', 0xA871)]),
    0x418: ('Quaternion', 'C', 'returns a pointer to 4 floats turned into rotation rows',
        [('apiOffsets', 0xA8E1), ('apiOffsets', 0xA905)]),
    0x420: ('Matrix4x4', 'C', 'returns a pose pointer passed where set_source_position passes a 4x4',
        [('apiOffsets', 0xA7F8), ('sourcePose', 0xD071), ('sourcePose', 0xCEE1)]),
    0x428: ('Unit', 'C', 'returns the unit or NULL ("Attempted to access a deleted unit as a source.")',
        [('apiOffsets', 0xA731), ('apiOffsets', 0xA742)]),
    0x448: ('is Vector3', 'C', 'the test that gates 0x408', [('apiOffsets', 0xA812)]),
    0x450: ('is Quaternion', 'C', 'the test that gates 0x418', [('apiOffsets', 0xA87E)]),
    0x460: ('is Matrix4x4', 'C', 'the test that gates 0x420', [('apiOffsets', 0xA7DE)]),
    0x468: ('is Unit', 'C', 'the test that gates 0x428', [('apiOffsets', 0xA715)]),
}
CALL_NAMES = {k: v[0] for k, v in API_OFFSETS.items() if k}


def arg(index, kind, read, becomes, absent=None):
    out = {'index': index, 'type': kind, 'read': read, 'becomes': becomes}
    if absent is not None:
        out['absent'] = absent
    return out


WORLD = arg(1, 'WwiseWorld', 'touserdata (api+0x140), [ptr]', 'the WwiseWorld object; NOT type-checked: a non-userdata '
    'is a NULL dereference')
SOURCE_ARGS = ('source resolver 0xA6C0: absent (gettop < index) = the world default source world+0x4148; Unit '
    '(+ optional node number, api+0x3C8) = the unit node\'s auto source (found or made); Matrix4x4 = a new position '
    'source; Vector3 (+ optional Quaternion) = a new position source; a number = that source id (validated later by '
    'the post); anything else, an explicit nil included = "Bad Source Id parameter" and -1')

BINDINGS = {
    'WwiseWorld.trigger_event': {
        'args': [WORLD, arg(2, 'string', 'tolstring', 'event name hashed by 0xD4A70 (FNV-1, lower-case ASCII)'),
            arg(3, 'source (see resolver)', SOURCE_ARGS, 'a source id', 'the world default source'),
            arg(4, 'number (only after a Unit)', 'isnumber + api+0x3C8', 'the unit node', 'node 0')],
        'returns': ['playing id (integer): 0 when the world is disabled, the source is -1 or 0, the name is '
            'NULL/empty, the hash is 0 or the post fails (stale/unknown source, AK returned 0); otherwise the '
            'plugin\'s own id (counter 0x64DA04, never 0)',
            'source id (integer): the resolved source, also when -1 (pushed as '
            '4294967295)'],
        'native': ['0xA6C0 resolver', '0xD4A70 hash', '0x1F5B0(manager, event id, source, 0) -> 0x1F7C0 -> 0xD7000 '
            '(event id, game object, flags 0x100005, callback 0x1C6E0, ...)'],
        'guards': ['world+0x4128 (disabled) -> invalid id [0x64D9B8] = 0', 'source validated in the manager table '
            '(live + exact id) by 0x1F5B0'],
        'scope': 'local', 'pins': ['triggerEvent', 'resolver', 'postEvent'],
        'notes': 'A Vector3/Matrix4x4 source makes a NEW position source per call, freed by the update sweep '
            'after its sounds end (sourceLifetime). A number naming a stale source '
            'posts nothing (0). An explicit nil as arg 3 is not "absent": it fails.'},
    'WwiseWorld.stop_event': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'playing id (u32)')],
        'returns': [], 'native': ['0x204C0(manager, id, fade 0)'],
        'guards': ['world+0x4128', 'unknown id: lookup 0x1AE90 fails, nothing stopped'],
        'scope': 'local', 'pins': ['stopEvent', 'playingLookup']},
    'WwiseWorld.pause_event': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'playing id (u32)')],
        'returns': [], 'native': ['0x1FE90 lookup (map manager+0x3F8)', '0xD3930(event id, 1, game object, 0, 4, '
            'id) [I: AK ExecuteActionOnEvent(Pause) by signature]'],
        'guards': ['world+0x4128', 'id 0', 'unknown id: nothing', 'record flag +0x21: nothing'],
        'scope': 'local', 'pins': ['pauseResume', 'playingLookup'],
        'notes': 'The lookup map manager+0x3F8 is keyed by the id 0xD7000 returned, while trigger_event returns the '
            'plugin counter id (postEvent pins): translate it through the counter map first (see '
            'playingIdTranslation). Same for resume_event, is_playing and get_playing_elapsed.'},
    'WwiseWorld.resume_event': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'playing id (u32)')],
        'returns': [], 'native': ['0x1FE90 lookup', '0xD3930(event id, 2, game object, 0, 4, id)'],
        'guards': ['world+0x4128', 'id 0', 'unknown id: nothing'], 'scope': 'local', 'pins': ['pauseResume']},
    'WwiseWorld.is_playing': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'playing id (u32)')],
        'returns': ['boolean: a record exists in manager+0x3F8 (false when the world is disabled)'],
        'native': ['0x1FE90'], 'guards': ['world+0x4128'], 'scope': 'local', 'pins': ['isPlaying']},
    'WwiseWorld.get_playing_elapsed': {
        'args': [arg(1, 'ignored', 'not read', 'the world is never read'),
            arg(2, 'number', 'tonumber, truncated', 'playing id (u32)')],
        'returns': ['number (ms) when 0xD5250 returns 1 and ms != -1; 0 for id 0; otherwise NO value'],
        'native': ['0xD5250(id, &ms, extrapolate 1) [I: AK GetSourcePlayPosition by signature; the post sets flag '
            '0x100000]'], 'guards': ['none of its own'], 'scope': 'local', 'pins': ['elapsed']},
    'WwiseWorld.set_source_parameter': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'source id'),
            arg(3, 'string', 'tolstring', 'parameter (RTPC) name hashed by 0xD4A70'),
            arg(4, 'number', 'tonumber', 'value (float)')],
        'returns': [], 'native': ['0x1B850(manager, source, parameter id, value) -> 0xDCF70(id, value, game object, 0, '
            '4, 0) [I: AK SetRTPCValue by id]'],
        'guards': ['world+0x4128', 'name NULL', 'source -1/0/not live/not exact id: ignored (0x1B850)'],
        'scope': 'local', 'pins': ['sourceParameter', 'sourceTable']},
    'WwiseWorld.set_global_parameter': {
        'args': [arg(1, 'WwiseWorld', 'touserdata, read last', 'only its disabled byte is read'),
            arg(2, 'string', 'tolstring', 'parameter name (hashed inside 0xDCFA0 the same way)'),
            arg(3, 'number', 'tonumber', 'value (float)')],
        'returns': [], 'native': ['0xDCFA0(name, value, game object -1, 0, 4, 0) [I: AK SetRTPCValue(name) with no '
            'game object = the global value]'], 'guards': ['world+0x4128', 'name NULL'],
        'scope': 'global', 'pins': ['globalParameter']},
    'WwiseWorld.set_switch': {
        'args': [WORLD, arg(2, 'string', 'tolstring', 'switch group name hashed by 0xD4A70'),
            arg(3, 'string', 'tolstring', 'switch name hashed by 0xD4A70'),
            arg(4, 'number', 'tonumber, truncated', 'source id')],
        'returns': [], 'native': ['0x1BB80(manager, group id, switch id, source) -> 0xDD7B0(group, switch, game '
            'object) [I: AK SetSwitch]'],
        'guards': ['world+0x4128', 'either name NULL', 'ids 0', 'source invalid (0x1B2D0: -1/0/not live/not exact)'],
        'scope': 'local', 'pins': ['setSwitch', 'sourceTable']},
    'WwiseWorld.post_trigger': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'source id'),
            arg(3, 'string', 'tolstring', 'trigger name (hashed inside 0xD7E80)')],
        'returns': [], 'native': ['0xD7E80(name, game object) [I: AK PostTrigger]'],
        'guards': ['world+0x4128', 'name NULL', 'source -1/0/not live/not exact id'],
        'scope': 'local', 'pins': ['postTrigger']},
    'WwiseWorld.has_source': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'source id')],
        'returns': ['boolean: live and exact id in the manager table; false when the world is disabled'],
        'native': [], 'guards': ['world+0x4128'], 'scope': 'local', 'pins': ['hasSource']},
    'WwiseWorld.make_auto_source': {
        'args': [WORLD, arg(2, 'Unit | Matrix4x4 | Vector3', 'gettop, then is Unit / is Matrix4x4 / is Vector3',
            'what the source follows or where it is', 'the world default source id is returned'),
            arg(3, 'number (after a Unit) | Quaternion (after a Vector3)', 'isnumber + tointeger - 1 / is Quaternion',
            'unit node (1-based) / rotation', 'node 0 / identity')],
        'returns': ['source id (integer); 4294967295 (-1) on a deleted unit, a disabled world or a bad argument'],
        'native': ['0xAAD0(world, L, kind 0)', 'unit: 0x53EF0 find (unit id + node) else 0x53EB0 -> 0x54120 make',
            'pose: 0x53DF0'],
        'guards': ['a Unit argument goes through the type test api+0x468 and the NULL check of api+0x428'],
        'scope': 'local', 'pins': ['makeSource'],
        'notes': 'An existing source of the same unit node is returned again (no second source). The plugin keeps '
            'the unit\'s engine id (slot +8) and node (+0xC), not the pointer. The node index is passed to the '
            'engine\'s node-pose call unchecked by the plugin.'},
    'WwiseWorld.make_manual_source': {
        'args': 'as make_auto_source', 'returns': ['source id (integer), as make_auto_source'],
        'native': ['0xAAD0(world, L, kind 1)'], 'guards': ['as make_auto_source'], 'scope': 'local',
        'pins': ['makeSource'], 'notes': 'kind 1 sets slot byte world+0x4161 = 1 (also on an existing auto source '
            'of the same unit node, and on the world default source when arg 2 is absent).'},
    'WwiseWorld.destroy_manual_source': {
        'args': [WORLD, arg(2, 'number', 'tointeger', 'source id')],
        'returns': [], 'native': ['0x545B0(world, id, fade 1.0, 1, 1): stop 0x1A0C0, unregister 0x1B1C0, free the '
            'slot'], 'guards': ['world+0x4128', 'world slot must hold this exact id'],
        'scope': 'local', 'pins': ['destroySource'],
        'notes': 'No kind check: it destroys any source of the world with a matching id, auto sources and the world '
            'default source included. When slot +0x14 is non-zero it only clears byte +0x11.'},
    'WwiseWorld.set_source_lifetime': {
        'args': [WORLD, arg(2, 'number', 'tointeger', 'source id'), arg(3, 'boolean', 'toboolean', 'slot byte +0x11')],
        'returns': [], 'native': [], 'guards': ['world+0x4128', '-1', 'exact id'], 'scope': 'local',
        'pins': ['lifetimeUnlink'], 'notes': 'Returns 1 Lua value count but pushes nothing (eax = 1 at 0xCB86).'},
    'WwiseWorld.unlink_source': {
        'args': [WORLD, arg(2, 'number', 'tointeger', 'source id')],
        'returns': [], 'native': ['0x564F0(world, id)'], 'guards': ['world+0x4128', 'only -1 rejected'],
        'scope': 'local', 'pins': ['lifetimeUnlink'],
        'notes': 'UNCHECKED id: the slot id & 0xFFF is cleared whatever source holds it (in bounds: 4096 slots).'},
    'WwiseWorld.set_source_position': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'source id'),
            arg(3, 'Vector3', 'api+0x408 with NO type test', 'translation of an identity 4x4')],
        'returns': [], 'native': ['0x1B420(manager, id, 4x4)'],
        'guards': ['world+0x4128', 'world slot exact id', 'manager table live + exact id'],
        'scope': 'local', 'pins': ['sourcePose'],
        'notes': 'Arg 3 is read before any check; what api+0x408 does with a non-Vector3 is UNPROVEN.'},
    'WwiseWorld.set_source_pose': {
        'args': [WORLD, arg(2, 'number', 'tonumber, truncated', 'source id'),
            arg(3, 'Matrix4x4', 'api+0x420 with NO type test', 'the pose')],
        'returns': [], 'native': ['0x1B420(manager, id, pose)'],
        'guards': ['world+0x4128', 'world slot exact id', 'manager table live + exact id'],
        'scope': 'local', 'pins': ['sourcePose'],
        'notes': 'Arg 3 is read before any check; what api+0x420 does with a non-Matrix4x4 is UNPROVEN.'},
    'WwiseWorld.add_source_listeners': {
        'args': [arg(1, 'ignored', 'touserdata result unused', '-'), arg(2, 'number', 'tonumber', 'source id'),
            arg(3, 'number', 'tonumber', 'listener index (bit)')],
        'returns': [], 'native': ['0x53CF0(-, source, mask)'], 'guards': ['only -1 and 0 rejected'],
        'scope': 'local', 'pins': ['sourceListeners'],
        'notes': 'UNCHECKED id: the mask is written into slot id & 0xFFF of the manager table.'},
    'WwiseWorld.remove_source_listeners': {
        'args': 'as add_source_listeners', 'returns': [], 'native': ['0x53CF0'],
        'guards': ['only -1 and 0 rejected'], 'scope': 'local', 'pins': ['sourceListeners'],
        'notes': 'UNCHECKED id, as add_source_listeners.'},
    'WwiseWorld.stop_all': {
        'args': [WORLD], 'returns': [], 'native': ['0x54FA0(world): every playing record on each of the 4096 world '
            'source slots stopped (0x206E0), then the world default source (0x1D7F0)'],
        'guards': ['world+0x4128'], 'scope': 'world', 'pins': ['worldAll']},
    'WwiseWorld.pause_all': {
        'args': [WORLD, arg(2, 'number', 'tonumber', 'fade seconds (x1000 = ms)', '0')],
        'returns': [], 'native': ['0x55200(world, fade): 0xD3930 action 1 for every playing record of the world'],
        'guards': ['world+0x4128'], 'scope': 'world', 'pins': ['worldAll']},
    'WwiseWorld.resume_all': {
        'args': [WORLD, arg(2, 'number', 'tonumber', 'fade seconds (x1000 = ms)', '0')],
        'returns': [], 'native': ['0x553C0(world, fade): action 2'], 'guards': ['world+0x4128'],
        'scope': 'world', 'pins': ['worldAll']},
    'WwiseWorld.set_environment': {
        'args': [WORLD, arg(2, 'string', 'tolstring', 'aux bus name hashed by 0xD4A70'),
            arg(3, 'number', 'tonumber', 'send value (float)')],
        'returns': [], 'native': ['0x55940(world, aux id, value): world list + every world source (0x20DA0)'],
        'guards': ['world+0x4128'], 'scope': 'world', 'pins': ['environment']},
    'WwiseWorld.set_dry_environment': {
        'args': [WORLD, arg(2, 'number', 'tonumber', 'dry level (float)')],
        'returns': [], 'native': ['0x55AD0(world, value): every world source'], 'guards': ['world+0x4128'],
        'scope': 'world', 'pins': ['environment']},
    'WwiseWorld.reset_aux_environment': {
        'args': [WORLD], 'returns': [], 'native': ['0x55BB0(world): every world source'],
        'guards': ['world+0x4128'], 'scope': 'world', 'pins': ['environment']},
    'WwiseWorld.set_environment_for_source': {
        'args': [WORLD, arg(2, 'number', 'tointeger', 'source id'),
            arg(3, 'string', 'tolstring', 'aux bus name hashed by 0xD4A70'),
            arg(4, 'number', 'tonumber', 'send value clamped to [0, 16]')],
        'returns': [], 'native': ['0x20DA0(manager, id, aux id, value)'], 'guards': ['world+0x4128', 'id 0'],
        'scope': 'local', 'pins': ['environment'],
        'notes': 'UNCHECKED id (slot id & 0xFFF, no live/exact-id check).'},
    'WwiseWorld.set_dry_environment_for_source': {
        'args': [WORLD, arg(2, 'number', 'tointeger', 'source id'), arg(3, 'number', 'tonumber', 'dry level clamped '
            'to [0, 16]')], 'returns': [], 'native': ['0x20F40(manager, id)'], 'guards': ['world+0x4128', 'id 0'],
        'scope': 'local', 'pins': ['environment'], 'notes': 'UNCHECKED id.'},
    'WwiseWorld.reset_environment_for_source': {
        'args': [WORLD, arg(2, 'number', 'tointeger', 'source id')], 'returns': [],
        'native': ['0x20F40(manager, id)'], 'guards': ['world+0x4128', 'id 0'], 'scope': 'local',
        'pins': ['environment'], 'notes': 'UNCHECKED id.'},
    'WwiseWorld.set_listener': {
        'args': [WORLD, arg(2, 'number', 'tointeger', 'listener index (Wwise.LISTENER_0..7)'),
            arg(3, 'Vector3 | Matrix4x4', 'is Vector3 else Matrix4x4 (no test)', 'listener position / pose')],
        'returns': [], 'native': ['0x19790 / 0xDCD90 / 0x4C900 (vector path), 0x52D80 (matrix path)'],
        'guards': ['world+0x4128 (vector path)'], 'scope': 'global', 'pins': ['listenerEnable'],
        'notes': 'The index addresses the manager listener game objects manager+0xCF8 + 8 * index with no range '
            'check: the listeners belong to the manager, not to the world.'},
    'WwiseWorld.add_default_listeners': {
        'args': [WORLD, arg(2, 'number', 'tointeger', 'listener bit')], 'returns': [], 'native': [],
        'guards': [], 'scope': 'world', 'pins': ['listenerEnable']},
    'WwiseWorld.remove_default_listeners': {
        'args': [WORLD, arg(2, 'number', 'tonumber', 'listener bit')], 'returns': [], 'native': [],
        'guards': [], 'scope': 'world', 'pins': []},
    'WwiseWorld.set_enabled': {
        'args': [WORLD, arg(2, 'boolean', 'toboolean', 'world+0x4128 = not arg 2')], 'returns': [], 'native': [],
        'guards': [], 'scope': 'world', 'pins': ['listenerEnable'],
        'notes': 'world+0x4128 is the byte every binding tests: non-zero = disabled.'},
    'WwiseWorld.enabled': {
        'args': [WORLD], 'returns': ['boolean: world+0x4128 == 0'], 'native': [], 'guards': [], 'scope': 'read',
        'pins': ['listenerEnable']},
    'Wwise.wwise_world': {
        'args': [arg(1, 'World', 'touserdata, [ptr]', 'the engine world pointer')],
        'returns': ['WwiseWorld userdata (metatable "WwiseWorld")'], 'native': ['0x44F60(world)'], 'guards': [],
        'scope': 'read', 'pins': ['wwiseModule'],
        'notes': 'A world missing from the plugin\'s map yields its end slot unchecked (0x44FC9).'},
    'Wwise.set_language': {
        'args': [arg(1, 'string', 'tolstring', 'language name')], 'returns': [], 'native': ['0x16A40(manager, name)'],
        'guards': ['manager present'], 'scope': 'global', 'pins': ['wwiseModule']},
    'Wwise.load_bank': {
        'args': [arg(1, 'string', 'tolstring', 'bank resource name, murmur64 (0x7400)')], 'returns': [],
        'native': ['0x1BCF0(manager, -, &hash)'], 'guards': ['manager present', 'name NULL'], 'scope': 'global',
        'pins': ['wwiseModule']},
    'Wwise.unload_bank': {
        'args': [arg(1, 'string', 'tolstring', 'bank name')], 'returns': [], 'native': ['0x1BFA0(manager, name)'],
        'guards': ['manager present'], 'scope': 'global', 'pins': ['wwiseModule']},
    'Wwise.has_event': {
        'args': [arg(1, 'string', 'tolstring', 'event name hashed by 0xD4A70')],
        'returns': ['boolean: the event id is a key of the metadata map'], 'native': ['0xA1C0'],
        'guards': ['manager present'], 'scope': 'read', 'pins': ['wwiseModule', 'metadata']},
    'Wwise.set_state': {
        'args': [arg(1, 'string', 'tolstring', 'state group name'), arg(2, 'string', 'tolstring', 'state name')],
        'returns': [], 'native': ['0xDD690(group, state): both hashed inside (FNV-1) [I: AK SetState(name, name)]'],
        'guards': ['either name NULL'], 'scope': 'global', 'pins': ['wwiseModule'],
        'notes': 'No world and no game object: a state is engine-wide.'},
    'Wwise.set_panning_rule': {
        'args': [arg(1, 'number', 'tonumber', 'rule (0 speakers, 1 headphones; anything else 0)'),
            arg(2, 'number', 'tonumber', 'device/output (u32)')], 'returns': [], 'native': ['0xDCD40'],
        'guards': [], 'scope': 'global', 'pins': ['wwiseModule']},
    'Wwise.position_type': {
        'args': [arg(1, 'string', 'tolstring', 'event name hashed by 0xD4A70')],
        'returns': ['number: metadata +0x14 (0 = WWISE_3D_SOUND, 1 = WWISE_2D_SOUND); 2 (WWISE_INVALID_SOUND) when '
            'unknown or no manager'], 'native': [], 'guards': [], 'scope': 'read', 'pins': ['metadata']},
    'Wwise.max_attenuation': {
        'args': [arg(1, 'string', 'tolstring', 'event name')],
        'returns': ['number: metadata +0x4 (float); 0 when unknown'], 'native': ['0xA240'], 'guards': [],
        'scope': 'read', 'pins': ['metadata']},
    'Wwise.duration_type': {
        'args': [arg(1, 'string', 'tolstring', 'event name')],
        'returns': ['number: metadata +0x10 (0 ONE_SHOT, 1 INFINITE, 2 UNSUPPORTED); 3 when unknown; 0 when no '
            'manager'], 'native': ['0xA3C0'], 'guards': [], 'scope': 'read', 'pins': ['metadata']},
    'Wwise.max_duration': {
        'args': [arg(1, 'string', 'tolstring', 'event name')],
        'returns': ['number: metadata +0x8 (float, seconds [I]); 0 when unknown'], 'native': ['0xA2C0'],
        'guards': [], 'scope': 'read', 'pins': ['metadata']},
    'Wwise.min_duration': {
        'args': [arg(1, 'string', 'tolstring', 'event name')],
        'returns': ['number: metadata +0xC (float); -1 when unknown, 0 when no manager'], 'native': ['0xA340'],
        'guards': [], 'scope': 'read', 'pins': ['metadata']},
}
UNANALYSED = {'WwiseWorld.add_soundscape_listener', 'WwiseWorld.remove_soundscape_listener',
    'WwiseWorld.add_soundscape_unit_source', 'WwiseWorld.remove_soundscape_source',
    'WwiseWorld.trigger_audio_input_event', 'WwiseWorld.trigger_audio_input_sound',
    'WwiseWorld.stop_audio_input_sound'}

METADATA_RECORD = [
    (0x00, 'u32', 'event id (the map key; FNV-1 of the event name)', '0x39C4E / 0xA219'),
    (0x04, 'f32', 'max_attenuation', '0xA2B1'),
    (0x08, 'f32', 'max_duration', '0xA331'),
    (0x0C, 'f32', 'min_duration', '0xA3B1'),
    (0x10, 'u32', 'duration_type: 0 WWISE_DURATION_ONE_SHOT, 1 WWISE_DURATION_INFINITE, 2 WWISE_DURATION_UNSUPPORTED',
        '0xA430'),
    (0x14, 'u32', 'position_type: 0 WWISE_3D_SOUND, 1 WWISE_2D_SOUND (2 WWISE_INVALID_SOUND = unknown)', '0xB82A'),
    (0x18, 'u32', 'copied into the map; read by no binding (meaning UNPROVEN)', '0x39C49'),
]


class Image:
    def __init__(self, path):
        self.raw = path.read_bytes()
        pe = struct.unpack_from('<I', self.raw, 0x3C)[0]
        count = struct.unpack_from('<H', self.raw, pe + 6)[0]
        optional = struct.unpack_from('<H', self.raw, pe + 20)[0]
        self.base = struct.unpack_from('<Q', self.raw, pe + 24 + 24)[0]
        self.sections = []
        for i in range(count):
            o = pe + 24 + optional + 40 * i
            name = self.raw[o:o + 8].rstrip(b'\0').decode()
            vsize, va, rsize, rptr = struct.unpack_from('<IIII', self.raw, o + 8)
            self.sections.append({'name': name, 'rva': va, 'virtualSize': vsize, 'rawSize': rsize, 'rawOffset': rptr})
        self.data = bytearray(max(s['rva'] + max(s['virtualSize'], s['rawSize']) for s in self.sections))
        for s in self.sections:
            self.data[s['rva']:s['rva'] + s['rawSize']] = self.raw[s['rawOffset']:s['rawOffset'] + s['rawSize']]
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def section(self, name):
        return next(s for s in self.sections if s['name'] == name)

    def insn(self, rva):
        return next(self.md.disasm(bytes(self.data[rva:rva + 16]), rva))

    def cstr(self, rva):
        return bytes(self.data[rva:self.data.index(b'\0', rva)]).decode('ascii')

    def pdata(self):
        p = self.section('.pdata')
        out = []
        for i in range(p['virtualSize'] // 12):
            b, e, _ = struct.unpack_from('<III', self.data, p['rva'] + 12 * i)
            if b == 0:
                break
            out.append((b, e))
        return out


def rip_target(insn):
    m = re.search(r'\[rip ([+-]) 0x([0-9a-f]+)\]', insn.op_str)
    if not m:
        return None
    return insn.address + insn.size + int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)


def prove(img):
    """Every pin: same bytes and same disassembly, else raise."""
    out, bad = {}, []
    for group, pins in PINS.items():
        out[group] = []
        for rva, hexbytes, asm, role in pins:
            insn = img.insn(rva)
            text = ('%s %s' % (insn.mnemonic, insn.op_str)).strip()
            got = bytes(insn.bytes).hex()
            if got != hexbytes or text != asm:
                bad.append('%s 0x%X: %s %r != %s %r' % (group, rva, got, text, hexbytes, asm))
                continue
            pin = {'rva': rva, 'bytes': got, 'asm': asm, 'role': role}
            target = rip_target(insn)
            if target is not None:
                pin['ripTarget'] = target
            out[group].append(pin)
    for key, (rva, hexbytes, role) in DATA_PINS.items():
        got = bytes(img.data[rva:rva + len(hexbytes) // 2]).hex()
        if got != hexbytes:
            bad.append('data %s 0x%X: %s != %s' % (key, rva, got, hexbytes))
    if bad:
        raise RuntimeError('the Wwise plugin changed at pinned RVAs:\n' + '\n'.join(bad))
    out['data'] = [{'key': k, 'rva': rva, 'bytes': h, 'role': role} for k, (rva, h, role) in DATA_PINS.items()]
    return out


def registration(img):
    """Emulate the registration function: the module/name/function (api+0x00) and module/key/number (api+0x38)
    calls, from the lea of the strings and the function and the xmm2 double."""
    regs, xmm, entries = {}, {}, []
    start, end = REGISTRATION
    for insn in img.md.disasm(bytes(img.data[start:end]), start):
        target = rip_target(insn)
        dst = insn.op_str.split(',')[0]
        if target is not None and insn.mnemonic == 'lea':
            regs[dst] = target
        elif target is not None and insn.mnemonic == 'movsd' and dst.startswith('xmm'):
            xmm[dst] = struct.unpack_from('<d', img.data, target)[0]
        elif insn.mnemonic == 'xorps':
            xmm[dst] = 0.0
        elif insn.mnemonic == 'movaps' and 'ptr' not in insn.op_str:
            xmm[dst] = xmm.get(insn.op_str.split(', ')[1])
        if insn.mnemonic in ('call', 'jmp') and insn.op_str in ('qword ptr [rbx]', 'qword ptr [rbx + 0x38]', 'rax'):
            module, name = img.cstr(regs['rcx']), img.cstr(regs['rdx'])
            if insn.op_str.endswith('0x38]'):
                entries.append({'kind': 'number', 'module': module, 'name': name, 'value': xmm['xmm2'],
                    'site': insn.address})
            else:
                entries.append({'kind': 'function', 'module': module, 'name': name, 'rva': regs['r8'],
                    'site': insn.address})
    return entries


def function_code(img, start, span=0x400):
    """Recursive descent from start; follows branches inside [start, start + span); stops at ret / int3 /
    an outside jmp. Returns the instructions in address order."""
    seen, todo, out = set(), [start], {}
    while todo:
        a = todo.pop()
        while a not in seen and start <= a < start + span:
            insn = img.insn(a)
            seen.add(a)
            out[a] = insn
            if insn.mnemonic in ('ret', 'int3'):
                break
            if insn.mnemonic.startswith('j'):
                try:
                    t = int(insn.op_str, 16)
                except ValueError:
                    break
                if insn.mnemonic == 'jmp':
                    if not start <= t < start + span:
                        break
                    a = t
                    continue
                todo.append(t)
            a += insn.size
    return [out[k] for k in sorted(out)]


REG64 = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp'}
REG64.update({'r%dd' % i: 'r%d' % i for i in range(8, 16)})


def api_calls(img, start):
    """The API-table calls of one binding with the argument index (edx) where it is a constant."""
    known, out = {}, []
    for insn in function_code(img, start):
        ops = insn.op_str.split(', ')
        dst = REG64.get(ops[0], ops[0]) if ops else None
        if insn.mnemonic == 'mov' and len(ops) == 2 and re.fullmatch(r'0x[0-9a-f]+|\d+', ops[1]):
            known[dst] = int(ops[1], 0)
        elif insn.mnemonic == 'xor' and len(ops) == 2 and ops[0] == ops[1]:
            known[dst] = 0
        elif insn.mnemonic == 'mov' and len(ops) == 2 and REG64.get(ops[1], ops[1]) in known:
            known[dst] = known[REG64.get(ops[1], ops[1])]
        elif insn.mnemonic == 'lea' and len(ops) == 2:
            m = re.fullmatch(r'\[(\w+) ([+-]) (0x[0-9a-f]+|\d+)\]', ops[1])
            if m and m.group(1) in known:
                known[dst] = known[m.group(1)] + int(m.group(3), 0) * (1 if m.group(2) == '+' else -1)
            else:
                known.pop(dst, None)
        m = re.fullmatch(r'qword ptr \[(r\w+) \+ (0x[0-9a-f]+)\]', insn.op_str)
        if insn.mnemonic in ('call', 'jmp') and m and int(m.group(2), 16) in CALL_NAMES:
            off = int(m.group(2), 16)
            entry = {'site': insn.address, 'offset': off, 'api': CALL_NAMES[off]}
            if 'rdx' in known and off not in (0x160, 0x168, 0x198):
                v = known['rdx'] & 0xFFFFFFFF
                entry['arg'] = v - 0x100000000 if v & 0x80000000 else v
            out.append(entry)
        if insn.mnemonic == 'call':
            for r in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                known.pop(r, None)
    return out


def holder_checks(img):
    """The API holder, the source table bounds and the invalid playing id [C]."""
    data = img.section('.data')
    lea_holder = img.insn(0x103F7)
    lea_table = img.insn(0x13FB3)
    holder, table = rip_target(lea_holder), rip_target(lea_table)
    assert holder == 0x64D8E0 and rip_target(img.insn(0x103FE)) == API_HOLDER
    assert table + 0x1000 * 0xD8 == holder, 'the game-object table does not end at the API holder'
    invalid = rip_target(img.insn(0xDA85))
    raw_end = data['rva'] + data['rawSize']
    assert invalid >= raw_end, 'the invalid playing id is not zero-initialised'
    writers = []
    for b, e in img.pdata():
        if b >= 0x80000:
            continue
        for insn in img.md.disasm(bytes(img.data[b:e]), b):
            if rip_target(insn) == invalid and insn.op_str.startswith('dword ptr [rip'):
                writers.append(insn.address)
    assert not writers, 'the invalid playing id is written at %s' % writers
    return {'apiHolder': {'object': holder, 'pointer': API_HOLDER, 'apiTableField': holder + 8},
        'managerGameObjectTable': {'rva': table, 'entries': 0x1000, 'stride': 0xD8, 'end': table + 0x1000 * 0xD8,
            'note': 'ends exactly at the API holder object: index id & 0xFFF is always in bounds [C]'},
        'invalidPlayingId': {'rva': invalid, 'value': 0, 'note': 'in .data beyond its raw size (zero-initialised); '
            'no instruction of the plugin code (< 0x80000) writes it [C]', 'dataRawEnd': raw_end}}


def metadata_data():
    """[O] the wwise_metadata resources of the install, parsed with the layout the loader proves."""
    import hd2_game_data as gdata
    rtype = gdata.murmur64(b'wwise_metadata')
    data = gdata.Data()
    found = {}
    for archive, rname, t, main, stream, gpu in data.tables():
        if t == rtype and rname not in found:
            found[rname] = (archive, main)
    resources, stats = [], collections.defaultdict(collections.Counter)
    examples = {}
    for rname in sorted(found):
        archive, main = found[rname]
        raw = data.read(archive, main)
        version, length = struct.unpack_from('<II', raw, 0)
        assert length % 28 == 0 and 8 + length == len(raw), 'a wwise_metadata resource does not fit the layout'
        resources.append({'name': '%016x' % rname, 'version': version, 'records': length // 28})
        for i in range(length // 28):
            eid, att, mx, mn, dt, pt, last = struct.unpack_from('<IfffIII', raw, 8 + 28 * i)
            stats['duration_type'][dt] += 1
            stats['position_type'][pt] += 1
            stats['field_0x18'][last] += 1
            key = struct.pack('<I', eid).hex()  # as the bytes appear in the file
            if key in ('b6161be0', 'bd830ab4') and key not in examples:
                examples[key] = {'eventId': '0x%08X' % eid, 'resource': '%016x' % rname, 'max_attenuation': att,
                    'max_duration': round(mx, 6),
                    'min_duration': round(mn, 6), 'duration_type': dt, 'position_type': pt, 'field_0x18': last}
    return {'type': '%016x' % rtype, 'resources': resources,
        'records': sum(r['records'] for r in resources),
        'valueCounts': {k: {str(a): b for a, b in sorted(v.items())} for k, v in sorted(stats.items())},
        'examples': examples}


MANAGER = 0x5757E8  # the manager pointer global (0 before init / after shutdown)
ENTER_CS, LEAVE_CS = 0x43A010, 0x43A030  # IAT: EnterCriticalSection / LeaveCriticalSection
MAP_MUTATORS = {0x1ABA0: 'counter map insert/update', 0x1AF50: 'counter map remove', 0x1E520: '+0x3F8 insert',
    0x2E480: '+0x3F8 erase', 0x1F7C0: 'post now'}


def import_name(img, iat):
    """The imported function name at an IAT slot (by its hint/name entry)."""
    pe = struct.unpack_from('<I', img.raw, 0x3C)[0]
    rva, _ = struct.unpack_from('<II', img.raw, pe + 24 + 112 + 8)
    while True:
        ilt, _, _, name, first = struct.unpack_from('<IIIII', img.data, rva)
        if name == 0:
            return None
        k = 0
        while True:
            entry = struct.unpack_from('<Q', img.data, (ilt or first) + 8 * k)[0]
            if entry == 0:
                break
            if first + 8 * k == iat and not entry >> 63:
                return img.cstr((entry & 0x7FFFFFFF) + 2)
            k += 1
        rva += 20


def rel32_callers(img, target):
    """Every direct call/jmp rel32 to target in .text (byte scan, then confirmed by disassembly)."""
    text = img.section('.text')
    data = bytes(img.data[text['rva']:text['rva'] + text['virtualSize']])
    out = []
    for i in range(len(data) - 5):
        if data[i] in (0xE8, 0xE9) and text['rva'] + i + 5 + struct.unpack_from('<i', data, i + 1)[0] == target:
            insn = img.insn(text['rva'] + i)
            if insn.size == 5 and int(insn.op_str, 16) == target:
                out.append(text['rva'] + i)
    return out


def playing_checks(img, funcs):
    """[C] every binding loads the manager from MANAGER only; the queued path takes no lock before its write;
    the end-of-event callback calls none of the map mutators."""
    assert import_name(img, ENTER_CS) == 'EnterCriticalSection'
    assert import_name(img, LEAVE_CS) == 'LeaveCriticalSection'
    loads = {}
    for name, e in funcs.items():
        for insn in function_code(img, e['rva']):
            t = rip_target(insn)
            if t is None or not insn.op_str.startswith(('r', 'qword ptr [rip')) or 'qword' not in insn.op_str:
                continue
            if insn.mnemonic in ('mov', 'cmp') and t not in (API_HOLDER,):
                loads.setdefault(name, set()).add(t)
    others = {n: sorted(v) for n, v in loads.items() if v - {MANAGER}}
    assert not others, others
    queued = [i for i in function_code(img, 0x1F5B0) if 0x1F631 <= i.address <= 0x1F70C]
    assert not any(rip_target(i) == ENTER_CS for i in queued), 'the queued path takes a lock'
    callback_calls = {int(i.op_str, 16) for i in function_code(img, 0x1C6E0, 0x300)
        if i.mnemonic == 'call' and re.fullmatch(r'0x[0-9a-f]+', i.op_str)}
    assert not callback_calls & set(MAP_MUTATORS), callback_calls
    return {'managerGlobal': MANAGER, 'bindingsLoadingTheManager': sorted(loads),
        'managerLoadTargets': sorted({t for v in loads.values() for t in v}),
        'queuedPathTakesALock': False, 'endOfEventCallbackCallsAMapMutator': False,
        'mutatorCallSites': {'0x%X %s' % (k, v): ['0x%X' % c for c in rel32_callers(img, k)]
            for k, v in MAP_MUTATORS.items()}}


PLAYING_ID_TRANSLATION = {
    'question': 'turn the id trigger_event returns (the plugin counter id) into the Wwise playing id that '
        'pause_event / resume_event / is_playing / get_playing_elapsed look up',
    'pins': 'playingIdMap',
    'manager': {'global': '0x5757E8 (qword): the manager pointer; 0 before init and after shutdown (0x1324D); a '
        '0x1CF90-byte object built by 0x13A70 (0x131F2-0x13208). Every binding that uses the manager loads this '
        'one global (computed: checks.managerLoadTargets).'},
    'counterMap': {
        'address': 'manager + 0x1CE70 (M)',
        'fields': {'M+0x08': 'u32 slot count (iteration end)', 'M+0x10': 'u64 pointer to the entries',
            'M+0x20': 'u32 live entries (0 = empty map; decremented on removal 0x1B092)',
            'M+0x24': 'u32 bucket count (the hash divisor)', 'M+0x2C': 'u32 free-slot list head (bit 31 set)'},
        'entry': {'size': 16, '+0x0': 'u32 key: the counter id trigger_event returned',
            '+0x4': 'u32 state', '+0x8': 'u32 Wwise playing id (0 until posted)',
            '+0xC': 'u32 next: 0x7FFFFFFF end of chain, 0xFFFFFFFE (-2) empty slot'},
        'hash': 'h = (key * 0x5BD1E995) mod 2^32; h ^= h >> 24; h = (h * 0x5BD1E995) mod 2^32; i = h % [M+0x24]',
        'lookup': ['if [M+0x20] == 0: not found', 'e = [M+0x10] + 16 * i; if s32 [e+0xC] == -2: not found',
            'loop: if [e+0] == key: found; i = [e+0xC]; if i == 0x7FFFFFFF: not found; e = [M+0x10] + 16 * i'],
        'states': {'0': 'posted by 0x1F7C0: +8 is this instance\'s Wwise id [C 0x1F8EE-0x1F914]',
            '1': 'held (virtual) with Wwise id 0; the update posts it later ("Start virtual events", 0x19712) '
                'and overwrites the entry [C 0x1FA88, 0x1FAB5]',
            '2': 'queued (posted off the owner thread) with Wwise id 0; the next update posts it and overwrites '
                'the entry, or removes it when the post fails [C 0x1F6C2, 0x1870F, 0x18722]',
            '3': 'joined an already-playing shared instance; +8 is that shared instance\'s id; no reverse entry '
                '[C 0x2228D-0x223E6, 0x1ADB1]',
            '4': 'started a new shared instance; +8 is its id [C 0x2228D-0x223E6]'},
        'removed': 'state 0 entries: by the update\'s end-of-event drain (0x1DCA0 via 0x189E5) after Wwise\'s '
            'AK_EndOfEvent callback; state 2: when the queued post fails; state 1: after the virtual-event '
            'dispatch; states 3/4: other paths (0x1E2C8, 0x1E2EC; not analysed)'},
    'reverseMap': 'manager + 0x1CEA0: Wwise id -> counter, 12-byte entries (key +0, counter +4, next +8), same '
        'hash; written for states other than 3 (0x1ADB1), read by the end-of-event drain (0x1E0EE)',
    'recordMap': {
        'address': 'manager + 0x3F8 (P), keyed by the Wwise id (0x1E5F1)',
        'fields': {'P+0x10': 'entries', 'P+0x20': 'live count', 'P+0x24': 'bucket count'},
        'entry': {'size': 0x38, '+0x00': 'u32 key (Wwise id)', '+0x08': 'record: u64 game object',
            '+0x10': 'record+8: u32 event id', '+0x21': 'record+0x19: a byte that makes pause/resume skip',
            '+0x30': 'u32 next (0x7FFFFFFF end, -2 empty)'},
        'hash': 'murmur64 (0x7400) of the 4 key bytes, high 32 bits, % [P+0x24]'},
    'threads': {
        'ownerThreadTest': 'post 0x1F5B0 calls [[manager+0x568]+0xA0]+0xD0 (manager+0x568 = the API holder; '
            'holder+0xA0 = get_api(0x20)); true -> post now and write M directly, false -> write M state 2 and '
            'queue under the lock manager+0x1CE00 (0x1F615-0x1F70C). What get_api(0x20) is (the public Stingray '
            'id 32 is THREAD_API_ID [I]) and what +0xD0 tests are UNPROVEN.',
        'unlockedWriters': ['bindings: the direct post (no lock passed, 0x1F776)', 'bindings: the queued path '
            'writes state 2 before taking any lock (0x1F6E6)', 'the update: queue drain (0x18706: no lock to '
            '0x1F7C0), end-of-event drain (0x1E0FF), virtual-event clean-up (0x19372)'],
        'lockedWriters': ['the update\'s "Start virtual events" jobs 0x196D0 (dispatched through get_api(0x20) '
            '+0xE8) run 0x1F7C0 under a critical section local to that dispatch (0x192BC-0x19712); the update '
            'then removes entries without that lock (0x19372), so the dispatch has completed by then [I]'],
        'wwiseThread': 'the AK_EndOfEvent callback 0x1C6E0 only appends the ended id to manager+0x440 under the '
            'lock manager+0x4F0 (0x1C732-0x1C78E) and calls no map mutator (computed); the update drains that list',
        'conclusion': 'M and P have no lock of their own: they belong to one thread (the one the +0xD0 test '
            'accepts, which also runs the plugin update 0x440C0 -> 0x18640) [I from the design: the queue exists '
            'to move posts onto that thread]. A reader on that thread never sees a half-updated table; a reader '
            'on any other thread can race the update and the direct posts.',
        'runtimeSelfCheck': 'right after trigger_event returns counter c (non-zero), read M[c]: state 0, 3 or 4 '
            'with a non-zero Wwise id proves that this call posted synchronously, i.e. that the calling Lua '
            'thread passed the +0xD0 test and owns M; state 2 means the call was queued: this thread does not '
            'own M, so stop reading it.'},
    'bindingsGivenTheWwiseId': {
        'pause_event / resume_event': 'P[Wwise id] -> 0xD3930(record event, 1 or 2, record game object, 0, 4, '
            'Wwise id) [C 0xDCD4-0xDCED]; acts on that playing instance [I: Wwise ExecuteActionOnEvent with a '
            'playing id]; a shared instance (state 3/4) is shared with every counter id on it',
        'is_playing': 'true while P[Wwise id] exists: from the post until the update drains the end-of-event '
            '(so up to one update after Wwise reports the end)',
        'get_playing_elapsed': 'the id goes straight to 0xD5250; the post sets flag 0x100000 (0x1F86A) [I: '
            'AK_EnableGetSourcePlayPosition]; an ended id returns no value',
        'stop_event': 'takes the counter id itself (0x204C0 -> 0x1AE90): no translation needed',
        'after the end': 'the drain erases P[Wwise id] (0x1E0E3) and M[counter] (0x1E0FF): pause/resume do '
            'nothing, is_playing is false'},
}


SOURCE_LIFETIME = {
    'pins': 'sourceLifetime',
    'slot': 'world source slot = world+0x4150 + 0x18 * (id & 0xFFF): +0x0 id, +0x8 unit id, +0xC node, '
        '+0x10 byte unit link, +0x11 byte keep (set_source_lifetime / make_manual_source / the resolver\'s unit '
        'path), +0x12 pose dirty, +0x13 delete mark, +0x14 u32 (a count; non-zero also blocks freeing)',
    'sweep': 'every plugin update (0x440C0 -> 0x56000 per world, 0x4415A) runs the job 0x562D0 over all 4096 '
        'slots ("WwiseWorldInterface::mark_delete_sources") and then frees the marked slots in the same update. '
        'Nothing is freed while the world is disabled (0x56012).',
    'rules': {
        'rule 1 (0x562FB-0x56317)': 'keep byte +0x11 == 0 and +0x14 == 0 and 0x1D4E0 == 0, i.e. the manager '
            'object has no playing event (+0x28: +1 when a post reaches Wwise at 0x1E59F, -1 in the end-of-event '
            'drain at 0x1E02A) and no queued post (+0x2C: +1 at 0x1A84B, -1 at 0x18727) -> mark 1 -> 0x545B0 '
            '(0x5612E): unregistered and the slot freed',
        'rule 2 (0x56326-0x56345)': 'unit link +0x10 set and get_api(0xE) fn 0 (holder+0x48, world+0x4120 = '
            'the holder 0x52863) returns NULL for the slot\'s unit id -> mark 2 -> 0x54790 (0x5611B): every '
            'source of that unit destroyed'},
    'kinds': {
        'trigger_event position source (Vector3 / Matrix4x4)': 'made by 0x53DF0 with +0x10..+0x17 = 0 '
            '(0x53E52); the resolver returns it without setting +0x11 (0xA80D, 0xAA96). FREED by rule 1 in the '
            'first update after its last event ended (or at once if the post failed). The post counts it '
            'synchronously (0x1E59F) or as queued (0x1A84B) before any update can sweep it.',
        'trigger_event unit source': 'made or reused by 0x54120 per unit node (one slot per unit node, never '
            'one per call); the resolver sets +0x11 = 1 (0xA7D1), so rule 1 never frees it; freed by rule 2 '
            'when the unit is gone, or explicitly (destroy_manual_source; unlink_source clears +0x10/+0x11 '
            '(0x56528) after which rule 1 applies)',
        'make_auto_source': '+0x11 = 0 (0xAEA0): rule 1 frees it at the next update with nothing playing on it '
            '(post on it before then)',
        'make_manual_source': '+0x11 = 1: kept until destroy_manual_source (or rule 2 for a unit source)'},
    'tableFull': '0x19D00 pops a free index from a ring (count manager+0xCEC); count 0 -> -1 (0x19D13) -> 0x19E50 '
        'logs "Too many sound source objects, skipping object `%s`" and returns 0 (0x19E77-0x19E9D) -> 0x53DF0 '
        'returns -1 (0x53EA3) -> trigger_event returns playing id 0 and source 4294967295. No live slot is '
        'overwritten; a reused index gets a new generation (0x19D84). The 4096 manager objects are shared by '
        'every world and the listeners.',
    'conclusion': 'A position source made by trigger_event(world, name, Vector3/Matrix4x4) is freed after its '
        'sounds end, by the per-world update sweep 0x56000 (rule 1 at 0x562FB-0x56317, freed by 0x545B0 at '
        '0x5612E) in the first plugin update after its last event ended. It does not leak; the Runtime must not '
        'destroy it itself.',
}


def main():
    raw = DLL.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    img = Image(DLL)
    pins = prove(img)
    reg = registration(img)
    funcs = {'%s.%s' % (e['module'], e['name']): e for e in reg if e['kind'] == 'function'}
    starts = {b for b, _ in img.pdata()}
    for e in funcs.values():  # a function start: a .pdata entry, or (a leaf/thunk) right after int3 or ret
        e['pdata'] = e['rva'] in starts
        assert e['pdata'] or img.data[e['rva'] - 1] in (0xCC, 0xC3), 'registered 0x%X is not a start' % e['rva']
    assert set(BINDINGS) | UNANALYSED == set(funcs), sorted(set(funcs) ^ (set(BINDINGS) | UNANALYSED))
    bindings = {}
    for name, e in sorted(funcs.items(), key=lambda kv: kv[1]['rva']):
        entry = {'rva': e['rva'], 'module': e['module'], 'name': e['name'], 'apiCalls': api_calls(img, e['rva'])}
        if name in BINDINGS:
            entry.update(BINDINGS[name])
        else:
            entry.update({'scope': 'unproven', 'notes': 'not analysed: only its API calls are listed'})
        bindings[name] = entry
    pinned = {(g, rva) for g, ps in PINS.items() for rva, *_ in ps}
    for name, b in BINDINGS.items():
        assert all(g in PINS for g in b['pins']), name
    for off, (_, _, _, ev) in API_OFFSETS.items():
        assert all(p in pinned for p in ev), hex(off)
    lua_check = {}
    for off, (api, tag, why, ev) in sorted(API_OFFSETS.items()):
        k = (off - LUA51_BASE) // 8
        order = LUA51[k] if off >= LUA51_BASE and (off - LUA51_BASE) % 8 == 0 and k < len(LUA51) else None
        lua_check['0x%X' % off] = {'name': api, 'evidence': tag, 'why': why,
            'pins': ['%s 0x%X' % p for p in ev], 'lua51Order': order}
        if order is not None and off <= 0x210:
            assert order == api, (hex(off), order, api)
    out = {
        'plugin': {'path': str(DLL), 'sha256': sha, 'sha256MatchesResearch': sha == RESEARCH_SHA256,
            'imageBase': img.base, 'sections': img.sections, 'wwiseSdk': '2024.1.9.8920 (build paths in .rdata)'},
        'apiTable': {'holder': 'mov rax, [0x64D9C0]; mov rX, [rax + 8]', 'offsets': lua_check,
            'note': 'offsets 0x88..0x210 coincide with the Lua 5.1 lua.h order from +0x68 [I], and each one\'s usage '
                'matches [C]; 0x360..0x468 are engine extensions named only by usage'},
        'layout': holder_checks(img),
        'nameHash': {'routine': 0xD4A70, 'algorithm': 'FNV-1 32-bit (offset basis 0x811C9DC5, prime 0x1000193, '
            'multiply then xor) over ASCII lower-cased A-Z; NULL -> 0', 'pins': 'hash',
            'alsoInline': ['0xDCFA0 set_global_parameter', '0xDD690 set_state', '0xD7E80 post_trigger']},
        'registration': [{**e, 'value': e.get('value')} if e['kind'] == 'number' else e for e in reg],
        'bindings': bindings,
        'sourceResolver': {'rva': 0xA6C0, 'call': '0xA6C0(world, L, first argument index)', 'order': [
            'gettop + 1 - index <= 0: the world default source world+0x4148',
            'is Unit (api+0x468): Unit (api+0x428); NULL -> message "Attempted to access a deleted unit as a '
            'source." and -1; next argument a number -> node (api+0x3C8) else 0; world disabled -> -1; '
            '0x54120(world, unit, node) finds or makes the unit node\'s source; slot byte +0x11 = 1',
            'is Matrix4x4 (api+0x460): a new position source 0x53DF0(world, pose, 0)',
            'is Vector3 (api+0x448): identity 4x4 with that translation; next argument is Quaternion (api+0x450) '
            '-> its rotation; a new position source 0x53DF0',
            'isnumber: tointeger, returned as the source id unchecked (the post checks it)',
            'otherwise (an explicit nil too): message "Bad Source Id parameter" and -1'], 'pins': 'resolver'},
        'sourceIds': {'manager': 'game-object table 0x5758E0, 4096 x 0xD8, index id & 0xFFF; live byte +0x40, id '
            '+0x38', 'world': 'source table world+0x4150, 4096 x 0x18, index id & 0xFFF; id +0, unit id +8, node '
            '+0xC, flags +0x10..+0x12, +0x14', 'checkedBy': ['has_source', 'trigger_event (post)',
            'set_source_parameter', 'set_switch', 'post_trigger', 'set_source_position', 'set_source_pose',
            'set_source_lifetime', 'destroy_manual_source'], 'uncheckedBy': ['unlink_source',
            'add_source_listeners', 'remove_source_listeners', 'set_environment_for_source',
            'set_dry_environment_for_source', 'reset_environment_for_source'],
            'note': 'unchecked = a stale id writes whichever source holds slot id & 0xFFF (in bounds, wrong target)'},
        'metadata': {'loader': 0x39AA0, 'map': 'manager+0x230 (entries at manager+0x240, 32 bytes: key +0, value '
            '+4..+0x1B, next +0x1C)', 'resource': 'u32 version, u32 byte length, then records of 28 bytes',
            'record': [{'offset': o, 'type': t, 'field': f, 'evidence': ev} for o, t, f, ev in METADATA_RECORD],
            'defaults': {'max_attenuation': 0.0, 'max_duration': 0.0, 'min_duration': -1.0, 'duration_type': 3,
                'position_type': 2, 'rva': 0x567AD0},
            'constants': {'WWISE_DURATION_ONE_SHOT': 0, 'WWISE_DURATION_INFINITE': 1, 'WWISE_DURATION_UNSUPPORTED': 2,
                'WWISE_3D_SOUND': 0, 'WWISE_2D_SOUND': 1, 'WWISE_INVALID_SOUND': 2},
            'pins': 'metadata', 'data': metadata_data()},
        'playingIdTranslation': {**PLAYING_ID_TRANSLATION, 'checks': playing_checks(img, funcs)},
        'sourceLifetime': SOURCE_LIFETIME,
        'pins': pins,
    }
    text = json.dumps(out, indent=1, sort_keys=False) + '\n'
    with open(OUTPUT, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    print('%s: %d registrations (%d functions), %d pins, sha256 %s' % (OUTPUT.relative_to(ROOT), len(reg),
        len(funcs), sum(len(v) for k, v in pins.items() if k != 'data'), sha))


if __name__ == '__main__':
    main()
