-- The lobby watch of beam conversions (docs/beam-conversion.md "Multiplayer"; research/docs/beam-conversion-mp-
-- F5FEE03DCFDB.md, research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md). Every peer builds a weapon from its OWN
-- membership list, so another player can join after a conversion was applied, or this machine can join another lobby
-- with one applied. While any conversion is applied this watch reads the lobby every CHECK second (memory reads only)
-- and, when another player is present (a joiner, or this machine joining another lobby):
--   * SWAP layout conversions (ProjectileWeapon swapped out): a weapon of that type that ANOTHER machine owns is built
--     here without the ProjectileWeapon instance its network apply looks up, and THIS game crashes when it spawns,
--     whatever the other machine converted. They are RESTORED at once (on the first read that sees the other player,
--     then every RESTORE_EVERY s) when they have ZERO live instances here; a live one cannot be (its list cannot change
--     under a live instance) and stays, with a loud warning and the safety notice (leave the lobby / quit).
--   * ADD layout conversions (ProjectileWeapon kept, BeamWeapon added): no crash in any combination, but every machine
--     simulates every player's beam, so a machine that does not hold the identical conversion sees bullets where this
--     one sees beams, and zone health and shields of the targets each owns follow its own simulation. They are kept
--     while runtime/beam_conversion_sync.lua says so (every member holds the identical conversion, or a member is still
--     pending, or a Runtime member is converging), and restored (no live instance) once a member is settled without it.
--     Before the sync has read any member (the first PENDING_WINDOW s) they are kept too.
-- The mods' ensures stay registered: a swap apply waits (NOT_SOLO), an add apply waits until every member agrees
-- (NOT_AGREED), and converts again then.
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local world_module=require('hd2runtime/runtime/event_world')
local M={}
M.CHECK=1
M.RESTORE_EVERY=5
M.PENDING_WINDOW=30
local KEY='HD2RuntimeBeamConversionWatchV2'
local function state()
    local s=rawget(_G,KEY)
    if not s then s={converted={},clock=0,next_check=0,next_restore=0,others=false,warned=nil};rawset(_G,KEY,s)end
    return s
end
local function log(text)log_module.emit('BEAM CONVERSION: '..text)end
M.TEXT={title='BEAM CONVERSION: NOT SOLO',
    rule='A swap-converted weapon type carried by another player can crash this game when it spawns; an add-layout '
        ..'conversion the other players do not hold identically puts beams on one screen and bullets on the other.',
    advice='Leave the lobby, or convert the same weapons the same way on every machine (add layout). Unequipped '
        ..'converted weapons were restored; quit the game if a swap-converted one is still in use.'}

-- Restores every converted weapon in `only` (names; nil: every one) whose census is zero; returns restored names and
-- the ones left (live).
local function restore_idle(E,only)
    local exclusive=require('hd2runtime/runtime/exclusive')
    local token={}
    if not exclusive.acquire(token)then return {},{},'another guarded operation is running'end
    local restored,left={},{}
    local ok,why=pcall(function()
        local transaction=require('hd2runtime/core/guarded_transaction')
        local world=E.open()
        local s=E.locate(world)
        local names={}
        for name,W in pairs(s.weapons)do
            if(W.state=='converted'or W.state=='orphaned')and(only==nil or only[name])then names[#names+1]=name end
        end
        table.sort(names)
        for _,name in ipairs(names)do
            local okp,prepared=pcall(E.prepare,world,s,{weapon=E.weapon(name),enabled=false})
            if okp then
                local report=transaction.apply(world.runtime,prepared.plan)
                E.commit(world,prepared,report)
                if report.status=='APPLIED'or report.status=='ALREADY_DESIRED'then restored[#restored+1]=name
                else left[#left+1]=name..' ('..tostring(report.reason)..')'end
                s=E.locate(world)
            else
                left[#left+1]=name..' ('..tostring(prepared):gsub('^TARGET_UNAVAILABLE: ','')..')'
            end
        end
    end)
    exclusive.release(token)
    if not ok then return restored,left,tostring(why)end
    return restored,left
end
M.restore_idle=restore_idle

-- Which converted weapons to restore now: {[name] = reason} (swap: always; add: per the sync), and the kept add ones.
local function to_restore(E,world,st)
    local sync=require('hd2runtime/runtime/beam_conversion_sync')
    local s=E.locate(world)
    local entries=sync.entries_of(s)
    local by_weapon={}
    for _,e in ipairs(entries)do
        local name=sync.weapon_of(e.resource)
        if name then by_weapon[name]=by_weapon[name]or{};table.insert(by_weapon[name],e)end
    end
    local restore,kept={},{}
    local add={}
    for name,W in pairs(s.weapons)do
        if W.state=='converted'or W.state=='orphaned'then
            if W.layout~='add'then restore[name]='swap layout: solo only'
            elseif W.state=='orphaned'then restore[name]='an orphaned conversion'
            else add[name]=by_weapon[name]or{}end
        end
    end
    if next(add)then
        if not sync.members_known()then
            if st.clock-st.others_since<M.PENDING_WINDOW then
                for name in pairs(add)do kept[name]='PENDING: the lobby members\' conversion sets are not read yet'end
            else
                for name in pairs(add)do restore[name]='the lobby members\' conversion sets could not be read'end
            end
        else
            for name,v in pairs(sync.keep(add))do
                if v.keep then kept[name]=v.code..': '..v.reason else restore[name]=v.code..': '..v.reason end
            end
        end
    end
    return restore,kept
end

local function tick(dt)
    local st=state()
    st.clock=st.clock+(type(dt)=='number'and dt>=0 and dt<10 and dt or 0)
    if st.clock<st.next_check then return end
    st.next_check=st.clock+M.CHECK
    if#st.converted==0 then return end
    local world=world_module.open()
    if not world then return end
    local E=require('hd2runtime/runtime/beam_conversion')
    local lobby,why=E.lobby(world)
    if lobby=='others'then
        -- The first sight of another player decides at once; while they stay, again every RESTORE_EVERY s.
        if not st.others then st.others=true;st.others_since=st.clock;st.next_restore=0 end
        if st.clock<st.next_restore then return end
        st.next_restore=st.clock+M.RESTORE_EVERY
        local okr,restore,kept=pcall(to_restore,E,world,st)
        if not okr then log('lobby watch: the conversions could not be read ('..tostring(restore)..')');return end
        local restored,left,err={},{},nil
        if next(restore)then restored,left,err=restore_idle(E,restore)end
        if#restored>0 then
            local why_list={}
            for _,name in ipairs(restored)do why_list[#why_list+1]=name..' ('..tostring(restore[name])..')'end
            log('ANOTHER PLAYER IS PRESENT ('..tostring(why)..'): restored '..table.concat(why_list,', ')
                ..' (no live instance)')
        end
        if#st.converted==0 then return end
        local kept_names={}
        for name in pairs(kept)do kept_names[#kept_names+1]=name end
        table.sort(kept_names)
        local key=table.concat(st.converted,', ')..'|'..tostring(why)..'|'..table.concat(left,';')
        if st.warned~=key then
            st.warned=key
            if#left>0 then
                log(('WARNING: ANOTHER PLAYER IS PRESENT (%s) while %s cannot be restored (%s). A SWAP-converted '
                    ..'weapon type that another player carries CRASHES THIS GAME when it spawns; an ADD-layout one the '
                    ..'others do not hold identically is a beam here and bullets there (no crash; zone health and '
                    ..'shields out of step). LEAVE THE LOBBY, or quit if a swap conversion is in use '
                    ..'(docs/beam-conversion.md "Multiplayer")'):format(tostring(why),table.concat(st.converted,', '),
                    table.concat(left,'; ')..(err and('; '..err)or'')))
                pcall(function()
                    require('hd2runtime/runtime/matchmaking_safety').notice(M.TEXT.title,
                        table.concat(st.converted,', ')..' converted; '..tostring(why)..'.',M.TEXT.rule,M.TEXT.advice)
                end)
            elseif#kept_names>0 then
                local parts={}
                for _,name in ipairs(kept_names)do parts[#parts+1]=name..' ('..kept[name]..')'end
                log(('another player is present (%s): add-layout conversions kept: %s'):format(tostring(why),
                    table.concat(parts,', ')))
            end
        end
    elseif lobby=='solo'then
        st.others=false
        if st.warned then
            st.warned=nil
            log('solo again: the lobby has one player')
        end
    end
end
M.tick_for_tests=tick

-- Called after every conversion write with the located state: starts the watch while a conversion is applied.
function M.sync(s)
    local st=state()
    local names={}
    for name,W in pairs(s.weapons)do if W.state=='converted'or W.state=='orphaned'then names[#names+1]=name end end
    table.sort(names)
    st.converted=names
    if#names>0 and not(st.watch and st.watch.status=='active')then
        local watch={status='active'}
        function watch.cancel()watch.status='cancelled'end
        function watch.tick(dt)
            if watch.status~='active'then return end
            local ok,why=pcall(tick,dt)
            if not ok then log('lobby watch step failed: '..tostring(why))end
            if#state().converted==0 then watch.status='complete'end
        end
        st.watch=watch
        pcall(scheduler.attach,watch)
    end
end
function M.status()local st=state();return {converted=st.converted,warned=st.warned,active=st.watch
    and st.watch.status=='active'or false,others=st.others}end
function M.reset_for_tests()
    local st=rawget(_G,KEY)
    if st and st.watch then st.watch.status='cancelled'end
    rawset(_G,KEY,nil)
end
return M
