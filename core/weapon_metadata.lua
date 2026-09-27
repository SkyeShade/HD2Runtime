-- Read-only, schema-bounded weapon-level metadata derived from reviewed components.
local b=require('hd2runtime/core/bytes')
local M={}

local function integral(value)
    return type(value)=='number'and value>=0 and value<=100000 and value%1==0
end

function M.weapon_slot(loadout_bytes,schema)
    if not loadout_bytes then return nil,{status='UNCLASSIFIED'}end
    local tag=b.u32(loadout_bytes,schema.fields.weapon_slot.offset)
    local slot=schema.fields.weapon_slot.tags[tag]
    if not slot then return nil,{status='UNCLASSIFIED',bundleTag=string.format('0x%08X',tag)}end
    return slot,{status='RESOLVED',bundleTag=string.format('0x%08X',tag),
        source='LoadoutPackageComponentData.BundleTag'}
end

function M.default_magazine_customization(customization_bytes,schema)
    if not customization_bytes then return nil end
    local field=schema.fields.capacity.default_customizations
    for index=0,field.count-1 do
        local at=field.offset+index*field.stride
        local slot=b.u32(customization_bytes,at)
        if slot==field.none then return nil end
        if slot==field.magazine then
            local id=b.u32(customization_bytes,at+4)
            if id~=0 then return {slot=slot,id=id,recordIndex=index}end
        end
    end
    return nil
end

function M.capacity(records,schema)
    records=records or{}
    local field=schema.fields.capacity
    local rounds=records.WeaponRoundsComponentData
    if rounds then
        local values,value={},0
        for index=0,(field.rounds.count or 1)-1 do
            local item=b.value(rounds,field.rounds.offset+index*(field.rounds.stride or 4),'f32')
            assert(integral(item),'WeaponRounds magazine capacity is not a bounded integer')
            values[#values+1]=item;value=value+item
        end
        assert(integral(value),'WeaponRounds summed magazine capacity is not a bounded integer')
        return {status='RESOLVED',value=value,baseValue=value,feedValues=values,
            transformation=field.rounds.transformation or'identity',
            chambered=rounds:byte(field.rounds.chambered_offset+1)~=0,
            source='WeaponRoundsComponentData.MagazineCapacity'}
    end
    local magazine=records.WeaponMagazineComponentData
    if not magazine then return {status='UNMAPPED',reason='no reviewed magazine/feed component'}end
    local value=b.u32(magazine,field.magazine.offset)
    assert(integral(value),'WeaponMagazine capacity outside bounded integer range')
    local customization=M.default_magazine_customization(
        records.WeaponCustomizationComponentData,schema)
    if customization then
        return {status='CUSTOMIZED_UNRESOLVED',baseValue=value,
            chambered=magazine:byte(field.magazine.chambered_offset+1)~=0,
            defaultMagazineCustomization=string.format('0x%08X',customization.id),
            reason='effective capacity is supplied by a default magazine customization AddPath'}
    end
    return {status='RESOLVED',value=value,baseValue=value,transformation='identity',
        chambered=magazine:byte(field.magazine.chambered_offset+1)~=0,
        source='WeaponMagazineComponentData.Capacity'}
end

local family_components={
    {'ArcWeaponComponentData','arc'},
    {'BeamWeaponComponentData','beam'},
    {'MeleeWeaponComponentData','melee'},
    {'ProjectileWeaponComponentData','conventional_projectile'},
    {'SprayWeaponComponentData','spray_flame'},
    {'WeaponRoundsComponentData','rounds_feed'},
}
function M.implementation_families(ownership)
    local result={}
    for _,item in ipairs(family_components)do
        if ownership[item[1]]then result[#result+1]=item[2]end
    end
    if #result==0 and ownership.WeaponDataComponentData then result[1]='special_or_non_damaging'end
    return result
end
return M
