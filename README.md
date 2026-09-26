# HD2Runtime

The standalone [live-validation package](docs/live-validation.md) reports 62
fields across the six requested resources, with ownership, baseline comparisons,
and provenance. Build it from a clean source commit with
`py -3.14 -B scripts/build_live_validation.py`. It does not deploy or launch HD2.

Reusable runtime reads and observations for Helldivers 2 mods using Bingus Shared
Loader v15+ / API 1. Milestone 1 is **read-only**. `patch`, `ensure`, and
`transaction` return `READ_ONLY_MILESTONE`; this package contains no memory writer
or page-protection-changing declaration.

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local watch = hd2.observe {
    targets = {
        { resource = 'jar5', fields = {
            'projectile_type', 'standard_damage', 'durable_damage', 'armor_penetration'
        } },
        { resource = 'shield_relay', fields = {
            'radius', 'durability', 'lifetime', 'cooldown'
        } },
    },
    on_result = function(result) print(hd2.format(result)) end,
    on_error = function(reason) print(reason) end,
}
-- watch.cancel() stops subsequent observations.
```

Observation starts after two update seconds and resolves again every 60 update
seconds after a completed read. The runtime owns scheduling and preserves prior
update callbacks. Unavailable modules/allocations retry up to six attempts, five
update seconds apart. Invalid structures latch a rejection. `hd2.read { targets = ... }` provides the same
resolution as a bounded job; call `job.step()` once per update until it returns
true, then inspect `job.status`, `job.result`, or `job.error`.

`hd2.describe('amr')` lists fields and evidence without accessing native memory.
Resource hashes such as `0x89C5493E08CA4207` also work. Public results identify
resource, component/settings record, and field. They expose no runtime addresses.
Observed values include `expected`, `expected_match`, storage, exact width, and
evidence. Baseline differences are reported by reads, never silently written.

The read result also exposes checked ownership-chain metadata (component/settings
type, record index/kind, group and unique owner) and discovery counters. Observer
`on_result(result)` and `on_error(reason, detail)` callbacks may return a report
string; HD2Runtime writes each line through its normal console/Bingus log sink.
Failure detail identifies the adapter stage and category. Observations have a
default 180-update-second / 10,000-step budget, adjustable with `timeout` for time.

From this directory, with Python 3.14 and an owned installation's standalone
`bin/lua51.dll` available:

```powershell
py -3.14 -B -m unittest discover -s tests -v
py -3.14 -B scripts/build.py
```

`HD2_GAME_ROOT` can select the installation used for the offline Lua VM. Tests
load only `lua51.dll` into Python, never the game executable or `game.dll`.
The generic report build produces `build/HD2Runtime-<VERSION>-readonly.zip`, a source Lua addon,
manifest, and empty archive sidecars. It includes a one-shot developer report for
all seven known resources. It neither deploys nor launches anything. Library and
report require each other explicitly, so Bingus discovery order is irrelevant.

Regression tests reproduce the requested values from sparse retained reference
bytes and the saved live cooldown row. `build/known-values.txt` is **fixture output**,
not a new live capture. HD2Runtime itself still requires an authorized in-game
read-only smoke test. A matching installed build is not proof of current process
ownership or gameplay behavior.

See [audit](docs/audit.md), [architecture and next milestone](docs/architecture.md),
[evidence policy](docs/evidence.md), and [source hashes](docs/provenance.json).
