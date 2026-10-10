-- The lobby watch of beam conversions (docs/beam-conversion.md "Multiplayer"; research/docs/beam-conversion-mp-
-- F5FEE03DCFDB.md). A conversion is applied only while this machine plays alone (runtime/beam_conversion.lua gates).
-- Another player can still join afterwards, or this machine can join another lobby with a conversion applied. Every
-- peer builds a weapon from its OWN membership list, so the converted weapon is a beam weapon here and a projectile
-- weapon on every other machine. Worse, a weapon of a converted type that ANOTHER machine owns (a joiner's Liberator)
-- is built here without the ProjectileWeapon instance its network apply step 0x6190C0 looks up: it gets -1 and writes
-- 12 bytes at an unmapped address, so THIS game crashes when that weapon spawns (research/docs/beam-conversion-mp-
-- F5FEE03DCFDB.md). The same conversion on the other machine does not help: the apply is chosen by the network type
-- alone (research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md; runtime/beam_conversion_sync.lua publishes this
-- machine's set and logs every member's state, and its decision is always REFUSED with others present). So while any
-- conversion is applied this watch reads the lobby every CHECK second (memory reads only) and, when another player is
-- present (a joiner, or this machine joining another lobby):
--   * logs a loud warning and shows the Runtime's safety notice (leave the lobby; quit if a converted weapon is in use);
--   * RESTORES at once (on the first read that sees the other player, then every RESTORE_EVERY s) every converted
--     weapon with ZERO live instances on this machine (one guarded transaction each, the same restore an ensure
--     makes), so a joiner's weapon of that type spawns as vanilla. A member appears in the PlayFab lobby long before
--     its session loads and its weapons spawn. A converted weapon that
--     is live cannot be restored (changing its list under a live instance corrupts the BeamWeapon destroy): it stays,
--     for the shooter, and the warning repeats until the player count changes.
-- The mods' ensures stay registered: their apply waits (NOT_SOLO) and converts again once the game is solo.
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local world_module=require('hd2runtime/runtime/event_world')
local M={}
M.CHECK=1
M.RESTORE_EVERY=5
local KEY='HD2RuntimeBeamConversionWatchV1'
local function state()
    local s=rawget(_G,KEY)
    if not s then s={converted={},clock=0,next_check=0,next_restore=0,others=false,warned=nil};rawset(_G,KEY,s)end
    return s
end
local function log(text)log_module.emit('BEAM CONVERSION: '..text)end
M.TEXT={title='BEAM CONVERSION: NOT SOLO',
    rule='A beam-converted weapon type carried by another player can crash this game when it spawns.',
    advice='Leave the lobby. Unequipped converted weapons were restored; quit the game if one is still in use.'}

-- Restores every converted weapon whose census is zero; returns restored names and the ones left (live).
local function restore_idle(E)
    local exclusive=require('hd2runtime/runtime/exclusive')
    local token={}
    if not exclusive.acquire(token)then return {},{},'another guarded operation is running'end
    local restored,left={},{}
    local ok,why=pcall(function()
        local transaction=require('hd2runtime/core/guarded_transaction')
        local world=E.open()
        local s=E.locate(world)
        local names={}
        for name,W in pairs(s.weapons)do if W.state=='converted'or W.state=='orphaned'then names[#names+1]=name end end
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
        -- The first sight of another player restores at once; while they stay, again every RESTORE_EVERY s.
        if st.others and st.clock<st.next_restore then return end
        st.others=true
        st.next_restore=st.clock+M.RESTORE_EVERY
        local restored,left,err=restore_idle(E)
        if#restored>0 then
            log('ANOTHER PLAYER IS PRESENT ('..tostring(why)..'): restored '..table.concat(restored,', ')
                ..' (no live instance): a joiner\'s weapon of that type now spawns as vanilla')
        end
        if#st.converted==0 then return end
        local key=table.concat(st.converted,', ')..'|'..tostring(why)
        if st.warned~=key then
            st.warned=key
            log(('WARNING: ANOTHER PLAYER IS PRESENT (%s) while %s %s converted to Trident beams. Each machine builds '
                ..'weapons from its own lists: a weapon of a converted type that another player carries is built here '
                ..'without its ProjectileWeapon and CRASHES THIS GAME when it spawns; your own converted weapon fires '
                ..'nothing visible on their machines. The same conversion on their machine does not prevent it '
                ..'(BEAM CONVERSION SYNC). Converted weapons with no live instance are restored at once; '
                ..'one in use cannot be (%s). LEAVE THE LOBBY, or quit the game (docs/beam-conversion.md '
                ..'"Multiplayer")'):format(tostring(why),table.concat(st.converted,', '),
                #st.converted==1 and'is'or'are',#left>0 and table.concat(left,'; ')or tostring(err or'none left')))
            pcall(function()
                require('hd2runtime/runtime/matchmaking_safety').notice(M.TEXT.title,
                    table.concat(st.converted,', ')..' converted; '..tostring(why)..'.',M.TEXT.rule,M.TEXT.advice)
            end)
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
    and st.watch.status=='active'or false}end
function M.reset_for_tests()
    local st=rawget(_G,KEY)
    if st and st.watch then st.watch.status='cancelled'end
    rawset(_G,KEY,nil)
end
return M
