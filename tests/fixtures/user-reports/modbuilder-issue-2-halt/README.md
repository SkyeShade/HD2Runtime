# ModBuilder issue 2: SG-20 Halt edits nullify other changes (2026-09-30)

Report (SkyeShade/HD2Runtime-ModBuilder#2): "overriding any of the Halt's values causes every single other change
made besides damage overrides to be nullified".

**Cause.** The published HD2Runtime 0.27.0 raised instead of rejecting when one operation failed validation. ModBuilder
1.3.1 writes the Halt's projectile and damage edits as generic fields (`hd2.fields.projectile.drag`,
`hd2.fields.damage.ap_direct`, ...) on `hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile()`. Published
0.27.0 did not resolve those to the Halt's branch fields (`projectile.primary.drag`, `damage.primary.ap_direct`), so
the first Halt operation raised `field is not exposed for SG-20 Halt: ...`. That aborted the addon: every operation
generated after it never registered, while operations generated before it (often damage transactions) still applied.
Weapon component fields (sway, fire rate, rounds) are exactly the ones that disappear.

**Fix (in the unreleased tree since commit aaabb0a, shipping with 0.28.0).**
- Rounds-feed attacks resolve generic projectile-object fields to their own branch.
- `hd2.patch/transaction/plan/ensure` log `<kind> <id> rejected: <reason>` and return a rejected handle instead of
  raising, so one refused operation can never abort the rest.
- One mod registering the same operation id twice gets one warning (both still register).

The ModBuilder 1.3.1 exports here (every writable Halt field plus unrelated Liberator and Reprimand edits, before and
after the Halt in project order) register and apply completely on the current tree.

| Variant | Contents | Published 0.27.0 | Current tree |
| --- | --- | --- | --- |
| `H0-control-no-halt` | Liberator and Reprimand edits only | 3 registered, applied | 3 applied |
| `H1-halt-all` | every writable Halt field (damage, projectile, rounds, weapon) plus the others | startup error, 0 registered | 8 applied |
| `H2-halt-damage-only` | the Halt's damage fields plus the others | startup error, 0 registered | 5 applied |
| `H3-halt-sway-only` | Halt sway (a weapon field) plus the others | 4 applied | 4 applied |

`generated/results.json` records both runs; `generated/summary.json` lists every field each variant edits.

Regenerate (needs .NET 10 and the ModBuilder v1.3.1 source, extracted read-only):

```
git -C ../HD2RuntimeGUI archive v1.3.1 | tar -x -C build/test-artifacts/mb-1.3.1
dotnet run --project tests/fixtures/user-reports/modbuilder-issue-2-halt/harness -c Release -- <output folder>
```
