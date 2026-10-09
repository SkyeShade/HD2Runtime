local hd2=require('mods/skyeshade/hd2runtime')
-- GameFontTextProof 0.2.0: THE GAME'S OWN FONTS IN A MOD WINDOW (HD2Runtime 0.30.4 development build; docs/ui-overlay.md
-- "Other scripts"). A mod window with one line each of Latin, Polish, Simplified Chinese, Traditional Chinese, Japanese,
-- Korean and Russian, and a wrapped Chinese paragraph. Characters FS Sinclair lacks are drawn in the game's own
-- language font. 0.2.0 (issue #8): the game loads only its selected language's font; the Runtime now loads the font
-- package a line needs, in ANY game language, so every line should draw a second or two after the window opens (each
-- shows '?' until its font is loaded). The log says 'ui fonts: loading the game's ... font package' once per font.
-- Visual only: nothing of the game is written (the font packages are loaded like item packages).
--   Ctrl+F7  show / hide the window
--   Ctrl+F8  log the window's state again (every line's runs, fonts and residency)
local mod=hd2.mod()
local BUILD='0.2.0 FONTS IN ANY LANGUAGE'
local fonts=require('hd2runtime/runtime/ui_fonts')
mod:log('GameFontTextProof '..BUILD..' BUILD: a mod window at the top left shows seven sample lines. EVERY line should '
    ..'draw in ANY game language a second or two after it opens. Report for each game language you try (English first, '
    ..'then one or two others): which lines are readable, which still show "?", whether the lines sit on one baseline, '
    ..'and anything that looks wrong. Ctrl+F7 hides / shows it, '
    ..'Ctrl+F8 logs its state again.')

local LINES={
    {label='Latin',text='Latin: HELLDIVERS 2 - Super Earth, café façade',needs='any language (FS Sinclair)'},
    {label='Polish',text='Polski: zażółć gęślą jaźń',needs='a European language font, loaded on demand'},
    {label='Simplified Chinese',text='简体中文：模组窗口测试',needs='Simplified Chinese font, loaded on demand'},
    {label='Traditional Chinese',text='繁體中文：模組視窗測試',needs='Traditional Chinese font, loaded on demand'},
    {label='Japanese',text='日本語：モッドのウィンドウ表示テスト',needs='Japanese font, loaded on demand'},
    {label='Korean',text='한국어: 모드 창 테스트입니다',needs='Korean font, loaded on demand'},
    {label='Russian',text='Русский: окно мода, проверка шрифта',needs='Russian font, loaded on demand'},
}
local PARAGRAPH='简体中文换行测试：这一段文字没有空格，应该在任意两个汉字之间换行，而且句号和逗号不会出现在一行的开头。'

if type(hd2.ui.can_draw)~='function'then
    mod:log('this HD2Runtime has no hd2.ui.can_draw: install the game-fonts development runtime that came with this '
        ..'proof (HD2Runtime 0.30.3 game-fonts test build)')
end

-- The state of every line: which font each run uses (the same split the overlay draws) and whether the game fonts
-- are loaded now.
local function describe(reason)
    local ok,list=pcall(hd2.ui.game_fonts)
    local resident,loaded={},{}
    if ok then
        for _,f in ipairs(list)do
            if f.resident then loaded[#loaded+1]=f.key end
            resident[f.key]=f.resident and'loaded'or('not loaded: '..tostring(f.reason))
        end
    end
    mod:log(('state (%s): game fonts loaded now: %s'):format(reason,#loaded>0 and table.concat(loaded,', ')or'none'))
    if ok then
        for _,f in ipairs(list)do mod:log(('  game font %-8s %-36s %s'):format(f.key,f.label,resident[f.key]))end
    end
    local runtime_ok,extra=pcall(function()
        local out={}
        for _,f in ipairs(list or{})do
            if f.resident then
                for _,e in ipairs(fonts.GAME)do if e.key==f.key then out[#out+1]=fonts.game_font(e)end end
            end
        end
        return out
    end)
    local body=require('hd2runtime/domains/ui_fonts').fonts.body
    for _,line in ipairs(LINES)do
        local can,missing,sample=false,nil,nil
        if hd2.ui.can_draw then can,missing,sample=hd2.ui.can_draw(line.text)end
        local parts={}
        for _,run in ipairs(fonts.runs(body,line.text,runtime_ok and extra or{}))do
            parts[#parts+1]=('[%s] %s'):format(run.font.key or'FS Sinclair',run.text)
        end
        mod:log(('  %-20s can_draw=%s%s (needs %s): %s'):format(line.label,tostring(can),
            can and''or(' missing='..tostring(missing)..' e.g. '..table.concat(sample or{},' ')),line.needs,
            table.concat(parts,' | ')))
    end
end

local visible=true
local overlay=hd2.ui.overlay({id='game_font_text_proof'})
local last_key,logged_status
overlay:draw(function(d)
    local s=d.scale
    local x,y,w=40*s,120*s,760*s
    local size=26*s
    local step=38*s
    d:rect(x-16*s,y-16*s,w+32*s,(#LINES*step)+5*30*s+40*s,{12,14,18,215})
    d:rect(x-16*s,y-16*s,w+32*s,3*s,'#C8B43C',1)
    for i,line in ipairs(LINES)do
        d:text(line.text,x,y+(i-1)*step,{size=size,z=2})
    end
    local py=y+#LINES*step+10*s
    for i,l in ipairs(d:wrap(PARAGRAPH,w,{size=20*s,lines=4}))do
        d:text(l,x,py+(i-1)*30*s,{size=20*s,colour={200,200,196},z=2})
    end
    -- log when the set of loaded game fonts changes (a language switch) and once at the first drawn frame
    local key={}
    for _,line in ipairs(LINES)do key[#key+1]=tostring(d:can_draw(line.text))end
    key=table.concat(key,',')
    if key~=last_key then
        last_key=key
        logged_status=false
    end
end)
mod:on_frame(function()
    if logged_status==false and overlay:status().state=='drawing'then
        logged_status=true
        describe('the window drew; can_draw per line '..tostring(last_key))
        local st=overlay:status()
        mod:log(('  overlay: state=%s items=%s game_fonts=%s waiting_text=%s text_reason=%s refused=%s first_refusal=%s')
            :format(st.state,tostring(st.items),table.concat(st.game_fonts or{},','),tostring(st.waiting_text),
            tostring(st.text_reason),tostring(st.refused),tostring(st.first_refusal)))
    end
end)
hd2.input.bind('game_font_text_proof.toggle',{key='Ctrl+F7',on_press=function()
    visible=not visible
    if visible then overlay:show()else overlay:hide()end
    mod:log('window '..(visible and'shown'or'hidden'))
end})
hd2.input.bind('game_font_text_proof.log',{key='Ctrl+F8',on_press=function()
    describe('Ctrl+F8')
    local st=overlay:status()
    mod:log(('  overlay: state=%s reason=%s items=%s game_fonts=%s waiting_text=%s text_reason=%s opened=%s')
        :format(st.state,tostring(st.reason),tostring(st.items),table.concat(st.game_fonts or{},','),
        tostring(st.waiting_text),tostring(st.text_reason),tostring(st.opened)))
end})
mod:log('loaded ('..BUILD..'): Ctrl+F7 show / hide, Ctrl+F8 log the state')
