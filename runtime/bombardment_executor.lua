-- The Runtime bombardment executor (development only; research/docs/beacon-redirect-F5FEE03DCFDB.md, "The Runtime
-- bombardment executor"). Not exported by api/hd2.lua.
--
-- It fires a vanilla shell (a ProjectileInfo type, e.g. the Orbital Gas Strike's shell 197) in a barrage pattern through
-- the game's own projectile wrapper (FireProjectile, the path of the live-proven hd2.projectiles.spawn), from the host's
-- avatar. Nothing is written to game data: no BombardmentComponentData, no shell, explosion or status row. The shell's
-- own chain (its impact explosion and statuses) does the rest, as when the game fires it.
--
-- The pattern is a donor's, read-only from its live record, which must be exactly its reviewed vanilla bytes (e.g. the
-- Orbital 120mm HE Barrage: 5 salvos of 3 shells, 0.75 s between shells, 2.0 s between salvos, scatter 27). Explicit
-- values may override any word. Where the game's barrage does something this executor does not reproduce, the
-- difference is documented, not approximated silently (M.DIFFERENCES).
--
-- Guards when started (refused, nothing fired): FireProjectile's prologue and the projectile system active (a
-- mission); host; solo; the shell's row resolves and is exactly its reviewed row; the shell donor's call-in package
-- resident; the pattern donor's record exactly vanilla; a finite target. Each shell re-checks the mission, the host and
-- the avatar; a failure ends the barrage.
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local handles=require('hd2runtime/runtime/handles')
local core_assets=require('hd2runtime/core/assets')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local PD=require('hd2runtime/domains/bombardment_payload')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local M={}
M.MAX_SHELLS=64

local function log(text)log_module.emit('[HD2Runtime] bombardment executor '..text)end

-- The reviewed record of a stratagem by name (domains/bombardment_payload.lua), or nil.
local function reviewed(name)
    local entry=catalog.stratagems[name]
    local id=entry and entry.root and entry.root.id
    return id and PD.records[tostring(id)],id
end
-- The donor's pattern from its reviewed vanilla record (static; the live record is checked when started).
function M.pattern_of(name)
    local record=reviewed(name)
    if not record then return nil end
    local raw=b.unhex(record.vanilla)
    local f=function(o)return b.value(raw,o,'f32')end
    return {shells_per_salvo=b.u32(raw,0x04),salvos=b.u32(raw,0x18),shell_delay=f(0x08),shell_delay_random=f(0x0C),
        salvo_delay=f(0x1C),salvo_delay_random=f(0x20),scatter=f(0x24),salvo_scatter=f(0x28),walk={f(0x10),f(0x14)},
        drift=f(0x60),distance=f(0x2C),start_delay=f(0x80)}
end

-- The live record of a reviewed stratagem: true when it is exactly its vanilla bytes, or nil and why. Read-only: the
-- game's own lookup (the payload hash's index slot), as runtime/bombardment_payload.lua reads it.
local function record_vanilla(world,name)
    local record=reviewed(name)
    if not record then return nil,'no reviewed bombardment record for '..tostring(name)end
    local components=world.view.pointer(world.game+PD.component.global)
    local index=components and world.view.pointer(components+PD.component.indexField)
    if not index then return nil,'the bombardment index is unreadable'end
    local address=index+PD.component.recordOffset+record.record*PD.component.stride
    local bytes=world.view.read(address,PD.component.stride)
    if bytes~=b.unhex(record.vanilla)then return nil,name..'\'s live record is not its reviewed vanilla record'end
    return true
end
-- The shell row (a ProjectileInfo type) exactly as reviewed: true, or nil and why.
local function shell_reviewed(world,shell)
    local reviewed_bytes=PD.shellRows[tostring(shell)]
    if not reviewed_bytes then return nil,'shell '..tostring(shell)..' has no reviewed row'end
    local row=world.view.pointer(world.game+PD.shellTable+shell*8)
    if not(row and world.view.read(row,PD.shellStride)==b.unhex(reviewed_bytes))then
        return nil,'shell '..tostring(shell)..'\'s live row is not its reviewed row'
    end
    return true
end
-- The call-in package of a stratagem: its dependency, or nil.
local function package_of(world,name)
    local entry=catalog.stratagems[name]
    local id=entry and entry.root and entry.root.id
    return id and core_assets.dependency_for_stratagem(id,name)
end

-- Where one shell comes from and goes to (research: the game's shell path, 0x8526AA-0x852931). The game spawns a shell
-- at the scattered aim point + up (0, 0, 1) x the record's +0x2C (3000) and, for records with +0x3C set (the 120mm,
-- the Gas Strike), moves that origin to a node of the caller's destroyer (0xA0AE00) and aims ballistically (0x13B2490).
-- When the barrage entity has no ship, the game keeps the origin straight above the aim. This executor uses that
-- straight-above origin and a straight-down direction (a vertical shot needs no ballistic elevation).
function M.geometry(aim,pattern)
    local height=pattern.distance or 3000
    return {x=aim.x,y=aim.y,z=aim.z+height},{x=0,y=0,z=-1}
end
-- What the game's barrage does that this executor does not (docs: "The Runtime bombardment executor").
M.DIFFERENCES={
    'origin: straight above the aim at the record distance, not the caller destroyer node with a ballistic aim',
    'aim height: the target\'s height; the game snaps each scattered aim to the ground (a raycast from +500 m)',
    'source: the host avatar (FireProjectile), not a barrage entity: no shared stats id; a moving avatar may add its '
        ..'velocity to the shell (row +0xF0 bit 0) [I]',
    'no barrage launch effect, no stratagem-fire sounds (first/last shell), no AI incoming warning',
    'the caller ship modules are not applied (extra salvo, spread reduction); the pattern is used as given',
    'network: the shells are spawned on the host only (SpawnProjectile sends nothing); a native barrage is created on '
        ..'every peer from replicated fields',
}

-- The game's scatter: a uniform square of half-width w around c (x and y; z kept), r = random() in [0, 1).
local function scatter(c,w,random)
    if not(w and w>0)then return {x=c.x,y=c.y,z=c.z}end
    return {x=c.x+(2*random()-1)*w,y=c.y+(2*random()-1)*w,z=c.z}
end
M.scatter=scatter

local function finite(v)return type(v)=='number'and v==v and math.abs(v)<1e6 end

-- Start a barrage. spec = {shell = ProjectileInfo type (default: the shell donor's first shell), shell_donor = name
-- (whose call-in package must be resident; default 'Orbital Gas Strike'), pattern = donor name (default 'Orbital
-- 120mm HE Barrage') or nil, overrides = {pattern words}, target = {x, y, z}, impact_explosion = a reviewed explosion
-- donor (runtime/explosion_donors.lua: each shell, right after it is fired, requests that donor's explosion on impact
-- instead of its own: one write of that shell's own copy; only the slot this executor has just spawned into, read from
-- the pool counter around its own FireProjectile), label, random = function (tests)}.
-- callback(event): 'started', 'shell' (n, salvo, aim, position, converted), 'ended' (shells, seconds, converted),
-- 'refused' (code, reason). Returns the handle {status, cancel()}, or nil, code, reason.
function M.start(spec,callback)
    spec=spec or{}
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','a barrage needs a mission'end
    if game.host~=true then return nil,'NOT_HOST','development executor: host only'end
    local record,code,reason=slots.local_record(world)
    if not record then return nil,code,reason end
    -- SpawnProjectile sends nothing: the shells exist on this machine only (spec.multiplayer: a custom stratagem call).
    local scode,swhy=require('hd2runtime/runtime/multiplayer').solo_guard(record.records,spec.multiplayer==true,
        'the shells exist on this machine only')
    if scode then return nil,scode,swhy end
    local avatar,awhy=handles.local_avatar(world)
    if not avatar then return nil,'NO_LOCAL_AVATAR','the shells are fired from the host avatar: '..tostring(awhy)end
    local shell_donor=spec.shell_donor or'Orbital Gas Strike'
    local donor_record=reviewed(shell_donor)
    local shell=spec.shell or(donor_record and donor_record.shells and donor_record.shells[1])
    if type(shell)~='number'then return nil,'INVALID','no shell type'end
    local ok
    ok,why=shell_reviewed(world,shell)
    if not ok then return nil,'SHELL_CHANGED',why end
    local dependency=package_of(world,shell_donor)
    if dependency then
        local okp,state=pcall(core_assets.state,world.runtime,dependency.package)
        if not(okp and state=='resident')then
            return nil,'SHELL_NOT_RESIDENT',('the call-in package of %s is not resident (%s)'):format(shell_donor,
                tostring(okp and state or'unreadable'))
        end
    end
    -- The impact explosion donor: reviewed, its chain intact and its package resident now.
    if spec.impact_explosion~=nil then
        local donors=require('hd2runtime/runtime/explosion_donors')
        if not donors.DONORS[spec.impact_explosion]then
            return nil,'UNREVIEWED_DONOR','no reviewed explosion donor '..tostring(spec.impact_explosion)
        end
        local ready,dcode,dwhy=donors.ready(world,spec.impact_explosion)
        if not ready then return nil,dcode,dwhy end
    end
    local pattern=spec.pattern~=false and M.pattern_of(spec.pattern or'Orbital 120mm HE Barrage')or{}
    if spec.pattern~=false then
        ok,why=record_vanilla(world,spec.pattern or'Orbital 120mm HE Barrage')
        if not ok then return nil,'PATTERN_CHANGED',why end
    end
    for k,v in pairs(spec.overrides or{})do pattern[k]=v end
    local shells=(pattern.shells_per_salvo or 0)*(pattern.salvos or 0)
    if not(shells>=1 and shells<=M.MAX_SHELLS)then return nil,'INVALID','the pattern fires '..shells..' shells'end
    for _,key in ipairs({'shell_delay','salvo_delay','scatter'})do
        if not(finite(pattern[key])and pattern[key]>=0)then return nil,'INVALID','pattern '..key..' is not usable'end
    end
    local t=spec.target
    if not(type(t)=='table'and finite(t.x)and finite(t.y)and finite(t.z))then
        return nil,'INVALID_TARGET','the target must be finite {x, y, z}'
    end
    local random=spec.random or math.random
    local h={status='active',fired=0,salvo=0,label=spec.label or'barrage',shell=shell,pattern=pattern,converted=0}
    local function emit(event)
        if callback then
            local okc,err=pcall(callback,event)
            if not okc then log('callback failed: '..tostring(err))end
        end
    end
    local elapsed,next_at,left=0,math.max(0,pattern.start_delay or 0),0
    local walk=pattern.walk or{0,0}
    local function finish(kind,code2,reason2)
        h.status='complete'
        if kind=='refused'then
            emit({kind='refused',code=code2,reason=reason2,shells=h.fired,seconds=elapsed})
        else
            emit({kind='ended',shells=h.fired,salvos=h.salvo,seconds=elapsed,converted=h.converted})
        end
    end
    function h.tick(dt)
        if h.status~='active'then return end
        elapsed=elapsed+(dt or 0)
        while h.status=='active'and elapsed>=next_at do
            if left==0 then
                if h.salvo>=pattern.salvos then return finish('ended')end
                h.salvo=h.salvo+1
                left=pattern.shells_per_salvo
                -- A salvo's centre: the target with the salvo-centre scatter (record +0x28); the aim restarts there.
                h.centre=scatter(t,pattern.salvo_scatter or 0,random)
                h.aim={x=h.centre.x,y=h.centre.y,z=h.centre.z}
            elseif(walk[1]or 0)~=0 or(walk[2]or 0)~=0 then
                -- The aim walk (record +0x10/+0x14), on every shell but a salvo's first: cumulative, z kept.
                local a,r2=random()*2*math.pi,random()
                local step=walk[1]+(walk[2]-walk[1])*r2
                h.aim={x=h.aim.x+step*math.cos(a),y=h.aim.y+step*math.sin(a),z=h.aim.z}
            end
            local w=world_module.open()
            local g=w and world_module.game_state(w)
            if not(g and g.mission and g.host==true)then return finish('refused','NOT_IN_MISSION','the mission ended')end
            local avatar,awhy=handles.local_avatar(w)
            if not avatar then return finish('refused','NO_LOCAL_AVATAR',tostring(awhy))end
            local aim=scatter(h.aim,pattern.scatter,random)
            local from,dir=M.geometry(aim,pattern)
            local before=spec.impact_explosion and world_module.projectile_counter(w)
            local fired,fwhy=world_module.projectile(w,{type=shell,x=from.x,y=from.y,z=from.z,dx=dir.x,dy=dir.y,dz=dir.z,
                entity=avatar.id})
            if not fired then return finish('refused','PROJECTILE_REFUSED',tostring(fwhy))end
            metrics.count('bombardment_executor.shells')
            h.fired=h.fired+1
            left=left-1
            -- This shell's own impact explosion: exactly the slot this FireProjectile spawned into (the counter moved by
            -- one; the slot holds this shell type from this avatar: projectile_impact.convert_slot re-checks both).
            local converted
            if spec.impact_explosion then
                local after,system=world_module.projectile_counter(w)
                local PO=require('hd2runtime/domains/projectile_rows').pool
                if before and after and(after-before)%4294967296==1 then
                    local event=require('hd2runtime/runtime/projectile_impact').convert_slot({slot=before%PO.slots,
                        source=avatar.id,projectile=shell,donor=spec.impact_explosion,label=h.label..' shell '..h.fired,
                        multiplayer=spec.multiplayer==true})
                    converted=event.kind=='converted'
                    if converted then h.converted=h.converted+1 end
                else
                    log(('%s shell %d: the pool counter moved by %s, not 1: this shell stays vanilla'):format(h.label,
                        h.fired,tostring(before and after and(after-before)%4294967296)))
                    converted=false
                end
            end
            emit({kind='shell',n=h.fired,salvo=h.salvo,aim=aim,from=from,seconds=elapsed,converted=converted})
            -- The game's timers: the next shell after +0x08 + (2r - 1) x +0x0C; after a salvo's last shell, the next salvo
            -- (its first shell at once) after +0x1C + (2r - 1) x +0x20.
            if left>0 then
                next_at=next_at+math.max(0,pattern.shell_delay+(2*random()-1)*(pattern.shell_delay_random or 0))
            else
                next_at=next_at+math.max(0,pattern.salvo_delay+(2*random()-1)*(pattern.salvo_delay_random or 0))
            end
        end
    end
    function h.cancel()if h.status=='active'then h.status='cancelled'end end
    scheduler.attach(h)
    emit({kind='started',shell=shell,pattern=pattern,target=t,shells=shells})
    log(('started %s: shell %d, %d salvos of %d, %.2f s between shells, %.2f s between salvos, scatter %.1f, start '
        ..'delay %.2f s, target (%.1f, %.1f, %.1f)%s'):format(h.label,shell,pattern.salvos,pattern.shells_per_salvo,
        pattern.shell_delay,pattern.salvo_delay,pattern.scatter,pattern.start_delay or 0,t.x,t.y,t.z,
        spec.impact_explosion and('; each shell explodes as '..spec.impact_explosion..'\'s on impact')or''))
    return h
end
return M
