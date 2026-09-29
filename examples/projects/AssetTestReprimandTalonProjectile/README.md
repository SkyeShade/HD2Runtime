# AssetTestReprimandTalonProjectile

Live test B. The SMG-32 Reprimand fires the LAS-58 Talon projectile.

Expected in game: with **nobody** carrying the Talon, Reprimand shots are visible Talon laser bolts that hit and damage (before, the swapped projectile was invisible unless someone brought the Talon).

Runtime loads the replacement's package through the game's own reference-counted package system before it writes the reference (status `waiting_for_assets` while loading) and keeps it loaded for the session. If the package cannot be made resident the write is refused with `ASSET_UNAVAILABLE` and the vanilla reference stays. See docs/asset-loading.md. Built only; this is a live test that still needs an in-game run.
