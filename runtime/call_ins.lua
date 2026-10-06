-- The thrown stratagem balls and their throwers (EXPERIMENTAL; read-only; research/peer-messaging-F5FEE03DCFDB.json
-- "callIn"; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md, section 11). Nothing here writes the game.
--
-- A thrown ball is a networked game object (type 1169) of the call-in component [game+0x3326D98]. Its replicated state
-- (+0x60, 0x28 each, the total count at +0x18 with the network copies) holds, on EVERY machine:
--   * +0x10 its thrower's session peer id: the throw writes game_object_owner of the thrower's Player and marks the
--     field for replication; a remote copy takes it from the network at its spawn and every update after;
--   * +0x18 the thrower's record entry index (-1 while still in hand), +0x08 the stratagem type;
--   * +0x1C from the landing, the network id of the beacon it spawned (0x7FFF before).
-- So a beacon maps to its thrower by its network id, on any machine, with no guess: M.thrower checks the ball names the
-- beacon, the thrower is a lobby record's peer and that record's entry holds the ball's type. Nothing else is inferred:
-- no ball, or one that does not check out, is reported as unknown.
local world_module=require('hd2runtime/runtime/event_world')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/peer_messaging').callIn
local M={}
M.MAX=64
local proven
function M.reset_for_tests()proven=nil end

function M.prove(world)
    if proven and proven.key==world.key then return proven.ok,proven.why end
    local ok,why=true,nil
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            ok,why=false,('game+%X changed (%s)'):format(pin.rva,pin.label)
            break
        end
    end
    proven={key=world.key,ok=ok,why=why}
    return ok,why
end

-- Every thrown ball (an owner and an entry index): {{index, type, owner (peer hex), entry, beacon_network}}, or nil, why.
function M.balls(world)
    local ok,why=M.prove(world)
    if not ok then return nil,why end
    local comp=world.view.pointer(world.game+D.global)
    if not comp then return nil,'the call-in component is unreadable'end
    local total=world.view.u32(comp+D.total)
    local states=world.view.pointer(comp+D.states)
    if not total or total>M.MAX then return nil,'the call-in count is implausible'end
    local out={}
    if total==0 then return out end
    if not states then return nil,'the call-in states are unreadable'end
    local raw=world.view.read(states,total*D.stride)
    if not raw then return nil,'the call-in states are unreadable'end
    for i=0,total-1 do
        local at=i*D.stride
        local lo,hi=b.u32(raw,at+D.owner),b.u32(raw,at+D.owner+4)
        local entry=b.u32(raw,at+D.entry)
        if(lo~=0 or hi~=0)and entry<0x80000000 then
            out[#out+1]={index=i,type=b.u32(raw,at+D.type),owner=world_module.peer_hex(lo,hi),entry=entry,
                beacon_network=b.u32(raw,at+D.beaconNetwork)}
        end
    end
    return out
end

-- The thrower of the beacon whose network id is `network`: {peer, entry, slot (its loadout slot), type, ball}, or nil
-- and why. records: runtime/stratagem_slot_conversion.lua records (each peer's {peer, entries}). accept(peer, slot,
-- entry type, ball type) (optional): whether another entry type is still that ball's (a custom slot's record here may
-- hold the token while the thrower's own, converted, threw the carrier: its conversion is not sent).
M.NO_NETWORK=D.noNetwork
function M.thrower(world,network,records,accept)
    if not network or network==D.noNetwork then return nil,'the beacon has no network id'end
    local balls,why=M.balls(world)
    if not balls then return nil,why end
    local ball
    for _,x in ipairs(balls)do
        if x.beacon_network==network then
            if ball then return nil,'two balls name that beacon'end
            ball=x
        end
    end
    if not ball then return nil,'no thrown ball names that beacon (yet)'end
    return M.resolve(ball,records,accept)
end
-- One ball (M.balls) checked against the records: {peer, entry, slot, type, ball}, or nil and why (as M.thrower).
function M.resolve(ball,records,accept)
    local record
    for _,r in ipairs(records or{})do if r.peer==ball.owner then record=r end end
    if not record then return nil,('the ball\'s owner %s has no stratagem record here'):format(ball.owner)end
    local entry,slot,n
    n=0
    local list={}
    for _,e in ipairs(record.entries)do list[#list+1]=e end
    table.sort(list,function(a,c)return a.index<c.index end)
    for _,e in ipairs(list)do
        if e.index==ball.entry then entry=e;slot=e.granted==0 and n or nil end
        if e.granted==0 then n=n+1 end
    end
    if not entry then return nil,('%s\'s record has no entry %d'):format(ball.owner,ball.entry)end
    if entry.type~=ball.type and not(accept and accept(record.peer,slot,entry.type,ball.type))then
        return nil,('%s\'s record entry %d holds type %d, the ball type %d'):format(ball.owner,ball.entry,entry.type,
            ball.type)
    end
    return {peer=ball.owner,entry=ball.entry,slot=slot,type=ball.type,ball=ball}
end
return M
