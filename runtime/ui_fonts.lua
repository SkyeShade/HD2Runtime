-- The custom stratagem panel's fonts (docs/custom-stratagems.md "The panel's fonts"): FS Sinclair, the native loadout
-- screen's typeface, as Runtime-owned engine fonts the build derives from the installed game (scripts/hd2_font.py,
-- domains/ui_fonts.lua): the title role in FS Sinclair Medium, the body role in FS Sinclair. They ship in the Runtime's
-- own archive (a patch of the boot package, where the game's own engine fonts are) and load at startup. A role whose
-- font and material are not both loaded draws in monaco, the engine font the panel used before (never guessed: the
-- same resource-table lookup as every other Runtime resource). Read-only.
--
-- The game's own language fonts (research/docs/game-font-text.md; docs/ui-overlay.md "Other scripts"): the regular
-- engine FONT of each language font package (Latin, Russian, Simplified and Traditional Chinese, Japanese, Korean),
-- named by its hash, drawn through a Runtime-owned material per font whose GUI instance the overlay points at the
-- font's atlas. The game loads only the selected language's package, so a game font is used only while its font, its
-- atlas and its Runtime material are all proven loaded. Text is split into runs: the role font draws every character
-- it has (text it fully covers is one run, exactly as before); a character it lacks goes to a resident game font that
-- has it; a character no font has stays with the role font (the engine draws its '?').
local images=require('hd2runtime/runtime/image_resources')
local D=require('hd2runtime/domains/ui_fonts')
local M={}
M.ROLES={'title','body'}
M.MAX_TEXT_BYTES=512      -- one text item (about 170 CJK characters): Builder:text and engine_gui refuse longer text
M.GAME=D.game or{}
M.KERN_KEY=4294967296     -- a kerning pair's key: previous * 2^32 + codepoint (domains/ui_fonts_<key>.lua)
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
-- The width of text at `size` pixels in a font (its glyph advances, and its kerning pairs as the engine adds them; an
-- unknown character counts as the '?').
function M.width(font,text,size)
    local adv,em,kern=font.advances,font.em,font.kerning
    local q=adv[63]or em*0.5
    local w,prev=0,nil
    for _,cp in utf8_codes(text)do
        w=w+(adv[cp]or q)
        if kern and prev then w=w+(kern[prev*M.KERN_KEY+cp]or 0)end
        prev=cp
    end
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

---------------------------------------------------------------------------------------------------- game fonts --
-- A game font's metrics module (its advances and kerning), loaded on first use; nil and why when it cannot be.
local metrics={}
local function game_metrics(entry)
    local m=metrics[entry.key]
    if m==nil then
        local ok,data=pcall(require,entry.module)
        m=ok and type(data)=='table'and type(data.advances)=='table'and data or false
        metrics[entry.key]=m
    end
    return m or nil
end
-- The measuring and drawing font of a game font entry: {key, game = entry, name = '#' .. its hash (the engine font,
-- named by IdString64), material, atlas, em, drop, advances, kerning}. nil when its metrics are missing.
local objects={}
function M.game_font(entry)
    local o=objects[entry.key]
    if o then return o end
    local m=game_metrics(entry)
    if not m then return nil end
    o={key=entry.key,game=entry,name='#'..entry.font,material=entry.material,atlas=entry.atlas,em=entry.em,
        drop=entry.drop or 0,cap=(entry.cap or 0.7)*entry.em,advances=m.advances,
        kerning=next(m.kerning or{})and m.kerning or nil,label=entry.label,languages=entry.languages}
    objects[entry.key]=o
    return o
end
-- Whether a game font can be drawn now: its FONT and atlas (by hash) and its Runtime material (by name) are all loaded,
-- read as the game's lookup reads them. true, or false and why. Not cached: the overlay asks it every frame a font is
-- used (a language switch unloads it).
function M.game_font_ready(runtime,entry)
    local checks={{D.types.font,entry.font,'its font'},{D.types.texture,entry.atlas,'its atlas'}}
    for _,c in ipairs(checks)do
        local done,ok,why=pcall(images.loaded_hex,runtime,c[1],c[2])
        if not(done and ok==true)then return false,entry.label..': '..c[3]..' is not loaded ('..tostring(done and why or ok)..')'end
    end
    local done,ok,why=pcall(images.loaded,runtime,D.types.material,entry.material)
    if not(done and ok==true)then return false,entry.label..': the Runtime material is not loaded ('..tostring(done and why or ok)..')'end
    return true
end
-- The game fonts loaded now, in the domain's order, as drawing fonts (M.game_font): proven at most `max_age` seconds
-- ago (default 1; 0 asks again). Callers that draw re-prove each font they use in the same frame (M.game_font_ready).
local cache,cache_at,cache_runtime={},nil,nil
M.clock=os.clock
function M.resident_game_fonts(runtime,max_age)
    local now=M.clock()
    if cache_at and cache_runtime==runtime and now-cache_at<(max_age or 1)and now>=cache_at then return cache end
    local list={}
    for _,entry in ipairs(M.GAME)do
        if M.game_font_ready(runtime,entry)then
            local o=M.game_font(entry)
            if o then list[#list+1]=o end
        end
    end
    cache,cache_at,cache_runtime=list,now,runtime
    return list
end

-- On demand (0.31.0, issue #8): the game loads only its selected language's font, so a mod window drawing Chinese in
-- an English game showed '?'. Text with characters neither its font nor a loaded game font has asks for the game font
-- package that covers the most of them (then the next, at most two per text), through the game's own reference-
-- counted package system (core/assets: proven pins, a catalogued package, residency read back, kept for the session).
-- Nothing is drawn with a font until the per-frame residency proof finds it loaded (resident_game_fonts): until then
-- the characters keep showing '?'. One request per font per session; a refusal is logged once and not retried.
M.requests={}            -- font key -> {state = 'requested' | 'refused', why}
local asked={}           -- text -> true (texts already looked at), bounded
local asked_count=0
local function emit(message)
    local ok,log=pcall(require,'hd2runtime/runtime/log')
    if ok and log and log.emit then pcall(log.emit,'[HD2Runtime] '..message)end
end
-- The game fonts (not loaded now) that cover the characters of text that `font` and `extra` lack: the font covering
-- most of them first (ties in the domain's order), then the next for what remains; at most two.
function M.fonts_for(font,text,extra)
    local missing,count={},0
    for _,cp in utf8_codes(text)do
        if cp>32 and not missing[cp]and not font.advances[cp]then
            local ok=false
            for _,g in ipairs(extra or{})do if g.advances[cp]then ok=true;break end end
            if not ok then missing[cp]=true;count=count+1 end
        end
    end
    local chosen={}
    while count>0 and#chosen<2 do
        local best,best_n
        for _,entry in ipairs(M.GAME)do
            local g=M.game_font(entry)
            local taken=false
            for _,c in ipairs(chosen)do if c==g then taken=true end end
            for _,e in ipairs(extra or{})do if e==g then taken=true end end
            if g and not taken then
                local n=0
                for cp in pairs(missing)do if g.advances[cp]then n=n+1 end end
                if n>0 and(not best_n or n>best_n)then best,best_n=g,n end
            end
        end
        if not best then break end
        chosen[#chosen+1]=best
        for cp in pairs(missing)do if best.advances[cp]then missing[cp]=nil;count=count-1 end end
    end
    return chosen
end
function M.want(runtime,font,text,extra)
    if asked[text]or type(runtime)~='table'then return end
    if asked_count<512 then asked[text]=true;asked_count=asked_count+1 end
    for _,g in ipairs(M.fonts_for(font,text,extra))do
        if not M.requests[g.key]then
            local ok,why=pcall(function()
                local assets=require('hd2runtime/core/assets')
                local dependency=assert(assets.font_dependency(g.key),'no package for the '..g.label..' font')
                assets.request(runtime,dependency,'hd2runtime-ui-fonts')
            end)
            M.requests[g.key]=ok and{state='requested'}or{state='refused',why=tostring(why)}
            emit(ok and('ui fonts: loading the game\'s '..g.label..' font package for mod window text (it draws once '
                ..'loaded; until then those characters show "?")')
                or('ui fonts: the game\'s '..g.label..' font package could not be requested: '..tostring(why)))
            -- the next residency check looks again soon
            cache_at=nil
        end
    end
end

-------------------------------------------------------------------------------------------------------- runs --
-- Splits text into runs {font, text} (byte-exact pieces of text, in order): the role `font` draws every character it
-- has; a character it lacks goes to the first font of `extra` (the resident game fonts) that has it; a space stays in
-- the run before it when that run's font has one (so a CJK phrase with spaces is one run); a character no font has
-- stays with the role font (its '?'). Text the role font fully covers, or no extra font, is a single run.
function M.runs(font,text,extra)
    if not extra or#extra==0 or M.has(font,text)then return {{font=font,text=text}}end
    local runs,cur,start={},nil,1
    for at,cp in utf8_codes(text)do
        local f
        if cur and cp==32 and cur.advances[32]then f=cur
        elseif font.advances[cp]then f=font
        else
            for _,g in ipairs(extra)do if g.advances[cp]then f=g;break end end
            f=f or font
        end
        if f~=cur then
            if cur then runs[#runs+1]={font=cur,text=text:sub(start,at-1)}end
            cur,start=f,at
        end
    end
    if cur then runs[#runs+1]={font=cur,text=text:sub(start)}end
    return runs
end
-- The width of text at `size` drawn as M.runs splits it.
function M.measure(font,text,size,extra)
    local w=0
    for _,run in ipairs(M.runs(font,text,extra))do w=w+M.width(run.font,run.text,size)end
    return w
end
-- Whether every character of text can be drawn by `font` or one of `extra`: true, or false, the number of distinct
-- characters none of them has and up to three of them (as UTF-8 strings).
function M.drawable(font,text,extra)
    local seen,n,sample={},0,{}
    for at,cp in utf8_codes(text)do
        if cp>=32 and not seen[cp]and not font.advances[cp]then
            local ok=false
            for _,g in ipairs(extra or{})do if g.advances[cp]then ok=true;break end end
            if not ok then
                seen[cp]=true;n=n+1
                if#sample<3 then sample[#sample+1]=text:sub(at,at+M.char_length(text,at)-1)end
            end
        end
    end
    return n==0,n,sample
end

-------------------------------------------------------------------------------------------------------- wrap --
-- Characters a line may break between with no space: CJK ideographs, kana, Hangul syllables, CJK punctuation and
-- fullwidth forms. Closing punctuation never starts a line (it stays with the character before it).
local function wide(cp)
    return(cp>=0x3000 and cp<=0x30FF)or(cp>=0x3400 and cp<=0x4DBF)or(cp>=0x4E00 and cp<=0x9FFF)
        or(cp>=0xAC00 and cp<=0xD7A3)or(cp>=0xF900 and cp<=0xFAFF)or(cp>=0xFF00 and cp<=0xFFEF)
        or(cp>=0x1100 and cp<=0x11FF)or(cp>=0x3130 and cp<=0x318F)
end
M.wide=wide
local CLOSING={[0x3001]=true,[0x3002]=true,[0xFF0C]=true,[0xFF0E]=true,[0xFF01]=true,[0xFF1F]=true,[0xFF1A]=true,
    [0xFF1B]=true,[0xFF09]=true,[0x300D]=true,[0x300F]=true,[0x3011]=true,[0x3009]=true,[0x300B]=true,[0x30FC]=true,
    [0x3063]=true,[0x30C3]=true,[0x3083]=true,[0x3085]=true,[0x3087]=true,[0x30E3]=true,[0x30E5]=true,[0x30E7]=true,
    [0x2026]=true,[0x2025]=true,[0x2019]=true,[0x201D]=true,[44]=true,[46]=true,[33]=true,[63]=true,[58]=true,[59]=true,
    [41]=true}
-- The byte length of the UTF-8 character at byte i of s (1 for a stray byte).
function M.char_length(s,i)
    local c=s:byte(i)
    if not c then return 0 end
    local n=c>=0xF0 and 4 or c>=0xE0 and 3 or c>=0xC0 and 2 or 1
    if i+n-1>#s then return 1 end
    for k=1,n-1 do local b=s:byte(i+k);if b<0x80 or b>0xBF then return 1 end end
    return n
end
-- Text without its last UTF-8 character.
local function drop_last(s)
    local i,last=1,0
    while i<=#s do last=i;i=i+M.char_length(s,i)end
    return s:sub(1,last-1)
end
M.drop_last=drop_last
-- The tokens a line is built from: {text, space} where space tells that a space came before it. A token is a run of
-- non-space characters, except that a wide character is a token of its own (closing punctuation joins the one before).
local function tokens(text)
    local out,cur,space,prev_wide={},nil,false,false
    local i=1
    while i<=#text do
        local n=M.char_length(text,i)
        local ch=text:sub(i,i+n-1)
        local cp
        for _,c in utf8_codes(ch)do cp=c end
        if cp<=32 then   -- a space or any other whitespace / control byte separates tokens, as %S+ did
            if cur then out[#out+1]=cur;cur=nil end
            space=true
        elseif cur and CLOSING[cp]then cur.text=cur.text..ch
        elseif wide(cp)then
            if cur then out[#out+1]=cur end
            cur={text=ch,space=space,wide=true};space=false
        else
            if cur and cur.wide then out[#out+1]=cur;cur=nil end
            if cur then cur.text=cur.text..ch else cur={text=ch,space=space};space=false end
        end
        i=i+n
    end
    if cur then out[#out+1]=cur end
    return out
end
-- Splits text into lines no wider than `width` pixels at `size`: at spaces, and between any two wide (CJK)
-- characters; a token wider than a line is cut between characters (never inside a UTF-8 sequence). At most `lines`
-- lines, the last ending with '...' when text remains. `extra`: the resident game fonts the text is measured with
-- (M.runs); nil measures with `font` alone, as before.
function M.wrap(font,text,size,width,lines,extra)
    local function w(s)return extra and M.measure(font,s,size,extra)or M.width(font,s,size)end
    local out,line={},''
    for _,token in ipairs(tokens(tostring(text)))do
        local candidate=line==''and token.text or(line..(token.space and' 'or'')..token.text)
        if w(candidate)<=width then line=candidate
        else
            if line~=''then out[#out+1]=line end
            line=token.text
            while w(line)>width and M.char_length(line,1)<#line do
                -- the longest prefix of whole characters that fits (at least one character)
                local cut,i=M.char_length(line,1),1+M.char_length(line,1)
                while i<=#line do
                    local n=M.char_length(line,i)
                    if w(line:sub(1,i+n-1))>width then break end
                    cut,i=i+n-1,i+n
                end
                out[#out+1]=line:sub(1,cut)
                line=line:sub(cut+1)
            end
        end
    end
    if line~=''then out[#out+1]=line end
    if lines and#out>lines then
        local last=out[lines]
        while M.char_length(last,1)<#last and w(last..'...')>width do last=drop_last(last)end
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
function M.reset_for_tests()resident={};metrics={};objects={};cache,cache_at,cache_runtime={},nil,nil
    M.requests={};asked={};asked_count=0 end
return M
