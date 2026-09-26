-- Little-endian integers for Lua 5.1/LuaJIT without string.pack.
local M={}
local LIMIT=9007199254740991
local function integer(value,label)
    assert(type(value)=='number'and value>=0 and value%1==0 and value<=LIMIT,
        (label or'integer')..' outside exact range')
    return value
end
function M.u32(value)
    value=integer(value,'u32');assert(value<=4294967295,'u32 overflow')
    return string.char(value%256,math.floor(value/256)%256,
        math.floor(value/65536)%256,math.floor(value/16777216)%256)
end
function M.u64(value)
    value=integer(value,'u64')
    local low=value%4294967296
    return M.u32(low)..M.u32(math.floor(value/4294967296))
end
function M.cursor(bytes,offset)
    local self={at=offset or 0}
    local function take(length)
        assert(length>=0 and self.at+length<=#bytes,'truncated binary input')
        local value=bytes:sub(self.at+1,self.at+length);self.at=self.at+length;return value
    end
    function self.bytes(length)return take(length)end
    function self.u32()
        local s=take(4);local a,b,c,d=s:byte(1,4)
        return a+b*256+c*65536+d*16777216
    end
    function self.u64()
        local low=self.u32();local high=self.u32()
        assert(high<=2097151,'u64 exceeds exact numeric range')
        return low+high*4294967296
    end
    return self
end
return M
