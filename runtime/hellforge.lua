-- HellForge's Lua bridge (docs/hellforge.md; HellForge's native/mod-sdk/hellforge_lua.h): when the Runtime runs in a
-- HellForge session, hellforge_modloader.dll is in the game and exports plain C functions for it. The Runtime then
-- writes nothing itself: a mod's patch, transaction, plan or ensure becomes a HellForge live edit of the same fields
-- (runtime/hellforge_writes.lua), so HellForge's F8 editor shows the mod that changed a value, and the events come
-- from HellForge's event hooks (runtime/hellforge_events.lua). The public API stays the same; what HellForge has no
-- engine call for is unavailable there (runtime/hellforge_api.lua). Outside HellForge none of this runs: the DLL is
-- never there, so active() is false and every module keeps its own path.
--
-- Exports are bound through GetProcAddress-typed pointers (runtime/windows_ffi.lua's convention): no global ffi.cdef
-- function names another mod could also declare; the structs carry this Runtime's prefix.
local M={}
local MODULE='hellforge_modloader.dll'
local BRIDGE=3   -- the bridge version this Runtime speaks (HF_LUA_BRIDGE_VERSION; 2: set_stat, copy_row, set_code;
                 -- 3: HellForge's heal, stat, weapon, explosion and bug hole events, and its actions)
M.BRIDGE=BRIDGE
-- hellforge_mod.h's constants the Runtime uses.
M.TYPE={u8=1,u16=2,u32=3,i32=4,f32=5,u64=6}
M.APPLIES={[1]='now',[2]='respawn',[3]='mission'}
M.LIVE_SHARED=1
M.ON={state=1,mission_start=2,mission_end=3,player_spawn=4,player_down=5,damage=6,stratagem=7,kill=8,spawn=9,
    heal=10,stat=11,weapon=12,explosion=13,bughole=14}
-- HF_ACT_...: what an action answered (0 refused)
M.ACT={done=1,requested=2,waiting=3,queued=4}
-- HF_STAT_...: the mission stats a stat event names
M.STAT={shots=0x565790DA,hits=0x897A5551,kills=0xD494C5CC,damage=0x5C7A2930}
M.EVENT_SIZE=128

local backend,checked,info
local mods={}

local STRUCTS_KEY='HD2RuntimeHellForgeFfiV1'
local function structs(ffi)
    if rawget(_G,STRUCTS_KEY)then return end
    ffi.cdef[[
        typedef struct HD2RuntimeHellForgeInfo {
            uint32_t size; uint32_t bridge; uint32_t sdk; uint32_t ready; const char *build; const char *logs;
        } HD2RuntimeHellForgeInfo;
        typedef struct HD2RuntimeHellForgeValue {
            uint32_t type; uint32_t applies; double now; double base; uint64_t now_u64; uint64_t base_u64;
            const char *holder;
        } HD2RuntimeHellForgeValue;
        typedef struct HD2RuntimeHellForgeEvent { uint8_t data[128]; } HD2RuntimeHellForgeEvent;
        typedef struct HD2RuntimeHellForgePassives {
            uint32_t armor, second, kit_armor, kit_second, want_armor, want_second, players; int held; char status[160];
        } HD2RuntimeHellForgePassives;
    ]]
    rawset(_G,STRUCTS_KEY,true)
end

-- The DLL's exports as Lua functions with the bridge's own signatures, or nil and why.
local SIGNATURES={
    info='int (*)(HD2RuntimeHellForgeInfo *)',
    mod='void *(*)(const char *)',
    set='int (*)(void *, const char *, uint64_t, uint32_t, uint32_t, double, uint64_t, uint32_t)',
    clear='int (*)(void *, const char *, uint64_t, uint32_t, uint32_t)',
    get='int (*)(void *, const char *, uint64_t, uint32_t, uint32_t, HD2RuntimeHellForgeValue *)',
    owner='uint64_t (*)(const char *, uint32_t, uint32_t *)',
    listen='int (*)(void *, uint32_t)',
    poll='int (*)(HD2RuntimeHellForgeEvent *, int, uint32_t *)',
    rewrites='int (*)(uint32_t, uint32_t)',
    game_state='uint32_t (*)(void)',
    stratagem_type='uint32_t (*)(uint32_t)',
    set_stat='int (*)(void *, const char *, const char *, uint64_t, int64_t, uint32_t, uint32_t, double)',
    clear_stat='int (*)(void *, const char *, const char *, uint64_t, int64_t, uint32_t, uint32_t)',
    copy_row='int (*)(void *, const char *, uint64_t, uint64_t, uint32_t, uint32_t)',
    set_code='int (*)(void *, uint32_t, const uint32_t *, uint32_t)',
    heal='int (*)(void *, float)',
    heal_limb='int (*)(void *, uint32_t)',
    injure='int (*)(void *, uint32_t, int32_t)',
    limb_state='int (*)(void *, uint32_t, uint32_t, int32_t *)',
    apply_status='int (*)(void *, uint32_t, uint32_t, float)',
    add_velocity='int (*)(void *, float, float, float)',
    resupply_from_pack='int (*)(void *)',
    spawn_explosion='int (*)(void *, uint32_t, float, float, float)',
    spawn_projectile='int (*)(void *, uint32_t, float, float, float, float, float, float)',
    credit_to_player='int (*)(void *, uint32_t)',
    freeze_mission_timer='int (*)(void *, int)',
    spawn_pelican='int (*)(void *, float, float, float, float, float, float, float, float, uint32_t *)',
    modify_shots='uint32_t (*)(void *, uint32_t, const uint64_t *, float, float, float, float, float, uint32_t)',
    homing='uint32_t (*)(void *, uint32_t, const uint64_t *, float, float, float, float, float, uint32_t)',
    stop_shots='int (*)(void *, uint32_t)',
    find='uint64_t (*)(uint32_t, const char *)',
    load_package='int (*)(void *, uint64_t)',
    set_passives='int (*)(void *, uint32_t, uint32_t)',
    get_passives='int (*)(void *, HD2RuntimeHellForgePassives *)',
    log='void (*)(void *, const char *)',
    last='const char *(*)(void *)',
}
local function native_backend()
    -- A HellForge session names its loader in the game's environment: without it nothing more is looked at (no FFI
    -- bindings are loaded for the check outside HellForge).
    local getenv=type(os)=='table'and os.getenv
    if getenv and not getenv('HELLFORGE_MODLOADER')then return nil,'not a HellForge session'end
    local ok_ffi,ffi=pcall(require,'ffi')
    if not ok_ffi then return nil,'no LuaJIT ffi'end
    local ok_win,win=pcall(require,'hd2runtime/runtime/windows_ffi')
    if not ok_win then return nil,'no Win32 bindings: '..tostring(win)end
    local module=win.kernel.GetModuleHandleA(MODULE)
    if module==nil then return nil,'not a HellForge session'end
    structs(ffi)
    local c={}
    for name,signature in pairs(SIGNATURES)do
        local address=win.kernel.GetProcAddress(module,'hellforge_lua_'..name)
        if address==nil then return nil,MODULE..' has no hellforge_lua_'..name..' (an older HellForge)'end
        c[name]=ffi.cast(win.fn(signature),address)
    end
    local out=ffi.new('HD2RuntimeHellForgeInfo')
    out.size=ffi.sizeof(out)
    if c.info(out)~=1 then return nil,'the bridge refused its info call'end
    local text=function(p)return p~=nil and ffi.string(p)or nil end
    local self={native=true,ffi=ffi,c=c}
    function self.info()
        c.info(out)
        return {bridge=out.bridge,sdk=out.sdk,ready=out.ready,build=text(out.build),logs=text(out.logs)}
    end
    function self.mod(name)local m=c.mod(name);return m~=nil and m or nil end
    function self.set(m,component,target,offset,kind,number,u64,flags)
        return c.set(m,component,target,offset,kind,number or 0,u64 or 0,flags or 0)
    end
    function self.clear(m,component,target,offset,kind)return c.clear(m,component,target,offset,kind)end
    local value=ffi.new('HD2RuntimeHellForgeValue')
    function self.get(m,component,target,offset,kind)
        local applies=c.get(m,component,target,offset,kind,value)
        if applies==0 then return nil end
        return {applies=applies,now=value.now,base=value.base,now_u64=value.now_u64,base_u64=value.base_u64,
            holder=text(value.holder)}
    end
    local owners=ffi.new('uint32_t[1]')
    function self.owner(component,record)
        local resource=c.owner(component,record,owners)
        return resource~=0 and resource or nil,owners[0]
    end
    function self.listen(m,kind)return c.listen(m,kind)==1 end
    local events,dropped=ffi.new('HD2RuntimeHellForgeEvent[64]'),ffi.new('uint32_t[1]')
    -- The queued events as byte strings (each starts with its HfEventInfo), and how many the queue dropped.
    function self.poll()
        local list,lost={},0
        repeat
            local n=c.poll(events,64,dropped)
            lost=lost+dropped[0]
            for i=0,n-1 do list[#list+1]=ffi.string(events[i].data,M.EVENT_SIZE)end
        until n<64
        return list,lost
    end
    function self.rewrites(rva,size)return c.rewrites(rva,size)==1 end
    function self.game_base()
        local game=win.kernel.GetModuleHandleA('game.dll')
        return game~=nil and tonumber(ffi.cast('uintptr_t',game))or nil
    end
    function self.game_state()return c.game_state()end
    function self.stratagem_type(stable)return c.stratagem_type(stable)end
    function self.set_stat(m,stat,component,resource,record,offset,kind,number)
        return c.set_stat(m,stat,component,resource,record,offset,kind,number)
    end
    function self.clear_stat(m,stat,component,resource,record,offset,kind)
        return c.clear_stat(m,stat,component,resource,record,offset,kind)
    end
    function self.copy_row(m,table_name,row,from,offset,size)return c.copy_row(m,table_name,row,from,offset,size)end
    -- the actions (HF_ACT_..., 0 refused)
    function self.heal(m,amount)return c.heal(m,amount)end
    function self.heal_limb(m,limb)return c.heal_limb(m,limb)end
    function self.injure(m,limb,damage)return c.injure(m,limb,damage)end
    function self.limb_state(m,entity,limb)
        local out=ffi.new('int32_t[3]')
        if c.limb_state(m,entity,limb,out)==0 then return nil end
        return {health=out[0],max=out[1],injured=out[2]~=0}
    end
    function self.apply_status(m,entity,status,buildup)return c.apply_status(m,entity,status,buildup)end
    function self.add_velocity(m,x,y,z)return c.add_velocity(m,x,y,z)end
    function self.resupply_from_pack(m)return c.resupply_from_pack(m)end
    function self.spawn_explosion(m,kind,x,y,z)return c.spawn_explosion(m,kind,x,y,z)end
    function self.spawn_projectile(m,kind,x,y,z,dx,dy,dz)return c.spawn_projectile(m,kind,x,y,z,dx,dy,dz)end
    function self.credit_to_player(m,entity)return c.credit_to_player(m,entity)end
    function self.freeze_mission_timer(m,frozen)return c.freeze_mission_timer(m,frozen and 1 or 0)end
    function self.spawn_pelican(m,x,y,z,hover,distance,height,fx,fy)
        local out=ffi.new('uint32_t[1]')
        local result=c.spawn_pelican(m,x,y,z,hover,distance,height,fx,fy,out)
        return result,out[0]
    end
    -- sources: weapon resources (u64, numbers or cdata), the list ending with them
    local function resources(list)
        if not list or #list==0 then return nil end
        local array=ffi.new('uint64_t[?]',#list+1)
        for i,v in ipairs(list)do array[i-1]=v end
        return array
    end
    function self.modify_shots(m,kind,sources,damage,penetration,speed,gravity,drag,flags)
        return c.modify_shots(m,kind,resources(sources),damage,penetration,speed,gravity,drag,flags or 0)
    end
    function self.homing(m,kind,sources,turn,cone,range,arm,aim,flags)
        return c.homing(m,kind,resources(sources),turn,cone,range,arm,aim,flags or 0)
    end
    function self.stop_shots(m,id)return c.stop_shots(m,id)==1 end
    -- values: the directions (1 up .. 4 left), or nil for the code from before
    function self.set_code(m,stable,values)
        if values==nil then return c.set_code(m,stable,nil,0)end
        local array=ffi.new('uint32_t[10]')
        for i,value in ipairs(values)do array[i-1]=value end
        return c.set_code(m,stable,array,#values)
    end
    function self.find(kind,name)local id=c.find(kind,name);return id~=0 and id or nil end
    function self.load_package(m,package)return c.load_package(m,package)end
    local passives=ffi.new('HD2RuntimeHellForgePassives')
    function self.set_passives(m,armor,second)return c.set_passives(m,armor,second)==1 end
    function self.get_passives(m)
        if c.get_passives(m,passives)==0 then return nil end
        return {armor=passives.armor,second=passives.second,kit_armor=passives.kit_armor,kit_second=passives.kit_second,
            want_armor=passives.want_armor,want_second=passives.want_second,players=passives.players,
            held=passives.held~=0,status=ffi.string(passives.status)}
    end
    function self.log(m,line)c.log(m,line)end
    function self.last(m)return text(c.last(m))or''end
    return self
end

-- Whether the Runtime runs on HellForge's bridge (checked once: the DLL is in the game from its start, or never).
function M.active()
    if checked==nil then
        local ok,made,why=pcall(native_backend)
        backend=ok and made or nil
        checked=backend~=nil
        M.reason=backend and nil or tostring(ok and why or made)
        if backend then
            info=backend.info()
            if info.bridge<BRIDGE then
                M.reason='HellForge speaks Lua bridge '..tostring(info.bridge)..'; this Runtime needs '..BRIDGE
                backend,checked=nil,false
            else
                pcall(function()require('hd2runtime/runtime/log').emit('[HD2Runtime] running on HellForge (Lua bridge '
                    ..tostring(info.bridge)..', SDK '..tostring(info.sdk)..', game build '..tostring(info.build)
                    ..'): mods change values through HellForge')end)
            end
        end
    end
    return checked
end
-- Whether this is a HellForge session (its loader names itself in the game's environment), bridge or not: one whose
-- bridge cannot be used (an older HellForge) still must not have the Runtime write the game itself, over HellForge's
-- own changes, so its operations go to the bridge, which refuses them with M.reason.
function M.session()
    if checked and backend then return true end
    local getenv=type(os)=='table'and os.getenv
    return getenv and getenv('HELLFORGE_MODLOADER')~=nil or false
end
-- The bridge's functions (active() first), for the bridge modules.
function M.backend()return M.active()and backend or nil end
-- What the loader has ready now: {game, entities, projectiles, events} (booleans).
function M.ready()
    local b=M.backend()
    if not b then return {}end
    local now=b.info()
    local r=now.ready or 0
    return {game=r%2==1,entities=math.floor(r/2)%2==1,projectiles=math.floor(r/4)%2==1,events=math.floor(r/8)%2==1}
end
-- HellForge's mod for a Runtime mod (lua.<name>): its changes show under that name in HellForge's editor.
function M.mod(name)
    local b=M.backend()
    if not b then return nil end
    name=type(name)=='string'and name~=''and name~='unknown'and name or'hd2runtime'
    local m=mods[name]
    if m==nil then m=b.mod(name)or false;mods[name]=m end
    return m or nil
end
-- Whether HellForge rewrote the code a pin proves (its moved tables' instructions, widened bounds, hooks, anything it
-- wrote into game.dll): such a pin reads as HellForge left it, so a proof accepts it there and nowhere else. module is
-- the pin's ('game'); false outside HellForge.
function M.rewritten(module,rva,size)
    local b=M.backend()
    if not b or(module~='game'and module~='game.dll')or type(rva)~='number'then return false end
    return b.rewrites(rva,size)==true
end
-- The same for an address (runtime/native_view.lua proves).
function M.rewritten_at(address,size)
    local b=M.backend()
    local base=b and b.game_base and b.game_base()
    if not base or type(address)~='number'or address<base then return false end
    return M.rewritten('game',address-base,size)
end

-- Tests: a fake bridge (the same functions as native_backend's, in Lua), or nil to detect again.
function M.set_backend(fake)
    backend,mods,info=fake,{},nil
    if fake then checked=true;M.reason=nil else checked=nil end
end
return M
