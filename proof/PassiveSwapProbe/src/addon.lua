local hd2=require('mods/skyeshade/hd2runtime')
-- PassiveSwapProbe 0.1.0: THE ARMOR PASSIVE OVERRIDE LIVE TEST (hd2.passives, hd2.player_passives; docs/armor-passives.md;
-- research/player-attributes-F5FEE03DCFDB.json). Development only; SOLO; public API only, plus its logging.
-- Logs the local player's passives when it loads and at each mission start. F8 cycles the ARMOR passive override
--     VANILLA (no override: the kit's own) -> SERVO-ASSISTED -> ENGINEERING KIT -> SCOUT -> VANILLA
-- Ctrl+F8 adds / removes a SECOND passive (MED-KIT) in the empty helmet slot. Ctrl+Shift+F8 restores everything (the
-- kit's own passives). Shift+F8 logs the passives and the handle now (changes nothing). Each change logs the handle, the slots and the modifiers the game now reads, and what to observe.
-- The Runtime logs each re-application after an armor or helmet change ("passives (...): RE-APPLIED ...").
local mod=hd2.mod()
local BUILD='0.1.0 PASSIVE SWAP PROBE'
mod:log('PassiveSwapProbe '..BUILD..' BUILD: start a SOLO mission; F8 cycles the armor passive VANILLA -> SERVO-ASSISTED '
    ..'-> ENGINEERING KIT -> SCOUT; Ctrl+F8 adds / removes a second passive (MED-KIT); Ctrl+Shift+F8 restores the kit\'s '
    ..'own passives; Shift+F8 logs the passives now. Each change logs what to observe.')

local MODES={
    {name='VANILLA',observe='the kit\'s own passive: throw a grenade at a fixed mark and note its landing point; note '
        ..'your grenade and stim counts after a resupply'},
    {name='SERVO-ASSISTED',passive='SERVO-ASSISTED',observe='THROW RANGE x1.3: throw a grenade at the same angle as in '
        ..'VANILLA, it must land clearly farther; limb health x1.5 (harder to injure a limb)'},
    {name='ENGINEERING KIT',passive='ENGINEERING KIT',observe='+2 GRENADES: the grenade count may only grow at the next '
        ..'resupply or reinforcement (UNPROVEN: is the capacity read once?); recoil x0.7 when crouching or prone'},
    {name='SCOUT',passive='SCOUT',observe='ENEMY DETECTION x0.7: patrols notice you later; a map marker makes a radar scan '
        ..'every 2 s (place a marker on the map and watch the minimap)'},
}
local SECOND,SECOND_OBSERVE='MED-KIT','+2 STIMS at the next resupply or reinforcement (UNPROVEN timing) and stim '
    ..'duration +2 s; readers that ignore the helmet slot (flinch, Integrated Explosives, one chest-bleed site) never see it'
local state={mode=1,second=false}
local handle

local function g(v)return v and('%g'):format(v)or'?'end
local function passives_line(why)
    local mine,code,reason=hd2.player_passives()
    if not mine then
        mod:log(('PASSIVES (%s): unreadable: %s: %s'):format(why,tostring(code),tostring(reason)))
        return
    end
    local rows={}
    for _,m in ipairs(mine.effective)do
        rows[#rows+1]=('%s %s %s from %s %s'):format(m.key_name,m.type,g(m.value),m.source,m.name)
    end
    mod:log(('PASSIVES (%s): entity %s record %s; armor kit %s%s (its passive %s), helmet kit %s%s; ARMOR SLOT %s (%d), '
        ..'HELMET SLOT %s (%d); kit-derived armor %d, helmet %d; overridden %s%s; the game reads (flags 3): %s')
        :format(why,tostring(mine.entity),tostring(mine.record),mine.armor_kit.id,
        mine.armor_kit.name and(' '..mine.armor_kit.name)or'',tostring(mine.armor_kit.passive),mine.helmet_kit.id,
        mine.helmet_kit.name and(' '..mine.helmet_kit.name)or'',mine.armor_passive.name,mine.armor_passive.id,
        mine.helmet_passive.id==0 and'none'or mine.helmet_passive.name,mine.helmet_passive.id,mine.derived.armor,
        mine.derived.second,tostring(mine.overridden),mine.runtime and(' by '..mine.runtime)or'',
        #rows>0 and table.concat(rows,'; ')or'nothing'))
end

local function apply(why)
    local m=MODES[state.mode]
    if not m.passive and not state.second then
        if handle then handle:stop();handle=nil end
        mod:log(('MODE %s (%s): no override; OBSERVE: %s'):format(m.name,why,m.observe))
        passives_line('after '..why)
        return
    end
    handle=hd2.player_passives.set({armor=m.passive,second=state.second and SECOND or false,allow_unverified_effect=true})
    mod:log(('MODE %s%s (%s): handle %s%s'):format(m.name,state.second and(' + second '..SECOND)or'',why,
        tostring(handle.status),handle.code and(': '..handle.code..': '..tostring(handle.reason))or''))
    if handle.status=='refused'then handle=nil;return end
    mod:log('OBSERVE: '..m.observe..(state.second and('; SECOND '..SECOND..': '..SECOND_OBSERVE)or''))
    passives_line('after '..why)
end

local list=hd2.passives.list()
mod:log(('the game has %d armor passives; this probe uses %s, %s, %s and %s'):format(#list,MODES[2].passive,
    MODES[3].passive,MODES[4].passive,SECOND))
passives_line('loaded')
hd2.events.on('mission_started',function()passives_line('mission start')end)

hd2.input.bind('passive_swap_probe.cycle',{key='F8',on_press=function()
    state.mode=state.mode%#MODES+1
    apply('F8')
end})
hd2.input.bind('passive_swap_probe.second',{key='Ctrl+F8',on_press=function()
    state.second=not state.second
    apply('Ctrl+F8: second passive '..(state.second and'on'or'off'))
end})
hd2.input.bind('passive_swap_probe.status',{key='Shift+F8',on_press=function()
    local h=handle and handle:describe()
    mod:log(('STATUS (Shift+F8): mode %s%s; handle %s%s, written %d time(s)'):format(MODES[state.mode].name,
        state.second and(' + second '..SECOND)or'',h and tostring(h.status)or'none',
        h and h.code and(': '..h.code..': '..tostring(h.reason))or'',h and h.applications or 0))
    passives_line('Shift+F8')
end})
hd2.input.bind('passive_swap_probe.restore',{key='Ctrl+Shift+F8',on_press=function()
    state.mode,state.second=1,false
    if handle then handle:stop();handle=nil end
    mod:log('RESTORED (Ctrl+Shift+F8): the kit\'s own passives; OBSERVE: '..MODES[1].observe)
    passives_line('after Ctrl+Shift+F8')
end})
