local hd2=require('mods/skyeshade/hd2runtime')
-- G-6 Frag: the explosion spawns its shrapnel from a count on the ExplosionSettings row, and the
-- starting count is the grenade's own ThrowableComponent. Separate native records, so a plan.
local frag=hd2.throwable('G-6 Frag')
return hd2.ensure({plan={id='frag-shrapnel',operations={
    -- The explosion row is a shared settings definition (allow_shared).
    {id='shrapnel',target=frag:explosion(),allow_shared=true,allow_unverified_effect=true,
        field=hd2.fields.explosion.shrapnel_count,expect=35,value=45},
    {id='starting',target=frag,allow_unverified_effect=true,
        field=hd2.fields.throwable.starting_count,expect=4,value=6},
}}})
