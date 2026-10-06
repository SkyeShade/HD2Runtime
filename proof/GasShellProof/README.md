# GasShellProof 0.1.0 (development only): Runtime gas shells

The first proof of the Runtime bombardment executor (`runtime/bombardment_executor.lua`). The Orbital Gas Strike's
shell **197** is fired in the Orbital 120mm HE Barrage's pattern by the Runtime, through the game's own projectile
wrapper (FireProjectile, the path of the live-proven `hd2.projectiles.spawn`). The beacon comes from the development
beacon API (`runtime/beacons.lua`).

Solo host; no multiplayer change. Not part of the Gas Barrage: the existing carrier-record Gas Barrage stays the
fallback.

## What happens

1. You throw an **AC-8 Autocannon**. In its first update its delivery becomes **none** (type 0, the empty default row):
   no pod, nothing spawned. This is one guarded write of that beacon's type.
2. When it activates, the Runtime fires, at the beacon's position (its state +0x30, the position the native dispatcher
   uses), **5 salvos of 3 shells 197**:
   - 0.75 s between shells and 2.0 s between salvos, the 120mm's own pattern, read from its live vanilla record;
   - a uniform square scatter of +-27 m;
   - each shell 3000 m above its aim, flying straight down at the row's 400 m/s, fired from your avatar.
3. Each shell's own chain does the rest: explosion 82, the 15 s gas cloud, gas and confusion.
4. Read-only, the proof counts the shells 197 that really appear in the game's projectile pool. It also logs the first
   one's position, velocity, source and owner.

**Never written:**
- the 120mm's or the Gas Strike's records;
- shell 197, explosion 82, any status row;
- any StratagemInfo;
- the mission record, the save, the account.

**Guards** (refused, nothing fired):
- a solo mission as host, with your avatar;
- shell 197's row exactly its reviewed row;
- the 120mm's record exactly vanilla;
- the Gas Strike's call-in package resident (requested at mission start: "READY").

A mission that ends mid-barrage ends it.

## Known differences from a native 120mm barrage

Each is logged as `GAS SHELLS DIFFERENCE n`:

| # | Difference |
| --- | --- |
| 1 | **Origin:** the native shells come from a node of your destroyer with a ballistic aim; these come straight from above at 3000 m |
| 2 | **Aim height:** native shells snap each aim to the ground; these use the beacon's height and hit whatever is below |
| 3 | **Source:** your avatar, not a barrage entity. If you move while a shell is fired, its velocity may be added [I], so **stand still** for this test |
| 4 | **Missing barrage effects:** no launch effect, no "stratagem fire" sounds, no AI incoming warning. The shell's own trail, whistle and impact remain |
| 5 | **Ship modules:** not applied (a native 120mm on your account fires 6 salvos with the extra-salvo module; this fires the 5 asked for) |
| 6 | **Network:** these shells exist on the host only; a native barrage is recreated on every peer |

## Live test

1. Install `HD2Runtime-0.28.0-runtime.zip` (this build) and `GasShellProof-0.1.0.zip`. Disable the other beacon proofs.
   The first proof line is `GasShellProof 0.1.0 RUNTIME GAS SHELLS BUILD`.
2. Put **AC-8 Autocannon** in your loadout. Start a **solo** mission. Wait for `GAS SHELLS READY`.
3. Throw the AC-8 once, some distance away (ideally near enemies), then **stand still** until `GAS SHELLS RESULT`.
4. Expect:
   - `GAS SHELLS BEACON NEUTRALIZED: … AC-8 Autocannon -> none, verified true`;
   - `GAS SHELLS BEACON ACTIVATED: … delivery none …; the dispatcher: spawn requested no`, and **no AC-8 pod**;
   - `GAS SHELLS STARTED …`, then 15 `GAS SHELL n (salvo s)` lines;
   - `GAS SHELLS POOL: the first shell 197 …`;
   - `GAS SHELLS RESULT …: ended: 15 shells …; the game's projectile pool shows 15 shell(s) 197`.
5. **Watch and report:**
   - whether the shells fall;
   - how they look and sound;
   - the explosions;
   - the gas clouds (size, about 15 s);
   - enemies coughing or confused;
   - the shell count and spacing (about 0.75 s within a salvo, 2 s between salvos).
6. **Send** every line starting with `GAS SHELL` or `MISSION START`.
7. **On a crash:** keep the newest dump and the Runtime log.
