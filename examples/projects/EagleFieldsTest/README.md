# EagleFieldsTest

Live test for the Eagle attack fields (`hd2.fields.eagle.*`). Uses the MODS tab (page **Eagle Fields Test**). The log
banner is **EAGLE FIELDS 0.1.0 BUILD**: check that this exact line appears, so you know the right build is loaded.

Each field is a member of the attack record of the Eagle's **own jet**. Runtime reaches it through the stratagem's
payload and re-proves it before every write. It is a **type-record write**: every call of that Eagle on this machine
uses the new value until the option is turned off. It is not per call, and no other Eagle reads it. The Napalm and
Strafing Run jets are also used by the Democracy Space Station's Eagle Storm, so those two operations set
`allow_shared`. Nothing here is live-proven yet, so every operation sets `allow_unverified_effect`.

| Option | Default | What it does | Field |
| --- | --- | --- | --- |
| Airstrike: 8-bomb zigzag | on | Eagle Airstrike landing pattern 0 -> 2 | `eagle.airstrike_pattern` |
| Napalm: slow release | on | Eagle Napalm Airstrike 0.2 s -> 0.6 s between bomb releases | `eagle.drop_interval` |
| Strafing Run: double burst | on | Eagle Strafing Run attack 1.5 s -> 3.0 s | `eagle.fire_duration` |
| 110mm: wide target search | on | Eagle 110mm Rocket Pods target search radius 20 m -> 60 m | `eagle.target_radius` |

## Before the mission

1. Install this mod, Bingus and the HD2Runtime build being tested (0.30.0-dev or later).
2. Take **Eagle Airstrike**, **Eagle Napalm Airstrike**, **Eagle Strafing Run** and **Eagle 110mm Rocket Pods**
   (one Eagle loadout per mission is fine; repeat for the others).
3. Play as the host (solo is simplest).

## Checklist

- [ ] The log shows `EAGLE FIELDS 0.1.0 BUILD` and `APPLIED` for each enabled operation (`eagle-airstrike-pattern`,
      `eagle-napalm-interval`, `eagle-strafe-duration`, `eagle-rocket-radius`).
- [ ] **Airstrike**, throw on open ground: **8 bombs** land in a tight zigzag about **21 m** long (vanilla: 6 bombs
      over about 35 m). Count the explosions.
- [ ] **Napalm**: the 4 bombs are released clearly further apart in time (0.6 s instead of 0.2 s). The landing
      points stay in the same line, because each bomb is aimed at its own pattern point.
- [ ] **Strafing Run**: the gun burst lasts about **3 s** instead of 1.5 s (about 200 rounds instead of 100). The
      sweep covers the same 60 m, only more slowly.
- [ ] **110mm**, throw the beacon so that enemies stand **30-50 m** from it and none within 20 m: the rockets
      engage those enemies (vanilla: they only target enemies within 20 m of the beacon).
- [ ] Turn each option off and APPLY: the next call of that Eagle is vanilla again, and the log shows the restore.
- [ ] Other Eagles you did not change (for example Eagle 500kg Bomb or Cluster Bomb) behave exactly as vanilla.

Report each item as seen, not seen, or unclear, together with the log. Please also note whether a change appeared on
the first call after APPLY or only on later calls. A jet already in flight picks up the drop interval, pattern and
attack duration at once; the target radius applies from the next call.
