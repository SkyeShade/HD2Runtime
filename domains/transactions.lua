-- Reviewed transaction fields. Values are encoded here before any runtime access.
local b=require('hd2runtime/core/bytes')
local catalog=require('hd2runtime/domains/catalog')
local M={}
local map={
    radius={component='ShieldComponentData',offset=0,expect=15,value=8,
        old='00007041',new='00000041'},
    durability={component='ShieldComponentData',offset=76,expect=4000,value=40000,
        old='00007a45',new='00401c47'},
    lifetime={component='HellpodPayloadComponentData',offset=4,expect=40,value=90,
        old='00002042',new='0000b442'},
    cooldown={component='StratagemSettings',offset=104,expect=90,value=180,
        old='0000b442',new='00003443'},
}
local function target_ok(t)
    if type(t)~='table' or t.resource~='shield_relay' or t.path~='stratagem' then return false end
    for key in pairs(t)do if key~='resource' and key~='path' then return false end end
    return true
end
function M.validate(request)
    local domains=require('hd2runtime/domains/write_domains')
    if type(request)=='table'and type(request.target)=='table'
        and domains.typed_resource(request.target.resource)then
        return domains.for_resource(request.target.resource).validate_transaction(request)
    end
    assert(type(request)=='table','transaction requires a descriptor')
    local allowed={id=true,target=true,changes=true,diagnostic=true}
    for key in pairs(request)do assert(allowed[key],'unsupported transaction option: '..tostring(key))end
    assert(type(request.id)=='string' and #request.id>0 and #request.id<=64
        and not request.id:find('[^%w_%-]'),'invalid transaction id')
    assert(target_ok(request.target),'unsupported transaction target')
    assert(type(request.changes)=='table' and #request.changes>=1 and #request.changes<=4,
        'transaction requires one to four reviewed changes')
    assert(request.diagnostic==nil or type(request.diagnostic)=='boolean','invalid diagnostic flag')
    local result={id=request.id,resource='shield_relay',diagnostic=request.diagnostic==true,changes={}}
    local seen={}
    for index,item in ipairs(request.changes)do
        assert(type(item)=='table','transaction change must be a descriptor')
        for key in pairs(item)do assert(key=='field' or key=='expect' or key=='value',
            'unsupported transaction change option: '..tostring(key))end
        local reviewed=assert(map[item.field],'field is not enabled for guarded transactions')
        assert(not seen[item.field],'duplicate transaction field: '..item.field);seen[item.field]=true
        assert(item.expect==reviewed.expect and item.value==reviewed.value,
            'unreviewed transaction values for '..item.field)
        result.changes[index]={field=item.field,component=reviewed.component,offset=reviewed.offset,
            expect=item.expect,value=item.value,expected=b.unhex(reviewed.old),desired=b.unhex(reviewed.new)}
    end
    return result
end
function M.requests(spec)
    if spec.kind=='player_weapon'then return nil end
    local fields={}
    for _,change in ipairs(spec.changes)do fields[#fields+1]=change.field end
    return {{key=spec.resource,fields=fields}}
end
function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots}
    for index,change in ipairs(spec.changes)do
        local described=assert(catalog[spec.resource][change.field],'reviewed field missing from catalog')
        assert(described.component==change.component and described.offset==change.offset
            and described.storage=='f32' and described.expected==change.expect,
            'transaction field schema changed: '..change.field)
        local record=resolved.record(spec.resource,change.component)
        assert(record.owner and type(record.offset)=='number','resolved record lacks internal ownership')
        local current=record.bytes:sub(change.offset+1,change.offset+4)
        assert(#current==4,'transaction field outside record')
        if current~=change.expected and current~=change.desired then
            error('CONFLICT: '..change.field..' is neither expected nor desired',0)
        end
        if change.field=='cooldown' then
            assert(record.bytes:sub(85,88)==string.rep('\0',4)
                and record.bytes:sub(109,112)==string.rep('\0',4),
                'cooldown adjacent fields changed')
        end
        plan.changes[index]={label=change.field,owner=record.owner,
            offset=record.offset+change.offset,expected=change.expected,desired=change.desired,
            before=current,already_desired=current==change.desired,identity=record.identity,
            chain=record.chain,expect=change.expect,value=change.value}
    end
    return plan
end
return M
