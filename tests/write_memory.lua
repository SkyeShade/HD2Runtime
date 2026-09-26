-- Test-only writer with real byte mutation and page-granular protection tracking.
local damage_base=0x5000000
local damage_offset=84+16+158*76+12
local target_address=damage_base+damage_offset
local target_page=target_address-target_address%4096
local page_protection=2
local all_writable=false
local writes,protections,logs={},{},{}
local raw_query=runtime.query
runtime.query=function(at)
    local r=raw_query(at)
    if r.allocation_base==damage_base then
        if all_writable then r.protect=4
        elseif page_protection~=2 then
            if at<target_page then r.size=target_page-r.base
            elseif at<target_page+4096 then r.base=target_page;r.size=4096;r.protect=page_protection
            else local ending=r.base+r.size;r.base=target_page+4096;r.size=ending-r.base end
        end
    end
    return r
end
runtime.protect=function(at,n,value)
    assert(at==target_page and n==4096,'changed a non-target page')
    local old=page_protection;page_protection=value
    protections[#protections+1]={address=at,size=n,value=value,old=old}
    return old
end
runtime.write=function(at,bytes)
    assert(runtime.query(at).protect==4,'write without writable page')
    assert(at==target_address and #bytes==12,'write outside logical AP field')
    writes[#writes+1]={address=at,bytes=bytes}
    replace(at,bytes)
    return true,nil,#bytes
end
hd2=require('hd2runtime/api/session').new(runtime,function(line)logs[#logs+1]=line end)
local function request()
    return {id='jar5-ap4',target=hd2.weapon('JAR-5 Dominator'):projectile():damage(),
        field='armor_penetration',expect=3,value=4}
end
local function patch()
    local w=hd2.patch(request())
    for _=1,1000 do
        w.tick(0.1)
        if w.status=='complete' or w.status=='rejected' then return w end
    end
    error('patch did not terminate')
end
local old=string.rep(u32(3),3)
local desired=string.rep(u32(4),3)
