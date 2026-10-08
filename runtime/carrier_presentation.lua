-- A custom stratagem carrier's MISSION presentation (docs/custom-stratagems.md, "The carrier presentation lifecycle").
-- Development infrastructure: not exported by api/hd2.lua, no SDK field.
--
-- Aboard the ship the carrier is native: its own name, cased name, description, icon and calldown code, so the native
-- loadout picker shows the vanilla stratagem. At mission start, before the conversion, apply(spec) checks that the
-- carrier row holds exactly its reviewed native values, then writes the custom ones:
--   * the text (name, cased name, description): runtime/stratagem_presentation.lua apply_text (Runtime text ids, its
--     own guarded transaction and the text registry);
--   * the icon and the calldown code: ONE guarded transaction through the stratagem write domain
--     (domains/stratagem_writes.lua: the same validation, capture and plan as the public presentation_icon and
--     calldown_code fields, which also records the code's row with runtime/calldown_codes.lua);
--   * an Eagle carrier's uses per rearm (spec.uses): in that same transaction, through the reviewed
--     eagle.uses_per_rearm field (StratagemInfo +0x50, read by the record build, the rearm reset and the rearm
--     availability check only): a native rearm then gives the custom Eagle's slot exactly its own uses. The carrier is
--     in no loadout, so its row serves only the custom stratagem while it presents as it.
-- Before anything is written, every byte this module could change is captured. restore() (a job) and restore_now()
-- (one tick, for the loadout-screen boundary) write those exact bytes back:
--   * only where the row still holds exactly what this module wrote. Bytes another writer changed are a CONFLICT and
--     are not written, the ownership rule of core/ownership.lua and the guarded transaction;
--   * the text only while the presentation module's state is the one this module applied;
--   * never another row: the token, the donors and every other stratagem are not targets.
-- Then every member is verified against its captured native bytes. A refused part stays recorded, so a later restore
-- can retry it; the state is never dropped. A finalizer restores before this Lua state closes.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local presentation=require('hd2runtime/runtime/stratagem_presentation')
local writes=require('hd2runtime/domains/stratagem_writes')
local Reader=require('hd2runtime/runtime/reader')
local calldown=require('hd2runtime/runtime/calldown_codes')
local texts=require('hd2runtime/runtime/text_resources')
local images=require('hd2runtime/runtime/image_resources')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local C=require('hd2runtime/domains/stratagem_calldown')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local P=C.presentation
local SEQUENCE,COUNT=C.row.sequence,C.row.count
local M={}
M.TEXT={'name','nameCased','description'}
M.USES_OFFSET=require('hd2runtime/domains/stratagem_slots').row.maxUses

-- {applied, restored, carrier, id, type, native = {members = {[name] = bytes}, code = values}, text = {applied,
--  restored, ref}, definition = {items = {{label, offset, before, desired}}, offset, base, restored}, spec}, ONE PER
-- CARRIER (several custom stratagems hold their carriers in one mission), by carrier name. `latest` serves the
-- one-carrier accessors (no carrier given).
local states={}
local latest
local sentinel
local restoring={}        -- by carrier: the restore job in flight (restore_now supersedes it)
-- The apply or restore job holding the presentation writes (r43): one at a time. Their transactions read and verify
-- shared ownership data across reader yields, so two in flight refused each other ('unstable ownership/data snapshot',
-- GUARD_REJECTED: r42, four early presentations started in one frame). Free once its job is no longer pending.
local busy
local function held(s)return s~=nil and s.applied and not s.restored end
-- A carrier's state; with no carrier, the latest one applied.
local function pick(carrier)
    if carrier~=nil then return states[carrier]end
    return latest
end
local function log(text)log_module.emit('[HD2Runtime] carrier presentation '..text)end
-- The alert card for the carriers that keep their own text (the TEXT FALLBACK): one card listing every such carrier.
local text_fallbacks={}
function M.text_fallback_alert(carrier)
    local seen=false
    for _,c in ipairs(text_fallbacks)do if c==carrier then seen=true end end
    if not seen then text_fallbacks[#text_fallbacks+1]=carrier end
    local ok,card=pcall(require,'hd2runtime/runtime/stratagem_alert')
    if not(ok and type(card)=='table'and card.post)then return end
    pcall(card.post,{key='text_fallback',severity='warn',title='Custom stratagems',tag='Vanilla names',
        items={{line=table.concat(text_fallbacks,', ')..' keep their vanilla name and description: the game text list '
            ..'is full.',fix='Disable some mods that add text, then restart the game.'}},
        footer='Their custom icons and call-in codes still work.'})
end
local function member_bytes(row,offset,width)return row:sub(offset+1,offset+width)end
local function code_text(values)return values and calldown.text(values)or'unreadable'end

-- The row's live code (+0x40 pointer, +0x48 count): values, or nil.
local function code_values(world,row_bytes)
    local pointer,count=b.pointer(row_bytes,SEQUENCE),b.u32(row_bytes,COUNT)
    local owned=calldown.owned(pointer,count)
    if owned then return owned,pointer,count end
    if not(count>=1 and count<=16)then return nil end
    local raw=world.runtime.read(pointer,count*4)
    if not raw or#raw~=count*4 then return nil end
    return calldown.decode(raw),pointer,count
end

-- Every member this module may write, as the row holds it now: {[name] = bytes}.
local function capture(row)
    local out={}
    for _,name in ipairs(presentation.FIELDS)do
        local f=P.fields[name]
        out[name]=member_bytes(row,f.offset,f.width)
    end
    out.codePointer=member_bytes(row,SEQUENCE,8)
    out.codeCount=member_bytes(row,COUNT,4)
    return out
end

-- Runs body as a coroutine: in a job each reader yield is a tick; with now=true the coroutine is resumed to its end
-- within this tick (the loadout-screen boundary and the finalizer).
local function run(body,now)
    local co=coroutine.create(body)
    for _=1,100000 do
        local ok,result,code,reason=coroutine.resume(co)
        if not ok then return nil,'FAILED',tostring(result)end
        if coroutine.status(co)=='dead'then return result,code,reason end
        if not now then coroutine.yield()end
    end
    return nil,'FAILED','the operation did not finish'
end

local function job(body,callback,exclusive)
    local handle={status='pending'}
    local inner=body
    if exclusive then
        body=function()
            while busy and busy~=handle and busy.status=='pending'and busy.watch.status=='active'do coroutine.yield()end
            busy=handle
            return inner()
        end
    end
    local co=coroutine.create(body)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    handle.watch=watch
    function watch.tick()
        if watch.status~='active'then return end
        local ok,result,code,reason=coroutine.resume(co)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then handle.status,handle.code,handle.reason='failed','FAILED',tostring(result)
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

local restore_body
local function finalize()
    local carriers={}
    for carrier,s in pairs(states)do if held(s)then carriers[#carriers+1]=carrier end end
    table.sort(carriers)
    for _,carrier in ipairs(carriers)do pcall(run,function()return restore_body(true,carrier)end,true)end
end
local function arm()
    if sentinel then return end
    local ok,ffi=pcall(require,'ffi')
    if ok then sentinel=ffi.gc(ffi.new('uint8_t[1]'),function()pcall(finalize)end)end
end
local function disarm()
    for _,s in pairs(states)do if held(s)then return end end
    if sentinel then pcall(function()require('ffi').gc(sentinel,nil)end);sentinel=nil end
end

-- Which members of the row are not their reviewed native values: a list of names (empty when native).
local function not_native(world,id,row)
    local out={}
    for _,name in ipairs(presentation.FIELDS)do
        local f=P.fields[name]
        if member_bytes(row,f.offset,f.width)~=presentation.reviewed(id,name)then out[#out+1]=name end
    end
    local values,pointer,count=code_values(world,row)
    local reviewed=C.nativeCodes[tostring(id)]
    if not(values and reviewed and calldown.same(values,reviewed))or calldown.owned(pointer,count)then
        out[#out+1]='calldown code ('..code_text(values)..')'
    end
    return out
end

-- The icon and the code: ONE guarded transaction through the stratagem write domain. Inside a coroutine (the reader
-- may yield): the plan's report and the items it wrote, or nil and code, reason.
local function write_definition(world,spec,native_code)
    local changes={}
    if spec.icon then
        changes[#changes+1]={field='stratagem.presentation.icon',expect=spec.carrier,value=spec.icon}
    end
    if spec.code then
        changes[#changes+1]={field='stratagem.calldown_code',expect=calldown.names(native_code),value=spec.code}
    end
    if spec.uses then
        changes[#changes+1]={field='eagle.uses_per_rearm',expect=M.native_uses(spec.carrier),value=spec.uses}
    end
    -- A nested coroutine, not pcall: the reader yields, and nothing yields through a pcall.
    local plan,_,failure=run(function()
        local validated=writes.validate_transaction({id='carrier-presentation',
            target={resource='stratagem',stratagem=spec.carrier,path='stratagem'},changes=changes})
        local reader=Reader.new(world.runtime)
        local resolved=writes.capture(world.runtime,reader,validated)
        local prepared=writes.prepare(resolved,reader,validated)
        reader.verify()
        assert(require('hd2runtime/core/fingerprint').matches(world.runtime),'application fingerprint mismatch')
        return prepared
    end,false)
    if not plan then
        local why=tostring(failure):gsub('^[^%s:]+:%d+: ','')
        return nil,why:find('CONFLICT',1,true)and'CONFLICT'or why:find('ASSET_UNAVAILABLE',1,true)
            and'ASSET_UNAVAILABLE'or'REFUSED',why
    end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('carrier_presentation.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local items={}
    for _,change in ipairs(plan.changes)do
        if change.before~=change.desired then
            items[#items+1]={label=change.label,field_offset=change.field_offset,before=change.before,
                desired=change.desired,base=change.owner.base,offset=change.offset}
        end
    end
    return report,items
end

-- The icon and the code back to the captured bytes, only where the row holds exactly what was written. Inside a
-- coroutine: true (or 'nothing'), or nil and code, reason.
local function restore_definition(world,state)
    local d=state.definition
    if not d or d.restored or#d.items==0 then return'nothing'end
    local resolved,code,reason=presentation.resolve(world,state.carrier)
    if not resolved then return nil,code,reason end
    if d.restored then return'nothing'end   -- restored by restore_now while this read yielded
    local row,record=resolved.row,resolved.record
    if resolved.owner.base~=d.base or record.offset~=d.offset or b.u32(row,0)~=state.type or b.u32(row,4)~=state.id then
        return nil,'ROW_CHANGED','the '..state.carrier..' row moved or no longer carries its identity'
    end
    local changes={}
    for index=#d.items,1,-1 do
        local item=d.items[index]
        if member_bytes(row,item.field_offset,#item.desired)~=item.desired then
            return nil,'CONFLICT','the carrier '..state.carrier..' '..item.label..' no longer holds what this '
                ..'presentation wrote (another writer owns it): not restored'
        end
        changes[#changes+1]={label='carrier_presentation.'..item.label,owner={base=resolved.owner.base,
            size=resolved.owner.size,type=resolved.owner.type,protect=resolved.owner.protect},offset=item.offset,
            expected=item.desired,desired=item.before,before=item.desired,already_desired=false,
            identity={component='StratagemSettings',record_type='StratagemInfo',record_kind=record.record_kind,
                group=record.group,row=record.row,unique_owner=true,owner_count=1},chain={}}
    end
    if d.code then
        -- The calldown module learns that its row goes back to the native code (its HUD check expects it).
        calldown.planned({address=d.base+d.offset,id=state.id,type=state.type,name=state.carrier,
            owner=resolved.owner,offset=d.offset,native=d.code,values=d.code.values})
    end
    local owner=changes[1].owner
    local report=transaction.apply(world.runtime,{snapshots={{owner=owner,offset=record.offset,bytes=row}},
        changes=changes})
    metrics.count('carrier_presentation.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    d.restored,d.report=true,report
    return true
end

-- The text back, through the presentation module, only while its state is the one this module applied.
local function restore_text(state)
    local t=state.text
    if not t or not t.applied or t.restored then return'nothing'end
    local current=presentation.state(state.carrier)
    if current~=t.ref then
        return nil,'CONFLICT','another Runtime presentation owns the '..state.carrier..' text now: not restored'
    end
    if current.restored then t.restored=true;return true end
    local result,code,reason=presentation.restore_body(state.carrier)
    if not result then return nil,code,reason end
    t.restored,t.report=true,result.report
    return true
end

-- An Eagle carrier's reviewed native uses per rearm (the write domain's eagle.uses_per_rearm current value), or nil
-- when it is not an Eagle with that field.
function M.native_uses(carrier)
    local entry=catalog.stratagems[carrier]
    for _,field in ipairs(entry and entry.fields or{})do
        if field.semanticFieldId=='eagle.uses_per_rearm'and field.target and field.target.path=='stratagem'then
            return field.currentDefault
        end
    end
end
M.MAX_USES=20
-- Applies the carrier's mission presentation. spec: {carrier = catalogued name, text = {name, nameCased,
-- description} (texts from runtime/text_resources.lua; any of them), icon = hd2.resources.image(id), code = a list of
-- direction names, uses = an Eagle carrier's uses per rearm (1..M.MAX_USES)}; at least one of text, icon and code. A
-- job: 'applied' (or 'refused' / 'failed' with code and reason; nothing is then left written).
function M.apply(spec,callback)
    return job(function()
        local state=type(spec)=='table'and states[spec.carrier]
        if held(state)then
            return nil,'ALREADY_APPLIED',state.carrier..' already holds its mission presentation'
        end
        if type(spec)~='table'or type(spec.carrier)~='string'then
            return nil,'INVALID','spec must be {carrier = name, text = {...}, icon = image, code = {...}}'
        end
        for key in pairs(spec)do
            if key~='carrier'and key~='text'and key~='icon'and key~='code'and key~='uses'then
                return nil,'INVALID','unsupported carrier presentation option: '..tostring(key)
            end
        end
        if spec.text==nil and spec.icon==nil and spec.code==nil then return nil,'NOTHING_TO_CHANGE','nothing given'end
        local entry=catalog.stratagems[spec.carrier]
        if not(entry and entry.root and entry.root.id)then
            return nil,'UNKNOWN_STRATAGEM',tostring(spec.carrier)..' is not a catalogued stratagem'
        end
        local id=entry.root.id
        if not P.values[tostring(id)]or not C.nativeCodes[tostring(id)]then
            return nil,'UNREVIEWED','no reviewed native presentation and code for '..spec.carrier
        end
        if spec.icon~=nil and not images.issued(spec.icon)then return nil,'INVALID','icon must be hd2.resources.image(id)'end
        if spec.code~=nil and not calldown.values(spec.code)then return nil,'INVALID','code must be a direction list'end
        if spec.uses~=nil then
            if not(type(spec.uses)=='number'and spec.uses>=1 and spec.uses<=M.MAX_USES and spec.uses%1==0)then
                return nil,'INVALID','uses must be 1..'..M.MAX_USES
            end
            if M.native_uses(spec.carrier)==nil then
                return nil,'NOT_AN_EAGLE',spec.carrier..' has no reviewed uses per rearm (not an Eagle)'
            end
            if spec.code==nil and spec.icon==nil then
                return nil,'INVALID','uses goes with the icon or the code (one transaction)'
            end
        end
        local world,why=world_module.open()
        if not world then return nil,'UNAVAILABLE',tostring(why)end
        local proven,pcode,preason=presentation.prove(world)
        if not proven then return nil,pcode,preason end
        local resolved,rcode,rreason=presentation.resolve(world,spec.carrier)
        if not resolved then return nil,rcode,rreason end
        -- 1. The carrier must be native: every member it could change, exactly its reviewed value.
        local stale=not_native(world,id,resolved.row)
        if#stale>0 then
            return nil,'NOT_NATIVE','the carrier '..spec.carrier..' is not native before the mission ('
                ..table.concat(stale,', ')..'): nothing written'
        end
        local native={members=capture(resolved.row),code=(code_values(world,resolved.row))}
        local _,native_pointer,native_count=code_values(world,resolved.row)
        state={applied=false,restored=false,carrier=spec.carrier,id=id,type=resolved.record.record_kind,
            native=native,spec=spec}
        states[spec.carrier]=state
        -- 2. The text (its own guarded transaction and the text registry), waited for.
        if spec.text then
            local text_spec={carrier=spec.carrier}
            for _,name in ipairs(M.TEXT)do text_spec[name]=spec.text[name]end
            local handle=presentation.apply_text(text_spec)
            while handle.status=='pending'do coroutine.yield()end
            if handle.status~='applied'and handle.code=='REGISTRY_FULL'and(spec.icon or spec.code)then
                -- 0.30.2: no place for Runtime text (the game's text registry is full; text_resources logs what holds
                -- it). The carrier keeps its own name and description and still takes the custom icon and code, so
                -- the custom stratagem runs instead of being refused for the mission. Nothing of the text was written.
                log(('TEXT FALLBACK: %s keeps its own name and description (%s); the custom icon and code are applied')
                    :format(spec.carrier,tostring(handle.reason)))
                M.text_fallback_alert(spec.carrier)
                spec={carrier=spec.carrier,icon=spec.icon,code=spec.code,uses=spec.uses}
                state.spec,state.text_fallback=spec,tostring(handle.reason)
            elseif handle.status~='applied'then
                states[spec.carrier]=nil
                return nil,handle.code or'REFUSED','the text: '..tostring(handle.reason)
            else
                state.text={applied=true,restored=false,ref=presentation.state(spec.carrier)}
            end
        end
        -- 3. The icon and the code: one guarded transaction. Refused: the text is restored, nothing stays written.
        if spec.icon or spec.code then
            local report,items_or_code,reason=write_definition(world,spec,native.code)
            if not report then
                local text_back=state.text and{restore_text(state)}or{'nothing'}
                local code=items_or_code
                states[spec.carrier]=nil
                return nil,code,'the icon and code: '..tostring(reason)..(text_back[1]and''or('; the text restore: '
                    ..tostring(text_back[2])..': '..tostring(text_back[3])))
            end
            state.definition={items=items_or_code,base=resolved.owner.base,offset=resolved.record.offset,
                report=report,restored=false,code=spec.code and{pointer=native_pointer,count=native_count,
                values=native.code}or nil}
        end
        state.applied=true
        latest=state
        arm()
        -- 4. Verify what the game will read: the custom values, the identity, the members not given still native.
        local after=presentation.resolve(world,spec.carrier)
        local verify={identity=after~=nil and b.u32(after.row,0)==state.type and b.u32(after.row,4)==id,
            text=true,icon=true,code=true,uses=true,others=true}
        if after and spec.uses then verify.uses=b.u32(after.row,M.USES_OFFSET)==spec.uses end
        if after then
            for _,name in ipairs(M.TEXT)do
                local f=P.fields[name]
                local now=member_bytes(after.row,f.offset,f.width)
                if spec.text and spec.text[name]then
                    if now~=texts.id_bytes(spec.text[name])or not texts.resolves(world.runtime,spec.text[name])then
                        verify.text=false
                    end
                elseif now~=native.members[name]then verify.others=false end
            end
            local icon=member_bytes(after.row,P.fields.icon.offset,P.fields.icon.width)
            if spec.icon then verify.icon=icon==images.bytes(spec.icon)elseif icon~=native.members.icon then
                verify.others=false end
            local values=code_values(world,after.row)
            if spec.code then verify.code=values~=nil and calldown.same(values,calldown.values(spec.code))
            elseif not(values and calldown.same(values,native.code))then verify.others=false end
        end
        local failed
        for _,key in ipairs({'identity','text','icon','code','uses','others'})do
            if not verify[key]then failed=failed or key end
        end
        if failed or not after then
            local back,bcode,breason=restore_body(false,spec.carrier)
            return nil,'VERIFY_FAILED',tostring(failed or'unreadable')..(back and'; restored'or('; restore '
                ..tostring(bcode)..': '..tostring(breason)))
        end
        local parts={}
        if spec.text then parts[#parts+1]='the Runtime text'end
        if spec.icon then parts[#parts+1]='the custom icon'end
        if spec.code then parts[#parts+1]='the code '..calldown.text(calldown.values(spec.code))end
        if spec.uses then parts[#parts+1]=('%d uses per rearm (native %s)'):format(spec.uses,tostring(M.native_uses(
            spec.carrier)))end
        local writes_n=(state.text and state.text.ref.report and state.text.ref.report.writes or 0)
            +(state.definition and state.definition.report.writes or 0)
        log(('APPLIED: %s (type %d, stable id %d) was native (its own name, cased name, description, icon and code %s) '
            ..'and now holds %s: %d writes; verified: identity %s, text %s, icon %s, code %s, members not given native %s; '
            ..'the exact native bytes kept for the restore'):format(spec.carrier,state.type,id,code_text(native.code),
            table.concat(parts,', '),writes_n,tostring(verify.identity),tostring(verify.text),tostring(verify.icon),
            tostring(verify.code),tostring(verify.others)))
        return {status='applied',carrier=spec.carrier,type=state.type,id=id,writes=writes_n,verify=verify,
            native=native.code}
    end,callback,true)
end

-- The restore (inside a coroutine; now=true: from restore_now or the finalizer). Returns a result table, or nil and
-- code, reason. A refused part stays recorded for a later restore.
function restore_body(now,carrier)
    local state=pick(carrier)
    if not held(state)then
        return nil,'NOT_APPLIED','the carrier presents as itself: nothing to restore'
    end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local proven,pcode,preason=presentation.prove(world)
    if not proven then return nil,pcode,preason end
    local def,dcode,dreason=restore_definition(world,state)
    local text,tcode,treason=restore_text(state)
    if not(def and text)then
        local reasons={}
        if not def then reasons[#reasons+1]='the icon and code: '..tostring(dcode)..': '..tostring(dreason)end
        if not text then reasons[#reasons+1]='the text: '..tostring(tcode)..': '..tostring(treason)end
        return nil,(not def and dcode or tcode),table.concat(reasons,'; ')..((def or text)and'; the other part '
            ..'restored'or'')
    end
    state.restored=true
    disarm()
    -- Read back: every member exactly the bytes captured before the mission, the identity unchanged.
    local after=presentation.resolve(world,state.carrier)
    local live=after and capture(after.row)
    local exact,mismatch=live~=nil,{}
    for name,bytes in pairs(state.native.members)do
        if not live or live[name]~=bytes then exact=false;mismatch[#mismatch+1]=name end
    end
    table.sort(mismatch)
    local values=after and code_values(world,after.row)
    local identity=after~=nil and b.u32(after.row,0)==state.type and b.u32(after.row,4)==state.id
    local native_now=after~=nil and#not_native(world,state.id,after.row)==0
    local writes_n=(state.definition and state.definition.report and state.definition.report.writes or 0)
        +(state.text and state.text.report and state.text.report.writes or 0)
    log(('RESTORED%s: %s presents as itself again: name, cased name, description, icon and code back to the bytes '
        ..'captured before the mission: exact %s%s; native %s (code %s); identity unchanged (type %d, stable id %d): %s')
        :format(now and' (in one tick)'or'',state.carrier,tostring(exact),#mismatch>0 and(' (differs: '
        ..table.concat(mismatch,', ')..')')or'',tostring(native_now),code_text(values),state.type,state.id,
        tostring(identity)))
    return {status='restored',carrier=state.carrier,writes=writes_n,verify={exact=exact,native=native_now,
        identity=identity,code=values}}
end

-- Restores as a job: 'restored' (or 'refused' with code and reason). carrier: whose presentation (default: the
-- latest one applied).
function M.restore(callback,carrier)
    local key=carrier or(latest and latest.carrier)or'?'
    restoring[key]=job(function()return restore_body(false,carrier)end,callback,true)
    return restoring[key]
end
-- Restores within this tick (the loadout-screen boundary): a result table, or nil and code, reason. Idempotent:
-- NOT_APPLIED when the carrier already presents as itself. A restore job still in flight is superseded first (its
-- callback is not called; it was between reads, and every write is one tick with no yield, so nothing is half
-- written).
function M.restore_now(carrier)
    local key=carrier or(latest and latest.carrier)or'?'
    local pending=restoring[key]
    if pending and pending.status=='pending'then
        pending.watch.cancel()
        pending.status='superseded'
    end
    restoring[key]=nil
    return run(function()return restore_body(true,carrier)end,true)
end
-- Whether the carrier holds a mission presentation this module applied and has not restored.
-- carrier nil: whether ANY carrier holds one.
function M.applied(carrier)
    if carrier~=nil then return held(states[carrier])end
    for _,s in pairs(states)do if held(s)then return true end end
    return false
end
-- The carriers holding a mission presentation now, sorted.
function M.applied_carriers()
    local out={}
    for carrier,s in pairs(states)do if held(s)then out[#out+1]=carrier end end
    table.sort(out)
    return out
end
-- {applied, restored, carrier, id, type, native, text, definition} or nil.
function M.state(carrier)return pick(carrier)end
function M.finalize_for_tests()finalize()end
function M.busy()return busy~=nil and busy.status=='pending'and busy.watch.status=='active'end
function M.reset_for_tests()states,latest,restoring,busy={},nil,{},nil;disarm()end
return M
