# Runtime cost and steady state

HD2Runtime separates one-time resolution from steady-state upkeep. After an ensured
mod reaches its desired state, the only recurring work is a byte check of its
applied targets, and that check backs off over time.

| Work | When it runs |
| --- | --- |
| Build fingerprint (SHA-256 of the exe and game.dll, ~30 MB) | Once per process and loaded-module identity; shared by all mods |
| Address-space discovery walk | Once per guarded operation. A completed walk is reused, after full re-validation, by operations starting within 15 s of the walk's start (see "Discovery walk") |
| Entity catalog, ownership and linkage chains, stratagem table, settings parse | Once per guarded operation |
| Read pacing | Every guarded resolution: about 1 ms of reads per update, at least 64 queries / 64 KiB (see "Read pacing") |
| Guarded transaction (context rereads, page protection, write, verify) | Only when an operation runs: startup, or after drift |
| Steady-state check | Every `interval` (default 60 s), doubling to `max_interval` (default 600 s): a few `VirtualQuery` calls and reads of the target bytes only |

## Fingerprint cache

The cache is an in-memory table of verified keys, one short string per
successful match: run mode plus the base address and handle of the exe and of
game.dll. No file contents, digests of other files, snapshot data, or disk cache
are kept. Hashing streams each module file through one 1 MiB buffer, which is
freed after the hash, and does not hold the ~30 MB of file data. Mismatches are
never cached. Windows keeps a loaded module's image file locked, so a key stays
valid for the life of the process.

## Module loading

The engine resolves archived Lua resources only while its startup package is
loaded; later, `require` of a module that was never loaded fails with "module
not found". At startup the packaged entry captures the loader of every shipped
module into `package.preload`, without running it, so modules first needed at
apply time or on drift still load. `scripts/validate_packaged_runtime.py` runs
the built ZIP with late lookups disabled and fails the release if any module is
required after startup and not captured.

## `hd2.ensure`

The first run is the complete guarded operation. After that, ensure keeps only the
applied byte ranges, their owner allocation identity, and a 32-byte owner header.
It then checks those at a backed-off interval, without discovery, catalog
rebuilds, fingerprint hashing, protection changes, or writes. A missing or
changed allocation, a changed header, or a target that is no longer desired
counts as drift. Drift resets the interval and reruns the unchanged full guarded
path. That path reapplies the edit, or rejects on conflict exactly as before.

## Operation gate

Only one guarded operation (patch, transaction, or plan) may be between its first
read and its final write at a time; the others report `queued`. Before this,
several mods starting together could invalidate each other's captured tables and
fail closed. Time spent queued does not count against the resolution budget.

The gate stays. Resolving several operations' read phases at once would not
shorten startup: resolution is bounded by the per-update read budget below, which
all operations would share, and a write landing in another operation's captured
table makes that operation's stability reread fail (`TARGET_UNSTABLE`, a 5 s retry).

## Read pacing

`runtime/reader.lua` decides only *when* a read happens, never what is checked:
every read re-queries its region and re-proves allocation ownership, type and
protection immediately before `ReadProcessMemory`, however many reads share an
update.

- A slice (the reads between two yields) may always do the base quantum of 64
  queries and 64 KiB. This was the only pacing before 0.30.0-dev.
- Inside an update tick with a precise clock (the live adapter's
  `QueryPerformanceCounter`), the slice continues while the Runtime's work in that
  update, including every watch ticked before it, stays under `SLICE_SECONDS`
  (1 ms). It never exceeds the hard ceilings of 1024 queries and 1 MiB.
- A slow machine, or an update that is already heavy, falls back to the base quantum.
  So a resolution never gets fewer reads per update than before.
- Without a clock (offline tests, the packaged validator) or outside an update
  tick, only the base quantum applies, exactly as before.

The atomic sections are unchanged: the guarded transaction (context rereads,
protection, write, verification) and a settings or catalogue parse still run
within one update. An update that ends a slice and then runs one of them can cost
up to one slice (1 ms) more than before.

## Discovery walk

`runtime/discover.lua` walks the address space once (one `VirtualQuery` per
region) to find the entity map, the entity delta table and the settings tables
by size window and header.

- **One header read per region.** A region inside several keys' size windows is
  read once, and that read serves every check. Before, it was read once per key.
  Each read still re-proves the region.
- **What is shared.** A completed walk records every allocation whose uniqueness it
  proved:
  - every key the operation needed;
  - the entity map and the entity delta table (one candidate region each, always
    checked);
  - any other settings key whose *whole* size window the walk read for a needed
    key.

  A key whose window contains a region the walk did not read is not recorded, so
  a later operation needing it walks again.
- **Reuse.** Reuse re-validates each needed allocation's identity, extent,
  protection and header, then captures and parses it again. Any difference or
  missing key falls back to a full walk.
- **Expiry.** The sharing window is still 15 s, dated from the walk's *start*.

## Startup timing (offline measurement)

These figures come from the built runtime ZIP run on HD2's lua51.dll against the
retained snapshot, at 60 simulated updates per second. The harness is
`build/test-artifacts/init-speed/measure.py`, a scratch tool that is not shipped.

- "Frames" counts updates until every registered operation settled. It includes
  the fixed 3 s (180-update) startup delay.
- "With clock" gives the overlay adapter a precise clock, as the live adapter has.
  The packaged validator has none.
- Snapshot reads are file-backed. Absolute times are therefore a proxy, not the
  live game's.

| Scenario (operations) | Before | Now, no clock | Now, with clock |
| --- | --- | --- | --- |
| player-weapon-patch (1) | 463 frames, 7.7 s | 463 | 201 frames, 3.4 s |
| player-weapon-transaction-gui (2) | 1240, 20.7 s | 925 | 291, 4.8 s |
| user-report-halt-issue-all-fields (8) | 1593, 26.6 s | 1278 | 323, 5.4 s |
| example-gib-threshold-test (23, options) | 683, 11.4 s | 683 | 241, 4.0 s |
| user-report-full-project (133) | 14181, 236 s (20 walks) | 4109, 68 s (6 walks) | 660, 11.0 s (2 walks) |

Per update, while an operation holds the gate:

- **133-operation project:**
  - Before: median 0.11 ms, maximum about 10–14 ms. The maximum is the guarded
    transaction and the CPU-only parse updates.
  - With clock: median 1.25 ms, 99th percentile 7–9 ms, maximum about 10–12 ms.
- **1-operation scenario:** the maximum is about 1.5 ms both before and after.

The number of updates over 8 ms is about the same (1–5 before, 4–8 after, across
repeated runs). They are the same per-operation atomic sections, now packed into
11 s instead of 236 s.

What remains:

- the 3 s default `startup_delay` (documented; there is no proven earlier readiness
  signal);
- the 5 s Mod Options Menu grace when the menu is absent;
- the game's own loading, the "game" stage of the startup progress line;
- about 3–5 updates per operation for its fresh capture, stability reread and
  guarded transaction.

## Metrics

`hd2.metrics()` returns process-wide counters and worst durations, including:

- `fingerprint.*`, `discover.walks` / `discover.regions` / `discover.shared_reuses`
- `entity_catalog.captures`, `stratagem.table_captures`
- `reader.queries` / `reader.bytes`
- `transaction.applies` / `writes` / `already_desired_fields` / `protection_changes` / `guard_bytes`
- `steady.verifications` / `drift`, `ensure.full_resolutions`
- `exclusive.*`, `scheduler.ticks`, `log.lines`

`worst_seconds['scheduler.tick']` is the longest single update-hook tick.

## Which mod is slow (0.30.0-dev)

`runtime/perf_watch.lua` times, with the precise clock, everything that runs on the game thread for a mod:

- every call into the mod: event listeners, timers and keybinds (`events.invoke`), and `run_as` (its main file,
  custom stratagem callbacks, Pelican events);
- every scheduler watch: each operation's updates count as its mod's (`ensure <id>`). The Runtime's own watches count
  as `HD2Runtime (its own work)`, named by module.

Each call counts only its own time, so a callback dispatched from inside another counts once, as the inner one's. It
stays quiet unless something is slow:

| Line | When |
|---|---|
| `PERFORMANCE: mod <id>: <callback> took <n> ms in one call` | One call took 8 ms or more. The same callback logs again only at twice its last logged time, at most 3 times. |
| `PERFORMANCE: mod <id> used <n> ms per update over the last 10 s (<calls> calls); heaviest: ...` | The mod used 1 ms or more per update on average over 10 s of game time. It names its 3 heaviest callbacks, with average, maximum and call count, at most once a minute per mod. |
| `PERFORMANCE: the slowest operations to settle: ...` | A burst of registered operations took 10 s or more to settle. It names the 3 slowest, each with the time spent in each state (`running`, `waiting_for_assets`, `waiting_for_options`, ...). |

`<callback>` reads like `event enemy_killed (subscription 4)`, `repeating timer (timer 7)`, `ensure my-op`, `the
function at mods/author/name:120` or `update of hd2runtime/runtime/custom_stratagems`.

`hd2.diagnostics.performance()` returns every owner's totals, its slowest call and its last 10 s window. Nothing is
formatted on the timing path, and offline (no precise clock) nothing is timed.

**Per-frame cost removed in the same pass:**
- `event_world.open()` reuses one memory adapter. It ran several times per update and built a new adapter each time,
  about 40 closures and FFI buffers, all discarded.
- Projectile homing checks the game state twice a second outside a mission, instead of every update.
- **Stratagem ownership:** each lookup scanned the account catalogue (two reads per entry). Inside an update the
  catalogue is now read once and every lookup uses it.
  - Aboard the ship, the custom stratagem carrier allocation reruns every few seconds, and it asks about a hundred
    candidates' ownership per custom stratagem. With four Pelican and barrage stratagems it went from 45,828 reads to
    6,838, with the same carriers.
  - Live, each read is a ReadProcessMemory call: that allocation was a ~150 ms hitch every few seconds aboard the ship
    (2026-10-06, `PERFORMANCE: HD2Runtime (its own work): update of hd2runtime/runtime/custom_stratagems took 156.0 ms`).
- Reads of up to 4 KiB share one buffer instead of allocating two FFI buffers each.

## Audit

`scripts/audit_steady_state.py` runs the example mods on the retained snapshot
through a copy-on-write overlay that simulates writes. It covers startup, a
steady-state window, a simulated game reinitialization, and all mods together,
and records the results in `validation/steady-state-audit.json`. The same audit
against the pre-fix 0.23.0 commit is kept in
`validation/steady-state-audit-before-0.23.0-22ec478.json`.

## Bounded retry

`hd2.patch`, `hd2.transaction`, and `hd2.plan` share one policy (`runtime/retry.lua`). `observe`
uses the same constants.

- **Attempt:** one complete guarded resolution and application run that has actually started, after
  the startup delay and after acquiring the operation gate. Time spent queued or waiting for a retry
  never counts, and the resolution budget applies per attempt.
- **Delay:** a fixed 5 update seconds between attempts, at most 6 attempts in total. After the last
  attempt the operation is terminal and no further polling occurs.
- **Retried failures:**
  - `TARGET_UNAVAILABLE`: game modules not loaded yet, the entity region or a settings allocation
    absent, or the stratagem table not initialized or not committed.
  - `TARGET_UNSTABLE`: captured data changed while resolving. The stability reread raises this
    before any write.

  A plan failure retries only if its rollback verified or was not needed.
- **Immediate failures:**
  - value conflicts (`CONFLICT`);
  - build fingerprint mismatch;
  - identity, ownership, schema, or extent changes;
  - transaction-core rejections, unverified rollback, or unrestored protection;
  - resolution budget exhaustion.
- **Success:** ends the operation immediately. A retry never re-applies a value that already verified.
- **After retries run out:** the result reports `code` (`TARGET_UNAVAILABLE` or `TARGET_UNSTABLE`)
  and `attempts`.
- **Ensure:** when drift is detected, ensure starts a fresh guarded operation with its own 6 attempts.
  While that operation retries, ensure stays alive. If it runs out of retries, ensure stops.
