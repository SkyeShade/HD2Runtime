"""proof/PelicanGatlingProof 0.5.0 (docs/research/pelican-cas-F5FEE03DCFDB.md sections 19-24): the Pelican's own chin
turret as a Gatling Sentry, on the offline Pelican world of tests/test_pelicans.py with the turret fixture of
tests/test_pelican_gatling.py and the hover controller of tests/test_pelican_heading.py: the Gatling read from the game;
projectile, rate, casing, zero aim recoil (0.4.1) and the safe-maximum magazine on the turret's own records; SetBehaviour
213; the target lock (0.4.2: acquired; held through the AI's own re-pick time; a released lock replaced by the
nearest candidate through the game's target setter, with a transition line); the read-only aim error;
the refill; the body facing; the live-proven orbit (requested with its proven shape; the orbit itself:
tests/test_pelicans.py); a summary. The game's routines are simulated; the guards, the writes and the read-back are the
Runtime's own."""
import unittest

from support import ROOT, run, lua as lua_literal
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_weapon import WEAPON
from test_pelican_ai import AI
from test_pelican_heading import HEADING
from test_pelican_readonly_probes import addon, HARNESS

FOLDER = ROOT / 'proof/PelicanGatlingProof'

PROOF = r"""
-- The orbit request is recorded (its callback driven by the test): the orbit itself is tests/test_pelicans.py's.
local orbits={}
pelicans.orbit=function(entity,spec,callback)
    orbits[#orbits+1]={entity=entity,spec=spec,callback=callback}
    return {status='waiting'}
end
local function pending()return b.value(W.read(record(1)+AI.pending,4),0,'i32')end
local function repick()local raw=W.read(record(1)+PE.ai213.repick,8);return b.u32(raw,0)+b.u32(raw,4)*4294967296 end
"""


class PelicanGatlingProofTests(unittest.TestCase):
    def lua(self, body):
        resource, wrapped, _ = addon(FOLDER)
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_pelican_gatling_proof')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + '\n'
            + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI + HEADING + PROOF + body + '\nend)()\n'), b'ok')

    def test_the_source(self):
        _, _, body = addon(FOLDER)
        code = '\n'.join(line.split('--')[0] for line in body.splitlines())
        self.assertIn("local BUILD='0.5.0 GATLING ATTRIBUTION BUILD'", body)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.5.0')
        # Every native call and write goes through runtime/pelican_weapon.lua, runtime/pelican_heading.lua and
        # runtime/pelicans.lua's orbit; no Gatling entity, no fire-window hold, no spawn, no hold.
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction',
                'native_', 'hd2.ensure', 'hd2.patch', 'hold_fire', '.replace(', 'destroy_original', 'pelicans.hold',
                'pelicans.retarget', 'pelicans.spawn', 'hd2.pelican.spawn', 'release_step'):
            self.assertNotIn(forbidden, code, forbidden)
        # The live-tested sources are kept, not packed (only src/ is).
        for kept in ('0.2.0-replacement-addon.lua', '0.3.0-chin-turret-addon.lua'):
            self.assertTrue((FOLDER / 'archive' / kept).exists(), kept)

    def test_the_configuration_the_lock_the_aim_the_refill_the_facing_and_the_summary(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
scene()
controller()
stage(0,2,0)                                                   -- the Pelican approaching
ai(4)                                                          -- its chin turret not active
tick(16)
assert(n('PelicanGatlingProof 0.5.0 GATLING ATTRIBUTION BUILD (solo host)')==1)
assert(n('GATLING CONFIG (#1): SEEN Runtime Pelican 9501 [0.5.0 GATLING ATTRIBUTION BUILD]; round AP4: projectile 275, '
    ..'the MG-206 Heavy Machine Gun\'s (damage 205, AP 4), rate the Gatling Sentry\'s x 2 (read from the game), casing '
    ..'Gatling, ammo 2047 (safe maximum, refilled below 1500), aim recoil ZERO (0 horizontal, 0 vertical), spread 100 mrad, '
    ..'AI 213, target lock on, orbit on, body facing on')==1,lines('SEEN'))
assert(n('GATLING CONFIG (#1): APPLIED: chin turret 8102: projectile 275 (read back), current RPM 3200.00')==1,
    lines('APPLIED'))
assert(n('GATLING CONFIG (#1): AIM RECOIL: ZERO applied: 0 horizontal, 0 vertical a shot (read back; was 2.5, 10)')==1
    and n('PELICAN WEAPON RECOIL (')==1 and n('-> ZERO: 0, 0;')==1,lines('RECOIL'))
-- The frozen tuning: 100 mrad on its own WeaponData instance record, 3200 RPM, the AP4 round 275.
assert(n('GATLING SPREAD (#1): chin turret 8102: 100 mrad applied: 100 horizontal, 100 vertical mrad (read back; the chin '
    ..'turret\'s own 1, 1; the Gatling Sentry\'s 10, 10, read from the game); its own WeaponData instance record only')==1
    and n('PELICAN WEAPON SPREAD (')==1,lines('SPREAD'))
assert(b.value(W.read(WDRECS+PE.spread.instance,4),0,'f32')==100)
-- Attribution: its own no-credit tag cleared (one guarded write).
assert(n('GATLING ATTRIBUTION (#1): SETUP: the call: Pelican 9501 asked for by ')==1 and n('chin turret 8102: wielder '
    ..'8102, Tag mask 0x0000000012000004 (no-credit tag SET), faction 1, network id 701 -> wielder 8102, Tag mask '
    ..'0x0000000002000004 (no-credit tag clear), faction 1, network id 701: its shots are credited by the game')==1,
    lines('ATTRIBUTION'))
assert(b.u32(W.read(TAGVALS,4),0)==0x02000004)
assert(n('GATLING TUNING (#1): spread 100 mrad, rate 3200 RPM, AP4 (projectile 275) (selected: spread 100 mrad, rate 2x, '
    ..'AP4; read back from its own records; the rate slot true)')==1,lines('TUNING'))
assert(n('GATLING AP (#1): AP4: projectile 275, the MG-206 Heavy Machine Gun\'s (damage 205, AP 4); its own ProjectileWeapon '
    ..'copy names projectile 275 (read back); donor row read live: type 275, damage 205, 980 m/s, mass 52')==1
    and n('projectile rows (148 and 275) unchanged true; shared definitions unchanged true')==1,lines('GATLING AP'))
-- Its own aim recoil reads 0 and 0; the rest of its block is its own.
assert(b.value(W.read(WDRECS+AIMD.weaponData.recoilB,4),0,'f32')==0
    and b.value(W.read(WDRECS+AIMD.weaponData.recoilB+4,4),0,'f32')==0
    and b.value(W.read(WDRECS+AIMD.weaponData.recoilB+8,4),0,'f32')==90)
assert(n('GATLING CASING (#1): AFTER: chin turret 8102: casing particles F6F679E12742E627')==1,lines('CASING'))
assert(n('GATLING AMMO (#1): its own magazine holds the safe maximum, 2047 rounds and one chambered')==1
    and n('read back: capacity 2047, rounds 2047 and 2047')==1,lines('AMMO'))
assert(n('GATLING AI (#1): RESULT: chin turret 8102: behaviour BEFORE = 645, behaviour AFTER = 213 (read back)')==1,
    lines('GATLING AI'))
assert(#orbits==1 and orbits[1].spec.radius==40 and orbits[1].spec.altitude==60 and orbits[1].spec.mode=='sweep')
-- The hold; an enemy 40 m east; the AI fires at it: LOCKED; the body turns toward it.
local world=world_module.open()
held(world)
W.add{entity=5555,type='73F8498BFFDCF415',unit=7555,health=500};W.unit(7555,100,70,0)
BOMB.set_clock(T0+1000000);ai(12,5555);tick(2)
assert(n('TARGET LOCKED (#1): t=')==1 and n('entity 5555 (the AI\'s pick), 41.8 m from the muzzle')==1,lines('TARGET'))
assert(pending()==-1 and repick()>T0+1000000,'the re-pick is held')
local x=desired()
assert(x>0.1,'the desired facing turned toward the target')
-- The aim, read-only: the shot passes 1 m above the aim point; the muzzle moves 8 m/s north.
local AW,AT=AIMD.weaponData,AIMD.targeting
W.write(TGRECS+AT.target,W.u32(5555));W.write(TGRECS+AT.point,f32(100)..f32(70)..f32(1))
W.write(WDRECS+AW.aim,f32(100)..f32(70)..f32(2))
W.write(WDRECS+AW.muzzle,f32(60)..f32(70)..f32(12));W.write(WDRECS+AW.muzzleVelocity,f32(0)..f32(8)..f32(0))
BOMB.set_clock(T0+1500000);W.set(5555,{health=400});tick(8)
assert(n('TARGET AIM ERROR (#1)')>=1 and n('the shot crosses 0.94 m above it (1.29 deg)')>=1 and n('the aim point is 1.00 m '
    ..'above its root')>=1,lines('AIM ERROR'))
BOMB.set_clock(T0+3000000);W.set(5555,{health=300});tick(8)
assert(n('TARGET RETAINED (#1)')>=1,lines('RETAINED'))
assert(n('BODY HEADING (#1)')>=1 and n('toward the locked target')>=1,lines('BODY HEADING'))
-- Its rounds fall below 1500: refilled to 2047.
W.write(MGENTS+AMD.entryRounds,W.u32(1400));W.write(MGRECS,W.u32(1400))
tick(2)
assert(n('GATLING AMMO REFILL (#1): t=')==1 and n(' s: 1400 -> 2047')==1,lines('REFILL'))
-- The lock dies: released, the AI's own exit queued; the game takes it.
-- Its last hit is the chin turret's, credited to the local peer: the death is a Pelican kill.
do
    local lo,hi=world_module.local_peer(world)
    local st=world_module.entity_state(world,5555)
    W.write(st.header.records+st.index*440+0x30,W.u32(8102)..W.u32(0)..W.u32(lo or 0x1234)..W.u32(hi or 0))
end
BOMB.set_clock(T0+3500000);W.set(5555,{health=0});tick(2)
-- The Runtime's own entity_died for it (dispatched as its health source would): credited to the local player.
do
    local lo,hi=world_module.local_peer(world)
    require('hd2runtime/runtime/events').dispatch('entity_died',{entity_id=5555,semantic_id='enemy/v1/test/victim',
        killer_peer=lo and world_module.peer_hex(lo,hi)or'0000000000001234',local_killer=true})
end
assert(n('KILL CREDIT (#1)')==1 and n('victim 5555 (enemy/v1/test/victim): its health record\'s last hit: owner 8102, '
    ..'creditor ')==1 and n('(you, the local player)')>=1,lines('KILL CREDIT'))
assert(n('GATLING ATTRIBUTION (#1): CHAIN: the call: Pelican CAS (asked for by ')==1 and n('-> Pelican 9501 -> chin '
    ..'turret 8102 (wielder 8102, Tag mask 0x0000000002000004 (no-credit tag clear), faction 1, network id 701) -> '
    ..'projectile nil')==1 and n('-> victim 5555 (enemy/v1/test/victim)')==1,lines('CHAIN'))
-- A death that was not its kill (last hit by another owner): not counted.
W.add{entity=6262,type='73F8498BFFDCF415',unit=7626,health=0}
require('hd2runtime/runtime/events').dispatch('entity_died',{entity_id=6262,semantic_id='enemy/v1/test/other',
    local_killer=true,killer_peer='0000000000001234'})
assert(n('KILL CREDIT (#1)')==1)
assert(n('TARGET RELEASED (#1)')==1 and n(': dead: entity 5555 is dead')==1 and pending()==4,lines('RELEASED'))
ai(5,0);BOMB.set_clock(T0+3700000);tick(2)
assert(n('TARGET EXIT RAN (#1)')==1,lines('EXIT'))
-- It leaves: the summary.
drop_entity(9501);tick(8)
assert(n('GATLING SUMMARY (#1): chin turret 8102: AI behaviour field after the change 213')==1
    and n('magazine 2047 rounds (safe maximum), 1 refills')==1 and n('aim recoil ZERO applied: 0 horizontal, 0 vertical')==1
    and n('targets: 1 locked')==1 and n('released dead 1')==1 and n('1 exits ran (0 not consumed)')==1
    and n('aim error over 2 samples: vertical 0.94 m mean')==1 and n('spread 100 mrad applied: 100 horizontal, 100 '
    ..'vertical mrad')==1 and n('(last read 100, 100 mrad)')==1
    and n('tuning selected spread 100 mrad, rate 2x, AP4, applied spread 100 mrad, rate 3200 RPM, AP4 (projectile 275)')==1
    and n('orbit never started; shared definitions unchanged true')==1,lines('SUMMARY'))
assert(n('GATLING ATTRIBUTION (#1): SUMMARY: chin turret 8102: no-credit tag cleared true; 0 of its shots seen in the '
    ..'projectile pool: 0 credited to you, 0 to nobody, 0 to another peer; 1 kills by it (its last hit): entity_died '
    ..'credited 1 to you, 0 to nobody, 0 to another player; full chain logged true')==1,lines('ATTRIBUTION'))
return 'ok'
""")

    def test_the_facing_key_and_no_tuning_keys(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
chord('F3')
chord('F4')
assert(n('Ctrl+Shift+F3')==0 and n('Ctrl+Shift+F4 [0.5.0 GATLING ATTRIBUTION BUILD]: body facing OFF')==1,lines('Ctrl+'))
scene()
controller()
stage(0,2,0)
ai(4)
tick(16)
assert(n('AIM RECOIL: ZERO applied')==1,lines('recoil'))
local world=world_module.open()
held(world)
W.add{entity=5555,type='73F8498BFFDCF415',unit=7555,health=500};W.unit(7555,100,70,0)
BOMB.set_clock(T0+1000000);ai(12,5555);tick(8)
local x,y=desired()
assert(n('TARGET LOCKED (#1)')==1 and n('BODY HEADING (#1)')==0 and x==0 and y==1,lines('BODY'))
-- Its aim recoil is zero whatever the keys.
assert(b.value(W.read(WDRECS+AIMD.weaponData.recoilB+4,4),0,'f32')==0)
return 'ok'
""")

    def test_the_spatial_replacement_the_restore_and_the_transition(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
tick(16)
local world=world_module.open()
held(world)
-- 5555 locked; 7777 11.2 m from it, 6666 far away, both in its sight; the turret points at 5555.
W.write(WDRECS+AIMD.weaponData.aim,f32(90)..f32(70)..f32(12))
W.add{entity=5555,type='73F8498BFFDCF415',unit=7555,health=500};W.unit(7555,90,70,12)
W.add{entity=7777,type='73F8498BFFDCF415',unit=7777,health=500};W.unit(7777,100,75,12)
W.add{entity=6666,type='73F8498BFFDCF415',unit=7666,health=500};W.unit(7666,60,110,12)
perceive(5555,90,70,12);perceive(7777,100,75,12);perceive(6666,60,110,12)
BOMB.set_clock(T0+1000000);ai(12,5555);tick(2)
assert(n('TARGET LOCKED (#1)')==1,lines('TARGET'))
-- A stage entry's re-pick takes 6666: restored.
ai(12,6666);tick(2)
assert(n('TARGET RESTORED (#1)')==1 and n('its re-pick had taken entity 6666')==1,lines('TARGET'))
assert(b.u32(W.read(record(1)+AI.target,4),0)==5555)
-- 5555 dies: 7777, the nearest, through the setter; the transition logged.
BOMB.set_clock(T0+1500000);W.set(5555,{health=0});tick(2)
assert(n('TARGET RELEASED (#1)')==1 and n('dead: entity 5555 is dead; 2 candidate(s); replacement: entity 7777, 11.2 m from '
    ..'the old one (within 25 m), a 7.1 degree turn; installed now; the AI\'s own exit from firing not queued')==1,
    lines('RELEASED'))
assert(n('entity 7777 (spatial)')==1,lines('LOCKED'))
assert(n('TARGET TRANSITION (#1)')==1 and n('5555 -> 7777 (spatial; the old one dead): old_pos (90.0, 70.0, 12.0), new_pos '
    ..'(100.0, 75.0, 12.0), distance_between_targets 11.2 m, turret_yaw_delta 7.1 deg (a 7.1 degree turn in all')==1,
    lines('TRANSITION'))
assert(n('PELICAN WEAPON TARGET SET (PelicanGatlingProof 0.5.0 GATLING ATTRIBUTION BUILD #1): chin turret 8102: entity '
    ..'7777')==1 and n('PELICAN WEAPON TARGET SET (')==2,lines('TARGET SET'))
drop_entity(9501);tick(8)
assert(n('targets: 2 locked (1 spatial, 1 the AI\'s pick')==1 and n('1 restored, released dead 1, 0 switched')==1
    and n('1 transitions: 11.2 m between targets on average (max 11.2), a 7.1 degree turn on average (max 7.1)')==1,
    lines('SUMMARY'))
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
