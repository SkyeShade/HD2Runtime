-- HD2-Addon: mods/skyeshade/hd2runtime_shield_relay
local key='HD2RuntimeShieldRelayProofV1'
local existing=rawget(_G,key)
if existing then return existing end
local hd2=require('mods/skyeshade/hd2runtime')
local state=hd2.ensure({
    transaction={
        id='shield-relay-proof',
        target=hd2.stratagem('Shield Relay'),
        changes={
            {field='radius',expect=15,value=8},
            {field='durability',expect=4000,value=40000},
            {field='lifetime',expect=40,value=90},
            {field='cooldown',expect=90,value=180},
        },
    },
})
rawset(_G,key,state)
return state
