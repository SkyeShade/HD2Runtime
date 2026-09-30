# ProjectileSlotTest

Live test for projectile slots on an ordinary weapon's own bullet. Uses the MODS tab (page **Projectile Slot Test**).

The AR-2 Coyote's bullet row is fired by the Coyote alone, so re-pointing its references changes no other weapon.
Natively the bullet has a direct hit (damage plus fire) and no impact or expiry explosion.

| Option | Default | What it does |
| --- | --- | --- |
| Coyote impact explosion | Vanilla (none) | every bullet releases another output's explosion where it hits: Grenade blast (GL-21), EMS stun field (EMS Mortar shell), Gas cloud (Speargun), Napalm burst (EAT-700, with its fire shrapnel) |
| Stun rounds | off | the direct hit becomes the AR-32 Pacifier's (Stun Medium instead of fire) |

Each donor row is only read, and Runtime loads its package before the write. The bullet row is read when a shot is
fired, so the change should reach the next shots without re-equipping; that is part of what this test checks.

**The EMS field and the gas cloud affect Helldivers too.** Test away from your squad and don't shoot at your feet.

## How to test

1. Equip the AR-2 Coyote. Check the log: `ensure coyote-impact` is `ALREADY_DESIRED` or `APPLIED` (Vanilla writes
   nothing).
2. Pick **Grenade blast**, APPLY. Without re-equipping, fire single shots at a wall or the ground: each bullet should
   explode like a GL-21 grenade. If nothing changes, re-equip the Coyote (or call in a new loadout) and try again,
   and report which one it needed.
3. **EMS stun field**: each hit leaves a blue EMS field (7 s) that stuns enemies. **Gas cloud**: a green gas cloud
   (10 s). **Napalm burst**: a fire burst with burning shrapnel.
4. **Stun rounds** on (impact back to Vanilla): a direct hit should stun enemies and no longer set them on fire.
5. Back to Vanilla and Stun rounds off: vanilla Coyote.

For each choice, report:
- whether the effect appeared, and whether it needed a re-equip;
- where it formed (the hit point, or elsewhere);
- whether any other weapon changed;
- how the game performed with an explosion on every bullet.

`allow_unverified_effect` is set: these slot writes are mapped offline, not yet shown in game.
