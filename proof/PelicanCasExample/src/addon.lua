local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanCasExample 0.1.8: Pelican Close Air Support on the custom stratagem API (docs/custom-stratagem-api.md).
-- An autonomous spawned entity archetype as DATA (pelican = {hover, orbit, gun}): the call's beacon is neutralized (its
-- carrier delivers nothing) and, at its activation, an empty game Pelican flies to the beacon, holds over it 60 s,
-- orbits it and fights with its own chin gun (the frozen Pelican CAS configuration: the MG-206's AP4 round, 2x the
-- Gatling Sentry's rate, 100 mrad spread, no aim recoil, the 2047-round safe magazine; the Gatling Sentry's AI with the
-- Runtime target lock and body facing). With several players (development, experimental) the session host spawns it
-- for whoever called it, and every compatible Runtime mirrors the chin gun's private presentation on its own copy.
local mod=hd2.mod()
local BUILD='0.1.8 HOST PELICAN BUILD'
mod:log('PelicanCasExample '..BUILD..': select Pelican Close Air Support in the custom panel, then a mission; '
    ..'call it with LEFT DOWN LEFT UP LEFT UP.')

hd2.custom_stratagem.register({
    id='pelican_close_air_support',
    name='PELICAN CLOSE AIR SUPPORT',
    name_cased='Pelican Close Air Support',
    description='Calls in a Pelican that flies to the beacon, holds over it for 60 seconds and fights with its chin gun.',
    icon=hd2.resources.image('pelican_close_air_support'),
    code={'left','down','left','up','left','up'},
    cooldown=60,
    -- An offensive stratagem throws a red beacon: an orbital carrier first, then any other red one.
    carrier={beacon='offensive',prefer_families={'orbital'}},
    -- The Pelican: it holds over the beacon 60 s and orbits it; its chin gun's packages (the Gatling Sentry's, the
    -- MG-206's) become assets.
    pelican={hover=60,orbit={radius=40,altitude=60,duration=55},
        gun={behave_as='gatling_sentry',rate_multiplier=2,round='ap4',spread=100,recoil=false,unlimited_ammo=true,
            face_target=true}},
})
