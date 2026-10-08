local hd2=require('mods/skyeshade/hd2runtime')
-- ArmorStatProbe 0.1.0: THE ARMOR STATS LIVE TEST (hd2.armor_stats; docs/armor-stats.md;
-- research/armor-stats-F5FEE03DCFDB.json). Development only; SOLO; public API only, plus its logging.
-- F9 cycles the local player's STAMINA FACTOR (hd2.armor_stats.player():set / restore)
--     0.5 (sprint about twice as long) -> 1.5 (about 2/3, or half on light armor) -> GAME (the kit's own) -> 0.5
-- Ctrl+F9 cycles the WORN ARMOR KIT's pieces (one hd2.ensure over hd2.armor_stats.kit(...):fields(), its values bound
-- to script choices) VANILLA -> ALL HEAVY (rating 150, damage x0.75) -> ALL LIGHT (rating 50, damage x1.25) -> VANILLA
-- Every hit on the local player's avatar logs the health it lost (entity_damaged), with the armor value and the damage
-- multiplier the Runtime reads now. Shift+F9 logs the state (changes nothing). The class tables are read-only in this
-- build (docs/armor-stats.md), so this probe exercises the writable levers.
local mod=hd2.mod()
local BUILD='0.1.0 ARMOR STAT PROBE'
mod:log('ArmorStatProbe '..BUILD..' BUILD: start a SOLO mission; F9 cycles YOUR stamina factor 0.5 -> 1.5 -> the '
    ..'game\'s (sprint until exhausted and time it); Ctrl+F9 cycles YOUR ARMOR KIT\'s pieces ALL HEAVY -> ALL LIGHT -> '
    ..'VANILLA (let the same weak enemy hit you; every hit logs the health lost); Shift+F9 logs the state now.')

local me=hd2.armor_stats.player()
local STAMINA={
    {name='0.5',value=0.5,observe='half the drain AND half the regen: a full sprint from full stamina lasts about TWICE '
        ..'as long as with the game\'s factor; an empty bar refills about half as fast'},
    {name='1.5',value=1.5,observe='x1.5 drain and regen: a full sprint lasts about 2/3 as long as at 1.0 (on light '
        ..'armor, 0.75, about HALF as long); it refills faster'},
    {name='GAME',observe='the game\'s own factor again (light 0.75, medium 1, heavy 1.5): time a full sprint as the baseline'},
}
local KIT={
    {name='VANILLA',observe='the kit\'s own pieces: note the health lost per hit from one weak enemy (the baseline)'},
    {name='ALL HEAVY',weight='heavy',observe='rating 150 (armor value 2): each hit must cost about x0.75 of a medium '
        ..'armor\'s, x0.6 of a light armor\'s (x0.75 / x1.25); speed 450 and stamina 50 only from your next respawn'},
    {name='ALL LIGHT',weight='light',observe='rating 50 (armor value 0): each hit must cost about x1.25 of a medium '
        ..'armor\'s, x1.67 of a heavy armor\'s; speed 550 and stamina 125 only from your next respawn'},
}
local state={stamina=#STAMINA,kit=1}
local binding                     -- {kit, leader, ensure}: the worn kit's ensure, made at the first Ctrl+F9
local avatar                      -- the local avatar's entity id, for the hit log
local hits={}                     -- per kit mode: {n, lost}

local function g(v)return v and('%g'):format(v)or'?'end
local function state_line(why)
    local view,code,reason=me:describe()
    if not view then
        mod:log(('STATE (%s): unreadable: %s: %s'):format(why,tostring(code),tostring(reason)))
        return nil
    end
    avatar=view.avatar
    local d=view.derived or{}
    local kit=view.armor_kit
    mod:log(('STATE (%s): avatar %s slot %s; armor kit %s%s; STAMINA FACTOR %s (the kit gives %s); ARMOR BONUS %s; '
        ..'the kit gives rating %s, speed %s, stamina regen %s (armor value %s, damage x%s); a hit uses armor value %s; '
        ..'overridden %s'):format(why,tostring(view.avatar),tostring(view.slot),kit and kit.id or'?',
        kit and kit.name and(' '..kit.name)or'',g(view.stamina_factor),g(d.stamina_factor),g(view.armor_bonus),
        g(d.rating),g(d.speed),g(d.stamina_regen),g(d.armor_value),g(d.damage_multiplier),
        g(view.effective_armor_value),tostring(view.overridden)))
    return view
end

local function stamina(why)
    local m=STAMINA[state.stamina]
    local r
    if m.value then r=me:set({stamina_factor=m.value,allow_unverified_effect=true})else r=me:restore()end
    mod:log(('STAMINA %s (%s): %s%s; OBSERVE: %s'):format(m.name,why,tostring(r.status),
        r.code and(': '..r.code..': '..tostring(r.reason))or(' (factor now '..g(r.stamina_factor)..')'),m.observe))
    state_line('after '..why)
end

-- The worn kit's ensure: one transaction over every armor piece, each value a script choice (index 1 the vanilla
-- weight as a number, 2 'heavy', 3 'light'; the first slot's choice leads, the others follow it).
local function bind_kit(view)
    local id=view.armor_kit and view.armor_kit.id
    if not id then return nil,'the worn armor kit is unknown'end
    if binding and binding.kit==id then return binding end
    if binding then return nil,'the probe is bound to kit '..binding.kit..': set VANILLA there first, then reload'end
    local kit=hd2.armor_stats.kit(id)
    local WEIGHT={light=0,medium=1,heavy=2}
    local changes,leader={},nil
    for _,f in ipairs(kit:fields())do
        local values={WEIGHT[f.currentDefault],'heavy','light'}
        local choice=mod:choice({id='kit_'..id..'_'..f.slot,values=values,follow=leader})
        leader=leader or choice
        changes[#changes+1]={field=f.semanticFieldId,expect=f.currentDefault,value=choice}
    end
    local ensure=hd2.ensure({interval=5,transaction={id='armor-stat-probe-kit-'..id,target=kit,allow_shared=true,
        allow_unverified_effect=true,changes=changes},on_status=function(status,info)
            mod:log(('KIT ENSURE %s: %s%s'):format(id,tostring(status),info.error and(': '..tostring(info.error))or''))
        end})
    local slots={}
    for _,f in ipairs(kit:fields())do slots[#slots+1]=f.slot end
    binding={kit=id,leader=leader,ensure=ensure,target=kit,slots=slots}
    local vanilla=kit:describe().vanilla
    mod:log(('KIT %s%s bound: %d armor slots (every body\'s piece), vanilla rating %s'):format(id,
        view.armor_kit.name and(' '..view.armor_kit.name)or'',#changes,vanilla and g(vanilla.rating)or'?'))
    return binding
end
local function kit_mode(why)
    local m=KIT[state.kit]
    local view=state_line(why)
    if not view then return end
    local b,reason=bind_kit(view)
    if not b then mod:log('KIT '..m.name..' ('..why..'): not bound: '..tostring(reason))return end
    b.leader:select(state.kit)
    -- What the ensure writes within a second (the stats those pieces give); Shift+F9 shows the live kit.
    local want={}
    if m.weight then for _,slot in ipairs(b.slots)do want[slot]=m.weight end end
    local after=b.target:preview(want)
    mod:log(('KIT %s (%s): kit %s, %s pieces (the ensure writes them within a second): rating %s, speed %s, stamina '
        ..'regen %s (armor value %s, damage x%s); OBSERVE: %s'):format(m.name,why,b.kit,m.weight or'vanilla',
        g(after.rating),g(after.speed),g(after.stamina_regen),g(after.armor_value),g(after.damage_multiplier),m.observe))
end

hd2.events.on('entity_damaged',function(e)
    if not(e.avatar and avatar and e.entity_id==avatar)then return end
    local m=KIT[state.kit]
    local h=hits[m.name]or{n=0,lost=0}
    hits[m.name]=h
    h.n,h.lost=h.n+1,h.lost+e.damage
    mod:log(('HIT [%s, stamina %s] #%d: -%d health (%d / %s left); average %.1f per hit in this mode'):format(m.name,
        STAMINA[state.stamina].name,h.n,e.damage,e.health,tostring(e.max_health),h.lost/h.n))
end)
hd2.events.on('player_spawned',function(e)
    if not e.local_player then return end
    local view=state_line('spawned')
    if view and STAMINA[state.stamina].value then
        mod:log(('SPAWN: the game applied the armor again (stamina factor %s, the kit gives %s); setting %s again')
            :format(g(view.stamina_factor),g(view.derived and view.derived.stamina_factor),STAMINA[state.stamina].name))
        stamina('respawn')
    end
end)
hd2.events.on('mission_started',function()state_line('mission start')end)
state_line('loaded')

hd2.input.bind('armor_stat_probe.stamina',{key='F9',on_press=function()
    state.stamina=state.stamina%#STAMINA+1
    stamina('F9')
end})
hd2.input.bind('armor_stat_probe.kit',{key='Ctrl+F9',on_press=function()
    state.kit=state.kit%#KIT+1
    kit_mode('Ctrl+F9')
end})
hd2.input.bind('armor_stat_probe.status',{key='Shift+F9',on_press=function()
    local parts={}
    for _,m in ipairs(KIT)do
        local h=hits[m.name]
        if h then parts[#parts+1]=('%s %d hits, %.1f per hit'):format(m.name,h.n,h.lost/h.n)end
    end
    mod:log(('STATUS (Shift+F9): stamina %s, kit %s%s; hits: %s'):format(STAMINA[state.stamina].name,KIT[state.kit].name,
        binding and(' (kit '..binding.kit..', ensure '..tostring(binding.ensure and binding.ensure.status)..')')or'',
        #parts>0 and table.concat(parts,'; ')or'none yet'))
    if binding then
        local now=binding.target:describe()
        local torso=now.pieces and now.pieces.torso
        mod:log(('KIT LIVE (Shift+F9): kit %s gives rating %s, speed %s, stamina regen %s (armor value %s, damage x%s; '
            ..'torso %s; source %s)'):format(binding.kit,g(now.stats.rating),g(now.stats.speed),g(now.stats.stamina_regen),
            g(now.stats.armor_value),g(now.stats.damage_multiplier),torso and tostring(torso.weight)or'?',
            tostring(now.source)))
    end
    state_line('Shift+F9')
end})
