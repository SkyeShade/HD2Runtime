# Runtime diagnostics

Two cheap diagnostics help tell whether HD2Runtime is involved when a large mixed mod setup loses frames. They do
not assume Runtime is the cause, and they do not prove it isn't. Both live in `runtime/diagnostics.lua` and are
reachable through `hd2.diagnostics`. A third, `hd2.diagnostics.operations()`, lists every registered operation and
how it ended (see [Registered operations](#registered-operations-hd2runtime-0281)).

## Write conflicts (always on)

An `hd2.ensure` keeps its target at the value it wrote. It re-checks only the owned bytes, on a verification interval
that backs off from 60 s to 10 minutes while the target stays stable. When the check finds the owned bytes changed
while their allocation is still the reviewed one (drift reason `target value drifted`), something else wrote them.
Runtime then re-applies, and counts the event for that operation.

After **3 external changes within the operation's window** (five of its verification intervals, at least 10 s),
Runtime logs one line:

```
[HD2Runtime] possible write conflict: operation gui-object-3d9ff4833c24584a039f823f (player_weapon SG-20 Halt:
weapon.fire_rate) externally changed and re-applied 3 times in 120.0 s; another mod may be writing the same memory
```

- **What the line names.** The operation id, its target (resource, weapon or stratagem, attack role or path) and up
  to four fields, the count and the time span.
- **No spam.** The next warning for that operation waits a full window.
- **Not counted.** A game reallocation (`owner allocation changed`, `target region changed`) is not a write conflict:
  it is the game rebuilding its data, and Runtime re-resolves it the normal way.
- **Cost.** The counting runs only on a detected drift, never per frame.

`hd2.diagnostics.write_conflicts()` returns every operation that saw external changes, most first:
`{operation, target, externalChanges, warnings, windowSeconds}`.

**Reading it.** Two mods writing the same bytes fight: each re-applies its own value. Runtime's side of the fight is
bounded by its verification interval, so it re-applies at most once per interval. A self-contained memory mod that
rewrites every frame costs whatever that mod costs. If a report shows conflicts, remove one of the two mods (or one of
the two edits); if it shows none, the FPS loss is not Runtime fighting another writer.

## Telemetry (off by default)

```lua
hd2.diagnostics.telemetry({enabled=true, report_seconds=60})
```

When enabled, every `report_seconds` Runtime logs:

```
[HD2Runtime] telemetry 60 s: update avg 0.071 ms p95 0.12 p99 0.31 max 1.20 (3600); ensure byte-check avg 0.02 ms
p95 0.03 p99 0.05 max 0.08 (40); event polling avg 0.05 ms ...; active ensures 12; re-applications 0
```

- **update** is the whole Runtime per-frame update.
- **ensure byte-check** is one steady-state verification.
- **event polling** is the event system's tick.
- **Samples.** They come from the durations the metrics module already measures, kept in fixed 512-entry rings.
- **Percentiles** are computed only when the report is written.
- **Disabled cost.** One boolean test per timed section and per update; nothing is sampled or allocated.
- **Precise clock.** Timing needs the game's precise clock (in game); offline, the report says so.

`hd2.diagnostics.telemetry()` without arguments returns the state and the running interval's sections.

## Registered operations (HD2Runtime 0.28.1+)

`hd2.diagnostics.operations()` returns every operation registered this session, in registration order, including
the ones Runtime refused. An addon that keeps no handle, or registers operations in a callback, is covered too:

```lua
for _, op in ipairs(hd2.diagnostics.operations()) do
    -- op.kind ('patch'|'transaction'|'plan'|'ensure'), op.id, op.mod, op.sdk, op.sdk_source,
    -- op.status ('rejected', 'complete', 'waiting', 'unavailable', ...), op.result ('APPLIED', 'REJECTED', ...),
    -- op.code, op.error, op.runs (ensure), op.legacy
end
```

- **`status` / `result`.** `status='rejected'` is a refusal: at registration (logged as `<kind> <id> rejected:
  <reason>`) or when applying (for example `CONFLICT`). `unavailable` and `disabled` are option-bound operations that
  are switched off or have no Mod Options Menu. An ensure that applied has `runs >= 1` and `result='APPLIED'`
  (or `ALREADY_DESIRED`).
- **`sdk` and `sdk_source`.** The SDK version the registering mod declares, and where it came from: `wrapper` (read
  from the mod's addon wrapper), `mod` (remembered for that mod resource) or `unknown`.
- **`legacy`.** `{target, field, acknowledgement, since}` for each field this operation wrote without an
  acknowledgement that a later SDK added (docs/legacy-sdk-compatibility.md). Each one is also logged once when the
  operation registers.

The list is a copy; the entries are read when it is called. At most 4096 registrations are kept (the oldest are
dropped first; the second return value is `{dropped = n}`).

## Asking for a report

A user with a large setup can:
1. add a small mod that enables telemetry;
2. play one mission;
3. send `HD2Runtime.log`.

The report and any write-conflict lines show whether Runtime's update is expensive or is fighting another mod.
