# Runtime cost and steady state

HD2Runtime separates one-time resolution from steady-state upkeep. After an ensured
mod reaches its desired state, the only recurring work is a byte check of its
applied targets, and that check backs off over time.

| Work | When it runs |
| --- | --- |
| Build fingerprint (SHA-256 of the exe and game.dll, ~30 MB) | Once per process and loaded-module identity; shared by all mods |
| Address-space discovery walk | Once per guarded operation. A completed walk is reused, after full re-validation, by operations starting within 15 s |
| Entity catalog, ownership and linkage chains, stratagem table, settings parse | Once per guarded operation |
| Guarded transaction (context rereads, page protection, write, verify) | Only when an operation runs: startup, or after drift |
| Steady-state check | Every `interval` (default 60 s), doubling to `max_interval` (default 600 s): a few `VirtualQuery` calls and reads of the target bytes only |

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

## Metrics

`hd2.metrics()` returns process-wide counters and worst durations, including:

- `fingerprint.*`, `discover.walks` / `discover.regions` / `discover.shared_reuses`
- `entity_catalog.captures`, `stratagem.table_captures`
- `reader.queries` / `reader.bytes`
- `transaction.applies` / `writes` / `already_desired_fields` / `protection_changes` / `guard_bytes`
- `steady.verifications` / `drift`, `ensure.full_resolutions`
- `exclusive.*`, `scheduler.ticks`, `log.lines`

`worst_seconds['scheduler.tick']` is the longest single update-hook tick.

## Audit

`scripts/audit_steady_state.py` runs the example mods on the retained snapshot
through a copy-on-write overlay that simulates writes. It covers startup, a
steady-state window, a simulated game reinitialization, and all mods together,
and records the results in `validation/steady-state-audit.json`. The same audit
against the pre-fix 0.23.0 commit is kept in
`validation/steady-state-audit-before-0.23.0-22ec478.json`.
