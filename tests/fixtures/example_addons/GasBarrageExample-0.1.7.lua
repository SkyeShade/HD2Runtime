local hd2=require('mods/skyeshade/hd2runtime')
-- GasBarrageExample 0.1.7: Orbital Gas Barrage on the custom stratagem API (docs/custom-stratagem-api.md).
-- A barrage archetype as DATA (orbital = {pattern, impact_explosion, native = true}): the call's beacon delivery becomes
-- the Orbital 120mm HE Barrage's own, so the game itself fires the 120mm's native barrage over the beacon (5 salvos of
-- 3 shells, replicated to every player), and each of that barrage's shells explodes on impact as the Orbital Gas
-- Strike's shell does: its explosion and its 15 s gas cloud. Each shell's own impact copy is changed, on every
-- compatible Runtime's own copies (development, experimental with several players); nothing of the 120mm, the Gas
-- Strike or any shared row is written, and every other barrage stays vanilla.
local mod=hd2.mod()
local BUILD='0.1.7 NATIVE BARRAGE BUILD'
mod:log('GasBarrageExample '..BUILD..': select Orbital Gas Barrage in the custom panel, then a mission; call it '
    ..'with UP UP DOWN DOWN.')

hd2.custom_stratagem.register({
    id='orbital_gas_barrage',
    name='ORBITAL GAS BARRAGE',
    name_cased='Orbital Gas Barrage',
    description='Calls down a barrage of gas shells.',
    icon=hd2.resources.image('orbital_gas_barrage'),
    code={'up','up','down','down'},
    cooldown=60,
    carrier={beacon='offensive',prefer_families={'orbital'}},
    -- The 120mm's own barrage; each of its shells takes the Gas Strike's explosion (both packages become assets).
    orbital={pattern='Orbital 120mm HE Barrage',impact_explosion='Orbital Gas Strike',native=true},
})
