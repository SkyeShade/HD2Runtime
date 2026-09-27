local M={}
function M.u32(s,o)
    assert(type(o)=='number' and o>=0 and o%1==0 and o+4<=#s,'u32 bounds')
    local a,b,c,d=s:byte(o+1,o+4)
    return a+b*256+c*65536+d*16777216
end
function M.u16(s,o)
    assert(o>=0 and o+2<=#s,'u16 bounds')
    local a,b=s:byte(o+1,o+2);return a+b*256
end
function M.pointer(s,o)
    local lo,hi=M.u32(s,o),M.u32(s,o+4)
    assert(hi<=2097151,'unsafe pointer precision')
    return lo+hi*4294967296
end
function M.resource(s,o)
    return string.format('0x%08X%08X',M.u32(s,o+4),M.u32(s,o))
end
function M.hex(s)
    return (s:gsub('.',function(c)return string.format('%02x',c:byte())end))
end
function M.unhex(s)
    assert(#s%2==0 and not s:find('[^%x]'),'invalid hex')
    return (s:gsub('..',function(p)return string.char(tonumber(p,16))end))
end
function M.value(s,o,kind)
    if kind=='u8' then
        assert(type(o)=='number'and o>=0 and o%1==0 and o<#s,'u8 bounds')
        return s:byte(o+1)
    end
    local n=M.u32(s,o)
    if kind=='u32' then return n end
    if kind=='i32' then return n>=2147483648 and n-4294967296 or n end
    assert(kind=='f32','unknown storage')
    local sign=n>=2147483648 and -1 or 1
    local exp=math.floor(n/8388608)%256
    local frac=n%8388608
    assert(exp~=255,'nonfinite field value')
    if exp==0 then return sign*frac*2^-149 end
    return sign*(1+frac/8388608)*2^(exp-127)
end
-- Accept only a relative offset or a relocated pointer to the SAME bounded body.
function M.relative(value,base,start,length,minimum)
    local rel=value>=minimum and value<=length and start<=length-value
    local delta=value-base
    local absolute=delta>=minimum and delta<=length and start<=length-delta
    assert(rel~=absolute,'invalid/ambiguous bounded pointer')
    return rel and value or delta
end
return M
