-- Per-mod saved data (hd2.store): a small key/value table each mod keeps between game sessions. See docs/mod-store.md.
--
-- * One JSON file per mod, %LOCALAPPDATA%\HD2Runtime\mod_data\<mod id with / as _>.json, outside the game folder and
--   outside every other mod's file. A mod only ever opens its own store (the owner is read the way hd2.mod() reads it).
-- * Values: nil (removes the key), booleans, finite numbers, strings, and tables of those (arrays or string-keyed
--   maps, no cycles, at most 16 deep). A table value is copied on set and on get, so the stored copy only changes
--   through set().
-- * Saving: set() marks the store changed and saves it SAVE_DELAY seconds later (one write for a burst of changes);
--   save() writes at once. The file is written to <name>.tmp and then moved over the old file, so a crash mid-write
--   keeps the previous save; a .tmp left behind is used only when the file itself is missing.
-- * Limits keep a runaway mod from filling the disk: MAX_BYTES per file, MAX_KEYS keys, MAX_KEY key length.
-- * A file that fails to parse is moved aside to <name>.corrupt (logged) and the store starts empty.
local log=require('hd2runtime/runtime/log')
local events=require('hd2runtime/runtime/events')
-- The folder is created through the read-only adapter's ensure_directory (absent offline: tests set a folder).
local readonly_ok,create_readonly=pcall(require,'hd2runtime/runtime/windows_readonly')
local KEY='HD2RuntimeModStoreV1'
local existing=rawget(_G,KEY)
if existing then return existing end
local M={}
rawset(_G,KEY,M)
M.MAX_BYTES=1048576
M.MAX_KEYS=4096
M.MAX_KEY=128
M.MAX_DEPTH=16
M.SAVE_DELAY=1
local stores={}
local folder_override

local function emit(message)pcall(log.emit,'[HD2Runtime] '..message)end

------------------------------------------------------------------------------------------------------- json --
local escapes={['"']='\\"',['\\']='\\\\',['\b']='\\b',['\f']='\\f',['\n']='\\n',['\r']='\\r',['\t']='\\t'}
local function encode_string(text)
    return '"'..text:gsub('[%c"\\]',function(c)return escapes[c]or string.format('\\u%04x',c:byte())end)..'"'
end
local function is_array(t)
    local n=0
    for k in pairs(t)do
        if type(k)~='number'or k<1 or k%1~=0 then return false end
        n=n+1
    end
    for i=1,n do if t[i]==nil then return false end end
    return true,n
end
local encode
local function encode_value(value,out,depth,seen)
    local kind=type(value)
    if kind=='boolean'then out[#out+1]=value and'true'or'false'
    elseif kind=='number'then
        assert(value==value and value~=math.huge and value~=-math.huge,'numbers must be finite')
        out[#out+1]=(value%1==0 and math.abs(value)<2^53)and string.format('%d',value)or string.format('%.17g',value)
    elseif kind=='string'then out[#out+1]=encode_string(value)
    elseif kind=='table'then
        assert(depth<M.MAX_DEPTH,'tables nest at most '..M.MAX_DEPTH..' deep')
        assert(not seen[value],'a table cannot contain itself')
        seen[value]=true
        local array,n=is_array(value)
        if array and n>0 then
            out[#out+1]='['
            for i=1,n do if i>1 then out[#out+1]=','end;encode_value(value[i],out,depth+1,seen)end
            out[#out+1]=']'
        else
            local keys={}
            for k in pairs(value)do
                assert(type(k)=='string','table keys must be all strings or a 1..n array')
                keys[#keys+1]=k
            end
            table.sort(keys)
            out[#out+1]='{'
            for i,k in ipairs(keys)do
                if i>1 then out[#out+1]=','end
                out[#out+1]=encode_string(k);out[#out+1]=':'
                encode_value(value[k],out,depth+1,seen)
            end
            out[#out+1]='}'
        end
        seen[value]=nil
    else error('cannot store a '..kind..' value',0)end
end
function encode(value)local out={};encode_value(value,out,0,{});return table.concat(out)end
M.encode=encode

local function decode(text)
    local pos=1
    local function fail(what)error('bad JSON at byte '..pos..': '..what,0)end
    local function space()pos=text:find('[^ \t\r\n]',pos)or#text+1 end
    local value
    local function str()
        local out={}
        pos=pos+1
        while true do
            local c=text:sub(pos,pos)
            if c==''then fail('unterminated string')end
            if c=='"'then pos=pos+1;return table.concat(out)end
            if c=='\\'then
                local e=text:sub(pos+1,pos+1)
                local simple=({['"']='"',['\\']='\\',['/']='/',b='\b',f='\f',n='\n',r='\r',t='\t'})[e]
                if simple then out[#out+1]=simple;pos=pos+2
                elseif e=='u'then
                    local hex=text:sub(pos+2,pos+5)
                    if not hex:match('^%x%x%x%x$')then fail('bad \\u escape')end
                    local code=tonumber(hex,16)
                    if code<128 then out[#out+1]=string.char(code)
                    elseif code<2048 then out[#out+1]=string.char(192+math.floor(code/64),128+code%64)
                    else out[#out+1]=string.char(224+math.floor(code/4096),128+math.floor(code/64)%64,128+code%64)end
                    pos=pos+6
                else fail('bad escape')end
            else
                local stop=text:find('["\\]',pos)or#text+1
                out[#out+1]=text:sub(pos,stop-1);pos=stop
            end
        end
    end
    function value(depth)
        if depth>M.MAX_DEPTH+1 then fail('nested too deep')end
        space()
        local c=text:sub(pos,pos)
        if c=='{'then
            local t={};pos=pos+1;space()
            if text:sub(pos,pos)=='}'then pos=pos+1;return t end
            while true do
                space()
                if text:sub(pos,pos)~='"'then fail('object key expected')end
                local k=str();space()
                if text:sub(pos,pos)~=':'then fail('":" expected')end
                pos=pos+1
                t[k]=value(depth+1);space()
                local d=text:sub(pos,pos);pos=pos+1
                if d=='}'then return t end
                if d~=','then fail('"," or "}" expected')end
            end
        elseif c=='['then
            local t={};pos=pos+1;space()
            if text:sub(pos,pos)==']'then pos=pos+1;return t end
            while true do
                t[#t+1]=value(depth+1);space()
                local d=text:sub(pos,pos);pos=pos+1
                if d==']'then return t end
                if d~=','then fail('"," or "]" expected')end
            end
        elseif c=='"'then return str()
        elseif text:sub(pos,pos+3)=='true'then pos=pos+4;return true
        elseif text:sub(pos,pos+4)=='false'then pos=pos+5;return false
        elseif text:sub(pos,pos+3)=='null'then pos=pos+4;return nil
        else
            local number=text:match('^-?%d+%.?%d*[eE]?[-+]?%d*',pos)
            if not number or number==''then fail('value expected')end
            pos=pos+#number
            return tonumber(number)or fail('bad number')
        end
    end
    local result=value(0);space()
    if pos<=#text then fail('trailing data')end
    return result
end
M.decode=decode

local function copy(value,depth)
    if type(value)~='table'then return value end
    depth=depth or 0
    assert(depth<M.MAX_DEPTH,'tables nest at most '..M.MAX_DEPTH..' deep')
    local out={}
    for k,v in pairs(value)do out[k]=copy(v,depth+1)end
    return out
end

------------------------------------------------------------------------------------------------------- files --
local resolved
local function folder()
    if folder_override then return folder_override end
    if resolved then return resolved end
    local localdata=assert(os.getenv('LOCALAPPDATA'),'LOCALAPPDATA unavailable')
    assert(readonly_ok,'directory creation unavailable')
    local runtime=create_readonly()
    resolved=assert(runtime.ensure_directory,'directory creation unavailable')(localdata..'\\HD2Runtime\\mod_data')
    return resolved
end
-- Tests: a folder that already exists (no directory creation).
function M.set_folder(path)folder_override=path;for k in pairs(stores)do stores[k]=nil end end
local function file_name(owner)return owner:gsub('[^%w_%.%-]','_')..'.json'end
local function read_file(path)
    local handle=io.open(path,'rb')
    if not handle then return nil end
    local text=handle:read('*a');handle:close()
    return text
end

------------------------------------------------------------------------------------------------------- store --
local Store={};Store.__index=Store
local function check_key(key)
    assert(type(key)=='string'and#key>0 and#key<=M.MAX_KEY and not key:find('%c'),
        'store keys are strings of 1 to '..M.MAX_KEY..' characters')
end
-- The stored value (a copy, for a table), or `default` when the key is not set.
function Store:get(key,default)
    check_key(key)
    local value=self.data[key]
    if value==nil then return default end
    return copy(value)
end
-- Store a value (nil removes the key). Raises on a value that cannot be saved; saved shortly after.
function Store:set(key,value)
    check_key(key)
    if value~=nil then
        encode(value)   -- validates: finite numbers, string keys, no cycles, depth
        if self.data[key]==nil then assert(self.count<M.MAX_KEYS,'a store holds at most '..M.MAX_KEYS..' keys')end
    end
    if self.data[key]==nil and value~=nil then self.count=self.count+1
    elseif self.data[key]~=nil and value==nil then self.count=self.count-1 end
    self.data[key]=copy(value)
    self:changed()
    return self
end
-- Every key, sorted.
function Store:keys()
    local keys={}
    for k in pairs(self.data)do keys[#keys+1]=k end
    table.sort(keys)
    return keys
end
-- Remove every key (saved shortly after, like set).
function Store:clear()self.data={};self.count=0;self:changed();return self end
function Store:changed()
    self.dirty=true
    if self.pending then return end
    self.pending=true
    events.timer('after',M.SAVE_DELAY,function()self.pending=false;if self.dirty then self:save()end end,
        {owner=self.owner,id='hd2runtime.store.save'})
end
-- Write the store now. Returns true, or false and the reason (also logged); the previous file is kept on failure.
function Store:save()
    local ok,why=pcall(function()
        local text=encode(self.data)
        assert(#text<=M.MAX_BYTES,'the store is '..#text..' bytes; at most '..M.MAX_BYTES..' are saved')
        local path=folder()..'\\'..file_name(self.owner)
        local handle=assert(io.open(path..'.tmp','wb'))
        local written,failure=handle:write(text)
        handle:close()
        assert(written,failure)
        os.remove(path)
        assert(os.rename(path..'.tmp',path))
    end)
    if ok then self.dirty=false;self.saved=(self.saved or 0)+1;return true end
    why=tostring(why):gsub('^[^%s:]+:%d+: ','')
    emit('store '..self.owner..' save failed: '..why)
    return false,why
end
-- {owner, keys, dirty, saved (writes this session), file}
function Store:describe()
    return {owner=self.owner,keys=self.count,dirty=self.dirty==true,saved=self.saved or 0,file=file_name(self.owner),
        load_error=self.load_error}
end

local function load(owner)
    local store=setmetatable({owner=owner,data={},count=0},Store)
    local ok,why=pcall(function()
        local path=folder()..'\\'..file_name(owner)
        local text=read_file(path)
        if not text then
            text=read_file(path..'.tmp')
            if text then emit('store '..owner..': using the unfinished save '..file_name(owner)..'.tmp')end
        end
        if not text or text==''then return end
        local parsed_ok,data=pcall(decode,text)
        if not parsed_ok or type(data)~='table'then
            store.load_error=parsed_ok and'the file is not a table'or tostring(data)
            os.remove(path..'.corrupt');os.rename(path,path..'.corrupt')
            emit('store '..owner..' could not be read ('..store.load_error..'); moved to '..file_name(owner)
                ..'.corrupt and started empty')
            return
        end
        for k,v in pairs(data)do
            if type(k)=='string'then store.data[k]=v;store.count=store.count+1 end
        end
    end)
    if not ok then
        store.load_error=tostring(why):gsub('^[^%s:]+:%d+: ','')
        emit('store '..owner..' unavailable: '..store.load_error)
    end
    return store
end

-- The store of `owner` (a mod id), loaded on first use and shared for the session.
function M.open(owner)
    assert(type(owner)=='string'and owner~='unknown'and owner:match('^[%w_][%w_/%.%-]*$')and#owner<=128,
        'hd2.store() cannot tell which mod is calling: call it from your mod (or pass hd2.mod():store())')
    local store=stores[owner]
    if not store then store=load(owner);stores[owner]=store end
    return store
end
function M.reset_for_tests()for k in pairs(stores)do stores[k]=nil end end
return M
