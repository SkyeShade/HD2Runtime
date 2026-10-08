local hd2=require('mods/skyeshade/hd2runtime')
-- PassiveSwapProbe 0.2.0: THE ARMOR PASSIVE OVERRIDE LIVE TEST, SECOND ROUND (hd2.passives, hd2.player_passives,
-- hd2.armor_kit; docs/armor-passives.md; research/player-attributes-F5FEE03DCFDB.json,
-- research/passive-effects-F5FEE03DCFDB.json). Development only; SOLO; public API only, plus its logging.
-- 0.1.0 proved the armor-slot swap to SERVO-ASSISTED, ENGINEERING KIT and SCOUT. 0.2.0 tests more passives IN THE ARMOR
-- SLOT whose effect is clearly observable, and one control that must NOT change (EXTRA PADDING: the armor rating follows
-- the worn kit, never the slot). F8 cycles the ARMOR passive override
--     VANILLA -> INTEGRATED EXPLOSIVES -> MED-KIT -> FORTIFIED -> DEMOCRACY PROTECTS -> ELECTRICAL CONDUIT -> INFLAMMABLE
--     -> EXTRA PADDING (control) -> SERVO-ASSISTED -> ENGINEERING KIT -> SCOUT -> VANILLA
-- INTEGRATED EXPLOSIVES carries an effect package: the Runtime loads it through core/assets before it writes the slot
-- (the handle is 'waiting_for_assets', then 'active'); the probe logs each status change. Ctrl+F8 adds / removes a
-- SECOND passive (MED-KIT) in the empty helmet slot. Ctrl+Shift+F8 restores everything (the kit's own passives).
-- Shift+F8 logs the passives and the handle now (changes nothing). Each change logs the handle, the slots, the rows the
-- game now reads, what follows the swap and what to observe. The Runtime logs each re-application after an armor or
-- helmet change ("passives (...): RE-APPLIED ...").
local mod=hd2.mod()
local BUILD='0.2.0 PASSIVE SWAP ROUND TWO'
mod:log('PassiveSwapProbe '..BUILD..' BUILD: start a SOLO mission; F8 cycles the armor passive VANILLA -> INTEGRATED '
    ..'EXPLOSIVES -> MED-KIT -> FORTIFIED -> DEMOCRACY PROTECTS -> ELECTRICAL CONDUIT -> INFLAMMABLE -> EXTRA PADDING '
    ..'(control: must NOT change) -> SERVO-ASSISTED -> ENGINEERING KIT -> SCOUT; Ctrl+F8 adds / removes a second passive '
    ..'(MED-KIT); Ctrl+Shift+F8 restores the kit\'s own passives; Shift+F8 logs the passives now. Each change logs what '
    ..'to observe.')

local MODES={
    {name='VANILLA',observe='the kit\'s own passive: note your health loss from your own grenade at a fixed distance, '
        ..'your grenade and stim counts after a resupply, and how a stim lasts'},
    {name='INTEGRATED EXPLOSIVES',passive='INTEGRATED EXPLOSIVES',observe='DEATH EXPLOSION: die (e.g. your own grenade '
        ..'or a fall); about 1.5 s later your body must EXPLODE where you died (visible blast and sound). The effect '
        ..'package must be logged resident BEFORE the handle turns active. Also +2 grenades (may only show after the next '
        ..'resupply or reinforcement)'},
    {name='MED-KIT',passive='MED-KIT',observe='+2 STIMS: call a resupply, the stim count must reach the kit\'s +2 '
        ..'(UNPROVEN timing: capacity may only change at resupply or reinforcement); STIM DURATION +2 s: the stim '
        ..'heal-over-time effect lasts about 2 s longer than in VANILLA'},
    {name='FORTIFIED',passive='FORTIFIED',observe='EXPLOSIVE DAMAGE x0.5: throw your own grenade at the same distance as '
        ..'in VANILLA (just outside the kill radius): you lose about half the health; recoil x0.7 when crouching or prone'},
    {name='DEMOCRACY PROTECTS',passive='DEMOCRACY PROTECTS',observe='SURVIVE LETHAL DAMAGE (the game text: 50% chance): '
        ..'take a lethal hit several times (e.g. your own grenade at your feet); about half the time you must survive '
        ..'with low health; a chest bleed (hemorrhage) must do no damage'},
    {name='ELECTRICAL CONDUIT',passive='ELECTRICAL CONDUIT',observe='ARC DAMAGE x0.05: stand next to your own Tesla '
        ..'Tower (A/ARC-3) or an Arc Thrower blast; in VANILLA it kills you quickly, now it must barely hurt'},
    {name='INFLAMMABLE',passive='INFLAMMABLE',observe='FIRE DAMAGE x0.25: stand in your own incendiary grenade\'s fire; '
        ..'the health bar must drain about four times slower than in VANILLA'},
    {name='EXTRA PADDING',passive='EXTRA PADDING',observe='CONTROL, MUST NOT CHANGE: its only effect is the armor rating, '
        ..'which follows the worn armor kit, never the slot (research). Take the same hit as in VANILLA: the same damage. '
        ..'Any difference is a finding: report it'},
    {name='SERVO-ASSISTED',passive='SERVO-ASSISTED',observe='live-proven in 0.1.0: THROW RANGE x1.3 (a grenade at the '
        ..'same angle lands clearly farther); limb health x1.5'},
    {name='ENGINEERING KIT',passive='ENGINEERING KIT',observe='live-proven in 0.1.0: +2 GRENADES (after a resupply or '
        ..'reinforcement); recoil x0.7 when crouching or prone'},
    {name='SCOUT',passive='SCOUT',observe='live-proven in 0.1.0: ENEMY DETECTION x0.7; a map marker makes a radar scan '
        ..'every 2 s'},
}
local SECOND,SECOND_OBSERVE='MED-KIT','+2 STIMS at the next resupply or reinforcement (UNPROVEN timing) and stim '
    ..'duration +2 s; readers that ignore the helmet slot (flinch, Integrated Explosives, one chest-bleed site) never see it'
local state={mode=1,second=false}
local handle
local seen_status

local function g(v)return v and('%g'):format(v)or'?'end
local function kit_text(k)
    if not k then return'?'end
    return k.id..(k.name and(' '..k.name)or'')..(k.weight and(' ('..k.weight..')')or'')
end
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
    mod:log(('PASSIVES (%s): entity %s record %s; armor kit %s (its passive %s), helmet kit %s; ARMOR SLOT %s (%d), '
        ..'HELMET SLOT %s (%d); kit-derived armor %d, helmet %d; overridden %s%s; the game reads (flags 3): %s')
        :format(why,tostring(mine.entity),tostring(mine.record),kit_text(mine.armor_kit),tostring(mine.armor_kit.passive),
        kit_text(mine.helmet_kit),mine.armor_passive.name,mine.armor_passive.id,
        mine.helmet_passive.id==0 and'none'or mine.helmet_passive.name,mine.helmet_passive.id,mine.derived.armor,
        mine.derived.second,tostring(mine.overridden),mine.runtime and(' by '..mine.runtime)or'',
        #rows>0 and table.concat(rows,'; ')or'nothing'))
end
-- What follows a swap for this passive (the research), and its effect package, in one line.
local function follows_line(name)
    local p=name and hd2.passives.find(name)
    if not p then return end
    local rows={}
    for _,m in ipairs(p.modifiers)do
        rows[#rows+1]=('%s %s%s'):format(m.key_name,tostring(m.reader),m.follows==false and' (does NOT follow)'
            or m.follows==nil and' (unknown)'or'')
    end
    mod:log(('FOLLOWS (%s): %s; %s%s%s'):format(p.name,tostring(p.follows_swap),table.concat(rows,', '),
        p.note and('; '..p.note)or'',p.package_info and('; effect package '..p.package_info.catalogue..' '
        ..p.package_info.package..' ('..p.package_info.contents..'): loaded before the write')or''))
end

local function apply(why)
    local m=MODES[state.mode]
    seen_status=nil
    if not m.passive and not state.second then
        if handle then handle:stop();handle=nil end
        mod:log(('MODE %s (%s): no override; OBSERVE: %s'):format(m.name,why,m.observe))
        passives_line('after '..why)
        return
    end
    -- The second passive is left out while the armor mode is that passive itself (it would add nothing).
    local second=state.second and m.passive~=SECOND
    handle=hd2.player_passives.set({armor=m.passive,second=second and SECOND or false,allow_unverified_effect=true})
    seen_status=handle.status
    mod:log(('MODE %s%s (%s): handle %s%s'):format(m.name,second and(' + second '..SECOND)or'',why,
        tostring(handle.status),handle.code and(': '..handle.code..': '..tostring(handle.reason))or''))
    if handle.status=='refused'then handle=nil;return end
    follows_line(m.passive)
    mod:log('OBSERVE: '..m.observe..(second and('; SECOND '..SECOND..': '..SECOND_OBSERVE)or''))
    passives_line('after '..why)
end

local list=hd2.passives.list()
local packaged={}
for _,p in ipairs(list)do if p.package_info then packaged[#packaged+1]=p.name..' '..p.package_info.package end end
mod:log(('the game has %d armor passives and %d kits; effect packages: %s; this probe uses %d modes and the second '
    ..'passive %s'):format(#list,#hd2.armor_kits(),table.concat(packaged,', '),#MODES,SECOND))
passives_line('loaded')
hd2.events.on('mission_started',function()passives_line('mission start')end)
-- A handle waiting for its effect package: its status changes are logged (waiting_for_assets -> active / refused).
hd2.every(0.25,function()
    if not handle or handle.status==seen_status then return end
    local was=seen_status
    seen_status=handle.status
    mod:log(('HANDLE %s -> %s%s'):format(tostring(was),tostring(handle.status),handle.code and(': '..handle.code..': '
        ..tostring(handle.reason))or''))
    if handle.status=='active'then passives_line('handle active')end
end)

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
