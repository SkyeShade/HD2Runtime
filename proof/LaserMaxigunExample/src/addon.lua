local hd2=require('mods/skyeshade/hd2runtime')
-- LaserMaxigunExample 0.1.1: the LAS-1000 LASER MAXIGUN, a mission-scoped VARIANT of the M-1000 Maxigun on its own type
-- (docs/custom-stratagem-api.md "weapon"; docs/custom-models.md; docs/research/weapon-variants-F5FEE03DCFDB.md).
-- The Maxigun is the only support weapon with its component set (spin-up, backpack-fed ammo, the ammo belt), so its own
-- type is its only carrier (the carrier group 'weapon'):
--   * its own stratagem row presents as the Laser Maxigun (name, icon, description) and answers to its code: you throw
--     its own blue beacon (a separate blue support carrier only when your account does not own the Maxigun);
--   * its own pod brings the Maxigun and its backpack, as always;
--   * for this mission its type fires the LAS-58 Talon's laser round (the same compatibility class) and shows the
--     custom name and icon; with Mod Options > Laser Maxigun > Model on "Debug model", its UnitPath is the mod's own
--     debug model (the Maxigun's mesh with a debug palette, shipped beside the vanilla model, never replacing it).
-- Everything is restored aboard the ship. While the Laser Maxigun is selected, the vanilla Maxigun is blocked in the
-- native picker; if anyone in the lobby brings the vanilla Maxigun, the Laser Maxigun is unavailable (no fallback).
local mod=hd2.mod()
local BUILD='0.1.1 LASER MAXIGUN CODE FIX BUILD'
mod:log('LaserMaxigunExample '..BUILD..': select LAS-1000 Laser Maxigun in the custom panel, choose the model in Mod '
    ..'Options (MODS > Laser Maxigun: "Check only" first, then "Debug model"), then a mission; call it with DOWN UP '
    ..'UP DOWN DOWN LEFT. It fires Talon laser rounds; nobody may bring the vanilla Maxigun.')

local options=hd2.options({id='laser_maxigun',title='Laser Maxigun'})
local model_use=options:choice({id='model_use',label='Model',choices={'Check only (vanilla model)','Debug model'},
    values={'check','apply'},default=1,
    description='At the next mission start: only check that the debug model is loaded (the Maxigun keeps its vanilla '
        ..'model), or show the debug model on the Laser Maxigun. Every player must choose the same.'})

hd2.custom_stratagem.register({
    id='laser_maxigun',
    name='LAS-1000 LASER MAXIGUN',
    name_cased='LAS-1000 Laser Maxigun',
    description='A Maxigun refitted to fire the LAS-58 Talon\'s laser bolts, fed from its backpack. Debug model build.',
    icon=hd2.resources.image('laser_maxigun'),
    code={'down','up','up','down','down','left'},
    -- The weapon group: the Maxigun's own stratagem is the beacon carrier, the variant and the pod.
    carrier={group='weapon'},
    delivery={family='weapon',weapon=hd2.support_weapon('M-1000 Maxigun'),round=hd2.attack_output('LAS-58 Talon'),
        model=hd2.resources.model('laser_maxigun'),model_use=model_use},
    -- What it uses this mission, in the log (read-only: hd2.custom_stratagem.describe).
    on_delivered=function(ctx)
        local d=hd2.custom_stratagem.describe('laser_maxigun')
        if not d then return end
        ctx:log(('USES: group %s; carrier %s (%s); carrier weapon %s; %d weapon(s) and %d item(s) captured'):format(
            tostring(d.group),d.carrier and d.carrier.name or'?',d.carrier and(d.carrier.condensed and
            'condensed: beacon, variant and pod in one'or('fallback beacon: '..tostring(d.carrier.fallback)))or'?',
            d.carrier_weapon and d.carrier_weapon.name or'?',#(ctx.weapons or{}),#(ctx.items or{})))
    end,
})
