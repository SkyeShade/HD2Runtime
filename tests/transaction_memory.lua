-- Test-only multi-page runtime for Shield Relay transaction fault injection.
local function record_address(component,key)
    local c=p.components[component]
    local r=p.resources.shield_relay.components[component]
    return 0x100000+c.offset+28+c.record_offset+r.record*c.stride
end
local targets={
    radius={address=record_address('ShieldComponentData')+0,old=string.char(0,0,112,65),new=string.char(0,0,0,65)},
    durability={address=record_address('ShieldComponentData')+76,old=string.char(0,0,122,69),new=string.char(0,64,28,71)},
    lifetime={address=record_address('HellpodPayloadComponentData')+4,old=string.char(0,0,32,66),new=string.char(0,0,180,66)},
    cooldown={address=0x6000000+cooldown_offset+104,old=string.char(0,0,180,66),new=string.char(0,0,52,67)},
}
local allowed={}
local target_pages={}
for name,target in pairs(targets)do
    target.name=name;target.page=target.address-target.address%4096
    allowed[target.address]=target;target_pages[target.page]=true
end
local raw_query=runtime.query
local page_values={}
local writes,protections,logs={},{},{}
runtime.query=function(at)
    local r=raw_query(at)
    if r.state~=0x1000 or r.type~=0x20000 then return r end
    local first,last=r.allocation_base,r.base+r.size
    for page,value in pairs(page_values)do
        if page>=first and page<last then
            if at>=page and at<page+4096 then
                return {base=page,size=4096,allocation_base=r.allocation_base,
                    state=r.state,type=r.type,protect=value}
            end
            if page+4096<=at then r.base=math.max(r.base,page+4096) end
            if page>at then last=math.min(last,page) end
        end
    end
    r.size=last-r.base
    return r
end
runtime.protect=function(page,size,value)
    assert(target_pages[page] and size==4096 and (value==2 or value==4),
        'protection outside reviewed target pages')
    local old=page_values[page] or 2
    protections[#protections+1]={page=page,old=old,value=value}
    if value==2 then page_values[page]=nil else page_values[page]=value end
    return old
end
runtime.write=function(address,bytes)
    local target=assert(allowed[address],'write outside reviewed fields')
    assert(#bytes==4 and runtime.query(address).protect==4,'invalid transaction write')
    writes[#writes+1]={field=target.name,address=address,bytes=bytes}
    replace(address,bytes)
    return true,nil,4
end
hd2=require('hd2runtime/api/session').new(runtime,function(line)logs[#logs+1]=line end)
local function transaction_request()
    return {id='shield-relay-proof',target=hd2.stratagem('Shield Relay'),changes={
        {field='radius',expect=15,value=8},
        {field='durability',expect=4000,value=40000},
        {field='lifetime',expect=40,value=90},
        {field='cooldown',expect=90,value=180},
    }}
end
local function finish(watch,dt)
    for _=1,3000 do
        watch.tick(dt or 0.1)
        if watch.status=='complete' or watch.status=='rejected' or watch.status=='cancelled' then return watch end
    end
    error('guarded operation did not terminate')
end
local function transaction(request)return finish(hd2.transaction(request or transaction_request()))end
local function assert_values(which)
    for _,target in pairs(targets)do assert(runtime.read(target.address,4)==target[which],target.name)end
end
local function protection_is(value)
    for page in pairs(target_pages)do assert((page_values[page] or 2)==value,string.format('page 0x%X',page))end
end
