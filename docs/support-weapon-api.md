# Support weapon read-only API

HD2Runtime 0.17 publishes the reviewed 35-weapon support catalog through
`sdk/SupportWeaponCapabilities.json` and a matching runtime metadata view. The contract is
`hd2runtime.support_weapon.read_only.v1`; it contains resource identities, implementation families,
attack graphs, projectile/explosion/status branches, charge data, backpack dependencies, placed
entities, shared settings, duplicates, and unresolved links. It contains no process addresses.

```lua
local hd2=require('mods/skyeshade/hd2runtime')
local arc=hd2.support_weapon('ARC-3 Arc Thrower')
local description=arc:describe()
local attacks=arc:attacks()
local primary=arc:attack('primary')
```

`describe()` and attack `describe()` return copied metadata. Support targets are intentionally not
accepted by `patch`, `transaction`, or `ensure` in this release. Duplicate resource identities and
unresolved graph nodes remain explicit instead of being assigned a canonical resource.

Complex systems retain their native graph shape: Solo Silo preserves its payload, spawned silo, and
missile/explosion ownership chain; C4 remains a placed explosive; ARC-3 retains ArcSettings and its
WeaponCharge component evidence.
