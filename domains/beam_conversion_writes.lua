-- Guarded writes of beam conversions (docs/beam-conversion.md; runtime/beam_conversion.lua): the target
-- hd2.weapon(name):beam_conversion() / hd2.support_weapon(name):beam_conversion(), resource 'beam_conversion'.
--
--   hd2.ensure({recover=true,transaction={id='sickle-beam',target=hd2.weapon('LAS-16 Sickle'):beam_conversion(),
--       allow_component_swap=true,allow_unverified_effect=true,changes={
--       {field=hd2.fields.beam_conversion.enabled,expect=false,value=true},
--       {field=hd2.fields.beam.fire_rate,expect=300,value=600}}}})
--
-- Fields (domains/beam_conversion.lua `fields`): beam_conversion.enabled (false = the weapon as shipped), the
-- converted weapon's OWN beam record (owned table path): beam.fire_rate, beam.pulse_beams, beam.pulse_seconds, and its
-- OWN beam / damage rows (borrowed spare slots, runtime/beam_conversion_rows.lua; at most 6 weapons): beam.length,
-- damage.standard_damage / durable_damage / ap_* / demolition / stagger / push_force. `expect` is always the reviewed
-- baseline (not converted; the Trident's 300 rpm, 2 beams, 0.15 s, row 6 / 508 values). A request that sets
-- beam.fire_rate without beam.pulse_seconds gets the FITTED pulse (runtime/beam_conversion.lua M.fitted_pulse: the
-- Trident's 0.15 s when it fits the shot interval, else the longest pulse that never caps the rate), logged.
-- Every request needs allow_component_swap (the weapon's component set changes: ProjectileWeapon out, BeamWeapon in)
-- and allow_unverified_effect (the product path is not live-tested yet). Helpers never add either.
local b=require('hd2runtime/core/bytes')
local C=require('hd2runtime/domains/beam_conversion')
local M={}
local FIELD={}
for _,f in ipairs(C.fields)do FIELD[f.id]=f end
M.ACKNOWLEDGEMENTS={'allow_component_swap','allow_unverified_effect'}

local function engine()return require('hd2runtime/runtime/beam_conversion')end
local function finite(v)return type(v)=='number'and v==v and v>-math.huge and v<math.huge end
local function same(a,b_,storage)
    if storage=='f32'then return b.encode(a,'f32')==b.encode(b_,'f32')end
    return a==b_
end

local function target_of(target)
    assert(type(target)=='table'and target.resource=='beam_conversion',
        'unsupported beam conversion target (use hd2.weapon(name):beam_conversion())')
    for key in pairs(target)do
        assert(key=='resource'or key=='weapon','unsupported beam conversion target identity: '..tostring(key))
    end
    local w=engine().weapon(target.weapon)
    if not w then error('UNKNOWN_WEAPON: '..tostring(target.weapon)..' is not in the beam conversion catalogue '
        ..'(hd2.beam_conversions())',0)end
    if not w.supported then error('REFUSED: '..w.reasonCode..': '..w.name..': '..w.reason,0)end
    return w
end

local function validate_change(w,item)
    assert(type(item)=='table','change must be a descriptor')
    for key in pairs(item)do assert(key=='field'or key=='expect'or key=='value',
        'unsupported change option: '..tostring(key))end
    local f=FIELD[item.field]
    if not f then
        error('field is not exposed on a beam conversion: '..tostring(item.field)..' (one of '
            ..table.concat((function()local o={}for _,x in ipairs(C.fields)do o[#o+1]=x.id end return o end)(),', ')
            ..')',0)
    end
    if f.type=='boolean'then
        assert(item.expect==f.default,'expect differs from the reviewed value of '..f.id..': declared='
            ..tostring(item.expect)..' reviewed='..tostring(f.default))
        assert(type(item.value)=='boolean','value must be true or false for '..f.id)
        return {field=f.id,descriptor=f,expect=item.expect,value=item.value}
    end
    assert(finite(item.expect),'expect must be a finite number for '..f.id)
    assert(finite(item.value),'value must be a finite number for '..f.id)
    assert(same(item.expect,f.default,f.storage),'expect differs from the reviewed value of '..f.id..': declared='
        ..tostring(item.expect)..' reviewed='..tostring(f.default))
    assert(item.value>=f.min and item.value<=f.max,('value outside the reviewed range [%s, %s] for %s%s'):format(
        tostring(f.min),tostring(f.max),f.id,f.rangeReason and(' ('..f.rangeReason..')')or''))
    if f.storage=='i32'or f.storage=='u32'then assert(item.value%1==0,f.id..' must be a whole number')end
    return {field=f.id,descriptor=f,expect=item.expect,value=item.value,
        desired=b.encode(item.value,f.storage),expected=b.encode(item.expect,f.storage)}
end

local function valid_id(id)
    assert(type(id)=='string'and#id>0 and#id<=64 and not id:find('[^%w_%-]'),'invalid operation id')
end

local function validate(request,multiple)
    assert(type(request)=='table',(multiple and'transaction'or'patch')..' requires a descriptor')
    local allowed={id=true,target=true,diagnostic=true,allow_component_swap=true,allow_unverified_effect=true}
    if multiple then allowed.changes=true else allowed.field=true;allowed.expect=true;allowed.value=true end
    for key in pairs(request)do assert(allowed[key],'unsupported option: '..tostring(key))end
    valid_id(request.id)
    local w=target_of(request.target)
    assert(request.allow_component_swap==true,'beam conversion requires allow_component_swap=true: it changes the '
        ..w.name..'\'s component set (ProjectileWeapon out, BeamWeapon in) in this game only; solo only; restart the '
        ..'game after using it (docs/beam-conversion.md)')
    assert(request.allow_unverified_effect==true,'beam conversion requires allow_unverified_effect=true: '
        ..(w.liveProven and'the conversion of the '..w.name..' was live-proven on the experiment, the Runtime path '
            ..'is not live-tested yet'or'the conversion of the '..w.name..' is not live-tested'))
    local items=multiple and request.changes or{{field=request.field,expect=request.expect,value=request.value}}
    assert(type(items)=='table'and#items>=1 and#items<=#C.fields,'transaction requires one to '..#C.fields..' changes')
    local spec={kind='beam_conversion',resource='beam_conversion',id=request.id,weapon=w.name,
        diagnostic=request.diagnostic==true,allow_component_swap=true,allow_unverified_effect=true,changes={}}
    local seen={}
    for index,item in ipairs(items)do
        local change=validate_change(w,item)
        assert(not seen[change.field],'transaction lists '..change.field..' twice')
        seen[change.field]=true
        spec.changes[index]=change
    end
    spec.field=request.field;spec.expect=request.expect;spec.value=request.value
    -- The Trident's package (its beam effect and sounds): loaded and held before any write (core/assets.lua gate).
    local assets=require('hd2runtime/core/assets')
    local dep=assets.dependency(C.trident.dependency)
    spec.asset_dependencies=dep and{dep}or nil
    return spec
end
function M.validate_patch(request)return validate(request,false)end
function M.validate_transaction(request)return validate(request,true)end

-- What the request asks the weapon's record to hold, and whether it converts: {enabled (nil = not named), settings,
-- requested = {[setting] = true}, fitted (the pulse was fitted), notes}.
function M.intent(spec,current,current_rows)
    local w=engine().weapon(spec.weapon)
    local out={settings={},requested={},notes={},expects={},rows={}}
    for _,change in ipairs(spec.changes)do
        local f=change.descriptor
        if f.id=='beam_conversion.enabled'then out.enabled=change.value
        elseif f.row then out.rows[f.id]=change.value
        else out.settings[f.setting]=change.value;out.requested[f.setting]=true;out.expects[f.setting]=change.expect end
    end
    -- Unnamed row values: the weapon's own rows now (converted) or the Trident's.
    for _,f in ipairs(C.fields)do
        if f.row and out.rows[f.id]==nil then
            if current_rows then out.rows[f.id]=current_rows[f.id]else out.rows[f.id]=f.default end
        end
    end
    -- Unnamed settings: the current record's (a converted weapon) or the donor's.
    local base=current or engine().DONOR_SETTINGS
    for _,def in ipairs(C.settings)do
        if out.settings[def.id]==nil then out.settings[def.id]=base[def.id]end
    end
    if out.requested.fire_rate and not out.requested.pulse_seconds then
        local pulse,fitted=engine().fitted_pulse(out.settings.fire_rate,nil)
        out.settings.pulse_seconds=b.value(b.encode(pulse,'f32'),0,'f32')
        out.fitted=fitted
        if fitted then
            out.notes[#out.notes+1]=('note: %s: beam.pulse_seconds fitted to %.4g s for %d rpm (the Trident\'s 0.15 s '
                ..'pulse would cap it at about %d rpm at 60 fps: a pulse starts only the update after the last one '
                ..'ended); set beam.pulse_seconds to choose it'):format(w.name,out.settings.pulse_seconds,
                out.settings.fire_rate,math.floor(engine().effective_rate(out.settings.fire_rate,0.15,60)+0.5))
        end
    end
    local rate,pulse=out.settings.fire_rate,out.settings.pulse_seconds
    local at60=engine().effective_rate(rate,pulse,60)
    if at60<rate*0.98 then
        out.notes[#out.notes+1]=('WARNING: %s: a %.3g s pulse caps %d rpm at about %d rpm at 60 fps (a pulse starts '
            ..'only the update after the last one ended); leave beam.pulse_seconds out to fit it'):format(w.name,pulse,
            rate,math.floor(at60+0.5))
    end
    return out
end

function M.capture(runtime,reader,spec)
    local E=engine()
    local world=E.open()
    local s=E.locate(world)
    E.record_edits(s)
    return {world=world,s=s,weapon=E.weapon(spec.weapon)}
end

function M.prepare(resolved,reader,spec)
    local E=engine()
    local w,s,world=resolved.weapon,resolved.s,resolved.world
    local W=assert(s.weapons[w.name],'located weapon')
    local converted=W.state=='converted'
    local current=converted and(s.path_mode=='owned'and E.decode_settings(W.record)or E.DONOR_SETTINGS)or nil
    local current_rows=converted and E.rows_of(s,W)or nil
    local intent=M.intent(spec,current,current_rows)
    local enabled=intent.enabled
    if enabled==nil then
        -- Settings alone: only on a converted weapon; on one that is not, only the baseline (an ensure's restore).
        if not converted then
            for _,change in ipairs(spec.changes)do
                if not(change.descriptor.storage and b.encode(change.value,change.descriptor.storage)
                    ==b.encode(change.descriptor.default,change.descriptor.storage))then
                    error('NOT_CONVERTED: the '..w.name..' is not converted: set beam_conversion.enabled to true in '
                        ..'the same request',0)
                end
            end
        end
        enabled=converted
    end
    -- Settings conflict: on a converted weapon each named setting must hold its expect or its value now.
    if converted and enabled then
        for _,change in ipairs(spec.changes)do
            local f=change.descriptor
            if f.row then
                local now=current_rows[f.id]
                if not(same(now,change.expect,f.storage)or same(now,change.value,f.storage))then
                    error(('CONFLICT: the %s: %s is %s, neither the expected %s nor the requested %s (another '
                        ..'operation set it)'):format(w.name,f.id,tostring(now),tostring(change.expect),
                        tostring(change.value)),0)
                end
            elseif f.setting then
                local now=current[f.setting]
                -- A pulse fitted to the current rate (by the request that set the rate) counts as the baseline.
                local fitted=f.setting=='pulse_seconds'and E.fitted_pulse(current.fire_rate,nil)
                if not(same(now,change.expect,f.storage)or same(now,change.value,f.storage)
                    or fitted and same(now,fitted,f.storage))then
                    error(('CONFLICT: the %s\'s %s is %s, neither the expected %s nor the requested %s (another '
                        ..'operation set it)'):format(w.name,f.id,tostring(now),tostring(change.expect),
                        tostring(change.value)),0)
                end
            end
        end
    end
    local prepared=E.prepare(world,s,{weapon=w,enabled=enabled,settings=intent.settings,rows=intent.rows})
    local plan=prepared.plan
    plan.notes={}
    for _,note in ipairs(intent.notes)do plan.notes[#plan.notes+1]=note end
    for _,note in ipairs(prepared.notes or{})do plan.notes[#plan.notes+1]='note: '..spec.id..': '..note end
    if enabled and not converted then
        plan.notes[#plan.notes+1]=('note: %s: the %s fires LAS-13 Trident pulses from its next spawn (%d rpm, %d beams '
            ..'per pulse, %.3g s); SOLO ONLY; restart the game after using a beam conversion'):format(spec.id,w.name,
            intent.settings.fire_rate,intent.settings.pulse_beams,intent.settings.pulse_seconds)
    end
    plan.commit=function(report)E.commit(world,prepared,report)end
    plan.beam_conversion={weapon=w.name,enabled=enabled,settings=intent.settings,rows=intent.rows,path=prepared.path}
    return plan
end
return M
