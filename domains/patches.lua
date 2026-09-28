-- Reviewed logical write fields; no addresses. Derived from retained JAR-5 records.
local b=require('hd2runtime/core/bytes')
local M={}
local projectile=b.unhex('b10000006faf2f1e08cd3b206952cdf1f5c84b7d5898656a0000704101000000000034430000c842000000009a99993e010000000000000000000000990000000000803e00000000b4494e1ae9d8d1a400000000000000000ad7233c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000a0420100000000000000000000000000000000000000cdcccc3dcdcccc3d0400000003000000010000000000a642000070420000403f0000004000004041ebe6fa54116ee98c0000000000000000000080bf0000000000000000000000000200000000000000390000000000000018953d390000000000000000000000000000000000000000')
local damage=b.unhex('99000000130100005a000000030000000300000003000000000000000a000000230000000f000000000000000000000000000000000000000000000000000000000000000000000000000000')
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
function M.validate(request)
    local domains=require('hd2runtime/domains/write_domains')
    if type(request)=='table'and type(request.target)=='table'
        and domains.typed_resource(request.target.resource)then
        return domains.for_resource(request.target.resource).validate_patch(request)
    end
    assert(type(request)=='table','patch requires a descriptor')
    local allowed={id=true,target=true,field=true,expect=true,value=true,diagnostic=true}
    for key in pairs(request)do assert(allowed[key],'unsupported patch option: '..tostring(key))end
    assert(type(request.id)=='string' and #request.id>0 and #request.id<=64
        and not request.id:find('[^%w_%-]'),'invalid patch id')
    local t=request.target
    assert(type(t)=='table' and t.resource=='jar5' and t.path=='damage','unsupported patch target')
    for key in pairs(t)do assert(key=='resource' or key=='path','unsupported target identity')end
    assert(request.field=='armor_penetration','field is not enabled for guarded writes')
    assert(request.expect==3 and request.value==4,'only reviewed JAR-5 AP3 to AP4 is enabled')
    assert(request.diagnostic==nil or type(request.diagnostic)=='boolean','invalid diagnostic flag')
    return {id=request.id,field=request.field,expect=request.expect,value=request.value,
        diagnostic=request.diagnostic==true}
end
function M.requests(spec)
    if spec.kind=='player_weapon'then return nil end
    return {{key='jar5',fields={'armor_penetration'}}}
end
function M.prepare(resolved,reader,spec)
    local r=resolved.record('jar5','DamageSettings')
    local pr=resolved.roots.projectile.records[177]
    assert(pr.bytes==projectile,'projectile record differs from reviewed original')
    assert(#r.bytes==76 and r.bytes:sub(1,12)==damage:sub(1,12)
        and r.bytes:sub(25)==damage:sub(25),'non-target damage record differs from reviewed original')
    local old=string.rep(u32(spec.expect),3)
    local new=string.rep(u32(spec.value),3)
    local current=r.bytes:sub(13,24)
    assert(current==old or current==new,'CONFLICT: AP lanes are neither expected nor desired')
    local owner=resolved.roots.damage.owner
    return {owner=owner,offset=r.offset+12,old=current,new=new,snapshots=reader.snapshots,
        identity=r.identity,chain=r.chain,already_desired=current==new}
end
return M
