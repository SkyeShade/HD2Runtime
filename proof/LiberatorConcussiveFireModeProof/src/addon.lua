local hd2=require('mods/skyeshade/hd2runtime')
-- Development proof: a weapon with two selectable projectile modes, three fire rates and a 50-round magazine. NOT a
-- public API: it calls Runtime internals (runtime/custom_projectiles.lua, runtime/projectile_replacement.lua,
-- api/actions.lua) that may change without notice. Host only, in a mission. Only one fire-mode proof (and not
-- ReprimandCustomProjectileProof) may be installed at a time: they all use the same carrier.
--
-- Modes (the game's own ProgrammableAmmo weapon function, on the weapon's free left input; weapon:feeds()):
--   Normal  the weapon's own projectile (ProjectileWeapon +0): never replaced
--   Custom  the function projectile (ProjectileWeapon +576), set to the harmless carrier (type 324); Runtime replaces
--           each of those shots with dev/talon_combined (docs/custom-projectile-rows.md#weapon-projectile-replacement)
-- The right input keeps the native fire-mode selector, which never selects projectiles.
--
-- Fire rate (Mod Options, applied when the game builds the weapon): weapon.fire_rate, the default rate slot in rounds
-- per minute. An in-game rate selector would need the same left input as the mode selector (see the README).
-- Magazine: 50 rounds, through whatever owns the effective capacity (CONFIG.magazine). Reserve ammunition is unchanged.
--
--   F12  custom replacement on / off (off: Custom mode fires the invisible, harmless carrier alone)
--   F9   counts, the mode of the last shot, the last burst's cadence and the configured rate
--
-- Everything weapon-specific is in CONFIG: ReprimandFireModeProof and LiberatorConcussiveFireModeProof share the
-- rest of this file exactly (tests/test_custom_projectiles.py checks it).
local CONFIG={
    name='LiberatorConcussiveFireModeProof',
    weapon='AR-23C Liberator Concussive',short='Liberator Concussive',
    native='output/v1/projectile/ar-23c-liberator-concussive',      -- the Normal mode: the weapon's own projectile
    -- rpm: the Concussive's own, the AR-23 Liberator's own, and the test rate.
    rates={400,640,1500},rate_choices={'400 RPM (native)','640 RPM','1500 RPM'},
    -- magazine.capacity is not writable on the Concussive: its default magazine attachment (Rifle 5,5x50mm. Drum,
    -- 60 rounds) owns the effective capacity.
    magazine={value=50,owner='attachment'},
    -- The Concussive round is also fired by two other entities (one is assault_rifle_exp): its STANDARD label shows
    -- wherever they list it in a mode menu.
    labels_allow_shared=true,
    id='concussive',options={id='liberator_concussive_firemode_proof',title='Liberator Concussive Fire-Mode Proof'},
}

local ok_custom,custom=pcall(require,'hd2runtime/runtime/custom_projectiles')
local ok_replacement,replacement=pcall(require,'hd2runtime/runtime/projectile_replacement')
assert(ok_custom and ok_replacement,CONFIG.name..' needs an HD2Runtime development build with weapon projectile '
    ..'replacement')
local actions=require('hd2runtime/api/actions')
local mod=hd2.mod()
local WEAPON,NATIVE,RATES,CAPACITY=CONFIG.weapon,CONFIG.native,CONFIG.rates,CONFIG.magazine.value
local CARRIER='output/v1/projectile/td-110-maelstrom-slot-2'
local DEFINITION='dev/talon_combined'

local spec
for _,item in ipairs(custom.DEVELOPMENT_VARIANTS)do if item.id==DEFINITION then spec=item end end
assert(spec,DEFINITION..' is not a development variant of this Runtime build')
local weapon=hd2.weapon(WEAPON)
local programmable=weapon:feed('programmable'):source()
assert(programmable.writable and programmable.binding,WEAPON..' can no longer gain a programmable-ammunition mode')
local rates=weapon:fire_rate_modes()
local function field(fields,id)
    for _,item in pairs(fields)do if item.semanticFieldId==id then return item end end
end
local right=field(weapon:describe().fields,'weapon_function.right')
local carrier=hd2.attack_output(CARRIER)
-- The two modes' projectile types, from the attack output catalog.
local NATIVE_TYPE,CARRIER_TYPE=assert(custom.output(NATIVE,false)).type,assert(custom.output(CARRIER,false)).type

local options=hd2.options(CONFIG.options)
local rate=options:choice({id='fire_rate',label=CONFIG.short..' fire rate',choices=CONFIG.rate_choices,values=RATES,
    default=3,description='weapon.fire_rate; applies to a freshly built '..CONFIG.short})
-- An option's current value (a handle in game; tools that validate the mod may pass the value itself).
local function current(value)return type(value)=='table'and value.get and value:get()or value end
local labels=options:toggle({id='mode_labels',label='Mode labels STANDARD / HE',default=true,
    description='The two modes\' menu labels and icons (the plain round and the HE icon)'})

local requests={}
-- 1. The modes: the ProgrammableAmmo selector on the left input, its projectile the carrier.
for _,request in ipairs(weapon:programmable_ammo():operations({id=CONFIG.id..'-custom-mode',base=carrier,
        allow_unverified_effect=true,allow_unverified_reference=true}))do
    requests[#requests+1]=request
end
-- 2. Their menu labels (the projectile rows' own label and icon members): Normal STANDARD, Custom HE. A row other
-- entities fire too shows the label there as well, which CONFIG acknowledges explicitly.
for _,request in ipairs(weapon:programmable_ammo():presentation({id=CONFIG.id..'-mode-labels',base=carrier,
        label='he',primary_label='standard',enabled=labels,allow_unverified_effect=true,
        allow_shared=CONFIG.labels_allow_shared}))do
    requests[#requests+1]=request
end
-- 3. The fire rate.
requests[#requests+1]={patch={id=CONFIG.id..'-fire-rate',target=weapon,field=hd2.fields.weapon.fire_rate,
    expect=rates.default.rpm,value=rate}}
-- 4. The magazine: the weapon's own capacity, or the capacity of the magazine attachment it is built with (a shared
-- definition: every weapon that equips it changes, so it needs allow_shared, and has its own toggle).
local magazine
if CONFIG.magazine.owner=='weapon'then
    local capacity=field(weapon:describe().fields,'magazine.capacity')
    magazine={from=capacity.currentDefault,what='magazine.capacity (WeaponMagazine +136)'}
    requests[#requests+1]={patch={id=CONFIG.id..'-magazine',target=weapon,field=hd2.fields.magazine.capacity,
        expect=capacity.currentDefault,value=CAPACITY}}
else
    local attachment=weapon:magazine_attachment()
    local view=attachment:describe()
    local capacity=field(view.fields,'attachment.magazine_capacity')
    magazine={from=capacity.currentDefault,what='attachment.magazine_capacity ('..view.name..', the default '
        ..'magazine; shared: every weapon that equips it)'}
    local shared=options:toggle({id='magazine',label=view.name..' '..CAPACITY..' rounds (shared)',default=true,
        description='attachment.magazine_capacity '..capacity.currentDefault..' -> '..CAPACITY..'; every weapon that '
            ..'equips this magazine changes'})
    requests[#requests+1]={enabled=shared,patch={id=CONFIG.id..'-magazine',target=attachment,
        field=hd2.fields.attachment.magazine_capacity,expect=capacity.currentDefault,value=CAPACITY,
        allow_shared=true,allow_unverified_effect=true}}
end

local enabled=true
local function bind(reason)
    local definition,code,why=custom.define(spec)
    if not definition then
        mod:log(reason..': '..DEFINITION..' not defined: '..tostring(code)..': '..tostring(why))
        return
    end
    local existing=replacement.describe(CARRIER_TYPE)
    if existing and existing.owner~=mod.id then
        mod:log('warning: '..tostring(existing.owner)..' also binds the carrier; install one fire-mode proof at a time '
            ..'and uninstall ReprimandCustomProjectileProof')
    end
    local action=actions.replace_projectiles(definition,{carrier=CARRIER,weapon=WEAPON,unreplaced=NATIVE,
        detail_logs=math.huge})
    mod:log(('%s: custom replacement binding: Custom mode carrier %s -> %s; Normal mode %s -> no replacement: %s%s')
        :format(reason,CARRIER,DEFINITION,NATIVE,action.status,action.code and(' '..action.code..': '
        ..tostring(action.reason))or''))
end
hd2.events.on('mission_started',function()
    if enabled then bind('mission started')end
end,{id=CONFIG.id..'-firemode-mission'})
hd2.input.bind(CONFIG.options.id..'.toggle',{key='F12',on_press=function()
    enabled=not enabled
    if enabled then
        bind('F12')
    else
        actions.stop_replacing_projectiles(CARRIER)
        mod:log('F12: custom replacement off; Custom mode now fires the invisible carrier alone, Normal mode is unchanged')
    end
end})
hd2.input.bind(CONFIG.options.id..'.status',{key='F9',on_press=function()
    local item=replacement.describe(CARRIER_TYPE)
    local configured=('configured: fire rate %s rpm (Mod Options), magazine %d'):format(tostring(current(rate)),CAPACITY)
    if not item then
        mod:log('F9: no custom replacement bound ('..(enabled and'waiting for a mission'or'off')..'); '..configured)
        return
    end
    local burst=item.last_burst
    mod:log(('F9: Custom mode: %d replaced, %d dropped (rate), %d refused, %d not yours; Normal mode: %d not '
        ..'replaced; last shot mode: %s; last burst: %s; %s'):format(item.replaced,item.dropped,item.refused,
        item.foreign,item.normal,item.last_mode=='custom'and'Custom (carrier)'or item.last_mode=='normal'
        and'Normal (native projectile)'or'none yet',burst and(('%d shots (%d custom, %d normal) over %.2f s%s')
        :format(burst.shots,burst.custom,burst.normal,burst.seconds,burst.rpm and(' = %.0f rpm'):format(burst.rpm)
        or''))or'none yet',configured))
end})

-- Startup diagnostics: what the ensures below configure, from the catalog the requests were built with.
local seconds=60/1500
mod:log(('fire modes: weapon_function.left %s -> programmable_ammo (Normal / Custom selector); '
    ..'weapon_function.right %s unchanged (Automatic / Single / Burst)'):format(programmable.binding.expect,
    tostring(right and right.currentDefault)))
mod:log(('mode Normal: %s (type %d, ProjectileWeapon +0), never replaced; mode Custom: function_ammo.projectile '
    ..'(ProjectileWeapon +576) %s -> carrier %s (type %d) -> %s'):format(NATIVE,NATIVE_TYPE,programmable.expect,
    CARRIER,CARRIER_TYPE,DEFINITION))
mod:log(('fire rate: weapon.fire_rate (ProjectileWeapon +8, rpm) %d -> %s (choices %d / %d / %d; 1500 rpm = %.0f '
    ..'shots/s, one every %.0f ms, %d rounds in %.2f s)'):format(rates.default.rpm,tostring(current(rate)),RATES[1],
    RATES[2],RATES[3],1/seconds,seconds*1000,CAPACITY,(CAPACITY-1)*seconds))
mod:log(('magazine: %s %d -> %d; reserve unchanged'):format(magazine.what,magazine.from,CAPACITY))
mod:log('loaded: take a freshly built '..CONFIG.short..' (loadout or call-in) after APPLY; switch Normal / Custom '
    ..'with the weapon-function menu; F12 replacement on / off, F9 status')

local handles={}
for _,request in ipairs(requests)do handles[#handles+1]=hd2.ensure(request)end
return handles
