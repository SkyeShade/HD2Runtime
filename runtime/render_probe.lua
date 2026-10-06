-- The render-order probe (development; docs/custom-stratagems.md, "Render order"). Not exported by api/hd2.lua.
--
-- Can a Runtime GUI appear above the native (Noesis) loadout UI? The research says a screen GUI cannot: the game draws
-- its UI world through the viewport hud_world_ui_and_composite_layer, whose layer config draws the world's GUIs (the
-- transparent passes), THEN the Noesis UI into the same target, then composites it into the back buffer; a GUI layer
-- only orders primitives inside its own GUI. This probe tests that live. It draws only: nothing is written to game
-- memory, and every engine call goes through runtime/engine_gui.lua.
--
-- While the stratagem grid is open and still, it draws over up to four realized, fully visible native cards (N0..N3)
-- and in an empty screen area O (right of the loadout panels, where the 0.3.0 floating card was seen):
--   * TEST RECTANGLE: a red rectangle with a white edge and the text TEST RECTANGLE over N0 (layers 998-999);
--   * LAYERS: one retained GUI with one rectangle per layer (0, 21, 100, 900, 990; on request also 2000 and 10000, whose
--     render-side handling is unproven), as horizontal strips across N1, bottom to top, and as squares in O;
--   * GUI ORDER: retained GUIs created in the order A, B, C, D: A (magenta) then B (cyan) overlapping at layer 500 in
--     N2's top half, C (cyan) then D (magenta) in its bottom half; the same pairs in O;
--   * IMMEDIATE: an immediate GUI (create_screen_gui(world, 0, 0, 'immediate'), as the engine's performance HUD script
--     makes one) whose white rectangle over N3 and in O is drawn again every frame.
-- On request, OVERLAY WORLD: a script world rendered through the render config's 'overlay' viewport (its transparent
-- pass goes straight into the back buffer) from the engine's Lua render callback, with a green rectangle over N0's
-- lower half and in O. The research predicts it is overwritten by the game's UI composite, which is queued after it.
-- Every GUI, layer, rectangle and engine result is logged.
local engine_gui=require('hd2runtime/runtime/engine_gui')
local images=require('hd2runtime/runtime/image_resources')
local selector=require('hd2runtime/runtime/stratagem_selector')
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local D=require('hd2runtime/domains/stratagem_selector')
local R=D.render
local M={}

local function log(text)log_module.emit('[HD2Runtime] render probe '..text)end
M.LAYERS={0,21,100,900,990}
M.EXTENDED={R.experimentalLayers[1],R.experimentalLayers[2]}
local SETTLE=0.2                 -- seconds of stillness before drawing
local IMMEDIATE_FRAMES=3600      -- the immediate rectangles are drawn for at most this many frames per position
local OVERLAY_SECONDS=30         -- the overlay world is released after this long
local LAYER_COLOR={[0]={255,255,40,40},[21]={255,255,150,0},[100]={255,255,255,0},[900]={255,40,220,40},
    [990]={255,0,220,255},[2000]={255,70,100,255},[10000]={255,220,0,220}}
local MAGENTA,CYAN,RED,WHITE,GREEN,LABEL={255,255,0,255},{255,0,255,255},{255,230,20,20},{255,255,255,255},
    {255,0,230,60},{255,255,255,255}

local function inside(a,frame)
    return a.x>=frame.x-0.5 and a.y>=frame.y-0.5 and a.x+a.w<=frame.x+frame.w+0.5 and a.y+a.h<=frame.y+frame.h+0.5
end
local function rect_text(r)return('%.0f, %.0f, %.0f x %.0f'):format(r.x,r.y,r.w,r.h)end

-- Up to four realized native cards fully inside the list viewport, row by row: {{rect, row, column}}, and the grid; or
-- nil and the reason. Read-only.
function M.cards(world,view)
    local grid,why=selector.grid(world,view)
    if not grid then return nil,why end
    local rows={}
    for r,row in pairs(grid.rows)do
        local whole=#row>0
        for _,card in ipairs(row)do if not inside(card,grid.viewport)then whole=false end end
        if whole then rows[#rows+1]=r end
    end
    table.sort(rows)
    local out={}
    for _,r in ipairs(rows)do
        for c,card in ipairs(grid.rows[r])do
            if #out<4 then out[#out+1]={rect=card,row=r,column=c-1}end
        end
    end
    if #out==0 then return nil,'no native card is fully visible',grid end
    return out,grid
end

-- The empty area O: right of the loadout panels, its top 16% below the top of the screen (the 0.3.0 card's place).
function M.outside(width,height)
    local u=math.floor(math.min(height*0.06,width*0.29/8.5))
    return {x=math.floor(width*0.67),top=math.floor(height*0.84),unit=u}
end

-- A resource's residency; a lookup that raises (the type absent, the manager busy) counts as not loaded.
local function loaded(runtime,type_hex,name)
    local ok,result,why=pcall(images.loaded,runtime,type_hex,name)
    if not ok then return false,tostring(result)end
    return result,why
end
local function font_ready(runtime)
    local font_ok,why=loaded(runtime,D.font.type,D.font.name)
    local material_ok,material_why=loaded(runtime,D.font.materialType,D.font.name)
    if font_ok and material_ok then return true end
    return nil,'the engine font is not loaded: '..tostring(why or material_why)
end

-- Draws the four experiments. spec: {cards = M.cards, world = a listed world (default main_world), extended = also
-- layers 2000 and 10000}. Returns the probe {order (GUI creation order), lines (what was drawn), tick() (the immediate
-- rectangles, once per frame), close()} or nil and the reason (everything created is closed).
function M.draw(runtime,spec)
    local ready,why=font_ready(runtime)
    if not ready then return nil,why end
    local P={screens={},order={},lines={},frames=0,state='open'}
    local font=D.font.name
    local function open(name,opts)
        opts=opts or{}
        opts.world=spec.world
        local screen,open_why=engine_gui.open(opts)
        if not screen then error('GUI '..name..': '..tostring(open_why),0)end
        P.screens[#P.screens+1]=screen
        P.order[#P.order+1]=name
        return screen
    end
    local function need(screen,value,what)
        if value==nil then error(what..' was refused: '..tostring(screen.reason),0)end
        return value
    end
    local cards=spec.cards or{}
    local layers={}
    for _,layer in ipairs(M.LAYERS)do layers[#layers+1]=layer end
    if spec.extended then for _,layer in ipairs(M.EXTENDED)do layers[#layers+1]=layer end end
    local ok,err=pcall(function()
        -- The labels in O come first, in their own GUI.
        local labels=open('labels')
        local W,H=labels.width,labels.height
        local O=M.outside(W,H)
        local u,size=O.unit,math.max(12,math.floor(O.unit*0.32))
        local function label(text,x,y)need(labels,labels.text(text,font,size,font,x,y,999,LABEL),'a label')end
        local row1,row2,row3,row4=O.top-u-size*2,O.top-2*u-size*5,O.top-3*u-size*8,O.top-4*u-size*11
        label('RENDER ORDER PROBE: outside the native UI',O.x,O.top-size)
        -- TEST RECTANGLE over N0 and in O.
        local test=open('test')
        local function test_rect(r,text_size)
            need(test,test.rect(r.x,r.y,998,r.w,r.h,WHITE),'the test rectangle edge')
            local e=math.max(3,math.floor(r.w*0.03))
            need(test,test.rect(r.x+e,r.y+e,999,r.w-2*e,r.h-2*e,RED),'the test rectangle')
            need(test,test.text('TEST',font,text_size,font,r.x+e*2,r.y+r.h*0.55,999,WHITE),'the test text')
            need(test,test.text('RECTANGLE',font,text_size,font,r.x+e*2,r.y+r.h*0.25,999,WHITE),'the test text')
        end
        local o_test={x=O.x,y=row3,w=4*u,h=u}
        test_rect(o_test,size)
        if cards[1]then
            local r=cards[1].rect
            test_rect(r,math.max(12,math.floor(r.h*0.14)))
            P.lines[#P.lines+1]=('N0 TEST RECTANGLE over row %d column %d (%s), layers 998-999'):format(cards[1].row,
                cards[1].column,rect_text(r))
        end
        label('TEST RECTANGLE',O.x,row3+u+4)
        -- LAYERS over N1 and in O, in one GUI.
        local layer_gui=open('layers',{max_layer=spec.extended and 10000 or 999})
        for k,layer in ipairs(layers)do
            local x=O.x+(k-1)*math.floor(u*1.15)
            need(layer_gui,layer_gui.rect(x,row1,layer,u,u,LAYER_COLOR[layer]),'the layer '..layer..' square')
            label(tostring(layer),x,row1+u+4)
        end
        if cards[2]then
            local r=cards[2].rect
            local h=r.h/#layers
            for k,layer in ipairs(layers)do
                need(layer_gui,layer_gui.rect(r.x,r.y+(k-1)*h,layer,r.w,h,LAYER_COLOR[layer]),'the layer '..layer..' strip')
            end
            local names={}
            for _,layer in ipairs(layers)do names[#names+1]=tostring(layer)end
            P.lines[#P.lines+1]=('N1 LAYERS over row %d column %d (%s): strips bottom to top %s'):format(cards[2].row,
                cards[2].column,rect_text(r),table.concat(names,', '))
        end
        -- GUI ORDER over N2 and in O: A, B, C, D created in this order, the same layer.
        local pairs_o={{x=O.x,y=row2},{x=O.x+math.floor(u*2.6),y=row2}}
        local pairs_n
        if cards[3]then
            local r=cards[3].rect
            pairs_n={{x=r.x,y=r.y+r.h*0.5,w=r.w,h=r.h*0.5},{x=r.x,y=r.y,w=r.w,h=r.h*0.5}}
        end
        local function pair_rects(first,second,first_color,second_color,o,n)
            local a=open(first)
            need(a,a.rect(o.x,o.y,500,u,u,first_color),'GUI '..first)
            if n then need(a,a.rect(n.x+n.w*0.05,n.y+n.h*0.1,500,n.w*0.55,n.h*0.8,first_color),'GUI '..first)end
            local b=open(second)
            need(b,b.rect(o.x+u*0.5,o.y-u*0.3,500,u,u,second_color),'GUI '..second)
            if n then need(b,b.rect(n.x+n.w*0.4,n.y+n.h*0.1,500,n.w*0.55,n.h*0.8,second_color),'GUI '..second)end
        end
        pair_rects('A','B',MAGENTA,CYAN,pairs_o[1],pairs_n and pairs_n[1])
        pair_rects('C','D',CYAN,MAGENTA,pairs_o[2],pairs_n and pairs_n[2])
        label('A then B',pairs_o[1].x,row2+u+4)
        label('C then D',pairs_o[2].x,row2+u+4)
        if cards[3]then
            P.lines[#P.lines+1]=('N2 GUI ORDER over row %d column %d (%s): A (magenta, created first) and B (cyan, '
                ..'second) in the top half, C (cyan, first) and D (magenta, second) in the bottom half, all at layer '
                ..'500'):format(cards[3].row,cards[3].column,rect_text(cards[3].rect))
        end
        -- IMMEDIATE over N3 and in O, drawn every frame by tick().
        P.immediate=open('immediate',{mode='immediate'})
        P.immediateRects={{x=O.x+math.floor(u*4.6),y=row3,w=u,h=u}}
        if cards[4]then
            local r=cards[4].rect
            P.immediateRects[2]={x=r.x,y=r.y,w=r.w,h=r.h}
            P.lines[#P.lines+1]=('N3 IMMEDIATE over row %d column %d (%s): white, drawn every frame at layer 999'):format(
                cards[4].row,cards[4].column,rect_text(r))
        end
        label('IMMEDIATE',O.x+math.floor(u*4.6),row3+u+4)
        label('OVERLAY WORLD (F6)',O.x,row4+u+4)
        P.outside={x=O.x,top=O.top,unit=u,overlay={x=O.x,y=row4,w=4*u,h=u}}
        P.lines[#P.lines+1]=('O (outside the native UI, from x %d, top %d, unit %d px): the same layers, A/B and C/D, '
            ..'TEST RECTANGLE and IMMEDIATE'):format(O.x,O.top,u)
    end)
    if not ok then
        for _,screen in ipairs(P.screens)do screen.close()end
        return nil,tostring(err)
    end
    function P.tick()
        if P.state~='open'or not P.immediate then return end
        if P.frames>=IMMEDIATE_FRAMES then
            P.immediate.close();P.immediate=nil
            log('immediate rectangles stopped after '..IMMEDIATE_FRAMES..' frames')
            return
        end
        P.frames=P.frames+1
        for _,r in ipairs(P.immediateRects)do
            if P.immediate.rect(r.x,r.y,999,r.w,r.h,WHITE)==nil then
                log('immediate GUI dropped: '..tostring(P.immediate.reason))
                P.immediate=nil
                return
            end
        end
    end
    function P.close()
        for _,screen in ipairs(P.screens)do screen.close()end
        P.immediate,P.state=nil,'closed'
    end
    return P
end

-- The overlay world: a script world rendered through the 'overlay' viewport from the engine's Lua render callback,
-- with a green rectangle over the first card's lower half and in O. probe: a drawn probe (its outside area and world).
-- Returns {close(), state, renders} or nil and the reason.
function M.overlay_world(runtime,probe,cards)
    local ready,why=font_ready(runtime)
    if not ready then return nil,why end
    local unit_ok,unit_why=loaded(runtime,R.unitType,R.cameraUnit)
    local shading_ok,shading_why=loaded(runtime,R.shadingType,R.shading)
    if not(unit_ok and shading_ok)then
        return nil,'the camera unit or the shading environment is not loaded: '..tostring(unit_why or shading_why)
    end
    local original=rawget(_G,'render')
    if type(original)~='function'then
        return nil,'the engine render callback is not a Lua function ('..type(original)..')'
    end
    local W,world_why=engine_gui.script_world(R.overlayViewport)
    if not W then return nil,world_why end
    local screen,open_why=engine_gui.open({world=W.world})
    if not screen then W.release();return nil,open_why end
    local O={state='open',renders=0,world=W.world}
    local drawn,draw_why=pcall(function()
        local function need(v,what)if v==nil then error(what..' was refused: '..tostring(screen.reason),0)end end
        local o=probe.outside.overlay
        need(screen.rect(o.x,o.y,999,o.w,o.h,GREEN),'the overlay rectangle')
        need(screen.text('OVERLAY WORLD',D.font.name,math.max(12,math.floor(o.h*0.32)),D.font.name,o.x+6,o.y+o.h*0.35,
            999,WHITE),'the overlay text')
        if cards and cards[1]then
            local r=cards[1].rect
            need(screen.rect(r.x,r.y,999,r.w,r.h*0.4,GREEN),'the overlay card rectangle')
        end
    end)
    if not drawn then screen.close();W.release();return nil,tostring(draw_why)end
    local chained
    local function submit()
        if O.state~='open'then return end
        local ok,render_why=W.render()
        if ok then O.renders=O.renders+1 else O.state,O.reason='failed',render_why;log('overlay world failed: '..tostring(render_why))end
    end
    local function after(...)pcall(submit);return ...end
    chained=function(...)return after(original(...))end
    rawset(_G,'render',chained)
    function O.close()
        if rawget(_G,'render')==chained then rawset(_G,'render',original)end
        if O.state=='open'then O.state='closed'end
        screen.close()
        W.release()
        return true
    end
    return O
end

-- The live controller: draws while the stratagem grid is open and still, closes on movement and when the grid closes.
-- Returns {toggle_extended(), toggle_overlay(), status(), stop()}.
function M.controller()
    local C={extended=false}
    local track={open=false,signature=nil,stable=0,probe=nil,overlay=nil,overlayAge=0,world=nil,cards=nil,reason=nil}
    local function close_probe()
        if track.probe then track.probe.close();track.probe=nil end
    end
    local function close_overlay(reason)
        if track.overlay then
            local renders=track.overlay.renders
            track.overlay.close();track.overlay=nil
            log(('overlay world released (%s) after %d renders'):format(reason,renders))
        end
    end
    local function follow(dt)
        local world=world_module.open()
        if not world then return end
        local ok,view=pcall(selector.screen,world)
        if not(ok and view and view.open and view.gridOpen)then return end
        local cards,grid_or_why,grid=M.cards(world,view)
        local g=cards and grid_or_why or grid
        local signature=g and selector.grid_signature(g)or('unreadable:'..tostring(grid_or_why))
        if signature~=track.signature then
            track.signature,track.stable=signature,0
            close_probe()
            close_overlay('the grid moved')
            return
        end
        track.stable=track.stable+(dt or 0)
        if track.overlay then
            track.overlayAge=track.overlayAge+(dt or 0)
            if track.overlay.state~='open'or track.overlayAge>=OVERLAY_SECONDS then
                close_overlay(track.overlay.state~='open'and('failed: '..tostring(track.overlay.reason))or'timeout')
            end
        end
        if track.stable<SETTLE then return end
        if track.probe then track.probe.tick();return end
        if not cards then
            if grid_or_why~=track.reason then track.reason=grid_or_why;log('not drawn: '..tostring(grid_or_why))end
            return
        end
        if track.world==nil or engine_gui.index_of(track.world)==nil then
            local main,main_why=engine_gui.main_world()
            if not main then log('not drawn: '..tostring(main_why));return end
            track.world=main
        end
        local index,count=engine_gui.index_of(track.world)
        local _,main_index=engine_gui.main_world()
        local probe,why=M.draw(world.runtime,{cards=cards,world=track.world,extended=C.extended})
        if not probe then
            if why~=track.reason then track.reason=why;log('not drawn: '..tostring(why))end
            return
        end
        track.probe,track.cards,track.reason=probe,cards,nil
        local facts=engine_gui.diagnostics()or{}
        local res=facts.resolution
        log(('drawn for slot %d (scroll %.1f): in worlds()[%s] of %s (main_world: worlds()[%s]); GUI resolution %s; '
            ..'render callback %s; GUIs created in order: %s'):format(view.editedSlot,g.scroll,tostring(index),
            tostring(count),tostring(main_index),res and(tostring(res[1])..' x '..tostring(res[2]))or'?',
            type(rawget(_G,'render')),table.concat(probe.order,', ')))
        for _,line in ipairs(probe.lines)do log(line)end
    end
    C.watch=selector.watch(function(event,view)
        if event=='grid_opened'then
            track.open,track.signature,track.reason,track.world=true,nil,nil,nil
            log('the stratagem grid opened for slot '..tostring(view.editedSlot))
        elseif event=='grid_closed'or event=='closed'then
            if track.probe then log('removed (the '..(event=='closed'and'loadout screen'or'grid')..' closed)')end
            track.open=false
            close_probe()
            close_overlay(event=='closed'and'the loadout screen closed'or'the grid closed')
        end
    end)
    C.follower={status='active'}
    function C.follower.cancel()C.follower.status='cancelled'end
    function C.follower.tick(dt)if C.follower.status=='active'and track.open then follow(dt)end end
    scheduler.attach(C.follower)
    function C.toggle_extended()
        C.extended=not C.extended
        close_probe()
        track.signature=nil
        return C.extended and'layers 2000 and 10000 added (unproven render-side handling); redrawn when still'
            or'layers 2000 and 10000 removed'
    end
    function C.toggle_overlay()
        if track.overlay then close_overlay('F6');return'overlay world released'end
        if not track.probe then return'the overlay world needs the probe drawn first (open a grid and hold still)'end
        local world=world_module.open()
        if not world then return'no game world'end
        local O,why=M.overlay_world(world.runtime,track.probe,track.cards)
        if not O then log('overlay world not created: '..tostring(why));return'overlay world not created: '..tostring(why)end
        track.overlay,track.overlayAge=O,0
        local index,count=engine_gui.index_of(O.world)
        log(('overlay world created: worlds()[%s] of %s, viewport overlay, rendered from the Lua render callback; '
            ..'green OVERLAY WORLD over N0\'s lower half and in O; released after %d s'):format(tostring(index),
            tostring(count),OVERLAY_SECONDS))
        return'overlay world created'
    end
    function C.status()
        local overlay=track.overlay and(('overlay world %s, %d renders'):format(track.overlay.state,track.overlay.renders))
            or'no overlay world'
        return ('grid %s; probe %s%s; layers %s; %s'):format(track.open and'open'or'closed',
            track.probe and'drawn'or'not drawn',track.probe and(' ('..table.concat(track.probe.order,', ')..')')or'',
            C.extended and'0..10000'or'0..990',overlay)
    end
    function C.stop()
        C.watch.cancel()
        C.follower.cancel()
        close_probe()
        close_overlay('stopped')
    end
    return C
end

return M
