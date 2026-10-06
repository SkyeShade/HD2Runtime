-- Identity-only typed builders. Metadata and method names never carry an address.
local metadata=require('hd2runtime/domains/metadata')
local catalog=require('hd2runtime/domains/catalog')
local player_weapons=require('hd2runtime/domains/player_weapon_authoring')
local composition=require('hd2runtime/domains/player_weapon_composition')
local M={}
function M.new(describe)
    local builders={}
    local function copy(value)
        if type(value)~='table'then return value end
        local result={};for key,item in pairs(value)do result[key]=copy(item)end;return result
    end
    local function target(key,domain)
        local resource=metadata.resources[key]
        local methods={}
        local function names()
            local result={}
            for name,f in pairs(catalog[key])do
                if domain==resource.kind or f.domain==domain then result[#result+1]=name end
            end
            table.sort(result);return result
        end
        function methods.read_target()return {resource=key,fields=names()}end
        function methods.describe()
            local result=describe(key)
            local fields={}
            for _,name in ipairs(names())do fields[name]=result.fields[name]end
            result.fields=fields;result.domain=domain
            return result
        end
        for method,next_domain in pairs(metadata.types[domain].methods)do
            local next_type=next_domain
            methods[method]=function()
                local found=false
                for _,available in ipairs(resource.domains)do if available==next_type then found=true end end
                assert(found,'domain is not mapped for '..resource.label..': '..next_type)
                return target(key,next_type)
            end
        end
        -- Methods live on the metatable; strict patch/transaction identity validation is unchanged.
        return setmetatable({resource=key,path=domain},{__index=methods})
    end
    local function explosion_target(name,role,phase)
        local attack=assert(composition.weapons[name].attacks[role],'unknown reviewed attack role')
        local action=assert(attack.terminal_actions[phase],'unknown terminal action phase: '..tostring(phase))
        assert(action.reference_type~=0 and action.linked_explosion_record,
            'terminal action has no reviewed ExplosionSettings reference')
        local explosion
        for _,candidate in ipairs(attack.explosions or{})do
            if candidate.explosionType==action.reference_type then explosion=candidate;break end
        end
        assert(explosion,'reviewed ExplosionSettings descriptor missing')
        local methods={}
        function methods.describe()return copy(explosion)end
        function methods.damage(self)return self end
        function methods.shrapnel()return copy(explosion.shrapnel)end
        return setmetatable({resource='player_weapon',path='explosion',weapon=name,
            attack=attack.role,phase=phase},{__index=methods})
    end
    local function terminal_target(name,role,phase)
        local attack=assert(composition.weapons[name].attacks[role],'unknown reviewed attack role')
        local action=assert(attack.terminal_actions[phase],'unknown terminal action phase: '..tostring(phase))
        local methods={}
        function methods.describe()return copy(action)end
        function methods.explosion()return explosion_target(name,attack.role,phase)end
        function methods.no_explosion()
            return {resource='player_weapon',path='no_explosion',weapon=name,
                attack=attack.role,phase=phase}
        end
        return setmetatable({resource='player_weapon',path='terminal_action',weapon=name,
            attack=attack.role,phase=phase},{__index=methods})
    end
    local function projectile_reference(name,role)
        local attack=assert(composition.weapons[name].attacks[role],'unknown reviewed attack role')
        local methods={}
        function methods.describe()return copy(attack)end
        function methods.terminal_action(_,phase)return terminal_target(name,attack.role,phase)end
        return setmetatable({resource='player_weapon',path='projectile_reference',weapon=name,
            attack=attack.role},{__index=methods})
    end
    -- Attack outputs (domains/attack_outputs.lua): what an attack emits, by native family. There is no common
    -- output reference: projectile outputs can replace a projectile host's reference; beam, arc, spray and
    -- melee outputs are catalogued with the reason they cannot (see docs/attack-outputs.md).
    local function attack_output_handle(identity)
        local catalog=require('hd2runtime/domains/attack_outputs')
        local id=catalog.outputs[identity]and identity or catalog.aliases[identity]
        local output=assert(id and catalog.outputs[id],'unknown attack output: '..tostring(identity))
        local methods={}
        -- The weapon-function mode label and icon this output's projectile shows (hd2.fields.presentation.*):
        -- native strings and icons only (sdk/AttackOutputCapabilities.json modePresentation).
        function methods.mode_labels()
            local names={}
            for key,item in pairs(catalog.modeLabels or{})do if item.offered then names[#names+1]=key end end
            table.sort(names);return names
        end
        -- The icon mode_icon = "auto" writes for a label: {icon, source} (exact_native or generic_fallback).
        function methods.mode_icon_for(_,label)
            local entry=assert(type(label)=='string'and(catalog.modeLabels or{})[label],
                'unknown mode label: '..tostring(label))
            return {icon=entry.icon,source=entry.iconSource}
        end
        function methods.mode_icons()
            local names={}
            for key,item in pairs(catalog.modeIcons or{})do if item.offered then names[#names+1]=key end end
            table.sort(names);return names
        end
        -- Projectile slots (research/projectile-builder): value handles naming this output's direct-hit damage,
        -- impact explosion or expiry explosion, for hd2.fields.projectile.direct_damage / impact_explosion /
        -- expiry_explosion on any selectable output (the base keeps its flight; only the reference moves).
        local SLOT_FIELDS={directDamage='projectile.direct_damage',impactExplosion='projectile.impact_explosion',
            expiryExplosion='projectile.expiry_explosion'}
        local function slot_handle(slot)
            local field=assert(output.slotFields and output.slotFields[SLOT_FIELDS[slot]],
                output.id..' has no projectile slots (not a selectable projectile output)')
            local slot_methods={}
            function slot_methods.describe()
                return {output=output.id,slot=slot,field=field.semanticFieldId,present=field.currentDefault~=0,
                    allowNone=field.allowNone,shared=field.shared}
            end
            return setmetatable({resource='attack_output_slot',output=output.id,slot=slot},{__index=slot_methods})
        end
        function methods.direct_damage()return slot_handle('directDamage')end
        function methods.impact_explosion()return slot_handle('impactExplosion')end
        function methods.expiry_explosion()return slot_handle('expiryExplosion')end
        function methods.describe()
            local slots
            if output.slotFields then
                slots={}
                for slot,field_id in pairs(SLOT_FIELDS)do
                    local field=output.slotFields[field_id]
                    slots[slot]={field=field_id,present=field.currentDefault~=0,allowNone=field.allowNone,
                        shared=field.shared,consumers=#field.sharedConsumers,references=field.consumerReferences}
                end
            end
            return {id=output.id,family=output.family,owner=copy(output.owner),
                compatibilityClass=output.compatibilityClass,selectable=output.editable==true,reason=output.reason,
                referenceScope=copy(output.referenceScope),fieldEffect=copy(output.fieldEffect),
                spare=output.spare and{twinOf=output.spare.twinOf,independent=true,borrowedVanillaRow=true,
                    interim=true}or nil,slots=slots,
                presentation=output.presentationFields and{
                    label=output.presentationFields['presentation.mode_label'].currentDefault,
                    icon=output.presentationFields['presentation.mode_icon'].currentDefault,
                    shared=output.presentationFields['presentation.mode_label'].shared,
                    fields={label='presentation.mode_label',icon='presentation.mode_icon'}}or nil}
        end
        return setmetatable({resource='attack_output',output=output.id},{__index=methods})
    end
    -- A programmable (ProgrammableAmmo) mode built from existing pieces: a base projectile output, optional slot
    -- overrides on that base and the mode's label and icon. operations(spec) returns the ensure requests that make
    -- it, one per backing object (the weapon's binding and function projectile; the base's slots; the base's and the
    -- weapon's own presentation), for hd2.ensure. No new native row is created: a spare twin base is an independent
    -- native row; writing any other base's row changes every entity that fires it (allow_shared when that is more
    -- than one). The spec's own acknowledgements are passed on; the builder never adds one.
    local function programmable_builder(name,weapon_target)
        local methods={}
        local function feed()
            for _,item in ipairs(weapon_target:feeds())do
                if item:describe().mechanism=='programmable_ammo'then return item end
            end
            error(name..' has no programmable-ammunition feed (see weapon:feeds())',0)
        end
        function methods.bases()
            local catalog=require('hd2runtime/domains/attack_outputs')
            local ids={}
            for id,output in pairs(catalog.outputs)do
                local scoped=not output.referenceScope
                for _,field in ipairs(output.referenceScope or{})do
                    if field=='function_ammo.projectile'then scoped=true end
                end
                if output.family=='projectile'and output.editable==true and scoped then ids[#ids+1]=id end
            end
            table.sort(ids)
            local result={}
            for index,id in ipairs(ids)do result[index]=attack_output_handle(id)end
            return result
        end
        function methods.describe()
            local source=feed():source()
            return {weapon=name,feed='programmable',writable=source.writable,reason=source.reason,
                binding=copy(source.binding),bases=#methods.bases(),
                slots={'direct_damage','impact_explosion','expiry_explosion'},
                presentation={label='a native mode label',icon='a native icon, or "auto" (the default when a label is '
                    ..'given: the exact native icon of the label, else the plain round)'},
                acknowledgements={'allow_unverified_effect','allow_unverified_reference'},
                note='A slot or presentation write changes every entity that fires the base row (its owner weapon '
                    ..'included); a row more than one entity fires needs allow_shared. A spare twin has none.'}
        end
        -- The acknowledgements a spec gives, copied onto one request body (only those the spec sets).
        local function acknowledged(body,spec,keys)
            for _,key in ipairs(keys)do if spec[key]==true then body[key]=true end end
            return body
        end
        -- The mode label and icon ensure request for one output ("auto" icon unless one is named: the plain round,
        -- never the empty placeholder).
        local function presentation_request(target,id,label,icon,spec)
            if label==nil and icon==nil then return nil end
            local view=target:describe().presentation
            local items={}
            if label~=nil then items[#items+1]={field='presentation.mode_label',expect=view.label,value=label}end
            items[#items+1]={field='presentation.mode_icon',expect=view.icon,value=icon or'auto'}
            local request={transaction=acknowledged({id=id,target=target,changes=items},spec,
                {'allow_unverified_effect','allow_shared'})}
            if spec.enabled~=nil then request.enabled=spec.enabled end
            return request
        end
        -- The base output(s) of a spec: a fixed attack output or every value of an options choice.
        local function spec_bases(spec)
            local options=require('hd2runtime/api/options')
            local chosen=options.is_handle(spec.base)
            local bases
            if chosen then
                assert(spec.base.kind=='choice','a programmable mode base option must be a choice')
                bases=spec.base:samples()
            else
                bases={spec.base}
            end
            for _,item in ipairs(bases)do
                assert(type(item)=='table'and item.resource=='attack_output',
                    'programmable mode spec requires base=hd2.attack_output(name) (or a choice of them)')
            end
            return bases,chosen
        end
        -- A label or icon for one base: a string, or a map from attack output name (any hd2.attack_output identity)
        -- to the string, so a choice base names each value's own label.
        local function per_base(value,item,label)
            if type(value)~='table'then return value end
            local catalog=require('hd2runtime/domains/attack_outputs')
            local found
            for key,entry in pairs(value)do
                local id=type(key)=='string'and(catalog.outputs[key]and key or catalog.aliases[key])
                assert(id,label..' map names an unknown attack output: '..tostring(key))
                if id==item.output then found=entry end
            end
            return found
        end
        -- Only the menu presentation: spec {id, base= (optional, as for operations), label=, icon= (a string, or with a
        -- choice base a map from output name to string), primary_label=, primary_icon= (the weapon's own mode),
        -- enabled=, allow_shared=}. Lets a separate option drive the labels.
        function methods.presentation(_,spec)
            assert(type(spec)=='table'and type(spec.id)=='string','programmable mode spec requires an id')
            local requests={}
            local function add(request)if request then requests[#requests+1]=request end end
            if spec.base~=nil then
                local bases,chosen=spec_bases(spec)
                for index,item in ipairs(bases)do
                    add(presentation_request(item,spec.id..'-label'..(chosen and'-'..index or''),
                        per_base(spec.label,item,'label'),per_base(spec.icon,item,'icon'),spec))
                end
            else
                assert(spec.label==nil and spec.icon==nil,'a mode label or icon needs the base it is shown for')
            end
            add(presentation_request(attack_output_handle(name),spec.id..'-primary-label',spec.primary_label,
                spec.primary_icon,spec))
            return requests
        end
        -- spec: {id, base=hd2.attack_output(...) or an options choice whose values are attack outputs,
        -- direct_damage=, impact_explosion=, expiry_explosion= (slot handles or "none"; a fixed base only),
        -- label=, icon= (default "auto" with a label; with a choice base, a map from output name to string),
        -- primary_label=, primary_icon= (the weapon's own mode), enabled= (an options toggle, applied to every
        -- request), allow_unverified_effect=, allow_unverified_reference=, allow_shared= (passed on as given)}
        function methods.operations(_,spec)
            assert(type(spec)=='table'and type(spec.id)=='string','programmable mode spec requires an id')
            local _,chosen=spec_bases(spec)
            local base=spec.base
            local source=feed():source()
            assert(source.writable,name..': the programmable feed is not writable: '..tostring(source.reason))
            local requests={}
            local function add(request)
                if spec.enabled~=nil then request.enabled=spec.enabled end
                requests[#requests+1]=request
            end
            local changes={}
            if source.binding then changes[#changes+1]={field=source.binding.field,expect=source.binding.expect,
                value=source.binding.value}end
            changes[#changes+1]={field='function_ammo.projectile',expect=source.expect,value=base}
            add({transaction=acknowledged({id=spec.id..'-mode',target=source.target,changes=changes},spec,
                {'allow_unverified_effect','allow_unverified_reference'})})
            local slots={}
            for _,item in ipairs({{'direct_damage','projectile.direct_damage'},
                    {'impact_explosion','projectile.impact_explosion'},{'expiry_explosion','projectile.expiry_explosion'}})do
                local value=spec[item[1]]
                if value~=nil then
                    assert(not chosen,'slot overrides ('..item[1]..') need a fixed base, not a choice')
                    local own=base[item[1]](base)
                    slots[#slots+1]={field=item[2],expect=own:describe().present and own or'none',value=value}
                end
            end
            if #slots>0 then
                add({transaction=acknowledged({id=spec.id..'-slots',target=base,changes=slots},spec,
                    {'allow_unverified_effect','allow_shared'})})
            end
            for _,request in ipairs(methods.presentation(nil,spec))do requests[#requests+1]=request end
            return requests
        end
        return methods
    end
    function builders.attack_output(identity)return attack_output_handle(identity)end
    -- Catalogued output IDs ({family=..., selectable=true} filters).
    function builders.attack_outputs(filter)
        local catalog=require('hd2runtime/domains/attack_outputs')
        local ids={}
        for id,output in pairs(catalog.outputs)do
            if not filter or((not filter.family or output.family==filter.family)
                and(filter.selectable==nil or(output.editable==true)==filter.selectable))then ids[#ids+1]=id end
        end
        table.sort(ids)
        return ids
    end
    -- A weapon's default ammunition (domains/attack_outputs.lua `ammunition`): where the fired projectile lives when
    -- the ammunition's entity delta patches ProjectileWeapon +0 at weapon build. Writes go through
    -- hd2.fields.ammunition.projectile with allow_shared and allow_unverified_effect.
    local function ammunition_view(name)
        local entry=assert(require('hd2runtime/domains/attack_outputs').ammunition[name],'NO_AMMUNITION_SOURCE: '
            ..name..' has no reviewed default ammunition that owns its fired projectile (see attack:projectile_source())')
        return entry,{weapon=name,semanticId=entry.id,item=entry.item,compatibilityClass=entry.compatibilityClass,
            sharedWithWeapons=copy(entry.sharedWithWeapons),appliesWhen=entry.appliesWhen,
            acknowledgements={'allow_shared','allow_unverified_effect'},reason=entry.acknowledgementReason}
    end
    local function ammunition_target(name)
        local _,view=ammunition_view(name)
        local methods={}
        function methods.describe()return copy(view)end
        function methods.projectile()
            local projectile_methods={}
            function projectile_methods.describe()return copy(view)end
            return setmetatable({resource='player_weapon',path='ammunition_projectile',weapon=name},
                {__index=projectile_methods})
        end
        return setmetatable({resource='player_weapon',path='ammunition',weapon=name},{__index=methods})
    end
    local projectile_source
    local function attack_target(name,role)
        local attack=assert(composition.weapons[name].attacks[role],
            'unknown reviewed attack role for '..name..': '..tostring(role))
        local methods={}
        function methods.describe()return copy(attack)end
        function methods.projectile()return projectile_reference(name,attack.role)end
        -- Where this attack's fired projectile lives, and the target/field that changes it (if any).
        function methods.projectile_source()return projectile_source(name,attack.role)end
        -- The output this weapon's attack emits (its family component's reference), as a typed handle.
        function methods.output()
            assert(attack.role=='primary','attack outputs are catalogued for the primary attack')
            return attack_output_handle(name)
        end
        return setmetatable({resource='player_weapon',path='attack',weapon=name,attack=attack.role},
            {__index=methods})
    end
    -- The active projectile source of a player attack (sdk/AttackOutputCapabilities.json projectileSources).
    -- writable=true only where changing the returned target's field changes the projectile the weapon fires.
    projectile_source=function(name,role)
        local catalog=require('hd2runtime/domains/attack_outputs')
        local source=assert((catalog.sources[name]or{})[role],
            'no classified projectile source for '..name..' attack '..tostring(role))
        local result={weapon=name,attack=role,status=source.status,mechanism=source.mechanism,member=source.member,
            reason=source.reason,writable=false}
        if source.mechanism=='component'and source.status=='ACTIVE_DIRECT'and source.previouslyWritable then
            local target=attack_target(name,role)
            result.writable=true;result.target=target;result.field='attack.projectile'
            result.expect=target:projectile();result.acknowledgements={}
        elseif source.mechanism=='ammunition'and catalog.ammunition[name]then
            local target=ammunition_target(name)
            result.writable=true;result.target=target;result.field='ammunition.projectile'
            result.expect=target:projectile();result.acknowledgements={'allow_shared','allow_unverified_effect'}
        end
        return result
    end
    local function magazine_target(name,option)
        local methods={};function methods.describe()return copy(option)end
        return setmetatable({resource='player_weapon',path='magazine_option',weapon=name,
            option=option.optionId or option.name},{__index=methods})
    end
    local function attachment_target(name,category,option)
        local methods={};function methods.describe()return copy(option)end
        return setmetatable({resource='player_weapon',path='attachment_option',weapon=name,
            category=category,option=option.name},{__index=methods})
    end
    local function attachment_category(graph,category)
        for _,item in ipairs(graph.magazine.attachment_categories or{})do
            if item.category==category then return item end
        end
    end
    local attachment_authoring=require('hd2runtime/domains/attachment_authoring')
    -- Native fire-mode sets (four packed FireMode slots); written through hd2.fields.fire_mode.*.
    local fire_mode_table=require('hd2runtime/domains/weapon_fire_modes')
    local function magazine_attachment_target(identity,relationship,option_name)
        local entry=assert(attachment_authoring.attachments[identity],'unknown reviewed magazine attachment')
        local methods={}
        function methods.describe()
            local fields={}
            for field_id,field in pairs(entry.fields)do
                fields[#fields+1]={semanticFieldId=field_id,instanceKey=field.instanceKey,
                    currentDefault=field.currentDefault,editable=true,
                    acknowledgements={'allow_shared','allow_unverified_effect'}}
            end
            table.sort(fields,function(a,b)return a.semanticFieldId<b.semanticFieldId end)
            return {semanticId=entry.semanticId,name=entry.name,slot='magazine',
                relationship=relationship,option=option_name,fields=fields}
        end
        return setmetatable({resource='weapon_attachment',attachment=entry.semanticId,path='magazine'},
            {__index=methods})
    end
    -- Rate-of-fire modes, feeds and presentation (domains/weapon_modes.lua, domains/weapon_presentation.lua): read views
    -- over the weapon's own field descriptors. Writes use the weapon target and hd2.fields.fire_rate.modes,
    -- hd2.fields.weapon_function.*, hd2.fields.function_ammo.projectile and hd2.fields.presentation.*.
    local weapon_modes=require('hd2runtime/domains/weapon_modes')
    local presentation_catalog=require('hd2runtime/domains/weapon_presentation')
    -- Rate slots in storage and weapon-menu order, and the order the selector visits them from the default (Y).
    local SLOT_NAMES,SELECTOR_ORDER={'x','y','z'},{'y','z','x'}
    local function field_of(entry,id)
        for _,field in ipairs(entry and entry.fields or{})do if field.semanticFieldId==id then return field end end
    end
    -- What a write of this field must acknowledge, and its live proof: a live-proven pair needs nothing, a
    -- value-scoped one nothing for its liveProvenValues (schemas/live_evidence.json).
    local function acknowledgements_of(field)
        return field and field.acknowledgement and{field.acknowledgement}or{}
    end
    local function live_of(field)
        if not(field and field.liveEvidence)then return nil end
        return {family=field.liveEvidence.family,tests=copy(field.liveEvidence.tests),
            values=copy(field.liveProvenValues)}
    end
    local function rate_modes(entry,kind,name)
        local field=field_of(entry,'fire_rate.modes')
        local modes_entry=weapon_modes.feeds[kind..':'..name]
        if not field then
            return {weapon=name,state=modes_entry and modes_entry.fireRateState or'absent',modes={},writable=false,
                reason='rate-of-fire modes are not authored for '..name..' (see WeaponFireRateCapabilities.json)'}
        end
        -- slots: all three, in storage order. modes: the filled ones in the order the weapon menu lists them, each
        -- with its slot and the selector presses that reach it from the default.
        local slots,modes,by_slot,selector_order={},{},{},{}
        for index,slot_name in ipairs(SLOT_NAMES)do
            local rpm=(field.currentDefault or{})[index]or 0
            slots[index]={slot=slot_name,index=index,rpm=rpm,enabled=rpm~=0,default=slot_name=='y'}
            by_slot[slot_name]=slots[index]
        end
        for _,slot_name in ipairs(SELECTOR_ORDER)do
            local slot=by_slot[slot_name]
            if slot.enabled then slot.presses=#selector_order;selector_order[#selector_order+1]=slot_name end
        end
        for _,slot in ipairs(slots)do
            if slot.enabled then modes[#modes+1]=slot;slot.menu=#modes end
        end
        local binding
        local acknowledgements=acknowledgements_of(field)
        if not field.selectorBound and field.bindableInputs and field.bindableInputs[1]then
            binding={field='weapon_function.'..field.bindableInputs[1],expect='none',value='rate_of_fire'}
            -- The binding keeps its own acknowledgement unless rate_of_fire is live-proven on this input.
            local input=field_of(entry,binding.field)
            local proven=false
            for _,value in ipairs(input and input.liveProvenValues or{})do proven=proven or value=='rate_of_fire'end
            binding.acknowledgements=proven and{}or acknowledgements_of(input)
            binding.liveProven=proven and live_of(input)or nil
            for _,item in ipairs(binding.acknowledgements)do
                if item~=acknowledgements[1]then acknowledgements[#acknowledgements+1]=item end
            end
        end
        return {weapon=name,state=field.fireRateState,modes=modes,slots=slots,default=by_slot.y,
            selectorOrder=selector_order,maxModes=field.maxModes,
            selector={bound=field.selectorBound==true,input=field.selectorInput,bindableInputs=copy(field.bindableInputs),
                order=copy(selector_order)},
            nativeSlots=copy(field.nativeSlots),field='fire_rate.modes',expect=copy(field.currentDefault),
            writable=field.editable==true,reason=field.reason,range={min=field.min,max=field.max},
            binding=binding,acknowledgements=acknowledgements,liveProven=live_of(field),
            overriddenWhenEquipped=copy(field.overriddenWhenEquipped)}
    end
    -- A mode by its menu position (1 = the top of the weapon menu) or by its slot ('x', 'y', 'z').
    local function rate_mode(entry,kind,name,index)
        local view=rate_modes(entry,kind,name)
        if type(index)=='string'then
            for _,slot in ipairs(view.slots or{})do if slot.slot==index then return slot end end
            error(name..' has no rate-of-fire slot '..index..' (slots are x, y and z)',2)
        end
        return assert(view.modes[index],name..' has no rate-of-fire mode '..tostring(index)..' ('..#view.modes
            ..' in its weapon menu)')
    end
    local function function_projectile_handle(kind,name,feed)
        local methods={};function methods.describe()return copy(feed)end
        return setmetatable({resource=kind=='player'and'player_weapon'or'support_weapon',path='function_projectile',
            weapon=name},{__index=methods})
    end
    local feed_handle
    local function feed_list(kind,name)
        local entry=weapon_modes.feeds[kind..':'..name]
        local result={}
        for index,feed in ipairs(entry and entry.feeds or{})do result[index]=feed_handle(kind,name,feed.id)end
        return result
    end
    feed_handle=function(kind,name,id)
        local entry=assert(weapon_modes.feeds[kind..':'..name],'no reviewed feeds for '..name)
        local feed
        for _,item in ipairs(entry.feeds)do if item.id==id or item.index==id then feed=item end end
        assert(feed,'unknown feed for '..name..': '..tostring(id)..' (see weapon:feeds())')
        local methods={}
        function methods.describe()return copy(feed)end
        -- The projectile this feed fires: the handle its projectile and damage fields are edited through, or for a
        -- programmable feed the handle that restores its native projectile.
        function methods.projectile()
            if feed.mechanism=='programmable_ammo'then
                assert(feed.nativeProjectile,name..' has no native programmable projectile; give it one with '
                    ..'hd2.fields.function_ammo.projectile (see feed:source())')
                return function_projectile_handle(kind,name,feed)
            end
            if kind=='player'then return attack_target(name,feed.attackRole or'primary'):projectile()end
            return builders.support_weapon(name):attack('primary'):projectile()
        end
        -- Where this feed's projectile is written, like attack:projectile_source().
        function methods.source()
            if feed.mechanism=='programmable_ammo'then
                local binding
                if feed.requiresBinding and feed.selector.bindableInputs[1]then
                    binding={field='weapon_function.'..feed.selector.bindableInputs[1],expect='none',
                        value='programmable_ammo'}
                end
                return {weapon=name,feed=feed.id,mechanism=feed.mechanism,writable=feed.writable==true,
                    target=kind=='player'and builders.weapon(name)or builders.support_weapon(name),
                    field='function_ammo.projectile',expect=feed.nativeProjectile and methods.projectile()or'none',
                    binding=binding,acknowledgements={'allow_unverified_effect','allow_unverified_reference'},
                    reason=feed.reason}
            end
            if kind=='player'and feed.mechanism=='projectile'then return projectile_source(name,'primary')end
            if kind=='support'and feed.mechanism=='projectile'then
                return builders.support_weapon(name):projectile_source('primary')
            end
            return {weapon=name,feed=feed.id,mechanism=feed.mechanism,writable=false,
                reason=feed.projectileSource and feed.projectileSource.reason or nil}
        end
        return setmetatable({resource=kind=='player'and'player_weapon'or'support_weapon',path='feed',weapon=name,
            feed=feed.id},{__index=methods})
    end
    local function presentation_view(entry,name)
        local traits=field_of(entry,'presentation.traits');local penetration=field_of(entry,'presentation.armor_penetration')
        local shown={}
        for index,id in ipairs(traits and traits.currentDefault or{})do
            shown[index]={id=id,label=presentation_catalog.traits[id]}
        end
        local all={};for id in pairs(presentation_catalog.traits)do all[#all+1]=id end
        table.sort(all)
        local missing='not writable for '..name..' (see WeaponPresentationCapabilities.json)'
        return {weapon=name,traits=shown,armorPenetration=penetration and penetration.currentDefault or nil,
            fields={traits='presentation.traits',armorPenetration='presentation.armor_penetration'},
            writable={traits=traits and traits.editable==true or false,
                armorPenetration=penetration and penetration.editable==true or false},
            reason={traits=traits and traits.reason or(not traits and missing)or nil,
                armorPenetration=penetration and penetration.reason or(not penetration and missing)or nil},
            choices={armorPenetration=penetration and copy(penetration.allowedValues)or nil,traits=all},
            labels=copy(presentation_catalog.penetration),
            acknowledgements={traits=acknowledgements_of(traits),armorPenetration=acknowledgements_of(penetration)},
            liveProven={traits=live_of(traits),armorPenetration=live_of(penetration)},
            refresh='Menus build their trait labels when they open: reopen the armory or loadout screen.'}
    end
    -- A nested sub-weapon (research/underbarrel-weapons): the separate weapon entity a host's underbarrel item names.
    -- Its own component members are written on this target with the ordinary field constants
    -- (hd2.fields.weapon.horizontal_spread, hd2.fields.rounds.spare_rounds, ...).
    local function subweapon_target(name)
        local weapon=assert(player_weapons.weapons[name],'unknown reviewed sub-weapon: '..tostring(name))
        local methods={}
        function methods.describe()
            local fields={}
            for _,field in ipairs(weapon.fields)do
                fields[#fields+1]={semanticFieldId=field.semanticFieldId,displayName=field.displayName,
                    currentDefault=field.currentDefault,unit=field.unit,editable=field.editable,
                    acknowledgement=field.acknowledgement,apiFieldConstant=field.apiFieldConstant}
            end
            return {name=name,kind=weapon.kind,subweaponOf=weapon.subweaponOf,link=weapon.link,
                sharedDefinitions=copy(weapon.sharedDefinitions),notExposed=copy(weapon.notExposed),fields=fields}
        end
        return setmetatable({resource='player_weapon',path='weapon',weapon=name},{__index=methods})
    end
    local function player_target(name,legacy)
        local weapon=player_weapons.weapons[name]
        if weapon.subweaponOf then return subweapon_target(name)end
        local graph=composition.weapons[name]
        local methods={}
        function methods.describe()return weapon end
        -- The underbarrel weapon (AR/GL-21 One-Two grenade launcher, AR-11 Arbitrator shotgun, SMG/FLAM-34 Stoker
        -- flamer): a separate weapon entity with its own spread, rounds and fire rate.
        function methods.underbarrel()
            for _,sub in ipairs(weapon.subweapons or{})do
                if sub.kind=='underbarrel'then return subweapon_target(sub.name)end
            end
            error(name..' has no reviewed underbarrel weapon',0)
        end
        function methods.read_target()
            error('generic player-weapon live reads use the mapper/capability API')
        end
        if legacy then
            for method in pairs(metadata.types.weapon.methods)do
                if legacy[method]then methods[method]=function()return legacy[method](legacy)end end
            end
        end
        function methods.attacks()
            local result={};for _,role in ipairs(graph.attack_order)do
                result[#result+1]=attack_target(name,role)
            end
            return result
        end
        function methods.attack(_,role)return attack_target(name,role)end
        -- The default ammunition that owns this weapon's fired projectile (weapons classified INDIRECT only).
        function methods.ammunition()return ammunition_target(name)end
        function methods.projectile_source(_,role)return projectile_source(name,role or'primary')end
        function methods.fire_modes()
            local result=copy(graph.fire_mode)
            result.modeSet=copy(fire_mode_table.weapons['player:'..name])
            return result
        end
        -- The native rate-of-fire modes in selector order (the first is the default, weapon.fire_rate).
        function methods.fire_rate_modes()return rate_modes(weapon,'player',name)end
        function methods.fire_rate_mode(_,index)return rate_mode(weapon,'player',name,index)end
        -- Selectable ammunition/output sources: rounds magazines, the ProgrammableAmmo projectile.
        function methods.feeds()return feed_list('player',name)end
        function methods.feed(_,id)return feed_handle('player',name,id)end
        function methods.programmable_ammo(self)return programmable_builder(name,self)end
        -- The armory trait labels (presentation only).
        function methods.presentation()return presentation_view(weapon,name)end
        function methods.magazine_options()
            local result={};local category=attachment_category(graph,'Magazine')
            for _,option in ipairs(category and category.options or graph.magazine.observed_options)do
                result[#result+1]=magazine_target(name,option)
            end
            return result
        end
        function methods.default_magazine()
            local category=attachment_category(graph,'Magazine')
            if category then for _,option in ipairs(category.options)do
                if option.default then return magazine_target(name,option)end
            end end
            local option=graph.magazine.default_option
            return option and magazine_target(name,option)or nil
        end
        function methods.magazine(_,identity)
            local category=attachment_category(graph,'Magazine')
            if category then for _,option in ipairs(category.options)do
                local native=option.nativeOption
                if identity==option.name or native and identity==native.optionId then
                    return magazine_target(name,option)
                end
            end end
            local option=graph.magazine.default_option
            if option and(identity==option.name or identity==option.optionId)then
                return magazine_target(name,option)
            end
            for _,candidate in ipairs(graph.magazine.observed_options)do
                if identity==candidate.name or identity==candidate.optionId then
                    return magazine_target(name,candidate)
                end
            end
            error('unknown reviewed magazine option for '..name..': '..tostring(identity))
        end
        function methods.attachment_options(_,category)
            local item=assert(attachment_category(graph,category),
                'unknown reviewed attachment category for '..name..': '..tostring(category))
            local result={};for _,option in ipairs(item.options)do
                result[#result+1]=attachment_target(name,category,option)
            end
            return result
        end
        function methods.attachment(_,category,identity)
            local item=assert(attachment_category(graph,category),
                'unknown reviewed attachment category for '..name..': '..tostring(category))
            for _,option in ipairs(item.options)do if option.name==identity then
                return attachment_target(name,category,option)end end
            error('unknown reviewed attachment for '..name..': '..tostring(identity))
        end
        function methods.magazine_attachments()
            local slot=attachment_authoring.weapons[name]
            local result={}
            if not slot then return result end
            local seen={}
            if slot.default then
                local label
                for _,option in ipairs(slot.options)do if option.attachment==slot.default then label=option.name end end
                result[#result+1]=magazine_attachment_target(slot.default,'native_resource_default',label)
                seen[slot.default]=true
            end
            for _,option in ipairs(slot.options)do
                if option.attachment and not seen[option.attachment]then
                    seen[option.attachment]=true
                    result[#result+1]=magazine_attachment_target(option.attachment,option.relationship,option.name)
                end
            end
            return result
        end
        function methods.magazine_attachment(_,identity)
            local slot=assert(attachment_authoring.weapons[name],'weapon has no reviewed magazine attachment slot: '..name)
            if identity==nil or identity=='default'then
                return magazine_attachment_target(assert(slot.default,'weapon has no native default magazine attachment'),
                    'native_resource_default')
            end
            for _,option in ipairs(slot.options)do
                if option.name==identity or option.attachment==identity
                    or(option.nativeName~=nil and option.nativeName==identity)then
                    assert(option.attachment,'magazine option '..tostring(identity)..' has no uniquely proven native '
                        ..'attachment ('..option.relationship..')')
                    return magazine_attachment_target(option.attachment,option.relationship,option.name)
                end
            end
            if identity==slot.default then return magazine_attachment_target(slot.default,'native_resource_default')end
            error('unknown magazine attachment for '..name..': '..tostring(identity),0)
        end
        return setmetatable({resource='player_weapon',path='weapon',weapon=name},{__index=methods})
    end
    for method,domain in pairs(metadata.builders)do
        local kind=domain
        builders[method]=function(name)
            for key,resource in pairs(metadata.resources)do
                if resource.kind==kind then
                    for _,alias in ipairs(resource.aliases)do
                        if name==alias then
                            local legacy=target(key,kind)
                            if kind=='weapon'and player_weapons.weapons[name]then
                                return player_target(name,legacy)
                            end
                            return legacy
                        end
                    end
                end
            end
            if kind=='weapon'and player_weapons.weapons[name]then
                return player_target(name)
            end
            error('unknown reviewed '..kind..' alias: '..tostring(name))
        end
    end
    local support_catalog=require('hd2runtime/domains/support_weapon_catalog')
    local support_authoring=require('hd2runtime/domains/support_weapon_authoring')
    local support_attack
    -- The reviewed attack role of a catalog branch: the authoring catalogue's own where it re-resolved a branch the
    -- read-only mapper matched heuristically (branchRoles: the PLAS-45 Epoch charge levels, the overcharge explosions;
    -- research/charge-explosions-F5FEE03DCFDB.json), else the mapper's runtime match.
    local function support_role(name,attack)
        local authoring=support_authoring.weapons[name]
        local roles=authoring and authoring.branchRoles
        if roles and roles[attack.name]~=nil then return roles[attack.name]end
        return attack.runtimeMatch and attack.runtimeMatch.runtimeAttackRole
    end
    -- The active projectile source of a support attack, like attack:projectile_source() on a player weapon: the same
    -- host rule (research/projectile-builder supportHosts), writable where the weapon is a component host.
    local function support_projectile_source(name,role)
        local catalog=require('hd2runtime/domains/attack_outputs')
        local source=(catalog.supportSources or{})[name]
        local result={weapon=name,attack=role,writable=false,
            reason='no classified projectile source for '..name..' attack '..tostring(role)}
        if not source then return result end
        result.status=source.status;result.mechanism=source.mechanism;result.member=source.member
        result.reason=source.reason;result.compatibilityClass=source.compatibilityClass
        local authoring=support_authoring.weapons[name]
        for _,field in ipairs(authoring and authoring.fields or{})do
            if field.semanticFieldId=='attack.'..tostring(role)..'.projectile'and field.editable then
                local weapon=support_catalog.weapons[name]
                for index,item in ipairs(weapon.attackGraph)do
                    if support_role(name,item)==role then
                        local target=support_attack(name,index)
                        result.writable=true;result.target=target;result.field='attack.projectile'
                        result.expect=target:projectile();result.acknowledgements={'allow_unverified_effect'}
                        return result
                    end
                end
            end
        end
        return result
    end
    support_attack=function(name,index)
        local weapon=assert(support_catalog.weapons[name],'unknown reviewed support weapon')
        local attack=assert(weapon.attackGraph[index],'unknown support weapon attack index')
        local role=support_role(name,attack)
        local authoring=support_authoring.weapons[name]
        local writable=role and authoring and authoring.attacks[role]
        local methods={}
        function methods.describe()return copy(attack)end
        function methods.projectile()
            assert(writable and writable.kind=='Projectile','attack has no writable reviewed projectile object')
            local projectile_methods={}
            function projectile_methods.describe()return copy(writable)end
            function projectile_methods.damage(self)return self end
            return setmetatable({resource='support_weapon',path='projectile_reference',weapon=name,
                attack=role},{__index=projectile_methods})
        end
        function methods.explosion()
            assert(writable and writable.kind=='Explosion','attack has no writable reviewed explosion object')
            local explosion_methods={}
            function explosion_methods.describe()return copy(writable)end
            function explosion_methods.damage(self)return self end
            return setmetatable({resource='support_weapon',path='explosion',weapon=name,
                attack=role},{__index=explosion_methods})
        end
        function methods.damage(self)
            assert(writable and writable.kind~='Status','attack has no directly owned DamageInfo')
            return self
        end
        function methods.output()return attack_output_handle(name)end
        -- Where this attack's fired projectile lives, and the target/field that changes it (if any).
        function methods.projectile_source()return support_projectile_source(name,role or'primary')end
        local identity={resource='support_weapon',path=writable and'attack'or'attack_read_only',weapon=name}
        if writable then identity.attack=role else identity.attack_index=index end
        return setmetatable(identity,{__index=methods})
    end
    -- Backpack-fed support weapons draw ammunition from their backpack's DepositComponent, not from a
    -- weapon magazine; the backpack is the semantic owner (sdk/BackpackAuthoringCapabilities.json).
    local fed_backpacks=require('hd2runtime/domains/entity_authoring').backpacks
    local function ammo_backpack(weapon)
        for name,entry in pairs(fed_backpacks)do
            if entry.feeds and entry.feeds.weapon==weapon then return name end
        end
    end
    function builders.support_weapon(name)
        local weapon=assert(support_catalog.weapons[name],
            'unknown reviewed support weapon: '..tostring(name))
        local methods={}
        -- The backpack that stores this weapon's ammunition.
        function methods.backpack()
            local backpack=ammo_backpack(name)
            if not backpack then
                error(name..' has no reviewed ammunition backpack (its ammunition is not backpack-owned)',0)
            end
            return builders.backpack(backpack)
        end
        function methods.describe()
            local result=copy(weapon);local authoring=support_authoring.weapons[name]
            result.authoring={writable=authoring and not authoring.ordinaryWritesBlocked or false,
                blockReason=authoring and authoring.blockReason or nil,
                writableFieldCount=authoring and#authoring.fields or 0}
            result.ammoBackpack=ammo_backpack(name)
            return result
        end
        function methods.attacks()
            local result={};for index=1,#weapon.attackGraph do result[index]=support_attack(name,index)end
            return result
        end
        function methods.attack(_,identity)
            if type(identity)=='number'then return support_attack(name,identity)end
            for index,item in ipairs(weapon.attackGraph)do
                if item.name==identity or support_role(name,item)==identity then return support_attack(name,index)end
            end
            error('unknown reviewed support attack: '..tostring(identity))
        end
        function methods.projectile(_,identity)return methods.attack(nil,identity):projectile()end
        function methods.explosion(_,identity)return methods.attack(nil,identity):explosion()end
        function methods.projectile_source(_,role)return support_projectile_source(name,role or'primary')end
        function methods.fire_modes()return {modeSet=copy(fire_mode_table.weapons['support:'..name])}end
        function methods.fire_rate_modes()return rate_modes(support_authoring.weapons[name],'support',name)end
        function methods.fire_rate_mode(_,index)return rate_mode(support_authoring.weapons[name],'support',name,index)end
        function methods.feeds()return feed_list('support',name)end
        function methods.feed(_,id)return feed_handle('support',name,id)end
        function methods.programmable_ammo(self)return programmable_builder(name,self)end
        function methods.presentation()return presentation_view(support_authoring.weapons[name],name)end
        return setmetatable({resource='support_weapon',path='weapon',weapon=name},{__index=methods})
    end
    local legacy_stratagem=builders.stratagem
    local stratagem_authoring=require('hd2runtime/domains/stratagem_authoring')
    local function public_field(field)
        return {instanceKey=field.instanceKey,semanticFieldId=field.semanticFieldId,
            displayName=field.displayName,type=field.type,unit=field.unit,
            currentDefault=copy(field.currentDefault),editable=field.editable,
            reason=field.reason,backingObjectId=field.backingObjectId,
            operationGroup=field.operationGroup,planGroup=field.planGroup,
            requires=field.requires,allowSharedRequired=field.allowSharedRequired,
            shared=field.shared,sharedConsumers=copy(field.sharedConsumers),
            provenance=field.provenance}
    end
    local function stratagem_attack(name,role)
        local entry=assert(stratagem_authoring.stratagems[name])
        local attack=assert(entry.attacks[role],'unknown reviewed stratagem attack: '..tostring(role))
        local deployed=false
        for _,field in ipairs(entry.fields)do
            if field.target.attack==role and field.target.entity then deployed=true;break end
        end
        local methods={}
        function methods.describe()
            local result=copy(attack);result.fieldInstances={}
            for _,field in ipairs(entry.fields)do if field.target.attack==role then
                result.fieldInstances[#result.fieldInstances+1]=public_field(field)end end
            return result
        end
        function methods.projectile(self)
            assert(attack.kind=='ProjectileSettings','attack is not a projectile settings object');return self
        end
        function methods.explosion(self)
            assert(attack.kind=='ExplosionSettings','attack is not an explosion settings object');return self
        end
        function methods.damage(self)
            assert(attack.kind=='DamageInfo','attack is not a DamageInfo object');return self
        end
        function methods.status(self)
            assert(attack.kind=='StatusEffectSettings','attack is not a status settings object');return self
        end
        function methods.arc(self)
            assert(attack.kind=='ArcSettings','attack is not an arc settings object');return self
        end
        function methods.beam(self)
            assert(attack.kind=='BeamSettings','attack is not a beam settings object');return self
        end
        local identity={resource='stratagem',stratagem=name,path='attack',attack=role}
        if deployed then identity.entity='main';identity.weapon=attack.weapon or'primary'end
        return setmetatable(identity,{__index=methods})
    end
    local function stratagem_entity(name)
        local entry=assert(stratagem_authoring.stratagems[name])
        assert(entry.deployedEntity,'stratagem has no deployed entity definition')
        local methods={}
        function methods.describe()
            local result=copy(entry.deployedEntity);result.name=entry.name;result.fields={};result.weapons={}
            result.damageZones=copy(entry.damageZones or{});result.shield=copy(entry.shield)
            for _,field in ipairs(entry.fields)do
                local path=field.target.path
                if path=='deployed_entity' or path=='weapon' or path=='attack' or path=='shield'
                    or path=='damage_zone' or path=='turret' or path=='targeting' or path=='minefield' then
                    result.fields[#result.fields+1]=public_field(field)end
            end
            for role,attack in pairs(entry.attacks)do
                local weapon=attack.weapon or 'primary'
                result.weapons[weapon]=result.weapons[weapon] or {identity=weapon,attacks={}}
                result.weapons[weapon].attacks[#result.weapons[weapon].attacks+1]=role
            end
            return result
        end
        function methods.health(self)return self end
        function methods.weapon(_,identity)
            identity=identity or 'primary'
            local target={resource='stratagem',stratagem=name,path='weapon',entity='main',weapon=identity}
            local weapon_methods={}
            function weapon_methods.describe()
                local result={name=name,identity=identity,fields={},attacks={}}
                for _,field in ipairs(entry.fields)do
                    if field.target.path=='weapon' and field.target.weapon==identity
                        or field.target.path=='attack' and field.target.weapon==identity then
                        result.fields[#result.fields+1]=public_field(field)
                    end
                end
                for role,attack in pairs(entry.attacks)do
                    if (attack.weapon or 'primary')==identity then result.attacks[#result.attacks+1]=role end
                end
                table.sort(result.attacks);return result
            end
            function weapon_methods.attack(_,role)return stratagem_attack(name,role)end
            function weapon_methods.attacks()
                local result={}
                for role,attack in pairs(entry.attacks)do
                    if (attack.weapon or 'primary')==identity then result[#result+1]=stratagem_attack(name,role)end
                end
                table.sort(result,function(a,b)return a.attack<b.attack end);return result
            end
            return setmetatable(target,{__index=weapon_methods})
        end
        function methods.weapons()
            local result={};local seen={}
            for _,field in ipairs(entry.fields)do
                local identity=field.target.weapon
                if identity and not seen[identity]then seen[identity]=true;result[#result+1]=methods.weapon(nil,identity)end
            end
            for _,attack in pairs(entry.attacks)do
                local identity=attack.weapon or 'primary'
                if not seen[identity]then seen[identity]=true;result[#result+1]=methods.weapon(nil,identity)end
            end
            table.sort(result,function(a,b)return a.weapon<b.weapon end);return result
        end
        function methods.attack(_,role)return stratagem_attack(name,role)end
        local function sub_target(path,zone)
            local target={resource='stratagem',stratagem=name,path=path,entity='main',zone=zone}
            local sub={}
            function sub.describe()
                local result={name=name,path=path,zone=zone,fields={}}
                for _,field in ipairs(entry.fields)do
                    if field.target.path==path and field.target.zone==zone then
                        result.fields[#result.fields+1]=public_field(field)end
                end
                if path=='shield'then result.shield=copy(entry.shield)end
                if path=='turret'then result.turret=copy(entry.turret)end
                if path=='targeting'then result.targeting=copy(entry.targeting)end
                if path=='minefield'then result.minefield=copy(entry.minefield)end
                return result
            end
            return setmetatable(target,{__index=sub})
        end
        function methods.shield()
            assert(entry.shield,'deployed entity has no reviewed shield configuration')
            return sub_target('shield')
        end
        -- Sentry turret motion (turn speeds, aim limits) and target acquisition range.
        function methods.turret()
            assert(entry.turret,'deployed entity has no reviewed turret: '..name)
            return sub_target('turret')
        end
        function methods.targeting()
            assert(entry.targeting,'deployed entity has no reviewed targeting sensor: '..name)
            return sub_target('targeting')
        end
        -- Mine deployers: salvo count and mines per salvo (reductions only).
        function methods.minefield()
            assert(entry.minefield,'deployed entity is not a reviewed mine deployer: '..name)
            return sub_target('minefield')
        end
        local function zone_identity(identity)
            for _,zone in ipairs(entry.damageZones or{})do
                if identity==zone.zoneId or identity==zone.name
                    or type(identity)=='number'and zone.zoneId=='zone_'..identity then return zone.zoneId end
            end
            error('unknown reviewed damage zone for '..name..': '..tostring(identity),0)
        end
        function methods.damage_zones()
            local result={}
            for _,zone in ipairs(entry.damageZones or{})do result[#result+1]=sub_target('damage_zone',zone.zoneId)end
            return result
        end
        function methods.damage_zone(_,identity)return sub_target('damage_zone',zone_identity(identity))end
        return setmetatable({resource='stratagem',stratagem=name,path='deployed_entity',entity='main'},
            {__index=methods})
    end
    local entity_authoring=require('hd2runtime/domains/entity_authoring')
    local function entity_public(field)
        local result=public_field(field)
        result.target=copy(field.target);result.allowedValues=copy(field.allowedValues)
        result.acknowledgement=field.acknowledgement
        result.acknowledgementReason=field.acknowledgementReason
        result.min,result.max,result.uiGroup=field.min,field.max,field.uiGroup
        return result
    end
    local function fields_for(entry,path,key,value)
        local result={}
        for _,field in ipairs(entry.fields)do
            if field.target.path==path and(key==nil or field.target[key]==value)then
                result[#result+1]=entity_public(field)end
        end
        return result
    end
    local function weapon_view(identity)
        local weapon=assert(entity_authoring.mountedWeapons[identity],'unknown discovered mounted weapon')
        return {semanticId=weapon.semanticId,displayName=weapon.displayName,attackFamily=weapon.attackFamily}
    end
    local legacy_vehicle=builders.vehicle
    -- Mounted weapons: vehicle -> mount slot -> the mounted weapon entity's own records, and its
    -- shared projectile/damage/explosion rows (see sdk/VehicleWeaponCapabilities.json).
    local vehicle_weapons=require('hd2runtime/domains/vehicle_weapon_authoring')
    local function vehicle_weapon_target(key)
        local weapon=assert(vehicle_weapons.weapons[key],'unknown reviewed mounted weapon: '..tostring(key))
        local methods={}
        function methods.describe()
            local fields={}
            for _,field in ipairs(weapon.fields)do
                fields[#fields+1]={semanticFieldId=field.semanticFieldId,displayName=field.displayName,
                    currentDefault=field.currentDefault,unit=field.unit,editable=field.editable,
                    scope=field.writeScope,allowSharedRequired=field.affectsMultipleWeapons,
                    otherConsumers=copy(field.sharedWithWeapons),acknowledgement=field.acknowledgement,
                    target=copy(field.target)}
            end
            local attacks={};for role,attack in pairs(weapon.attacks)do attacks[#attacks+1]={role=role,kind=attack.kind}end
            table.sort(attacks,function(a,b)return a.role<b.role end)
            return {name=key,semanticId=weapon.semanticId,vehicle=weapon.vehicle,mount=weapon.mount,slot=weapon.slot,
                attacks=attacks,fields=fields}
        end
        function methods.attacks()
            local result={}
            for role in pairs(weapon.attacks)do result[#result+1]=methods.attack(nil,role)end
            table.sort(result,function(a,b)return a.attack<b.attack end)
            return result
        end
        -- Where a mounted attack's fired projectile lives (the same host rule and donor pool as player and support
        -- weapons): writable on a mounted component host through hd2.fields.attack.projectile.
        local function source(role)
            local catalog=require('hd2runtime/domains/attack_outputs')
            local row=(catalog.supportSources or{})[key]
            local result={weapon=key,attack=role,writable=false,
                reason='no classified projectile source for '..key..' attack '..tostring(role)}
            if not row then return result end
            result.status=row.status;result.mechanism=row.mechanism;result.member=row.member;result.reason=row.reason
            result.compatibilityClass=row.compatibilityClass;result.sharedEntity=copy(row.sharedEntity)
            for _,field in ipairs(weapon.fields)do
                if field.semanticFieldId=='attack.'..tostring(role)..'.projectile'and field.editable then
                    result.writable=true
                    result.target=setmetatable({resource='vehicle_weapon',path='attack',weapon=key,attack=role},
                        {__index={describe=function()return copy(weapon.attacks[role])end}})
                    result.field='attack.projectile';result.expect=methods.attack(nil,role)
                    result.acknowledgements=field.affectsMultipleWeapons and{'allow_shared','allow_unverified_effect'}
                        or{'allow_unverified_effect'}
                end
            end
            return result
        end
        function methods.attack(_,role)
            local attack=assert(weapon.attacks[role],'unknown mounted weapon attack for '..key..': '..tostring(role))
            local attack_methods={}
            function attack_methods.describe()return copy(attack)end
            function attack_methods.projectile_source()return source(role)end
            return setmetatable({resource='vehicle_weapon',path=attack.targetPath,weapon=key,attack=role},
                {__index=attack_methods})
        end
        function methods.projectile_source(_,role)return source(role or'primary')end
        function methods.projectile()return methods.attack(nil,'primary')end
        function methods.explosion(_,phase)return methods.attack(nil,phase or'impact')end
        return setmetatable({resource='vehicle_weapon',path='weapon',weapon=key},{__index=methods})
    end
    local function weapon_key(name,identity)
        local slots=vehicle_weapons.byVehicle[name] or{}
        if type(identity)=='number'then
            return assert(slots[tostring(identity)],'mount slot '..identity..' of '..name..' holds no reviewed weapon')
        end
        for _,key in pairs(slots)do
            local weapon=vehicle_weapons.weapons[key]
            if identity==key or identity==weapon.mount or identity==weapon.semanticId then return key end
        end
        error('unknown mounted weapon for '..name..': '..tostring(identity),0)
    end
    function builders.vehicle(name)
        local entry=entity_authoring.vehicles[name]
        if not entry then return legacy_vehicle(name)end
        local methods={}
        function methods.weapons()
            local slots={};for slot in pairs(vehicle_weapons.byVehicle[name] or{})do slots[#slots+1]=tonumber(slot)end
            table.sort(slots)
            local result={};for index,slot in ipairs(slots)do result[index]=vehicle_weapon_target(weapon_key(name,slot))end
            return result
        end
        function methods.weapon(_,identity)return vehicle_weapon_target(weapon_key(name,identity))end
        local function zone_target(zone)
            local zone_methods={}
            function zone_methods.describe()
                local info=entry.zones[zone]
                return {vehicle=name,zone=zone,index=info.index,name=info.name,
                    fields=fields_for(entry,'damage_zone','zone',zone)}
            end
            return setmetatable({resource='vehicle',vehicle=name,path='damage_zone',zone=zone},
                {__index=zone_methods})
        end
        local function zone_identity(identity)
            for zone,info in pairs(entry.zones)do
                if identity==zone or identity==info.name or identity==info.index then return zone end
            end
            error('unknown reviewed damage zone for '..name..': '..tostring(identity),0)
        end
        local function mount_target(mount)
            local info=entry.mounts[mount]
            local field
            for _,item in ipairs(entry.fields)do
                if item.target.path=='mount'and item.target.mount==mount then field=item end
            end
            local mount_methods={}
            function mount_methods.describe()
                return {vehicle=name,mount=mount,slot=info.slot,role=info.role,
                    current=weapon_view(info.current),fields=fields_for(entry,'mount','mount',mount)}
            end
            function mount_methods.current()return weapon_view(info.current)end
            -- The weapon currently in this mount, with its own editable fields.
            function mount_methods.weapon()return vehicle_weapon_target(weapon_key(name,info.slot))end
            function mount_methods.candidates()
                local result={}
                for _,identity in ipairs(field and field.allowedValues or{})do result[#result+1]=weapon_view(identity)end
                return result
            end
            function mount_methods.candidate(_,identity)
                local found
                for _,candidate in ipairs(mount_methods.candidates())do
                    if candidate.semanticId==identity or candidate.displayName==identity then
                        assert(not found,'mounted weapon display name is ambiguous; use its semanticId')
                        found=candidate
                    end
                end
                return assert(found,'not a compatible discovered mounted weapon: '..tostring(identity))
            end
            return setmetatable({resource='vehicle',vehicle=name,path='mount',mount=mount},
                {__index=mount_methods})
        end
        local function mount_identity(identity)
            for mount,info in pairs(entry.mounts)do
                if identity==mount or identity==info.role or identity==info.slot then return mount end
            end
            error('unknown swappable mount for '..name..': '..tostring(identity),0)
        end
        function methods.describe()
            local zones,mounts={},{}
            for zone,info in pairs(entry.zones)do zones[#zones+1]={zone=zone,index=info.index,name=info.name}end
            table.sort(zones,function(a,b)return a.index<b.index end)
            for mount,info in pairs(entry.mounts)do
                mounts[#mounts+1]={mount=mount,slot=info.slot,role=info.role,current=weapon_view(info.current)}
            end
            table.sort(mounts,function(a,b)return a.slot<b.slot end)
            return {name=name,semanticId=entry.semanticId,fields=fields_for(entry,'entity'),
                damageZones=zones,mounts=mounts}
        end
        function methods.entity(self)return self end
        function methods.health(self)return self end
        function methods.damage_zones()
            local ids={};for zone,info in pairs(entry.zones)do ids[#ids+1]={zone,info.index}end
            table.sort(ids,function(a,b)return a[2]<b[2]end)
            local result={};for index,item in ipairs(ids)do result[index]=zone_target(item[1])end
            return result
        end
        function methods.damage_zone(_,identity)return zone_target(zone_identity(identity))end
        function methods.mounts()
            local ids={};for mount,info in pairs(entry.mounts)do ids[#ids+1]={mount,info.slot}end
            table.sort(ids,function(a,b)return a[2]<b[2]end)
            local result={};for index,item in ipairs(ids)do result[index]=mount_target(item[1])end
            return result
        end
        function methods.mount(_,identity)return mount_target(mount_identity(identity))end
        return setmetatable({resource='vehicle',vehicle=name,path='entity'},{__index=methods})
    end
    function builders.weapon_attachment(identity)
        if attachment_authoring.attachments[identity]then return magazine_attachment_target(identity)end
        local semantic=attachment_authoring.names[identity]
        assert(semantic,'unknown reviewed magazine attachment: '..tostring(identity))
        return magazine_attachment_target(semantic)
    end
    function builders.backpack(name)
        local entry=assert(entity_authoring.backpacks[name],'unknown reviewed backpack: '..tostring(name))
        local methods={}
        function methods.describe()
            local zones={}
            for zone,info in pairs(entry.zones or{})do zones[#zones+1]={zone=zone,index=info.index,name=info.name}end
            table.sort(zones,function(a,b)return a.index<b.index end)
            local linked={};for item in pairs(entry.linked or{})do linked[#linked+1]=item end
            table.sort(linked)
            return {name=name,semanticId=entry.semanticId,fields=fields_for(entry,'backpack'),
                damageZones=#zones>0 and zones or nil,linked=#linked>0 and linked or nil,
                feeds=entry.feeds and{supportWeapon=entry.feeds.weapon,relationship='backpack_ammo'}or nil}
        end
        -- The support weapon this backpack stores ammunition for, if any.
        function methods.weapon()
            assert(entry.feeds,name..' does not store ammunition for a support weapon')
            return builders.support_weapon(entry.feeds.weapon)
        end
        -- Fields of the backpack itself (linked == nil) or of one linked entity.
        local function linked_fields(path,linked,zone)
            local result={}
            for _,field in ipairs(entry.fields)do
                local t=field.target
                if t.path==path and t.linked==linked and(zone==nil or t.zone==zone)then
                    result[#result+1]=entity_public(field)end
            end
            return result
        end
        -- Reviewed damage zones (the SH-20's shield plate): zone id ('zone_0'), native zone name or index.
        local function zone_target(zone)
            local zone_methods={}
            function zone_methods.describe()
                local info=entry.zones[zone]
                return {backpack=name,zone=zone,index=info.index,name=info.name,
                    fields=linked_fields('damage_zone',nil,zone)}
            end
            return setmetatable({resource='backpack',backpack=name,path='damage_zone',zone=zone},
                {__index=zone_methods})
        end
        -- Linked entities the backpack deploys: 'drone' (Guard Dog) and 'energy_shield' (SH-51 barrier). The link
        -- (the backpack's own typed reference to the entity) is re-proven before every write.
        local function linked_target(linked)
            local link=assert(entry.linked and entry.linked[linked],name..' has no linked '..tostring(linked))
            local linked_methods={}
            local function linked_zone(zone)
                local zone_methods={}
                function zone_methods.describe()
                    local info=link.zones[zone]
                    return {backpack=name,linked=linked,zone=zone,index=info.index,name=info.name,
                        fields=linked_fields('damage_zone',linked,zone)}
                end
                return setmetatable({resource='backpack',backpack=name,path='damage_zone',linked=linked,zone=zone},
                    {__index=zone_methods})
            end
            function linked_methods.describe()
                local zones={}
                for zone,info in pairs(link.zones or{})do zones[#zones+1]={zone=zone,index=info.index,name=info.name}end
                table.sort(zones,function(a,b)return a.index<b.index end)
                return {backpack=name,linked=linked,fields=linked_fields('linked',linked),damageZones=zones}
            end
            function linked_methods.damage_zones()
                local ids={};for zone,info in pairs(link.zones or{})do ids[#ids+1]={zone,info.index}end
                table.sort(ids,function(a,b)return a[2]<b[2]end)
                local result={};for index,item in ipairs(ids)do result[index]=linked_zone(item[1])end
                return result
            end
            function linked_methods.damage_zone(_,identity)
                for zone,info in pairs(link.zones or{})do
                    if identity==zone or identity==info.name or identity==info.index then return linked_zone(zone)end
                end
                error('unknown reviewed damage zone of the '..linked..' of '..name..': '..tostring(identity),0)
            end
            if linked=='drone'then
                -- The drone's mounted weapon (sdk/VehicleWeaponCapabilities.json, carrier = this backpack).
                function linked_methods.weapon()return vehicle_weapon_target(weapon_key(name,0))end
            end
            return setmetatable({resource='backpack',backpack=name,path='linked',linked=linked},
                {__index=linked_methods})
        end
        function methods.drone()return linked_target('drone')end
        function methods.energy_shield()return linked_target('energy_shield')end
        function methods.linked()
            local names={};for linked in pairs(entry.linked or{})do names[#names+1]=linked end
            table.sort(names)
            return names
        end
        function methods.damage_zones()
            local ids={};for zone,info in pairs(entry.zones or{})do ids[#ids+1]={zone,info.index}end
            table.sort(ids,function(a,b)return a[2]<b[2]end)
            local result={};for index,item in ipairs(ids)do result[index]=zone_target(item[1])end
            return result
        end
        function methods.damage_zone(_,identity)
            for zone,info in pairs(entry.zones or{})do
                if identity==zone or identity==info.name or identity==info.index then return zone_target(zone)end
            end
            error('unknown reviewed damage zone for '..name..': '..tostring(identity),0)
        end
        return setmetatable({resource='backpack',backpack=name,path='backpack'},{__index=methods})
    end
    -- Drop-pod payloads: a stratagem's primary payload is a hellpod rack whose slots name the items the pod
    -- opens with. The rack is the semantic owner (several stratagems can share one); see
    -- sdk/PodPayloadCapabilities.json. Replacements are catalog pickups, never raw identifiers.
    local pods=require('hd2runtime/domains/pod_payload_authoring')
    local function pickup_view(identity)
        if identity=='empty'or identity==nil then return identity end
        local item=pods.pickups[identity]
        return {semanticId=item.semanticId,name=item.name,category=item.category,compatibility=item.compatibility}
    end
    function builders.pickup(identity)
        local semantic=pods.pickups[identity]and identity or pods.names[identity]
        local item=assert(semantic and pods.pickups[semantic],'unknown reviewed pickup: '..tostring(identity))
        return setmetatable({resource='pickup',semanticId=item.semanticId,name=item.name,category=item.category},
            {__index={describe=function()
                return {name=item.name,semanticId=item.semanticId,category=item.category,
                    compatibility=item.compatibility,alwaysResident=item.alwaysResident,packageKey=item.packageKey}
            end}})
    end
    -- Every reviewed pickup, optionally of one category (support_weapon, backpack, ammo, stim, grenade, supply).
    function builders.pickups(category)
        local names={}
        for name,semantic in pairs(pods.names)do
            if category==nil or pods.pickups[semantic].category==category then names[#names+1]=name end
        end
        table.sort(names)
        local result={};for index,name in ipairs(names)do result[index]=builders.pickup(name)end
        return result
    end
    local function rack_entry(identity)
        if pods.racks[identity]then return pods.racks[identity]end
        for _,rack in pairs(pods.racks)do if rack.semanticId==identity then return rack end end
        error('unknown reviewed pod rack: '..tostring(identity),0)
    end
    function builders.pod_rack(identity)
        local rack=rack_entry(identity);local name=rack.name
        local methods={}
        local function slot_target(number)
            local slot=assert(rack.slots[tostring(number)],'slot '..tostring(number)..' of '..name
                ..' is not an authored payload slot')
            local slot_methods={}
            function slot_methods.describe()
                -- Replacements live-verified in exactly this slot need no allow_unverified_reference.
                local live={}
                for semantic in pairs(slot.live or{})do live[#live+1]=pods.pickups[semantic].name end
                table.sort(live)
                return {rack=name,slot=number,active=slot.active,current=pickup_view(slot.current),
                    shared=rack.shared,acknowledgements=rack.shared and{'allow_unverified_reference','allow_shared'}
                        or{'allow_unverified_reference'},live_verified=live}
            end
            function slot_methods.current()
                return slot.current=='empty'and'empty'or builders.pickup(slot.current)
            end
            return setmetatable({resource='pod_rack',rack=name,path='slot',slot=number},{__index=slot_methods})
        end
        function methods.slot(_,number)return slot_target(number)end
        function methods.slots()
            local numbers={};for number in pairs(rack.slots)do numbers[#numbers+1]=tonumber(number)end
            table.sort(numbers)
            local result={};for index,number in ipairs(numbers)do result[index]=slot_target(number)end
            return result
        end
        function methods.describe()
            local consumers={};for index,consumer in ipairs(rack.consumers)do consumers[index]=consumer.name end
            local slots={};for _,target in ipairs(methods.slots())do slots[#slots+1]=target:describe()end
            return {name=name,semanticId=rack.semanticId,shared=rack.shared,consumers=consumers,
                spawnCount=rack.spawnCount,writable=rack.writable,reason=rack.reason,slots=slots}
        end
        return setmetatable({resource='pod_rack',rack=name,path='rack'},{__index=methods})
    end
    local function delivery_for(rack_name,owner)
        assert(rack_name,owner..' delivers no reviewed pod rack')
        return setmetatable({},{__index={rack=function()return builders.pod_rack(rack_name)end}})
    end
    -- Boosters own no settings type: their fields live on the records the Booster enum
    -- reaches (native definition table, code-selected settings rows, granted stratagem,
    -- deployed entity), each exposed as a sub-target.
    function builders.booster(identity)
        local booster_authoring=require('hd2runtime/domains/booster_authoring')
        local entry=booster_authoring.boosters[identity]
        if not entry then
            for _,candidate in pairs(booster_authoring.boosters)do
                if candidate.semanticId==identity then entry=candidate end
            end
        end
        assert(entry,'unknown reviewed booster: '..tostring(identity))
        local function owned_fields(path)
            local fields={}
            for field_id,field in pairs(entry.targets[path].fields)do
                fields[#fields+1]={semanticFieldId=field_id,instanceKey=field.instanceKey,
                    currentDefault=field.currentDefault,editable=true,range=field.range,
                    acknowledgements=field.shared and{'allow_shared','allow_unverified_effect'}
                        or{'allow_unverified_effect'}}
            end
            table.sort(fields,function(a,b)return a.semanticFieldId<b.semanticFieldId end)
            return fields
        end
        local function owned_target(path)
            assert(entry.targets[path],entry.name..' has no reviewed '..path..' target')
            local owned={describe=function()return {booster=entry.name,path=path,fields=owned_fields(path)}end}
            if path=='granted_stratagem'then
                -- The granted stratagem's drop pod (its primary payload rack).
                local rack=pods.byStratagemId[pods.boosterGranted[entry.name]or'']
                function owned.delivery()return delivery_for(rack,entry.name)end
                function owned.payload()return delivery_for(rack,entry.name):rack()end
            end
            return setmetatable({resource='booster',booster=entry.name,path=path},{__index=owned})
        end
        local methods={}
        function methods.describe()
            local targets={}
            for path in pairs(entry.targets)do targets[#targets+1]=path end
            table.sort(targets)
            return {name=entry.name,semanticId=entry.semanticId,identityStatus=entry.identityStatus,
                enumValue=entry.enumValue,nativeName=entry.nativeName,targets=targets}
        end
        function methods.tuning()return owned_target('tuning')end
        function methods.explosion()return owned_target('explosion')end
        function methods.status_effect()return owned_target('status_effect')end
        function methods.status_damage()return owned_target('status_damage')end
        function methods.granted_stratagem()return owned_target('granted_stratagem')end
        function methods.deployed_entity()return owned_target('deployed_entity')end
        return setmetatable({resource='booster',booster=entry.name,path='booster'},{__index=methods})
    end
    -- Throwables: every accessor is a native record the throwable entity owns or reaches through
    -- typed references (see sdk/ThrowableAuthoringCapabilities.json).
    -- Enemies and enemy structures: health, armor and damage zones of a hash-verified native class, named by its
    -- wiki name when the research resolved one, otherwise by its native class name (see docs/enemy-authoring.md).
    local function enemy_target(identity,kind)
        local enemy_writes=require('hd2runtime/domains/enemy_writes')
        local entry=assert(enemy_writes.entry(identity),'unknown reviewed '..kind..': '..tostring(identity))
        assert(kind=='enemy'or entry.kind==kind,tostring(identity)..' is an enemy unit; use hd2.enemy')
        local function public_fields(path,zone,attack)
            local result={}
            for _,field in ipairs(entry.fields)do
                if field.path==path and field.zone==zone and field.attack==attack then
                    local descriptor=enemy_writes.descriptor(entry,field)
                    result[#result+1]={semanticFieldId=field.id,currentDefault=field.currentDefault,
                        editable=descriptor.editable,reason=field.reason,shared=descriptor.shared,
                        min=descriptor.min,max=descriptor.max,acknowledgement=descriptor.acknowledgement,
                        sharedWithClasses=descriptor.sharedWithClasses}
                end
            end
            return result
        end
        local function zone_identity(value)
            for _,zone in ipairs(entry.zones)do
                if value==zone.id or value==zone.name or value==zone.wikiZone
                    or type(value)=='number'and zone.index==value then return zone end
            end
            error('unknown damage zone for '..entry.name..': '..tostring(value),0)
        end
        local methods={}
        local function zone_target(zone)
            local sub={}
            function sub.describe()
                return {name=entry.name,zone=zone.id,nativeName=zone.name,wikiZone=zone.wikiZone,
                    fields=public_fields('damage_zone',zone.id)}
            end
            return setmetatable({resource='enemy',enemy=entry.name,path='damage_zone',zone=zone.id},{__index=sub})
        end
        -- Attacks: the DamageInfo row each mounted weapon reaches (slot_<n>, slot_<n>_impact / _expiry for its
        -- explosions, slot_<n>_spray), or a wiki attack name the row matches exactly on all nine values.
        local function attack_identity(value)
            for _,attack in ipairs(entry.attacks or{})do if attack.id==value then return attack end end
            local found
            for _,attack in ipairs(entry.attacks or{})do
                for _,name in ipairs(attack.wikiAttacks)do
                    if name==value then found=found or attack end
                end
            end
            return found or error('unknown attack for '..entry.name..': '..tostring(value),0)
        end
        local function attack_target(attack)
            local sub={}
            function sub.describe()
                return {name=entry.name,attack=attack.id,mountSlot=attack.slot,role=attack.role,
                    wikiAttacks=copy(attack.wikiAttacks),rowWikiMatches=copy(attack.rowWikiMatches),
                    sharedWithClasses=copy(attack.reviewedClassesReachingRow),
                    fields=public_fields('attack',nil,attack.id)}
            end
            return setmetatable({resource='enemy',enemy=entry.name,path='attack',attack=attack.id},{__index=sub})
        end
        function methods.describe()
            local zones,attacks={},{}
            for _,zone in ipairs(entry.zones)do
                zones[#zones+1]={id=zone.id,nativeName=zone.name,wikiZone=zone.wikiZone}
            end
            for _,attack in ipairs(entry.attacks or{})do
                attacks[#attacks+1]={id=attack.id,mountSlot=attack.slot,role=attack.role,
                    wikiAttacks=copy(attack.wikiAttacks)}
            end
            return {name=entry.name,className=entry.className,wikiName=entry.wikiName,kind=entry.kind,
                faction=entry.faction,semanticId=entry.semanticId,zones=zones,attacks=attacks,
                fields=public_fields('entity')}
        end
        function methods.attack(_,identity_)return attack_target(attack_identity(identity_))end
        function methods.attacks()
            local result={}
            for _,attack in ipairs(entry.attacks or{})do result[#result+1]=attack_target(attack)end
            return result
        end
        function methods.zones()
            local result={}
            for _,zone in ipairs(entry.zones)do result[#result+1]=zone_target(zone)end
            return result
        end
        function methods.zone(_,identity_)return zone_target(zone_identity(identity_))end
        methods.damage_zone=methods.zone
        methods.damage_zones=methods.zones
        return setmetatable({resource='enemy',enemy=entry.name,path='entity'},{__index=methods})
    end
    function builders.enemy(identity)return enemy_target(identity,'enemy')end
    function builders.structure(identity)return enemy_target(identity,'structure')end
    -- Every reviewed enemy / structure name ({kind=...} filters).
    function builders.enemies(filter)
        local database=require('hd2runtime/domains/enemy_authoring')
        local names={}
        for name,entry in pairs(database.enemies)do
            if not filter or((not filter.kind or entry.kind==filter.kind)
                and(not filter.faction or entry.faction==filter.faction))then names[#names+1]=name end
        end
        table.sort(names)
        return names
    end
    function builders.throwable(identity)
        local throwable_authoring=require('hd2runtime/domains/throwable_authoring')
        local entry=throwable_authoring.throwables[identity]
        if not entry then
            for _,candidate in pairs(throwable_authoring.throwables)do
                if candidate.semanticId==identity then entry=candidate end
            end
        end
        assert(entry,'unknown reviewed throwable: '..tostring(identity))
        local function fields_of(owned)
            local fields={}
            for field_id,field in pairs(owned.fields)do
                fields[#fields+1]={semanticFieldId=field_id,instanceKey=field.instanceKey,
                    currentDefault=field.currentDefault,editable=field.editable,reason=field.reason,
                    range=field.range,shared=field.shared,
                    acknowledgements=field.editable and(field.shared and{'allow_shared','allow_unverified_effect'}
                        or{'allow_unverified_effect'})or{}}
            end
            table.sort(fields,function(a,b)return a.semanticFieldId<b.semanticFieldId end)
            return fields
        end
        local owned_target
        local function status_keys()
            local keys={}
            for label,owned in pairs(entry.targets)do
                if owned.path=='status_effect'then keys[#keys+1]=owned end
            end
            table.sort(keys,function(a,b)return a.slot<b.slot end)
            return keys
        end
        local function status_target(identity_)
            for _,owned in ipairs(status_keys())do
                if owned.key==identity_ or owned.label==identity_ or owned.slot==identity_ then
                    return owned_target('status_effect',owned.key)
                end
            end
            error(entry.name..' has no reviewed status effect '..tostring(identity_),2)
        end
        function owned_target(path,key)
            local label=key and path..':'..key or path
            local owned=assert(entry.targets[label],entry.name..' has no reviewed '..path..' target')
            local methods={}
            function methods.describe()
                return {throwable=entry.name,path=path,status=key,label=owned.label,fields=fields_of(owned)}
            end
            if path=='explosion'then
                function methods.status_effect(_,identity_)return status_target(identity_)end
                function methods.status_effects()
                    local result={};for index,item in ipairs(status_keys())do
                        result[index]=owned_target('status_effect',item.key)end
                    return result
                end
                function methods.shrapnel()return owned_target('shrapnel')end
                function methods.bomblets()return owned_target('bomblets')end
            elseif path=='bomblets'then
                function methods.explosion()return owned_target('bomblet_explosion')end
            end
            return setmetatable({resource='throwable',throwable=entry.name,path=path,status=key},
                {__index=methods})
        end
        local methods={}
        function methods.describe()
            local targets={}
            for label in pairs(entry.targets)do targets[#targets+1]=label end
            table.sort(targets)
            return {name=entry.name,semanticId=entry.semanticId,family=entry.family,category=entry.category,
                identityStatus=entry.identityStatus,targets=targets,fields=fields_of(entry.targets.throwable)}
        end
        function methods.detonation()return owned_target('detonation')end
        function methods.explosion()return owned_target('explosion')end
        function methods.status_effect(_,identity_)return status_target(identity_)end
        function methods.status_effects()return owned_target('explosion'):status_effects()end
        function methods.shrapnel()return owned_target('shrapnel')end
        function methods.bomblets()return owned_target('bomblets')end
        function methods.damage()return owned_target('damage')end
        function methods.entity()return owned_target('entity')end
        function methods.shield()return owned_target('shield')end
        return setmetatable({resource='throwable',throwable=entry.name,path='throwable'},{__index=methods})
    end
    function builders.stratagem(name)
        local entry=stratagem_authoring.stratagems[name]
        if not entry then return legacy_stratagem(name)end
        local methods={}
        local legacy_ok,legacy=pcall(legacy_stratagem,name)
        if legacy_ok then for method in pairs(metadata.types.stratagem.methods)do
            if legacy[method]then methods[method]=function()return legacy[method](legacy)end end
        end
            if legacy.read_target then methods.read_target=function()return legacy:read_target()end end
        end
        function methods.describe()
            local result={name=entry.name,family=entry.family,rootResolution=entry.rootResolution,
                fields={},attackRoles={},deployedEntity=entry.deployedEntity,
                mineScopeDeferred=entry.family=='mine'and not entry.mine,mine=entry.mine}
            for _,field in ipairs(entry.fields)do if field.target.path=='stratagem'then
                result.fields[#result.fields+1]=public_field(field)end end
            for role in pairs(entry.attacks)do result.attackRoles[#result.attackRoles+1]=role end
            table.sort(result.attackRoles);return result
        end
        function methods.attacks()
            local roles={};for role in pairs(entry.attacks)do roles[#roles+1]=role end;table.sort(roles)
            local result={};for index,role in ipairs(roles)do result[index]=stratagem_attack(name,role)end
            return result
        end
        function methods.attack(_,role)return stratagem_attack(name,role)end
        -- A mine stratagem's deployed-mine explosion (its MinefieldComponent explosion).
        function methods.mine()
            assert(entry.attacks.mine,'stratagem has no reviewed mine explosion: '..name)
            return stratagem_attack(name,'mine')
        end
        function methods.deployed_entity()return stratagem_entity(name)end
        -- The drop pod this call-in delivers (hellpod rack and its item slots).
        function methods.delivery()return delivery_for(pods.byStratagem[name],name)end
        function methods.payload()return delivery_for(pods.byStratagem[name],name):rack()end
        function methods.eagle_rearm()
            assert(entry.family=='eagle','stratagem has no Eagle rearm definition')
            local rearm_methods={}
            function rearm_methods.describe()
                local result={name=name,path='eagle_rearm',fields={}}
                for _,field in ipairs(entry.fields)do if field.target.path=='eagle_rearm'then
                    result.fields[#result.fields+1]=public_field(field)end end
                return result
            end
            return setmetatable({resource='stratagem',stratagem=name,path='eagle_rearm'},
                {__index=rearm_methods})
        end
        return setmetatable({resource='stratagem',stratagem=name,path='stratagem'},
            {__index=methods})
    end
    return builders
end
return M
