# User report: SG-20 Halt edits nullify other changes (2026-09-30)

SkyeShade/HD2Runtime-ModBuilder#2: "overriding any of the Halt's values causes every single other change made besides
damage overrides to be nullified".

## Reproduction

The reporter used ModBuilder 1.3.1 (the latest release) with the published HD2Runtime 0.27.0. The fixture
`tests/fixtures/user-reports/modbuilder-issue-2-halt` holds ModBuilder 1.3.1's own `LuaGenerator` output, extracted
read-only with `git archive v1.3.1`. The exports edit every writable Halt field together with unrelated AR-23
Liberator and SMG-32 Reprimand edits, placed before and after the Halt in project order.

| Export | Published 0.27.0 | 0.28.0 |
| --- | --- | --- |
| no Halt edit | 3 registered, applied | 3 applied |
| every Halt field | **startup error** `field is not exposed for SG-20 Halt: projectile.drag`, **0 registered** | 8 applied |
| Halt damage only | **startup error** `field is not exposed for SG-20 Halt: damage.ap_direct`, **0 registered** | 5 applied |
| Halt sway only | 4 applied | 4 applied |

## Cause (Runtime)

1. **Unresolved fields.** ModBuilder emits the Halt's projectile and damage fields as generic constants
   (`hd2.fields.projectile.drag`, `hd2.fields.damage.ap_direct`, ...) on
   `hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile()`. The Halt names these fields per feed
   (`projectile.primary.drag`, `damage.alternate.ap_direct`). Published 0.27.0 did not resolve generic fields on a
   rounds-feed attack to its branch.
2. **Addon aborted.** Published 0.27.0 raised on the first operation that failed validation. The raise aborted the
   generated `addon.lua`: every operation after it never registered. Operations generated before it still applied,
   often the damage transactions. Weapon component fields (sway, fire rate, rounds) disappeared, which is what the
   user saw.

**Fixed in 0.28.0 (commit aaabb0a):**
- **Branch resolution.** A generic projectile-object field on a rounds-feed attack resolves to that feed's branch.
- **Registration isolation.** `hd2.patch`, `transaction`, `plan` and `ensure` log `<kind> <id> rejected: <reason>`
  and return a rejected handle instead of raising. This holds for a whole plan too.
- **Duplicate ids.** One mod registering the same operation id twice gets one warning; both still register.

Regression coverage:
- `tests/test_user_reports.py` `HaltIssueTests`: the recorded results, every export operation validates, ids are
  unique, a refused plan in the middle of an addon, duplicate ids.
- The packaged-runtime scenarios `user-report-halt-issue-*` run every export from the built ZIP.

## ModBuilder: required and recommended changes (not made in this repository)

- **Required:** export with SDK 0.28.0 or later and declare `min_version = 0.28.0`. 0.27.0 cannot resolve the Halt's
  generic feed fields, and aborts on the first refused operation.
- **Recommended:** emit each operation so that an error while *building* its request (an unknown weapon or role name,
  a missing field constant) cannot stop the ones after it. Registration isolation catches every validation failure
  inside `hd2.ensure`, but a Lua error while evaluating the request table happens before `hd2.ensure` is called:

  ```lua
  local function add(build)
      local ok,operation=pcall(build)
      if ok then operations[#operations+1]=operation
      else print('[ModBuilder] operation skipped: '..tostring(operation))end
  end
  add(function()return hd2.ensure({patch={...}})end)
  ```

- **Optional:** the branch-qualified constants (`hd2.fields.damage.primary_standard_damage`, ...) remain accepted and
  resolve without the feed fallback.
- **Keep:** operation ids are already unique in every export (`gui-object-*`, `plan-*`, `op-*`).
