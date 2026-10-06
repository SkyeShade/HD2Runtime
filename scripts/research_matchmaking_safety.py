"""Runtime public-matchmaking safety (docs/research/matchmaking-safety-F5FEE03DCFDB.md): where Helldivers 2 keeps the
lobby privacy, how the host's lobby advertises it, how Quickplay and the SOS Beacon reach strangers, and the game's own
functions that change privacy and cancel Quickplay. Read-only, offline: the game.dll image of the retained snapshots of
build F5FEE03DCFDB. Nothing is written or called.

Proves (every row below is an exact instruction at an exact game.dll RVA, byte-identical in all seven snapshots):

1. The privacy SETTING. The settings object is [game+0x3326340] (the Game object) + 0xAC3DC; the options writer and
   reader name its member "privacy_mode" at +0x174 (the live value is therefore Game + 0xAC550). The reader clamps a
   loaded value to <= 2. Its names are the table at 0x21D3F28: Open (0), FriendsOnly (1), InviteOnly (2),
   FriendsAndClan (3).
2. The ADVERTISED privacy. The game's lobby wrapper (network context [game+0x347CEF0] + 0x1D470) caches each lobby
   key as decimal text at +0x38 + key * 0x101 and publishes it (PlayFab lobby data) on the host's countdown. Key 19 is
   PrivacyMode (numeric search attribute number_key6), key 8 SOSBeacons (number_key8). A new lobby takes key 19 from
   the setting.
3. The host's JOIN GATE reads lobby key 19 and refuses a non-friend (1), a non-invited peer (2) or a non-friend /
   non-clan peer (3) with deny reason 10 (PrivacySettings); 0 (Open) admits anyone.
4. QUICKPLAY searches only lobbies whose key 19 equals 0 (game filter operator 2 = Equal). It runs while the matchmaker
   ([game+0x347CE80]) byte +0x10BD5C is set; only the galactic-war UI and the "quick_play" activity set it. The game's
   own stop is set_quickplay(matchmaker, 0, -1, 0x7FFFFFFF, ...) (game.dll 0x133E6E0), which the UI calls on cancel
   and when the galactic war map closes.
5. The SOS BEACON sets SOSBeacons = 1 and forces key 19 to 0 (Open) on the host whatever the setting; while it is
   active every privacy change keeps key 19 at 0; when it ends key 19 returns to the setting.
6. The game's own privacy SETTER is game.dll 0x11ED0B0 set_setting(settings, id, &value), case 0: settings +0x174 :=
   value, then lobby key 19 := value (0 while an SOS Beacon is active). The options menu calls it on its working copy;
   the game also calls it on the LIVE settings (0xADFFC6, another id). Its descriptor lookup (0x11ECD60) must find id 0
   (else the setter reads a NULL descriptor).
7. The snapshots [O]: the setting, the cached keys, the matchmaker flags and the descriptor lookup as they were.

Output: research/matchmaking-safety-F5FEE03DCFDB.json.
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

OUTPUT = ROOT / 'research/matchmaking-safety-F5FEE03DCFDB.json'

# Globals and layouts (game.dll RVAs / offsets); each is re-derived from the pinned code below.
GAME, STATE, SHIP = 0x3326340, 0xAC21C, 3
SETTINGS, PRIVACY, SETTINGS_SIZE = 0xAC3DC, 0x174, 0x194
CONTEXT, LOCAL_PEER, HOST_PEER, WRAPPER, SINGLEPLAYER = 0x347CEF0, 0xB398, 0xB3A8, 0x1D470, 0x1F868
ENGINE_LOBBY, PLATFORM_LOBBY, ACTIVE, KEYS, KEY_STRIDE, KEY_LENGTH = 0x0, 0x8, 0x1BA6, 0x38, 0x101, 0x100
PL, PL_STATE, PL_HANDLE, JOINED = 0x10, 0x118, 0x120, 3
COUNTDOWN, COUNTDOWN_CONFIG_GLOBAL, COUNTDOWN_CONFIG = 0x1B80, 0x347CEE0, 0x3CE68
SOS_KEY, PRIVACY_KEY, KEY_COUNT = 8, 19, 27
MATCHMAKER, QUICKPLAY, JOINING = 0x347CE80, 0x10BD5C, 0x10BD5D
MM_IN_SUBSYSTEM, CTX_IN_SUBSYSTEM = 0x1AF0A30, 0x1C91CD0
SETTER, SETTER_CASE0, SETTER_TABLE, PRIVACY_ID, SETTER_MAX_ID = 0x11ED0B0, 0x11ED812, 0x11EDFB0, 0, 0x92
LOOKUP, DESCRIPTOR_TABLE, DESCRIPTOR_COUNTS, COUNT_STRIDE, GROUPS, DESCRIPTOR_STRIDE = (0x11ECD60, 0x21CB040,
    0x32EC994, 0x30, 12, 0xD8)
STOP_QUICKPLAY = 0x133E6E0
PRIVACY_NAMES_TABLE, LOBBY_KEY_NAMES, DENY_NAMES, SEARCH_SLOTS, OPERATOR_NAMES = (0x21D3F28, 0x21D61C0, 0x21D52C0,
    0x21D42F0, 0x21D59A0)
STRINGS = {'privacy_mode': 0x225F7A0, 'decimal': 0x2247B30,
    'friendsOnlyDenied': 0x2263990, 'friendsAndClanDenied': 0x2263930, 'quickplayAborted': 0x225A3C8}
PRIVACY_NAMES = ['Open', 'FriendsOnly', 'InviteOnly', 'FriendsAndClan']

GAME_PINS = {
    'settings': [
        (0x1377728, 'mov rcx, qword ptr [rip + {rip}]', GAME, 'the options save: the Game object ...'),
        (0x137772F, 'add rcx, 0xac3dc', None, '... + 0xAC3DC is the settings object ...'),
        (0x1377764, 'call 0x102f7a0', None, '... passed to the settings writer'),
        (0x102F7C2, 'mov rbx, rcx', None, 'the writer: rbx = the settings'),
        (0x103005F, 'lea rdx, [rip + {rip}]', STRINGS['privacy_mode'], 'its "privacy_mode" key ...'),
        (0x1030066, 'mov r8d, dword ptr [rbx + 0x174]', None, '... is settings + 0x174 (u32)'),
        (0x13779A7, 'mov rcx, qword ptr [rip + {rip}]', GAME, 'the options load: the Game object ...'),
        (0x13779B1, 'add rcx, 0xac3dc', None, '... its settings ...'),
        (0x13779BB, 'call 0x1030260', None, '... passed to the settings reader'),
        (0x103026A, 'lea rbx, [rcx + 0xbc]', None, 'the reader: rbx = settings + 0xBC ...'),
        (0x1030B6D, 'lea rdx, [rip + {rip}]', STRINGS['privacy_mode'], '... reads "privacy_mode" ...'),
        (0x1030B9F, 'mov ecx, 2', None, '... clamps it to at most 2 ...'),
        (0x1030BA6, 'cmovl ecx, eax', None, '... (min(value, 2)) ...'),
        (0x1030BB0, 'mov dword ptr [rbx + 0xb8], ecx', None, '... into settings + 0xBC + 0xB8 = + 0x174'),
        (0x134A206, 'movsxd rax, dword ptr [rdi + 0xb8]', None, 'the settings telemetry: the privacy (settings + 0x174) ...'),
        (0x134A20D, 'mov rax, qword ptr [rcx + rax*8 + 0x21d3f28]', None, '... names it from the privacy name table'),
    ],
    'lobbyCreate': [
        (0x10916A9, 'mov r8d, dword ptr [rbp + 0xac550]', None, 'a new lobby: Game + 0xAC550 (the privacy setting) ...'),
        (0x10916B0, 'lea edx, [rsi + 0x13]', None, '... as lobby key 19 (PrivacyMode) ...'),
        (0x10916B6, 'call 0x10925d0', None, '... through the lobby key setter'),
    ],
    'lobbyKeys': [
        (0x1092606, 'lea r8, [rip + {rip}]', STRINGS['decimal'], 'the lobby key setter formats the value "%d" ...'),
        (0x1092672, 'call 0x10924d0', None, '... into the wrapper\'s key cache'),
        (0x10924E6, 'lea rbx, [rcx + 0x38]', None, 'the cache: wrapper + 0x38 ...'),
        (0x10924EA, 'imul rax, rbp, 0x101', None, '... + key * 0x101 (text, at most 0x100 bytes)'),
        (0x109251F, 'bts rax, rbp', None, 'a changed key is marked pending (posted on the host\'s countdown)'),
        (0x10928D8, 'mov rax, qword ptr [rdx + 0x110]', None, 'the lobby key getter reads the PlayFab lobby data (T+0x110) '
            'while an engine lobby exists'),
        (0x109413B, 'setae bl', None, 'the host posts pending lobby data when the countdown (wrapper + 0x1B80) runs out ...'),
        (0x1094149, 'movd xmm0, dword ptr [rax + 0x3ce68]', None, '... reset from the configured seconds'),
        (0x10941D7, 'cmp rcx, qword ptr [rax + 0xb398]', None, '... only as the lobby owner (a client never posts lobby data)'),
        (0x1094555, 'call qword ptr [r8 + 0x100]', None, 'the post (T+0x100)'),
    ],
    'joinGate': [
        (0x108BCC6, 'mov rcx, qword ptr [rip + {rip}]', CONTEXT, 'the host\'s join request check: the network context ...'),
        (0x108BCCD, 'mov edx, 0x13', None, '... lobby key 19 ...'),
        (0x108BCDA, 'add rcx, 0x1d470', None, '... of the lobby wrapper ...'),
        (0x108BCF1, 'call 0x1092950', None, '... read as a number ...'),
        (0x108BCFC, 'mov r15d, eax', None, '... (r15 = the advertised privacy)'),
        (0x108C005, 'sub r15d, 1', None, '1 (FriendsOnly) ...'),
        (0x108C009, 'je 0x108c11e', None, '... a non-friend is refused'),
        (0x108C00F, 'sub r15d, 1', None, '2 (InviteOnly) ...'),
        (0x108C013, 'je 0x108c086', None, '... a peer not on the invited list is refused'),
        (0x108C015, 'cmp r15d, 1', None, '3 (FriendsAndClan): a non-friend non-clan peer is refused; 0 (Open) admits '
            'anyone'),
        (0x108C02B, 'lea rdx, [rip + {rip}]', STRINGS['friendsAndClanDenied'], '"... when in PrivacyMode_FriendsAndClan"'),
        (0x108C142, 'lea rdx, [rip + {rip}]', STRINGS['friendsOnlyDenied'], '"... when in PrivacyMode_FriendsOnly"'),
        (0x108C159, 'mov r8d, 0xa', None, 'deny reason 10 (PrivacySettings)'),
        (0x108C1E2, 'cmp byte ptr [rax + 0x1f868], r14b', None, 'the network context +0x1F868 (singleplayer mode) ...'),
        (0x108C1EF, 'mov r8d, 9', None, '... refuses every join (reason 9, HostInSingleplayerMode)'),
    ],
    'quickplayFilter': [
        (0x133ACF9, 'xor r9d, r9d', None, 'Quickplay\'s lobby search: value 0 ...'),
        (0x133ACFC, 'mov dword ptr [rsp + 0x20], 2', None, '... operator 2 (Equal) ...'),
        (0x133AD04, 'lea r8d, [r15 + 0x12]', None, '... lobby key 19 (PrivacyMode) ...'),
        (0x133AD08, 'call 0x13f16f0', None, '... a numeric search filter: only Open lobbies are found'),
        (0x13F171F, 'lea rcx, [rip + {rip}]', SEARCH_SLOTS, 'the numeric filter names the key\'s search slot ...'),
        (0x13F1770, 'call qword ptr [r10 + 0x188]', None, '... through the engine\'s filter builder (T+0x188)'),
        (0x133D34A, 'mov rax, qword ptr [r8 + rsi*8 + 0x21d59a0]', None, 'the filter telemetry names the operator from '
            'the operator table'),
    ],
    'quickplay': [
        (0x14899E2, 'mov rbx, qword ptr [rip + {rip}]', MATCHMAKER, 'the galactic war UI: the matchmaker ...'),
        (0x1489A0C, 'mov byte ptr [rbx + 0x10bd5c], 1', None, '... Quickplay on (+0x10BD5C) ...'),
        (0x1489A13, 'call 0x133a1b0', None, '... and its start'),
        (0x13D4ABD, 'mov rdi, qword ptr [rip + {rip}]', MATCHMAKER, 'the "quick_play" activity: the matchmaker ...'),
        (0x13D4ADD, 'mov byte ptr [rdi + 0x10bd5c], 1', None, '... Quickplay on ...'),
        (0x13D4AE4, 'call 0x133a1b0', None, '... and its start'),
        (0x133A1CA, 'mov rcx, qword ptr [rax + 0xb3a8]', None, 'the start returns at once for a client of another '
            'host\'s session ...'),
        (0x133A1D6, 'cmp rcx, qword ptr [rax + 0xb398]', None, '... (session host != the local peer)'),
        (0x13F780C, 'lea rcx, [r15 + 0x1af0a30]', None, 'the frame update ticks the matchmaker (subsystem + 0x1AF0A30) ...'),
        (0x13F7816, 'call 0x13374b0', None, '... (its update) ...'),
        (0x13F7858, 'lea rbx, [r15 + 0x1c91cd0]', None, '... next to the network context (subsystem + 0x1C91CD0)'),
        (0x1337AD1, 'mov byte ptr [rsi + 0x10bd5c], r14b', None, 'the update ends Quickplay once this machine is a '
            'client of another session (it joined) ...'),
        (0x1337AF2, 'cmp dword ptr [rax + 0xac21c], 3', None, '... or the game left the ship ...'),
        (0x1337B26, 'mov byte ptr [rsi + 0x10bd5c], r14b', None, '... (cleared)'),
        (0x1337B2D, 'cmp byte ptr [rsi + 0x10bd5d], r14b', None, '+0x10BD5D: a found lobby is being joined'),
        (0x1337B43, 'call 0x133c6c0', None, '(the join step)'),
        (0x1337B77, 'mov byte ptr [rsi + 0x10bd5c], r14b', None, 'and ends it when the lobby is full'),
    ],
    'stopQuickplay': [
        (0x133E6E0, 'push rbx', None, 'set_quickplay(matchmaker, on, ...) ...'),
        (0x133E6E2, 'sub rsp, 0x70', None, ''),
        (0x133E6E6, 'mov r10d, r8d', None, ''),
        (0x133E6E9, 'mov rbx, rcx', None, ''),
        (0x133E6EC, 'cmp byte ptr [rcx + 0x10bd5c], dl', None, '... nothing when already in that state ...'),
        (0x133E6F2, 'je 0x133e92c', None, ''),
        (0x133E6F8, 'mov byte ptr [rcx + 0x10bd5c], dl', None, '... the flag := on ...'),
        (0x133E6FE, 'test dl, dl', None, ''),
        (0x133E700, 'je 0x133e73d', None, '... off: ...'),
        (0x133E73D, 'mov eax, dword ptr [rcx + 0x68c]', None, '... the search state (for the abort telemetry) ...'),
        (0x133E8DF, 'lea rdx, [rip + {rip}]', STRINGS['quickplayAborted'], '... "QuickplayAborted" ...'),
        (0x133E927, 'jmp 0x133a940', None, '... then the matchmaker reset (it also cancels a join in progress)'),
        (0x1482163, 'mov rax, qword ptr [rip + {rip}]', MATCHMAKER, 'closing the galactic war map: the matchmaker ...'),
        (0x148216A, 'cmp byte ptr [rax + 0x10bd5c], 0', None, '... while Quickplay is on ...'),
        (0x1482173, 'mov byte ptr [rsp + 0x38], 0', None, '... argument 8: 0 ...'),
        (0x1482178, 'xor edx, edx', None, '... off ...'),
        (0x148217A, 'mov r9d, 0x7fffffff', None, '... 0x7FFFFFFF ...'),
        (0x1482180, 'mov byte ptr [rsp + 0x28], 0', None, '... argument 6: 0 ...'),
        (0x1482185, 'mov r8d, 0xffffffff', None, '... -1 ...'),
        (0x148218B, 'mov rcx, rax', None, ''),
        (0x148218E, 'call 0x133e6e0', None, '... the game\'s own stop'),
        (0x14897A2, 'mov rbx, qword ptr [rip + {rip}]', MATCHMAKER, 'the map\'s cancel input: the same call ...'),
        (0x14897D1, 'call 0x133e6e0', None, '... with the same arguments'),
    ],
    'sos': [
        (0x67A9B4, 'mov rax, qword ptr [rbx + 0xb3a8]', None, 'an SOS Beacon activates: on the session host only ...'),
        (0x67A9D8, 'mov edx, 8', None, '... lobby key 8 (SOSBeacons) ...'),
        (0x67A9E4, 'lea r8d, [rdx - 7]', None, '... := 1 ...'),
        (0x67A9E8, 'call 0x10925d0', None, ''),
        (0x67A9ED, 'xor r8d, r8d', None, '... and the privacy key := 0 (Open) ...'),
        (0x67A9F3, 'lea edx, [r8 + 0x13]', None, '... (key 19) ...'),
        (0x67A9F7, 'call 0x134fca0', None, '... whatever the setting'),
        (0x134FCC0, 'cmp edi, 0x13', None, 'setting key 19 ...'),
        (0x134FCC5, 'lea edx, [rdi - 0xb]', None, '... reads key 8 ...'),
        (0x134FCCB, 'call 0x1092950', None, ''),
        (0x134FCD2, 'jne 0x134fd05', None, '... an active SOS Beacon keeps key 19 at 0'),
        (0x134FCFD, 'mov ebx, dword ptr [rax + 0xac550]', None, 'SOSBeacons 0: key 19 returns to the setting'),
        (0x67AA69, 'lea edx, [r8 + 8]', None, 'an SOS Beacon ends: key 8 := 0 ...'),
        (0x67AA81, 'mov r8d, dword ptr [rax + 0xac550]', None, '... key 19 := the setting'),
        (0x67AA88, 'call 0x134fca0', None, ''),
    ],
    'setter': [
        (0x11ED0B0, 'test r8, r8', None, 'set_setting(settings, id, &value): no value, nothing ...'),
        (0x11ED0B3, 'je 0x11edfaf', None, ''),
        (0x11ED0C0, 'mov ebp, edx', None, '... ebp = the id ...'),
        (0x11ED0C2, 'mov rsi, rcx', None, '... rsi = the settings ...'),
        (0x11ED0D9, 'call 0x11ecd60', None, '... the id\'s descriptor ...'),
        (0x11ED0F3, 'movss xmm2, dword ptr [rax + 0x34]', None, '... read unchecked (the id must have one) ...'),
        (0x11ED102, 'cmp ebp, 0x92', None, '... ids 0 - 0x92 ...'),
        (0x11ED11A, 'mov eax, dword ptr [r15 + rbp*4 + 0x11edfb0]', None, '... through the jump table'),
        (0x11ED812, 'mov edi, dword ptr [rbx]', None, 'case 0: the value ...'),
        (0x11ED814, 'mov edx, 8', None, ''),
        (0x11ED819, 'mov rbx, qword ptr [rip + {rip}]', CONTEXT, '... the network context ...'),
        (0x11ED820, 'mov dword ptr [rsi + 0x174], edi', None, '... settings + 0x174 (privacy_mode) := value ...'),
        (0x11ED826, 'lea rcx, [rbx + 0x1d470]', None, '... the lobby wrapper ...'),
        (0x11ED82D, 'call 0x1092950', None, '... key 8 (SOSBeacons) ...'),
        (0x11ED83B, 'test eax, eax', None, ''),
        (0x11ED83D, 'cmovne edi, edx', None, '... an active SOS Beacon advertises 0 ...'),
        (0x11ED840, 'mov edx, 0x13', None, '... lobby key 19 ...'),
        (0x11ED845, 'mov r8d, edi', None, ''),
        (0x11ED848, 'call 0x10925d0', None, '... := the value (cached; the host posts it)'),
        (0x11ED84D, 'jmp 0x11edf94', None, '... and returns'),
        (0x11ECD6F, 'lea rsi, [rip + {rip}]', DESCRIPTOR_TABLE, 'the descriptor lookup: 12 group arrays ...'),
        (0x11ECD7B, 'lea r11, [rip + {rip}]', DESCRIPTOR_COUNTS, '... their counts (0x30 apart) ...'),
        (0x11ECDA2, 'imul rdx, rcx, 0xd8', None, '... entries 0xD8 apart ...'),
        (0x11ECDA9, 'cmp dword ptr [r10 + rdx], edi', None, '... whose first u32 is the id ...'),
        (0x11ECDB9, 'add r11, 0x30', None, ''),
        (0x11ECDC1, 'cmp r9d, 0xc', None, '... 12 groups ...'),
        (0x11ECDC7, 'xor eax, eax', None, '... none: NULL'),
        (0xADFF0E, 'mov rbx, qword ptr [rip + {rip}]', GAME, 'the game calls the setter on the LIVE settings too: the '
            'Game object ...'),
        (0xADFF15, 'add rbx, 0xac3dc', None, '... + 0xAC3DC ...'),
        (0xADFF67, 'mov rcx, rbx', None, '...'),
        (0xADFFC6, 'call 0x11ed0b0', None, '... set_setting(live settings, 0x15, &3)'),
        (0x1805363, 'mov rcx, qword ptr [rdi + 0xb28]', None, 'an options page: its settings copy ...'),
        (0x180536C, 'call 0x11ed0b0', None, '... set_setting(copy, id, &value) as the player changes an option'),
        (0x1996352, 'lea r13, [rdi + 0x141e68]', None, 'the options menu\'s working copy ...'),
        (0x199637B, 'lea rax, [r8 + 0xac3dc]', None, '... filled from the live settings when it opens'),
        (0x1997CFA, 'add r8, 0xac3dc', None, 'the commit copies it back into the live settings ...'),
        (0x1997D88, 'call 0x1377bb0', None, '... and saves them'),
    ],
}
# Data pins: exact bytes that are not instructions (the setter's jump table entry for id 0).
DATA_PINS = [(SETTER_TABLE, struct.pack('<I', SETTER_CASE0), 'the setter\'s jump table: id 0 -> 0x11ED812 (privacy)')]


def cstr_at(image, rva):
    return image.cstr(rva) if rva is not None else None


def name_table(image, table, count):
    return [cstr_at(image, image.pointer_rva(table + 8 * i)) for i in range(count)]


def read_key(mem, wrapper, key):
    raw = mem.read(wrapper + KEYS + key * KEY_STRIDE, KEY_STRIDE)
    return None if raw is None else raw.split(b'\0')[0].decode('latin-1')


def descriptor(mem, wanted):
    """The game's own lookup (0x11ECD60) replayed: (group, index) of the first entry whose id is `wanted`, or None."""
    g = mem.game
    for k in range(GROUPS):
        count = mem.u32(g + DESCRIPTOR_COUNTS + COUNT_STRIDE * k) or 0
        array = mem.ptr(g + DESCRIPTOR_TABLE + 8 * k)
        if not array:
            continue
        for i in range(count):
            if mem.u32(array + i * DESCRIPTOR_STRIDE) == wanted:
                return {'group': k, 'index': i}
    return None


def observe(name: str) -> dict:
    mem = base.Mem(name)
    g = mem.game
    game = mem.ptr(g + GAME)
    ctx = mem.ptr(g + CONTEXT)
    mm = mem.ptr(g + MATCHMAKER)
    wrapper = ctx + WRAPPER
    engine = mem.ptr(wrapper + ENGINE_LOBBY)
    pl = engine and mem.ptr(engine + PL)
    out = {'snapshot': name,
        'gameState': mem.u32(game + STATE),
        'privacySetting': mem.u32(game + SETTINGS + PRIVACY),
        'privacyName': PRIVACY_NAMES[mem.u32(game + SETTINGS + PRIVACY)],
        'singleplayer': mem.read(ctx + SINGLEPLAYER, 1)[0],
        'localPeer': '%016X' % mem.u64(ctx + LOCAL_PEER), 'hostPeer': '%016X' % mem.u64(ctx + HOST_PEER),
        'wrapperActive': mem.read(wrapper + ACTIVE, 1)[0], 'engineLobby': engine is not None,
        'platformLobby': mem.ptr(wrapper + PLATFORM_LOBBY) is not None,
        'playfabState': pl and mem.u32(pl + PL_STATE), 'handleSet': bool(pl and mem.u64(pl + PL_HANDLE)),
        'lobbyKeys': {str(k): read_key(mem, wrapper, k) for k in range(KEY_COUNT) if k not in (0, 2, 10)},
        'pendingKeys': [mem.u64(wrapper + 0x18), mem.u64(wrapper + 0x20)],
        'countdownSeconds': mem.u32(mem.ptr(g + COUNTDOWN_CONFIG_GLOBAL) + COUNTDOWN_CONFIG),
        'quickplay': mem.read(mm + QUICKPLAY, 1)[0], 'joining': mem.read(mm + JOINING, 1)[0],
        'matchmakerMinusContext': mm - ctx,
        'privacyDescriptor': descriptor(mem, PRIVACY_ID)}
    mem.close()
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [dict(game.prove(*row), module='game') for row in rows] for group, rows in GAME_PINS.items()}
    data_pins = []
    for rva, raw, role in DATA_PINS:
        if game.data[rva:rva + len(raw)] != raw:
            raise ValueError('data at %x changed' % rva)
        data_pins.append({'rva': rva, 'bytes': raw.hex(), 'asm': 'data', 'role': role, 'module': 'game'})
    # The strings and name tables the pins point at.
    texts = {key: game.cstr(rva) for key, rva in STRINGS.items()}
    if texts['privacy_mode'] != 'privacy_mode' or texts['decimal'] != '%d' or texts['quickplayAborted'] != 'QuickplayAborted':
        raise ValueError('a pinned string moved: %r' % texts)
    if 'PrivacyMode_FriendsOnly' not in texts['friendsOnlyDenied'] or 'PrivacyMode_FriendsAndClan' not in \
            texts['friendsAndClanDenied']:
        raise ValueError('the join refusal texts moved')
    privacy_names = name_table(game, PRIVACY_NAMES_TABLE, 5)
    if privacy_names != PRIVACY_NAMES + ['Count']:
        raise ValueError('the privacy names changed: %r' % privacy_names)
    lobby_keys = name_table(game, LOBBY_KEY_NAMES, KEY_COUNT + 1)
    if (lobby_keys[SOS_KEY], lobby_keys[PRIVACY_KEY], lobby_keys[KEY_COUNT]) != ('SOSBeacons', 'PrivacyMode', 'Count'):
        raise ValueError('the lobby key names changed: %r' % lobby_keys)
    deny = name_table(game, DENY_NAMES, 17)
    if (deny[9], deny[10]) != ('HostInSingleplayerMode', 'PrivacySettings'):
        raise ValueError('the join refusal reasons changed: %r' % deny)
    operators = name_table(game, OPERATOR_NAMES, 6)
    if operators[2] != 'Equal':
        raise ValueError('the filter operators changed: %r' % operators)
    slots = {k: struct.unpack_from('<II', game.data, SEARCH_SLOTS + 8 * k) for k in range(KEY_COUNT)}
    if slots[PRIVACY_KEY] != (6, 2) or slots[SOS_KEY] != (8, 2):
        raise ValueError('the search slots changed: %r' % slots)
    flat = [p for rows in pins.values() for p in rows] + data_pins
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    snapshots = [observe(name) for name in SNAPSHOTS]
    for s in snapshots:
        keyed = s['lobbyKeys']
        if s['privacyDescriptor'] is None:
            raise ValueError('%s: the setter cannot find the privacy id' % s['snapshot'])
        if keyed[str(PRIVACY_KEY)] != str(s['privacySetting']) or keyed[str(SOS_KEY)] != '0':
            raise ValueError('%s: the advertised privacy is not the setting' % s['snapshot'])
        if s['matchmakerMinusContext'] != MM_IN_SUBSYSTEM - CTX_IN_SUBSYSTEM:
            raise ValueError('%s: the matchmaker is not the subsystem\'s' % s['snapshot'])
        if s['quickplay'] or s['joining'] or s['singleplayer']:
            raise ValueError('%s: unexpected matchmaking state' % s['snapshot'])
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'nativeCalls': 0,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA}, 'exe': {'sha256': base.PROFILE_EXE_SHA},
        'game': {'global': '0x%X' % GAME, 'state': STATE, 'ship': SHIP, 'settings': SETTINGS},
        'settings': {'privacy': PRIVACY, 'size': SETTINGS_SIZE, 'loadClamp': 2},
        'privacy': {'names': PRIVACY_NAMES, 'open': 0, 'friendsOnly': 1, 'inviteOnly': 2, 'friendsAndClan': 3,
            'nameTable': '0x%X' % PRIVACY_NAMES_TABLE},
        'context': {'global': '0x%X' % CONTEXT, 'localPeer': LOCAL_PEER, 'hostPeer': HOST_PEER, 'wrapper': WRAPPER,
            'singleplayer': SINGLEPLAYER},
        'wrapper': {'engineLobby': ENGINE_LOBBY, 'platformLobby': PLATFORM_LOBBY, 'active': ACTIVE, 'keys': KEYS,
            'keyStride': KEY_STRIDE, 'keyLength': KEY_LENGTH, 'countdown': COUNTDOWN},
        'playfab': {'lobby': PL, 'state': PL_STATE, 'joined': JOINED, 'handle': PL_HANDLE},
        'lobbyKeys': {'names': lobby_keys[:KEY_COUNT], 'sosBeacons': SOS_KEY, 'privacyMode': PRIVACY_KEY,
            'searchSlots': {str(k): list(v) for k, v in slots.items()}},
        'joinDenyReasons': deny, 'filterOperators': operators,
        'matchmaker': {'global': '0x%X' % MATCHMAKER, 'quickplay': QUICKPLAY, 'joining': JOINING,
            'inSubsystem': MM_IN_SUBSYSTEM, 'contextInSubsystem': CTX_IN_SUBSYSTEM},
        'setter': {'rva': '0x%X' % SETTER, 'case0': '0x%X' % SETTER_CASE0, 'table': '0x%X' % SETTER_TABLE,
            'privacyId': PRIVACY_ID, 'maxId': SETTER_MAX_ID,
            'signature': 'void set_setting(void *settings, uint32_t id, const void *value)',
            'lookup': {'rva': '0x%X' % LOOKUP, 'table': '0x%X' % DESCRIPTOR_TABLE, 'counts': '0x%X' % DESCRIPTOR_COUNTS,
                'countStride': COUNT_STRIDE, 'groups': GROUPS, 'stride': DESCRIPTOR_STRIDE}},
        'stopQuickplay': {'rva': '0x%X' % STOP_QUICKPLAY,
            'signature': 'void set_quickplay(void *matchmaker, uint8_t on, int32_t, int32_t, uint8_t, uint8_t, uint8_t, '
                'uint8_t)', 'stopArguments': [0, -1, 0x7FFFFFFF, 0, 0, 0, 0]},
        'pins': pins, 'dataPins': data_pins, 'pinnedBytesMismatchPerSnapshot': relocation, 'snapshots': snapshots,
        'facts': {
            'setting': 'privacy is a user SETTING (options "privacy_mode", saved with the options; a load clamps it to '
                '0-2) at settings + 0x174, the settings object at Game + 0xAC3DC [C]; Open 0, FriendsOnly 1, InviteOnly '
                '2, FriendsAndClan 3 [C: the name table and the join gate cases]',
            'advertised': 'the host advertises it as lobby key 19 (PrivacyMode; numeric search slot 6), cached as text at '
                'wrapper + 0x38 + 19 * 0x101 and posted when the countdown (30 s in every snapshot) runs out; a new lobby '
                'starts with the setting [C]; every snapshot advertises its setting [O]',
            'joinGate': 'the host refuses joins by the ADVERTISED value (lobby key 19): FriendsOnly non-friends, '
                'InviteOnly non-invited, FriendsAndClan non-friend non-clan; Open admits anyone [C]',
            'quickplay': 'Quickplay finds only lobbies whose key 19 equals 0 (Open) [C]; it runs while matchmaker '
                '+0x10BD5C is set, set only by the galactic war UI and the quick_play activity [C]; the client\'s own '
                'privacy is not read by Quickplay [C: no matchmaker reader of the setting]',
            'sos': 'an SOS Beacon makes the host advertise Open (key 19 = 0) whatever the setting, until it ends [C]',
            'setter': 'game.dll 0x11ED0B0 case 0 is the game\'s own privacy change: settings + 0x174 and lobby key 19, '
                'nothing else; the options menu calls it on its working copy, the game also on the live settings '
                '(0xADFFC6) [C]; the id 0 descriptor exists in every snapshot [O]',
            'stopQuickplay': 'game.dll 0x133E6E0 with on = 0 is the game\'s own Quickplay stop (the map\'s cancel input '
                'and the map closing call it with the same arguments) [C]',
            'replicated': 'privacy is visible to everyone through lobby data (key 19 and the search attribute) [C]; the '
                'Runtime\'s hd2rt member property exists only inside a joined lobby, so it cannot gate Quickplay or the '
                'host\'s join gate before a stranger is a member [C]'}}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), len(flat), 'pins')


if __name__ == '__main__':
    main()
