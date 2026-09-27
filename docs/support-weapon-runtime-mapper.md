# Support weapon runtime mapper

The support mapper reuses HD2Runtime's bounded entity/component/settings scan and the same
snapshot reader used by the player-weapon mapper. It adds support-catalog normalization and a
graph report; it does not add another memory scanner.

Run it offline with:

```powershell
py -B hd2.py snapshot scan-support-weapons <build>.hd2snap wiki_support_weapons.json
```

The command writes `SupportWeaponRuntimeMap.json`,
`SupportWeaponRuntimeMap.identity-candidates.json`, `support_weapon_identity_summary.json`, and
`SupportWeaponRuntimeMap.log`. The committed current-build result is
[`research/support-weapon-runtime-F5FEE03DCFDB.json`](../research/support-weapon-runtime-F5FEE03DCFDB.json).

The report preserves every imported attack and its parent/child relationships. Runtime branches
are linked only when the owned component family and compared scalar fingerprint agree. Missing
branches remain explicit. The current profile has no reviewed `ExplosionSettings`, status-settings,
backblast-root, backpack-storage, or charge/alternate-fire selection adapter. Those links are
reported as unresolved rather than inferred from coincidental record values.

Current snapshot results are 30 resolved identities out of 35, including 24 unique roots and six
duplicate-resource groups. The remaining five are ARC-3 Arc Thrower, B/MD C4 Pack, CQC-72
Entrenchment Tool, GL-28 Belt-Fed Grenade Launcher, and MS-11 Solo Silo. ARC-3 and GL-28 have one
strong partial root each, but their imported fire rates disagree with the direct runtime value;
the matcher leaves them ambiguous.

The future semantic direction is `hd2.support_weapon(name)` with branch-aware access. It is not a
public runtime API yet. Snapshot evidence does not prove enough live ownership for guarded support
weapon writes, and duplicate identities have no canonical resource. All output remains read-only:
`writes=0`, `protectionChanges=0`, and `fixtureFallback=disabled`.
