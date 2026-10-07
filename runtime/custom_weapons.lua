-- Per-instance weapon configuration of ONE exact entity a custom stratagem call delivered (development;
-- docs/custom-stratagem-api.md, "Weapon modifications"). Not exported by api/hd2.lua: the custom stratagem payload
-- families reach it (a delivered support weapon, a sentry).
--
-- The mechanisms are the ones live-proven on the Pelican's chin turret (runtime/pelican_weapon.lua, research
-- "turretWeapon", "gatling", "ammo", "spread", "aim"), applied to any entity that wields a projectile weapon itself or
-- is wielded, never to a type:
--   * projectile: the game's own ProjectileWeapon copy routine (0x61AF10, an unmodified copy of the entity's type
--     record for this entity only; skipped when the entity already has its own copy), then the copy's projectile type
--     (+0). A magazine weapon fires its chambered round and re-derives it after every shot, from its magazine pattern
--     when one is on (the Gatling Sentry's 148, 148, 148, 242, 148) or from the resolved ProjectileWeapon +0: so its
--     own magazine copy (the magazine copy routine 0x770B10) gets the pattern off, its own magazine record the pattern
--     mode and length 0 and the chambered round the new type, the values the game derives from such a magazine;
--   * rpm: the copy's rate slot (+0x8: a later re-derivation by the game gives the same rate) and the entity's own
--     current RPM, times the factor the game applied to it at creation (1, or 0.9 under mission modifier 0x33). Not on
--     a weapon whose type binds a rate-of-fire selector (it rewrites the rate); a weapon without one keeps its Y slot
--     (its X and Z rates are dormant);
--   * spread: its own WeaponData instance record's widths (+0x58, +0x5C: milliradians), its distribution word kept;
--   * ammo: its own magazine copy's capacity (+0x88) and both round counts, filled as the game fills a magazine
--     (capacity - 1 and one chambered); the rounds are an 11-bit network field, so at most 2047;
--   * recoil = 'zero': its own WeaponData instance's aim recoil (block B) to 0 sideways and 0 up a shot;
--   * sound (a sentry's weapon only; 2026-10-07): a weapon firing-sound catalogue name (runtime/weapon_sounds.lua). Its
--     own ProjectileWeapon copy's firing-sound block (+0xED, +0xF0.., +0x210.., +0x22C) and its own instance record's
--     MIDI source (+0x38) from exactly its type's own catalogued sound to that sound's: the values the game derives
--     for a weapon whose record names that sound (research pelican-maelstrom-sound, weapon-sounds; the mechanism the
--     Pelican gun's sound uses), in the same transaction as the round, while it is quiet; the sound's pins proven and
--     its bank resident (a package that lists it). Every compatible machine applies it to its own copy.
-- Every write is one guarded transaction on that entity's own records, read back; the entity's type records
-- (ProjectileWeapon, magazine, WeaponData) are compared whole before and after. Refused, with nothing called or
-- written, unless: the adapter can call the copy routines; inside the Runtime's own update; the pins and both routines'
-- exact entry bytes prove (runtime/pelican_weapon.lua prove); a mission, as the solo host; the entity is associated with
-- a custom stratagem call (runtime/spawned_instances.lua) and alive; each value is its type's (nothing configured it
-- before); room for a copy in the manager (the routines do not check their capacity).
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local scheduler=require('hd2runtime/runtime/scheduler')
local instances=require('hd2runtime/runtime/spawned_instances')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local pelicans=require('hd2runtime/runtime/pelicans')
local gatling=require('hd2runtime/runtime/pelican_gatling')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/pelican')
local M={}
local G,TW=D.gatling,D.turretWeapon
local MC,AM=G.magazineCopy,D.ammo
local WD,SPD=D.aim.weaponData,D.spread
M.AMMO_MAX=D.ammo.roundsMax
M.RPM={30,3000}
M.SPREAD_MAX=100
M.KEYS={projectile=true,rpm=true,spread=true,ammo=true,recoil=true,sound=true}
local WS=require('hd2runtime/runtime/weapon_sounds')
local SD=D.sound

local function log(text)log_module.emit('[HD2Runtime] custom weapon '..text)end
local function u32(n)return b.encode(n%4294967296,'u32')end
local function f32(raw,o)local ok,v=pcall(b.value,raw,o,'f32');return ok and v or nil end
local function single(v)return b.value(b.encode(v,'f32'),0,'f32')end
local function map_at(at)return {keys=at,capacity=at+8,empty=at+0xC,multiplier=at+0x10}end

-- Validates a modification table (a mod's data): nil when valid, else the reason. The values a ModBuilder offers:
-- projectile (a ProjectileInfo type, 1..65535), rpm (30..3000), spread (0 < mrad <= 100), ammo (rounds, 1..2047),
-- recoil ('zero').
function M.check(spec)
    if type(spec)~='table'then return'must be a table'end
    for key in pairs(spec)do if not M.KEYS[key]then return'unsupported weapon modification: '..tostring(key)end end
    local p=spec.projectile
    if p~=nil and not(type(p)=='number'and p>0 and p<65536 and p%1==0)then return'projectile must be a projectile type'end
    local r=spec.rpm
    if r~=nil and not(type(r)=='number'and r>=M.RPM[1]and r<=M.RPM[2])then
        return('rpm must be %d..%d'):format(M.RPM[1],M.RPM[2])
    end
    local s=spec.spread
    if s~=nil and not(type(s)=='number'and s==s and s>0 and s<=M.SPREAD_MAX)then
        return('spread must be more than 0 and at most %d mrad'):format(M.SPREAD_MAX)
    end
    local a=spec.ammo
    if a~=nil and not(type(a)=='number'and a>=1 and a<=M.AMMO_MAX and a%1==0)then
        return('ammo must be 1..%d rounds (an 11-bit network field)'):format(M.AMMO_MAX)
    end
    if spec.recoil~=nil and spec.recoil~='zero'then return"recoil must be 'zero'"end
    if spec.sound~=nil then
        local _,e=WS.resolve(spec.sound)
        if not e then return'sound must be a firing sound of the catalogue ('..WS.hint()..')'end
        if e.own then return'sound '..tostring(spec.sound)..' is the Pelican chin gun\'s own'end
    end
    return nil
end

-- The entity's own world record, reached through its ProjectileWeapon index (research/custom-payloads weaponHandle: the
-- manager's handles +0x68, the record every component handle points at: +0 resource, +8 entity, +0x14 flags): handle,
-- raw (0x18), resource (hex, as event_world.entity_type); or nil. Any projectile weapon, with or without an AI.
local WH=require('hd2runtime/domains/custom_payloads').weaponHandle
local WF=require('hd2runtime/domains/custom_payloads').weaponFunction
local function weapon_handle(world,entity)
    local pw=world.view.pointer(world.game+WH.global)
    local index=pw and pw~=0 and pelicans.index_of(world,pw,map_at(TW.projectileWeapon.map),entity)
    local handles=index and world.view.pointer(pw+WH.handles)
    local handle=handles and handles~=0 and world.view.pointer(handles+index*8)
    local raw=handle and handle~=0 and world.view.read(handle,0x18)
    if not(raw and b.u32(raw,WH.handleEntity)==entity)then return nil end
    return handle,raw,string.format('%08X%08X',b.u32(raw,WH.handleResource+4),b.u32(raw,WH.handleResource))
end
M.weapon_handle=weapon_handle
-- The entity's WeaponData instance record: raw (through the recoil block and the multipliers), address; or nil.
local function weapon_data(world,entity)
    local mgr=world.view.pointer(world.game+WD.global)
    local index=mgr and mgr~=0 and pelicans.index_of(world,mgr,map_at(WD.map),entity)
    local records=index and world.view.pointer(mgr+WD.records)
    if not(records and records~=0)then return nil end
    local at=records+index*WD.stride
    local raw=world.view.read(at,math.max(SPD.multipliers[2]+4,WD.recoilB+WD.recoilSize))
    return raw,at
end
-- The magazine manager's copy count and capacity, and the entity's own magazine record, entry and copy (read-only).
local function magazine_state(world,entity)
    local MG=TW.magazine
    local manager=world.view.pointer(world.game+MG.global)
    if not manager or manager==0 then return nil end
    local count=world.view.read(manager+MC.count,4)
    local capacity=world.view.read(manager+MC.capacity,4)
    local ri=pelicans.index_of(world,manager,map_at(MG.map),entity)
    local records=ri and world.view.pointer(manager+MG.records)
    local entries=ri and world.view.pointer(manager+AM.entries)
    local ci=pelicans.index_of(world,manager,map_at(MC.map),entity)
    local copies=ci and world.view.pointer(manager+MC.records)
    return {manager=manager,count=count and b.u32(count,0),capacity=capacity and b.u32(capacity,0),
        record=records and records~=0 and records+ri*MG.stride or nil,
        entry=entries and entries~=0 and entries+ri*AM.entryStride or nil,
        copy=copies and copies~=0 and copies+ci*MC.stride or nil}
end
-- The entity's ProjectileWeapon copy, when it has one: address, raw (the whole record).
local function pw_copy(world,entity)
    local PW=TW.projectileWeapon
    local pw=world.view.pointer(world.game+PW.global)
    local ci=pw and pw~=0 and pelicans.index_of(world,pw,map_at(PW.copies),entity)
    local copies=ci and world.view.pointer(pw+PW.copyRecords)
    if not(copies and copies~=0)then return nil end
    local at=copies+ci*PW.copyStride
    return at,world.view.read(at,PW.copyStride)
end

-- What the entity's weapon is now, read-only: {resource, weapon (pelicans.weapon_config), magazine (rounds, working,
-- chambered, capacity, from), spread {x, y, word}, recoil {x, y}, types {pw, magazine, weapon_data: its type records}}, or
-- nil and why.
function M.state(world,entity)
    local handle,_,resource=weapon_handle(world,entity)
    if not handle then return nil,'the entity has no projectile weapon (no ProjectileWeapon world record)'end
    local w=pelicans.weapon_config(world,entity)
    if not w then return nil,'the entity has no projectile weapon'end
    local out={entity=entity,resource=resource,weapon=w,types={pw=gatling.type_record(world,G.pwTypes,resource),
        magazine=gatling.type_record(world,G.magazineTypes,resource),
        weapon_data=gatling.type_record(world,WD.types,resource)}}
    local mag=magazine_state(world,entity)
    local rec=mag and mag.record and world.view.read(mag.record,TW.magazine.stride)
    local ent=mag and mag.entry and world.view.read(mag.entry,AM.entryStride)
    if rec and ent then
        local resolved=mag.copy and world.view.read(mag.copy,MC.stride)or out.types.magazine
        out.magazine={rounds=b.value(ent,AM.entryRounds,'i32'),working=b.value(rec,TW.magazine.rounds,'i32'),
            chambered=b.u32(rec,TW.magazine.chambered),pattern=b.u32(rec,TW.magazine.pattern),
            length=b.u32(rec,TW.magazine.patternLength),chamber_empty=ent:byte(AM.entryChamberEmpty+1),
            capacity=resolved and b.u32(resolved,AM.capacity),from=mag.copy and'copy'or'type'}
    end
    local raw=weapon_data(world,entity)
    if raw then
        out.spread={x=f32(raw,SPD.instance),y=f32(raw,SPD.instance+4),word=b.u32(raw,SPD.word),
            multipliers={x=f32(raw,SPD.multipliers[1]),y=f32(raw,SPD.multipliers[2])}}
        out.recoil={x=f32(raw,WD.recoilB),y=f32(raw,WD.recoilB+4)}
    end
    return out
end
function M.text(s)
    if not s then return'(unreadable)'end
    local w,m=s.weapon,s.magazine
    return ('projectile %s (%s), current RPM %s, magazine %s rounds of %s (%s; chambered %s, pattern %s), spread %s x %s '
        ..'mrad, recoil %s/%s'):format(tostring(w.copy and w.copy.projectileType or(s.types.pw and b.u32(s.types.pw,0))),
        w.copy and'its own record'or'its type\'s',tostring(w.currentRpm),tostring(m and m.rounds),
        tostring(m and m.capacity),tostring(m and m.from),tostring(m and m.chambered),tostring(m and m.pattern),
        tostring(s.spread and s.spread.x),tostring(s.spread and s.spread.y),tostring(s.recoil and s.recoil.x),
        tostring(s.recoil and s.recoil.y))
end

local configured={}
function M.configured(entity)return configured[entity]end

local function change(list,label,owner,base,raw,at,desired)
    list[#list+1]={label=label,owner=owner,offset=base+at-owner.base,expected=raw:sub(at+1,at+#desired),desired=desired,
        before=raw:sub(at+1,at+#desired),already_desired=false,
        identity={component='Weapon',component_type='native',unique_owner=true,owner_count=1},chain={}}
end

-- M.configure(world, entity, spec, label, opts): spec as M.check. opts.role (custom multiplayer, EXPERIMENTAL; docs/
-- custom-stratagem-api.md "Several players"):
--   * nil / 'own': the host's own call (the development rule: the host only);
--   * 'client': this client's OWN call (a family the orchestrator runs on clients, the client-write proof enabled);
--   * 'published': another machine's call, its entity correlated through its published network id by
--     runtime/custom_mp_items.lua (the caller verified, its synced picks selecting it).
-- Whatever the role, the machine that CREATED the entity (its world record's created-here flag) configures it whole;
-- every other machine mirrors on its OWN copy only what each machine reads from its own data for its own shots (live:
-- each machine fires a turret's rounds from its own copy, docs/research/runtime-peer-messaging-F5FEE03DCFDB.md
-- section 15): the round (its own ProjectileWeapon copy and, for a magazine weapon, its own magazine copy with the
-- pattern off and the chambered round), the spread and the aim recoil. The rate and the ammunition are the creator's,
-- which the game replicates (its current RPM entry, the 11-bit round counts): never written on a copy.
-- What the host guard protected, a write on an entity this machine does not simulate, is exactly what the copy rule
-- leaves out. Returns {entity, spec (what was written), writes, verify = {...}, verified, before, after, mirror} or nil,
-- code, reason (nothing called or written).
function M.configure(world,entity,spec,label,opts)
    label=tostring(label or'?')
    opts=opts or{}
    local role=opts.role or'own'
    local function refuse(code,reason)
        log(('REFUSED (%s): entity %s: %s: %s (it stays as it is)'):format(label,tostring(entity),code,reason))
        metrics.count('custom_weapons.refused')
        return nil,code,reason
    end
    local invalid=M.check(spec)
    if invalid then return refuse('INVALID',invalid)end
    if next(spec)==nil then return refuse('INVALID','nothing to modify')end
    local runtime=world.runtime
    if(spec.projectile~=nil or spec.rpm~=nil or spec.sound~=nil)and not runtime.native_weapon_copy then
        return refuse('UNAVAILABLE','this Runtime adapter cannot call game functions')
    end
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    local ok,why=require('hd2runtime/runtime/pelican_weapon').prove(world)
    if not ok then return refuse('UNSUPPORTED_BUILD',tostring(why))end
    ok,why=require('hd2runtime/runtime/custom_eagles').prove(world)
    if not ok then return refuse('UNSUPPORTED_BUILD',tostring(why))end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return refuse('NOT_IN_MISSION','in a mission only')end
    local mp=require('hd2runtime/runtime/multiplayer')
    if role~='own'and role~='client'and role~='published'then return refuse('INVALID','unknown role '..tostring(role))end
    if role=='own'and game.host~=true then return refuse('NOT_HOST','development: host only')end
    if role=='client'and not mp.client_proof()then
        return refuse('NOT_HOST','a client\'s own call: the client-write proof is not enabled in this mission')
    end
    local record_list,rcode,rreason=slots.local_record(world)
    if not record_list then return refuse(rcode,rreason)end
    -- The entity's own copies and records; peers keep their own (an entity of a custom stratagem call accepts it, and so
    -- does another machine's published call item).
    local scode,swhy=mp.solo_guard(record_list.records,role=='published'or mp.entity_allowed(entity),
        'its own copies are not sent to peers')
    if scode then return refuse(scode,swhy)end
    if role~='published'and not instances.lookup(entity)then
        return refuse('NOT_ASSOCIATED','the entity is not associated with a custom stratagem call (never a vanilla one)')
    end
    if role=='published'and opts.published~=true then
        return refuse('NOT_PUBLISHED','another machine\'s entity is configured only as a published call item')
    end
    if world_module.entity_exists(world,entity)~=true then return refuse('GONE','the entity no longer exists')end
    local before,swhy=M.state(world,entity)
    if not before then return refuse('NOT_A_WEAPON',tostring(swhy))end
    if not(before.types.pw and before.types.magazine and before.types.weapon_data)then
        return refuse('UNAVAILABLE','its type records are unreadable')
    end
    local w=before.weapon
    local m=before.magazine
    local record,record_raw=weapon_handle(world,entity)
    if not record then return refuse('UNAVAILABLE','its world record is unreadable')end
    local magazine_weapon=w.path=='magazine'and m~=nil
    -- The creator configures it whole; any other machine mirrors the round, spread and recoil on its own copy.
    local created_here=record_raw~=nil and b.u32(record_raw,WH.handleFlags)%2==WH.createdHere
    -- (The host's own call keeps the development rule exactly: only its magazine needs the created-here flag.)
    local mirror=role~='own'and not created_here
    if mirror then
        local kept={}
        for _,key in ipairs({'projectile','spread','recoil','sound'})do kept[key]=spec[key]end
        if next(kept)==nil then
            return refuse('NOT_CREATED_HERE','its rate and magazine are its creator\'s (replicated): nothing to mirror here')
        end
        spec=kept
    end
    -- The firing sound: its type's own catalogued sound (the writes' source), the sound's pins, its bank resident.
    local sound
    if spec.sound~=nil then
        local canonical,target=WS.resolve(spec.sound)
        local base_name,base
        for name,e in pairs(WS.SOUNDS)do
            if e.resource==before.resource and not e.own and(not base_name or name<base_name)then base_name,base=name,e end
        end
        if not base then return refuse('SOUND_UNEXPECTED','its weapon type has no catalogued firing sound')end
        for _,pin in ipairs(WS.PINS)do
            if not world.view.proves(world.game+pin.rva,pin.hex)then
                return refuse('UNSUPPORTED_BUILD',('game+%X changed (%s)'):format(pin.rva,pin.label))
            end
        end
        local pwm=require('hd2runtime/runtime/pelican_weapon')
        local package,acode,areason=pwm.sound_resident(world,canonical)
        if not package then return refuse(acode,areason)end
        local st=pwm.sound_state(world,entity,before.resource)
        if not st then return refuse('UNAVAILABLE','its firing sound is unreadable')end
        if st.block~=b.unhex(base.blockBytes)or st.instance.midi~=base.midi then
            return refuse('SOUND_UNEXPECTED',('its firing sound is not its type\'s own (%s)'):format(base_name))
        end
        if not st.instance.quiet then return refuse('NOT_QUIET','it is firing (its trigger, fire state or MIDI notes)')end
        if canonical~=base_name then
            sound={name=canonical,target=target,base=base,base_name=base_name,package=package}
        end
    end
    local needs_pw=spec.projectile~=nil or spec.rpm~=nil or sound~=nil
    -- The rate: the factor the game applied at creation (current RPM over its type's Y slot), 1 or the seed factor.
    local factor
    if spec.rpm then
        local type_rpm=f32(before.types.pw,TW.projectileWeapon.rpmSlots+4)
        if not(type_rpm and type_rpm>0 and w.currentRpm)then return refuse('RATE_UNEXPECTED','its rate is unreadable')end
        -- Only a weapon whose own type binds the rate-of-fire selector to an input cycles its rate slots (research
        -- weapon-functions; custom-payloads weaponFunction): refused. Without one (a sentry has none) its Y slot is its
        -- rate and its X and Z rates are dormant (the MG-43 Sentry's 630 / 630 / 900).
        local T=before.types.weapon_data
        local left,right=b.u32(T,WF.left),b.u32(T,WF.right)
        if left==WF.rateOfFire or right==WF.rateOfFire then
            return refuse('RPM_SELECTOR','its type binds a rate-of-fire selector, which rewrites its rate')
        end
        for _,f in ipairs({1,D.rateSeed.factor})do
            if math.abs(w.currentRpm-single(type_rpm*f))<0.01 then factor=f end
        end
        if not factor then
            return refuse('RATE_UNEXPECTED',('it runs %.2f RPM, not its type\'s %.0f x a factor the game gives'):format(
                w.currentRpm,type_rpm))
        end
    end
    -- The magazine: own copy for the ammunition or to turn a pattern off.
    local pattern_off=spec.projectile~=nil and magazine_weapon and m.pattern~=0
    local needs_mag_copy=spec.ammo~=nil or pattern_off
    if needs_mag_copy and not runtime.native_magazine_copy then
        return refuse('UNAVAILABLE','this Runtime adapter cannot call game functions')
    end
    if spec.ammo~=nil or spec.projectile~=nil and magazine_weapon then
        if not magazine_weapon then return refuse('NOT_A_MAGAZINE_WEAPON','it has no magazine')end
        if m.from~='type'then return refuse('ALREADY_CONFIGURED','it already has its own magazine record')end
        if m.capacity~=b.u32(before.types.magazine,AM.capacity)then return refuse('MAGAZINE_UNEXPECTED','its capacity is not its type\'s')end
    end
    if spec.ammo~=nil then
        if m.rounds~=m.working then return refuse('MAGAZINE_UNEXPECTED',('its two round counts differ (%d, %d)'):format(
            m.rounds,m.working))end
        if m.chambered==0 or m.chamber_empty~=0 then return refuse('MAGAZINE_UNEXPECTED','no round is chambered')end
        if not(record_raw and b.u32(record_raw,WH.handleFlags)%2==WH.createdHere)then
            return refuse('NOT_HOST','it was not created here')
        end
    end
    if spec.spread~=nil or spec.recoil~=nil then
        if not before.spread then return refuse('UNAVAILABLE','its WeaponData is unreadable')end
        local T=before.types.weapon_data
        if spec.spread~=nil then
            local tx,ty,tw=f32(T,SPD.type),f32(T,SPD.type+4),b.u32(T,SPD.typeWord)
            local s=before.spread
            if s.word~=tw or s.x~=single(tx*s.multipliers.x)or s.y~=single(ty*s.multipliers.y)then
                return refuse('SPREAD_UNEXPECTED','its spread is not its type\'s')
            end
        end
        if spec.recoil~=nil then
            local raw=weapon_data(world,entity)
            if raw:sub(WD.recoilB+1,WD.recoilB+WD.recoilSize)~=T:sub(WD.types.recoilB+1,WD.types.recoilB+WD.recoilSize)then
                return refuse('RECOIL_UNEXPECTED','its recoil is not its type\'s')
            end
        end
    end
    -- Room for the copies.
    local PW=TW.projectileWeapon
    local pw=world.view.pointer(world.game+PW.global)
    local copy_at,copy=pw_copy(world,entity)
    if needs_pw and not copy_at then
        local count=pw and world.view.read(pw+PW.copyCount,4)
        local capacity=pw and world.view.read(pw+G.copyCapacity,4)
        if not(count and capacity and b.u32(count,0)+1<b.u32(capacity,0))then
            return refuse('NO_CAPACITY','no room for a per-instance ProjectileWeapon copy')
        end
    end
    local mag=magazine_state(world,entity)
    if needs_mag_copy and not(mag and mag.record and mag.entry and mag.count and mag.capacity and mag.count+1<mag.capacity)
    then return refuse('NO_CAPACITY','no room for a per-instance magazine copy')end
    if spec.projectile~=nil then
        local row=world_module.projectile_row(world,spec.projectile)
        if not row or b.u32(row,0)~=spec.projectile then return refuse('UNKNOWN_PROJECTILE','no row for projectile '..spec.projectile)end
    end
    local shared_before=before.types
    log(('BEFORE (%s): entity %d (%s): %s'):format(label,entity,before.resource,M.text(before)))
    local writes,verify=0,{}
    -- 1. The ProjectileWeapon: its own copy, then the projectile and the rate.
    if needs_pw then
        if not copy_at then
            metrics.count('custom_weapons.native_calls')
            runtime.native_weapon_copy(world.game+G.copy.rva,pw,record)
            copy_at,copy=pw_copy(world,entity)
            if not copy_at then return refuse('COPY_FAILED','no per-instance ProjectileWeapon copy after the call')end
        end
        local copy_owner=pelicans.owner_of(world,copy_at,PW.copyStride)
        local current=world.view.pointer(pw+PW.current)
        local entry_at=current and current~=0 and current+w.index*PW.currentStride
        local entry=entry_at and world.view.read(entry_at,PW.currentStride)
        local entry_owner=entry_at and pelicans.owner_of(world,entry_at,PW.currentStride)
        if not(copy_owner and entry and entry_owner)then
            return refuse('NOT_PRIVATE','the copy or the current-RPM entry is not in private read-write memory')
        end
        local changes={}
        if spec.projectile~=nil then change(changes,'weapon.'..entity..'.projectile',copy_owner,copy_at,copy,PW.projectileType,
            u32(spec.projectile))end
        if spec.rpm~=nil then
            change(changes,'weapon.'..entity..'.rate_slot',copy_owner,copy_at,copy,PW.rpmSlots+4,b.encode(spec.rpm,'f32'))
            change(changes,'weapon.'..entity..'.current_rpm',entry_owner,entry_at,entry,PW.currentRpm,
                b.encode(single(spec.rpm*factor),'f32'))
        end
        local plan={snapshots={{owner=copy_owner,offset=copy_at-copy_owner.base,bytes=copy},
            {owner=entry_owner,offset=entry_at-entry_owner.base,bytes=entry}},changes=changes}
        if sound then
            -- Its own copy still holds its type's own sound, and it is quiet; then block by block, base -> target.
            local pwm=require('hd2runtime/runtime/pelican_weapon')
            local st=pwm.sound_state(world,entity,before.resource)
            local base_block,target_block=b.unhex(sound.base.blockBytes),b.unhex(sound.target.blockBytes)
            if not(st and st.from=='copy'and st.copy_at==copy_at and st.block==base_block)then
                return refuse('SOUND_UNEXPECTED','its own copy does not hold its type\'s own firing sound')
            end
            if not st.instance.quiet then return refuse('NOT_QUIET','it is firing (its trigger, fire state or MIDI notes)')end
            -- Field by field (a byte, or 4-byte words within a block), only where the two sounds differ.
            local cursor=0
            for _,blk in ipairs(SD.record.blocks)do
                local off,len=blk[1],blk[2]
                local step=len==1 and 1 or 4
                if len%step~=0 then return refuse('SOUND_UNEXPECTED','a firing-sound block is not whole words')end
                for k=0,len-step,step do
                    local to=target_block:sub(cursor+k+1,cursor+k+step)
                    if base_block:sub(cursor+k+1,cursor+k+step)~=to then
                        change(changes,('weapon.%d.sound_%X'):format(entity,off+k),copy_owner,copy_at,copy,off+k,to)
                    end
                end
                cursor=cursor+len
            end
            if sound.base.midi~=sound.target.midi then
                local inst=st.instance
                local inst_owner=pelicans.owner_of(world,inst.at,PW.instanceStride)
                if not inst_owner then return refuse('NOT_PRIVATE','its instance record is not in private read-write memory')end
                plan.snapshots[#plan.snapshots+1]={owner=inst_owner,offset=inst.at-inst_owner.base,bytes=inst.raw}
                change(changes,'weapon.'..entity..'.instance.sound_midi',inst_owner,inst.at,inst.raw,SD.instance.midi,
                    string.char(sound.target.midi))
            end
        end
        local report=transaction.apply(runtime,plan)
        metrics.count('custom_weapons.transactions')
        if report.status~='APPLIED'then return refuse('GUARD_REJECTED','the weapon writes were refused: '..tostring(report.reason))end
        writes=writes+report.writes
    end
    -- 2. The magazine: its own copy (pattern off, capacity), its record (pattern, chambered round, working count) and its
    -- entry (the authoritative count). A mirror: the pattern and the chambered round only (no ammo: the counts are the
    -- creator's, replicated).
    if spec.ammo~=nil or spec.projectile~=nil and magazine_weapon then
        if needs_mag_copy then
            metrics.count('custom_weapons.native_calls')
            runtime.native_magazine_copy(world.game+MC.rva,mag.manager,record)
            mag=magazine_state(world,entity)
            if not(mag and mag.copy)then return refuse('COPY_FAILED','no per-instance magazine copy after the call')end
        end
        local MG=TW.magazine
        local rec=world.view.read(mag.record,MG.stride)
        local ent=world.view.read(mag.entry,AM.entryStride)
        local mcopy=mag.copy and world.view.read(mag.copy,MC.stride)
        local rec_owner=rec and pelicans.owner_of(world,mag.record,MG.stride)
        local ent_owner=ent and pelicans.owner_of(world,mag.entry,AM.entryStride)
        local copy_owner=mcopy and pelicans.owner_of(world,mag.copy,MC.stride)
        if not(rec_owner and ent_owner and(not mag.copy or copy_owner))then
            return refuse('NOT_PRIVATE','its magazine is not in private read-write memory')
        end
        if mcopy and b.u32(mcopy,AM.capacity)~=b.u32(before.types.magazine,AM.capacity)then
            return refuse('GUARD_REJECTED','the magazine copy is not its type\'s')
        end
        local plan={snapshots={{owner=rec_owner,offset=mag.record-rec_owner.base,bytes=rec},
            {owner=ent_owner,offset=mag.entry-ent_owner.base,bytes=ent}},changes={}}
        if mcopy then plan.snapshots[3]={owner=copy_owner,offset=mag.copy-copy_owner.base,bytes=mcopy}end
        local ch=plan.changes
        if pattern_off then
            change(ch,'weapon.'..entity..'.magazine_copy.mode',copy_owner,mag.copy,mcopy,MC.mode,u32(0))
            change(ch,'weapon.'..entity..'.magazine.pattern',rec_owner,mag.record,rec,MG.pattern,u32(0))
            change(ch,'weapon.'..entity..'.magazine.pattern_length',rec_owner,mag.record,rec,MG.patternLength,u32(0))
        end
        if spec.projectile~=nil and b.u32(rec,MG.chambered)~=0 then
            change(ch,'weapon.'..entity..'.magazine.chambered',rec_owner,mag.record,rec,MG.chambered,u32(spec.projectile))
        end
        if spec.ammo~=nil then
            change(ch,'weapon.'..entity..'.magazine_copy.capacity',copy_owner,mag.copy,mcopy,AM.capacity,u32(spec.ammo))
            change(ch,'weapon.'..entity..'.magazine.working_rounds',rec_owner,mag.record,rec,MG.rounds,u32(spec.ammo-1))
            change(ch,'weapon.'..entity..'.magazine.rounds',ent_owner,mag.entry,ent,AM.entryRounds,u32(spec.ammo-1))
        end
        if#ch>0 then
            local report=transaction.apply(runtime,plan)
            metrics.count('custom_weapons.transactions')
            if report.status~='APPLIED'then
                return refuse('GUARD_REJECTED','the magazine writes were refused: '..tostring(report.reason))
            end
            writes=writes+report.writes
        end
    end
    -- 3. Its WeaponData: the spread widths and the aim recoil.
    if spec.spread~=nil or spec.recoil~=nil then
        local raw,at=weapon_data(world,entity)
        local owner=raw and pelicans.owner_of(world,at,WD.stride)
        if not owner then return refuse('NOT_PRIVATE','its WeaponData is not in private read-write memory')end
        local plan={snapshots={{owner=owner,offset=at-owner.base,bytes=raw}},changes={}}
        if spec.spread~=nil then
            change(plan.changes,'weapon.'..entity..'.spread_x',owner,at,raw,SPD.instance,b.encode(spec.spread,'f32'))
            change(plan.changes,'weapon.'..entity..'.spread_y',owner,at,raw,SPD.instance+4,b.encode(spec.spread,'f32'))
        end
        if spec.recoil=='zero'then
            change(plan.changes,'weapon.'..entity..'.recoil_x',owner,at,raw,WD.recoilB,b.encode(0,'f32'))
            change(plan.changes,'weapon.'..entity..'.recoil_y',owner,at,raw,WD.recoilB+4,b.encode(0,'f32'))
        end
        local report=transaction.apply(runtime,plan)
        metrics.count('custom_weapons.transactions')
        if report.status~='APPLIED'then return refuse('GUARD_REJECTED','the WeaponData writes were refused: '..tostring(report.reason))end
        writes=writes+report.writes
    end
    -- The read-back, and the shared type records unchanged.
    local after=M.state(world,entity)
    local aw,am=after and after.weapon,after and after.magazine
    if spec.projectile~=nil then
        verify.projectile=aw~=nil and aw.copy~=nil and aw.copy.projectileType==spec.projectile
        if magazine_weapon then
            verify.magazine=am~=nil and am.pattern==0 and(am.chambered==0 or am.chambered==spec.projectile)
        end
    end
    if spec.rpm~=nil then verify.rpm=aw~=nil and aw.currentRpm==single(spec.rpm*factor)end
    if spec.ammo~=nil then
        verify.ammo=am~=nil and am.from=='copy'and am.capacity==spec.ammo and am.rounds==spec.ammo-1
            and am.working==spec.ammo-1
    end
    if spec.spread~=nil then
        verify.spread=after~=nil and after.spread~=nil and after.spread.x==single(spec.spread)and after.spread.y==single(spec.spread)
    end
    if spec.recoil~=nil then verify.recoil=after~=nil and after.recoil~=nil and after.recoil.x==0 and after.recoil.y==0 end
    if sound then
        local st=require('hd2runtime/runtime/pelican_weapon').sound_state(world,entity,before.resource)
        verify.sound=st~=nil and st.from=='copy'and st.block==b.unhex(sound.target.blockBytes)
            and st.instance.midi==sound.target.midi
    end
    local now_types={pw=gatling.type_record(world,G.pwTypes,before.resource),
        magazine=gatling.type_record(world,G.magazineTypes,before.resource),
        weapon_data=gatling.type_record(world,WD.types,before.resource)}
    verify.shared=now_types.pw==shared_before.pw and now_types.magazine==shared_before.magazine
        and now_types.weapon_data==shared_before.weapon_data
    local verified=true
    for _,v in pairs(verify)do if v~=true then verified=false end end
    configured[entity]={spec=spec,label=label}
    local parts={}
    for _,key in ipairs({'projectile','rpm','spread','ammo','recoil','sound'})do
        if spec[key]~=nil then parts[#parts+1]=key..' '..tostring(spec[key])..(verify[key]==false and' (NOT read back)'or'')end
    end
    if sound then
        parts[#parts+1]=('its firing sound %s -> %s (%s; bank %s, resident through %s)'):format(sound.base_name,sound.name,
            require('hd2runtime/runtime/pelican_weapon').sound_events(sound.target),sound.target.bank.name,
            sound.package.label)
    end
    log(('%s (%s): entity %d (%s): %s; %d writes on its own records; verified %s; its type records unchanged %s; '
        ..'every other %s stays vanilla. AFTER: %s'):format(mirror and'MIRRORED (another machine created it: the round, '
        ..'spread and recoil on this machine\'s own copy)'or'CONFIGURED',label,entity,before.resource,
        table.concat(parts,', '),writes,tostring(verified),tostring(verify.shared),before.resource,M.text(after)))
    return {entity=entity,spec=spec,writes=writes,verify=verify,verified=verified,before=before,after=after,
        mirror=mirror}
end
-- Whether a support weapon's own type binds the rate-of-fire selector (its catalogued fire_rate.modes field is
-- selector-bound: the MG-43 Machine Gun, the MG-206, the M-105): the game builds each weapon's rate record from the
-- type's three slots and the selector re-reads that record (research weapon-functions; game.dll 0x6117C0, 0x617960),
-- so a per-call rpm is refused (RPM_SELECTOR at delivery, and at registration). Its modes are fire_rate.modes'.
function M.binds_rate_selector(name)
    local w=type(name)=='string'and require('hd2runtime/domains/support_weapon_authoring').weapons[name]
    for _,f in ipairs(w and w.fields or{})do
        if f.semanticFieldId=='fire_rate.modes'and f.selectorBound==true then return true end
    end
    return false
end
function M.reset_for_tests()configured={}end
return M
