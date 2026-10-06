# EagleStunRocketPodsExample 0.3.1: Eagle Stun Rocket Pods on the custom stratagem API

Development example of `hd2.custom_stratagem` (docs/custom-stratagem-api.md, "eagle"). **Solo host only.**
It is the "custom Eagle" archetype.

**Status:** the call's rocket association and conversion are **LIVE-PROVEN** (0.3.0, 2026-10-04). Only the EMS field's
presentation is still open (see "Still to prove live").

0.3.1 (`0.3.1 DEV LINE BUILD`): the HD2Runtime 0.30 development line. It requires HD2Runtime 0.30.0-dev or newer
(`requires.hd2runtime.min_version`). The custom stratagem API is not in 0.28.0, so an older Runtime now shows its
update warning instead of failing at load. The example itself is unchanged. The Runtime now logs each call's state
transitions only (see "Logs").

## What the live builds showed (2026-10-04)

- 0.1.0: the redirect and the jet capture worked; the binding ended at once; no rocket converted.
- 0.2.0 (the trace): the call's jet stays in the Eagle manager for the whole run (about 12 s). Its rockets were seen,
  but none was converted:
  - call #1: jet 1019, rockets from sources 1020 and 1021 (entity types 0E8C2515261E0325, 486522867199D7F3), owner
    1019, impact copy 229;
  - call #2: jet 1160, sources 1161 and 1162, owner 1160.

  The 0.2.0 rule took only rockets whose source is the jet (`NOT THIS CALL'S`).
- 0.3.0 (pod ownership), **live-proven**:
  - the jet was captured;
  - its right and left pods were bound from the jet's own mount record;
  - the call's type-82 rockets were captured, with the jet as their owner;
  - each was converted 229 → 188 on its own impact copy, and read back;
  - the game queued explosion 188 for them;
  - unrelated projectiles stayed vanilla.

## The ownership hierarchy (research custom-payloads "eagleMount")

- The 110mm jet's MountComponentData mounts two payload pods, both projectile weapons:
  - 0x0E8C2515261E0325 at node "payload_right" (slot 0);
  - 0x486522867199D7F3 at node "payload_left" (slot 1).
- The pods fire the rockets: a rocket's pool **source** is a pod, its **owner** is the jet.
- The game keeps each mounted child in the jet's own mount record (the mount component, six per mount).

## The rule (since 0.3.0)

**A rocket is this call's only when both hold, checked per projectile from its own records:**

1. **Its source is a pod of the call's jet.** The pod is named by the jet's own mount record, in the slot the jet's type
   mounts that resource in, and is of exactly that entity type.
2. **Its owner is the call's jet.**

**What stays vanilla:**
- A vanilla 110mm's rockets name its own pods and its own jet, so they are never converted.
- A rocket of a pod with another owner is refused (`OWNER_MISMATCH`), and so is a pod the mount record does not name.
- Only if the jet's mount record cannot be read at all is a source taken by its pod type plus the owner. The log says so.

The conversion is one guarded write of that rocket's own impact copy (229 → 188), read back. The carrier, the 5 uses
per rearm and the Runtime rearm are as before.

## Logs (HD2Runtime 0.30.0-dev)

By default the log keeps each call's state transitions:
- `custom eagle JET CAPTURED (...)`;
- `custom eagle ROCKETS BOUND (...)`;
- `custom eagle PAYLOAD POD (...)`, once per pod;
- `projectile impact CONVERTED (...)`, once per rocket (or `REFUSED`, with the reason);
- one `custom eagle ROCKETS RESULT (...)`, ending in `NOT PROVEN` if no rocket converted.

The detailed per-rocket trace is behind verbose. It covers the TRACE lines (`ROCKET CAPTURED`, `IMPACT CONVERTED`,
`NOT THIS CALL'S`, `IMPACT REQUESTED`), the jet's presence in the Eagle manager and the explosion requests read from the
game's queue. Turn it on with `hd2.custom_stratagem.verbose(true)` in a mod's `src/addon.lua`, then rebuild that mod.
Without verbose none of those reads happen.

## Still to prove live

Whether the explosion 188 the rockets request presents as the Orbital EMS Strike's does: the blue static field and the
stun status on enemies.
- The request is built exactly as the EMS shell's is: the same impact path, the projectile's own copy, the same row
  word.
- Explosion 188's own rows carry the stun and the 15 s StaticField.
- The field itself cannot be read in this build. Watch for it.

## Test

1. Expect `EagleStunRocketPodsExample 0.3.1 DEV LINE BUILD`. Select Eagle Stun Rocket Pods.
2. Solo mission. Call it once, away from anything else. Expect:
   - `JET CAPTURED`, `ROCKETS BOUND`, then two `PAYLOAD POD (...)` lines (payload_right, payload_left);
   - one `projectile impact CONVERTED (...): ... impact explosion 229 -> 188` per rocket;
   - `ROCKETS RESULT ... N rockets converted 229 -> 188, 0 refused; ...` without `NOT PROVEN`.

   Say whether a blue EMS field appears and whether enemies are stunned.
3. **Isolation:** bring a vanilla Eagle 110mm Rocket Pods. Call the vanilla one and the custom one some seconds apart
   (not in the same second: then the capture refuses and both runs stay vanilla). Expect normal explosions from the
   vanilla run and no CONVERTED line for it.
4. Optional: call a real Orbital EMS Strike in the same mission to compare the field.

## Limits

- Solo host only.
- The rockets' creditor must be you (live: yes, the local peer).
- The HUD's inbound time is the carrier Eagle's; the jet and the strike are the 110mm's.
