# Stratagem mission uses

`hd2.fields.stratagem.max_uses` sets how many times a stratagem can be called in during a mission.
It works for every non-Eagle stratagem, whether its baseline is limited or unlimited.

```lua
-- Exosuits: 3 uses -> unlimited (see examples/projects/ExosuitUnlimitedUses)
hd2.ensure({patch={id='patriot-unlimited',target=hd2.stratagem('EXO-45 Patriot Exosuit'),
    field=hd2.fields.stratagem.max_uses,expect=3,value='unlimited'}})
-- FRV: unlimited -> 2 uses (not gameplay-proven, so acknowledged)
hd2.ensure({patch={id='frv-two-uses',target=hd2.stratagem('M-102 Gunner FRV'),
    field=hd2.fields.stratagem.max_uses,expect='unlimited',value=2,allow_unverified_effect=true}})
```

## Native model

The use count is `StratagemInfo` +80, a u32. The game's own unlimited value is `0xFFFFFFFF`, which
most stratagems carry, including the FRVs. The runtime writes exactly that value for `'unlimited'`,
never a large finite count.

| Baseline | Stratagems |
| --- | --- |
| 3 uses | The four Exosuits and the Orbital Laser |
| Unlimited | Every other non-Eagle stratagem (80) |
| Uses per rearm | The eight Eagles. On Eagles the same field means uses per rearm, exposed as `hd2.fields.eagle.uses_per_rearm`, so `max_uses` is read-only for them |

## Values and transitions

- **Values:** `value` and `expect` are either `'unlimited'` or an integer from 1 to 100. `expect` must
  equal the reviewed baseline.
- **Transitions:** finite → unlimited, unlimited → finite, and finite → a different finite count are
  all supported.
- **Proven change:** Exosuit 3 → `'unlimited'` is gameplay-proven by the Exosuit Unlimited Uses
  reference mod, so it needs no acknowledgement.
- **Unproven changes:** every other change requires `allow_unverified_effect=true`.
- **Host behavior:** the mission host applies use counts, and the HUD counter may show the old value
  until the next mission.

`sdk/StratagemAuthoringCapabilities.json` publishes `maxUses` for every stratagem, with:

- `value`, `mode` (`finite` or `unlimited`) and `writable`;
- `range`, `transitions` and `gameplayProvenValues`;
- `acknowledgement` and `caveat`.

Eagles carry a `reason` instead. The summary counts the stratagems by mode.
