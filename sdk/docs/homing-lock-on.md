# Pre-fire lock-on and reticles

An opt-in extension of `hd2.projectiles.homing`. Calls without `acquisition = 'pre_fire'`
retain in-flight target acquisition, the existing defaults and the velocity-only write path.
The shared engine is used; a mod does not bundle another homing implementation.

**Validation:** the Runtime port has partial live solo AR-23 coverage on build
25480438: steering/LOS/multi-lock records on `cb8f9a3`, actual stock-asset rendering
on `9aaba06`, and user-confirmed initial/reinforcement descent suppression with
landed HUD recovery on `53c7630`. Remaining validation includes explicit latest
hip-fire/re-aim and broader map/menu transitions, controller/toggle/remapped Aim,
and other weapons. Native-looking art is not a claim of exact native timing or
appearance. No hit, HP or damage outcome is recorded. Full research/snapshot and
SDK/release generation still require inputs unavailable in this checkout.
See `validation/homing-lock-port.json` for the exact distinction and native provenance.

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local gun = hd2.projectiles.homing('AR-23 Liberator', {
    acquisition = 'pre_fire',
    lock_time = 0.3, max_targets = 3,
    cone = 12, range = 100, arm_distance = 0,
    lateral_acceleration = 600, turn_rate = 1440,
    require_los = true, require_aim = true,
})
if gun.status == 'active' then
    local hud = gun:reticle({
        marker_shape = 'corners', marker_size = 12,
        acquiring_color = '#FFB420', locked_color = '#40FF60',
        ring_width = 1.5, aim_only = true,
    })
    -- Appearance changes preserve acquisition and rounds already in flight.
    hud:style({marker_shape = 'cross', locked_color = '#00CCFF'})
    -- hud:hide(); hud:show(); hud:stop() -- visual only
end
-- gun:stop() also removes its HUD and frame callback.
```

This example requires a development build containing this extension, not the stock
0.40.0 release. Stock 0.40.0 safely refuses the new options. Do not replace a user's
installed Runtime solely because the version string is 0.40.0.

## Acquisition contract

| Option | Default | Meaning |
| --- | --- | --- |
| `acquisition` | `'in_flight'` | Existing behavior, or `'pre_fire'`. |
| `lock_time` | 0.3 | Pre-fire only, 0..2 seconds of uninterrupted acquisition. |
| `max_targets` | 1 | Pre-fire only, integer 1..6. New rounds rotate over the locked set. |
| `require_los` | false | Pre-fire only. When true, both blocked and unknown rays are rejected. |
| `require_aim` | false | Pre-fire only. New acquisition and shot assignment require the native Aim action. Release or unknown input clears locks; previously allocated rounds continue. |
| `lateral_acceleration` | unset | Optional 1..100000 m/s² budget, available with either acquisition mode. |

Pre-fire currently requires **solo/host**, enemy targets, `cone <= 30`, `range <= 300`
and no retargeting. `retarget` defaults to false in this mode; explicitly requesting
true is refused. Friendly/multiplayer support remains the original in-flight API's
experimental behavior; it is not silently enabled for pre-fire. The weapon must be
held, not merely present in the inventory. The public weapon catalogue still decides
which projectile types and firing entity types belong to it; unit-driven projectiles
are still refused.

Capture uses a verified current camera when available. If discovery fails, new
acquisition falls back to the held weapon's root direction and the HUD hides. Changing
this basis restarts acquisition but does not terminate valid allocated flying rounds.
Weapon/owner/session changes, stale observations, unknown spawn windows or reused
slots invalidate the relevant allocation. A target's health descriptor and unit are
rechecked, not only its entity number.

A round is assigned once, at first observation. A target must have locked before the
**previous** observation of that spawn window. A round fired before locking never
acquires later. The set is ordered by identity so angular jitter does not reshuffle
the rotation; losing and reacquiring a target restarts its timer. Lock completion
does not imply that a particular future shot will hit.

`require_aim` controls gameplay independently of the HUD's `aim_only`. The latter
only hides drawing: a configuration omitting `require_aim` can still acquire and
steer hip-fired rounds while its HUD is hidden. This default preserves the original
API. To require aiming, opt in explicitly as the example does. Releasing Aim clears
pending and completed locks; re-aiming starts the timer again. A round already
assigned while aiming remains fire-and-forget, subject to the normal owner/slot
guards. Unknown input refuses new assignments without cancelling valid old rounds.

The shared engine retains 16 tracked rounds, 64 new slots per update, 10 seconds
of follow-up and its bounded incremental target scan (12 cached position refreshes
per update). Pre-fire filters that cache by its 0.5-second position age and current
cone/range, then freshly validates at most eight candidates per controller
observation. Existing locks/acquisitions retain their validation slots; remaining
slots rotate through the other candidates so blocked front rows do not starve later
clear targets. Each validated target's current identity, position and cone/range
are checked again before acquisition. A dense scene can delay discovery until that
target's cache position and rotating validation slot are both available.

There are at most eight LOS queries per observation, with 0.1-second reuse for
unchanged rays. LOS uses the same `aim_height` as acquisition, steering and the HUD.
The policy also retains at most 4096 assigned generation keys for 120 seconds to
reject duplicate observations. Reaching any tracking/assignment/window limit can
leave a shot flying straight; these budgets are not a hit guarantee.

A transient read/proof failure clears locks and in-flight identities without
erasing `stats()` totals for the current mission. A confirmed mission end resets
those totals as before.

## Speed-aware steering

With no acceleration setting the original fixed angular rate is unchanged. With it:

```
angular_rate_rad_s = min(rad(turn_rate), lateral_acceleration / current_speed_m_s)
maximum_turn = angular_rate_rad_s * update_seconds
```

Speed magnitude is preserved. `turn_rate` remains the angular safety cap; the existing
default is 90 degrees/second. To compare with the originating mod's 600 setting, use
`turn_rate = 1440`: at 900 m/s the calculated rate is about 38.2 degrees/second.
This is a calculation, not a guaranteed AR-23 speed. Lower acceleration gives gentler
curves at the same speed and can make nearby/off-axis targets harder to hit. There
is no predictive lead, obstacle avoidance or forced hit.

## Standard HUD

`handle:reticle(style)` is optional and needs an active pre-fire handle. It returns
a visual handle with `:style(partial)`, `:show()`, `:hide()`, `:status()` and `:stop()`.
Invalid style raises, as `hd2.ui.overlay` does; gameplay refusals still return a
refused homing handle. A bad style update leaves the previous HUD intact. Stopping
or replacing gameplay removes its HUD; two different owners' HUDs do not destroy
each other. Hiding/stopping the HUD never stops homing.

| Style | Default / allowed values |
| --- | --- |
| `ring` | true |
| `ring_color` | amber |
| `ring_width` | 1.2, .5..8 pixels |
| `ring_segments` | 96, integer 24..128 |
| `ring_radius` | unset: current capture cone/FOV; optional 8..2000 pixel cosmetic override |
| `marker_shape` | `'corners'`, `'box'`, `'cross'` or `'vanilla'` |
| `marker_size` | 12, half size at 1080p, 4..64 |
| `line_width` | 1.5, .5..8 pixels |
| `scale` | 1, .5..3; markers and labels, not the capture angle |
| `acquiring_color`, `locked_color` | amber / green |
| `clear_color`, `blocked_color`, `unknown_color` | blue / red / grey |
| `show_labels`, `show_numbers`, `show_progress`, `show_los` | false for vanilla, true for other shapes; explicit values override |
| `aim_only` | true; false still suppresses menus |

Colours use `{r,g,b[,a]}` in 0..255 or `#RRGGBB[AA]`. Inputs are copied. Omit
`ring_radius` to keep the drawn ring faithful to acquisition; a cosmetic override
never enlarges the actual capture cone. Resolution/FOV changes are handled by the
renderer. Fonts are optional: geometric progress/number markers remain available.

`vanilla` uses the stock P-92 Warrant atlas marker when its material/texture and
bitmap bindings are resident. Three markers orbit each actual Runtime target,
rotate once as its acquisition progresses, and contract from 24 to 10 pixels at
1080p. Complete locks are compact and green by default. Mod-added numbers, LOCK/ACQ text, LOS labels/bars and progress bars are off
by default for this shape. Explicit `show_* = true` opts into those decorations;
custom colours and independent markers for multiple targets remain available. This draws stock
art; it does not activate the game's native TargetLock or change the weapon's
crosshair enum. The reference is Guided Rounds' `markers_setup`, `quad` and
`markers_draw` in commit `71303dd35954f94f57f8308fb6e2c86d8e22abc4`.

Missing resources or bindings use three geometric chevrons instead. HUD `status()`
reports `marker_renderer` as `vanilla_asset` / `vanilla_geometry` and supplies
`renderer_reason` for a fallback. Runtime does not force a weapon package to load
just by creating a reticle. A caller may explicitly warm a known semantic package
with `hd2.require_assets({id='homing-stock-markers', targets={hd2.weapon('P-92 Warrant')}})`;
normal package proofs, asynchronous readiness and session retention still apply.
The `9aaba06` local test logged `vanilla_asset` and completed the explicit
Warrant package request. That verifies this resource path on the tested build,
not pixel-identical native timing, colour, circle dimensions or TargetLock behavior.
Web comparison reference: [Better Aim Reticles](https://www.nexusmods.com/helldivers2/mods/2388),
the author's lock-on circle/triangle sections. The comparison image could not be
visually inspected through the available browser; no exact appearance match is claimed.

Aim-only reads the game's resolved Aim action (group 2/index 8), not a hardcoded
mouse button or guessed zoom threshold. The input layout is code-pinned. This is
action activation, not proof of completion of an aiming animation. Remapped input,
toggle aim and controllers need separate device coverage in the generic integration.
ESC stack, Runtime settings and a visible cursor suppress drawing. The private
gate also requires the current local player's spawned lifecycle (3), living owned
health record and proven avatar flags: alive, not seated, tactical map closed and
weapon menu closed. These gates apply even with `aim_only = false`, and frame
cleanup removes retained ring/stock/label GUIs while acquisition is idle. The flag
layout reuses `player_equipment` proofs; semantic bits are retained from C4 Quick
Actions 1.13.1. Unknown state hides conservatively. This is a positive gameplay
eligibility check, not a claim that any specific lifecycle value means descent.
The `2d1bfa8` user test demonstrated that these avatar conditions do not identify
hellpod descent: a healthy/spawned avatar can still be attached to that view.
The private HUD gate therefore reads the actual HellpodComponent manager now.
Only the known initial/reinforcement player-pod types owned by this machine are
considered; phase 0 (falling) and 1 (braking) hide the HUD, phase 2 (landed) releases
this gate subject to the other avatar/menu checks. The existing same-build
HellpodDropHold v1.2 was the lead; globals, record/hash/array layout, owner bit and
phase instructions were independently checked in the retained unpacked game.dll
and are code-pinned again at runtime. An unavailable/changed manager, unstable
identity, unknown phase or scan-budget excess hides instead of claiming no drop.
The scan inspects at most 64 records and at most 64 hash probes per relevant pod.
There are no FOV thresholds, delay timers, native calls or writes in this reader.
The `53c7630` / local client 0.4.0 user test on 2026-10-20 confirmed the reported
descent/landing HUD issue resolved. Logs show initial-pod braking (phase 1) and
reinforcement falling (phase 0) suppressing ring/markers, then landed phase 2
drawing again. This is observed coverage, not every phase for every drop type,
input device or multiplayer role. Other UI without these indicators may remain
unknown; universal menu coverage is not claimed.

HUD `status()` also records the last admission observation's `drop_state`,
`drop_phase`, game `drop_entity`, `drop_type` and `drop_records` when available.
These are actual manager observations, not a custom test ID. Raw camera FOV and
capture radius may change during descent even while `ui_visible` is false: the
radius follows projection, and is not a descent detector. The 0.3.0 user log
showed roughly 164 -> 651 px at the same 12-degree cone and 1080p height; through
the projection formula these imply vertical FOVs about 70 -> 20 degrees. The old
log did not store FOV directly, so that numerical reconstruction is an inference.

## Custom renderers

`handle:lock_state()` returns nil for in-flight acquisition, otherwise a detached
observation: `state`, `reason`, `aim_basis`, `observed_at`, `locked`, `acquiring`,
`visible`, `ui_visible`, optional `width`, `height`, native `vertical_fov` (radians) and capture `radius`.
With the optional Aim gate, `aim_active` is true/false when observed and nil when
unknown; `aim_reason` explains the observation or `not_required` for the default.

Targets carry an observation-scoped `id`, game `entity`, catalogued `name`, root plus
`aim_height` `position`, optional top-left pixel `screen`, `progress`, `acquired_at`,
and LOS state/reason/time. No native pointer, camera handle or mutable engine record
is published. `visible` means a usable acquisition camera frame; custom HUDs should
also respect `ui_visible` for the standard menu/aim gate. Observation times use the
homing engine's elapsed clock, not wall time, native game time or `hd2.events` time.

Entity IDs may be reused and are not persistent lifetime identifiers. These fields
are acquisition/steering observations: they do not identify a projectile collision,
hit body part, armor, health loss or final damage. LOS is the weapon-root straight
ray to the aim point, not a muzzle/barrel clearance proof or curved-flight prediction.
A failed, saturated, ambiguous or unavailable native query remains `'unknown'`.
The native call goes through the writable adapter's private `native_raycast`
capability during a scheduler update, after code/descriptor/physics-world checks.
A read-only or custom adapter without that capability reports unknown; it never
falls back to calling an absolute engine address. The adapter owns and accounts for
reused query buffers and stops further calls if their guard is overwritten.

## Repeating the live check

1. Use the development Runtime with `examples/projects/HomingLockOn`; disable another
   writer for the same weapon. Start solo/host with normal AR-23 rounds.
2. Confirm the HUD hides/reappears on aim release/press and stays hidden in menus.
   With `require_aim=true`, hip fire must not acquire or assign new shots. Previously
   assigned rounds may keep steering after release; re-aim must restart acquisition.
3. Fire before lock: no retroactive steering. Lock three targets and burst: inspect
   `lock_state()`/`stats()` separately from hit outcomes.
4. Compare the same geometry at acceleration 300/600/1200, then without the setting.
5. Exercise an occluded target with `require_los` false/true; unknown must not count
   as clear. Replace/stop the handle and cross a mission transition.
6. Select `vanilla`, inspect `marker_renderer`, and compare acquisition/locked
   appearance on several targets. Keep a geometry fallback distinct from stock art.

Offline tests do not replace this test. The repository's full research/snapshot suite
also requires the separately hosted research submodule and retained snapshots; they
were unavailable for this contribution's full release validation.
