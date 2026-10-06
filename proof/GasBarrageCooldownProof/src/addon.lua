local hd2=require('mods/skyeshade/hd2runtime')
-- GasBarrageCooldownProof 0.1.0: THE FIXED 60 S COOLDOWN (docs/custom-stratagems.md, "The fixed cooldown"). Development
-- only; solo host; no multiplayer.
-- A COMPANION of GasBarragePayloadProof 0.2.2, installed with it and unchanged: that proof selects, discovers, presents,
-- converts and pays the Gas Barrage (all live-proven). This one only gives the converted Gas Barrage slot a fixed 60 s
-- cooldown, whichever carrier was discovered:
--   * research/slot-cooldown-F5FEE03DCFDB.json: the cooldown is the mission record ENTRY's own (+0x18, an absolute game
--     time in microseconds, compared unsigned with the clock); a call writes end = the call-in's ARRIVAL + the carrier
--     row's cooldown x the active modifiers; the HUD shows the slot inbound until the arrival, then cooling, and its bar
--     takes the time left on its first cooling frame as its total;
--   * runtime/slot_cooldown.lua watches the converted entry every frame; in the frame the game starts its cooldown it
--     writes the end once, guarded: 60 s from the arrival (the game's own rule: the HUD's cooling bar shows 60 s for
--     every carrier), or, with "Count from the call" on, 60 s from that frame (the current game time);
--   * never written: the carrier's row (its own cooldown), the token, the donors, the save, the account; a call it
--     cannot prove (stale, not the carrier, a shared cooldown type, not a cooldown) keeps the carrier's own cooldown;
--   * nothing to restore: the record's ends are mission state the game rebuilds.
-- The payload proof's own "CALL-IN: ... cooldown changed" line may appear twice for one call (the game's write, then
-- this override): both are this one call.
local mod=hd2.mod()
local BUILD='0.1.0 FIXED COOLDOWN'
mod:log('GasBarrageCooldownProof '..BUILD..' BUILD (a companion of GasBarragePayloadProof 0.2.2, which must also be '
    ..'installed): play the Gas Barrage test exactly as before (custom panel, READY, solo mission, wait for "READY TO '
    ..'CALL"); call it with UP UP DOWN DOWN. Expect "COOLDOWN: game started", "COOLDOWN: Gas Barrage override = 60.0", '
    ..'"COOLDOWN: verified end", then "COOLDOWN: HUD" (the bar\'s total) and, 60 s after the call-in\'s arrival, '
    ..'"COOLDOWN: READY AGAIN"; call it again to see a second cooldown. Ctrl+F10: cooldown status.')

local cool=require('hd2runtime/runtime/slot_cooldown')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local world_module=require('hd2runtime/runtime/event_world')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local PD=require('hd2runtime/domains/bombardment_payload')
local DEFINITION,SECONDS='orbital_gas_barrage',60
local US=1000000

local options=hd2.options({id='gas_barrage_cooldown_proof',title='Gas Barrage Cooldown Proof',fallback='default'})
local enabled=options:toggle({id='cooldown',label='Fixed 60 s Gas Barrage cooldown',default=true,
    description='In a solo mission, when the converted Gas Barrage slot is called, its cooldown becomes 60 s (the '
        ..'mission record entry only; the carrier\'s own cooldown is never written). Off: the carrier\'s own cooldown. '
        ..'Read at mission start.'})
local from_call=options:toggle({id='from_call',label='Count the 60 s from the call',default=false,
    description='Off (default): 60 s from the call-in\'s arrival, the game\'s own rule (the HUD\'s cooling bar shows '
        ..'60 s for every carrier). On: 60 s from the moment the Runtime sees the call (the current game time), so the '
        ..'carrier\'s inbound time comes out of the 60 s. Read at mission start.'})
local function settled(t)return t:describe().state~='pending'end
local function wanted(t)return settled(t)and t:get()==true and not t:disables()end

local function s(us)return us/US end
local function f(n)return n and('%.2f'):format(n)or'?'end
local function name_of(world,kind)
    local id=loadout.id_of(world,kind)
    for name,entry in pairs(catalog.stratagems)do if entry.root and entry.root.id==id then return name end end
    return'type '..tostring(kind)
end

------------------------------------------------------------------------------------------------- the ship --
-- Read-only, once aboard the ship: the native cooldowns of every payload-compatible carrier (before any conversion).
local shown_native=false
local function native_cooldowns(world)
    if shown_native then return end
    local parts={}
    for id,c in pairs(PD.compatibility)do
        if c.compatible then
            local kind=loadout.type_of(world,tonumber(id))
            local cooldown,ctype
            if kind then cooldown,ctype=cool.row_cooldown(world,kind)end
            if cooldown==nil then return end
            parts[#parts+1]=('%s %s s (cooldown type %s)'):format(c.name,f(cooldown),tostring(ctype))
        end
    end
    table.sort(parts)
    shown_native=true
    mod:log('COOLDOWN: carrier native cooldowns before any conversion (the payload-compatible carriers\' own rows, '
        ..'read-only): '..table.concat(parts,'; ')..'; the Gas Barrage cooldown will be '..SECONDS..'.0 s whichever is '
        ..'discovered')
end

----------------------------------------------------------------------------------------------- the mission --
local M_={in_mission=false,armed=false,calls={},progress={}}
local function report(e)
    local call=e.index and M_.calls[e.index]
    if e.kind=='armed'then
        M_.carrier,M_.from=e.carrier,e.from
        local parts={}
        for _,index in ipairs(e.indices)do
            parts[#parts+1]=('loadout slot %s = record entry %d'):format(tostring(e.slots[index]),index)
        end
        mod:log(('COOLDOWN: the Gas Barrage conversion is seen: %s -> the carrier %s (type %d, stable id %s). COOLDOWN: '
            ..'carrier native = %s s (its row, never written; cooldown type %s: the entry\'s own). Each call of the slot '
            ..'gets %d.0 s from %s'):format(table.concat(parts,', '),e.carrier,e.type,tostring(e.id),f(e.rowCooldown),
            tostring(e.cooldownType),SECONDS,e.from=='now'and'the call (the current game time when the Runtime sees '
            ..'it)'or'the call-in\'s arrival (the game\'s own rule)'))
    elseif e.kind=='overridden'or e.kind=='refused'and e.index then
        local native=s(e.gameEnd-e.arrival)
        M_.calls[e.index]={activation=e.activation,arrival=e.arrival,gameEnd=e.gameEnd,clock=e.clock,desired=e.desired,
            overridden=e.kind=='overridden',native=native,next=e.clock+15*US}
        mod:log(('COOLDOWN: carrier native = %s s (%s\'s row; with the game\'s modifiers x%s that is %s s)'):format(
            f(e.rowCooldown),e.carrier,e.rowCooldown and('%.4f'):format(native/e.rowCooldown)or'?',f(native)))
        mod:log(('COOLDOWN: game started = %s s after the call-in\'s arrival (record entry %d, loadout slot %s: activation '
            ..'t=%d, arrival t=%d, %s s inbound, end t=%d; seen %s s after the activation, at t=%d, %s s left)'):format(
            f(native),e.index,tostring(e.slot),e.activation,e.arrival,f(s(e.arrival-e.activation)),e.gameEnd,
            f(s(e.clock-e.activation)),e.clock,f(s(e.gameEnd-e.clock))))
        if e.kind=='refused'then
            mod:log(('COOLDOWN: Gas Barrage override REFUSED (nothing written; this call keeps the carrier\'s own %s s): '
                ..'%s: %s'):format(f(native),tostring(e.code),tostring(e.reason)))
            return
        end
        mod:log(('COOLDOWN: Gas Barrage override = %d.0 s from %s (end t=%d -> t=%d; %d write; the entry reads it %s, '
            ..'nothing else of the record changed %s, non-target bytes unchanged %s, protection restored %s)'):format(
            SECONDS,e.from=='now'and'the current game time'or'the call-in\'s arrival',e.gameEnd,e.desired,e.writes,
            tostring(e.verify.finish),tostring(e.verify.others),tostring(e.verify.nonTarget),tostring(e.verify.protection)))
        mod:log(('COOLDOWN: verified end = current_game_time + %s (t=%d at the write; the entry\'s end t=%d = the '
            ..'call-in\'s arrival + %s = the activation + %s)'):format(f(s(e.desired-e.clock)),e.clock,e.desired,
            f(s(e.desired-e.arrival)),f(s(e.desired-e.activation))))
    elseif e.kind=='hud'then
        local native=call and s(call.gameEnd-e.clock)
        mod:log(('COOLDOWN: HUD: the slot is COOLING; its bar took a total of %s s on its first cooling frame (t=%d: '
            ..'the Gas Barrage end gives %s s; the carrier\'s own end would have given %s s) and shows %s s left -> %s')
            :format(f(e.total),e.clock,f(e.expected),f(native),f(e.coolingLeft),not e.overridden and'the carrier\'s own '
            ..'cooldown (not overridden)'or math.abs(e.total-e.expected)<0.25 and'the HUD shows the Gas Barrage cooldown'
            or'the bar took ANOTHER total (the override came after its first cooling frame?)'))
    elseif e.kind=='changed'then
        mod:log(('COOLDOWN: record entry %d\'s end changed, not yet a cooldown start (%s): activation t=%d, arrival t=%d, '
            ..'end t=%d at t=%d; nothing written, still watching'):format(e.index,e.reason,e.activation,e.arrival,e.finish,
            e.clock))
    elseif e.kind=='rewritten'then
        mod:log(('COOLDOWN: the GAME CHANGED the end again after the override: t=%d -> t=%d (now %s s left; not written '
            ..'again)'):format(e.expected,e.value,f(e.clock and s(e.value-e.clock))))
    elseif e.kind=='ready'then
        mod:log(('COOLDOWN: READY AGAIN: record entry %d (loadout slot %s) is callable again at t=%d: %s s after the '
            ..'call-in\'s arrival, %s s after the activation, %s s after the write; %s'):format(e.index,tostring(e.slot),
            e.clock,f(s(e.clock-e.arrival)),f(s(e.clock-e.activation)),f(s(e.clock-e.writeClock)),e.overridden and
            ('final cooldown = %s s from %s (the carrier\'s own would have lasted %s s more)'):format(
            f(s(e.finish-(M_.from=='now'and e.writeClock or e.arrival))),M_.from=='now'and'the call'or'the arrival',
            f(call and s(call.gameEnd-e.finish)))or'the carrier\'s own cooldown (not overridden)'))
        M_.calls[e.index]=nil
    elseif e.kind=='ended'then
        -- Armed once per mission (a new mission arms again).
        mod:log('COOLDOWN: watch ended: '..tostring(e.reason))
    elseif e.kind=='refused'then
        mod:log(('COOLDOWN: REFUSED (nothing written): %s: %s'):format(tostring(e.code),tostring(e.reason)))
    end
end
-- While a call cools down: every 15 s, the entry's time left and what the HUD shows (read-only).
local function progress(world)
    local clock=cool.clock(world)
    if not clock then return end
    for index,c in pairs(M_.calls)do
        if clock>=c.next then
            c.next=clock+15*US
            local h,why=cool.hud(world,index)
            mod:log(('COOLDOWN: +%s s after the arrival: %s s left on the entry; the HUD %s'):format(f(s(clock-c.arrival)),
                f(s((c.overridden and c.desired or c.gameEnd)-clock)),h and('slot state %s, cooling %s s left, bar total '
                ..'%s s'):format(tostring(h.state),f(h.coolingLeft),f(h.total))or('unreadable: '..tostring(why))))
        end
    end
end

local function arm()
    if not(settled(enabled)and settled(from_call))then return end
    M_.armed=true
    if not wanted(enabled)then
        mod:log('MISSION START: the fixed cooldown is switched off (Gas Barrage Cooldown Proof): the carrier keeps its '
            ..'own cooldown; nothing written')
        return
    end
    local from=wanted(from_call)and'now'or'arrival'
    local watch,why=cool.arm({definition=DEFINITION,seconds=SECONDS,from=from},report)
    mod:log(watch and('MISSION START: the fixed cooldown is armed: %d.0 s from %s for the converted Gas Barrage slots '
        ..'(waiting for the conversion)'):format(SECONDS,from=='now'and'the call'or'the call-in\'s arrival')
        or('MISSION START: the fixed cooldown could not be armed: '..tostring(why)))
end

hd2.every(0.5,function()
    local world=world_module.open()
    if not world then return end
    local state=hd2.game_state()
    local mission=state and state.mission
    if mission and not M_.in_mission then
        M_.in_mission,M_.armed,M_.calls=true,false,{}
    elseif not mission and M_.in_mission then
        M_.in_mission=false
        if cool.armed()then cool.disarm()end
        mod:log('MISSION END: the record\'s cooldown ends are mission state the game rebuilds: nothing to restore; the '
            ..'carrier\'s row cooldown was never written')
    end
    if mission then
        if not M_.armed then arm()end
        progress(world)
    elseif state then
        native_cooldowns(world)
    end
end,{id='gas-barrage-cooldown-proof'})

hd2.input.bind('gas_barrage_cooldown_proof.status',{key='Ctrl+F10',on_press=function()
    local world=world_module.open()
    local conv=slots.state()
    local clock=world and cool.clock(world)
    local parts={}
    if world and conv and conv.converted and conv.definition==DEFINITION then
        local record=slots.local_record(world)
        for _,index in ipairs(conv.indices)do
            local entry=record and record.entries[index+1]
            if entry then
                local b=entry.bytes
                local function u64(o)return b:byte(o+1)+b:byte(o+2)*256+b:byte(o+3)*65536+b:byte(o+4)*16777216
                    +(b:byte(o+5)+b:byte(o+6)*256+b:byte(o+7)*65536+b:byte(o+8)*16777216)*4294967296 end
                local h=cool.hud(world,index)
                parts[#parts+1]=('entry %d %s: activation t=%d, arrival t=%d, end t=%d (%s s left); HUD %s'):format(index,
                    name_of(world,entry.type),u64(0x10),u64(0x20),u64(0x18),f(clock and math.max(0,s(u64(0x18)-clock))),
                    h and('state '..tostring(h.state)..', bar total '..f(h.total)..' s, cooling '..f(h.coolingLeft)..' s')
                    or'unreadable')
            end
        end
    end
    mod:log(('Ctrl+F10 [%s]: clock t=%s; armed %s (%s); carrier %s; converted Gas Barrage entries: %s'):format(BUILD,
        tostring(clock),tostring(cool.armed()),tostring(M_.from or'-'),tostring(M_.carrier),#parts>0 and
        table.concat(parts,'; ')or'none'))
end})
mod:log('loaded ('..BUILD..'): the converted '..DEFINITION..' slots get a fixed '..SECONDS..'.0 s cooldown (the '
    ..'mission record entry only). Ctrl+F10: cooldown status.')
