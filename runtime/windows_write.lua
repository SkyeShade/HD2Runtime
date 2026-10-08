-- Loaded only by a patch-capable package when patch() is requested.
local M={}
function M.create()
    local runtime=require('hd2runtime/runtime/windows_readonly')()
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi,kernel=win.ffi,win.kernel
    if not rawget(_G,'HD2RuntimeWriteFfiV1') then
        ffi.cdef [[
            int WriteProcessMemory(void *,void *,const void *,size_t,size_t *);
            int VirtualProtect(void *,size_t,uint32_t,uint32_t *);
        ]]
        rawset(_G,'HD2RuntimeWriteFfiV1',true)
    end
    -- packed=true is only passed for byte-packed entity-delta data; it must still stay in one page.
    function runtime.write(address,bytes,packed)
        assert(type(address)=='number' and address>0 and address<=9007199254740991
            and type(bytes)=='string' and (#bytes==1 or #bytes==4 or #bytes==8 or #bytes==12)
            and (#bytes==1 or address%4==0 or (packed==true and #bytes==4 and address%4096+4<=4096)),
            'unsupported native write extent')
        local count=ffi.new('size_t[1]')
        local ok=kernel.WriteProcessMemory(kernel.GetCurrentProcess(),ffi.cast('void *',address),bytes,#bytes,count)
        return ok~=0,ok==0 and tonumber(kernel.GetLastError()) or nil,tonumber(count[0])
    end
    function runtime.protect(page,size,protection)
        assert(type(page)=='number' and page>0 and page<=9007199254740991
            and page%4096==0 and size==4096 and (protection==2 or protection==4),
            'unsupported native protection extent')
        local old=ffi.new('uint32_t[1]')
        local ok=kernel.VirtualProtect(ffi.cast('void *',page),size,protection,old)
        return ok~=0 and tonumber(old[0]) or nil,ok==0 and tonumber(kernel.GetLastError()) or nil
    end
    -- One native call, used only by core/assets after it re-proved the build, the exact code bytes of
    -- game.dll's RefcountedPackageSystem request function and the instance it passes: take one reference on
    -- one catalog package (the same call gameplay makes when a player carries the item).
    function runtime.package_request(entry,instance,id)
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(instance)=='number'and instance>0 and instance<=9007199254740991
            and type(id)=='string'and#id==8 and id~=string.rep('\0',8),'unsupported package request')
        local ids=ffi.new('uint64_t[1]');ffi.copy(ids,id,8)
        local request=ffi.cast(win.fn('void (*)(void *, const uint64_t *, uint32_t)'),entry)
        request(ffi.cast('void *',instance),ids,1)
        return true
    end
    -- One native call, used only by runtime/event_world.lua after it re-proved the heal function's exact prologue
    -- bytes and that the entity is the local player's living avatar: the game's own
    -- AddHealthFraction(health manager, entity, fraction), which clamps to maximum health.
    function runtime.native_heal(entry,manager,entity,fraction)
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(manager)=='number'and manager>0 and manager<=9007199254740991
            and type(entity)=='number'and entity>0 and entity<4294967296 and entity%1==0
            and type(fraction)=='number'and fraction>0 and fraction<=1,'unsupported heal call')
        local heal=ffi.cast(win.fn('void (*)(void *, uint32_t, float)'),entry)
        heal(ffi.cast('void *',manager),entity,fraction)
        return true
    end
    -- One native call, used only by runtime/event_world.lua after it re-proved the request function's exact prologue
    -- bytes, the queue headroom and that the type's settings record carries that type: the game's own
    -- RequestExplosion(queue, position, type, source, owner, creditor, ...) with the argument template the game's own
    -- callers pass (research/event-actions-F5FEE03DCFDB.json): 0, null, 1, 0, null, null, null, 0, 0.
    function runtime.native_explosion(entry,queue,x,y,z,kind,source,owner,peer_lo,peer_hi)
        local function coordinate(v)return type(v)=='number'and v==v and math.abs(v)<=100000 end
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(queue)=='number'and queue>0 and queue<=9007199254740991
            and coordinate(x)and coordinate(y)and coordinate(z)
            and type(kind)=='number'and kind>0 and kind<0x1A7 and kind%1==0
            and type(source)=='number'and source>0 and source<4294967296 and source%1==0
            and type(owner)=='number'and owner>0 and owner<4294967296 and owner%1==0
            and type(peer_lo)=='number'and peer_lo>=0 and peer_lo<4294967296 and peer_lo%1==0
            and type(peer_hi)=='number'and peer_hi>=0 and peer_hi<4294967296 and peer_hi%1==0,'unsupported explosion call')
        local position=ffi.new('float[3]',x,y,z)
        local peer=ffi.new('uint64_t',peer_hi)*4294967296+peer_lo
        local request=ffi.cast(win.fn('void (*)(void *, const float *, uint32_t, uint32_t, uint32_t, uint64_t, uint32_t, '
            ..'const float *, uint8_t, uint32_t, const uint32_t *, const float *, const float *, uint8_t, uint32_t)'),entry)
        request(ffi.cast('void *',queue),position,kind,source,owner,peer,0,nil,1,0,nil,nil,nil,0,0)
        return true
    end
    -- One native call, used only by runtime/event_world.lua after it re-proved the wrapper's exact prologue bytes,
    -- that the projectile system is active and that the type's settings record carries that type: the game's own
    -- FireProjectile(system, type, position, direction, entity, target, entity_path) with the template of the game's
    -- AI fire helper (research/event-actions-F5FEE03DCFDB.json): target 0 and entity_path 0 (a plain projectile).
    function runtime.native_projectile(entry,system,kind,x,y,z,dx,dy,dz,entity)
        local function coordinate(v)return type(v)=='number'and v==v and math.abs(v)<=100000 end
        local function unit(v)return type(v)=='number'and v==v and math.abs(v)<=1.0001 end
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(system)=='number'and system>0 and system<=9007199254740991
            and coordinate(x)and coordinate(y)and coordinate(z)and unit(dx)and unit(dy)and unit(dz)
            and math.abs(dx*dx+dy*dy+dz*dz-1)<1e-3
            and type(kind)=='number'and kind>0 and kind<351 and kind%1==0
            and type(entity)=='number'and entity>0 and entity<4294967296 and entity%1==0,'unsupported projectile call')
        local position,direction=ffi.new('float[3]',x,y,z),ffi.new('float[3]',dx,dy,dz)
        local fire=ffi.cast(win.fn('void (*)(void *, uint32_t, const float *, const float *, uint32_t, uint32_t, uint64_t)'),
            entry)
        fire(ffi.cast('void *',system),kind,position,direction,entity,0,0)
        return true
    end
    -- Runtime-owned blocks (a custom projectile's ProjectileInfo row, docs/custom-projectile-rows.md): zeroed,
    -- 16-byte aligned LuaJIT allocations, never game memory and never executable. The adapter keeps every block alive
    -- for the life of this Lua state (the game reads a row only during the SpawnProjectile call that receives it), and
    -- owned_write copies only into a block this adapter allocated.
    local owned={}
    function runtime.owned_block(size)
        assert(type(size)=='number'and size>0 and size<=4096 and size%8==0,'unsupported owned block size')
        local block=ffi.new('uint8_t[?]',size+16)
        local base=tonumber(ffi.cast('uintptr_t',block))
        local address=base+(16-base%16)%16
        owned[address]={block=block,size=size}
        return address
    end
    function runtime.owned_write(address,bytes)
        local item=owned[address]
        assert(item and type(bytes)=='string'and#bytes==item.size,'not a whole Runtime-owned block')
        ffi.copy(ffi.cast('void *',address),bytes,#bytes)
        return true
    end
    -- Runtime-owned permanent blocks (a Runtime text table, runtime/text_resources.lua): committed pages from
    -- VirtualAlloc (through a GetProcAddress-typed pointer, no global FFI declaration), filled once, then read-only and
    -- NEVER freed, not even when this Lua state closes, because the game may keep a pointer to a text it looked up.
    -- runtime/text_resources.lua bounds how many it asks for.
    local virtual_alloc
    function runtime.permanent_block(bytes)
        assert(type(bytes)=='string'and#bytes>0 and#bytes<=65536,'unsupported permanent block size')
        if not virtual_alloc then
            local export=kernel.GetProcAddress(kernel.GetModuleHandleA('kernel32.dll'),'VirtualAlloc')
            assert(export~=nil,'VirtualAlloc export unavailable')
            virtual_alloc=ffi.cast(win.fn('void *(__stdcall *)(void *, size_t, uint32_t, uint32_t)'),export)
        end
        local size=#bytes+(4096-#bytes%4096)%4096
        local block=virtual_alloc(nil,size,0x3000,4)              -- MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
        assert(block~=nil,'VirtualAlloc failed: '..tostring(kernel.GetLastError()))
        ffi.copy(block,bytes,#bytes)
        local old=ffi.new('uint32_t[1]')
        assert(kernel.VirtualProtect(block,size,2,old)~=0,'permanent block protection failed')   -- PAGE_READONLY
        local address=tonumber(ffi.cast('uintptr_t',block))
        assert(ffi.string(block,#bytes)==bytes,'the permanent block did not read back as written')
        return address
    end
    -- One Runtime-owned native procedure (r52, used only by runtime/mouse_wheel.lua's read-only message hook): two
    -- committed pages from VirtualAlloc that are NEVER freed (the window thread may still be inside the procedure when
    -- its hook is removed, or when this Lua state closes): page 1 stays read-write and zeroed (the procedure's counters),
    -- page 0 holds the code `build(counters address)` returns (at most 4096 bytes) and is then execute-read only.
    -- Returns the code address and the counters address.
    local native_alloc,native_flush
    function runtime.native_procedure(build)
        assert(type(build)=='function','native_procedure needs a code builder')
        if not native_alloc then
            local k32=kernel.GetModuleHandleA('kernel32.dll')
            local alloc=kernel.GetProcAddress(k32,'VirtualAlloc')
            local flush=kernel.GetProcAddress(k32,'FlushInstructionCache')
            assert(alloc~=nil and flush~=nil,'VirtualAlloc / FlushInstructionCache exports unavailable')
            native_alloc=ffi.cast(win.fn('void *(__stdcall *)(void *, size_t, uint32_t, uint32_t)'),alloc)
            native_flush=ffi.cast(win.fn('int (__stdcall *)(void *, const void *, size_t)'),flush)
        end
        local block=native_alloc(nil,8192,0x3000,4)                 -- MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
        assert(block~=nil,'VirtualAlloc failed: '..tostring(kernel.GetLastError()))
        local base=tonumber(ffi.cast('uintptr_t',block))
        local code=build(base+4096)
        assert(type(code)=='string'and#code>0 and#code<=4096,'a native procedure is 1 to 4096 bytes')
        ffi.copy(block,code,#code)
        local old=ffi.new('uint32_t[1]')
        assert(kernel.VirtualProtect(block,4096,0x20,old)~=0,'the procedure page could not be made execute-read')
        native_flush(kernel.GetCurrentProcess(),block,#code)
        assert(ffi.string(block,#code)==code,'the procedure did not read back as written')
        return base,base+4096
    end
    -- One native call, used only by runtime/event_world.lua after it re-proved SpawnProjectile's exact prologue bytes
    -- and the projectile row pins, that the projectile system is active and that the Runtime-owned row is a VALID
    -- hybrid of its live vanilla base row: the game's own SpawnProjectile(system, descriptor, extra) with the
    -- descriptor FireProjectile's plain path builds (research/projectile-rows-F5FEE03DCFDB.json): position and
    -- direction pointers, the row, source, owner, creditor and kind; no extra parameters (null). The row must be a
    -- block this adapter owns: a game row is never passed. Returns the pool slot the game wrote.
    function runtime.native_spawn_projectile(entry,system,row,x,y,z,dx,dy,dz,source,owner,peer_lo,peer_hi,kind,layout)
        local function coordinate(v)return type(v)=='number'and v==v and math.abs(v)<=100000 end
        local function unit(v)return type(v)=='number'and v==v and math.abs(v)<=1.0001 end
        local function entity(v)return type(v)=='number'and v>0 and v<4294967296 and v%1==0 end
        local function half(v)return type(v)=='number'and v>=0 and v<4294967296 and v%1==0 end
        local function slot(name,width)
            local at=type(layout)=='table'and layout[name]
            return type(at)=='number'and at>=0 and at%width==0 and at+width<=layout.size
        end
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(system)=='number'and system>0 and system<=9007199254740991
            and owned[row]~=nil and coordinate(x)and coordinate(y)and coordinate(z)
            and unit(dx)and unit(dy)and unit(dz)and math.abs(dx*dx+dy*dy+dz*dz-1)<1e-3
            and entity(source)and entity(owner)and half(peer_lo)and half(peer_hi)
            and type(kind)=='number'and kind>=0 and kind<256 and kind%1==0
            and type(layout)=='table'and type(layout.size)=='number'and layout.size>=16 and layout.size<=256
            and slot('position',8)and slot('direction',8)and slot('row',8)and slot('source',4)and slot('owner',4)
            and slot('creditor',8)and slot('kind',4),'unsupported custom projectile call')
        -- Every cdata is created before the descriptor is filled: the descriptor holds raw pointers to position and
        -- direction, so nothing may allocate (and collect them) between filling it and the call.
        local position,direction=ffi.new('float[3]',x,y,z),ffi.new('float[3]',dx,dy,dz)
        local descriptor=ffi.new('uint8_t[?]',layout.size+8)
        local creditor=ffi.new('uint64_t',peer_hi)*4294967296+peer_lo
        local spawn=ffi.cast(win.fn('uint32_t (*)(void *, const void *, const void *)'),entry)
        local base=tonumber(ffi.cast('uintptr_t',descriptor))
        local at=descriptor+(8-base%8)%8
        ffi.cast('const float **',at+layout.position)[0]=position
        ffi.cast('const float **',at+layout.direction)[0]=direction
        ffi.cast('uint64_t *',at+layout.row)[0]=row
        ffi.cast('uint32_t *',at+layout.source)[0]=source
        ffi.cast('uint32_t *',at+layout.owner)[0]=owner
        ffi.cast('uint64_t *',at+layout.creditor)[0]=creditor
        ffi.cast('uint32_t *',at+layout.kind)[0]=kind
        local result=spawn(ffi.cast('void *',system),at,nil)
        -- Keeps position, direction and the descriptor referenced until the game returned.
        assert(position~=nil and direction~=nil and descriptor~=nil)
        return tonumber(result)
    end
    -- One native call, used only by runtime/pelicans.lua M.spawn after it re-proved the spawn request's exact bytes and
    -- every spawn and anchor pin, from the Runtime's own update on the game thread, in a mission as host, with the
    -- Pelican's entity loaded and the world's default spawn context all zero: the game's own spawn request(out, entity,
    -- descriptor) for the transport Pelican ONLY (research/pelican-F5FEE03DCFDB.json, "spawn" and "anchor"). The
    -- descriptor is the one the beacon dispatcher builds: created here (+0x0 = 1), no network id yet (+0x4 = 0x7FFF), the
    -- pose (+0x8: right, forward, up, position; Z up), a spawn context (+0x48) and no modifier block (+0x50 null). The
    -- context is a Runtime-owned copy of the game's own default (0x8A0 bytes, all zero: no cargo, no associated entity)
    -- with ONE member set, the anchor (+0x610: x, y, z), as the beacon sets it for a vehicle's Pelican: the Pelican's
    -- drop-position record takes it at creation and its flight hovers there. Each context stays referenced for the life
    -- of this Lua state (the game reads it during the call). Returns the entity id the game wrote.
    local PELICAN='\179\166\146\133\237\130\190\117'   -- 0x75BE82ED8592A6B3, little-endian
    local CONTEXT_SIZE,ANCHOR=0x8A0,0x610
    local contexts={}
    function runtime.native_spawn_pelican(entry,x,y,z,fx,fy,ax,ay,az)
        local function coordinate(v)return type(v)=='number'and v==v and math.abs(v)<=100000 end
        local function unit(v)return type(v)=='number'and v==v and math.abs(v)<=1.0001 end
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and coordinate(x)and coordinate(y)and coordinate(z)and unit(fx)and unit(fy)
            and math.abs(fx*fx+fy*fy-1)<1e-3 and coordinate(ax)and coordinate(ay)and coordinate(az)
            and #contexts<256,'unsupported Pelican spawn call')
        local context=ffi.new('uint8_t[?]',CONTEXT_SIZE+16)            -- zero-filled
        local cbase=tonumber(ffi.cast('uintptr_t',context))
        local cat=context+(16-cbase%16)%16
        local anchor=ffi.cast('float *',cat+ANCHOR)
        anchor[0],anchor[1],anchor[2]=ax,ay,az
        contexts[#contexts+1]=context
        local descriptor=ffi.new('uint8_t[?]',0x58+8)
        local out=ffi.new('uint32_t[1]')
        local entity=ffi.new('uint64_t[1]')
        ffi.copy(entity,PELICAN,8)
        local base=tonumber(ffi.cast('uintptr_t',descriptor))
        local at=descriptor+(8-base%8)%8
        at[0]=1
        ffi.cast('uint32_t *',at+4)[0]=0x7FFF
        local pose=ffi.cast('float *',at+8)
        local rows={fy,-fx,0,0, fx,fy,0,0, 0,0,1,0, x,y,z,1}
        for k=1,16 do pose[k-1]=rows[k]end
        ffi.cast('void **',at+0x48)[0]=cat
        ffi.cast('void **',at+0x50)[0]=nil
        local spawn=ffi.cast(win.fn('uint32_t *(*)(uint32_t *, uint64_t, void *)'),entry)
        spawn(out,entity[0],at)
        -- Keeps the descriptor and out referenced until the game returned.
        assert(descriptor~=nil and out~=nil)
        return tonumber(out[0])
    end
    -- The Pelican Gatling turret experiment (PelicanGatlingProof; research/docs/pelican-cas-F5FEE03DCFDB.md section 16;
    -- research/pelican-F5FEE03DCFDB.json "gatling"). Five native calls, used only by runtime/pelican_gatling.lua after it
    -- re-proved each routine's exact entry bytes and every Gatling pin, from the Runtime's own update on the game
    -- thread, in a mission as the solo host, for ONE Runtime-spawned Pelican and its own chin turret. None is exposed
    -- through the public API.
    -- The game's own spawn request(out, entity, descriptor) for the Gatling Sentry entity ONLY: created here (+0x0 = 1),
    -- no network id yet (+0x4 = 0x7FFF), the pose (+0x8), no spawn context (+0x48 null: the world's default) and no
    -- modifier block (+0x50 null). Returns the entity id the game wrote.
    local GATLING='\112\29\227\88\207\214\133\239'   -- 0xEF85D6CF58E31D70, little-endian
    function runtime.native_spawn_gatling(entry,x,y,z,fx,fy)
        local function coordinate(v)return type(v)=='number'and v==v and math.abs(v)<=100000 end
        local function unit(v)return type(v)=='number'and v==v and math.abs(v)<=1.0001 end
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and coordinate(x)and coordinate(y)and coordinate(z)and unit(fx)and unit(fy)
            and math.abs(fx*fx+fy*fy-1)<1e-3,'unsupported Gatling spawn call')
        local descriptor=ffi.new('uint8_t[?]',0x58+8)
        local out=ffi.new('uint32_t[1]')
        local entity=ffi.new('uint64_t[1]')
        ffi.copy(entity,GATLING,8)
        local base=tonumber(ffi.cast('uintptr_t',descriptor))
        local at=descriptor+(8-base%8)%8
        at[0]=1
        ffi.cast('uint32_t *',at+4)[0]=0x7FFF
        local pose=ffi.cast('float *',at+8)
        local rows={fy,-fx,0,0, fx,fy,0,0, 0,0,1,0, x,y,z,1}
        for k=1,16 do pose[k-1]=rows[k]end
        ffi.cast('void **',at+0x48)[0]=nil
        ffi.cast('void **',at+0x50)[0]=nil
        local spawn=ffi.cast(win.fn('uint32_t *(*)(uint32_t *, uint64_t, void *)'),entry)
        spawn(out,entity[0],at)
        assert(descriptor~=nil and out~=nil)
        return tonumber(out[0])
    end
    local function entity_id(v)return type(v)=='number'and v>0 and v<4294967296 and v%1==0 end
    local function address(v)return type(v)=='number'and v>0 and v<=9007199254740991 and v%1==0 end
    -- The game's own attach routine(attachable manager, child, parent unit link, parent node, &offset, &rotation, 0.0):
    -- the call the mount system makes for each child it attaches. The rotation is 16-byte aligned (the routine reads it
    -- with an aligned load).
    function runtime.native_attach(entry,manager,child,link,node,offset,rotation)
        local function finite(v)return type(v)=='number'and v==v and math.abs(v)<=1000 end
        assert(address(entry)and address(manager)and entity_id(child)and entity_id(link)
            and type(node)=='number'and node>=0 and node<65536 and node%1==0
            and type(offset)=='table'and finite(offset.x)and finite(offset.y)and finite(offset.z)
            and type(rotation)=='table'and finite(rotation.x)and finite(rotation.y)and finite(rotation.z)
            and finite(rotation.w)and math.abs(rotation.x^2+rotation.y^2+rotation.z^2+rotation.w^2-1)<1e-2,
            'unsupported attach call')
        local storage=ffi.new('float[12]')
        local base=tonumber(ffi.cast('uintptr_t',storage))
        local aligned=ffi.cast('float *',ffi.cast('uint8_t *',storage)+(16-base%16)%16)
        aligned[0],aligned[1],aligned[2],aligned[3]=rotation.x,rotation.y,rotation.z,rotation.w
        aligned[4],aligned[5],aligned[6]=offset.x,offset.y,offset.z
        local attach=ffi.cast(win.fn('void (*)(void *, uint32_t, uint32_t, uint32_t, const float *, const float *, float)'),
            entry)
        attach(ffi.cast('void *',manager),child,link,node,aligned+4,aligned,0)
        assert(storage~=nil)
        return true
    end
    -- The game's own relation unlink(child, owner, parent): the call the mount system makes before it removes a child
    -- (the owner is the mount manager). A child without that relation is left as it is.
    function runtime.native_relation_unlink(entry,child,owner,parent)
        assert(address(entry)and entity_id(child)and address(owner)and entity_id(parent),'unsupported unlink call')
        local unlink=ffi.cast(win.fn('void (*)(uint32_t, void *, uint32_t)'),entry)
        unlink(child,ffi.cast('void *',owner),parent)
        return true
    end
    -- The game's own entity removal(world, entity): deferred (queued in the world's removal map on the host).
    function runtime.native_remove_entity(entry,world,entity)
        assert(address(entry)and address(world)and entity_id(entity),'unsupported removal call')
        local remove=ffi.cast(win.fn('void (*)(void *, uint32_t)'),entry)
        remove(ffi.cast('void *',world),entity)
        return true
    end
    -- The game's own destroy routine(world, the entity's own world record, not forced): what the pending-removal pass
    -- calls for each queued entity. Not forced, it keeps the game's own check: a networked entity must pass the network
    -- layer's ownership check, any other must have been created here. Used only as the second attempt for one
    -- Runtime Pelican's original chin turret, after the game's removal request left it alive.
    function runtime.native_destroy_entity(entry,world,record)
        assert(address(entry)and address(world)and address(record),'unsupported destroy call')
        local destroy=ffi.cast(win.fn('void (*)(void *, void *, uint8_t)'),entry)
        destroy(ffi.cast('void *',world),ffi.cast('void *',record),0)
        return true
    end
    -- The game's own per-instance ProjectileWeapon copy routine(manager, the entity's handle, a delta entry): with the
    -- entry {kind 0, first patch 0, count 0} it reads no patch, so the entity gets an unmodified copy of its type's
    -- record (an entity that already has one is left as it is). Used by runtime/pelican_weapon.lua (a Runtime Pelican's
    -- chin turret) and runtime/custom_weapons.lua (one entity a custom stratagem call delivered and associated).
    function runtime.native_weapon_copy(entry,manager,handle)
        assert(address(entry)and address(manager)and address(handle),'unsupported weapon copy call')
        local delta=ffi.new('uint32_t[4]')   -- zero-filled: kind 0, first patch 0, count 0
        local copy=ffi.cast(win.fn('void (*)(void *, void *, const uint32_t *)'),entry)
        copy(ffi.cast('void *',manager),ffi.cast('void *',handle),delta)
        assert(delta~=nil)
        return true
    end
    -- The game's own SetBehaviour(Behavior manager, entity, behaviour), used only by runtime/pelican_weapon.lua
    -- (PelicanGatlingAIProof) for one Runtime Pelican's own chin turret, and ONLY with behaviour 213 (the Gatling
    -- Sentry's AI): the game's own behaviour change (it exits the old behaviour through its own transition, writes and
    -- replicates the id, and enters the new one at stage 1).
    function runtime.native_set_behaviour(entry,manager,entity,behaviour)
        -- 213: the Gatling AI; 645: the chin turret's own AI back (r44: never let 213 die on a chin turret).
        assert(address(entry)and address(manager)and entity_id(entity)and(behaviour==213 or behaviour==645),
            'unsupported behaviour call')
        local set=ffi.cast(win.fn('void (*)(void *, uint32_t, uint32_t)'),entry)
        set(ffi.cast('void *',manager),entity,behaviour)
        return true
    end
    -- The game's own target setter(context, entry), used only by runtime/pelican_weapon.lua (PelicanGatlingProof 0.4.2)
    -- for one Runtime Pelican's own chin turret running the Gatling AI: the context the Behavior update builds ({the
    -- turret's Behavior handle record, P = its Behavior record + 8}) and a live entry of the turret's own perception
    -- lists, which it copies in as the target (its own pick calls it the same way). Never with a null entry (that would
    -- clear the target).
    function runtime.native_set_target(entry,handle,state,candidate)
        assert(address(entry)and address(handle)and address(state)and address(candidate),'unsupported target call')
        local context=ffi.new('void *[2]')
        context[0]=ffi.cast('void *',handle)
        context[1]=ffi.cast('void *',state)
        local set=ffi.cast(win.fn('void (*)(void *, const void *)'),entry)
        set(context,ffi.cast('const void *',candidate))
        assert(context~=nil)
        return true
    end
    -- The game's own selection close(loadout UI) (research selectorClose), used only by runtime/stratagem_selector.lua
    -- (close_native) after it re-proved the handler's exact bytes and that the selection the Runtime's own selection
    -- filled is still open on this UI: what Back on a focused stratagem slot calls. One argument, no result.
    function runtime.native_selector_close(entry,ui)
        assert(address(entry)and address(ui),'unsupported selector close call')
        local close=ffi.cast(win.fn('void (*)(void *)'),entry)
        close(ffi.cast('void *',ui))
        return true
    end
    -- The game's own per-card grey helper(card list, card key, enabled) (research cardEnable), used only by
    -- runtime/stratagem_blocking.lua (the carrier-in-slot probe's doubles) after it re-proved the helper's whole body,
    -- that the stratagem grid is open on this list and that exactly one card has that key: what the game's own post-pick
    -- refresh calls with 0. It writes that card's enabled byte and, for a realized card, its grey bit and redraw.
    function runtime.native_card_enable(entry,list,key,enabled)
        assert(address(entry)and address(list)and type(key)=='number'and key>=0 and key<4294967296 and key%1==0
            and(enabled==0 or enabled==1),'unsupported card enable call')
        local set=ffi.cast(win.fn('void (*)(void *, uint32_t, uint8_t)'),entry)
        set(ffi.cast('void *',list),key,enabled)
        return true
    end
    -- The game's own per-instance magazine copy routine(manager, the entity's world record, a delta entry), used only by
    -- runtime/pelican_weapon.lua (one Runtime Pelican's chin turret) and runtime/custom_weapons.lua (one entity a custom
    -- stratagem call delivered and associated): with the entry {kind 0, first patch 0, count 0} it reads no patch, so
    -- the entity gets an unmodified copy of its type's magazine record (one that already has a copy is left as it is).
    function runtime.native_magazine_copy(entry,manager,handle)
        assert(address(entry)and address(manager)and address(handle),'unsupported magazine copy call')
        local delta=ffi.new('uint32_t[4]')
        local copy=ffi.cast(win.fn('void (*)(void *, void *, const uint32_t *)'),entry)
        copy(ffi.cast('void *',manager),ffi.cast('void *',handle),delta)
        assert(delta~=nil)
        return true
    end
    -- One native call, used only by runtime/event_world.lua after it re-proved the request function's exact
    -- prologue bytes, the queue headroom, that the type is on the reviewed allowlist and that its settings record
    -- carries that type: the game's own QueueStatusRequest(ignored, type, target, buildup, instigator, variant) with
    -- the game's own template (variant 0).
    function runtime.native_status(entry,kind,target,buildup,instigator)
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(kind)=='number'and kind>0 and kind<=71 and kind%1==0
            and type(target)=='number'and target>0 and target<4294967296 and target%1==0
            and type(buildup)=='number'and buildup==buildup and buildup>0 and buildup<=1000
            and type(instigator)=='number'and instigator>0 and instigator<4294967296 and instigator%1==0,
            'unsupported status call')
        local request=ffi.cast(win.fn('void (*)(void *, uint32_t, uint32_t, float, uint32_t, uint32_t)'),entry)
        request(nil,kind,target,buildup,instigator,0)
        return true
    end
    -- One native call, used only by runtime/event_world.lua (injure) after it re-proved that the engine unit API slot
    -- game.dll's own VG-70 self-damage calls is exactly this function and its exact entry bytes: the engine's unit actor
    -- lookup(unit, actor name, null) (research/player-injury-path-F5FEE03DCFDB.json). A pure lookup over the unit's
    -- actors; returns the actor handle, or nil when the unit has no actor of that name.
    function runtime.native_unit_actor(entry,unit,name)
        assert(address(entry)and entity_id(unit)and entity_id(name),'unsupported unit actor call')
        local lookup=ffi.cast(win.fn('uint32_t (*)(uint32_t, uint32_t, uint32_t *)'),entry)
        local handle=tonumber(lookup(unit,name,nil))
        if handle==0xFFFFFFFF then return nil end
        return handle
    end
    -- One native call, used only by runtime/event_world.lua (injure) after it re-proved QueueDamage's exact entry bytes,
    -- the queue headroom, that the target is the local player's own living Helldiver avatar and that the actor handle
    -- came from the engine's lookup of one of its limb actors: the game's own QueueDamage(ignored, kind, element,
    -- target, damage, a6, dealer, owner, creditor, a10, f11, f12, f13, a14, a15, actor, a17, a18, f19) with the
    -- template of the game's own VG-70 Variable self-damage (research/player-injury-path-F5FEE03DCFDB.json): kind 6
    -- (Ability), element 0, a6 = 1, floats 0, a14 = (0, 0, -1), a15 = (0, 0, 0), a17 = 9, a18 = 0, f19 = 1.0. Dealer
    -- and owner are the avatar's own network id (a self-inflicted injury); the creditor is the avatar's current last-hit
    -- creditor (the VG-70 call passes that too). The game copies both vectors during the call and applies the event
    -- in its own drain.
    function runtime.native_injure(entry,target,damage,network,creditor_lo,creditor_hi,actor)
        local function half(v)return type(v)=='number'and v>=0 and v<4294967296 and v%1==0 end
        assert(address(entry)and entity_id(target)and type(damage)=='number'and damage>=1 and damage<=100
            and damage%1==0 and type(network)=='number'and network>0 and network<0x7FFF and network%1==0
            and half(creditor_lo)and half(creditor_hi)and half(actor)and actor~=0xFFFFFFFF,'unsupported injury call')
        local direction,position=ffi.new('float[3]',0,0,-1),ffi.new('float[3]',0,0,0)
        local creditor=ffi.new('uint64_t',creditor_hi)*4294967296+creditor_lo
        local queue=ffi.cast(win.fn('void (*)(void *, uint32_t, uint32_t, uint32_t, uint32_t, uint8_t, uint32_t, uint32_t, '
            ..'uint64_t, uint32_t, float, float, float, const float *, const float *, uint32_t, uint32_t, uint32_t, '
            ..'float)'),entry)
        queue(nil,6,0,target,damage,1,network,network,creditor,0,0,0,0,direction,position,actor,9,0,1)
        -- Keeps both vectors referenced until the game returned (it copies them during the call).
        assert(direction~=nil and position~=nil)
        return true
    end
    -- One native call, used only by runtime/event_world.lua (heal_limb) after it re-proved RestoreZone's exact entry
    -- bytes and that the entity is the local player's own living Helldiver avatar with a health record: the game's own
    -- RestoreZone(ignored, entity, zone name) (research/player-avatar-actions-F5FEE03DCFDB.json), with one of the
    -- avatar's six zone names. The function checks neither, so this adapter accepts only those names.
    local AVATAR_ZONES={[0x8C5570C9]=true,[0xAA1DB0B0]=true,[0x1880288E]=true,[0xB6F2BAF5]=true,[0x64A3FA1D]=true,
        [0x87B05FF4]=true}
    function runtime.native_restore_zone(entry,entity,zone)
        assert(address(entry)and entity_id(entity)and AVATAR_ZONES[zone],'unsupported zone restore call')
        local restore=ffi.cast(win.fn('void (*)(void *, uint32_t, uint32_t)'),entry)
        restore(nil,entity,zone)
        return true
    end
    -- One native call, used only by runtime/event_world.lua (add_velocity) after it re-proved SetVelocity's exact entry
    -- bytes and that the entity is the local player's own living Helldiver avatar with a motion record that names it:
    -- the game's own SetVelocity(ignored, entity, v) (research/player-avatar-actions-F5FEE03DCFDB.json). The game copies
    -- the vector during the call.
    function runtime.native_set_velocity(entry,entity,x,y,z)
        local function speed(v)return type(v)=='number'and v==v and math.abs(v)<=100 end
        assert(address(entry)and entity_id(entity)and speed(x)and speed(y)and speed(z)
            and x*x+y*y+z*z<=100*100,'unsupported velocity call')
        local v=ffi.new('float[3]',x,y,z)
        local set=ffi.cast(win.fn('void (*)(void *, uint32_t, const float *)'),entry)
        set(nil,entity,v)
        assert(v~=nil)
        return true
    end
    -- The game's PlayFab lobby member data (research/peer-messaging-F5FEE03DCFDB.json): two slots of the engine's API
    -- table that game.dll itself calls for its own member keys. Used only by runtime/peer_channel.lua after it re-proved
    -- every pin, the table and both slot targets, from the Runtime's own update on the game thread, with the game's
    -- lobby joined (the wrapper's flag, its engine lobby, PlayfabLobby state 3). The key is the Runtime's own one
    -- lowercase name (never one of the game's), the value printable ASCII.
    local function member_key(v)return type(v)=='string'and#v>=1 and#v<=32 and v:match('^[a-z][a-z0-9_]*$')~=nil end
    -- set_member_data(engine lobby, 1, &key, &value): one PFLobbyPostUpdate of this machine's own member property, no
    -- lobby update, a NULL async context (the engine's completion reads none). Returns the HRESULT (0 = queued).
    function runtime.native_lobby_publish(entry,lobby,key,value)
        assert(address(entry)and address(lobby)and member_key(key)and type(value)=='string'and#value>=1
            and#value<=512 and not value:find('[^\32-\126]'),'unsupported lobby publish call')
        local k,v=ffi.new('char[?]',#key+1),ffi.new('char[?]',#value+1)
        ffi.copy(k,key);ffi.copy(v,value)
        local keys,values=ffi.new('const char *[1]'),ffi.new('const char *[1]')
        keys[0],values[0]=k,v
        local publish=ffi.cast(win.fn('int32_t (*)(void *, uint32_t, const char **, const char **)'),entry)
        local result=publish(ffi.cast('void *',lobby),1,keys,values)
        -- Keeps the strings and arrays referenced until the game returned (the SDK copies them during the call).
        assert(k~=nil and v~=nil and keys~=nil and values~=nil)
        return tonumber(result)
    end
    -- member_data(engine lobby, peer, key): a lobby member's property as the SDK holds it. Returns the address of the
    -- SDK's own string (read it at once, through the view) or nil (no such member or property).
    function runtime.native_lobby_read(entry,lobby,peer_lo,peer_hi,key)
        local function half(n)return type(n)=='number'and n>=0 and n<4294967296 and n%1==0 end
        assert(address(entry)and address(lobby)and half(peer_lo)and half(peer_hi)and(peer_lo~=0 or peer_hi~=0)
            and member_key(key),'unsupported lobby read call')
        local k=ffi.new('char[?]',#key+1)
        ffi.copy(k,key)
        local peer=ffi.new('uint64_t',peer_hi)*4294967296+peer_lo
        local read=ffi.cast(win.fn('const char *(*)(void *, uint64_t, const char *)'),entry)
        local value=read(ffi.cast('void *',lobby),peer,k)
        assert(k~=nil)
        if value==nil then return nil end
        return tonumber(ffi.cast('uintptr_t',value))
    end
    return runtime
end
return M
