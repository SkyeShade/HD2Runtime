# HaltFeedTest

Live test: the SG-20 Halt's two feeds, modified independently. No options; needs this HD2Runtime test build (not the
published 0.27.0).

The Halt has two magazines, both built into every Halt, switched with its magazine weapon function:

| Feed | Native | This test |
| --- | --- | --- |
| `primary`: FLECHETTES | 8 rounds, flechette pellets | **4 rounds**, and the flechettes **set enemies on fire** (Fire, strength 2) |
| `alternate`: Stun ALTERNATE | 8 rounds, stun pellets | **12 rounds**, stun pellets unchanged |

## How to test

1. Check the log for `transaction halt-feed-capacities APPLIED` (`rounds.feed_capacity_1 8 -> 4`,
   `rounds.feed_capacity_2 8 -> 12`) and `transaction halt-flechettes-burn APPLIED`.
2. Deploy with a Halt (freshly built: capacities are copied into the weapon when it is built).
3. On the flechette magazine: the HUD should show 4 rounds, and hit enemies should catch fire.
4. Switch to the stun magazine: 12 rounds, enemies are stunned and do **not** catch fire.
5. Switch back and forth several times and reload each: the two feeds must keep their own capacity and effect (the
   fire must not appear on stun rounds, the 12 must not appear on flechettes).
6. Check reload, spare rounds and handling behave normally.

Report what each feed showed and did. The feed capacities are weapon data (not yet live-tested for feeds); the fire
status on a projectile row is a live-proven kind of change.
