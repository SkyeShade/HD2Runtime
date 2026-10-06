local hd2=require('mods/skyeshade/hd2runtime')
-- HmgSentryExample 0.2.1: the A/HMG-206 Heavy Machine Gun Sentry on the custom stratagem API
-- (docs/custom-stratagem-api.md, "sentry"). A custom sentry archetype: the call throws a support (blue) beacon from a
-- sentry carrier; in its first update its delivery becomes the vanilla A/MG-43 Machine Gun Sentry's, so the game's own
-- hellpod deploys an MG-43 Machine Gun Sentry chassis (its model, AI and targeting). The Runtime reads exactly that
-- pod's sentry and configures ITS OWN weapon records only: the MG-206 Heavy Machine Gun's armor-piercing round (275),
-- 400 rounds a minute, the MG-206's own tight 5 mrad spread and a 300-round magazine. Every normal MG-43 Machine Gun
-- Sentry and A/G-16 Gatling Sentry in the same mission stays exactly vanilla, and so does the MG-206. Its kills credit
-- the player who called it, as a native sentry's do. Development API: solo host only.
local mod=hd2.mod()
local BUILD='0.2.1 DEV LINE BUILD'
mod:log('HmgSentryExample '..BUILD..': select A/HMG-206 Heavy Machine Gun Sentry in the custom panel, then a SOLO '
    ..'mission; call it with DOWN UP LEFT LEFT DOWN UP.')

hd2.custom_stratagem.register({
    id='hmg_sentry',
    name='A/HMG-206 HEAVY MACHINE GUN SENTRY',
    name_cased='A/HMG-206 Heavy Machine Gun Sentry',
    description='Deploys a machine gun sentry that fires the MG-206 heavy machine gun\'s armor-piercing rounds at a '
        ..'deliberate 400 rounds per minute.',
    icon=hd2.resources.image('hmg_sentry'),
    code={'down','up','left','left','down','up'},
    cooldown=150,
    -- A sentry throws a blue beacon: an unused sentry carrier, and nothing else.
    carrier={beacon='support',prefer_families={'sentry'},allow_families={'sentry'}},
    sentry={
        donor='A/MG-43 Machine Gun Sentry',
        weapon={projectile=hd2.support_weapon('MG-206 Heavy Machine Gun'),rpm=400,spread=5,ammo=300},
    },
})
