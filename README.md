# HD2Runtime

Version 0.5.0 separates the installed-once runtime from the developer SDK and
independent gameplay mods. The 0.4.0 guarded patch/transaction/ensure behavior
was confirmed in live gameplay by the user and is retained unchanged.

Install Bingus Shared Loader, the standalone HD2Runtime runtime ZIP, and the
gameplay mods you want. Authors use the separate SDK for typed Lua completion,
field constants, offline inspection, and project generation. No runtime source
is copied into generated gameplay projects.

```powershell
py -B sdk/hd2.py inspect weapon "JAR-5 Dominator"
py -B sdk/hd2.py inspect type DamageProfile
py -B sdk/hd2.py new build/MyMod --name mods/my_author/my_mod
py -B build/MyMod/build.py
```

The [SDK guide](sdk/README.md) covers Rider/LuaLS setup, install-once dependencies,
templates and packaging. The [generated API catalog](sdk/docs/api.md) contains
all mapped domains and evidence. [Example projects](examples/projects) reference
the shared SDK. `schemas/sdk.json` generates runtime descriptors, constants,
annotations, CLI metadata and API docs through `scripts/generate_sdk.py`.
Build all release artifacts from a clean commit with
`py -B scripts/build_release.py`.

```lua
local damage = hd2.weapon('JAR-5 Dominator'):projectile():damage()
local field = hd2.fields.damage.armor_penetration
local health = hd2.vehicle('Bastion'):health():read_target()
```

The following read-only and self-contained proof builds remain available as
regression/diagnostic tools; normal gameplay projects use the shared runtime.

The standalone [live-validation package](docs/live-validation.md) reports 62
fields across the six requested resources, with ownership, baseline comparisons,
and provenance. Build it from a clean source commit with
`py -3.14 -B scripts/build_live_validation.py`. It does not deploy or launch HD2.

Version 0.4.0 adds guarded [transactions and ensure](docs/transaction-ensure.md).
The first proof applies the four reviewed Shield Relay fields as one transaction
and revalidates them every 60 update seconds. Build it from a clean commit with
`py -3.14 -B scripts/build_transaction_proof.py`.

Reusable runtime reads and observations for Helldivers 2 mods using Bingus Shared
Loader v15+ / API 1. The gameplay proof enables `patch` for the reviewed JAR-5 AP
field. The Shield Relay proof enables `transaction` and `ensure` for its four
reviewed fields. Read-only package builds exclude the native writer and reject
all write APIs.

```lua
hd2.patch({
    id = 'jar5-ap4',
    target = hd2.weapon('JAR-5 Dominator'):projectile():damage(),
    field = 'armor_penetration', expect = 3, value = 4,
})
```

```lua
hd2.ensure({
    transaction = {
        id = 'shield-relay-proof',
        target = hd2.stratagem('Shield Relay'),
        changes = {
            { field='radius', expect=15, value=8 },
            { field='durability', expect=4000, value=40000 },
            { field='lifetime', expect=40, value=90 },
            { field='cooldown', expect=90, value=180 },
        },
    },
})
```

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
not a new live capture. The user confirmed all six live-validation resources
at commit `9e7a9e6e2ab94195ef8c06d22ec4df8388069b08`, and confirmed the 0.4.0 live
gameplay proof at `b3ee7326ce53448590a830b924c99e2df6eec179`. Version 0.5.0
packaging and SDK changes have offline validation only. A matching installed
build is not proof of current process ownership.

See [audit](docs/audit.md), [architecture and next milestone](docs/architecture.md),
[evidence policy](docs/evidence.md), and [source hashes](docs/provenance.json).
