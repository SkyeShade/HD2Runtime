# User report: HMG plan exceeds the guarded read budget (2026-09-30)

A user's mod ("HMG" by Strynox, built with ModBuilder 1.3.1 against SDK 0.27.0) logged:

```
support-plan-ff0bc43a596f53f27e5dfd80 REJECTED code=VALIDATION_FAILED
reason=hd2runtime/core/guarded_transaction.lua:62: transaction read budget exceeded
```

It reported that some magazine and capacity changes did not apply.

## Fixture

- `addon.lua`: the mod's source, byte-identical to the user's `src/addon.lua`.
- `HMG.wrapped.lua`: the Lua resource the user's ZIP ships (extracted from `mod/9ba626afa44a3aa3.patch_0`), exactly
  as ModBuilder wraps it.
- `hd2runtime.json`, `build-report.json`: the user's package metadata.
- `results.json`: the guarded-read profile before and after the fix (`build/scratch/hmg/profile.py`, on the retained
  snapshot).

The mod has two plans:
- **FLAM-40 Flamethrower** (`support-plan-a7d11bc364c94023b9ff184d`): 5 operations, 13 fields.
- **MG-206 Heavy Machine Gun** (`support-plan-ff0bc43a596f53f27e5dfd80`): 6 operations, 19 fields:
  - projectile drag, pellets, penetration slowdown and velocity;
  - fire rate and reload;
  - seven handling fields;
  - four magazine fields;
  - two damage fields.

## Cause

The guarded engine rereads every captured context in each full check. It ran 4 + 2 × changed checks: before and
after opening the pages, before and after every write, and before and after restoring protection. Its fixed cap was
16 MiB.

- **FLAM-40 plan:** 28 contexts, 424,064 bytes, 30 checks, 12.7 MB. It passed.
- **MG-206 plan:** 53 contexts, 925,492 bytes, 42 checks, 38.9 MB. It failed.
  - **Duplicate contexts.** The MG-206 is delivery-resolved, and each of the 6 operations re-captured its call-in
    delivery proof (the StratagemInfo table and three game.dll ranges, 85,584 bytes). That is 20 duplicate contexts
    and 427,920 duplicate bytes, re-read in every check.
  - **The cap was reached mid-commit.** It ran out at the 19th check, the one before the 9th write, after 8 writes had
    landed. The rollback then had no read budget left, so those 8 writes stayed in memory:
    - projectile drag, pellets, penetration slowdown and velocity;
    - fire rate, reload, ergonomics and horizontal spread.

    The remaining handling fields, the magazine and the damage were never written.

Even without the duplicates, 42 checks × 497,572 bytes (20.9 MB) exceeds the fixed cap. A fixed cap cannot scale with
the number of fields.

## Fix (core/guarded_transaction.lua)

1. **Contexts are deduplicated by range.** A copy whose bytes differ fails closed.
2. **One full check right before every write, and one after the last.** There are also checks before opening the
   pages and after restoring protection, changed + 3 in total. The dropped checks repeated one another back to back
   with nothing written in between. A write that disturbs a context, or a change by anything else, is still caught
   before the next write.
3. **The allowance is derived from the plan:** (2 × changed + 6) × context bytes + 8 × target bytes. It covers the
   apply and the worst rollback. A hard ceiling of 64 MiB applies, and a plan above it is refused before any page is
   opened.

## Result

| Plan | Before | After | Allowance |
| --- | --- | --- | --- |
| FLAM-40 | 12,722,024 bytes, 1,019 queries | 6,785,128 bytes, 571 queries | 13,570,464 |
| MG-206 | 38,870,816 bytes, rejected | 10,946,736 bytes, 905 queries, APPLIED | 21,893,776 |

The packaged-runtime scenario `user-report-hmg-read-budget` runs `HMG.wrapped.lua` from the built runtime ZIP. Both
plans apply (13 and 19 writes) and re-apply after the simulated reset.
