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

## Charges before cooldown (0.31.0)

`hd2.fields.stratagem.rearm_pool` lets a non-Eagle stratagem hold several uses (charges) before a longer wait, the way
Eagles do. It is StratagemInfo +200, a StratagemType naming the rearm that refills the stratagem's uses
(`scripts/research_stratagem_rearm_pool.py`, `research/stratagem-rearm-pool-F5FEE03DCFDB.json`).

```lua
-- Orbital Laser: 5 charges, 15 s apart, refilled all at once by Eagle Rearm (proof/UserRequestsProof).
hd2.ensure({transaction={id='laser-charges',target=hd2.stratagem('Orbital Laser'),allow_unverified_effect=true,
    changes={
    {field=hd2.fields.stratagem.max_uses,expect=3,value=5},
    {field=hd2.fields.stratagem.definition_cooldown,expect=300,value=15},
    {field=hd2.fields.stratagem.rearm_pool,expect='none',value='eagle_rearm'}}}})
```

### Native model

- **Only one pool exists.** Every reader of +200 compares it with 49, StratagemType EagleRearm (the type library's
  alias length matches). It is 49 on the ten Eagle rows and 0 on every other row. There is no other pool and no
  per-stratagem charge counter.
- **Uses.** When the mission's stratagem record is built (game.dll 0x66EFD0), each entry gets its uses from 0x879550:
  row +80, a linked row's bonus, and the player's upgrades.
- **A call** (0xB9A6D0 and its twin 0x135C2C0) sets the entry's cooldown end to its arrival plus the effective cooldown
  (row +104). For a pool member, every other pool entry gets the same end. So each charge is followed by the
  stratagem's own cooldown on the whole pool, Eagles included.
- **The rearm.** Calling Eagle Rearm does the same with the rearm's cooldown (150 s) and refills every pool entry to
  its maximum. Charges come back all at once, never one at a time.
- **Availability.** Eagle Rearm can be called while any pool entry has fewer uses than its maximum (0x66D650). The
  automatic rearm waits until every pool entry has 0 uses (0x66E580).

### The field

| Value | Meaning |
| --- | --- |
| `'none'` (0) | Mission uses: every call starts the stratagem's own cooldown and nothing refills `max_uses` (every non-Eagle row natively) |
| `'eagle_rearm'` (49) | Charges: `max_uses` uses per rearm, `stratagem.cooldown` between charges (shared with the Eagles), Eagle Rearm refills them |

- **Writable** on every catalogued non-Eagle stratagem (86). It is read-only on the Eagles, which are the pool.
  Numbers (0, 49) and the names are both accepted.
- **Finite uses.** In the pool, an unlimited use count would never reach 0, so the Eagles' automatic rearm would stop.
  Joining is refused while the row's use count is unlimited, and so is an unlimited `max_uses` while the row is in the
  pool (`REARM_POOL_UNLIMITED`). Write `max_uses`, `cooldown` and `rearm_pool` in one transaction: they are one
  StratagemInfo object.
- **Coupling.** The pool shares one cooldown. A pooled Orbital Laser with a 300 s cooldown would hold every Eagle for
  300 s after each laser call, and each Eagle call holds the laser for 15 s. Set the stratagem's cooldown to the time
  you want between charges.
- **Acknowledgement.** `allow_unverified_effect`. The readers are proven offline, but no non-Eagle row is in the pool
  natively, and how the mission HUD presents a pooled orbital is untested.
- **When it applies.** Uses are counted when the mission's record is built, so write it on the ship. Calls and rearms
  read +200 every time.
- **Multiplayer.** A per-machine type record. The mission host applies use counts and peers sync the record entries
  (research/slot-cooldown). Every machine should run the same mod.
- **Restore.** Restoring the transaction puts +200 back to 0. The uses already counted in a mission stay until the
  next mission.
