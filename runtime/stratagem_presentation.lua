-- A carrier stratagem's presentation borrowed from an existing vanilla stratagem (docs/custom-stratagems.md,
-- "Presentation"). Development infrastructure: not exported by api/hd2.lua, no SDK field.
--
-- Only the carrier row's presentation members change, to the donor row's reviewed values (domains/
-- stratagem_calldown.lua presentation; research/stratagem-calldown-*.json):
--   name (+0x28) and nameCased (+0x2C)   localization ids
--   description (+0x30)                   a localization id
--   icon (+0xB0)                          a 64-bit image hash
-- Never its type (+0), stable id (+4), or anything else: the loadout, the saved loadout, the mission record, the matcher
-- and the call-in keep seeing the carrier. Values only: no pointer is copied, so nothing is shared with the donor row.
-- Other members (the +0x10/+0x18/+0x20 strings, +0x34, +0x38, category +0xB8, beacon colour +0xD4) are refused.
--
-- Guards: the game.dll build and the readers of every field (pins) are proven first; both rows are found by their
-- catalogue identity (stable id and package), never a type number; each carrier field must hold its reviewed native
-- value, and the donor's its reviewed value; one guarded transaction writes them, with the whole carrier row as its
-- context (so its identity bytes are proven unchanged at every write). Restore writes the native values back through
-- the same guards and refuses when anything else changed a field. A finalizer restores before this Lua state closes.
--
-- The mission HUD caches each slot's visual per stratagem type, so apply the presentation before the mission: the HUD
-- then builds the slot from the borrowed values. Applied during a mission, the slot keeps its icon until the next.
--
-- M.apply_text is the development custom text path (docs/custom-text.md; not reachable from the public fields): a
-- carrier's name, cased name and description from Runtime-owned text (runtime/text_resources.lua).
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local Stratagem=require('hd2runtime/core/stratagem')
local reader_module=require('hd2runtime/runtime/reader')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local C=require('hd2runtime/domains/stratagem_calldown')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local P=C.presentation
local ROW=profile.stratagem.stride
local M={}
M.FIELDS={'name','nameCased','description','icon'}

-- One state per carrier (several custom stratagems hold their carriers at once), by carrier name: {applied, restored,
-- carrier, donor, type, id, fields = {{name, offset, native, borrowed}}, changes, report, text}. `state` is the latest
-- one, for the one-carrier accessors (M.state() and M.restore() without a carrier).
local states={}
local state
local function held(carrier)
    local s=carrier~=nil and states[carrier]
    return s and s.applied and not s.restored and s or nil
end
-- Whether a carrier other than `except` still shows Runtime text (the text table then stays registered for it).
local function other_text(except)
    for carrier,s in pairs(states)do
        if carrier~=except and s.text and s.applied and not s.restored then return true end
    end
    return false
end
local sentinel
local function log(text)log_module.emit('[HD2Runtime] stratagem presentation '..text)end

-- The value as row bytes: u32 little-endian, or the 64-bit hash given as '0x' + 16 hex digits.
local function encode(field,value)
    if P.fields[field].width==4 then
        return string.char(value%256,math.floor(value/256)%256,math.floor(value/65536)%256,math.floor(value/16777216)%256)
    end
    local digits=value:gsub('^0x','')
    local out={}
    for index=8,1,-1 do out[#out+1]=string.char(tonumber(digits:sub(index*2-1,index*2),16))end
    return table.concat(out)
end
M.encode=encode

-- The reviewed value of a member of the row with this stable id, as row bytes; nil when not reviewed. Used by the public
-- fields (domains/stratagem_writes.lua) to turn a stratagem name into the exact bytes it stands for.
function M.reviewed(id,member)
    local values=P.values[tostring(id)]
    if not(values and P.fields[member]and values[member]~=nil)then return nil end
    return encode(member,values[member])
end
-- Whether the member of the row with this stable id is known not to resolve as a presentation source (its
-- localization id is in no registered strings resource: it would display blank).
function M.unresolved(id,member)
    local entry=P.unresolved and P.unresolved[tostring(id)]
    return entry~=nil and entry[member]==true
end
-- The readers of every presentation member, proven once per loaded game.dll before the public fields write: true,
-- or nil and the reason.
local proven_runtime={}
function M.prove_runtime(runtime)
    if C.source.gameDllSha256~=profile.dll_sha then return nil,'the presentation research covers another game.dll build'end
    local handle=runtime.module and runtime.module('game.dll')
    local base=handle and runtime.address and runtime.address(handle)
    if type(base)~='number'then return nil,'game.dll is not loaded'end
    if proven_runtime[base]then return true end
    for _,pin in ipairs(P.pins)do
        local expected=pin.hex:gsub('..',function(pair)return string.char(tonumber(pair,16))end)
        if runtime.read(base+pin.rva,#expected)~=expected then
            return nil,'presentation reader changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    proven_runtime[base]=true
    return true
end

local function prove(world)
    if C.source.gameDllSha256~=profile.dll_sha then
        return nil,'UNSUPPORTED_BUILD','the presentation research covers another game.dll build'
    end
    for _,pin in ipairs(P.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,'UNSUPPORTED_BUILD','presentation reader changed ('..pin.label..' at game+'
                ..string.format('%X',pin.rva)..')'
        end
    end
    return true
end

-- The live row of a catalogued stratagem, by its catalogue identity: {entry, record, owner, row}. Inside a job.
local function resolve(world,name)
    local entry=catalog.stratagems[name]
    if not(entry and entry.root and entry.root.id)then return nil,'UNKNOWN_STRATAGEM','no catalogued stratagem '..tostring(name)end
    local reader=reader_module.new(world.runtime)
    local records,owner=Stratagem.capture_all(world.runtime,reader,profile)
    local record
    for _,item in ipairs(records)do
        if item.id==entry.root.id and item.package==entry.root.package then
            if record then return nil,'STRATAGEM_AMBIGUOUS',name..' resolves to more than one row'end
            record=item
        end
    end
    if not record then return nil,'STRATAGEM_ABSENT',name..' has no StratagemInfo row'end
    local row=reader.read(owner,record.offset,ROW,true)
    if b.u32(row,0)~=record.record_kind or b.u32(row,4)~=entry.root.id then
        return nil,'ROW_CHANGED','the '..name..' row no longer carries its identity'
    end
    return {entry=entry,record=record,owner=owner,row=row}
end

local function plan_for(resolved,changes)
    local owner={base=resolved.owner.base,size=resolved.owner.size,type=resolved.owner.type,
        protect=resolved.owner.protect}
    local plan={snapshots={{owner=owner,offset=resolved.record.offset,bytes=resolved.row}},changes={}}
    for _,item in ipairs(changes)do
        plan.changes[#plan.changes+1]={label='presentation.'..item.name,owner=owner,
            offset=resolved.record.offset+item.offset,expected=item.expected,desired=item.desired,before=item.expected,
            already_desired=false,identity={component='StratagemSettings',record_type='StratagemInfo',
                record_kind=resolved.record.record_kind,group=resolved.record.group,row=resolved.record.row,
                unique_owner=true,owner_count=1},chain={}}
    end
    return plan
end

local function finalize()
    local carriers={}
    for carrier,s in pairs(states)do if s.applied and not s.restored then carriers[#carriers+1]=carrier end end
    table.sort(carriers)
    for _,carrier in ipairs(carriers)do
        local co=coroutine.create(function()return M.restore_body(carrier)end)
        for _=1,10000 do
            if coroutine.status(co)=='dead'then break end
            if not coroutine.resume(co)then break end
        end
    end
end
function M.finalize_for_tests()finalize()end
local function arm()
    if sentinel then return end
    local ffi=require('ffi')
    sentinel=ffi.gc(ffi.new('uint8_t[1]'),function()pcall(finalize)end)
end
-- The finalizer goes only when no carrier holds a presentation of this module any more.
local function disarm()
    for _,s in pairs(states)do if s.applied and not s.restored then return end end
    if sentinel then require('ffi').gc(sentinel,nil);sentinel=nil end
end

local function job(body,callback)
    local handle={status='pending'}
    local co=coroutine.create(body)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick()
        local ok,result,code,reason=coroutine.resume(co)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then handle.status,handle.code,handle.reason='failed','PRESENTATION_FAILED',tostring(result)
        elseif result then for key,value in pairs(result)do handle[key]=value end
        else handle.status,handle.code,handle.reason='refused',code,reason end
        if handle.status~='applied'and handle.status~='restored'then
            log('refused: '..tostring(handle.code)..': '..tostring(handle.reason))
        end
        if callback then callback(handle)end
    end
    scheduler.attach(watch)
    return handle
end

-- Borrows the donor's presentation for the carrier. spec: {carrier = name, donor = name, fields = {...} (default
-- M.FIELDS)}. A job: 'pending', then 'applied' (or 'refused' / 'failed' with code and reason).
function M.apply(spec,callback)
    return job(function()
        local current=type(spec)=='table'and held(spec.carrier)
        if current then
            return nil,'ALREADY_APPLIED',current.carrier..' already presents as '..current.donor
        end
        local world,why=world_module.open()
        if not world then return nil,'UNAVAILABLE',tostring(why)end
        local proven,code,reason=prove(world)
        if not proven then return nil,code,reason end
        local fields=spec.fields or M.FIELDS
        for _,field in ipairs(fields)do
            if not P.fields[field]then
                return nil,'UNSUPPORTED_FIELD',tostring(field)..' is not a presentation field (only name, nameCased, '
                    ..'description, icon)'
            end
        end
        local carrier,donor=catalog.stratagems[spec.carrier],catalog.stratagems[spec.donor]
        if not(carrier and donor)then return nil,'UNKNOWN_STRATAGEM','carrier and donor must be catalogued stratagems'end
        if carrier.root.id==donor.root.id then return nil,'SAME_STRATAGEM','the donor is the carrier'end
        local native,borrowed=P.values[tostring(carrier.root.id)],P.values[tostring(donor.root.id)]
        if not(native and borrowed)then return nil,'UNREVIEWED','no reviewed presentation for the carrier or donor'end
        local resolved,rcode,rreason=resolve(world,spec.carrier)
        if not resolved then return nil,rcode,rreason end
        local donor_row,dcode,dreason=resolve(world,spec.donor)
        if not donor_row then return nil,dcode,dreason end
        local changes,list={}, {}
        for _,field in ipairs(fields)do
            local f=P.fields[field]
            local expected,desired=encode(field,native[field]),encode(field,borrowed[field])
            local live=resolved.row:sub(f.offset+1,f.offset+f.width)
            local donor_live=donor_row.row:sub(f.offset+1,f.offset+f.width)
            if donor_live~=desired then
                return nil,'CONFLICT','the donor '..spec.donor..' '..field..' is not its reviewed value'
            end
            if live~=expected then
                return nil,'CONFLICT','the carrier '..spec.carrier..' '..field..' is not its reviewed native value '
                    ..'(another writer changed it)'
            end
            list[#list+1]={name=field,offset=f.offset,native=expected,borrowed=desired}
            if expected~=desired then changes[#changes+1]={name=field,offset=f.offset,expected=expected,desired=desired}end
        end
        if #changes==0 then return nil,'NOTHING_TO_CHANGE','the donor presents exactly like the carrier'end
        local report=transaction.apply(world.runtime,plan_for(resolved,changes))
        metrics.count('stratagem_presentation.transactions')
        if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
        local st={applied=true,restored=false,carrier=spec.carrier,donor=spec.donor,type=resolved.record.record_kind,
            id=carrier.root.id,fields=list,changes=changes,report=report}
        states[spec.carrier],state=st,st
        arm()
        local game=world_module.game_state(world)
        log(('APPLIED: %s (type %d, stable id %d) presents as %s: %d writes (%s), identity unchanged%s'):format(
            spec.carrier,st.type,st.id,spec.donor,report.writes,table.concat((function()
                local names={};for _,item in ipairs(changes)do names[#names+1]=item.name end;return names end)(),', '),
            game and game.mission and '; in a mission: the HUD keeps each slot\'s icon until the next mission' or''))
        return {status='applied',report=report,type=st.type,id=st.id,fields=list}
    end,callback)
end

-- The carrier's other presentation members, read from a row: true when every one still holds its reviewed native value.
local function others_native(row,native,except)
    for _,field in ipairs(M.FIELDS)do
        if field~=except then
            local f=P.fields[field]
            if row:sub(f.offset+1,f.offset+f.width)~=encode(field,native[field])then return false end
        end
    end
    return true
end

-- Development custom text proof (docs/custom-text.md; CustomStratagemP0Proof 0.12.0): the carrier's name, cased name
-- and description members, from their reviewed native ids to Runtime text ids (runtime/text_resources.lua). spec:
-- {carrier = name, name = text, nameCased = text, description = text} (any of the three; texts from
-- text_resources.handle). The icon is not this path's: it may be custom (presentation_icon) and is left as it is.
-- Before the one write every condition must hold, else it is refused with nothing written: the build and the
-- presentation readers (pins); the text registry code, its only registrar and every text consumer path (text pins);
-- the carrier row by catalogue identity; each given member holding its exact reviewed native id; the Runtime text
-- table registered (or registered now) with none of its ids in a game table; and each text resolving, in the current
-- language, to exactly its own text. After the write: the ids read back, each resolves to its text, the identity, the
-- icon and the members not given unchanged, non-target bytes unchanged and the page protection restored; any failure
-- restores at once. While applied, the table is kept registered (after a language change the game drops it); if that
-- is refused, the carrier's own text is restored so nothing shows blank.
local texts=require('hd2runtime/runtime/text_resources')
M.TEXT_FIELDS={'name','nameCased','description'}
function M.apply_text(spec,callback)
    return job(function()
        local current=type(spec)=='table'and held(spec.carrier)
        if current then
            return nil,'ALREADY_APPLIED',current.carrier..' already presents as '..current.donor
        end
        if type(spec)~='table'then return nil,'NOT_TEXT','spec must be {carrier = name, name = text, ...}'end
        for key in pairs(spec)do
            if key~='carrier'and key~='name'and key~='nameCased'and key~='description'then
                return nil,'UNSUPPORTED_FIELD',tostring(key)..' is not a text member (name, nameCased, description)'
            end
        end
        local given={}
        for _,field in ipairs(M.TEXT_FIELDS)do
            if spec[field]~=nil then
                if not texts.issued(spec[field])then
                    return nil,'NOT_TEXT',field..' must be a text from runtime/text_resources.lua'
                end
                given[#given+1]=field
            end
        end
        if #given==0 then return nil,'NOTHING_TO_CHANGE','no text member given'end
        local world,why=world_module.open()
        if not world then return nil,'UNAVAILABLE',tostring(why)end
        local proven,code,reason=prove(world)
        if not proven then return nil,code,reason end
        local text_pins,text_why=texts.prove(world.runtime)
        if not text_pins then return nil,'UNSUPPORTED_BUILD',tostring(text_why)end
        local carrier=catalog.stratagems[spec.carrier]
        if not(carrier and carrier.root and carrier.root.id)then
            return nil,'UNKNOWN_STRATAGEM','the carrier must be a catalogued stratagem'
        end
        local native=P.values[tostring(carrier.root.id)]
        if not native then return nil,'UNREVIEWED','no reviewed presentation for the carrier'end
        local resolved,rcode,rreason=resolve(world,spec.carrier)
        if not resolved then return nil,rcode,rreason end
        local changes,list={},{}
        for _,field in ipairs(given)do
            local f=P.fields[field]
            local expected=encode(field,native[field])
            if resolved.row:sub(f.offset+1,f.offset+f.width)~=expected then
                return nil,'CONFLICT','the carrier '..spec.carrier..' '..field..' is not its reviewed native value '
                    ..'(another writer changed it)'
            end
            local desired=texts.id_bytes(spec[field])
            changes[#changes+1]={name=field,offset=f.offset,expected=expected,desired=desired}
            list[#list+1]={name=field,offset=f.offset,native=expected,borrowed=desired,text=spec[field]}
        end
        -- The Runtime table first: registered, collision-free, every id resolving to exactly its text.
        local registered,info,registry_reason=texts.ensure(world.runtime)
        if not registered then return nil,info,registry_reason end
        for _,field in ipairs(given)do
            local ok,tcode,treason=texts.resolves(world.runtime,spec[field])
            if not ok then return nil,tcode,treason end
        end
        local icon=resolved.row:sub(P.fields.icon.offset+1,P.fields.icon.offset+P.fields.icon.width)
        local report=transaction.apply(world.runtime,plan_for(resolved,changes))
        metrics.count('stratagem_presentation.text_transactions')
        if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
        local st={applied=true,restored=false,carrier=spec.carrier,donor='custom text',type=resolved.record.record_kind,
            id=carrier.root.id,fields=list,changes=changes,report=report,custom=true,text=true}
        states[spec.carrier],state=st,st
        arm()
        local language=texts.language(world.runtime)
        -- One keeper for every carrier showing Runtime text: when the table cannot stay registered, each of them gets
        -- its own text back so nothing shows blank.
        texts.keep(world.runtime,function(lost_code,lost_reason)
            local carriers={}
            for name,s in pairs(states)do if s.text and s.applied and not s.restored then carriers[#carriers+1]=name end end
            table.sort(carriers)
            for _,name in ipairs(carriers)do
                log('custom text LOST ('..tostring(lost_code)..': '..tostring(lost_reason)..'); restoring '
                    ..name..'\'s own text so it never shows blank')
                M.restore(nil,name)
            end
        end)
        -- After the write: what the game will read.
        local after=resolve(world,spec.carrier)
        local verify={readBack=after~=nil,resolves=true,identity=after~=nil and after.record.record_kind==st.type
            and b.u32(after.row,4)==st.id,iconUnchanged=after~=nil and after.row:sub(P.fields.icon.offset+1,
                P.fields.icon.offset+P.fields.icon.width)==icon,
            nonTarget=report.non_target_bytes_unchanged==true,protection=report.protection_restored==true,
            othersNative=true}
        for _,item in ipairs(changes)do
            if after and after.row:sub(item.offset+1,item.offset+#item.desired)~=item.desired then verify.readBack=false end
        end
        for _,field in ipairs(given)do
            if not texts.resolves(world.runtime,spec[field])then verify.resolves=false end
        end
        for _,field in ipairs(M.TEXT_FIELDS)do
            if spec[field]==nil and after then
                local f=P.fields[field]
                if after.row:sub(f.offset+1,f.offset+f.width)~=encode(field,native[field])then verify.othersNative=false end
            end
        end
        local failed
        for _,key in ipairs({'readBack','resolves','identity','iconUnchanged','othersNative','nonTarget','protection'})do
            if not verify[key]then failed=failed or key end
        end
        local shown={}
        for _,item in ipairs(list)do
            shown[#shown+1]=('%s %s -> %s "%s"'):format(item.name,string.format('0x%08X',b.u32(item.native,0)),
                texts.id_hex(item.text),texts.text(item.text,language))
        end
        local text=('%s (type %d, stable id %d): %s; %d write; Runtime text table %s (table %d of %d, language %s); '
            ..'read back %s; each resolves to exactly its text: %s; identity unchanged: %s; icon unchanged: %s; other '
            ..'text members native: %s; non-target bytes unchanged %s; protection restored %s'):format(spec.carrier,
            st.type,st.id,table.concat(shown,'; '),report.writes,tostring(info.action),info.index or 0,
            info.count or info.index or 0,tostring(language),tostring(verify.readBack),tostring(verify.resolves),
            tostring(verify.identity),tostring(verify.iconUnchanged),tostring(verify.othersNative),
            tostring(verify.nonTarget),tostring(verify.protection))
        if failed then
            log('custom text VERIFY FAILED ('..failed..'), restoring now: '..text)
            local restored,restore_code,restore_reason=M.restore_body(spec.carrier)
            return nil,'VERIFY_FAILED',failed..(restored and'; restored'or('; restore '..tostring(restore_code)..': '
                ..tostring(restore_reason)))
        end
        local game=world_module.game_state(world)
        log('custom text APPLIED: '..text..(game and game.mission and'; in a mission: the HUD keeps what it built until '
            ..'the next mission'or''))
        return {status='applied',report=report,type=st.type,id=st.id,fields=list,verify=verify,
            registry=info,language=language}
    end,callback)
end

-- Writes the native values back (inside a job or the finalizer): true, or nil and code, reason. carrier: whose
-- presentation (default: the latest one applied).
function M.restore_body(carrier)
    local state=carrier~=nil and states[carrier]or(carrier==nil and state)or nil
    if not(state and state.applied and not state.restored)then return nil,'NOT_APPLIED','nothing to restore'end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local proven,code,reason=prove(world)
    if not proven then return nil,code,reason end
    local resolved,rcode,rreason=resolve(world,state.carrier)
    if not resolved then return nil,rcode,rreason end
    local changes={}
    for _,item in ipairs(state.changes)do
        local live=resolved.row:sub(item.offset+1,item.offset+#item.desired)
        if live~=item.desired then
            return nil,'CONFLICT','the carrier '..state.carrier..' '..item.name..' changed since it was applied'
        end
        changes[#changes+1]={name=item.name,offset=item.offset,expected=item.desired,desired=item.expected}
    end
    local report=transaction.apply(world.runtime,plan_for(resolved,changes))
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    state.restored=true
    disarm()
    -- Custom text: no row shows it any more. Stop keeping the table registered and take it out when it is the last
    -- entry (it stays allocated: the game may hold a text it looked up).
    local released
    if state.text and not other_text(state.carrier)then
        texts.keep_stop()
        released=texts.unregister(world.runtime)
    end
    -- Read back: every restored member holds its native value exactly, the identity is unchanged.
    local after=resolve(world,state.carrier)
    local exact=after~=nil
    for _,item in ipairs(state.changes)do
        if exact and after.row:sub(item.offset+1,item.offset+#item.expected)~=item.expected then exact=false end
    end
    local identity=after~=nil and after.record.record_kind==state.type and b.u32(after.row,4)==state.id
    local native=P.values[tostring(state.id)]
    -- Custom text restores its own members only (the icon may be a public presentation_icon value).
    local all_native=after~=nil and native~=nil and others_native(after.row,native,state.text and'icon'or nil)
    log(('RESTORED: %s presents as itself again: %d writes; restored values read back exactly: %s; %s native: %s; '
        ..'identity unchanged (type %d, stable id %d): %s; non-target bytes unchanged %s; protection restored %s%s')
        :format(state.carrier,report.writes,tostring(exact),state.text and'name, cased name and description'
        or'all presentation members',tostring(all_native),state.type,state.id,tostring(identity),
        tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored),state.text
        and('; Runtime text table '..(released and'unregistered'or'left registered (not the last entry)'))or''))
    return {status='restored',report=report,type=state.type,id=state.id,verify={exact=exact,allNative=all_native,
        identity=identity}}
end
function M.restore(callback,carrier)return job(function()return M.restore_body(carrier)end,callback)end

-- The live row of a catalogued stratagem by its catalogue identity (inside a job: the reader may yield):
-- {entry, record, owner, row}, or nil and code, reason. Used by runtime/carrier_presentation.lua.
M.resolve=resolve
M.prove=prove

-- {applied, restored, carrier, donor, type, id, fields = {{name, native, borrowed}}} or nil.
-- carrier: its state (default: the latest one applied).
function M.state(carrier)if carrier~=nil then return states[carrier]end;return state end
function M.reset_for_tests()states,state={},nil;disarm();proven_runtime={} end
return M
