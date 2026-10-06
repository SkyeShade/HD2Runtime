-- The custom stratagem panel's fonts (docs/custom-stratagems.md "The panel's fonts"): FS Sinclair, the native loadout
-- screen's typeface, as Runtime-owned engine fonts the build derives from the installed game (scripts/hd2_font.py,
-- domains/ui_fonts.lua): the title role in FS Sinclair Medium, the body role in FS Sinclair. They ship in the Runtime's
-- own archive (a patch of the boot package, where the game's own engine fonts are) and load at startup. A role whose
-- font and material are not both loaded draws in monaco, the engine font the panel used before (never guessed: the
-- same resource-table lookup as every other Runtime resource). Read-only.
local images=require('hd2runtime/runtime/image_resources')
local D=require('hd2runtime/domains/ui_fonts')
local M={}
M.ROLES={'title','body'}
local utf8_codes

local resident={}
local function loaded(runtime,name)
    if resident[name]~=nil then return resident[name]end
    local ok=true
    for _,kind in ipairs({D.types.font,D.types.material})do
        local done,result=pcall(images.loaded,runtime,kind,name)
        ok=ok and done and result==true
    end
    -- Only a positive answer is kept (a font loads at startup and stays loaded); a negative one is asked again.
    if ok then resident[name]=true end
    return ok
end

-- The font of a role: {name (font and material), em, cap, ascent, descent, line, advances, fallback} and why it fell
-- back (nil when it is the role's own font).
function M.font(runtime,role)
    local f=D.fonts[role]
    if f and loaded(runtime,f.name)then return f end
    local m=D.fonts.monaco
    return setmetatable({fallback=true},{__index=m}),(f and(f.name..' is not loaded')or('no font role '..tostring(role)))
end
-- The width of text at `size` pixels in a font (its glyph advances; an unknown character counts as the '?').
function M.width(font,text,size)
    local adv,em=font.advances,font.em
    local q=adv[63]or em*0.5
    local w=0
    for _,cp in utf8_codes(text)do w=w+(adv[cp]or q)end
    return w*size/em
end
-- Whether a font has a glyph for every character of text (the Runtime-owned fonts have the call-in code's arrows,
-- monaco does not).
function M.has(font,text)
    for _,cp in utf8_codes(text)do if not font.advances[cp]then return false end end
    return true
end
-- The cap height of a font at `size` (the size that gives a cap height: size = cap_px * em / cap).
function M.size_for_cap(font,cap_px)return cap_px*font.em/font.cap end
-- Splits text into lines no wider than `width` pixels at `size`, at spaces (a word wider than a line is cut); at most
-- `lines` lines, the last ending with '...' when text remains.
function M.wrap(font,text,size,width,lines)
    local out,line={},''
    for word in tostring(text):gmatch('%S+')do
        local candidate=line==''and word or(line..' '..word)
        if M.width(font,candidate,size)<=width then line=candidate
        else
            if line~=''then out[#out+1]=line end
            line=word
            while M.width(font,line,size)>width and#line>1 do
                local cut=#line-1
                while cut>1 and M.width(font,line:sub(1,cut),size)>width do cut=cut-1 end
                out[#out+1]=line:sub(1,cut)
                line=line:sub(cut+1)
            end
        end
    end
    if line~=''then out[#out+1]=line end
    if lines and#out>lines then
        local last=out[lines]
        while#last>1 and M.width(font,last..'...',size)>width do last=last:sub(1,-2)end
        out[lines]=last..'...'
        for k=#out,lines+1,-1 do out[k]=nil end
    end
    return out
end
-- UTF-8 codepoints of a string (ASCII and two/three-byte sequences; anything else byte by byte).
utf8_codes=function(s)
    local i,n=1,#s
    return function()
        if i>n then return nil end
        local c=s:byte(i)
        local cp,len=c,1
        if c>=0xF0 and i+3<=n then cp,len=((c%8)*262144)+((s:byte(i+1)%64)*4096)+((s:byte(i+2)%64)*64)+(s:byte(i+3)%64),4
        elseif c>=0xE0 and i+2<=n then cp,len=((c%16)*4096)+((s:byte(i+1)%64)*64)+(s:byte(i+2)%64),3
        elseif c>=0xC0 and i+1<=n then cp,len=((c%32)*64)+(s:byte(i+1)%64),2 end
        local at=i
        i=i+len
        return at,cp
    end
end
M.utf8_codes=utf8_codes
function M.reset_for_tests()resident={}end
return M
