# HeavyDevastatorDelayedExplosionTest

Acceptance test for hand-written gameplay logic (`docs/event-scripting.md`): **when a Heavy Devastator dies, wait
3 seconds, then request an R-36 Eruptor explosion where it died.**

```lua
hd2.events.on('entity_died', function(event)
    if not TARGETS[event.semantic_id] then return end      -- the heavy machine gun Devastator classes
    local position = event.position                        -- read-only snapshot, valid after the enemy is gone
    hd2.after(3, function()
        hd2.explosions.spawn('R-36 Eruptor', {position = position})
    end, {scope = 'mission'})
end)
```

It proves: enemy identity from the event snapshot (the semantic id), deaths the game replaced by a corpse before
Runtime polled (`observed=corpse`), a death position that survives the enemy's destruction, a timer owned by the mod
without passing its id, and a gameplay action from arbitrary Lua (the game's own explosion request).

## Identity (read this before testing)

The enemy catalog proves no native class for the name "Heavy Devastator" (its anatomy matches no class one to one),
so the test targets the heavy machine gun Devastator classes by resource path: `enemy/v1/automatons/soldier_mg`,
`soldier_mg_ivory_legion` and `soldier_mg_assassinate` (`cha_soldier_mg`). Every other automaton class that dies is
logged once per mission with its id, so your kill tells us whether the mapping is right. The Devastator's shield is a
separate entity (`enemy/v1/automatons/soldier_shield`); destroying it is not the Devastator's death.

## How to test

Host a mission against the automatons (solo is simplest). Kill a Heavy Devastator, and some other automatons. Stay
more than 7 m from where it died (the explosion hurts you too).

Expected `HD2Runtime.log` lines (prefix `[mods/hd2runtime_examples/heavy_devastator_delayed_explosion_test]`):

```
mission started: R-36 Eruptor explosion assets ready            (or: waiting_for_assets)
automaton died: enemy/v1/automatons/<class> (<name>), not a target   (once per other class)
Heavy Devastator died at (x, y, z) (enemy/v1/automatons/soldier_mg, observed=corpse|dead_state, corpse=<id|nil>)
scheduled explosion in 3 s
timer fired at saved position (x, y, z) (the entity is still valid: false)
explosion requested: R-36 Eruptor at (x, y, z)
[HD2Runtime] explosion R-36 Eruptor requested at (x, y, z) by mods/hd2runtime_examples/heavy_devastator_delayed_explosion_test
```

In game: 3 seconds after the Heavy Devastator dies, an explosion like an Eruptor shell's impact goes off where it
died, and enemies near that spot take damage. If it refuses instead, the log says exactly why:
`explosion blocked: <CODE>: <reason>` (as a client: `HOST_ONLY`).

Report:

1. the `Heavy Devastator died` line, or, if no such line appears after killing one, the `automaton died:` id logged
   for it (that is the id the test should target);
2. the `observed=` value;
3. whether the explosion was visible and at the right place, and whether it damaged enemies;
4. if you have a second player: whether they saw the explosion.
