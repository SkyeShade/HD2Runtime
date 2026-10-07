# In-game options

HD2Runtime can bind operations to the in-game **MODS** tab that CowboyBingus
**Mod Options Menu** adds to the escape menu. A player moves a slider and presses APPLY, and
the value your mod declared becomes the new desired value of one `hd2.ensure`. That ensure
re-runs the full guarded path: same target, same acknowledgements, same conflict checks.

```lua
local hd2=require('mods/skyeshade/hd2runtime')
local options=hd2.options({id='liberator_damage',title='Liberator Damage'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true})
local damage=options:slider({id='damage',label='AR-23 Liberator Damage',min=90,max=500,step=10,default=150})
return hd2.ensure({enabled=enabled,patch={id='liberator-damage',allow_shared=true,
    target=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile(),
    field=hd2.fields.damage.player_standard_damage,expect=90,value=damage}})
```

See the `LiberatorDamageOptions` example project.

## Requirements: an optional dependency

| Component | Version | Needed by |
| --- | --- | --- |
| HD2Runtime | 0.25.1+ | Mods that call `hd2.options` (0.25.0 has no `fallback`: it rejects the key, and without the menu it always keeps bound operations inactive) |
| Bingus Shared Loader | v15+ / API 1 | HD2Runtime itself (unchanged) |
| Mod Options Menu (CowboyBingus) | v1+ (api 1) | Only the configurable settings of mods that call `hd2.options` |
| Bingus Shared Loader | v18+ | Only when Mod Options Menu is installed (it requires v18) |

Mod Options Menu is an **optional enhancement**. HD2Runtime never requires it, and neither do
mods that do not call `hd2.options`: those behave exactly as before, never look for the menu,
and never log about it. It supports Steam build 25480438 only, the same build this HD2Runtime
release is pinned to; on any other build it does not add the tab.

For a mod that does call `hd2.options`:

- **Menu installed and compatible:** options register, persisted values are used, and every
  bound `hd2.ensure` runs normally with live changes.
- **Menu missing, incompatible, or rejecting an option:** HD2Runtime logs **one warning per
  options page**. What happens next depends on the page's `fallback`:

  | `fallback` | Bound operations without the menu |
  | --- | --- |
  | `'default'` (the default) | Run normally with each unavailable option's **declared default**, through the same guarded path |
  | `'disable'` (strict) | Stay **inactive for the session**: status `unavailable`, no writes, removed from the scheduler |

  ```
  [HD2Runtime] options liberator_damage unavailable: Mod Options Menu is not installed; using configured defaults
  [HD2Runtime] options liberator_damage unavailable: Mod Options Menu is not installed; configurable operation will not be applied (liberator-damage)
  ```

  The first line is the default mode; the second is strict mode, which names the operations
  it keeps inactive. Operations in the same mod that are not bound to options run normally
  in both modes, as do other mods.

Choose strict mode only if your mod must not change anything unless the player has configured
it. Tools that generate mods should use the default mode.

```lua
local options=hd2.options({id='liberator_damage',title='Liberator Damage'})                     -- defaults
local strict=hd2.options({id='liberator_strict',title='Liberator Strict',fallback='disable'})   -- strict
```

Defaults are not a bypass. A declared default is validated like every other value in the
option's domain when the `hd2.ensure` is declared (see *Binding an operation*). A default the
operation would reject (outside the field's reviewed range, fractional for an integer field, or
missing an acknowledgement) fails at startup, in both modes, before the menu is ever consulted.

How availability is decided:

- It is decided **once per session**. A present menu is judged on the first update tick. An
  absent one gets 5 update seconds, because it may load after your mod; after that the result
  is final. Bound operations wait for that result (status `waiting_for_options`), so without the
  menu the defaults apply after about 5 seconds.
- A missing or incompatible result is **never probed again**. Options declared later inherit
  it immediately.
- A menu whose `api` is not 1, or that lacks `register_option`, `get` or `on_change`, is
  incompatible. The reason names the api it reported.
- If a registration is **rejected** (for example "option already registered differently"),
  only that option is unavailable. It uses its default (or, in strict mode, keeps its
  operations inactive). Other options on the page stay live.
- A menu that **errors during registration, or disappears after it was found**, makes the
  affected options unavailable. It is not retried.
- An option id **declared twice**, by your mod or by another mod using the same ids, is not
  fatal. The later declaration is unavailable and logged.

Each handle reports this in `:available()` and in `:describe().state`
(`pending`, `ready` or `unavailable`), with `:describe().reason` and `:describe().fallback`. An
unavailable option's value is always its declared default (`:describe().source` is `default`),
even if the menu returned a saved value before it failed. A bound ensure running on defaults
reports `option_defaults = true`.

Declare the optional dependency in your project's `hd2runtime.json` beside the unchanged
`requires` block:

```json
"optional": {"mod_options_menu": {"min_version": "1.0.0", "api": 1, "bingus_min_release": 18}}
```

The SDK and starter builders validate this block and add an "Optional: … Mod Options Menu"
note to the manager description. It never gates loading.

## The Mod Options Menu contract

This is the behavior of Mod Options Menu v1.0.1 (api 1), which HD2Runtime wraps:

- **Registration.** `ModOptionsMenu.register_option(id, spec)` returns `true`, or `false`
  and a reason. The `id` keys the saved value, so it must stay stable. Registering the same
  id again succeeds only if the spec is identical. There is no unregister.
- **Controls.**
  - `toggle`: a boolean, `false` by default.
  - `choice`: 2–16 names; the value is the 1-based index. Names are shown uppercased, and
    words the game already translates (ON, OFF, LOW, HIGH…) are translated.
  - `slider`: `min < max` and `0 < step <= max - min` (step 1 by default). Values snap to the
    step and are clamped to `min..max`. The row shows up to 3 decimals; a whole-number step
    and minimum give an integer slider.
- **Layout.** Each `mod` name becomes a category button: at most 8 mods, 32 options each.
  `gap = true` adds space above a row, and `description` (up to 400 bytes) is shown in the
  game's description box. There is no heading or group control, and rows cannot be hidden
  or disabled after registration.
- **Applying.** Edits take effect only when the player presses APPLY (Tab). Leaving with
  unapplied edits shows the game's UNAPPLIED CHANGES prompt, and confirming it discards them.
  On APPLY, every changed option's `on_change(value, id)` callbacks run once, in
  registration order. `set(id, value)` from code does not call callbacks.
- **Persistence.** Applied values are saved to
  `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\ModOptionsMenu.values` about 1 s after
  APPLY, and whenever the menu closes. At registration a saved value is re-validated: a
  slider value is snapped and clamped to the current range, and anything unusable falls back
  to the default. The menu saves only while its native integration is active.
- **Load order.** The menu may load before or after a dependent mod, so registration must
  wait for the global `ModOptionsMenu` to exist.

## HD2Runtime API

`hd2.options({id, title, fallback})` declares one options page. `title` is the category button
label (up to 40 characters). `id` (letters, digits, `_` or `-`) prefixes every option id, so the
saved ids are `<page id>.<option id>`. Keep both stable across releases. `fallback` is
`'default'` (the default) or `'disable'`; see above. Declaring the same page again with another
title or fallback is an error.

| Method | Native control | Value |
| --- | --- | --- |
| `options:toggle{id, label, default=false, description, gap}` | toggle | boolean |
| `options:slider{id, label, min, max, step=1, default=min, description, gap}` | slider | number, snapped to `step` |
| `options:choice{id, label, choices, values, default=1, description, gap}` | choice | `values[index]` (the index if `values` is omitted) |

A choice's `values` may be numbers, semantic names (letters, digits, `_`, `-` and `.`, such as the penetration label
`'medium'`) or typed semantic reference handles, such as `weapon:attack(role):projectile()` or
`hd2.attack_output(name)`. A choice of references selects between complete compositions of one reference field. For
example, `LiberatorAttackOutputTest` switches the Liberator's projectile between its own bullet and two donor
outputs. Each change is one owned transition, and a donor's assets are loaded before its write. See
[attack outputs](attack-outputs.md).

Declarations are checked against the menu's limits at startup and fail with a clear error.
Registration happens on the first update ticks, whatever the load order. Each handle has:

- `:get()`, the current value;
- `:index()`, for choices;
- `:describe()`, returning id, kind, label, default, value, range, choices, values,
  `registered`, and `source` (`default`, `saved`, or `menu`).

A value from the menu or its saved file that is not usable is ignored and logged.

### Binding an operation

Pass a slider or choice handle as a field `value` anywhere in an ensured patch, transaction,
or plan, or as an element of a list `value` (one slider per rate in `fire_rate.modes`, see `HMGFireRateModesTest`).
Pass a toggle as `enabled`:

```lua
hd2.ensure({enabled=toggle, transaction={id='firebomb', target=hd2.booster('Firebomb Hellpods'):explosion(),
    allow_shared=true, allow_unverified_effect=true, changes={
        {field=hd2.fields.explosion.inner_radius, expect=2, value=inner},
        {field=hd2.fields.explosion.outer_radius, expect=4, value=outer}}}})
```

Rules:

- **Only `hd2.ensure` owns bound values.** `hd2.patch`, `hd2.transaction`, and `hd2.plan`
  reject option handles, because they resolve once.
- **Handles bind only `value`.** `expect` stays the reviewed baseline and never follows an
  option. A toggle can only be `enabled`.
- **The whole option domain is validated when the ensure is declared.** For a slider: its
  minimum, maximum, default, and first step. For a choice: every value. Each goes through
  the operation's normal validation, so a slider wider than a field's published safe range,
  a fractional slider on an integer field, a read-only field, or a missing `allow_shared`,
  `allow_unverified_effect`, or `allow_unverified_reference` fails at declaration, not in
  game. The restore request (every value back to `expect`) is validated too.

### What happens on a change

1. The handle updates only if the applied value actually differs. A no-op APPLY does no work.
2. Any in-flight resolution of that ensure is cancelled. This is always safe: guarded writes
   never yield, so a pending resolution has written nothing.
3. After a 0.5 s debounce, the whole request is validated again with the new values.
   Several options applied together cause one resolution.
4. The same logical operation resolves and writes through the normal guarded path.

The live value may be the reviewed baseline, the new desired value, or the exact bytes this
same ensure verified last time. The last case is an owned transition, not a conflict.
Anything else is still a `CONFLICT`. A transaction or plan changes all of its fields
atomically, as always.

5. On success the ensure returns to idle steady state: byte checks back off from `interval`
   to `max_interval`. After a game reset, drift is detected and the current desired value is
   re-applied.

If a guarded run is rejected (for example a conflict), a bound ensure is **blocked**, not
removed. It does nothing until an option changes, then tries again through the same guards.

### Enable and disable

- **Disable** restores the reviewed baseline through the same guards. It writes only bytes
  this ensure owns: the live value must be the value it applied, or already the baseline.
  After a successful restore the ensure is **dormant**. It does no verification and no
  writes, so a game reset while disabled changes nothing.
- **Disable before anything was applied**, including while a first apply is waiting on a
  retry, simply goes dormant.
- **Disable while a retry is pending** cancels the pending apply, then restores whatever
  this ensure had applied earlier.
- **Re-enable** runs a full guarded resolution with the current option values.
- **A conflicting live value** blocks the restore. Nothing is written over another writer's
  value.

The ensure watch reports `status` as one of the following, plus `enabled`, `restores`, and
`rebinds`:

- `waiting_for_options` — availability not yet decided; nothing applied;
- `unavailable` — strict mode only: an option it uses is unavailable; inactive for the session;
- `waiting` — idle, verified;
- `running` — resolving;
- `blocked` — rejected; waiting for an option change;
- `recovering` — rejected because the game's data was not ready or moved; a fresh resolution follows (`recover`);
- `disabled` — dormant.

### Recovery and status callbacks (`recover`, `on_status`)

Both options work on every ensure, bound or not:

```lua
hd2.ensure{transaction = t, recover = true,               -- or {delay = 30, max_delay = 600, limit = 20}
    on_status = function(status, info)                      -- after every status change, run as your mod
        mod:log(info.id .. ': ' .. info.previous .. ' -> ' .. status .. ' ' .. tostring(info.code or ''))
    end}
```

- **`recover`** (off by default). Each guarded run already retries a game that is not ready up to six times, five
  update seconds apart. Without `recover`, an ensure whose run still fails stops (`rejected`; a bound ensure is
  `blocked` until an option changes). With it, a run rejected because the data was not ready or **moved under the
  check** is followed, after `delay` seconds (doubling up to `max_delay`, back to `delay` after a success), by a
  fresh full guarded resolution: status `recovering`, `recoveries` counts them, `retry_in` is the wait left.
  - Recovered: `TARGET_UNAVAILABLE` and `TARGET_UNSTABLE` after their retries, and `ownership/context or non-target
    bytes changed` (the data changed between the pre-write check and the write), only when the rollback is verified
    (or nothing was written) and page protection was restored.
  - Never recovered: `CONFLICT` (another writer's value), validation and acknowledgement refusals, an unsupported
    build, an incomplete rollback, and anything else; `limit` caps the recoveries.
  - Nothing is relaxed: the new attempt re-runs discovery, ownership, the build fingerprint, the expected bytes and
    the guarded transaction exactly as the first one did.
- **`on_status(status, info)`** after every status change: `info = {id, status, previous, error, code, runs,
  recoveries, retry_in}`. It runs as the mod that registered the ensure (its actions are attributed to it); a
  failing callback is logged (its first three failures) and never changes the ensure. It replaces polling
  `handle.status` from a timer.

## Performance

- Registration runs once on the first update ticks, and its scheduler entry is then removed.
  Without the menu it stops after 5 update seconds. Mods that declare no options add no work.
- Option callbacks do no memory work. Work starts only when a value actually changes, after
  the debounce.
- Steady state is unchanged: a byte check of the applied targets, with geometric back-off.
- Counters, via `hd2.metrics()`:
  - `options.changes`, `options.noop_changes`, `options.rejected_values`, `options.registered`;
  - `options.bound_resolutions`, `options.restores`, `options.owned_transitions`,
    `options.noop_settles`.

## Validation

- `scripts/validate_options_binding_snapshot.py` runs Mod Options Menu's own source (its
  native menu hook fails closed outside the game) against the retained snapshot with a
  copy-on-write overlay. It covers:
  - saved, malformed, out-of-range, and missing values;
  - live, no-op, and rapid changes; owned transitions; drift after a change;
  - disable, restore, re-enable, and a reset while disabled;
  - changes while the target is unavailable, and disable during a pending retry;
  - conflicts, transactions, plans, and every acknowledgement and range guard.
- The packaged-runtime validator's `options-missing` scenario runs the same mod without the
  menu, plus an unrelated operation. It checks that the bound operation applies its declared
  default once, that the unrelated operation applies, that exactly one warning is logged, and
  that nothing is retried or re-logged afterwards. `options-missing-strict` runs the same mod
  with `fallback='disable'` and checks that the bound operation stays inactive with no writes.
  Every other scenario checks that mods without options never mention the menu.
- The packaged-runtime validator's `options-live` scenario runs `LiberatorDamageOptions` from
  the built runtime ZIP. A contract stand-in for Mod Options Menu is installed after the addon
  starts. The scenario applies a live change, a no-op, a disable with restore, a re-enable,
  and a simulated reset.
- The `options-test-mod-live` and `options-test-mod-missing` scenarios run the same checks on
  the live-validation mod `examples/live/HD2RuntimeOptionsTest`, under its own ids. That mod is
  not a release example.
- **Confirmed in game** (HD2Runtime 0.25.0, Mod Options Menu v1.0.1, Bingus Shared Loader v18,
  Steam build 25480438), with `examples/live/HD2RuntimeOptionsTest`:
  - the option controls appear on the MODS tab and work;
  - APPLY updates the value managed by the runtime;
  - disabling restores the reviewed baseline;
  - without Mod Options Menu, only the option-bound operation was disabled (the 0.25.0
    behavior, now strict mode `fallback='disable'`; the default mode is validated offline);
  - saved values survive a full game restart (a saved 230 was loaded and applied at startup).
