# PelicanTurretProbe 0.3.0 (development only, read-only): what the turret fires, and what of it is per instance

**Nothing is written, created or called.** The research (research/docs/pelican-cas-F5FEE03DCFDB.md, section 15) found:

- **What a turret fires.** Its weapon record's flags name the components it has. The chin turret and the Gatling
  Sentry are both *magazine* weapons. After every shot, the game re-derives the magazine's "chambered" type from:
  - the magazine **pattern**, when the weapon has one. The Gatling's is 148, 148, 148, 242, 148;
  - otherwise its **resolved ProjectileWeapon +0**. The chin turret has no pattern, so it fires 120.
- **Resolved** means the entity's own per-instance copy if an entity delta made one when it was created. Otherwise it
  is its type's record, shared by every chin turret. Neither mission snapshot has a single copy.
- **Per instance:** the shot interval (60 / RPM, set once at creation), the rate-of-fire record and current RPM, and
  the magazine record (rounds, chambered type).
- **Shared:** the projectile type, the RPM, the magazine pattern, the turret and the wind-up (spin-up). Wind-up is a
  separate component that the chin turret does not have.

For every chin turret and Gatling Sentry, 0.3.0 adds:
- `TURRET WEAPON`: its path, flags, own copies (or none), interval and RPM, magazine record, heat and wind-up.
- `GATLING CONFIG` (chin turrets only): each value a Gatling configuration would change, and whether this turret has a
  per-instance home for it, then a verdict.
- `TURRET FIRE` while it shoots: rounds and the chambered type, at most 40 lines per turret.

The first line is `PelicanTurretProbe 0.3.0 TURRET WEAPON CONFIG PROBE (read-only)`. Use the same live test as below.
Send also every `TURRET WEAPON`, `GATLING CONFIG` and `TURRET FIRE` line. Say whether the chin gun fired, and whether
the Gatling Sentry spun up before firing.

# PelicanTurretProbe 0.2.0: the parent/child link, read

**0.1.0 live:** every Runtime Pelican's chin turret exists (its entity id is the Pelican's + 1) and acts (its
Behavior record cycles), but its transform position stayed where it was created, so the "within 15 m" test mostly
missed it.

**0.2.0:** the research found the link: a mounted child's **attachable** record names its parent by the parent's
handle link (+0xC) and the parent's node. The probe now reads, for every chin turret and Gatling Sentry: `TURRET LINK`
(its handle link, its attachable record: parent link, node, world position; the parent found **by that link**), and
every 2 s `TURRET FOLLOW` (its attachable position against its parent's pose, and its transform position). For every
Runtime Pelican: `RUNTIME PELICAN TURRET ... rides it by its attachable link: entity N, node M`.

The rest of this page is 0.1.0's, with the build names updated.

# PelicanTurretProbe 0.1.0: the Pelican's chin turret and the Gatling Sentry, observed

**Nothing is written, spawned or called.** Offline research (research/docs/pelican-cas-F5FEE03DCFDB.md, "The Pelican's
turret") found:

- the transport Pelican (`shuttle_transport`, ours) and the extraction Pelican (`shuttle_gunship`) both mount the
  **same chin turret**. It is a separate entity (`shuttle_gunship_turret_hmg`, behaviour 645) spawned on their
  `attach_front_turret` node from their entity type's MountComponentData, which is a **shared definition**;
- the A/G-16 Gatling Sentry is its own entity (`hellpod/turret/gatling_turret`, behaviour 213) with the same kind of
  weapon chain (turret, targeting, weapon data, projectile weapon, magazine, wind-up).

Whether one Pelican's turret can take the Gatling's weapon **per instance** is not established, so nothing is changed.
This probe gathers the live evidence: for every chin turret and Gatling Sentry it reports the Pelican it rides, its
weapon components, and which words of its Behavior record change while it acts (targeting and firing show there). For
every Runtime Pelican it reports whether a chin turret rides it.

## Which build is running

The first line names the build (0.3.0: `TURRET WEAPON CONFIG PROBE`); Ctrl+Shift+F5 prints the status.

## Live test

**Setup:** this hand-off's HD2Runtime runtime ZIP, `PelicanTurretProbe-0.3.0.zip`, and `PelicanCasProof-0.1.1.zip`
or `PelicanSpawnProof-0.2.0.zip` (to call a Runtime Pelican); a Gatling Sentry in your loadout; solo, as host.

1. In a mission with enemies, call a Runtime Pelican (Pelican CAS, or PelicanSpawnProof Ctrl+F8) near enemies.
   Expect `TURRET SEEN (#n): the Pelican chin turret ... rides the shuttle_transport ... a Runtime Pelican`, and
   `RUNTIME PELICAN TURRET: ... a chin turret rides it` (or `NO chin turret`).
2. Watch: does the Pelican's chin gun fire at enemies? `TURRET STATE` lines show its record changing.
3. Place the Gatling Sentry near enemies. Expect `TURRET SEEN (#n): the Gatling Sentry ...` and `TURRET STATE` lines
   while it fires.
4. Expect `TURRET GONE` lines when they leave.

**Send** every line starting with `PelicanTurretProbe`, `TURRET` (SEEN, LINK, FOLLOW, STATE, GONE), `RUNTIME PELICAN TURRET` and `Ctrl+Shift+F5`, and
say whether the Pelican's chin gun fired, at what, and how the Gatling Sentry behaved.
