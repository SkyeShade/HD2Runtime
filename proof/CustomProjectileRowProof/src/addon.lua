local hd2=require('mods/skyeshade/hd2runtime')
-- Development proof for Runtime-owned custom projectile rows (docs/custom-projectile-rows.md). NOT a public API: it
-- calls Runtime internals (runtime/custom_projectiles.lua, api/actions.lua, runtime/event_world.lua) that may change
-- without notice. Host only, in a mission.
--
-- Each custom projectile (custom_projectiles.DEVELOPMENT_VARIANTS) is a byte-for-byte clone of the LAS-58 Talon row
-- (type 144) in a block the Runtime owns, with one component (or all of them) taken from a donor projectile: the
-- component copies exactly the members its descriptor owns. It is fired through the game's native SpawnProjectile.
-- Row 144 itself is never written.
--
--   F7   visual only: the PLAS-1 Scorcher's spawn particle effects
--   F5   damage only: the RS-422 Railgun's direct-hit DamageInfo
--   F6   ballistics only: the GL-21 Grenade Launcher's flight (100 m/s, gravity 1, drag 1.2: a visible lob)
--   F10  impact explosion only: the R-36 Eruptor's shell blast
--   F11  all four together
--   F8   a vanilla LAS-58 Talon bolt the same way (hd2.projectiles.spawn), for comparison
--   F9   verify: every vanilla projectile row, and the table entries just outside it, byte-identical to the moment
--        the mission started, and every custom row unchanged since its definition
--
-- Every shot leaves from your weapon along its aim (see launch() below).
--
-- What to check is listed in docs/custom-projectile-rows.md#live-test.
local ok_custom,custom=pcall(require,'hd2runtime/runtime/custom_projectiles')
assert(ok_custom,'CustomProjectileRowProof needs an HD2Runtime build with runtime/custom_projectiles (v0.29 '
    ..'development build)')
local actions=require('hd2runtime/api/actions')
local world_module=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local natives=require('hd2runtime/domains/event_natives')
local mod=hd2.mod()
local VARIANTS={{key='F7',id='dev/talon_visual'},{key='F5',id='dev/talon_damage'},
    {key='F6',id='dev/talon_ballistics'},{key='F10',id='dev/talon_impact'},{key='F11',id='dev/talon_combined'}}
local specs={}
for _,spec in ipairs(custom.DEVELOPMENT_VARIANTS)do specs[spec.id]=spec end
local definitions,baseline={},nil

local function define(id)
    if definitions[id]then return definitions[id]end
    local def,code,reason=custom.define(assert(specs[id],id))
    if not def then
        mod:log('custom projectile '..id..' not defined: '..tostring(code)..': '..tostring(reason))
        return nil
    end
    definitions[id]=def
    mod:log('defined: '..custom.line(def))
    return def
end
-- "visual from PLAS-1 Scorcher + damage from RS-422 Railgun": the components that differ from the base.
local function components_of(def)
    local parts={}
    for _,summary in ipairs(def.components or{})do
        parts[#parts+1]=summary.id..' from '..tostring(summary.weapon)..(summary.differs and''or' (same as the base)')
    end
    return table.concat(parts,' + ')
end
-- Every vanilla row (types 1..350) plus the table entries 0 and 351 (a new id would appear there), as read now.
local function table_state()
    local world,why=world_module.open()
    if not world then return nil,why end
    local parts={}
    for kind=1,natives.projectile.typeCount-1 do
        parts[kind]=world_module.projectile_row(world,kind)or'<none>'
    end
    local edges=world.view.read(world.game+natives.projectile.settingsTable,8)..
        (world.view.read(world.game+natives.projectile.settingsTable+natives.projectile.typeCount*8,8)or'')
    return {rows=parts,edges=edges}
end

-- The local avatar, followed across the mission: the game announces a mission before your Helldiver has landed, and
-- a death, reinforcement or mission change replaces it. Definitions do not depend on it and stay ready throughout;
-- only firing needs the avatar's pose.
local AVATAR_POLL,WAIT_LOG_SECONDS=0.5,10
local avatar={state='idle',entity=nil,waited=0,since_log=0,warned=nil}

-- The local avatar's entity and root pose, or nil and the step that failed. The player list (the network-id route
-- hd2.local_player() uses, with no record limit) comes first; handles.local_avatar, the one the action layer uses
-- (the same list first, then the owned health records), is the fallback. action_ready tells whether it resolves this
-- avatar too: a spawn is refused with NO_LOCAL_AVATAR while it does not.
local function resolve_avatar()
    local world,why=world_module.open()
    if not world then return nil,'the game world is not readable: '..tostring(why)end
    local id,route,reason
    local me=hd2.local_player()
    if me then
        local entity
        entity,reason=me:avatar()
        if entity then id,route=entity.id,'player list'end
    else
        reason='no local player in the player list'
    end
    local scanned=handles.local_avatar(world)
    if not id and scanned then id,route=scanned.id,'owned health records'end
    if not id then return nil,tostring(reason or'no local avatar')end
    local state=world_module.entity_state(world,id)
    if not state then return nil,'avatar entity '..id..' has no health record'end
    if state.life>=2 then return nil,'avatar entity '..id..' is dead'end
    local body=world_module.unit_pose(world,state.descriptor.unit)
    if not body then
        return nil,'avatar entity '..id..' (unit '..tostring(state.descriptor.unit)..') has no readable pose'
    end
    return {world=world,id=id,route=route,body=body,action_ready=scanned~=nil and scanned.id==id}
end

local function available(found,how)
    local previous=avatar.entity
    avatar.state,avatar.entity,avatar.waited,avatar.since_log='available',found.id,0,0
    local text=how=='restored'and previous and previous~=found.id and('avatar restored: entity '..found.id
        ..' replaces entity '..previous)or('avatar '..(how=='restored'and'restored'or'became available')
        ..': entity '..found.id)
    mod:log(text..' (via the '..found.route..'); F5 F6 F7 F8 F10 F11 ready')
    if not found.action_ready and avatar.warned~=found.id then
        avatar.warned=found.id
        mod:log('note: Runtime\'s action layer does not see entity '..found.id..' (handles.local_avatar); spawns '
            ..'will be refused NO_LOCAL_AVATAR while that lasts')
    end
end
-- Leaving a mission (seen by the poll or the mission_ended event, whichever comes first): logged once.
local function leave()
    if avatar.state~='idle'then
        avatar.state,avatar.entity='idle',nil
        mod:log('mission ended: the custom projectiles stay defined for the next one')
    end
end
-- One avatar check: polled every AVATAR_POLL seconds, and before every key press.
local function check_avatar()
    local state=hd2.game_state()
    if not(state and state.mission)then
        leave()
        return nil,'not in a mission'
    end
    if avatar.state=='idle'then
        avatar.state,avatar.waited,avatar.since_log='waiting',0,0
        mod:log('in a mission: waiting for avatar')
    end
    local found,why=resolve_avatar()
    if found then
        if avatar.state=='waiting'then available(found,'available')
        elseif avatar.state=='lost'or(avatar.state=='available'and avatar.entity~=found.id)then
            available(found,'restored')
        end
        return found
    end
    if avatar.state=='available'then
        avatar.state,avatar.waited,avatar.since_log='lost',0,0
        mod:log('avatar lost: '..why..'; waiting for avatar')
    end
    return nil,why
end
hd2.every(AVATAR_POLL,function()
    local before=avatar.state
    local _,why=check_avatar()
    if(avatar.state=='waiting'or avatar.state=='lost')and avatar.state==before then
        avatar.waited=avatar.waited+AVATAR_POLL
        avatar.since_log=avatar.since_log+AVATAR_POLL
        if avatar.since_log>=WAIT_LOG_SECONDS then
            avatar.since_log=0
            mod:log(('still waiting for avatar after %.0f s: %s'):format(avatar.waited,tostring(why)))
        end
    end
end,{id='proof-avatar'})

hd2.events.on('mission_started',function()
    local ready=0
    for _,variant in ipairs(VARIANTS)do if define(variant.id)then ready=ready+1 end end
    baseline=table_state()
    if avatar.state~='waiting'then
        avatar.state,avatar.entity,avatar.waited,avatar.since_log='waiting',nil,0,0
    end
    mod:log('mission started: '..ready..' of '..#VARIANTS..' custom projectiles defined; vanilla table baseline '
        ..(baseline and('taken ('..#baseline.rows..' rows)')or'unreadable')..'; waiting for avatar')
end,{id='proof-mission'})
hd2.events.on('mission_ended',leave,{id='proof-mission-end'})

-- Where F7 and F8 fire from: the most accurate origin Runtime can read. No muzzle node or camera transform is
-- researched, so the source is the weapon in hand: its root world pose (runtime/event_world.lua unit_pose), with the
-- origin MUZZLE_OFFSET metres along its forward axis (an approximation of the muzzle that also keeps the shot clear
-- of your own body) and its forward axis as the direction (it follows the weapon's pitch). The weapon pose is used
-- only while the weapon is in your hands: within MAX_WEAPON_DISTANCE of the avatar and heading the way the avatar
-- faces. Otherwise (nothing held, or the weapon is not in the hands) the shot leaves at chest height along the
-- avatar's facing. found is resolve_avatar()'s result. Returns origin, direction and a description of the source.
local MUZZLE_OFFSET,CHEST_HEIGHT,MAX_WEAPON_DISTANCE,MIN_ALIGNMENT=1.0,1.4,2.5,0.5
local function launch(found)
    local world,body=found.world,found.body
    local fallback='nothing in hand'
    local held=world_module.equipped(world,found.id)
    local unit=held and held.entity and world_module.entity_unit(world,held.entity)
    local weapon=unit and world_module.unit_pose(world,unit)
    if held and held.entity and not weapon then fallback='the pose of the held weapon is unreadable'end
    if weapon then
        local p,q,f=weapon.position,body.position,weapon.forward
        local distance=math.sqrt((p.x-q.x)^2+(p.y-q.y)^2+(p.z-q.z)^2)
        local flat=math.sqrt(f.x^2+f.y^2)
        local alignment=flat>1e-3 and(f.x*body.forward.x+f.y*body.forward.y)/flat or -1
        if distance<=MAX_WEAPON_DISTANCE and alignment>=MIN_ALIGNMENT then
            return {x=p.x+f.x*MUZZLE_OFFSET,y=p.y+f.y*MUZZLE_OFFSET,z=p.z+f.z*MUZZLE_OFFSET},{x=f.x,y=f.y,z=f.z},
                'held weapon pose'
        end
        fallback=('the held weapon is not in the hands (%.1f m from the avatar, heading alignment %.2f)')
            :format(distance,alignment)
    end
    local q,f=body.position,body.forward
    return {x=q.x+f.x*MUZZLE_OFFSET,y=q.y+f.y*MUZZLE_OFFSET,z=q.z+CHEST_HEIGHT},{x=f.x,y=f.y,z=f.z},
        'avatar facing ('..fallback..')'
end
local function shot_line(key,what,from,direction,source,shot)
    return ('%s: %s from (%.2f, %.2f, %.2f) along (%.2f, %.2f, %.2f) [%s]: %s%s'):format(key,what,from.x,from.y,
        from.z,direction.x,direction.y,direction.z,source,shot.status,
        shot.code and(' '..shot.code..': '..tostring(shot.reason))or'')
end
for _,variant in ipairs(VARIANTS)do
    local key,id=variant.key,variant.id
    hd2.input.bind('custom_projectile_row_proof.'..id:gsub('^dev/',''),{key=key,on_press=function()
        local def=define(id)
        if not def then return end
        local found,why=check_avatar()
        if not found then mod:log(key..': waiting for avatar ('..tostring(why)..')');return end
        local from,direction,source=launch(found)
        local shot=actions.spawn_custom_projectile(id,{position=from,direction=direction})
        mod:log(shot_line(key,id..' ('..components_of(def)..')',from,direction,source,shot))
    end})
end
hd2.input.bind('custom_projectile_row_proof.fire_vanilla',{key='F8',on_press=function()
    local found,why=check_avatar()
    if not found then mod:log('F8: waiting for avatar ('..tostring(why)..')');return end
    local from,direction,source=launch(found)
    local shot=hd2.projectiles.spawn('LAS-58 Talon',{position=from,direction=direction})
    mod:log(shot_line('F8','vanilla LAS-58 Talon',from,direction,source,shot))
end})
hd2.input.bind('custom_projectile_row_proof.verify',{key='F9',on_press=function()
    if not baseline then mod:log('F9: no baseline yet (start a mission)');return end
    local now,why=table_state()
    if not now then mod:log('F9: the projectile table is unreadable: '..tostring(why));return end
    local changed={}
    for kind=1,#baseline.rows do
        if now.rows[kind]~=baseline.rows[kind]then changed[#changed+1]=tostring(kind)end
    end
    mod:log(('F9: %d vanilla rows compared: %s; row 144 %s; table entries 0 and 351 %s'):format(#baseline.rows,
        #changed==0 and'all byte-identical to the mission start'or('CHANGED: '..table.concat(changed,', ')),
        now.rows[144]==baseline.rows[144]and'byte-identical'or'CHANGED',
        now.edges==baseline.edges and'unchanged'or'CHANGED'))
    local world=world_module.open()
    for _,variant in ipairs(VARIANTS)do
        local def=definitions[variant.id]
        if def then
            local live=world and world.view.read(def.row.address,def.row.size)
            mod:log('F9: '..variant.id..' Runtime-owned row 0x'..string.format('%X',def.row.address)..' '
                ..(live==def.bytes and'unchanged since its definition'or'CHANGED or unreadable'))
        end
    end
end})

mod:log('loaded: in a mission as host, F7 visual, F5 damage, F6 ballistics, F10 impact explosion, F11 all four '
    ..'(custom Talon-derived projectiles), F8 a vanilla Talon bolt, F9 verifies the vanilla projectile table')
