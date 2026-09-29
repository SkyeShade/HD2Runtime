"""Trace the health / damage / death / kill-credit pipeline through the unpacked game.dll image.
Read-only; nothing writes and nothing touches a live process.

The on-disk game.dll is packed; the retained snapshot holds the unpacked image the game runs.
This script re-derives, from that image and targeted reads of the three retained ship snapshots:

* The HealthComponent manager chain: the global, its entity->index hash, the partitioned dense
  record array (0x1B8 bytes per record), the parallel 0x1C-byte state array and descriptor array,
  and how records are added, activated, moved and swap-removed.
* The damage pipeline: producer -> damage-system FIFO queue (0x70-byte events) -> consumer ->
  damage apply, with every per-hit field that is persisted into the health record.
* Death, life state, kill credit (mission stat maps keyed by the creditor's peer id), healing,
  and every multiplier read at damage-application time (for the per-hit scaling verdict).

Every relationship is pinned as exact instruction bytes at exact RVAs, and each pin is re-proven to
be a real instruction boundary by recursive-descent decoding from its function start. Scans are
re-derived with a memory-light RIP-displacement search validated against the image's .pdata.
Requires the research-only packages capstone and numpy.
"""
from __future__ import annotations

import bisect
import hashlib
import json
from pathlib import Path
import struct
import sys

try:
    import capstone
    from capstone import x86
    import numpy
except ImportError as error:  # research dependency only; never needed at runtime or in tests
    raise SystemExit('research_event_combat requires capstone and numpy: ' + str(error))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/event-combat-F5FEE03DCFDB.json'
PROFILE_DLL_SHA = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
IMAGE_SIZE = 0x4744000
TEXT = (0x1000, 0x1000 + 0x210FA93)
RDATA = (0x2111000, 0x2111000 + 0x52AA0C)
DATA = (0x263C000, 0x263C000 + 0x119B5FC)
SNAPSHOTS = ('F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap')

# Globals (RVA of a pointer-sized slot in game.dll .data). Each is proven by the pins that load it.
GLOBALS = {
    'healthManager': (0x3326688, 'HealthComponent manager (inline object; set once at 0x568DFD)'),
    'actorManager': (0x3326D20, 'player avatar (actor) manager; entity hash +0xF8, descriptors +0x110'),
    'playerManager': (0x3326468, 'player list: count +0x84, peer ids +0x2C8 (stride 0x38), descriptors +0xE8'),
    'missionStats': (0x3326AE0, 'mission stats manager: per-player stat maps and the 64-entry hit ring'),
    'damageSystem': (0x347CF38, 'damage system: FIFO queues, queue 0 = 4096 x 0x70 damage events'),
    'hitVerifyBuffer': (0x346D558, 'deferred hit buffer (<=256 x 0xB0, <=64 drained per tick)'),
    'networkRoot': (0x346BF98, 'network root: GOID->entity hash, shared HealthComponentData table'),
    'localUser': (0x347CEF0, 'local user; +0xB398 = local peer id (u64)'),
    'telemetry': (0x347CE18, 'telemetry manager (PlayerDamage/PlayerScore JSON)'),
    'damageInfoTable': (0x37C60C0, 'DamageInfo settings pointer table (650 x 8 bytes)'),
    'careerStats': (0x346D570, 'backend career stats; +0x14 kills (max-merged from server data)'),
    'invalidEntity': (0x3483C20, 'invalid entity sentinel'),
    'invalidId': (0x3483C4C, 'invalid id sentinel (initial record+0x44/+0x48)'),
}

# Function starts; every pin below is re-proven as an instruction boundary reachable from its start.
FUNCTIONS = {
    'health_record_getter': (0x4A4410, 'Record *HealthRecord(<unused>, u32 entity): hash lookup, [mgr+0x1058]+idx*0x1B8'),
    'add_instance': (0x53DCE0, 'AddInstance(Descriptor*, const u8 *owned): live partition insert'),
    'add_staged_instance': (0x53DC10, 'AddStagedInstance(Descriptor*): append to staged partition'),
    'activate_staged': (0x928940, 'ActivateStaged(mgr): moves staged records into the live partition'),
    'move_record': (0x927520, 'MoveRecord(mgr, u32 dst, u32 src): copies record/ext/descriptor, rehashes'),
    'remove_instance': (0x928A70, 'RemoveInstance(<unused>, Descriptor*): hash remove + swap-with-last'),
    'record_init': (0x91D580, 'InitRecord(<unused>, Descriptor*): health, zones, armor from settings'),
    'update': (0x920260, 'HealthManager::Update(mgr, float dt): regen, timers, replicated life state'),
    'set_life_state': (0x91C240, 'SetLifeState(mgr, u32 index, u32 state, kind, element, ...): raise only'),
    'is_dead': (0x927050, 'bool IsDead(mgr, u32 entity): record+0x19C >= 2'),
    'damage_apply': (0x9235F0, 'ApplyDamage(mgr, u32 target, kind, element, 15 stack args)'),
    'event_consumer': (0x12A7D40, 'ConsumeDamageEvent(ctx, DamageEvent*): apply + telemetry + stats'),
    'queue_drain': (0x12A6EF0, 'DamageSystem::Drain(system): <=16 events per queue per call, compacts'),
    'enqueue_copy': (0x129EF00, 'EnqueueDamageEvent(<unused>, const DamageEvent*)'),
    'producer': (0x129DD30, 'ProduceDamage(?, DamageValues*, HitInfo*, u32 arg4): fills a queue slot'),
    'hit_init': (0x12A15E0, 'InitHitInfo(..., HitInfo*, kind, ...): DamageInfo row -> hit fields'),
    'resolve_goid': (0xFD9BA0, 'u32 *ResolveGoid(u32 *out, u32 goid): network GameObject id -> entity'),
    'settings_getter': (0x507920, 'HealthComponentData *Settings(Descriptor*): instance copy else shared'),
    'heal_add_fraction': (0x91E920, 'AddHealthFraction(mgr, u32 entity, float fraction)'),
    'heal_set_fraction': (0x91E500, 'RestoreHealth(mgr, u32 entity, float fraction)'),
    'stim_restore_call': (0x11C9440, 'stim status handler (contains the CombatDrugs booster anchor)'),
    'kill_dispatch': (0xB96310, 'dispatch "entity killed" to listeners of kind 0xFA'),
    'kill_credit': (0x129FD00, 'kill-credit listener: increments mission kill stats for the creditor'),
    'add_stat': (0x62C930, 'AddStat(stats, u64 peer, u32 key, u32 amount, u32 entity, ...)'),
    'player_index': (0x62C710, 'u32 StatsPlayerIndex(stats, u64 peer)'),
    'stat_map_lookup': (0x1731A60, 'Entry *StatMapLookup(StatMap*, u32 key)'),
    'score_getter': (0x630130, 'BuildScore(stats, Score*, u32 playerIndex): stat keys -> score fields'),
    'score_telemetry': (0xBF9810, 'PlayerScore telemetry: names every score field'),
    'hit_ring': (0x62E650, 'RecordHit(<unused>, dealer, target, u32 key, u64 creditor): 64-entry ring'),
    'damage_apply_hit_ring_call': (0x9235F0, 'ring call site inside ApplyDamage'),
    'attribute_lookup': (0x11D9DF0, 'Attribute *EntityAttribute(u32 entity, u32 key, u32 flags)'),
    'career_kills_ui': (0x17B4680, 'debug/UI "Kills: %u. (session: %u)"'),
}

PINS = {
    'health_record_getter': [
        (0x4A4414, '3b1506f8fd02', 'invalid-entity compare'),
        (0x4A441A, '4c8b156722e802', 'load health manager global'),
        (0x4A442A, '458b8a38100000', 'hash capacity +0x1038'),
        (0x4A4439, '418b9a40100000', 'hash multiplier +0x1040'),
        (0x4A445A, '498bba30100000', 'hash buckets +0x1030'),
        (0x4A4461, '418bb23c100000', 'hash empty key +0x103C'),
        (0x4A44C1, '418b4304', 'bucket value = record index'),
        (0x4A44AA, '4869c1b8010000', 'record stride 0x1B8'),
        (0x4A44B1, '49038258100000', 'record array +0x1058'),
    ],
    'add_instance': [
        (0x53DCFA, '488b358789de02', 'load health manager global'),
        (0x53DD36, '8b8620100000', 'live count +0x1020'),
        (0x53DD3E, '8bae24100000', 'owned-partition count +0x1024'),
        (0x53DD50, 'e8cb973e00', 'move record to make room'),
        (0x53DD6C, '4869dfb8010000', 'record stride'),
        (0x53DD79, '48039e58100000', 'record array'),
        (0x53DD88, 'c6430501', 'record+5 enabled = 1'),
        (0x53DD8E, '488983a4010000', 'record+0x1A4 = 0'),
        (0x53DD9E, 'ff8620100000', '++live count'),
        (0x53DDAA, 'ff861c100000', '++total count +0x101C'),
        (0x53DDB5, '488b8648100000', 'descriptor array +0x1048'),
        (0x53DDC9, '4c8934f8', 'descriptor store'),
        (0x53DDEB, 'e9a0191f01', 'hash insert'),
    ],
    'add_staged_instance': [
        (0x53DC34, '8bae1c100000', 'total count +0x101C'),
        (0x53DC6A, '4869dfb8010000', 'record stride'),
        (0x53DC77, '48039e58100000', 'record array'),
        (0x53DCB1, 'ff861c100000', '++total count only (staged partition)'),
    ],
    'activate_staged': [
        (0x9289EA, '8bbb20100000', 'live count'),
        (0x9289F0, '8b831c100000', 'total count'),
        (0x928A1D, 'e8feeaffff', 'move staged record into live partition'),
        (0x928A3A, '898320100000', 'live count = total count'),
    ],
    'move_record': [
        (0x9275E8, '498b9260100000', 'ext array +0x1060'),
        (0x92761B, '498b8248100000', 'descriptor array'),
        (0x927682, '41896804', 'hash value rewritten to destination index'),
    ],
    'remove_instance': [
        (0x928A78, '488b3d09dc9f02', 'load health manager global'),
        (0x928A8C, 'e80f6ee000', 'hash remove'),
        (0x928A91, '448b8720100000', 'live count'),
        (0x928AA2, 'ff8f1c100000', '--total (staged remove)'),
        (0x928AD6, 'f6411401', 'descriptor flag bit0 selects owned partition'),
        (0x928ADC, '838724100000ff', '--owned count'),
        (0x928B05, 'ff8f1c100000', '--total count'),
        (0x928B0E, '44898720100000', 'live count = live-1'),
        (0x928B1D, 'e8fee9ffff', 'swap last live record into hole'),
    ],
    'record_init': [
        (0x91D5AC, '488b3dd590a002', 'load health manager global'),
        (0x91D61C, 'e8ffa2beff', 'settings getter'),
        (0x91D626, '4c69e9b8010000', 'record stride'),
        (0x91D62D, '486be91c', 'ext stride 0x1C'),
        (0x91D637, '4c03af58100000', 'record array'),
        (0x91D646, '4803af60100000', 'ext array'),
        (0x91D64D, '41894d44', 'record+0x44 = invalid id'),
        (0x91D657, '41894d48', 'record+0x48 = invalid id'),
        (0x91D694, '8b4514', 'ext+0x14 max health'),
        (0x91D69E, '41894514', 'record+0x14 = max health'),
        (0x91D6AE, '41c7451802000000', 'record+0x18 = 2'),
        (0x91D6D1, '41894510', 'record+0x10 = settings.RegenerationSegments-1'),
        (0x91D74D, '4189455c', 'record+0x5C = default zone armor'),
        (0x91D772, '898768ffffff', 'record+0x60+z*4 = zone armor'),
        (0x91D77B, '8907', 'record+0xF8+z*4 = zone health'),
        (0x91D801, '4881c328020000', 'zone stride 0x228'),
        (0x91D75A, '41bc26000000', '38 zones'),
    ],
    'update': [
        (0x920317, '41398620100000', 'iterate live count +0x1020'),
        (0x920482, 'c6460400', 'record+4 hit flag cleared each tick'),
        (0x92049B, '448b441f0c', 'ext+0xC replicated life state'),
        (0x9204A0, '8b869c010000', 'record+0x19C life state'),
        (0x9204BD, 'e87ebdffff', 'SetLifeState when they differ'),
        (0x9204CF, 'f30f588ea4010000', 'record+0x1A4 += dt'),
        (0x9204D7, 'f30f118ea4010000', 'store record+0x1A4'),
        (0x92087D, '488b5638', 'tick death: creditor = record+0x38'),
        (0x920881, 'c744242002000000', 'tick death kind 2 (DPS)'),
        (0x920889, 'e8825a2700', 'killed-entity dispatch'),
        (0x920CDC, '488b5638', 'tick death: creditor = record+0x38'),
        (0x920CE8, 'c744242007000000', 'tick death kind 7 (Flat)'),
        (0x920CF0, 'e81b562700', 'killed-entity dispatch'),
    ],
    'set_life_state': [
        (0x91C277, '4869f9b8010000', 'record stride'),
        (0x91C28D, '498bb758100000', 'record array'),
        (0x91C2C8, '3b9c379c010000', 'only raises state (jbe exit)'),
        (0x91CF8B, '41899c309c010000', 'store record+0x19C'),
    ],
    'is_dead': [
        (0x9270E4, '4869c8b8010000', 'record stride'),
        (0x9270EB, '498b8258100000', 'record array'),
        (0x9270F2, '83bc019c01000002', 'dead = state >= 2'),
    ],
    'damage_apply': [
        (0x923683, '8b3d9705b602', 'invalid entity'),
        (0x923691, '448b8138100000', 'hash capacity'),
        (0x9236BE, '4d8b942430100000', 'hash buckets'),
        (0x923719, '498b842448100000', 'descriptor array'),
        (0x923731, '4d69f8b8010000', 'record stride'),
        (0x92373C, '4d03bc2458100000', 'record array'),
        (0x923747, '496bc01c', 'ext stride'),
        (0x923756, '498b842460100000', 'ext array'),
        (0x923766, 'e8b541beff', 'settings getter'),
        (0x92388C, '44386c0818', 'ext+0x18 immune flag'),
        (0x923897, '45386f05', 'record+5 enabled flag'),
        (0x92392E, '8b540210', 'ext+0x10 per-kind 2-bit acceptance mask'),
        (0x923937, '0f84f4230000', 'mask 0 => no damage'),
        (0x92395B, '488d0d96ec8101', 'relation multiplier table'),
        (0x923962, 'f30f100c91', 'multiplier = table[mask]'),
        (0x92396E, '488d8afc530000', 'settings.ElementDamageValues +0x53FC'),
        (0x9239E2, 'f30f598cc200540000', 'element multiplier +0x5400'),
        (0x9239FA, 'f34c0f2ce0', 'damage = trunc(damage*multiplier)'),
        (0x923A85, 'ba01000000', 'Vitality booster argument'),
        (0x923A8A, 'e8b132f3ff', 'IsBoosterActive'),
        (0x923A9E, 'f30f59052aa09d02', 'Vitality scalar'),
        (0x923B04, 'c744242833000000', 'mission modifier kind 0x33'),
        (0x923B10, 'e8fbb59b00', 'mission modifier list'),
        (0x923B44, 'f30f594220', 'modifier value'),
        (0x923BED, 'e8ae5f6b00', 'resolve owner GOID'),
        (0x923BF9, 'e8a25f6b00', 'resolve dealer GOID'),
        (0x923C20, '49894738', 'record+0x38 = creditor'),
        (0x923C24, '45896740', 'record+0x40 = event+0x60'),
        (0x923C34, '45897930', 'record+0x30 = owner entity'),
        (0x923C57, '4969f828020000', 'zone stride 0x228'),
        (0x923C68, '488d87d0030000', 'zone actor list +0x3D0'),
        (0x923F04, '8b8482f8000000', 'zone health read'),
        (0x923F15, '4489ac8af8000000', 'zone health store'),
        (0x924B75, '8b4018', 'settings.Constitution'),
        (0x924B81, '894114', 'record+0x14 = max(health, -Constitution)'),
        (0x924D18, '4489a8a4010000', 'record+0x1A4 = 0 (time since damage)'),
        (0x924ECC, '8b819c010000', 'prior life state'),
        (0x924F3E, '894844', 'record+0x44 = owner entity at downing'),
        (0x924F48, '48894850', 'record+0x50 = creditor at downing'),
        (0x924F50, '897848', 'record+0x48 = dealer entity at downing'),
        (0x924F53, '44896058', 'record+0x58 = event+0x60 at downing'),
        (0x92536F, '41894e44', 'record+0x44 (second path)'),
        (0x925377, '41897e48', 'record+0x48 (second path)'),
        (0x92537B, '4d896e50', 'record+0x50 (second path)'),
        (0x92537F, '45896658', 'record+0x58 (second path)'),
        (0x925387, 'e8840b0000', 'HealthComponentDeath'),
        (0x925557, '4183fd02', 'new state == dead'),
        (0x925567, '498b5638', 'creditor from record+0x38'),
        (0x925578, 'e8930d2700', 'killed-entity dispatch'),
        (0x925680, '83f909', 'BleedOut (kind 9) replays downing data'),
        (0x925696, '458b4e48', 'record+0x48'),
        (0x92569A, '458b4644', 'record+0x44'),
        (0x9256A2, '498b4650', 'record+0x50'),
        (0x9256AB, '418b4658', 'record+0x58'),
        (0x9256D7, 'e804902200', 'death listener dispatch'),
        (0x9256F4, 'e8476bffff', 'SetLifeState'),
    ],
    'event_consumer': [
        (0x12A874A, '488b059f471d02', 'load local user global'),
        (0x12A8751, '483b8898b30000', 'creditor == local user +0xB398'),
        (0x12A7DA5, '418b5e14', 'event+0x14 owner GOID'),
        (0x12A8205, '418b16', 'event+0 target entity'),
        (0x12A8241, '458b4e08', 'event+8 element'),
        (0x12A8245, '458b4604', 'event+4 damage source kind'),
        (0x12A8254, '418b4620', 'event+0x20'),
        (0x12A825F, '418b4660', 'event+0x60'),
        (0x12A82B4, 'f3410f104634', 'event+0x34'),
        (0x12A82C4, '498b4618', 'event+0x18 creditor'),
        (0x12A82D1, '418b4614', 'event+0x14'),
        (0x12A82D9, '418b4610', 'event+0x10 dealer GOID'),
        (0x12A82E0, '488b0da1e30702', 'health manager as this'),
        (0x12A82EB, 'e800b367ff', 'damage apply'),
        (0x12A81DC, '418b762c', 'event+0x2C damage amount'),
        (0x12A876E, '488d356b86f200', 'damage source name table'),
        (0x12A8751, '483b8898b30000', 'creditor == local user'),
        (0x12A8783, 'e8889e67ff', 'remaining health getter'),
        (0x12A88B2, 'e8691495ff', 'PlayerDamage telemetry'),
        (0x12A8948, 'e8d31695ff', 'EntityDamage telemetry'),
        (0x12A89FA, 'e85185ffff', 'damage stats'),
    ],
    'queue_drain': [
        (0x12A6F17, '8b8120112000', 'queue0 count +0x201120'),
        (0x12A6F1D, '41bf10000000', '16 events per call'),
        (0x12A6F51, '488db92c110000', 'queue0 base +0x1120'),
        (0x12A6FA3, 'e8980d0000', 'consume event'),
        (0x12A6FA8, '4883c770', 'event stride 0x70'),
        (0x12A6FB9, '2bc6', 'count -= processed'),
        (0x12A6FEF, 'e8fc18df00', 'memmove remainder to front'),
    ],
    'enqueue_copy': [
        (0x129EF04, '4c8b052de01d02', 'damage system global'),
        (0x129EF12, '3d00100000', 'capacity 4096'),
        (0x129EF37, '486bc070', 'event stride'),
        (0x129EF43, '420f11840020110000', 'slot +0x1120'),
        (0x129EF8F, '41898020112000', 'count store'),
    ],
    'producer': [
        (0x129DD77, '4c8b35baf11d02', 'damage system global'),
        (0x129E416, '41898620112000', 'queue0 count++'),
        (0x129E41D, '81f900100000', 'capacity 4096'),
        (0x129E430, '4c6be970', 'event stride'),
        (0x129E440, '4389842e20110000', 'event+0 = hit+0x20 target'),
        (0x129E44B, '4389842e24110000', 'event+4 = hit+0 kind'),
        (0x129E457, '4389842e28110000', 'event+8 = hit+4 element'),
        (0x129E472, '4389842e30110000', 'event+0x10 = hit+0x84 dealer GOID'),
        (0x129E481, '4389842e34110000', 'event+0x14 = hit+0x104 owner GOID'),
        (0x129E490, '4b89842e38110000', 'event+0x18 = hit+0x110 creditor'),
        (0x129E49C, '4389842e40110000', 'event+0x20 = arg4'),
        (0x129E4B9, '4389842e4c110000', 'event+0x2C = damage'),
        (0x129E4F9, '4389842e60110000', 'event+0x60 = hit+0x10'),
        (0x129E123, 'e8c8bcf3ff', 'target attribute 0x2CFAECA3'),
        (0x129E13C, 'f30f59c8', 'damage *= target attribute'),
    ],
    'hit_init': [
        (0x12A1C29, '8b4324', 'DamageInfoType from source struct +0x24'),
        (0x12A23FD, '488d0dbc3c5202', 'DamageInfo pointer table'),
        (0x12A2408, '8b4128', 'DamageInfo +0x28 element'),
        (0x12A240E, '41894604', 'hit+4 element'),
        (0x12A2479, '660f6e5904', 'DamageInfo +4 standard damage'),
        (0x12A247E, '660f6e4908', 'DamageInfo +8 durable damage'),
        (0x12A2516, '41898684000000', 'hit+0x84 dealer GOID'),
        (0x12A2549, '41898604010000', 'hit+0x104 owner GOID'),
        (0x12A2592, '49898610010000', 'hit+0x110 creditor'),
    ],
    'resolve_goid': [
        (0xFD9BA4, '4c8b1ded234902', 'network root global'),
        (0xFD9BB1, '81faff7f0000', '0x7FFF = none'),
        (0xFD9BC9, '458b93d02ef200', 'GOID hash capacity +0xF22ED0'),
        (0xFD9BF9, '498bbbc82ef200', 'GOID hash buckets +0xF22EC8'),
        (0xFD9C4C, '488d0440', 'entry stride 24'),
        (0xFD9C50, '488d80e4651e00', 'entity table +0x1E65E4*8'),
    ],
    'settings_getter': [
        (0x507942, '4c8b1d3fede102', 'health manager'),
        (0x50795B, '458b8b78100000', 'instance-copy hash +0x1078'),
        (0x50797A, '498bbb70100000', 'instance-copy buckets +0x1070'),
        (0x5079D2, '4869c050560000', 'settings stride 0x5650'),
        (0x5079D9, '490383b0100000', 'instance copies +0x10B0'),
        (0x507435, '488b055c4bf602', 'network root'),
        (0x50743F, '4c8b90782bf100', 'shared HealthComponentData table +0xF12B78'),
        (0x507463, '69c0ea030000', '1002 slots'),
        (0x5074B1, '4869c150560000', 'settings stride'),
        (0x5074B8, '4805a03e0000', 'records +0x3EA0'),
    ],
    'heal_add_fraction': [
        (0x91E967, '4c8bf9', 'this = health manager'),
        (0x91EA3C, 'e80f860000', 'IsDead gate'),
        (0x91EA5D, '438b4c0814', 'ext+0x14 max'),
        (0x91EA78, 'f30f59ce', 'max*fraction'),
        (0x91EA7C, 'f30f58c8', '+ current'),
        (0x91EA86, '0f4cc8', 'clamp to max'),
        (0x91EA89, '41890a', 'store record+0x14'),
        (0x91EA17, '41f644241401', 'descriptor flag bit0 (owning peer) gates network paths'),
        (0x91EAEF, 'e83cded0ff', 'stat add on owning peer'),
        (0x91EB54, '4183bd9c01000001', 'downed?'),
        (0x91EB69, '4589b59c010000', 'revive: state = 0'),
        (0x91EB89, '458974000c', 'ext+0xC = 0'),
        (0x91ED18, 'e8f342d9ff', 'synced health update'),
    ],
    'heal_set_fraction': [
        (0x91E5B4, '458ba69c010000', 'life state'),
        (0x91E5BB, '4183fc02', 'dead => no-op'),
        (0x91E5C5, '428b440a14', 'ext+0x14 max'),
        (0x91E5D1, 'f30f59c6', 'max*fraction'),
        (0x91E5F6, '45894614', 'store record+0x14'),
        (0x91E621, '4189b69c010000', 'state = 0'),
        (0x91E6F7, 'f6411401', 'owning-peer gate'),
        (0x91E708, '8974020c', 'ext+0xC = 0'),
        (0x91E811, 'e88a49d9ff', 'synced health update'),
    ],
    'stim_restore_call': [
        (0x11C9939, '488b0d48cd1502', 'health manager'),
        (0x11C9940, '0f28d7', 'fraction'),
        (0x11C9945, 'e8b64b75ff', 'RestoreHealth'),
    ],
    'kill_dispatch': [
        (0xB96320, '488b2d410b7902', 'listener registry'),
        (0xB9636C, '817ccd08fa000000', 'listener kind 0xFA'),
        (0xB96392, 'e869997000', 'kill credit listener'),
    ],
    'kill_credit': [
        (0x12A0060, 'e8bb7826ff', 'victim settings'),
        (0x12A006A, '396830', 'KillScore > 0'),
        (0x12A0077, '41b8ccc594d4', 'stat dealt_kills'),
        (0x12A0086, '498bd5', 'creditor'),
        (0x12A008E, 'e89dc838ff', 'AddStat'),
        (0x12A01DE, '41b85619539d', 'stat dealt_team_kills'),
        (0x12A0738, '41b81b0a68c7', 'stat dealt_melee_kills'),
    ],
    'add_stat': [
        (0x62C94D, 'e8befdffff', 'player index from creditor'),
        (0x62C989, '488d8657160000', 'map index + 0x1657'),
        (0x62C992, '488d0480', 'x5'),
        (0x62C996, '488d3cc7', 'x8 (map stride 0x28)'),
        (0x62C99D, 'e8be501001', 'map lookup'),
        (0x62C9CD, '016804', 'value += amount'),
    ],
    'player_index': [
        (0x62C71A, '488b0d479dcf02', 'player manager'),
        (0x62C724, '448b9184000000', 'player count +0x84'),
        (0x62C730, '4c8d89c8020000', 'peer ids +0x2C8'),
        (0x62C73E, '4983c138', 'peer stride 0x38'),
        (0x62C751, '488b8cc1e8000000', 'player descriptor +0xE8'),
        (0x62C759, '8b5108', 'player entity'),
        (0x62C764, '458b8b607d0300', 'stats index hash cap +0x37D60'),
        (0x62C78C, '498bbb587d0300', 'stats index buckets +0x37D58'),
    ],
    'stat_map_lookup': [
        (0x1731A6A, '448b4108', 'capacity +8'),
        (0x1731A70, '448b5110', 'multiplier +0x10'),
        (0x1731A84, '4c8b19', 'entries +0'),
        (0x1731A87, '8b590c', 'empty key +0xC'),
        (0x1731A99, '488d0c92', 'entry stride 20'),
    ],
    'score_getter': [
        (0x630158, 'ba30297a5c', 'key dealt_damage'), (0x630185, '890b', 'score+0x00'),
        (0x630187, 'baccc594d4', 'key dealt_kills'), (0x6301A9, '894b04', 'score+0x04'),
        (0x6301AC, 'ba5619539d', 'key dealt_team_kills'), (0x6301CE, '894b08', 'score+0x08'),
        (0x6301D1, 'ba1b0a68c7', 'key dealt_melee_kills'), (0x6301F3, '894b0c', 'score+0x0C'),
        (0x6301F6, 'ba010e80b5', 'key dealt_team_damage'), (0x630218, '894b10', 'score+0x10'),
        (0x63021B, 'ba896725c8', 'key stims_used'), (0x63023D, '894b28', 'score+0x28'),
        (0x630240, 'ba95d1a3b7', 'key received_damage'), (0x630262, '894b34', 'score+0x34'),
        (0x6302B0, '3d8ab00143', 'key reinforcements_called'), (0x6302C7, '894330', 'score+0x30'),
        (0x630459, None, 'key received_revives'), (0x6304A9, None, 'key received_deaths'),
    ],
    'hit_ring': [
        (0x62E65A, '4c8b1d7f84cf02', 'mission stats manager'),
        (0x62E669, '498d8348c00000', 'ring keys +0xC048'),
        (0x62E67C, '4183fa40', '64 entries'),
        (0x62E69B, '47898cc348c00000', 'key store'),
        (0x62E6A3, '43c784c34cc0000001000000', 'count = 1'),
        (0x62E6AF, '49890cc3', 'dealer store'),
        (0x62E6B3, '41ff8338c00000', 'write index +0xC038'),
        (0x62E6D3, '41ff84c34cc00000', 'existing key: count++'),
    ],
    'damage_apply_hit_ring_call': [
        (0x924B9C, '8bbd480b0000', 'event+0x20'),
        (0x924BB6, 'e8e54f6b00', 'resolve dealer'),
        (0x924BCF, 'e87c9ad0ff', 'hit ring'),
    ],
    'attribute_lookup': [
        (0x11D9E19, '4c8b1d00cf1402', 'actor manager'),
        (0x11D9ED1, '486bc178', 'actor record stride 0x78'),
        (0x11D9EDA, '428b9418a4785400', 'actor -> player GOID +0x5478A4'),
        (0x11D9EF5, '4c8b0dfcc51402', 'attribute manager'),
    ],
    'career_kills_ui': [
        (0x17B46CA, '488b059f8ecb01', 'career stats global'),
        (0x17B46F2, '448b4814', 'kills +0x14'),
    ],
}

# Score fields named by the game's own PlayerScore telemetry (0xBF9810) and filled from these stat keys
# by BuildScore (0x630130). received_revives / received_deaths are re-derived below from their stores.
STAT_KEYS = {0x5C7A2930: 'dealt_damage', 0xD494C5CC: 'dealt_kills', 0x9D531956: 'dealt_team_kills',
    0xC7680A1B: 'dealt_melee_kills', 0xB5800E01: 'dealt_team_damage', 0xC8256789: 'stims_used',
    0x4301B08A: 'reinforcements_called', 0xB7A3D195: 'received_damage', 0x6C34CF41: 'received_revives',
    0x9D6C8635: 'received_deaths'}
SCORE_NAME_TABLE = {0x0: 'dealt_damage', 0x4: 'dealt_kills', 0x8: 'dealt_team_kills', 0xC: 'dealt_melee_kills',
    0x10: 'dealt_team_damage', 0x28: 'stims_used', 0x30: 'reinforcements_called', 0x34: 'received_damage',
    0x38: 'received_revives', 0x3C: 'received_deaths'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class Image:
    def __init__(self, data: bytes, base: int):
        self.data, self.base = data, base
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.lite = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        pe = struct.unpack_from('<I', data, 60)[0]
        if struct.unpack_from('<I', data, pe + 80)[0] != IMAGE_SIZE:
            raise ValueError('game.dll SizeOfImage changed')
        exc_rva, exc_size = struct.unpack_from('<II', data, pe + 24 + 112 + 3 * 8)
        table = numpy.frombuffer(data[exc_rva:exc_rva + exc_size // 12 * 12], dtype='<u4').reshape(-1, 3)
        table = table[table[:, 0] < table[:, 1]]
        self.pdata = table
        self.pdata_begin = table[:, 0].astype(numpy.int64)
        self._phases = None

    def u32(self, rva): return struct.unpack_from('<I', self.data, rva)[0]
    def u64(self, rva): return struct.unpack_from('<Q', self.data, rva)[0]
    def f32(self, rva): return struct.unpack_from('<f', self.data, rva)[0]

    def cstr(self, rva):
        return self.data[rva:self.data.index(b'\0', rva)].decode('latin-1')

    def insn(self, rva):
        found = next(self.md.disasm(self.data[rva:rva + 16], rva, 1), None)
        if found is None:
            raise ValueError('undecodable instruction at %x' % rva)
        return found

    def rip_target(self, insn):
        for op in insn.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base == x86.X86_REG_RIP:
                return insn.address + insn.size + op.mem.disp
        return None

    def chunk(self, rva):
        i = int(numpy.searchsorted(self.pdata_begin, rva, side='right')) - 1
        if i >= 0 and self.pdata[i, 0] <= rva < self.pdata[i, 1]:
            return int(self.pdata[i, 0]), int(self.pdata[i, 1])
        return None

    def reachable(self, start, limit=40000):
        """Instruction starts reachable from start by recursive descent (tail jumps into other
        .pdata function starts are not followed)."""
        seen, work = {}, [start]
        while work and len(seen) < limit:
            a = work.pop()
            while a not in seen and TEXT[0] <= a < TEXT[1]:
                ins = next(self.md.disasm(self.data[a:a + 16], a, 1), None)
                if ins is None:
                    break
                seen[a] = ins
                if ins.mnemonic in ('ret', 'int3', 'ud2'):
                    break
                if ins.mnemonic == 'jmp':
                    op = ins.operands[0]
                    if op.type == x86.X86_OP_IMM:
                        target = self.chunk(op.imm)
                        if not (target and target[0] == op.imm and op.imm != start):
                            work.append(op.imm)
                    break
                if ins.mnemonic.startswith('j') and ins.operands[0].type == x86.X86_OP_IMM:
                    work.append(ins.operands[0].imm)
                a += ins.size
        return seen

    def proof(self, rva, role):
        insn = self.insn(rva)
        entry = {'rva': rva, 'bytes': self.data[rva:rva + insn.size].hex(), 'role': role,
            'asm': insn.mnemonic + ' ' + insn.op_str}
        target = self.rip_target(insn)
        if target is not None:
            entry['ripTarget'] = target
        if insn.mnemonic in ('call', 'jmp') and insn.operands[0].type == x86.X86_OP_IMM:
            entry['branchTarget'] = insn.operands[0].imm
        return entry

    # Memory-light RIP-relative / rel32 reference scan: one int32 view per byte phase.
    def _phase_keys(self):
        if self._phases is None:
            self._phases = []
            size = TEXT[1] - TEXT[0]
            for phase in range(4):
                count = (size - phase) // 4
                view = numpy.frombuffer(self.data, dtype='<i4', offset=TEXT[0] + phase, count=count)
                positions = numpy.arange(count, dtype=numpy.int64) * 4 + TEXT[0] + phase
                self._phases.append(positions + 4 + view.astype(numpy.int64))
        return self._phases

    def references(self, target):
        """Validated instructions whose displacement / rel32 resolves to target."""
        found = {}
        for phase, keys in enumerate(self._phase_keys()):
            for tail in (0, 1, 2, 4):
                for hit in numpy.nonzero(keys == target - tail)[0]:
                    disp_at = TEXT[0] + phase + int(hit) * 4
                    chunk = self.chunk(disp_at)
                    if not chunk:
                        continue
                    for address, size, _, _ in self.lite.disasm_lite(self.data[chunk[0]:chunk[1]], chunk[0]):
                        if address <= disp_at < address + size:
                            if address + size == disp_at + 4 + tail:
                                found[address] = self.insn(address)
                            break
                        if address > disp_at:
                            break
        return [found[a] for a in sorted(found)]

    def root(self, rva):
        chunk = self.chunk(rva)
        if not chunk:
            return None
        i = int(numpy.searchsorted(self.pdata_begin, chunk[0], side='right')) - 1
        unwind = int(self.pdata[i, 2])
        for _ in range(10):
            if not (self.data[unwind] >> 3) & 4:
                break
            count = self.data[unwind + 2]
            at = unwind + 4 + ((count + 1) & ~1) * 2
            begin, _, unwind = struct.unpack_from('<III', self.data, at)
            chunk = (begin, None)
        return chunk[0]


class Mem:
    """Targeted reads of one retained snapshot (never scans whole regions)."""

    def __init__(self, path):
        self.s = snapshot_image.Snapshot(path)
        self.game = self.s.modules['game.dll']['base']

    def read(self, address, size):
        region = self.s.region(address)
        if region is None or region['status'] != 1 or address + size > region['base'] + region['size']:
            return None
        self.s.handle.seek(region['data_offset'] + address - region['base'])
        return self.s.handle.read(size)

    def u32(self, a): return struct.unpack('<I', self.read(a, 4))[0]
    def i32(self, a): return struct.unpack('<i', self.read(a, 4))[0]
    def u64(self, a): return struct.unpack('<Q', self.read(a, 8))[0]
    def f32(self, a): return struct.unpack('<f', self.read(a, 4))[0]

    def ptr(self, a):
        value = self.u64(a)
        if not 0x10000 <= value < 0x800000000000:
            raise ValueError('not a user pointer at %x' % a)
        return value

    def lookup(self, buckets, capacity, empty, multiplier, key, stride=8):
        """The game's open-addressing hash: slot = (i + key*mult) & (cap-1), linear probe."""
        for i in range(capacity):
            slot = (i + key * multiplier) & 0xFFFFFFFF & (capacity - 1)
            k, v = struct.unpack('<II', self.read(buckets + slot * stride, 8))
            if k == empty:
                return None
            if k == key:
                return v
        return None

    def close(self):
        self.s.close()


def snapshot_evidence(path):
    m = Mem(path)
    g = m.game
    hm = m.ptr(g + GLOBALS['healthManager'][0])
    header = m.read(hm + 0x1000, 0xB8)
    u = lambda off: struct.unpack_from('<I', header, off - 0x1000)[0]  # noqa: E731
    counts = {'capacity': u(0x1010), 'highWater': u(0x1018), 'total': u(0x101C), 'live': u(0x1020),
        'owned': u(0x1024), 'hashCapacity': u(0x1038), 'hashEmptyKey': u(0x103C), 'hashMultiplier': u(0x1040),
        'instanceSettingsCopies': u(0x10A8)}
    if not counts['owned'] <= counts['live'] <= counts['total'] <= counts['capacity']:
        raise ValueError('health partitions out of order')
    descriptors, records, ext = m.ptr(hm + 0x1048), m.ptr(hm + 0x1058), m.ptr(hm + 0x1060)
    buckets = m.ptr(hm + 0x1030)
    per_record = []
    for index in range(counts['live']):
        desc = m.ptr(descriptors + index * 8)
        raw = m.read(desc, 0x20)
        entity = struct.unpack_from('<I', raw, 8)[0]
        if m.lookup(buckets, counts['hashCapacity'], counts['hashEmptyKey'], counts['hashMultiplier'], entity) != index:
            raise ValueError('hash does not map the descriptor entity to its record index')
        rec = m.read(records + index * 0x1B8, 0x1B8)
        ex = m.read(ext + index * 0x1C, 0x1C)
        # Settings through the same path as 0x507920 -> 0x507430.
        type_hash = struct.unpack_from('<Q', raw, 0)[0]
        net = m.ptr(g + GLOBALS['networkRoot'][0])
        table = m.ptr(net + 0xF12B78)
        start = type_hash % 1002
        settings_index = None
        for step in range(1002):
            k, v = struct.unpack('<QI', m.read(table + ((start + step) % 1002) * 16, 12))
            if k == type_hash:
                settings_index = v
                break
            if k == 0:
                break
        settings = table + 0x3EA0 + settings_index * 0x5650
        zone_health = list(struct.unpack_from('<38i', rec, 0xF8))
        max_health = struct.unpack_from('<i', ex, 0x14)[0]
        zone_settings = []
        for z in range(38):  # InitRecord (0x91D770..0x91D79F): negative zone health uses max / AffectsMainHealth
            health = m.i32(settings + 0x208 + z * 0x228 + 0xE8)
            affects = m.f32(settings + 0x208 + z * 0x228 + 0xF8)
            zone_settings.append(health if health >= 0 else (int(max_health / affects) if affects > 0 else max_health))
        per_record.append({
            'index': index, 'descriptor': {'typeHash': '0x%016X' % type_hash, 'entity': entity,
                'unit': struct.unpack_from('<I', raw, 0xC)[0], 'goid': struct.unpack_from('<I', raw, 0x10)[0],
                'flags': struct.unpack_from('<I', raw, 0x14)[0], 'bytes': raw.hex()},
            'record': {'enabled_05': rec[5], 'hitFlag_04': rec[4], 'regenSegment_10': struct.unpack_from('<I', rec, 0x10)[0],
                'health_14': struct.unpack_from('<i', rec, 0x14)[0], 'field_18': struct.unpack_from('<I', rec, 0x18)[0],
                'lastOwnerEntity_30': struct.unpack_from('<I', rec, 0x30)[0], 'lastCreditor_38': '0x%016X' % struct.unpack_from('<Q', rec, 0x38)[0],
                'lastEvent60_40': struct.unpack_from('<I', rec, 0x40)[0], 'downOwnerEntity_44': '0x%08X' % struct.unpack_from('<I', rec, 0x44)[0],
                'downDealerEntity_48': '0x%08X' % struct.unpack_from('<I', rec, 0x48)[0], 'downCreditor_50': '0x%016X' % struct.unpack_from('<Q', rec, 0x50)[0],
                'downEvent60_58': struct.unpack_from('<I', rec, 0x58)[0], 'defaultArmor_5C': struct.unpack_from('<I', rec, 0x5C)[0],
                'zoneHealth_F8': zone_health, 'lifeState_19C': struct.unpack_from('<I', rec, 0x19C)[0],
                'secondsSinceDamage_1A4': round(struct.unpack_from('<f', rec, 0x1A4)[0], 3)},
            'ext': {'kind_00': struct.unpack_from('<I', ex, 0)[0], 'lifeState_0C': struct.unpack_from('<I', ex, 0xC)[0],
                'acceptMask_10': struct.unpack_from('<I', ex, 0x10)[0], 'maxHealth_14': struct.unpack_from('<i', ex, 0x14)[0],
                'immune_18': ex[0x18], 'bytes': ex.hex()},
            'settings': {'sharedIndex': settings_index, 'Health': m.i32(settings), 'RegenerationSegments': m.u32(settings + 0x10),
                'Constitution': m.i32(settings + 0x18), 'KillScore': m.u32(settings + 0x30),
                'ElementDamageValues': [list(struct.unpack('<If', m.read(settings + 0x53FC + 8 * i, 8))) for i in range(4)],
                'zoneHealthMatchesRecord': zone_settings == zone_health},
        })
    # Avatar -> player -> peer -> stats (the chain AddStat / attribute lookup use).
    actors = m.ptr(g + GLOBALS['actorManager'][0])
    net = m.ptr(g + GLOBALS['networkRoot'][0])

    def resolve(goid):
        j = m.lookup(m.ptr(net + 0xF22EC8), m.u32(net + 0xF22ED0), m.u32(net + 0xF22ED4), m.u32(net + 0xF22ED8), goid)
        return None if j is None else m.u32(net + (0x1E65E4 + j * 3) * 8)

    avatars = []
    for rec in per_record:
        entity = rec['descriptor']['entity']
        idx = m.lookup(m.ptr(actors + 0xF8), m.u32(actors + 0x100), m.u32(actors + 0x104), m.u32(actors + 0x108), entity)
        if idx is None:
            continue
        player_goid = m.u32(actors + 0x5478A4 + idx * 0x78)
        avatars.append({'avatarEntity': entity, 'actorIndex': idx,
            'actorDescriptorIsHealthDescriptor': m.ptr(actors + 0x110 + idx * 8) == m.ptr(descriptors + rec['index'] * 8),
            'ownGoidResolvesToAvatar': resolve(rec['descriptor']['goid']) == entity,
            'playerGoid': player_goid, 'playerEntity': resolve(player_goid)})
    players = m.ptr(g + GLOBALS['playerManager'][0])
    stats = m.ptr(g + GLOBALS['missionStats'][0])
    local_peer = m.u64(m.ptr(g + GLOBALS['localUser'][0]) + 0xB398)
    player_rows = []
    for i in range(m.u32(players + 0x84)):
        peer = m.u64(players + 0x2C8 + i * 0x38)
        pdesc = m.ptr(players + 0xE8 + i * 8)
        pentity = m.u32(pdesc + 8)
        sidx = m.lookup(m.ptr(stats + 0x37D58), m.u32(stats + 0x37D60), m.u32(stats + 0x37D64), m.u32(stats + 0x37D68), pentity)
        stat_values = {}
        if sidx is not None:
            mp = stats + (sidx + 0x1657) * 0x28
            entries, cap, empty = m.ptr(mp), m.u32(mp + 8), m.u32(mp + 0xC)
            raw = m.read(entries, cap * 20)
            for s in range(cap):
                k, v = struct.unpack_from('<II', raw, s * 20)
                if k != empty:
                    stat_values[STAT_KEYS.get(k, '0x%08X' % k)] = v
        player_rows.append({'peer': '0x%016X' % peer, 'isLocal': peer == local_peer, 'playerEntity': pentity,
            'statsIndex': sidx, 'stats': stat_values})
    system = m.ptr(g + GLOBALS['damageSystem'][0])
    verify = m.ptr(g + GLOBALS['hitVerifyBuffer'][0])
    evidence = {'snapshot': Path(path).name, 'gameBase': '0x%X' % g, 'healthManager': counts, 'records': per_record,
        'avatars': avatars, 'localPeer': '0x%016X' % local_peer, 'players': player_rows,
        'hitRingWriteIndex': m.u32(stats + 0xC038),
        'hitRingNonEmpty': sum(1 for i in range(64) if m.read(stats + 0xC040 + i * 16, 16) != bytes(16)),
        'damageQueueCounts': [m.u32(system + 0x201120 + 4 * k) for k in range(8)],
        'hitVerifyCount': m.u32(verify + 0x9828),
        'careerKills': m.u32(m.ptr(g + GLOBALS['careerStats'][0]) + 0x14)}
    m.close()
    return evidence


def main():
    snap = snapshot_image.Snapshot(build_profile.SNAPSHOT)
    if snap.game_dll_sha256 != PROFILE_DLL_SHA:
        raise ValueError('snapshot game.dll fingerprint differs from the pinned profile')
    base, data = snap.module_image('game.dll')
    snap.close()
    image = Image(data, base)

    # 1. Pins: exact bytes at exact RVAs, each a reachable instruction boundary of its function.
    functions = {}
    for name, (start, signature) in FUNCTIONS.items():
        reachable = image.reachable(start)
        if name == 'settings_getter':
            reachable.update(image.reachable(0x507430))  # tail-called shared-settings path (no .pdata)
        pins = []
        for rva, expected, role in PINS.get(name, []):
            if rva not in reachable:
                raise ValueError('%s pin %x is not a reachable instruction boundary' % (name, rva))
            proof = image.proof(rva, role)
            if expected is not None and proof['bytes'] != expected:
                raise ValueError('%s pin %x bytes changed: %s' % (name, rva, proof['bytes']))
            pins.append(proof)
        functions[name] = {'rva': start, 'signature': signature, 'instructions': len(reachable), 'pins': pins}

    # RIP-relative pins must resolve to the named globals / tables.
    rip_expect = {0x4A441A: 'healthManager', 0x53DCFA: 'healthManager', 0x928A78: 'healthManager',
        0x91D5AC: 'healthManager', 0x12A82E0: 'healthManager', 0x507942: 'healthManager', 0x11C9939: 'healthManager',
        0x129EF04: 'damageSystem', 0x129DD77: 'damageSystem', 0xFD9BA4: 'networkRoot', 0x507435: 'networkRoot',
        0x62C71A: 'playerManager', 0x62E65A: 'missionStats', 0x11D9E19: 'actorManager', 0x12A23FD: 'damageInfoTable',
        0x17B46CA: 'careerStats', 0x4A4414: 'invalidEntity', 0x923683: 'invalidEntity', 0x12A874A: 'localUser'}
    by_rva = {p['rva']: p for f in functions.values() for p in f['pins']}
    for rva, global_name in rip_expect.items():
        if by_rva[rva].get('ripTarget') != GLOBALS[global_name][0]:
            raise ValueError('pin %x no longer references %s' % (rva, global_name))
    if by_rva[0x92395B]['ripTarget'] != 0x21425F8 or by_rva[0x923A9E]['ripTarget'] != 0x32FDAD0:
        raise ValueError('multiplier tables moved')
    if by_rva[0x12A876E]['ripTarget'] != 0x21D0DE0:
        raise ValueError('damage source name table moved')

    # 2. Scans (re-derived, not trusted).
    manager_refs = image.references(GLOBALS['healthManager'][0])
    manager_stores = [i for i in manager_refs if i.operands[0].type == x86.X86_OP_MEM]
    if len(manager_stores) != 1 or manager_stores[0].address != 0x568DFD:
        raise ValueError('health manager global is no longer written exactly once')
    init = image.insn(0x568DF6)
    if (init.mnemonic, init.op_str) != ('lea', 'rax, [rbx + 0x7c6230]'):
        raise ValueError('health manager is no longer an inline object of the world container')

    def callers(target):
        return [{'rva': i.address, 'function': image.root(i.address), 'asm': i.mnemonic + ' ' + i.op_str}
            for i in image.references(target) if i.mnemonic in ('call', 'jmp')]

    apply_callers = callers(0x9235F0)
    heal_add_callers = callers(0x91E920)
    heal_set_callers = callers(0x91E500)
    producer_callers = callers(0x129DD30)
    kill_dispatch_callers = callers(0xB96310)
    info_refs = [{'rva': i.address, 'function': image.root(i.address)} for i in image.references(0x37C60C0)]
    attribute_calls = callers(0x11D9DF0)
    pipeline = {0x129DD30, 0x9235F0, 0x12A7D40} | {c['function'] for c in producer_callers}
    attribute_in_pipeline = []
    for call in attribute_calls:
        if call['function'] not in pipeline:
            continue
        seen = image.reachable(call['function'])
        order = sorted(seen)
        k = order.index(call['rva'])
        setup = [seen[a].mnemonic + ' ' + seen[a].op_str for a in order[max(0, k - 8):k]
            if seen[a].op_str.startswith(('edx', 'ecx', 'r8d'))]
        attribute_in_pipeline.append(dict(call, setup=setup))
    if sorted(c['rva'] for c in attribute_in_pipeline) != [0x7D26BF, 0x923CB4, 0x924A5C, 0x129E123]:
        raise ValueError('attribute lookups in the damage pipeline changed')
    if any(r['function'] in pipeline - {0x7D01C0} for r in info_refs if r['function'] != 0x12A15E0):
        raise ValueError('a pipeline function now indexes the DamageInfo table directly')

    # 3. Constant tables read by the damage path.
    source_kinds = []
    for i in range(16):
        pointer = image.u64(0x21D0DE0 + 8 * i)
        name = image.cstr(pointer - base)
        source_kinds.append(name)
        if name == 'Count':
            break
    relation = [image.f32(0x21425F8 + 4 * i) for i in range(4)]
    received_keys = {}
    for rva, key_name, store_expect in ((0x630459, 'received_revives', 0x38), (0x6304A9, 'received_deaths', 0x3C)):
        insn = image.insn(rva)
        key = insn.operands[1].imm
        seen = image.reachable(0x630130)
        order = sorted(seen)
        k = order.index(rva)
        store = next(seen[a] for a in order[k + 1:k + 12] if seen[a].mnemonic == 'mov'
            and seen[a].operands[0].type == x86.X86_OP_MEM and seen[a].reg_name(seen[a].operands[0].mem.base) == 'rbx')
        if store.operands[0].mem.disp != store_expect or STAT_KEYS.get(key) != key_name:
            raise ValueError('score key map changed for ' + key_name)
        received_keys[key_name] = {'key': '0x%08X' % key, 'scoreOffset': store_expect, 'keyInsn': image.proof(rva, 'key'),
            'store': image.proof(store.address, 'score store')}
    score_strings = {}
    seen = image.reachable(0xBF9810)
    last = None
    for a in sorted(seen):
        ins = seen[a]
        target = image.rip_target(ins)
        if ins.mnemonic == 'lea' and target and RDATA[0] <= target < RDATA[1]:
            text = image.cstr(target)
            if text.startswith(','):
                last = text.strip(',":')
                continue
        if last:
            for op in ins.operands:
                if op.type == x86.X86_OP_MEM and ins.reg_name(op.mem.base) == 'rdi':
                    score_strings[op.mem.disp] = last
                    last = None
                    break
    for offset, name in SCORE_NAME_TABLE.items():
        if score_strings.get(offset) != name:
            raise ValueError('PlayerScore telemetry no longer names score+%x %s' % (offset, name))

    # 4. Snapshot cross-checks (targeted reads only).
    snap_dir = Path(build_profile.SNAPSHOT).parent
    evidence = [snapshot_evidence(snap_dir / name) for name in SNAPSHOTS]
    for e in evidence:
        rec = e['records'][0]
        if not (rec['record']['health_14'] == rec['ext']['maxHealth_14'] == rec['settings']['Health']):
            raise ValueError('record health / ext max / settings Health disagree in ' + e['snapshot'])
        if not rec['settings']['zoneHealthMatchesRecord']:
            raise ValueError('zone health init rule not reproduced in ' + e['snapshot'])

    # Functions Runtime may call: the exact prologue bytes (whole instructions) re-proven before every call.
    callable_functions = {}
    for name, count in (('heal_add_fraction', 12),):
        start = FUNCTIONS[name][0]
        at, asm = start, []
        for _ in range(count):
            insn = image.insn(at)
            asm.append(insn.mnemonic + ' ' + insn.op_str)
            at += insn.size
        callable_functions[name] = {'rva': start, 'prologue': data[start:at].hex(), 'asm': asm,
            'signature': FUNCTIONS[name][1]}

    report = {
        'schemaVersion': 1, 'sourceSnapshot': Path(build_profile.SNAPSHOT).name,
        'callable': callable_functions,
        'gameDll': {'sha256': PROFILE_DLL_SHA, 'imageSize': IMAGE_SIZE, 'unpackedImageSha256': sha(data),
            'textSha256': sha(data[TEXT[0]:TEXT[1]])},
        'globals': {name: {'rva': rva, 'role': role} for name, (rva, role) in GLOBALS.items()},
        'functions': functions,
        'scans': {
            'healthManagerReferences': {'total': len(manager_refs), 'functions': len({image.root(i.address) for i in manager_refs}),
                'stores': [image.proof(0x568DFD, 'only store: world container + 0x7C6230'), image.proof(0x568DF6, 'address')]},
            'damageApplyCallers': apply_callers, 'producerCallers': producer_callers,
            'healAddFractionCallers': heal_add_callers, 'restoreHealthCallers': heal_set_callers,
            'killDispatchCallers': kill_dispatch_callers, 'damageInfoTableReferences': info_refs,
            'attributeLookupsInDamagePipeline': attribute_in_pipeline},
        'layouts': {
            'healthManager': {
                '0x0000': '4 x {u32 entity[256]; u32 count} lists per HealthComponent Size (Size 4 excluded)',
                '0x1010': 'u32 record capacity', '0x1018': 'u32 live high-water', '0x101C': 'u32 total (live + staged)',
                '0x1020': 'u32 live count', '0x1024': 'u32 owned count (descriptor flag bit0 set)',
                '0x1030': 'hash buckets {u32 entity, u32 index} x capacity', '0x1038': 'u32 hash capacity (pow2)',
                '0x103C': 'u32 hash empty key', '0x1040': 'u32 hash multiplier', '0x1048': 'Descriptor *[]',
                '0x1058': 'HealthRecord[] stride 0x1B8', '0x1060': 'HealthExt[] stride 0x1C',
                '0x1070': 'instance-settings hash (entity -> copy index)', '0x10A8': 'u32 instance-settings copies',
                '0x10B0': 'HealthComponentData copies stride 0x5650',
                'partitions': '[0,+0x1024) owned (descriptor+0x14 bit0), [+0x1024,+0x1020) other live, [+0x1020,+0x101C) staged',
                'indexStability': 'indices move: AddInstance/ActivateStaged/RemoveInstance relocate records with MoveRecord; '
                    'always re-resolve entity -> index through the hash (or verify descriptor+8 == entity)'},
            'descriptor': {'0x00': 'u64 entity type hash', '0x08': 'u32 entity', '0x0C': 'u32 unit', '0x10': 'u32 GOID',
                '0x14': 'u32 flags; bit0 = owned by this peer (selects the owned partition; gates network sends in heal paths)'},
            'healthRecord': {
                'size': 0x1B8,
                '0x04': 'u8 hit flag: set by ApplyDamage paths, cleared by Update every tick (not reliably pollable)',
                '0x05': 'u8 enabled (1 on add; ApplyDamage requires != 0)',
                '0x10': 'u32 regeneration segment', '0x14': 'i32 current health (can go to -Constitution)',
                '0x18': 'u32 initialised to 2 (meaning unproven)', '0x20': '16 bytes zeroed on init/heal (meaning unproven)',
                '0x30': 'u32 owner entity of the last applied hit (resolved event+0x14 GOID)',
                '0x38': 'u64 creditor peer id of the last applied hit (event+0x18; kept when a hit has none); the kill '
                    'creditor passed by every health-manager kill dispatch (0x925578, 0x920889, 0x920CF0)',
                '0x40': 'u32 event+0x60 of the last applied hit (meaning unproven)',
                '0x44': 'u32 owner entity at downing (initial: invalid id)', '0x48': 'u32 dealer entity at downing (initial: invalid id)',
                '0x50': 'u64 creditor at downing', '0x58': 'u32 event+0x60 at downing',
                '0x5C': 'u32 default-zone armor', '0x60': 'u32 zone armor[38]', '0xF8': 'i32 zone health[38]',
                '0x190': 'u16 0xFFFF on init', '0x194': '2 x u32 while-living effect handles',
                '0x19C': 'u32 life state 0 alive, 1 downed (constitution), 2 dead; SetLifeState only raises it; heals reset <2 to 0',
                '0x1A0': 'f32 set on init for avatars (meaning unproven)',
                '0x1A4': 'f32 seconds since last applied damage (Update += dt; ApplyDamage = 0)'},
            'healthExt': {'size': 0x1C, '0x00': 'u32 damage source kind of the replicated state change (10 = none)',
                '0x04': 'u32 element of the replicated state change', '0x0C': 'u32 replicated life state (Update applies it via SetLifeState)',
                '0x10': 'u32 per-source-kind 2-bit acceptance mask: 0 no damage, 1 x1.5, 2 x1.0, 3 x0.75',
                '0x14': 'i32 max health', '0x18': 'u8 immune (non-zero skips damage)'},
            'damageEvent': {'size': 0x70, 'queue': 'damageSystem+0x1120, 4096 slots, count +0x201120',
                '0x00': 'u32 target entity', '0x04': 'u32 damage source kind', '0x08': 'u32 element type',
                '0x0C': 'u32 hit actor (converted to a zone actor hash)', '0x10': 'u32 dealer GOID', '0x14': 'u32 owner GOID',
                '0x18': 'u64 creditor peer id', '0x20': 'u32 producer argument 4 (hit ring key; meaning unproven)',
                '0x28': 'u8', '0x2C': 'u32 damage amount', '0x30': 'u32', '0x34': 'f32', '0x38': 'f32',
                '0x3C': 'f32 distance (telemetry)', '0x40': 'f32 height (telemetry)', '0x44': 'vec3', '0x50': 'vec3 (hit position; telemetry location)',
                '0x5C': 'u32', '0x60': 'u32 hit+0x10 (meaning unproven)', '0x64': 'u8', '0x68': 'u32', '0x6C': '4 x u8 relation flags'},
            'damageInfoRow': {'table': 'damageInfoTable[DamageInfoType] -> row', '0x04': 'i32 standard damage', '0x08': 'i32 durable damage',
                '0x1C': 'demolition', '0x20': 'stagger', '0x24': 'push force', '0x28': 'u32 element type (-> hit+4 -> event+8)',
                '0x2C': 'status effects (4 x type/strength)'},
            'statMap': {'address': 'missionStats + (statsIndex + 0x1657) * 0x28', '0x00': 'entries (20 bytes: u32 key, u32 value, ...)',
                '0x08': 'u32 capacity', '0x0C': 'u32 empty key', '0x10': 'u32 multiplier',
                'statsIndex': 'missionStats+0x37D58 hash (cap +0x37D60, empty +0x37D64, mult +0x37D68): player entity -> index',
                'playerEntity': 'playerManager: peer ids +0x2C8 (stride 0x38, count +0x84); descriptor +0xE8[i]; entity at +8'},
            'hitRing': {'address': 'missionStats + 0xC040', 'entries': 64, 'entry': '{u64 dealer entity, u32 key (event+0x20), u32 hits}',
                'writeIndex': 'missionStats + 0xC038 (wraps at 64)'},
        },
        'enums': {'damageSourceKind': source_kinds},
        'relationMultipliers': relation,
        'vitality': {'scalarRva': 0x32FDAD0, 'value': round(image.f32(0x32FDAD0), 6),
            'rule': 'applies only when the target is in the actor (player avatar) manager'},
        'statKeys': {'0x%08X' % k: v for k, v in STAT_KEYS.items()}, 'receivedKeys': received_keys,
        'scoreTelemetryNames': {'0x%02X' % k: v for k, v in sorted(score_strings.items())},
        'snapshots': evidence,
        'unproven': [
            'event+0x60 / record+0x40 / record+0x58: copied from hit+0x10 and persisted, but no reader was found that '
                'interprets it; it is NOT proven to be the DamageInfoType (the DamageInfoType enters InitHitInfo from '
                'its source struct +0x24 and is used only to read the row).',
            'event+0x20 (hit-ring key): producer argument 4; meaning unknown.',
            'Whether record+0x30 (owner) is the avatar, the player entity or another owner for each weapon family; '
                'the snapshots contain no damage.',
            'record+0x18, +0x20..+0x2F, +0x1A0 semantics.',
            'Frame order of HealthManager::Update (0x920260) and the damage drain relative to the Lua update(dt) callback.',
            'Network authority beyond what code shows: heal/revive paths send network messages and update synced '
                'health only when descriptor+0x14 bit0 is set; a remote-owned record is overwritten by synced health '
                '(0x6B2A90) and ext+0x0C replication.',
            'The data-driven attribute multiplier in producer caller 0x7D01C0 (key = settings row +0xD4, entity = [r12]): '
                'which entity is looked up (dealer or target) is not established.',
            'The fraction passed by the stim handler (xmm7 at 0x11C9940) was not traced to its source.',
        ],
        'writes': 0, 'protectionChanges': 0,
    }
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'functions': len(functions), 'pins': sum(len(f['pins']) for f in functions.values()),
        'healthManagerRefs': len(manager_refs), 'damageApplyCallers': [hex(c['rva']) for c in apply_callers],
        'healAddFractionCallers': len(heal_add_callers), 'restoreHealthCallers': len(heal_set_callers),
        'attributeLookups': [hex(c['rva']) for c in attribute_in_pipeline], 'damageSourceKinds': source_kinds,
        'snapshots': [{'name': e['snapshot'], 'health': e['records'][0]['record']['health_14'],
            'lifeState': e['records'][0]['record']['lifeState_19C'], 'players': e['players']} for e in evidence]}, indent=1))


if __name__ == '__main__':
    main()
