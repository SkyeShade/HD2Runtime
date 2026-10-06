# PelicanGatlingAIProof 0.2.0 (development only, solo host): the AI change through the game's own SetBehaviour

**0.1.0 live: the AI was never changed** (`AI switched false`). The freshly spawned chin turret sat in behaviour 645
stage 4, and 0.1.0 allowed the change from stage 1 only. That run tested 148 at 600 RPM on the native AI only.

**Research since** (docs/research/pelican-cas-F5FEE03DCFDB.md section 18b):
- **645 stage 4 = the turret is not active.** It sits there during the Pelican's approach. Entering it parks the aim
  and clears the target, and it runs no timer. 645 pulls the trigger only on entering stage 3, so the trigger is
  released in stage 4 (and in stage 1).
- **213's real start is its own stage 1, entered through its own transition.** That is what the game gives every new
  entity. 213's stage 4 is a mid-engagement state, so a raw id write in stage 4 would start it in the wrong place.
- **The game changes behaviours itself** with **SetBehaviour** (0x843EA0). It exits the old behaviour through its own
  transition, writes and replicates the id, and enters the new one at stage 1.

**0.2.0:**
- It calls the game's SetBehaviour with 213 (the adapter accepts 213 only) while the chin turret is quiet: 645 stage 1
  or 4, nothing pending, no transition running.
- It reads the field before and after: `behaviour BEFORE = 645`, `behaviour AFTER = 213`. Anything but exactly 213
  after is a failure (`AI SWITCH FAILED`, `NOT_APPLIED`).
- The requested behaviour is labelled separately from the field.
- Every `AI STAGE` line prints the field.
- The summary gives the field after the change and at the end, and how many AI STAGE lines read 213.

**Note:** the Gatling AI does not use the chin turret's "active" check. It may engage during the Pelican's approach as
soon as it has a target.

The first line is `PelicanGatlingAIProof 0.2.0 GATLING-AI SET-BEHAVIOUR BUILD (solo host)`. The live test is the
sequence below, with this build's ZIP.

# PelicanGatlingAIProof 0.1.0 (development only, solo host): the Gatling Sentry's AI on the Pelican's own chin turret

The chin turret keeps its entity, model, mount, node 41 and attachment. Only its AI and weapon change, for that one
Pelican. Research: docs/research/pelican-cas-F5FEE03DCFDB.md, section 18.

## The field, found [C]

Every entity with an AI has a Behavior record (504 bytes). Its first 4 bytes are the **behaviour id**: 645 on the chin
turret, 213 on the Gatling Sentry.
- It is per instance: written when the entity is created.
- Every frame, the Behavior update reads it and runs that behaviour's code through the game's behaviour jump table.
- The record's layout is the same for every behaviour. A behaviour's own code sets up its state through its own stage
  transitions; there is no other per-behaviour setup.

So the proof changes only that one value, 645 -> 213, with one guarded write. It does so only while the chin turret is
idle: stage 1, no stage pending, no transition running (so its trigger is released). The Gatling AI then starts from its
own stage 1 and walks its own stages: 6, a deploy stage, then search and its continuous firing stage 12. No fire-window
hold and no spin-up.

## Timing

It acts as soon as a Runtime Pelican's chin turret exists and is uniquely identified, during the Pelican's approach,
before the turret has done anything. It refuses if more than one turret names the Pelican.

## What it does

For each Pelican CAS Pelican:
1. `AI FIELD` (read-only) shows the chin turret's Behavior record, the id field's address and value, its stage, pending
   and transition fields and its target. The same is shown for every Gatling Sentry seen.
2. **Weapon:** projectile 148 at the configured RPM (default 600) on its own ProjectileWeapon record. The Gatling
   pattern is optional (Ctrl+F10).
3. **AI:** 645 -> 213 while idle. Ctrl+F9 turns this off for a read-only run that only shows the field.

Logged throughout:
- every AI stage change (`AI STAGE`, with the stage's meaning; `-- FIRING` in stage 12);
- every target change (`AI TARGET`: acquired, lost, switched);
- the rounds (`AI FIRE`);
- a summary when the Pelican leaves (`AI SUMMARY`).

**Keys** (each applies to Pelicans seen from then on):
- Ctrl+Shift+F2: RPM 600 -> 1000 -> 1600 -> 300.
- Ctrl+F9: AI switch on/off.
- Ctrl+F10: pattern on/off.
- Ctrl+Shift+F1: status.

## Known risk

The Gatling AI's stage 2 drops to stage 10 when neither of its weapon checks passes, probably while out of ammunition
or reloading. Stage 10 waits for a flag from a component the chin turret does not have, so the AI could stay there.
Watch for `stage 10` in `AI STAGE`, typically after a reload.

## Which build is running

The first line names the build (0.2.0: `GATLING-AI SET-BEHAVIOUR BUILD`).

## Live test

**Setup:** solo host. Install this hand-off's runtime ZIP, `PelicanGatlingAIProof-0.2.0.zip` and
`PelicanCasProof-0.1.1.zip`. Install no other Pelican proof alongside it.

1. Call Pelican CAS near a group of enemies. Expect `AI FIELD`, `AI WEAPON`, `AI SWITCHED` and `AI RESULT` while it
   approaches, then the `AI STAGE` lines walking 1 -> 6 -> (7/8/9) -> 2 ...
2. The sequence to check:
   1. it acquires a target (`AI TARGET acquired`);
   2. it fires continuously (stage 12 `-- FIRING`, `AI FIRE` lines);
   3. the target dies or leaves its view (`AI TARGET LOST`);
   4. the firing stops (it leaves stage 12);
   5. another enemy comes into view;
   6. it retargets (`acquired` / `switched`) and fires again.
3. Optional: Ctrl+F9 once (read-only), call CAS again, and compare with the native AI.

**Send** every line starting with `PelicanGatlingAIProof`, `PELICAN WEAPON`, `AI ` and `assets for`. Say what the chin
gun did at each step of the sequence: did it track, fire continuously, stop, and resume on a new target?
