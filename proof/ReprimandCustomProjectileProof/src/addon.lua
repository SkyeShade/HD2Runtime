local hd2=require('mods/skyeshade/hd2runtime')
-- Development proof: the SMG-32 Reprimand fires the slow custom projectile dev/talon_combined (CustomProjectileRowProof's
-- F11 projectile) through weapon projectile replacement (docs/custom-projectile-rows.md#weapon-projectile-replacement).
-- NOT a public API: it calls Runtime internals (runtime/custom_projectiles.lua, runtime/projectile_replacement.lua,
-- api/actions.lua) that may change without notice. Host only, in a mission.
--
-- 1. The Reprimand is swapped to fire a carrier: the TD-110 Maelstrom's slot 2 projectile (type 324), which has no
--    particle effect, no unit, damage type 0 (the game's all-zero DamageInfo) and no explosion. This is the ordinary
--    guarded projectile swap; the game copies it into a Reprimand when it builds one.
-- 2. At each mission start dev/talon_combined is defined and bound to the carrier. Every update Runtime reads which
--    projectiles the game spawned; for each carrier your Reprimand fired it spawns dev/talon_combined from the
--    carrier's spawn point along its direction: the game's own aim, spread and fire rate, one frame later.
--
--   F12  replacement on / off (off: the Reprimand fires the invisible, harmless carrier alone)
--   F9   log the replacement counts
--
-- What to check is listed in docs/custom-projectile-rows.md#live-test-weapon-projectile-replacement.
local ok_custom,custom=pcall(require,'hd2runtime/runtime/custom_projectiles')
local ok_replacement,replacement=pcall(require,'hd2runtime/runtime/projectile_replacement')
assert(ok_custom and ok_replacement,'ReprimandCustomProjectileProof needs an HD2Runtime development build with weapon '
    ..'projectile replacement')
local actions=require('hd2runtime/api/actions')
local mod=hd2.mod()
local WEAPON='SMG-32 Reprimand'
local CARRIER='output/v1/projectile/td-110-maelstrom-slot-2'
local DEFINITION='dev/talon_combined'

local spec
for _,item in ipairs(custom.DEVELOPMENT_VARIANTS)do if item.id==DEFINITION then spec=item end end
assert(spec,DEFINITION..' is not a development variant of this Runtime build')
local source=hd2.weapon(WEAPON):projectile_source()
assert(source.writable,WEAPON..' is no longer a projectile host')

local enabled=true
local function bind(reason)
    local definition,code,why=custom.define(spec)
    if not definition then
        mod:log(reason..': '..DEFINITION..' not defined: '..tostring(code)..': '..tostring(why))
        return
    end
    local action=actions.replace_projectiles(definition,{carrier=CARRIER,weapon=WEAPON})
    mod:log(('%s: %s carrier shots -> %s: %s%s'):format(reason,WEAPON,DEFINITION,action.status,
        action.code and(' '..action.code..': '..tostring(action.reason))or''))
end
hd2.events.on('mission_started',function()
    if enabled then bind('mission started')end
end,{id='reprimand-replacement-mission'})
hd2.input.bind('reprimand_custom_projectile_proof.toggle',{key='F12',on_press=function()
    enabled=not enabled
    if enabled then
        bind('F12')
    else
        actions.stop_replacing_projectiles(CARRIER)
        mod:log('F12: replacement off; the Reprimand now fires the invisible carrier alone')
    end
end})
hd2.input.bind('reprimand_custom_projectile_proof.status',{key='F9',on_press=function()
    local bindings=replacement.list()
    if #bindings==0 then mod:log('F9: no replacement bound ('..(enabled and'waiting for a mission'or'off')..')')end
    for _,item in ipairs(bindings)do
        mod:log(('F9: %s (type %d) -> %s: %d replaced, %d dropped (rate), %d refused, %d not yours, %d other weapons')
            :format(item.carrier_name,item.carrier,item.definition,item.replaced,item.dropped,item.refused,
            item.foreign,item.other_weapons))
    end
end})

mod:log('loaded: the '..WEAPON..' fires '..DEFINITION..' (host, in a mission); F12 replacement on / off, F9 counts. '
    ..'Take a freshly built Reprimand (loadout or call-in) so the carrier swap is in it.')
return hd2.ensure({transaction={id='reprimand-carrier',target=source.target,
    changes={{field=source.field,expect=source.expect,value=hd2.attack_output(CARRIER)}}}})
