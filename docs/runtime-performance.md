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

Between checks the scheduler keeps only a sleep countdown: it skips the ensure's
tick, status callback wrapper and per-watch timing. An option change wakes it on
the next update, with the normal debounce. Skipped time advances the verification
clock but cannot consume a new option's debounce or a child's resolution/asset
timeout. Recovery waits sleep until their deadline; blocked or disabled bound
ensures wait for an option change. Cancellation still cleans up immediately.

This preserves periodic detection of reloaded game data while removing the cost
of calling every settled field watch on every frame. Active operations still run
each update and use the same guards, operation gate and read budget.

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
  queries and 64 KiB. This was the only pacing before 0.30.0.
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

## Which mod is slow (0.30.0)

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

**Live view (0.31.1).** The F10 panel's PERFORMANCE tab (`runtime/performance_panel.lua`) draws the same measurements
live. While it is shown, `perf_watch.record(true)` keeps a history:

- One series per mod's background work and one for its overlay windows, and one per part of the Runtime: a scheduler watch's module, each event
  source (every source's poll is now timed as `event source <name>`), the Runtime's own overlays. A part's name comes
  from its label once per callback.
- Every 0.25 s of game time each series gets one value, its own time per update averaged over that quarter second.
  The last 60 values are kept, with each quarter's largest single update and frame time.
- Recording adds one addition per timed call and one pass over the series per update. Closing the tab stops it and
  drops the history.

The graph changes only when a quarter completes. Every column always draws six rectangles (an empty segment is
transparent), so the overlay updates rectangles in place. The panel's own drawing is measured too.

In 0.40.0, `HD2R Editor UI` measures the Editor's overlay callbacks and
`HD2R Editor work` measures its other callbacks and operations. The former
`overlay settings` measurement is split into `F10 layout` (building the window),
`F10 GUI sync` (reconciling engine primitives), and `F10 resources/input` (the
remaining overlay work, including resource checks). Nested timings count only
their own time, so these pieces can be added without double counting. They
measure CPU work in Runtime callbacks, not the game's complete GPU rendering cost.

The Performance graph retains validated text and rectangle geometry between its
quarter-second updates. Input and resource residency checks still run every frame;
content, resolution, font availability and GUI changes invalidate the retained
geometry. Engine primitive IDs stay separate from cached geometry, including when
hovered controls insert a preceding highlight. Other overlay text also benefits
from bounded per-font glyph/width caches, and text covered by its normal font
does not query fallback font residency just to wrap or check coverage.

In 0.40.0, read-only `hd2.inspect` jobs inherit their caller's performance
owner. Their field validation, memory reads and larger catalogue parsing loops
advance cooperatively, targeting roughly 0.75 ms per job update. This is a soft
budget: an atomic operation or garbage collection can overrun it. Ordinary
patch/transaction pacing is unchanged, and inspections retain all ownership,
identity and stability checks.

The Editor caches page definitions and completed inspection batches for the
session. Only the selected page advances live checks, with one outstanding
batch; navigating away or closing cancels it. Returning resumes unfinished
batches. No startup scan of every live target is required, and cached inspection
results never replace the fresh guards used to apply or restore values.

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

An ensure watch also exposes `watch.set_verification_enabled(boolean)`. It defaults to
`true`. Setting it to `false` suspends periodic verification after the current operation
settles; ownership and applied values are retained. Initial application, option edits,
restore, cancellation and recovery already in progress still run. Setting it back to
`true` wakes the watch and resumes its verification schedule.

The Editor uses this control while closed. It requests one-second verification intervals
while open (`interval=1, max_interval=1`) and suspends them while closed. If the game
reloads data while the Editor is closed, a settled preset is checked and repaired when
the Editor opens again. Other mods retain their existing ensure policy.

`scripts/audit_steady_state.py` runs the example mods on the retained snapshot
through a copy-on-write overlay that simulates writes. It covers startup, a
steady-state window, a simulated game reinitialization, and all mods together,
and records the results in `validation/steady-state-audit.json`. The same audit
against the pre-fix 0.23.0 commit is kept in
`validation/steady-state-audit-before-0.23.0-22ec478.json`.

The performance graph separates event-engine costs into key binding polling,
key sampling, mouse wheel polling, event sources, named Runtime subscriptions,
dispatch, timer scheduling, and frame scheduling. `events: bookkeeping` is the
remaining engine overhead. Nested callbacks retain their owning mod's attribution;
their duration is subtracted from the surrounding poller or dispatch scope.

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

## Global and Runtime views (0.40.0)

F10 > Performance has **Global** and **Runtime** buttons and page arrows.
Runtime retains the detailed service/event breakdown and separate mod UI/work
rows. Global groups all observed work into one **HD2Runtime core** row and one
row per mod. **[R]** identifies a mod that uses Runtime's dispatch or operations.
The Editor's UI and work are combined in its own Global row, excluded from core.
Nested callbacks count once; a group's peak is its combined time in one frame,
not the sum of peaks from different frames. Switching views starts a fresh history.

Global temporarily wraps identifiable Lua mod entry points in the global update
and render chains, exposed global functions, and public API callback tables.
Saved callbacks across mod boundaries, including private callback tables and
multiple same-owner wrappers, are measured separately; identifiable
vanilla callbacks are excluded. It uses the existing precise-clock timing stack,
preserves all returns and error objects, and removes its wrappers when the panel
closes or switches back to Runtime. It never installs a debug hook or changes JIT
settings. A later hook installed by another mod is preserved on removal.

The loader's loaded-mod inventory also appears. **Not measured** means no
attributable callback ran during the current recording; it does not mean zero
cost. Native detours, callbacks hidden behind native pointers, anonymous Lua
chunks without a resource identity, and asset/GPU costs cannot be individually
measured here. This is observed Lua callback wall time, not whole-process CPU or
GPU profiling. New callback chains are discovered when Global opens; reopen the
view after dynamically loading another mod. Bounded discovery reports partial
coverage if it reaches its traversal limit.

The F10 menu has its own row below a separator in Global, pinned there on every
page. Its rendering, layout, and input/resource work are excluded from core and
from the main graph's mod total. Profiler bookkeeping, label formatting and
performance diagnostics also belong to that row rather than the surrounding
core or mod callback. Runtime keeps these stages as separate rows.
The note below the menu row explains that rendering and profiling stop while
closed. Timing, aggregation and performance log output run only while the
Performance tab is visible. Explicit diagnostic telemetry remains opt-in.

## Applying large sets of edits

Entity captures reuse decoded map/index metadata only after fresh guarded reads
match the cached bytes exactly. Record values, native table pointers, snapshots,
page protections and expected bytes are always read and checked again. Enemy
captures without mounted attack chains build candidates for the requested
resources, while checking the full index for shared ownership. Owned membership
lists bypass the map decode cache.

New queued operations share a one-millisecond admission budget per update. The
first operation is always admitted so other recurring work cannot starve writes;
a running operation retains the exclusive gate and existing timeout/rollback
rules. Read slices can extend to two MiB only within the existing time budget.

Discovery proofs are retained independently for each memory address space and schema
view. The live API shares an internal process identity across its per-operation
adapter wrappers; independent snapshot/test adapters remain isolated. Alternating enemy and weapon operations therefore cannot evict each other's
completed allocation walks. Each proof keeps its original 15-second expiry; every
reuse checks allocation identity, size, protection and headers, then reads current
settings again. Missing or changed allocations trigger a full scan. Applying and
restoring values both use this path and keep the same transaction guards.


The dev15 Global observer inspects saved update/render function chains before
private data tables, with separate traversal limits for functions and table cells.
Instrumentation is installed only after discovery. When a chain cannot be fully
inspected, its unresolved exclusive remainder is shown as **Unattributed callback
work** rather than charged to the outer mod. This addresses changing apparent
culprits when reopening the tab. The observer still cannot attribute callbacks
hidden in native hooks or unidentifiable Lua chunks. A ranking is observed Lua
callback time, not proof of which mod causes a whole-game frame spike.

Dev16 isolates incomplete callbacks at their own timing boundary, including helpers
from the same mod. An unresolved callback no longer makes its already-separated
callers unattributed. Only genuinely unresolved exclusive work stays in that row;
mods with no observed callback work remain unmeasured. Collection and timing still
stop when the Performance tab closes.

F10 uses the same renewable input block as the editor. Each window owns its lease,
so closing one does not release the other's block. Escape closes the language list
first, then the panel. Menu sounds can be switched off under Interface. The existing
"Mouse wheel hook off" installation choice also disables native input blocking.

Dev17 preserves samples when switching between Global and Runtime. Runtime filters
foreign callback series out of both its table and graph. Closing Performance still
stops collection and discards the session. Resumed coroutines are measured only for
each synchronous resume call and shown as unattributed when their owner cannot be
established. A suspended coroutine cannot keep the frame timing stack open or charge
its waiting time to whichever callback runs next. This fixes an offline-reproduced
freeze; it is not a confirmed diagnosis of every reported in-game graph freeze.
# Faster application (0.40.0 optimizations): off by default since 0.40.1

F10 > Settings > Interface has **Faster application (0.40.0)**. It is **off by default** since 0.40.1 (the user's
decision of 2026-10-19, after reports of the game failing to start with 0.40.0). Off is the 0.31 behaviour; on turns
on every application optimization 0.40.0 added (`runtime/application_mode.lua`):
- shared discovery walks between back-to-back operations and writers, and the decoded entity map and component index
  caches;
- the 2 MiB extended read slice (off: 1 MiB);
- sleeping ensures: the scheduler skips an ensure's tick until its next verification is due (off: every watch ticks
  every frame);
- paused verification: the HD2R Editor pauses its ensures' periodic checks while its window is hidden (off: they keep
  verifying);
- the write-gate budget: once an update has spent 1 ms, a second operation waits for the next update (off: a burst is
  admitted in one update);
- the enemy capture's resource filter (off: every candidate is decoded).

The choice is saved in the Runtime's own store and applied at load, before any mod applies anything. It affects
subsequent work across all runtime mods, including apply and remove operations; it does not cancel or undo existing
changes. Switching rebuilds caches from fresh reads.

Both modes retain ownership checks, fingerprints, transaction snapshots and rollback. Both also copy game data into
buffers: this is not a buffer-free mode or a confirmed fix for third-party mods that scan and rewrite arbitrary memory
copies. `hd2.diagnostics.application_optimizations()` reads the current choice, and passing `true` or `false` changes it
for the process only. `hd2.diagnostics.save_application_optimizations(enabled)` also saves it as the F10 setting (the
HD2R Editor's Settings switch uses this from 1.0.1).

The smaller per-frame savings of 0.40.0 (timing only while F10 > Performance records, cached glyph widths, the event
queue's empty-queue skip) are not part of the switch: they never change what is read or written.


# Memory view (RC8)

F10 > Performance > Memory graphs known HD2Runtime buffer/cache payloads in MiB,
with one sample per second and up to 90 visible samples. Collection is driven only
by drawing this view; closing it or selecting another view stops sampling. CPU
profiling and the global callback observer are stopped while Memory is selected.
No shared-heap query, forced garbage collection or per-sample logging is used.

The tracked categories are entity-map/index cache strings, captured read/rollback
snapshot strings, reusable event buffers, registered native buffers, and permanent
native pages allocated by the Runtime. Identical Lua strings are counted once,
preferentially under caches. Weak registration does not keep Lua objects or FFI
buffers alive. Released objects disappear when the normal collector processes them;
permanent native pages remain counted for the lifetime of this Lua state.

This is **known payload accounting, not total per-mod RAM or process working set**.
It excludes Lua object/table overhead, generated catalogue tables, JIT/code memory,
unregistered temporary allocations, engine/GPU resources and other mods' allocations.
The shared Lua heap cannot supply an accurate Runtime-only total. Buffers allocated
by Runtime services on behalf of runtime mods belong to the tracked Runtime service
allocation; this graph does not split those buffers by requesting mod.


RC9 uses the same chart renderer for Memory, Runtime and Global: identical plot
bounds, left scale gutter, three grid lines, palette, bar spacing and layer order.
Memory's table uses CURRENT and PEAK columns, aligned like the timing table, with
per-category share bars. Memory sampling remains on-demand at one second intervals.
