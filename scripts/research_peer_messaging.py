"""The Runtime-to-Runtime peer channel (research/docs/runtime-peer-messaging-F5FEE03DCFDB.md): the game's PlayFab lobby
member data, which game.dll itself publishes and reads through two slots of the engine's API table. Read-only, offline:
the game.dll and executable images and the seven retained snapshots of build F5FEE03DCFDB. Nothing is written.

Proves:

1. The objects. The network context [game+0x347CEF0] (the Runtime's "local user global"; +0xB398 the local peer id)
   holds the game's lobby wrapper at +0x1D470 (the SOS key setter's caller). The wrapper's +0 is the engine lobby and
   its byte +0x1BA6 the flag the wrapper update requires before it uses the lobby. The game's leave destroys the engine
   lobby through T+0xB8, then clears +0 and +0x1BA6, so a cleared flag never leaves a dangling lobby behind.
2. The table. game.dll reaches the engine's PlayFab API table T as [[game+0x3326308]+0xF8] (the engine API registry,
   which core/assets also uses for its package API) and calls T+0x120 set_member_data(engine lobby, 1, &key, &value)
   (0x1094087, its "platform_lobby" key) and T+0x118 member_data(engine lobby, peer, key) (0x1093DFC, skipping the local
   peer [ctx+0xB398]).
3. The engine functions. T+0x120 is exe 0x8C7010: PlayfabLobby = engine lobby +0x10; PFLobbyPostUpdate(PlayfabLobby
   +0x120 handle, &PlayfabLobby+0x130 local user, lobby update NULL, member update {n, keys, values}, async context
   NULL). T+0x118 is exe 0x8C6F30: the peer must be in PlayfabLobby +0x108[+0x100] (else NULL), then
   PFLobbyGetMemberProperty(handle, {"%llX" of the peer, "title_player_account"}, key, &value); returns the SDK's value
   or NULL. PlayfabLobby +0x118 == 3 is "joined" (kick_member's check before its own post).
4. The completion. The engine's PostUpdateCompleted handler (0x8CFA87) logs, reads the result (+4) and, only for
   0x89236226 (the lobby is gone), the handle (+8); it never reads the async context, and the engine keeps no in-flight
   state. A Runtime post's completion is therefore one more log line.
5. The snapshots [O]. In all seven (ship and mission, solo host) the lobby is joined (flag set, engine lobby state 3,
   PlayfabLobby state 3) with one member whose peer id is the Runtime's local session peer id; the mission snapshots
   keep one lobby id from the mission through its end transition; T and both slots resolve to the same functions.

Output: research/peer-messaging-F5FEE03DCFDB.json.
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
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/peer-messaging-F5FEE03DCFDB.json'
CONTEXT, LOCAL_PEER, HOST_PEER, WRAPPER = 0x347CEF0, 0xB398, 0xB3A8, 0x1D470
HOST_TEXT = 0x2262E70           # "Got game_session_disconnect from peer that isn't host! (host=%llx, peer_id=%llx)"
ENGINE_LOBBY, ACTIVE, PLATFORM_POSTED, WRAPPER_MEMBERS, WRAPPER_MEMBER_COUNT = 0x0, 0x1BA6, 0x1BA7, 0x1B58, 0x1BB0
ENGINE_LOBBY_STATE, PLAYFAB = 0x8, 0x10
PL_MEMBER_COUNT, PL_MEMBERS, PL_STATE, PL_HANDLE, PL_LOCAL_USER, JOINED = 0x100, 0x108, 0x118, 0x120, 0x130, 3
REGISTRY_GLOBAL, REGISTRY_RVA, TABLE, TABLE_RVA = 0x3326308, 0x27C8D80, 0xF8, 0x27CDE70
MEMBER_DATA, SET_MEMBER_DATA, DESTROY = 0x118, 0x120, 0xB8
MEMBER_DATA_RVA, SET_MEMBER_DATA_RVA = 0x8C6F30, 0x8C7010
POST_UPDATE_IAT, GET_MEMBER_PROPERTY_IAT = 0x13F70E8, 0x13F70F8
GAME_KEYS = {'platform_lobby': 0x2264220, 'crossplay_mode': 0x2264210}
LOBBY_GONE = 0x89236226
# The thrown stratagem balls (the call-in component; research local_research/mp/ball/ball-owner-notes.md): replicated
# state per instance at +0x60 (0x28 each), the total instance count at +0x18 (network copies included).
CALL_IN, CI_TOTAL, CI_STATES, CI_STRIDE = 0x3326D98, 0x18, 0x60, 0x28
CI_TYPE, CI_OWNER, CI_SLOT, CI_BEACON, NO_NETWORK = 0x08, 0x10, 0x18, 0x1C, 0x7FFF
# The loadout screen's four player panels (research local_research/mp/panels/remote-panels-notes.md): panel k = ui +
# PANELS + k * PANEL_STRIDE (0: the local player, 1-3: teammates); its bound peer and record; its slot panel (the one
# panel 0's research already pins: ui + 0x595F0) with its bound record (+0xD960), local flag (+0xD978) and slot widgets.
PANELS, PANEL_STRIDE, PANEL_COUNT, PANEL_PEER, PANEL_RECORD, SLOT_PANEL = 0x53A78, 0x1EE18, 4, 0x1EE00, 0x1EDF0, 0x5B78
SP_RECORD, SP_LOCAL, SP_WIDGETS, WIDGET_STRIDE, WIDGET_TYPE, RECORD_OWNER = 0xD960, 0xD978, 0x8EC0, 0x12A8, 0x128C, 0x9E8
# The Pelican CAS chin gun on a peer that did not spawn it (notes local_research/mp/pelican/pelican-mp-notes.md): every
# machine fires its OWN rounds from its OWN copy of the turret, driven by the replicated trigger byte, with its own
# resolved data (the projectile its copy names, its instance interval, spread, recoil and casing); the owner's blob is
# re-applied before the local fire (the current RPM entry with it, never the copies or the instance records); the AI runs
# on the owner only; the copy routine and the resolver test no ownership. And the credit: a round's pool creditor flows
# unchanged into the damage event, the victim's health +0x38 and the kill, for any player in the list.
PELICAN_INSTANCE_INTERVAL, PELICAN_INSTANCE_CACHED_RPM = 0xC, 0x64
PELICAN_RESOURCE, CHIN_RESOURCE = '75BE82ED8592A6B3', '8365609B35EF6672'
PELICAN_MIRROR_PINS = [
    (0x740795, 'mov byte ptr [rdx + rcx + 1], al', None, 'the weapon update copies each trigger byte into the PW instance, '
        'remote copies included'),
    (0x7464F7, 'mov byte ptr [rdx + rcx], al', None, 'a remote copy\'s trigger byte comes from the owner\'s blob'),
    (0x617909, 'cmp dword ptr [rbp + 0x3c], r14d', None, 'the fire loop covers every world-spawned instance (remote '
        'copies fire locally)'),
    (0x616E63, 'cmp byte ptr [r12 + 0x94], dil', None, 'only a networked-shot weapon (PW +0x94) ...'),
    (0x616E6D, 'test byte ptr [r13 + 0x14], 1', None, '... not created here ...'),
    (0x616E76, 'cmove r15d, edi', None, '... skips the local fire (the chin turret\'s +0x94 is 0)'),
    (0x61406C, 'call 0x7456d0', None, 'each shot resolves its projectile from this machine\'s own data'),
    (0x616612, 'call 0x13a9830', None, 'pool rounds spawn on every machine (no created-here test)'),
    (0xAB5EAA, 'call 0xfdde30', None, 'the remote objects\' blobs are re-applied ...'),
    (0xAB5EC9, 'call 0x571250', None, '... before the systems pass (the weapons fire)'),
    (0xAB55AF, 'call 0x13f73f0', None, 'the projectile step runs before the fire (a new round is not stepped in its '
        'spawn update)'),
    (0x619163, 'mov dword ptr [r8 + r9*4 + 4], ecx', None, 'a remote copy\'s current RPM entry is the owner\'s value'),
    (0x616E99, 'ucomiss xmm1, dword ptr [r14 + rbp + 0x64]', None, 'the current RPM against the instance\'s cached '
        'one (+0x64) ...'),
    (0x616EC0, 'movss dword ptr [r14 + rbp + 0xc], xmm0', None, '... only when they differ: the instance interval '
        '(+0xC) := 60 / current'),
    (0x6175E2, 'mov eax, dword ptr [rbp + 0x40]', None, 'the RPM reset covers the instances created here only'),
    (0x8434EC, 'cmp r12d, r8d', None, 'the AI update covers the instances created here only'),
    (0x845C3B, 'add r8, qword ptr [r11 + 0x68]', None, 'a received behaviour goes into the replicated-state block, not '
        'the AI record'),
    (0x5151B9, 'add rax, qword ptr [r11 + 0xd0]', None, 'the resolver takes the instance\'s own copy when it has one '
        '(no ownership test)'),
    (0x61AF42, 'mov r9d, dword ptr [rcx + 0x98]', None, 'the copy routine keys by the local entity (no ownership test)'),
    (0x13AD2AD, 'mov rax, qword ptr [r14]', None, 'a hit takes its round\'s pool creditor (hit record +0) ...'),
    (0x12A1239, 'test r14, r14', None, '... and derives one only when it is 0 ...'),
    (0x923C20, 'mov qword ptr [r15 + 0x38], rax', None, '... into the victim\'s health record +0x38 (the kill\'s credit)'),
    (0x62C737, 'cmp rdx, qword ptr [r9]', None, 'a kill\'s stat finds its player by peer id (any player, no local test)'),
    (0x5AA736, 'movups xmmword ptr [rcx + 4], xmm0', None, 'a remote Pelican\'s mount record names its children by '
        'network id ...'),
    (0x5A8B65, 'call 0xfd9c80', None, '... resolved to this machine\'s own entities'),
]
# A native orbital barrage (notes local_research/mp/barrage/barrage-notes.md): created by the thrower's dispatcher as a
# NETWORKED game object (the same network id on every machine; a remote copy is a replicated spawn with the creator's
# block, seed included); every copy fires its own shells (source = this machine's own barrage entity; no shot id, so each
# machine explodes its own copy's impact explosion). No component names the beacon, but two replicated ones name what
# ties it to its beacon: component 131 the beacon's creation type (the CARRIER for a redirected beacon; a native 120mm
# its own type) and component 28 the creator's peer; its block's target is the beacon's position.
BARRAGE_MANAGER = {'networkCount': 0x20, 'ownerCount': 0x24, 'map': 0x30, 'handles': 0x48, 'block': 0x60,
    'blockStride': 0x1C, 'blockTarget': 0x08}
BARRAGE_HANDLE = {'payload': 0x00, 'entity': 0x08, 'network': 0x10, 'flags': 0x14}
BARRAGE_CREATOR = {'global': 0x3326C40, 'map': 0xA0, 'peers': 0xC0}
BARRAGE_CARRIER = {'global': 0x3326C08, 'map': 0x20, 'types': 0x50}
BARRAGE_PINS = [
    (0x6ABB89, 'lea r15, [r13 + 0x40]', None, 'the activation passes the dispatcher the beacon state + 0x40'),
    (0x6A8F72, 'movups xmmword ptr [rbx + 0x3d8], xmm0', None, 'the beacon state keeps its creation parameters (type '
        'included) at +0x3D8'),
    (0x6AD7B9, 'mov word ptr [rbp], 1', None, 'the payload entity is created here as a network object'),
    (0x6AD7D3, 'mov qword ptr [rbp + 0x48], rsi', None, 'its spawn context names the dispatch block'),
    (0x6AD919, 'call 0xfd9710', None, 'the barrage spawn request'),
    (0xFDC1D7, 'mov dword ptr [r14 + 0x14], 1', None, 'the entity handle\'s created-here bit (+0x14 bit 0)'),
    (0x581775, 'mov dword ptr [r15 + 0x10], r9d', None, 'the entity handle\'s network id (+0x10)'),
    (0xBA04CA, 'mov dword ptr [rsp + 0x84], esi', None, 'a remote copy is spawned with the same network id'),
    (0xBD48C8, 'call 0x854b00', None, 'and gets the creator\'s bombardment block'),
    (0x537497, 'mov qword ptr [rax + rdx*8], rsi', None, 'the bombardment manager +0x48 names each barrage\'s entity handle'),
    (0x53741C, 'cmp byte ptr [rdi], 0', None, 'its owner group [0, +0x24) and its remote copies [+0x24, +0x20)'),
    (0x854AAF, 'mov dword ptr [rax + r13 + 0x18], ecx', None, 'the replicated block\'s seed'),
    (0x8537AE, 'cmp eax, dword ptr [r15 + 0x20]', None, 'every copy fires (owner and remote groups)'),
    (0x852CA9, 'mov dword ptr [rbp + 0x1b8], ecx', None, 'each shell\'s source is this machine\'s barrage entity'),
    (0x852CD6, 'call 0x9ef150', None, 'its creditor from the caller\'s object (component 48)'),
    (0x13AA4EE, 'mov dword ptr [rsi + rdx*4 + 0x3b04c], eax', None, 'the pool source record +0x0C'),
    (0x13AA64C, 'mov dword ptr [rdi + 0x7c], ecx', None, 'the impact explosion copy +0x7C'),
    (0x13AA49D, 'mov dword ptr [rsi + rax*4 + 0x3b044], ecx', None, 'the arming distance (row +0xA0; 0 for the 120mm\'s '
        'shells)'),
    (0x13B0A24, 'cmp edi, -1', None, 'no shot id: no impact message (each machine explodes its own copy)'),
    (0x51A3FD, 'mov qword ptr [r9 + r8], rdx', None, 'component 28 +0xC0: the creator\'s peer'),
    (0x9C4BA9, 'mov qword ptr [rcx + rdx*8], rax', None, '... replicated to every copy'),
    (0x52B67E, 'mov ecx, dword ptr [rcx + 0x398]', None, 'component 131: the beacon\'s creation type ...'),
    (0x52B684, 'mov dword ptr [r8 + rdx], ecx', None, '... into +0x50 (the carrier for a redirected beacon)'),
    (0x6B0A46, 'mov dword ptr [rcx + rdx*4], eax', None, '... replicated to every copy'),
]
PANEL_PINS = [
    (0x1466AE2, 'lea rsi, [rdi + 0x53a78]', None, 'the player panels start at ui + 0x53A78 ...'),
    (0x146CC5A, 'imul rbx, rax, 0x1ee18', None, '... one every 0x1EE18 ...'),
    (0x146D2C0, 'cmp ebp, 4', None, '... four of them'),
    (0x146CC17, 'lea rax, [rsi + 0x27ec]', None, 'teammates take the panels from 1 up'),
    (0x14670C7, 'mov dword ptr [rdi + rcx*4 + 0x27d8], r14d', None, 'the local player is panel 0'),
    (0x146C4C9, 'mov dword ptr [rsi + rax*4 + 0x27e8], r13d', None, 'a panel\'s session player index'),
    (0x189CA4E, 'mov qword ptr [rcx + 0x1edf0], rdx', None, 'binding a panel: its record (+0x1EDF0) ...'),
    (0x189CA55, 'mov qword ptr [rcx + 0x1ee00], r8', None, '... and its player\'s peer id (+0x1EE00)'),
    (0x189CBCC, 'mov qword ptr [rcx + 0x1ee00], r8', None, 'the joining-player binder: the peer id too ...'),
    (0x189CBD6, 'xor r8d, r8d', None, '... never the local flag'),
    (0x189CA8E, 'sete r8b', None, 'the local flag: the first local player only'),
    (0x189C796, 'lea r14, [rcx + 0x5958]', None, 'the panel\'s slot panel: + 0x5958 ...'),
    (0x189C8EF, 'lea rcx, [r14 + 0x220]', None, '... + 0x220 ...'),
    (0x189C900, 'call 0x1895a20', None, '... repainted from the record (the slots\' own repaint)'),
    (0x14706AF, 'lea rcx, [rsi + 0x9f8]', None, 'a teammate\'s record: the UI record whose owner (+0x9E8) is its peer'),
    (0x14706DD, 'imul rcx, rax, 0x9f0', None, 'UI records are 0x9F0 apart'),
    (0x1896336, 'imul rsi, rax, 0x12a8', None, 'slot widgets 0x12A8 apart ...'),
    (0x1896340, 'lea rcx, [rsi + 0x8ec0]', None, '... from the slot panel + 0x8EC0'),
    (0x1893613, 'mov dword ptr [rcx + 0x128c], edi', None, 'a widget\'s shown type (+0x128C)'),
    (0x189361C, 'test edx, edx', None, 'type 0: the icon is cleared'),
    (0x18964C7, 'lea rbx, [r13 + 0x9240]', None, 'no record: every icon cleared'),
]
CALL_IN_PINS = [
    (0x6A3608, 'mov rbx, qword ptr [rax + 0x160]', None, 'the throw: the engine API\'s game_object_owner (+0x160) ...'),
    (0x6A361B, 'call rbx', None, '... of the thrower\'s network object (its Player) ...'),
    (0x6A3624, 'mov edx, 0xfe9aee41', None, '... the owner field, marked for replication ...'),
    (0x6A3631, 'mov rcx, qword ptr [rdi + 0x60]', None, '... in the replicated states (+0x60, 0x28 each) ...'),
    (0x6A3635, 'mov qword ptr [rbx + rcx + 0x10], r15', None, '... state +0x10 := the thrower\'s peer id'),
    (0x6A3663, 'mov dword ptr [rbx + rcx + 0x18], eax', None, 'state +0x18 := the record entry index'),
    (0x6A368F, 'mov dword ptr [rbx + rcx + 8], eax', None, 'state +0x08 := the stratagem type'),
    (0x6A3416, 'mov dword ptr [rcx + rbx*8 + 0x1c], eax', None, 'at the landing: state +0x1C := the beacon\'s network id'),
    (0x6A2AF4, 'test byte ptr [r12 + 0x14], 1', None, 'the landing runs where the ball was created'),
    (0x6A46BE, 'mov dword ptr [r14 + rax*8 + 4], 9', None, 'the owner is a 64-bit network field'),
    (0x6A4886, 'mov qword ptr [r8 + 0x10], rcx', None, 'a remote copy: the owner from the network ...'),
    (0x6A489C, 'mov dword ptr [r8 + 0x1c], ecx', None, '... and the beacon\'s network id'),
    (0xBC3947, 'call 0x6a47b0', None, 'game object type 1169 (the ball) applies its fields ...'),
    (0xFDC29B, 'call 0xbc2d30', None, '... when a remote copy spawns ...'),
    (0xFDDE6A, 'call 0xbc2d30', None, '... and every update after'),
    (0x542EFB, 'inc dword ptr [rbx + 0x18]', None, 'the total instance count (+0x18)'),
    (0x6A506A, 'mov qword ptr [rsi + 0x60], rax', None, 'the replicated state array (+0x60)'),
    (0x13634FF, 'mov qword ptr [r15 + 0xa20], rax', None, 'a record\'s call-in key (state +0x9E8) := its peer id'),
    (0x66D286, 'cmp qword ptr [r9 + rcx*8 + 0x10], r11', None, 'the game matches a ball\'s owner with that key'),
    (0x1866A1B, 'mov rdx, qword ptr [rbx + r11*8 + 0x10]', None, 'the HUD reads a ball\'s owner peer ...'),
    (0x1866A20, 'call 0x1366dc0', None, '... and finds that peer\'s record'),
]

GAME = {
    'sessionHost': [
        (0x1084CFF, 'mov rax, qword ptr [rip + {rip}]', CONTEXT, 'game_session_disconnect: the network context ...'),
        (0x1084D06, 'mov r8, qword ptr [rax + 0xb3a8]', None, '... its session host peer (+0xB3A8) ...'),
        (0x1084D0D, 'cmp r8, rdi', None, '... compared with the sending peer ...'),
        (0x1084D42, 'lea rdx, [rip + {rip}]', HOST_TEXT, '... logged as "host=%llx" when they differ'),
    ],
    'context': [
        (0x518125, 'mov rbx, qword ptr [rip + {rip}]', CONTEXT, 'the network context global ...'),
        (0x518133, 'lea rcx, [rbx + 0x1d470]', None, '... + 0x1D470: the game\'s lobby wrapper (the lobby key setter '
            'takes it)'),
        (0x51813A, 'call 0x10925d0', None, '... the lobby key setter (wrapper, key, value)'),
    ],
    'wrapperUpdate': [
        (0x10937C4, 'cmp byte ptr [rcx + 0x1ba6], 0', None, 'the wrapper update uses the lobby only while +0x1BA6 is '
            'set ...'),
        (0x10937CB, 'mov rdi, rcx', None, '... (rdi = the wrapper)'),
    ],
    'leave': [
        (0x1091ECA, 'cmp byte ptr [rcx + 0x1ba6], 0', None, 'the lobby leave: the flag ...'),
        (0x1091F50, 'mov rcx, qword ptr [rbx]', None, '... the engine lobby (wrapper +0) ...'),
        (0x1091F58, 'mov rax, qword ptr [rip + {rip}]', REGISTRY_GLOBAL, '... the engine API registry ...'),
        (0x1091F5F, 'mov rdx, qword ptr [rax + 0xf8]', None, '... its PlayFab table T ...'),
        (0x1091F66, 'call qword ptr [rdx + 0xb8]', None, '... T+0xB8 destroys the engine lobby ...'),
        (0x1091F6C, 'mov qword ptr [rbx], rdi', None, '... wrapper +0 = 0 ...'),
        (0x1091F76, 'mov byte ptr [rbx + 0x1ba6], dil', None, '... and the flag cleared: no dangling lobby'),
    ],
    'setMemberData': [
        (0x1094062, 'mov rax, qword ptr [rip + {rip}]', REGISTRY_GLOBAL, 'the game\'s own member-data post: the '
            'registry ...'),
        (0x1094069, 'lea r9, [rsp + 0x20]', None, '... &value ...'),
        (0x109406E, 'mov rcx, qword ptr [rdi]', None, '... the engine lobby (wrapper +0) ...'),
        (0x1094071, 'lea r8, [rsp + 0x50]', None, '... &key ...'),
        (0x109407B, 'mov edx, 1', None, '... one property ...'),
        (0x1094080, 'mov r10, qword ptr [rax + 0xf8]', None, '... T ...'),
        (0x1094087, 'call qword ptr [r10 + 0x120]', None, '... T+0x120 set_member_data'),
        (0x109408E, 'mov byte ptr [rdi + 0x1ba7], 1', None, 'its "platform_lobby" key is posted once per join, '
            'whatever the result'),
    ],
    'memberData': [
        (0x1093DD4, 'mov rax, qword ptr [rip + {rip}]', CONTEXT, 'the game\'s own member-data read: the context ...'),
        (0x1093DDB, 'cmp rdx, qword ptr [rax + 0xb398]', None, '... it skips the local peer ...'),
        (0x1093DE4, 'mov rax, qword ptr [rip + {rip}]', REGISTRY_GLOBAL, '... the registry ...'),
        (0x1093DEB, 'mov rcx, qword ptr [rax + 0xf8]', None, '... T ...'),
        (0x1093DF2, 'mov rax, qword ptr [rcx + 0x118]', None, '... T+0x118 member_data ...'),
        (0x1093DF9, 'mov rcx, qword ptr [rdi]', None, '... the engine lobby ...'),
        (0x1093DFC, 'call rax', None, '... called (rdx = the peer)'),
        (0x1093DFE, 'test rax, rax', None, 'a NULL value: the member has no such property'),
    ],
}

EXE = {
    'setMemberData': [
        (0x8C7010, 'sub rsp, 0x58', None, 'set_member_data(engine lobby, n, keys, values) ...'),
        (0x8C7014, 'mov rcx, qword ptr [rcx + 0x10]', None, '... PlayfabLobby = engine lobby +0x10 (no null check) ...'),
        (0x8C7018, 'xor eax, eax', None, ''),
        (0x8C701A, 'mov dword ptr [rsp + 0x30], edx', None, '... member update: the count ...'),
        (0x8C701E, 'mov qword ptr [rsp + 0x38], r8', None, '... the keys ...'),
        (0x8C7023, 'xor r8d, r8d', None, '... no lobby update ...'),
        (0x8C7026, 'mov qword ptr [rsp + 0x40], r9', None, '... the values ...'),
        (0x8C702B, 'lea r9, [rsp + 0x30]', None, '... &member update ...'),
        (0x8C7030, 'lea rdx, [rcx + 0x130]', None, '... &the local user (PlayfabLobby +0x130) ...'),
        (0x8C7037, 'mov dword ptr [rsp + 0x34], eax', None, ''),
        (0x8C703B, 'mov rcx, qword ptr [rcx + 0x120]', None, '... the PFLobbyHandle (+0x120) ...'),
        (0x8C7042, 'mov qword ptr [rsp + 0x20], rax', None, '... async context NULL ...'),
        (0x8C7047, 'call qword ptr [rip + {rip}]', POST_UPDATE_IAT, '... PFLobbyPostUpdate: one post per call'),
        (0x8C704D, 'add rsp, 0x58', None, 'its result is returned'),
        (0x8C7051, 'ret', None, ''),
    ],
    'memberData': [
        (0x8C6F30, 'mov qword ptr [rsp + 0x10], rbx', None, 'member_data(engine lobby, peer, key) ...'),
        (0x8C6F3A, 'mov rbx, qword ptr [rcx + 0x10]', None, '... PlayfabLobby ...'),
        (0x8C6F3E, 'mov rdi, r8', None, '... the key ...'),
        (0x8C6F41, 'mov rax, qword ptr [rbx + 0x108]', None, '... the member peer ids (+0x108) ...'),
        (0x8C6F48, 'mov r9d, dword ptr [rbx + 0x100]', None, '... their count (+0x100) ...'),
        (0x8C6F58, 'cmp qword ptr [rax], rdx', None, '... the peer must be a member ...'),
        (0x8C6F66, 'xor eax, eax', None, '... else NULL'),
        (0x8C6F9C, 'mov rcx, qword ptr [rbx + 0x120]', None, 'the handle ...'),
        (0x8C6FAD, 'lea r9, [rsp + 0x60]', None, '... &value ...'),
        (0x8C6FB9, 'mov r8, rdi', None, '... the key ...'),
        (0x8C6FC6, 'call qword ptr [rip + {rip}]', GET_MEMBER_PROPERTY_IAT, '... PFLobbyGetMemberProperty'),
        (0x8C6FFF, 'mov rax, qword ptr [rsp + 0x60]', None, 'returns the value (the SDK clears it on failure)'),
    ],
    'joined': [
        (0x8CDF9A, 'mov rbx, qword ptr [rcx + 0x10]', None, 'kick_member: PlayfabLobby ...'),
        (0x8CDF9E, 'movsxd rax, dword ptr [rbx + 0x118]', None, '... its state (+0x118) ...'),
        (0x8CDFA5, 'cmp eax, 3', None, '... must be 3 (joined) before its own post'),
        (0x8CDFBD, 'mov rcx, qword ptr [rbx + 0x120]', None, 'the handle it posts with'),
    ],
    'lobbyState': [
        (0x8C6C60, 'mov eax, dword ptr [rcx + 8]', None, 'T+0xF0: the engine lobby\'s state (+0x8)'),
    ],
    'postUpdateCompleted': [
        (0x8CFAA2, 'mov ecx, dword ptr [rbx + 4]', None, 'PostUpdateCompleted: the result ...'),
        (0x8CFAA5, 'test ecx, ecx', None, '... success: one log line ...'),
        (0x8CFAD0, 'cmp dword ptr [rbx + 4], 0x89236226', None, '... only "the lobby doesn\'t exist" ...'),
        (0x8CFADD, 'mov rdx, qword ptr [rbx + 8]', None, '... looks up the lobby by its handle (+8): the async '
            'context (+0x20) is never read'),
    ],
}


def u64(raw, at):
    return struct.unpack_from('<Q', raw, at)[0]


def observe(name: str) -> dict:
    mem = base.Mem(name)
    g, x = mem.game, mem.exe
    ctx = mem.ptr(g + CONTEXT)
    local = mem.u64(ctx + LOCAL_PEER)
    wrapper = ctx + WRAPPER
    engine_lobby = mem.ptr(wrapper + ENGINE_LOBBY)
    flags = mem.read(wrapper + ACTIVE, 2)
    pl = mem.ptr(engine_lobby + PLAYFAB)
    count = mem.u32(pl + PL_MEMBER_COUNT)
    array = mem.ptr(pl + PL_MEMBERS)
    members = ['%016X' % mem.u64(array + 8 * i) for i in range(count)]
    wrapper_members = ['%016X' % mem.u64(wrapper + WRAPPER_MEMBERS + 8 * i)
        for i in range(mem.u32(wrapper + WRAPPER_MEMBER_COUNT))]
    registry = mem.ptr(g + REGISTRY_GLOBAL)
    table = mem.ptr(registry + TABLE)
    lobby_id = mem.read(mem.ptr(pl), 40).split(b'\0')[0].decode('ascii')
    out = {'snapshot': name, 'localPeer': '%016X' % local, 'hostPeer': '%016X' % mem.u64(ctx + HOST_PEER),
        'active': flags[0], 'platformPosted': flags[1],
        'engineLobbyState': mem.u32(engine_lobby + ENGINE_LOBBY_STATE), 'playfabState': mem.u32(pl + PL_STATE),
        'handleSet': mem.u64(pl + PL_HANDLE) != 0, 'members': members, 'wrapperMembers': wrapper_members,
        'localIsMember': ('%016X' % local) in members, 'lobbyId': lobby_id,
        'registry': registry - x, 'table': table - x,
        'memberData': mem.ptr(table + MEMBER_DATA) - x, 'setMemberData': mem.ptr(table + SET_MEMBER_DATA) - x,
        'destroy': mem.ptr(table + DESTROY) - x}
    comp = mem.ptr(g + CALL_IN)
    total = mem.u32(comp + CI_TOTAL)
    states = mem.ptr(comp + CI_STATES)
    balls = []
    for i in range(min(total or 0, 64)):
        e = states + i * CI_STRIDE
        owner, slot = mem.u64(e + CI_OWNER), struct.unpack('<i', mem.read(e + CI_SLOT, 4))[0]
        if owner and slot >= 0:
            balls.append({'type': mem.u32(e + CI_TYPE), 'owner': '%016X' % owner, 'entry': slot,
                'beaconNetwork': mem.u32(e + CI_BEACON)})
    out['callIn'] = {'total': total, 'thrown': balls}
    mem.close()
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    exe = base.Image(exe_data, exe_base, base.EXE_TEXT)
    pins = {group: [dict(game.prove(*row), module='game') for row in rows] for group, rows in GAME.items()}
    for group, rows in EXE.items():
        pins['engine.' + group] = [dict(exe.prove(*row), module='exe') for row in rows]
    if not game.cstr(HOST_TEXT).startswith("Got game_session_disconnect from peer that isn't host! (host=%llx"):
        raise ValueError('the session host log line moved')
    for key, rva in GAME_KEYS.items():
        if game.cstr(rva) != key:
            raise ValueError('the game\'s member key %s moved' % key)
    call_in_pins = [dict(game.prove(*row), module='game') for row in CALL_IN_PINS]
    panel_pins = [dict(game.prove(*row), module='game') for row in PANEL_PINS]
    pelican_pins = [dict(game.prove(*row), module='game') for row in PELICAN_MIRROR_PINS]
    barrage_pins = [dict(game.prove(*row), module='game') for row in BARRAGE_PINS]
    flat_game = ([p for rows in pins.values() for p in rows if p['module'] == 'game'] + call_in_pins + panel_pins
        + pelican_pins + barrage_pins)
    flat_exe = [p for rows in pins.values() for p in rows if p['module'] == 'exe']
    relocation = {name: base.verify_pins_live(name, flat_game, flat_exe) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    snapshots = [observe(name) for name in SNAPSHOTS]
    for s in snapshots:
        if (s['registry'], s['table'], s['memberData'], s['setMemberData']) != (REGISTRY_RVA, TABLE_RVA,
                MEMBER_DATA_RVA, SET_MEMBER_DATA_RVA):
            raise ValueError('%s: the engine table or a slot differs' % s['snapshot'])
        if not (s['active'] and s['engineLobbyState'] == JOINED and s['playfabState'] == JOINED and s['handleSet']):
            raise ValueError('%s: the lobby is not joined' % s['snapshot'])
        if s['hostPeer'] != s['localPeer']:
            raise ValueError('%s: the solo host is not its own session host' % s['snapshot'])
        if not s['localIsMember'] or s['members'] != s['wrapperMembers']:
            raise ValueError('%s: the local session peer is not the lobby member' % s['snapshot'])
    mission_ids = {s['lobbyId'] for s in snapshots if 'mission' in s['snapshot']}
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'nativeCalls': 0,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA}, 'exe': {'sha256': base.PROFILE_EXE_SHA},
        'context': {'global': '0x%X' % CONTEXT, 'localPeer': LOCAL_PEER, 'hostPeer': HOST_PEER, 'wrapper': WRAPPER},
        'wrapper': {'engineLobby': ENGINE_LOBBY, 'active': ACTIVE, 'platformPosted': PLATFORM_POSTED,
            'members': WRAPPER_MEMBERS, 'memberCount': WRAPPER_MEMBER_COUNT},
        'engineLobby': {'state': ENGINE_LOBBY_STATE, 'playfab': PLAYFAB},
        'playfabLobby': {'memberCount': PL_MEMBER_COUNT, 'members': PL_MEMBERS, 'state': PL_STATE, 'joined': JOINED,
            'handle': PL_HANDLE, 'localUser': PL_LOCAL_USER},
        'api': {'registryGlobal': '0x%X' % REGISTRY_GLOBAL, 'registry': '0x%X' % REGISTRY_RVA, 'table': TABLE,
            'tableRva': '0x%X' % TABLE_RVA, 'memberData': MEMBER_DATA, 'setMemberData': SET_MEMBER_DATA,
            'memberDataRva': '0x%X' % MEMBER_DATA_RVA, 'setMemberDataRva': '0x%X' % SET_MEMBER_DATA_RVA,
            'memberDataSignature': 'const char *member_data(void *engine_lobby, u64 peer, const char *key)',
            'setMemberDataSignature': 'i32 set_member_data(void *engine_lobby, u32 n, const char **keys, '
                'const char **values)'},
        'gameKeys': {key: '0x%X' % rva for key, rva in GAME_KEYS.items()},
        'barrage': {'manager': BARRAGE_MANAGER, 'handle': BARRAGE_HANDLE,
            'creator': {k: ('0x%X' % v if k == 'global' else v) for k, v in BARRAGE_CREATOR.items()},
            'carrier': {k: ('0x%X' % v if k == 'global' else v) for k, v in BARRAGE_CARRIER.items()},
            'pins': barrage_pins,
            'facts': 'a native barrage is a networked game object: the same network id on every machine, a remote copy '
                'spawned from the creator\'s replicated block; every copy fires its own shells from its own barrage '
                'entity and explodes its own copies (no shot id) [C]; component 131 names the beacon\'s creation type '
                '(the carrier for a redirected beacon), component 28 the creator\'s peer, the block\'s target the '
                'beacon\'s position [C]; no snapshot holds a barrage [O: none]; live: the derived match on each machine'},
        'pelicanMirror': {'instanceInterval': PELICAN_INSTANCE_INTERVAL,
            'instanceCachedRpm': PELICAN_INSTANCE_CACHED_RPM, 'pelicanResource': PELICAN_RESOURCE,
            'chinResource': CHIN_RESOURCE, 'pins': pelican_pins,
            'facts': 'every machine fires its own rounds of a networked turret from its own data (the projectile its own '
                'copy names, its instance interval, spread, recoil and casing), driven by the replicated trigger; the '
                'owner\'s blob (current RPM entry, trigger, rounds) is re-applied before the local fire; the AI runs on '
                'the owner only; the copy routine and the resolver test no ownership [C]; a round\'s pool creditor flows '
                'into the kill for any player [C]; live: a client mirror holding its projectile, casing and interval, '
                'and the kill credit of a written creditor'},
        'panels': {'base': PANELS, 'stride': PANEL_STRIDE, 'count': PANEL_COUNT, 'peer': PANEL_PEER,
            'record': PANEL_RECORD, 'slotPanel': SLOT_PANEL, 'boundRecord': SP_RECORD, 'localFlag': SP_LOCAL,
            'widgets': SP_WIDGETS, 'widgetStride': WIDGET_STRIDE, 'widgetType': WIDGET_TYPE, 'recordOwner': RECORD_OWNER,
            'pins': panel_pins,
            'facts': 'the loadout screen draws four player panels, panel 0 the local player, 1-3 teammates; each holds its '
                'player\'s peer id and record; a teammate\'s slot widgets are panel 0\'s offsets shifted by the panel '
                'stride and repainted by the same routine [C]; no retained snapshot has the loadout screen open [O: '
                'none]; live: the teammate icons drawn, their columns'},
        'callIn': {'global': '0x%X' % CALL_IN, 'total': CI_TOTAL, 'states': CI_STATES, 'stride': CI_STRIDE,
            'type': CI_TYPE, 'owner': CI_OWNER, 'entry': CI_SLOT, 'beaconNetwork': CI_BEACON, 'noNetwork': NO_NETWORK,
            'pins': call_in_pins,
            'facts': 'a thrown ball replicates (game object type 1169) with its thrower\'s session peer id (+0x10, from '
                'game_object_owner of the thrower\'s Player), its record entry index (+0x18; -1 in hand), its type (+0x08) '
                'and, from the landing, its beacon\'s network id (+0x1C) [C]; how long it lives after the landing is '
                'U (live)'},
        'lobbyGoneResult': '0x%X' % LOBBY_GONE,
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation, 'snapshots': snapshots,
        'missionLobbyIds': sorted(mission_ids),
        'facts': {
            'peerIds': 'every snapshot: the single lobby member is the Runtime\'s local session peer id [O]',
            'sessionHost': 'network context +0xB3A8 is the session host peer: game_session_disconnect compares the sender '
                'with it and logs it as host (0x1084CFF) [C]; every solo-host snapshot holds the local peer there [O]',
            'missionPersistence': 'the four mission snapshots (mission start to its end transition) keep one lobby '
                'id [O]',
            'completion': 'PostUpdateCompleted never reads the async context; no in-flight state [C]',
            'gameUse': 'game.dll posts "platform_lobby" once per join (never retried) and "crossplay_mode" on change '
                '(0x10940FC); it reads the other members\' values through T+0x118 [C]',
            'quotas': 'the property count, key and value lengths and request rate are enforced by the service; the '
                'SDK retries HTTP 429 [C strings, U numbers]'}}
    if len(mission_ids) != 1:
        raise ValueError('the mission snapshots changed lobby: %r' % mission_ids)
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), sum(len(r) for r in pins.values()), 'pins')


if __name__ == '__main__':
    main()
