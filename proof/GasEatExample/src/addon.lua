local hd2=require('mods/skyeshade/hd2runtime')
-- GasEatExample 0.1.7: the EAT-17G Gas Expendable Anti-Tank on the custom stratagem API (docs/custom-stratagem-api.md).
-- A custom support weapon archetype: the call throws a support (blue) beacon; in its first update its delivery becomes
-- the vanilla EAT-17's, so the game's own hellpod brings the EAT-17's own rack with two launchers. The Runtime reads
-- exactly those two launchers from the pod's rack, and each one's rocket explodes on impact as the Orbital Gas Strike's
-- shell does: the Gas Strike's explosion and its 15 s gas cloud. Only those two launchers change (each rocket's own
-- impact copy, written while it flies); every other EAT-17, its definition and its projectile stay vanilla.
-- The gas is DATA (delivery.items[].modify.impact_explosion), not a callback: with several players every compatible
-- Runtime derives it from this same registered definition and converts its own copy of those launchers' rockets,
-- whoever fires them (development, experimental).
local mod=hd2.mod()
local BUILD='0.1.7 MULTIPLAYER PROVENANCE BUILD'
mod:log('GasEatExample '..BUILD..': select EAT-17G Gas Expendable Anti-Tank in the custom panel, then a mission; '
    ..'call it with DOWN DOWN RIGHT UP RIGHT, pick up a launcher from the pod and fire it.')

local GAS='Orbital Gas Strike'

hd2.custom_stratagem.register({
    id='eat17_gas',
    name='EAT-17G GAS EXPENDABLE ANTI-TANK',
    name_cased='EAT-17G Gas Expendable Anti-Tank',
    description='Drops two expendable launchers whose rockets burst into the Orbital Gas Strike\'s gas cloud on impact.',
    icon=hd2.resources.image('eat17_gas'),
    code={'down','down','right','up','right'},
    cooldown=70,
    -- A support weapon throws a blue beacon: an unused support weapon carrier first, then a backpack; nothing else.
    carrier={beacon='support',prefer_families={'support','backpack'}},
    -- The EAT-17's own pod and rack; each delivered launcher's rocket takes the Gas Strike's explosion (its package
    -- becomes an asset, resident before a rocket can take it).
    delivery={family='support',items={{donor='EAT-17 Expendable Anti-Tank',modify={impact_explosion=GAS}}}},
})
