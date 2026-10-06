local hd2=require('mods/skyeshade/hd2runtime')
-- GasBarragePayloadProof 0.2.2: CARRIER REVALIDATION (docs/custom-stratagems.md, "Carrier revalidation"). Development
-- only; solo host; no multiplayer, no matchmaking.
-- 0.2.1 is live-proven and unchanged (the presentation lifecycle, the payload, the code, the virtual slots). Its second
-- mission in one session was refused: the carrier discovered once (the 380mm) had been put in the loadout, and the
-- proof kept it for the session. Now the discovered carrier is a CACHE that is REVALIDATED before every mission, with the
-- discovery's own guards against the CURRENT loadout (stratagem_selector.validate_carrier: in the loadout, not owned,
-- not selectable, disabled, limited uses, no call-in package, a special-case type, not payload-compatible, the donor):
--   * aboard the ship whenever the saved loadout changes and every 5 s; at mission start against the saved loadout
--     and the mission record (the final check);
--   * invalid: "CARRIER INVALIDATED: <carrier> reason: <codes>", the cache discarded, the discovery run again at once
--     ("CARRIER CANDIDATE" lines, "CARRIER: <next> SELECTED"); refused only when no carrier is eligible;
--   * never while the old carrier's mission presentation or payload is still applied: their restores come first.
-- The conversion's own record guard still refuses a carrier in the mission record, so no payload is ever written on a
-- carrier in the current loadout.
-- GasBarragePayloadProof 0.2.1: THE CARRIER LIFECYCLE (docs/custom-stratagems.md, "The carrier presentation
-- lifecycle").
-- 0.2.0 live-proved the Gas Barrage. It also showed a lifecycle bug: the carrier's Gas Barrage look and code were applied
-- aboard the ship, through public ensures that only their toggles restore, and stayed for the session. After a mission
-- the native loadout picker still showed the carrier's card as Orbital Gas Barrage. Now:
--   * SHIP: the carrier is NATIVE: its own name, cased name, description, icon and calldown code (its own card in the
--     picker). Selecting the custom Gas Barrage only records the virtual slot (the saved Precision Strike token).
--   * MISSION START: after every check, the carrier verified native, then its Gas Barrage text, icon and code applied
--     and verified (runtime/carrier_presentation.lua, which captures the exact native bytes first), then the packages,
--     the conversion and the payload in one tick (unchanged), READY TO CALL. Never callable without the look and code.
--   * MISSION: kept for the whole mission. MISSION END: the payload restored as before.
--   * RETURN TO SHIP: the look and code restored from the captured bytes as soon as the mission HUD is torn down (at
--     the latest 5 s after the mission end), verified native ("RETURN TO SHIP: carrier presentation RESTORED").
--   * THE LOADOUT SCREEN OPENING is the hard boundary (every frame watched): a stale look or code found then is
--     restored in that frame, before the native loadout UI uses the carrier; each opening reports the carrier native.
-- The restore writes only where the carrier row still holds what this proof wrote (another writer's bytes are refused,
-- never overwritten) and never the token or the donors. Discovery, the conversion and the payload are unchanged.
-- GasBarragePayloadProof 0.2.0: STAGE C, THE GAS STRIKE SHELL ON THE 120MM PATTERN (docs/custom-stratagems.md,
-- "Payload stage C").
-- Stage B (0.1.1) is live-proven and unchanged: the carrier's own record takes the 120mm's pattern, written in the tick
-- of the conversion, never callable without it, restored exactly at the mission end. Stage C changes ONLY the carrier's
-- own shell list: 194, 137, 137 -> 197, 197, 197, the Orbital Gas Strike's reviewed shell (payload.shells). The pattern
-- stays the 120mm's (5 salvos, 3 shells per salvo, 0.75 s between shells, 2 s between salvos, scatter 27). The shell
-- brings the Gas Strike's existing chain: explosion 82 -> damage 447 (gas and gas_confusion) and the volume template 16
-- (a 15 s, 15 m gas cloud applying gas and gas_confusion every tick). Nothing of that chain is written or copied: the
-- carrier only points at shell 197. In the conversion's tick: the conversion, the 120mm pattern (verified), then the
-- shell list on it (verified: packed, exactly 197, 197, 197); any failure rolls back and undoes the conversion. Extra
-- guards: the Gas Strike's package resident before anything is written, its record exactly vanilla, its shell row and
-- whole chain exactly as reviewed. The rest of this header is stage B's.
-- Everything GasBarrageMissionProof 0.5.0 live-proved is unchanged (identity, presentation, the Up Up Down Down code,
-- the mission conversion):
--   saved virtual Gas Barrage -> Orbital Precision Strike token -> a carrier DISCOVERED from what the account owns ->
--   ONLY the virtual slot becomes the carrier -> it presents as Orbital Gas Barrage and answers to UP UP DOWN DOWN.
-- New in this proof, stage B of the payload work: the carrier's OWN BombardmentComponentData takes the Orbital 120mm HE
-- Barrage's bombardment pattern WITH THE 120MM'S OWN SHELLS (194, 137, 137). Deliberately not gas yet.
--   * The carrier must be PAYLOAD-COMPATIBLE (stratagem_slot_conversion.discover_carriers with payload = {donor}):
--     a reviewed orbital BombardmentComponentData record, its row's delivery value equal to the 120mm's, nothing
--     outside the pattern words differing. Sentries, mines, backpacks, support weapons, strikes and other orbitals are
--     never carriers here. On this build that is the 380mm, the Napalm and the Walking Barrage.
--   * Aboard the ship, read-only: "PAYLOAD RECORD" reports the carrier's record (address, owner, size, the shell list
--     and count, salvos, delays, scatter, every word that differs from the 120mm's).
--   * In the mission the carrier is NEVER callable without its payload (stratagem_selector.convert_with_payload):
--     while the virtual slot is still its Precision Strike token, the carrier's and the 120mm's packages are loaded and
--     every payload guard is checked ("NOT READY: carrier payload is still being applied"); then, in ONE tick with no
--     yield, the conversion and the payload are written, and a refused payload undoes the conversion in that tick.
--     Only then "READY TO CALL". (0.1.0's first live run: the payload was refused, ALREADY_CALLED, because a fresh
--     entry's cooldown end is a shared non-zero time, not 0; the guard now compares it with the value the conversion
--     recorded, and checks the game clock.)
--   * The payload: ONE guarded transaction writes only the differing pattern words (for the 380mm: +0x08 1.5 -> 0.75, +0x1C 3 -> 2, +0x24 36 -> 27, the
--     shells 80/266/266 -> 194/137/137) with exact vanilla expectations (runtime/bombardment_payload.lua): solo, host,
--     the carrier the converted one and not yet called, its record owned by it alone and exactly vanilla, the 120mm's
--     record exactly vanilla, the 120mm shells reviewed rows, no barrage running, no active variant, the 120mm's
--     package resident. The 120mm, the Gas Strike, the Precision Strike, the StratagemInfo registry, the account
--     catalogue and the save are never written.
--   * At the mission end, aboard the ship, the record is restored exactly (only from the written bytes, no barrage of
--     the carrier running) and verified byte for byte against its vanilla bytes ("PAYLOAD: RESTORED ... exact").
-- No projectile, explosion, status, save-format, account, catalogue, inventory or StratagemInfo-registry write; no
-- native call, FFI, hook or OS input.
local mod=hd2.mod()
local BUILD='0.2.2 CARRIER REVALIDATION'
mod:log('GasBarragePayloadProof '..BUILD..' BUILD: ship: Orbital Gas Barrage from the custom panel (the Precision Strike '
    ..'token is saved), the rest of the loadout picked natively; leave the loadout screen: the carrier is then discovered '
    ..'from what you own ("CARRIER CANDIDATE" lines, then "CARRIER: ... SELECTED"), REVALIDATED before every mission '
    ..'against the current loadout (a carrier you put in your loadout: "CARRIER INVALIDATED: ... reason: in_loadout", '
    ..'then the next eligible carrier "CARRIER: ... SELECTED") and STAYS NATIVE aboard the ship (its '
    ..'own card in the picker; "LOADOUT OPEN ... NATIVE" each time the loadout screen opens); do NOT select the carrier '
    ..'natively; wait for "PRE-MISSION CHECK ... READY", then a SOLO mission: the carrier takes the Gas Barrage look and '
    ..'code UP UP DOWN DOWN ("MISSION START: carrier presentation APPLIED"), then wait for "READY TO CALL" (before it: '
    ..'"NOT READY: carrier payload is still being applied"; do not call); call it with UP UP DOWN DOWN: expect a GAS '
    ..'BARRAGE (5 salvos of 3 gas shells, the gas clouds). Mission end: "PAYLOAD: RESTORED ... exact", then "RETURN TO '
    ..'SHIP: carrier presentation RESTORED"; open the loadout screen: "LOADOUT OPEN ... NATIVE". F9 ship status; F10 '
    ..'mission status.')

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
local catalog=require('hd2runtime/domains/stratagem_authoring')
local domain=require('hd2runtime/domains/stratagem_calldown')
local SEL=require('hd2runtime/domains/stratagem_selector')
local TABLE=require('hd2runtime/schemas/current').stratagem.table_rva
local RESOURCE='mods/skyeshade/hd2runtime_gas_barrage_payload_proof'
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
    selection={token=TOKEN},mission={discover=true,exclude={DONOR}},payload={donor=DONOR,shells='Orbital Gas Strike'}},RESOURCE)
local GAS_STRIKE='Orbital Gas Strike'
local function f(n)return(('%.2f'):format(n):gsub('0+$',''):gsub('%.$',''))end

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
local options=hd2.options({id='gas_barrage_payload_proof',title='Gas Barrage Payload Proof',fallback='default'})
local present=options:toggle({id='presentation',label='Gas Barrage look on the carrier',default=true,
    description='In a solo mission, from its start, the carrier (a vanilla orbital not in your loadout) presents as '
        ..'Orbital Gas Barrage (Runtime text and the masked icon). Aboard the ship it is always native. Read at mission '
        ..'start.'})
local code_on=options:toggle({id='code',label='Gas Barrage code on the carrier',default=true,
    description='In a solo mission, from its start, the carrier answers to UP UP DOWN DOWN (the carrier only). Aboard '
        ..'the ship it keeps its own code. Read at mission start.'})
local pattern_on=options:toggle({id='pattern',label='Gas Barrage payload on the carrier',default=true,
    description='In a solo mission, in the tick of the conversion, the carrier\'s own bombardment record takes the '
        ..'120mm\'s pattern and the Orbital Gas Strike\'s shell; restored at the mission end. Off: the carrier keeps its '
        ..'own payload.'})
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
-- Barrage slot exists and the saved loadout is the one it was recorded in; then fixed for the session. Aboard the ship
-- it stays native; its look and code are applied to it alone at mission start. Its stable id is kept (a future
-- multiplayer policy avoids carriers in peers' loadouts).
local carrier={name=nil,id=nil,kind=nil,native_code=nil,code_refused=nil}
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
        ..'in_loadout=%s special_case=%s package_available=%s presentation=%s code=%s payload_compatible=%s -> %s'):format(
        c.name,c.type,c.id,tostring(c.family),tostring(c.component or'-'),own_text,yes(c.selectable),yes(c.enabled),
        yes(c.unlimited),yes(c.inLoadout),c.special and('true ('..c.special..')')or'false',yes(c.package),
        yes(c.presentation),yes(c.code),c.payloadCompatible and('true ('..tostring(c.payloadWords)..' words)')or'false',
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
-- Read-only: the carrier's bombardment record (stage A at run time): where it is, who owns it, and every word that
-- differs from the 120mm's.
local function payload_line(world,name,label)
    local r,code,why=selector.inspect_payload(GAS.id,name)
    if not r then return label..': '..name..' record unreadable: '..tostring(code)..': '..tostring(why)end
    local diffs={}
    for _,d in ipairs(r.differences)do
        diffs[#diffs+1]=('+0x%02X %s %s -> %s'):format(d.offset,d.role,f(d.value),f(d.donor))
    end
    return ('%s: %s BombardmentComponentData at 0x%X (record %d of index slot %d, reviewed %d/%d; owners %d; %d bytes; '
        ..'rows listing its payload: %d, its own %s; own row\'s payloads catalogued %s): shell list at +0x40 = %s (count %s), '
        ..'%d shells per salvo, %d salvos, delay between shells %s (+%s random), between salvos %s (+%s random), scatter '
        ..'%s, aim walk %s..%s, salvo-centre scatter %s, drift %s; exactly vanilla %s; holds the Gas Barrage payload %s; '
        ..'payload-compatible %s%s; differs from the 120mm at: %s; instances of it %s; active variant naming it %s'):format(
        label,name,r.address,r.record,r.indexRow,r.reviewedRecord,r.reviewedRow,r.owners,r.size,#r.rowsListing,
        tostring(r.rowsListing[1]==r.type),tostring(r.ownRow),list(r.shells),tostring(r.shellCount),r.perSalvo,r.salvos,
        f(r.shellDelay[1]),f(r.shellDelay[2]),f(r.salvoDelay[1]),f(r.salvoDelay[2]),f(r.scatter),f(r.walk[1]),f(r.walk[2]),
        f(r.centreScatter),f(r.drift),tostring(r.vanilla),tostring(r.desired),tostring(r.compatible),
        r.compatible and''or(' ('..table.concat(r.reasons,'; ')..')'),#diffs==0 and'nothing'or table.concat(diffs,'; '),
        r.instances and tostring(r.instances.of)or'unreadable',tostring(r.variant))
end
local function donors_vanilla(world)
    local d1=selector.inspect_payload(GAS.id,DONOR)
    local d2=selector.inspect_payload(GAS.id,GAS_STRIKE)
    local d=selector.payload_donors(GAS.id)or{}
    return ('the 120mm record vanilla = %s; the Gas Strike record vanilla = %s; 120mm donor unchanged = %s; Gas Strike '
        ..'donor unchanged = %s (its record, and its shell 197, explosion 82, damage 447, gas volume template 16 and '
        ..'statuses 42/44 as reviewed: %s)'):format(tostring(d1 and d1.vanilla),tostring(d2 and d2.vanilla),
        tostring(d.pattern==true),tostring(d.shells==true and d.chain==true),tostring(d.chain==true))
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
        ok and'SAFE: applied at mission start (aboard the ship the carrier keeps its own code)'
        or'REFUSED: the code is not applied'))
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
            ..'loadout changes)'):format(#found.candidates))
        return
    end
    local c=found.chosen
    carrier.name,carrier.id,carrier.kind=c.name,c.id,c.type
    mod:log(('CARRIER: %s SELECTED (type %d, stable id %d, %s/%s): the first of %d eligible carriers (orbital '
        ..'bombardments first); owned, not in the current loadout, not the donor; its native code: %s; the donor %s '
        ..'is not written. Do NOT select %s natively. Aboard the ship it stays native (its own card in the loadout '
        ..'picker); in the mission it presents as Orbital Gas Barrage and answers to %s; restored on the return to the '
        ..'ship'):format(c.name,c.type,c.id,tostring(c.family),tostring(c.component or'-'),eligible,
        code_of(world,c.id),DONOR,c.name,CODE_TEXT))
    mod:log(payload_line(world,c.name,'PAYLOAD RECORD'))
    mod:log('PAYLOAD RECORD: donor: '..payload_line(world,DONOR,'the 120mm')..'; '..donors_vanilla(world))
    -- The Gas Barrage code against every native code, from the carrier's native code read first (read-only: the code
    -- is written at mission start, with the look).
    local native_now=code_check(world,c)
    if native_now then carrier.native_code=native_now else carrier.code_refused=true end
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
local function code_wanted()return carrier.native_code~=nil and not carrier.code_refused and wanted(code_on)end
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
local text={probed=false}
local clock=0
-- The game's text registry, read once (the custom text is registered at mission start).
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
-- The discovered carrier is a CACHE, never trusted: it is validated with the discovery's own guards against the CURRENT
-- loadout (stratagem_selector.validate_carrier) aboard the ship whenever the saved loadout changes and every
-- REVALIDATE_EVERY s, and at mission start against the saved loadout and the mission record. Invalid: logged, discarded,
-- and the discovery runs again at once. Never while the carrier's mission presentation or payload is still applied.
local validation={key=nil,at=-1}
local REVALIDATE_EVERY=5
-- 'valid', 'invalidated' (logged and discarded) or 'waiting' and why (nothing can be trusted yet).
local function check_carrier(present_set,where)
    local v=selector.validate_carrier(GAS.id,carrier.name,present_set)
    if not v.ready then return'waiting',v.reason end
    if v.valid then return'valid'end
    mod:log(('CARRIER INVALIDATED: %s reason: %s (%s; checked %s): the cached carrier is discarded and the carrier '
        ..'discovery runs again now'):format(carrier.name,table.concat(v.codes,', '),table.concat(v.reasons,'; '),where))
    carrier.name,carrier.id,carrier.kind,carrier.native_code,carrier.code_refused=nil,nil,nil,nil,nil
    discovery.key,discovery.waiting,discovery.retry=nil,nil,0
    return'invalidated'
end
local function carrier_busy()
    local state=selector.payload_state()
    return carrier_presentation.applied()or(state~=nil and state.applied==true)
end
local function revalidation_step(world)
    if not carrier.name or carrier_busy()then return end
    local ids,present_set=saved_ids(world)
    if not ids then return end
    local key=table.concat(ids,',')
    if key==validation.key and clock<validation.at+REVALIDATE_EVERY then return end
    validation.key,validation.at=key,clock
    if check_carrier(present_set,'aboard the ship against the saved loadout: '..order_text(ids))=='invalidated'then
        discovery_step(world)
    end
end
-- The loadout slots the Runtime records as virtual Gas Barrage slots (no carrier needed).
local function gas_slots()
    local set=selector.virtual_slots()
    local out={}
    for slot=0,3 do
        local e=set and set.slots[slot]
        if e and e.definition==GAS.id then out[#out+1]=slot end
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

-- Whether the carrier row holds exactly its own text, icon and code (read-only).
local NATIVE_LOOK='its native text and its native icon'
local function carrier_native(world)
    return carrier.id~=nil and row_look(world)==NATIVE_LOOK and code_native(world,carrier.id)==true
end
local function carrier_text(world)
    return ('the carrier %s row holds %s and %s; %s'):format(tostring(carrier.name),row_look(world),row_code_text(world),
        others_text(world))
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
    revalidation_step(world)
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
    local record=carrier.name and selector.inspect_payload(GAS.id,carrier.name)
    local donors=donors_vanilla(world)
    local payload_text=carrier.name and(record and('payload-compatible %s (%d pattern words differ from the 120mm); its '
        ..'record exactly vanilla %s; %s; the 120mm pattern and the Gas Strike shell %s'):format(
        tostring(record.compatible),#record.differences,tostring(record.vanilla),donors,
        wanted(pattern_on)and'ON (written in the mission)'or'off')or'unreadable')
        or'no carrier'
    local key=table.concat(parts,'; ')..' | '..selector.slots_text(selector.virtual_slots())..' | '..look_now..' | '
        ..code_now..' | '..others..' | '..tostring(carrier.name)..' | '..tostring(code_wanted())..' | '..payload_text
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
        reasons[#reasons+1]=('the carrier %s is in the saved loadout: it is replaced as soon as it can be revalidated')
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
    if carrier.name and not carrier_native(world)then
        reasons[#reasons+1]=carrier_presentation.applied()and'the carrier\'s mission presentation is still being '
            ..'restored'or('the carrier row is not native aboard the ship ('..look_now..'; '..code_now..')')
    end
    if carrier.code_refused then
        reasons[#reasons+1]='the Gas Barrage code was refused (see CODE CHECK)'
    end
    if#conflicts>0 then
        reasons[#reasons+1]='TEST REFUSED: the Gas Barrage code '..CODE_TEXT..' conflicts with your loadout: '
            ..table.concat(conflicts,'; ')
    end
    if carrier.name and not(record and record.compatible and record.vanilla)then
        reasons[#reasons+1]='the carrier\'s bombardment record is not payload-compatible and exactly vanilla'
    end
    if carrier.name and not(donors:find('120mm donor unchanged = true',1,true)
            and donors:find('Gas Strike donor unchanged = true',1,true))then
        reasons[#reasons+1]='a donor record is not vanilla'
    end
    pre={ready=#reasons==0,carrier_saved=carrier_saved,slots=spec and spec.slots,look=look_now}
    mod:log(('PRE-MISSION CHECK: virtual Gas Barrage slots = %s; saved tokens = %s; carrier = %s (stable id %s); carrier '
        ..'present in saved loadout = %s; 120mm present in saved loadout = %s; saved order matches the virtual identity = '
        ..'%s%s; %s; the carrier row holds %s and %s (aboard the ship the carrier is native; its Gas Barrage look and '
        ..'code are applied at mission start); the Gas Barrage code against the saved loadout: %s; payload: %s -> %s'):format(
        spec and(#spec.slots..' (loadout slot'..(#spec.slots==1 and' 'or's ')..list(spec.slots)..')')or'0',
        #parts>0 and table.concat(parts,'; ')or'none',tostring(carrier.name),tostring(carrier.id),tostring(carrier_saved),
        tostring(donor_saved),tostring(matched),found and(' (reconstructed: '..n..' slot'..(n==1 and''or's')..')')or'',
        others,look_now,code_now,#conflicts==0 and'no conflict'or table.concat(conflicts,'; '),payload_text,
        #reasons==0 and'READY: start a solo mission'or('NOT READY: '..table.concat(reasons,'; '))))
end

----------------------------------------------------------------------------------------------- the mission --
local M_={in_mission=false,clock=0}
local function reset_mission()
    M_.clock,M_.populated,M_.probed,M_.op,M_.result,M_.hud,M_.calls,M_.conflicts=0,nil,false,'idle',nil,nil,{},{}
    M_.unconverting,M_.retry_return=nil,nil
    M_.payload,M_.payload_result,M_.atomic,M_.phase,M_.ready=nil,nil,nil,nil,false
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
-------------------------------------------------------------------------------------- the carrier lifecycle --
-- Aboard the ship the carrier is NATIVE (its own card in the loadout picker). At mission start, after every check and
-- before the conversion, its Gas Barrage text, icon and code are applied and verified (runtime/carrier_presentation.lua
-- captures the exact native bytes first); the mission keeps them. On the return to the ship they are restored from those
-- bytes as soon as the mission HUD is torn down (stratagem_hud.populated no longer true; at the latest RESTORE_DEADLINE s
-- after the mission end, whether or not the loadout screen is ever opened), and the loadout screen opening is the hard
-- boundary: a stale look or code found then is restored in that frame, before the native loadout UI uses the carrier.
-- Only the carrier row is written; the token and the donors never.
local life={opens=0,picks=0,busy=false,due=nil,retry_at=0,refused=nil}
local RESTORE_DEADLINE=5
local function presentation_restored(label)
    return function(handle)
        life.busy=false
        local world=world_module.open()
        if handle.status=='restored'then
            life.due,life.refused=nil,nil
            mod:log(('%s: carrier presentation RESTORED: %d writes; exact = %s (the name, cased name, description, icon and '
                ..'code back to the bytes captured at mission start); native = %s; %s'):format(label,handle.writes or 0,
                tostring(handle.verify.exact),tostring(handle.verify.native),world and carrier_text(world)or''))
        elseif handle.code=='UNAVAILABLE'or handle.code=='TARGET_UNAVAILABLE'then
            life.retry_at=clock+1
        else
            life.refused=handle.code
            mod:log(('%s: carrier presentation restore REFUSED (nothing overwritten; retried when the loadout screen '
                ..'opens): %s: %s'):format(label,tostring(handle.code),tostring(handle.reason)))
        end
    end
end
-- When the conversion did not happen, the carrier is not in the mission record: restored at once.
local function presentation_back(why)
    if not carrier_presentation.applied()or life.busy then return end
    life.busy=true
    carrier_presentation.restore(presentation_restored('PRESENTATION ('..why..')'))
end
-- Aboard the ship, every half second: restore once the mission HUD is torn down (or the deadline passed).
local function lifecycle_step(world,mission)
    if mission or life.busy or life.refused or not carrier_presentation.applied()or clock<life.retry_at then return end
    life.due=life.due or clock+RESTORE_DEADLINE
    if stratagem_hud.populated(world)==true and clock<life.due then return end
    life.busy=true
    carrier_presentation.restore(presentation_restored('RETURN TO SHIP'))
end
-- The loadout screen opening (and the native picker opening on a slot), seen the frame it happens.
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
local payload_report   -- the payload callback (defined below, after the HUD and restore helpers it shares)
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
        -- With the 120mm pattern on, the payload was written in this same tick (convert_with_payload).
        if M_.payload~='applied'then
            M_.payload='off'
            M_.ready=true
            mod:log('PAYLOAD: the Gas Barrage payload is switched off (Gas Barrage Payload Proof > Gas Barrage payload on the carrier): nothing written; '
                ..'READY TO CALL: the carrier with its own payload')
        end
    else
        M_.op='refused'
        mod:log(('MISSION START: conversion REFUSED (nothing written; the mission goes on normally): %s: %s'):format(
            tostring(handle.code),tostring(handle.reason)))
        presentation_back('the conversion was refused')
    end
end
-- The 120mm pattern on the carrier's own record, right after the conversion and before its first call-in.
function payload_report(handle)
    M_.payload_result=handle
    local world=world_module.open()
    if handle.status=='applied'then
        M_.payload='applied'
        local list={}
        for k,shell in ipairs(handle.shells or{})do list[k]=tostring(shell)end
        mod:log(('PAYLOAD: APPLIED: the carrier %s\'s own BombardmentComponentData: the 120mm pattern (%s writes), then '
            ..'the Gas Strike shell (%s writes), %d writes in all; shell list = %s; shell donor = %s; the record verified '
            ..'%s; packed with %s shells; Gas Strike donor unchanged = %s; 120mm donor unchanged = %s; non-target bytes '
            ..'unchanged %s; the packages %s'):format(handle.carrier,tostring(handle.patternWrites),
            tostring(handle.shellWrites),handle.writes,table.concat(list,', '),tostring(handle.shellDonor),
            tostring(handle.verify.record),tostring(handle.verify.shellCount),tostring(handle.verify.shellDonor==true
            and handle.verify.chain==true),tostring(handle.verify.donor),tostring(handle.verify.nonTarget),
            tostring(handle.package)))
        mod:log(payload_line(world,handle.carrier,'PAYLOAD RECORD')..'; '..donors_vanilla(world))
    else
        M_.payload='refused'
        mod:log(('PAYLOAD: REFUSED (nothing written; the carrier keeps its own payload): %s: %s'):format(
            tostring(handle.code),tostring(handle.reason)))
    end
end
-- The combined step (stratagem_selector.convert_with_payload): the conversion and the payload in one tick, or neither.
local PHASES={packages='the carrier\'s, the 120mm\'s and the Gas Strike\'s call-in packages are loading',
    barrage='waiting for running barrages to end before the write',converting='converting and writing'}
local function atomic_report(handle)
    if handle.status=='applied'then
        M_.payload='applied'
        conversion_report(handle.conversion)
        payload_report(handle.payload)
        M_.ready=true
        mod:log(('READY TO CALL: the virtual Gas Barrage slot is the carrier %s, and its own bombardment record holds the '
            ..'120mm pattern with the Gas Strike shell 197 (the conversion, the 120mm pattern, the Gas Strike shell and '
            ..'PAYLOAD: APPLIED in the same tick, after %.1f s of preparation: it was never callable without them): call it '
            ..'now with %s'):format(carrier.name,handle.waited or 0,CODE_TEXT))
    else
        M_.op,M_.payload='refused','refused'
        mod:log(('NOT READY: the carrier payload was REFUSED (%s: %s); %s; the virtual slot stays an Orbital Precision '
            ..'Strike: do NOT call it for this test, send this line'):format(tostring(handle.code),tostring(handle.reason),
            handle.conversion and('the conversion was undone in the same tick: '..tostring(handle.undone))
            or'nothing was converted or written'))
        presentation_back('the payload was refused')
    end
end
local function readiness_step()
    local h=M_.atomic
    if not(h and h.status=='pending')or h.phase==M_.phase then return end
    M_.phase=h.phase
    mod:log(('NOT READY: carrier payload is still being applied (%s); the virtual slot is still an Orbital Precision '
        ..'Strike, the carrier is not callable yet: do NOT call it'):format(PHASES[h.phase]or tostring(h.phase)))
end
local restore={pending=false,retry_at=0,busy=false}
local function payload_restored(handle)
    restore.busy=false
    local world=world_module.open()
    if handle.status=='restored'then
        restore.pending=false
        mod:log(('PAYLOAD: RESTORED: the carrier %s\'s BombardmentComponentData: %d writes; exact vanilla carrier record '
            ..'= %s (after restoration the whole record equals the exact vanilla record before modification); %s'):format(
            tostring(handle.carrier),handle.writes,tostring(handle.exact),world and donors_vanilla(world)or''))
        if world and carrier.name then mod:log(payload_line(world,carrier.name,'PAYLOAD RECORD'))end
    elseif handle.code=='IN_USE'or handle.code=='UNAVAILABLE'then
        restore.retry_at=clock+1
        if not restore.said then
            restore.said=true
            mod:log('PAYLOAD: restore waiting: '..tostring(handle.code)..': '..tostring(handle.reason))
        end
    else
        restore.pending=false
        mod:log(('PAYLOAD: restore REFUSED: %s: %s'):format(tostring(handle.code),tostring(handle.reason)))
    end
end
local function restore_step()
    if not restore.pending or restore.busy or clock<restore.retry_at then return end
    if not(selector.payload_state()and selector.payload_state().applied)then restore.pending=false;return end
    restore.busy=true
    selector.restore_payload(payload_restored)
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
        restore.pending,restore.said=true,nil
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
                    ..'%s'):format(slot,item.index,label(world,item.type),row_code_text(world),M_.payload=='applied'
                    and'expect a GAS BARRAGE: 5 salvos of 3 Orbital Gas Strike shells (197), 0.75 s between shells, 2 s '
                    ..'between salvos, scatter 27; each shell\'s gas cloud (15 s, 15 m) with gas and confusion'or'the Gas '
                    ..'Barrage payload is NOT applied ('..tostring(M_.payload)..'): expect the carrier\'s own normal attack'))
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
-- The conversion and the payload (unchanged): the carrier is never callable without its payload: prepared while the
-- slot is still the token, then the conversion and the payload in one tick (or neither).
local function start_conversion()
    M_.op='converting'
    if wanted(pattern_on)then
        M_.atomic=selector.convert_with_payload(GAS.id,atomic_report,carrier.name)
        readiness_step()
    else
        selector.convert_virtual(GAS.id,conversion_report,carrier.name)
    end
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
    readiness_step()
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
        -- Nothing to convert: no carrier is checked, discovered or written.
        if#gas_slots()==0 then
            return refuse('no virtual Gas Barrage slot in this mission (select Orbital Gas Barrage in the custom panel '
                ..'aboard the ship)')
        end
        -- The final check: the cached carrier against the CURRENT loadout (the saved loadout and this mission record);
        -- invalid: discarded and discovered again now, with the same present set.
        local ids,current=mission_present(world)
        if carrier.name then
            local status,why=check_carrier(current,'at mission start against the saved loadout and this mission record')
            if status=='waiting'then
                return refuse('the carrier '..carrier.name..' cannot be validated now: '..tostring(why))
            end
        end
        if not carrier.name then
            discovery.key=nil
            choose(world,ids,current)
            if not carrier.name then return refuse('no carrier is eligible for the current loadout (see the CARRIER lines)')end
        end
        -- Aboard the ship the carrier stayed native; it must still be, exactly, before its look and code are applied.
        if not carrier_native(world)then
            return refuse(('the carrier %s is not native at mission start (%s and %s); its Gas Barrage look and code are '
                ..'applied only to a native carrier'):format(carrier.name,row_look(world),row_code_text(world)))
        end
        if not(settled(code_on)and settled(present))then return end
        -- A backstop (the validation above already excludes it): never a carrier in the current loadout.
        local view=slots.inspect(world,{token=TOKEN,carrier=carrier.name})
        if current[carrier.id]or view.carrierInRecord then
            return refuse(('the carrier %s is in the current loadout; it must not be selected'):format(carrier.name))
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
        if not settled(pattern_on)then return end
        -- The Gas Barrage look and code on the native carrier, verified, before the conversion: never callable without.
        local spec={carrier=carrier.name}
        if wanted(present)then spec.text,spec.icon=TEXTS,ICON end
        if code_wanted()then spec.code=CODE end
        if not(spec.text or spec.code)then
            mod:log('MISSION START: the Gas Barrage look and code are switched off: the carrier keeps its own')
            return start_conversion()
        end
        M_.op='presenting'
        mod:log(('MISSION START: the carrier %s is native (%s and %s); applying the Gas Barrage %s before the conversion')
            :format(carrier.name,row_look(world),row_code_text(world),spec.text and spec.code and'look and code'
            or spec.text and'look'or'code'))
        carrier_presentation.apply(spec,presentation_applied)
    end
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
        local current=slots.state()
        restore.pending,restore.said=selector.payload_state()~=nil and selector.payload_state().applied,nil
        life.due,life.refused,life.retry_at=nil,nil,0
        mod:log(('MISSION END: state %s; payload %s; conversion %s; the carrier presentation %s; %s'):format(
            tostring(state and state.name),restore.pending and'applied: restoring aboard the ship'or tostring(M_.payload),
            current and current.converted and'still held (the game has not rebuilt the record yet)'or(M_.op=='converted'
            and'gone: the game rebuilt the record (see "no longer hold")'or M_.op),carrier_presentation.applied()
            and'applied: restored aboard the ship once the mission HUD is torn down (at the latest when the loadout '
            ..'screen opens)'or'not applied',carrier_text(world)))
        saved_key=nil
    end
    if state then text_probe(world)end
    restore_step()
    if state then lifecycle_step(world,mission)end
    if mission then mission_step(world,state)elseif state then ship_step(world)end
end,{id='gas-barrage-payload-proof'})

----------------------------------------------------------------------------------------------- the keys --
hd2.input.bind('gas_barrage_payload_proof.focus',{key='F6',on_press=function()mod:log('F6: '..P.focus_next())end})
hd2.input.bind('gas_barrage_payload_proof.unfocus',{key='Ctrl+F6',on_press=function()mod:log('Ctrl+F6: '..P.clear_focus())end})
hd2.input.bind('gas_barrage_payload_proof.select',{key='F7',on_press=function()mod:log('F7: '..P.press())end})
hd2.input.bind('gas_barrage_payload_proof.restore',{key='Ctrl+F7',on_press=function()mod:log('Ctrl+F7: '..P.cancel())end})
hd2.input.bind('gas_barrage_payload_proof.slot_overlays',{key='Ctrl+F9',on_press=function()
    mod:log('Ctrl+F9: slot overlays '..(P.set_slot_overlays(not P.overlays)and'on'or'off (the native icons underneath)'))
end})
hd2.input.bind('gas_barrage_payload_proof.status',{key='F9',on_press=function()
    local world=world_module.open()
    mod:log('F9 ['..BUILD..']: '..P.status()..'; virtual slots: '..selector.slots_text(selector.virtual_slots())
        ..'; carrier '..tostring(carrier.name)..' (stable id '..tostring(carrier.id)..'; its row holds '
        ..(world and(row_look(world)..' and '..row_code_text(world))or'unreadable')..'); '
        ..(world and others_text(world)or'')..'; mission presentation '..(carrier_presentation.applied()and'APPLIED'
        or'not applied (the carrier native aboard the ship)')..'; loadout openings '..life.opens..', picker openings '
        ..life.picks..'; payload '..tostring(selector.payload_state()and
        selector.payload_state().applied)..'; pre-mission check '..(pre.ready and'READY'or'NOT READY'))
    if world and carrier.name then mod:log('F9 '..payload_line(world,carrier.name,'PAYLOAD RECORD'))end
    saved_key=nil
end})
hd2.input.bind('gas_barrage_payload_proof.mission',{key='F10',on_press=function()
    local world=world_module.open()
    local state=hd2.game_state()or{}
    local current=slots.state()
    local seen=world and slots.observe(world)
    local parts={}
    for _,item in ipairs(seen or{})do
        parts[#parts+1]=('entry %d %s in flight %s'):format(item.index,label(world,item.type),tostring(item.flying))
    end
    mod:log(('F10 [%s]: mission %s, host %s; carrier %s (its row holds %s); payload %s; %s; conversion %s%s; converted '
        ..'entries: %s; record: %s'):format(BUILD,tostring(state.mission==true),tostring(state.host),tostring(carrier.name),
        world and row_code_text(world)or'unreadable',tostring(M_.payload),M_.ready and'READY TO CALL'or
        ('NOT READY'..(M_.atomic and M_.atomic.status=='pending'and(': '..(PHASES[M_.atomic.phase]or'pending'))or'')),M_.op,M_.result and M_.result.code and(' ('..tostring(M_.result.code)
        ..')')or'',current and current.converted and table.concat(parts,', ')or'none',world and state.mission
        and record_text(world)or'-'))
    if world and carrier.name then mod:log('F10 '..payload_line(world,carrier.name,'PAYLOAD RECORD'))end
end})
mod:log('loaded ('..BUILD..'): virtual stratagem '..GAS.id..' (token '..TOKEN..'; carrier: discovered from what you '
    ..'own and payload-compatible with the '..DONOR..'\'s pattern, never the donor itself; native aboard the ship; in '
    ..'the mission: icon orbital_gas_barrage_masks, code '..CODE_TEXT..', the 120mm\'s pattern with the Gas Strike '
    ..'shell on the carrier\'s own record) and 5 visual placeholders. Ship: click or F7 selects; Ctrl+F7 undoes; F6 focus; Ctrl+F9 slot overlays; '
    ..'F9 status. Mission: F10 status.')
