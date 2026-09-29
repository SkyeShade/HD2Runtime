-- HD2-Addon: mods/nephelym/nephelym_s_weaponry_rebalance
local loader=rawget(_G,'CowboyBingusModLoader')
assert(loader and loader.api==1 and type(loader.version)=='number' and loader.version>=16,
    'Requires Bingus Shared Loader v15+ / API 1')
local runtime=require('mods/skyeshade/hd2runtime')
local function version(v)
    local a,b,c=tostring(v):match('^(%d+)%.(%d+)%.(%d+)$')
    assert(a,'Invalid HD2Runtime version');return tonumber(a),tonumber(b),tonumber(c)
end
local a,b,c=version(runtime.version)
local x,y,z=version('0.27.0')
assert(runtime.api_version==1 and (a>x or a==x and (b>y or b==y and c>=z)),
    'HD2Runtime dependency version mismatch')
local key='HD2RuntimeMod:mods/nephelym/nephelym_s_weaponry_rebalance'
local existing=rawget(_G,key)
if existing then return existing end
local function start()
local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    transaction={
        id='entity-2f5a386db841be55d3be8e66',
        target=hd2.support_weapon('M-1000 Maxigun'):backpack(),
        allow_unverified_effect=true,
        changes={
            {field=hd2.fields.deposit.capacity,expect=1000,value=1500},
            {field=hd2.fields.deposit.refill_amount,expect=500,value=750},
        },
    }
})

end
local state=start() or true
rawset(_G,key,state)
return state
