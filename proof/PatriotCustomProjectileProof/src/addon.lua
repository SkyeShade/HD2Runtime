local hd2=require('mods/skyeshade/hd2runtime')
-- Development proof: the EXO-45 Patriot Exosuit's primary weapon (its right_gun minigun) fires dev/talon_combined
-- through weapon projectile replacement (docs/custom-projectile-rows.md#weapon-projectile-replacement). NOT a public
-- API: it calls Runtime internals (runtime/custom_projectiles.lua, runtime/projectile_replacement.lua, api/actions.lua)
-- that may change without notice. Host only, in a mission. Install no other carrier proof alongside it.
--
-- 1. Suppression: the minigun's projectile (its ProjectileWeapon +0, the member the live-proven Patriot swaps write) is
--    swapped to the harmless carrier (type 324). Every minigun shot is then a carrier; its native bullet (type 148)
--    is never spawned. Runtime still watches for type 148 from the minigun: a sighting is logged as a suppression
--    failure.
-- 2. Replacement: every update Runtime reads the projectiles spawned since its last look; each carrier whose source is
--    the minigun (its catalogued entity type) is replaced by exactly one dev/talon_combined, and the next update
--    confirms that projectile in the pool.
--
--   F12  replacement on / off (off: the minigun fires the invisible, harmless carrier alone)
--   F9   counts: carriers, replaced, confirmed in the pool, dropped, refused, native bullets seen, latency, last burst
local ok_custom,custom=pcall(require,'hd2runtime/runtime/custom_projectiles')
local ok_replacement,replacement=pcall(require,'hd2runtime/runtime/projectile_replacement')
assert(ok_custom and ok_replacement,'PatriotCustomProjectileProof needs an HD2Runtime development build with weapon '
    ..'projectile replacement')
local actions=require('hd2runtime/api/actions')
local mod=hd2.mod()
local VEHICLE,WEAPON='EXO-45 Patriot Exosuit','right_gun'
local HOST='output/v1/projectile/exo-45-patriot-exosuit-right-gun'
local CARRIER='output/v1/projectile/td-110-maelstrom-slot-2'
local DEFINITION='dev/talon_combined'
-- Every shot of the first DETAIL shots is logged in full (with creditor, owner, source and latency); then a summary
-- per burst and every 10 seconds. The minigun fires 1200 rounds per minute.
local DETAIL=100

local spec
for _,item in ipairs(custom.DEVELOPMENT_VARIANTS)do if item.id==DEFINITION then spec=item end end
assert(spec,DEFINITION..' is not a development variant of this Runtime build')
local gun=hd2.vehicle(VEHICLE):weapon(WEAPON)
local source=gun:projectile_source()
assert(source.writable,'the Patriot minigun is no longer a projectile host: '..tostring(source.reason))
local host=assert(custom.output(HOST,false))
local carrier=assert(custom.output(CARRIER,false))

local enabled=true
local function bind(reason)
    local definition,code,why=custom.define(spec)
    if not definition then
        mod:log(reason..': '..DEFINITION..' not defined: '..tostring(code)..': '..tostring(why))
        return
    end
    local existing=replacement.describe(carrier.type)
    if existing and existing.owner~=mod.id then
        mod:log('warning: '..tostring(existing.owner)..' also binds the carrier; install one carrier proof at a time')
    end
    local action=actions.replace_projectiles(definition,{carrier=CARRIER,source=HOST,suppressed=HOST,
        credit='local_or_none',attribute=true,detail_logs=DETAIL})
    mod:log(('%s: replacement binding: carrier %s (type %d) from %s -> %s; native %s (type %d) suppressed: %s%s')
        :format(reason,CARRIER,carrier.type,host.weapon,DEFINITION,HOST,host.type,action.status,action.code and(' '
        ..action.code..': '..tostring(action.reason))or''))
end
hd2.events.on('mission_started',function()
    if enabled then bind('mission started')end
end,{id='patriot-replacement-mission'})
hd2.input.bind('patriot_custom_projectile_proof.toggle',{key='F12',on_press=function()
    enabled=not enabled
    if enabled then
        bind('F12')
    else
        actions.stop_replacing_projectiles(CARRIER)
        mod:log('F12: replacement off; the minigun now fires the invisible carrier alone')
    end
end})
hd2.input.bind('patriot_custom_projectile_proof.status',{key='F9',on_press=function()
    local item=replacement.describe(carrier.type)
    if not item then
        mod:log('F9: no replacement bound ('..(enabled and'waiting for a mission'or'off')..')')
        return
    end
    local l,burst=item.latency,item.last_burst
    mod:log(('F9: %d carriers -> %d replaced (%d confirmed in the pool, %d not), %d dropped (rate), %d refused, %d not '
        ..'the local player\'s, %d other sources; native bullets seen: %d (suppression %s); latency one game update: '
        ..'%s; last burst: %s'):format(item.carriers,item.replaced,item.confirmed,item.unconfirmed,item.dropped,
        item.refused,item.foreign,item.other_weapons,item.normal,item.normal==0 and'held'or'FAILED',l.count>0 and(
        ('mean %.1f ms, max %.1f ms, carrier flight before the read max %.1f ms'):format(l.mean*1000,l.max*1000,
        l.flight*1000))or'none yet',burst and(('%d shots over %.2f s%s'):format(burst.shots,burst.seconds,burst.rpm
        and(' = %.0f rpm'):format(burst.rpm)or''))or'none yet'))
end})

mod:log(('host: %s / %s, output %s, native projectile type %d, source identity entity type %s; swap: %s %s -> '
    ..'carrier %s (type %d); replacement: %s'):format(VEHICLE,WEAPON,HOST,host.type,host.catalog.resource,
    source.field,tostring(host.type),CARRIER,carrier.type,DEFINITION))
mod:log('loaded: call in a fresh Patriot after APPLY (the projectile is copied in when the game builds it); '
    ..'F12 replacement on / off, F9 counts')
-- The carrier is not one of the Patriot swap's live-proven donors (EAT-17, Talon, Scorcher): acknowledged here.
return hd2.ensure({transaction={id='patriot-carrier',target=source.target,allow_unverified_effect=true,
    changes={{field=source.field,expect=source.expect,value=hd2.attack_output(CARRIER)}}}})
