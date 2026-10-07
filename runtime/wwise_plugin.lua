-- The loaded Wwise plugin (bin/plugins/wwise_pluginw64_release.dll), proven against domains/wwise_plugin.lua
-- (scripts/generate_wwise_plugin.py; research/docs/wwise-plugin-bindings-F5FEE03DCFDB.md). Read-only: nothing here
-- writes memory or calls the plugin.
--
-- prove(world): the module's image size and the exact bytes of every pinned instruction of the bindings the Runtime
-- calls (runtime/sound_events.lua) and of the counter-id map, once per loaded module base.
--
-- counter_entry(world, counter): trigger_event returns the plugin's own counter id; pause_event / resume_event /
-- is_playing / get_playing_elapsed look the sound engine's playing id up instead. The plugin keeps counter -> {state,
-- Wwise id} in a map of its manager ([plugin+0x5757E8] + 0x1CE70; lookup 0x1AE90): live count +0x20, bucket count
-- +0x24, entries +0x10 of 16 bytes (key +0, state +4, Wwise id +8, next +0xC: 0x7FFFFFFF ends a chain, 0xFFFFFFFE an
-- empty bucket); the bucket is (k * 0x5BD1E995; h ^= h >> 24; h * 0x5BD1E995) mod 2^32 % buckets. The map has no lock:
-- it belongs to the thread that posts synchronously, so it is read only right after this thread's own post returned,
-- and only state 0 (posted now, its own Wwise id) is taken (the self-check: a queued post, state 2, means this thread
-- does not own the map).
local D=require('hd2runtime/domains/wwise_plugin')
local b=require('hd2runtime/core/bytes')
local bit=require('bit')
local M={}
local C=D.counterMap
local E=C.entry
M.STATES=C.states
local proven   -- {base, view}

local function mul32(a,c)
    local low,high=c%65536,math.floor(c/65536)
    return(a*low+((a*high)%65536)*65536)%4294967296
end
-- The plugin's bucket hash of a counter id (0x1AEA7..0x1AEBB).
function M.hash(key)
    local h=mul32(key,C.multiplier)
    h=bit.bxor(h,bit.rshift(h,C.shift))%4294967296
    return mul32(h,C.multiplier)
end

-- The proven plugin {base, view}, or nil and why.
function M.prove(world)
    local runtime=world and world.runtime
    if not(runtime and runtime.module and runtime.address)then return nil,'no runtime adapter'end
    local handle=runtime.module(D.module)
    if not handle then return nil,'the Wwise plugin is not loaded'end
    local base=runtime.address(handle)
    if proven and proven.base==base and proven.view==world.view then return proven end
    local view=world.view
    local header=view.read(base,4096)
    if not(header and header:sub(1,2)=='MZ')then return nil,'the Wwise plugin header is unreadable'end
    local pe=b.u32(header,60)
    if not(pe>=64 and pe+88<=#header and header:sub(pe+1,pe+4)=='PE\0\0')then return nil,'the Wwise plugin PE header'end
    if b.u32(header,pe+80)~=D.imageSize then return nil,'the Wwise plugin changed (image size)'end
    for _,pin in ipairs(D.pins)do
        if not view.proves(base+pin.rva,pin.hex)then
            return nil,('the Wwise plugin changed (%s at +%X)'):format(pin.label,pin.rva)
        end
    end
    proven={base=base,view=view}
    return proven
end

-- The plugin's {state, Wwise playing id} of a counter id, or nil and why. Only right after this thread's own post.
function M.counter_entry(world,counter)
    if not(type(counter)=='number'and counter%1==0 and counter>0 and counter<4294967296)then
        return nil,'not a playing id'
    end
    local plugin,why=M.prove(world)
    if not plugin then return nil,why end
    local view=plugin.view
    local manager=view.pointer(plugin.base+C.managerGlobal)
    if not manager then return nil,'the Wwise plugin has no manager'end
    local map=view.read(manager+C.map,0x28)
    if not map then return nil,'the playing-id map is unreadable'end
    local live,buckets=b.u32(map,C.live),b.u32(map,C.buckets)
    local entries=b.u32(map,C.entries)+b.u32(map,C.entries+4)*4294967296
    if live==0 then return nil,'the playing id is not in the map'end
    if buckets==0 or buckets>16777216 or entries<65536 then return nil,'the playing-id map is implausible'end
    local index=M.hash(counter)%buckets
    for step=1,4096 do
        local e=view.read(entries+E.size*index,E.size)
        if not e then return nil,'the playing-id map is unreadable'end
        local key,state,id,nextIndex=b.u32(e,E.key),b.u32(e,E.state),b.u32(e,E.id),b.u32(e,E.next)
        if step==1 and nextIndex==E.empty then return nil,'the playing id is not in the map'end
        if key==counter then return {state=state,id=id}end
        if nextIndex==C.chainEnd then return nil,'the playing id is not in the map'end
        if nextIndex>=16777216 then return nil,'the playing-id map is implausible'end
        index=nextIndex
    end
    return nil,'the playing-id chain is too long'
end
function M.reset_for_tests()proven=nil end
return M
