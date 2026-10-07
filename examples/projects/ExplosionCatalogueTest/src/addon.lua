-- The explosion catalogue (docs/explosions.md). Not live-tested: every write below carries the acknowledgements the
-- catalogue asks for. The log starts with EXPLOSION CATALOGUE 0.1.0 BUILD.
--   * edit: the Orbital 120mm HE Barrage's shell explosion, inner radius 3.3 -> 5 m and outer radius 10 -> 14 m
--     (hd2.explosion(name), a catalogued explosion as a target; its own row, not shared);
--   * payload: the R-36 Eruptor's impact explosion becomes the PLAS-15 Loyalist's (a catalogued explosion as a
--     terminal.explosion donor; its effect ships in the mission effects package, resident in every mission);
--   * spawn: with a mission running, every enemy death the local player causes requests the Orbital Gas Strike's shell
--     explosion where the enemy died (host only; its call-in package is loaded at mission start).
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('EXPLOSION CATALOGUE 0.1.0 BUILD: barrage shell edit, Eruptor payload, gas strike on kills')

local barrage=hd2.explosion('stratagem/orbital_120mm_he_barrage/shell_impact')
local wider=hd2.ensure({transaction={id='barrage-shell-wider',target=barrage,allow_unverified_effect=true,changes={
    {field=hd2.fields.explosion.inner_radius,expect=3.3,value=5},
    {field=hd2.fields.explosion.outer_radius,expect=10,value=14}}}})

local eruptor=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile():terminal_action('impact')
local payload=hd2.ensure({patch={id='eruptor-loyalist-impact',target=eruptor,field=hd2.fields.terminal.explosion,
    expect=eruptor:explosion(),value=hd2.explosion('weapon/plas15_loyalist/impact'),
    allow_unverified_reference=true,allow_unverified_effect=true}})

local GAS='stratagem/orbital_gas_strike/shell_impact'
hd2.events.on('mission_started',function()hd2.explosions.prepare(GAS,{allow_unverified_effect=true})end)
hd2.events.on('entity_died',function(event)
    if event.local_killer and event.position then
        hd2.explosions.spawn(GAS,{position=event.position,allow_unverified_effect=true})
    end
end)
return {wider,payload}
