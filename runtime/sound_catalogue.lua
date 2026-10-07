-- The full sound-event catalogue (docs/sounds.md; docs/research/sound-events-F5FEE03DCFDB.md), read-only.
--
-- domains/sound_events.lua (scripts/generate_sound_events.py) names every Wwise event of build F5FEE03DCFDB:
-- `<family>/<bank>/<event>`, for example 'explosions/stratagems_orbital_380mm_he/3d167800' or
-- 'ambience/env_shared/env_sludge_bubbling' (the event's own Wwise name where the game's code or data names it, else its
-- id as eight hex digits). Each event keeps its banks, kind and range (the game's own wwise_metadata), the mixer bus it
-- plays on, the game parameters / switch and state groups its sounds react to, its global effects, the weapon-catalogue
-- sounds that post it and the package that provides its bank. The domain is large: it is loaded on first use only.
-- The weapon firing-sound catalogue (runtime/weapon_sounds.lua) is separate and unchanged.
local M={}
local D,by_id,by_wwise,sorted

local function data()
    if D then return D end
    D=require('hd2runtime/domains/sound_events')
    by_id,by_wwise={},{}
    for name,e in pairs(D.events)do
        by_id[e.id]=name
        if e.wwise then by_wwise[e.wwise]=name end
    end
    return D
end
M.data=data

-- Every event name, sorted.
local function names()
    if not sorted then
        sorted={}
        for name in pairs(data().events)do sorted[#sorted+1]=name end
        table.sort(sorted)
    end
    return sorted
end

-- The canonical name and entry of a catalogue name (any case), or nil.
function M.resolve(name)
    if type(name)~='string'or#name>160 then return nil end
    local d=data()
    local lower=name:lower()
    local e=d.events[lower]
    if e then return lower,e end
    return nil
end
-- The catalogue name and entry of a 32-bit event id, or nil.
function M.by_id(id)
    if type(id)~='number'then return nil end
    data()
    local name=by_id[('%08X'):format(id)]
    if name then return name,D.events[name]end
    return nil
end
-- The catalogue name of an event's own Wwise name (lower case), or nil.
function M.by_wwise(name)
    if type(name)~='string'then return nil end
    data()
    return by_wwise[name:lower()]
end
-- The 32-bit id of an entry.
function M.id(e)return tonumber(e.id,16)end
-- Whether posting the event would leave the sound engine changed (a state, a global game parameter, a global mix
-- change or pause the event does not undo; scripts/wwise_banks.py effects), and its global effects.
function M.persistent(e)return e.persistent==true,e.effects end

local function bank(i)return D.banks[i]end
local function label(kind,hex)
    local row=D[kind][hex]
    return row and row.name or('0x'..hex)
end
local function labels(kind,list)
    local out={}
    for k,hex in ipairs(list or{})do out[k]=label(kind,hex)end
    return out
end
-- The package that provides an entry's bank: {stratagem, stratagemId, packages} | {item, itemLabel} | nil (resident only).
function M.provider(e)
    data()
    return bank(e.banks[1]).provider
end

-- What mods see of an entry.
function M.public(name,e)
    data()
    local b=bank(e.banks[1])
    local banks={}
    for k,i in ipairs(e.banks)do banks[k]=bank(i).name end
    local p=b.provider or{}
    local effects={}
    for k,v in ipairs(e.effects or{})do effects[k]=v end
    local positional=nil
    if e.position~=nil then positional=e.position==0 end
    local weapons={}
    for k,v in ipairs(e.weapons or{})do weapons[k]=v end
    return {name=name,catalogue='events',family=name:match('^[^/]+'),bank=b.name,banks=banks,faction=b.faction,
        kind=e.kind,range_m=e.range,duration_s=e.duration,positional=positional,
        bus=e.bus,global_effect=e.effects and(e.persistent and'persistent'or'transient')or nil,effects=effects,
        wwise_name=e.wwise,weapons=weapons,stratagem=p.stratagem,item=p.itemLabel,resident_only=b.provider==nil,
        parameters=labels('parameters',e.parameters),volume_parameters=labels('parameters',e.volume),
        switch_groups=labels('switchGroups',e.switchGroups),state_groups=labels('stateGroups',e.stateGroups)}
end
function M.describe(name)
    local canonical,e=M.resolve(name)
    return e and M.public(canonical,e)or nil
end

-- filter: nil (all), a family ('explosions') or {family, kind ('one_shot' | 'loop' | 'unknown' | 'control'), bank (a
-- bank name), faction ('automaton' | 'terminid' | 'illuminate'), bus (a part of the bus path, 'explosion'),
-- stratagem (true | a name), resident_only (boolean), named (true: only events with their own Wwise name), weapon
-- (true | a weapon-catalogue name), global (boolean: has a global effect), text (in the name)}. Sorted by name.
local KEYS={family=true,kind=true,bank=true,faction=true,bus=true,stratagem=true,resident_only=true,named=true,
    weapon=true,global=true,text=true,catalogue=true}
local KINDS={one_shot=true,loop=true,unknown=true,control=true}
M.FILTER_KEYS=KEYS
function M.check_filter(filter)
    if filter==nil then return {}end
    if type(filter)=='string'then filter={family=filter}end
    if type(filter)~='table'then return nil,'the filter must be nil, a family name or a table'end
    for key in pairs(filter)do
        if not KEYS[key]then return nil,'unsupported filter key: '..tostring(key)end
    end
    if filter.family~=nil then
        local ok=false
        for _,f in ipairs(data().families)do if f==filter.family then ok=true end end
        if not ok then return nil,'unknown event family: '..tostring(filter.family)end
    end
    if filter.kind~=nil and not KINDS[filter.kind]then
        return nil,"filter.kind must be 'one_shot', 'loop', 'unknown' or 'control'"
    end
    for _,key in ipairs({'resident_only','named','global'})do
        if filter[key]~=nil and type(filter[key])~='boolean'then return nil,'filter.'..key..' must be a boolean'end
    end
    for _,key in ipairs({'stratagem','weapon'})do
        if filter[key]~=nil and filter[key]~=true and type(filter[key])~='string'then
            return nil,'filter.'..key..' must be true or a name'
        end
    end
    for _,key in ipairs({'bank','faction','bus','text'})do
        if filter[key]~=nil and type(filter[key])~='string'then return nil,'filter.'..key..' must be a string'end
    end
    return filter
end
local function has(list,value)
    for _,v in ipairs(list or{})do if v==value then return true end end
    return false
end
function M.list(filter)
    local f,why=M.check_filter(filter)
    if not f then return nil,why end
    local d=data()
    local text=f.text and f.text:lower()
    local out={}
    for _,name in ipairs(names())do
        local e=d.events[name]
        local b=bank(e.banks[1])
        local p=b.provider or{}
        if(f.family==nil or name:match('^[^/]+')==f.family)and(f.kind==nil or e.kind==f.kind)
            and(f.bank==nil or has((function()local t={}for k,i in ipairs(e.banks)do t[k]=bank(i).name end return t end)(),
                f.bank:lower()))
            and(f.faction==nil or b.faction==f.faction)
            and(f.bus==nil or(e.bus~=nil and e.bus:find(f.bus:lower(),1,true)~=nil))
            and(f.stratagem==nil or(f.stratagem==true and p.stratagem~=nil)or p.stratagem==f.stratagem)
            and(f.resident_only==nil or(b.provider==nil)==f.resident_only)
            and(f.named==nil or(e.wwise~=nil)==f.named)
            and(f.weapon==nil or(f.weapon==true and e.weapons~=nil)or has(e.weapons,f.weapon))
            and(f.global==nil or(e.effects~=nil)==f.global)
            and(text==nil or name:find(text,1,true))then
            out[#out+1]=M.public(name,e)
        end
    end
    return out
end

-- The Init bank's game parameters, switch groups and state groups: {name ('0x<id>' when unnamed), named, ...}.
function M.parameters()
    local d=data()
    local out={}
    for hex,p in pairs(d.parameters)do
        out[#out+1]={name=p.name or('0x'..hex),named=p.name~=nil,default=p.default,events=p.events}
    end
    table.sort(out,function(a,b)return a.name<b.name end)
    return out
end
local function groups(key)
    local d=data()
    local out={}
    for hex,g in pairs(d[key])do
        local values={}
        for vhex,v in pairs(g.values)do values[#values+1]=v or('0x'..vhex)end -- v is false when unnamed
        table.sort(values)
        out[#out+1]={name=g.name or('0x'..hex),named=g.name~=nil,values=values,
            parameter=g.parameter and label('parameters',g.parameter)or nil}
    end
    table.sort(out,function(a,b)return a.name<b.name end)
    return out
end
function M.switch_groups()return groups('switchGroups')end
function M.state_groups()return groups('stateGroups')end

-- A game parameter, switch group, switch, state group or state by name or {id = n}: the 32-bit id and the name the
-- sound engine hashes (its own name, lower case; nil when only the id is known: post it through a name that hashes to
-- the id). kind: 'parameters' | 'switchGroups' | 'stateGroups'. For a group's value pass the group's id as `group`.
-- Returns id, own name (or nil), or nil and why. Ids outside the catalogue are accepted only when `any` is true.
local function fnv1(name)
    local bit=require('bit')
    local h=0x811C9DC5
    for i=1,#name do
        local c=name:byte(i)
        if c>=65 and c<=90 then c=c+32 end
        h=(h*0x193+(h%256)*16777216)%4294967296
        local low=h%256
        h=h-low+bit.band(bit.bxor(low,c),255)
    end
    return h
end
M.fnv1=fnv1
function M.lookup(kind,value,group_hex)
    local d=data()
    local id
    if type(value)=='table'then
        id=value.id
        if not(type(id)=='number'and id%1==0 and id>0 and id<4294967296)then return nil,'{id = ...} needs a 32-bit id'end
    elseif type(value)=='string'and#value>0 and#value<=128 and not value:find('[%z\1-\31\127]')then
        id=fnv1(value)
    else
        return nil,'a name or {id = ...} is required'
    end
    local hex=('%08X'):format(id)
    if type(d[kind])~='table'then return nil,'not in the catalogue'end
    if group_hex then
        local g=d[kind][group_hex]
        local v=g and g.values[hex]
        if v==nil then return nil,'not a value of that group in the catalogue'end
        return id,v or nil
    end
    local row=d[kind][hex]
    if row then return id,row.name end
    return nil,'not in the catalogue'
end
function M.reset_for_tests()D,by_id,by_wwise,sorted=nil,nil,nil,nil end
return M
