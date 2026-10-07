"""Read the game's Wwise sound banks (wwise_bank resources) offline: chunks, HIRC objects, events and actions, the Init
bank's STMG (state groups, switch groups, game parameters), the sound-structure nodes (parent, children, switch and
state groups, RTPCs) and the Stingray wwise_metadata records. Pure parsing, no game process; reused by
scripts/research_sound_events.py (docs/research/sound-events-F5FEE03DCFDB.md) and scripts/research_weapon_sounds.py.

The bank layout is this build's (Wwise as shipped with build F5FEE03DCFDB): a Stingray header (magic A5F4A378, u32,
u64 id) before BKHD; HIRC objects are (u8 kind, u32 size, u32 id, body); a Sound's source is 18 bytes (u32 plugin,
u8 stream type, u64 source id, u32 in-memory size, u8 bits) plus u32 size + data for a source plugin. Every node
parser is checked by the caller against exact consumption of the object (`Node.exact`); nothing parsed short is used.
"""
from __future__ import annotations

import struct

# HIRC object kinds (Wwise HircType).
KINDS = {1: 'State', 2: 'Sound', 3: 'Action', 4: 'Event', 5: 'RandomSequence', 6: 'Switch', 7: 'ActorMixer', 8: 'Bus',
    9: 'Layer', 10: 'MusicSegment', 11: 'MusicTrack', 12: 'MusicSwitch', 13: 'MusicRandomSequence', 14: 'Attenuation',
    15: 'DialogueEvent', 16: 'FxShareSet', 17: 'FxCustom', 18: 'AuxBus', 19: 'LFO', 20: 'Envelope',
    21: 'AudioDevice', 22: 'TimeMod'}
EVENT, ACTION, SOUND = 4, 3, 2
# Action types: the high byte is the action, the low byte its scope (Wwise AkActionType).
ACTIONS = {0x01: 'stop', 0x02: 'pause', 0x03: 'resume', 0x04: 'play', 0x05: 'play_and_continue', 0x06: 'mute',
    0x07: 'unmute', 0x08: 'set_pitch', 0x09: 'reset_pitch', 0x0A: 'set_volume', 0x0B: 'reset_volume',
    0x0C: 'set_bus_volume', 0x0D: 'reset_bus_volume', 0x0E: 'set_lpf', 0x0F: 'reset_lpf', 0x10: 'use_state',
    0x11: 'unuse_state', 0x12: 'set_state', 0x13: 'set_game_parameter', 0x14: 'reset_game_parameter',
    0x19: 'set_switch', 0x1A: 'toggle_bypass', 0x1B: 'reset_bypass', 0x1C: 'break', 0x1D: 'trigger', 0x1E: 'seek',
    0x1F: 'release', 0x20: 'set_hpf', 0x21: 'play_event', 0x22: 'reset_playlist', 0x30: 'reset_hpf', 0x31: 'set_fx'}
# Scope (low byte): 1 the posting game object (switches), 2 every game object ("E"), 3 the posting game object
# ("E_O"), 4 every object everywhere ("ALL"), 5 every object on the posting game object ("ALL_O").
SCOPES = {1: 'object', 2: 'global', 3: 'object', 4: 'global', 5: 'object_all', 0: 'global'}
# Set state is global by nature (a state is a sound-engine-wide value).
GLOBAL_ACTIONS = {0x10, 0x11, 0x12}


class Reader:
    __slots__ = ('b', 'o')

    def __init__(self, b, o=0):
        self.b, self.o = b, o

    def u8(self):
        v = self.b[self.o]
        self.o += 1
        return v

    def u16(self):
        v = struct.unpack_from('<H', self.b, self.o)[0]
        self.o += 2
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.b, self.o)[0]
        self.o += 4
        return v

    def f32(self):
        v = struct.unpack_from('<f', self.b, self.o)[0]
        self.o += 4
        return v

    def var(self):
        """Wwise variable-length unsigned (7 bits a byte, high bit = more)."""
        v = 0
        while True:
            c = self.u8()
            v = (v << 7) | (c & 0x7F)
            if not c & 0x80:
                return v

    def skip(self, n):
        if n < 0 or self.o + n > len(self.b):
            raise ValueError('read past the object')
        self.o += n

    def ids(self, n):
        out = list(struct.unpack_from('<%dI' % n, self.b, self.o))
        self.o += 4 * n
        return out


# ------------------------------------------------------------------------------------------------------ chunks --
def chunks(raw):
    """[(tag, offset of the data, size)] from BKHD on; ValueError when there is no BKHD."""
    o = raw.find(b'BKHD')
    if o < 0:
        raise ValueError('no BKHD')
    out = []
    while o + 8 <= len(raw):
        tag, size = raw[o:o + 4], struct.unpack_from('<I', raw, o + 4)[0]
        if o + 8 + size > len(raw):
            raise ValueError('chunk %r runs past the bank' % tag)
        out.append((tag.decode('latin-1'), o + 8, size))
        o += 8 + size
    return out


def hirc(raw):
    """{id: (kind, body)} of a bank's HIRC (the body after the id). {} when the bank has none."""
    for tag, o, size in chunks(raw):
        if tag != 'HIRC':
            continue
        count = struct.unpack_from('<I', raw, o)[0]
        out, p = {}, o + 4
        for _ in range(count):
            kind = raw[p]
            length, oid = struct.unpack_from('<II', raw, p + 1)
            out[oid] = (kind, raw[p + 9:p + 5 + length])
            p += 5 + length
        if p != o + size:
            raise ValueError('HIRC object sizes do not add up')
        return out
    return {}


# ------------------------------------------------------------------------------------------- events, actions --
def event_actions(body):
    """An Event's action ids (u8 count, u32 ids); ValueError unless the body is exactly that."""
    n = body[0]
    if len(body) != 1 + 4 * n:
        raise ValueError('unexpected event body')
    return list(struct.unpack_from('<%dI' % n, body, 1))


def action(body):
    """An Action: {type (u16), action, scope, target, isBus, props}; set_state / set_switch add group and value."""
    r = Reader(body)
    t = r.u16()
    target = r.u32()
    is_bus = r.u8()
    n = r.u8()
    ids = [r.u8() for _ in range(n)]
    vals = r.ids(n)
    n = r.u8()
    r.skip(n + 8 * n)
    out = {'type': t, 'action': ACTIONS.get(t >> 8, 'action_%02X' % (t >> 8)), 'scope': SCOPES.get(t & 0xFF, 'unknown'),
        'target': target, 'isBus': is_bus, 'props': dict(zip(ids, vals))}
    if (t >> 8) in GLOBAL_ACTIONS:
        out['scope'] = 'global'
    if t >> 8 in (0x12, 0x19) and r.o + 8 <= len(body):
        out['group'], out['value'] = struct.unpack_from('<II', body, r.o)
    return out


# What a set of actions does beyond the posting game object (scope 2 / 4 or a sound-engine-wide state):
#   'state'      set_state / use_state / unuse_state: an engine-wide state stays changed;
#   'parameter'  a global game parameter set or reset: stays changed;
#   'mix'        a global volume / pitch / LPF / HPF / bus-volume / mute change the same actions do not reset;
#   'pause'      a global pause the same actions do not resume;
#   'stop'       a global stop of an element (every game object's instances of it): transient.
# A global set and its reset in the same event (a duck) is transient and not listed.
_SET_RESET = {0x08: 0x09, 0x0A: 0x0B, 0x0C: 0x0D, 0x0E: 0x0F, 0x20: 0x30, 0x06: 0x07}
PERSISTENT = ('state', 'parameter', 'mix', 'pause')


def effects(actions):
    """The global effects of a list of action dicts (wwise_banks.action): a sorted list of the names above."""
    out = set()
    done = {(a['type'] >> 8, a['target']) for a in actions if a['scope'] == 'global'}
    for a in actions:
        kind = a['type'] >> 8
        if kind in GLOBAL_ACTIONS:
            out.add('state')
        elif a['scope'] != 'global':
            continue
        elif kind in (0x13, 0x14):
            out.add('parameter')
        elif kind in _SET_RESET and (_SET_RESET[kind], a['target']) not in done:
            out.add('mix')
        elif kind == 0x02 and (0x03, a['target']) not in done:
            out.add('pause')
        elif kind == 0x01:
            out.add('stop')
    return sorted(out)


# ------------------------------------------------------------------------------------------------ the Init bank --
def stmg(body):
    """The Init bank's STMG: {volumeThreshold, maxVoices, maxVirtualVoices, stateGroups [{id, defaultTransitionMs,
    transitions [(from, to, ms)]}], switchGroups [{id, parameter, parameterType, points [(value, switch, curve)]}],
    parameters [{id, default, rampType, rampUp, rampDown, builtIn}], textures}. ValueError unless consumed exactly."""
    r = Reader(body, 2)
    out = {'volumeThreshold': r.f32(), 'maxVoices': r.u16(), 'maxVirtualVoices': r.u16()}
    groups = []
    for _ in range(r.u32()):
        gid, ms, n = r.u32(), r.u32(), r.u32()
        groups.append({'id': gid, 'defaultTransitionMs': ms,
            'transitions': [tuple(r.ids(3)) for _ in range(n)]})
    out['stateGroups'] = groups
    switches = []
    for _ in range(r.u32()):
        gid, parameter, ptype, n = r.u32(), r.u32(), r.u8(), r.u32()
        points = []
        for _ in range(n):
            value = r.f32()
            switch, curve = r.u32(), r.u32()
            points.append((value, switch, curve))
        switches.append({'id': gid, 'parameter': parameter, 'parameterType': ptype, 'points': points})
    out['switchGroups'] = switches
    parameters = []
    for _ in range(r.u32()):
        pid, value, ramp, up, down, builtin = struct.unpack_from('<IfIffB', body, r.o)
        r.o += 21
        parameters.append({'id': pid, 'default': value, 'rampType': ramp, 'rampUp': up, 'rampDown': down,
            'builtIn': builtin})
    out['parameters'] = parameters
    out['textures'] = r.u32()
    if out['textures'] or r.o != len(body):
        raise ValueError('STMG not consumed exactly (%d of %d)' % (r.o, len(body)))
    return out


# --------------------------------------------------------------------------------------------- sound structure --
class Node:
    """A sound-structure object's links: parent, bus, children, the RTPCs (game parameter, target property id), the
    state groups (group, states) and, for a switch container, its group (type 0 switch, 1 state), default and the
    switch values it lists. `exact` is True when the parse consumed the whole object."""
    __slots__ = ('kind', 'parent', 'bus', 'children', 'rtpcs', 'states', 'switchGroup', 'switchType', 'switches',
        'default', 'props', 'exact', 'sourcePlugin', 'layerParameters', 'triggers')

    def __init__(self, kind):
        self.kind = kind
        self.parent = self.bus = self.switchGroup = self.switchType = self.default = self.sourcePlugin = None
        self.children, self.rtpcs, self.states, self.switches, self.layerParameters, self.triggers = [], [], [], [], [], []
        self.props = {}
        self.exact = False


def _rtpcs(r, node):
    for _ in range(r.u16()):
        rid = r.u32()
        r.u8()
        r.u8()
        param = r.var()
        r.u32()
        r.u8()
        size = r.u16()
        r.skip(12 * size)
        node.rtpcs.append((rid, param))


def _node_base(r, node):
    r.u8()
    n = r.u8()
    if n:
        r.skip(1 + 6 * n)
    r.u8()
    n = r.u8()
    r.skip(6 * n)
    node.bus, node.parent = r.u32(), r.u32()
    r.u8()
    n = r.u8()
    ids = [r.u8() for _ in range(n)]
    node.props = dict(zip(ids, r.ids(n)))
    n = r.u8()
    r.skip(n + 8 * n)
    bits = r.u8()
    if bits & 1 and bits & 2:
        b3 = r.u8()
        if b3 & 0x60:
            r.u8()
            r.f32()
            r.skip(16 * r.u32())
            n = r.u32()
            r.skip(8 * n + 12 * n)
    if r.u8() & 8:
        r.skip(16)
    r.u32()
    r.skip(6)
    for _ in range(r.var()):
        r.var()
        r.skip(2)
    for _ in range(r.var()):
        group = r.u32()
        r.u8()
        states = []
        for _ in range(r.var()):
            states.append(r.u32())
            k = r.u16()
            r.skip(6 * k)
        node.states.append((group, states))
    _rtpcs(r, node)


def _children(r, node):
    node.children = r.ids(r.u32())


def node(kind, body):
    """The links of a Sound, RandomSequence, Switch, ActorMixer, Layer or a music node; None for other kinds. Raises on
    a malformed object; check `exact` before use."""
    r = Reader(body)
    n = Node(kind)
    if kind == 2:
        n.sourcePlugin = r.u32()
        r.skip(14)
        if n.sourcePlugin & 0xF == 2:
            r.skip(r.u32())
        _node_base(r, n)
    elif kind == 7:
        _node_base(r, n)
        _children(r, n)
    elif kind == 5:
        _node_base(r, n)
        r.skip(24)
        _children(r, n)
        r.skip(8 * r.u16())
    elif kind == 6:
        _node_base(r, n)
        n.switchType, n.switchGroup, n.default = r.u8(), r.u32(), r.u32()
        r.u8()
        _children(r, n)
        for _ in range(r.u32()):
            n.switches.append(r.u32())
            r.skip(4 * r.u32())
        r.skip(13 * r.u32())
    elif kind == 9:
        _node_base(r, n)
        _children(r, n)
        for _ in range(r.u32()):
            r.u32()
            _rtpcs(r, n)
            rid = r.u32()
            r.u8()
            n.layerParameters.append(rid)
            for _ in range(r.u32()):
                r.u32()
                r.skip(12 * r.u32())
        r.u8()
    else:
        return None
    n.exact = r.o == len(body)
    return n


# --------------------------------------------------------------------------------------------- wwise_metadata --
def metadata(raw):
    """A Stingray wwise_metadata resource: an 8-byte header (magic A5F4A378, u32 size of the records) then 28-byte
    records; returns {event id: record tuple (id, f32, f32, f32, u32, u32, u32)}."""
    magic, size = struct.unpack_from('<II', raw, 0)
    if magic != 0x78A3F4A5 or size != len(raw) - 8 or size % 28:
        raise ValueError('unexpected wwise_metadata layout')
    out = {}
    for o in range(8, len(raw), 28):
        rec = struct.unpack_from('<IfffIII', raw, o)
        out[rec[0]] = rec
    return out


def fnv1(name):
    """The Wwise id of a name (AK GetIDFromString: FNV-1 32 of the lower-cased name)."""
    if isinstance(name, str):
        name = name.encode('utf-8')
    h = 0x811C9DC5
    for c in name.lower():
        h = ((h * 0x01000193) & 0xFFFFFFFF) ^ c
    return h
