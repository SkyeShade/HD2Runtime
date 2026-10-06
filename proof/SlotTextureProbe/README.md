# SlotTextureProbe 0.1.0 (development only, READ ONLY): the native slot icon's texture chain

**Nothing is written.** This probe only reads.

## Why a probe

The texture a native loadout slot icon draws with is not held in any main-thread field
(`docs/custom-stratagems.md`, "A custom texture in a native slot").
- The game binds it with a native call. That call queues a render command, and the render thread stores the texture's
  render handle in the render-side copy of the slot's material.
- Every draw reads it from there.

Showing a custom image in one slot by data would mean writing into that render-thread memory while the render thread
reads it. Before that is even considered, this probe checks the whole read chain in the live game.

## What it reads

For each of the four slots, F9 resolves:
- the icon element's own material instance and its render handle;
- the render world (checked by its type and its link back to the material's world);
- the render-side material object (checked by its type, kind, shader and template);
- the image property's index and the texture handle the slot draws with.

It also logs, for comparison:
- the handle of the atlas page the slot's sprite is on (it should equal the slot's handle);
- the handle of this proof's own custom texture `orbital_gas_barrage_masks`. It is loaded only to be compared, never
  shown.

**Which build is running:**
- the first log line is `SlotTextureProbe 0.1.0 READ ONLY BUILD: ...`;
- F9 prints `F9 [0.1.0 READ ONLY]`.

## Live test

Install the HD2Runtime runtime ZIP and `SlotTextureProbe-0.1.0.zip` only. Solo, aboard the ship, no mission.

1. Put a few stratagems in the loadout. Two different stratagems are enough.
2. Open the loadout screen and press **F9**.
3. Change a slot natively, then press F9 again.

Send every `[HD2Runtime] slot texture probe` line. Each slot line ends with `valid; ... texture handle ...` or
`NOT resolved: <reason>`.
