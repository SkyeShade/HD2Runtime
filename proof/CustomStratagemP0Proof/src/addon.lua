local hd2=require('mods/skyeshade/hd2runtime')
-- CustomStratagemP0Proof 0.12.0: the custom TEXT write proof (docs/custom-text.md), together with the public custom
-- icon (live-verified by 0.11.0) and the public calldown code, on the Orbital 120mm HE Barrage carrier:
--   * name "ORBITAL GAS BARRAGE", cased name "Orbital Gas Barrage", description "Calls down a barrage of gas
--     shells.": Runtime-owned text (runtime/text_resources.lua), through the development path
--     (runtime/stratagem_presentation.lua apply_text); the public presentation fields do not take custom text yet;
--   * the icon: this proof's own image, hd2.resources.image('orbital_gas_barrage_icon') through the public
--     presentation_icon field;
--   * the calldown code Up Up Down Down through the public calldown_code field;
--   * the payload, cooldown, stable id, type, account items, inventory and loadout are never written: calling it in
--     fires the normal 120mm barrage.
-- The text is one Runtime-owned table appended after the game's own text tables (never a game table or entry). The
-- development path refuses with nothing written unless every guard holds, and verifies the write.
--
-- Development-only parts: the read-only text probe, read-only observers (saved loadout, mission record, HUD slot, what
-- the 120mm row holds and what its text ids show), F9 status.
--
-- Restore (MODS tab, Mod Options Menu, page "Custom Stratagem Proof"), aboard the ship: "Custom text" off + APPLY
-- (the 120mm's own name and description), "Custom icon and code" off + APPLY (its own icon and code). The mission HUD
-- keeps what it built until the next mission. A finalizer also restores the text before the Lua state closes. Without
-- Mod Options Menu nothing is applied (there would be no way to restore).
local mod=hd2.mod()
local BUILD='0.12.0 CUSTOM-TEXT-WRITE'
mod:log('CustomStratagemP0Proof '..BUILD..' BUILD: the 120mm carrier presents as "Orbital Gas Barrage" (Runtime text, '
    ..'development path), with this proof\'s custom icon and the code Up Up Down Down (public fields); it still calls in '
    ..'the normal 120mm barrage.')

local texts=require('hd2runtime/runtime/text_resources')
local presentation=require('hd2runtime/runtime/stratagem_presentation')
local world_module=require('hd2runtime/runtime/event_world')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local domain=require('hd2runtime/domains/stratagem_calldown')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local stratagem_hud=require('hd2runtime/runtime/stratagem_hud')
local images=require('hd2runtime/runtime/image_resources')
local RESOURCE='mods/skyeshade/hd2runtime_custom_stratagem_p0_proof'
local CARRIER='Orbital 120mm HE Barrage'
local ID=catalog.stratagems[CARRIER].root.id
local NATIVE=domain.presentation.values[tostring(ID)]
local NAME=texts.handle('orbital_gas_barrage_name','ORBITAL GAS BARRAGE',RESOURCE)
local CASED=texts.handle('orbital_gas_barrage_name_cased','Orbital Gas Barrage',RESOURCE)
local DESCRIPTION=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',RESOURCE)
local TEXTS={name=NAME,nameCased=CASED,description=DESCRIPTION}
local icon=hd2.resources.image('orbital_gas_barrage_icon')
mod:log(('carrier: %s, stable id %d; native name 0x%08X, cased name 0x%08X, description 0x%08X, icon %s; Runtime text '
    ..'ids: name %s, cased name %s, description %s'):format(CARRIER,ID,NATIVE.name,NATIVE.nameCased,NATIVE.description,
    NATIVE.icon,texts.id_hex(NAME),texts.id_hex(CASED),texts.id_hex(DESCRIPTION)))

------------------------------------------------------------------------------------------ read-only text probe --
local function probe(world)
    local r=texts.inspect(world.runtime)
    if not r.available then return nil,tostring(r.reason)end
    local lines={('game text registry: %d of %d tables, %d spare; current language %s'):format(r.count,r.capacity,
        r.spare,tostring(r.language)),
        'Runtime text table: '..(r.registered and('already registered (table '..r.registered..')')or'not registered yet'),
        'Runtime text ids already in a game table: '..(#r.collisions==0 and'none'or table.concat(r.collisions,', '))}
    local ok=r.spare>=1 and#r.collisions==0 and not tostring(r.language):find('unknown',1,true)
    lines[#lines+1]='TEXT PROBE RESULT: '..(ok and'PASS: room for the Runtime text table, no id clash, a known language'
        or'FAIL: the custom text would be refused')
    return lines,nil,ok
end

---------------------------------------------------------------------------------------------- row observers --
local function row_of(world)
    local kind=loadout.type_of(world,ID)
    return kind and world.view.pointer(world.game+require('hd2runtime/schemas/current').stratagem.table_rva+kind*8)
end
-- What the 120mm row holds now (read-only): its text members and icon.
local function row_look(world)
    local row=world and row_of(world)
    if not row then return 'unreadable'end
    local fields=domain.presentation.fields
    local function member(name)return world.view.read(row+fields[name].offset,fields[name].width)end
    local runtime_text,native_text=true,true
    for name,handle in pairs(TEXTS)do
        local bytes=member(name)
        if bytes~=texts.id_bytes(handle)then runtime_text=false end
        if bytes~=presentation.encode(name,NATIVE[name])then native_text=false end
    end
    local bytes=member('icon')
    local which=bytes==images.bytes(icon)and'the custom icon'or bytes==presentation.encode('icon',NATIVE.icon)
        and'its native icon'or'another icon'
    return (runtime_text and'the Runtime text'or native_text and'its native text'or'MIXED or other text')..' and '..which
end
-- What each Runtime text shows in the current language (read-only).
local function shown(world)
    local parts={}
    for _,name in ipairs({'name','nameCased','description'})do
        local ok=texts.resolves(world.runtime,TEXTS[name])
        parts[#parts+1]=name..' '..(ok and('"'..texts.text(TEXTS[name],texts.language(world.runtime))..'"')or'NOT RESOLVED')
    end
    return table.concat(parts,', ')
end
local names_by_id={}
for name,entry in pairs(catalog.stratagems)do names_by_id[entry.root.id]=name end
local function label(id,kind)
    return ('%s (type %s, stable id %s)'):format(names_by_id[id]or'not catalogued',tostring(kind),tostring(id))
end
local ship={key=nil}
local found
local function watch_ship(world)
    local saved,code,reason=loadout.saved(world)
    local parts={}
    for index,pair in ipairs(saved and saved.pairs or{})do parts[index]=label(pair.id,pair.type)end
    local key=(saved and table.concat(parts,'; ')or tostring(code))..' | '..row_look(world)
    if key==ship.key then return end
    ship.key=key
    if not saved then mod:log('saved ship loadout unreadable: '..tostring(code)..': '..tostring(reason));return end
    local slot
    for index,pair in ipairs(saved.pairs)do if pair.id==ID then slot=index end end
    mod:log(('saved ship loadout (by stable id): %s; the 120mm row holds %s -> %s'):format(table.concat(parts,'; '),
        row_look(world),slot and('the 120mm is selected (saved stratagem '..slot..' of '..#saved.pairs..')')
        or'the 120mm is NOT selected: pick the Orbital 120mm HE Barrage in the loadout screen and leave it'))
end
local function watch_mission(world)
    if found then return end
    local record=loadout.record(world)
    if not record then return end
    local entry
    for _,item in ipairs(record)do if item.id==ID then entry=item end end
    if not entry then
        if not ship.missing then
            ship.missing=true
            mod:log('mission record: the 120mm is NOT in it (pick it on the ship for this test)')
        end
        return
    end
    local located=stratagem_hud.locate(world,entry.type)
    if not located then return end
    found=entry
    mod:log(('the 120mm is record entry %d: %s, uses %s; its row holds %s; its text shows: %s'):format(entry.index,
        label(entry.id,entry.type),tostring(entry.uses),row_look(world),shown(world)))
    mod:log(('HUD slot %d draws record entry %d: %s'):format(located.index,entry.index,label(entry.id,entry.type)))
end

------------------------------------------------------------------------------------------------- the options --
local options=hd2.options({id='custom_stratagem_proof',title='Custom Stratagem Proof',fallback='disable'})
local look=options:toggle({id='look',label='Custom icon and code',default=true,
    description='The Orbital 120mm HE Barrage shows this proof\'s custom icon and takes the code Up Up Down Down '
        ..'(public presentation_icon and calldown_code). Off + APPLY restores both, aboard the ship.'})
local text_toggle=options:toggle({id='text',label='Custom text',default=true,
    description='The Orbital 120mm HE Barrage is named "Orbital Gas Barrage" with this proof\'s description (Runtime '
        ..'text, applied aboard the ship). Off + APPLY restores its own name and description, aboard the ship.'})

-- The public part: one ensure, the icon and the calldown code together; its toggle restores both exactly.
local ensure=hd2.ensure({transaction={id='gas-barrage-look',target=hd2.stratagem(CARRIER),changes={
    {field=hd2.fields.stratagem.presentation_icon,expect=CARRIER,value=icon},
    {field=hd2.fields.stratagem.calldown_code,expect={'right','right','down','left','right','down'},
        value={'up','up','down','down'}}}},enabled=look})

-- The development part: the text members.
local op={state='idle',attempts=0,retry_at=0}   -- idle | applying | applied | restoring | restored | refused
local clock=0
local function report(handle)
    if handle.status=='applied'then
        op.state='applied'
        mod:log('custom text APPLIED aboard the ship: the 120mm row holds '..row_look(world_module.open())
            ..'; its text shows: '..shown(world_module.open())..'; open the loadout screen now')
    elseif handle.status=='restored'then
        op.state='restored'
        mod:log('custom text RESTORED: the 120mm row holds '..row_look(world_module.open()))
    else
        local transient=tostring(handle.reason):find('TARGET_UNAVAILABLE',1,true)~=nil and op.attempts<6
        op.state=transient and'idle'or'refused'
        op.retry_at=clock+5
        mod:log(('custom text %s: %s: %s%s'):format(op.state=='refused'and'REFUSED (nothing written)'or'not ready',
            tostring(handle.code),tostring(handle.reason),transient and' (the same guarded attempt runs again in a few '
            ..'seconds)'or''))
    end
end
local function step(world,mission)
    if op.state=='applying'or op.state=='restoring'or op.state=='refused'then return end
    local wanted=text_toggle:available()and text_toggle:get()==true
    -- The icon and code first (a clean log order): the text waits until that ensure has a result or is off.
    local settled=not(look:available()and look:get()==true)or ensure.result~=nil
    if wanted and not mission and settled and(op.state=='idle'or op.state=='restored')then
        op.state='applying';op.attempts=op.attempts+1
        presentation.apply_text({carrier=CARRIER,name=NAME,nameCased=CASED,description=DESCRIPTION},report)
    elseif not wanted and op.state=='applied'then
        if mission and not op.said_mission then
            op.said_mission=true
            mod:log('restore requested in a mission: restoring now; the HUD keeps what it built until the next mission')
        end
        op.state='restoring'
        presentation.restore(report)
    end
end

----------------------------------------------------------------------------------------------------- the loop --
local probed,in_mission,said_ensure=nil,false,nil
hd2.every(0.5,function()
    clock=clock+0.5
    local state=hd2.game_state()
    local mission=state and state.mission
    if mission and not in_mission then
        in_mission,found,ship.missing=true,nil,nil
        mod:log(('mission started (host %s)'):format(tostring(state and state.host)))
    elseif not mission and in_mission then
        in_mission=false
        mod:log('mission ended; the 120mm row holds '..row_look(world_module.open()))
    end
    local world=world_module.open()
    if not world then return end
    if not probed then
        local ok,lines,why=pcall(probe,world)
        if ok and lines then
            probed=true
            mod:log('text probe (before any text write):')
            for _,line in ipairs(lines)do mod:log('  '..line)end
        elseif clock%10==0 then
            mod:log('text probe not ready: '..tostring(ok and why or lines))
        end
    end
    local result=ensure.result and ensure.result.status
    if result~=said_ensure then
        said_ensure=result
        mod:log('custom icon and code (public ensure): '..tostring(ensure.status)..' '..tostring(result)
            ..(ensure.error and(' '..tostring(ensure.error))or''))
    end
    if not text_toggle:available()and text_toggle:disables()and not op.said_menu then
        op.said_menu=true
        mod:log('Mod Options Menu unavailable: nothing is applied (the toggles are the restore path)')
    end
    if state and probed and clock>=op.retry_at then step(world,mission)end
    if not mission then watch_ship(world)else watch_mission(world)end
end,{id='custom-text-write-proof'})

hd2.input.bind('custom_stratagem_p0_proof.status',{key='F9',on_press=function()
    local world=world_module.open()
    local state=hd2.game_state()or{}
    local r=world and texts.inspect(world.runtime)or{}
    mod:log(('F9 [%s]: custom text %s (attempts %d), toggle %s; icon and code ensure %s %s, toggle %s; the 120mm row '
        ..'holds %s; language %s, Runtime text table %s; mission %s, host %s'):format(BUILD,op.state,op.attempts,
        text_toggle:get()and'on'or'off',tostring(ensure.status),tostring(ensure.result and ensure.result.status),
        look:get()and'on'or'off',world and row_look(world)or'unreadable',tostring(r.language),
        r.registered and('registered (table '..r.registered..' of '..tostring(r.count)..')')or'not registered',
        tostring(state.mission==true),tostring(state.host)))
end})
mod:log('loaded ('..BUILD..'): aboard the ship, after "custom text APPLIED", open the loadout screen; then a solo '
    ..'mission (Up Up Down Down calls in the 120mm). Restore: MODS > Custom Stratagem Proof, both toggles off + APPLY, '
    ..'aboard the ship. F9 status.')
