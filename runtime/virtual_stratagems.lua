-- Virtual custom stratagems (development only; docs/custom-stratagems.md, "A Runtime-owned custom stratagem
-- selector"). Not exported by api/hd2.lua and no public field reaches it.
--
-- A definition is Runtime state only, entirely separate from StratagemInfo: what the Runtime's own selector shows,
-- which vanilla stratagem the loadout saves for it, and what the mission-time slot conversion turns that token into.
--   {id = 'orbital_gas_barrage',
--    display = {name = <Runtime text>, description = <Runtime text>, icon = <Runtime image>,
--               slot_icon = 'Orbital Gas Strike' (optional; FALLBACK ONLY: a VANILLA stratagem whose icon the native
--               loadout slot shows for this definition's slots when a caller starts runtime/stratagem_slot_icons.lua;
--               it must sit on the token's atlas page, which is checked when it is shown),
--               colours = 'EAT-17 Expendable Anti-Tank' (optional: a VANILLA stratagem whose icon colour set the custom
--               panel's tile and the native slot overlay use for this definition, as the native loadout colours that
--               stratagem; default the token's. A support custom stratagem takes a support stratagem's: blue)},
--   A virtual slot shows display.icon over the native slot by default (runtime/stratagem_slot_overlay.lua
--   virtual_slots, started by the custom stratagems panel); the native slot is never written for it.
--    selection = {token = 'Orbital Precision Strike'},     the vanilla stratagem one loadout slot holds
--    mission = {carrier = 'Orbital 120mm HE Barrage'},     what the mission-time slot conversion makes it, or
--    mission = {carriers = {'...', '...'}},                 an ordered list of candidate carriers: the first one every
--                                                           carrier guard accepts (stratagem_selector.choose_carrier), or
--    mission = {discover = true, exclude = {'...'}},        the carrier discovered from what the account owns
--                                                           (stratagem_selector.discover_carrier), never an excluded one
--    calldown = {code = {...}} (optional),
--    payload = {donor = 'Orbital 120mm HE Barrage'} (optional; development, needs mission.discover): the carrier must be
--              payload-compatible with the donor's bombardment pattern (runtime/bombardment_payload.lua), which
--              stratagem_selector.convert_with_payload writes onto the converted carrier's own record;
--              shells = 'Orbital Gas Strike' (optional, stage C): the carrier's shell list then points at that
--              stratagem's own shell instead of the pattern donor's}
-- The texts and the image are the Runtime's own resources (runtime/text_resources.lua, runtime/image_resources.lua);
-- nothing here writes the game.
local texts=require('hd2runtime/runtime/text_resources')
local images=require('hd2runtime/runtime/image_resources')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local M={}
M.MAX=16
local definitions,order={},{}

local DIRECTIONS={up=true,down=true,left=true,right=true}
local function stratagem(name,what)
    local entry=type(name)=='string'and catalog.stratagems[name]
    assert(entry and entry.root and entry.root.id,what..' must name a catalogued stratagem')
    return entry.root.id
end

-- Validates and stores a definition; returns it. owner: the defining mod's resource id.
function M.define(spec,owner)
    assert(type(spec)=='table','a virtual stratagem must be a table')
    assert(type(owner)=='string'and#owner>0,'a virtual stratagem needs its mod')
    local id=spec.id
    assert(type(id)=='string'and#id>=1 and#id<=64 and id:match('^[a-z0-9_]+$'),
        'id must be 1-64 characters of a-z, 0-9 and _')
    assert(not definitions[id],'virtual stratagem '..id..' is already defined')
    assert(#order<M.MAX,'at most '..M.MAX..' virtual stratagems')
    local display=spec.display
    assert(type(display)=='table','display must be {name, description, icon}')
    assert(texts.issued(display.name)and texts.issued(display.description),
        'display.name and display.description must be Runtime texts')
    assert(images.issued(display.icon),'display.icon must be a Runtime image')
    local colours
    if display.colours~=nil then
        colours={stratagem=display.colours,id=stratagem(display.colours,'display.colours')}
    end
    local slot_icon
    if display.slot_icon~=nil then
        assert(display.slot_icon~=spec.selection and display.slot_icon~=(spec.selection or{}).token,
            'display.slot_icon must be another stratagem than the token')
        slot_icon={stratagem=display.slot_icon,id=stratagem(display.slot_icon,'display.slot_icon')}
    end
    assert(type(spec.selection)=='table'and type(spec.mission)=='table','selection and mission are required')
    local token=stratagem(spec.selection.token,'selection.token')
    local carriers=spec.mission.carriers
    local discover=spec.mission.discover
    assert(discover==nil or discover==true,'mission.discover must be true or absent')
    local exclude_ids,exclude_names={},{}
    if discover then
        assert(spec.mission.carrier==nil and carriers==nil,'mission.discover takes no carrier or carriers')
        for k,name in ipairs(spec.mission.exclude or{})do
            exclude_ids[k]=stratagem(name,'mission.exclude['..k..']')
            exclude_names[k]=name
        end
        carriers={}
    else
        assert(spec.mission.exclude==nil,'mission.exclude needs mission.discover')
    end
    assert(discover or(spec.mission.carrier==nil)~=(carriers==nil),'mission needs carrier or carriers (one of them)')
    if carriers==nil then carriers={spec.mission.carrier}end
    assert(type(carriers)=='table'and(discover or#carriers>=1)and#carriers<=8,
        'mission.carriers is a list of 1-8 stratagems')
    local carrier_ids,seen={},{}
    for k,name in ipairs(carriers)do
        local id_=stratagem(name,'mission.carriers['..k..']')
        assert(id_~=token,'the carrier must differ from the token')
        assert(not seen[id_],'mission.carriers lists '..name..' twice')
        seen[id_]=true
        carrier_ids[k]=id_
    end
    local carrier=carrier_ids[1]
    local names={}
    for k,name in ipairs(carriers)do names[k]=name end
    local code
    if spec.calldown~=nil then
        assert(type(spec.calldown)=='table'and type(spec.calldown.code)=='table','calldown must be {code = {...}}')
        assert(#spec.calldown.code>=1 and#spec.calldown.code<=8,'a calldown code has 1-8 directions')
        code={}
        for i,direction in ipairs(spec.calldown.code)do
            assert(DIRECTIONS[direction],'calldown directions are up, down, left and right')
            code[i]=direction
        end
    end
    local payload
    if spec.payload~=nil then
        assert(discover,'payload needs mission.discover (the carrier is chosen for its payload compatibility)')
        assert(type(spec.payload)=='table'and type(spec.payload.donor)=='string','payload must be {donor = name}')
        for key in pairs(spec.payload)do assert(key=='donor'or key=='shells','payload takes only donor and shells')end
        payload={donor=spec.payload.donor,donorId=stratagem(spec.payload.donor,'payload.donor')}
        assert(payload.donorId~=token,'the donor must differ from the token')
        if spec.payload.shells~=nil then
            assert(type(spec.payload.shells)=='string','payload.shells must name a stratagem')
            payload.shells=spec.payload.shells
            payload.shellsId=stratagem(spec.payload.shells,'payload.shells')
            assert(payload.shellsId~=token and payload.shellsId~=payload.donorId,
                'the shell donor must differ from the token and the pattern donor')
        end
    end
    local definition={id=id,owner=owner,display={name=display.name,description=display.description,icon=display.icon,
        slotIcon=slot_icon,colours=colours and colours.stratagem,coloursId=colours and colours.id},
        selection={token=spec.selection.token,tokenId=token},mission={carrier=carriers[1],carrierId=carrier,
            carriers=names,carrierIds=carrier_ids,discover=discover==true,exclude=exclude_names,excludeIds=exclude_ids},
        calldown=code and{code=code}or nil,payload=payload}
    definitions[id]=definition
    order[#order+1]=definition
    return definition
end
function M.get(id)return definitions[id]end
function M.list()
    local out={}
    for i,definition in ipairs(order)do out[i]=definition end
    return out
end
-- The display strings of a definition in a game language code (the Runtime text's own fallback applies).
function M.strings(definition,code)
    return texts.text(definition.display.name,code or'us'),texts.text(definition.display.description,code or'us')
end
function M.reset_for_tests()definitions,order={},{}end
return M
