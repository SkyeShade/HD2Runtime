# HD2Runtime

Version 0.21.0 adds guarded `hd2.stratagem(name)` authoring for all 20 imported offensive
stratagems and cooldown authoring for 33 uniquely resolved support-weapon call-ins. It keeps
Orbital, Eagle, and support call-in definitions separate from their projectile, DamageInfo,
explosion, status, and beam payload objects. Eagle uses before rearm and the shared 150-second
rearm definition have separate semantic fields. The canonical per-instance catalog contains
exact baselines and opaque backing-object, shared-scope, transaction, and plan identities.
Finite maximum uses and barrage scheduling remain read-only because their mutation semantics
are not yet gameplay-proven. See [stratagem authoring](docs/stratagem-authoring.md).

Version 0.20.1 corrects the support-authoring SDK metadata without changing runtime write
semantics. `SupportWeaponAuthoringCapabilities.json` schema v2 publishes all 828 internal field
instances with exact baselines, attack-qualified identities, semantic backing-object and shared
scope keys, and transaction/plan grouping metadata. The 812-entry deduplicated weapon lookup is
retained as a compatibility view and is no longer the canonical authoring source.

Version 0.20.0 promotes guarded authoring for all 27 uniquely resolved support-weapon
identities. The same semantic fields, exact baselines, shared-object acknowledgement,
stable rereads, rollback, protection restoration, and composition plans used by player
weapons now cover ordinary support weapon, ammo, projectile, DamageInfo, explosion,
Arc, Beam, Spray, Melee, status, and charge values. All eight duplicate groups remain
fail-closed. LAS-98 heat is structurally present but blocked with its duplicate identity;
backpack storage and unresolved stratagem scalars remain read-only. See the generated
[support capability catalog](sdk/SupportWeaponAuthoringCapabilities.json).

Version 0.19.0 adds `hd2.plan`, a guarded multi-target composition operation.
One plan can coordinate projectile physics, DamageInfo, terminal references,
ExplosionSettings, and explosion DamageInfo as a complete declared write set.
Ordered phases support projectile reference replacement followed by fresh
resolution of the resulting shared projectile object. `ensure` accepts plans
with the same 60-second conflict behavior as patches and transactions.

Version 0.18.0 adds guarded heat and heatsink authoring for five uniquely owned
player weapons through the native `WeaponHeatComponentData` record. Seven energy
weapons are mapped; Scythe and Dagger remain fail-closed because their runtime
identities are duplicated. The same pass audited all 191 captured customization
records and retained attachment selection/effect editing as read-only because no
alternate allowed-option collection or option-owned effect record is present.
JAR-5 Full Auto also remains blocked: its native vector `[2,3,0]` does not prove
that its consumer accepts mode 1.

Version 0.17.0 added guarded Full Auto/Semi Auto selection for 21 weapons whose native
mode vectors contain both values, typed terminal explosion removal, explicit shared projectile
object semantics, projectile-residency safety metadata, and a stable read-only 35-support-weapon
SDK contract. It preserves backwards compatibility for existing mods. The complete 80-weapon
primary and secondary catalog has 73 uniquely owned identities that
expose reviewed weapon, projectile, DamageInfo, Arc, Beam, Spray, Melee, magazine,
and rounds-feed fields through the existing `patch`, `transaction`, and `ensure`
engine. The seven duplicate-resource identities remain visible but fail closed
for ordinary writes. Shared settings require explicit opt-in. See the
[authoring guide](docs/player-weapon-authoring.md) and generated
[GUI capability catalog](sdk/PlayerWeaponAuthoringCapabilities.json). Ammo-specific
controls and unresolved customization ownership are in the generated
[ammo capability catalog](sdk/PlayerWeaponAmmoCapabilities.json).
The capability catalog marks 0.13 capacity/feed constants as deprecated semantic
aliases of their preferred `magazine.*` and `rounds.*` names. Runtime validation
continues to accept the old constants and coalesces equal alias requests into one
physical write.

The weapon-composition pass includes typed projectile and terminal references, guarded explosion
fields, magazine-option research, and fire-mode vectors. See the
[composition guide](docs/player-weapon-composition.md) and
[guarded composition-plan guide](docs/composition-plans.md), plus the
[support-weapon API](docs/support-weapon-api.md).

Version 0.10.0 adds offline-correlated player-weapon slot and guarded capacity
resolution. Slot tags separate all 54 unique training anchors. Capacity matches
all 35 anchors whose effective magazine is directly represented; default
magazine customizations remain fail-closed until their attachment AddPath is
mapped. See [the slot/capacity report](research/weapon-slot-capacity-F5FEE03DCFDB.json).

Version 0.8.0 adds offline-correlated primary-weapon fire rate and projectile
pellet count, velocity, mass, drag, and gravity fields. These mappings are
structural/correlation evidence pending gameplay confirmation. Capacity remains
unmapped. See [the correlation report](research/primary-weapon-field-correlation-F5FEE03DCFDB.json).

Version 0.7.1 schedules snapshot capture 60 seconds after load by default, before
any region enumeration or file creation. `capture_delay_seconds=0` provides an
explicit immediate-start override for development and tests.

Version 0.7.0 added build-bound, read-only HD2 process snapshots. The incremental
capture package records committed readable regions without changing process
memory or page protection. The SDK can run the existing Primary Weapon Runtime
Mapper offline through `SnapshotMemoryReader`; live and snapshot modes share the
same resolver and matcher code. See [the snapshot guide](docs/snapshots.md).

Version 0.9.0 generalizes the read-only weapon mapper to the combined 55-primary
and 25-secondary player catalog. It compares 365 structurally owned
weapon-resource candidates, preserves all attack branches, and reports separate
projectile and damage branch evidence without writing game memory. The original
primary-only offline command remains available. See the
[player mapper guide](docs/player-weapon-runtime-mapper.md) and the
[live diagnostic guide](docs/primary-weapon-runtime-mapper.md).
The [support weapon mapper guide](docs/support-weapon-runtime-mapper.md) describes the graph-aware,
read-only pass over the imported 35-support-weapon catalog.

Version 0.5.0 separates the installed-once runtime from the developer SDK and
independent gameplay mods. The 0.4.0 guarded patch/transaction/ensure behavior
was confirmed in live gameplay by the user and is retained unchanged.

Version 0.5.1 added the recommended beginner path. For this release, extract
`HD2Runtime-ModTemplate-0.21.0.zip`, open that folder directly in Rider, rename
the display name and resource ID, edit `src/addon.lua`, and run `build.cmd`.
The starter bundles IDE annotations and a Windows PowerShell/.NET archive builder,
so normal use needs no Python or HD2Runtime source copy.

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
