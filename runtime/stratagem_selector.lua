-- The Runtime-owned custom stratagem selector (development only; docs/custom-stratagems.md, "A Runtime-owned custom
-- stratagem selector"). Not exported by api/hd2.lua and no public field reaches it.
--
-- While the player prepares the loadout and the stratagem grid is open for a slot, the Runtime shows its own card for
-- each virtual stratagem (runtime/virtual_stratagems.lua): the Runtime image as the icon, the Runtime texts as name and
-- description. Selecting a card writes the definition's vanilla TOKEN into that slot of the local loadout record, the
-- record the game itself saves at launch (research/runtime-stratagem-ui-F5FEE03DCFDB.json):
--   * drawing: runtime/engine_gui.lua, the engine GUI subset a released mod uses in game (a screen GUI in the world
--     the game rendered last). The card's icon is the Runtime image's GUI material, by name (the lookup it was proven
--     against); the text uses the engine font core/performance_hud/monaco, whose bitmap-font shader two of the game's
--     own UI fonts use. Every value is validated first and any failure disables drawing;
--   * the selection: one guarded transaction in the loadout UI object: the slot's entry {type, uses} (and the count for
--     a new slot) and the local panel's cached record pointer cleared. The game's own per-frame bind then repaints the
--     four slot widgets from the record, so its later rebuilds from the widgets keep the entry. sync_loadout saves the
--     record at launch (save store, mission record, the whole loadout sent to the session);
--   * no hook or patch, and one native game-function call only: the game's own selection close (M.close_native), what
--     Back calls, made only when a Runtime selection filled the loadout; no account, catalogue, inventory, save-format
--     or StratagemInfo write. The save holds the vanilla token: Runtime keeps which slot is virtual in its own identity
--     record.
--
-- Guards (refused with nothing written): the game.dll and exe builds and the pinned code; aboard the ship, the loadout
-- screen open with the local record, the grid open for a stratagem slot, not ready, not launched; the panel bound to the
-- local record (with several players too: EXPERIMENTAL, runtime/multiplayer.lua; the write is this machine's own record
-- and sends no per-slot message: peers learn the token when the game sends the loadout itself); the
-- token catalogued, enabled, selectable, owned, unlimited and not a vehicle; the record's loadout entries contiguous.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local slot_conversion=require('hd2runtime/runtime/stratagem_slot_conversion')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local payload_module=require('hd2runtime/runtime/bombardment_payload')
local texts=require('hd2runtime/runtime/text_resources')
local images=require('hd2runtime/runtime/image_resources')
local engine_gui=require('hd2runtime/runtime/engine_gui')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local core_assets=require('hd2runtime/core/assets')
local D=require('hd2runtime/domains/stratagem_selector')
local ROWM=require('hd2runtime/domains/stratagem_slots').row
local M={}
local L,IN=D.loadout,D.input
local TABLE=profile.stratagem.table_rva
local VEHICLE_BITS=0x700000          -- StratagemInfo +0x104: exosuit, FRV and tank categories (the pick redirects them)
local REPAINT_TIMEOUT=3

local function log(text)log_module.emit('[HD2Runtime] stratagem selector '..text)end
local function signed(n)return n and n>=2147483648 and n-4294967296 or n end
local function u32(n)n=n%4294967296;return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end

local proven={}
function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha or D.source.exeSha256~=profile.exe_sha then
        return nil,'the selector research covers another game build'
    end
    if proven[world.key or world.game]then return true end
    for _,pin in ipairs(D.pins)do
        local base=pin.module=='exe'and world.exe or world.game
        if not world.view.proves(base+pin.rva,pin.hex)then
            return nil,'loadout screen code changed ('..pin.label..' at '..pin.module..'+'..string.format('%X',pin.rva)..')'
        end
    end
    proven[world.key or world.game]=true
    return true
end

---------------------------------------------------------------------------------------------- the screen (read) --
local function qword(world,at)
    local s=world.view.read(at,8)
    return s and b.u32(s,0)+b.u32(s,4)*4294967296
end
local function byte(world,at)local s=world.view.read(at,1);return s and s:byte()end
-- The loadout screen as the game holds it: {open=false} while no loadout UI exists; otherwise {open=true, ui, subState,
-- gridOpen, editedSlot, ready, launched, localIndex, players, record = {address, count, owner, entries = {{index,
-- address, type, uses}}}, widgets = {types of the local panel's four slots}, bound (its cached record pointer)}; or nil
-- and the reason when it reads inconsistently.
function M.screen(world)
    local owner=world.view.pointer(world.game+L.ownerGlobal)
    local ui=owner and qword(world,owner+L.root)
    if not owner or not ui or ui==0 then return {open=false}end
    local sub,edited,index=world.view.u32(ui+L.subState),world.view.u32(ui+L.editedSlot),world.view.u32(ui+L.localRecordIndex)
    local ready,launched=byte(world,ui+L.ready),byte(world,ui+L.launched)
    local selecting=byte(world,ui+L.selectionOpen)
    if not(sub and edited and index and ready and launched and selecting)then return nil,'the loadout screen is unreadable'end
    -- The stratagem grid is open only while a selection is open (ui+0x273990, set and cleared by the open and close
    -- handlers alone) for a stratagem slot: the sub-state 10 alone only means a stratagem slot is FOCUSED (recomputed
    -- every frame from the panel's focus), and the edited slot is -1 before the first selection.
    edited=signed(edited)
    local out={open=true,ui=ui,subState=sub,selecting=selecting~=0,
        gridOpen=selecting~=0 and sub==L.gridSubState and edited>=0 and edited<L.maxLoadoutEntries,
        slotFocused=sub==L.gridSubState,editedSlot=edited,ready=ready~=0,launched=launched~=0,localIndex=signed(index),
        players=0,widgets={}}
    for k=0,L.recordCount-1 do
        local id=qword(world,ui+L.records+k*L.recordStride+L.owner)
        if id==nil then return nil,'a loadout record is unreadable'end
        if id~=0 then out.players=out.players+1 end
    end
    out.widgetFlags={}
    for k=0,L.maxLoadoutEntries-1 do
        out.widgets[k+1]=world.view.u32(ui+L.panel0Widgets+k*L.widgetStride+L.widgetType)
        out.widgetFlags[k+1]=byte(world,ui+L.panel0Widgets+k*L.widgetStride+L.widgetFlags)
    end
    out.panelMode=world.view.u32(ui+L.panelMode)
    out.bound=qword(world,ui+L.panel0BoundRecord)
    if out.localIndex>=0 and out.localIndex<L.recordCount then
        local record=ui+L.records+out.localIndex*L.recordStride
        local count=world.view.u32(record+L.count)
        if not count then return nil,'the local record is unreadable'end
        local entries={}
        for k=0,math.min(count,L.maxLoadoutEntries)-1 do
            local at=record+L.entries+k*L.entryStride
            entries[#entries+1]={index=k,address=at,type=world.view.u32(at+L.entryType),
                uses=signed(world.view.u32(at+L.entryUses))}
        end
        out.record={address=record,count=count,owner=qword(world,record+L.owner),entries=entries}
    end
    return out
end
-- Every lobby player's loadout record the loadout screen holds (up to four: its owner and its slots' types), read-only:
-- {{index, owner (hex), local, count, types}}, or nil and why. What this machine shows of each player's selection.
function M.lobby_records(world)
    local view,why=M.screen(world)
    if not(view and view.open)then return nil,why or'the loadout screen is not open'end
    local out={}
    for k=0,L.recordCount-1 do
        local record=view.ui+L.records+k*L.recordStride
        local owner=world.view.read(record+L.owner,8)
        if not owner then return nil,'a loadout record is unreadable'end
        local lo,hi=b.u32(owner,0),b.u32(owner,4)
        if lo~=0 or hi~=0 then
            local count=world.view.u32(record+L.count)or 0
            local types={}
            for i=0,math.min(count,L.maxLoadoutEntries)-1 do
                types[#types+1]=world.view.u32(record+L.entries+i*L.entryStride+L.entryType)
            end
            out[#out+1]={index=k,owner=string.format('%08X%08X',hi,lo),['local']=k==view.localIndex,count=count,
                types=types}
        end
    end
    return out
end
local function signature(view)
    if not(view and view.open)then return'closed'end
    local parts={view.gridOpen and('grid'..view.editedSlot)or'overview'}
    for _,entry in ipairs(view.record and view.record.entries or{})do parts[#parts+1]=tostring(entry.type)end
    return table.concat(parts,',')
end

-------------------------------------------------------------------------------------- the native grid (read) --
-- Where the native stratagem cards are on screen, read exactly as the game's own hover test reads a GUI element
-- (research gridGeometry; the element contains-point test 0x144D320): its size (w, h) at +0x24 and its world transform,
-- so its rectangle is x = tx .. tx + m00*w + m20*h and y = ty .. ty + m02*w + m22*h, in screen pixels from the
-- bottom-left corner: the space the Runtime's screen GUI draws in. Only unrotated elements with a positive scale are
-- used. Nothing here writes.
local G=D.grid
local SC=G.scroll
local function f32(s,o)
    local n=b.u32(s,o)
    local exp=math.floor(n/8388608)%256
    if exp==255 then return nil end
    local sign=n>=2147483648 and-1 or 1
    if exp==0 then return sign*(n%8388608)*2^-149 end
    return sign*(1+(n%8388608)/8388608)*2^(exp-127)
end
local function element_rect(world,at)
    local s=world.view.read(at,0xA0)
    if not s then return nil end
    local E=G.element
    local w,h=f32(s,E.size),f32(s,E.size+4)
    local m00,m02,m20,m22,tx,ty=f32(s,E.m00),f32(s,E.m02),f32(s,E.m20),f32(s,E.m22),f32(s,E.tx),f32(s,E.ty)
    if not(w and h and m00 and m02 and m20 and m22 and tx and ty)then return nil end
    if math.abs(m02)>1e-4 or math.abs(m20)>1e-4 or m00<=0 or m22<=0 or w<=0 or h<=0 then return nil end
    return {x=tx,y=ty,w=m00*w,h=m22*h}
end
M.element_rect=element_rect
local function read_f32(world,at)
    local s=world.view.read(at,4)
    return s and f32(s,0)
end

-- The native details panel while a selection is open (research detailsPanel): the GUI element at ui+0x24B520, laid
-- out at 1024 x 400 units for a stratagem. Returns {rect (screen pixels, bottom-left origin), units = {w, h}, scale
-- (pixels per unit)} or nil and the reason. Its laid-out size must be exactly the stratagem layout and its pixels per
-- unit equal in both directions; read-only.
function M.details(world,view)
    if not(view and view.open and view.gridOpen)then return nil,'no stratagem selection is open'end
    local at=view.ui+L.details
    local s=world.view.read(at+G.element.size,8)
    local rect=element_rect(world,at)
    if not(s and rect)then return nil,'the details panel is unreadable'end
    local w,h=f32(s,0),f32(s,4)
    local units=L.detailsUnits
    if math.abs(w-units[1])>0.5 or math.abs(h-units[2])>0.5 then
        return nil,('the details panel is %.1f x %.1f units, not the stratagem layout'):format(w,h)
    end
    local sx,sy=rect.w/w,rect.h/h
    if math.abs(sx-sy)>math.max(sx,sy)*0.01 then return nil,'the details panel is not uniformly scaled'end
    return {rect=rect,units={w=w,h=h},scale=sy}
end

-- The native grid while it is open (research gridGeometry, gridScroll), all read as data:
--   viewport: the list frame on screen (395 x 528 units: the 528-unit viewport the rows scroll in);
--   rowCount, rowCards[r], heights[r] (each row's height in units: 85, plus its section header on a section's first
--   row), content (their sum), scroll (the offset, units from the content top), limit (the largest offset),
--   sections = {{first row, id (the stratagem category)}}, firstRow / realized (the realized row widgets),
--   rows = {[absolute row] = {card rects}}, cards = {every realized card rect}.
-- Returns it, or nil and the reason.
function M.grid(world,view)
    if not(view and view.open and view.gridOpen)then return nil,'the stratagem grid is not open'end
    local list=view.ui+G.list
    local rows,first=world.view.u32(list+G.rowCount),world.view.u32(list+G.firstRealizedRow)
    local realized,sections=world.view.u32(list+G.realizedRows),world.view.u32(list+G.sections)
    if not(rows and first and realized and sections)or rows>256 or realized>12 or sections>64 then
        return nil,'the grid is unreadable'
    end
    if rows==0 then return nil,'the grid is empty'end
    local viewport=element_rect(world,list)
    local content,scroll,limit=read_f32(world,list+SC.content),read_f32(world,list+SC.offset),read_f32(world,list+SC.limit)
    if not(viewport and content and scroll and limit)then return nil,'the grid frame is unreadable'end
    local out={viewport=viewport,rowCount=rows,firstRow=first,realized=realized,content=content,scroll=scroll,
        limit=limit,rowCards={},heights={},sections={},rows={},cards={}}
    local sum=0
    for r=0,rows-1 do
        local n,height=world.view.u32(list+G.rowCards+r*4),read_f32(world,list+SC.rowHeights+r*4)
        if not(n and height)or n<1 or n>G.cardsPerRow or height<SC.cell then return nil,'the grid layout is unreadable'end
        out.rowCards[r],out.heights[r]=n,height
        sum=sum+height
    end
    if math.abs(sum-content)>0.5 then return nil,'the row heights do not add up to the content height'end
    out.lastCards=out.rowCards[rows-1]
    for k=0,sections-1 do
        out.sections[k+1]={first=world.view.u32(list+G.sectionFirstRow+k*4),id=world.view.u32(list+SC.sectionIds+k*4)}
    end
    for r=0,realized-1 do
        local base=list+r*G.rowWidgetStride
        local n=world.view.u32(base+G.rowRealizedCards)
        if not n or n>G.cardsPerRow then return nil,'a realized row is unreadable'end
        local row={}
        for c=0,n-1 do
            local rect=element_rect(world,base+G.cardWidget+c*G.cardWidgetStride)
            if not rect then return nil,'a native card is unreadable'end
            row[c+1]=rect
            out.cards[#out.cards+1]=rect
        end
        out.rows[first+r]=row
    end
    return out
end

-- The last row of a section (k: 1-based), from the next section's first row.
local function section_last(grid,k)
    local nxt=grid.sections[k+1]
    return(nxt and nxt.first or grid.rowCount)-1
end
-- The Runtime card's cell, chosen from the layout alone (never from what is visible, so it does not move while
-- scrolling):
--   'end': the free cell after the final native card (its row has fewer than four cards);
--   'end-new-row': the final row is full: column 0 of a new row, only where the list can show it (content that does not
--     scroll, with room below); a scrolling list stops `padding` units below its content, less than a card, so it never
--     reaches a new row;
--   'section': the free cell at the end of the token's own category section;
--   'any-section': the free cell at the end of the last section that has one.
-- category: the token's stratagem category (StratagemInfo +0xB8), or nil. Returns {kind, row, column, newRow} or nil and
-- the limitation.
function M.target(grid,category)
    local last=grid.rowCount-1
    if grid.lastCards<G.cardsPerRow then return {kind='end',row=last,column=grid.lastCards,newRow=false}end
    local scrolls=grid.content>SC.viewport
    if not scrolls and grid.content+SC.cell<=SC.viewport then
        return {kind='end-new-row',row=grid.rowCount,column=0,newRow=true}
    end
    local function free(k)
        local row=section_last(grid,k)
        local n=grid.rowCards[row]
        if n and n<G.cardsPerRow then return {row=row,column=n,newRow=false}end
    end
    if category then
        for k,section in ipairs(grid.sections)do
            if section.id==category then
                local cell=free(k)
                if cell then cell.kind='section';return cell end
            end
        end
    end
    for k=#grid.sections,1,-1 do
        local cell=free(k)
        if cell then cell.kind='any-section';return cell end
    end
    return nil,('the final row is full and the list scrolls (it stops %d units below its content, less than a %d-unit '
        ..'card), and no section has a free cell'):format(SC.padding,SC.cell)
end

local function inside(a,frame)
    return a.x>=frame.x-0.5 and a.y>=frame.y-0.5 and a.x+a.w<=frame.x+frame.w+0.5 and a.y+a.h<=frame.y+frame.h+0.5
end
local function overlaps(a,c)
    return a.x<c.x+c.w-0.5 and c.x<a.x+a.w-0.5 and a.y<c.y+c.h-0.5 and c.y<a.y+a.h-0.5
end
-- The bottom of a cell in content units (from the content top): a row's cards sit above its 5-unit gap, below its
-- section header; a new row starts at the content end.
local function cell_bottom(grid,row,new_row)
    if new_row then return grid.content+SC.cell end
    local top=0
    for k=0,row-1 do top=top+grid.heights[k]end
    return top+grid.heights[row]-SC.gap
end
-- Where the target cell is on screen now, from the scroll offset and the native cards' own geometry. Every realized
-- native card is checked against the same model (its column, its row's content position, the scroll offset); any
-- disagreement over 1.5 px refuses. Returns {card, text (or nil), visible, reason (when not visible), target, scale,
-- pitch}, or nil and the reason.
function M.placement(grid,target)
    if not target then return nil,'no target cell'end
    local first=grid.cards[1]
    if not first then return nil,'no native card is realized'end
    local scale=first.h/SC.cell
    if math.abs(grid.viewport.h/SC.frame[2]-scale)>scale*0.01 then return nil,'the grid frame and its cards differ in scale'end
    local pitch=(SC.cell+SC.gap)*scale
    local size=SC.cell*scale
    -- The model: a card's bottom on screen = top of the viewport - (its content bottom - scroll) x scale + offset; its
    -- x = column 0 + column x pitch. The offset and column 0 come from the first realized card; every other must agree.
    local top=grid.viewport.y+grid.viewport.h
    local x0,offset
    for r,row in pairs(grid.rows)do
        for c,card in ipairs(row)do
            local model=top-(cell_bottom(grid,r,false)-grid.scroll)*scale
            if not offset then offset,x0=card.y-model,card.x-(c-1)*pitch end
            if math.abs(card.y-(model+offset))>1.5 or math.abs(card.x-(x0+(c-1)*pitch))>1.5
                or math.abs(card.w-size)>1.5 or math.abs(card.h-size)>1.5 then
                return nil,'the native cards do not match the grid model'
            end
        end
    end
    local y=top-(cell_bottom(grid,target.row,target.newRow)-grid.scroll)*scale+offset
    local card={x=x0+target.column*pitch,y=y,w=size,h=size}
    local out={card=card,target=target,scale=scale,pitch=pitch}
    if not inside(card,grid.viewport)then out.visible,out.reason=false,'outside the viewport';return out end
    for _,native in ipairs(grid.cards)do
        if overlaps(card,native)then out.visible,out.reason=false,'it would overlap a native card';return out end
    end
    out.visible=true
    -- The text: the free cells to its right (two or more); for the list's end, else the free row below when visible.
    local free=G.cardsPerRow-1-target.column
    local candidates={}
    if free>=2 then candidates[1]={x=card.x+pitch,y=card.y,w=(free-1)*pitch+size,h=size}end
    if target.kind=='end'or target.kind=='end-new-row'then
        candidates[#candidates+1]={x=x0,y=card.y-pitch,w=(G.cardsPerRow-1)*pitch+size,h=size}
    end
    for _,area in ipairs(candidates)do
        local clear=inside(area,grid.viewport)
        for _,native in ipairs(grid.cards)do if overlaps(area,native)then clear=false end end
        if clear then out.text=area;break end
    end
    return out
end
-- Coordinate calibration (development diagnostics): every stage from content units to the rectangle the Runtime GUI
-- draws, for up to three realized native cards in different rows and columns (fully inside the viewport) and for the
-- virtual cell. Stages: content (x from the frame's left edge, y the card's bottom from the content top, in units) ->
-- after scroll (y minus the scroll offset) -> the pure model on screen (frame top-left + units x scale) -> the native
-- card's own transform (the truth) -> the Runtime GUI rectangle (the same pixels: the Runtime draws in the space the
-- native transforms give). depth: the transform translation's middle component (+0x98; unproven, logged only). Returns
-- {scale, frameScale, frame, scroll, limit, content, samples = {{label, row, column, content, scrolled, model, native,
-- runtime, delta}}, virtual = {...} or nil}. target: the virtual cell when the placement refused (V is then the pure
-- model, unanchored). Read-only.
function M.calibration(world,view,grid,placement,target,why)
    local first=grid.cards[1]
    if not first then return nil,'no native card is realized'end
    local scale=first.h/SC.cell
    local frame=grid.viewport
    local top=frame.y+frame.h
    local pitch=(SC.cell+SC.gap)*scale
    local x0
    for _,row in pairs(grid.rows)do if row[1]and not x0 then x0=row[1].x end end
    local left=(x0-frame.x)/scale
    local list=view.ui+G.list
    local out={scale=scale,frameScale=frame.h/SC.frame[2],frame=frame,scroll=grid.scroll,limit=grid.limit,
        content=grid.content,leftUnits=left,samples={}}
    local function stage(label,r,c,new_row,native)
        local x_u,y_u=left+c*(SC.cell+SC.gap),cell_bottom(grid,r,new_row)
        local model={x=frame.x+x_u*scale,y=top-(y_u-grid.scroll)*scale,w=SC.cell*scale,h=SC.cell*scale}
        local item={label=label,row=r,column=c,content={x=x_u,y=y_u},scrolled={x=x_u,y=y_u-grid.scroll},model=model}
        if native then
            item.native=native
            item.runtime={x=native.x,y=native.y,w=native.w,h=native.h}
            item.delta={x=model.x-native.x,y=model.y-native.y}
            local base=list+(r-grid.firstRow)*G.rowWidgetStride+G.cardWidget+c*G.cardWidgetStride
            local s=world.view.read(base+G.element.tx+4,4)
            item.depth=s and f32(s,0)
        end
        return item
    end
    -- Rows fully inside the viewport, top to bottom.
    local visible={}
    for r,row in pairs(grid.rows)do
        local inside_all=#row>0
        for _,card in ipairs(row)do if not inside(card,frame)then inside_all=false end end
        if inside_all then visible[#visible+1]=r end
    end
    table.sort(visible)
    local picks={}
    if visible[1]then picks[#picks+1]={visible[1],0}end
    if#visible>=3 then
        local mid=visible[math.floor((#visible+1)/2)]
        picks[#picks+1]={mid,#grid.rows[mid]-1}
    end
    if#visible>=2 then
        local last=visible[#visible]
        picks[#picks+1]={last,math.min(1,#grid.rows[last]-1)}
    end
    for k,pick in ipairs(picks)do
        local r,c=pick[1],pick[2]
        out.samples[#out.samples+1]=stage('N'..(k-1),r,c,false,grid.rows[r][c+1])
    end
    local cell=placement and placement.target or target
    if cell then
        local v=stage('V',cell.row,cell.column,cell.newRow,nil)
        if placement then
            v.runtime={x=placement.card.x,y=placement.card.y,w=placement.card.w,h=placement.card.h}
            v.visible,v.reason=placement.visible,placement.reason
        else
            v.runtime={x=v.model.x,y=v.model.y,w=v.model.w,h=v.model.h}
            v.visible,v.reason=false,'the placement refused ('..tostring(why)..'); V is the unanchored model'
        end
        out.virtual=v
    end
    return out
end

-- A change detector: the layout, the scroll offset and the frame, to half a unit / pixel.
function M.grid_signature(grid)
    local function q(v)return math.floor(v*2+0.5)end
    local first=grid.cards[1]
    return table.concat({grid.rowCount,grid.lastCards,grid.firstRow,grid.realized,q(grid.content),q(grid.scroll),
        q(grid.viewport.x),q(grid.viewport.y),q(grid.viewport.w),q(grid.viewport.h),first and q(first.x)or'-',
        first and q(first.y)or'-'},':')
end

-- The game's menu actions triggered this frame ({up, down, left, right, back, select} = true), read as data. Read-only.
-- Not wired to the selector: the native grid reacts to the same actions, and no input can be consumed without a hook.
function M.menu_actions(world)
    local owner=world.view.pointer(world.game+IN.ownerGlobal)
    if not owner then return nil end
    local out={}
    for name,action in pairs(IN.menu)do
        if name~='group'then
            local at=owner+IN.states+(IN.menu.group*IN.groupActions+action)*IN.stride
            local s=world.view.read(at,1)
            if not s then return nil end
            out[name]=s:byte()~=0
        end
    end
    return out
end

-- Lifecycle: calls listener(event, view) on each change, with event 'opened', 'grid_opened', 'grid_closed',
-- 'record_changed' or 'closed'. Reads only; returns the watch (cancel()).
function M.watch(listener)
    local watch={status='active'}
    local last={open=false,grid=nil,record=nil}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick()
        if watch.status~='active'then return end
        local world=world_module.open()
        if not world then return end
        local ok,view=pcall(M.screen,world)
        if not ok or not view then return end
        local grid=view.open and view.gridOpen and view.editedSlot or nil
        local record=view.open and signature(view)or nil
        if not view.open then
            if last.open then listener('closed',view)end
        else
            if not last.open then listener('opened',view)end
            if last.grid~=grid then
                if last.grid~=nil then listener('grid_closed',view)end
                if grid~=nil then listener('grid_opened',view)end
            end
            if last.open and record~=last.record then listener('record_changed',view)end
        end
        last={open=view.open,grid=grid,record=record}
    end
    scheduler.attach(watch)
    return watch
end

------------------------------------------------------------------------------------------- the engine renderer --
-- Draws cards through runtime/engine_gui.lua (the engine GUI subset a released mod uses in game). Retained mode: the card
-- is created once when shown and the GUI destroyed when hidden. Before anything is drawn: the engine font and every card
-- icon must be loaded, every text printable.
--   * Required, in order: the screen GUI, each card's background rectangle, its icon bitmap, its name and its
--     description. If one fails, the GUI is destroyed and the renderer is disabled for the session.
--   * Optional: the focus frame (opts.focus_frame), a Runtime rectangle behind the focused card, recoloured when the
--     focus moves. If it cannot be created or updated, "focus frame unavailable" is logged once, the frame is dropped
--     and the card stays drawn.
-- Nothing is written to game memory.
local CARD={x=0.67,top=0.16,w=0.29,h=0.15,gap=0.01,icon=0.11,name=0.024,description=0.018}
local FRAME_ON,FRAME_OFF,BACK={255,255,232,0},{0,255,232,0},{230,12,12,12}
local NAME,DESCRIPTION,WHITE={255,255,232,0},{255,220,220,220},{255,255,255,255}
local TILE_EDGE,TILE,LABEL={255,74,74,74},{255,24,24,24},{215,16,16,16}
local OPTIONAL={optional=true}
function M.engine_renderer(runtime,opts)
    opts=opts or{}
    -- opts.layer: the tile's base GUI layer (default 21; the tile uses it and the next two layers).
    local layer=type(opts.layer)=='number'and opts.layer%1==0 and opts.layer>=0 and opts.layer<=990 and opts.layer or 21
    local R={state='closed',drawn=0,focusFrame=opts.focus_frame==true and'pending'or'off'}
    local screen,frames
    local function fail(why)
        if screen then screen.close()end
        screen,frames=nil,nil
        R.state,R.reason='failed',why
        log('drawing disabled: '..why)
        return nil,why
    end
    local function must(value,why)
        if value==nil then error((screen and screen.reason)or why or'an engine GUI call failed',0)end
        return value
    end
    -- The optional focus frame is dropped (never fatal): logged once, the card stays.
    local function drop_frame(why)
        frames=nil
        if R.focusFrame~='unavailable'then
            R.focusFrame,R.focusReason='unavailable',why
            log('focus frame unavailable ('..tostring(why)..'); the card stays drawn without it')
        end
        return true
    end
    -- cards: {{name, description, icon (Runtime image)}}; focus: index.
    -- placement (M.placement): draw the first card as a native-sized tile in that grid cell, its name and description in
    -- the placement's text area when it has one; without a placement, the cards float beside the grid.
    function R.show(cards,focus,placement)
        if R.state=='failed'then return nil,R.reason end
        if R.state=='shown'then return R.focus(focus)end
        local _,why=engine_gui.api()
        if why then return fail(why)end
        if type(cards)~='table'or#cards<1 or#cards>4 then return fail('one to four cards')end
        if placement and#cards~=1 then return fail('one card in a grid cell')end
        local font=D.font.name
        local font_ok,font_why=images.loaded(runtime,D.font.type,font)
        local material_ok,material_why=images.loaded(runtime,D.font.materialType,font)
        if not(font_ok and material_ok)then
            return fail('the engine font is not loaded: '..tostring(font_why or material_why))
        end
        for _,card in ipairs(cards)do
            local family=images.family(runtime,card.icon)
            if not family.complete then return fail('a card icon is not loaded: '..tostring(family.reason))end
        end
        local opened,open_why=engine_gui.open()
        if not opened then return fail(open_why)end
        screen=opened
        local geometry={}
        local ok,err=pcall(function()
            if placement then
                -- The native card's proportions (stratagem card style): card 80, inner frame 68, icon 51 units.
                local cell,area,card=placement.card,placement.text,cards[1]
                local unit=cell.w/G.card.size
                local inset=(G.card.size-G.card.inner)/2*unit
                local icon=G.card.icon*unit
                geometry[1]={x=cell.x-2,y=cell.y-2,w=cell.w+4,h=cell.h+4}
                must(screen.rect(cell.x,cell.y,layer,cell.w,cell.h,TILE_EDGE),'the card background was refused')
                must(screen.rect(cell.x+inset,cell.y+inset,layer+1,cell.w-2*inset,cell.h-2*inset,TILE),
                    'the card background was refused')
                must(screen.bitmap(images.material_name(card.icon),cell.x+(cell.w-icon)/2,cell.y+(cell.h-icon)/2,
                    layer+2,icon,icon,WHITE),'the card icon was refused')
                -- The name and description only where the placement found a free area (they are never forced).
                if area then
                    must(screen.rect(area.x,area.y,layer,area.w,area.h,LABEL),'the card text area was refused')
                    must(screen.text(card.name,font,area.h*0.2,font,area.x+area.h*0.12,area.y+area.h*0.58,layer+1,NAME),
                        'the card name was refused')
                    must(screen.text(card.description,font,area.h*0.14,font,area.x+area.h*0.12,area.y+area.h*0.26,
                        layer+1,DESCRIPTION),'the card description was refused')
                end
                return
            end
            local width,height=screen.width,screen.height
            local x,w,h=width*CARD.x,width*CARD.w,height*CARD.h
            local icon=height*CARD.icon
            for index,card in ipairs(cards)do
                -- Bottom-left origin: the first card's top edge sits CARD.top below the top of the screen.
                local y=height*(1-CARD.top)-h-(index-1)*(h+height*CARD.gap)
                geometry[index]={x=x-3,y=y-3,w=w+6,h=h+6}
                must(screen.rect(x,y,21,w,h,BACK),'the card background was refused')
                must(screen.bitmap(images.material_name(card.icon),x+h*0.1,y+(h-icon)/2,22,icon,icon,WHITE),
                    'the card icon was refused')
                must(screen.text(card.name,font,height*CARD.name,font,x+icon+h*0.25,y+h*0.62,22,NAME),
                    'the card name was refused')
                must(screen.text(card.description,font,height*CARD.description,font,x+icon+h*0.25,y+h*0.3,22,
                    DESCRIPTION),'the card description was refused')
            end
        end)
        if not ok then return fail(tostring(err))end
        R.state,R.drawn,R.cards='shown',R.drawn+1,#cards
        metrics.count('stratagem_selector.shown')
        if R.focusFrame=='pending'or R.focusFrame=='shown'then
            frames={}
            for index,box in ipairs(geometry)do
                local id,frame_why=screen.rect(box.x,box.y,20,box.w,box.h,FRAME_OFF,OPTIONAL)
                if id==nil then drop_frame(frame_why);break end
                frames[index]={id=id,x=box.x,y=box.y,w=box.w,h=box.h}
            end
            if frames then R.focusFrame='shown'end
        end
        return R.focus(focus)
    end
    -- Moves the focus. With the optional frame, only the focused card's frame is visible (its alpha).
    function R.focus(index)
        if R.state~='shown'then return nil,R.state end
        R.focused=index
        if not frames then return true end
        for k,frame in ipairs(frames)do
            local done,why=screen.update_rect(frame.id,frame.x,frame.y,20,frame.w,frame.h,
                k==index and FRAME_ON or FRAME_OFF,OPTIONAL)
            if not done then return drop_frame(why)end
        end
        return true
    end
    function R.close()
        if screen then screen.close()end
        screen,frames=nil,nil
        if R.state=='shown'then R.state='closed'end
        if R.focusFrame=='shown'then R.focusFrame='pending'end
        return true
    end
    return R
end

-- The smallest drawing proof: one rectangle, one text line and one image near the screen centre, until closed. spec:
-- {text = Runtime text, icon = Runtime image}. Returns the overlay ({calls, close()}) or nil and the reason. The engine
-- font and the icon must be loaded first. Writes nothing to game memory.
function M.overlay(runtime,spec)
    if type(spec)~='table'or not texts.issued(spec.text)or not images.issued(spec.icon)then
        return nil,'the overlay needs a Runtime text and a Runtime image'
    end
    local label=texts.text(spec.text,'us')
    local font=D.font.name
    local font_ok,font_why=images.loaded(runtime,D.font.type,font)
    local material_ok,material_why=images.loaded(runtime,D.font.materialType,font)
    if not(font_ok and material_ok)then return nil,'the engine font is not loaded: '..tostring(font_why or material_why)end
    local family=images.family(runtime,spec.icon)
    if not family.complete then return nil,'the icon is not loaded: '..tostring(family.reason)end
    local screen,why=engine_gui.open()
    if not screen then return nil,why end
    local w,h=screen.width,screen.height
    local x,y,bw,bh=w*0.35,h*0.42,w*0.3,h*0.16
    local icon=bh*0.8
    local steps={function()return screen.rect(x,y,30,bw,bh,{220,20,20,20})end,
        function()return screen.bitmap(images.material_name(spec.icon),x+bh*0.1,y+bh*0.1,31,icon,icon,{255,255,255,255})end,
        function()return screen.text(label,font,h*0.03,font,x+bh,y+bh*0.45,31,{255,255,232,0})end}
    for index,step in ipairs(steps)do
        if step()==nil then
            local reason=screen.reason or({'the rectangle','the image','the text'})[index]..' was refused'
            screen.close()
            return nil,reason
        end
    end
    return {calls=screen.calls,close=screen.close,screen=screen}
end

---------------------------------------------------------------------------------------------- the selection --
-- The selections of the current loadout-screen visit, newest last (Ctrl+F7 undoes the newest): each {ui, record, index,
-- appended, old = {type, uses}, written (false when the slot already held the token), definition, token, previous
-- (the slot's virtual entry before this selection, or nil)}.
local history={}
-- The virtual slots: the Runtime's own record, never the save. {slots = {[slot] = {definition, token (stable id),
-- type}}, pairs = {stable ids in loadout order}}, or nil when no slot is virtual. Several slots may hold the same
-- definition: the definition is shared, the slot identity is separate.
local virtual_slots

local function job(body,callback)
    local handle={status='pending'}
    local co=coroutine.create(body)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        local ok,result,code,reason=coroutine.resume(co,dt)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then handle.status,handle.code,handle.reason='failed','SELECTOR_FAILED',tostring(result)
        elseif result then for key,value in pairs(result)do handle[key]=value end
        else handle.status,handle.code,handle.reason='refused',code,reason end
        if handle.status=='refused'or handle.status=='failed'then
            log('REFUSED (nothing written): '..tostring(handle.code)..': '..tostring(handle.reason))
        end
        if callback then callback(handle)end
    end
    scheduler.attach(watch)
    return handle
end
local function row(world,kind)
    return type(kind)=='number'and kind>0 and kind<150 and world.view.pointer(world.game+TABLE+kind*8)or nil
end
local function pairs_of(world,view)
    local out={}
    for _,entry in ipairs(view.record.entries)do out[#out+1]=loadout.id_of(world,entry.type)or 0 end
    return out
end
local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end

-- Whether the four slot widgets show exactly the record: widget k holds entry k's type for k below the count and is
-- empty after it. A native pick into a later slot with an empty one before it leaves a gap on screen (the widget takes
-- the type; the record is rebuilt compacted) until the next repaint: a write by record index would then land in another
-- slot than the player sees, so it is refused.
function M.widgets_mirror(view)
    local record=view and view.record
    if not record then return nil,'no local record'end
    for k=0,L.maxLoadoutEntries-1 do
        local entry=record.entries[k+1]
        local want=entry and entry.type or 0
        if view.widgets[k+1]~=want then
            return nil,('slot %d on screen (type %s) differs from the record (type %s): the slots have a gap; reopen the '
                ..'selector or pick natively'):format(k,tostring(view.widgets[k+1]),tostring(want))
        end
    end
    return true
end

-- What a slot may be written to hold (the token, or a carrier itself): its row enabled, selectable, unlimited, not a
-- vehicle, and owned. Returns its type, or nil, code, reason.
local function pick_checks(world,pick_id,pick_name)
    local token=loadout.type_of(world,pick_id)
    local trow=token and row(world,token)
    if not trow then return nil,'UNKNOWN_STRATAGEM','no row carries '..pick_name end
    if not(math.floor(world.view.u32(trow+ROWM.selectable)/ROWM.selectableBit)%2==1
            and world.view.u32(trow+ROWM.enabled)%2==1)then
        return nil,'TOKEN_NOT_SELECTABLE',pick_name..' is not an enabled, selectable stratagem'
    end
    if signed(world.view.u32(trow+ROWM.maxUses))~=-1 then
        return nil,'TOKEN_LIMITED',pick_name..' does not have unlimited uses'
    end
    if math.floor(world.view.u32(trow+0x104)/0x100000)%8~=0 then
        return nil,'TOKEN_VEHICLE','vehicle categories are redirected by the game\'s pick; not a token'
    end
    local is_owned=slot_conversion.owned(world,pick_id)
    if is_owned==nil then return nil,'UNAVAILABLE','the account catalogue is unreadable'end
    if not is_owned then return nil,'TOKEN_NOT_OWNED',pick_name..' is not owned'end
    return token
end
-- The checks before the write: the screen, the token, the slot. Returns view, target ({index, appended, old}) or nil,
-- code, reason.
local function check(world,definition,pick)
    local game=world_module.game_state(world)
    if game and game.mission then return nil,'IN_MISSION','the loadout is selected aboard the ship'end
    local view,why=M.screen(world)
    if not view then return nil,'UNAVAILABLE',why end
    if not view.open then return nil,'SCREEN_CLOSED','the loadout screen is not open'end
    if not view.record then return nil,'NO_RECORD','the local loadout record is not set'end
    if view.launched then return nil,'LAUNCHED','the loadout is already launched'end
    if view.ready then return nil,'READY','the player is ready; unready to change the loadout'end
    if not view.gridOpen or view.editedSlot<0 or view.editedSlot>=L.maxLoadoutEntries then
        return nil,'NO_SLOT','open the stratagem grid for a slot first'
    end
    -- Several players (EXPERIMENTAL, runtime/multiplayer.lua): the write is this machine's own loadout record only. It
    -- sends no per-slot message, so peers' loadout screens show this slot's token only once the game itself sends the
    -- loadout (rpc_sync_stratagems when the screen is left, sync_loadout at launch).
    if view.players>1 then require('hd2runtime/runtime/multiplayer').announce(view.players,'the loadout selection')end
    if view.bound~=view.record.address then
        return nil,'NOT_BOUND','the local panel is not bound to the local record'
    end
    local record=view.record
    if record.count>L.maxLoadoutEntries then return nil,'RECORD_SHAPE','the record holds '..record.count..' entries'end
    for _,entry in ipairs(record.entries)do
        if not entry.type or entry.type==0 then return nil,'RECORD_SHAPE','the loadout entries are not contiguous'end
    end
    local mirrors,mirror_why=M.widgets_mirror(view)
    if not mirrors then return nil,'SLOTS_DIFFER',mirror_why end
    -- What the slot will hold: the token, or (the carrier-in-slot probe, runtime/carrier_in_slot.lua) the carrier itself,
    -- under the same guards.
    local pick_id=pick and pick.id or definition.selection.tokenId
    local pick_name=pick and pick.name or definition.selection.token
    local token,code,reason=pick_checks(world,pick_id,pick_name)
    if not token then return nil,code,reason end
    -- An occupied slot is replaced (whatever it holds, a virtual slot included); a slot that already holds the token
    -- needs no write and only becomes (or stays) virtual.
    local slot=view.editedSlot
    local target
    if slot<record.count then
        local entry=record.entries[slot+1]
        target={index=slot,appended=false,old={type=entry.type,uses=entry.uses},same=entry.type==token}
    else
        if record.count>=L.maxLoadoutEntries then return nil,'RECORD_FULL','the loadout is full'end
        local at=record.address+L.entries+record.count*L.entryStride
        target={index=record.count,appended=true,old={type=world.view.u32(at+L.entryType),
            uses=signed(world.view.u32(at+L.entryUses))}}
        if target.old.type~=0 then return nil,'RECORD_SHAPE','the free entry is not empty'end
    end
    return view,target,token
end

-- The guarded transaction: the entry's type and uses (+ the count) and the bound record pointer cleared.
local function plan_for(world,view,target,desired_type,desired_uses,desired_count)
    local record=view.record
    local span_first=record.address+L.entries
    local span=L.count+4-L.entries
    local bound=view.ui+L.panel0BoundRecord
    local owner=owner_of(world,view.ui,L.panel0BoundRecord+0x20)
    if not owner or record.address+L.recordStride>owner.base+owner.size then return nil end
    local context=world.view.read(span_first,span)
    local around=world.view.read(bound,0x20)
    local who=world.view.read(record.address+L.owner,8)
    if not(context and around and who)then return nil end
    local function change(label,address,expected,desired)
        return {label=label,owner=owner,offset=address-owner.base,expected=expected,desired=desired,before=expected,
            already_desired=false,identity={component='LoadoutRecord',component_type='native',unique_owner=true,
            owner_count=1},chain={}}
    end
    local entry=record.address+L.entries+target.index*L.entryStride
    local changes={}
    if target.current_type~=desired_type then
        changes[1]=change('loadout.slot'..target.index..'.type',entry+L.entryType,u32(target.current_type),
            u32(desired_type))
    end
    if target.current_uses~=desired_uses then
        changes[#changes+1]=change('loadout.slot'..target.index..'.uses',entry+L.entryUses,u32(target.current_uses),
            u32(desired_uses))
    end
    if desired_count~=record.count then
        changes[#changes+1]=change('loadout.count',record.address+L.count,u32(record.count),u32(desired_count))
    end
    changes[#changes+1]=change('loadout.panel.bound_record',bound,u64(view.bound),u64(0))
    return {snapshots={{owner=owner,offset=record.address+L.owner-owner.base,bytes=who},
            {owner=owner,offset=span_first-owner.base,bytes=context},
            {owner=owner,offset=bound-owner.base,bytes=around}},changes=changes}
end
local function others_same(before,after,index)
    for k,entry in ipairs(before.record.entries)do
        local now=after.record.entries[k]
        if k-1~=index and not(now and now.type==entry.type and now.uses==entry.uses)then return false end
    end
    return true
end
-- Waits (inside a job) for the game's own repaint: the panel re-binds the record and the slot widget shows the type.
local function repainted(world,view,index,kind)
    local waited=0
    while waited<REPAINT_TIMEOUT do
        waited=waited+(coroutine.yield()or 0)
        local now=M.screen(world)
        if not(now and now.open and now.ui==view.ui)then return false,'the loadout screen closed'end
        if now.bound==view.record.address and now.widgets[index+1]==kind then return true end
    end
    return false,'the slots were not repainted within '..REPAINT_TIMEOUT..' s'
end

-------------------------------------------------------------------------------------------- the virtual slots --
local function slot_list(set)
    local out={}
    for slot in pairs(set and set.slots or{})do out[#out+1]=slot end
    table.sort(out)
    return out
end
local function slots_text(set)
    local parts={}
    for _,slot in ipairs(slot_list(set))do parts[#parts+1]=slot..' = '..set.slots[slot].definition end
    return #parts>0 and table.concat(parts,', ')or'none'
end
-- Marks one slot virtual (or plain, when entry is nil) and records the loadout order it was read in.
local function remember(slot,entry,pairs_now)
    virtual_slots=virtual_slots or{slots={},pairs={}}
    virtual_slots.slots[slot]=entry
    if pairs_now then virtual_slots.pairs=pairs_now end
    if next(virtual_slots.slots)==nil then virtual_slots=nil end
end
local function copy_entry(entry)
    return entry and{definition=entry.definition,token=entry.token,type=entry.type,carrier=entry.carrier}or nil
end

-- The first empty slot after `index` (index+1 .. 3; never wrapping to slot 0), or nil when every later slot is filled:
-- the native pick's own rule (research selectionAdvance, 0x146E619..0x146E660) restricted to the later slots: a slot
-- widget is empty when its type is 0 or above the last type, and one whose flags have the skip bit is passed over.
-- Read after the game's repaint, the widgets mirror the contiguous record, so this is the record's count when below 4.
function M.next_empty(view,index)
    if not(view and view.widgets and type(index)=='number')then return nil end
    for k=index+1,L.maxLoadoutEntries-1 do
        local kind,flags=view.widgets[k+1],view.widgetFlags and view.widgetFlags[k+1]or 0
        if kind and(kind==0 or kind>L.maxType)and math.floor(flags/L.widgetSkipBit)%2==0 then return k end
    end
    return nil
end

-- The icon shader's mask colours for a stratagem type, exactly as the native loadout slot sets them on its icon
-- element's material (research iconShader, 0x1893669..0x18936BF): c0 = the category colour of the type's colour set
-- (StratagemInfo +0xB8) from the game's table, c1 and c2 the game's constants, c3 zero (never set). Returns
-- {{'c0', s, r, g, b}, {'c1', ...}, {'c2', ...}, {'c3', 0, 0, 0, 0}} for engine_gui's set_vectors and the colour set,
-- or nil and why. Read-only; the caller proves the code first (M.prove).
local function vec4(world,at)
    local s=world.view.read(at,16)
    if not s or#s~=16 then return nil end
    local out={}
    for i=0,3 do
        local v=f32(s,i*4)
        if not(v and v==v and v>=-16 and v<=16)then return nil end
        out[#out+1]=v
    end
    return out
end
function M.icon_colours(world,kind)
    local C=D.iconColours
    local trow=row(world,kind)
    if not trow then return nil,'no StratagemInfo row for type '..tostring(kind)end
    local set=world.view.u32(trow+0xB8)
    if not(set and set<C.sets)then return nil,'colour set '..tostring(set)..' is outside the table'end
    local c0,c1,c2=vec4(world,world.game+C.table+set*C.stride),vec4(world,world.game+C.c1),vec4(world,world.game+C.c2)
    if not(c0 and c1 and c2)then return nil,'the icon colours are unreadable'end
    return {{'c0',c0[1],c0[2],c0[3],c0[4]},{'c1',c1[1],c1[2],c1[3],c1[4]},{'c2',c2[1],c2[2],c2[3],c2[4]},
        {'c3',0,0,0,0}},set
end

-- Moves the open native selection on after a selection (opts.advance of M.select): when an empty slot follows the one
-- just written, one guarded u32 write of the edited slot (ui+0x281C) from the slot the selector was open for to it, as
-- the native pick does (0x146E6D4); nothing reads it each frame, so the next pick, native or Runtime, lands there and the
-- selection stays open. The native focus highlight and the grid's greying are applied only inside native calls and are
-- left as they are. With no empty slot after it nothing is written: the native close handler hides the grid through
-- element calls and the Back action cannot be injected as data (research selectionClose), so the selector stays open
-- for the player to close. Returns {status = 'advanced' | 'full' | 'refused', slot, from, reason, verified}.
local ADVANCE_TIMEOUT=1
function M.advance(world,view,handle)
    local from=handle.edited
    if handle.next==nil then
        return {status='full',from=from,reason='no empty slot after slot '..handle.index..': the native selector stays '
            ..'open (closing it needs the game\'s own close handler, a native UI call the Runtime does not make)'}
    end
    local now,why=M.screen(world)
    if not(now and now.open and now.ui==view.ui and now.record)then
        return {status='refused',from=from,reason='the loadout screen changed: '..tostring(why)}
    end
    if not(now.selecting and now.subState==L.gridSubState and now.editedSlot==from)then
        return {status='refused',from=from,reason=('the native selector is no longer open for slot %s (open %s, sub-state '
            ..'%s, edited slot %s)'):format(tostring(from),tostring(now.selecting),tostring(now.subState),
            tostring(now.editedSlot))}
    end
    if now.ready or now.launched then
        return {status='refused',from=from,reason='ready or launched'}
    end
    if now.panelMode~=0 then
        return {status='refused',from=from,reason='panel mode '..tostring(now.panelMode)..' (a native pick there closes)'}
    end
    local mirrors,mirror_why=M.widgets_mirror(now)
    if not mirrors then return {status='refused',from=from,reason=mirror_why}end
    local target=M.next_empty(now,handle.index)
    if target==nil then return {status='full',from=from,reason='no empty slot after slot '..handle.index}end
    local owner=owner_of(world,now.ui,L.panelMode+4)
    if not owner then return {status='refused',from=from,reason='the loadout UI is not in private read-write memory'}end
    local function snap(at,n)
        local bytes=world.view.read(at,n)
        return bytes and{owner=owner,offset=at-owner.base,bytes=bytes}or nil
    end
    -- The contexts: the selection byte, the panel mode, and the sub-state with the edited slot (the target) after it.
    local open_byte,mode,sub=snap(now.ui+L.selectionOpen,1),snap(now.ui+L.panelMode,4),snap(now.ui+L.subState,8)
    if not(open_byte and mode and sub)then return {status='refused',from=from,reason='the loadout UI is unreadable'}end
    local plan={snapshots={open_byte,mode,sub},changes={{label='loadout.selection.edited_slot',owner=owner,
        offset=now.ui+L.editedSlot-owner.base,expected=u32(from),desired=u32(target),before=u32(from),
        already_desired=false,identity={component='LoadoutScreen',component_type='native',unique_owner=true,
        owner_count=1},chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('stratagem_selector.transactions')
    if report.status~='APPLIED'then return {status='refused',from=from,reason='guard rejected: '..tostring(report.reason)}end
    -- The game's next frames: the selection still open, on the new slot.
    local waited,verified=0,false
    while waited<ADVANCE_TIMEOUT do
        waited=waited+(coroutine.yield()or 0)
        local later=M.screen(world)
        if not(later and later.open and later.ui==now.ui)then break end
        if later.selecting and later.subState==L.gridSubState and later.editedSlot==target then verified=true;break end
        if not later.selecting then break end
    end
    log(('ADVANCED: the native selector moved from slot %d to slot %d, the next empty slot (the edited slot ui+0x281C; '
        ..'%d write; non-target bytes unchanged %s; protection restored %s); still open on it: %s. The native slot '
        ..'highlight and the grid\'s greying are not moved (native calls only)'):format(from,target,report.writes,
        tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored),tostring(verified)))
    return {status='advanced',slot=target,from=from,report=report,verified=verified}
end

-- A native UI sound (runtime/ui_sound.lua, required when first used: it requires this module). Never raises: returns
-- the play's result, or {status = 'refused', code, reason} (logged; nothing else depends on it).
local function play_sound(key)
    local ok,result,code,reason=pcall(function()return require('hd2runtime/runtime/ui_sound').play(key)end)
    if ok and result then return result end
    if not ok then code,reason='FAILED',tostring(result)end
    log(('sound %s not played: %s: %s'):format(key,tostring(code),tostring(reason)))
    return {status='refused',code=code,reason=reason}
end
M.play_sound=play_sound

-- Closes the open native selection after a Runtime selection filled the loadout (the 'full' case of the advance),
-- exactly as Back on a stratagem slot and a native pick that fills the last slot do (research selectorClose): the
-- picker-close sound, then the game's own close handler 0x146F3B0(the loadout UI). One typed native UI call; no patch,
-- no hook, nothing written by the Runtime. Refused with nothing called (the selector stays open for Back) unless: the
-- adapter can call game functions; inside the Runtime's own update; the selector's pinned code and the handler's exact
-- first bytes; aboard the ship; the same loadout screen, its selection still open for the slot the selection was made
-- in (the selection byte set, sub-state 10, that edited slot); not ready or launched; solo; panel mode 0; the panel
-- bound to the local record and the slots showing it; the record full, the selection's token in its slot. Verified at
-- once (the selection byte and the sub-state 0, the card list empty) and on the game's next frames (the selection stays
-- closed on the same screen, every slot unchanged). handle: M.select's ({index, edited, token}). Returns {status =
-- 'closed' | 'not closed' | 'refused', from, code, reason, verify, verified, sound}.
M.CLOSE_SETTLE=0.25
function M.close_native(world,view,handle)
    local C=D.selectorClose
    local from=handle.edited
    local function refuse(code,reason)
        log(('SELECTOR CLOSE REFUSED (nothing called; the native selector stays open: close it with Back): %s: %s')
            :format(code,reason))
        return {status='refused',from=from,code=code,reason=code..': '..reason}
    end
    if not world.runtime.native_selector_close then
        return refuse('UNAVAILABLE','this Runtime adapter cannot call game functions')
    end
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    local proven,proof_why=M.prove(world)
    if not proven then return refuse('UNSUPPORTED_BUILD',tostring(proof_why))end
    if not world.view.proves(world.game+C.rva,C.prologue)then
        return refuse('UNSUPPORTED_BUILD',('the game\'s selection close changed (game+%X)'):format(C.rva))
    end
    local game=world_module.game_state(world)
    if not game or game.mission then return refuse('IN_MISSION','aboard the ship only')end
    local now,why=M.screen(world)
    if not(now and now.open and now.ui==view.ui and now.record)then
        return refuse('SCREEN_CHANGED','the loadout screen changed: '..tostring(why))
    end
    if not(now.selecting and now.subState==L.gridSubState and now.editedSlot==from)then
        return refuse('NOT_OPEN',('the selection is no longer open for slot %s (open %s, sub-state %s, edited slot %s)')
            :format(tostring(from),tostring(now.selecting),tostring(now.subState),tostring(now.editedSlot)))
    end
    if now.ready or now.launched then return refuse('READY','the player is ready or launched')end
    if now.panelMode~=0 then return refuse('PANEL_MODE','panel mode '..tostring(now.panelMode))end
    if now.bound~=now.record.address then return refuse('NOT_BOUND','the slots are not repainted from the record')end
    local mirrors,mirror_why=M.widgets_mirror(now)
    if not mirrors then return refuse('SLOTS_DIFFER',mirror_why)end
    if now.record.count<L.maxLoadoutEntries or M.next_empty(now,-1)~=nil then
        return refuse('NOT_FULL','an empty slot is left ('..now.record.count..' of '..L.maxLoadoutEntries..' filled)')
    end
    local entry=now.record.entries[handle.index+1]
    if not(entry and entry.type==handle.token)then
        return refuse('RECORD_CHANGED','slot '..tostring(handle.index)..' no longer holds the selection\'s token')
    end
    local list=now.ui+G.list
    local rows,cards=world.view.u32(list+G.rowCount),world.view.u32(list+G.cardCount)
    -- As Back does: the picker-close sound, then the close.
    local sound=play_sound('picker_close')
    metrics.count('stratagem_selector.native_closes')
    world.runtime.native_selector_close(world.game+C.rva,now.ui)
    local function same(v)
        if not(v and v.open and v.ui==now.ui and v.record and v.record.count==now.record.count)then return false end
        for k,e in ipairs(now.record.entries)do
            local x=v.record.entries[k]
            if not(x and x.type==e.type and x.uses==e.uses)then return false end
        end
        return true
    end
    local after=M.screen(world)
    local verify={selection=after~=nil and after.open==true and after.ui==now.ui and not after.selecting,
        subState=after~=nil and after.subState==C.subStateAfter,
        list=world.view.u32(list+G.rowCount)==C.rowCountAfter and world.view.u32(list+G.cardCount)==C.cardCountAfter,
        record=same(after),stays=false}
    -- The game's next frames: the selection stays closed on the same screen, every slot as it was.
    local waited,frames=0,0
    while waited<M.CLOSE_SETTLE do
        waited=waited+(coroutine.yield()or 0)
        frames=frames+1
        local later=M.screen(world)
        verify.stays=later~=nil and later.open==true and later.ui==now.ui and not later.selecting and same(later)
        if not verify.stays then break end
    end
    local all=verify.selection and verify.subState and verify.list and verify.record and verify.stays
    log(('SELECTOR CLOSE %s: the native selector (open for slot %d) %s by the game\'s own close handler (game+%X, '
        ..'the call Back makes) after the selection filled the loadout; picker-close sound %s; at once: selection byte '
        ..'cleared %s, sub-state 0 %s, card list emptied %s (rows %s, cards %s before), slots unchanged %s; over %d '
        ..'frame(s): still closed, same screen and slots %s'):format(all and'VERIFIED'or verify.selection and
        'NOT VERIFIED'or'NOT CLOSED',from,verify.selection and'closed'or'NOT closed',C.rva,
        sound.status=='played'and'played'or('not played ('..tostring(sound.code)..')'),tostring(verify.selection),
        tostring(verify.subState),tostring(verify.list),tostring(rows),tostring(cards),tostring(verify.record),frames,
        tostring(verify.stays)))
    -- 'closed' once the selection byte is cleared; a call that left the selection open reports so (open for Back).
    return {status=verify.selection and'closed'or'not closed',from=from,verify=verify,verified=all,sound=sound,
        reason=not verify.selection and'the close handler was called but the selection is still open'or nil}
end

-- Writes the definition's token into the slot the native selector is open for, replacing whatever the slot holds, and
-- records that slot as the definition's virtual instance. A job: 'pending', then 'selected' (or 'refused' / 'failed'
-- with code and reason). The handle carries {index, token, appended, written, report, verify, next (the next empty
-- slot, or nil), virtual (the collection), sound}; opts.sound plays the native pick sound after a successful selection;
-- opts.advance(world, view, handle) is called after it (the native selector's move to the next empty slot, or its
-- close).
function M.select(id,callback,opts)
    opts=opts or{}
    return job(function()
        local definition=virtual.get(id)
        if not definition then return nil,'UNKNOWN_DEFINITION','no virtual stratagem '..tostring(id)end
        local world,why=world_module.open()
        if not world then return nil,'UNAVAILABLE',tostring(why)end
        local ok,proof_why=M.prove(world)
        if not ok then return nil,'UNSUPPORTED_BUILD',tostring(proof_why)end
        -- opts.carrier = {id (stable id), name}: the carrier-in-slot probe writes the carrier itself.
        local carrier=opts.carrier
        local view,target,token=check(world,definition,carrier)
        if not view then return nil,target,token end
        target.current_type,target.current_uses=target.old.type,target.old.uses%4294967296
        local count=target.appended and view.record.count+1 or view.record.count
        local previous=virtual_slots and copy_entry(virtual_slots.slots[target.index])or nil
        local report,painted,paint_why
        local written=not(target.same and target.old.uses==-1)
        if written then
            local plan=plan_for(world,view,target,token,0xFFFFFFFF,count)
            if not plan then return nil,'RECORD_CHANGED','the loadout UI is not in private read-write memory'end
            report=transaction.apply(world.runtime,plan)
            metrics.count('stratagem_selector.transactions')
            if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
        else
            report={status='UNCHANGED',writes=0,non_target_bytes_unchanged=true,protection_restored=true}
        end
        history[#history+1]={ui=view.ui,record=view.record.address,index=target.index,appended=target.appended,
            old=target.old,written=written,definition=definition,token=token,previous=previous}
        local after=M.screen(world)
        local entry=after and after.record and after.record.entries[target.index+1]
        local verify={type=entry~=nil and entry.type==token and entry.uses==-1,count=after~=nil and after.record~=nil
            and after.record.count==count,others=after~=nil and after.record~=nil and others_same(view,after,target.index),
            nonTarget=report.non_target_bytes_unchanged==true,protection=report.protection_restored==true}
        if written then
            painted,paint_why=repainted(world,view,target.index,token)
        else
            painted=after~=nil and after.widgets[target.index+1]==token
            if not painted then paint_why='the slot widget does not show the token'end
        end
        verify.repainted=painted
        local final=M.screen(world)
        if final and final.record then
            remember(target.index,{definition=definition.id,token=carrier and carrier.id or definition.selection.tokenId,
                type=token,carrier=carrier and true or nil},pairs_of(world,final))
        end
        local text
        if written then
            text=('%s -> slot %d holds %s (type %d, '..(carrier and'the CARRIER itself: the carrier-in-slot probe'
                or'the token')..')%s: %d writes; the entry reads '..(carrier and'the carrier'or'the token')
                ..': %s; count %d: %s; '
                ..'every other entry unchanged: %s; the game repainted the slots from the record: %s%s; non-target bytes '
                ..'unchanged %s; protection restored %s; nothing else written (no save, account, catalogue or '
                ..'StratagemInfo write)'):format(definition.id,target.index,carrier and carrier.name
                or definition.selection.token,token,
                target.appended and''or(' replacing type '..tostring(target.old.type)),report.writes,tostring(verify.type),
                count,tostring(verify.count),tostring(verify.others),tostring(painted),
                painted and''or(' ('..tostring(paint_why)..')'),tostring(verify.nonTarget),tostring(verify.protection))
        else
            text=('%s -> slot %d already holds %s (type %d, %s, unlimited): no write; the slot is now virtual')
                :format(definition.id,target.index,carrier and carrier.name or definition.selection.token,token,
                carrier and'the carrier itself'or'the token')
        end
        log('SELECTED: '..text)
        log('virtual slots: '..slots_text(virtual_slots))
        -- opts.sound: the native pick sound, as the game's card list posts it for every pick (before the advance).
        local sound=opts.sound and play_sound('stratagem_pick')or nil
        local handle={status='selected',index=target.index,edited=view.editedSlot,token=token,appended=target.appended,
            written=written,report=report,verify=verify,virtual=virtual_slots,next=M.next_empty(final,target.index)}
        -- Compatibility: the slot's own identity (definition, slot, token, pairs).
        handle.identity=virtual_slots and{definition=definition.id,slot=target.index,token=definition.selection.tokenId,
            pairs=virtual_slots.pairs}or nil
        handle.sound=sound
        -- The advance may wait for the game (it yields inside this job), so it is not wrapped in pcall: it never raises.
        if opts.advance and final and final.open then handle.advance=opts.advance(world,final,handle)end
        return handle
    end,callback)
end

-- Undoes the newest selection of this visit (while the screen is open, the same record and the slot still holding the
-- token): the slot gets back what it held (an appended slot is removed again) and its virtual entry is what it was.
function M.restore_body()
    local last=history[#history]
    if not last then return nil,'NOT_SELECTED','nothing to restore'end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local ok,proof_why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(proof_why)end
    local view=M.screen(world)
    local entry=view and view.open and view.record and view.record.entries[last.index+1]
    if not(view and view.ui==last.ui and view.record and view.record.address==last.record and entry
            and entry.type==last.token)then
        history={}
        return nil,'GONE','the loadout changed; nothing to restore'
    end
    if view.ready or view.launched then return nil,'READY','the player is ready or launched'end
    if view.bound~=view.record.address then return nil,'NOT_BOUND','the local panel is not bound to the local record'end
    if last.appended and(view.record.count~=last.index+1)then
        return nil,'RECORD_CHANGED','the virtual slot is no longer the last entry'
    end
    local report,back
    if last.written then
        local target={index=last.index,current_type=entry.type,current_uses=entry.uses%4294967296}
        local count=last.appended and view.record.count-1 or view.record.count
        local plan=plan_for(world,view,target,last.old.type,last.old.uses%4294967296,count)
        if not plan then return nil,'RECORD_CHANGED','the loadout UI is not in private read-write memory'end
        report=transaction.apply(world.runtime,plan)
        if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
        local after=M.screen(world)
        back=after and after.record and(last.appended and after.record.count==last.index
            or(after.record.entries[last.index+1]and after.record.entries[last.index+1].type==last.old.type))
    else
        report={writes=0,non_target_bytes_unchanged=true,protection_restored=true}
        back=true
    end
    history[#history]=nil
    local after=M.screen(world)
    remember(last.index,last.previous,after and after.record and pairs_of(world,after)or nil)
    log(('RESTORED: slot %d back to %s: %d writes; exact: %s; non-target bytes unchanged %s; protection restored %s; '
        ..'virtual slots: %s'):format(last.index,last.appended and'empty'or('type '..tostring(last.old.type)),
        report.writes,tostring(back),tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored),
        slots_text(virtual_slots)))
    return {status='restored',index=last.index,report=report,exact=back==true,virtual=virtual_slots}
end
function M.restore(callback)return job(M.restore_body,callback)end

-- A stratagem's name from its stable id (the authoring catalogue).
local names_by_id
local function stratagem_name(id)
    if not names_by_id then
        names_by_id={}
        for name,entry in pairs(catalog.stratagems)do if entry.root and entry.root.id then names_by_id[entry.root.id]=name end end
    end
    return names_by_id[id]or('stable id '..tostring(id))
end
-- THE CARRIER MOVE (the carrier-in-slot probe 0.2.1, runtime/carrier_in_slot.lua; the user's rule of 2026-10-07: a
-- carrier slot never locks its carrier out of anyone's loadout; when anyone else picks it, the slot moves to its next
-- carrier before the mission). One virtual carrier slot of this player rewritten from its carrier to `to` = {id
-- (stable id), name}: the pick's own guarded loadout write (plan_for: the entry's type, the panel's cached record
-- pointer cleared, the game repaints), at the slot's own index, with the stratagem grid open or closed. Refused with
-- nothing written unless: aboard the ship, the loadout screen open with the local record bound, not ready, not
-- launched, the slots on screen mirror the record; the slot is a virtual CARRIER slot of `definition` whose record entry
-- reads exactly its carrier (type and stable id) with unlimited uses; `to` passes the pick's row checks and is in no
-- entry of the record (never a duplicate of a real pick). Only that entry's type changes; the virtual slot then records
-- the new carrier. Returns a job: 'moved' {slot, from, to, report, verify} or 'refused' / 'failed'.
function M.move_carrier(slot,definition,to,callback)
    return job(function()
        local world,why=world_module.open()
        if not world then return nil,'UNAVAILABLE',tostring(why)end
        local ok,proof_why=M.prove(world)
        if not ok then return nil,'UNSUPPORTED_BUILD',tostring(proof_why)end
        local game=world_module.game_state(world)
        if not(game and game.name=='Ship')then return nil,'NOT_ABOARD','a carrier slot moves aboard the ship only'end
        local view,vwhy=M.screen(world)
        if not view then return nil,'UNAVAILABLE',vwhy end
        if not view.open then return nil,'SCREEN_CLOSED','the loadout screen is not open'end
        if not view.record then return nil,'NO_RECORD','the local loadout record is not set'end
        if view.launched then return nil,'LAUNCHED','the loadout is already launched'end
        if view.ready then return nil,'READY','the player is ready; unready to let the slot move'end
        if view.bound~=view.record.address then return nil,'NOT_BOUND','the local panel is not bound to the local record'end
        local record=view.record
        if record.count>L.maxLoadoutEntries then return nil,'RECORD_SHAPE','the record holds '..record.count..' entries'end
        for _,entry in ipairs(record.entries)do
            if not entry.type or entry.type==0 then return nil,'RECORD_SHAPE','the loadout entries are not contiguous'end
        end
        local mirrors,mirror_why=M.widgets_mirror(view)
        if not mirrors then return nil,'SLOTS_DIFFER',mirror_why end
        local e=virtual_slots and virtual_slots.slots[slot]
        if not(e and e.carrier and e.definition==definition)then
            return nil,'NOT_CARRIER_SLOT',('slot %s is not a carrier slot of %s'):format(tostring(slot),tostring(definition))
        end
        local entry=record.entries[slot+1]
        if not(entry and entry.type==e.type and loadout.id_of(world,entry.type)==e.token and entry.uses==-1)then
            return nil,'SLOT_CHANGED',('slot %d no longer reads its carrier (type %s, unlimited)'):format(slot,
                tostring(e.type))
        end
        if type(to)~='table'or type(to.id)~='number'or type(to.name)~='string'then
            return nil,'BAD_SPEC','to = {id, name}'
        end
        if to.id==e.token then return nil,'SAME_CARRIER','the slot already holds '..to.name end
        local kind,code,reason=pick_checks(world,to.id,to.name)
        if not kind then return nil,code,reason end
        for _,other in ipairs(record.entries)do
            if other.type==kind then
                return nil,'CARRIER_IN_LOADOUT',('%s is already in loadout slot %d'):format(to.name,other.index)
            end
        end
        local target={index=slot,current_type=entry.type,current_uses=0xFFFFFFFF}
        local plan=plan_for(world,view,target,kind,0xFFFFFFFF,record.count)
        if not plan then return nil,'RECORD_CHANGED','the loadout UI is not in private read-write memory'end
        local report=transaction.apply(world.runtime,plan)
        metrics.count('stratagem_selector.transactions')
        if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
        local after=M.screen(world)
        local now=after and after.record and after.record.entries[slot+1]
        local verify={type=now~=nil and now.type==kind and now.uses==-1,count=after~=nil and after.record~=nil
            and after.record.count==record.count,others=after~=nil and after.record~=nil and others_same(view,after,slot),
            nonTarget=report.non_target_bytes_unchanged==true,protection=report.protection_restored==true}
        local painted,paint_why=repainted(world,view,slot,kind)
        verify.repainted=painted
        local final=M.screen(world)
        local from_name=stratagem_name(e.token)
        remember(slot,{definition=definition,token=to.id,type=kind,carrier=true},
            final and final.record and pairs_of(world,final)or nil)
        log(('MOVED (carrier-in-slot probe): virtual slot %d (%s): its carrier %s (type %d) -> %s (type %d): %d write%s; '
            ..'the entry reads the new carrier: %s; every other entry unchanged: %s; count unchanged: %s; the game '
            ..'repainted the slots from the record: %s%s; non-target bytes unchanged %s; protection restored %s; nothing '
            ..'else written (no save, account, catalogue or StratagemInfo write)'):format(slot,definition,from_name,e.type,
            to.name,kind,report.writes,report.writes==1 and''or's',tostring(verify.type),tostring(verify.others),
            tostring(verify.count),tostring(painted),painted and''or(' ('..tostring(paint_why)..')'),
            tostring(verify.nonTarget),tostring(verify.protection)))
        log('virtual slots: '..slots_text(virtual_slots))
        return {status='moved',slot=slot,from={id=e.token,type=e.type,name=from_name},to={id=to.id,type=kind,
            name=to.name},report=report,verify=verify,virtual=virtual_slots}
    end,callback)
end

-- The virtual slots (the Runtime's own record, never the save): {slots = {[slot] = {definition, token, type}},
-- pairs}, or nil when none.
function M.virtual_slots()return virtual_slots end
-- Unpicks a virtual definition: every virtual slot of `id` is dropped from the Runtime's own record. Nothing native is
-- written: those slots already hold the token, so each is plainly the token again (no conversion, no presentation, no
-- payload). Returns the dropped slots (sorted; empty when none).
function M.drop_virtual(id,reason)
    if not virtual_slots then return {}end
    local dropped,kept={},{}
    for slot,entry in pairs(virtual_slots.slots)do
        if entry.definition==id then dropped[#dropped+1]=slot else kept[slot]=entry end
    end
    if#dropped==0 then return dropped end
    table.sort(dropped)
    if next(kept)==nil then virtual_slots=nil else virtual_slots={slots=kept,pairs=virtual_slots.pairs}end
    log(('virtual slot%s %s (%s) UNPICKED: %s; %s the plain token again (nothing written); virtual slots: %s'):format(
        #dropped==1 and''or's',table.concat(dropped,', '),tostring(id),tostring(reason),#dropped==1 and'it is'
        or'they are',slots_text(virtual_slots)))
    return dropped
end
M.identity=M.virtual_slots
M.slots_text=slots_text
-- A copy of the virtual slots (the ship-scoped loadout state freezes it at the mission entry), or nil.
local function copy_set(set)
    if not set then return nil end
    local out={slots={},pairs={}}
    for slot,e in pairs(set.slots or{})do
        out.slots[slot]={definition=e.definition,token=e.token,type=e.type,carrier=e.carrier}
    end
    for k,id in ipairs(set.pairs or{})do out.pairs[k]=id end
    if next(out.slots)==nil then return nil end
    return out
end
function M.snapshot_virtual()return copy_set(virtual_slots)end
-- The deliberate lifecycle step (custom_stratagems' ship loadout state): the virtual slots become `set` (a copy; nil
-- clears them). Nothing native is written: those slots already hold their tokens. Logged with its reason.
function M.restore_virtual(set,reason)
    virtual_slots=copy_set(set)
    log(('virtual slots %s: %s'):format(virtual_slots and('restored ('..slots_text(virtual_slots)..')')or'cleared',
        tostring(reason)))
    return virtual_slots
end
-- Keeps the virtual slots in step with the loadout while the screen is open (other slots changed natively). Each
-- virtual slot is followed by position: when the order is the recorded one with entries changed in place, appended or
-- removed at the end, a slot that still holds its token stays virtual and one that does not is dropped; when exactly
-- one entry was removed (the game compacts the record), the later slots move down by one. Any other change drops
-- every virtual slot (never guessed). Only the loadout the player edits aboard the ship counts: in any other game
-- state (the mission, the transitions) and once the loadout is readied or launched, the loadout screen's record is the
-- game's, not the player's edit, and the identity is left as it is. A drop logs what the slot holds now. The caller
-- passes a settled record (the custom stratagems panel waits until it has not changed for a moment). Read-only.
local function order_text(ids)
    local out={}
    for k,id in ipairs(ids)do out[k]=id==0 and'empty'or stratagem_name(id)end
    return #out>0 and table.concat(out,'; ')or'none'
end
function M.track(world,view)
    if not(virtual_slots and view and view.open and view.record)then return virtual_slots end
    local game=world_module.game_state(world)
    if not(game and game.name=='Ship')then return virtual_slots end
    if view.ready or view.launched then return virtual_slots end
    local old,now=virtual_slots.pairs,pairs_of(world,view)
    if table.concat(now,',')==table.concat(old,',')then return virtual_slots end
    local map={}       -- old slot -> new slot
    local removed
    if #now==#old-1 then
        for k=1,#old do
            local rest={}
            for j=1,#old do if j~=k then rest[#rest+1]=old[j]end end
            if table.concat(rest,',')==table.concat(now,',')then removed=k-1;break end
        end
    end
    for slot in pairs(virtual_slots.slots)do
        if removed then
            if slot<removed then map[slot]=slot elseif slot>removed then map[slot]=slot-1 end
        else
            map[slot]=slot
        end
    end
    local kept={}
    for _,slot in ipairs(slot_list(virtual_slots))do
        local entry=virtual_slots.slots[slot]
        local to=map[slot]
        if to and now[to+1]==entry.token then
            kept[to]=entry
            if to~=slot then log(('virtual slot %d (%s) is now slot %d: the game removed slot %d'):format(slot,
                entry.definition,to,removed))end
        else
            log(('virtual slot %d (%s) no longer holds its token: %s; that slot is plain again (the loadout order was %s, '
                ..'now %s)'):format(slot,entry.definition,to and('it now holds '..(now[to+1]and order_text({now[to+1]})
                or'nothing'))or'the loadout changed in another way than one slot',order_text(old),order_text(now)))
        end
    end
    if next(kept)==nil then
        virtual_slots=nil
        log('no virtual slot remains')
        return nil
    end
    virtual_slots={slots=kept,pairs=now}
    log(('virtual slots kept: %s; the loadout order is now recorded as %s'):format(slots_text(virtual_slots),
        table.concat(now,', ')))
    return virtual_slots
end
-- Which slots of a saved loadout (stable ids in order) are virtual: when the saved order is the recorded one, every
-- recorded virtual slot holding its token, each with its own definition (duplicates stay separate instances). Returns
-- {[slot] = definition id} and their number, or nil (never guessed).
function M.reconstruct(saved)
    if not virtual_slots or type(saved)~='table'or#saved~=#virtual_slots.pairs then return nil end
    for k,id in ipairs(virtual_slots.pairs)do if saved[k]~=id then return nil end end
    local out,n={},0
    for slot,entry in pairs(virtual_slots.slots)do
        if saved[slot+1]~=entry.token then return nil end
        out[slot],n=entry.definition,n+1
    end
    return out,n
end
-- The selections of this visit: {selected (any to undo), count, last}.
function M.state()return {selected=#history>0,count=#history,last=history[#history]}end

-- The mission conversion's exact identity for one virtual definition (docs/custom-stratagems.md, "The custom
-- stratagem in a mission"), from the Runtime's own record only: the loadout slots holding instances of that definition
-- with its token, and the loadout order they were recorded in (stable ids). Returns the spec of
-- stratagem_slot_conversion.convert_virtual {definition, token, carrier, slots, order}, or nil and why. carrier
-- (optional) must be one of the definition's carriers; default its first. Read-only.
function M.conversion_spec(id,carrier)
    local definition=virtual.get(id)
    if not definition then return nil,'no virtual stratagem '..tostring(id)end
    if carrier~=nil and definition.mission.discover then
        -- A discovered carrier: any catalogued stratagem but the token and the excluded ones (the conversion re-checks
        -- every carrier guard).
        local entry=catalog.stratagems[carrier]
        if not(entry and entry.root)then return nil,tostring(carrier)..' is not a catalogued stratagem'end
        if entry.root.id==definition.selection.tokenId then return nil,'the token is never its own carrier'end
        for _,name in ipairs(definition.mission.exclude)do
            if name==carrier then return nil,carrier..' is excluded as a carrier of '..id end
        end
        if definition.payload then
            local fits,why=payload_module.compatible(carrier,definition.payload.donor)
            if not fits then
                return nil,carrier..' is not payload-compatible with '..definition.payload.donor..'\'s pattern: '
                    ..table.concat(why,'; ')
            end
        end
    elseif carrier~=nil then
        local listed=false
        for _,name in ipairs(definition.mission.carriers)do if name==carrier then listed=true end end
        if not listed then return nil,tostring(carrier)..' is not a carrier of '..id end
    elseif definition.mission.discover then
        return nil,'the carrier of '..id..' is discovered: name it'
    end
    if not virtual_slots then return nil,'no virtual slot'end
    local slots={}
    for _,slot in ipairs(slot_list(virtual_slots))do
        local entry=virtual_slots.slots[slot]
        if entry.definition==id and entry.token==definition.selection.tokenId then slots[#slots+1]=slot end
    end
    if#slots==0 then return nil,'no virtual slot holds '..id end
    local order={}
    for k,stable in ipairs(virtual_slots.pairs)do order[k]=stable end
    return {definition=id,token=definition.selection.token,carrier=carrier or definition.mission.carrier,slots=slots,
        order=order}
end
-- Read-only: the carrier discovery for a definition with mission.discover (stratagem_slot_conversion.discover_carriers:
-- every owned stratagem checked as a carrier, ranked; its excluded ones never chosen). present: a set of stable ids
-- (the saved loadout). Returns the discovery {ready, reason, candidates, chosen}.
function M.discover_carrier(id,present)
    local definition=virtual.get(id)
    if not definition then return {ready=false,reason='no virtual stratagem '..tostring(id),candidates={}}end
    if not definition.mission.discover then return {ready=false,reason=id..' lists its carriers',candidates={}}end
    local world,why=world_module.open()
    if not world then return {ready=false,reason=tostring(why),candidates={}}end
    return slot_conversion.discover_carriers(world,definition.selection.token,{present=present,
        exclude=definition.mission.exclude,payload=definition.payload})
end
-- Read-only: a cached carrier of a definition with mission.discover, validated now with the discovery's own guards
-- against `present` (the CURRENT loadout: stratagem_slot_conversion.validate_carrier): {ready, valid, candidate, codes,
-- reasons, reason}.
function M.validate_carrier(id,carrier,present)
    local definition=virtual.get(id)
    if not definition then return {ready=false,valid=false,codes={},reasons={},reason='no virtual stratagem '..tostring(id)}end
    if not definition.mission.discover then
        return {ready=false,valid=false,codes={},reasons={},reason=id..' lists its carriers'}
    end
    local world,why=world_module.open()
    if not world then return {ready=false,valid=false,codes={},reasons={},reason=tostring(why)}end
    return slot_conversion.validate_carrier(world,definition.selection.token,carrier,{present=present,
        exclude=definition.mission.exclude,payload=definition.payload})
end
-- Development payload stage B: the definition's donor pattern onto the converted carrier's OWN BombardmentComponentData
-- (runtime/bombardment_payload.lua apply, which re-checks every guard: mission, host, solo, the carrier is the current
-- conversion's and has not been called, ownership, vanilla bytes, no barrage, no active variant, the donor's package).
function M.apply_payload(id,callback)
    local definition=virtual.get(id)
    local function refuse(code,reason)
        local handle={status='refused',code=code,reason=reason}
        if callback then callback(handle)end
        return handle
    end
    if not definition then return refuse('NO_DEFINITION','no virtual stratagem '..tostring(id))end
    if not definition.payload then return refuse('NO_PAYLOAD',id..' has no payload')end
    local converted=slot_conversion.state(id)
    if not(converted and converted.converted and converted.definition==id)then
        return refuse('NOT_CONVERTED','no slot of '..id..' is converted')
    end
    return payload_module.apply({carrier=converted.carrier_name,donor=definition.payload.donor,
        shells=definition.payload.shells},callback)
end
-- Development payload stage B, ATOMICALLY: the carrier is never callable without its payload (docs/custom-stratagems.md,
-- "Payload stage B"). While the virtual slot is still its token (the carrier is not in the record, so not callable):
--   * both call-in packages are made resident through the Runtime's loader: the carrier's and the donor's;
--   * every payload guard that does not need the conversion holds, with no barrage running (waited for).
-- Then, in ONE tick with no yield: the conversion (one transaction) and the payload (in its no-wait mode: one
-- transaction; with payload.shells, two: the pattern, then the shell list). A refused payload undoes the conversion in that same tick, so the carrier never stays in the record without
-- its payload. Returns the handle: status 'pending' (phase 'packages', then 'barrage'), then 'applied' {conversion,
-- payload, waited} or 'refused' {code, reason, undone}; callback(handle) at the end.
function M.convert_with_payload(id,callback,carrier)
    local definition=virtual.get(id)
    local handle={status='pending',phase='packages'}
    local function finish(result)
        for key,value in pairs(result)do handle[key]=value end
        if handle.status=='refused'or handle.status=='failed'then
            log(('carrier with payload REFUSED: %s: %s%s'):format(tostring(handle.code),tostring(handle.reason),
                handle.conversion and('; the conversion was undone in the same tick: '..tostring(handle.undone))
                or' (nothing converted, nothing written)'))
        end
        if callback then callback(handle)end
    end
    if not(definition and definition.payload)then
        finish({status='refused',code='NO_PAYLOAD',reason='no payload for '..tostring(id)})
        return handle
    end
    local spec,why=M.conversion_spec(id,carrier)
    if not spec then finish({status='refused',code='NO_VIRTUAL_SLOT',reason=tostring(why)});return handle end
    local pspec={carrier=spec.carrier,donor=definition.payload.donor,shells=definition.payload.shells}
    local co=coroutine.create(function()
        local world,why_world=world_module.open()
        if not world then return {status='refused',code='UNAVAILABLE',reason=tostring(why_world)}end
        local entry=catalog.stratagems[spec.carrier]
        local deps={entry and entry.root and core_assets.dependency_for_stratagem(entry.root.id,spec.carrier),
            payload_module.donor_dependency(pspec.donor)}
        -- Stage C: the shell donor's package (its shell's, explosion's and gas volume's assets) too.
        if pspec.shells then deps[3]=payload_module.donor_dependency(pspec.shells)or false end
        if not(deps[1]and deps[2]and(not pspec.shells or deps[3]))then
            return {status='refused',code='ASSET_UNAVAILABLE',reason='no call-in package is known for the carrier or the donor'}
        end
        -- 1. Both packages resident, nothing converted yet.
        local waited=0
        local function resident()
            for _,dependency in ipairs(deps)do
                local ok,state=pcall(core_assets.state,world.runtime,dependency.package)
                if not(ok and state=='resident')then return false end
            end
            return true
        end
        if not resident()then
            local gate=core_assets.gate(world.runtime,{id='carrier-with-payload-'..entry.root.id,
                asset_dependencies=deps},log_module.emit)
            while true do
                local dt=coroutine.yield()or 0
                waited=waited+dt
                local result,why_not=gate.tick(dt)
                if result=='ready'then break end
                if result=='failed'or waited>payload_module.ASSET_TIMEOUT then
                    return {status='refused',code='ASSET_UNAVAILABLE',reason=tostring(why_not
                        or'the carrier\'s or the donor\'s call-in package did not load')}
                end
            end
        end
        -- 2. Every payload guard that does not need the conversion, with no barrage running (waited for).
        handle.phase='barrage'
        local barrage_wait=0
        while true do
            local ctx,code,reason=payload_module.preflight(world,pspec)
            if ctx then break end
            if code~='BARRAGE_ACTIVE'or barrage_wait>payload_module.BARRAGE_WAIT then
                return {status='refused',code=code,reason=reason}
            end
            barrage_wait=barrage_wait+(coroutine.yield()or 0)
        end
        -- 3. One tick, no yield: the conversion, then the payload; a refused payload undoes the conversion.
        handle.phase='converting'
        local conv,ccode,creason=slot_conversion.convert_virtual_body(spec,{atomic=true})
        if not conv then return {status='refused',code=ccode,reason=creason}end
        local applied,pcode,preason=payload_module.apply_body(pspec,{atomic=true})
        if not applied then
            local back,bcode,breason=slot_conversion.restore_body(spec.definition)
            return {status='refused',code=pcode,reason=preason,conversion=conv,undone=back~=nil and back.status=='restored',
                undoCode=bcode,undoReason=breason}
        end
        return {status='applied',conversion=conv,payload=applied,waited=waited}
    end)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        local ok,result=coroutine.resume(co,dt)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then result={status='failed',code='PAYLOAD_FAILED',reason=tostring(result)}end
        finish(result)
    end
    scheduler.attach(watch)
    return handle
end
-- The restore of an applied carrier payload (exactly the written bytes back; no barrage of the carrier running).
function M.restore_payload(callback)return payload_module.restore(callback)end
function M.payload_state()return payload_module.state()end
-- Read-only: whether the definition's donors are exactly as reviewed: {pattern (the pattern donor's record), shells (the
-- shell donor's record), chain (the shell donor's chain: shell, explosion, damage, volume template, statuses)}, or nil.
function M.payload_donors(id)
    local definition=virtual.get(id)
    local world=world_module.open()
    if not(definition and definition.payload and world)then return nil end
    return payload_module.donors(world,definition.payload.shells)
end
-- Read-only: the carrier's bombardment record report (runtime/bombardment_payload.lua inspect) against the definition's
-- donor, or nil, code, reason.
function M.inspect_payload(id,carrier)
    local definition=virtual.get(id)
    if not(definition and definition.payload)then return nil,'NO_PAYLOAD','no payload for '..tostring(id)end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    return payload_module.inspect(world,carrier,definition.payload.donor,definition.payload.shells)
end
-- Read-only: the carrier for definition `id`: the first of its carriers every carrier guard accepts and that is not in
-- `present` (a set of stable ids). Returns the name and its types, and the passed-over candidates
-- (stratagem_slot_conversion.choose_carrier).
function M.choose_carrier(id,present)
    local definition=virtual.get(id)
    if not definition then return nil,nil,{{carrier='*',code='UNKNOWN_DEFINITION',reason='no virtual stratagem '..tostring(id)}}end
    local world,why=world_module.open()
    if not world then return nil,nil,{{carrier='*',code='UNAVAILABLE',reason=tostring(why)}}end
    return slot_conversion.choose_carrier(world,definition.selection.token,definition.mission.carriers,present)
end
-- Converts, in a mission, exactly the virtual slots of definition `id` to its carrier
-- (stratagem_slot_conversion.convert_virtual; every guard there). carrier: one of the definition's carriers (default
-- its first). A job; refused NO_VIRTUAL_SLOT when none is recorded.
-- opts.uses: an Eagle carrier's slot's own uses per rearm (the conversion writes them with the type).
-- The carrier-in-slot probe (runtime/carrier_in_slot.lua): the virtual slots of `id` picked with the carrier itself are
-- verified and adopted in the mission record, nothing written (stratagem_slot_conversion.adopt_virtual).
function M.adopt_virtual(id,callback,carrier,opts)
    local slots={}
    for _,slot in ipairs(slot_list(virtual_slots))do
        local entry=virtual_slots.slots[slot]
        if entry.definition==id and entry.carrier then slots[#slots+1]=slot end
    end
    local order={}
    for k,stable in ipairs(virtual_slots and virtual_slots.pairs or{})do order[k]=stable end
    if#slots==0 then
        return slot_conversion.adopt_virtual({definition=tostring(id),slots={},order=order,carrier=carrier},callback)
    end
    -- opts.uses: the native per-slot uses its adoption writes (probe 0.2.0).
    return slot_conversion.adopt_virtual({definition=id,slots=slots,order=order,carrier=carrier,
        uses=opts and opts.uses or nil},callback)
end
-- The carrier-in-slot probe's launch fallback (0.3.0): the virtual CARRIER slots of `id`, picked with a carrier that is
-- no longer its carrier, converted in the mission record from that old carrier (the slots' own, as the token) to
-- `carrier`: stratagem_slot_conversion.convert_virtual's every guard (the recorded order, each slot exactly the old
-- carrier with unlimited uses, the new carrier in no entry, its package, no call-in in flight; solo host). opts:
-- multiplayer, client (as convert_virtual's).
function M.reconvert_virtual(id,callback,carrier,opts)
    local slots,from={},nil
    for _,slot in ipairs(slot_list(virtual_slots))do
        local entry=virtual_slots.slots[slot]
        if entry.definition==id and entry.carrier then
            if from==nil then from=entry.token end
            if entry.token==from then slots[#slots+1]=slot end
        end
    end
    local order={}
    for k,stable in ipairs(virtual_slots and virtual_slots.pairs or{})do order[k]=stable end
    local spec=#slots>0 and{definition=id,token=stratagem_name(from),carrier=carrier,slots=slots,order=order,
        multiplayer=opts and opts.multiplayer or nil,client=opts and opts.client or nil}
        or{definition=tostring(id),reason='no carrier slot holds '..tostring(id)}
    return slot_conversion.convert_virtual(spec,callback)
end
function M.convert_virtual(id,callback,carrier,opts)
    local spec,why=M.conversion_spec(id,carrier)
    if spec and opts and opts.uses then spec.uses=opts.uses end
    if spec and opts and opts.multiplayer then spec.multiplayer=true end
    -- The client-write proof (runtime/multiplayer.lua): only the orchestrator marks it.
    if spec and opts and opts.client then spec.client=true end
    return slot_conversion.convert_virtual(spec or{definition=tostring(id),reason=why},callback)
end

-- Draws the calibration markers (development diagnostics) in their own screen GUI: an outline of each sampled native
-- card (N0..) and of the virtual cell (V) and the list frame (F) on layers 990-993, centre dots and labels, and low-layer
-- probes (L, layer 21) at the centres of N0 and V: a probe hidden where its high-layer outline shows means the native UI
-- covers low layers. The Runtime GUI's own space is marked too: a square in each corner, labelled for the corner it is
-- meant to be under a bottom-left origin (BL at 0,0; TR at the GUI resolution), and a cross at its centre, so a
-- screenshot shows the origin, the axis directions and whether the GUI spans the screen. Returns the screen (close()) or
-- nil and the reason. Writes nothing.
local MAGENTA,CYAN,GREEN,YELLOW,WHITE_MARK={255,255,0,255},{255,0,255,255},{255,0,255,0},{255,255,255,0},{255,255,255,255}
function M.draw_calibration(runtime,cal)
    local font=D.font.name
    local font_ok,font_why=images.loaded(runtime,D.font.type,font)
    local material_ok=images.loaded(runtime,D.font.materialType,font)
    if not(font_ok and material_ok)then return nil,'the engine font is not loaded: '..tostring(font_why)end
    local screen,why=engine_gui.open()
    if not screen then return nil,why end
    local ok,err=pcall(function()
        local function need(v)if v==nil then error(screen.reason or'a marker was refused',0)end end
        local function clip(r)
            local x,y=math.max(0,r.x),math.max(0,r.y)
            return {x=x,y=y,w=math.max(0,math.min(screen.width,r.x+r.w)-x),h=math.max(0,math.min(screen.height,r.y+r.h)-y)}
        end
        local function outline(r,color,layer)
            local t=3
            for _,b in ipairs({{r.x,r.y,r.w,t},{r.x,r.y+r.h-t,r.w,t},{r.x,r.y,t,r.h},{r.x+r.w-t,r.y,t,r.h}})do
                local c=clip({x=b[1],y=b[2],w=b[3],h=b[4]})
                if c.w>0 and c.h>0 then need(screen.rect(c.x,c.y,layer,c.w,c.h,color))end
            end
        end
        local function dot(x,y,size,color,layer)
            local c=clip({x=x-size/2,y=y-size/2,w=size,h=size})
            if c.w>0 and c.h>0 then need(screen.rect(c.x,c.y,layer,c.w,c.h,color))end
        end
        local function label(text,x,y,color)
            if x>=0 and y>=0 and x<=screen.width and y<=screen.height then
                need(screen.text(text,font,math.max(12,cal.scale*12),font,x,y,993,color))
            end
        end
        local corner=math.max(24,cal.scale*20)
        local W,H=screen.width,screen.height
        for _,c in ipairs({{'BL 0,0',0,0},{'BR',W-corner,0},{'TL',0,H-corner},{'TR '..W..','..H,W-corner,H-corner}})do
            need(screen.rect(c[2],c[3],990,corner,corner,YELLOW))
            local lx=c[2]==0 and corner+6 or c[2]-corner*0.6-#c[1]*corner*0.35
            label(c[1],math.max(0,lx),c[3]==0 and corner*0.3 or H-corner*0.8,YELLOW)
        end
        need(screen.rect(W/2-corner,H/2-1,990,2*corner,3,YELLOW))
        need(screen.rect(W/2-1,H/2-corner,990,3,2*corner,YELLOW))
        label('C',W/2+6,H/2+6,YELLOW)
        outline(cal.frame,CYAN,990)
        label('F',cal.frame.x+6,cal.frame.y+cal.frame.h-math.max(14,cal.scale*14),CYAN)
        for k,item in ipairs(cal.samples)do
            local n=item.native
            outline(n,MAGENTA,991)
            dot(n.x+n.w/2,n.y+n.h/2,10,MAGENTA,992)
            label(('%s r%d c%d'):format(item.label,item.row,item.column),n.x+4,n.y+n.h-math.max(14,cal.scale*14),WHITE_MARK)
            if k==1 then dot(n.x+n.w/2,n.y+n.h*0.25,14,YELLOW,21);label('L',n.x+n.w/2+9,n.y+n.h*0.25-6,YELLOW)end
        end
        local v=cal.virtual
        if v then
            local r=v.runtime
            outline(r,GREEN,991)
            dot(r.x+r.w/2,r.y+r.h/2,12,GREEN,992)
            label(('V r%d c%d'):format(v.row,v.column),r.x+4,r.y+r.h-math.max(14,cal.scale*14),GREEN)
            dot(r.x+r.w/2,r.y+r.h*0.25,14,YELLOW,21)
        end
    end)
    if not ok then screen.close();return nil,tostring(err)end
    return screen
end
local function fmt_rect(r)return('%.1f, %.1f, %.1f x %.1f'):format(r.x,r.y,r.w,r.h)end
-- The calibration as log lines.
function M.calibration_lines(cal,engine,slot)
    local lines={}
    local res=engine and engine.resolution
    local bb=engine and engine.backBuffer
    lines[1]=('calibration (slot %s): GUI resolution %s, back buffer %s, worlds %s (main #%s); frame %s px (%.4f px/unit for '
        ..'its 395 x 528 units); card scale %.4f px/unit; scroll %.2f of limit %.2f, content %.2f units; column 0 at %.2f '
        ..'units'):format(tostring(slot),res and(tostring(res[1])..' x '..tostring(res[2]))or'?',
        bb and(tostring(bb[1])..' x '..tostring(bb[2]))or'?',tostring(engine and engine.worlds),
        tostring(engine and engine.mainIndex),fmt_rect(cal.frame),cal.frameScale,cal.scale,cal.scroll,cal.limit,
        cal.content,cal.leftUnits)
    for _,item in ipairs(cal.samples)do
        lines[#lines+1]=('calibration %s row %d column %d: content (%.2f, %.2f) -> after scroll (%.2f, %.2f) -> model (%.1f, '
            ..'%.1f) -> native transform (%s; depth %s) -> Runtime GUI (%s); model - native (%.2f, %.2f)'):format(item.label,
            item.row,item.column,item.content.x,item.content.y,item.scrolled.x,item.scrolled.y,item.model.x,item.model.y,
            fmt_rect(item.native),item.depth and('%.3f'):format(item.depth)or'?',fmt_rect(item.runtime),item.delta.x,
            item.delta.y)
    end
    local v=cal.virtual
    if v then
        lines[#lines+1]=('calibration V row %d column %d: content (%.2f, %.2f) -> after scroll (%.2f, %.2f) -> model (%.1f, '
            ..'%.1f) -> Runtime GUI (%s); %s'):format(v.row,v.column,v.content.x,v.content.y,v.scrolled.x,v.scrolled.y,
            v.model.x,v.model.y,fmt_rect(v.runtime),v.visible and'inside the viewport'or tostring(v.reason))
    end
    return lines
end

--------------------------------------------------------------------------------------------- the controller --
-- One selector: shows the virtual stratagem's card while the grid is open, moves focus and selects through actions
-- ('next', 'previous', 'confirm', 'cancel'), from any input source (the proof binds Runtime keys).
--   * opts.placement = 'grid' (default): the card is a virtual continuation of the native scrollable list. Its cell is
--     chosen from the layout (M.target: the free cell after the final native card, else a reachable new row, else the
--     free cell at the end of the token's category section, else of any section) and placed on screen from the scroll
--     offset and the native cards' geometry (M.placement). It is drawn only while that cell lies inside the viewport
--     and clear of every native card. While the grid moves (scrolling, navigation, a rebuild) the card is hidden; it is
--     drawn again once the grid has been still for SETTLE seconds, so nothing is redrawn every frame.
--   * opts.placement = 'float': the card floats beside the grid (the 0.3.0 layout).
-- opts.renderer: the renderer (default the engine renderer); opts.focus_frame: the optional focus frame (default off);
-- opts.tile_only: draw the grid card as its tile alone (no name or description beside it); opts.layer: the tile's base
-- GUI layer; opts.diagnostics: start with the coordinate diagnostics on (S.diagnostics(on) toggles them: calibration
-- log lines and markers each time the grid settles; development only, nothing written);
-- opts.on_selected(handle). Selection is M.select; identity follows the loadout (M.track) while the screen is open.
local SETTLE=0.2
function M.selector(opts)
    opts=opts or{}
    local grid_mode=opts.placement~='float'
    local S={focus=1,shown=false,cards={},handles={}}
    local renderer=opts.renderer
    local track={open=false,signature=nil,stable=0,reason=nil,category=nil,diagnostics=opts.diagnostics==true,
        calibrated=nil,markers=nil}
    local function close_markers()
        if track.markers then track.markers.close();track.markers=nil end
        track.calibrated=nil
    end
    local function cards()
        local out={}
        for _,definition in ipairs(virtual.list())do
            local name,description=virtual.strings(definition,'us')
            out[#out+1]={id=definition.id,name=name,description=description,icon=definition.display.icon}
        end
        return out
    end
    local function hide(reason,quiet)
        if not S.shown then return end
        renderer.close()
        S.shown,S.placement=false,nil
        if not quiet then log('hidden ('..reason..')')end
    end
    local function show(view,placement)
        if S.shown then return end
        S.cards=cards()
        if#S.cards==0 then return end
        local world=world_module.open()
        if not world then return end
        renderer=renderer or M.engine_renderer(world.runtime,{focus_frame=opts.focus_frame,layer=opts.layer})
        if grid_mode then S.cards={S.cards[1]}end
        S.focus=math.min(S.focus,#S.cards)
        local ok,why=renderer.show(S.cards,S.focus,placement)
        S.shown,S.placement=ok==true,ok==true and placement or nil
        local where=placement and(' in the grid: %s cell, row %d, column %d (x %.0f, y %.0f, %.0f px)%s'):format(
            placement.target.kind,placement.target.row,placement.target.column,placement.card.x,placement.card.y,
            placement.card.w,placement.text and''or'; no free area for the name and description')or''
        log(('%s for slot %d: %d card%s (%s)%s%s'):format(S.shown and'shown'or'not shown',view.editedSlot,#S.cards,
            #S.cards==1 and''or's',S.cards[S.focus].id,where,S.shown and''or(': '..tostring(why))))
    end
    -- While the grid is open: hide on movement, show once the geometry has settled (grid mode).
    local function follow(dt)
        local world=world_module.open()
        if not world then return end
        local ok,view=pcall(M.screen,world)
        if not(ok and view and view.open and view.gridOpen)then return end
        if renderer and renderer.state=='failed'then return end
        local grid,why=M.grid(world,view)
        local target,placement
        if grid then target,why=M.target(grid,track.category)end
        if target then placement,why=M.placement(grid,target)end
        if placement and not placement.visible then why=placement.reason end
        local signature=grid and M.grid_signature(grid)or('unreadable:'..tostring(why))
        if signature~=track.signature then
            track.signature,track.stable=signature,0
            hide('the grid moved',true)
            close_markers()
            return
        end
        track.stable=track.stable+(dt or 0)
        if track.stable<SETTLE then return end
        if placement and opts.tile_only then placement.text=nil end
        -- Diagnostics: once per settled position, the calibration lines and the markers.
        if track.diagnostics and grid and track.calibrated~=signature then
            track.calibrated=signature
            local cal,cal_why=M.calibration(world,view,grid,placement,target,why)
            if cal then
                for _,line in ipairs(M.calibration_lines(cal,engine_gui.diagnostics(),view.editedSlot))do log(line)end
                local drawn,draw_why=M.draw_calibration(world.runtime,cal)
                if drawn then track.markers=drawn else log('calibration markers not drawn: '..tostring(draw_why))end
            else
                log('calibration unavailable: '..tostring(cal_why))
            end
        end
        if S.shown then return end
        if not(placement and placement.visible)then
            if why~=track.reason then
                track.reason=why
                local where=target and(' (its cell: %s, row %d, column %d)'):format(target.kind,target.row,target.column)or''
                log(('not shown for slot %d: %s%s'):format(view.editedSlot,tostring(why),where))
            end
            return
        end
        track.reason=nil
        show(view,placement)
    end
    S.watch=M.watch(function(event,view)
        if event=='grid_opened'then
            track.open,track.signature,track.reason=true,nil,nil
            track.category=nil
            local world=world_module.open()
            local definition=virtual.list()[1]
            local token=world and definition and loadout.type_of(world,definition.selection.tokenId)
            local trow=token and row(world,token)
            track.category=trow and world.view.u32(trow+0xB8)or nil
            if not grid_mode then show(view)end
        elseif event=='grid_closed'then
            track.open=false
            hide('the grid closed')
            close_markers()
        elseif event=='closed'then
            track.open=false
            hide('the loadout screen closed')
            close_markers()
        elseif event=='record_changed'then
            local world=world_module.open()
            if world then M.track(world,view)end
        end
    end)
    if grid_mode then
        S.follower={status='active'}
        function S.follower.cancel()S.follower.status='cancelled'end
        function S.follower.tick(dt)if S.follower.status=='active'and track.open then follow(dt)end end
        scheduler.attach(S.follower)
    end
    function S.action(name)
        if not S.shown then return false end
        if name=='next'or name=='previous'then
            S.focus=(S.focus-1+(name=='next'and 1 or-1))%#S.cards+1
            renderer.focus(S.focus)
            return true
        elseif name=='confirm'then
            local card=S.cards[S.focus]
            S.handles[#S.handles+1]=M.select(card.id,opts.on_selected)
            return true
        elseif name=='cancel'then
            hide('cancelled')
            return true
        end
        return false
    end
    function S.stop()
        S.watch.cancel()
        if S.follower then S.follower.cancel()end
        hide('stopped')
        close_markers()
    end
    -- The coordinate diagnostics on or off (development; toggled by the proof's F8). Returns the new state.
    function S.diagnostics(on)
        if on==nil then on=not track.diagnostics end
        track.diagnostics=on==true
        close_markers()
        if not track.diagnostics then log('coordinate diagnostics off')else log('coordinate diagnostics on')end
        return track.diagnostics
    end
    function S.renderer()return renderer end
    return S
end

function M.reset_for_tests()history={};virtual_slots=nil;proven={}end
-- Validation only: the Runtime's virtual-slot record as a selection would have left it ({slots, pairs}).
function M.set_virtual_slots_for_tests(set)virtual_slots=set end
return M
