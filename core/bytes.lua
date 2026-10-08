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
function M.encode(value,kind)
    if kind=='u8' then
        assert(type(value)=='number'and value>=0 and value<=255 and value%1==0,'invalid u8 value')
        return string.char(value)
    end
    if kind=='u32'or kind=='i32' then
        assert(type(value)=='number'and value%1==0,'invalid integer value')
        if kind=='u32'then assert(value>=0 and value<=4294967295,'u32 range')
        else assert(value>=-2147483648 and value<=2147483647,'i32 range');if value<0 then value=value+4294967296 end end
        return string.char(value%256,math.floor(value/256)%256,
            math.floor(value/65536)%256,math.floor(value/16777216)%256)
    end
    assert(kind=='f32'and type(value)=='number'and value==value
        and value>-math.huge and value<math.huge,'invalid f32 value')
    if value==0 then return string.rep('\0',4)end
    local sign=0;if value<0 then sign=2147483648;value=-value end
    local exponent=math.floor(math.log(value)/math.log(2))
    local fraction
    if exponent<-126 then
        fraction=math.floor(value/2^-149+0.5);exponent=0
    else
        fraction=math.floor((value/2^exponent-1)*8388608+0.5)
        if fraction==8388608 then fraction=0;exponent=exponent+1 end
        exponent=exponent+127
    end
    assert(exponent>=0 and exponent<255,'f32 range')
    local bits=sign+exponent*8388608+fraction
    return string.char(bits%256,math.floor(bits/256)%256,
        math.floor(bits/65536)%256,math.floor(bits/16777216)%256)
end
-- Accept only a relative offset or a relocated pointer to the SAME bounded body.
function M.relative(value,base,start,length,minimum)
    local rel=value>=minimum and value<=length and start<=length-value
    local delta=value-base
    local absolute=delta>=minimum and delta<=length and start<=length-delta
    assert(rel~=absolute,'invalid/ambiguous bounded pointer')
    return rel and value or delta
end
-- M.relative for an entity map row's membership pointer, its refusal naming the row (0.30.2: the bare message named
-- nothing, and a stray row of another resource refuses the whole capture). No address is put in the message.
function M.membership(value,base,start,length,minimum,row,resource,count)
    local ok,result=pcall(M.relative,value,base,start,length,minimum)
    if ok then return result end
    error(('invalid/ambiguous bounded pointer: entity map row %d (resource %s, %d members) has a membership list '
        ..'outside the map body; the entity map of the game is not as reviewed (another mod may have loaded or changed '
        ..'entities), so this write is refused'):format(row,tostring(resource),count),0)
end
return M
