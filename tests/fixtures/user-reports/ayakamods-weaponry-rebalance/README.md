# AyakaMods user report fixture (2026-09-29)

Real-world ModBuilder project "Nephelym's Weaponry Rebalance" (SDK 0.27.0) and the `HD2Runtime.log` its user sent
with the report analysed in `docs/user-report-ayakamods-2026-09-29.md`. The project's local export folder is
redacted (`exportDirectory`); nothing else is changed.

- `project.hd2mod.json`: the project as the user saved it.
- `HD2Runtime.log`: the user's log with the published 0.27.0 Runtime. It schedules exactly the export's first 42
  operations; operation 42 raised and aborted the rest.
- `generated/<variant>.lua`: ModBuilder 1.3.1's own `LuaGenerator` output. `<variant>.wrapped.lua` is the gameplay
  addon exactly as ModBuilder packages it (`ModExporter.Wrap`).

| Variant | Contents |
| --- | --- |
| `A-original` | the exact project (133 operations) |
| `B-no-stratagem`, `B2-no-support`, `B3-no-stratagem-no-support`, `B4-no-entity` | the project minus stratagem, support, both, or attachment edits |
| `C-original-plus-maxigun-backpack` | the project plus Maxigun backpack capacity 1500 and refill 750 |
| `D-ma5c-only`, `D2-ma5c-capacity-only` | all MA5C edits; only magazine.capacity 32 → 60 |
| `D3-ma5c-plus-stratagem`, `D4-ma5c-plus-support` | MA5C plus the stratagem edit; MA5C plus every support edit |
| `E-maxigun-only`, `E2-maxigun-plus-backpack`, `E3-backpack-only` | the Maxigun weapon edits, plus the backpack edit, the backpack alone |
| `G-orbital-precision-strike-only` | Orbital Precision Strike cooldown 80 → 60 |
| `F-<weapon>` | each reported weapon alone |

Regenerate (needs the sibling `HD2RuntimeGUI` repository and .NET 10):

```
dotnet run --project scripts/modbuilder_export_harness -c Release -- tests/fixtures/user-reports/ayakamods-weaponry-rebalance/project.hd2mod.json tests/fixtures/user-reports/ayakamods-weaponry-rebalance/generated
```

Then delete the harness's `generated/workspace` folder.
