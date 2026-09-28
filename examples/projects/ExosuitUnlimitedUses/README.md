# ExosuitUnlimitedUses

Recreates the Exosuit Unlimited Uses v2 reference mod through `hd2.fields.stratagem.max_uses`. Each
Exosuit call-in (`StratagemInfo` +80) goes from 3 uses to `'unlimited'`, which the runtime writes as the
game's own unlimited value (0xFFFFFFFF, the value the FRVs and most stratagems already carry), not a
large finite count. The reference mod demonstrated this exact transition in game, so no
`allow_unverified_effect` is needed. Mission uses are applied by the mission host, and the HUD counter
may keep showing 3 until the next mission. This was built only, not deployed or launched.
