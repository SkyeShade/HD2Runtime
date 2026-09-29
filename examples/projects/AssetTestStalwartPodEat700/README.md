# AssetTestStalwartPodEat700

Live test A. The M-105 Stalwart pod spawns its Stalwart plus an EAT-700 (slot 2 and spawn count 2).

Expected in game: in a mission where **nobody** equips the EAT-700, the pod still opens with a working, pick-up-able EAT-700, not a purple question mark.

Runtime loads the replacement's package through the game's own reference-counted package system before it writes the reference (status `waiting_for_assets` while loading) and keeps it loaded for the session. If the package cannot be made resident the write is refused with `ASSET_UNAVAILABLE` and the vanilla reference stays. See docs/asset-loading.md. Built only; this is a live test that still needs an in-game run.
