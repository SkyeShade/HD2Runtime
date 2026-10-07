-- Names for Wwise event ids (runtime/sound_events.lua; docs/sounds.md). Pure computation, no game access; the build
-- runs the same code offline (scripts/generate_sound_event_names.py) to precompute the catalogue's names.
--
-- The sound engine identifies an event by the FNV-1 32 hash of its lower-cased name (AK GetIDFromString; the Wwise
-- plugin's trigger_event takes only a name). An event known only by its id is posted through a name whose hash is that
-- id: PREFIX and seven characters of ALPHABET, found by meet-in-the-middle.
local bit=require('bit')
local M={}
M.PREFIX='hd2runtime_'
M.ALPHABET='abcdefghijklmnopqrstuvwxyz0123456789_'
local P_LOW=0x193
local P_INV=0x359C449B   -- 0x01000193^-1 mod 2^32
M.P_INV=P_INV

-- FNV-1 32 one step: h * 0x01000193 mod 2^32 (exactly: h * 0x193 + (h mod 256) * 2^24), then the low byte xor c.
function M.forward(h,c)
    h=(h*P_LOW+(h%256)*16777216)%4294967296
    local low=h%256
    return h-low+bit.band(bit.bxor(low,c),255)
end
-- (a * b) mod 2^32, exact for u32 operands.
function M.mul32(a,b)
    local lo,hi=b%65536,math.floor(b/65536)
    return(a*lo+((a*hi)%65536)*65536)%4294967296
end
function M.backward(h,c)
    local low=h%256
    return M.mul32(h-low+bit.band(bit.bxor(low,c),255),P_INV)
end
-- The Wwise id of a name (A-Z lower-cased, as the sound engine does).
function M.id(name)
    local h=0x811C9DC5
    for i=1,#name do
        local c=name:byte(i)
        if c>=65 and c<=90 then c=c+32 end
        h=M.forward(h,c)
    end
    return h
end

-- A name whose id is `id`: the states after 3 characters forward from the prefix, then 4 characters backward from the
-- id (37^4 ~ 1.9 M steps, about 22 expected matches); the smallest matching name is taken, so it is always the same.
-- nil when none.
function M.search(id)
    assert(type(id)=='number'and id%1==0 and id>0 and id<4294967296,'a Wwise event id is an integer from 1 to 2^32 - 1')
    local A=M.ALPHABET
    local n=#A
    local codes={}
    for i=1,n do codes[i]=A:byte(i)end
    local forward,backward=M.forward,M.backward
    local start=0x811C9DC5
    for i=1,#M.PREFIX do start=forward(start,M.PREFIX:byte(i))end
    local table3={}
    for i=1,n do
        local h1=forward(start,codes[i])
        for j=1,n do
            local h2=forward(h1,codes[j])
            for k=1,n do
                local h3=forward(h2,codes[k])
                if table3[h3]==nil then table3[h3]=(i-1)*n*n+(j-1)*n+(k-1)end
            end
        end
    end
    local best
    for d=1,n do
        local g3=backward(id,codes[d])
        for e=1,n do
            local g2=backward(g3,codes[e])
            for f=1,n do
                local g1=backward(g2,codes[f])
                for g=1,n do
                    local head=table3[backward(g1,codes[g])]
                    if head then
                        local i,j,k=math.floor(head/(n*n)),math.floor(head/n)%n,head%n
                        local name=M.PREFIX..A:sub(i+1,i+1)..A:sub(j+1,j+1)..A:sub(k+1,k+1)
                            ..A:sub(g,g)..A:sub(f,f)..A:sub(e,e)..A:sub(d,d)
                        if M.id(name)==id and(best==nil or name<best)then best=name end
                    end
                end
            end
        end
    end
    return best
end
return M
