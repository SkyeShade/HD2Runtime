-- Reviewed semantic player-weapon writes. Runtime addresses never enter this database or public API.
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
local database=require('hd2runtime/domains/player_weapon_authoring')
local status_catalog=require('hd2runtime/domains/status_catalog')
local support_database=require('hd2runtime/domains/support_weapon_authoring')
-- Mounted weapons (vehicles, Exosuits, GATER) share the support-weapon entry shape.
local vehicle_database=require('hd2runtime/domains/vehicle_weapon_authoring')
-- Acknowledgements a later SDK added, which a mod declaring an older SDK need not carry (docs/legacy-sdk-compatibility.md).
local sdk_compatibility=require('hd2runtime/core/sdk_compatibility')
local function database_for(kind)
    if kind=='vehicle_weapon'then return vehicle_database end
    return kind=='support_weapon'and support_database or database
end
local M={}
-- Catalogued attack outputs, projectile sources and ammunition sources (domains/attack_outputs.lua).
local function attack_outputs()return require('hd2runtime/domains/attack_outputs')end
-- Package the source weapon's projectile/explosion assets live in (its generated loadout package), when the
-- source is another weapon whose package differs from the target's. Unknown sources return nil.
local function source_dependency(target_name,source_name,attack)
    if source_name==target_name then return nil end
    local assets=require('hd2runtime/core/assets')
    local function lookup(name)
        return assets.dependency('projectile_source/'..name..':'..tostring(attack))
            or assets.dependency('player_weapon/'..name)or assets.dependency('support_weapon/'..name)
    end
    local source,target=lookup(source_name),lookup(target_name)
    if source and target and source.package==target.package then return nil end
    return source
end
-- Package of a catalogued attack output: a weapon-owned output resolves like its owner weapon (nil when it shares the
-- target's package); a stratagem-owned donor by its own catalogued key (the entity that fires it owns the package).
local function output_dependency(target_name,output)
    -- A spare twin resolves like its twin's owner (their rows are byte-identical outside the references).
    local owner=output.dependencyOwner or output.owner
    if owner.kind=='player_weapon'or owner.kind=='support_weapon'then
        return source_dependency(target_name,owner.name,'primary')
    end
    return assert(require('hd2runtime/core/assets').dependency(output.dependencyKey),
        'ASSET_UNAVAILABLE: no catalogued package for attack output '..output.id)
end
-- An output catalogued for particular fields only (referenceScope) is refused everywhere else.
-- A donor catalogued without a live test (research/projectile-donors: Eagle payloads, orbital shells, sentry rounds,
-- weapons' second projectiles) needs both acknowledgements, whatever its class.
local function require_unverified_donor(output,allow_unverified_reference,allow_unverified_effect)
    if not output.unverifiedDonor then return end
    assert(allow_unverified_reference,'this donor is not live-tested yet and requires allow_unverified_reference=true: '
        ..output.id)
    assert(allow_unverified_effect,'this donor is not live-tested yet and requires allow_unverified_effect=true: '
        ..output.id)
end
local function require_output_scope(output,field_id)
    if not output.referenceScope then return end
    for _,allowed in ipairs(output.referenceScope)do if allowed==field_id then return end end
    error('OUTPUT_SCOPE: '..output.id..' is catalogued only for '..table.concat(output.referenceScope,', ')
        ..' (see sdk/AttackOutputCapabilities.json)',0)
end
local component_names={'ProjectileWeaponComponentData','WeaponDataComponentData',
    'WeaponMagazineComponentData','WeaponRoundsComponentData','ArcWeaponComponentData',
    'MeleeWeaponComponentData','BeamWeaponComponentData','SprayWeaponComponentData',
    'WeaponHeatComponentData','WeaponChargeComponentData','ExplosiveComponentData',
    'HellpodRackComponentData','WeaponLinkedAmmoComponentData','WeaponReloadComponentData',
    'WeaponWindUpComponentData','HealthComponentData','MountComponentData','LoadoutEntryComponentData',
    'DepositComponentData'}
-- Weapons whose default ammunition owns the fired projectile also re-prove their default customization.
local ammunition_component_names={}
for index,name in ipairs(component_names)do ammunition_component_names[index]=name end
ammunition_component_names[#ammunition_component_names+1]='WeaponCustomizationComponentData'

local function equal(a,c,kind)
    if kind=='f32'then return type(a)=='number'and type(c)=='number'
        and math.abs(a-c)<=math.max(0.000001,math.abs(c)*0.000001)end
    return a==c
end
local function target_name(target)
    assert(type(target)=='table'and(target.resource=='player_weapon'
        or target.resource=='support_weapon'or target.resource=='vehicle_weapon')and type(target.weapon)=='string',
        'unsupported weapon target')
    local kind=target.resource
    if target.path=='ammunition'then
        -- A weapon's default ammunition: the active projectile source when its delta patches ProjectileWeapon +0.
        assert(kind=='player_weapon','ammunition targets are player weapons')
        for key in pairs(target)do assert(key=='resource'or key=='path'or key=='weapon',
            'unsupported ammunition target identity')end
        return target.weapon,'primary','ammunition',nil,kind
    end
    if target.path=='weapon'then
        for key in pairs(target)do assert(key=='resource'or key=='path'or key=='weapon',
            'unsupported player weapon target identity')end
        return target.weapon,nil,'weapon',nil,kind
    end
    assert((target.path=='attack'or target.path=='projectile_reference'
        or target.path=='terminal_action'or target.path=='explosion')
        and type(target.attack)=='string','unsupported weapon target')
    if target.path=='terminal_action'or(target.path=='explosion'and kind=='player_weapon')then
        assert(target.phase=='impact'or target.phase=='expiry','unsupported terminal action phase')
    end
    for key in pairs(target)do assert(key=='resource'or key=='path'or key=='weapon'or key=='attack'
        or key=='phase','unsupported player weapon target identity')end
    return target.weapon,target.attack,target.path,target.phase,kind
end
local function canonical_explosion_phase(weapon,role,phase)
    local graph=assert(require('hd2runtime/domains/player_weapon_composition').weapons[weapon.name])
    local attack=assert(graph.attacks[role]);local action=assert(attack.terminal_actions[phase])
    for _,candidate in ipairs({'impact','expiry'})do
        local other=attack.terminal_actions[candidate]
        if other and other.reference_type==action.reference_type then return candidate end
    end
    return phase
end
-- The branch names an attack's projectile-object fields may use: the role itself and, for rounds-fed attacks
-- (feed_primary / feed_alternate), the branch without the feed_ prefix. A weapon with two feeds (SG-20 Halt) names
-- them damage.primary.*, damage.alternate.*; the generic field on attack('feed_primary'):projectile() must resolve to
-- them. A stripped branch is accepted only when the field's backing branch is that feed.
local function branch_field(weapon,domain,role,rest)
    local feed=type(role)=='string'and role:match('^feed_(%a+)$')
    for _,branch in ipairs({role,feed})do
        local candidate=domain..'.'..branch..'.'..rest
        for _,field in ipairs(weapon.fields)do
            if field.semanticFieldId==candidate and(branch==role
                or field.backing and(field.backing.branch==branch or field.backing.branch==role))then
                return candidate
            end
        end
    end
end
-- A field the catalog publishes as refused on this weapon (fieldRefusals) names its reason.
local function not_exposed(weapon,id)
    local reason=weapon.fieldRefusals and weapon.fieldRefusals[id]
    error('field is not exposed for '..weapon.name..': '..tostring(id)..(reason and(' ('..reason..')')or''),0)
end
local function field_for(weapon,id,role,path,phase)
    local resolved=id
    if path=='ammunition'then
        assert(id=='ammunition.projectile','ammunition targets only accept hd2.fields.ammunition.projectile')
        return assert(attack_outputs().ammunition[weapon.name],'NO_AMMUNITION_SOURCE: '..weapon.name
            ..' has no reviewed default ammunition that owns its fired projectile (see attack:projectile_source())')
    end
    if weapon.supportWeapon then
        if id=='attack.projectile'then
            assert(type(role)=='string','attack.projectile requires weapon:attack(role) target')
            resolved='attack.'..role..'.projectile'
        elseif path=='projectile_reference'and id:match('^projectile%.')then
            resolved='projectile.'..role..'.'..id:sub(#'projectile.'+1)
        elseif path=='projectile_reference'and id:match('^damage%.')then
            resolved='damage.'..role..'.'..id:sub(#'damage.'+1)
        elseif path=='explosion'and id:match('^explosion%.damage%.')then
            resolved='explosion.'..role..'.damage.'..id:sub(#'explosion.damage.'+1)
        elseif path=='explosion'and id:match('^explosion%.')then
            resolved='explosion.'..role..'.'..id:sub(#'explosion.'+1)
        elseif path=='attack'and(id:match('^damage%.')or id:match('^arc%.')
            or id:match('^beam%.')or id:match('^status%.'))then
            local domain=id:match('^([^.]+)')
            resolved=domain..'.'..role..'.'..id:sub(#domain+2)
        end
        for _,field in ipairs(weapon.fields)do if field.semanticFieldId==resolved then return field end end
        not_exposed(weapon,id)
    end
    if id=='attack.projectile'then
        assert(type(role)=='string','attack.projectile requires weapon:attack(role) target')
        resolved='attack.'..role..'.projectile'
    elseif id=='terminal.explosion'then
        resolved='terminal.'..role..'.'..phase..'.explosion'
    elseif path=='projectile_reference'and id:match('^projectile%.')then
        resolved=branch_field(weapon,'projectile',role,id:sub(#'projectile.'+1))or resolved
    elseif path=='projectile_reference'and id:match('^damage%.')then
        resolved=branch_field(weapon,'damage',role,id:sub(#'damage.'+1))or resolved
    elseif path=='explosion'and id:match('^explosion%.')
        and not id:match('^explosion%.[^.]+%.impact%.')
        and not id:match('^explosion%.[^.]+%.expiry%.')then
        local rest=canonical_explosion_phase(weapon,role,phase)..'.'..id:sub(#'explosion.'+1)
        resolved=branch_field(weapon,'explosion',role,rest)or('explosion.'..role..'.'..rest)
    end
    for _,field in ipairs(weapon.fields)do if field.semanticFieldId==resolved then return field end end
    not_exposed(weapon,id)
end
local function identical_backing(a,c)
    if type(a)~='table'or type(c)~='table'or a.kind~=c.kind
        or a.offset~=c.offset or a.width~=c.width or a.storage~=c.storage then return false end
    if a.kind=='component'then return a.component==c.component and a.recordIndex==c.recordIndex
        and a.indexRow==c.indexRow end
    return a.settings==c.settings and a.group==c.group and a.row==c.row
        and a.recordType==c.recordType and a.settingsType==c.settingsType
end
local function scalar(field,value,label)
    if field.type=='boolean'then
        assert(type(value)=='boolean',label..' must be boolean')
        -- Enum-backed booleans (third-person reticle) encode per weapon; plain flags are 0/1.
        if field.encoding then return assert(field.encoding[value and'on'or'off'],'boolean encoding missing')end
        return value and 1 or 0
    end
    assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
        label..' must be finite number')
    if field.type=='integer'then assert(value%1==0,label..' must be integer')end
    return value
end
-- An ordered fire-mode list (first = default) as the four packed native FireMode slots.
local function mode_set(field,value,label)
    assert(type(value)=='table'and getmetatable(value)==nil,label..' must be a list of fire mode names')
    local count=0;for _ in pairs(value)do count=count+1 end
    assert(count==#value and#value>=1,label..' must list at least one fire mode')
    assert(#value<=field.maxModes,label..' lists '..#value..' modes; this weapon allows '..field.maxModes
        ..(field.maxModes==1 and' (no fire-mode selector is bound)'or''))
    local seen,bytes={},{}
    for index,name in ipairs(value)do
        local native=field.modeValues[name]
        assert(native,label..' names an unsupported fire mode: '..tostring(name))
        assert(not seen[name],label..' lists '..name..' twice');seen[name]=true
        bytes[index]=b.encode(native,'u32')
    end
    for index=#value+1,4 do bytes[index]=b.encode(0,'u32')end
    return table.concat(bytes)
end
-- Native slot lists written slot by slot: every slot is conflict-checked, only changed slots are written, and no
-- write crosses a slot. fire_mode_set: four FireMode slots; fire_rate_set: the three rate-of-fire slots X/Y/Z;
-- trait_set and armor_penetration_label: the five LoadoutEntry trait tags.
-- weapon_sound: the loop start / loop stop / per-shot event slots (+252/+256/+260; its +237 MIDI flag is one more
-- 1-byte change).
local SLOT_SETS={fire_mode_set=4,fire_rate_set=3,trait_set=5,armor_penetration_label=5,weapon_sound=3}
-- Rate-of-fire modes: the three native slots in the order the weapon menu lists them (X, Y, Z). The middle slot (Y) is
-- the default a weapon is built on; 0 is an empty slot, which the menu and the selector skip. The selector visits the
-- slots Y -> Z -> X.
local function plain_list(value,label,noun)
    assert(type(value)=='table'and getmetatable(value)==nil,label..' must be a list of '..noun)
    local count=0;for _ in pairs(value)do count=count+1 end
    assert(count==#value,label..' must be a list of '..noun)
end
local RATE_SLOT_NAMES={'X','Y','Z'}
local function rate_set(field,value,label)
    plain_list(value,label,'three rates of fire (rounds per minute)')
    assert(#value==3,label..' must list the three rate slots in weapon-menu order {X, Y, Z} (0 = no mode in that slot); '
        ..'got '..#value..(#value==1 and' entry'or' entries'))
    local rates=0
    for index,rate in ipairs(value)do
        local slot=RATE_SLOT_NAMES[index]
        assert(type(rate)=='number'and rate==rate and rate>-math.huge and rate<math.huge,
            label..' slot '..slot..' must be a finite number')
        if rate~=0 or index==2 then
            assert(rate>=field.min and rate<=field.max,label..' slot '..slot..' is outside the reviewed range '
                ..field.min..' to '..field.max..' rounds per minute'..(index==2 and' (Y is the default rate and '
                ..'cannot be empty)'or' (0 = no mode)'))
            rates=rates+1
        end
    end
    assert(rates<=field.maxModes,label..' lists '..rates..' rates; this weapon allows '..field.maxModes
        ..(field.maxModes==1 and' (no rate-of-fire selector can be bound: X and Z stay 0)'or' (three native slots)'))
    return b.encode(value[1],'f32')..b.encode(value[2],'f32')..b.encode(value[3],'f32'),rates
end
local function encode_slots(values)
    local bytes={};for index,value in ipairs(values)do bytes[index]=b.encode(value,'u32')end
    return table.concat(bytes)
end
local function trait_set(field,value,label)
    plain_list(value,label,'trait IDs')
    assert(#value<=5,label..' lists '..#value..' traits; a weapon shows at most five')
    local seen,tags={},{}
    for index,trait in ipairs(value)do
        local native=type(trait)=='string'and field.traitValues[trait]
        assert(native,label..' names an unknown trait: '..tostring(trait)..' (see WeaponPresentationCapabilities.json)')
        assert(not seen[trait],label..' lists '..trait..' twice');seen[trait]=true
        tags[index]=native
    end
    for index=#value+1,5 do tags[index]=0 end
    return encode_slots(tags)
end
-- The displayed armor-penetration label: replaces the weapon's single penetration tag in place, adds one in the first
-- empty slot, or ('none') removes it and keeps the remaining tags packed. The other tags never change.
local function penetration_tags(field,value,label)
    assert(type(value)=='string'and(value=='none'or field.penetrationValues[value]),
        label..' must be "none" or one of the native penetration labels (light, medium, heavy, light_anti_tank, '
        ..'anti_tank)')
    local tags={};for index=1,5 do tags[index]=field.nativeTags[index]end
    local slot=field.penetrationSlot and field.penetrationSlot+1
    if value=='none'then
        if slot then table.remove(tags,slot);tags[5]=0 end
    elseif slot then tags[slot]=field.penetrationValues[value]
    else
        local free
        for index=1,5 do if tags[index]==0 then free=index;break end end
        assert(free,label..': all five trait slots are used')
        tags[free]=field.penetrationValues[value]
    end
    return encode_slots(tags)
end
local function same_list(a,c)
    if type(a)~='table'or type(c)~='table'or#a~=#c then return false end
    for index=1,#a do if a[index]~=c[index]then return false end end
    return true
end
-- Attack outputs are family-aware, never a common abstraction.
local function output_selector(value,label)
    for key in pairs(value)do assert(key=='resource'or key=='output',
        label..' contains unsupported attack output identity')end
    local output=assert(type(value.output)=='string'and attack_outputs().outputs[value.output],
        label..' names an unknown attack output: '..tostring(value.output))
    return {output=output.id,entry=output}
end
-- The handle resource of a host weapon entry (mounted entries share the support-weapon shape).
local function host_resource(weapon)
    return weapon.vehicleWeapon and'vehicle_weapon'or weapon.supportWeapon and'support_weapon'or'player_weapon'
end
local function reference_selector(value,label)
    assert(type(value)=='table',label..' must be a projectile reference handle')
    if value.resource=='attack_output'then return output_selector(value,label)end
    if value.resource=='support_weapon'or value.resource=='vehicle_weapon'then
        -- A support or mounted weapon's attack projectile (hd2.support_weapon(name):attack(role):projectile(),
        -- hd2.vehicle(name):weapon(mount):attack(role)).
        for key in pairs(value)do assert(key=='resource'or key=='path'or key=='weapon'or key=='attack',
            label..' contains unsupported projectile reference identity')end
        assert(value.path=='projectile_reference'and type(value.weapon)=='string'and type(value.attack)=='string',
            label..' must come from weapon:attack(role):projectile()')
        return {weapon=value.weapon,attack=value.attack,support=true,resource=value.resource}
    end
    if value.path=='ammunition_projectile'then
        for key in pairs(value)do assert(key=='resource'or key=='path'or key=='weapon',
            label..' contains unsupported ammunition projectile identity')end
        assert(value.resource=='player_weapon'and type(value.weapon)=='string',
            label..' must come from weapon:ammunition():projectile()')
        return {weapon=value.weapon,attack='primary',ammunition=true}
    end
    for key in pairs(value)do assert(key=='resource'or key=='path'or key=='weapon'or key=='attack',
        label..' contains unsupported projectile reference identity')end
    assert(value.resource=='player_weapon'and value.path=='projectile_reference'
        and type(value.weapon)=='string'and type(value.attack)=='string',
        label..' must come from weapon:attack(role):projectile()')
    return {weapon=value.weapon,attack=value.attack}
end
local function explosion_selector(value,label)
    assert(type(value)=='table',label..' must be an explosion reference handle')
    for key in pairs(value)do assert(key=='resource'or key=='path'or key=='weapon'or key=='attack'
        or key=='phase',label..' contains unsupported explosion reference identity')end
    assert(value.resource=='player_weapon'and(value.path=='explosion'or value.path=='no_explosion')
        and type(value.weapon)=='string'and type(value.attack)=='string'
        and(value.phase=='impact'or value.phase=='expiry'),
        label..' must come from projectile:terminal_action(phase):explosion()')
    return {weapon=value.weapon,attack=value.attack,phase=value.phase,
        is_null=value.path=='no_explosion'}
end
-- The firing-sound catalogue (runtime/weapon_sounds.lua; docs/weapon-sounds.md).
local function weapon_sounds()return require('hd2runtime/runtime/weapon_sounds')end
-- weapon.sound: the weapon type's firing sound as a catalogue sound name, written exactly as a catalogue entry's
-- chin-copy writes are, relative to this weapon's own record: a shot sets the per-shot event (+260) and the MIDI flag
-- (+237) and clears the loop (+252/+256); a loop sets its start and stop and clears the per-shot event and MIDI. The
-- 13 bytes are the 12-byte block +252..+263 followed by the +237 flag. The weapon's own sound restores its reviewed
-- bytes exactly; any other sound loads its bank's package before the write (asset_dependencies); a resident-only one
-- (no package Runtime can load) is refused.
local function sound_change(weapon,item,field)
    local sounds=weapon_sounds()
    local own=assert(field.nativeSound,'reviewed firing sound missing for '..weapon.name)
    local declared=type(item.expect)=='string'and sounds.resolve(item.expect)or nil
    assert(declared==field.currentDefault,'expect differs from the reviewed firing sound for '..item.field..' on '
        ..weapon.name..': declared='..tostring(item.expect)..' reviewed='..tostring(field.currentDefault))
    if type(item.value)~='string'then
        error('value must be a catalogued sound name: '..sounds.hint(),0)
    end
    local name,entry=sounds.resolve(item.value)
    if not name then error('UNKNOWN_SOUND: no firing sound '..item.value..'; use '..sounds.hint(),0)end
    local expected=b.unhex(own.block)..b.encode(own.midi,'u8')
    local change={field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
        semantic_aliases={item.field},expect=item.expect,value=item.value,expected=expected,sound=name}
    if name==field.currentDefault then change.desired=expected;return change end
    if entry.kind~='shot'and entry.kind~='loop'then
        error('UNSUPPORTED_SOUND: '..name..' is neither a shot nor a loop',0)
    end
    if entry.residentOnly or entry.own or not entry.stratagem then
        error('RESIDENT_ONLY_SOUND: the '..name..' sound is resident-only (no stratagem package Runtime can load '
            ..'provides its bank), so its bank cannot be made resident before the write; choose a sound with a '
            ..'stratagem (hd2.sounds.list({stratagem=true}))',0)
    end
    local dependencies,why=require('hd2runtime/api/assets').sound_dependencies(name)
    if not dependencies or#dependencies==0 then error('ASSET_UNAVAILABLE: '..tostring(why or name),0)end
    local zero=b.encode(0,'u32')
    if entry.kind=='loop'then
        change.desired=b.encode(tonumber(entry.start,16),'u32')..b.encode(tonumber(entry.stop,16),'u32')..zero
            ..b.encode(0,'u8')
    else
        change.desired=zero..zero..b.encode(tonumber(entry.event,16),'u32')..b.encode(entry.midi==1 and 1 or 0,'u8')
    end
    change.asset_dependencies=dependencies
    return change
end
-- Every asset dependency of a validated operation's changes (one reference, or a sound's bank packages).
local function change_dependencies(changes)
    local out={}
    for _,change in ipairs(changes)do
        if change.asset_dependency then out[#out+1]=change.asset_dependency end
        for _,dependency in ipairs(change.asset_dependencies or{})do out[#out+1]=dependency end
    end
    return out
end
-- Fields of the original fixed JAR-5 resource. Typed weapon targets use per-angle AP and the
-- player_* damage constants; say so instead of a generic rejection.
local LEGACY_DAMAGE={armor_penetration='hd2.fields.damage.ap_direct, ap_slight, ap_large and ap_extreme '
    ..'(one field per impact angle)',standard_damage='hd2.fields.damage.player_standard_damage',
    durable_damage='hd2.fields.damage.player_durable_damage'}
local function validate_change(weapon,item,allow_shared,role,path,phase,allow_unverified_effect,
        allow_unverified_reference)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local legacy=type(item.field)=='string'and(LEGACY_DAMAGE[item.field]
        or item.field:match('^armor_penetration_lanes')and LEGACY_DAMAGE.armor_penetration)
    if legacy then
        error('field '..item.field..' is a legacy fixed-resource field (the original JAR-5 patch) and does not apply to '
            ..'typed weapon targets; use '..legacy..' on weapon:attack(role):projectile()',0)
    end
    if path=='attack'and weapon.supportWeapon then
        assert(item.field:match('^damage%.')or item.field:match('^arc%.')
            or item.field:match('^beam%.')or item.field:match('^status%.')
            or item.field=='attack.projectile'or item.field=='attack.'..tostring(role)..'.projectile',
            'support attack target accepts only its projectile reference and reviewed damage/family/status fields')
    elseif path=='ammunition'then
        assert(item.field=='ammunition.projectile','ammunition targets only accept hd2.fields.ammunition.projectile')
    elseif path=='attack'then
        assert(item.field=='attack.projectile'or item.field=='attack.'..role..'.projectile',
            'COMPOSITION_TARGET_CHANGED: attack transactions only replace the projectile reference; edit the freshly resolved source projectile object in a separate guarded operation with allow_shared=true')
    elseif path=='terminal_action'then
        assert(item.field=='terminal.explosion'or item.field=='terminal.'..role..'.'..phase..'.explosion',
            'terminal targets only accept the typed terminal.explosion reference field')
    elseif path=='explosion'then
        assert(item.field:match('^explosion%.'),'explosion targets only accept explosion fields')
    elseif path=='projectile_reference'then
        assert(item.field:match('^projectile%.')or item.field:match('^damage%.'),
            'projectile objects only accept projectile or linked damage fields')
    else
        assert(item.field~='attack.projectile'and item.field~='terminal.explosion'
            and not item.field:match('^attack%..+%.projectile$')
            and not item.field:match('^terminal%.'),'typed reference field requires its semantic target')
    end
    local requested=field_for(weapon,item.field,role,path,phase);local field=requested
    if requested.aliasOf then
        field=field_for(weapon,requested.aliasOf,role,path,phase)
        assert(requested.deprecated and not requested.canonical and not requested.preferred
            and requested.acceptedForWrites and field.canonical and field.preferred,
            'field is read-only: '..item.field..' ('..tostring(requested.reason)..')')
        assert(requested.semanticTarget==field.semanticTarget
            and identical_backing(requested.backing,field.backing),'semantic alias backing changed')
    end
    -- A deprecated id published with legacyContract (charge.minimum_seconds / maximum_seconds) keeps exactly the
    -- acknowledgement and range it always had, while it writes its canonical id's bytes.
    local contract=requested.aliasOf and requested.legacyContract and requested or field
    assert(field.editable and field.backing,'field is read-only: '..item.field..' ('..tostring(field.reason)..')')
    assert(not field.affectsMultipleWeapons or allow_shared,
        'shared field requires allow_shared=true: '..item.field)
    -- A value a user test proved on exactly this target (liveProvenValues, from the provenTargets of
    -- schemas/live_evidence.json) needs no acknowledgement, nor does restoring that field's reviewed baseline;
    -- every other value of the field keeps it.
    local live_value=field.liveProvenValues~=nil and item.value==field.currentDefault
    -- A reference value is compared by the catalogued output it names (sdk/LiveEvidenceCatalog.json values are output
    -- ids): an attack output handle, or another weapon's attack projectile handle through its output alias.
    local compared=item.value
    if type(item.value)=='table'and item.value.resource=='attack_output'then compared=item.value.output
    elseif type(item.value)=='table'and item.value.path=='projectile_reference'and item.value.weapon~=weapon.name then
        local catalog=attack_outputs()
        compared=catalog.aliases[tostring(item.value.weapon)..'/'..tostring(item.value.attack)]or compared
    end
    for _,value in ipairs(field.liveProvenValues or{})do if value==compared then live_value=true end end
    -- Restoring a host's own projectile is its reviewed baseline.
    if field.type=='projectile_reference'and type(item.value)=='table'and item.value.path=='projectile_reference'
        and item.value.weapon==weapon.name and item.value.attack==role
        and item.value.resource==host_resource(weapon)then live_value=true end
    -- Restoring a weapon's own catalogued firing sound writes its reviewed baseline bytes.
    if field.type=='weapon_sound'and type(item.value)=='string'
        and weapon_sounds().resolve(item.value)==field.currentDefault then live_value=true end
    -- A field that gained the acknowledgement after the SDK the registering mod declares keeps its earlier rule (the
    -- contract the request is checked against: a deprecated alias keeps its own, which never carried one).
    local legacy,legacy_detail
    if contract.acknowledgement=='allow_unverified_effect'and not allow_unverified_effect and not live_value then
        legacy,legacy_detail=sdk_compatibility.legacy('allow_unverified_effect',host_resource(weapon),weapon.name,
            field.semanticFieldId,field.acknowledgementReason)
    end
    assert(contract.acknowledgement~='allow_unverified_effect'or allow_unverified_effect or live_value or legacy,
        'field requires allow_unverified_effect=true: '..item.field..' ('..tostring(field.acknowledgementReason)..')'
        ..(field.liveProvenValues and' (live-proven without it: '..table.concat(field.liveProvenValues,', ')..')'or'')
        ..(legacy_detail and' ['..legacy_detail..']'or''))
    if path=='projectile_reference'and field.backing.settings then
        assert(allow_shared,'projectile object edits require allow_shared=true because definitions are shared')
    end
    if field.type=='projectile_reference'then
        assert(field.referenceKind=='projectile'and field.referenceRole==role,
            'projectile reference role changed')
        local expected=reference_selector(item.expect,'expect')
        local desired=reference_selector(item.value,'value')
        local ammunition=path=='ammunition'
        local support=weapon.supportWeapon==true
        local resource=host_resource(weapon)
        assert(not expected.output and expected.weapon==weapon.name and expected.attack==role
            and(expected.resource or'player_weapon')==resource and(expected.ammunition==true)==ammunition,ammunition
            and'expect must be the weapon ammunition current projectile handle (weapon:ammunition():projectile())'
            or'expect must be the target attack current projectile handle')
        if desired.weapon and not desired.ammunition and((desired.resource or'player_weapon')~=resource or support)
            and not(desired.weapon==weapon.name and desired.attack==role
                and(desired.resource or'player_weapon')==resource)then
            -- One donor pool: another weapon's attack projectile across loadout slots (a support donor on a player
            -- host, any weapon donor on a support host) resolves to that weapon's catalogued attack output, and is
            -- checked like hd2.attack_output(name).
            local catalog=attack_outputs()
            local output_id=catalog.aliases[desired.weapon..'/'..desired.attack]
                or desired.attack=='primary'and catalog.aliases[desired.weapon]
            assert(output_id,'UNKNOWN_DONOR: '..desired.weapon..' attack '..desired.attack..' has no catalogued attack '
                ..'output (see sdk/AttackOutputCapabilities.json)')
            desired={output=output_id,entry=catalog.outputs[output_id]}
        end
        if desired.weapon and support then
            -- The support or mounted host's own projectile: restoring the reviewed baseline.
            return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
                semantic_aliases={item.field},expect=item.expect,value=item.value,
                expected_selector=expected,desired_selector=desired,source_descriptor=field,self_reference=true}
        end
        if desired.ammunition then
            -- Only the weapon's own ammunition projectile: restoring the reviewed baseline.
            assert(ammunition and desired.weapon==weapon.name,
                'an ammunition projectile handle only restores its own weapon ammunition')
            return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
                semantic_aliases={item.field},expect=item.expect,value=item.value,
                expected_selector=expected,desired_selector=desired,source_descriptor=field,self_reference=true}
        end
        if desired.output then
            -- A catalogued output: only the projectile family can be referenced by a projectile host.
            local output=desired.entry
            if output.family~='projectile'then
                error('INCOMPATIBLE_OUTPUT_FAMILY: '..output.id..' is a '..output.family..' output. '
                    ..tostring(output.reason),0)
            end
            require_output_scope(output,field.semanticFieldId)
            assert(output.editable~=false and output.backing,'attack output is not selectable: '..output.id)
            require_unverified_donor(output,allow_unverified_reference,allow_unverified_effect)
            local cross=output.compatibilityClass~=field.compatibilityClass
            if cross then
                local host=attack_outputs().hosts[weapon.name]
                assert(host and host.mechanism==(ammunition and'ammunition'or'component'),
                    'CROSS_CLASS_HOST_REJECTED: '..weapon.name..' is not a projectile host whose fired projectile this '
                    ..'target writes (see attack:projectile_source())')
                -- Exactly the compositions a user test proved in play (sdk/LiveEvidenceCatalog.json) need no
                -- acknowledgement; every other cross-class pair stays behind both.
                local proven=((attack_outputs().provenCompositions or{})[weapon.name]or{})[output.id]
                if proven~=host.mechanism then
                    assert(allow_unverified_reference,'cross-class attack output requires allow_unverified_reference=true: '
                        ..output.id..' ('..attack_outputs().crossClassReason..')')
                    assert(allow_unverified_effect,'cross-class attack output requires allow_unverified_effect=true: '
                        ..output.id..' ('..attack_outputs().crossClassReason..')')
                end
            end
            local source={referenceKind='projectile',compatibilityClass=output.compatibilityClass,
                backing=output.backing,currentDefault={projectileType=output.currentDefault},
                referenceSettings=output.referenceSettings}
            local dependency=output_dependency(weapon.name,output)
            return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
                semantic_aliases={item.field},expect=item.expect,value=item.value,
                expected_selector=expected,desired_selector=desired,source_descriptor=source,
                source_resource=output.resource,cross_class=cross,host_proof=cross,asset_dependency=dependency}
        end
        local source_weapon=assert(database.weapons[desired.weapon],
            'unknown projectile source weapon: '..desired.weapon)
        assert(not source_weapon.ordinaryWritesBlocked,
            'projectile source identity is ambiguous: '..desired.weapon)
        local source=field_for(source_weapon,'attack.'..desired.attack..'.projectile',desired.attack)
        assert(source.referenceKind=='projectile'and source.compatibilityClass==field.compatibilityClass,
            'incompatible projectile reference class')
        assert(source.compatibilityClass=='conventional_plain'
            or source.compatibilityClass=='explosive_impact'
            or source.compatibilityClass=='explosive_impact_and_expiry'
            or source.compatibilityClass=='explosive_shrapnel',
            'projectile compatibility class is not approved for replacement')
        -- The source's assets are loaded automatically when its package is known (core/assets); a source
        -- observed to need its own weapon's package and without a catalog package stays rejected.
        local dependency=source_dependency(weapon.name,desired.weapon,desired.attack)
        assert(expected.weapon==desired.weapon and expected.attack==desired.attack or dependency
            or not source.residency or source.residency.observedWithoutLoader~='SOURCE_WEAPON_REQUIRED',
            'projectile source dependency is not resident without its source weapon: '..desired.weapon)
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected_selector=expected,desired_selector=desired,source_descriptor=source,
            -- The host's own projectile: the reviewed baseline, whatever another output currently holds.
            self_reference=not ammunition and expected.weapon==desired.weapon and expected.attack==desired.attack,
            asset_dependency=dependency}
    end
    if field.type=='explosion_reference'then
        assert(field.referenceKind=='explosion'and field.referenceRole==role
            and field.referencePhase==phase,'explosion reference target changed')
        local expected=explosion_selector(item.expect,'expect')
        local desired=explosion_selector(item.value,'value')
        assert(expected.weapon==weapon.name and expected.attack==role and expected.phase==phase,
            'expect must be the target terminal action current explosion handle')
        assert(expected.is_null==(field.currentDefault.explosionType==0),
            'expect does not represent the reviewed terminal reference')
        local source
        if not desired.is_null then
            local source_weapon=assert(database.weapons[desired.weapon],
                'unknown explosion source weapon: '..desired.weapon)
            assert(not source_weapon.ordinaryWritesBlocked,
                'explosion source identity is ambiguous: '..desired.weapon)
            source=field_for(source_weapon,'terminal.explosion',desired.attack,
                'terminal_action',desired.phase)
            assert(source.referenceKind=='explosion'and source.currentDefault.explosionType~=0,
                'source is not a reviewed ExplosionSettings reference')
        end
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected_selector=expected,desired_selector=desired,source_descriptor=source,
            asset_dependency=not desired.is_null and source_dependency(weapon.name,desired.weapon,desired.attack)
                or nil}
    end
    if field.type=='status_reference'then
        -- A DamageInfo status slot. Values are catalog semantic IDs ('fire', 'stun_medium', ...) or 'none'.
        local function native(value,label)
            assert(type(value)=='string',label..' must be a status semantic ID or "none"')
            if value=='none'then return 0 end
            local status=assert(status_catalog.statuses[value],label..' names an unknown status: '..value)
            return status.nativeType
        end
        assert(item.expect==field.currentDefault,'expect differs from the reviewed status for '..item.field
            ..': declared='..tostring(item.expect)..' reviewed='..tostring(field.currentDefault))
        local expected,desired=native(item.expect,'expect'),native(item.value,'value')
        if item.value=='none'then
            assert(field.allowNone,'status slot '..item.field..' cannot be cleared: only the last used slot can, '
                ..'so the slots stay packed')
        elseif item.value~=item.expect then
            local allowed=false
            for _,candidate in ipairs(field.allowedValues or{})do if candidate==item.value then allowed=true end end
            assert(allowed,'status '..item.value..' is not attachable (no player-side attack applies it through '
                ..'a DamageInfo slot); see StatusEffectCatalog.json')
        end
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected=b.encode(expected,'u32'),desired=b.encode(desired,'u32'),status_type=desired}
    end
    if field.type=='weapon_sound'then
        return sound_change(weapon,item,field)
    end
    if field.type=='fire_rate_set'then
        -- The three native rate slots in weapon-menu order {X, Y, Z}; expect is the reviewed list, and its bytes are
        -- the exact native slots.
        assert(same_list(item.expect,field.currentDefault),'expect differs from the reviewed rates of fire for '
            ..item.field..' (three slots in weapon-menu order {X, Y, Z}: see weapon:fire_rate_modes().expect)')
        local expected=rate_set(field,item.expect,'expect')
        local desired,rates=rate_set(field,item.value,'value')
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,expected=expected,desired=desired,
            rates=rates}
    end
    if field.type=='weapon_function'then
        -- The WeaponFunctionType bound to one weapon-function input. Only an unbound input takes a binding, and only
        -- a function this weapon can host (see hd2.weapon(name):fire_rate_modes() and weapon:feeds()).
        assert(item.expect==field.currentDefault,'expect differs from the reviewed weapon function for '..item.field
            ..': declared='..tostring(item.expect)..' reviewed='..tostring(field.currentDefault))
        local allowed=false
        for _,name in ipairs(field.allowedValues or{})do if name==item.value then allowed=true end end
        assert(allowed,item.field..' cannot bind '..tostring(item.value)..' on '..weapon.name..' (allowed: '
            ..table.concat(field.allowedValues or{},', ')..')')
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected=b.encode(field.functionValues[item.expect],'u32'),
            desired=b.encode(field.functionValues[item.value],'u32'),binding=item.value}
    end
    if field.type=='trait_set'then
        assert(same_list(item.expect,field.currentDefault),'expect differs from the reviewed traits for '..item.field)
        local expected=encode_slots(field.nativeTags)
        assert(trait_set(field,item.expect,'expect')==expected,'reviewed traits no longer match their native tags')
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected=expected,desired=trait_set(field,item.value,'value')}
    end
    if field.type=='armor_penetration_label'then
        assert(item.expect==field.currentDefault,'expect differs from the reviewed penetration label for '..item.field
            ..': declared='..tostring(item.expect)..' reviewed='..tostring(field.currentDefault))
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,
            expected=encode_slots(field.nativeTags),desired=penetration_tags(field,item.value,'value')}
    end
    if field.type=='function_projectile_reference'then
        -- The projectile a ProgrammableAmmo weapon function fires (ProjectileWeapon +576): "none" (no alternate
        -- projectile), the weapon's own native one (weapon:feed(id):projectile()) or a donor attack output.
        local function selector(value,label)
            if value=='none'then return {none=true}end
            assert(type(value)=='table',label..' must be "none", weapon:feed(id):projectile() or hd2.attack_output(name)')
            if value.path=='function_projectile'then
                for key in pairs(value)do assert(key=='resource'or key=='path'or key=='weapon',
                    label..' contains unsupported function projectile identity')end
                assert(value.weapon==weapon.name,label..' is another weapon function projectile')
                return {self=true,weapon=weapon.name}
            end
            assert(value.resource=='attack_output',
                label..' must be "none", weapon:feed(id):projectile() or hd2.attack_output(name)')
            return output_selector(value,label)
        end
        local native=field.currentDefault.projectileType
        local expected,desired=selector(item.expect,'expect'),selector(item.value,'value')
        assert(native==0 and expected.none or native~=0 and expected.self,native==0
            and'expect must be "none": '..weapon.name..' has no native function projectile'
            or'expect must be the weapon feed projectile handle (weapon:feed(id):projectile())')
        assert(not desired.none or native==0,'the native function projectile of '..weapon.name
            ..' cannot be removed; restore it with its feed projectile handle')
        assert(not desired.self or native~=0,weapon.name..' has no native function projectile to restore')
        local change={field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,expected_selector=expected,
            desired_selector=desired,source_descriptor=field,expected=b.encode(native,'u32')}
        if desired.output then
            local output=desired.entry
            if output.family~='projectile'then
                error('INCOMPATIBLE_OUTPUT_FAMILY: '..output.id..' is a '..output.family..' output. '
                    ..tostring(output.reason),0)
            end
            assert(output.editable~=false and(output.backing or output.spare),'attack output is not selectable: '
                ..output.id)
            require_output_scope(output,field.semanticFieldId)
            require_unverified_donor(output,allow_unverified_reference,allow_unverified_effect)
            -- A (weapon, function projectile) pair a live test proved needs no acknowledgement (liveProvenValues).
            assert(allow_unverified_reference or live_value,'a function projectile requires '
                ..'allow_unverified_reference=true: '..output.id..' ('..tostring(field.acknowledgementReason)..')')
            change.source_descriptor={referenceKind='projectile',compatibilityClass=output.compatibilityClass,
                backing=output.backing,currentDefault={projectileType=output.currentDefault},
                referenceSettings=output.referenceSettings}
            change.source_resource=output.resource
            change.source_spare=output.spare and output or nil
            if output.spare then require('hd2runtime/domains/output_writes').require_spare_build(output)end
            change.asset_dependency=output_dependency(weapon.name,output)
        else
            change.desired=b.encode(desired.none and 0 or native,'u32')
        end
        return change
    end
    if field.type=='fire_mode_set'then
        local expected=mode_set(field,item.expect,'expect');local desired=mode_set(field,item.value,'value')
        assert(same_list(item.expect,field.currentDefault),'expect differs from reviewed fire modes for '..item.field)
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,
            semantic_aliases={item.field},expect=item.expect,value=item.value,expected=expected,desired=desired}
    end
    if field.type=='overcharge_explosion_reference'then
        -- The explosion a charge weapon's overcharge failure spawns (WeaponChargeComponent +200): the semantic name of
        -- a catalogued charge weapon whose overcharge explosion it is. Only donors with a known package are listed;
        -- another weapon's explosion loads that weapon's package first and needs allow_unverified_reference.
        local function option(value,label)
            assert(type(value)=='string',label..' must be the name of a charge weapon whose overcharge explosion to use')
            local entry=field.explosionOptions[value]
            assert(entry,label..' names no catalogued overcharge explosion: '..value..' (allowed: '
                ..table.concat(field.allowedValues or{},', ')..')')
            return entry
        end
        assert(item.expect==field.currentDefault,'expect differs from the reviewed overcharge explosion for '
            ..item.field..': declared='..tostring(item.expect)..' reviewed='..tostring(field.currentDefault))
        local expected,desired=option(item.expect,'expect'),option(item.value,'value')
        local dependency
        if item.value~=item.expect then
            assert(allow_unverified_reference,"another weapon's overcharge explosion requires "
                ..'allow_unverified_reference=true: '..item.value)
            assert(require('hd2runtime/core/assets').dependency(desired.dependencyKey),
                'UNKNOWN_EXPLOSION_PACKAGE: the package of the '..item.value..' overcharge explosion is not catalogued')
            dependency=source_dependency(weapon.name,item.value,'overcharge')
        end
        return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,requested_descriptor=requested,
            semantic_aliases={item.field},expect=item.expect,value=item.value,explosion_types={expected.explosionType,
            desired.explosionType},expected=b.encode(expected.explosionType,'u32'),
            desired=b.encode(desired.explosionType,'u32'),asset_dependency=dependency}
    end
    local expected=scalar(field,item.expect,'expect');local desired=scalar(field,item.value,'value')
    if contract.min~=nil then assert(desired>=contract.min,'value is below the reviewed minimum '..contract.min..' for '
        ..item.field..(contract.rangeReason and(': '..contract.rangeReason)or''))end
    if contract.max~=nil then assert(desired<=contract.max,'value is above the reviewed maximum '..contract.max..' for '
        ..item.field..(contract.rangeReason and(': '..contract.rangeReason)or''))end
    if field.writeKind=='reorder_native_mode_vector'then
        assert((expected==1 or expected==2)and(expected==field.currentDefault),
            'expect differs from reviewed default fire mode')
        local allowed={};for _,mode in ipairs(field.allowedValues)do allowed[mode]=true end
        assert(allowed[desired]and desired~=expected,
            'destination fire mode is not in this weapon native mode vector')
    end
    local storage=field.backing.storage
    local canonical=field.currentDefault
    if field.type=='boolean'then canonical=scalar(field,field.currentDefault,'reviewed default')end
    assert(equal(expected,canonical,storage),'expect differs from reviewed current value for '
        ..item.field..': declared='..tostring(expected)..' reviewed='..tostring(canonical)
        ..' resolved='..tostring(field.semanticFieldId))
    return {field=item.field,canonical_field=field.semanticFieldId,descriptor=field,requested_descriptor=requested,
        semantic_aliases={item.field},expect=item.expect,value=item.value,
        expected=b.encode(expected,storage),desired=b.encode(desired,storage)}
end
-- Charge times (WeaponChargeComponent +0/+24/+48) are meant to stay minimum < full < overcharge. The ids are older than
-- this check and mods already write them freely, so a write that breaks the order is accepted; it carries a one-time
-- "CHARGE ORDER" notice (core/field_notices.lua, at registration) saying what the game will do. A time the operation
-- does not write is taken at its reviewed value (every write's expect is the reviewed value).
local function check_charge_order(weapon,changes)
    local times,first={},nil
    for _,field in ipairs(weapon.fields)do
        if field.chargeTime then times[field.backing.offset]=field.currentDefault end
    end
    for _,change in ipairs(changes)do
        if change.descriptor.chargeTime then
            times[change.descriptor.backing.offset]=change.value;first=first or change
        end
    end
    if not first then return end
    local t0,t1,t2=times[0],times[24],times[48]
    if not(t0 and t1 and t2)or(t0<t1 and t1<t2)then return end
    local function s(value)return string.format('%.6g',value)end
    local effects={}
    if t1<=t0 then
        effects[#effects+1]='the full charge time ('..s(t1)..' s) is not above the minimum ('..s(t0)..' s): the charge '
            ..'meter shows full first, and outside fire mode 6 (Railgun Safe) the charge stops at the full time, so a '
            ..'release never reaches the minimum and fires nothing unless charge.auto_fire_at_full is on; in fire mode 6 '
            ..'a release fires only from '..s(t0)..' s'
    end
    if t2<=t1 then
        effects[#effects+1]='the overcharge time ('..s(t2)..' s) is not above the full time ('..s(t1)..' s): in fire '
            ..'mode 6 the overcharge is reached at '..s(t2)..' s (with charge.explode_at_overcharge the weapon then fires '
            ..'and is destroyed, even before a full charge) and the shot multipliers jump to their overcharge values'
    end
    first.notices={{kind='charge order',text=weapon.name..' charge times after this operation are '..s(t0)..' / '
        ..s(t1)..' / '..s(t2)..' s (minimum / full / overcharge), not increasing; the write is applied. In game: '
        ..table.concat(effects,'; ')..'. Write related times together in one transaction to keep them ordered.'}}
end
-- Turret limits (TurretComponent +20/+24 vertical, +28/+32 horizontal, docs/vehicle-weapons.md): each minimum must stay
-- below its maximum after the operation. A limit the operation does not write keeps its reviewed value, so a pair that
-- crosses must be changed in one transaction.
local TURRET_PAIRS={{'turret.pitch_min','turret.pitch_max'},{'turret.yaw_min','turret.yaw_max'}}
local function check_turret_order(weapon,changes)
    for _,pair in ipairs(TURRET_PAIRS)do
        local values,written={},false
        for _,field in ipairs(weapon.fields)do
            if field.semanticFieldId==pair[1]or field.semanticFieldId==pair[2]then
                values[field.semanticFieldId]=field.currentDefault
            end
        end
        for _,change in ipairs(changes)do
            local id=change.descriptor.semanticFieldId
            if id==pair[1]or id==pair[2]then values[id]=change.value;written=true end
        end
        if written then
            local low,high=values[pair[1]],values[pair[2]]
            assert(type(low)=='number'and type(high)=='number','turret limit pair incomplete for '..weapon.name)
            assert(low<high,'TURRET_LIMIT_ORDER: '..weapon.name..' '..pair[1]..' must stay below '..pair[2]
                ..'; this operation would leave '..low..' / '..high..' degrees (a limit it does not write keeps its '
                ..'reviewed value: change both in one transaction)')
        end
    end
end
local function id(value)
    assert(type(value)=='string'and#value>0 and#value<=64 and not value:find('[^%w_%-]'),'invalid operation id')
end
-- A selector binding and the modes it selects are written together, so nothing an operation writes is dormant: rates
-- beyond the default need a bound rate-of-fire selector, a function projectile needs a bound ProgrammableAmmo
-- selector, and binding either selector needs what it selects in the same operation.
local function check_selector_pairs(weapon,changes)
    local binds,rates,projectile={},nil,nil
    for _,change in ipairs(changes)do
        local kind=change.descriptor.type
        if kind=='weapon_function'and change.binding~=change.expect then binds[change.binding]=change.field end
        if kind=='fire_rate_set'then rates=change end
        if kind=='function_projectile_reference'then projectile=change end
    end
    -- A wind-up weapon's X and Z hold its rate natively with no selector bound (dormant, the Maxigun's 1500/1500/1500):
    -- writing exactly those reviewed slots back writes nothing a selector would newly visit.
    local dormant_baseline=rates and rates.descriptor.windUp==true and same_list(rates.value,rates.descriptor.currentDefault)
    if rates and rates.rates>1 and not rates.descriptor.selectorBound and not dormant_baseline then
        assert(binds.rate_of_fire,'SELECTOR_REQUIRED: fire_rate.modes fills '..rates.rates..' rate slots, but '..weapon.name
            ..' has no rate-of-fire selector; bind it in the same transaction (hd2.fields.weapon_function.'
            ..table.concat(rates.descriptor.bindableInputs or{'left'},' or ')..' = "rate_of_fire")')
    end
    if binds.rate_of_fire then
        assert(rates and rates.rates>1,'SELECTOR_REQUIRED: binding the rate-of-fire selector needs fire_rate.modes with '
            ..'at least two filled rate slots in the same transaction')
    end
    if projectile and not projectile.desired_selector.none and not projectile.descriptor.selectorBound then
        assert(binds.programmable_ammo,'SELECTOR_REQUIRED: function_ammo.projectile needs a bound ProgrammableAmmo '
            ..'selector on '..weapon.name..'; bind it in the same transaction (hd2.fields.weapon_function.'
            ..table.concat(projectile.descriptor.bindableInputs or{'left'},' or ')..' = "programmable_ammo")')
    end
    if binds.programmable_ammo then
        assert(projectile and not projectile.desired_selector.none,'SELECTOR_REQUIRED: binding the ProgrammableAmmo '
            ..'selector needs a function_ammo.projectile in the same transaction')
    end
end

function M.validate_patch(request)
    assert(type(request)=='table','patch requires a descriptor')
    local allowed={id=true,target=true,field=true,expect=true,value=true,diagnostic=true,allow_shared=true,
        allow_unverified_effect=true,allow_unverified_reference=true}
    for key in pairs(request)do assert(allowed[key],'unsupported patch option: '..tostring(key))end
    id(request.id);local name,role,path,phase,kind=target_name(request.target)
    local selected=database_for(kind)
    local weapon=assert(selected.weapons[name],'unknown reviewed weapon')
    assert(not weapon.ordinaryWritesBlocked,weapon.blockReason)
    local change=validate_change(weapon,{field=request.field,expect=request.expect,value=request.value},
        request.allow_shared==true,role,path,phase,request.allow_unverified_effect==true,
        request.allow_unverified_reference==true)
    check_selector_pairs(weapon,{change})
    check_charge_order(weapon,{change})
    check_turret_order(weapon,{change})
    return {kind=kind,id=request.id,weapon=name,
        resource=weapon.attackResource or weapon.resources[1],identity_resource=weapon.identityResource,
        ownership_chain=weapon.ownershipChain,root_rack=weapon.rootRack,mount_chain=weapon.mountChain,
        attack=role,target_path=path,phase=phase,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,
        field=request.field,expect=request.expect,value=request.value,changes={change},
        asset_dependencies=change_dependencies({change})}
end
function M.validate_transaction(request)
    assert(type(request)=='table','transaction requires a descriptor')
    local allowed={id=true,target=true,changes=true,diagnostic=true,allow_shared=true,
        allow_unverified_effect=true,allow_unverified_reference=true}
    for key in pairs(request)do assert(allowed[key],'unsupported transaction option: '..tostring(key))end
    id(request.id);local name,role,path,phase,kind=target_name(request.target)
    local selected=database_for(kind)
    local weapon=assert(selected.weapons[name],'unknown reviewed weapon')
    assert(not weapon.ordinaryWritesBlocked,weapon.blockReason)
    assert(type(request.changes)=='table'and#request.changes>=1 and#request.changes<=32,
        'transaction requires one to 32 changes')
    local result={kind=kind,id=request.id,weapon=name,
        resource=weapon.attackResource or weapon.resources[1],identity_resource=weapon.identityResource,
        ownership_chain=weapon.ownershipChain,root_rack=weapon.rootRack,mount_chain=weapon.mountChain,attack=role,
        target_path=path,phase=phase,
        diagnostic=request.diagnostic==true,allow_shared=request.allow_shared==true,changes={}}
    local seen,canonical_seen={},{ }
    for _,item in ipairs(request.changes)do
        assert(not seen[item.field],'duplicate transaction field: '..tostring(item.field));seen[item.field]=true
        local change=validate_change(weapon,item,result.allow_shared,role,path,phase,
            request.allow_unverified_effect==true,request.allow_unverified_reference==true)
        local prior=canonical_seen[change.canonical_field]
        if prior then
            local same_desired=prior.desired==change.desired
            local same_expected=prior.expected==change.expected
            if prior.desired_selector or change.desired_selector then
                same_desired=prior.desired_selector and change.desired_selector
                    and prior.desired_selector.output==change.desired_selector.output
                    and prior.desired_selector.weapon==change.desired_selector.weapon
                    and prior.desired_selector.attack==change.desired_selector.attack
                    and prior.desired_selector.phase==change.desired_selector.phase
                same_expected=prior.expected_selector and change.expected_selector
                    and prior.expected_selector.weapon==change.expected_selector.weapon
                    and prior.expected_selector.attack==change.expected_selector.attack
                    and prior.expected_selector.phase==change.expected_selector.phase
            end
            if not same_desired then
                error('SEMANTIC_CONFLICT: '..prior.field..' and '..change.field
                    ..' alias '..change.canonical_field..' with different desired values',0)
            end
            assert(same_expected,
                'semantic alias expected values differ: '..prior.field..' and '..change.field)
            prior.semantic_aliases[#prior.semantic_aliases+1]=change.field
        else
            result.changes[#result.changes+1]=change
            canonical_seen[change.canonical_field]=change
        end
    end
    check_selector_pairs(weapon,result.changes)
    check_charge_order(weapon,result.changes)
    check_turret_order(weapon,result.changes)
    result.asset_dependencies=change_dependencies(result.changes)
    return result
end

local function find_candidate(catalog,resource)
    local found
    for _,candidate in ipairs(catalog.candidates)do
        if candidate.resourceHash==resource then assert(not found,'duplicate resource candidate');found=candidate end
    end
    assert(found and found.entityRow and#found.diagnostics==0,'weapon resource ownership unresolved')
    return found
end

-- Re-prove a weapon's ammunition source inside the live, uniquely owned entity delta allocation: the delta chain
-- (header, hashmap row, settings entry, component rows, reviewed data offset) and the weapon's own default
-- customization still naming that ammunition item. Returns the active projectile type the weapon is built with.
local function prove_ammunition(reader,roots,catalog,candidate,ammunition)
    local region=assert(roots.entity_deltas,'entity delta table was not located')
    reader.stage='domains/player_weapon_writes:ammunition_delta'
    local offsets=require('hd2runtime/domains/attachment_writes').prove(reader,region,ammunition)
    local rows=assert(offsets[ammunition.component],
        'AMMUNITION_SOURCE_CHANGED: the ammunition delta no longer patches ProjectileWeaponComponentData')
    assert(rows[ammunition.componentOffset]==ammunition.dataOffset,
        'AMMUNITION_SOURCE_CHANGED: reviewed ammunition delta data offset changed')
    local custom=catalog.record(candidate,'WeaponCustomizationComponentData')
    local pair=ammunition.defaultCustomization
    assert(b.u32(custom.bytes,pair.offset)==pair.slot and b.u32(custom.bytes,pair.offset+4)==pair.optionId,
        'AMMUNITION_SOURCE_CHANGED: '..ammunition.weapon..' no longer defaults to '..ammunition.item)
    local bytes=reader.read(region,ammunition.dataOffset,4,true)
    return {entry=ammunition,region=region,bytes=bytes,projectile_type=b.u32(bytes,0)}
end

local function add_need(needed,name,value)
    if value==true or needed[name]==nil then needed[name]=value end
end
local function collect_needs(needed,spec)
    add_need(needed,'entity',true)
    if spec.kind=='player_weapon'and attack_outputs().ammunition[spec.weapon]then
        -- The weapon's fired projectile is its ammunition delta: projectile resolution and ammunition writes use it.
        add_need(needed,'entity_deltas',true);add_need(needed,'projectile',true)
    end
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing
        if backing.kind=='settings'then
            local settings_kind=backing.settings=='explosion_damage'and'damage'or backing.settings
            add_need(needed,settings_kind,true)
            local linkage=(backing.linkage or'')..' '..(backing.parentLinkage or'')
            if backing.parentLinkage then add_need(needed,'damage',true)end
            if linkage:find('projectile',1,true)then add_need(needed,'projectile',true)end
            if linkage:find('explosion',1,true)then add_need(needed,'explosion',true)end
            if linkage:find('arc',1,true)then add_need(needed,'arc',true)end
            if linkage:find('beam',1,true)then add_need(needed,'beam',true)end
        end
        if change.descriptor.type=='projectile_reference'or change.descriptor.type=='function_projectile_reference'then
            add_need(needed,'projectile',true)
        end
        if change.descriptor.type=='status_reference'then add_need(needed,'status',true)end
        if change.descriptor.type=='overcharge_explosion_reference'then add_need(needed,'explosion',true)end
        if change.descriptor.type=='explosion_reference'or backing.settings=='explosion'
            or backing.settings=='explosion_damage'then
            add_need(needed,'projectile',true);add_need(needed,'explosion',true)
        end
        if backing.settings=='explosion_damage'then add_need(needed,'damage',true)end
        if backing.settings=='damage'then
            add_need(needed,'projectile',true);add_need(needed,'arc','optional')
            add_need(needed,'beam','optional')
        end
    end
end
-- A mounted weapon's TurretComponent (vehicle turret motion) is captured only by an operation that writes it, so every
-- other weapon write keeps exactly its guarded context (the table adds its index rows and one record).
-- A projectile donor's own component (research/projectile-donors: EagleComponentData, BombardmentComponentData,
-- OrbitalAbilityComponentData) is captured too, so its reference can be re-proven before the write.
local function with_turret(names,specs)
    local out
    local function add(name)
        for _,have in ipairs(out or names)do if have==name then return end end
        if not out then out={};for index,have in ipairs(names)do out[index]=have end end
        out[#out+1]=name
    end
    for _,spec in ipairs(specs)do
        for _,change in ipairs(spec.changes or{})do
            local backing=change.descriptor and change.descriptor.backing
            if backing and backing.component=='TurretComponentData'then add('TurretComponentData')end
            local source=change.source_descriptor and change.source_descriptor.backing
            if source and source.kind=='component'and source.component then add(source.component)end
        end
    end
    return out or names
end
M.with_turret=with_turret
function M.capture_many(runtime,reader,specs)
    assert(type(specs)=='table'and#specs>=1,'composition capture requires operation specs')
    reader.stage='runtime/windows_readonly:fingerprint'
    require('hd2runtime/core/fingerprint').require(runtime)
    local needed={};for _,spec in ipairs(specs)do collect_needs(needed,spec)end
    local roots=discover.locate(runtime,reader,profile,needed)
    local catalog=entities.capture(reader,roots.entity,profile,
        with_turret(needed.entity_deltas and ammunition_component_names or component_names,specs))
    local results={}
    for index,spec in ipairs(specs)do
        local selected=database_for(spec.kind)
        local resolved={roots=roots,catalog=catalog,candidate=find_candidate(catalog,spec.resource),
            database=selected,
            reference_sources={}}
        if spec.kind=='support_weapon'and spec.identity_resource
            and spec.identity_resource~=spec.resource then
            local identity_candidate=find_candidate(catalog,spec.identity_resource)
            local rack=resolved.catalog.record(identity_candidate,'HellpodRackComponentData')
            local linked=false
            for slot=0,7 do if b.resource(rack.bytes,slot*64)==spec.resource then linked=true end end
            assert(linked,'support ownership chain changed: rack no longer links attack entity')
            local expected=spec.root_rack
            assert(expected and identity_candidate.entityRow==expected.entityRow
                and rack.identity.recordIndex==expected.recordIndex,
                'support ownership chain changed: rack identity differs')
            local stratagem=require('hd2runtime/core/stratagem')
            local records=stratagem.capture_all(runtime,reader,profile);local chain=spec.ownership_chain or{}
            for _,node in ipairs(chain)do if node.kind=='stratagem_payload'then
                local found=false
                for _,record in ipairs(records)do
                    if record.id==node.id and record.package==node.package then
                        for _,payload in ipairs(record.payloads or{})do
                            if payload==spec.identity_resource then found=true end
                        end
                    end
                end
                assert(found,'support ownership chain changed: stratagem payload link absent')
            end end
            resolved.identity_candidate=identity_candidate
        end
        local ammunition=spec.kind=='player_weapon'and attack_outputs().ammunition[spec.weapon]
        if ammunition then resolved.ammunition=prove_ammunition(reader,roots,catalog,resolved.candidate,ammunition)end
        if spec.kind=='vehicle_weapon'then
            -- Re-prove the mount chain: the vehicle's own MountComponentData slot still holds this weapon.
            local chain=assert(spec.mount_chain,'vehicle weapon mount chain missing')
            local vehicle=find_candidate(catalog,chain.vehicleResource)
            if chain.carrier then
                -- Guard Dog: the carrier backpack still deploys this drone (its DepositComponent +24 names it).
                local carrier=chain.carrier
                local backpack=find_candidate(catalog,carrier.backpackResource)
                local link=catalog.record(backpack,carrier.link.component)
                assert(link.identity.recordIndex==carrier.link.recordIndex and link.identity.indexRow==carrier.link.indexRow
                    and link.identity.ownerCount==carrier.link.ownerCount,'drone carrier link ownership changed')
                assert(b.resource(link.bytes,carrier.link.offset)==chain.vehicleResource,
                    'drone chain changed: the backpack no longer deploys the reviewed drone')
                assert(vehicle.entityRow==carrier.droneEntityRow,'drone chain changed: drone entity row differs')
            end
            local mount=catalog.record(vehicle,'MountComponentData')
            assert(b.resource(mount.bytes,chain.slot*24)==chain.mountPath,
                'vehicle mount chain changed: slot '..chain.slot..' no longer holds the reviewed weapon')
            assert(chain.mountPath==spec.resource,'vehicle mount chain does not name the weapon owner')
        end
        for _,change in ipairs(spec.changes)do
            if change.self_reference then
                -- The host's own projectile: its reviewed type, re-proven through its settings row in prepare.
            elseif change.source_resource then
                resolved.reference_sources[change.canonical_field]=find_candidate(catalog,change.source_resource)
            elseif change.desired_selector and not change.desired_selector.is_null
                and change.descriptor.type~='function_projectile_reference'then
                local source=assert(selected.weapons[change.desired_selector.weapon],
                    'projectile source metadata missing')
                resolved.reference_sources[change.canonical_field]=find_candidate(catalog,source.resources[1])
            end
        end
        results[index]=resolved
    end
    return results
end
function M.capture(runtime,reader,spec)
    return M.capture_many(runtime,reader,{spec})[1]
end

local function component_record_for(resolved,candidate,backing)
    local record=resolved.catalog.record(candidate,backing.component)
    local identity=record.identity
    assert(identity.recordIndex==backing.recordIndex and identity.indexRow==backing.indexRow
        and identity.ownerCount==backing.ownerCount,'component ownership identity changed')
    return record
end
local function component_record(resolved,backing)
    return component_record_for(resolved,resolved.candidate,backing)
end
local function projectile_for_candidate(resolved,candidate,branch)
    local ownership=candidate.ownership
    local projectile_type
    if resolved.ammunition and candidate==resolved.candidate then
        -- The weapon fires its default ammunition delta; ProjectileWeapon +0 is dormant.
        projectile_type=resolved.ammunition.projectile_type
    elseif ownership.WeaponRoundsComponentData then
        local rounds=resolved.catalog.record(candidate,'WeaponRoundsComponentData')
        projectile_type=b.u32(rounds.bytes,(branch=='alternate'or branch=='feed_alternate')and 68 or 64)
    elseif ownership.ProjectileWeaponComponentData then
        local weapon=resolved.catalog.record(candidate,'ProjectileWeaponComponentData')
        projectile_type=b.u32(weapon.bytes,0)
    end
    assert(projectile_type and projectile_type~=0,'linked projectile selector absent')
    return assert(resolved.roots.projectile.records[projectile_type],
        'linked ProjectileSettings absent'),projectile_type
end
local function linked(resolved,kind,branch,phase)
    local ownership=resolved.candidate.ownership
    if kind=='projectile'or kind=='explosion'or kind=='explosion_damage'
        or(kind=='damage'and(ownership.WeaponRoundsComponentData
            or ownership.ProjectileWeaponComponentData))then
        local projectile_type
        local projectile;projectile,projectile_type=projectile_for_candidate(resolved,resolved.candidate,branch)
        if kind=='projectile'then return projectile,resolved.roots.projectile.owner end
        if kind=='damage'then
            local damage_type=b.u32(projectile.bytes,60)
            return assert(resolved.roots.damage.records[damage_type],'linked DamageInfo absent'),resolved.roots.damage.owner
        end
        local terminal_offset=phase=='expiry'and 156 or 144
        local explosion_type=b.u32(projectile.bytes,terminal_offset)
        local explosion=assert(resolved.roots.explosion.records[explosion_type],
            'linked ExplosionSettings absent')
        if kind=='explosion'then return explosion,resolved.roots.explosion.owner end
        local damage_type=b.u32(explosion.bytes,4)
        return assert(resolved.roots.damage.records[damage_type],
            'linked explosion DamageInfo absent'),resolved.roots.damage.owner
    end
    if kind=='arc'or(kind=='damage'and ownership.ArcWeaponComponentData)then
        local component=resolved.catalog.record(resolved.candidate,'ArcWeaponComponentData')
        local record=assert(resolved.roots.arc.records[b.u32(component.bytes,0)],'linked ArcSettings absent')
        if kind=='arc'then return record,resolved.roots.arc.owner end
        return assert(resolved.roots.damage.records[b.u32(record.bytes,36)],'linked arc DamageInfo absent'),resolved.roots.damage.owner
    end
    if kind=='beam'or(kind=='damage'and ownership.BeamWeaponComponentData)then
        local component=resolved.catalog.record(resolved.candidate,'BeamWeaponComponentData')
        local record=assert(resolved.roots.beam.records[b.u32(component.bytes,0)],'linked BeamSettings absent')
        if kind=='beam'then return record,resolved.roots.beam.owner end
        return assert(resolved.roots.damage.records[b.u32(record.bytes,12)],'linked beam DamageInfo absent'),resolved.roots.damage.owner
    end
    if kind=='damage'and ownership.SprayWeaponComponentData then
        local component=resolved.catalog.record(resolved.candidate,'SprayWeaponComponentData')
        return assert(resolved.roots.damage.records[b.u32(component.bytes,200)],'linked spray DamageInfo absent'),resolved.roots.damage.owner
    end
    if kind=='damage'and ownership.MeleeWeaponComponentData then
        local component=resolved.catalog.record(resolved.candidate,'MeleeWeaponComponentData')
        return assert(resolved.roots.damage.records[b.u32(component.bytes,12)],'linked melee DamageInfo absent'),resolved.roots.damage.owner
    end
    error('reviewed settings linkage unavailable: '..kind,0)
end

-- Charge-level shots and overcharge explosions (research/charge-explosions-F5FEE03DCFDB.json): the weapon's own
-- WeaponCharge record selects them live. A charge-level shot fires the projectile its level names (+4 partial,
-- +28 full, +52 overcharged; every selector of the role must name the same row); the overcharge failure spawns the
-- explosion at +200. The caller re-proves the reviewed row identity, so a swapped selector or overcharge explosion
-- (charge.overcharge_explosion) refuses the write instead of editing another row.
local function charge_record(resolved,backing)
    local identity=assert(backing.chargeRecord,'charge record identity missing')
    return component_record(resolved,{component='WeaponChargeComponentData',recordIndex=identity.recordIndex,
        indexRow=identity.indexRow,ownerCount=identity.ownerCount})
end
local function charge_projectile(resolved,backing)
    local record=charge_record(resolved,backing)
    local projectile_type
    for _,offset in ipairs(assert(backing.chargeSelectorOffsets,'charge level selector missing'))do
        local value=b.u32(record.bytes,offset)
        assert(value~=0,'linked charge level projectile selector absent')
        assert(projectile_type==nil or projectile_type==value,
            'charge levels of this role no longer fire one projectile')
        projectile_type=value
    end
    return assert(resolved.roots.projectile.records[projectile_type],'linked charge level ProjectileSettings absent')
end
local function charge_explosion(resolved,backing)
    if backing.linkage:find('charge_overcharge_explosion',1,true)then
        local record=charge_record(resolved,backing)
        return assert(resolved.roots.explosion.records[b.u32(record.bytes,assert(backing.chargeExplosionOffset))],
            'linked overcharge ExplosionSettings absent')
    end
    local projectile=charge_projectile(resolved,backing)
    return assert(resolved.roots.explosion.records[b.u32(projectile.bytes,backing.phase=='expiry'and 156 or 144)],
        'linked charge level ExplosionSettings absent')
end

local function support_explosion(resolved,backing)
    if backing.linkage:find('charge_',1,true)==1 then return charge_explosion(resolved,backing)end
    if backing.linkage:find('explosive_explosion',1,true)then
        local component=component_record(resolved,{component='ExplosiveComponentData',
            recordIndex=resolved.candidate.ownership.ExplosiveComponentData.recordIndex,
            indexRow=resolved.candidate.ownership.ExplosiveComponentData.indexRow,
            ownerCount=resolved.candidate.ownership.ExplosiveComponentData.ownerCount})
        local explosion_type=b.u32(component.bytes,assert(backing.selectorOffset))
        return assert(resolved.roots.explosion.records[explosion_type],
            'linked placed-entity ExplosionSettings absent')
    end
    local projectile=projectile_for_candidate(resolved,resolved.candidate,
        backing.parentRole or backing.branch)
    local offset=backing.phase=='expiry'and 156 or 144
    return assert(resolved.roots.explosion.records[b.u32(projectile.bytes,offset)],
        'linked support projectile ExplosionSettings absent')
end

local function support_damage(resolved,backing,linkage)
    if linkage=='charge_projectile_damage'then
        local projectile=charge_projectile(resolved,backing)
        return assert(resolved.roots.damage.records[b.u32(projectile.bytes,60)],
            'linked charge level DamageInfo absent')
    end
    if linkage=='projectile_damage'then
        local projectile=projectile_for_candidate(resolved,resolved.candidate,backing.branch)
        return assert(resolved.roots.damage.records[b.u32(projectile.bytes,60)],
            'linked support projectile DamageInfo absent')
    end
    if linkage=='arc_damage'then
        local component=resolved.catalog.record(resolved.candidate,'ArcWeaponComponentData')
        local arc=assert(resolved.roots.arc.records[b.u32(component.bytes,0)],'linked ArcSettings absent')
        return assert(resolved.roots.damage.records[b.u32(arc.bytes,36)],'linked arc DamageInfo absent')
    end
    if linkage=='beam_damage'then
        local component=resolved.catalog.record(resolved.candidate,'BeamWeaponComponentData')
        local beam=assert(resolved.roots.beam.records[b.u32(component.bytes,0)],'linked BeamSettings absent')
        return assert(resolved.roots.damage.records[b.u32(beam.bytes,12)],'linked beam DamageInfo absent')
    end
    if linkage=='spray_damage'then
        local component=resolved.catalog.record(resolved.candidate,'SprayWeaponComponentData')
        return assert(resolved.roots.damage.records[b.u32(component.bytes,200)],'linked spray DamageInfo absent')
    end
    if linkage=='melee_damage'then
        local component=resolved.catalog.record(resolved.candidate,'MeleeWeaponComponentData')
        return assert(resolved.roots.damage.records[b.u32(component.bytes,12)],'linked melee DamageInfo absent')
    end
    if linkage:find('explosion_damage',1,true)then
        local explosion=support_explosion(resolved,backing)
        return assert(resolved.roots.damage.records[b.u32(explosion.bytes,4)],
            'linked support explosion DamageInfo absent')
    end
    error('reviewed support DamageInfo linkage unavailable: '..tostring(linkage),0)
end

local function support_linked(resolved,backing)
    local linkage=assert(backing.linkage,'support settings linkage missing')
    if linkage=='projectile'then
        local record=projectile_for_candidate(resolved,resolved.candidate,backing.branch)
        return record,resolved.roots.projectile.owner
    end
    if linkage=='charge_projectile'then
        return charge_projectile(resolved,backing),resolved.roots.projectile.owner
    end
    if linkage=='arc'then
        local component=resolved.catalog.record(resolved.candidate,'ArcWeaponComponentData')
        return assert(resolved.roots.arc.records[b.u32(component.bytes,0)],'linked ArcSettings absent'),
            resolved.roots.arc.owner
    end
    if linkage=='beam'then
        local component=resolved.catalog.record(resolved.candidate,'BeamWeaponComponentData')
        return assert(resolved.roots.beam.records[b.u32(component.bytes,0)],'linked BeamSettings absent'),
            resolved.roots.beam.owner
    end
    if linkage=='status'then
        local damage=support_damage(resolved,backing,assert(backing.parentLinkage))
        local matches=0
        for offset=44,68,8 do if b.u32(damage.bytes,offset)==backing.statusType then matches=matches+1 end end
        assert(matches==1,'linked StatusEffectSettings owner absent or ambiguous')
        return assert(resolved.roots.status.records[backing.statusType],
            'linked StatusEffectSettings absent'),resolved.roots.status.owner
    end
    if linkage:find('explosion',1,true)and not linkage:find('damage',1,true)then
        return support_explosion(resolved,backing),resolved.roots.explosion.owner
    end
    return support_damage(resolved,backing,linkage),resolved.roots.damage.owner
end

function M.prepare(resolved,reader,spec)
    local plan={changes={},snapshots=reader.snapshots};local physical={}
    for _,change in ipairs(spec.changes)do
        local backing=change.descriptor.backing;local record,owner
        if backing.kind=='component'then record=component_record(resolved,backing);owner=record.owner
        elseif backing.kind=='entity_delta'then
            local ammunition=assert(resolved.ammunition,'ammunition source was not freshly proven')
            assert(ammunition.entry.dataOffset==change.descriptor.dataOffset,'ammunition source changed')
            record={bytes=ammunition.bytes,offset=change.descriptor.dataOffset};owner=ammunition.region
        elseif(spec.kind=='support_weapon'or spec.kind=='vehicle_weapon')and backing.linkage then
            record,owner=support_linked(resolved,backing)
            assert(record.group==backing.group and record.row==backing.row
                and record.kind==backing.recordType and record.settings_type==backing.settingsType,
                'support settings record identity changed')
        else
            record,owner=linked(resolved,backing.settings,backing.branch,backing.phase)
            assert(record.group==backing.group and record.row==backing.row
                and record.kind==backing.recordType and record.settings_type==backing.settingsType,
                (spec.target_path=='projectile_reference'
                    and 'COMPOSITION_TARGET_CHANGED: projectile fields now belong to the newly referenced object; target that source projectile handle and acknowledge shared ownership'
                    or 'settings record identity changed'))
        end
        assert(backing.offset+backing.width<=#record.bytes,'field outside reviewed record')
        local current=record.bytes:sub(backing.offset+1,backing.offset+backing.width)
        if change.descriptor.type=='weapon_sound'then
            -- The firing-sound block and its MIDI flag are checked (and owned) as one value.
            local at=assert(change.descriptor.midiOffset,'MIDI flag offset missing')
            current=current..record.bytes:sub(at+1,at+1)
        end
        if backing.statusSlot then
            -- Status slots stay packed from slot 1: the slots before this one are still used, and a slot is
            -- cleared only when every later slot is empty.
            local slot=backing.statusSlot
            for index=1,slot-1 do
                assert(b.u32(record.bytes,44+(index-1)*8)~=0,'CONFLICT: status slot '..index..' is now empty')
            end
            if change.status_type==0 then
                for index=slot+1,4 do
                    assert(b.u32(record.bytes,44+(index-1)*8)==0,'CONFLICT: a later status slot is used')
                end
            end
            -- Every status row stores its own name; the reviewed and desired statuses must still carry the
            -- names the catalog was built from, so a renumbered status table can never be written through.
            local function verify_status(semantic)
                if semantic=='none'then return end
                local status=assert(status_catalog.statuses[semantic],'unknown status '..tostring(semantic))
                local root=assert(resolved.roots.status,'live status table absent')
                local row=assert(root.records[status.nativeType],
                    'status '..semantic..' has no row in the live status table')
                local pointer=b.pointer(row.bytes,8)
                local owner=root.owner
                assert(pointer>=owner.base and pointer<owner.base+owner.size,'status name outside the status table')
                local text=reader.read(owner,pointer-owner.base,math.min(64,owner.base+owner.size-pointer))
                assert(text:match('^([^%z]*)')==status.name,'CONFLICT: the live status table no longer names '
                    ..semantic..' "'..status.name..'" (status catalog is stale for this build)')
            end
            if change.descriptor.type=='status_reference'then
                verify_status(change.descriptor.currentDefault);verify_status(change.value)
            end
        end
        local source_identity
        if change.descriptor.type=='projectile_reference'then
            local reviewed=change.descriptor.currentDefault.projectileType
            local expected=b.encode(reviewed,'u32')
            local source_type
            if change.self_reference then
                -- Restoring the host's own projectile: its reviewed type (the settings row is re-proven below);
                -- the host record may legitimately hold another output this operation applied.
                source_type=reviewed
            else
                local source_candidate=assert(resolved.reference_sources[change.canonical_field],
                    'projectile source was not freshly resolved')
                local source_record=component_record_for(resolved,source_candidate,
                    change.source_descriptor.backing)
                source_type=b.u32(source_record.bytes,change.source_descriptor.backing.offset)
                assert(source_type==change.source_descriptor.currentDefault.projectileType,
                    'CONFLICT: source projectile reference changed')
            end
            local settings=assert(resolved.roots.projectile.records[source_type],
                'source ProjectileSettings record absent')
            local reviewed_settings=change.source_descriptor.referenceSettings
            assert(settings.group==reviewed_settings.group and settings.row==reviewed_settings.row
                and settings.kind==reviewed_settings.recordType
                and settings.settings_type==reviewed_settings.settingsType,
                'source ProjectileSettings identity changed')
            if change.host_proof then
                local ownership_map=resolved.candidate.ownership
                assert(ownership_map.WeaponMagazineComponentData and not ownership_map.WeaponRoundsComponentData
                    and not ownership_map.WeaponChargeComponentData and not ownership_map.WeaponHeatComponentData,
                    'CROSS_CLASS_HOST_REJECTED: host fire/resource composition changed')
                local magazine=resolved.catalog.record(resolved.candidate,'WeaponMagazineComponentData')
                assert(magazine.bytes:sub(5,136)==string.rep('\0',132),
                    'CROSS_CLASS_HOST_REJECTED: host magazine pattern selects other projectiles')
            end
            change.expected=expected;change.desired=b.encode(source_type,'u32')
            source_identity={component=change.source_descriptor.backing.component,
                record_index=change.source_descriptor.backing.recordIndex,
                index_row=change.source_descriptor.backing.indexRow,
                projectile_type=source_type,settings_group=settings.group,
                settings_row=settings.row,settings_type=settings.settings_type,
                scope='projectile_reference_source'}
        elseif change.descriptor.type=='function_projectile_reference'then
            -- The host must still have the shape the research saw (the same rounds feed or none, no spawned entity, no
            -- magazine pattern), so the ProgrammableAmmo override replaces exactly the projectile it fires.
            local ownership_map=resolved.candidate.ownership
            assert((ownership_map.WeaponRoundsComponentData~=nil)==(change.descriptor.hostRounds==true),
                'FUNCTION_HOST_CHANGED: '..spec.weapon..' rounds feed changed')
            local zero8=string.rep(string.char(0),8)
            assert(record.bytes:sub(41,48)==zero8 and record.bytes:sub(585,592)==zero8,
                'FUNCTION_HOST_CHANGED: '..spec.weapon..' now spawns an entity when it fires')
            if ownership_map.WeaponMagazineComponentData then
                local magazine=resolved.catalog.record(resolved.candidate,'WeaponMagazineComponentData')
                assert(magazine.bytes:sub(5,136)==string.rep(string.char(0),132),
                    'FUNCTION_HOST_CHANGED: a magazine pattern now selects the fired projectiles')
            end
            local source_type,reviewed_settings
            if change.source_spare then
                -- A spare twin (no owner entity): its row must still be its twin's, byte for byte, outside the
                -- references and presentation, so the twin's package covers what it draws.
                local spare=change.source_spare
                local function row(settings,label)
                    local record=assert(resolved.roots.projectile.records[settings.recordType],
                        label..' ProjectileSettings record absent')
                    assert(record.group==settings.group and record.row==settings.row and record.kind==settings.recordType
                        and record.settings_type==settings.settingsType,label..' ProjectileSettings identity changed')
                    return record.bytes
                end
                local function masked(bytes)
                    for _,range in ipairs(spare.spare.excluded)do
                        bytes=bytes:sub(1,range[1])..string.rep(string.char(0),range[2]-range[1])..bytes:sub(range[2]+1)
                    end
                    return bytes
                end
                assert(masked(row(spare.referenceSettings,spare.id))==masked(row(spare.spare.twinSettings,spare.spare.twinOf)),
                    'SPARE_TWIN_CHANGED: '..spare.id..' is no longer byte-identical to '..spare.spare.twinOf
                    ..' outside its references')
                source_type=spare.currentDefault
                reviewed_settings=spare.referenceSettings
            elseif change.desired_selector.output then
                local source_candidate=assert(resolved.reference_sources[change.canonical_field],
                    'function projectile source was not freshly resolved')
                local source_record=component_record_for(resolved,source_candidate,change.source_descriptor.backing)
                source_type=b.u32(source_record.bytes,change.source_descriptor.backing.offset)
                assert(source_type==change.source_descriptor.currentDefault.projectileType,
                    'CONFLICT: source projectile reference changed')
                reviewed_settings=change.source_descriptor.referenceSettings
            else
                source_type=b.u32(change.desired,0)
                reviewed_settings=change.descriptor.referenceSettings
            end
            if source_type~=0 then
                local settings=assert(resolved.roots.projectile.records[source_type],
                    'function projectile ProjectileSettings record absent')
                assert(reviewed_settings and settings.group==reviewed_settings.group
                    and settings.row==reviewed_settings.row and settings.kind==reviewed_settings.recordType
                    and settings.settings_type==reviewed_settings.settingsType,
                    'function projectile ProjectileSettings identity changed')
                source_identity={component='ProjectileSettings',projectile_type=source_type,
                    settings_group=settings.group,settings_row=settings.row,settings_type=settings.settings_type,
                    scope='function_projectile_source'}
            end
            change.desired=b.encode(source_type,'u32')
        elseif change.descriptor.type=='explosion_reference'then
            local reviewed=change.descriptor.currentDefault.explosionType
            local expected=b.encode(reviewed,'u32')
            local source_type=0
            if not change.desired_selector.is_null then
                local source_candidate=assert(resolved.reference_sources[change.canonical_field],
                    'explosion source was not freshly resolved')
                local source_projectile,source_projectile_type=projectile_for_candidate(resolved,
                    source_candidate,change.source_descriptor.referenceRole)
                local reviewed_projectile=change.source_descriptor.projectileSettings
                assert(source_projectile.group==reviewed_projectile.group
                    and source_projectile.row==reviewed_projectile.row
                    and source_projectile.kind==reviewed_projectile.recordType
                    and source_projectile.settings_type==reviewed_projectile.settingsType,
                    'source ProjectileSettings identity changed')
                source_type=b.u32(source_projectile.bytes,change.source_descriptor.backing.offset)
                assert(source_type==change.source_descriptor.currentDefault.explosionType,
                    'CONFLICT: source explosion reference changed')
                local settings=assert(resolved.roots.explosion.records[source_type],
                    'source ExplosionSettings record absent')
                local reviewed_settings=change.source_descriptor.referenceSettings
                assert(settings.group==reviewed_settings.group and settings.row==reviewed_settings.row
                    and settings.kind==reviewed_settings.recordType
                    and settings.settings_type==reviewed_settings.settingsType,
                    'source ExplosionSettings identity changed')
                source_identity={component='ExplosionSettings',record_index=settings.row,
                    projectile_type=source_projectile_type,explosion_type=source_type,
                    settings_group=settings.group,settings_row=settings.row,
                    settings_type=settings.settings_type,scope='explosion_reference_source'}
            end
            change.expected=expected;change.desired=b.encode(source_type,'u32')
        elseif change.descriptor.type=='overcharge_explosion_reference'then
            -- Both explosions still exist in the live ExplosionSettings table (rows are keyed by ExplosionType).
            for _,explosion_type in ipairs(change.explosion_types)do
                assert(resolved.roots.explosion and resolved.roots.explosion.records[explosion_type],
                    'overcharge explosion '..explosion_type..' is absent from the live explosion table')
            end
        end
        local expected=ownership.expected(change,current,nil,{target=spec.kind..' '..tostring(spec.weapon)
            ..(spec.attack and(' '..spec.attack)or'')})
        local identity
        if backing.kind=='entity_delta'then
            identity={component='EntityDelta:'..backing.component,component_type='semantic',
                record_index=change.descriptor.settingsIndex,unique_owner=false,
                owner_count=#change.descriptor.sharedWithWeapons+1,scope=change.descriptor.writeScope}
        elseif backing.kind=='component'then
            identity={component=backing.component,component_type=record.identity.componentType,
                record_index=record.identity.recordIndex,index_row=record.identity.indexRow,
                unique_owner=record.identity.uniqueOwner,owner_count=record.identity.ownerCount,
                scope=change.descriptor.writeScope}
        else
            identity={component=backing.settings..'Settings',component_type=backing.settingsType,
                record_index=backing.row,group=backing.group,record_kind=backing.recordType,
                unique_owner=not change.descriptor.affectsMultipleWeapons,
                owner_count=#change.descriptor.sharedWithWeapons+1,scope=change.descriptor.writeScope}
        end
        local offset=record.offset+backing.offset
        local key=tostring(owner.base)..':'..tostring(offset)..':'..tostring(backing.width)
        -- Differently sized fields over the same bytes (fire_mode.modes and the older fire-mode views)
        -- are never combined in one plan.
        for _,other in ipairs(plan.changes)do
            local other_field=other.canonical_field:gsub('%[%d+%]$','')
            if other.owner.base==owner.base and other_field~=change.canonical_field
                and other.offset<offset+backing.width and offset<other.offset+#other.desired then
                error('overlapping semantic fields are not proven aliases: '..other.label..' and '..change.field,0)
            end
        end
        local prior=physical[key]
        if prior then
            if prior.canonical_field==change.canonical_field then
                if prior.desired~=change.desired then
                    error('SEMANTIC_CONFLICT: '..prior.label..' and '..change.field
                        ..' resolve to the same backing bytes with different desired values',0)
                end
                for _,alias in ipairs(change.semantic_aliases)do
                    prior.semantic_aliases[#prior.semantic_aliases+1]=alias
                end
            else
                error('overlapping semantic fields are not proven aliases: '..prior.label
                    ..' and '..change.field,0)
            end
        else
            local item={label=change.field,canonical_field=change.canonical_field,
            semantic_aliases=change.semantic_aliases,owner=owner,offset=offset,field_offset=backing.offset,
            expected=expected,desired=change.desired,before=current,
            already_desired=current==change.desired,identity=identity,chain={identity},
            expect=change.expect,value=change.value,
            -- Entity delta data is byte-packed; the ammunition rows are aligned but opt in explicitly.
            packed=backing.kind=='entity_delta'or nil}
            if source_identity then item.chain[#item.chain+1]=source_identity end
            local slots=SLOT_SETS[change.descriptor.type]
            if slots then
                -- A native slot list is written as aligned 4-byte changes in one atomic transaction: every slot is
                -- conflict-checked, only changed slots are written, and no write crosses a page.
                for slot=0,slots-1 do
                    local at=slot*4+1
                    local part={label=change.field..'['..(slot+1)..']',
                        canonical_field=change.canonical_field..'['..(slot+1)..']',
                        semantic_aliases=change.semantic_aliases,owner=owner,offset=offset+slot*4,
                        field_offset=backing.offset+slot*4,expected=expected:sub(at,at+3),
                        desired=change.desired:sub(at,at+3),before=current:sub(at,at+3),
                        identity=identity,chain={identity},expect=change.expect,value=change.value}
                    part.already_desired=part.before==part.desired
                    plan.changes[#plan.changes+1]=part
                end
                if change.descriptor.type=='weapon_sound'then
                    -- The MIDI flag (+237): one byte, checked and written with the event slots.
                    local at=change.descriptor.midiOffset
                    local part={label=change.field..'.midi',canonical_field=change.canonical_field..'.midi',
                        semantic_aliases=change.semantic_aliases,owner=owner,offset=record.offset+at,field_offset=at,
                        expected=expected:sub(13,13),desired=change.desired:sub(13,13),before=current:sub(13,13),
                        identity=identity,chain={identity},expect=change.expect,value=change.value}
                    part.already_desired=part.before==part.desired
                    plan.changes[#plan.changes+1]=part
                end
                physical[key]=item
            else
                plan.changes[#plan.changes+1]=item;physical[key]=item
            end
            if change.descriptor.writeKind=='reorder_native_mode_vector'then
                local vector=change.descriptor.nativeModeVector
                assert(#vector==3 and(b.u32(record.bytes,144)==change.expect
                    or b.u32(record.bytes,144)==change.value),
                    'CONFLICT: native fire-mode vector changed')
                local companion_index
                for index=2,3 do if vector[index]==change.value then companion_index=index end end
                assert(companion_index,'destination fire mode is absent from native vector')
                local companion_offset=record.offset+144+(companion_index-1)*4
                local companion_current=record.bytes:sub(145+(companion_index-1)*4,
                    148+(companion_index-1)*4)
                local companion_expected=b.encode(change.value,'u32')
                local companion_desired=b.encode(change.expect,'u32')
                assert(companion_current==companion_expected or companion_current==companion_desired,
                    'CONFLICT: native fire-mode companion changed')
                local companion={label=change.field..'.allowed_slot',
                    canonical_field=change.canonical_field..'.allowed_slot',semantic_aliases={},
                    owner=owner,offset=companion_offset,expected=companion_expected,
                    desired=companion_desired,before=companion_current,
                    already_desired=companion_current==companion_desired,identity=identity,
                    chain={identity},expect=change.value,value=change.expect}
                plan.changes[#plan.changes+1]=companion
                physical[tostring(owner.base)..':'..tostring(companion_offset)..':4']=companion
            end
        end
    end
    return plan
end
return M
