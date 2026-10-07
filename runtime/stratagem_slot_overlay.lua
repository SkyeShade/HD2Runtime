-- Runtime icon overlays over native stratagem slot icons (development; docs/custom-stratagems.md, "Slot icon overlays";
-- live-proven by SlotOverlayProof 0.1.0, 2026-10-02). Not exported by api/hd2.lua and no public field reaches it.
-- VISUAL ONLY: nothing here writes game memory.
--
-- The four ship loadout slots and the mission HUD's stratagem list are the game's own element primitives drawn into
-- screen GUIs of the Ui World (research slotOverlay; not Noesis). Application.main_world is the Game World, under the
-- whole UI composite; a screen GUI created in the Ui World (worlds()[k], found by its index in the engine's world
-- array) is depth-sorted with the native GUIs by layer, so at a layer above the slot parts it draws over the slot icons
-- (and under Noesis). This module reads, every frame, the on-screen rectangle of a target slot's icon element
-- from the element's own size (+0x24) and world transform (the quad the native GUI draws; the slot icons have no
-- rotation), and draws a Runtime image over it, following the native icon's alpha (+0x54) and hiding while the native
-- primitive does not exist (+0x110 = -1). The native icon, its material and its texture are never touched.
--   ship:    icon = ui + panel0Widgets + slot * widgetStride + element (+0x380), ui = the loadout screen;
--   mission: icon = [game + hudRoot] + hudList + entries + k * entryStride + widget + icon, the HUD entry whose record
--            index (+0x3748) is the local record entry; only while the game mode is the mission HUD's and the HUD is set
--            up (the stratagem list of domains/stratagem_calldown.lua hud: the same root, list, stride and index).
-- Every read happens only after the selector's pins (these offsets' code included) are proven on the loaded build.
--
-- The proven icon technique is shared with every context that shows a Runtime stratagem icon (these overlays and the
-- custom stratagems panel's tiles, runtime/custom_stratagem_panel.lua), so the art has one colour treatment everywhere:
--   M.open_gui:  a screen GUI in the Ui World;
--   M.draw_icon: a bitmap of the image's GUI material at a layer, on an opaque plate one layer below on exactly the
--                icon's quad, in the native icon background's colour (research slotBackground: the slot's grey box,
--                widget + 0x110, a filled rectangle at layer 12; read live where a native slot is covered);
--   M.colour:    the icon shader's c0-c3 on this GUI's own instance of that material (stratagem_selector.icon_colours).
-- M.virtual_slots is the production follower: the overlays of the real virtual slots (stratagem_selector.virtual_slots)
-- aboard the ship. It replaces the borrowed-icon writes of runtime/stratagem_slot_icons.lua, which stays a documented
-- fallback that a caller must start itself.
local world_module=require('hd2runtime/runtime/event_world')
local selector=require('hd2runtime/runtime/stratagem_selector')
local engine_gui=require('hd2runtime/runtime/engine_gui')
local images=require('hd2runtime/runtime/image_resources')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local scheduler=require('hd2runtime/runtime/scheduler')
local conversion=require('hd2runtime/runtime/stratagem_slot_conversion')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/stratagem_selector')
local L,I,O=D.loadout,D.slotIcon,D.slotOverlay
local G=D.grid.element
local H=require('hd2runtime/domains/stratagem_calldown').hud
local M={}

local function log(text)log_module.emit('[HD2Runtime] slot overlay '..text)end
local function f32(world,at)
    local s=world.view.read(at,4)
    if not s then return nil end
    local ok,v=pcall(b.value,s,0,'f32')
    return ok and v or nil
end

-- The engine World value (from Application.worlds) whose World pointer is `pointer`, and its 1-based index; or nil and
-- why. Worlds are full userdata, so they are matched by position: Application.worlds lists the engine's world array in
-- order (exe 0x3F821F..0x3F8277), read here from the application ([exe+application] +worldArray, +worldCount).
function M.world_value(world,pointer)
    if not(pointer and pointer~=0)then return nil,'no such world'end
    if not world.exe then return nil,'the executable base is unknown'end
    local app=world.view.pointer(world.exe+O.application)
    local count=app and world.view.u32(app+O.worldCount)
    local array=app and world.view.pointer(app+O.worldArray)
    if not(count and array and count>0 and count<=64)then return nil,'the engine world list is unreadable'end
    local index
    for k=0,count-1 do
        local s=world.view.read(array+8*k,8)
        if not s then return nil,'the engine world list is unreadable'end
        if b.u32(s,0)+b.u32(s,4)*4294967296==pointer then
            if index then return nil,'the world is listed twice'end
            index=k+1
        end
    end
    if not index then return nil,'the world is not in the engine world list'end
    local S=rawget(_G,'stingray')
    if not(type(S)=='table'and type(S.Application)=='table'and engine_gui.callable(S.Application.worlds))then
        return nil,'stingray.Application.worlds is unavailable'
    end
    local ok,list=pcall(S.Application.worlds)
    if not(ok and type(list)=='table')then return nil,'Application.worlds failed'end
    if#list~=count then return nil,('Application.worlds lists %d worlds, the engine %d'):format(#list,count)end
    if list[index]==nil then return nil,'no world value at index '..index end
    return list[index],index
end
-- The Ui World's engine value (the world the game draws its loadout screen and HUD GUIs in), or nil and why.
function M.ui_world(world)
    local context=world.view.pointer(world.game+O.gameContext)
    local s=context and world.view.read(context+O.uiWorld,8)
    if not s then return nil,'the game context is unreadable'end
    return M.world_value(world,b.u32(s,0)+b.u32(s,4)*4294967296)
end

-- The on-screen rectangle of an image element: {x, y, w, h, alpha} in GUI pixels (bottom-left origin), or nil and why.
function M.rect(world,E)
    local primitive=world.view.u32(E+O.primitive)
    if primitive==nil then return nil,'the element is unreadable'end
    if primitive==0xFFFFFFFF then return nil,'the native icon is not drawn'end
    local m02,m20=f32(world,E+G.m02),f32(world,E+G.m20)
    if not(m02 and m20)or math.abs(m02)>1e-6 or math.abs(m20)>1e-6 then return nil,'the icon is rotated or unreadable'end
    local r=selector.element_rect(world,E)
    local alpha=f32(world,E+O.alpha)
    if not(r and alpha)then return nil,'the icon geometry is unreadable'end
    if not(r.w>0 and r.h>0 and r.w<4096 and r.h<4096)then return nil,'the icon has no plausible size'end
    if alpha<=0 then return nil,'the native icon is transparent'end
    r.alpha=math.min(1,alpha)
    return r
end

-- The ship loadout slot icon element for a slot (0-3), or nil and why.
function M.ship_icon(world,slot)
    local view=selector.screen(world)
    if not(view and view.open)then return nil,'the loadout screen is not open'end
    return view.ui+L.panel0Widgets+slot*L.widgetStride+I.element,view
end

-- The mission HUD stratagem list: {[record index] = {entry, widget, icon, type}}, or nil and why; type is the entry's
-- stratagem type (the calldown HUD's slot type, +0x374C). Read-only.
function M.hud_entries(world)
    local context=world.view.pointer(world.game+O.gameContext)
    local mode=context and world.view.u32(context+O.gameMode)
    if mode~=O.missionHudMode then return nil,'the mission HUD is not shown (game mode '..tostring(mode)..')'end
    local root=world.view.pointer(world.game+O.hudRoot)
    if not root then return nil,'the HUD root is unreadable'end
    local set_up=world.view.read(root+H.setUp,1)
    if not(set_up and set_up:byte()==1)then return nil,'the mission HUD is not set up'end
    local list=root+O.hudList
    local out={}
    for k=0,O.hudEntries-1 do
        local entry=list+O.entries+k*O.entryStride
        local index=world.view.u32(entry+O.entrySlot)
        local widget=entry+O.widget
        local kind=world.view.u32(entry+H.slots.type)
        if index==nil or kind==nil then return nil,'a HUD entry is unreadable'end
        if index<O.hudEntries then out[index]={entry=entry,widget=widget,icon=widget+O.hudIcon,type=kind}end
    end
    return out
end

-- The mission HUD icon element showing loadout slot `slot` (0-3): the slot-th loadout (non-granted) entry of the local
-- player's stratagem record, shown by the HUD entry whose record index is that entry's; or nil and why. Read-only.
function M.mission_icon(world,slot)
    local entries,why=M.hud_entries(world)
    if not entries then return nil,why end
    local record,_,rwhy=conversion.local_record(world)
    if not record then return nil,tostring(rwhy)end
    local n=0
    for _,entry in ipairs(record.entries)do
        if entry.granted==0 then
            if n==slot then
                local hud=entries[entry.index]
                if not hud then return nil,'no HUD entry shows record entry '..entry.index end
                if hud.type~=entry.type then
                    return nil,('the HUD entry shows type %d, the record entry is type %d'):format(hud.type,entry.type)
                end
                return hud.icon,hud
            end
            n=n+1
        end
    end
    return nil,'the loadout has no slot '..slot
end


-------------------------------------------------------------------------------------- the proven icon technique --
-- The native icon background's grey (research slotBackground: 36/255), for a plate with no live native colour.
M.PLATE={O.backgroundGrey,O.backgroundGrey,O.backgroundGrey}
-- The live colour of a native icon background element (its effective colour, +0x54: a, r, g, b) as {r, g, b} 0-255, or
-- nil and why (not drawn, transparent or unreadable).
function M.plate_colour(world,element)
    local primitive=world.view.u32(element+O.primitive)
    if primitive==nil then return nil,'the icon background is unreadable'end
    if primitive==0xFFFFFFFF then return nil,'the icon background is not drawn'end
    local a=f32(world,element+O.effectiveColour)
    if not(a and a==a)then return nil,'the icon background colour is unreadable'end
    if a<=0 then return nil,'the icon background is transparent'end
    local out={}
    for i=1,3 do
        local v=f32(world,element+O.effectiveColour+4*i)
        if not(v and v==v)then return nil,'the icon background colour is unreadable'end
        out[i]=math.floor(255*math.max(0,math.min(1,v))+0.5)
    end
    return out
end
-- A screen GUI in the Ui World, or nil and why.
function M.open_gui(world)
    local w,why=M.ui_world(world)
    if not w then return nil,'the Ui World: '..tostring(why)end
    return engine_gui.open({world=w,max_layer=O.maxLayer})
end
local function alpha_of(spec)return math.floor(255*math.max(0,math.min(1,spec.alpha or 1))+0.5)end
-- The shade over an icon's unlit parts (spec.shade = {lo, hi}: the lit band, fractions of the icon's height from its
-- top): {top, bottom}, each {y, h}, in pixels (bottom-left origin). The shade is the Runtime's own (a black rectangle at
-- M.SHADE of the icon's alpha), not the native look.
M.SHADE=0.6
local function shade_bands(spec)
    local lo,hi=spec.shade[1],spec.shade[2]
    return {y=spec.y+spec.h*(1-lo),h=spec.h*lo},{y=spec.y,h=spec.h*(1-hi)}
end
local function shade_colour(spec)return{math.floor(alpha_of(spec)*M.SHADE+0.5),0,0,0}end
-- One icon: spec = {material (a loaded GUI material's name), x, y, w, h (pixels, bottom-left origin), layer, alpha (0-1,
-- default 1), plate ({r, g, b} 0-255, or nil for none), shade ({lo, hi} or nil for none)}. The bitmap at the layer, then
-- the plate one layer below on the same quad, both with the icon's alpha, and the shade one layer above. Returns {icon,
-- plate, plateWhy, shadeTop, shadeBottom} (the engine ids; plate nil when none or refused) or nil and why (nothing
-- drawn).
function M.draw_icon(screen,spec)
    local a=alpha_of(spec)
    local id,why=screen.bitmap(spec.material,spec.x,spec.y,spec.layer,spec.w,spec.h,{a,255,255,255},{optional=true})
    if id==nil then return nil,tostring(why)end
    local ids={icon=id}
    if spec.plate then
        local p=spec.plate
        ids.plate,ids.plateWhy=screen.rect(spec.x,spec.y,spec.layer-1,spec.w,spec.h,{a,p[1],p[2],p[3]},{optional=true})
    end
    if spec.shade then
        local top,bottom=shade_bands(spec)
        local c=shade_colour(spec)
        ids.shadeTop=screen.rect(spec.x,top.y,spec.layer+1,spec.w,top.h,c,{optional=true})
        ids.shadeBottom=screen.rect(spec.x,bottom.y,spec.layer+1,spec.w,bottom.h,c,{optional=true})
    end
    return ids
end
-- Moves, resizes or fades a drawn icon, its plate and its shade to spec. true, or nil and why.
function M.move_icon(screen,ids,spec)
    local a=alpha_of(spec)
    local ok,why=screen.update_bitmap(ids.icon,spec.material,spec.x,spec.y,spec.layer,spec.w,spec.h,{a,255,255,255},
        {optional=true})
    if ids.plate and spec.plate then
        local p=spec.plate
        screen.update_rect(ids.plate,spec.x,spec.y,spec.layer-1,spec.w,spec.h,{a,p[1],p[2],p[3]},{optional=true})
    end
    if spec.shade and(ids.shadeTop or ids.shadeBottom)then
        local top,bottom=shade_bands(spec)
        local c=shade_colour(spec)
        if ids.shadeTop then screen.update_rect(ids.shadeTop,spec.x,top.y,spec.layer+1,spec.w,top.h,c,{optional=true})end
        if ids.shadeBottom then
            screen.update_rect(ids.shadeBottom,spec.x,bottom.y,spec.layer+1,spec.w,bottom.h,c,{optional=true})
        end
    end
    return ok,why
end
-- The icon shader's colours (c0-c3, from stratagem_selector.icon_colours) on this GUI's own instance of a material;
-- call it after a bitmap of that material was drawn in this GUI. true, or nil and why.
function M.colour(screen,material,colours)
    local instance,why=screen.material(material)
    if not instance then return nil,why end
    return screen.set_vectors(instance,colours)
end

------------------------------------------------------------------------------------------------- the follower --
local RETRY=60                 -- ticks before a target set with an image not loaded yet is tried again
local function same_colours(a,c)
    if#a~=#c then return false end
    for i=1,#a do for j=1,5 do if a[i][j]~=c[i][j]then return false end end end
    return true
end
local function moved(old,new)
    if math.abs(old.x-new.x)>0.25 or math.abs(old.y-new.y)>0.25 or math.abs(old.w-new.w)>0.25
        or math.abs(old.h-new.h)>0.25 or math.abs(old.alpha-new.alpha)>0.01 then return true end
    local p,q=old.plate,new.plate
    if(p==nil)~=(q==nil)then return true end
    if p~=nil and(p[1]~=q[1]or p[2]~=q[2]or p[3]~=q[3])then return true end
    local s,t=old.shade,new.shade
    if(s==nil)~=(t==nil)then return true end
    return s~=nil and(math.abs(s[1]-t[1])>0.002 or math.abs(s[2]-t[2])>0.002)
end
-- The follower: every frame, overlays every target opts.targets(world) returns: {key, icon (the native icon element's
-- address), label, image (a Runtime image handle; default opts.image), colours (default opts.colours), layer (default
-- opts.layer, else the overlay layer), plateElement (a native icon background element: the plate in its live colour)
-- or plate ({r, g, b}), shade ({lo, hi}: M.draw_icon)}; opts.backing ({a, r, g, b}) is a plate for every target without
-- one. A target that disappears, or stops being returned, loses its overlay at once. opts.quiet: the OVERLAY and
-- 'overlays removed' lines are not logged (a caller that logs its own placements). Returns S {status(), stop(), shown =
-- {[key] = rect}}.
function M.follow(opts)
    local S={shown={},layer=opts.layer or O.overlayLayer}
    local screen,drawn,keys_text=nil,{},nil
    local reasons={}
    local overlay_line            -- the last OVERLAY line (a rebuild drawing the same is not logged again)
    local function say(key,why,text)
        if reasons[key]~=why then
            reasons[key]=why
            if why~=nil then log(text)end
        end
    end
    local function close()
        if screen then screen.close()end
        screen,drawn,keys_text=nil,{},nil
    end
    local function spec_of(world,t)
        local plate
        if t.plateElement then
            local c,why=M.plate_colour(world,t.plateElement)
            say('plate '..tostring(t.key),why,('%s: the native icon background: %s; the plate takes the native grey')
                :format(t.label,tostring(why)))
            plate=c or M.PLATE
        elseif t.plate then plate=t.plate
        elseif opts.backing then plate={opts.backing[2],opts.backing[3],opts.backing[4]}end
        local r=t.rect
        return {material=t.material,x=r.x,y=r.y,w=r.w,h=r.h,layer=t.layer,alpha=r.alpha,plate=plate,shade=t.shade}
    end
    local function tick()
        local world=world_module.open()
        if not world then return end
        local proven,pwhy=selector.prove(world)
        say('proof',not proven and pwhy or nil,'not drawn: '..tostring(pwhy))
        local targets=proven and opts.targets(world)or{}
        local live={}
        for _,t in ipairs(targets)do
            local label=t.label or tostring(t.key)
            local r,why=M.rect(world,t.icon)
            say(t.key,r==nil and why or nil,('%s: no overlay: %s'):format(label,tostring(why)))
            if r then
                local image=t.image or opts.image
                live[#live+1]={key=t.key,label=label,rect=r,image=image,material=images.material_name(image),
                    colours=t.colours or opts.colours,layer=t.layer or S.layer,plateElement=t.plateElement,plate=t.plate,
                    shade=t.shade}
            end
        end
        table.sort(live,function(a,c)return tostring(a.key)<tostring(c.key)end)
        local parts={}
        for _,t in ipairs(live)do parts[#parts+1]=('%s=%s@%d'):format(tostring(t.key),t.material,t.layer)end
        local text=table.concat(parts,',')
        if#live==0 then
            if screen then
                close();S.shown={};overlay_line=nil
                if not opts.quiet then log('overlays removed')end
            end
            return
        end
        if S.retry then
            S.retry=S.retry-1
            if S.retry<=0 then S.retry,keys_text=nil,nil end
        end
        if text~=keys_text then
            -- The target set changed: a fresh GUI with one icon (and plate) per target and the colours on each material.
            -- A target whose image is not loaded is left out (logged) and the set is tried again later.
            close()
            local ready={}
            for _,t in ipairs(live)do
                local done,family=pcall(images.family,world.runtime,t.image)
                local why=not(done and family.complete)and tostring(done and family.reason or family)or nil
                say('image '..tostring(t.key),why,('%s: not drawn: the overlay image is not loaded: %s'):format(t.label,
                    tostring(why)))
                if why then S.retry=RETRY else ready[#ready+1]=t end
            end
            keys_text=text
            if#ready==0 then return end
            local s,why=M.open_gui(world)
            say('open',not s and why or nil,'not drawn: '..tostring(why))
            if not s then keys_text=nil;return end
            screen,drawn,keys_text,S.shown=s,{},text,{}
            local coloured,placed,layers,plated={},{},{},false
            for _,t in ipairs(ready)do
                do
                    local spec=spec_of(world,t)
                    local ids,iwhy=M.draw_icon(screen,spec)
                    if not ids then log(('%s: overlay bitmap refused: %s'):format(t.label,tostring(iwhy)))
                    else
                        if spec.plate and not ids.plate then
                            log(('%s: backing refused: %s'):format(t.label,tostring(ids.plateWhy)))
                        end
                        plated=plated or ids.plate~=nil
                        drawn[t.key]={ids=ids,spec=spec}
                        S.shown[t.key]=t.rect
                        layers[t.layer]=true
                        placed[#placed+1]=('%s at %.0f, %.0f, %.0f x %.0f'):format(t.label,t.rect.x,t.rect.y,t.rect.w,
                            t.rect.h)
                        if t.colours then
                            if coloured[t.material]==nil then
                                coloured[t.material]=t.colours
                                local set,swhy=M.colour(screen,t.material,t.colours)
                                if not set then log('overlay colours not set: '..tostring(swhy))end
                            elseif not same_colours(coloured[t.material],t.colours)then
                                log(('%s: other colours than an earlier overlay of the same image: drawn with the '
                                    ..'first'):format(t.label))
                            end
                        end
                    end
                end
            end
            local list={}
            for layer in pairs(layers)do list[#list+1]=layer end
            table.sort(list)
            local line=('OVERLAY: %d icon%s drawn over native slot icons (layer %s%s, the native icons untouched): %s')
                :format(#placed,#placed==1 and''or's',table.concat(list,'/'),plated and', on a backing plate'or'',
                table.concat(placed,'; '))
            if line~=overlay_line then
                overlay_line=line
                if not opts.quiet then log(line)end
            end
            return
        end
        -- Same targets: follow the native icons (position, size, alpha) and the native background's colour.
        for _,t in ipairs(live)do
            local d=drawn[t.key]
            if d then
                local spec=spec_of(world,t)
                if moved(d.spec,spec)then
                    M.move_icon(screen,d.ids,spec)
                    d.spec=spec
                    S.shown[t.key]=t.rect
                end
            end
        end
    end
    S.watch={status='active'}
    function S.watch.cancel()S.watch.status='cancelled'end
    function S.watch.tick()if S.watch.status=='active'then tick()end end
    scheduler.attach(S.watch)
    function S.status()
        local parts={}
        for key,r in pairs(S.shown)do parts[#parts+1]=('%s %.0f,%.0f %.0fx%.0f a%.2f'):format(tostring(key),r.x,r.y,r.w,
            r.h,r.alpha)end
        table.sort(parts)
        return#parts>0 and table.concat(parts,'; ')or'no overlay shown'
    end
    function S.stop()S.watch.cancel();close();S.shown={}end
    return S
end

------------------------------------------------------------------------------------------ the real virtual slots --
-- A mission HUD target for loadout slot `slot` (the HUD's own layer; no plate: the HUD entry's icon background is not
-- researched), or nil and why. Ready for the mission HUD; M.virtual_slots does not use it yet.
function M.mission_target(world,slot,image,colours)
    local icon,why=M.mission_icon(world,slot)
    if not icon then return nil,why end
    return {key='mission '..slot,icon=icon,image=image,colours=colours,layer=O.hudOverlayLayer,
        label='mission slot '..slot}
end
-- The production follower: aboard the ship, while the loadout screen is open, every slot of
-- stratagem_selector.virtual_slots() whose widget shows its token gets its definition's icon (display.icon), coloured
-- with the token's colour set as the native slot colours the token (stratagem_selector.icon_colours), on a plate of
-- that slot's own icon background (its live colour) on exactly the icon's quad; every other slot gets nothing. The
-- token is resolved by its stable id. In a mission nothing is drawn (the HUD's overlays are not activated). Returns the
-- follower (M.follow).
-- The stratagem type whose icon colour set a virtual slot shows: its definition's colour donor (display.colours: a
-- support custom stratagem takes a support stratagem's, blue), else its token's type, as the native slot colours that
-- stratagem. nil when the donor has no row.
function M.colour_type(world,definition,token_kind)
    local donor=definition.display.coloursId
    if not donor then return token_kind end
    return loadout.type_of(world,donor)
end
function M.virtual_slots()
    local types,colours,notes={},{},{}
    local function note(slot,why,text)
        if notes[slot]~=why then
            notes[slot]=why
            if why~=nil then log(text)end
        end
    end
    local function targets(world)
        local out={}
        local set=selector.virtual_slots()
        if not set then notes={};return out end
        local game=world_module.game_state(world)
        if not game or game.mission then return out end
        local ok,view=pcall(selector.screen,world)
        if not(ok and view and view.open)then return out end
        for slot=0,L.maxLoadoutEntries-1 do
            local entry=set.slots[slot]
            if not entry then notes[slot]=nil
            else
                local definition=virtual.get(entry.definition)
                local kind=types[entry.token]
                if kind==nil then kind=loadout.type_of(world,entry.token)or false;types[entry.token]=kind end
                if not definition then
                    note(slot,'definition',('slot %d: no overlay: no virtual stratagem %s'):format(slot,
                        tostring(entry.definition)))
                elseif not kind then
                    note(slot,'token',('slot %d: no overlay: the token %s has no type'):format(slot,tostring(entry.token)))
                elseif view.widgets[slot+1]~=kind then
                    note(slot,'shows '..tostring(view.widgets[slot+1]),('slot %d: no overlay: the slot shows type %s, '
                        ..'not the token (type %d)'):format(slot,tostring(view.widgets[slot+1]),kind))
                else
                    note(slot,nil)
                    local donor=definition.display.coloursId
                    local ckind=kind
                    if donor then
                        ckind=types[donor]
                        if ckind==nil then ckind=M.colour_type(world,definition,kind)or false;types[donor]=ckind end
                    end
                    local c=ckind and colours[ckind]
                    if ckind and c==nil then c=selector.icon_colours(world,ckind)or false;colours[ckind]=c end
                    local widget=view.ui+L.panel0Widgets+slot*L.widgetStride
                    out[#out+1]={key=slot,icon=widget+I.element,plateElement=widget+O.background,
                        image=definition.display.icon,colours=c or nil,layer=O.overlayLayer,
                        label=('slot %d (%s)'):format(slot,entry.definition)}
                end
            end
        end
        return out
    end
    return M.follow({targets=targets})
end

------------------------------------------------------------------------------------- other players' custom slots --
-- The loadout screen also draws each teammate's four stratagems (research/peer-messaging-F5FEE03DCFDB.json "panels";
-- research/docs/runtime-peer-messaging-F5FEE03DCFDB.md section 13): panel k = ui + base + k * stride, panel 0 the local
-- player, 1-3 teammates, each holding its player's peer id and record, its slot widgets at panel 0's offsets shifted by
-- the panel stride (the same repaint). Read-only: nothing here writes the game, the teammate's record is never touched.
local PANELS=require('hd2runtime/domains/peer_messaging').panels
local panels_proven
local function prove_panels(world)
    if panels_proven and panels_proven.key==world.key then return panels_proven.ok,panels_proven.why end
    local ok,why=true,nil
    for _,pin in ipairs(PANELS.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            ok,why=false,('game+%X changed (%s)'):format(pin.rva,pin.label)
            break
        end
    end
    panels_proven={key=world.key,ok=ok,why=why}
    return ok,why
end
-- Every player panel of the loadout screen, mapped by its OWN peer binding (panel + 0x1EE00), never by its index or the
-- machine's role: {panels = {[0..3] = {k, peer (hex) or nil (unbound), record, bound, owner (hex), local_flag, widgets
-- = {[0..3] = {address, type}}}}, by_peer = {[peer] = panel}, local_peer, duplicates = {[peer] = true}}, or nil and why.
-- The research has panel 0 as the local player and teammates from 1 [C], but a teammate panel is accepted by its peer
-- binding alone (live 2026-10-04: one direction drew, the other did not; the host log was not available): its record,
-- the slot panel's bound record and the record's owner are reported (REMOTE OVERLAY MAP), not required, and the
-- teammate's record does not have to hold anything yet. A peer bound to two panels is ambiguous (none of them is used).
function M.player_panels(world)
    local ok,why=prove_panels(world)
    if not ok then return nil,why end
    local view=selector.screen(world)
    if not(view and view.open and view.ui)then return nil,'the loadout screen is not open'end
    local P=PANELS
    local lo,hi=world_module.local_peer(world)
    if not lo then return nil,'this machine\'s peer id is unreadable'end
    local out={panels={},by_peer={},local_peer=world_module.peer_hex(lo,hi),duplicates={}}
    for k=0,P.count-1 do
        local panel=view.ui+P.base+k*P.stride
        local slot_panel=panel+P.slotPanel
        local raw=world.view.read(panel+P.peer,8)
        local p={k=k}
        if raw and raw~=string.rep('\0',8)then
            p.peer=world_module.peer_hex(b.u32(raw,0),b.u32(raw,4))
            p.record=world.view.pointer(panel+P.record)
            p.bound=world.view.pointer(slot_panel+P.boundRecord)
            local flag=world.view.read(slot_panel+P.localFlag,1)
            p.local_flag=flag and flag:byte()or nil
            local owner=p.record and p.record~=0 and world.view.read(p.record+P.recordOwner,8)
            p.owner=owner and world_module.peer_hex(b.u32(owner,0),b.u32(owner,4))or nil
            p.widgets={}
            for s=0,L.maxLoadoutEntries-1 do
                local w=slot_panel+P.widgets+s*P.widgetStride
                p.widgets[s]={address=w,type=world.view.u32(w+P.widgetType)}
            end
            if out.by_peer[p.peer]then out.duplicates[p.peer]=true else out.by_peer[p.peer]=p end
        end
        out.panels[k]=p
    end
    return out
end
-- The panel map as one line: 'panel 0 -> peer A (this machine), panel 1 -> peer B (record owner B, local flag 0), ...'.
function M.panel_map_text(map)
    local parts={}
    for k=0,PANELS.count-1 do
        local p=map.panels[k]
        if not(p and p.peer)then parts[#parts+1]=('panel %d -> none'):format(k)
        else
            parts[#parts+1]=('panel %d -> peer %s (%s; record owner %s, local flag %s%s)'):format(k,p.peer,
                p.peer==map.local_peer and'this machine'or'a teammate',tostring(p.owner),tostring(p.local_flag),
                p.bound~=p.record and', slot panel bound to another record'or'')
        end
    end
    return table.concat(parts,', ')
end
-- Every teammate panel (bound to another peer than this machine's, not ambiguous): {{k, peer, record, widgets}}, or nil
-- and why; and the ambiguous ones ({{k, peer, why}}).
function M.remote_panels(world)
    local map,why=M.player_panels(world)
    if not map then return nil,why end
    local out,rejected={},{}
    for k=0,PANELS.count-1 do
        local p=map.panels[k]
        if p.peer and p.peer~=map.local_peer then
            if map.duplicates[p.peer]then
                rejected[#rejected+1]={k=k,peer=p.peer,why='this player is bound to more than one panel'}
            else
                out[#out+1]={k=k,peer=p.peer,record=p.record,widgets=p.widgets}
            end
        end
    end
    return out,nil,rejected,map
end
-- The follower of teammates' custom picks (display only). THE AUTHORITY IS THE SYNCED TABLE: the native teammate slot
-- does not have to show the token (live 2026-10-04: aboard the ship a teammate's panel widgets read type 0 while that
-- player's record here held no slot yet; the game had not sent it). While the loadout screen is open, a teammate slot
-- gets the custom icon when:
--   * a panel is bound to that player (M.player_panels: the panel's OWN peer binding, whatever its index and whatever
--     this machine's role; one panel per player);
--   * that player is a compatible peer and its synced state says this slot holds a custom id registered here;
--   * the slot is visible: its icon box (the widget's background element, the 70-unit square the native icon fills)
--     is drawn with an alpha above 0 (a faded panel, e.g. while the stratagem grid is open, hides it).
-- It is drawn on exactly that box, coloured as this player's own slots colour it, whatever the native widget shows. The
-- teammate's record and every native element are never written. Logged: REMOTE OVERLAY MAP (every panel and its peer,
-- once when the screen opens and again when the map changes); REMOTE OVERLAY DRAWN (each teammate slot drawn, once per
-- placement); REMOTE OVERLAY REFUSED: peer P, slot N, reason R (once per reason). This player's own slots keep the
-- stricter rule of M.virtual_slots (the widget must show the token). source() -> {[peer] = {[0..3] = id or false}}:
-- every compatible teammate's synced slots (copies), or nil. Re-evaluated every frame, so a changed pick, a player
-- leaving, a lost compatibility or a closed screen removes the overlay.
function M.remote_slots(source)
    local types,colours,notes,drawn={},{},{},{}
    local map_line
    local function refused(peer,slot,why)
        local key=peer..' '..slot
        if why~=nil then drawn[key]=nil end
        if notes[key]~=why then
            notes[key]=why
            if why~=nil then log(('REMOTE OVERLAY REFUSED: peer %s, slot %d, reason %s'):format(peer,slot,why))end
        end
    end
    local function targets(world)
        local out={}
        local synced=source()
        -- No compatible teammate: nothing is read.
        if not synced or not next(synced)then notes,drawn,map_line={},{},nil;return out end
        local game=world_module.game_state(world)
        if not game or game.mission then map_line=nil;return out end
        local list,_,rejected,map=M.remote_panels(world)
        if not list then map_line=nil;drawn={};return out end   -- the screen is closed (or its code changed)
        local line=M.panel_map_text(map)
        if line~=map_line then
            map_line=line
            if log_module.sample('overlay.remote_map',4)then log('REMOTE OVERLAY MAP: '..line)end
        end
        local by_peer,bad={},{}
        for _,p in ipairs(list)do by_peer[p.peer]=p end
        for _,r in ipairs(rejected or{})do bad[r.peer]=r end
        local peers={}
        for peer in pairs(synced)do peers[#peers+1]=peer end
        table.sort(peers)
        for _,peer in ipairs(peers)do
            local slots,p=synced[peer],by_peer[peer]
            for s=0,L.maxLoadoutEntries-1 do
                local id=slots[s]
                local definition=id and virtual.get(id)
                local key=peer..' '..s
                if not id then refused(peer,s,nil);drawn[key]=nil
                elseif not p then
                    refused(peer,s,bad[peer]and('its loadout panel %d is not usable: %s'):format(bad[peer].k,
                        bad[peer].why)or'no panel of the loadout screen is bound to this player')
                elseif not definition then
                    refused(peer,s,id..' is not registered here (the native slot stays)')
                else
                    local w=p.widgets[s].address
                    local box=w+O.background
                    local r,why=M.rect(world,box)
                    if not r then
                        refused(peer,s,'the slot is not visible: '..(tostring(why):gsub('the native icon','its icon box')))
                    else
                        refused(peer,s,nil)
                        local placed=('%s@%d'):format(id,p.k)
                        if drawn[key]~=placed then
                            drawn[key]=placed
                            log(('REMOTE OVERLAY DRAWN: panel %d, peer %s, slot %d: %s at %.0f, %.0f, %.0f x %.0f (the native '
                                ..'slot shows type %s)'):format(p.k,peer,s,id,r.x,r.y,r.w,r.h,tostring(p.widgets[s].type)))
                        end
                        local token=definition.selection and definition.selection.tokenId
                        local kind=token and types[token]
                        if token and kind==nil then kind=loadout.type_of(world,token)or false;types[token]=kind end
                        local ckind=kind and(M.colour_type(world,definition,kind)or kind)
                        local c=ckind and colours[ckind]
                        if ckind and c==nil then c=selector.icon_colours(world,ckind)or false;colours[ckind]=c end
                        out[#out+1]={key=('remote %s slot %d'):format(peer,s),icon=box,plateElement=box,
                            image=definition.display.icon,colours=c or nil,layer=O.overlayLayer,
                            label=('remote %s slot %d (%s, panel %d)'):format(peer,s,id,p.k)}
                    end
                end
            end
        end
        return out
    end
    return M.follow({targets=targets})
end

------------------------------------------------------------------------- teammates' custom slots in a mission --
-- The mission HUD's teammate panels (shown while the stratagem key is held; research/teammate-hud-F5FEE03DCFDB.json,
-- domains/teammate_hud.lua): up to 3 panels in the HUD's squad container, each bound to its player by the player entity
-- it stores, each with 4 cards. A card shows ONE entry of this machine's copy of that player's stratagem record (by
-- index): every frame the native takes the entry's type to its StratagemInfo row's icon, and its cooldown to the card's
-- state and lit band. A custom stratagem's owner converts only its own copy of the entry, so this copy keeps the token
-- the owner's game sent (Orbital Precision Strike) until that game sends the record again (then the carrier). Read-only:
-- the record copy, the card and every native element are never written.
local TH=require('hd2runtime/domains/teammate_hud')
local THL=TH.layout
local teammate_proven
local function prove_teammate_hud(world)
    if teammate_proven and teammate_proven.key==world.key then return teammate_proven.ok,teammate_proven.why end
    local ok,why=true,nil
    for _,pin in ipairs(TH.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            ok,why=false,('game+%X changed (%s)'):format(pin.rva,pin.label)
            break
        end
    end
    teammate_proven={key=world.key,ok=ok,why=why}
    return ok,why
end
local function fraction(s,at)
    local ok,v=pcall(b.value,s,at,'f32')
    if not(ok and v==v)then return nil end
    return math.max(0,math.min(1,v))
end
-- The drawn cards of the teammate panels: {{k, entity, cards = {{j, icon (the icon element), entry (the record entry
-- index), type (the type it shows), state, band ({lo, hi}: its lit band, or nil)}}}} (panels without a drawn card left
-- out; none while the stratagem key is not held), or nil and why.
function M.teammate_cards(world)
    local ok,why=prove_teammate_hud(world)
    if not ok then return nil,why end
    local context=world.view.pointer(world.game+O.gameContext)
    local mode=context and world.view.u32(context+O.gameMode)
    if mode~=O.missionHudMode then return nil,'the mission HUD is not shown (game mode '..tostring(mode)..')'end
    local root=world.view.pointer(world.game+THL.hudSystem)
    if not root then return nil,'the HUD root is unreadable'end
    local set_up=world.view.read(root+THL.setUp,1)
    if not(set_up and set_up:byte()==1)then return nil,'the mission HUD is not set up'end
    local container=root+THL.missionHud+THL.container
    local out={}
    for k=0,THL.panelCount-1 do
        local panel=container+THL.panels+k*THL.panelStride
        local cards
        for j=0,THL.cardCount-1 do
            local card=panel+THL.cards+j*THL.cardStride
            local icon=card+THL.cardIcon
            local primitive=world.view.u32(icon+O.primitive)
            if primitive and primitive~=0xFFFFFFFF then
                local s=world.view.read(card+THL.cardEntry,THL.bandEnd+4-THL.cardEntry)
                if s then
                    local lo,hi=fraction(s,THL.bandStart-THL.cardEntry),fraction(s,THL.bandEnd-THL.cardEntry)
                    cards=cards or{}
                    cards[#cards+1]={j=j,icon=icon,entry=b.u32(s,0),type=b.u32(s,THL.cardType-THL.cardEntry),
                        state=b.u32(s,THL.cardState-THL.cardEntry),band=(lo and hi and lo<=hi)and{lo,hi}or nil}
                end
            end
        end
        if cards then out[#out+1]={k=k,entity=world.view.u32(panel+THL.panelEntity),cards=cards}end
    end
    return out
end
-- The loadout slot of each entry of a record (this machine's copy): {[entry index] = slot (0-3) or false (granted)}.
-- The loadout entries are the record's non-granted ones in index order (as custom_multiplayer reads first-seen records).
local function slots_of(entries)
    local list={}
    for _,e in ipairs(entries)do list[#list+1]=e end
    table.sort(list,function(a,c)return a.index<c.index end)
    local out,n={},0
    for _,e in ipairs(list)do
        if e.granted==0 then out[e.index]=n;n=n+1 else out[e.index]=false end
    end
    return out
end
M.TEAMMATE_REFRESH=30          -- ticks between re-reads of the teammates' record entries while a card is drawn
-- The follower of teammates' custom slots on the mission HUD's teammate panels (display only). THE AUTHORITY IS THE
-- MISSION'S FROZEN SYNCED TABLE: never a card's type (the token is a real stratagem a player may have picked). source()
-- -> synced, carriers: synced = {[peer] = {[0..3] = id or false}} (every other player's slots of the table frozen for
-- this mission), carriers = {[carrier type] = id} (the frozen carrier map); nil while custom multiplayer is not running
-- (nothing is read). A card gets the custom stratagem's icon when:
--   * its panel is bound to that player (the panel's own player entity, matched in the player list to a peer);
--   * the card's record entry is that player's loadout slot s and the table names a custom id registered here for s;
--   * the card shows that custom stratagem's token or its frozen carrier (anything else: refused, the native stays);
--   * the card's icon is drawn and not transparent (while the stratagem key is not held nothing is drawn).
-- It is drawn on exactly the card's icon quad (which also holds the card's frame and background), on the native slot
-- grey, coloured as this player's own slots colour it, with the card's own lit band followed by a shade over its unlit
-- part (cooling, unavailable). Every other card, every vanilla slot and this player's own HUD are untouched.
-- Logged quietly: TEAMMATE HUD OVERLAY DRAWN once per mission per player, slot and custom id; TEAMMATE HUD OVERLAY
-- REFUSED once per reason; showing and hiding (the stratagem key) is not logged.
function M.mission_remote_slots(source)
    local types,colours,notes,drawn={},{},{},{}
    local records={tick=nil,by_peer={}}
    local tick=0
    local function refused(peer,slot,why)
        local key=peer..' '..slot
        if notes[key]~=why then
            notes[key]=why
            if why~=nil then log(('TEAMMATE HUD OVERLAY REFUSED: peer %s, slot %d, reason %s'):format(peer,slot,why))end
        end
    end
    local function type_of(world,id)
        local kind=types[id]
        if kind==nil then kind=loadout.type_of(world,id)or false;types[id]=kind end
        return kind or nil
    end
    local function slots_by_peer(world)
        if records.tick and tick-records.tick<M.TEAMMATE_REFRESH then return records.by_peer end
        records.tick,records.by_peer=tick,{}
        for _,r in ipairs(conversion.records(world)or{})do
            if not r['local']then records.by_peer[r.peer]=slots_of(r.entries)end
        end
        return records.by_peer
    end
    local function targets(world)
        local out={}
        local synced,carriers,native=source()
        -- Custom multiplayer is not running (no mission, solo, or refused): nothing is read; the next mission starts over.
        if not synced or not next(synced)then
            types,colours,notes,drawn,records={},{},{},{},{tick=nil,by_peer={}}
            return out
        end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return out end
        tick=tick+1
        local panels,pwhy=M.teammate_cards(world)
        if not panels and pwhy and pwhy:find(' changed (',1,true)then
            -- Another build: the teammate HUD's code is not the researched one (logged once).
            if notes.proof~=pwhy then notes.proof=pwhy;log('TEAMMATE HUD OVERLAY REFUSED: not drawn: '..pwhy)end
        end
        if not(panels and panels[1])then return out end
        local entity_peer={}
        for _,p in ipairs(world_module.players(world))do
            if p.entity and not p['local']then entity_peer[p.entity]=p.peer end
        end
        local by_peer=slots_by_peer(world)
        local carrier_of={}
        for kind,id in pairs(carriers or{})do carrier_of[id]=kind end
        for _,panel in ipairs(panels)do
            local peer=entity_peer[panel.entity]
            local picks=peer and synced[peer]
            if picks then
                local map=by_peer[peer]
                for _,card in ipairs(panel.cards)do
                    local slot=map and map[card.entry]
                    local id=slot and picks[slot]
                    local definition=id and virtual.get(id)
                    if not slot then
                        -- A granted entry, or no record of that player here yet: not a loadout slot of the table.
                    elseif not id then refused(peer,slot,nil)   -- a vanilla slot: never touched
                    elseif not definition then refused(peer,slot,id..' is not registered here (the native card stays)')
                    else
                        local token=definition.selection and definition.selection.tokenId
                        local kind=token and type_of(world,token)
                        local carrier=carrier_of[id]
                        if not kind then
                            refused(peer,slot,('%s\'s token has no type here (the native card stays)'):format(id))
                        elseif card.type~=kind and card.type~=carrier then
                            refused(peer,slot,('the card shows type %s, neither %s\'s token (type %d) nor its frozen '
                                ..'carrier (type %s); the native card stays'):format(tostring(card.type),id,kind,
                                tostring(carrier)))
                        elseif card.type==carrier and native and native(card.type,id)then
                            -- r38: the carrier is presented as that custom stratagem on this machine: the native card
                            -- shows it (the carrier-in-slot probe); no overlay.
                            refused(peer,slot,nil)
                            local key=peer..' '..slot
                            if drawn[key]~='native '..id then
                                drawn[key]='native '..id
                                log(('TEAMMATE HUD NATIVE: panel %d, peer %s, slot %d (record entry %d): its carrier (type '
                                    ..'%d) is presented here as %s: the native card shows it; no overlay'):format(panel.k,
                                    peer,slot,card.entry,card.type,id))
                            end
                        elseif M.rect(world,card.icon)then
                            refused(peer,slot,nil)
                            local placed=('%s@%d'):format(id,panel.k)
                            local key=peer..' '..slot
                            if drawn[key]~=placed then
                                drawn[key]=placed
                                local r=M.rect(world,card.icon)
                                log(('TEAMMATE HUD OVERLAY DRAWN: panel %d, peer %s, slot %d (record entry %d): %s over the '
                                    ..'card showing type %d (its %s), at %.0f, %.0f, %.0f x %.0f; display only'):format(
                                    panel.k,peer,slot,card.entry,id,card.type,card.type==kind and'token'or'carrier',
                                    r and r.x or 0,r and r.y or 0,r and r.w or 0,r and r.h or 0))
                            end
                            local ckind=M.colour_type(world,definition,kind)or kind
                            local c=colours[ckind]
                            if c==nil then c=selector.icon_colours(world,ckind)or false;colours[ckind]=c end
                            out[#out+1]={key=('teammate %s slot %d'):format(peer,slot),icon=card.icon,plate=M.PLATE,
                                image=definition.display.icon,colours=c or nil,layer=O.hudOverlayLayer,
                                shade=card.band or{0,1},
                                label=('teammate %s slot %d (%s, panel %d)'):format(peer,slot,id,panel.k)}
                        end
                    end
                end
            end
        end
        return out
    end
    local S=M.follow({targets=targets,quiet=true})
    S.source=source
    return S
end
function M.reset_panels_for_tests()panels_proven=nil;teammate_proven=nil end
return M
