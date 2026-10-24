-- Synthetic byte-addressed world. No FFI, native calls, process IO or game start.
-- The projectile/health layouts, byte encoders, steering engine and guarded
-- transaction are real. Only event_world reads, scheduler and OS memory are fake.
local bytes=require('hd2runtime/core/bytes')
local domain=require('hd2runtime/domains/projectile_homing')
local rows=require('hd2runtime/domains/projectile_rows')
local natives=require('hd2runtime/domains/event_natives')
local PO,F,H,FL=rows.pool,domain.flight,rows.pool.hit,rows.pool.flags
local weapon
for _,w in ipairs(domain.weapons)do if w.name=='AR-23 Liberator'then weapon=w end end
assert(weapon and weapon.types[1]==276 and weapon.sources[1]=='968211C0033DCE64')

return function(opts)
    opts=opts or{}
    local f={counter=0,writes={},allocations={},write_events={},logs={},alive=true,locked=opts.locked~=false,
             ready=true,session='session1',
             players=opts.players or 1,base=0x10000000,size=0x200000,system=0x10000000,mem={},PO=PO,F=F,H=H}
    local function put(at,value)for i=1,#value do f.mem[at+i-1]=value:sub(i,i)end end
    local function read(at,size)
        assert(at>=f.base and at+size<=f.base+f.size,'fixture read outside synthetic pool')
        local out={};for i=0,size-1 do out[#out+1]=f.mem[at+i]or'\0'end;return table.concat(out)
    end
    local function scalar(at,value,kind)put(at,bytes.encode(value,kind or'u32'))end
    f.read,f.put,f.scalar=read,put,scalar
    f.address=function(slot)return f.system+PO.flight.base+slot*PO.flight.stride end
    f.velocity=function(slot)
        local data=read(f.address(slot)+F.velocity,12)
        return bytes.value(data,0,'f32'),bytes.value(data,4,'f32'),bytes.value(data,8,'f32')
    end
    f.records=function(slot)
        return {flight=read(f.address(slot),F.read),hit=read(f.system+H.base+slot*H.stride,H.stride),
            source=read(f.system+PO.source.base+slot*PO.source.stride,PO.source.stride),
            kind=read(f.system+PO.types.base+slot*PO.types.stride,PO.types.stride),
            flags=read(f.system+FL.base+slot*FL.stride,FL.stride)}
    end
    f.spawn=function(spec)
        spec=spec or{};local slot=f.counter%PO.slots;f.counter=f.counter+1
        local flight=f.address(slot);put(flight,string.rep('\0',PO.flight.stride))
        scalar(flight+F.velocity,100,'f32');scalar(flight+F.speed,100,'f32')
        scalar(flight+F.distance,10,'f32');scalar(flight+F.unit,spec.unit or 0)
        local hit=f.system+H.base+slot*H.stride;put(hit,string.rep('\0',H.stride))
        scalar(hit+H.creditor,spec.peer or 55);scalar(hit+H.creditor+4,66);scalar(hit+H.owner,77)
        scalar(f.system+PO.source.base+slot*PO.source.stride+PO.source.entity,spec.source or 10)
        scalar(f.system+PO.types.base+slot*PO.types.stride,spec.kind or weapon.types[1])
        put(f.system+FL.base+slot*FL.stride,string.char(FL.inFlight,0))
        return slot
    end
    local runtime={}
    runtime.query=function(at)
        if at<f.base or at>=f.base+f.size then return nil end
        return {base=f.base,size=f.size,allocation_base=f.base,state=0x1000,type=0x20000,protect=4}
    end
    runtime.read=function(at,size)
        if f.race then local race=f.race;f.race=nil;scalar(race,999)end
        return read(at,size)
    end
    runtime.write=function(at,data)
        assert(at>=f.base and at+#data<=f.base+f.size,'write outside synthetic memory')
        f.writes[#f.writes+1]={at=at,data=data};put(at,data);return true,nil,#data
    end
    runtime.system_info=function()return 4096 end
    runtime.protect=function()error('private RW synthetic pool needs no protection changes')end
    local view={read=read,u32=function(at)return bytes.u32(read(at,4),0)end,slot=function()return{}end}
    view.fill=function(slot,at,size)
        local data=read(at,size)
        return {u32=function(_,offset)return bytes.u32(data,offset)end,
            ptr=function(_,offset)return bytes.pointer(data,offset)end}
    end
    local proofs={}
    for _,pin in ipairs(domain.pins)do proofs[pin.rva]=pin.hex end
    view.proves=function(at,hex)return proofs[at-0x80000000]==hex end
    local world={key='synthetic-world',view=view,runtime=runtime,game=0x80000000}
    f.world=world
    local targets={}
    local D,R=natives.health.descriptor,natives.health.record
    local header={buckets=f.base+0x100000,descriptors=f.base+0x101000,records=f.base+0x102000,
        live=3,hash_capacity=3,hash_empty=4294967295}
    for index=0,2 do
        local entity,unit=20+index,30+index
        local target={entity=entity,unit=unit,name='synthetic enemy '..index,x=100,y=20+index*10,z=0}
        targets[#targets+1]=target
        scalar(header.buckets+index*8,entity);scalar(header.buckets+index*8+4,index)
        local desc=f.base+0x104000+index*0x100
        scalar(header.descriptors+index*8,desc);scalar(header.descriptors+index*8+4,0)
        scalar(desc+D.type,1234);scalar(desc+D.type+4,0);scalar(desc+D.entity,entity);scalar(desc+D.unit,unit)
        scalar(header.records+index*natives.health.stride+R.life,0)
    end
    f.targets=targets
    local w={open=function()return world end,game_state=function()return{mission=true,host=true,mode_entity=99}end,
        prove_projectile_pool=function()return true end,projectile_counter=function()return f.counter,f.system end,
        local_peer=function()return 55,66 end,health_header=function()return header end,
        equipped=function()return{entity=10,type=weapon.sources[1]}end,
        entity_type=function(_,entity)return entity==10 and weapon.sources[1]or'FFFFFFFFFFFFFFFF'end,
        type_info=function()return{kind='enemy',display='synthetic enemy'}end,
        entity_exists=function()return f.alive end,
        unit_position=function(_,unit)
            for _,target in ipairs(targets)do if target.unit==unit then return target end end
        end}
    w.players=function()
        local out={{['local']=true,avatar=1,peer='local-peer'}}
        for i=2,f.players do out[#out+1]={['local']=false,avatar=i,peer=55+i}end
        return out
    end
    w.projectile_types=function(_,system,first,count)
        if f.unreadable_slots then return nil end
        local out={}
        for n=first,first+count-1 do
            local slot=n%PO.slots
            out[#out+1]={slot=slot,type=view.u32(system+PO.types.base+slot*PO.types.stride)}
        end
        return out
    end
    w.entity_unit=function(_,entity)return entity end
    w.unit_pose=function()return{position={x=0,y=0,z=0},forward={x=1,y=0,z=0}}end
    w.entity_network=function(_,entity)return entity end
    w.entity_state=function(_,entity)
        for i,t in ipairs(targets)do if t.entity==entity then return{life=f.alive and 0 or 2,
            descriptor={pointer=f.base+0x104000+(i-1)*0x100,unit=t.unit}}end end
    end
    f.world_api=w
    package.loaded['hd2runtime/runtime/event_world']=w
    package.loaded['hd2runtime/runtime/scheduler']={attach=function(watch)f.watch=watch end}
    package.loaded['hd2runtime/runtime/log']={emit=function(t)f.logs[#f.logs+1]=t end,
        detail=function(t)f.logs[#f.logs+1]=t end}
    package.loaded['hd2runtime/runtime/projectile_homing']=nil
    local engine=require('hd2runtime/runtime/projectile_homing');f.engine=engine
    f.config=assert(engine.configure({owner='ar23_homing',output='fixture.ar23',weapon=weapon.name,
        type=weapon.types[1],sources=weapon.sources,target='enemy',turn_rate=math.rad(90),cone=math.rad(30),
        range=200,arm_distance=0,aim_height=0,retarget=false,multiplayer=false}))
    engine.step(0.016) -- Establish the spawn counter baseline before firing.
    engine.step(0.016) -- Establish the controller session before firing.
    return f
end
