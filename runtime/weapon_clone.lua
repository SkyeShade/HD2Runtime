-- The carrier weapon clone (development; research/docs/carrier-weapon-clone-F5FEE03DCFDB.md, docs/custom-stratagem-api.md
-- "expendable"). Not exported by api/hd2.lua.
--
-- An unused vanilla support weapon TYPE of the donor's expendable component class (for the EAT-17: the EAT-700, then the
-- EAT-411; domains/weapon_clone.lua) becomes the donor for ONE mission. The game reads its weapon type records in place
-- (the entity manager's type tables ARE the entity region the Runtime's entity writes use; a private per-entity copy
-- exists only for an entity created with an entity delta on that component), so the carrier's own records are
-- converted BEFORE its first entity exists and restored only aboard the ship:
--   * presentation: EncyclopediaEntry +8 (the name every pickup prompt, map label and weapon panel shows: a Runtime
--     text, else the donor's), +0x30 (the weapon panel image: the donor's), Spottable +0x38 (the marker / prompt icon: a
--     Runtime icon family, else the donor's);
--   * model: the unit, the sight (default optics option and optics unit), the wielder's animations and grip;
--   * full: the rocket (ProjectileWeapon +0), its sounds and the handling members, so the carrier is the donor.
-- Every member is copied from the donor's REVIEWED value (pinned research, never a live entity). The carrier's records
-- must each have exactly one owner and hold exactly their reviewed native bytes (an FNV-1a of the whole record), the
-- game's type tables must point at them, no entity of the carrier type may exist yet, and the pins (the type-table
-- readers, the prompt icon path, the Spottable instance manager) must prove on this game.dll; else nothing is written.
-- One guarded transaction (the entity region's PAGE_READONLY handling, read-back, non-target bytes, protection
-- restored). restore() (a job) and restore_now() (one tick, for the loadout-screen boundary) write the captured bytes
-- back only where the record still holds what was written (CONFLICT otherwise) and verify every record is its native
-- bytes again. A finalizer restores before this Lua state closes.
-- A ROUND (spec.round: a reviewed round of the donor, M.round / M.rounds) makes the clone fire that round instead of
-- the donor's own: ProjectileWeapon +0 ProjType := the round's type at every level (see "rounds" below).
-- A VARIANT (spec.variant = true; domains/weapon_variants.lua, research/docs/weapon-variants-F5FEE03DCFDB.md) is a weapon
-- whose component class is itself (the M-1000 Maxigun): its OWN type becomes the custom weapon for one mission, never
-- another's: the presentation members (as a clone's), its round (ProjectileWeapon +0 := a catalogued attack output of
-- its own compatibility class, its package resident) and its model (UnitComponent +0 UnitPath := a Runtime-owned unit
-- the mod ships beside the vanilla one, runtime/model_resources.lua: loaded, derived on this build from the reviewed
-- base unit; the UnitPath consumer pins proven). Same records rule, same transaction, same restore.
if rawget(_G,'jit')then jit.off(true,true)end
local bit=require('bit')
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local Reader=require('hd2runtime/runtime/reader')
local texts=require('hd2runtime/runtime/text_resources')
local images=require('hd2runtime/runtime/image_resources')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local core_assets=require('hd2runtime/core/assets')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/weapon_clone')
local V=require('hd2runtime/domains/weapon_variants')
local models=require('hd2runtime/runtime/model_resources')
local M={}
M.LEVELS={presentation=1,model=2,full=3}
M.PAGE=4096
M.MAX_INSTANCES=65536
local TWO32=4294967296

local function log(text)log_module.emit('[HD2Runtime] weapon clone '..text)end
local function fnv1a(text)
    local h=2166136261
    for i=1,#text do
        h=bit.bxor(h,text:byte(i))%TWO32
        h=((h%256)*16777216+h*403)%TWO32
    end
    return string.format('%08X',h)
end
M.fnv1a=fnv1a

-- The entity catalog's profile with the clone's components (the generated schema: the same entity file).
local merged={}
for k,v in pairs(profile)do merged[k]=v end
merged.components=setmetatable({},{__index=function(_,name)return D.components[name]or profile.components[name]end})
local NAMES={}
for name in pairs(D.components)do NAMES[#NAMES+1]=name end
table.sort(NAMES)

-- A carrier's reviewed facts: a variant host's own (variant = true), else a clone carrier's, else a variant host's. A
-- weapon can be both (the EAT-700: a carrier of the EAT-17 clone, and a variant host), and the two differ: a clone
-- carrier's presentation borrows the DONOR's values, a variant's its own.
local function facts(carrier,variant)
    if variant then return V.hosts[carrier]end
    return D.carriers[carrier]or V.hosts[carrier]
end
-- The clone hosts of a donor, in pool order (nil: not a clone donor). variant = true: a variant's pool (the weapon
-- itself), even for a weapon that is also a clone donor (the EAT-17).
function M.pool(donor,variant)
    local d
    if variant then d=V.hosts[donor]else d=D.donors[donor]end
    if not d then return nil end
    local out={}
    for k,name in ipairs(d.pool)do out[k]=name end
    return out
end
-- A clone DONOR's reviewed facts (domains/weapon_clone.lua donors), or nil. A variant host is not a clone donor.
function M.donor(name)return D.donors[name]end
-- Every clone donor, sorted.
function M.donors()
    local out={}
    for name in pairs(D.donors)do out[#out+1]=name end
    table.sort(out)
    return out
end
function M.carrier(name)return D.carriers[name]or V.hosts[name]end
-- A variant host's reviewed facts (its own type is its only carrier), or nil.
function M.variant(name)return V.hosts[name]end
-- Why a support weapon can have no variant (a shared written record, no stratagem of its own), or nil.
function M.variant_excluded(name)return V.excluded and V.excluded[name]end
function M.variants()
    local out={}
    for name in pairs(V.hosts)do out[#out+1]=name end
    table.sort(out)
    return out
end

-- EXPENDABLE LIFECYCLE vs CLONE COMPATIBILITY (research/docs/expendable-carriers-F5FEE03DCFDB.md). A lifecycle member
-- is a support weapon that discards itself when empty and can never be reloaded (WeaponData +0x1CC auto drop, no
-- WeaponReload / SeatCollection instance to stop it, no other ammunition feed, no spare magazine): EAT-17, EAT-700,
-- EAT-411, MLS-4X Commando, MGX-42 Bullet Storm. Membership says nothing about the vanilla round count (the Commando has
-- 4, the Bullet Storm 300). A member carries a donor's TYPE-level clone only inside the donor's component class (the
-- same component set, the expendable contract identical): for the EAT-17 the EAT-700 and the EAT-411 (M.pool, which
-- membership never widens). Read-only data.
-- The lifecycle members in order (names).
function M.expendables()
    local out={}
    for k,name in ipairs(D.expendables.order)do out[k]=name end
    return out
end
-- A member's reviewed facts {entity, label, stableId, autoDropAbility, dropMode, rounds, spareMagazines, chambered,
-- podCapacity, exclusiveRack, cloneClass, roundsOverride = {type, instance}, clone = {[donor] = {compatible, reason}}},
-- or nil (not an expendable lifecycle member).
function M.expendable(name)return D.expendables.members[name]end
-- The members sharing a member's component set (itself included), or nil.
function M.clone_class(name)
    local m=D.expendables.members[name]
    if not m then return nil end
    local out={}
    for k,x in ipairs(m.cloneClass)do out[k]=x end
    return out
end
-- Whether `carrier` can host a type-level clone of `donor`: true, or false and why.
function M.compatible(donor,carrier)
    local d=D.donors[donor]
    if not d then return false,tostring(donor)..' is not a reviewed clone donor'end
    local m=D.expendables.members[carrier]
    if not m then return false,tostring(carrier)..' is not an expendable lifecycle member'end
    local c=m.clone[donor]
    local in_pool=false
    for _,name in ipairs(d.pool)do in_pool=in_pool or name==carrier end
    if c and c.compatible==true and in_pool then return true end
    return false,(c and c.reason)or('no reviewed '..donor..' clone compatibility')
end
---------------------------------------------------------------------------------------------------- rounds --
-- A donor's reviewed ROUNDS (domains/weapon_clone.lua rounds; scripts/research_clone_rounds.py): a round its clone may
-- fire instead of the donor's own. The carrier's ProjectileWeapon +0 ProjType becomes the round's type at EVERY level
-- (at full instead of the donor's value; at presentation and model as one more write from the carrier's reviewed native
-- value), so every machine spawns every copy of every shot from its own converted type as that round. The round's whole
-- behaviour is its rows' (the RL-77 Airburst round 312: a proximity burst after 1 m, a 1.5 s self-burst, explosion 325
-- releasing 25 bomblets 78 that explode as 7). Before a write: the code consuming those members proves, every reviewed
-- row of the chain is exactly as reviewed (relocated words masked; ROUND_CHANGED) and both packages its resources ship
-- in are resident (ROUND_NOT_RESIDENT): the round's own loadout package (a custom stratagem loads it through the asset
-- key) and the mission package (loaded with the level, never requested). Residency is core/assets state(): the engine's
-- package list with every part loaded, which holds a level-loaded package too (it never reads the refcount map).
local ROUNDS=D.rounds or{}
local function round_entry(donor,name)
    local list=type(donor)=='string'and ROUNDS[donor]or nil
    return type(name)=='string'and list and list[name]or nil
end
-- The carrier's reviewed ProjType write (ProjectileWeapon +0), or nil.
local function projtype_write(c)
    for _,w in ipairs(c.writes)do
        if w.component=='ProjectileWeaponComponentData'and w.offset==0 and w.width==4 then return w end
    end
end
-- The reviewed round `name` of `donor`, or nil: {name, type, asset_key, weapon (its weapon entity), packages = {unit,
-- mission} (package ids), package_names = {unit, mission}, impact, expiry, proximity, arming, lifetime, speed,
-- direct = {standard, armor_penetration}, submunition = {count, projectile, explosion}, summary}. A copy.
function M.round(donor,name)
    local r=round_entry(donor,name)
    if not r then return nil end
    return {name=r.name,type=r.type,asset_key=r.assetKey,weapon=r.weapon,
        packages={unit=r.packages.unit.id,mission=r.packages.mission.id},
        package_names={unit=r.packages.unit.name,mission=r.packages.mission.name},
        impact=r.impact,expiry=r.expiry,proximity=r.proximity,arming=r.arming,lifetime=r.lifetime,speed=r.speed,
        direct={standard=r.direct.standard,armor_penetration=r.direct.armorPenetration},
        submunition=r.submunition and{count=r.submunition.count,projectile=r.submunition.projectile,
            explosion=r.submunition.explosion}or nil,
        summary=r.summary}
end
-- The reviewed round names of a donor, sorted (empty: none, or not a clone donor).
function M.rounds(donor)
    local out={}
    for name in pairs(type(donor)=='string'and ROUNDS[donor]or{})do out[#out+1]=name end
    table.sort(out)
    return out
end

-- How many writes a level makes on a carrier (presentation members included). With `round` (a reviewed round's name of
-- a donor whose pool holds the carrier) the ProjType write is counted at every level (below full it is one more write;
-- at full it replaces the donor's value). nil when the carrier, the level or the round is not reviewed.
function M.writes_at(carrier,level,round)
    local c=D.carriers[carrier]
    local rank=M.LEVELS[level]
    if not(c and rank)then return nil end
    local n=#c.presentation
    for _,w in ipairs(c.writes)do if M.LEVELS[w.level]<=rank then n=n+1 end end
    if round~=nil then
        local reviewed=false
        for donor,d in pairs(D.donors)do
            for _,name in ipairs(d.pool)do reviewed=reviewed or(name==carrier and round_entry(donor,round)~=nil)end
        end
        local w=projtype_write(c)
        if not(reviewed and w)then return nil end
        if M.LEVELS[w.level]>rank then n=n+1 end
    end
    return n
end

---------------------------------------------------------------------------------------------------- proofs --
local proven={}
-- The pins (the component type-table readers, the pickup prompt's icon path, the Spottable instance manager) on this
-- game.dll: true, or nil and why. Proven once per loaded game.
function M.prove(world)
    local key=tostring(world.game)
    if proven[key]then return true end
    for _,pin in ipairs(D.pins)do
        local expected=b.unhex(pin.hex)
        if world.runtime.read(world.game+pin.rva,#expected)~=expected then
            return nil,('the weapon clone research no longer matches this game.dll (%s at game.dll+%X)'):format(pin.label,
                pin.rva)
        end
    end
    proven[key]=true
    return true
end

local function masked_equal(bytes,reviewed,masked)
    if not bytes or#bytes~=#reviewed then return false end
    local skip={}
    for _,offset in ipairs(masked or{})do skip[offset]=true end
    for offset=0,#reviewed-4,4 do
        if not skip[offset]and bytes:sub(offset+1,offset+4)~=reviewed:sub(offset+1,offset+4)then return false end
    end
    return true
end
-- Whether a reviewed round can be written now (read-only, within this call): the code consuming its members proves on
-- this game.dll (once per loaded game), every row of its chain is exactly as reviewed and both its packages are
-- resident. true, or nil, code, reason.
local proven_rounds={}
function M.round_ready(world,donor,name)
    local r=round_entry(donor,name)
    if not r then
        return nil,'UNREVIEWED_ROUND',tostring(name)..' is not a reviewed round of the '..tostring(donor)..' clone'
    end
    local key=tostring(world.game)..'|'..donor..'|'..name
    if not proven_rounds[key]then
        for _,pin in ipairs(r.pins)do
            local expected=b.unhex(pin.hex)
            if world.runtime.read(world.game+pin.rva,#expected)~=expected then
                return nil,'UNSUPPORTED_BUILD',('the %s round research no longer matches this game.dll (%s at '
                    ..'game.dll+%X)'):format(name,pin.label,pin.rva)
            end
        end
        proven_rounds[key]=true
    end
    for _,row in ipairs(r.rows)do
        local at=world.view.pointer(world.game+row.table+row.id*8)
        if not masked_equal(at and world.view.read(at,row.stride),b.unhex(row.reviewed),row.masked)then
            return nil,'ROUND_CHANGED',('%s %d of the %s round is not its reviewed row'):format(row.kind,row.id,name)
        end
    end
    for _,role in ipairs({'unit','mission'})do
        local p=r.packages[role]
        local ok,state=pcall(core_assets.state,world.runtime,p.id)
        if not(ok and state=='resident')then
            return nil,'ROUND_NOT_RESIDENT',('the %s round\'s %s package %s is %s'):format(name,role,p.name or p.id,
                ok and tostring(state)or('unreadable: '..tostring(state)))
        end
    end
    return true
end

-- The live entities of a type (16 hex digits, '0x' optional) through the Spottable instance manager (every support
-- weapon has a Spottable component): their number, or nil and why. Read-only.
function M.instances(world,entity_type)
    local want=tostring(entity_type):gsub('^0x',''):upper()
    local S=D.spottableInstances
    local manager=world.view.pointer(world.game+S.global)
    if not manager or manager==0 then return nil,'no Spottable instance manager'end
    local count=world.view.u32(manager+S.count)
    local handles=world.view.pointer(manager+S.handles)
    if not count or count>M.MAX_INSTANCES or(count>0 and not handles)then return nil,'the Spottable instances are unreadable'end
    if count==0 then return 0 end
    local raw=world.view.read(handles,count*8)
    if not raw or#raw~=count*8 then return nil,'the Spottable instance list is unreadable'end
    local n=0
    for i=0,count-1 do
        local handle=b.pointer(raw,i*8)
        local kind=handle and handle~=0 and world.view.read(handle+S.handleType,8)
        if kind and#kind==8 and string.format('%08X%08X',b.u32(kind,4),b.u32(kind,0))==want then n=n+1 end
    end
    return n
end

-- The carrier's records as the game holds them now: {[component] = record (catalog.record: bytes, owner, offset)}, the
-- entity region, or nil, code, reason. Inside a coroutine (the reader yields).
local function capture(world,carrier,variant)
    local c=facts(carrier,variant)
    local reader=Reader.new(world.runtime)
    require('hd2runtime/core/fingerprint').require(world.runtime)
    local roots=discover.locate(world.runtime,reader,profile,{entity=true})
    local catalog=entities.capture(reader,roots.entity,merged,NAMES)
    local candidate
    for _,x in ipairs(catalog.candidates)do if x.resourceHash==c.entity then candidate=x end end
    if not(candidate and candidate.entityRow and#candidate.diagnostics==0)then
        return nil,'IDENTITY_CHANGED','the '..carrier..' entity is not where the research found it'
    end
    local records={}
    local em=world.view.pointer(world.game+D.entityManager)
    for component,r in pairs(c.records)do
        local ok,record=pcall(catalog.record,candidate,component)
        if not ok then return nil,'IDENTITY_CHANGED',carrier..' '..component..': '..tostring(record)end
        local id=record.identity
        if id.recordIndex~=r.recordIndex or id.indexRow~=r.indexRow then
            return nil,'IDENTITY_CHANGED',carrier..' '..component..' moved (row '..tostring(id.indexRow)..', record '
                ..tostring(id.recordIndex)..')'
        end
        if id.ownerCount~=1 or id.uniqueOwner~=true then
            return nil,'SHARED',carrier..' '..component..' is shared by '..tostring(id.ownerCount)..' entities'
        end
        -- The game's own type table for this component is this region's (the type lookups read it in place).
        local schema=D.components[component]
        local table_at=em and world.view.pointer(em+schema.slot)
        if table_at~=roots.entity.base+schema.offset+28 then
            return nil,'TABLE_ELSEWHERE','the game\'s '..component..' type table is not the entity region\'s'
        end
        records[component]=record
    end
    return records,roots.entity
end

---------------------------------------------------------------------------------------------------- state --
-- {applied, restored, carrier, donor, level, changes = {{label, component, owner, offset, before, desired}},
--  records = {[component] = {offset, owner, fnv1a}}, borrowed}, one per carrier, by carrier name.
local states={}
local sentinel
local restoring={}
local function held(s)return s~=nil and s.applied and not s.restored end
local function run(body,now)
    local co=coroutine.create(body)
    for _=1,100000 do
        local ok,result,code,reason=coroutine.resume(co)
        if not ok then return nil,'FAILED',tostring(result)end
        if coroutine.status(co)=='dead'then return result,code,reason end
        if not now then coroutine.yield()end
    end
    return nil,'FAILED','the operation did not finish'
end
local function job(body,callback)
    local handle={status='pending'}
    local co=coroutine.create(body)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    handle.watch=watch
    function watch.tick()
        if watch.status~='active'then return end
        local ok,result,code,reason=coroutine.resume(co)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then handle.status,handle.code,handle.reason='failed','FAILED',tostring(result)
        elseif result then for key,value in pairs(result)do handle[key]=value end
        else handle.status,handle.code,handle.reason='refused',code,reason end
        if handle.status~='applied'and handle.status~='restored'then
            log('refused: '..tostring(handle.code)..': '..tostring(handle.reason))
        end
        if callback then callback(handle)end
    end
    scheduler.attach(watch)
    return handle
end
local restore_body
local function finalize()
    local list={}
    for carrier,s in pairs(states)do if held(s)then list[#list+1]=carrier end end
    table.sort(list)
    for _,carrier in ipairs(list)do pcall(run,function()return restore_body(true,carrier)end,true)end
end
local function arm()
    if sentinel then return end
    local ok,ffi=pcall(require,'ffi')
    if ok then sentinel=ffi.gc(ffi.new('uint8_t[1]'),function()pcall(finalize)end)end
end
local function disarm()
    for _,s in pairs(states)do if held(s)then return end end
    if sentinel then pcall(function()require('ffi').gc(sentinel,nil)end);sentinel=nil end
end

-- One change of the transaction; an 8- or 12-byte member that would cross a page is written as 4-byte words.
local function add_changes(list,label,component,record,offset,before,desired)
    local address=record.owner.base+record.offset+offset
    local parts={{0,#desired}}
    if address%M.PAGE+#desired>M.PAGE then
        parts={}
        for k=0,#desired-4,4 do parts[#parts+1]={k,4}end
    end
    for _,p in ipairs(parts)do
        local at,width=p[1],p[2]
        local was,want=before:sub(at+1,at+width),desired:sub(at+1,at+width)
        list[#list+1]={label='weapon_clone.'..label..(#parts>1 and(' +'..at)or''),component=component,
            owner=record.owner,offset=record.offset+offset+at,expected=was,desired=want,before=was,
            already_desired=was==want,identity={component=component,component_type='weapon clone host',
            record_index=record.index,unique_owner=true,owner_count=1},chain={}}
    end
end

-- The values the presentation members take: the Runtime text / icon when ready, else the donor's (borrowed, with why).
local function presentation_values(world,carrier,spec,donor)
    local out,borrowed={},{}
    local runtime=world.runtime
    for _,p in ipairs(facts(carrier,spec.variant==true).presentation)do
        local value=b.unhex(p.donor)
        if p.role=='name'and spec.name then
            local registered,code,reason=texts.ensure(runtime)
            local ok,rcode,rreason
            if registered then ok,rcode,rreason=texts.resolves(runtime,spec.name)end
            if registered and ok then value=texts.id_bytes(spec.name)
            else borrowed.name=('the Runtime text is not shown by the game (%s: %s): the %s\'s name is borrowed')
                :format(tostring(registered and rcode or code),tostring(registered and rreason or reason),donor)end
        elseif p.role=='icon'and spec.icon then
            local ok,ready,code,reason=pcall(images.icon_ready,runtime,spec.icon)
            if ok and ready then value=images.bytes(spec.icon)
            else borrowed.icon=('the Runtime icon is not ready (%s: %s): the %s\'s marker icon is borrowed'):format(
                tostring(ok and code or'UNAVAILABLE'),tostring(ok and reason or ready),donor)end
        end
        out[p.role]=value
    end
    if not spec.name then borrowed.name='none given: the '..donor..'\'s name is borrowed'end
    if not spec.icon then borrowed.icon='none given: the '..donor..'\'s marker icon is borrowed'end
    return out,borrowed
end

-- Converts a carrier weapon type for this mission. spec = {carrier = a clone host's catalogue name, donor = its
-- donor's, level = 'presentation' | 'model' | 'full', name = a Runtime text (runtime/text_resources.lua) or nil,
-- icon = hd2.resources.image(id) or nil, multiplayer = true (a custom stratagem's own conversion with several players),
-- round = the name of a reviewed round of the donor (M.rounds) or nil}.
-- A job: 'applied' (or 'refused' / 'failed' with code and reason; nothing is then left written). With a round:
-- INVALID (not a string), UNREVIEWED_ROUND, UNSUPPORTED_BUILD (its code pins), ROUND_CHANGED (a chain row is not as
-- reviewed), ROUND_NOT_RESIDENT (either package), all before any write.
function M.apply(spec,callback)
    return job(function()
        if type(spec)~='table'then return nil,'INVALID','spec must be a table'end
        for key in pairs(spec)do
            if key~='carrier'and key~='donor'and key~='level'and key~='name'and key~='icon'and key~='multiplayer'
                and key~='label'and key~='round'and key~='variant'and key~='model'then
                return nil,'INVALID','unsupported weapon clone option: '..tostring(key)
            end
        end
        if spec.variant~=nil or spec.model~=nil then return M.variant_body(spec)end
        local c,d=D.carriers[spec.carrier],D.donors[spec.donor]
        if not(c and d)then return nil,'UNREVIEWED',tostring(spec.carrier)..' is not a reviewed clone host of '
            ..tostring(spec.donor)end
        local in_pool=false
        for _,name in ipairs(d.pool)do in_pool=in_pool or name==spec.carrier end
        if not in_pool then return nil,'NOT_IN_CLASS',spec.carrier..' is not in '..spec.donor..'\'s expendable class'end
        local rank=M.LEVELS[spec.level]
        if not rank then return nil,'INVALID','level must be presentation, model or full'end
        local round,round_write
        if spec.round~=nil then
            if type(spec.round)~='string'then
                return nil,'INVALID','round must be the name of a reviewed round of the '..spec.donor..' clone'
            end
            round=round_entry(spec.donor,spec.round)
            if not round then
                return nil,'UNREVIEWED_ROUND',spec.round..' is not a reviewed round of the '..spec.donor..' clone'
            end
            round_write=projtype_write(c)
            if not round_write then return nil,'UNREVIEWED_ROUND',spec.carrier..' has no reviewed ProjType write'end
        end
        if spec.name~=nil and not texts.issued(spec.name)then return nil,'INVALID','name must be a Runtime text'end
        if spec.icon~=nil and not images.issued(spec.icon)then return nil,'INVALID','icon must be hd2.resources.image(id)'end
        if held(states[spec.carrier])then return nil,'ALREADY_APPLIED',spec.carrier..' is already a clone'end
        local world,why=world_module.open()
        if not world then return nil,'UNAVAILABLE',tostring(why)end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return nil,'NOT_IN_MISSION','a carrier weapon is converted in a mission only'end
        local players=#(world_module.players(world)or{})
        if players>1 and spec.multiplayer~=true then
            return nil,'NOT_SOLO','with several players only a custom stratagem\'s synchronized conversion runs'
        end
        local ok,pwhy=M.prove(world)
        if not ok then return nil,'UNSUPPORTED_BUILD',pwhy end
        -- Before its first entity: an entity created earlier would keep a vanilla model and copies.
        local present,iwhy=M.instances(world,c.entity)
        if present==nil then return nil,'UNAVAILABLE',iwhy end
        if present>0 then
            return nil,'CARRIER_PRESENT',('%d %s entit%s already exist in this world (a call before this machine\'s '
                ..'setup, or a join in progress): converting now would leave them vanilla'):format(present,spec.carrier,
                present==1 and'y'or'ies')
        end
        local records,rcode,rreason=capture(world,spec.carrier)
        if not records then return nil,rcode,rreason end
        for component,r in pairs(c.records)do
            if fnv1a(records[component].bytes)~=r.fnv1a then
                return nil,'NOT_NATIVE',spec.carrier..' '..component..' is not its reviewed native record (another '
                    ..'writer changed it): nothing written'
            end
        end
        if round then
            local ready,code,reason=M.round_ready(world,spec.donor,spec.round)
            if not ready then return nil,code,reason..': nothing written'end
        end
        local values,borrowed=presentation_values(world,spec.carrier,spec,spec.donor)
        local changes={}
        for _,p in ipairs(c.presentation)do
            local record=records[p.component]
            add_changes(changes,p.role,p.component,record,p.offset,b.unhex(p.native),values[p.role])
        end
        for _,w in ipairs(c.writes)do
            if M.LEVELS[w.level]<=rank then
                local desired=b.unhex(w.donor)
                -- The round replaces the donor's ProjType at full.
                if w==round_write then desired=b.encode(round.type,'u32')end
                add_changes(changes,w==round_write and(w.label..' (round)')or w.label,w.component,records[w.component],
                    w.offset,b.unhex(w.native),desired)
            end
        end
        -- Below full, the round is one more write from the carrier's reviewed native ProjType.
        if round and M.LEVELS[round_write.level]>rank then
            add_changes(changes,round_write.label..' (round)',round_write.component,records[round_write.component],
                round_write.offset,b.unhex(round_write.native),b.encode(round.type,'u32'))
        end
        local snapshots,seen={},{}
        for component,record in pairs(records)do
            if not seen[component]then
                seen[component]=true
                snapshots[#snapshots+1]={owner=record.owner,offset=record.offset,bytes=record.bytes}
            end
        end
        table.sort(snapshots,function(a,x)return a.offset<x.offset end)
        local report=transaction.apply(world.runtime,{changes=changes,snapshots=snapshots})
        metrics.count('weapon_clone.transactions')
        if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
        local state={applied=true,restored=false,carrier=spec.carrier,donor=spec.donor,level=spec.level,
            changes={},records={},borrowed=borrowed,report=report,round=round and spec.round or nil}
        for _,ch in ipairs(changes)do
            if ch.before~=ch.desired then
                state.changes[#state.changes+1]={label=ch.label,component=ch.component,owner=ch.owner,offset=ch.offset,
                    before=ch.before,desired=ch.desired}
            end
        end
        for component,record in pairs(records)do
            state.records[component]={owner=record.owner,offset=record.offset,size=#record.bytes,
                fnv1a=c.records[component].fnv1a}
        end
        states[spec.carrier]=state
        arm()
        -- What the game will read: every change, exactly; nothing else of the records.
        local exact=true
        for _,ch in ipairs(state.changes)do
            if world.runtime.read(ch.owner.base+ch.offset,#ch.desired)~=ch.desired then exact=false end
        end
        local parts={}
        for _,key in ipairs({'name','icon'})do if borrowed[key]then parts[#parts+1]=key..': '..borrowed[key]end end
        log(('APPLIED (%s): %s is the %s for this mission: %d writes (level %s: presentation%s%s); each record had one '
            ..'owner and its exact native bytes; read back %s; non-target bytes unchanged %s, protection restored '
            ..'%s%s%s')
            :format(tostring(spec.label or spec.carrier),spec.carrier,spec.donor,report.writes,spec.level,
            rank>=2 and', model and animations'or'',rank>=3 and', rocket, sounds and handling'or'',tostring(exact),
            tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored),
            #parts>0 and('; borrowed '..table.concat(parts,'; '))or'',
            round and('; it fires '..round.summary..': its rows as reviewed, both packages resident')or''))
        if not exact then
            local back,bcode,breason=restore_body(false,spec.carrier)
            return nil,'VERIFY_FAILED','a converted member does not read back'..(back and'; restored'or('; restore '
                ..tostring(bcode)..': '..tostring(breason)))
        end
        return {status='applied',carrier=spec.carrier,donor=spec.donor,level=spec.level,writes=report.writes,
            borrowed=borrowed,round=state.round,verify={exact=exact,nonTarget=report.non_target_bytes_unchanged,
            protection=report.protection_restored}}
    end,callback)
end

-- The UnitPath consumer pins (domains/weapon_variants.lua unitPins: every lookup call site and type-table read, reviewed)
-- on this game.dll: true, or nil and why. Proven once per loaded game.
local proven_unit={}
function M.prove_model_consumers(world)
    local key=tostring(world.game)
    if proven_unit[key]then return true end
    for _,pin in ipairs(V.unitPins)do
        local expected=b.unhex(pin.hex)
        if world.runtime.read(world.game+pin.rva,#expected)~=expected then
            return nil,('the UnitPath consumer review no longer matches this game.dll (%s at game.dll+%X)'):format(pin.label,
                pin.rva)
        end
    end
    proven_unit[key]=true
    return true
end
-- Where a record differs from its reviewed native bytes (hex): '; differs at +off native -> now, ...' (4-byte words,
-- little-endian u32 hex, at most 12), or '' without reviewed bytes. Read-only; for the refusal's log line.
local function u32hex(word)return(word:reverse():gsub('.',function(ch)return('%02X'):format(ch:byte())end))end
function M.native_diff(native_hex,bytes)
    if type(native_hex)~='string'or type(bytes)~='string'then return''end
    local native=b.unhex(native_hex)
    if #native~=#bytes then return('; the record is %d bytes, reviewed %d'):format(#bytes,#native)end
    local parts,n={},0
    for at=0,#native-1,4 do
        local a,x=native:sub(at+1,at+4),bytes:sub(at+1,at+4)
        if a~=x then
            n=n+1
            if n<=12 then
                parts[#parts+1]=('+0x%X %s -> %s'):format(at,u32hex(a),u32hex(x))
            end
        end
    end
    if n==0 then return''end
    return('; differs in %d word%s: %s%s'):format(n,n==1 and''or's',table.concat(parts,', '),n>12 and', ...'or'')
end
-- How many writes a variant makes (presentation, plus a round and a model when given), or nil (not a variant host).
function M.variant_writes(carrier,round,model)
    local c=V.hosts[carrier]
    if not c then return nil end
    return #c.presentation+(round and 1 or 0)+(model and 1 or 0)
end
-- A variant's conversion (inside apply's job). spec = {carrier = a variant host, variant = true, donor = nil or the
-- carrier, name, icon, multiplayer, label, round = {type, package, label} or nil, model = hd2.resources.model(id) or nil}.
function M.variant_body(spec)
    if spec.variant~=true then return nil,'INVALID','variant must be true (a model is a variant\'s)'end
    local c=V.hosts[spec.carrier]
    if not c then return nil,'UNREVIEWED',tostring(spec.carrier)..' is not a reviewed variant host'end
    if spec.donor~=nil and spec.donor~=spec.carrier then
        return nil,'NOT_IN_CLASS','a variant converts its own type only: '..tostring(spec.donor)..' is not '..spec.carrier
    end
    if spec.level~=nil and spec.level~='variant'then return nil,'INVALID','a variant has no clone level'end
    local round=spec.round
    if round~=nil then
        if type(round)~='table'or type(round.type)~='number'or round.type<1 or round.type>65535 or round.type%1~=0
            or type(round.package)~='string'then
            return nil,'INVALID','round must be {type, package, label}'
        end
        if not c.round then
            return nil,'NO_ROUND','the '..spec.carrier..' fires no projectile (no ProjectileWeapon): it has no round to change'
        end
        if round.type==c.projectile then round=nil end
    end
    if spec.model~=nil and not models.issued(spec.model)then
        return nil,'INVALID','model must be hd2.resources.model(id)'
    end
    if spec.name~=nil and not texts.issued(spec.name)then return nil,'INVALID','name must be a Runtime text'end
    if spec.icon~=nil and not images.issued(spec.icon)then return nil,'INVALID','icon must be hd2.resources.image(id)'end
    if held(states[spec.carrier])then return nil,'ALREADY_APPLIED',spec.carrier..' is already converted'end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','a variant is converted in a mission only'end
    local players=#(world_module.players(world)or{})
    if players>1 and spec.multiplayer~=true then
        return nil,'NOT_SOLO','with several players only a custom stratagem\'s synchronized conversion runs'
    end
    local ok,pwhy=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',pwhy end
    local present,iwhy=M.instances(world,c.entity)
    if present==nil then return nil,'UNAVAILABLE',iwhy end
    if present>0 then
        return nil,'CARRIER_PRESENT',('%d %s entit%s already exist in this world (a call before this machine\'s setup, '
            ..'or a join in progress): converting now would leave them vanilla'):format(present,spec.carrier,
            present==1 and'y'or'ies')
    end
    local records,rcode,rreason=capture(world,spec.carrier,true)
    if not records then return nil,rcode,rreason end
    for component,r in pairs(c.records)do
        if fnv1a(records[component].bytes)~=r.fnv1a then
            return nil,'NOT_NATIVE',spec.carrier..' '..component..' is not its reviewed native record (another writer '
                ..'changed it): nothing written'..M.native_diff(r.native,records[component].bytes)
        end
    end
    if round then
        local rok,state=pcall(core_assets.state,world.runtime,round.package)
        if not(rok and state=='resident')then
            return nil,'ROUND_NOT_RESIDENT',('the %s round\'s package %s is %s: nothing written'):format(tostring(
                round.label),round.package,rok and tostring(state)or('unreadable: '..tostring(state)))
        end
    end
    if spec.model then
        local mok,mwhy=M.prove_model_consumers(world)
        if not mok then return nil,'UNSUPPORTED_BUILD',mwhy..': nothing written'end
        local ready,code,reason=models.ready(world.runtime,spec.model,spec.carrier)
        if not ready then return nil,'MODEL_'..tostring(code),tostring(reason)..': nothing written'end
    end
    local values,borrowed=presentation_values(world,spec.carrier,spec,spec.carrier)
    local changes={}
    for _,p in ipairs(c.presentation)do
        add_changes(changes,p.role,p.component,records[p.component],p.offset,b.unhex(p.native),values[p.role])
    end
    if round then
        local w=c.round
        add_changes(changes,'ProjType (round '..tostring(round.label)..')',w.component,records[w.component],w.offset,
            b.unhex(w.native),b.encode(round.type,'u32'))
    end
    if spec.model then
        local w=c.model
        add_changes(changes,'UnitPath (model '..models.label(spec.model)..')',w.component,records[w.component],w.offset,
            b.unhex(w.native),models.unit_bytes(spec.model))
    end
    local snapshots={}
    for _,record in pairs(records)do snapshots[#snapshots+1]={owner=record.owner,offset=record.offset,bytes=record.bytes}end
    table.sort(snapshots,function(a,x)return a.offset<x.offset end)
    -- Nothing differs (no Runtime name or icon the game can show, no round, no model): nothing to write.
    local differs=false
    for _,ch in ipairs(changes)do differs=differs or ch.before~=ch.desired end
    local report={status='APPLIED',writes=0,non_target_bytes_unchanged=true,protection_restored=true}
    if differs then
        report=transaction.apply(world.runtime,{changes=changes,snapshots=snapshots})
        metrics.count('weapon_clone.transactions')
    end
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local state={applied=true,restored=false,carrier=spec.carrier,donor=spec.carrier,level='variant',variant=true,
        changes={},records={},borrowed=borrowed,report=report,round=round and round.label or nil,
        model=spec.model and models.unit_hex(spec.model)or nil}
    for _,ch in ipairs(changes)do
        if ch.before~=ch.desired then
            state.changes[#state.changes+1]={label=ch.label,component=ch.component,owner=ch.owner,offset=ch.offset,
                before=ch.before,desired=ch.desired}
        end
    end
    for component,record in pairs(records)do
        state.records[component]={owner=record.owner,offset=record.offset,size=#record.bytes,fnv1a=c.records[component].fnv1a}
    end
    states[spec.carrier]=state
    arm()
    local exact=true
    for _,ch in ipairs(state.changes)do
        if world.runtime.read(ch.owner.base+ch.offset,#ch.desired)~=ch.desired then exact=false end
    end
    local parts={}
    for _,key in ipairs({'name','icon'})do if borrowed[key]then parts[#parts+1]=key..': '..borrowed[key]end end
    log(('APPLIED (%s): %s is its own VARIANT for this mission: %d writes (presentation%s%s); each record had one owner '
        ..'and its exact native bytes; read back %s; non-target bytes unchanged %s, protection restored %s%s')
        :format(tostring(spec.label or spec.carrier),spec.carrier,report.writes,round and('; round '..tostring(round.label)
        ..' (projectile '..round.type..', its package resident)')or'',spec.model and('; model '..models.label(spec.model)
        ..' (unit '..models.unit_hex(spec.model)..', loaded, derived on this build from the reviewed unit)')or'',
        tostring(exact),tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored),
        #parts>0 and('; borrowed '..table.concat(parts,'; '))or''))
    if not exact then
        local back,bcode,breason=restore_body(false,spec.carrier)
        return nil,'VERIFY_FAILED','a converted member does not read back'..(back and'; restored'or('; restore '
            ..tostring(bcode)..': '..tostring(breason)))
    end
    return {status='applied',carrier=spec.carrier,donor=spec.carrier,level='variant',variant=true,writes=report.writes,
        borrowed=borrowed,round=state.round,model=state.model,verify={exact=exact,
        nonTarget=report.non_target_bytes_unchanged,protection=report.protection_restored}}
end

-- The restore (inside a coroutine; now = from restore_now or the finalizer).
function restore_body(now,carrier)
    local state=states[carrier]
    if not held(state)then return nil,'NOT_APPLIED','the carrier is its own weapon: nothing to restore'end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local changes={}
    for index=#state.changes,1,-1 do
        local ch=state.changes[index]
        local now_bytes=world.runtime.read(ch.owner.base+ch.offset,#ch.desired)
        if now_bytes~=ch.desired then
            return nil,'CONFLICT',carrier..' '..ch.label..' no longer holds what the clone wrote (another writer owns it): '
                ..'not restored'
        end
        changes[#changes+1]={label=ch.label..' (restore)',owner=ch.owner,offset=ch.offset,expected=ch.desired,
            desired=ch.before,before=ch.desired,already_desired=false,identity={component=ch.component,
            component_type='weapon clone host',unique_owner=true,owner_count=1},chain={}}
    end
    local snapshots={}
    for _,r in pairs(state.records)do
        local bytes=world.runtime.read(r.owner.base+r.offset,r.size)
        if not bytes or#bytes~=r.size then return nil,'UNAVAILABLE','the '..carrier..' records are unreadable'end
        snapshots[#snapshots+1]={owner=r.owner,offset=r.offset,bytes=bytes}
    end
    table.sort(snapshots,function(a,x)return a.offset<x.offset end)
    local report={status='APPLIED',writes=0,non_target_bytes_unchanged=true,protection_restored=true}
    if#changes>0 then
        report=transaction.apply(world.runtime,{changes=changes,snapshots=snapshots})
        metrics.count('weapon_clone.transactions')
        if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    end
    state.restored=true
    disarm()
    local exact=true
    for component,r in pairs(state.records)do
        local bytes=world.runtime.read(r.owner.base+r.offset,r.size)
        if not bytes or fnv1a(bytes)~=r.fnv1a then exact=false;log('RESTORE: '..carrier..' '..component..' differs')end
    end
    log(('RESTORED%s: %s is its own weapon again: %d writes; every record its native bytes: %s; non-target bytes unchanged '
        ..'%s, protection restored %s'):format(now and' (in one tick)'or'',carrier,report.writes,tostring(exact),
        tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored)))
    return {status='restored',carrier=carrier,writes=report.writes,verify={exact=exact}}
end

-- Restores as a job: 'restored' (or 'refused' with code and reason).
function M.restore(callback,carrier)
    restoring[carrier]=job(function()return restore_body(false,carrier)end,callback)
    return restoring[carrier]
end
-- Restores within this tick (the loadout-screen boundary): a result table, or nil and code, reason.
function M.restore_now(carrier)
    local pending=restoring[carrier]
    if pending and pending.status=='pending'then pending.watch.cancel();pending.status='superseded'end
    restoring[carrier]=nil
    return run(function()return restore_body(true,carrier)end,true)
end
function M.applied(carrier)
    if carrier~=nil then return held(states[carrier])end
    for _,s in pairs(states)do if held(s)then return true end end
    return false
end
function M.applied_carriers()
    local out={}
    for carrier,s in pairs(states)do if held(s)then out[#out+1]=carrier end end
    table.sort(out)
    return out
end
function M.state(carrier)return states[carrier]end
-- Read-only, within this call: whether a clone host's records are where the research found them (one owner each, the
-- game's type tables pointing at them) and hold exactly their native bytes. {native, records = n}, or nil, code, reason.
function M.inspect(world,carrier,variant)
    local c=facts(carrier,variant)
    if not c then return nil,'UNREVIEWED',tostring(carrier)..' is not a reviewed clone host'end
    return run(function()
        local records,code,reason=capture(world,carrier,variant)
        if not records then return nil,code,reason end
        local native,n=true,0
        for component,r in pairs(c.records)do
            n=n+1
            if fnv1a(records[component].bytes)~=r.fnv1a then native=false end
        end
        return {native=native,records=n}
    end,true)
end
function M.finalize_for_tests()finalize()end
function M.reset_for_tests()states,restoring,proven,proven_rounds,proven_unit={},{},{},{},{};disarm()end
return M
