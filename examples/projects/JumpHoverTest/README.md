# JumpHoverTest

Live test for the jump / hover movement fields (`hd2.fields.jump.*`, `hd2.fields.hover.*`,
docs/backpack-authoring.md). Uses the MODS tab (page **Jump Hover Test**). The log starts with
`JUMP HOVER 0.1.0 BUILD`; then one `APPLIED` line per option that is on.

Each field is a member of the pack's own JumppackComponent record, read live by the flight code every frame. An
APPLIED write takes effect at once, also on a pack you already wear. The Jump Pack and the Hover Pack run different
code paths, so each field exists only on the pack that reads it (the Hover Pack, for example, never runs the launch
thrust).

| Option | Default | Pack | Field(s) | Vanilla -> test |
| --- | --- | --- | --- | --- |
| Jump: flat dash | on | LIFT-850 | jump.launch_forward_ratio | 0.4 -> 0.95 |
| Jump: long launch | off | LIFT-850 | jump.launch_duration | 0.5 -> 2 s |
| Jump: strong second boost | off | LIFT-850 | jump.sustain_thrust / sustain_duration | 60 / 1 s -> 120 / 4 s |
| Jump: strong air control | off | LIFT-850 | jump.air_control_acceleration | 4 -> 40 |
| Jump: big take-off hop | off | LIFT-850 | jump.takeoff_speed | 2.8 -> 12 m/s |
| Hover: fast drift, slow climb | on | LIFT-860 | hover.max_horizontal_speed / max_vertical_speed | 3.5 / 10 -> 15 / 1 m/s |
| Hover: frugal fuel | off | LIFT-860 | hover.fuel_rate_low_speed / fuel_rate_high_speed | 1.6 / 0 -> -0.9 / -0.9 |
| Hover: snappy climb | off | LIFT-860 | hover.vertical_acceleration_low_speed | 9.8 -> 40 |

## Checklist (host, in a mission)

Jump Pack (LIFT-850):

- [ ] Log shows `JUMP HOVER 0.1.0 BUILD` and `patch jump-flat-dash APPLIED`.
- [ ] **Flat dash**: jump while running. The arc is very low and long (most of the thrust goes forward). Standing
      still, the pack pushes you almost flat along your facing instead of up.
- [ ] **Long launch** (flat dash off): the thrust lasts about 2 s instead of 0.5 s; you go roughly four times as high.
- [ ] **Strong second boost**: keep moving after take-off; about 1 s in, a long second push carries you much further.
- [ ] **Strong air control**: mid-air, steering with the movement keys turns you sharply (vanilla barely).
- [ ] **Big take-off hop**: a visible hop straight up before the thrust starts.

Hover Pack (LIFT-860):

- [ ] Log shows `transaction hover-drift APPLIED`.
- [ ] **Fast drift, slow climb**: while hovering you drift sideways fast (15 m/s, vanilla 3.5). The climb cap
      (1 m/s, vanilla 10) shows only together with a lift above gravity: the vanilla Hover Pack does not climb by
      itself (docs/backpack-authoring.md, How high the Hover Pack flies).
- [ ] **Frugal fuel**: hover until the pack gives out: it lasts far longer than vanilla (the recharge meter fills at
      0.1 s per second instead of 1 to 2.6).
- [ ] **Snappy climb** (fast drift off): the lift (40) is far above gravity: after activation the pack climbs fast
      (about 6 m/s) for about 6 s of air time, then holds height.
- [ ] A gentler "climb higher" (lift 15, about 2.8 m/s) is a toggle of proof/RebalanceFixesProof. Vanilla: the pack
      only holds the height you activated it at.
- [ ] Turn every option off: vanilla behaviour again.

Report each line (what you saw, and the APPLIED / REJECTED log lines). Also report whether the effect applied to a
pack already on your back (expected: yes, next frame) and, if you can, whether other players' packs changed.
