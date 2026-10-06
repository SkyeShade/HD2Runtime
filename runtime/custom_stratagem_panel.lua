-- The Runtime-owned CUSTOM STRATAGEMS panel (development; docs/custom-stratagems.md, "A Runtime-owned custom stratagems
-- panel"). Not exported by api/hd2.lua.
--
-- A small grid of the Runtime's virtual stratagems (runtime/virtual_stratagems.lua), drawn through
-- runtime/engine_gui.lua in an area of the loadout screen that the native UI leaves empty, ONLY while the player is
-- choosing a stratagem (a selection open for a stratagem slot; see the controller).
--
-- Two renderers: the compact renderer (0.2.0, M.compact_layout / M.draw_compact / M.draw_focus: a 3-column grid of
-- small tiles and a tooltip only while a tile is focused) is the default; the 0.1.0 renderer (M.layout / M.draw: one
-- native-sized card and a permanent description area, live-tested) is kept unchanged as the legacy renderer and the
-- fallback when the compact layout is refused. Both obey the same lifecycle. The native picker is never touched or drawn over: the game draws its UI after every Runtime GUI, so the panel
-- can only appear where nothing native is. The vanilla loadout record is the bridge between the two pickers: a selection
-- (phase 2) is the existing guarded token write of runtime/stratagem_selector.lua into the slot being edited.
--
-- Layout (M.layout, the legacy renderer): everything is in native units (the stratagem card is 80 units, its inner frame 68, its icon 51,
-- the grid pitch 85) times the pixels per unit: the native card's own scale while the grid is open, else height / 1080.
-- The panel stays inside the box where Runtime GUI was proven visible while the grid is open (the 0.3.0 card: x 0.67 W,
-- top 0.16 H below the screen top, 0.29 W x 0.15 H); when it does not fit, the unit shrinks (compact). Three columns,
-- empty cells undrawn, as many rows as fit (one in that box), later rows by scrolling.
--
-- The tile: no vanilla image draws the native card's background, border or inner frame (they are sized elements with
-- no resource); the only image on the card is its focus bracket, a sprite on a single-channel UI atlas page that no
-- GUI material the Lua API can name samples. So the tile is drawn with rectangles in the native proportions: an opaque
-- dark square, a thin light border, an inner frame at 68/80, the icon at 51/80, and when focused four corner brackets
-- measured from that sprite (arms 15/80, 3/80 thick, on the card's edges).
--
-- 0.7.0: the icon is drawn with the live-proven slot overlay technique (runtime/stratagem_slot_overlay.lua, SlotOverlayProof
-- 0.1.0): every panel GUI is a screen GUI of the Ui World (M.WORLD; 'main' keeps Application.main_world, the 0.1-0.6
-- path, as a documented fallback that is not used by default), the icon a bitmap of the image's GUI material on an
-- opaque plate of the native icon background's grey on exactly the icon's quad (overlay.draw_icon), its shader colours
-- the token's colour set on this GUI's own material instance (overlay.colour), the same as over a virtual loadout slot.
-- The panel's layers sit in the overlay's band (LAYER: above the native slot parts, below the HUD's 950 and the native
-- 991-1018). The panel also starts the virtual slots' overlays (opts.slot_overlays, default on).
local engine_gui=require('hd2runtime/runtime/engine_gui')
local images=require('hd2runtime/runtime/image_resources')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local selector=require('hd2runtime/runtime/stratagem_selector')
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local input=require('hd2runtime/runtime/input')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local slot_focus=require('hd2runtime/runtime/stratagem_slot_focus')
local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
local D=require('hd2runtime/domains/stratagem_selector')
local CARD=D.grid.card
local GAP=D.grid.scroll.gap
local M={}

local function log(text)log_module.emit('[HD2Runtime] custom stratagem panel '..text)end
-- Where Runtime GUI was proven visible while the stratagem grid is open (screen fractions; top from the screen top).
M.SAFE={x=0.67,top=0.16,w=0.29,h=0.15}
M.COLUMNS=3
M.TITLE='CUSTOM STRATAGEMS'
-- Native units.
local PAD,HEADER,HEADER_GAP,TITLE_SIZE,NAME_SIZE,TEXT_SIZE=8,18,6,13,12,9
local MIN_DESCRIPTION=110        -- units the description area needs beside the grid
local BRACKET_ARM,BRACKET_THICK=15,3
local COLOURS={panel={205,10,12,14},panelEdge={255,64,68,72},title={255,232,232,226},tile={255,18,20,22},
    tileEdge={255,116,120,124},inner={255,50,53,57},icon={255,255,255,255},name={255,240,240,232},
    text={255,200,200,196},bracket={255,236,236,232},
    -- An unavailable entry (an expendable custom stratagem without a free carrier weapon): dimmed, a warning mark.
    unavailableShade={170,6,6,8},warning={255,236,74,48}}
M.COLOURS=COLOURS
-- The world the panel's GUIs are opened in: 'ui' (the Ui World, the proven icon technique; default) or 'main'
-- (Application.main_world, the 0.1-0.6 path: under the whole UI composite, where the icon looked darker; a documented
-- fallback only). Set by M.panel (opts.world).
M.WORLD='ui'
local function open_screen()
    if M.WORLD=='main'then return engine_gui.open()end
    local world,why=world_module.open()
    if not world then return nil,'no game world: '..tostring(why)end
    return overlay.open_gui(world)
end
M.open_screen=open_screen
-- The compact panel's, focus overlay's and icon diagnostics' layers: the 0.2-0.6 layers (10-22) moved up by BASE, into
-- the overlay's band of the Ui World (above every native slot part, below the HUD's 950-953 and the native 991-1018).
local BASE=920
M.LAYER_BASE=BASE

-- The layout for a width x height GUI. opts: unit (pixels per native unit; default height / 1080), count (entries),
-- scroll (the first visible row), protected ({rects} the panel must not meet, e.g. the native list frame). Returns
-- {box, panel, unit, card, pitch, title = {x, y, size}, grid = {x, top, columns, rows (visible), totalRows},
-- tiles = {[index] = {rect, column, row, visible}}, description = rect, sizes = {name, text}} or nil and the reason.
-- Rectangles are {x, y, w, h} in pixels from the bottom-left corner.
function M.layout(width,height,opts)
    opts=opts or{}
    if type(width)~='number'or type(height)~='number'or width<640 or height<360 then return nil,'unsupported resolution'end
    local count=opts.count or 1
    if count<0 or count%1~=0 or count>60 then return nil,'unsupported entry count'end
    local box={x=math.floor(width*M.SAFE.x),w=math.floor(width*M.SAFE.w),h=math.floor(height*M.SAFE.h)}
    box.y=math.floor(height*(1-M.SAFE.top))-box.h
    local u=opts.unit or height/1080
    if type(u)~='number'or u~=u or u<=0 then return nil,'invalid unit'end
    local grid_w=M.COLUMNS*CARD.size+(M.COLUMNS-1)*GAP
    local need_w=PAD+grid_w+PAD+MIN_DESCRIPTION+PAD
    local need_h=PAD+HEADER+HEADER_GAP+CARD.size+PAD
    local compact=math.min(1,box.w/(need_w*u),box.h/(need_h*u))
    u=u*compact
    local out={box=box,unit=u,compact=compact<1,card=CARD.size*u,pitch=(CARD.size+GAP)*u}
    local rows=math.max(1,math.floor((box.h/u-(PAD+HEADER+HEADER_GAP+PAD)+GAP)/(CARD.size+GAP)))
    local total=math.max(1,math.ceil(count/M.COLUMNS))
    rows=math.min(rows,total)
    local panel_h=(PAD+HEADER+HEADER_GAP+rows*CARD.size+(rows-1)*GAP+PAD)*u
    local top=box.y+box.h
    out.panel={x=box.x,y=top-panel_h,w=box.w,h=panel_h}
    out.title={x=box.x+PAD*u,y=top-(PAD+HEADER*0.8)*u,size=TITLE_SIZE*u}
    local scroll=math.max(0,math.min(opts.scroll or 0,total-rows))
    out.grid={x=box.x+PAD*u,top=top-(PAD+HEADER+HEADER_GAP)*u,columns=M.COLUMNS,rows=rows,totalRows=total,scroll=scroll,
        w=grid_w*u}
    out.tiles={}
    for index=1,count do
        local column,row=(index-1)%M.COLUMNS,math.floor((index-1)/M.COLUMNS)-scroll
        local rect={x=out.grid.x+column*out.pitch,y=out.grid.top-row*out.pitch-out.card,w=out.card,h=out.card}
        out.tiles[index]={rect=rect,column=column,row=row+scroll,visible=row>=0 and row<rows}
    end
    local dx=out.grid.x+out.grid.w+PAD*u
    out.description={x=dx,y=out.grid.top-out.card,w=box.x+box.w-PAD*u-dx,h=out.card}
    out.sizes={name=NAME_SIZE*u,text=TEXT_SIZE*u}
    -- Checks: inside the screen and the safe box, and clear of every protected rectangle.
    local function inside(a,b)return a.x>=b.x-0.5 and a.y>=b.y-0.5 and a.x+a.w<=b.x+b.w+0.5 and a.y+a.h<=b.y+b.h+0.5 end
    local function meets(a,b)return a.x<b.x+b.w and b.x<a.x+a.w and a.y<b.y+b.h and b.y<a.y+a.h end
    if not inside(out.panel,{x=0,y=0,w=width,h=height})or not inside(out.panel,box)then
        return nil,'the panel does not fit the safe area'
    end
    if out.description.w<MIN_DESCRIPTION*u-0.5 then return nil,'no room for the description'end
    for _,rect in ipairs(opts.protected or{})do
        if meets(out.panel,rect)then return nil,'the panel would meet protected native UI'end
    end
    return out
end

-- Splits text into at most `lines` lines of at most `chars` characters at spaces; the last is cut with '...'.
function M.wrap(text,chars,lines)
    local out,line={},''
    for word in tostring(text):gmatch('%S+')do
        local candidate=line==''and word or(line..' '..word)
        if #candidate<=chars then line=candidate
        else
            out[#out+1]=line
            line=word
        end
    end
    if line~=''then out[#out+1]=line end
    for k=1,#out do if #out[k]>chars then out[k]=out[k]:sub(1,math.max(1,chars-3))..'...'end end
    if #out>lines then
        out[lines]=(out[lines]:sub(1,math.max(1,chars-3)))..'...'
        for k=#out,lines+1,-1 do out[k]=nil end
    end
    return out
end

-- Draws the panel once (retained): the panel, its title, each visible entry's tile, icon and name, and for the focused
-- entry its brackets and description. entries: {{id, name, description, icon (Runtime image)}}; state: {focus (index
-- or nil), variants ({[index] = Runtime image}, an icon shown instead)}. Returns the screen (close()) or nil and the
-- reason; nothing is left open on failure. Writes nothing.
function M.draw(runtime,layout,entries,state)
    state=state or{}
    local font=D.font.name
    -- A residency lookup that raises (the type absent, the manager busy) counts as not loaded.
    local function loaded(type_hex)
        local ok,result,reason=pcall(images.loaded,runtime,type_hex,font)
        if not ok then return false,tostring(result)end
        return result,reason
    end
    local ok_font,why=loaded(D.font.type)
    local ok_material=loaded(D.font.materialType)
    if not(ok_font and ok_material)then return nil,'the engine font is not loaded: '..tostring(why)end
    for index,entry in ipairs(entries)do
        local icon=state.variants and state.variants[index]or entry.icon
        if icon then
            local family=images.family(runtime,icon)
            if not family.complete then return nil,'an icon is not loaded: '..tostring(family.reason)end
        end
    end
    local screen,open_why=open_screen()
    if not screen then return nil,open_why end
    local u=layout.unit
    local px=function(n)return math.max(1,math.floor(n*u+0.5))end
    local ok,err=pcall(function()
        local function need(value,what)if value==nil then error(what..' was refused: '..tostring(screen.reason),0)end end
        local function rect(r,layer,colour,what)need(screen.rect(r.x,r.y,layer,r.w,r.h,colour),what)end
        local function frame(r,t,layer,colour,what)
            rect({x=r.x,y=r.y,w=r.w,h=t},layer,colour,what);rect({x=r.x,y=r.y+r.h-t,w=r.w,h=t},layer,colour,what)
            rect({x=r.x,y=r.y,w=t,h=r.h},layer,colour,what);rect({x=r.x+r.w-t,y=r.y,w=t,h=r.h},layer,colour,what)
        end
        local P=layout.panel
        rect(P,10,COLOURS.panel,'the panel')
        frame(P,px(1),11,COLOURS.panelEdge,'the panel edge')
        need(screen.text(M.TITLE,font,layout.title.size,font,layout.title.x,layout.title.y,17,COLOURS.title),'the title')
        for index,entry in ipairs(entries)do
            local tile=layout.tiles[index]
            if tile and tile.visible then
                local r=tile.rect
                rect(r,12,COLOURS.tile,'a tile')
                frame(r,px(1.5),13,COLOURS.tileEdge,'a tile edge')
                local inset=(CARD.size-CARD.inner)/2*u
                frame({x=r.x+inset,y=r.y+inset,w=r.w-2*inset,h=r.h-2*inset},px(1),14,COLOURS.inner,'a tile frame')
                local icon=CARD.icon*u
                local image=state.variants and state.variants[index]or entry.icon
                if image then
                    need(screen.bitmap(images.material_name(image),r.x+(r.w-icon)/2,r.y+(r.h-icon)/2,15,icon,icon,
                        COLOURS.icon),'an icon')
                end
                if state.focus==index then
                    local arm,t=BRACKET_ARM*u,px(BRACKET_THICK)
                    for _,c in ipairs({{r.x,r.y,1,1},{r.x+r.w,r.y,-1,1},{r.x,r.y+r.h,1,-1},{r.x+r.w,r.y+r.h,-1,-1}})do
                        local x,y,sx,sy=c[1],c[2],c[3],c[4]
                        rect({x=sx>0 and x or x-arm,y=sy>0 and y or y-t,w=arm,h=t},16,COLOURS.bracket,'a focus bracket')
                        rect({x=sx>0 and x or x-t,y=sy>0 and y or y-arm,w=t,h=arm},16,COLOURS.bracket,'a focus bracket')
                    end
                end
            end
        end
        -- The description area: the focused entry's name and description; unfocused, the first entry's name only.
        local A=layout.description
        local shown=entries[state.focus or 1]
        if shown then
            local chars=math.max(4,math.floor(A.w/(layout.sizes.name*0.62)))
            local name=M.wrap(shown.name,chars,1)[1]
            need(screen.text(name,font,layout.sizes.name,font,A.x,A.y+A.h-layout.sizes.name*1.2,17,COLOURS.name),
                'the name')
            if state.focus then
                local text_chars=math.max(4,math.floor(A.w/(layout.sizes.text*0.62)))
                for k,line in ipairs(M.wrap(shown.description,text_chars,3))do
                    need(screen.text(line,font,layout.sizes.text,font,A.x,
                        A.y+A.h-layout.sizes.name*1.2-k*layout.sizes.text*1.45,17,COLOURS.text),'the description')
                end
            end
        end
    end)
    if not ok then screen.close();return nil,tostring(err)end
    return screen
end

-- The entries: every virtual stratagem, in definition order.
function M.entries()
    local out={}
    for _,definition in ipairs(virtual.list())do
        local name,description=virtual.strings(definition,'us')
        out[#out+1]={id=definition.id,name=name,description=description,icon=definition.display.icon}
    end
    return out
end

local function rect_text(r)return('%.0f, %.0f, %.0f x %.0f'):format(r.x,r.y,r.w,r.h)end
-- c0-c3 as text for the logs.
local function colours_text(vars)
    local parts={}
    for _,v in ipairs(vars or{})do parts[#parts+1]=('%s (%.3f, %.3f, %.3f, %.3f)'):format(v[1],v[2],v[3],v[4],v[5])end
    return table.concat(parts,', ')
end
M.colours_text=colours_text
local function inside(a,b)return a.x>=b.x-0.5 and a.y>=b.y-0.5 and a.x+a.w<=b.x+b.w+0.5 and a.y+a.h<=b.y+b.h+0.5 end
local function meets(a,b)return a.x<b.x+b.w and b.x<a.x+a.w and a.y<b.y+b.h and b.y<a.y+a.h end
-- A residency lookup that raises (the type absent, the manager busy) counts as not loaded.
local function font_ready(runtime)
    for _,kind in ipairs({D.font.type,D.font.materialType})do
        local ok,result,why=pcall(images.loaded,runtime,kind,D.font.name)
        if not ok then return nil,'the engine font is not loaded: '..tostring(result)end
        if not result then return nil,'the engine font is not loaded: '..tostring(why)end
    end
    return true
end

-- Placeholder entries (purely visual; never selectable): Placeholder Custom Stratagem 2..n+1.
function M.placeholders(count)
    local out={}
    for k=1,count or 0 do
        out[k]={id='placeholder_'..(k+1),name='Placeholder Custom Stratagem '..(k+1),
            description='Visual placeholder: no stratagem yet.',placeholder=true}
    end
    return out
end

------------------------------------------------------------------------------------------------ the compact panel --
-- 0.2.0: a compact grid, no permanent description area. In native units times the pixels per unit (as above): the
-- title, then a three-column grid of tiles; the panel wraps only the title and the grid. A small tooltip (the focused
-- entry's name and description) appears to the right of the panel, beside the focused tile's row, only while a tile is
-- focused; the opt-in icon test uses the same side. The panel and that side together (the footprint) stay inside the
-- safe box and clear of protected native UI; when they do not fit, the unit shrinks.
-- The tiles (and their icons, drawn in the native proportions of the tile) are 75 units at an 80-unit pitch (150 px at
-- 4K, 15/16 of the native card), a quarter larger than 0.2.0's 60 at 64; the anchored panel (M.anchored_layout) uses
-- them. The 0.2.0 box layout (M.compact_layout; no longer drawn) keeps its 60-unit tiles.
M.COMPACT={tile=75,gap=5,pad=8,title=16,titleGap=6,titleSize=11,tooltip={w=172,pad=6,gap=6,name=10,text=8,lines=3},
    iconTest={sizes={118.8,80,51,38.25},gap=6,label=8}}
local CP=M.COMPACT
local BOX=setmetatable({tile=60,gap=4},{__index=M.COMPACT})
-- Returns {box, unit, compact, panel, footprint, title, tile, pitch, grid, tiles, side (the area right of the panel)} or
-- nil and the reason. opts: unit, count, scroll, protected (as M.layout).
function M.compact_layout(width,height,opts)
    opts=opts or{}
    if type(width)~='number'or type(height)~='number'or width<640 or height<360 then return nil,'unsupported resolution'end
    local count=opts.count or 1
    if count<1 or count%1~=0 or count>60 then return nil,'unsupported entry count'end
    local box={x=math.floor(width*M.SAFE.x),w=math.floor(width*M.SAFE.w),h=math.floor(height*M.SAFE.h)}
    box.y=math.floor(height*(1-M.SAFE.top))-box.h
    local u=opts.unit or height/1080
    if type(u)~='number'or u~=u or u<=0 then return nil,'invalid unit'end
    local grid_w=M.COLUMNS*BOX.tile+(M.COLUMNS-1)*BOX.gap
    local panel_w=BOX.pad+grid_w+BOX.pad
    local head=BOX.pad+BOX.title+BOX.titleGap
    local total=math.ceil(count/M.COLUMNS)
    -- At most two rows in view now (six entries); more rows wait for scrolling.
    local want_rows=math.min(total,2)
    local need_w=panel_w+BOX.tooltip.gap+BOX.tooltip.w
    local need_h=head+want_rows*BOX.tile+(want_rows-1)*BOX.gap+BOX.pad
    local factor=math.min(1,box.w/(need_w*u),box.h/(need_h*u))
    u=u*factor
    local rows=math.max(1,math.min(want_rows,math.floor((box.h/u-head-BOX.pad+BOX.gap)/(BOX.tile+BOX.gap)+1e-9)))
    local scroll=math.max(0,math.min(opts.scroll or 0,total-rows))
    local panel_h=(head+rows*BOX.tile+(rows-1)*BOX.gap+BOX.pad)*u
    local top=box.y+box.h
    local out={box=box,unit=u,compact=factor<1,tile=BOX.tile*u,pitch=(BOX.tile+BOX.gap)*u}
    out.panel={x=box.x,y=top-panel_h,w=panel_w*u,h=panel_h}
    out.title={x=box.x+BOX.pad*u,y=top-(BOX.pad+BOX.title*0.8)*u,size=BOX.titleSize*u}
    out.grid={x=box.x+BOX.pad*u,top=top-head*u,columns=M.COLUMNS,rows=rows,totalRows=total,scroll=scroll,w=grid_w*u}
    out.tiles={}
    for index=1,count do
        local column,row=(index-1)%M.COLUMNS,math.floor((index-1)/M.COLUMNS)-scroll
        out.tiles[index]={rect={x=out.grid.x+column*out.pitch,y=out.grid.top-row*out.pitch-out.tile,w=out.tile,h=out.tile},
            column=column,row=row+scroll,visible=row>=0 and row<rows}
    end
    local side_x=out.panel.x+out.panel.w+BOX.tooltip.gap*u
    out.side={x=side_x,y=out.panel.y,w=box.x+box.w-side_x,h=panel_h}
    out.tooltipMode,out.tooltipArea='right',out.side
    out.footprint={x=out.panel.x,y=out.panel.y,w=need_w*u,h=panel_h}
    if not inside(out.footprint,{x=0,y=0,w=width,h=height})or not inside(out.footprint,box)then
        return nil,'the compact panel does not fit the safe area'
    end
    for _,rect in ipairs(opts.protected or{})do
        if meets(out.footprint,rect)then return nil,'the compact panel would meet protected native UI'end
    end
    return out
end

-- The tooltip rectangle for a focused tile: right of the panel, its top level with the tile's top, kept inside the
-- side area. Its height follows its lines (up to two name lines and up to three description lines).
function M.tooltip_rect(layout,index,lines,name_lines)
    local tile=layout.tiles[index]
    if not(tile and tile.visible)then return nil end
    local u,T=layout.unit,CP.tooltip
    local h=(T.pad*2+(name_lines or 1)*T.name*1.3+(lines or 1)*T.text*1.45)*u
    local w=T.w*u
    local A=layout.tooltipArea or layout.side
    if layout.tooltipMode=='none'then return nil end
    if layout.tooltipMode=='below'then
        -- Under the panel, its top just below the panel's bottom edge.
        h=math.min(h,A.h)
        return {x=A.x,y=A.y+A.h-h,w=math.min(w,A.w),h=h}
    end
    local top=math.min(tile.rect.y+tile.rect.h,A.y+A.h)
    local y=math.max(A.y,top-h)
    return {x=A.x,y=y,w=w,h=math.min(h,A.h)}
end

local function frame_rects(screen,r,t,layer,colour,what)
    for _,b in ipairs({{r.x,r.y,r.w,t},{r.x,r.y+r.h-t,r.w,t},{r.x,r.y,t,r.h},{r.x+r.w-t,r.y,t,r.h}})do
        if screen.rect(b[1],b[2],layer,b[3],b[4],colour)==nil then error(what..' was refused: '..tostring(screen.reason),0)end
    end
end

-- The compact panel (retained): its background and edge, the title and each visible entry's tile: dark square, outer
-- border, inner frame at 68/80 of the tile, and the icon at 51/80, centred; a placeholder shows a dim '?'. report(line),
-- when given, receives each icon draw: attempted, then succeeded (with the engine's id) or failed. Returns the screen or
-- nil and the reason (nothing left open).
function M.draw_compact(runtime,layout,entries,report)
    local ready,why=font_ready(runtime)
    if not ready then return nil,why end
    -- An icon that is not loaded does not stop the panel: its tile gets the placeholder mark (logged).
    local unavailable={}
    for index,entry in ipairs(entries)do
        if entry.icon then
            local done,family=pcall(images.family,runtime,entry.icon)
            if not(done and family.complete)then
                unavailable[index]=done and tostring(family.reason)or tostring(family)
                if report then report(('custom icon unavailable for %s (%s): drawing the placeholder mark'):format(entry.id,
                    unavailable[index]))end
            end
        end
    end
    local screen,open_why=open_screen()
    if not screen then return nil,open_why end
    local u,font=layout.unit,D.font.name
    local px=function(n)return math.max(1,math.floor(n*u+0.5))end
    local coloured={}
    local ok,err=pcall(function()
        local function need(v,what)if v==nil then error(what..' was refused: '..tostring(screen.reason),0)end end
        local P=layout.panel
        need(screen.rect(P.x,P.y,BASE+10,P.w,P.h,COLOURS.panel),'the panel')
        frame_rects(screen,P,px(1),BASE+11,COLOURS.panelEdge,'the panel edge')
        need(screen.text(M.TITLE,font,layout.title.size,font,layout.title.x,layout.title.y,BASE+17,COLOURS.title),
            'the title')
        for index,entry in ipairs(entries)do
            local tile=layout.tiles[index]
            if tile and tile.visible then
                local r=tile.rect
                need(screen.rect(r.x,r.y,BASE+12,r.w,r.h,COLOURS.tile),'a tile')
                frame_rects(screen,r,px(1),BASE+13,COLOURS.tileEdge,'a tile edge')
                local inset=(CARD.size-CARD.inner)/2/CARD.size*r.w
                frame_rects(screen,{x=r.x+inset,y=r.y+inset,w=r.w-2*inset,h=r.h-2*inset},px(0.75),BASE+14,COLOURS.inner,
                    'a tile frame')
                local drawn_icon=false
                if entry.icon and not unavailable[index]then
                    local icon=CARD.icon/CARD.size*r.w
                    local material=images.material_name(entry.icon)
                    local spec={material=material,x=r.x+(r.w-icon)/2,y=r.y+(r.h-icon)/2,w=icon,h=icon,layer=BASE+16,
                        alpha=1,plate=overlay.PLATE}
                    if report then
                        report(('custom icon GUI bitmap draw attempted: Gui.bitmap("%s", %.0f, %.0f, %.0f x %.0f, layer %d)'
                            ..' for %s, on the native icon background\'s plate (%d, %d, %d) at layer %d'):format(material,
                            spec.x,spec.y,icon,icon,spec.layer,entry.id,spec.plate[1],spec.plate[2],spec.plate[3],
                            spec.layer-1))
                    end
                    -- The slot overlay's technique: the icon, then its opaque plate on the same quad. Optional: a refused
                    -- icon leaves the tile and the GUI standing.
                    local ids,why=overlay.draw_icon(screen,spec)
                    if report then
                        report(ids~=nil and('custom icon GUI bitmap draw succeeded for %s (engine id %s; plate %s)'):format(
                            entry.id,tostring(ids.icon),ids.plate~=nil and'drawn'or('NOT drawn: '..tostring(ids.plateWhy)))
                            or('custom icon GUI bitmap draw failed for %s: %s; drawing the placeholder mark'):format(
                            entry.id,tostring(why)))
                    end
                    drawn_icon=ids~=nil
                    -- The icon shader colours the texture's R, G and B as masks with c0-c2, zero unless set (nothing
                    -- would show): set on this GUI's own instance of the material, as the native loadout slot sets them
                    -- and as the slot overlay sets them (one instance per material in a GUI: set once).
                    if ids~=nil and coloured[material]==nil then
                        coloured[material]=true
                        if entry.colours then
                            local set,set_why=overlay.colour(screen,material,entry.colours)
                            if report then
                                report(set and('custom icon colours set for %s on this GUI\'s material instance (the '
                                    ..'native loadout slot\'s values, colour set %s): %s'):format(entry.id,
                                    tostring(entry.colourSet),colours_text(entry.colours))or('custom icon colours NOT set '
                                    ..'for %s: %s (the icon stays transparent)'):format(entry.id,tostring(set_why)))
                            end
                        elseif report then
                            report(('custom icon colours unavailable for %s: %s (the icon stays transparent)')
                                :format(entry.id,tostring(entry.coloursWhy)))
                        end
                    end
                end
                if not drawn_icon then
                    local size=math.max(4,r.h*0.4)
                    need(screen.text('?',font,size,font,r.x+r.w/2-size*0.3,r.y+r.h/2-size*0.35,BASE+16,COLOURS.inner),
                        'a placeholder mark')
                end
                if entry.unavailable then
                    -- Unavailable: the tile is dimmed and carries a warning mark; its tooltip says why.
                    need(screen.rect(r.x,r.y,BASE+17,r.w,r.h,COLOURS.unavailableShade),'an unavailable shade')
                    local size=math.max(4,r.h*0.45)
                    need(screen.text('!',font,size,font,r.x+r.w/2-size*0.15,r.y+r.h/2-size*0.35,BASE+18,COLOURS.warning),
                        'an unavailable mark')
                    if report then report(('%s is UNAVAILABLE: its tile is dimmed and marked'):format(entry.id))end
                end
            end
        end
    end)
    if not ok then screen.close();return nil,tostring(err)end
    return screen
end

-- The focus overlay (retained, its own GUI): four corner brackets on the focused tile and the tooltip beside it.
function M.draw_focus(runtime,layout,entry,index)
    local ready,why=font_ready(runtime)
    if not ready then return nil,why end
    local tile=layout.tiles[index]
    if not(tile and tile.visible)then return nil,'the focused tile is not visible'end
    local u,font,T=layout.unit,D.font.name,CP.tooltip
    local inner=(T.w-2*T.pad)*u
    local lines=M.wrap(entry.unavailable and(tostring(entry.unavailable)..' It cannot be picked now.')or entry.description,
        math.max(4,math.floor(inner/(T.text*u*0.62))),T.lines)
    local names=M.wrap(entry.name,math.max(4,math.floor(inner/(T.name*u*0.62))),2)
    local tip=M.tooltip_rect(layout,index,#lines,#names)
    local screen,open_why=open_screen()
    if not screen then return nil,open_why end
    local ok,err=pcall(function()
        local function need(v,what)if v==nil then error(what..' was refused: '..tostring(screen.reason),0)end end
        local r=tile.rect
        local arm,t=BRACKET_ARM/CARD.size*r.w,math.max(1,math.floor(BRACKET_THICK/CARD.size*r.w+0.5))
        for _,c in ipairs({{r.x,r.y,1,1},{r.x+r.w,r.y,-1,1},{r.x,r.y+r.h,1,-1},{r.x+r.w,r.y+r.h,-1,-1}})do
            local x,y,sx,sy=c[1],c[2],c[3],c[4]
            need(screen.rect(sx>0 and x or x-arm,sy>0 and y or y-t,BASE+18,arm,t,COLOURS.bracket),'a focus bracket')
            need(screen.rect(sx>0 and x or x-t,sy>0 and y or y-arm,BASE+18,t,arm,COLOURS.bracket),'a focus bracket')
        end
        need(screen.rect(tip.x,tip.y,BASE+10,tip.w,tip.h,COLOURS.panel),'the tooltip')
        frame_rects(screen,tip,math.max(1,math.floor(u+0.5)),BASE+11,COLOURS.panelEdge,'the tooltip edge')
        local x,y=tip.x+T.pad*u,tip.y+tip.h-(T.pad+T.name)*u
        for k,name in ipairs(names)do
            if k>1 then y=y-T.name*1.3*u end
            need(screen.text(name,font,T.name*u,font,x,y,BASE+17,COLOURS.name),'the tooltip name')
        end
        for k,line in ipairs(lines)do
            need(screen.text(line,font,T.text*u,font,x,y-k*T.text*1.45*u,BASE+17,COLOURS.text),'the tooltip text')
        end
    end)
    if not ok then screen.close();return nil,tostring(err)end
    return screen,tip,lines
end

-------------------------------------------------------------------------------------------- the anchored placement --
-- 0.3.0: the compact panel to the RIGHT of the native details panel (stratagem_selector.details), never meeting it.
-- A column runs from the details panel's right edge plus a margin to the screen's right edge minus the same margin, in
-- the details panel's own vertical band (clear of the screen's top bar and the bottom controls). The panel takes the
-- column's top-left corner; the tooltip goes to its right when the column is wide enough, else below it; the icon
-- diagnostics use the area below the panel. Three columns are kept: the tiles shrink first, and a column is dropped
-- only when a tile would fall below minTile pixels per 1080 lines.
M.ANCHOR={margin=15,minTile=36}
-- opts: details (the details panel's screen rect, required), unit (pixels per native unit; default height / 1080),
-- count, scroll, protected. Returns the layout (as M.compact_layout, plus column, details, tooltipMode, tooltipArea,
-- diagArea, columnsDropped) or nil and the reason.
function M.anchored_layout(width,height,opts)
    opts=opts or{}
    if type(width)~='number'or type(height)~='number'or width<640 or height<360 then return nil,'unsupported resolution'end
    local count=opts.count or 1
    if count<1 or count%1~=0 or count>60 then return nil,'unsupported entry count'end
    local d=opts.details
    if not(type(d)=='table'and type(d.w)=='number'and d.w>0 and type(d.h)=='number'and d.h>0)then
        return nil,'the native details panel is unknown'
    end
    local base=opts.unit or height/1080
    if type(base)~='number'or base~=base or base<=0 then return nil,'invalid unit'end
    local margin=M.ANCHOR.margin*base
    local col={x=d.x+d.w+margin,y=math.max(0,d.y)}
    col.w=width-margin-col.x
    col.h=math.min(height,d.y+d.h)-col.y
    if col.w<=0 or col.h<=0 then return nil,'no room right of the native details panel'end
    local head=CP.pad+CP.title+CP.titleGap
    for columns=M.COLUMNS,1,-1 do
        local grid_w=columns*CP.tile+(columns-1)*CP.gap
        local panel_w=CP.pad+grid_w+CP.pad
        local total=math.ceil(count/columns)
        local want=math.min(total,2)
        local need_h=head+want*CP.tile+(want-1)*CP.gap+CP.pad
        local u=math.min(base,col.w/panel_w,col.h/need_h)
        if u*CP.tile>=M.ANCHOR.minTile*height/1080 or columns==1 then
            if u*CP.tile<M.ANCHOR.minTile*height/1080 then return nil,'no room for even one column of tiles'end
            local rows=math.max(1,math.min(want,math.floor((col.h/u-head-CP.pad+CP.gap)/(CP.tile+CP.gap)+1e-9)))
            local scroll=math.max(0,math.min(opts.scroll or 0,total-rows))
            local panel_h=(head+rows*CP.tile+(rows-1)*CP.gap+CP.pad)*u
            local top=col.y+col.h
            local out={unit=u,compact=u<base-1e-9,tile=CP.tile*u,pitch=(CP.tile+CP.gap)*u,column=col,box=col,details=d,
                columnsDropped=M.COLUMNS-columns}
            out.panel={x=col.x,y=top-panel_h,w=panel_w*u,h=panel_h}
            out.title={x=col.x+CP.pad*u,y=top-(CP.pad+CP.title*0.8)*u,size=CP.titleSize*u}
            out.grid={x=col.x+CP.pad*u,top=top-head*u,columns=columns,rows=rows,totalRows=total,scroll=scroll,w=grid_w*u}
            out.tiles={}
            for index=1,count do
                local column,row=(index-1)%columns,math.floor((index-1)/columns)-scroll
                out.tiles[index]={rect={x=out.grid.x+column*out.pitch,y=out.grid.top-row*out.pitch-out.tile,w=out.tile,
                    h=out.tile},column=column,row=row+scroll,visible=row>=0 and row<rows}
            end
            local gap=CP.tooltip.gap*u
            local right_x=out.panel.x+out.panel.w+gap
            local below={x=col.x,y=col.y,w=col.w,h=out.panel.y-gap-col.y}
            if col.x+col.w-right_x>=CP.tooltip.w*u then
                out.tooltipMode,out.tooltipArea='right',{x=right_x,y=out.panel.y,w=col.x+col.w-right_x,h=panel_h}
            elseif below.h>=(CP.tooltip.pad*2+CP.tooltip.name*1.3+CP.tooltip.text*1.45)*u then
                out.tooltipMode,out.tooltipArea='below',below
            else
                out.tooltipMode,out.tooltipArea='none',{x=col.x,y=col.y,w=0,h=0}
            end
            out.side=out.tooltipArea
            out.diagArea=below
            out.footprint={x=col.x,y=math.min(out.panel.y,out.tooltipMode=='below'and below.y or out.panel.y),
                w=math.max(out.panel.w,out.tooltipMode=='right'and(out.tooltipArea.x+out.tooltipArea.w-col.x)or
                    math.min(col.w,CP.tooltip.w*u)),h=0}
            out.footprint.h=top-out.footprint.y
            if not inside(out.footprint,{x=0,y=0,w=width,h=height})or not inside(out.footprint,col)then
                return nil,'the compact panel does not fit right of the native details panel'
            end
            local protected={d}
            for _,rect in ipairs(opts.protected or{})do protected[#protected+1]=rect end
            for _,rect in ipairs(protected)do
                for _,area in ipairs({out.panel,out.tooltipArea,out.footprint})do
                    if area.w>0 and area.h>0 and meets(area,rect)then
                        return nil,'the compact panel would meet protected native UI'
                    end
                end
            end
            return out
        end
    end
    return nil,'no room for the grid'
end

-- The icon diagnostics (development; opt-in), in the area below the panel. Each cell is drawn over a split background
-- (left dark, right light), so a black result and an invisible one can be told apart. The icon material's shader colours
-- the texture's R, G and B as masks with the variables c0-c2, which are zero unless set (research iconShader), so the
-- same materials are drawn twice:
--   Row 1, COLOURED (one GUI; the native loadout slot's c0-c3 set on this GUI's instance of each icon material):
--     A font:    the engine font material by name (it draws the panel's text; its own shader, nothing set);
--     A vanilla: the vanilla 120mm icon material by hash (IdString64), the same template as a Runtime image's material;
--     B name:    the custom image's GUI material by name (the panel's own path);
--     B hash:    the same material by hash;
--     E pattern: a second Runtime image, the VirtualSelectorProof 0.3.0 test pattern (pure red and green), when given;
--     C texture: the custom image's texture: not drawable (Gui.bitmap takes a material resource), logged and left empty;
--   Row 2, PLAIN (a second GUI, nothing set): A vanilla, B name and E pattern again: expected invisible;
--   Row 3, D: the custom material, coloured, at 38.25, 51, 80 and 118.8 units, scaled down together to fit.
-- A material is drawn only when resident. Every cell logs its resource, whether its material and texture are loaded, the
-- material's shader, its texture slot, Gui.bitmap's result and the colours set. report(line) receives the lines.
-- opts: colours (the c0-c3 set to use, from stratagem_selector.icon_colours), pattern (a Runtime image) and patternLabel
-- (its cells' label, default 'E pattern'). Returns a
-- screen-like {close()} and the results, or nil and the reason.
M.VANILLA_ICON={label='vanilla 120mm icon material',high=0x9C9B3DCE,low=0x316F1256}
M.ICON_SIZES={38.25,51,80,118.8}
function M.draw_icon_diagnostics(runtime,layout,custom,report,opts)
    report=report or function()end
    opts=opts or{}
    local ready,why=font_ready(runtime)
    if not ready then return nil,why end
    local A=layout.diagArea
    if not A or A.w<=0 or A.h<=0 then return nil,'no room for the icon diagnostics'end
    local u,font=layout.unit,D.font.name
    local pad,gap,label=8*u,6*u,8*u
    local cell=math.min(60*u,(A.w-2*pad-5*gap)/6)
    local row_h=label*1.5+cell+label*0.6
    local rows=pad+label*1.5+2*row_h
    if cell<12 or A.h<rows+pad then return nil,'no room for the icon diagnostics'end
    local sizes_sum=0
    for _,size in ipairs(M.ICON_SIZES)do sizes_sum=sizes_sum+size end
    local fit=math.max(0.1,math.min(1,(A.w-2*pad-(#M.ICON_SIZES-1)*gap)/(sizes_sum*u),
        (A.h-rows-pad-label*1.8)/(M.ICON_SIZES[4]*u)))
    -- (a read that raises counts as not resident)
    local function inspect(high,low)
        local done,result=pcall(images.inspect,runtime,high,low)
        if done and type(result)=='table'then return result end
        return {available=false,reason=tostring(result)}
    end
    local function facts(info)
        local m,t,slot=info.material or{},info.texture or{},info.imageSlot
        return('material %s, texture %s, shader %s, texture slot %s'):format(m.loaded and'loaded'or'NOT loaded',
            t.loaded and'loaded'or'not loaded',tostring(m.shader),
            slot and(tostring(slot.id)..' -> '..tostring(slot.resolvesTo))or'?')
    end
    local fh,fl=images.hash(font)
    local font_info=inspect(fh,fl)
    local vanilla=inspect(M.VANILLA_ICON.high,M.VANILLA_ICON.low)
    local name=images.material_name(custom)
    local high,low=images.hash(name)
    local info=inspect(high,low)
    local chex=('%08x%08x'):format(high,low)
    local vhex=('%08x%08x'):format(M.VANILLA_ICON.high,M.VANILLA_ICON.low)
    report(('custom icon loaded: texture %s %s'):format(name,info.texture and info.texture.loaded and'loaded'or'NOT loaded'))
    report(('custom icon GUI material loaded: %s %s, exact %s, shader %s'):format(name,info.material and info.material.loaded
        and'loaded'or'NOT loaded',tostring(info.material and info.material.exact),tostring(info.material and info.material.shader)))
    local custom_ok=info.material and info.material.loaded==true
    local vanilla_ok=vanilla.material and vanilla.material.loaded==true
    local pattern,pattern_info,pattern_ok
    local pattern_label=type(opts.patternLabel)=='string'and opts.patternLabel or'E pattern'
    if opts.pattern then
        pattern=images.material_name(opts.pattern)
        pattern_info=inspect(images.hash(pattern))
        pattern_ok=pattern_info.material and pattern_info.material.loaded==true
    end
    local colours=opts.colours
    report(colours and('icon diagnostics colours (row 1 and D): '..colours_text(colours)..' (the native loadout slot\'s '
        ..'values); row 2 sets nothing')or'icon diagnostics: no colours available; row 1 is drawn plain too')
    local coloured_row={
        {label='A font',name=font,resident=font_info.material and font_info.material.loaded==true,info=font_info,
            own=true},
        {label='A vanilla',hex=vhex,resident=vanilla_ok,info=vanilla},
        {label='B name',name=name,resident=custom_ok,info=info},
        {label='B hash',hex=chex,resident=custom_ok,info=info},
        pattern and{label=pattern_label,name=pattern,resident=pattern_ok,info=pattern_info}or
            {label=pattern_label,missing='no test pattern image in this build',info=info},
        {label='C texture',texture=true,info=info}}
    local plain_row={
        {label='A vanilla plain',hex=vhex,resident=vanilla_ok,info=vanilla},
        {label='B name plain',name=name,resident=custom_ok,info=info},
        pattern and{label=pattern_label..' plain',name=pattern,resident=pattern_ok,info=pattern_info}or
            {label=pattern_label..' plain',missing='no test pattern image in this build',info=info}}
    local coloured,open_why=open_screen()
    if not coloured then return nil,open_why end
    local plain,plain_why=open_screen()
    if not plain then coloured.close();return nil,plain_why end
    local results={}
    local function close()coloured.close();plain.close()end
    local ok,err=pcall(function()
        local function need(screen,v,what)if v==nil then error(what..' was refused: '..tostring(screen.reason),0)end end
        need(coloured,coloured.rect(A.x,A.y,BASE+20,A.w,A.h,COLOURS.panel),'the diagnostics background')
        local top=A.y+A.h
        need(coloured,coloured.text('ICON DIAGNOSTICS: ROW 1 COLOURED, ROW 2 PLAIN',font,label,font,A.x+pad,
            top-pad-label,BASE+22,COLOURS.title),'the title')
        -- The colours go on each material's instance in the coloured GUI once it has a bitmap of it.
        local set_for={}
        local function colour(control)
            if control.own or not colours then return'none (its own shader)'end
            local key=control.name or control.hex
            if set_for[key]~=nil then return set_for[key]end
            local instance,inst_why=coloured.material(control.name or control.hex,control.hex~=nil)
            local done,set_why=nil,inst_why
            if instance then done,set_why=coloured.set_vectors(instance,colours)end
            set_for[key]=done and'set on this GUI\'s instance'or('NOT set: '..tostring(set_why))
            return set_for[key]
        end
        local function cell_at(screen,x,y,size,control,coloured_gui)
            need(screen,screen.rect(x,y,BASE+21,size/2,size,{255,18,20,22}),'a dark background')
            need(screen,screen.rect(x+size/2,y,BASE+21,size/2,size,{255,220,220,220}),'a light background')
            local id,why_,colour_state
            if control.texture then why_='not drawable: Gui.bitmap takes a material, not a texture'
            elseif control.missing then why_=control.missing
            elseif not control.resident then why_='not drawn: the material is not loaded'
            elseif control.name then
                id,why_=screen.bitmap(control.name,x,y,BASE+22,size,size,{255,255,255,255},{optional=true})
            else id,why_=screen.bitmap_id(control.hex,x,y,BASE+22,size,size,{255,255,255,255},{optional=true})end
            if id~=nil then colour_state=coloured_gui and colour(control)or'none (plain GUI)'end
            results[#results+1]={label=control.label,size=math.floor(size+0.5),id=id,reason=why_,colours=colour_state}
            report(('icon diagnostics %s at %.0f px: resource %s; %s; Gui.bitmap %s; colours %s; update: not used '
                ..'(retained bitmap)'):format(control.label,size,control.name or(control.hex and('0x'..control.hex:upper()))
                or name,facts(control.info),id~=nil and('created (engine id '..tostring(id)..')')or('not created: '
                ..tostring(why_)),tostring(colour_state or'-')))
        end
        local y=top-pad-label*1.5-cell
        for k,control in ipairs(coloured_row)do
            local x=A.x+pad+(k-1)*(cell+gap)
            cell_at(coloured,x,y,cell,control,true)
            need(coloured,coloured.text(control.label,font,label*0.8,font,x,y-label*1.0,BASE+22,COLOURS.text),'a label')
        end
        y=y-row_h
        for k,control in ipairs(plain_row)do
            local x=A.x+pad+(k-1)*(cell+gap)
            cell_at(plain,x,y,cell,control,false)
            need(coloured,coloured.text(control.label,font,label*0.8,font,x,y-label*1.0,BASE+22,COLOURS.text),'a label')
        end
        local x=A.x+pad
        local base=y-label*1.8-M.ICON_SIZES[4]*u*fit
        for _,size in ipairs(M.ICON_SIZES)do
            local s_=size*u*fit
            cell_at(coloured,x,base,s_,{label='D '..math.floor(s_+0.5)..' px',name=name,resident=custom_ok,info=info},true)
            x=x+s_+gap
        end
    end)
    if not ok then close();return nil,tostring(err)end
    return {close=close},results
end

-- The mouse in GUI pixels: the client area (top-left origin, its own size) scaled to the GUI resolution with the
-- bottom-left origin the GUI draws in.
function M.to_gui(mouse,gui_w,gui_h)
    if not(mouse and mouse.w and mouse.w>0 and mouse.h and mouse.h>0)then return nil end
    return mouse.x*gui_w/mouse.w,(mouse.h-mouse.y)*gui_h/mouse.h
end
-- The visible tile under (x, y), or nil; and whether the point is inside the panel.
function M.hit(layout,x,y)
    if not(layout and x and y)then return nil,false end
    local function contains(r)return x>=r.x and x<r.x+r.w and y>=r.y and y<r.y+r.h end
    for index,tile in ipairs(layout.tiles)do
        if tile.visible and contains(tile.rect)then return index,true end
    end
    return nil,contains(layout.panel)
end

--------------------------------------------------------------------------------------- the native-style panel --
-- 0.8.0 (the user's UI overhaul, 2026-10-06): the panel drawn like the native stratagem list, right of the native
-- details panel, in the native list's own vertical band (stratagem_selector.grid viewport):
--   * four columns of native-sized cards (80 units at the native 85-unit pitch, the native cards' own px per unit), up to
--     six rows in view; more rows scroll (the mouse wheel over the panel, the scrollbar track, keyboard focus), with a
--     native-style scrollbar right of the grid while there are more rows than fit;
--   * each card in the native look (measured from the native card): a grey 103/255 frame 2 units thick, open in the
--     middle of its left and right sides, a translucent inner square at 68/80, the icon at 51/80; focused, the frame is
--     white; a custom stratagem already in a loadout slot has the native equipped look (a yellow frame, a darker inner
--     square, a dimmed icon); an unavailable one is dimmed with a warning mark;
--   * the title CUSTOM STRATAGEMS in FS Sinclair Medium at the native list header's size (runtime/ui_fonts.lua; monaco
--     when the Runtime's fonts are not loaded);
--   * while a card is focused, its details are drawn OVER the native details panel in the native details layout (its
--     category line, its name, its description, a STATS box and an ITEM TRAITS box), on a plate that hides the native
--     panel's own text: the native details elements are layers 800-803 of the Ui World (research: the details class
--     0x189EB10), the plate and text the overlay band above them (below the native 991-1018).
-- floor: units above the screen bottom the panel stays clear of (the native squad bars, 'EMPTY SLOT', reach about 151);
-- ceiling: units below the screen top (the top bar).
M.NATIVE={card=CARD.size,inner=CARD.inner,icon=CARD.icon,gap=GAP,columns=4,maxRows=6,pad=10,header=50,margin=15,
    titleCap=13,frame=2,focusFrame=2.5,split=21,scrollbar={w=3,gap=7},minUnit=0.6,floor=170,ceiling=60}
local NV=M.NATIVE
local NCOLOURS={panel={214,8,9,10},panelEdge={255,54,56,58},title={255,236,236,226},frame={255,103,103,103},
    inner={226,36,37,36},focus={255,255,255,255},equipped={255,132,121,8},equippedInner={235,30,27,17},
    track={170,56,58,60},thumb={235,150,150,146},
    -- the details overlay (sampled from the native details panel)
    plate={255,10,11,12},box={255,1,2,3},boxEdge={255,96,96,94},category={255,178,178,170},name={255,244,244,236},
    text={255,206,206,198},label={255,184,184,178},value={255,244,244,236},bullet={255,244,244,236}}
M.NATIVE_COLOURS=NCOLOURS

-- The layout for a width x height GUI. opts: details (the native details panel's rect, required), viewport (the native
-- list frame's rect; else the details panel's band), unit (px per native unit: the native cards'), count, scroll (the
-- first visible row). Returns {unit, panel, header, title = {cx, baseline, cap}, grid = {x, top, w, h, columns, rows,
-- totalRows, scroll}, tiles, scrollbar = {track, thumb} or nil, details} or nil and the reason. Rects {x, y, w, h} from
-- the bottom-left, in pixels.
function M.native_layout(width,height,opts)
    opts=opts or{}
    if type(width)~='number'or type(height)~='number'or width<640 or height<360 then return nil,'unsupported resolution'end
    local count=opts.count or 1
    if count<1 or count%1~=0 or count>240 then return nil,'unsupported entry count'end
    local d=opts.details
    if not(type(d)=='table'and type(d.w)=='number'and d.w>0)then return nil,'the native details panel is unknown'end
    local base=opts.unit or height/1080
    if type(base)~='number'or base~=base or base<=0 then return nil,'invalid unit'end
    local v=opts.viewport
    local band_top=v and(v.y+v.h)or(d.y+d.h)
    local band_bottom=v and v.y or d.y
    local col_x=d.x+d.w+NV.margin*base
    local col_w=width-NV.margin*base-col_x
    local grid_w=NV.columns*NV.card+(NV.columns-1)*NV.gap
    local panel_w=NV.pad+grid_w+NV.scrollbar.gap+NV.scrollbar.w+NV.pad
    local u=math.min(base,col_w/panel_w)
    if u<NV.minUnit*base then return nil,'no room right of the native details panel for four columns'end
    local pitch=(NV.card+NV.gap)*u
    local total=math.ceil(count/NV.columns)
    -- Between the floor (clear of the native squad bars) and the ceiling (below the top bar); the panel's top at the
    -- native list header's level when it fits, else raised just enough.
    local floor,ceiling=NV.floor*base,height-NV.ceiling*base
    local fit=math.floor(((ceiling-floor)/u-NV.header-2*NV.pad+NV.gap)/(NV.card+NV.gap)+1e-9)
    local rows=math.max(1,math.min(NV.maxRows,total,fit))
    local scroll=math.max(0,math.min(opts.scroll or 0,total-rows))
    local grid_h=(rows*NV.card+(rows-1)*NV.gap)*u
    local panel_h=NV.header*u+NV.pad*u+grid_h+NV.pad*u
    local panel_top=math.min(ceiling,math.max(band_top+NV.header*u,floor+panel_h))
    local out={unit=u,base=base,compact=u<base-1e-9,tile=NV.card*u,pitch=pitch,details=d,renderer='native'}
    out.panel={x=col_x,y=panel_top-panel_h,w=panel_w*u,h=panel_h}
    out.header={x=col_x,y=panel_top-NV.header*u,w=panel_w*u,h=NV.header*u}
    out.title={cx=col_x+panel_w*u/2,baseline=out.header.y+(NV.header-NV.titleCap)/2*u,cap=NV.titleCap*u}
    local gx=col_x+NV.pad*u
    local gtop=out.header.y-NV.pad*u
    out.grid={x=gx,top=gtop,w=grid_w*u,h=grid_h,columns=NV.columns,rows=rows,totalRows=total,scroll=scroll}
    out.tiles={}
    for index=1,count do
        local column,row=(index-1)%NV.columns,math.floor((index-1)/NV.columns)-scroll
        out.tiles[index]={rect={x=gx+column*pitch,y=gtop-row*pitch-NV.card*u,w=NV.card*u,h=NV.card*u},column=column,
            row=row+scroll,visible=row>=0 and row<rows}
    end
    if total>rows then
        local track={x=gx+grid_w*u+NV.scrollbar.gap*u,y=gtop-grid_h,w=NV.scrollbar.w*u,h=grid_h}
        local th=math.max(track.h*rows/total,6*u)
        local ty=track.y+track.h-th-(track.h-th)*scroll/math.max(1,total-rows)
        out.scrollbar={track=track,thumb={x=track.x,y=ty,w=track.w,h=th}}
    end
    if out.panel.y<0 or out.panel.x+out.panel.w>width+0.5 then return nil,'the panel does not fit the screen'end
    return out
end

-- The scroll a point on the scrollbar track asks for (a page up above the thumb, a page down below it), or nil.
function M.scroll_hit(layout,x,y)
    local s=layout and layout.scrollbar
    if not s then return nil end
    local t=s.track
    if not(x>=t.x-4*layout.unit and x<t.x+t.w+4*layout.unit and y>=t.y and y<t.y+t.h)then return nil end
    local g=layout.grid
    if y>s.thumb.y+s.thumb.h then return math.max(0,g.scroll-g.rows)end
    if y<s.thumb.y then return math.min(g.totalRows-g.rows,g.scroll+g.rows)end
    return g.scroll
end

-- A native-look frame: four bars of thickness t, the left and right ones open in their middle over `split` pixels.
local function split_frame(screen,r,t,split,layer,colour,what)
    local half=(r.h-split)/2
    local bars={{r.x,r.y,r.w,t},{r.x,r.y+r.h-t,r.w,t},
        {r.x,r.y,t,half},{r.x,r.y+r.h-half,t,half},{r.x+r.w-t,r.y,t,half},{r.x+r.w-t,r.y+r.h-half,t,half}}
    for _,b in ipairs(bars)do
        if screen.rect(b[1],b[2],layer,b[3],b[4],colour)==nil then error(what..' was refused: '..tostring(screen.reason),0)end
    end
end
M.split_frame=split_frame

-- The panel (retained): background, title, every visible card and the scrollbar. entries as M.entries (plus
-- equipped, unavailable, colours); report(line) receives the icon draws. Returns the screen or nil and the reason.
function M.draw_native(runtime,layout,entries,report)
    local fonts=require('hd2runtime/runtime/ui_fonts')
    local title_font=fonts.font(runtime,'title')
    if title_font.fallback then
        local ready,why=font_ready(runtime)
        if not ready then return nil,why end
    end
    local unavailable={}
    for index,entry in ipairs(entries)do
        if entry.icon then
            local done,family=pcall(images.family,runtime,entry.icon)
            if not(done and family.complete)then
                unavailable[index]=done and tostring(family.reason)or tostring(family)
                if report then report(('custom icon unavailable for %s (%s): drawing the placeholder mark'):format(entry.id,
                    unavailable[index]))end
            end
        end
    end
    local screen,open_why=open_screen()
    if not screen then return nil,open_why end
    local u=layout.unit
    local coloured={}
    local ok,err=pcall(function()
        local function need(v,what)if v==nil then error(what..' was refused: '..tostring(screen.reason),0)end end
        local P=layout.panel
        need(screen.rect(P.x,P.y,BASE+10,P.w,P.h,NCOLOURS.panel),'the panel')
        frame_rects(screen,P,math.max(1,math.floor(u+0.5)),BASE+11,NCOLOURS.panelEdge,'the panel edge')
        -- The header: a thin rule under the title band, the title centred like the native list's.
        need(screen.rect(P.x+NV.pad*u,layout.header.y,BASE+11,P.w-2*NV.pad*u,math.max(1,math.floor(u+0.5)),
            NCOLOURS.panelEdge),'the header rule')
        local size=fonts.size_for_cap(title_font,layout.title.cap)
        local w=fonts.width(title_font,M.TITLE,size)
        need(screen.text(M.TITLE,title_font.name,size,title_font.name,layout.title.cx-w/2,layout.title.baseline,BASE+17,
            NCOLOURS.title),'the title')
        for index,entry in ipairs(entries)do
            local tile=layout.tiles[index]
            if tile and tile.visible then
                local r=tile.rect
                local inset=(NV.card-NV.inner)/2*u
                local inner={x=r.x+inset,y=r.y+inset,w=r.w-2*inset,h=r.h-2*inset}
                need(screen.rect(inner.x,inner.y,BASE+12,inner.w,inner.h,entry.equipped and NCOLOURS.equippedInner
                    or NCOLOURS.inner),'a card')
                split_frame(screen,r,NV.frame*u,NV.split*u,BASE+13,entry.equipped and NCOLOURS.equipped or NCOLOURS.frame,
                    'a card frame')
                local drawn_icon=false
                if entry.icon and not unavailable[index]then
                    local icon=NV.icon*u
                    local material=images.material_name(entry.icon)
                    local spec={material=material,x=r.x+(r.w-icon)/2,y=r.y+(r.h-icon)/2,w=icon,h=icon,layer=BASE+16,
                        alpha=entry.equipped and 0.55 or 1,plate=overlay.PLATE}
                    if report then
                        report(('custom icon GUI bitmap draw attempted: Gui.bitmap("%s", %.0f, %.0f, %.0f x %.0f, layer %d)'
                            ..' for %s, on the native icon background\'s plate (%d, %d, %d) at layer %d'):format(material,
                            spec.x,spec.y,icon,icon,spec.layer,entry.id,spec.plate[1],spec.plate[2],spec.plate[3],
                            spec.layer-1))
                    end
                    local ids,why=overlay.draw_icon(screen,spec)
                    if report then
                        report(ids~=nil and('custom icon GUI bitmap draw succeeded for %s (engine id %s; plate %s)'):format(
                            entry.id,tostring(ids.icon),ids.plate~=nil and'drawn'or('NOT drawn: '..tostring(ids.plateWhy)))
                            or('custom icon GUI bitmap draw failed for %s: %s; drawing the placeholder mark'):format(
                            entry.id,tostring(why)))
                    end
                    drawn_icon=ids~=nil
                    if ids~=nil and coloured[material]==nil then
                        coloured[material]=true
                        if entry.colours then
                            local set,set_why=overlay.colour(screen,material,entry.colours)
                            if report then
                                report(set and('custom icon colours set for %s on this GUI\'s material instance (the '
                                    ..'native loadout slot\'s values, colour set %s): %s'):format(entry.id,
                                    tostring(entry.colourSet),colours_text(entry.colours))or('custom icon colours NOT set '
                                    ..'for %s: %s (the icon stays transparent)'):format(entry.id,tostring(set_why)))
                            end
                        elseif report then
                            report(('custom icon colours unavailable for %s: %s (the icon stays transparent)')
                                :format(entry.id,tostring(entry.coloursWhy)))
                        end
                    end
                end
                if not drawn_icon then
                    local mark=math.max(4,r.h*0.4)
                    need(screen.text('?',D.font.name,mark,D.font.name,r.x+r.w/2-mark*0.3,r.y+r.h/2-mark*0.35,BASE+16,
                        NCOLOURS.frame),'a placeholder mark')
                end
                if entry.unavailable then
                    need(screen.rect(inner.x,inner.y,BASE+17,inner.w,inner.h,COLOURS.unavailableShade),'an unavailable shade')
                    local mark=math.max(4,r.h*0.45)
                    need(screen.text('!',D.font.name,mark,D.font.name,r.x+r.w/2-mark*0.15,r.y+r.h/2-mark*0.35,BASE+18,
                        COLOURS.warning),'an unavailable mark')
                    if report then report(('%s is UNAVAILABLE: its tile is dimmed and marked'):format(entry.id))end
                end
            end
        end
        local sb=layout.scrollbar
        if sb then
            need(screen.rect(sb.track.x,sb.track.y,BASE+12,sb.track.w,sb.track.h,NCOLOURS.track),'the scrollbar track')
            need(screen.rect(sb.thumb.x,sb.thumb.y,BASE+13,sb.thumb.w,sb.thumb.h,NCOLOURS.thumb),'the scrollbar thumb')
        end
    end)
    if not ok then screen.close();return nil,tostring(err)end
    return screen,title_font
end

-- The details layout (units from the details panel's top-left; 1024 x 400): the category line, the name and the
-- description where the native panel has them; the STATS and ITEM TRAITS boxes the user's layout of 2026-10-06 (their
-- titles inside, under the top edge; four stat rows: call-in time, uses, cooldown, the call-in code).
M.DETAILS={plate={6,6,1012,388},textX=42,category={baseline=48.5,cap=15},name={baseline=81.5,cap=20},
    description={baseline=116.5,pitch=20,cap=12.5,lines=4,right=990},
    stats={box={15,203,500.5,374},title='STATS',labelX=31.5,valueRight=472,rows={252,283,314,345}},
    traits={box={522,203,1009,374},title='ITEM TRAITS',bulletX=547,textX=572,rows={256.5,292.5,328.5,364.5},
        rows5={248,277,306,335,364}},
    titleX=17.5,titleBaseline=220,titleGap=12,rowCap=15,boxTitleCap=15}
local DT=M.DETAILS
M.ARROWS={up='\226\134\145',down='\226\134\147',left='\226\134\144',right='\226\134\146'}   -- U+2191 2193 2190 2192

-- The focus overlay (retained, its own GUI): the focused card's white frame, and the entry's details over the native
-- details panel. info: {category, name, description, stats = {{label, value}}, traits = {text}}. Returns the screen
-- or nil and the reason.
function M.draw_native_focus(runtime,layout,entry,index,info)
    local fonts=require('hd2runtime/runtime/ui_fonts')
    local tile=layout.tiles[index]
    if not(tile and tile.visible)then return nil,'the focused card is not visible'end
    local title_font,body_font=fonts.font(runtime,'title'),fonts.font(runtime,'body')
    if title_font.fallback or body_font.fallback then
        local ready,why=font_ready(runtime)
        if not ready then return nil,why end
    end
    info=info or{}
    local d=layout.details
    local du=d.h/400
    local function X(units)return d.x+units*du end
    local function Y(units)return d.y+d.h-units*du end
    local screen,open_why=open_screen()
    if not screen then return nil,open_why end
    local ok,err=pcall(function()
        local function need(v,what)if v==nil then error(what..' was refused: '..tostring(screen.reason),0)end end
        local u=layout.unit
        split_frame(screen,tile.rect,NV.focusFrame*u,NV.split*u,BASE+18,NCOLOURS.focus,'the focus frame')
        -- The plate over the native details panel (its corner marks stay visible outside it).
        local p=DT.plate
        need(screen.rect(X(p[1]),Y(p[2]+p[4]),BASE+20,p[3]*du,p[4]*du,NCOLOURS.plate),'the details plate')
        local function text(s,font,cap,x,baseline,colour,what)
            local size=fonts.size_for_cap(font,cap*du)
            need(screen.text(s,font.name,size,font.name,x,Y(baseline),BASE+24,colour),what)
            return size
        end
        text(string.upper(info.category or'CUSTOM STRATAGEM'),title_font,DT.category.cap,X(DT.textX),DT.category.baseline,
            NCOLOURS.category,'the category')
        text(string.upper(info.name or entry.name or entry.id),title_font,DT.name.cap,X(DT.textX),DT.name.baseline,
            NCOLOURS.name,'the name')
        local dsize=fonts.size_for_cap(body_font,DT.description.cap*du)
        local lines=fonts.wrap(body_font,info.description or entry.description or'',dsize,(DT.description.right-DT.textX)*du,
            DT.description.lines)
        for k,line in ipairs(lines)do
            need(screen.text(line,body_font.name,dsize,body_font.name,X(DT.textX),Y(DT.description.baseline+(k-1)
                *DT.description.pitch),BASE+24,NCOLOURS.text),'the description')
        end
        local t=math.max(1,math.floor(du+0.5))
        for _,box in ipairs({DT.stats,DT.traits})do
            local b=box.box
            local r={x=X(b[1]),y=Y(b[4]),w=(b[3]-b[1])*du,h=(b[4]-b[2])*du}
            need(screen.rect(r.x,r.y,BASE+21,r.w,r.h,NCOLOURS.box),'a details box')
            -- Its frame: the left, right and bottom edges, the top edge right of the title; the title inside the box,
            -- its cap hanging under the top edge.
            local tsize=fonts.size_for_cap(title_font,DT.boxTitleCap*du)
            local tx=r.x+DT.titleX*du
            local te=tx+fonts.width(title_font,box.title,tsize)+DT.titleGap*du
            for _,e in ipairs({{r.x,r.y,t,r.h},{r.x+r.w-t,r.y,t,r.h},{r.x,r.y,r.w,t},{te,r.y+r.h-t,r.x+r.w-te,t}})do
                need(screen.rect(e[1],e[2],BASE+22,e[3],e[4],NCOLOURS.boxEdge),'a box edge')
            end
            need(screen.text(box.title,title_font.name,tsize,title_font.name,tx,Y(DT.titleBaseline),BASE+24,
                NCOLOURS.label),'a box title')
        end
        local rsize=fonts.size_for_cap(title_font,DT.rowCap*du)
        local rows=DT.stats.rows
        for k,row in ipairs(info.stats or{})do
            if rows[k]then
                local label=string.upper(row[1])
                need(screen.text(label,title_font.name,rsize,title_font.name,X(DT.stats.labelX),Y(rows[k]),
                    BASE+24,NCOLOURS.label),'a stat label')
                local value=string.upper(tostring(row[2]))
                -- The call-in code in the game's arrows when the font has them (the Runtime's FS Sinclair; monaco
                -- keeps the words).
                if type(row.code)=='table'and#row.code>0 then
                    local arrows={}
                    for i,dir in ipairs(row.code)do arrows[i]=M.ARROWS[dir]or'?'end
                    arrows=table.concat(arrows,' ')
                    if fonts.has(title_font,arrows)then value=arrows end
                end
                -- A value wider than the room right of its label is drawn smaller to fit (a long call-in code).
                local room=X(DT.stats.valueRight)-(X(DT.stats.labelX)+fonts.width(title_font,label,rsize)+12*du)
                local vsize=rsize
                local vw=fonts.width(title_font,value,vsize)
                if vw>room and room>0 then vsize=rsize*room/vw;vw=room end
                need(screen.text(value,title_font.name,vsize,title_font.name,X(DT.stats.valueRight)-vw,Y(rows[k]),
                    BASE+24,NCOLOURS.value),'a stat value')
            end
        end
        -- Five traits (CUSTOM STRATAGEM and four of the definition's): a tighter pitch in the same box.
        rows=#(info.traits or{})>#DT.traits.rows and DT.traits.rows5 or DT.traits.rows
        for k,trait in ipairs(info.traits or{})do
            if rows[k]then
                need(screen.rect(X(DT.traits.bulletX),Y(rows[k]),BASE+24,math.max(1,2.5*du),DT.rowCap*du,
                    NCOLOURS.bullet),'a trait bullet')
                need(screen.text(string.upper(trait),title_font.name,rsize,title_font.name,X(DT.traits.textX),Y(rows[k]),
                    BASE+24,NCOLOURS.value),'a trait')
            end
        end
    end)
    if not ok then screen.close();return nil,tostring(err)end
    return screen
end

---------------------------------------------------------------------------------------------- the controller --
-- Shown ONLY while the player is choosing a stratagem: a selection open (ui+0x273990) for a stratagem slot 0-3
-- (stratagem_selector.screen().gridOpen). Polled every frame: the frame the selection closes, everything is destroyed.
-- opts:
--   renderer: 'native' (the native-style panel and the details overlay; the custom stratagems' panel), 'compact' (the
--     default: the 0.2-0.7 panel; also the fallback when the native layout is refused) or 'legacy' (the 0.1.0
--     renderer; the last fallback);
--   details(id): the focused entry's details for the overlay ({category, name, description, stats, traits});
--   placeholders: visual placeholder entries after the virtual stratagems (default 0);
--   focus: keyboard focus allowed (S.focus_next / S.clear_focus: brackets and the tooltip);
--   selection: phase 2, S.press() selects the focused virtual stratagem (the guarded token write), S.cancel() restores;
--   mouse: hover focuses the tile under the cursor (brackets and tooltip), a left click selects it (runtime/input.lua
--     mouse: the OS cursor in the game window's client area, converted to GUI pixels); the keys stay as fallbacks;
--   icon_test: the Runtime image the icon test draws (default the first entry's icon); on_selected(handle);
--   advance: false leaves the native selector where it is after a selection (default: on to the next empty slot, and
--     closed as Back closes it when no empty slot is left); sound: false plays no native pick sound (default on);
--   world: 'ui' (default: the Ui World, the proven icon technique) or 'main' (the 0.1-0.6 main_world path; fallback);
--   slot_overlays: the virtual slots' icon overlays over the native loadout slots (stratagem_slot_overlay.virtual_slots;
--     default on; the borrowed-icon writes of runtime/stratagem_slot_icons.lua are never started here).
-- Returns S {shown, renderer, layout, focus, overlays, focus_next(), clear_focus(), toggle_icon_test(), press(),
-- cancel(), set_slot_overlays(on), status(), stop()}.
local SETTLE=0.15
local TRACK_SETTLE=0.5          -- seconds the loadout record must stay unchanged before the identity follows it
function M.panel(opts)
    opts=opts or{}
    assert(opts.world==nil or opts.world=='ui'or opts.world=='main','world must be \'ui\' or \'main\'')
    M.WORLD=opts.world or'ui'
    local S={shown=false,focus=nil,renderer=nil,iconTest=false,scroll=0}
    if opts.slot_overlays~=false then S.overlays=overlay.virtual_slots()end
    local track={active=false,slot=nil,stable=0,poll=0,resolution=nil,reason=nil,wait=0,details=nil,mouse=nil,
        left=false,hover=nil,mouseReason=nil}
    local screens={}            -- panel, focus, icon test
    local entries
    -- A line said while the panel stays open is not said again (a re-show with the same layout, a focus already
    -- reported); hiding the panel forgets them.
    local said={}
    local function say(key,text)
        if said[key]==text then return end
        said[key]=text
        log(text)
    end
    local function close(name)if screens[name]then screens[name].close();screens[name]=nil end end
    local function hide(reason)
        close('focus');close('icontest');close('panel')
        if S.shown and reason then log('hidden: '..reason);said={}end
        S.shown,S.layout,S.renderer=false,nil,nil
    end
    local function availability_of(id)
        if not opts.availability then return nil end
        local ok,why=pcall(opts.availability,id)
        return ok and why or nil
    end
    local function availability_key()
        local parts={}
        for _,e in ipairs(M.entries())do parts[#parts+1]=e.id..'='..tostring(availability_of(e.id))end
        return table.concat(parts,'|')
    end
    -- The loadout picks behind the cards' equipped look: the panel redraws when they change (a pick, a native pick over
    -- a custom slot, the selector dropping the last mission's slots). Live r27: drawn only when the panel opened, the
    -- marks stayed the previous mission's picks while the selector had already cleared them.
    local function equipped_key()
        local vs=selector.virtual_slots()
        local parts={}
        for slot,e in pairs(vs and vs.slots or{})do parts[#parts+1]=tostring(slot)..'='..tostring(e.definition)end
        table.sort(parts)
        return table.concat(parts,',')
    end
    local function all_entries()
        local out=M.entries()
        local held={}
        local vs=selector.virtual_slots()
        for _,e in pairs(vs and vs.slots or{})do held[e.definition]=true end
        for _,e in ipairs(out)do e.unavailable=availability_of(e.id);e.equipped=held[e.id]==true end
        for _,p in ipairs(M.placeholders(opts.placeholders or 0))do out[#out+1]=p end
        return out
    end
    local function draw_focus()
        close('focus')
        if not(S.shown and S.focus)then return end
        if S.renderer=='legacy'then
            -- The legacy renderer draws focus into its own panel: redraw it.
            close('panel')
            local world=world_module.open()
            local drawn,why=nil,'no game world'
            if world then drawn,why=M.draw(world.runtime,S.layout,entries,{focus=S.focus})end
            if drawn then screens.panel=drawn else log('legacy focus not drawn: '..tostring(why))end
            return
        end
        if S.iconTest then log('tooltip not drawn: the icon test uses that side');return end
        local world=world_module.open()
        if not world then return end
        if S.renderer=='native'then
            local entry=entries[S.focus]
            local info
            if opts.details then
                local ok,v=pcall(opts.details,entry.id)
                info=ok and v or nil
            end
            info=info or{}
            if entry.unavailable then
                info.description=tostring(entry.unavailable)..' It cannot be picked now.'
            end
            local drawn,why=M.draw_native_focus(world.runtime,S.layout,entry,S.focus,info)
            if not drawn then log('focus not drawn: '..tostring(why));return end
            screens.focus=drawn
            say('focus '..S.focus,('focused %s (card %d): its details drawn over the native details panel %s'):format(
                entry.id,S.focus,rect_text(S.layout.details)))
            return
        end
        local drawn,tip,lines=M.draw_focus(world.runtime,S.layout,entries[S.focus],S.focus)
        if not drawn then log('focus not drawn: '..tostring(tip));return end
        screens.focus=drawn
        say('focus '..S.focus,('focused %s (tile %d): tooltip %s, %d description line%s'):format(entries[S.focus].id,
            S.focus,rect_text(tip),#lines,#lines==1 and''or's'))
    end
    local function show(view,world,reason)
        hide()
        local facts=engine_gui.diagnostics()or{}
        local res=facts.resolution
        if not(res and type(res[1])=='number'and type(res[2])=='number')then return nil,'no GUI resolution'end
        entries=all_entries()
        S.equipped=equipped_key()
        if #entries==0 then return nil,'no entries'end
        -- Each virtual stratagem's icon colours: its colour donor's colour set (display.colours, e.g. a support
        -- stratagem's for a support custom stratagem), else its token's, read as the native loadout slot reads it.
        local proven,proof_why=selector.prove(world)
        for _,e in ipairs(entries)do
            if not e.placeholder then
                local definition=virtual.get(e.id)
                local kind=definition and loadout.type_of(world,definition.display.coloursId
                    or definition.selection.tokenId)
                if not proven then e.coloursWhy='the selector code is not proven: '..tostring(proof_why)
                elseif not kind then e.coloursWhy='the token has no type'
                else e.colours,e.colourSet=selector.icon_colours(world,kind)
                    if not e.colours then e.coloursWhy=e.colourSet;e.colourSet=nil end
                end
            end
        end
        -- The native details panel: the panel goes to its right and never meets it (nor the list frame).
        local details,details_why=selector.details(world,view)
        if not details then return nil,'the native details panel: '..tostring(details_why)end
        local unit,protected,source=details.scale,{details.rect},'the native details panel'
        local grid=select(1,selector.grid(world,view))
        if grid then
            protected[#protected+1]=grid.viewport
            if grid.cards[1]then unit=grid.cards[1].h/CARD.size;source='the native cards'end
        end
        local layout,renderer,why
        if opts.renderer=='native'then
            layout,why=M.native_layout(res[1],res[2],{unit=unit,count=#entries,details=details.rect,
                viewport=grid and grid.viewport,scroll=S.scroll})
            renderer='native'
            if not layout then log('native layout refused ('..tostring(why)..'); falling back to the compact renderer')end
        end
        if not layout and opts.renderer~='legacy'then
            layout,why=M.anchored_layout(res[1],res[2],{unit=unit,count=#entries,details=details.rect,protected=protected})
            renderer='compact'
            if not layout then log('compact layout refused ('..tostring(why)..'); falling back to the legacy renderer')end
        end
        if not layout then
            layout,why=M.layout(res[1],res[2],{unit=unit,count=#entries,protected=protected})
            renderer='legacy'
            if not layout then return nil,'the legacy renderer refused too: '..tostring(why)end
        end
        local drawn,draw_why,font
        if renderer=='native'then drawn,draw_why=M.draw_native(world.runtime,layout,entries,function(t)say(t,t)end)
            font=draw_why
            if drawn then draw_why=nil end
        elseif renderer=='compact'then drawn,draw_why=M.draw_compact(world.runtime,layout,entries,function(t)say(t,t)end)
        else drawn,draw_why=M.draw(world.runtime,layout,entries,{focus=S.focus})end
        if not drawn then return nil,draw_why end
        screens.panel,S.layout,S.renderer,S.shown=drawn,layout,renderer,true
        if layout.grid then S.scroll=layout.grid.scroll or 0 end
        S.availability=availability_key()
        track.resolution=res[1]..'x'..res[2]
        track.details=rect_text(details.rect)
        local shown_tiles=0
        for _,t in ipairs(layout.tiles)do if t.visible then shown_tiles=shown_tiles+1 end end
        say('shown',('shown: active selector slot %d (%s; %s renderer): panel %s, %.3f px/unit (%s%s), tiles %.0f px in %d '
            ..'columns, %d of %d entries in view (%d row%s)%s'):format(view.editedSlot,reason,renderer,rect_text(layout.panel),
            layout.unit,source,layout.compact and', compact'or'',layout.tile or layout.card,layout.grid.columns,shown_tiles,
            #entries,layout.grid.rows,layout.grid.rows==1 and''or's',
            renderer=='compact'and(', footprint with the tooltip '..rect_text(layout.footprint))or''))
        if renderer=='native'then
            say('native',('native-style panel right of the native details panel %s: %d columns, %d of %d rows in view%s; '
                ..'title font %s%s'):format(rect_text(details.rect),layout.grid.columns,layout.grid.rows,layout.grid.totalRows,
                layout.scrollbar and(', scrolled to row '..layout.grid.scroll..' (wheel or scrollbar)')or'',
                font and font.name or'?',font and font.fallback and' (FS Sinclair not loaded: monaco)'or' (FS Sinclair)'))
        end
        if renderer=='compact'then
            say('right',('right of the native details panel %s (%.3f px/unit, %.0f x %.0f units): column %s, tooltip %s%s')
                :format(rect_text(details.rect),details.scale,details.units.w,details.units.h,rect_text(layout.column),
                layout.tooltipMode,layout.columnsDropped>0 and(', '..layout.columnsDropped..' column(s) dropped')or''))
        end
        if grid then say('clear','clear of the native list frame '..rect_text(grid.viewport))end
        if S.iconTest then S.iconTest=false;S.toggle_icon_test()end
        if S.focus then draw_focus()end
        return true
    end
    S.follower={status='active'}
    function S.follower.cancel()S.follower.status='cancelled'end
    function S.follower.tick(dt)
        if S.follower.status~='active'then return end
        if S.track_due then
            S.track_due=S.track_due-(dt or 0)
            if S.track_due<=0 then
                S.track_due=nil
                local tworld=world_module.open()
                local tok,tview=false,nil
                if tworld then tok,tview=pcall(selector.screen,tworld)end
                if tok and tview and tview.open then selector.track(tworld,tview)end
            end
        end
        local world=world_module.open()
        local ok,view=false,nil
        if world then ok,view=pcall(selector.screen,world)end
        local active=ok and view and view.open and view.gridOpen and view.editedSlot or nil
        if not active then
            if track.active then
                track.active,track.slot,track.reason=false,nil,nil
                track.hover,track.mouse,track.left=nil,nil,false
                S.focus=nil
                S.full=nil
                S.scroll=0
                hide('selector closed')
            end
            return
        end
        if S.full then
            if active~=track.slot then S.full=nil else return end
        end
        if not track.active then
            track.active,track.slot,track.stable,track.wait,track.reason=true,active,0,0,nil
            return
        end
        if active~=track.slot then
            log(('active selector slot %d (was %d)'):format(active,track.slot))
            track.slot=active
        end
        track.stable=track.stable+(dt or 0)
        track.wait=math.max(0,track.wait-(dt or 0))
        if track.stable<SETTLE or track.wait>0 then return end
        if S.shown and opts.mouse then S.mouse_tick(view)end
        if not S.shown then
            local done,why=show(view,world,'the selector opened')
            if not done then
                if why~=track.reason then track.reason=why;log('not shown: '..tostring(why))end
                track.wait=5
            end
            return
        end
        if S.renderer=='native'and equipped_key()~=S.equipped then
            show(view,world,'the loadout picks changed')
            return
        end
        track.poll=track.poll+(dt or 0)
        if track.poll<0.5 then return end
        track.poll=0
        local facts=engine_gui.diagnostics()or{}
        local res=facts.resolution
        if res and(tostring(res[1])..'x'..tostring(res[2]))~=track.resolution then show(view,world,'the resolution changed')
            return end
        local details=selector.details(world,view)
        if S.renderer=='compact'and details and rect_text(details.rect)~=track.details then
            show(view,world,'the details panel moved')
        elseif opts.availability and availability_key()~=S.availability then
            show(view,world,'the availability of an entry changed')
        end
    end
    scheduler.attach(S.follower)
    -- Identity follows the loadout while the screen is open (phase 2). Only a settled record counts: each change restarts
    -- a short wait, and the identity follows the record read when it has stayed unchanged that long, never a frame of a
    -- native pick or a rebuild in progress (stratagem_selector.track also ignores anything but the ship loadout before
    -- launch). Opening the screen checks nothing by itself (its record may not be filled yet); a mission conversion
    -- checks the exact recorded order itself.
    -- Leaving the screen before the wait is over applies the pending follow to the last record seen while it was open
    -- (the player's final edit), so a quick exit never leaves the recorded order stale.
    S.watch=selector.watch(function(event,view)
        if event=='record_changed'then
            S.track_due,S.track_view=TRACK_SETTLE,view
        elseif event=='closed'and S.track_due then
            S.track_due=nil
            local world=world_module.open()
            if world and S.track_view then selector.track(world,S.track_view)end
        end
    end)
    function S.focus_next()
        if not opts.focus then return'focus is not enabled in this build'end
        if not S.shown then return'the panel is not shown (open a stratagem selector)'end
        local n=#entries
        local k=S.focus or 0
        if S.renderer=='native'then
            k=k+1
            if k>n then S.focus=nil;close('focus');log('focus cleared');return'focus cleared'end
            S.focus=k
            local tile=S.layout.tiles[k]
            if tile and not tile.visible then
                local g=S.layout.grid
                S.scroll_to(math.max(0,math.min(tile.row,g.totalRows-g.rows)),'the focus moved')
            else draw_focus()end
            return'focused '..entries[k].id
        end
        repeat k=k+1 until k>n or(S.layout.tiles[k]and S.layout.tiles[k].visible)
        if k>n then S.focus=nil;close('focus');log('focus cleared');return'focus cleared'end
        S.focus=k
        draw_focus()
        return'focused '..entries[k].id
    end
    function S.clear_focus()
        if not S.focus then return'nothing focused'end
        S.focus=nil
        if S.renderer=='legacy'and S.shown then
            local world=world_module.open()
            close('panel')
            local drawn=nil
            if world then drawn=M.draw(world.runtime,S.layout,entries,{})end
            if drawn then screens.panel=drawn end
        else
            close('focus')
        end
        log('focus cleared')
        return'focus cleared'
    end
    function S.toggle_icon_test()
        if S.iconTest then
            S.iconTest=false
            close('icontest')
            if S.focus then draw_focus()end
            return'icon diagnostics off'
        end
        S.iconTest=true
        if not S.shown then return'icon test on (drawn when the panel is shown)'end
        if S.renderer~='compact'then return'icon diagnostics on, but the legacy renderer has no area for them'end
        local icon=opts.icon_test or(entries[1]and entries[1].icon)
        if not icon then return'icon diagnostics: no custom icon'end
        close('focus')
        local world=world_module.open()
        local drawn,results=nil,'no game world'
        local first=entries[1]
        if world then drawn,results=M.draw_icon_diagnostics(world.runtime,S.layout,icon,log,{colours=first and first.colours,
            pattern=opts.icon_pattern,patternLabel=opts.icon_pattern_label})end
        if not drawn then
            log('icon diagnostics not drawn: '..tostring(results))
            return'icon diagnostics not drawn: '..tostring(results)
        end
        screens.icontest=drawn
        local parts={}
        for _,r in ipairs(results)do parts[#parts+1]=r.label..(r.id~=nil and(' ok'..(r.colours and r.colours:find('^set')
            and' (coloured)'or''))or' failed')end
        log('icon diagnostics drawn: '..table.concat(parts,', '))
        return'icon diagnostics on'
    end
    -- Selects entry `index` (a click or F7): the panel's own checks, then the existing guarded token write into the slot
    -- being edited (stratagem_selector.select re-checks the selector, the slot 0-3, the local record, solo, aboard).
    function S.select_index(index,how)
        if not opts.selection then return'selection is not enabled in this build'end
        if not S.shown then return'the panel is not shown (open a stratagem selector)'end
        local entry=entries[index]
        if not entry then return'no such tile'end
        if entry.placeholder then
            log(('%s on %s refused: placeholders cannot be selected'):format(how or'selection',entry.id))
            return'placeholders cannot be selected'
        end
        local unavailable=availability_of(entry.id)
        if unavailable then
            log(('%s on %s REFUSED (nothing written): %s'):format(how or'selection',entry.id,tostring(unavailable)))
            if opts.on_selected then opts.on_selected({status='refused',code='UNAVAILABLE',reason=unavailable})end
            return'unavailable: '..tostring(unavailable)
        end
        local world=world_module.open()
        local ok,view=false,nil
        if world then ok,view=pcall(selector.screen,world)end
        if not(ok and view and view.open and view.gridOpen and view.editedSlot==track.slot)then
            log(('%s on %s refused: the selector is no longer open for slot %s'):format(how or'selection',entry.id,
                tostring(track.slot)))
            return'the selector is no longer open for slot '..tostring(track.slot)
        end
        log(('%s: selecting %s (token %s) into slot %d'):format(how or'selection',entry.id,
            tostring(virtual.get(entry.id)and virtual.get(entry.id).selection.token),view.editedSlot))
        S.handle=selector.select(entry.id,function(handle)
            if handle.status=='selected'then
                S.selected={id=entry.id,slot=handle.index}
                log(('SELECTED %s: slot %d now holds %s%s; virtual slots: %s'):format(entry.id,handle.index,
                    tostring(virtual.get(entry.id).selection.token),handle.written and''or' (already; no write)',
                    selector.slots_text(selector.virtual_slots())))
                local advance=handle.advance
                if advance and advance.status=='advanced'then
                    log(('the native selector moved on to slot %d (the next empty slot): the native highlight and the '
                        ..'edited slot%s; the panel stays open for it'):format(advance.slot,advance.verified==false
                        and' (the redraw did not verify)'or''))
                elseif advance and advance.status=='closed'then
                    -- No empty slot left: the native selector was closed as Back closes it (the game's own close
                    -- handler); the panel closes with it.
                    S.full=true
                    S.focus=nil
                    log(('the loadout is full: the native selector was closed as Back closes it (verified %s)'):format(
                        tostring(advance.verified)))
                    hide('the loadout is full; the native stratagem selector closed')
                elseif advance and advance.status=='full'then
                    -- No empty slot left and the close was refused: the panel closes and stays closed until the
                    -- player closes the native selector.
                    S.full=true
                    S.focus=nil
                    hide(('the loadout is full (%s); close the native stratagem selector with Back'):format(
                        tostring(advance.reason)))
                elseif advance then
                    log(('the native selector was not moved on: %s'):format(tostring(advance.reason)))
                end
            end
            if opts.on_selected then opts.on_selected(handle)end
        end,{advance=opts.advance~=false and slot_focus.advance or nil,sound=opts.sound~=false})
        return'selecting '..entry.id..' into slot '..tostring(track.slot)
    end
    -- F7 fallback: the first press focuses, the next selects the focused entry.
    function S.press()
        if not opts.selection then return'selection is not enabled in this build'end
        if not S.shown then return'the panel is not shown (open a stratagem selector)'end
        if not S.focus then return S.focus_next()end
        return S.select_index(S.focus,'F7')
    end
    -- The mouse, each frame while shown: hover focuses (only when the cursor moved, so the keys keep their focus), a
    -- left press over a tile selects it. Engine Mouse values are logged beside each click (research only).
    local function engine_mouse()
        local S_=rawget(_G,'stingray')
        local Mouse=S_ and S_.Mouse
        if type(Mouse)~='table'then return'stingray.Mouse unavailable'end
        local ok,text=pcall(function()
            local axis=Mouse.axis(Mouse.axis_index('cursor'))
            local left=Mouse.button(Mouse.button_index('left'))
            return('engine Mouse cursor (%s, %s), left %s'):format(tostring(axis and axis.x),tostring(axis and axis.y),
                tostring(left))
        end)
        return ok and text or('engine Mouse unreadable: '..tostring(text))
    end
    -- Scrolls the native panel to `row` (the first visible row) and redraws it (its focus kept when still in view).
    function S.scroll_to(row,why)
        if not(S.shown and S.renderer=='native'and S.layout and S.layout.grid)then return false end
        local g=S.layout.grid
        row=math.max(0,math.min(row,g.totalRows-g.rows))
        if row==g.scroll then return false end
        S.scroll=row
        local world=world_module.open()
        local ok,view=false,nil
        if world then ok,view=pcall(selector.screen,world)end
        if not(ok and view and view.open)then return false end
        local focus=S.focus
        show(view,world,'scrolled ('..tostring(why)..')')
        if focus and S.layout and S.layout.tiles[focus]and S.layout.tiles[focus].visible then S.focus=focus;draw_focus()
        else S.focus=nil;track.hover=nil end
        return true
    end
    -- The engine mouse wheel this frame (the stingray.Mouse 'wheel' axis: + up), or 0; unavailable once, logged.
    local function wheel()
        local S_=rawget(_G,'stingray')
        local Mouse=S_ and S_.Mouse
        if type(Mouse)~='table'or track.noWheel then return 0 end
        local ok,v=pcall(function()return Mouse.axis(Mouse.axis_index('wheel'))end)
        if not ok or v==nil then
            track.noWheel=true
            log('mouse wheel unavailable ('..tostring(v)..'): the scrollbar track and the keys scroll the panel')
            return 0
        end
        local ok2,y=pcall(function()return v.y end)
        if not ok2 or type(y)~='number'then
            local ok3,_,y3=pcall(function()return S_.Vector3.to_elements(v)end)
            y=ok3 and y3 or 0
        end
        return y or 0
    end
    function S.mouse_tick(view)
        local mouse,why=input.mouse()
        if not mouse then
            if why~=track.mouseReason then track.mouseReason=why;log('mouse unavailable: '..tostring(why))end
            track.left=false
            return
        end
        track.mouseReason=nil
        local facts=engine_gui.diagnostics()or{}
        local res=facts.resolution
        if not res then return end
        local x,y=M.to_gui(mouse,res[1],res[2])
        local index,in_panel=M.hit(S.layout,x,y)
        if S.renderer=='native'and in_panel and S.layout.scrollbar then
            local w=wheel()
            if w~=0 then
                S.scroll_to(S.layout.grid.scroll+(w>0 and-1 or 1),'the mouse wheel')
                return
            end
        end
        local key=('%d,%d'):format(math.floor(x+0.5),math.floor(y+0.5))
        if key~=track.mouse then
            track.mouse=key
            if opts.focus and index~=track.hover then
                track.hover=index
                if index then
                    S.focus=index
                    draw_focus()
                elseif S.focus then
                    S.focus=nil
                    close('focus')
                    if S.renderer=='legacy'then draw_focus()end
                end
            end
        end
        local pressed=mouse.left and not track.left
        track.left=mouse.left
        if pressed and S.renderer=='native'then
            local row=M.scroll_hit(S.layout,x,y)
            if row~=nil then S.scroll_to(row,'the scrollbar');return end
        end
        if pressed and in_panel then
            log(('click at GUI (%.0f, %.0f) [client (%d, %d) of %d x %d; GUI %d x %d] on %s; %s'):format(x,y,mouse.x,mouse.y,
                mouse.w,mouse.h,res[1],res[2],index and('tile '..index..' ('..entries[index].id..')')or'no tile',
                engine_mouse()))
            if index then S.select_index(index,'click')end
        end
    end
    function S.cancel()
        if not opts.selection then return'selection is not enabled in this build'end
        local current=selector.state()
        if current and current.selected then
            S.handle=selector.restore(function(handle)
                -- The restore's repaint puts the native highlight on slot 0: back onto the edited slot.
                if handle.status=='restored'then
                    slot_focus.sync(function(sync)
                        if sync.status=='moved'then
                            log(('the native highlight is back on the edited slot %d'):format(sync.to))
                        elseif sync.status~='in step'then
                            log(('the native highlight was not put back on the edited slot: %s'):format(
                                tostring(sync.reason or sync.code)))
                        end
                    end)
                end
                if opts.on_selected then opts.on_selected(handle)end
            end)
            return'restoring the slot'
        end
        return S.clear_focus()
    end
    function S.status()
        local L=S.layout
        return('selector %s; panel %s%s; focus %s; icon test %s'):format(track.active and('open on slot '..tostring(track.slot))
            or'closed',S.shown and('shown ('..tostring(S.renderer)..' renderer)')or'hidden',
            S.shown and L and(' at '..rect_text(L.panel)..(' (%.3f px/unit)'):format(L.unit))or'',
            S.focus and(entries[S.focus].id..' (tile '..S.focus..')')or'none',S.iconTest and'on'or'off')
            ..('; GUI world %s; slot overlays %s'):format(M.WORLD,S.overlays and S.overlays.status()or'off')
    end
    -- The virtual slots' overlays on or off (development: off shows the untouched native slot icons underneath).
    function S.set_slot_overlays(on)
        if on and not S.overlays then S.overlays=overlay.virtual_slots()
        elseif not on and S.overlays then S.overlays.stop();S.overlays=nil end
        log('slot overlays '..(S.overlays and'on'or'off'))
        return S.overlays~=nil
    end
    function S.stop()
        S.watch.cancel()
        S.follower.cancel()
        if S.overlays then S.overlays.stop()end
        hide('stopped')
    end
    return S
end

return M
