-- THE GAME'S PER-CARD GREY HELPER (research cardEnable, research/stratagem-blocking-F5FEE03DCFDB.json; research/docs/
-- stratagem-blocking-F5FEE03DCFDB.md). Development module: not exported by api/hd2.lua; its only caller is the
-- carrier-in-slot probe's doubles (runtime/stratagem_blocking.lua enable, handed this module by its owner,
-- runtime/custom_stratagems.lua).
--
-- The game greys and un-greys a stratagem card through game.dll+0x18D1440(card list, card key, enabled): it finds the
-- card with that key, writes its enabled byte (card list + 0x92DC2 + index: 0 = "already in this loadout"), and when
-- that card is realized it flips the card widget's grey bit (+0x2B5A bit 2) and calls the game's redraw of that widget;
-- nothing else (its whole body reviewed: those two writes and that one call). The game's own post-pick refresh calls it
-- with 0 for every type of the edited record; Stratagem MultiSelect (a research lead) calls it with 1. A byte written
-- by the Runtime alone is accepted by the pick paths at once but was still drawn grey live (r36): this call also redraws.
--
-- One native call per card, made only: inside the Runtime's own update; with the helper's WHOLE body re-proved (its
-- exact bytes at its address, every call); with the card list of the grid that is open now; for a key exactly one card
-- of that list carries; with 0 or 1. The byte is read back after each call.
local D=require('hd2runtime/domains/stratagem_blocking')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local G=D.grid

-- nil when the helper can be called now, else why not.
function M.unavailable(world)
    local H=D.cardEnable
    if not world.runtime.native_card_enable then return'this Runtime adapter cannot call game functions'end
    if not scheduler.in_update()then return'not inside the Runtime\'s own update'end
    if not(H and world.view.proves(world.game+H.rva,H.code))then
        return('the game\'s per-card grey helper changed (game+%X)'):format(H and H.rva or 0)
    end
    return nil
end

-- The cards through the helper: g = the open grid (stratagem_blocking.grid), entries = {{index, key, to = 0|1}}. Every
-- key must be carried by exactly one card of g (else nothing is called). Returns the number of calls, or nil and why
-- (the calls before a failed read-back stand: the caller re-reads the bytes).
function M.call(world,g,entries)
    local why=M.unavailable(world)
    if why then return nil,why end
    if not(g and g.open and g.list and g.keys and g.count)then return nil,'no open grid'end
    local count={}
    for i=0,g.count-1 do count[g.keys[i]]=(count[g.keys[i]]or 0)+1 end
    for _,e in ipairs(entries)do
        if count[e.key]~=1 then return nil,('%d cards carry the key 0x%08X'):format(count[e.key]or 0,e.key)end
        if not(e.to==0 or e.to==1)then return nil,'enabled must be 0 or 1'end
    end
    local done=0
    for _,e in ipairs(entries)do
        metrics.count('stratagem_card_enable.calls')
        world.runtime.native_card_enable(world.game+D.cardEnable.rva,g.list,e.key,e.to)
        local now=world.view.read(g.list+G.enabled+e.index,1)
        if not(now and now:byte()==e.to)then
            return nil,('card %d reads %s after the helper (wanted %d)'):format(e.index,tostring(now and now:byte()),e.to)
        end
        done=done+1
    end
    return done
end

return M
