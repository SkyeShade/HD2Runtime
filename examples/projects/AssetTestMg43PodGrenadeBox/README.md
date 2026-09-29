# AssetTestMg43PodGrenadeBox

Live test D. The MG-43 Machine Gun pod opens with a Grenade Box instead of the MG-43.

Expected in game: a normal, interactable grenade box in the pod, even on a mission where no grenade boxes were placed in the level.

Runtime loads the replacement's package through the game's own reference-counted package system before it writes the reference (status `waiting_for_assets` while loading) and keeps it loaded for the session. If the package cannot be made resident the write is refused with `ASSET_UNAVAILABLE` and the vanilla reference stays. See docs/asset-loading.md.

**Live result (2026-09-29): PASS.** The Grenade Box spawned correctly from the MG-43 pod and could be picked up. The rack/pickup pair itself still needs `allow_unverified_reference` in general; this exact pair is recorded as live-verified in `sdk/PodPayloadCapabilities.json` (`liveVerifiedPairs`).
