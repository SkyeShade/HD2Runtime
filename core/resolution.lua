local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local Entity=require('hd2runtime/core/entity')
local Stratagem=require('hd2runtime/core/stratagem')
local profile=require('hd2runtime/schemas/current')
local catalog=require('hd2runtime/domains/catalog')
local M={}
function M.capture(runtime,reader,requested)
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={entity=true}
    local wants_stratagem=false
    for _,target in ipairs(requested)do
        target.key=assert(target.key,'internal resource key required')
        assert(type(target.fields)=='table' and #target.fields>0,'target requires fields')
        for _,name in ipairs(target.fields)do
            local f=assert(catalog[target.key][name],'unknown field: '..tostring(name))
            if target.component then assert(target.component==f.component,'component identity mismatch')end
            if f.component=='DamageSettings' then
                needed.damage=true
                if target.key=='jar5' then needed.projectile=true end
            end
            if f.component=='StratagemSettings' then wants_stratagem=true end
        end
    end
    local roots=discover.locate(runtime,reader,profile,needed)
    local resolve=Entity.new(reader,roots.entity,profile)
    local stratagem=wants_stratagem and Stratagem.capture(runtime,reader,profile) or nil
    local function record(key,component)
        if component=='StratagemSettings' then
            -- Also prove that the named payload is a current entity member.
            local payload=resolve(key,'HellpodPayloadComponentData')
            stratagem.chain={payload.identity,stratagem.identity}
            return stratagem
        end
        if component~='DamageSettings' then return resolve(key,component)end
        local kind,chain
        if key=='jar5' then
            local weapon=resolve(key,'ProjectileWeaponComponentData')
            assert(b.u32(weapon.bytes,0)==177,'projectile link changed')
            local projectile=assert(roots.projectile.records[177],'projectile record absent')
            assert(projectile.group==0 and projectile.row==262,'projectile record identity changed')
            kind=b.u32(projectile.bytes,60)
            assert(kind==153,'projectile damage link changed')
            local consumers=0
            for _,r in pairs(roots.projectile.records)do if b.u32(r.bytes,60)==kind then consumers=consumers+1 end end
            assert(consumers==1,'JAR-5 damage has multiple projectile consumers')
            chain={weapon.identity,{component='ProjectileSettings',component_type=projectile.settings_type,
                record_index=projectile.row,group=projectile.group,record_kind=177,
                unique_owner=true,owner_count=1,scope='unique typed settings record'}}
        else
            local orbital=resolve(key,'OrbitalAbilityComponentData')
            kind=b.u32(orbital.bytes,476)
            assert(kind==513,'orbital damage link changed')
            chain={orbital.identity}
        end
        local r=assert(roots.damage.records[kind],'linked damage record absent')
        assert(r.group==1 and r.row==(key=='jar5' and 158 or 504),'damage record identity changed')
        r.identity={component='DamageSettings',component_type=r.settings_type,record_type='DamageInfo',
            record_index=r.row,group=r.group,record_kind=kind,unique_owner=true,owner_count=1,
            scope='unique typed record and checked resource linkage; not all consumers'}
        chain[#chain+1]=r.identity;r.chain=chain
        return r
    end
    return {roots=roots,record=record}
end
return M
