-- Runtime-owned custom text (docs/custom-text.md): a mod's own stratagem name and description. Development
-- infrastructure until its live proof: api/hd2.lua does not export it and the public presentation fields refuse it; the
-- development presentation path (runtime/stratagem_presentation.lua apply_text) uses it.
--
-- How the game shows text (research/stratagem-text-F5FEE03DCFDB.json): a StratagemInfo text member holds a text id,
-- and every reader looks it up through exe 0x321C40, the only reader of the text registry [exe+0x1A101E0] = {u32
-- count, u32 capacity, table pointers}. It reads the count and the array once and walks the tables in order: the first
-- table holding (current language, id) wins, otherwise the text is empty. Only the game's language registration
-- (game.dll 0x12FEDC0) writes the registry, at startup and on each language change: it clears it (count 0, the array
-- and capacity kept) and registers its own tables again.
--
-- The Runtime's text is ONE table it builds and owns, holding every mod's texts in all 15 game languages (a language a
-- mod did not give gets the mod's default text, so nothing shows blank). Its memory is never freed (the game may keep a
-- pointer to a text it looked up). It is registered by appending its pointer into the registry's spare capacity,
-- through the guarded transaction: the slot first, then the count. A reader sees either the old count or the new count
-- with the slot already written. The Runtime never grows or reallocates the game's array, never writes a game table and
-- never changes one of the game's registrations. When texts change, a new table replaces the old pointer; the old table
-- stays allocated. A language change drops the table, and M.keep registers it again on the next update.
--
-- Ids: the upper 32 bits of MurmurHash64A of '<mod resource id>/text/<id>', mod-local like images and never published.
-- Before anything is registered every id must be absent from every game table (the first table holding an id wins).
-- Codes: UNSUPPORTED_BUILD (pins), UNAVAILABLE (no registry or language yet), UNSUPPORTED_LANGUAGE (not one of the 15),
-- NO_TEXT, ID_COLLISION, REGISTRY_FULL (no spare capacity), TEXT_BUDGET, REGISTRY_CHANGED, VERIFY_FAILED.
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/text_resources')
local images=require('hd2runtime/runtime/image_resources')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local M={}
M.MAX_ID=64
local function log(text)log_module.emit('[HD2Runtime] text '..text)end

local LANGUAGE,CODE,CODES={},{},{}
for _,item in ipairs(D.languages)do LANGUAGE[item.code]=item.hash;CODE[item.hash]=item.code;CODES[#CODES+1]=item.code end
M.LANGUAGES=CODES
local TWO32=4294967296
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function u64(n)return u32(n%TWO32)..u32(math.floor(n/TWO32))end

--------------------------------------------------------------------------------------------------- texts --
-- Well-formed UTF-8 with no NUL and no control character other than a line feed.
local function valid_utf8(s)
    local i,n=1,#s
    while i<=n do
        local c=s:byte(i)
        if c<0x80 then
            if c<0x20 and c~=0x0A then return false end
            i=i+1
        else
            local extra,cp,min
            if c>=0xC2 and c<=0xDF then extra,cp,min=1,c-0xC0,0x80
            elseif c>=0xE0 and c<=0xEF then extra,cp,min=2,c-0xE0,0x800
            elseif c>=0xF0 and c<=0xF4 then extra,cp,min=3,c-0xF0,0x10000
            else return false end
            if i+extra>n then return false end
            for k=1,extra do
                local d=s:byte(i+k)
                if d<0x80 or d>0xBF then return false end
                cp=cp*64+(d-0x80)
            end
            if cp<min or cp>0x10FFFF or(cp>=0xD800 and cp<=0xDFFF)then return false end
            i=i+extra+1
        end
    end
    return true
end
-- {default = text, [code] = text}: a string is the text of every language.
local function values_of(value)
    if type(value)=='string'then value={default=value}end
    assert(type(value)=='table'and getmetatable(value)==nil,'text must be a string, or a table {default = text, '
        ..'<language code> = text, ...}')
    local out={}
    for key,text in pairs(value)do
        assert(key=='default'or LANGUAGE[key],'unsupported text language '..tostring(key)..' (the game\'s languages: '
            ..table.concat(CODES,', ')..'; default is the text of every language not given)')
        assert(type(text)=='string'and#text>=1 and#text<=D.limits.textBytes and valid_utf8(text),
            'text '..tostring(key)..' must be 1 to '..D.limits.textBytes..' bytes of UTF-8 without control characters')
        out[key]=text
    end
    assert(out.default,'a text table needs default: the text of every language it does not give')
    return out
end
local function same(a,c)
    for key,value in pairs(a)do if c[key]~=value then return false end end
    for key in pairs(c)do if a[key]==nil then return false end end
    return true
end
local function valid_owner(owner)
    if type(owner)~='string'or#owner>128 or not owner:match('^mods/')then return false end
    local parts=0
    for part in(owner..'/'):gmatch('([^/]*)/')do
        if part==''or part:find('[^%w_]')then return false end
        parts=parts+1
    end
    return parts>=3
end
function M.valid_id(id)return type(id)=='string'and#id>=1 and#id<=M.MAX_ID and id:match('^[a-z0-9_]+$')~=nil end
function M.key(owner,id)return owner..'/text/'..id end

local identities=setmetatable({},{__mode='k'})   -- handle -> {owner, id, key, loc, values}
local by_key,by_loc,ordered={},{},{}
local version=0
local Text={}
Text.__index=Text
function Text.__tostring(self)
    local identity=identities[self]
    return identity and("text '"..identity.id.."' of "..identity.owner)or'text'
end
function Text.describe(self)
    local identity=identities[self]
    return {kind='text',id=identity.id,mod=identity.owner}
end
-- The mod's text `id` with its value (one handle per mod and id; the same id again must carry the same text).
function M.handle(id,value,owner)
    assert(M.valid_id(id),'text id must be 1 to 64 lowercase letters, digits or underscores: '..tostring(id))
    assert(valid_owner(owner),'custom text must be defined by a mod (from its startup or one of its callbacks): a '
        ..'text belongs to the mod that defines it')
    local values=values_of(value)
    local key=M.key(owner,id)
    local existing=by_key[key]
    if existing then
        assert(same(identities[existing].values,values),"text '"..id.."' of "..owner..' is already defined with other '
            ..'text')
        return existing
    end
    assert(#ordered<D.limits.texts,'custom text budget reached ('..D.limits.texts..' texts)')
    local loc=images.hash(key)
    assert(loc~=0 and not by_loc[loc],"text '"..id.."' of "..owner..' has the same text id as '
        ..tostring(by_loc[loc])..'; rename one of them')
    local handle=setmetatable({resource='text',text=id,mod=owner},Text)
    identities[handle]={owner=owner,id=id,key=key,loc=loc,values=values}
    by_key[key],by_loc[loc]=handle,key
    ordered[#ordered+1]=handle
    version=version+1
    return handle
end
function M.issued(value)return type(value)=='table'and identities[value]~=nil end
-- The 4 bytes a row member stores for the text (its id, little-endian). Internal.
function M.id_bytes(handle)
    local identity=assert(identities[handle],'not a Runtime text')
    return u32(identity.loc)
end
function M.id_hex(handle)return string.format('0x%08X',assert(identities[handle],'not a Runtime text').loc)end
-- The text shown for a language code (its own text, else the default).
function M.text(handle,code)
    local identity=assert(identities[handle],'not a Runtime text')
    return identity.values[code]or identity.values.default
end

-- The Runtime's table for every defined text, as the game's lookup reads it (scripts/hd2_text.py build): the language
-- hashes and ids ascending, language-major offsets from the table start, each distinct text stored once.
function M.table_bytes()
    local hashes={}
    for _,item in ipairs(D.languages)do hashes[#hashes+1]=item.hash end
    table.sort(hashes)
    local ids,by={},{}
    for _,handle in ipairs(ordered)do
        local identity=identities[handle]
        ids[#ids+1]=identity.loc;by[identity.loc]=identity
    end
    table.sort(ids)
    local nl,n=#hashes,#ids
    local head={u32(D.table.magic),u32(nl),u32(n)}
    for _,hash in ipairs(hashes)do head[#head+1]=u32(hash)end
    for _,id in ipairs(ids)do head[#head+1]=u32(id)end
    local base=D.table.header+4*nl+4*n+4*nl*n
    local offsets,blob,seen,size={},{},{},0
    for _,hash in ipairs(hashes)do
        local code=CODE[hash]
        for _,id in ipairs(ids)do
            local values=by[id].values
            local data=(values[code]or values.default)..'\0'
            local at=seen[data]
            if not at then at=base+size;seen[data]=at;blob[#blob+1]=data;size=size+#data end
            offsets[#offsets+1]=u32(at)
        end
    end
    return table.concat(head)..table.concat(offsets)..table.concat(blob)
end

--------------------------------------------------------------------------------------------- the game side --
local function busy(what)error('TARGET_UNAVAILABLE: text registry '..what,0)end
local function base_of(runtime,name)
    local handle=runtime.module and runtime.module(name)
    local address=handle and runtime.address and runtime.address(handle)
    if type(address)~='number'then error('TARGET_UNAVAILABLE: '..(name or'executable')..' not loaded',0)end
    return address
end
local proven={}
-- The registry code, the game's registration and every consumer path (pins), once per loaded game: {exe, game}, or nil
-- and the reason.
function M.prove(runtime)
    if D.source.exeSha256~=profile.exe_sha or D.source.gameDllSha256~=profile.dll_sha then
        return nil,'the text research covers another game build'
    end
    require('hd2runtime/core/fingerprint').require(runtime)
    local exe,game=base_of(runtime,nil),base_of(runtime,'game.dll')
    local key=exe..'|'..game
    if proven[key]then return proven[key]end
    for _,pin in ipairs(D.pins)do
        local expected=b.unhex(pin.hex)
        if runtime.read((pin.module=='exe'and exe or game)+pin.rva,#expected)~=expected then
            return nil,'text code changed ('..pin.label..' at '..pin.module..'+'..string.format('%X',pin.rva)..')'
        end
    end
    proven[key]={exe=exe,game=game}
    return proven[key]
end
local function bytes(runtime,at,size)
    local s=type(at)=='number'and at>0 and runtime.read(at,size)
    if type(s)~='string'or#s~=size then busy('unreadable')end
    return s
end
local function qword(s,o)
    local high=b.u32(s,o+4)
    if high>2097151 then busy('holds an invalid pointer')end
    return b.u32(s,o)+high*TWO32
end
-- The registry as the lookup reads it: {list, head, count, capacity, array, slots, tables}, or nil and why.
local function registry(runtime,exe)
    local list=qword(bytes(runtime,exe+D.registry.global,8),0)
    if list==0 then return nil,'the game has not registered its text yet'end
    local head=bytes(runtime,list,16)
    local count,capacity=b.u32(head,D.registry.count),b.u32(head,D.registry.capacity)
    local array=qword(head,D.registry.tables)
    if array==0 or capacity==0 or capacity>D.limits.registryCapacity or count>capacity then busy('shape changed')end
    local slots=bytes(runtime,array,capacity*8)
    local tables={}
    for index=0,count-1 do tables[index+1]=qword(slots,index*8)end
    return {list=list,head=head,count=count,capacity=capacity,array=array,slots=slots,tables=tables}
end
-- One table, as 0x321C40 reads it: the offset of (language, id), or nil when this table does not hold it.
local function offset_in(runtime,at,id,language)
    local head=bytes(runtime,at,D.table.header)
    local nl,n=b.u32(head,D.table.languages),b.u32(head,D.table.ids)
    if nl>D.limits.tableLanguages or n>D.limits.tableIds then busy('holds a table of unexpected shape')end
    if nl==0 or n==0 then return nil end
    local languages=bytes(runtime,at+D.table.header,4*nl)
    local li
    for k=0,nl-1 do if b.u32(languages,4*k)==language then li=k;break end end
    if not li then return nil end
    local ids=at+D.table.header+4*nl
    local low,high=0,n-1
    while low<=high do
        local mid=math.floor((low+high)/2)
        local value=b.u32(bytes(runtime,ids+4*mid,4),0)
        if value==id then
            local offset=b.u32(bytes(runtime,ids+4*n+4*(li*n+mid),4),0)
            return offset~=0 and offset or nil
        elseif value<id then low=mid+1 else high=mid-1 end
    end
    return nil
end
-- What the game shows for a text id now: the index of the table that answers, and whether it shows `expected`
-- exactly. index nil: no table holds it (the game shows an empty text).
local function shown(runtime,reg,id,language,expected)
    for index,at in ipairs(reg.tables)do
        local offset=offset_in(runtime,at,id,language)
        if offset then
            local exact=expected~=nil and runtime.read(at+offset,#expected+1)==expected..'\0'
            return index,exact
        end
    end
    return nil,false
end

---------------------------------------------------------------------------------------------- registration --
local state={table=nil,version=-1,tables=0,index=nil,language=nil}
local function registered_index(reg)
    if not state.table then return nil end
    for index,at in ipairs(reg.tables)do if at==state.table then return index end end
    return nil
end
local function owner_of(runtime,address,size)
    local r=runtime.query and runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base
            and address+size<=r.base+r.size)then
        return nil
    end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end
local function change(label,owner,address,expected,desired)
    return {label='text.'..label,owner=owner,offset=address-owner.base,expected=expected,desired=desired,
        before=expected,already_desired=false,identity={component='TextRegistry',component_type='native',
            unique_owner=true,owner_count=1},chain={}}
end
-- The registry header and slots as the guarded transaction's contexts: every write re-proves them.
local function plan_for(runtime,reg,changes)
    local head=owner_of(runtime,reg.list,16)
    local slots=owner_of(runtime,reg.array,reg.capacity*8)
    if not(head and slots)then return nil end
    local plan={snapshots={{owner=head,offset=reg.list-head.base,bytes=reg.head},
        {owner=slots,offset=reg.array-slots.base,bytes=reg.slots}},changes={}}
    for _,item in ipairs(changes)do
        local owner=item.slot and slots or head
        plan.changes[#plan.changes+1]=change(item.label,owner,item.address,item.expected,item.desired)
    end
    return plan
end
local function current_language(runtime,exe)return b.u32(bytes(runtime,exe+D.currentLanguage,4),0)end
-- Every Runtime id resolves, in the current language, to exactly its text from the Runtime table.
local function verify(runtime,reg,language)
    local code=CODE[language]
    for _,handle in ipairs(ordered)do
        local identity=identities[handle]
        local index,exact=shown(runtime,reg,identity.loc,language,M.text(handle,code))
        if not(index and reg.tables[index]==state.table and exact)then return false,tostring(handle)end
    end
    return true
end

-- Registers the Runtime table for every defined text (or confirms it): true and {action, index, language}, or nil, code
-- and reason. At most one guarded transaction; never inside a game table.
function M.ensure(runtime)
    local pins,why=M.prove(runtime)
    if not pins then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    if #ordered==0 then return nil,'NO_TEXT','no custom text is defined'end
    local language=current_language(runtime,pins.exe)
    if language==0 then return nil,'UNAVAILABLE','the game has no text language yet'end
    if not CODE[language]then
        return nil,'UNSUPPORTED_LANGUAGE',string.format('the game\'s text language (0x%08X) is not one of its 15 known '
            ..'languages, so Runtime text has no entry for it',language)
    end
    local reg,unavailable=registry(runtime,pins.exe)
    if not reg then return nil,'UNAVAILABLE',unavailable end
    local index=registered_index(reg)
    -- Every id must be absent from every other table, or the game would show that table's text instead.
    for at_index,at in ipairs(reg.tables)do
        if at_index~=index then
            for _,handle in ipairs(ordered)do
                if offset_in(runtime,at,identities[handle].loc,language)then
                    return nil,'ID_COLLISION',tostring(handle)..' has the id of a text the game already has; rename it'
                end
            end
        end
    end
    if index and state.version==version then
        state.index,state.language=index,language
        return true,{action='present',index=index,language=CODE[language]}
    end
    if not index and reg.count>=reg.capacity then
        return nil,'REGISTRY_FULL',('the game\'s text registry has no spare capacity (%d of %d); the Runtime never grows '
            ..'it'):format(reg.count,reg.capacity)
    end
    local address=state.table
    if state.version~=version or not address then
        if state.tables>=D.limits.tables then
            return nil,'TEXT_BUDGET','too many text changes this session ('..D.limits.tables..' tables)'
        end
        local data=M.table_bytes()
        if #data>D.limits.tableBytes then return nil,'TEXT_BUDGET','the custom text table is too large'end
        if not runtime.permanent_block then return nil,'UNAVAILABLE','this Runtime adapter cannot own text memory'end
        address=runtime.permanent_block(data)
        if runtime.read(address,#data)~=data then return nil,'VERIFY_FAILED','the text table did not read back'end
        state.tables=state.tables+1
        metrics.count('text.tables')
    end
    local changes,action
    if index then
        -- Replace the Runtime's own older table (texts changed): one pointer, never a game entry.
        local slot=reg.array+(index-1)*8
        changes={{label='table',slot=true,address=slot,expected=u64(state.table),desired=u64(address)}}
        action='replaced'
    else
        local slot=reg.array+reg.count*8
        changes={{label='slot',slot=true,address=slot,expected=reg.slots:sub(reg.count*8+1,reg.count*8+8),
                desired=u64(address)},
            {label='count',address=reg.list+D.registry.count,expected=u32(reg.count),desired=u32(reg.count+1)}}
        action='appended'
    end
    local plan=plan_for(runtime,reg,changes)
    if not plan then return nil,'REGISTRY_CHANGED','the text registry is not in private read-write memory'end
    local report=transaction.apply(runtime,plan)
    metrics.count('text.registrations')
    if report.status~='APPLIED'then return nil,'REGISTRY_CHANGED',tostring(report.reason)end
    local previous=state.table
    state.table,state.version=address,version
    -- After the write: the game's tables unchanged and in place, the Runtime table where it was put, every id exact.
    local after=registry(runtime,pins.exe)
    local placed=after and registered_index(after)
    local intact=after~=nil and after.count==(index and reg.count or reg.count+1)
    for at_index,at in ipairs(reg.tables)do
        if intact and at_index~=index and after.tables[at_index]~=at then intact=false end
    end
    local exact=intact and placed==(index or reg.count+1)and verify(runtime,after,language)
    if not exact then
        -- Undo exactly this registration, guarded.
        local undo=index and{{label='table',slot=true,address=reg.array+(index-1)*8,expected=u64(address),
            desired=u64(previous)}}
            or{{label='count',address=reg.list+D.registry.count,expected=u32(reg.count+1),desired=u32(reg.count)}}
        local undo_plan=after and plan_for(runtime,after,undo)
        local undone=undo_plan and transaction.apply(runtime,undo_plan).status=='APPLIED'
        if index then state.table=previous end
        state.version=-1                     -- rebuilt (a new table) next time
        return nil,'VERIFY_FAILED','the registered text did not resolve exactly'..(undone and'; undone'or'; undo refused')
    end
    state.index,state.language=placed,language
    return true,{action=action,index=placed,language=CODE[language],count=after.count,capacity=after.capacity,
        writes=report.writes,report=report}
end

-- Whether a text shows exactly its own text now (current language): true, or nil, code and reason. Read-only.
function M.resolves(runtime,handle)
    local pins,why=M.prove(runtime)
    if not pins then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local language=current_language(runtime,pins.exe)
    if not CODE[language]then return nil,'UNSUPPORTED_LANGUAGE','the game\'s text language is not one of its 15'end
    local reg,unavailable=registry(runtime,pins.exe)
    if not reg then return nil,'UNAVAILABLE',unavailable end
    local identity=assert(identities[handle],'not a Runtime text')
    local index,exact=shown(runtime,reg,identity.loc,language,M.text(handle,CODE[language]))
    if not index then return nil,'NOT_REGISTERED',tostring(handle)..' is not in any registered table'end
    if reg.tables[index]~=state.table or not exact then
        return nil,'VERIFY_FAILED',tostring(handle)..' resolves to another table\'s text'
    end
    return true
end
-- Read-only inspection (the development proof's probe and validation; never a write): {available, reason, language,
-- count, capacity, spare, registered (the Runtime table's position, or nil), collisions (texts whose id a game table
-- holds), texts}.
function M.inspect(runtime)
    local pins,why=M.prove(runtime)
    if not pins then return {available=false,reason=tostring(why)}end
    local language=current_language(runtime,pins.exe)
    local reg,unavailable=registry(runtime,pins.exe)
    if not reg then return {available=false,reason=unavailable,language=CODE[language]}end
    local index=registered_index(reg)
    local collisions={}
    for at_index,at in ipairs(reg.tables)do
        if at_index~=index then
            for _,handle in ipairs(ordered)do
                if offset_in(runtime,at,identities[handle].loc,language)then collisions[#collisions+1]=tostring(handle)end
            end
        end
    end
    return {available=true,language=CODE[language]or string.format('0x%08X (unknown)',language),count=reg.count,
        capacity=reg.capacity,spare=reg.capacity-reg.count,registered=index,collisions=collisions,texts=#ordered}
end
-- The current language code, or nil. Read-only.
function M.language(runtime)
    local pins=M.prove(runtime)
    return pins and CODE[current_language(runtime,pins.exe)]or nil
end

-- Removes the Runtime table from the registry when it is the last entry (count - 1, guarded); otherwise leaves it (it
-- stays valid). true when it is no longer registered.
function M.unregister(runtime)
    local pins=M.prove(runtime)
    if not pins then return false end
    local reg=registry(runtime,pins.exe)
    local index=reg and registered_index(reg)
    if not index then return true end
    if index~=reg.count then return false end
    local plan=plan_for(runtime,reg,{{label='count',address=reg.list+D.registry.count,expected=u32(reg.count),
        desired=u32(reg.count-1)}})
    local done=plan~=nil and transaction.apply(runtime,plan).status=='APPLIED'
    if done then state.index=nil end
    return done
end

------------------------------------------------------------------------------------------------- the watch --
-- Keeps the Runtime table registered while a row shows Runtime text. Each update reads the count and the Runtime's
-- slot; when the table is gone (the game rebuilt its registry for a language change) and the registry is the same on
-- two consecutive updates (no registration in progress), it registers it again. on_lost(code, reason) runs once when
-- that is refused (another language, no spare capacity, a collision, another build): the caller restores the row's
-- own text so nothing shows blank. Returns stop().
local keeper
local TRANSIENT_TICKS=240
function M.keep(runtime,on_lost)
    if keeper then keeper.stop()end
    local watch={status='active'}
    local last,transient=nil,0
    function watch.cancel()watch.status='cancelled'end
    local function lost(code,reason)
        watch.status='complete'
        log('Runtime text could not stay registered ('..tostring(code)..': '..tostring(reason)..')')
        if on_lost then on_lost(code,reason)end
    end
    function watch.tick()
        if watch.status~='active'then return end
        local ok,result=pcall(function()
            local pins,why=M.prove(runtime)
            if not pins then return 'build',why end
            local list=qword(bytes(runtime,pins.exe+D.registry.global,8),0)
            if list==0 then return 'wait'end
            local head=bytes(runtime,list,16)
            local count,array=b.u32(head,D.registry.count),qword(head,D.registry.tables)
            if state.index and state.index<=count
                    and qword(bytes(runtime,array+(state.index-1)*8,8),0)==state.table then
                return 'ok'
            end
            local key=head..u32(current_language(runtime,pins.exe))
            if last~=key then last=key;return 'wait'end
            return 'register'
        end)
        if ok and result=='ok'then last,transient=nil,0;return end
        if ok and result=='wait'then return end
        if ok and result=='build'then return lost('UNSUPPORTED_BUILD','the text code changed')end
        if ok then
            local from=state.language and CODE[state.language]or'?'
            local called,done,info,why=pcall(M.ensure,runtime)
            if called and done then
                last,transient=nil,0
                log(('the game rebuilt its text registry (language %s -> %s); Runtime text registered again (table %d '
                    ..'of %d)'):format(from,tostring(info.language),info.index,info.count or info.index))
                metrics.count('text.reregistrations')
                return
            end
            if called then return lost(info,why)end
            result=done
        end
        -- A table that read inconsistently (TARGET_UNAVAILABLE) is retried for a bounded time.
        transient=transient+1
        if tostring(result):find('TARGET_UNAVAILABLE',1,true)and transient<TRANSIENT_TICKS then return end
        lost('REGISTRY_CHANGED',tostring(result))
    end
    scheduler.attach(watch)
    keeper={watch=watch}
    function keeper.stop()watch.cancel();if keeper and keeper.watch==watch then keeper=nil end end
    return keeper.stop
end
function M.keeping()return keeper~=nil and keeper.watch.status=='active'end
function M.keep_stop()if keeper then keeper.stop()end end

function M.state()return {table=state.table,index=state.index,language=state.language and CODE[state.language],
    tables=state.tables,texts=#ordered}end
function M.reset_for_tests()
    if keeper then keeper.stop()end
    identities=setmetatable({},{__mode='k'});by_key,by_loc,ordered={},{},{};version=0
    state={table=nil,version=-1,tables=0,index=nil,language=nil};proven={}
end
return M
