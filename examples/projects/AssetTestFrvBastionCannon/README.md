# AssetTestFrvBastionCannon

Live test C. The M-102 Gunner FRV's gun is replaced by the TD-220 Bastion MK XVI tank cannon.

Expected in game: in a mission where **nobody** brings the Bastion, the FRV gunner seat shows and fires the tank cannon.

Runtime loads the replacement's package through the game's own reference-counted package system before it writes the reference (status `waiting_for_assets` while loading) and keeps it loaded for the session. If the package cannot be made resident the write is refused with `ASSET_UNAVAILABLE` and the vanilla reference stays. See docs/asset-loading.md. Built only; this is a live test that still needs an in-game run.
