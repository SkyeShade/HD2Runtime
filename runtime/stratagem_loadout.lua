-- The player's stratagem loadout, read-only (docs/custom-stratagems.md, "Selectable custom stratagem"). Development
-- infrastructure for the selectable-stratagem proof: not exported by api/hd2.lua, no SDK field, never writes.
--
--   * saved(world): the ship loadout as the game saved it when the loadout screen was left: {StratagemInfo +4 stable
--     id, uses} pairs in the save store (domains/stratagem_calldown.lua loadout, research/stratagem-calldown-*.json),
--     each with the type that stable id has on this build;
--   * record(world): the local player's stratagem record in a mission: every entry's numeric type, its row's stable
--     id and its uses (the same record the HUD's stratagem list and the matcher read);
--   * type_of(world, id): the stratagem type whose row +4 is a stable id (types drift between builds; ids do not).
--
-- The save store's pins are proven once per loaded game.dll before the first read; the record shares the HUD
-- research's pins (runtime/stratagem_hud.lua prove()).
local world_module=require('hd2runtime/runtime/event_world')
local hud=require('hd2runtime/runtime/stratagem_hud')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local C=require('hd2runtime/domains/stratagem_calldown')
local L,REC=C.loadout,C.hud.records
local TABLE,ENTRIES=profile.stratagem.table_rva,profile.stratagem.entries
local MAX_RECORDS=64
local ENTRY_USES=4      -- record entry +4: its uses (pinned: the loadout save copies it as a pair's uses)
local M={}

local proven={}
function M.prove(world)
    if C.source.gameDllSha256~=profile.dll_sha then return nil,'the loadout research covers another game.dll build'end
    if proven[world.game]then return true end
    for _,pin in ipairs(L.pins)do
        local expected=pin.hex:gsub('..',function(pair)return string.char(tonumber(pair,16))end)
        if world.view.read(world.game+pin.rva,#expected)~=expected then
            return nil,'loadout code changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    proven[world.game]=true
    return true
end

local function row(world,kind)
    if type(kind)~='number'or kind<1 or kind>=ENTRIES then return nil end
    return world.view.pointer(world.game+TABLE+kind*8)
end
-- The stable id (row +4) of a type, or nil.
function M.id_of(world,kind)
    local at=row(world,kind)
    return at and world.view.u32(at+4)
end
-- The type whose row +4 is id, or nil. Rows do not move while game.dll stays loaded, so a found type is remembered per
-- loaded game.dll (a full scan reads 149 rows).
local types={}
function M.type_of(world,id)
    if type(id)~='number'or id==0 then return nil end
    local known=types[world.game]
    if not known then known={};types[world.game]=known end
    local kind=known[id]
    if kind and M.id_of(world,kind)==id then return kind end
    for candidate=1,ENTRIES-1 do
        if M.id_of(world,candidate)==id then known[id]=candidate;return candidate end
    end
end

-- {saved = bool, pairs = {{id, uses, type}}}, or nil, code, reason.
function M.saved(world)
    local ok,why=M.prove(world)
    if not ok then return nil,'LOADOUT_UNAVAILABLE',why end
    local store=world.view.pointer(world.game+L.store)
    if not store then return nil,'NO_SAVE_STORE','the save store is not set up'end
    local flag=world.view.read(store+L.savedFlag,1)
    local bytes=world.view.read(store+L.pairs,L.pairCount*L.pairStride)
    if not(flag and bytes)then return nil,'NO_SAVE_STORE','the save store is unreadable'end
    local out={saved=flag:byte()==1,pairs={}}
    for index=0,L.pairCount-1 do
        local id=b.u32(bytes,index*L.pairStride+L.pair.id)
        local uses=b.u32(bytes,index*L.pairStride+L.pair.uses)
        if id~=0 or uses~=0 then out.pairs[#out.pairs+1]={id=id,uses=uses,type=M.type_of(world,id)}end
    end
    return out
end

-- The local player's record entries {{index (0-based, the HUD list slot that draws it), type, id, uses}}, or nil,
-- code, reason.
function M.record(world)
    local ok,why=hud.prove(world)
    if not ok then return nil,'HUD_UNAVAILABLE',why end
    local lo,hi=world_module.local_peer(world)
    local records=world.view.pointer(world.game+REC.global)
    local count=records and world.view.u32(records+REC.count)
    if not(lo and records and count and count<=MAX_RECORDS)then return nil,'NO_RECORD','no stratagem records'end
    for index=0,count-1 do
        local record=records+index*REC.stride
        if world.view.u32(record)==lo and world.view.u32(record+4)==hi then
            local entries=world.view.u32(record+REC.entryCount)
            if not entries or entries>C.hud.slots.count then
                return nil,'NO_RECORD','the local player\'s record has an unexpected entry count'
            end
            local out={}
            for entry=0,entries-1 do
                local at=record+REC.entries+entry*REC.entryStride
                local kind=world.view.u32(at)
                out[#out+1]={index=entry,type=kind,id=M.id_of(world,kind),uses=world.view.u32(at+ENTRY_USES)}
            end
            return out
        end
    end
    return nil,'NO_RECORD','the local player has no stratagem record'
end

function M.reset_for_tests()proven,types={},{}end
return M
