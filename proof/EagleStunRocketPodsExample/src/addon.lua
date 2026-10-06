local hd2=require('mods/skyeshade/hd2runtime')
-- EagleStunRocketPodsExample 0.3.1: Eagle Stun Rocket Pods on the custom stratagem API (docs/custom-stratagem-api.md,
-- "eagle"). A custom Eagle archetype: the call throws an offensive (red) beacon from an Eagle carrier; in its first
-- update its delivery becomes the vanilla Eagle 110mm Rocket Pods', so the game's own Eagle flies the rocket-pod run.
-- The Runtime identifies exactly that call's jet and makes each of its rockets explode on impact as the Orbital EMS
-- Strike's shell does: no damage, a strong stun and a 15 s static field (the rocket's direct hit stays). Its slot has 5
-- uses per rearm: the game's own Eagle rearm with a real Eagle in the loadout, else the Runtime's after the Eagle Rearm
-- time. A normal Eagle 110mm Rocket Pods in the same loadout stays exactly vanilla. 0.3.0: the call's rockets are the
-- ones fired by the two pods mounted on ITS jet and owned by that jet (live-proven with 0.3.0). The Runtime logs each
-- call's state transitions and a ROCKETS RESULT; hd2.custom_stratagem.verbose(true) adds the per-rocket trace.
-- Development API: solo host only.
local mod=hd2.mod()
local BUILD='0.3.1 DEV LINE BUILD'
mod:log('EagleStunRocketPodsExample '..BUILD..': select Eagle Stun Rocket Pods in the custom panel, then a SOLO mission; '
    ..'call it with UP LEFT UP RIGHT DOWN RIGHT.')

hd2.custom_stratagem.register({
    id='eagle_stun_rocket_pods',
    name='EAGLE STUN ROCKET PODS',
    name_cased='Eagle Stun Rocket Pods',
    description='An Eagle fires a rocket-pod run whose warheads burst into the Orbital EMS Strike\'s stun field on '
        ..'impact.',
    icon=hd2.resources.image('eagle_stun_rocket_pods'),
    code={'up','left','up','right','down','right'},
    -- An Eagle throws a red beacon: an unused Eagle carrier, and nothing else.
    carrier={beacon='offensive',prefer_families={'eagle'},allow_families={'eagle'}},
    eagle={
        donor='Eagle 110mm Rocket Pods',
        uses=5,
        payload={impact_explosion='Orbital EMS Strike'},
    },
})
