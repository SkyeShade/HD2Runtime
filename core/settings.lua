local b=require('hd2runtime/core/bytes')
local M={}
function M.parse(bytes,base,desc)
    assert(#bytes==desc.size and b.u32(bytes,0)==#desc.groups,'settings extent/count')
    local records={}
    local ending=4
    for gi,g in ipairs(desc.groups)do
        assert(g.offset==ending,'settings group continuity')
        assert(bytes:sub(g.offset+1,g.offset+24)==b.unhex(g.header),'settings framing changed')
        ending=g.offset+24+b.u32(bytes,g.offset+12)
        assert(ending<=#bytes,'settings group outside allocation')
        if g.root then
            local p=b.pointer(bytes,g.root)
            assert(p==g.row_offset or p==base+g.root+g.row_offset,'settings pointer outside reviewed rows')
            assert(b.pointer(bytes,g.root+8)==g.count,'settings row count changed')
            local start=g.root+g.row_offset
            assert(g.row_offset>=16 and start+g.count*desc.stride<=ending,'settings row bounds')
            for row=0,g.count-1 do
                local at=start+row*desc.stride
                local kind=b.u32(bytes,at)
                assert(not records[kind],'duplicate settings type')
                records[kind]={bytes=bytes:sub(at+1,at+desc.stride),group=gi-1,row=row,offset=at,
                    kind=kind,settings_type=string.format('0x%08X',b.u32(bytes,g.offset+8))}
            end
        end
    end
    assert(ending==#bytes,'settings trailing bytes')
    return records
end
return M
