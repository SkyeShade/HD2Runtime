-- Enemy spawn weights (docs/enemy-spawns.md; research/enemy-spawn-weights-F5FEE03DCFDB.json;
-- domains/enemy_spawn_weights.lua). Not exported directly: hd2.enemies.spawn_weight (api/enemy_spawns.lua) uses it.
--
-- game.dll keeps one static enemy roster per faction (.data): rows of 0x80 bytes, each an enemy type in a spawn group
-- with ten weights, one per difficulty (row +0x30). Every spawn that picks an enemy type calls PickEnemy (0x953150),
-- which keeps the group's rows with an active subfaction and a weight above 0 at the mission difficulty and picks one
-- with probability weight / sum. A multiplier k for an enemy type writes, in every row of that type, each weight as its
-- vanilla value x k (only the difficulties asked for): the type's share of every group it is in grows (k > 1), shrinks
-- (k < 1) or ends (k = 0); the other types keep their weights.
--
-- Every write is a guarded transaction over the type's rows read now (each whole row is a context; game.dll image
-- memory, read-write only): the expected bytes are exactly the vanilla weights (or the ones this configuration wrote),
-- so another writer's value is a CONFLICT and is never overwritten. stop() writes the vanilla bytes back the same way.
--
-- What loads: a mission loads the packages of the rows whose weight at its difficulty is above 0 (0xABD6AC). So a weight
-- never goes from 0 (or less) to positive while a mission or its preparation runs: such a change (restoring a k = 0
-- type, or k = 0 -> k > 0) waits until the game is aboard the ship (or before it), and the handle says 'deferred'.
-- A k > 0 never changes which weights are above 0, and k = 0 only removes candidates, so those apply at once.
--
-- The rosters are process-wide: a configuration lasts until stop() or the end of the session, across missions. Enemies
-- are spawned by the mission host: on a client the rosters are written but decide nothing.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local natives=require('hd2runtime/domains/event_natives')
local D=require('hd2runtime/domains/enemy_spawn_weights')
local M={}
M.CHECK_EVERY=1.0
M.MAX_MULTIPLIER=10
local IMAGE=0x1000000
local ROW,DIFFICULTIES=D.row.stride,D.row.difficulties
local WEIGHTS=D.row.weights
-- Game states in which no mission is loading or running (None, Splash, TitleScreen, Ship, PrepareShip): only there may
-- a weight go from 0 to positive.
local SAFE_STATES={[0]=true,[1]=true,[2]=true,[3]=true,[5]=true}

local function log(text)log_module.emit('[HD2Runtime] enemy spawns '..text)end

-- entity (16 hex digits) -> its rows {faction, index, rva, vanilla (40 bytes), group}
local rows_by_entity={}
for _,faction in ipairs(D.factions)do
    for _,entry in ipairs(faction.entries)do
        local list=rows_by_entity[entry.entity]or{}
        list[#list+1]={faction=faction.name,index=entry.index,rva=faction.rows+entry.index*ROW,
            vanilla=b.unhex(entry.weights),group=entry.group}
        rows_by_entity[entry.entity]=list
    end
end
function M.rows_of(entity)return rows_by_entity[entity]end

local configs={}          -- entity -> configuration
local watch
local clock,last_check=0,-math.huge
local unavailable_logged
local client_logged=false

-- The pins and the live roster descriptors (each must name its rows and count), proven once per loaded game.dll. The
-- image owner, or nil and the reason.
local function image_of(world)
    if world.enemy_spawn_image then return world.enemy_spawn_image end
    if D.source.gameDllSha256~=natives.source.gameDllSha256 then
        return nil,'the enemy spawn research covers another game.dll build'
    end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,'native spawn pick changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    for _,faction in ipairs(D.factions)do
        local d=world.view.read(world.game+faction.descriptor,12)
        if not d or b.pointer(d,0)~=world.game+faction.rows or b.u32(d,8)~=faction.count then
            return nil,'the '..faction.name..' roster descriptor does not name its rows'
        end
    end
    local r=world.runtime.query and world.runtime.query(world.game+D.factions[1].rows)
    if not(r and r.type==IMAGE and r.allocation_base==world.game)then
        return nil,'the rosters are not game.dll image memory'
    end
    world.enemy_spawn_image={base=world.game,size=D.source.imageSize,type=IMAGE,protect=4}
    return world.enemy_spawn_image
end

local function f32(bytes,offset)
    local n=b.u32(bytes,offset)
    if math.floor(n/8388608)%256==255 then return nil end
    return b.value(bytes,offset,'f32')
end

-- The 40 weight bytes a configuration wants for a row: each asked-for difficulty's vanilla weight x k. nil and the
-- reason when a value does not encode exactly.
local function desired_weights(row,config)
    local parts={}
    for d=1,DIFFICULTIES do
        local v=f32(row.vanilla,(d-1)*4)
        if not v then return nil,'a vanilla weight is not finite'end
        if config.difficulties[d]then
            local want=v*config.multiplier
            local bytes=b.encode(want,'f32')
            local back=b.value(bytes,0,'f32')
            if math.abs(back-want)>math.max(1e-6,math.abs(want)*1e-6)then return nil,'a weight does not encode exactly'end
            parts[#parts+1]=bytes
        else
            parts[#parts+1]=row.vanilla:sub((d-1)*4+1,d*4)
        end
    end
    return table.concat(parts)
end

-- Whether going from bytes `from` to `to` makes any weight go from 0 (or less) to positive.
local function enables(from,to)
    for d=1,DIFFICULTIES do
        local a,c=f32(from,(d-1)*4),f32(to,(d-1)*4)
        if a and c and a<=0 and c>0 then return true end
    end
    return false
end

-- Moves every row of a configuration from its expected bytes to `target` (a function row -> 40 bytes) in one guarded
-- transaction. Returns 'APPLIED' | 'ALREADY' | 'DEFERRED' | nil, code, reason.
local function move(world,image,config,target,expected)
    local game=world_module.game_state(world)
    local safe=game~=nil and SAFE_STATES[game.state]==true
    local snapshots,changes={},{}
    local any=false
    for _,row in ipairs(config.rows)do
        local address=world.game+row.rva
        local bytes=world.view.read(address,ROW)
        if not bytes then return nil,'UNREADABLE','a roster row is unreadable'end
        local current=bytes:sub(WEIGHTS+1,WEIGHTS+40)
        local want=target(row)
        local from=expected(row)
        if current~=from and current~=want then
            return nil,'CONFLICT',('the %s row %d of %s holds weights that are neither the vanilla nor this '
                ..'configuration\'s (another writer)'):format(row.faction,row.index,config.label)
        end
        if current~=want then
            if not safe and enables(current,want)then return 'DEFERRED'end
            any=true
            snapshots[#snapshots+1]={owner=image,offset=row.rva,bytes=bytes}
            for chunk=0,4 do
                local at=chunk*8
                local before,desired=current:sub(at+1,at+8),want:sub(at+1,at+8)
                if before~=desired then
                    changes[#changes+1]={label=('enemy.spawn_weight.%s.row%d+%d'):format(row.faction,row.index,at),
                        owner=image,offset=row.rva+WEIGHTS+at,expected=before,desired=desired,before=before,
                        already_desired=false,identity={component='EnemyRoster',component_type='native_module_data',
                            record_index=row.index,unique_owner=true,owner_count=1},chain={}}
                end
            end
        end
    end
    if not any then return 'ALREADY'end
    local report=transaction.apply(world.runtime,{snapshots=snapshots,changes=changes})
    metrics.count('enemy_spawns.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    config.last_writes=report.writes
    return 'APPLIED'
end

local function vanilla(row)return row.vanilla end
-- What a configuration holds in the rows now: config.held (a function row -> 40 bytes), or the vanilla bytes.
local function held(config)return config.held or vanilla end

local function settle(world,image,config)
    if config.status=='stopping'then
        local result,code,reason=move(world,image,config,vanilla,held(config))
        if result=='APPLIED'or result=='ALREADY'then
            config.status,config.held='stopped',nil
            configs[config.entity]=nil
            log(('(%s): %s restored to the vanilla weights (%d row%s)'):format(config.owner,config.label,#config.rows,
                #config.rows==1 and''or's'))
        elseif result=='DEFERRED'then
            if not config.restore_logged then
                config.restore_logged=true
                log(('(%s): restoring %s waits until no mission is running (a weight goes from 0 to positive; the '
                    ..'mission loaded without its packages)'):format(config.owner,config.label))
            end
        else
            config.status,config.code,config.reason='conflict',code,reason
            configs[config.entity]=nil
            log(('(%s): %s NOT restored: %s: %s'):format(config.owner,config.label,tostring(code),tostring(reason)))
        end
        return
    end
    local function wanted(row)return config.desired[row]end
    local result,code,reason=move(world,image,config,wanted,held(config))
    if result=='APPLIED'or result=='ALREADY'then
        config.status,config.held='applied',wanted
        config.code,config.reason=nil,nil
        log(('(%s): %s spawn weight x %g%s APPLIED in %d roster row%s (%s)'):format(config.owner,config.label,
            config.multiplier,config.difficulty_text,#config.rows,#config.rows==1 and''or's',config.factions))
    elseif result=='DEFERRED'then
        if config.status~='deferred'then
            log(('(%s): %s x %g waits until no mission is running (a weight goes from 0 to positive; the mission '
                ..'loaded without its packages)'):format(config.owner,config.label,config.multiplier))
        end
        config.status='deferred'
    else
        config.status,config.code,config.reason=code=='CONFLICT'and'conflict'or'refused',code,reason
        log(('(%s): %s x %g REFUSED: %s: %s'):format(config.owner,config.label,config.multiplier,tostring(code),
            tostring(reason)))
    end
end

-- Applied configurations are re-read every check: a row that no longer holds this configuration's bytes was changed by
-- another writer (CONFLICT, logged once; nothing is written).
local function verify(world,config)
    for _,row in ipairs(config.rows)do
        local current=world.view.read(world.game+row.rva+WEIGHTS,40)
        if current and current~=config.desired[row]then
            config.status,config.code,config.reason='conflict','CONFLICT',('the %s row %d of %s was changed by '
                ..'another writer'):format(row.faction,row.index,config.label)
            log(('(%s): %s: %s'):format(config.owner,config.label,config.reason))
            return
        end
    end
end

local function step()
    if not next(configs)then return end
    local world,why=world_module.open()
    if not world then return end
    local image,reason=image_of(world)
    if not image then
        if unavailable_logged~=reason then
            unavailable_logged=reason
            log('UNAVAILABLE: no spawn weight is written: '..tostring(reason))
        end
        for _,config in pairs(configs)do
            if config.status=='pending'then config.status,config.code,config.reason='unavailable','UNAVAILABLE',reason end
        end
        return
    end
    local game=world_module.game_state(world)
    if game and game.mission and game.host==false and not client_logged then
        client_logged=true
        log('this machine is not the host: its rosters decide nothing (enemies are spawned by the mission host)')
    end
    for _,config in pairs(configs)do
        if config.status=='applied'then verify(world,config)
        elseif config.status=='pending'or config.status=='deferred'or config.status=='stopping'
                or config.status=='unavailable'then settle(world,image,config)end
    end
end
M.step=step

local function ensure_watch()
    if watch and watch.status=='active'then return end
    watch={status='active'}
    function watch.tick(dt)
        if watch.status~='active'then return end
        clock=clock+(dt or 0)
        if clock-last_check<M.CHECK_EVERY then return end
        last_check=clock
        local ok,why=pcall(step)
        if not ok then log('update failed: '..tostring(why))end
        if not next(configs)then watch.status='complete'end
    end
    function watch.cancel()watch.status='cancelled'end
    scheduler.attach(watch)
end

-- Configures one enemy type. spec = {owner, entity (16 hex digits), label, multiplier (0..MAX_MULTIPLIER), difficulties
-- (set of 1..10; nil = all)}; validated by api/enemy_spawns.lua. A second configuration of the same owner for the
-- same type replaces the first; another owner's is refused. Applies at once when it can. Returns the configuration,
-- or nil, code, reason.
function M.configure(spec)
    local rows=rows_by_entity[spec.entity]
    if not rows then return nil,'NOT_IN_A_ROSTER',tostring(spec.label)..' is in no spawn roster'end
    local prior=configs[spec.entity]
    if prior and prior.owner~=spec.owner and prior.status~='stopping'then
        return nil,'ALREADY_SET',spec.label..' spawn weights are set by '..prior.owner
    end
    local config={owner=spec.owner,entity=spec.entity,label=spec.label,multiplier=spec.multiplier,rows=rows,
        difficulties=spec.difficulties,status='pending',desired={},held=nil}
    local factions,seen={},{}
    for _,row in ipairs(rows)do
        local bytes,why=desired_weights(row,config)
        if not bytes then return nil,'INVALID_MULTIPLIER',why end
        config.desired[row]=bytes
        if not seen[row.faction]then seen[row.faction]=true;factions[#factions+1]=row.faction end
    end
    config.factions=table.concat(factions,', ')
    local listed={}
    for d=1,DIFFICULTIES do if spec.difficulties[d]then listed[#listed+1]=d end end
    config.difficulty_text=#listed==DIFFICULTIES and''or(' at difficulty '..table.concat(listed,', '))
    -- A replaced configuration (the same owner's, or one being restored) hands over what it holds in the rows: the new
    -- one moves from those bytes in one transaction.
    if prior then
        config.held=prior.held
        prior.status='replaced'
    end
    configs[spec.entity]=config
    local ok,why=pcall(step)
    if not ok then log('update failed: '..tostring(why))end
    ensure_watch()
    return config
end

-- Restores a configuration's rows to the vanilla weights (deferred while a mission runs when a weight goes from 0 to
-- positive). true when it was active.
function M.stop(config)
    if not config or configs[config.entity]~=config then return false end
    if config.status=='conflict'then configs[config.entity]=nil;return true end
    if not config.held then
        config.status='stopped'
        configs[config.entity]=nil
        return true
    end
    config.status='stopping'
    local ok,why=pcall(step)
    if not ok then log('update failed: '..tostring(why))end
    ensure_watch()
    return true
end

function M.configs()return configs end
function M.reset_for_tests()
    configs,clock,last_check,unavailable_logged,client_logged={},0,-math.huge,nil,false
    if watch then watch.status='cancelled'end
    watch=nil
end
return M
