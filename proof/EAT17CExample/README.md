# EAT77ExpendableCluster 0.3.0: EAT-77 Expendable Cluster

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| EAT-77 Expendable Cluster | ↓↓←↓← (DOWN DOWN LEFT DOWN LEFT) | 70 s | unlimited |

> A single-use weapon that comes down in pairs. Explodes into a cluster of lesser explosions upon impact.

Item traits: CUSTOM STRATAGEM, SUPPORT WEAPON, MEDIUM ARMOR PENETRATING, ANTI-TANK, EXPENDABLE.

The EAT-17C renamed: two EAT-17 clones from one pod firing the RL-77 Airburst's rocket, which bursts into a cluster of bomblets. Its code is DOWN DOWN LEFT DOWN LEFT (the requested DOWN DOWN LEFT UP LEFT is the EAT-700's own).

The log names this build: `EAT77ExpendableCluster 0.3.0 BUILD`.

## What to look for in a live test

1. Two launchers in the pod, with this name and icon.
2. Each rocket bursts into the cluster.
3. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

The expendable family (live-proven with several players): the round is converted on every machine at its mission start, like the clone.

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
