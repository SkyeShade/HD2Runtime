local hd2=require('mods/skyeshade/hd2runtime')
-- GasBarrageMissionProof 0.5.0: CUSTOM CALLDOWN (payload stage A; docs/custom-stratagems.md, "The custom stratagem in
-- a mission"). Development only; solo; no multiplayer, no matchmaking.
-- The carrier identity is live-proven (0.4.0, 2026-10-02: carrier Orbital 380mm HE Barrage) and unchanged here:
--   saved virtual Gas Barrage -> Orbital Precision Strike token -> mission start -> a carrier DISCOVERED from what the
--   account owns (stratagem_slot_conversion.discover_carriers: selectable, enabled, owned, unlimited uses, a normal
--   call-in class, a known package, a reviewed presentation and code, not in the saved loadout, never the token or the
--   donor; orbital bombardments first) -> ONLY the virtual slot becomes the carrier -> the carrier presents as Orbital
--   Gas Barrage (applied aboard the ship) -> its own call-in.
-- New in 0.5.0, stage A of the payload work: the carrier answers to the Gas Barrage code UP UP DOWN DOWN, set through
-- the public hd2.fields.stratagem.calldown_code (one hd2.ensure on the carrier only), with its own NORMAL payload:
--   * the carrier's native code is read from its row first; it must equal the reviewed native code (the field's
--     expect). The ensure restores it when its toggle is off, and the Runtime restores it when the game closes;
--   * the code is checked first. The game's matcher selects the first record entry whose whole code is entered at
--     once, so a code EQUAL to another's is ambiguous, one that STARTS another's leaves that stratagem uncallable while
--     the carrier is ready, and one that EXTENDS another's is never reached. Refused: any of these with a stratagem a
--     player can select. Guarded: the three mission-only objectives whose codes start with UP UP DOWN DOWN (cargo
--     container, mobile comms relay, destroyer call-in): a saved loadout or a mission record holding a related entry
--     refuses the test before anything is converted, and one appearing after the conversion returns the virtual slot
--     to its token (the conversion's own guarded restore);
--   * the Orbital Precision Strike (the token) and the Orbital 120mm HE Barrage (the donor) codes and rows are never
--     written; every report checks them native.
-- The game believes the slot is vanilla stratagem X (the carrier) while the Runtime makes X present as the custom
-- stratagem and answer to its code; X keeps its own type, stable id, call-in and payload.
-- No payload, projectile, save-format, account, catalogue, inventory or StratagemInfo-registry change; no native call,
-- FFI, hook or OS input.
local mod=hd2.mod()
local BUILD='0.5.0 CUSTOM CALLDOWN'
mod:log('GasBarrageMissionProof '..BUILD..' BUILD: ship: Orbital Gas Barrage from the custom panel (the Precision Strike '
    ..'token is saved), the rest of the loadout picked natively; leave the loadout screen: the carrier is then discovered '
    ..'from what you own ("CARRIER CANDIDATE" lines, then "CARRIER: ... SELECTED") and gets the Gas Barrage code UP UP '
    ..'DOWN DOWN ("CODE CHECK", then "CODE"); do NOT select the carrier natively; wait for "PRE-MISSION CHECK ... READY", '
    ..'then a SOLO mission: the virtual slot becomes the carrier, presented as Orbital Gas Barrage; call it with UP UP '
    ..'DOWN DOWN: expect the carrier\'s own normal attack. F9 ship status; F10 mission status.')

local panel=require('hd2runtime/runtime/custom_stratagem_panel')
local selector=require('hd2runtime/runtime/stratagem_selector')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local texts=require('hd2runtime/runtime/text_resources')
local presentation=require('hd2runtime/runtime/stratagem_presentation')
local images=require('hd2runtime/runtime/image_resources')
local calldown=require('hd2runtime/runtime/calldown_codes')
local world_module=require('hd2runtime/runtime/event_world')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local stratagem_hud=require('hd2runtime/runtime/stratagem_hud')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local domain=require('hd2runtime/domains/stratagem_calldown')
local SEL=require('hd2runtime/domains/stratagem_selector')
local TABLE=require('hd2runtime/schemas/current').stratagem.table_rva
local RESOURCE='mods/skyeshade/hd2runtime_gas_barrage_mission_proof'
local TOKEN,DONOR='Orbital Precision Strike','Orbital 120mm HE Barrage'
local TOKEN_ID,DONOR_ID=catalog.stratagems[TOKEN].root.id,catalog.stratagems[DONOR].root.id
-- The custom Gas Barrage code (the public field's direction names), and its native values.
local CODE={'up','up','down','down'}
local CODE_VALUES=assert(calldown.values(CODE))
local CODE_TEXT=calldown.text(CODE_VALUES)

-- The Runtime-rendered icon (the game's mask convention), converted from the author's source/orbital_gas_barrage.png.
local ICON=hd2.resources.image('orbital_gas_barrage_masks')
local NAME=texts.handle('orbital_gas_barrage_name','ORBITAL GAS BARRAGE',RESOURCE)
local CASED=texts.handle('orbital_gas_barrage_name_cased','Orbital Gas Barrage',RESOURCE)
local DESCRIPTION=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',RESOURCE)
local TEXTS={name=NAME,nameCased=CASED,description=DESCRIPTION}
local GAS=virtual.define({id='orbital_gas_barrage',display={name=CASED,description=DESCRIPTION,icon=ICON},
    selection={token=TOKEN},mission={discover=true,exclude={DONOR}}},RESOURCE)

local names_by_id={}
for name,entry in pairs(catalog.stratagems)do names_by_id[entry.root.id]=name end
-- Mission-only types are not catalogued: the calldown research names the ones whose codes start with UP UP DOWN DOWN.
local overlap_names={}
for _,o in ipairs(domain.p0.overlaps or{})do overlap_names[calldown.key(o.sequence)]=o.nativeName end
local function label(world,kind)
    local id=world and loadout.id_of(world,kind)
    return ('%s (type %s, stable id %s)'):format(names_by_id[id]or'not catalogued',tostring(kind),tostring(id))
end
local function list(t)local out={};for _,v in ipairs(t or{})do out[#out+1]=tostring(v)end;return table.concat(out,', ')end
local function order_text(order)
    local out={}
    for k,id in ipairs(order or{})do out[k]=names_by_id[id]or tostring(id)end
    return table.concat(out,'; ')
end
local function row_of(world,kind)return kind and world.view.pointer(world.game+TABLE+kind*8)end
local function row_by_id(world,id)
    local kind=loadout.type_of(world,id)
    return row_of(world,kind),kind
end
-- Whether a row still holds its own reviewed name, cased name, description and icon: true / false / nil.
local function native(world,id)
    local row=row_by_id(world,id)
    local values=domain.presentation.values[tostring(id)]
    if not(row and values)then return nil end
    local fields=domain.presentation.fields
    for _,name in ipairs({'name','nameCased','description','icon'})do
        if world.view.read(row+fields[name].offset,fields[name].width)~=presentation.encode(name,values[name])then
            return false
        end
    end
    return true
end
-- A row's live calldown code (+0x40 directions, +0x48 count) as native values, or nil (read-only).
local function row_code(world,row)
    local count=row and world.view.u32(row+domain.row.count)
    local array=row and world.view.pointer(row+domain.row.sequence)
    if not(count and array and count>0 and count<=16)then return nil end
    local values={}
    for k=0,count-1 do values[k+1]=world.view.u32(array+k*4)end
    return values
end
local function code_values(world,id)return row_code(world,(row_by_id(world,id)))end
local function code_of(world,id)
    local values=code_values(world,id)
    return values and calldown.text(values)or'unreadable'
end
-- Whether a row holds its reviewed native code: true / false / nil.
local function code_native(world,id)
    local values=code_values(world,id)
    local reviewed=domain.nativeCodes[tostring(id)]
    if not(values and reviewed)then return nil end
    return calldown.same(values,reviewed)
end
local function relation_text(relation)
    return relation=='equal'and'is EQUAL to it'or relation=='prefix'and'starts with it'or'is its start'
end
local function code_name(id,values)
    return names_by_id[id]or overlap_names[calldown.key(values)]or('stable id '..tostring(id))
end

------------------------------------------------------------------------------------------------- the options --
-- With Mod Options Menu the toggles are the restore paths; without it all run with their defaults (on).
local options=hd2.options({id='gas_barrage_mission_proof',title='Gas Barrage Mission Proof',fallback='default'})
local present=options:toggle({id='presentation',label='Gas Barrage look on the carrier',default=true,
    description='Aboard the ship the carrier (a vanilla orbital not in your loadout) presents as Orbital Gas Barrage '
        ..'(Runtime text and the masked icon). Off + APPLY, aboard the ship, restores its own look.'})
local code_on=options:toggle({id='code',label='Gas Barrage code on the carrier',default=true,
    description='The carrier answers to UP UP DOWN DOWN (the public calldown_code field on the carrier only). Off + '
        ..'APPLY restores its own code.'})
local convert=options:toggle({id='convert',label='Convert virtual Gas Barrage slots',default=true,
    description='In a solo mission the virtual Gas Barrage slots become the carrier (the record entry type only). Off: '
        ..'nothing is converted.'})
local function settled(t)return t:describe().state~='pending'end
local function wanted(t)return settled(t)and t:get()==true and not t:disables()end

------------------------------------------------------------------------------------------------ the ship --
local function report_selection(handle)
    if handle.status=='selected'then
        mod:log(('SHIP: custom Gas Barrage SELECTED into loadout slot %d; the underlying token written: %s%s; virtual '
            ..'slots: %s'):format(handle.index,TOKEN,handle.written and''or' (already held: no write)',
            selector.slots_text(selector.virtual_slots())))
    elseif handle.status=='restored'then
        mod:log('SHIP: slot '..handle.index..' restored (exact: '..tostring(handle.exact)..'); virtual slots: '
            ..selector.slots_text(selector.virtual_slots()))
    else
        mod:log(('SHIP: selection REFUSED (nothing written): %s: %s'):format(tostring(handle.code),tostring(handle.reason)))
    end
end
local P=panel.panel({renderer='compact',placeholders=5,focus=true,selection=true,mouse=true,
    on_selected=report_selection})

-- The carrier: DISCOVERED aboard the ship from what the account owns, once the catalogue is ready, a virtual Gas
-- Barrage slot exists and the saved loadout is the one it was recorded in; then fixed for the session, and its look and
-- code applied to it alone. Its stable id is kept (a future multiplayer policy avoids carriers in peers' loadouts).
local carrier={name=nil,id=nil,kind=nil,look=nil,code=nil,native_code=nil,code_refused=nil}
local discovery={key=nil,waiting=nil,retry=0}
local function saved_ids(world)
    local saved=loadout.saved(world)
    if not saved then return nil end
    local ids,set={},{}
    for k,pair in ipairs(saved.pairs or{})do ids[k]=pair.id;set[pair.id]=true end
    return ids,set
end
local function yes(v)return v and'true'or'false'end
local function candidate_line(c,selected)
    local own=c.ownership
    local own_text=yes(c.owned)
    if own and not c.owned then
        own_text=own_text..(own.found and(' (catalogue state %s, parent %s)'):format(tostring(own.state),
            tostring(own.parent))or(' (not in the catalogue range %d..%d)'):format(own.range[1],own.range[2]))
    end
    return ('CARRIER CANDIDATE: %s (type %d, stable id %d, %s/%s): owned=%s selectable=%s enabled=%s unlimited=%s '
        ..'in_loadout=%s special_case=%s package_available=%s presentation=%s code=%s -> %s'):format(c.name,c.type,c.id,
        tostring(c.family),tostring(c.component or'-'),own_text,yes(c.selectable),yes(c.enabled),yes(c.unlimited),
        yes(c.inLoadout),c.special and('true ('..c.special..')')or'false',yes(c.package),yes(c.presentation),yes(c.code),
        selected and'SELECTED'or c.eligible and'eligible'or('rejected: '..table.concat(c.reasons,'; ')))
end
-- Whether a stratagem (by stable id) is selectable in the ship loadout (row +0x80 bit 1): true / false / nil.
local ROWM=require('hd2runtime/domains/stratagem_slots').row
local function selectable(world,id)
    local row=row_by_id(world,id)
    local flags=row and world.view.u32(row+ROWM.selectable)
    if not flags then return nil end
    return math.floor(flags/ROWM.selectableBit)%2==1
end
-- The custom code against every reviewed native code (read-only). The game's matcher re-checks every record entry on
-- each arrow and selects the first entry whose whole code is entered at once: an EQUAL code is ambiguous, a code that
-- is the START of another's makes that other stratagem uncallable while the carrier is ready, and one that EXTENDS
-- another's is never reached. So any relation with a stratagem a player can select refuses the code (no
-- acknowledgement is given); a relation with a mission-only (not selectable) stratagem is listed and guarded instead:
-- the mission record is checked before the conversion (such a mission is refused) and watched after it.
local function code_check(world,c)
    local relations=calldown.native_relations(CODE_VALUES,{[c.id]=true})
    local refused,guarded={},{}
    for _,r in ipairs(relations)do
        local pick=selectable(world,r.id)
        local text=('%s (%s, %s) %s'):format(code_name(r.id,r.values),calldown.text(r.values),pick==false and
            'mission only'or pick and'selectable'or'unreadable',relation_text(r.relation))
        if r.relation=='equal'or pick~=false then refused[#refused+1]=text else guarded[#guarded+1]=text end
    end
    local native_now=code_values(world,c.id)
    local reviewed=domain.nativeCodes[tostring(c.id)]
    local ok=#refused==0 and native_now~=nil and calldown.same(native_now,reviewed)
    mod:log(('CODE CHECK: the Gas Barrage code %s for the carrier %s (stable id %d): its native code read from its row '
        ..'first: %s (the reviewed native code: %s; equal: %s); native codes equal to it or related to a selectable '
        ..'stratagem: %s; mission-only stratagems related to it: %s (guarded: a mission record holding one refuses the '
        ..'conversion) -> %s'):format(CODE_TEXT,c.name,c.id,native_now and calldown.text(native_now)or'unreadable',
        reviewed and calldown.text(reviewed)or'none',yes(native_now and reviewed and calldown.same(native_now,reviewed)),
        #refused==0 and'none'or table.concat(refused,'; '),#guarded==0 and'none'or table.concat(guarded,'; '),
        ok and'SAFE: applying it'or'REFUSED: the code is not applied'))
    return ok and native_now or nil
end
local function choose(world,ids,present_set)
    local key=table.concat(ids,',')
    if key==discovery.key then return end
    local found=selector.discover_carrier(GAS.id,present_set)
    if not found.ready then
        -- Not trusted yet (the account catalogue may not be filled): checked again shortly.
        if discovery.waiting~=found.reason then
            discovery.waiting=found.reason
            mod:log('CARRIER: waiting: '..tostring(found.reason))
        end
        return
    end
    discovery.key,discovery.waiting=key,nil
    for _,c in ipairs(found.candidates)do mod:log(candidate_line(c,found.chosen==c))end
    local eligible=0
    for _,c in ipairs(found.candidates)do if c.eligible then eligible=eligible+1 end end
    if not found.chosen then
        mod:log(('CARRIER: none eligible (%d checked): carrier = nil; the test refuses safely (checked again when the '
            ..'saved loadout changes)'):format(#found.candidates))
        return
    end
    local c=found.chosen
    carrier.name,carrier.id,carrier.kind=c.name,c.id,c.type
    mod:log(('CARRIER: %s (type %d, stable id %d, %s/%s) SELECTED: the first of %d eligible carriers (orbital '
        ..'bombardments first); owned, not in the saved loadout, not the donor; its native code: %s; the donor %s '
        ..'is not written. Do NOT select %s natively: while this proof runs its own card presents as Orbital Gas '
        ..'Barrage and answers to %s'):format(c.name,c.type,c.id,tostring(c.family),tostring(c.component or'-'),eligible,
        code_of(world,c.id),DONOR,c.name,CODE_TEXT))
    -- The masked icon through the public field, on the carrier only.
    carrier.look=hd2.ensure({transaction={id='gas-barrage-carrier-icon',target=hd2.stratagem(c.name),changes={
        {field=hd2.fields.stratagem.presentation_icon,expect=c.name,value=ICON}}},enabled=present})
    -- The Gas Barrage code through the public field, on the carrier only, from its native code read first.
    local native_now=code_check(world,c)
    if native_now then
        carrier.native_code=native_now
        carrier.code=hd2.ensure({patch={id='gas-barrage-carrier-code',target=hd2.stratagem(c.name),
            field=hd2.fields.stratagem.calldown_code,expect=calldown.names(native_now),value=CODE},enabled=code_on})
    else
        carrier.code_refused=true
    end
end
local function discovery_step(world)
    if carrier.name then return end
    local ids,present_set=saved_ids(world)
    if not ids then return end
    -- Only once a virtual Gas Barrage slot exists and the saved loadout is the one it was recorded in.
    local spec=selector.virtual_slots()
    if not spec then return end
    local found=selector.reconstruct(ids)
    if not found then return end
    if discovery.waiting then
        discovery.retry=discovery.retry-1
        if discovery.retry>0 then return end
        discovery.retry=4
    end
    choose(world,ids,present_set)
end
local function row_look(world)
    if not carrier.id then return'no carrier yet'end
    local row=row_by_id(world,carrier.id)
    if not row then return'unreadable'end
    local values=domain.presentation.values[tostring(carrier.id)]
    local fields=domain.presentation.fields
    local function member(name)return world.view.read(row+fields[name].offset,fields[name].width)end
    local runtime_text,native_text=true,true
    for name,handle in pairs(TEXTS)do
        local bytes=member(name)
        if bytes~=texts.id_bytes(handle)then runtime_text=false end
        if bytes~=presentation.encode(name,values[name])then native_text=false end
    end
    local bytes=member('icon')
    local which=bytes==images.bytes(ICON)and'the Gas Barrage icon'or bytes==presentation.encode('icon',values.icon)
        and'its native icon'or'another icon'
    return (runtime_text and'the Gas Barrage text'or native_text and'its native text'or'MIXED or other text')..' and '..which
end
-- The carrier row's code: 'the Gas Barrage code', 'its native code' or 'another code', with the directions.
local CODE_HELD='the Gas Barrage code ('..CODE_TEXT..')'
local function row_code_text(world)
    if not carrier.id then return'no carrier yet'end
    local values=code_values(world,carrier.id)
    if not values then return'unreadable'end
    if calldown.same(values,CODE_VALUES)then return CODE_HELD end
    if calldown.same(values,domain.nativeCodes[tostring(carrier.id)])then
        return'its native code ('..calldown.text(values)..')'
    end
    return'another code ('..calldown.text(values)..')'
end
local function code_wanted()return carrier.code~=nil and wanted(code_on)end
-- The token's and the donor's codes and rows: never written.
local function others_text(world)
    return ('Orbital Precision Strike presentation native = %s, code native = %s; donor %s presentation native = %s, '
        ..'code native = %s'):format(tostring(native(world,TOKEN_ID)),tostring(code_native(world,TOKEN_ID)),DONOR,
        tostring(native(world,DONOR_ID)),tostring(code_native(world,DONOR_ID)))
end
local function shown(world)
    local parts={}
    for _,name in ipairs({'name','nameCased','description'})do
        local ok=texts.resolves(world.runtime,TEXTS[name])
        parts[#parts+1]=name..' '..(ok and('"'..texts.text(TEXTS[name],texts.language(world.runtime))..'"')or'NOT RESOLVED')
    end
    return table.concat(parts,', ')
end
local text={state='idle',attempts=0,retry_at=0,probed=false}
local clock=0
local function text_report(handle)
    if handle.status=='applied'then
        text.state='applied'
        mod:log(('PRESENTATION: the carrier %s text APPLIED aboard the ship: its row holds %s; its text shows: %s'):format(
            carrier.name,row_look(world_module.open()),shown(world_module.open())))
    elseif handle.status=='restored'then
        text.state='restored'
        mod:log('PRESENTATION: the carrier '..carrier.name..' text RESTORED: its row holds '..row_look(world_module.open()))
    else
        local transient=tostring(handle.reason):find('TARGET_UNAVAILABLE',1,true)~=nil and text.attempts<6
        text.state=transient and'idle'or'refused'
        text.retry_at=clock+5
        mod:log(('PRESENTATION: the carrier text %s: %s: %s'):format(text.state=='refused'and'REFUSED (nothing written)'
            or'not ready (retried)',tostring(handle.code),tostring(handle.reason)))
    end
end
local function text_step(world,mission)
    if not text.probed then
        local r=texts.inspect(world.runtime)
        if not r.available then return end
        text.probed=true
        local ok=r.spare>=1 and#r.collisions==0 and not tostring(r.language):find('unknown',1,true)
        mod:log(('text probe: game text registry %d of %d tables, %d spare; language %s; id clashes: %s -> %s'):format(
            r.count,r.capacity,r.spare,tostring(r.language),#r.collisions==0 and'none'or table.concat(r.collisions,', '),
            ok and'PASS'or'FAIL: the custom text would be refused'))
    end
    if not(carrier.name and carrier.look)then return end
    if text.state=='applying'or text.state=='restoring'or text.state=='refused'or clock<text.retry_at then return end
    if not settled(present)then return end
    local on=wanted(present)
    -- The icon first (a clean log order): the text waits until the icon's ensure has a result.
    if on and not mission and(text.state=='idle'or text.state=='restored')and carrier.look.result~=nil then
        text.state='applying';text.attempts=text.attempts+1
        presentation.apply_text({carrier=carrier.name,name=NAME,nameCased=CASED,description=DESCRIPTION},text_report)
    elseif not on and text.state=='applied'and not mission then
        text.state='restoring'
        presentation.restore(text_report)
    end
end

-- The custom code against the codes of the saved loadout's stratagems (read-only): {"<name> (<code>) <relation>"}.
local function saved_conflicts(world,ids)
    local out={}
    for _,id in ipairs(ids or{})do
        if id~=carrier.id then
            local values=code_values(world,id)
            local relation=values and calldown.relation(CODE_VALUES,values)
            if relation then
                out[#out+1]=('%s (%s) %s'):format(code_name(id,values),calldown.text(values),relation_text(relation))
            end
        end
    end
    return out
end

-- Aboard the ship: the PRE-MISSION CHECK, read-only, whenever the saved loadout, the virtual slots, the carrier, a row's
-- look or code changes: the virtual Gas Barrage slots, the saved tokens, the carrier and whether it is in the saved
-- loadout (then the test is refused), whether the saved order is the one the virtual slots were recorded in, the token's
-- and the donor's rows native, the carrier's look and code, and the code against the saved loadout.
local saved_key
local pre={ready=false,carrier_saved=false}
local function ship_step(world)
    discovery_step(world)
    local saved=loadout.saved(world)
    local parts,ids,carrier_saved,donor_saved={},{},false,false
    for index,pair in ipairs(saved and saved.pairs or{})do
        parts[index]=names_by_id[pair.id]or tostring(pair.id)
        ids[index]=pair.id
        if carrier.id and pair.id==carrier.id then carrier_saved=true end
        if pair.id==DONOR_ID then donor_saved=true end
    end
    -- The virtual Gas Barrage slots and their recorded order, from the Runtime's own record (a spec needs no carrier).
    local spec
    local set=selector.virtual_slots()
    if set then
        local slots_list={}
        for slot=0,3 do
            local e=set.slots[slot]
            if e and e.definition==GAS.id then slots_list[#slots_list+1]=slot end
        end
        if#slots_list>0 then spec={slots=slots_list,order=set.pairs}end
    end
    local token_ok,look_now,code_now=native(world,TOKEN_ID),row_look(world),row_code_text(world)
    local others=others_text(world)
    local conflicts=carrier.id and saved_conflicts(world,ids)or{}
    local key=table.concat(parts,'; ')..' | '..selector.slots_text(selector.virtual_slots())..' | '..look_now..' | '
        ..code_now..' | '..others..' | '..tostring(carrier.name)..' | '..tostring(code_wanted())
    if key==saved_key then return end
    saved_key=key
    local found,n=selector.reconstruct(ids)
    local matched=found~=nil and spec~=nil
    if matched then for _,slot in ipairs(spec.slots)do if found[slot]~=GAS.id then matched=false end end end
    local reasons={}
    if spec and matched and not carrier.name then
        reasons[#reasons+1]=discovery.waiting and('no carrier yet: '..discovery.waiting)or
            'no eligible carrier (see the CARRIER CANDIDATE lines)'
    end
    if carrier_saved then
        reasons[#reasons+1]=('TEST REFUSED: the carrier %s is in the saved loadout (while this proof runs it presents as '
            ..'Orbital Gas Barrage; the custom Gas Barrage is the custom panel\'s tile): replace it with another stratagem')
            :format(carrier.name)
    end
    if not spec then reasons[#reasons+1]='no virtual Gas Barrage slot: select Orbital Gas Barrage in the custom panel'end
    if spec and not matched then
        reasons[#reasons+1]='the saved order is not the one the virtual slots were recorded in (leave the loadout screen '
            ..'so the game saves it, or select the slot again)'
    end
    if token_ok~=true or code_native(world,TOKEN_ID)~=true then
        reasons[#reasons+1]='the Orbital Precision Strike row is not native'
    end
    if code_native(world,DONOR_ID)==false then reasons[#reasons+1]='the donor '..DONOR..' code is not native'end
    if carrier.name and look_now~='the Gas Barrage text and the Gas Barrage icon'then
        reasons[#reasons+1]='the carrier\'s Gas Barrage look is not ready yet'
    end
    if carrier.code_refused then
        reasons[#reasons+1]='the Gas Barrage code was refused (see CODE CHECK)'
    elseif code_wanted()and code_now~=CODE_HELD then
        reasons[#reasons+1]='the carrier\'s Gas Barrage code is not applied yet'
    end
    if#conflicts>0 then
        reasons[#reasons+1]='TEST REFUSED: the Gas Barrage code '..CODE_TEXT..' conflicts with your loadout: '
            ..table.concat(conflicts,'; ')
    end
    pre={ready=#reasons==0,carrier_saved=carrier_saved,slots=spec and spec.slots,look=look_now}
    mod:log(('PRE-MISSION CHECK: virtual Gas Barrage slots = %s; saved tokens = %s; carrier = %s (stable id %s); carrier '
        ..'present in saved loadout = %s; 120mm present in saved loadout = %s; saved order matches the virtual identity = '
        ..'%s%s; %s; the carrier row holds %s and %s; the Gas Barrage code against the saved loadout: %s -> %s'):format(
        spec and(#spec.slots..' (loadout slot'..(#spec.slots==1 and' 'or's ')..list(spec.slots)..')')or'0',
        #parts>0 and table.concat(parts,'; ')or'none',tostring(carrier.name),tostring(carrier.id),tostring(carrier_saved),
        tostring(donor_saved),tostring(matched),found and(' (reconstructed: '..n..' slot'..(n==1 and''or's')..')')or'',
        others,look_now,code_now,#conflicts==0 and'no conflict'or table.concat(conflicts,'; '),
        #reasons==0 and'READY: start a solo mission'or('NOT READY: '..table.concat(reasons,'; '))))
end

----------------------------------------------------------------------------------------------- the mission --
local M_={in_mission=false,clock=0}
local function reset_mission()
    M_.clock,M_.populated,M_.probed,M_.op,M_.result,M_.hud,M_.calls,M_.conflicts=0,nil,false,'idle',nil,nil,{},{}
    M_.unconverting,M_.retry_return=nil,nil
end
reset_mission()
local function record_text(world)
    local view=slots.inspect(world,{token=TOKEN,carrier=carrier.name or DONOR})
    if not view.entries then return tostring(view.record and view.record.reason)end
    local out={}
    for _,entry in ipairs(view.entries)do
        out[#out+1]=('%d:%s%s'):format(entry.index,label(world,entry.type),entry.granted==1 and'*'or'')
    end
    return table.concat(out,', ')..' (* granted)'
end
-- The custom code against every entry of the mission record except the carrier's own (read-only):
-- {{index, type, values, relation, text}}, or nil when the record is unreadable.
local function record_conflicts(world)
    local record=slots.local_record(world)
    if not record then return nil end
    local out={}
    for _,entry in ipairs(record.entries)do
        if entry.type~=carrier.kind then
            local values=row_code(world,row_of(world,entry.type))
            local relation=values and calldown.relation(CODE_VALUES,values)
            if relation then
                local id=loadout.id_of(world,entry.type)
                out[#out+1]={index=entry.index,type=entry.type,values=values,relation=relation,
                    text=('record entry %d %s (type %d, %s) %s'):format(entry.index,code_name(id,values),entry.type,
                        calldown.text(values),relation_text(relation))}
            end
        end
    end
    return out
end
local function conversion_report(handle)
    M_.result=handle
    if handle.status=='converted'then
        M_.op='converted'
        M_.hud={since=M_.clock}
        local pairs_text={}
        for k,index in ipairs(handle.indices)do
            pairs_text[#pairs_text+1]=('loadout slot %d = record entry %d'):format(handle.slots[k],index)
        end
        local world=world_module.open()
        mod:log(('MISSION START: conversion APPLIED: %s -> the carrier %s (type %d, stable id %d; its own type and stable '
            ..'id, unchanged); carrier package %s; %s; every other record entry and the count unchanged: %s; the record '
            ..'now: %s'):format(table.concat(pairs_text,', '),carrier.name,handle.carrier,handle.carrierId,
            tostring(handle.package),handle.report and(handle.report.writes..' writes')or'?',
            tostring(handle.verify and handle.verify.others),record_text(world)))
        -- The identity stays with the slot: the Runtime's record still names each converted loadout slot.
        local set=selector.virtual_slots()
        local after=slots.local_record(world)
        for k,index in ipairs(handle.indices)do
            local slot=handle.slots[k]
            local entry=set and set.slots[slot]
            local now=after and after.entries[index+1]
            mod:log(('IDENTITY: loadout slot %d = %s (the Runtime\'s record: %s) is record entry %d, now %s'):format(slot,
                entry and entry.definition or'NOTHING',entry and entry.definition==GAS.id and'kept'or'LOST',index,
                now and label(world,now.type)or'unreadable'))
        end
        mod:log(('PRESENTATION: %s; the carrier row holds %s'):format(others_text(world),row_look(world)))
        mod:log(('CODE: the carrier %s row holds %s (its native code: %s); %s'):format(carrier.name,row_code_text(world),
            carrier.native_code and calldown.text(carrier.native_code)or'not read',others_text(world)))
    else
        M_.op='refused'
        mod:log(('MISSION START: conversion REFUSED (nothing written; the mission goes on normally): %s: %s'):format(
            tostring(handle.code),tostring(handle.reason)))
    end
end
-- The HUD after the conversion: each converted entry's HUD slot type, icon and drawn arrows, and the carrier row's text
-- (read-only).
local function hud_step(world)
    if not(M_.hud and not M_.hud.done and M_.result)then return end
    local types=slots.hud_types(world)
    local proven=selector.prove(world)
    local entries=proven and overlay.hud_entries(world)
    local values=domain.presentation.values[tostring(carrier.id)]
    local located,why_code,why=stratagem_hud.locate(world,M_.result.carrier)
    local all=types~=nil and located~=nil
    local parts={}
    for k,index in ipairs(M_.result.indices)do
        local kind=types and types[index]
        local icon=entries and entries[index]and world.view.read(entries[index].icon+SEL.slotIcon.name,8)
        local icon_text=icon==images.bytes(ICON)and'the Gas Barrage icon'or(values and icon==presentation.encode('icon',
            values.icon))and'the carrier\'s native icon'or icon and('another icon')or'icon unread'
        if kind~=M_.result.carrier then all=false end
        local arrows=located and located.index==index and calldown.text(located.shows)
            or('not read ('..tostring(why_code)..': '..tostring(why)..')')
        parts[#parts+1]=('HUD slot %d (loadout slot %d, record entry %d): %s; icon element shows %s; its arrows draw %s'):format(
            index,M_.result.slots[k],index,label(world,kind),icon_text,arrows)
    end
    if all then
        M_.hud.done=true
        mod:log('HUD: '..table.concat(parts,'; ')..'; the carrier row holds '..row_look(world)..' and '..row_code_text(world)
            ..'; its text shows: '..shown(world)..'; '..others_text(world)..' (the vanilla HUD refreshed each slot from the '
            ..'type change; nothing written to the HUD by this proof)')
    elseif M_.clock>M_.hud.since+10 then
        M_.hud.done=true
        mod:log('HUD did NOT follow within 10 s: '..table.concat(parts,'; '))
    end
end
-- A record entry related to the Gas Barrage code that appears after the conversion (no code path adding one
-- mid-mission is known; a record the host replaces would also discard the conversion): the matcher would select the
-- carrier first and leave that stratagem uncallable, so the virtual slot is returned to its token through the
-- conversion's own guarded restore (1 write; retried while a call-in of it is in flight). Nothing else is written.
local function unconverted(handle)
    M_.unconverting=handle.status=='pending'or nil
    if handle.status=='restored'then
        M_.op='returned'
        mod:log(('CODE CONFLICT: the virtual slot returned to its token %s (%d write%s, exact: %s): the related '
            ..'stratagem stays callable; the Gas Barrage is not available for the rest of this mission'):format(TOKEN,
            handle.report.writes,handle.report.writes==1 and''or's',tostring(handle.exact)))
    elseif handle.code=='IN_USE'then
        M_.retry_return=M_.clock+1
    else
        M_.op='returned'
        mod:log(('CODE CONFLICT: the virtual slot was not returned: %s: %s'):format(tostring(handle.code),
            tostring(handle.reason)))
    end
end
local function conflict_step(world)
    if M_.op~='converted'or not code_wanted()then return end
    local found=record_conflicts(world)
    local fresh=false
    for _,c in ipairs(found or{})do
        local key=c.index..':'..c.type
        if not M_.conflicts[key]then
            M_.conflicts[key],fresh=true,true
            mod:log(('CODE CONFLICT: the mission record now holds %s; the carrier answers to %s and the game would select '
                ..'it first: returning the virtual slot to its token'):format(c.text,CODE_TEXT))
        end
    end
    if(fresh or M_.retry_return)and not M_.unconverting and(not M_.retry_return or M_.clock>=M_.retry_return)then
        M_.retry_return,M_.unconverting=nil,true
        slots.restore(unconverted)
    end
end
-- Call-ins of the converted entries: a call-in in flight (the game's own table) and the entry's cooldown (read-only).
local function call_step(world)
    if M_.op~='converted'then return end
    local seen=slots.observe(world)
    for _,item in ipairs(seen or{})do
        local last=M_.calls[item.index]
        if last then
            local slot
            for k,index in ipairs(M_.result.indices)do if index==item.index then slot=M_.result.slots[k]end end
            if item.flying and not last.flying then
                mod:log(('CALL-IN: the virtual Gas Barrage slot (loadout slot %d, record entry %d) was called: a call-in '
                    ..'of %s is in flight (the game\'s own beacon); the carrier row holds %s, the only code that calls it; '
                    ..'expect the carrier\'s own normal attack'):format(slot,item.index,label(world,item.type),
                    row_code_text(world)))
            end
            if item.cooldown~=last.cooldown then
                mod:log(('CALL-IN: record entry %d (loadout slot %d) cooldown changed: the game started the carrier\'s '
                    ..'cooldown on that slot'):format(item.index,slot))
            end
        end
        M_.calls[item.index]=item
    end
end
local function refuse(text)
    M_.op='test refused'
    mod:log('MISSION START: TEST REFUSED (nothing converted, nothing written): '..text)
end
local function mission_step(world,state)
    M_.clock=M_.clock+0.5
    hud_step(world)
    call_step(world)
    conflict_step(world)
    if not M_.populated then
        if stratagem_hud.populated(world)then M_.populated=M_.clock end
        return
    end
    if M_.clock<M_.populated+5 then return end
    if not M_.probed then
        M_.probed=true
        local spec,why=selector.conversion_spec(GAS.id,carrier.name)
        mod:log('MISSION START: the local mission record: '..record_text(world))
        mod:log(spec and('MISSION START: virtual slot%s discovered: loadout slot%s %s = %s (token %s); recorded loadout '
            ..'order: %s; carrier %s'):format(#spec.slots==1 and''or's',#spec.slots==1 and''or's',list(spec.slots),GAS.id,
            TOKEN,order_text(spec.order),tostring(carrier.name))or('MISSION START: no virtual slot: '..tostring(why)))
        if carrier.name then
            local view=slots.inspect(world,{token=TOKEN,carrier=carrier.name})
            mod:log(('MISSION START: carrier %s: owned %s, selectable %s, enabled %s, unlimited %s, in the record %s, '
                ..'call-in package %s; %s stratagem record(s); host %s'):format(carrier.name,tostring(view.carrierOwned),
                tostring(view.carrierSelectable),tostring(view.carrierEnabled),tostring(view.carrierUnlimited),
                tostring(view.carrierInRecord==true),tostring(view.carrierPackage),tostring(view.records),
                tostring(state.host)))
        end
    end
    if M_.op=='idle'then
        if not carrier.name then return refuse('no carrier was chosen aboard the ship')end
        if row_look(world)~='the Gas Barrage text and the Gas Barrage icon'then
            return refuse(('the carrier %s does not hold the Gas Barrage look (%s); it is applied aboard the ship before '
                ..'the mission'):format(carrier.name,row_look(world)))
        end
        if not settled(code_on)then return end
        if code_wanted()and row_code_text(world)~=CODE_HELD then
            return refuse(('the carrier %s does not hold the Gas Barrage code (%s); it is applied aboard the ship before '
                ..'the mission'):format(carrier.name,row_code_text(world)))
        end
        -- The test is refused with the carrier in the saved loadout (checked aboard the ship) or in this record.
        local view=slots.inspect(world,{token=TOKEN,carrier=carrier.name})
        if pre.carrier_saved or view.carrierInRecord then
            return refuse(('the carrier %s is in the %s; it must not be selected'):format(carrier.name,
                pre.carrier_saved and'saved loadout'or'mission record'))
        end
        -- The code against every entry of this mission record (the granted ones too), before anything is converted.
        local conflicts=record_conflicts(world)
        if conflicts==nil then return refuse('the mission record is unreadable for the code check')end
        if code_wanted()and#conflicts>0 then
            local out={}
            for _,c in ipairs(conflicts)do out[#out+1]=c.text;M_.conflicts[c.index..':'..c.type]=true end
            return refuse('the Gas Barrage code '..CODE_TEXT..' conflicts with this mission record: '..table.concat(out,'; '))
        end
        mod:log(('CODE CHECK: the Gas Barrage code %s against this mission record (%s): no entry has an equal code, a '
            ..'code that starts with it or a code that is its start'):format(CODE_TEXT,record_text(world)))
        if not settled(convert)then return end
        if not wanted(convert)then
            M_.op='off'
            mod:log('MISSION START: conversion is switched off (Gas Barrage Mission Proof > Convert): nothing written')
            return
        end
        M_.op='converting'
        selector.convert_virtual(GAS.id,conversion_report,carrier.name)
    end
end

----------------------------------------------------------------------------------------------- the loop --
-- The public ensures' results (the icon and the code), logged when the result changes.
local said={}
local function ensure_report(key,handle,what)
    local result=handle and handle.result and handle.result.status
    local now=tostring(result)..(handle and handle.error and(' '..tostring(handle.error))or'')
    if handle and now~=said[key]then
        said[key]=now
        local world=world_module.open()
        local held=key=='code'and world and('; the carrier row holds '..row_code_text(world)..'; '..others_text(world))or''
        mod:log(('%s: the carrier %s %s: %s %s%s'):format(key=='code'and'CODE'or'PRESENTATION',carrier.name,what,
            tostring(handle.status),now,held))
    end
end
hd2.every(0.5,function()
    clock=clock+0.5
    ensure_report('icon',carrier.look,'icon (public presentation_icon ensure)')
    ensure_report('code',carrier.code,'code (public calldown_code ensure)')
    local world=world_module.open()
    if not world then return end
    local state=hd2.game_state()
    local mission=state and state.mission
    if mission and not M_.in_mission then
        M_.in_mission=true
        reset_mission()
        mod:log(('MISSION START: mission started (host %s); the Runtime\'s virtual slots: %s; carrier %s; the last '
            ..'pre-mission check: %s'):format(tostring(state.host),selector.slots_text(selector.virtual_slots()),
            tostring(carrier.name),pre.ready and'READY'or(pre.carrier_saved and'REFUSED (the carrier in the saved loadout)'
            or'NOT READY')))
    elseif not mission and M_.in_mission then
        M_.in_mission=false
        local current=slots.state()
        mod:log(('MISSION END: state %s; conversion %s; the carrier row holds %s (the code stays with the ensure while its '
            ..'toggle is on)'):format(tostring(state and state.name),current and current.converted
            and'still held (the game has not rebuilt the record yet)'or(M_.op=='converted'and'gone: the game rebuilt the '
            ..'record (see "no longer hold")'or M_.op),row_code_text(world)))
        saved_key=nil
    end
    if state then text_step(world,mission)end
    if mission then mission_step(world,state)elseif state then ship_step(world)end
end,{id='gas-barrage-mission-proof'})

----------------------------------------------------------------------------------------------- the keys --
hd2.input.bind('gas_barrage_mission_proof.focus',{key='F6',on_press=function()mod:log('F6: '..P.focus_next())end})
hd2.input.bind('gas_barrage_mission_proof.unfocus',{key='Ctrl+F6',on_press=function()mod:log('Ctrl+F6: '..P.clear_focus())end})
hd2.input.bind('gas_barrage_mission_proof.select',{key='F7',on_press=function()mod:log('F7: '..P.press())end})
hd2.input.bind('gas_barrage_mission_proof.restore',{key='Ctrl+F7',on_press=function()mod:log('Ctrl+F7: '..P.cancel())end})
hd2.input.bind('gas_barrage_mission_proof.slot_overlays',{key='Ctrl+F9',on_press=function()
    mod:log('Ctrl+F9: slot overlays '..(P.set_slot_overlays(not P.overlays)and'on'or'off (the native icons underneath)'))
end})
hd2.input.bind('gas_barrage_mission_proof.status',{key='F9',on_press=function()
    local world=world_module.open()
    mod:log('F9 ['..BUILD..']: '..P.status()..'; virtual slots: '..selector.slots_text(selector.virtual_slots())
        ..'; carrier '..tostring(carrier.name)..' (stable id '..tostring(carrier.id)..'; its row holds '
        ..(world and(row_look(world)..' and '..row_code_text(world))or'unreadable')..'); '
        ..(world and others_text(world)or'')..'; text '..text.state..'; icon ensure '..tostring(carrier.look and
        carrier.look.status)..' '..tostring(carrier.look and carrier.look.result and carrier.look.result.status)
        ..'; code ensure '..tostring(carrier.code and carrier.code.status)..' '..tostring(carrier.code and
        carrier.code.result and carrier.code.result.status)..'; pre-mission check '..(pre.ready and'READY'or'NOT READY'))
    saved_key=nil
end})
hd2.input.bind('gas_barrage_mission_proof.mission',{key='F10',on_press=function()
    local world=world_module.open()
    local state=hd2.game_state()or{}
    local current=slots.state()
    local seen=world and slots.observe(world)
    local parts={}
    for _,item in ipairs(seen or{})do
        parts[#parts+1]=('entry %d %s in flight %s'):format(item.index,label(world,item.type),tostring(item.flying))
    end
    mod:log(('F10 [%s]: mission %s, host %s; carrier %s (its row holds %s); conversion %s%s; converted entries: %s; '
        ..'record: %s'):format(BUILD,tostring(state.mission==true),tostring(state.host),tostring(carrier.name),
        world and row_code_text(world)or'unreadable',M_.op,M_.result and M_.result.code and(' ('..tostring(M_.result.code)
        ..')')or'',current and current.converted and table.concat(parts,', ')or'none',world and state.mission
        and record_text(world)or'-'))
end})
mod:log('loaded ('..BUILD..'): virtual stratagem '..GAS.id..' (token '..TOKEN..'; carrier: discovered from what you '
    ..'own, never the donor '..DONOR..'; icon orbital_gas_barrage_masks; code '..CODE_TEXT..' on the carrier) and 5 '
    ..'visual placeholders. Ship: click or F7 selects; Ctrl+F7 undoes; F6 focus; Ctrl+F9 slot overlays; F9 status. '
    ..'Mission: F10 status.')
