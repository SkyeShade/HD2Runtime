local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanCasProof 0.1.1: THE RED-BEACON CARRIER (research/docs/pelican-cas-F5FEE03DCFDB.md, "Carrier allocation").
-- Development only; solo host; no multiplayer, no weapons.
-- 0.1.0 is LIVE-PROVEN and unchanged except for the carrier choice: its carrier was the Orbital EMS Strike, an orbital
-- bombardment whose beacon is BLUE. "Orbital" (the delivery family) and the call-in class never meant offensive. Now the
-- carrier's beacon category is the colour of its beam, the row's +0xD4 (1 red = offensive, 2 blue = support, 3 yellow =
-- other; research "beaconPresentation"), reported apart from its family and its ping colour (+0xB8), and the Pelican CAS
-- takes only a RED-beacon carrier: an orbital first, then an Eagle (refused by the discovery's own guards in this build:
-- limited uses, Eagle Rearm), then any other red carrier; none left: refused (the explicit fallback: refuse).
-- PelicanCasProof 0.1.0: PELICAN CLOSE AIR SUPPORT, THE CALL-IN AND THE HOVER OVER THE BEACON.
--
-- The first custom stratagem whose delivery is a Runtime-summoned game Pelican:
--   ship: Pelican Close Air Support from the custom panel (the saved loadout holds the Precision Strike token);
--   -> a CARRIER ALLOCATED for it (runtime/carrier_allocator.lua): the Gas Barrage's discovery runs first and reserves
--      every carrier it could use; the Pelican CAS takes the first UNUSED RED-beacon carrier (owned, selectable,
--      enabled, unlimited, not in the loadout, never the 120mm or the Gas Strike): an orbital, then an Eagle, then any
--      other red carrier; refused when none is left (never shared). Cached aboard the ship and REVALIDATED before every
--      mission;
--   -> aboard the ship the carrier is NATIVE; at mission start (solo) its look becomes Pelican Close Air Support (the
--      Runtime text, the masked icon) and its code LEFT DOWN LEFT UP LEFT UP (runtime/carrier_presentation.lua), then
--      the beacon watch and the 60 s cooldown are armed and ONLY the virtual slot is converted to the carrier;
--   -> a call throws the CARRIER's own beacon (its red beam, its own call-in time); in the beacon's FIRST Runtime update
--      its delivery becomes 'none' (runtime/beacons.lua: one guarded write of THAT beacon's type), so the carrier's own
--      payload never executes;
--   -> the beacon lands: its landing position is recorded; at its activation the Runtime asks for one EMPTY game Pelican
--      (hd2.pelican.spawn) anchored at that landing position: it is created 250 m back along your heading and 80 m up,
--      flies in, hovers over the beacon (the anchor, read back from its own drop-position record), is held 60 s after
--      its release (one guarded write of its own release time) and leaves normally;
--   -> the slot's cooldown is 60 s from the call-in's arrival (runtime/slot_cooldown.lua: the mission record entry
--      only; the carrier's own cooldown is never written);
--   -> back aboard the ship the carrier's look and code are restored exactly (the loadout screen opening is the hard
--      boundary).
-- Never written: the carrier's StratagemInfo cooldown or payload, any shared Pelican, carrier or weapon definition, the
-- token, the save, the account, the catalogue. The Gas Barrage payload is not part of this proof. One custom stratagem
-- per mission in this build (the presentation, conversion and cooldown each hold one carrier): install this proof
-- without the Gas Barrage proofs.
-- Read-only diagnostics (labelled INTERNAL, not public API): the beacon's landing state, and which movement components
-- hold the Pelican (runtime/pelicans.lua movers: a Pelican in the flight component alone is retargetable by data).
local mod=hd2.mod()
local BUILD='0.1.1 RED-BEACON CARRIER BUILD'
mod:log('PelicanCasProof '..BUILD..': ship: select Pelican Close Air Support in the custom panel (F6 focus, F7 or a '
    ..'click selects); leave the loadout screen; the carrier is ALLOCATED with a RED beacon ("CARRIER CANDIDATE" lines '
    ..'with each carrier\'s family and beacon colour, "CUSTOM CARRIER: ...", "CARRIER: ... SELECTED ... a red beacon") '
    ..'and stays native aboard the ship; wait for "PRE-MISSION CHECK ... READY", then a SOLO mission: '
    ..'"MISSION START: carrier presentation APPLIED", then "READY TO CALL". Call it with LEFT DOWN LEFT UP LEFT UP: expect '
    ..'"BEACON NEUTRALIZED" (the carrier\'s own attack never comes), "BEACON LANDED", "BEACON ACTIVATED", "PELICAN CAS '
    ..'REQUESTED", an EMPTY Pelican flying in and "PELICAN CAS HOVERING ... from the beacon", "PELICAN CAS HELD", about '
    ..'60 s over the beacon (move away: it must stay), then "PELICAN CAS DEPARTING", "PELICAN CAS GONE" and "PELICAN CAS '
    ..'SUMMARY"; the slot cools 60 s ("COOLDOWN: Pelican CAS override = 60.0"). Back aboard the ship: "RETURN TO SHIP: '
    ..'carrier presentation RESTORED". F9 ship status; F10 mission status.')

local panel=require('hd2runtime/runtime/custom_stratagem_panel')
local selector=require('hd2runtime/runtime/stratagem_selector')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local texts=require('hd2runtime/runtime/text_resources')
local presentation=require('hd2runtime/runtime/stratagem_presentation')
local carrier_presentation=require('hd2runtime/runtime/carrier_presentation')
local images=require('hd2runtime/runtime/image_resources')
local calldown=require('hd2runtime/runtime/calldown_codes')
local world_module=require('hd2runtime/runtime/event_world')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local stratagem_hud=require('hd2runtime/runtime/stratagem_hud')
local allocator=require('hd2runtime/runtime/carrier_allocator')
local beacons=require('hd2runtime/runtime/beacons')
local cool=require('hd2runtime/runtime/slot_cooldown')
-- INTERNAL read-only observation (never written through here): the beacon's landing state and the Pelican's movers.
local beacon_reader=require('hd2runtime/runtime/beacon_redirect')
local pelicans=require('hd2runtime/runtime/pelicans')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local domain=require('hd2runtime/domains/stratagem_calldown')
local SEL=require('hd2runtime/domains/stratagem_selector')
local TABLE=require('hd2runtime/schemas/current').stratagem.table_rva
local RESOURCE='mods/skyeshade/hd2runtime_pelican_cas_proof'
local A=allocator.PELICAN_CAS
local TOKEN=A.token
local TOKEN_ID=catalog.stratagems[TOKEN].root.id
local HOVER,COOLDOWN=60,60
-- "At the beacon": the hover point within this many metres of the beacon's landing position, horizontally.
local AT_BEACON=25
-- The Pelican CAS code (the public field's direction names), and its native values.
local CODE={'left','down','left','up','left','up'}
local CODE_VALUES=assert(calldown.values(CODE))
local CODE_TEXT=calldown.text(CODE_VALUES)

-- The Runtime-rendered icon (the game's mask convention), converted from the supplied source/pelican_close_air_support.png.
local ICON=hd2.resources.image('pelican_close_air_support')
local NAME=texts.handle('pelican_close_air_support_name','PELICAN CLOSE AIR SUPPORT',RESOURCE)
local CASED=texts.handle('pelican_close_air_support_name_cased','Pelican Close Air Support',RESOURCE)
local DESCRIPTION=texts.handle('pelican_close_air_support_description','Calls in a Pelican that flies to the beacon and '
    ..'holds over it for 60 seconds.',RESOURCE)
local TEXTS={name=NAME,nameCased=CASED,description=DESCRIPTION}
local CAS=virtual.define({id=A.id,display={name=CASED,description=DESCRIPTION,icon=ICON},selection={token=TOKEN},
    mission={discover=true,exclude=A.exclude}},RESOURCE)
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function at(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'(?)'end
local function flat(a,c)
    if not(a and c)then return nil end
    return math.sqrt((a.x-c.x)^2+(a.y-c.y)^2)
end

local names_by_id={}
for name,entry in pairs(catalog.stratagems)do names_by_id[entry.root.id]=name end
-- Mission-only types are not catalogued: the calldown research names the ones whose codes overlap others.
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
local function yes(v)return v and'true'or'false'end

------------------------------------------------------------------------------------------------- the ship --
local function report_selection(handle)
    if handle.status=='selected'then
        mod:log(('SHIP: Pelican Close Air Support SELECTED into loadout slot %d; the underlying token written: %s%s; '
            ..'virtual slots: %s'):format(handle.index,TOKEN,handle.written and''or' (already held: no write)',
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

-- The carrier: ALLOCATED aboard the ship (runtime/carrier_allocator.lua, read-only) once the catalogue is ready, a
-- virtual Pelican CAS slot exists and the saved loadout is the one it was recorded in; cached and revalidated.
local carrier={name=nil,id=nil,kind=nil,class=nil,native_code=nil,code_refused=nil}
local allocation={key=nil,waiting=nil,retry=0,line=nil}
local function saved_ids(world)
    local saved=loadout.saved(world)
    if not saved then return nil end
    local ids,set={},{}
    for k,pair in ipairs(saved.pairs or{})do ids[k]=pair.id;set[pair.id]=true end
    return ids,set
end
-- Whether a stratagem (by stable id) is selectable in the ship loadout (row +0x80 bit 1): true / false / nil.
local ROWM=require('hd2runtime/domains/stratagem_slots').row
local function selectable(world,id)
    local row=row_by_id(world,id)
    local flags=row and world.view.u32(row+ROWM.selectable)
    if not flags then return nil end
    return math.floor(flags/ROWM.selectableBit)%2==1
end
-- One candidate of the Pelican CAS's discovery: its family and call-in class, its beacon category (the beam colour,
-- row +0xD4) and ping colour (+0xB8), and the allocation's verdict.
local function candidate_line(c,verdict)
    local own=c.ownership
    local own_text=yes(c.owned)
    if own and not c.owned then
        own_text=own_text..(own.found and(' (catalogue state %s, parent %s)'):format(tostring(own.state),
            tostring(own.parent))or(' (not in the catalogue range %d..%d)'):format(own.range[1],own.range[2]))
    end
    return ('CARRIER CANDIDATE: %s (type %d, stable id %d): family = %s (%s, class %s), beacon_category = %s (%s beam, '
        ..'row +0xD4 = %s; %s ping, +0xB8 = %s): owned=%s selectable=%s enabled=%s unlimited=%s in_loadout=%s '
        ..'special_case=%s package_available=%s presentation=%s code=%s -> %s'):format(c.name,c.type,c.id,
        tostring(c.family),tostring(c.component or'-'),tostring(c.class),tostring(c.beaconCategory),tostring(c.beamColour),
        tostring(c.beam),tostring(c.pingColour),tostring(c.ping),own_text,yes(c.selectable),yes(c.enabled),yes(c.unlimited),
        yes(c.inLoadout),c.special and('true ('..c.special..')')or'false',yes(c.package),yes(c.presentation),yes(c.code),
        tostring(verdict))
end
-- The custom code against every reviewed native code (read-only). The game's matcher selects the first record entry
-- whose whole code is entered: an EQUAL code is ambiguous, a code that is the START of another's makes that one
-- uncallable while the carrier is ready, one that EXTENDS another's is never reached. A relation with a stratagem a
-- player can select refuses the code; one with a mission-only stratagem is listed and guarded (the mission record is
-- checked before the conversion and watched after it).
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
    mod:log(('CODE CHECK: the Pelican CAS code %s for the carrier %s (stable id %d): its native code read from its row '
        ..'first: %s (the reviewed native code: %s; equal: %s); native codes equal to it or related to a selectable '
        ..'stratagem: %s; mission-only stratagems related to it: %s (guarded: a mission record holding one refuses the '
        ..'conversion) -> %s'):format(CODE_TEXT,c.name,c.id,native_now and calldown.text(native_now)or'unreadable',
        reviewed and calldown.text(reviewed)or'none',yes(native_now and reviewed and calldown.same(native_now,reviewed)),
        #refused==0 and'none'or table.concat(refused,'; '),#guarded==0 and'none'or table.concat(guarded,'; '),
        ok and'SAFE: applied at mission start (aboard the ship the carrier keeps its own code)'
        or'REFUSED: the code is not applied'))
    return ok and native_now or nil
end
local function forget_carrier()
    carrier.name,carrier.id,carrier.kind,carrier.class,carrier.native_code,carrier.code_refused=nil,nil,nil,nil,nil,nil
end
-- Runs the allocation for every custom stratagem of this build (the Gas Barrage first) against `present_set`, logs it
-- and takes the Pelican CAS's carrier. 'taken', 'none' or 'waiting' (and why).
local function allocate(world,present_set,where)
    local a=allocator.allocate(world,allocator.DEFINITIONS,present_set)
    if not a.ready then return'waiting',a.reason end
    local mine=a.assignments[A.id]
    local verdicts=a.verdicts[A.id]or{}
    for _,c in ipairs(a.candidates[A.id]or{})do mod:log(candidate_line(c,verdicts[c.id]))end
    allocation.line=a.line
    mod:log(a.line..' ('..where..'; the Gas Barrage reserves every carrier its discovery could use; the Pelican CAS takes '
        ..'the first unused RED-beacon carrier: an orbital, then an Eagle, then any other red carrier, each by its red ping, '
        ..'call-in class, then stable id; none: refused)')
    if not mine then
        forget_carrier()
        mod:log('CARRIER: none for the Pelican CAS: '..tostring(a.refused[A.id])..'; carrier = nil; it refuses safely '
            ..'(allocated again when the loadout changes)')
        return'none'
    end
    if mine.stable_id==carrier.id then return'taken'end
    forget_carrier()
    carrier.name,carrier.id,carrier.kind,carrier.class=mine.carrier,mine.stable_id,mine.type,mine.class
    mod:log(('CARRIER: %s SELECTED for the Pelican CAS (type %d, stable id %d): family = %s (class %s), '
        ..'beacon_category = %s (a %s beacon, %s ping), tier %s%s (%d red eligible, %d taken or reserved by an earlier '
        ..'custom stratagem); owned, not in the current loadout, never the 120mm or the Gas Strike; its native code: %s; '
        ..'its own cooldown %s s (never written). Do NOT select %s natively. Aboard the ship it stays native; in the '
        ..'mission it presents as Pelican Close Air Support, answers to %s and delivers nothing itself (its beacon is '
        ..'neutralized)'):format(mine.carrier,mine.type,mine.stable_id,tostring(mine.family),tostring(mine.class),
        tostring(mine.beacon),tostring(mine.beam),tostring(mine.ping),tostring(mine.tier),mine.fallback and' FALLBACK'
        or'',mine.eligible,mine.skipped,code_of(world,mine.stable_id),n1(cool.row_cooldown(world,mine.type)),
        mine.carrier,CODE_TEXT))
    local native_now=code_check(world,{name=mine.carrier,id=mine.stable_id})
    if native_now then carrier.native_code=native_now else carrier.code_refused=true end
    return'taken'
end
local function discovery_step(world)
    if carrier.name then return end
    local ids,present_set=saved_ids(world)
    if not ids then return end
    -- Only once a virtual Pelican CAS slot exists and the saved loadout is the one it was recorded in.
    if not selector.virtual_slots()then return end
    if not selector.reconstruct(ids)then return end
    local key=table.concat(ids,',')
    if key==allocation.key then return end
    if allocation.waiting then
        allocation.retry=allocation.retry-1
        if allocation.retry>0 then return end
        allocation.retry=4
    end
    local status,why=allocate(world,present_set,'aboard the ship against the saved loadout: '..order_text(ids))
    if status=='waiting'then
        if allocation.waiting~=why then mod:log('CARRIER: waiting: '..tostring(why))end
        allocation.waiting=why
        return
    end
    allocation.key,allocation.waiting=key,nil
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
    local which=bytes==images.bytes(ICON)and'the Pelican CAS icon'or bytes==presentation.encode('icon',values.icon)
        and'its native icon'or'another icon'
    return (runtime_text and'the Pelican CAS text'or native_text and'its native text'or'MIXED or other text')..' and '..which
end
local CODE_HELD='the Pelican CAS code ('..CODE_TEXT..')'
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
local function code_wanted()return carrier.native_code~=nil and not carrier.code_refused end
-- The token's row: never written.
local function others_text(world)
    return ('Orbital Precision Strike presentation native = %s, code native = %s'):format(
        tostring(native(world,TOKEN_ID)),tostring(code_native(world,TOKEN_ID)))
end
local function shown(world)
    local parts={}
    for _,name in ipairs({'name','nameCased','description'})do
        local ok=texts.resolves(world.runtime,TEXTS[name])
        parts[#parts+1]=name..' '..(ok and('"'..texts.text(TEXTS[name],texts.language(world.runtime))..'"')or'NOT RESOLVED')
    end
    return table.concat(parts,', ')
end
local text={probed=false}
local clock=0
local function text_probe(world)
    if text.probed then return end
    local r=texts.inspect(world.runtime)
    if not r.available then return end
    text.probed=true
    local ok=r.spare>=1 and#r.collisions==0 and not tostring(r.language):find('unknown',1,true)
    mod:log(('text probe: game text registry %d of %d tables, %d spare; language %s; id clashes: %s -> %s'):format(
        r.count,r.capacity,r.spare,tostring(r.language),#r.collisions==0 and'none'or table.concat(r.collisions,', '),
        ok and'PASS'or'FAIL: the custom text would be refused'))
end

-------------------------------------------------------------------------------------- carrier revalidation --
-- The allocated carrier is a CACHE, never trusted: validated with the discovery's own guards against the CURRENT
-- loadout aboard the ship whenever the saved loadout changes and every REVALIDATE_EVERY s; at mission start the whole
-- allocation runs again against the saved loadout and the mission record. Invalid: logged, discarded, allocated again
-- at once. Never while the carrier's mission presentation is still applied.
local validation={key=nil,at=-1}
local REVALIDATE_EVERY=5
local function check_carrier(present_set,where)
    local v=selector.validate_carrier(CAS.id,carrier.name,present_set)
    if not v.ready then return'waiting',v.reason end
    if v.valid then return'valid'end
    mod:log(('CARRIER INVALIDATED: %s reason: %s (%s; checked %s): the cached carrier is discarded and the allocation '
        ..'runs again now'):format(carrier.name,table.concat(v.codes,', '),table.concat(v.reasons,'; '),where))
    forget_carrier()
    allocation.key,allocation.waiting,allocation.retry=nil,nil,0
    return'invalidated'
end
local function revalidation_step(world)
    if not carrier.name or carrier_presentation.applied()then return end
    local ids,present_set=saved_ids(world)
    if not ids then return end
    local key=table.concat(ids,',')
    if key==validation.key and clock<validation.at+REVALIDATE_EVERY then return end
    validation.key,validation.at=key,clock
    if check_carrier(present_set,'aboard the ship against the saved loadout: '..order_text(ids))=='invalidated'then
        discovery_step(world)
    end
end
-- The loadout slots the Runtime records as virtual slots of a definition (no carrier needed).
local function slots_of(id)
    local set=selector.virtual_slots()
    local out={}
    for slot=0,3 do
        local e=set and set.slots[slot]
        if e and e.definition==id then out[#out+1]=slot end
    end
    return out
end
-- Virtual slots of OTHER custom stratagems (one custom stratagem per mission in this build).
local function other_custom()
    local set=selector.virtual_slots()
    local out={}
    for slot=0,3 do
        local e=set and set.slots[slot]
        if e and e.definition~=CAS.id then out[#out+1]=('loadout slot %d = %s'):format(slot,tostring(e.definition))end
    end
    return out
end
-- The current loadout in a mission: the saved loadout's stable ids and every mission record entry's.
local function mission_present(world)
    local ids,set=saved_ids(world)
    ids,set=ids or{},set or{}
    local record=slots.local_record(world)
    for _,entry in ipairs(record and record.entries or{})do
        local id=loadout.id_of(world,entry.type)
        if id then set[id]=true end
    end
    return ids,set
end
local NATIVE_LOOK='its native text and its native icon'
local function carrier_native(world)
    return carrier.id~=nil and row_look(world)==NATIVE_LOOK and code_native(world,carrier.id)==true
end
local function carrier_text(world)
    return ('the carrier %s row holds %s and %s; %s'):format(tostring(carrier.name),row_look(world),row_code_text(world),
        others_text(world))
end
-- The custom code against the codes of the saved loadout's stratagems (read-only).
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

-- Aboard the ship: the PRE-MISSION CHECK, read-only, whenever something it reports changes.
local saved_key
local pre={ready=false,carrier_saved=false}
local function ship_step(world)
    revalidation_step(world)
    discovery_step(world)
    local saved=loadout.saved(world)
    local parts,ids,carrier_saved={},{},false
    for index,pair in ipairs(saved and saved.pairs or{})do
        parts[index]=names_by_id[pair.id]or tostring(pair.id)
        ids[index]=pair.id
        if carrier.id and pair.id==carrier.id then carrier_saved=true end
    end
    local mine=slots_of(CAS.id)
    local spec=#mine>0 and{slots=mine,order=selector.virtual_slots().pairs}or nil
    local others=other_custom()
    local token_ok,look_now,code_now=native(world,TOKEN_ID),row_look(world),row_code_text(world)
    local others_now=others_text(world)
    local conflicts=carrier.id and saved_conflicts(world,ids)or{}
    local capability=hd2.pelican.status()
    local row_cd=carrier.kind and cool.row_cooldown(world,carrier.kind)
    local key=table.concat(parts,'; ')..' | '..selector.slots_text(selector.virtual_slots())..' | '..look_now..' | '
        ..code_now..' | '..others_now..' | '..tostring(carrier.name)..' | '..tostring(code_wanted())..' | '
        ..tostring(capability.status)..' | '..tostring(row_cd)
    if key==saved_key then return end
    saved_key=key
    local found,n=selector.reconstruct(ids)
    local matched=found~=nil and spec~=nil
    if matched then for _,slot in ipairs(spec.slots)do if found[slot]~=CAS.id then matched=false end end end
    local reasons={}
    if spec and matched and not carrier.name then
        reasons[#reasons+1]=allocation.waiting and('no carrier yet: '..allocation.waiting)or
            'no unused red-beacon (offensive) carrier (see the CUSTOM CARRIER and CARRIER CANDIDATE lines)'
    end
    if carrier_saved then
        reasons[#reasons+1]=('the carrier %s is in the saved loadout: it is replaced as soon as it can be revalidated')
            :format(carrier.name)
    end
    if not spec then
        reasons[#reasons+1]='no virtual Pelican CAS slot: select Pelican Close Air Support in the custom panel'
    end
    if spec and not matched then
        reasons[#reasons+1]='the saved order is not the one the virtual slots were recorded in (leave the loadout screen '
            ..'so the game saves it, or select the slot again)'
    end
    if#others>0 then
        reasons[#reasons+1]='another custom stratagem is in this loadout ('..table.concat(others,', ')..'): one custom '
            ..'stratagem per mission in this build (the second would be refused safely); remove it for this test'
    end
    if token_ok~=true or code_native(world,TOKEN_ID)~=true then
        reasons[#reasons+1]='the Orbital Precision Strike row is not native'
    end
    if carrier.name and not carrier_native(world)then
        reasons[#reasons+1]=carrier_presentation.applied()and'the carrier\'s mission presentation is still being '
            ..'restored'or('the carrier row is not native aboard the ship ('..look_now..'; '..code_now..')')
    end
    if carrier.code_refused then reasons[#reasons+1]='the Pelican CAS code was refused (see CODE CHECK)'end
    if#conflicts>0 then
        reasons[#reasons+1]='TEST REFUSED: the Pelican CAS code '..CODE_TEXT..' conflicts with your loadout: '
            ..table.concat(conflicts,'; ')
    end
    pre={ready=#reasons==0,carrier_saved=carrier_saved,slots=spec and spec.slots,look=look_now}
    mod:log(('PRE-MISSION CHECK: virtual Pelican CAS slots = %s; saved tokens = %s; carrier = %s (stable id %s, its own '
        ..'cooldown %s s, never written); carrier present in saved loadout = %s; saved order matches the virtual identity '
        ..'= %s%s; %s; the carrier row holds %s and %s (aboard the ship the carrier is native; its Pelican CAS look and code '
        ..'are applied at mission start); the Pelican CAS code against the saved loadout: %s; the Pelican: %s -> %s'):format(
        spec and(#spec.slots..' (loadout slot'..(#spec.slots==1 and' 'or's ')..list(spec.slots)..')')or'0',
        #parts>0 and table.concat(parts,'; ')or'none',tostring(carrier.name),tostring(carrier.id),n1(row_cd),
        tostring(carrier_saved),tostring(matched),found and(' (reconstructed: '..n..' slot'..(n==1 and''or's')..')')or'',
        others_now,look_now,code_now,#conflicts==0 and'no conflict'or table.concat(conflicts,'; '),
        tostring(capability.status),#reasons==0 and'READY: start a SOLO mission'or('NOT READY: '..table.concat(reasons,'; '))))
end

----------------------------------------------------------------------------------------------- the mission --
local M_={in_mission=false,clock=0}
local calls={}         -- by beacon entity: {n, created, landing, activation, pelican handle, samples}
local call_count=0
local function reset_mission()
    M_.clock,M_.populated,M_.probed,M_.op,M_.result,M_.hud,M_.seen,M_.conflicts=0,nil,false,'idle',nil,nil,{},{}
    M_.unconverting,M_.retry_return,M_.ready,M_.watch,M_.cooldown,M_.cool_carrier=nil,nil,false,nil,nil,nil
    calls,call_count={},0
end
reset_mission()
local function record_text(world)
    local view=slots.inspect(world,{token=TOKEN,carrier=carrier.name or TOKEN})
    if not view.entries then return tostring(view.record and view.record.reason)end
    local out={}
    for _,entry in ipairs(view.entries)do
        out[#out+1]=('%d:%s%s'):format(entry.index,label(world,entry.type),entry.granted==1 and'*'or'')
    end
    return table.concat(out,', ')..' (* granted)'
end
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
-------------------------------------------------------------------------------------- the carrier lifecycle --
-- As the live-proven Gas Barrage lifecycle: native aboard the ship; applied and verified at mission start before the
-- conversion; restored from the captured bytes once the mission HUD is torn down (at the latest RESTORE_DEADLINE s
-- after the mission end), and in the frame the loadout screen opens if still stale.
local life={opens=0,picks=0,busy=false,due=nil,retry_at=0,refused=nil}
local RESTORE_DEADLINE=5
local function presentation_restored(what)
    return function(handle)
        life.busy=false
        local world=world_module.open()
        if handle.status=='restored'then
            life.due,life.refused=nil,nil
            mod:log(('%s: carrier presentation RESTORED: %d writes; exact = %s (the name, cased name, description, icon and '
                ..'code back to the bytes captured at mission start); native = %s; %s'):format(what,handle.writes or 0,
                tostring(handle.verify.exact),tostring(handle.verify.native),world and carrier_text(world)or''))
        elseif handle.code=='UNAVAILABLE'or handle.code=='TARGET_UNAVAILABLE'then
            life.retry_at=clock+1
        else
            life.refused=handle.code
            mod:log(('%s: carrier presentation restore REFUSED (nothing overwritten; retried when the loadout screen '
                ..'opens): %s: %s'):format(what,tostring(handle.code),tostring(handle.reason)))
        end
    end
end
local function presentation_back(why)
    if not carrier_presentation.applied()or life.busy then return end
    life.busy=true
    carrier_presentation.restore(presentation_restored('PRESENTATION ('..why..')'))
end
local function lifecycle_step(world,mission)
    if mission or life.busy or life.refused or not carrier_presentation.applied()or clock<life.retry_at then return end
    life.due=life.due or clock+RESTORE_DEADLINE
    if stratagem_hud.populated(world)==true and clock<life.due then return end
    life.busy=true
    carrier_presentation.restore(presentation_restored('RETURN TO SHIP'))
end
selector.watch(function(event,view)
    if event~='opened'and event~='grid_opened'then return end
    local world=world_module.open()
    local state=hd2.game_state()
    if not world or not carrier.name or(state and state.mission)then return end
    local what
    if event=='opened'then
        life.opens=life.opens+1
        what=('LOADOUT OPEN #%d'):format(life.opens)
    else
        life.picks=life.picks+1
        what=('LOADOUT PICKER OPEN #%d (loadout slot %s)'):format(life.picks,tostring(view and view.editedSlot))
    end
    if carrier_presentation.applied()then
        local r,code,reason=carrier_presentation.restore_now()
        life.busy=false
        if r then
            life.due,life.refused=nil,nil
            mod:log(('%s: a STALE carrier presentation was found and RESTORED in this frame, before the native loadout UI '
                ..'uses the carrier: %d writes; exact = %s; native = %s; %s'):format(what,r.writes,tostring(r.verify.exact),
                tostring(r.verify.native),carrier_text(world)))
        else
            mod:log(('%s: a STALE carrier presentation could NOT be restored (nothing overwritten): %s: %s; %s'):format(
                what,tostring(code),tostring(reason),carrier_text(world)))
        end
    else
        mod:log(('%s: %s -> %s'):format(what,carrier_text(world),carrier_native(world)and'NATIVE: nothing to restore'
            or'NOT NATIVE (not this proof\'s presentation: nothing is written)'))
    end
end)

------------------------------------------------------------------------------------------- the Pelican --
-- One call: the beacon landed (its position recorded), activated, then one empty Pelican anchored at the landing
-- position. Its events, measured against the beacon (horizontal distance, height above it).
local function pelican_event(call)
    return function(e)
        local beacon=call.landing
        if e.kind=='spawned'then
            local r=e.result
            call.entity=r.entity
            mod:log(('PELICAN CAS SPAWNED (call %d): entity %d (network id %s): empty (no cargo, no cargo entity, no '
                ..'associated entity); created at %s, %s m from the beacon; its anchor %s read back, %s m from the beacon '
                ..'landing position %s'):format(call.n,r.entity,tostring(r.network),at(r.pelican and r.pelican.position
                or r.position),n1(flat(r.pelican and r.pelican.position or r.position,beacon)),at(r.anchor_read),
                n1(flat(r.anchor_read,beacon)),at(beacon)))
        elseif e.kind=='stage'then
            mod:log(('PELICAN CAS STAGE (call %d): entity %d: %s -> %s at %s s; flight target %s (%s m from the beacon '
                ..'horizontally); at %s (%s m from the beacon)'):format(call.n,e.entity,tostring(e.from),tostring(e.to),
                n1(e.seconds),at(e.target),n1(flat(e.target,beacon)),at(e.position),n1(flat(e.position,beacon))))
        elseif e.kind=='hovering'then
            call.hover_at=M_.clock
            local world=world_module.open()
            local m=world and pelicans.movers(world,e.entity)
            mod:log(('PELICAN CAS HOVERING (call %d): entity %d at %s s; hover point %s: %s m from the beacon '
                ..'horizontally, %s m above it -> %s'):format(call.n,e.entity,n1(e.seconds),at(e.target),
                n1(flat(e.target,beacon)),n1(e.target and beacon and e.target.z-beacon.z),
                (flat(e.target,beacon)or 1e9)<=AT_BEACON and'AT THE BEACON'or'NOT AT THE BEACON'))
            if m then
                mod:log(('PELICAN CAS MOVERS (INTERNAL, read-only; call %d): entity %d: the flight component %s (its target '
                    ..'%s, %s m from the beacon horizontally); the ground mover %s; the other mover %s -> %s'):format(call.n,
                    e.entity,m.flight and('holds it (record '..m.flight..')')or'does NOT hold it',at(m.flight_target),
                    n1(flat(m.flight_target,beacon)),m.ground and'HOLDS it'or'not',m.other and'HOLDS it'or'not',
                    (m.ground or m.other)and'a native mover holds it: a later hover point is not a data change'
                    or m.flight and'the flight component alone holds it: a later hover point is a data change (research)'
                    or'no movement component found for it'))
            end
        elseif e.kind=='released'then
            mod:log(('PELICAN CAS RELEASED (call %d): entity %d in stage %d at %s s (released nothing); at %s (%s m from '
                ..'the beacon)'):format(call.n,e.entity,e.stage,n1(e.seconds),at(e.position),n1(flat(e.position,beacon))))
        elseif e.kind=='held'then
            local r=e.result
            call.held=true
            mod:log(('PELICAN CAS HELD (call %d): entity %d: departs %s s after its release (native %s s); verified %s'):format(
                call.n,e.entity,n1(r.seconds),n1((r.native-r.release)/1e6),tostring(r.verified)))
        elseif e.kind=='departing'then
            call.departing=M_.clock
            mod:log(('PELICAN CAS DEPARTING (call %d): entity %d: stage %d, %s s after its release; at %s (%s m from the '
                ..'beacon)'):format(call.n,e.entity,e.stage,n1(e.after_release),at(e.position),n1(flat(e.position,beacon))))
        elseif e.kind=='gone'then
            local s=call.samples
            mod:log(('PELICAN CAS GONE (call %d): entity %d: %s s after it was spawned, %s s after its release, %s s after '
                ..'departing'):format(call.n,e.entity,n1(e.seconds),n1(e.after_release),n1(e.after_departing)))
            mod:log(('PELICAN CAS SUMMARY (call %d): entity %d: spawned empty at the beacon\'s activation; hovered %s s '
                ..'after its release (asked %d); while held, %d samples: %s..%s m from the beacon horizontally (you: up to %s '
                ..'m from it); left and was removed by the game %s s later -> %s'):format(call.n,e.entity,
                n1(e.after_release and e.after_departing and e.after_release-e.after_departing),HOVER,s.n,n1(s.min),
                n1(s.max),n1(s.player),n1(e.after_departing),call.held and s.n>0 and s.max<=AT_BEACON
                and'PASS: it held over the beacon, not over you'or'CHECK: see the lines above'))
        elseif e.kind=='refused'or e.kind=='unverified'or e.kind=='hold_refused'or e.kind=='cargo'then
            mod:log(('PELICAN CAS %s (call %d): %s: %s'):format(e.kind:upper(),call.n,tostring(e.code or(e.result and
                'SPAWN_UNVERIFIED')or e.spawned),tostring(e.reason or'')))
        end
    end
end
local function summon(call)
    if call.pelican then return end
    local where=call.landing or call.activation
    if not where then
        mod:log(('PELICAN CAS REFUSED (call %d): the beacon\'s position was never readable: no Pelican'):format(call.n))
        return
    end
    call.landing=where
    call.pelican=hd2.pelican.spawn({position=where,hover=HOVER,on_event=pelican_event(call)})
    local h=call.pelican
    mod:log(('PELICAN CAS REQUESTED (call %d): one empty Pelican anchored at the beacon landing position %s (hover %d s '
        ..'after its release; created %s m back along your heading and %s m up): status %s%s'):format(call.n,at(where),
        HOVER,n1(h.approach and h.approach.distance),n1(h.approach and h.approach.height),h.status,h.code and
        (' '..h.code..': '..tostring(h.reason))or''))
end
-- Every 0.1 s while a call is pending (INTERNAL, read-only): the beacon's landing (its countdown started) and its
-- position then; a beacon that moves afterwards is reported (the Pelican keeps the landing position).
local function landing_step()
    if next(calls)==nil then return end
    local world=world_module.open()
    local list=world and beacon_reader.beacons(world)
    if not list then return end
    for entity,call in pairs(calls)do
        local it=list[entity]
        if it and not call.landing and it.counting then
            call.landing=beacons.position(world,entity)
            if call.landing then
                mod:log(('BEACON LANDED (call %d): beacon %d at %s; its countdown started (%s s to its activation); the '
                    ..'Pelican will hover here'):format(call.n,entity,at(call.landing),n1(it.countdown and it.threshold
                    and it.countdown-it.threshold)))
            end
        elseif it and call.landing and not call.moved then
            local now=beacons.position(world,entity)
            if now and pelicans.distance(now,call.landing)>1 then
                call.moved=true
                mod:log(('BEACON MOVED (call %d): beacon %d now at %s, %s m from its landing position: the Pelican keeps '
                    ..'the landing position (no follow)'):format(call.n,entity,at(now),n1(pelicans.distance(now,call.landing))))
            end
        end
    end
end
-- Every 5 s while a Pelican of this proof is alive: where it is against the beacon, and where you are.
local function pelican_state_step()
    local me=hd2.local_player()
    local mine=me and me:position()
    for _,call in pairs(calls)do
        local h=call.pelican
        local s=h and h:alive()and h.entity and h:state()
        if s then
            local d,you=flat(s.position,call.landing),flat(mine,call.landing)
            if call.held and h.status=='held'then
                local m=call.samples
                m.n=m.n+1
                m.min=math.min(m.min or d or 1e9,d or 1e9)
                m.max=math.max(m.max or 0,d or 0)
                m.player=math.max(m.player or 0,you or 0)
            end
            mod:log(('PELICAN CAS STATE (call %d): entity %d stage %s released %s cargo %s at %s: %s m from the beacon '
                ..'horizontally, %s m above it; its anchor %s; you are %s m from the beacon; status %s'):format(call.n,
                s.entity,tostring(s.stage),tostring(s.released),tostring(s.cargo),at(s.position),n1(d),
                n1(s.position and call.landing and s.position.z-call.landing.z),at(s.anchor),n1(you),h.status))
        end
    end
end

---------------------------------------------------------------------------------------- the beacon watch --
-- Armed at mission start, before the conversion: every beacon of the carrier type is ours (the carrier is in no
-- loadout). In its FIRST update its delivery becomes 'none'; at its activation the Pelican is summoned.
local function beacon_event(e)
    if e.kind=='created'and not e.observed then
        call_count=call_count+1
        local b=e.beacon
        calls[b.entity]={n=call_count,created=M_.clock,samples={n=0}}
        mod:log(('BEACON CREATED (call %d): the carrier %s\'s beacon %d (type %d, frame %d): its own beam and call-in '
            ..'(%s s)'):format(call_count,tostring(b.carrier),b.entity,b.type,e.frame,
            n1(b.timing and b.timing.call_in_time)))
        -- A beacon exists once its ball has landed: its position now is the landing position.
        landing_step()
    elseif e.kind=='applied'then
        local call=calls[e.entity]
        local r=e.result
        if call then call.neutralized=true end
        mod:log(('BEACON NEUTRALIZED (call %s): beacon %d in its first update: delivery %s -> %s (%d write%s, verified %s): '
            ..'the carrier\'s own payload will not execute'):format(tostring(call and call.n),e.entity,
            tostring(r.delivery and r.delivery.from_name),tostring(r.delivery and r.delivery.to_name),r.writes or 0,
            (r.writes or 0)==1 and''or's',tostring(r.verified)))
    elseif e.kind=='refused'then
        local call=e.entity and calls[e.entity]
        if call then call.refused=true end
        mod:log(('BEACON NEUTRALIZE REFUSED (call %s): %s: %s; the carrier\'s own payload may execute; no Pelican is '
            ..'summoned for it'):format(tostring(call and call.n),tostring(e.code),tostring(e.reason)))
    elseif e.kind=='activated'and not e.observed then
        local call=calls[e.entity]
        if not call then return end
        local world=world_module.open()
        call.activation=world and beacons.position(world,e.entity)
        mod:log(('BEACON ACTIVATED (call %d): beacon %d %s s after it was first seen; the delivery the game had: %s (type '
            ..'%d); at %s, %s m from its landing position'):format(call.n,e.entity,n1(e.seconds),tostring(e.delivery),
            e.type,at(call.activation),n1(call.landing and call.activation and
            pelicans.distance(call.activation,call.landing))))
        if call.neutralized and e.type==0 then
            summon(call)
        else
            mod:log(('PELICAN CAS NOT SUMMONED (call %d): the beacon was not neutralized (its delivery type %d)'):format(
                call.n,e.type))
        end
    elseif e.kind=='gone'and not e.observed then
        local call=calls[e.entity]
        mod:log(('BEACON GONE (call %s): beacon %d, %s s after its activation'):format(tostring(call and call.n),e.entity,
            n1(e.after)))
    elseif e.kind=='ended'then
        mod:log('BEACON WATCH ENDED: '..tostring(e.reason))
    end
end
local function decide()return {delivery='none'}end

---------------------------------------------------------------------------------------- the cooldown --
local function cooldown_event(e)
    if e.kind=='armed'then
        mod:log(('COOLDOWN: armed for the Pelican CAS slot (carrier %s, its own row cooldown %s s, never written): each '
            ..'call\'s cooldown becomes %d s from the call-in\'s arrival'):format(tostring(e.carrier),n1(e.rowCooldown),
            COOLDOWN))
    elseif e.kind=='overridden'then
        mod:log(('COOLDOWN: Pelican CAS override = %s s from the arrival (record entry %d, loadout slot %s; the game\'s own '
            ..'end was %s s after the arrival); verified %s'):format(n1(COOLDOWN),e.index,tostring(e.slot),
            n1(e.gameEnd and e.arrival and(e.gameEnd-e.arrival)/1e6),tostring(e.verify and e.verify.finish and e.verify.others)))
    elseif e.kind=='refused'then
        mod:log(('COOLDOWN: REFUSED for this call (the carrier\'s own cooldown stays): %s: %s'):format(tostring(e.code),
            tostring(e.reason)))
    elseif e.kind=='hud'then
        mod:log(('COOLDOWN: HUD cooling bar total %s s (expected %s s left)'):format(n1(e.total),n1(e.expected)))
    elseif e.kind=='ready'then
        mod:log('COOLDOWN: READY AGAIN: the Pelican CAS slot can be called')
    elseif e.kind=='rewritten'or e.kind=='changed'then
        mod:log(('COOLDOWN: %s: entry %s: %s'):format(e.kind,tostring(e.index),tostring(e.reason or'')))
    elseif e.kind=='ended'then
        mod:log('COOLDOWN: ended')
    end
end

---------------------------------------------------------------------------------------- the conversion --
local function disarm()
    if M_.watch then M_.watch.cancel();M_.watch=nil end
    if cool.armed()then cool.disarm()end
end
local function conversion_report(handle)
    M_.result=handle
    local world=world_module.open()
    if handle.status=='converted'then
        M_.op='converted'
        M_.hud={since=M_.clock}
        local pairs_text={}
        for k,index in ipairs(handle.indices)do
            pairs_text[#pairs_text+1]=('loadout slot %d = record entry %d'):format(handle.slots[k],index)
        end
        mod:log(('MISSION START: conversion APPLIED: %s -> the carrier %s (type %d, stable id %d; its own type and stable '
            ..'id, unchanged); carrier package %s; %s; every other record entry and the count unchanged: %s; the record '
            ..'now: %s'):format(table.concat(pairs_text,', '),carrier.name,handle.carrier,handle.carrierId,
            tostring(handle.package),handle.report and(handle.report.writes..' writes')or'?',
            tostring(handle.verify and handle.verify.others),record_text(world)))
        M_.ready=true
        mod:log(('READY TO CALL: the virtual Pelican CAS slot is the carrier %s, presenting as Pelican Close Air Support '
            ..'with %s; its beacons are neutralized in their first update and the 60 s cooldown is armed: call it now with '
            ..'%s'):format(carrier.name,row_code_text(world),CODE_TEXT))
    else
        M_.op='refused'
        mod:log(('MISSION START: conversion REFUSED (nothing written; the mission goes on normally): %s: %s'):format(
            tostring(handle.code),tostring(handle.reason)))
        disarm()
        presentation_back('the conversion was refused')
    end
end
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
        local icon_text=icon==images.bytes(ICON)and'the Pelican CAS icon'or(values and icon==presentation.encode('icon',
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
            ..'; its text shows: '..shown(world)..'; '..others_text(world))
    elseif M_.clock>M_.hud.since+10 then
        M_.hud.done=true
        mod:log('HUD did NOT follow within 10 s: '..table.concat(parts,'; '))
    end
end
-- A record entry related to the code that appears after the conversion: the virtual slot returns to its token
-- through the conversion's own guarded restore (as the live-proven Gas Barrage proof).
local function unconverted(handle)
    M_.unconverting=handle.status=='pending'or nil
    if handle.status=='restored'then
        M_.op='returned'
        mod:log(('CODE CONFLICT: the virtual slot returned to its token %s (%d write%s, exact: %s): the related '
            ..'stratagem stays callable; the Pelican CAS is not available for the rest of this mission'):format(TOKEN,
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
-- Call-ins of the converted entries (read-only): a call-in in flight and its cooldown.
local function call_step(world)
    if M_.op~='converted'then return end
    local seen=slots.observe(world)
    for _,item in ipairs(seen or{})do
        local last=M_.seen[item.index]
        if last then
            local slot
            for k,index in ipairs(M_.result.indices)do if index==item.index then slot=M_.result.slots[k]end end
            if item.flying and not last.flying then
                mod:log(('CALL-IN: the virtual Pelican CAS slot (loadout slot %s, record entry %d) was called: a call-in of '
                    ..'%s is in flight (the carrier\'s own beacon, neutralized in its first update); the carrier row holds '
                    ..'%s'):format(tostring(slot),item.index,label(world,item.type),row_code_text(world)))
            end
        end
        M_.seen[item.index]=item
    end
end
local function refuse(text_)
    M_.op='test refused'
    mod:log('MISSION START: TEST REFUSED (nothing converted, nothing written): '..text_)
end
-- After the presentation: the beacon watch and the cooldown first (before any carrier beacon can exist), then the
-- conversion. A watch that cannot run refuses the test (the carrier's own payload would otherwise execute).
local function start_conversion()
    local watch,why=beacons.watch({carrier=carrier.name,label='Pelican CAS: neutralize '..carrier.name,decide=decide},
        beacon_event)
    if not watch then
        M_.op='test refused'
        mod:log('MISSION START: TEST REFUSED (nothing converted): the beacon watch cannot run: '..tostring(why))
        return presentation_back('the beacon watch could not run')
    end
    M_.watch=watch
    local armed,cwhy=cool.arm({definition=CAS.id,seconds=COOLDOWN,from='arrival',carrier=carrier.name},cooldown_event)
    if not armed then mod:log('COOLDOWN: not armed (the carrier\'s own cooldown applies): '..tostring(cwhy))end
    M_.op='converting'
    mod:log(('MISSION START: the beacon watch is armed (every beacon of %s neutralized in its first update) and the 60 s '
        ..'cooldown %s; converting the virtual slot'):format(carrier.name,armed and'armed'or'NOT armed'))
    selector.convert_virtual(CAS.id,conversion_report,carrier.name)
end
local function presentation_applied(handle)
    local world=world_module.open()
    if handle.status=='applied'then
        mod:log(('MISSION START: carrier presentation APPLIED (before the conversion; the carrier was native and its exact '
            ..'native values are kept for the restore): %d writes; %s'):format(handle.writes,world and carrier_text(world)
            or''))
        start_conversion()
    else
        M_.op='test refused'
        mod:log(('MISSION START: TEST REFUSED (nothing converted; the carrier keeps its own look and code): the carrier '
            ..'presentation was refused: %s: %s'):format(tostring(handle.code),tostring(handle.reason)))
    end
end
local function mission_step(world,state)
    M_.clock=M_.clock+0.5
    hud_step(world)
    call_step(world)
    conflict_step(world)
    if M_.clock%5==0 then pelican_state_step()end
    if not M_.populated then
        if stratagem_hud.populated(world)then M_.populated=M_.clock end
        return
    end
    if M_.clock<M_.populated+5 then return end
    if not M_.probed then
        M_.probed=true
        local spec,why=selector.conversion_spec(CAS.id,carrier.name)
        mod:log('MISSION START: the local mission record: '..record_text(world))
        mod:log(spec and('MISSION START: virtual slot%s discovered: loadout slot%s %s = %s (token %s); recorded loadout '
            ..'order: %s; carrier %s'):format(#spec.slots==1 and''or's',#spec.slots==1 and''or's',list(spec.slots),CAS.id,
            TOKEN,order_text(spec.order),tostring(carrier.name))or('MISSION START: no virtual slot: '..tostring(why)))
    end
    if M_.op~='idle'then return end
    if#slots_of(CAS.id)==0 then
        return refuse('no virtual Pelican CAS slot in this mission (select Pelican Close Air Support in the custom panel '
            ..'aboard the ship)')
    end
    local others=other_custom()
    if#others>0 then
        return refuse('another custom stratagem is in this loadout ('..table.concat(others,', ')..'): one custom '
            ..'stratagem per mission in this build')
    end
    local players=hd2.players()
    if#players~=1 then
        return refuse(('solo only (%d players): the beacon neutralization and the cooldown are solo-guarded, and the '
            ..'Pelican\'s multiplayer behaviour is not proven'):format(#players))
    end
    local capability=hd2.pelican.status()
    if capability.status~='available'then
        return refuse('the Pelican is unavailable: '..tostring(capability.status)..': '..tostring(capability.reason))
    end
    -- The final check: the whole allocation again against the CURRENT loadout (the saved loadout and this record).
    local ids,current=mission_present(world)
    local before=carrier.name
    local status,why=allocate(world,current,'at mission start against the saved loadout and this mission record')
    if status=='waiting'then return refuse('the carrier cannot be allocated now: '..tostring(why))end
    if not carrier.name then return refuse('no unused red-beacon (offensive) carrier for the current loadout')end
    if before and before~=carrier.name then
        mod:log(('CARRIER INVALIDATED: %s reason: reallocated at mission start (the allocation now gives %s)'):format(
            before,carrier.name))
    end
    if carrier.code_refused then return refuse('the Pelican CAS code was refused (see CODE CHECK)')end
    if not carrier_native(world)then
        return refuse(('the carrier %s is not native at mission start (%s and %s); its Pelican CAS look and code are '
            ..'applied only to a native carrier'):format(carrier.name,row_look(world),row_code_text(world)))
    end
    local view=slots.inspect(world,{token=TOKEN,carrier=carrier.name})
    if current[carrier.id]or view.carrierInRecord then
        return refuse(('the carrier %s is in the current loadout; it must not be selected'):format(carrier.name))
    end
    local conflicts=record_conflicts(world)
    if conflicts==nil then return refuse('the mission record is unreadable for the code check')end
    if#conflicts>0 then
        local out={}
        for _,c in ipairs(conflicts)do out[#out+1]=c.text;M_.conflicts[c.index..':'..c.type]=true end
        return refuse('the Pelican CAS code '..CODE_TEXT..' conflicts with this mission record: '..table.concat(out,'; '))
    end
    mod:log(('CODE CHECK: the Pelican CAS code %s against this mission record (%s): no entry has an equal code, a code '
        ..'that starts with it or a code that is its start'):format(CODE_TEXT,record_text(world)))
    M_.op='presenting'
    mod:log(('MISSION START: the carrier %s is native (%s and %s; its own cooldown %s s, never written); applying the '
        ..'Pelican CAS look and code before the conversion'):format(carrier.name,row_look(world),row_code_text(world),
        n1(cool.row_cooldown(world,carrier.kind))))
    carrier_presentation.apply({carrier=carrier.name,text=TEXTS,icon=ICON,code=CODE},presentation_applied)
end

----------------------------------------------------------------------------------------------- the loop --
hd2.every(0.5,function()
    clock=clock+0.5
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
        life.due,life.refused,life.retry_at=nil,nil,0
        disarm()
        local current=slots.state()
        mod:log(('MISSION END: state %s; calls %d; conversion %s; the carrier presentation %s; the carrier\'s own cooldown '
            ..'%s s (never written); %s'):format(tostring(state and state.name),call_count,current and current.converted
            and'still held (the game has not rebuilt the record yet)'or(M_.op=='converted'and'gone: the game rebuilt the '
            ..'record'or M_.op),carrier_presentation.applied()and'applied: restored aboard the ship once the mission HUD is '
            ..'torn down (at the latest when the loadout screen opens)'or'not applied',
            n1(carrier.kind and cool.row_cooldown(world,carrier.kind)),carrier_text(world)))
        saved_key=nil
    end
    if state then text_probe(world)end
    if state then lifecycle_step(world,mission)end
    if mission then mission_step(world,state)elseif state then ship_step(world)end
end,{id='pelican-cas-proof'})
hd2.every(0.1,landing_step,{id='pelican-cas-proof-landing'})

----------------------------------------------------------------------------------------------- the keys --
hd2.input.bind('pelican_cas_proof.focus',{key='F6',on_press=function()mod:log('F6: '..P.focus_next())end})
hd2.input.bind('pelican_cas_proof.unfocus',{key='Ctrl+F6',on_press=function()mod:log('Ctrl+F6: '..P.clear_focus())end})
hd2.input.bind('pelican_cas_proof.select',{key='F7',on_press=function()mod:log('F7: '..P.press())end})
hd2.input.bind('pelican_cas_proof.restore',{key='Ctrl+F7',on_press=function()mod:log('Ctrl+F7: '..P.cancel())end})
hd2.input.bind('pelican_cas_proof.status',{key='F9',on_press=function()
    local world=world_module.open()
    mod:log('F9 ['..BUILD..']: '..P.status()..'; virtual slots: '..selector.slots_text(selector.virtual_slots())
        ..'; '..tostring(allocation.line)..'; carrier '..tostring(carrier.name)..' (stable id '..tostring(carrier.id)
        ..'; its row holds '..(world and(row_look(world)..' and '..row_code_text(world))or'unreadable')..'); '
        ..(world and others_text(world)or'')..'; mission presentation '..(carrier_presentation.applied()and'APPLIED'
        or'not applied (the carrier native aboard the ship)')..'; loadout openings '..life.opens..', picker openings '
        ..life.picks..'; the Pelican '..tostring(hd2.pelican.status().status)..'; pre-mission check '
        ..(pre.ready and'READY'or'NOT READY'))
    saved_key=nil
end})
hd2.input.bind('pelican_cas_proof.mission',{key='F10',on_press=function()
    local world=world_module.open()
    local state=hd2.game_state()or{}
    local parts={}
    for _,call in pairs(calls)do
        local h=call.pelican
        parts[#parts+1]=('call %d: beacon landing %s, Pelican %s'):format(call.n,at(call.landing),h and(h.status..' '
            ..tostring(h.entity))or'none')
    end
    mod:log(('F10 [%s]: mission %s, host %s; carrier %s (its row holds %s); %s; conversion %s%s; beacon watch %s; '
        ..'cooldown armed %s; Runtime Pelicans alive %d; calls: %s; record: %s'):format(BUILD,tostring(state.mission==true),
        tostring(state.host),tostring(carrier.name),world and row_code_text(world)or'unreadable',M_.ready and
        'READY TO CALL'or'NOT READY',M_.op,M_.result and M_.result.code and(' ('..tostring(M_.result.code)..')')or'',
        M_.watch and M_.watch.status or'none',tostring(cool.armed()),#hd2.pelican.active(),#parts>0 and
        table.concat(parts,'; ')or'none',world and state.mission and record_text(world)or'-'))
end})
mod:log('loaded ('..BUILD..'): virtual stratagem '..CAS.id..' (token '..TOKEN..'; carrier: allocated from what you own, '
    ..'never shared with the Gas Barrage; native aboard the ship; in the mission: icon pelican_close_air_support, code '
    ..CODE_TEXT..', its beacon neutralized, an empty Pelican held 60 s over the beacon, a 60 s cooldown) and 5 visual '
    ..'placeholders. Ship: click or F7 selects; Ctrl+F7 undoes; F6 focus; F9 status. Mission: F10 status.')
