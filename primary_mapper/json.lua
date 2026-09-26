-- Minimal deterministic JSON encoder for machine-readable diagnostic output.
local M={}
local ARRAY={}
function M.array(values)return setmetatable(values or {},ARRAY)end
local function escape(value)
    return '"'..value:gsub('[%z\1-\31\\"]',function(char)
        local map={['"']='\\"',['\\']='\\\\',['\b']='\\b',['\f']='\\f',
            ['\n']='\\n',['\r']='\\r',['\t']='\\t'}
        return map[char] or string.format('\\u%04X',char:byte())
    end)..'"'
end
local encode
local function is_array(value)
    if getmetatable(value)==ARRAY then return true,#value end
    local count=0
    for key in pairs(value)do
        if type(key)~='number' or key<1 or key%1~=0 then return false end
        count=count+1
    end
    return count>0 and count==#value,#value
end
encode=function(value,seen)
    local kind=type(value)
    if kind=='nil' then return 'null' end
    if kind=='boolean' then return value and 'true' or 'false' end
    if kind=='number' then assert(value==value and value~=math.huge and value~=-math.huge,'nonfinite JSON number');return string.format('%.17g',value)end
    if kind=='string' then return escape(value)end
    assert(kind=='table','unsupported JSON type: '..kind)
    assert(not seen[value],'JSON cycle');seen[value]=true
    local array,n=is_array(value);local parts={}
    if array then
        for i=1,n do parts[i]=encode(value[i],seen)end
        seen[value]=nil;return '['..table.concat(parts,',')..']'
    end
    local keys={};for key in pairs(value)do assert(type(key)=='string','JSON object key must be string');keys[#keys+1]=key end
    table.sort(keys)
    for i,key in ipairs(keys)do parts[i]=escape(key)..':'..encode(value[key],seen)end
    seen[value]=nil;return '{'..table.concat(parts,',')..'}'
end
function M.encode(value)return encode(value,{})end
return M
