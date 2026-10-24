-- Immutable per-renderer style. Colour conventions match hd2.ui, converted to
-- the native {a,r,g,b} order once; nothing unvalidated reaches Gui bindings.
local M={}
local DEFAULTS={ring=true,ring_color='#FFB420E6',ring_width=1.2,ring_segments=96,
    marker_shape='corners',marker_size=12,line_width=1.5,scale=1,
    acquiring_color='#FFB420E6',locked_color='#40FF60FF',clear_color='#64DCFFE6',
    blocked_color='#FF5050FF',unknown_color='#AAB4BEBE',show_labels=true,
    show_numbers=true,show_progress=true,show_los=true,aim_only=true}
local BOUNDS={ring_width={.5,8},ring_segments={24,128},marker_size={4,64},
    line_width={.5,8},scale={.5,3},ring_radius={8,2000}}
local function finite(n,lo,hi)return type(n)=='number'and n==n and n>=lo and n<=hi end
local function colour(value)
    if type(value)=='string'then
        local hex=value:match('^#(%x+)$')
        if not hex or(#hex~=6 and#hex~=8)then return nil end
        return{#hex==8 and tonumber(hex:sub(7,8),16)or 255,
            tonumber(hex:sub(1,2),16),tonumber(hex:sub(3,4),16),tonumber(hex:sub(5,6),16)}
    end
    if type(value)~='table'then return nil end
    local out={value[4]or value.a or 255,value[1]or value.r,value[2]or value.g,value[3]or value.b}
    for i=1,4 do if not finite(out[i],0,255)then return nil end;out[i]=math.floor(out[i]+.5)end
    return out
end
function M.validate(opts)
    assert(opts==nil or type(opts)=='table','reticle style must be a table')
    local style={}
    for key,value in pairs(DEFAULTS)do style[key]=value end
    for key,value in pairs(opts or{})do
        assert(DEFAULTS[key]~=nil or key=='ring_radius','unknown reticle style: '..tostring(key))
        style[key]=value
    end
    -- Vanilla selects the stock marker art without the mod's diagnostic overlay.
    -- Explicit decorations remain available to API clients that ask for them.
    if style.marker_shape=='vanilla'then
        for _,key in ipairs({'show_labels','show_numbers','show_progress','show_los'})do
            if not opts or opts[key]==nil then style[key]=false end
        end
    end
    for key,value in pairs(style)do
        if key:match('_color$')then style[key]=assert(colour(value),'invalid colour: '..key)
        elseif BOUNDS[key]then assert(finite(value,BOUNDS[key][1],BOUNDS[key][2]),'invalid '..key)
        elseif key=='marker_shape'then assert(value=='corners'or value=='box'or value=='cross'or value=='vanilla','invalid marker_shape')
        else assert(type(value)=='boolean','invalid '..key)end
    end
    assert(style.ring_segments%1==0,'ring_segments must be an integer')
    return style
end
return M
