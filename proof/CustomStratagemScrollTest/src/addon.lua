-- The 0.40.1 panel scroll test: 24 custom stratagems (six rows of four), more than the 20 the panel shows at once.
-- Each is the Orbital Gas Barrage example under its own id, name and code (LEFT LEFT RIGHT RIGHT + three directions).
-- Needs the HD2Runtime 0.40.1 development build: 0.40.0 refuses the 17th custom stratagem.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
mod:log('CustomStratagemScrollTest 0.1.0 SCROLL BUILD: 24 custom stratagems; the panel shows 20 and scrolls the last row.')
local DIRECTIONS={'up','down','left','right'}
local icon=hd2.resources.image('orbital_gas_barrage')
for n=1,24 do
    local code,k={'left','left','right','right'},n-1
    for _=1,3 do code[#code+1]=DIRECTIONS[k%4+1];k=math.floor(k/4)end
    hd2.custom_stratagem.register({
        id=('scroll_test_%02d'):format(n),
        name=('SCROLL TEST %02d'):format(n),
        name_cased=('Scroll Test %02d'):format(n),
        description=('Card %d of 24: the Orbital Gas Barrage example. Cards 21 to 24 are on the sixth row, in view only '
            ..'after scrolling.'):format(n),
        icon=icon,
        code=code,
        cooldown=60,
        traits={'Orbital','Caustic'},
        carrier={beacon='offensive',prefer_families={'orbital'}},
        orbital={native=true,pattern='Orbital 120mm HE Barrage',impact_explosion='Orbital Gas Strike'},
    })
end
