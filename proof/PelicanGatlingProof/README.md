# PelicanGatlingProof 0.5.0 (development only, solo host): frozen tuning, kill attribution

The first line is `PelicanGatlingProof 0.5.0 GATLING ATTRIBUTION BUILD (solo host)`. Install this hand-off's runtime ZIP,
`PelicanGatlingProof-0.5.0.zip` and `PelicanCasProof-0.1.1.zip`. Research: docs/research/pelican-cas-F5FEE03DCFDB.md
section 24.

**Frozen tuning** (the Pelican CAS defaults for now; the Mod Options settings are gone):
- the MG-206's AP4 round 275;
- 3200 RPM (2x the Gatling Sentry's rate, read from the game);
- 100 mrad spread and zero aim recoil;
- the Gatling casing, and the 2047-round magazine refilled below 1500.

Targeting, the orbit and body facing are 0.4.5's. Lighter logging: the aim error, body heading, fire, orbit and retained
lines come every 10 s, stage changes only for the first 30, and the target-setter lines for the first 10 calls, then
every 25th.

**Why the chin gun's kills were credited to nobody.** A turret shot's owner is its weapon's wielder, and its creditor
comes from the game's own creditor routine: the peer owning the wielder's network object. That routine gives no one
when the wielder carries the no-credit tag 0x10000000; the game gives the same tag to an Eagle with no owner. The chin
turret wields itself and its data gives it that tag, so every chin-turret bullet carried no creditor. A kill credits the
victim's last creditor, so the Pelican's kills went to nobody, or to whoever had hit that enemy before.

**Now.** One guarded 8-byte write clears that tag in the chin turret's own Tag mask (0x12000004 → 0x02000004); every
other bit is kept. The game's own routine then names the owner of the turret's network object, the host, which is the
caller (Runtime Pelicans are host-only). That is the same derivation a native self-wielding sentry's shots go through.
- **Refused unless:** the turret wields itself, has faction bit 0 and a network id, and carries the tag.
- **Unchanged:** no definition, no other entity, no code.

**Lines:**
- `GATLING ATTRIBUTION (#n): SETUP: the call: Pelican N asked for by … ; the caller: the local player, peer …, avatar …;
  chin turret T: wielder T, Tag mask 0x0000000012000004 (no-credit tag SET) … -> … (no-credit tag clear) …`
- `GATLING ATTRIBUTION (#n): SHOT: projectile 275 in pool slot S: source T (the chin turret), owner T, creditor <peer>
  (you)`: its shots as the projectile pool holds them.
- `KILL CREDIT (#n): victim V (<semantic id>): its health record's last hit: owner T, creditor <peer> (you); entity_died:
  killer <peer> (you, the local player)`: the first five kills whose last hit was the chin turret's.
- `GATLING ATTRIBUTION (#n): CHAIN: the call -> the player -> Pelican -> chin turret -> projectile -> victim -> credited`:
  the full chain, once.
- `GATLING ATTRIBUTION (#n): SUMMARY`: shots seen (credited to you, to nobody, to another peer) and kills by the chin
  turret (credited to you, to nobody, to another player).

**Live test (solo host):**
1. Call Pelican CAS near enemies.
2. Let it kill some, and do not shoot them yourself.
3. Expect `SETUP … no-credit tag clear`, `SHOT … creditor … (you)`, `KILL CREDIT … killer … (you, the local player)`,
   one `CHAIN` line, and a `SUMMARY` with every shot and kill credited to you. Check the mission-end kill count too.
4. Send every line starting with `PelicanGatlingProof`, `PELICAN `, `GATLING `, `TARGET `, `KILL `, `BODY ` and
   `assets for`.

# PelicanGatlingProof 0.4.5 (development only, solo host): combat tuning

The first line is `PelicanGatlingProof 0.4.5 GATLING COMBAT BUILD (solo host)`. Install this hand-off's runtime ZIP,
`PelicanGatlingProof-0.4.5.zip` and `PelicanCasProof-0.1.1.zip`. Everything else is 0.4.4's: targeting, orbit, body
facing, ammunition refill, zero recoil, AI, casing, and the 1600 / 2400 / 3200 RPM path.

**Settings** (MODS tab → Pelican Gatling Proof), read when each Pelican appears:
- **Chin gun spread:** 25, 50 (default), 75 or 100 mrad, horizontal and vertical alike.
- **Chin gun fire rate:** Normal (1600 RPM, default), 1.5x (2400), 2x (3200).
- **Chin gun armor penetration:** Standard (default) or AP4.
  - **Standard:** projectile 148, the MG-43 Machine Gun's round (damage 125, AP3).
  - **AP4:** projectile 275, the MG-206 Heavy Machine Gun's round. Damage record 205: AP4 direct, slight and large; 150
    damage, 35 durable; 980 m/s; mass 52. It is the same round the FRVs and the Bastion's coaxial gun fire.

**The AP4 donor.** The reasonable AP4 conventional rounds, from the existing research:

| Projectile | Fired by | Why or why not |
| --- | --- | --- |
| **275** | MG-206 HMG, FRVs, Bastion coaxial gun | **chosen:** the heavy machine gun round; its own small package |
| 251 | TD-110 Maelstrom coaxial gun | the same round; only a visual resource differs, and its package is the whole tank |
| 68 | EXO-55 Breakthrough | AP4, but a slow, light pellet (385 m/s) |
| 226 | APW-1 Anti-Materiel Rifle | a sniper round |

**How it is applied:**
- Only that Pelican's own ProjectileWeapon copy names projectile 275; no projectile or damage definition is written.
- The rows of 148 and 275 are compared before and after.
- The MG-206's package is requested at mission start through the asset loader.
- 275's row is read live before use (type, damage record 205, 980 m/s, mass 52). Anything else refuses the AP4 round.
- If the package fails to load, that Pelican fires the standard round, with a log line.
- The casing stays the Gatling's.

**Lines:**
- `GATLING AP (#n): AP4: projectile 275, the MG-206 Heavy Machine Gun's (damage 205, AP 4); its own ProjectileWeapon copy
  names projectile 275 (read back); donor row read live: …; projectile rows (148 and 275) unchanged true; shared
  definitions unchanged true`;
- `GATLING TUNING (#n): spread 50 mrad, rate 3200 RPM, AP4 (projectile 275) (selected: …)`;
- `Mod Options [...]: chin gun spread …, rate …, penetration … -> …`, on each APPLY;
- the summary: `tuning selected …, applied …`.

# PelicanGatlingProof 0.4.4 (development only, solo host): tuning build

0.4.4 was built but never live-tested; 0.4.5 carries it with new spread choices and the armor penetration setting.

**Settings** (MODS tab → Pelican Gatling Proof). Both are read when each Pelican appears, so change them and APPLY
between call-ins.
- **Chin gun spread** (full width, horizontal and vertical alike): Precise 1, Mild 5.5 (default), Gatling 10, Wide 20,
  Very Wide 30, Extreme 50 mrad. It is written to that Pelican's own WeaponData instance record, as in 0.4.3.
- **Chin gun fire rate:** Normal (default) is the Gatling Sentry's rate read from the game, 1600 RPM; 1.5x is 2400 and
  2x is 3200. It goes through the same per-instance current RPM and rate slot as Normal. The Gatling rate read from the
  game must still be 30–3000 RPM; only the allowlisted factor multiplies it.

The 2047-round magazine and the refill below 1500 are unchanged. At 3200 RPM it refills about every 10 s of firing (about 548 rounds at 53 a second).
Without Mod Options Menu, every Pelican gets Mild and Normal.

**Lines:**
- `GATLING TUNING (#n): spread 30 mrad, rate 3200 RPM (selected: spread 30 mrad (Very Wide), rate 2x; read back from its
  own records; the rate slot true)`;
- `Mod Options [...]: chin gun spread … , rate … -> … for Pelicans seen from now on`, on each APPLY;
- the summary: `tuning selected …, applied …`, plus the measured RPM while firing.

# PelicanGatlingProof 0.4.3 (development only, solo host): spread experiment

0.4.3 was built but never live-tested; 0.4.4 carries it, with the spread choices widened. Everything else is 0.4.2's: targeting, body facing,
ammunition, zero aim recoil. Research: docs/research/pelican-cas-F5FEE03DCFDB.md section 22.

**Where the spread lives.** Every shot turns its direction by two random angles. They come from the weapon's own
WeaponData instance record: +0x58 is the horizontal width and +0x5C the vertical width, full widths in milliradians, so a
shot turns by up to half of each, each way. The record took its type's spread once, at creation. The chin turret's is
1 mrad (±2.5 cm at 50 m) and the Gatling Sentry's 10 mrad (±25 cm at 50 m).

**The setting.** MODS tab → Pelican Gatling Proof → Chin gun spread:
- **Precise:** the chin turret's own spread, 1 mrad (nothing written).
- **Mild** (default): halfway between the chin turret's and the Gatling Sentry's, 5.5 mrad.
- **Gatling:** the Gatling Sentry's exactly, 10 mrad, read from the game.

The value is read when each Pelican is seen, so change it and APPLY between calls to compare Pelicans in one mission.
Without Mod Options Menu, every Pelican gets Mild. Only that Pelican's own WeaponData instance record is written; no
type or shared definition is.

**Lines:**
- `GATLING CONFIG … SEEN … spread MILD … (spread from Mod Options ready, saved/menu/default)`;
- `GATLING SPREAD (#n): chin turret N: MILD applied: 5.5 horizontal, 5.5 vertical mrad (read back; the chin turret's
  own 1, 1; the Gatling Sentry's 10, 10, read from the game)`;
- `Mod Options [...]: chin gun spread MILD -> GATLING for Pelicans seen from now on`, on each APPLY;
- `GATLING SPREAD … CHANGED`, if anything changes its spread while it flies (not expected);
- the summary: `spread … (last read …)`.

**Live test:** call Pelican CAS three times in one mission, with the setting at Precise, Mild and Gatling (APPLY before
each call). Send every line starting with `PelicanGatlingProof`, `PELICAN `, `GATLING `, `TARGET `, `BODY `, `Mod Options`
and `assets for`, and how each Pelican's fire looked and hit.

# PelicanGatlingProof 0.4.2 (development only, solo host): target lock fixed, spatial replacement

0.4.2 was built but never live-tested; 0.4.3 carries it unchanged. Everything else is 0.4.1's: zero aim recoil,
spread and aim math unchanged, the body facing toward the locked target. Research: docs/research/pelican-cas-F5FEE03DCFDB.md
section 21.

**Why 0.4.1 never locked.** The lock refused any target farther than 100 m from the chin turret. It took the turret's
position from its transform record, which the game never updates for a mounted child (the scene graph places it). That
record kept the turret's creation point, where the Pelican spawned, about 250 m from every target. So every target
failed, every update. The targets were alive, so the "firing at nothing" release never fired either: no line at all.
The distance is now measured from the turret's muzzle (its WeaponData record, live: the one TARGET AIM ERROR prints).

**The lock now:**
- **Locked:** the AI's own target while it aims (stage 5) or fires (stage 12), alive. Its periodic re-score is held
  off.
- **Restored:** a stage change makes the AI re-pick at once, which holding cannot stop. When that re-pick takes another
  target while the lock is alive and in its sight, the lock is put back through the game's own target setter, the call
  the AI's own pick makes. The same applies if it drops out of sight for a moment and comes back.
- **Released** when:
  - it dies;
  - it is out of sight for 0.5 s;
  - it takes no damage for 2 s of firing;
  - the AI aims at it for 3 s without firing.

  The last two are not locked again for 5 s.
- **Replaced** by the enemy nearest where it was:
  - perceived, hostile and alive;
  - within 25 m, else 50 m;
  - scored by distance plus 0.5 m per degree of turret turn.

  It is installed through the setter. While firing that happens at once if the turn is at most 12 degrees. A bigger
  turn goes through the AI's own exit from firing first, so it fires again only within 3 degrees. With no enemy that
  close, the AI's own pick stands.
- **Check rate:** every 0.05 s.

**New lines:**
- `TARGET RESTORED`;
- `TARGET RELEASED … replacement: entity N, X m from the old one, a Y degree turn; installed now / after the AI's own exit`;
- `TARGET TRANSITION: old -> new (how; the old one …): old_pos, new_pos, distance_between_targets, turret_yaw_delta`;
- `PELICAN WEAPON TARGET SET` (each setter call).

The summary counts spatial locks, restores and transitions (mean and maximum distance and turn).

**Live test:** as 0.4.1, below. Send every line starting with `PelicanGatlingProof`, `PELICAN `, `GATLING `, `TARGET `,
`BODY ` and `assets for`, and what the chin gun did: does it work through a group instead of snapping across the
field? Do the big aim-error spikes still come with the transitions?

# PelicanGatlingProof 0.4.1 (development only, solo host): zero aim recoil

One change from 0.4.0: the chin turret's own aim recoil (its WeaponData block B) is set to **0 horizontal / 0 vertical
per shot** instead of the Gatling Sentry's (0 / 3). The log says so:
- `GATLING CONFIG … AIM RECOIL: ZERO applied: 0 horizontal, 0 vertical a shot (read back; was 2.5, 10)`
- `PELICAN WEAPON RECOIL … -> ZERO: 0, 0`

Ctrl+Shift+F3 turns it off, which gives the chin turret's own recoil. Everything else is 0.4.0's, below. The first line is
`PelicanGatlingProof 0.4.1 GATLING ZERO-RECOIL BUILD (solo host)`. Install this hand-off's runtime ZIP,
`PelicanGatlingProof-0.4.1.zip` and `PelicanCasProof-0.1.1.zip`.

# PelicanGatlingProof 0.4.0 (development only, solo host): target lock, aim, safe ammunition, body facing

The Pelican's own chin turret, configured as a Gatling Sentry. It keeps its entity, model, mount, node 41, parent link and
movement. Nothing shared is written: every Pelican, Gatling, weapon, magazine, WeaponData and projectile definition is
read, never changed, and compared whole before and after.

Research: docs/research/pelican-cas-F5FEE03DCFDB.md, sections 19 and 20. Earlier sources are kept in `archive/`: 0.2.0,
the physical Gatling replacement, set aside; and 0.3.0, the first chin-turret build, live-tested.

## What 0.3.0 showed live, and what changed

**Ammunition.**
- **Found:** the rounds are an 11-bit network field. Every shot queues them for replication, and the flush saturates
  the host's own count to 0..2047. That is why 4999 became about 2047 as soon as it fired.
- **Now:** its own magazine holds the safe maximum, 2047, plus one chambered round. Below 1500 the Runtime refills both
  of its own round counts to 2047, the way the game's own refill does. No reload, chamber, spare magazine or shared
  definition is touched. The log line is `GATLING AMMO REFILL: old -> new`.

**Aiming above targets.** The turret's pointing math is fine. The bullets' aim point is what moves:
- **Recoil (fixed):** the chin turret's own aim recoil kicks 10 up and 2.5 sideways per shot, against the Gatling
  Sentry's 3 and 0, and it is applied every shot at 1600 RPM. The turret's own WeaponData now takes the Gatling's aim
  recoil (`GATLING CONFIG … AIM RECOIL`). Ctrl+Shift+F3 turns this off so the two can be compared.
- **Own-motion lead (logged, not fixed):** the AI leads for the Pelican's own motion, but the bullets never get that
  velocity. It is type and global data, so nothing per-instance reaches it.
- **Aim node:** the AI aims at the target's aim node nearest the turret, which from above is high on the target.
- `TARGET AIM ERROR` splits the miss every second while firing, read-only. Spread is unchanged: the chin turret's is 10x
  tighter than the Gatling's, and it comes after the aim.

**Target switching.** The Gatling AI has no lock and re-scores every second. The Runtime now:
- holds the AI's own re-pick time while the locked target stays its target, so the AI keeps it;
- releases it through the AI's own exit from firing when it dies, after 1 s out of sight, or after 2 s of firing with no
  damage;
- does not lock an unhittable target again for 5 s.

The log lines are `TARGET LOCKED`, `RETAINED`, `LOS`, `RELEASED`, `SWITCHED` and `EXIT RAN`. A queued exit is now confirmed
when the AI consumes it, even if it is back in firing at once (0.3.0's "not consumed" was that case).

**Body facing.**
- **Why it didn't turn:** in the hold, the hover controller turns the body toward a per-instance desired facing that
  nothing sets.
- **Now:** the Runtime turns that facing toward the locked target, 40 degrees per second at most, and the game's
  controller turns the body smoothly. With no target the heading is kept. It stops for good if anything else changes the
  facing. Log line: `BODY HEADING`. Ctrl+Shift+F4 turns this off.

**Kept:**
- behaviour 213;
- projectile 148 at the Gatling Sentry's exact rate (1600);
- the Gatling casing;
- the live-proven orbit;
- the mission-only CAS presentation and carrier (PelicanCasProof, unchanged).

**Keys** (each applies to Pelicans seen from then on):
- Ctrl+Shift+F2: rate.
- Ctrl+F9: AI on/off.
- Ctrl+F10: pattern on/off.
- Ctrl+F11: orbit on/off.
- Ctrl+Shift+F3: Gatling aim recoil on/off.
- Ctrl+Shift+F4: body facing on/off.
- Ctrl+Shift+F1: status.

## Which build is running

The first line is `PelicanGatlingProof 0.4.0 GATLING LOCK-AIM-AMMO BUILD (solo host)`.

## Live test

**Setup:** solo host. Install this hand-off's runtime ZIP, `PelicanGatlingProof-0.4.0.zip` and `PelicanCasProof-0.1.1.zip`.
Install no other Pelican proof alongside them.

1. Call Pelican CAS near a group of enemies. During the approach, expect:
   - `GATLING CONFIG … REFERENCE`, `… APPLIED`, `… AIM RECOIL`;
   - `GATLING CASING`;
   - `GATLING AMMO` (2047);
   - `GATLING AI … behaviour AFTER = 213`.
2. While it orbits, watch the chin gun and note:
   - does it keep one target until that target dies (`TARGET LOCKED` then `RETAINED`), rather than switching?
   - does it hit, or still fire above? `TARGET AIM ERROR` gives the numbers;
   - does the nose turn toward its target (`BODY HEADING`), smoothly?
   - when a target dies or hides: `TARGET RELEASED`, then a new lock;
   - a target it can't hit: released after 2 s, firing stops;
   - the ammunition: `GATLING AMMO REFILL` lines, firing never stops for lack of rounds.
3. Optional: Ctrl+Shift+F3 (aim recoil off), call CAS again, and compare `TARGET AIM ERROR`.
4. After it leaves: `GATLING SUMMARY`.

**Send** every line starting with `PelicanGatlingProof`, `PELICAN `, `GATLING `, `TARGET `, `BODY ` and `assets for`, and
what the chin gun and the Pelican did.
