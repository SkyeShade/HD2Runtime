-- Beam conversion sync (DEVELOPMENT; docs/beam-conversion.md "Multiplayer"; research/docs/beam-conversion-mp-sync-
-- F5FEE03DCFDB.md). Not exported to mods.
--
-- Each Runtime publishes the beam conversions applied on it, and reads every other lobby member's, through the game's
-- own PlayFab lobby member data (runtime/peer_channel.lua, the key `hd2bc`, the hd2bc/1 grammar of runtime/beam_
-- conversion_sync_protocol.lua; the channel's rate limits are shared with `hd2rt` and `hd2as`).
--
-- WHAT IT CANNOT DO (the research's verdict, CONFIRMED and pinned): the same conversion on every machine does NOT make
-- multiplayer safe. The game applies a remote weapon's replicated state through a case chosen by its network TYPE
-- alone, and every convertible type's case calls the ProjectileWeapon apply 0x6190C0 unconditionally; a weapon built
-- from a converted list has no ProjectileWeapon instance, so on a converted machine EVERY remote-owned weapon of that
-- type hits the -1 store, whatever its owner converted. With both machines converted, each crashes when the other's
-- weapon spawns. So the decision below is REFUSED whenever another member is present: the agreement code first
-- (NO_RUNTIME, PENDING, MISMATCH, INCOMPATIBLE, MALFORMED), REMOTE_APPLY_UNSAFE when every member matches. The build
-- capability M.REMOTE_APPLY_SAFE is empty: no build is proven, and runtime/beam_conversion.lua's apply gate stays SOLO
-- whatever this module decides (the decision only explains the refusal).
--
-- What it does:
--   * PUBLISH: once this machine applied a conversion in this session, its set: per converted root the resource, the
--     path, a digest of its BeamWeapon record and of its borrowed rows, and the pair; with this Runtime's version, the
--     game build and the catalogue hash. After the last restore the empty set (`-`) is published, so the lobby never
--     keeps a stale set. The channel posts it again in every lobby this machine joins.
--   * READ: in the Runtime's own update, every M.POLL_EVERY s and only in a joined lobby of at least 2 members, every
--     other member's `hd2bc` value. Per member: match | mismatch | incompatible | malformed | pending (no value yet,
--     within M.PENDING_WINDOW s of first seeing it: the channel's own first post waits 10-20 s) | no_runtime.
--   * WARN THE OTHER SIDE: a member whose value lists conversions has a game that crashes when THIS machine spawns a
--     weapon of one of those types: a loud log line and the Runtime's notice name the weapons (once per member and set).
--   * LOG: `BEAM CONVERSION SYNC:` lines for the posted set, every member state change and the decision (once this
--     machine applied a conversion in this session, or while a member has one).
-- Safety: a received value is text; it is compared and its resources are named through the catalogue, nothing more.
local channel=require('hd2runtime/runtime/peer_channel')
local protocol=require('hd2runtime/runtime/beam_conversion_sync_protocol')
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local metadata=require('hd2runtime/domains/metadata')
local profile=require('hd2runtime/schemas/current')
local C=require('hd2runtime/domains/beam_conversion')
local fnv1a=require('hd2runtime/runtime/peer_protocol').fnv1a
local M={}
M.KEY='hd2bc'
M.BY='beam conversion sync'
M.POLL_EVERY=3
M.PENDING_WINDOW=30
-- Builds on which a remote weapon of a converted type is proven safe to apply (none: research/docs/beam-conversion-mp-
-- sync-F5FEE03DCFDB.md section 4 is a lead, not a proof).
M.REMOTE_APPLY_SAFE={}
M.STATES={match='match',mismatch='mismatch',incompatible='incompatible',malformed='malformed',pending='pending',
    no_runtime='no runtime'}
-- The order a refusal names its reason in: what a member lacks first.
local ORDER={'no_runtime','malformed','incompatible','mismatch','pending'}
local CODE={no_runtime='NO_RUNTIME',malformed='MALFORMED',incompatible='INCOMPATIBLE',mismatch='MISMATCH',
    pending='PENDING'}

local KEY='HD2RuntimeBeamConversionSyncV1'   -- survives a module reload, as the conversions do
local function st()
    local s=rawget(_G,KEY)
    if not s then
        s={entries={},names={},seq=0,ever=false,dirty=false,published=nil,members={},clock=0,acc=0,said={},
            said_count=0,decision=nil,watch=nil}
        rawset(_G,KEY,s)
    end
    return s
end
local function log(text)log_module.emit('BEAM CONVERSION SYNC: '..text)end
local function say(text)
    local s=st()
    if s.said[text]then return end
    if s.said_count>=512 then s.said,s.said_count={},0 end
    s.said[text]=true;s.said_count=s.said_count+1
    log(text)
end
function M.reset_for_tests()
    local s=rawget(_G,KEY)
    if s and s.watch then s.watch.status='cancelled'end
    rawset(_G,KEY,nil)
end

local BY_RESOURCE={}
for _,w in ipairs(C.weapons)do for _,root in ipairs(w.roots or{})do BY_RESOURCE[root.resource:sub(3):upper()]=w.name end end
function M.version()return tostring(metadata.version)end
function M.build()return tostring(profile.exe_sha):sub(1,12):upper()end
local catalogue
-- FNV-1a 32 of the catalogue a digest is meaningful against: the build, the donor record, every catalogued weapon
-- with its record and roots, and the borrowed pairs in research order.
function M.catalogue_hash()
    if not catalogue then
        local lines={'build '..tostring(C.source and C.source.build),'trident '..tostring(C.trident.recordHex)}
        for _,w in ipairs(C.weapons)do
            local roots={}
            for _,root in ipairs(w.roots or{})do roots[#roots+1]=root.resource end
            lines[#lines+1]=('%s|%s|%s|%s'):format(w.name,tostring(w.record),tostring(w.supported),
                table.concat(roots,','))
        end
        for i,p in ipairs(C.rows and C.rows.pairs or{})do lines[#lines+1]=('pair %d %s/%s'):format(i,
            tostring(p.beamType),tostring(p.damageInfo))end
        catalogue=fnv1a(table.concat(lines,'\n'))
    end
    return catalogue
end
-- The weapon name a converted root resource (16 hex digits) belongs to.
function M.weapon_of(resource)return BY_RESOURCE[tostring(resource):upper()]end

-- The entries of a located beam conversion state (runtime/beam_conversion.lua locate): one per converted or orphaned
-- root of every converted or orphaned weapon. Pure.
function M.entries_of(s)
    local entries,names={},{}
    for name,W in pairs(s.weapons or{})do
        if W.state=='converted'or W.state=='orphaned'then
            names[#names+1]=name
            local record,pair,rows='00000000',0,'00000000'
            if W.state=='converted'then
                local bytes=s.path_mode=='owned'and W.record or C.trident.recordHex
                record=fnv1a(tostring(bytes))
                if W.pair and s.rs and s.rs.pairs and s.rs.pairs[W.pair]then
                    local P=s.rs.pairs[W.pair]
                    pair=W.pair
                    rows=fnv1a(tostring(P.beam)..tostring(P.damage))
                end
            end
            for _,R in ipairs(W.roots or{})do
                if R.state=='converted'or R.state=='orphaned'then
                    entries[#entries+1]={resource=R.root.resource:sub(3):upper(),
                        path=R.state=='orphaned'and'x'or(s.path_mode=='owned'and'o'or's'),
                        record=R.state=='orphaned'and'00000000'or record,pair=R.state=='orphaned'and 0 or pair,
                        rows=R.state=='orphaned'and'00000000'or rows}
                end
            end
        end
    end
    table.sort(names)
    table.sort(entries,function(a,c)return a.resource<c.resource end)
    return entries,names
end

-- Called after every conversion write with the located state (runtime/beam_conversion.lua commit): the local set.
function M.note(s)
    local S=st()
    local entries,names=M.entries_of(s)
    local text=protocol.canonical(entries)
    local before=protocol.canonical(S.entries)
    S.names=names
    if text==before and S.seq>0 then return end
    S.entries=entries
    if#entries>0 then S.ever=true end
    if not S.ever then return end
    S.seq=S.seq+1;S.dirty=true
end

-- The local set as an hd2bc/1 value (nil before any conversion of this session), or nil, reason.
function M.value()
    local S=st()
    if not S.ever then return nil end
    return protocol.encode({version=M.version(),build=M.build(),catalog=M.catalogue_hash(),seq=math.max(S.seq,1),
        entries=S.entries})
end
function M.digest()
    local _,digest=protocol.canonical(st().entries)
    return digest
end

-- One member's state from its value (nil: none) against this machine's set. Pure but for the clock.
function M.member_state(value,local_digest,first_seen,clock)
    if value==nil then
        if clock-first_seen<M.PENDING_WINDOW then return'pending','no value yet'end
        return'no_runtime','no '..M.KEY..' value after '..M.PENDING_WINDOW..' s (no Runtime, an older one, or one '
            ..'that has applied no conversion this session)'
    end
    local d,why=protocol.decode(value)
    if not d then return'malformed',tostring(why)end
    if d.version~=M.version()or d.build~=M.build()or d.catalog~=M.catalogue_hash()then
        return'incompatible',('Runtime %s, build %s, catalogue %s (this machine: %s, %s, %s)'):format(d.version,d.build,
            d.catalog,M.version(),M.build(),M.catalogue_hash()),d
    end
    if d.digest~=local_digest then
        return'mismatch',('their conversions %s (%d root(s)), this machine\'s %s'):format(d.digest,#d.entries,
            local_digest),d
    end
    return'match','the same conversions ('..d.digest..')',d
end

-- The decision for an apply. input: {members = {{peer, state, host}}, build, remote_apply_safe (default: this build's
-- capability)}. Returns {allowed, code, reason}. Solo: allowed. Otherwise refused with the first agreement failure in
-- ORDER, else REMOTE_APPLY_UNSAFE unless the build's remote apply is proven safe. Pure.
function M.decide(input)
    local members=input and input.members or{}
    if#members==0 then return {allowed=true,code='SOLO',reason='no other lobby member'}end
    for _,state in ipairs(ORDER)do
        local which={}
        for _,m in ipairs(members)do
            if m.state==state then which[#which+1]=tostring(m.peer)..(m.host and' (host)'or'')end
        end
        if#which>0 then
            return {allowed=false,code=CODE[state],reason=('%s: %s'):format(M.STATES[state],table.concat(which,', '))}
        end
    end
    local safe=input.remote_apply_safe
    if safe==nil then safe=M.REMOTE_APPLY_SAFE[input.build or M.build()]==true end
    if not safe then
        return {allowed=false,code='REMOTE_APPLY_UNSAFE',reason='every member posts the same conversions, but on this '
            ..'build a remote weapon of a converted type crashes the converted machine at its network apply (the '
            ..'ProjectileWeapon apply is called by the network type alone): research/docs/beam-conversion-mp-sync-'
            ..'F5FEE03DCFDB.md'}
    end
    return {allowed=true,code='ALL_MATCH',reason='every member posts the same conversions'}
end

-- The current decision from the last read (solo when no lobby of 2 or more was read).
function M.decision()
    local S=st()
    local list={}
    for peer,m in pairs(S.members)do list[#list+1]={peer=peer,state=m.state,host=m.host}end
    table.sort(list,function(a,c)return a.peer<c.peer end)
    return M.decide({members=list})
end
-- One line for a refusal message. present: the caller saw another player (the apply gate): before this module's
-- next read the decision is PENDING, never SOLO.
function M.describe(present)
    local d=M.decision()
    if present and d.code=='SOLO'then
        d={allowed=false,code='PENDING',reason='another player is present; the lobby members\' '..M.KEY..' values are not '
            ..'read yet'}
    end
    return ('BEAM CONVERSION SYNC: %s (%s: %s)'):format(d.allowed and'ALLOWED'or'REFUSED',d.code,d.reason)
end

local function publish_step()
    local S=st()
    if not S.dirty then return end
    S.dirty=false
    local value,why=M.value()
    if not value then
        if why then say('the conversion set cannot be published ('..tostring(why)..'): other Runtimes see no value, '
            ..'which they treat as no Runtime')end
        return
    end
    S.published=value
    log(('posting seq %d: %s (%s)'):format(S.seq,#S.entries>0 and table.concat(S.names,', ')or'nothing converted',
        value))
    local result=channel.publish(value,M.BY,M.KEY)
    if result and(result.status=='refused'or result.status=='failed')then
        say(('post seq %d %s (%s: %s)'):format(S.seq,result.status,tostring(result.code),tostring(result.reason)))
    end
end

local NOTICE={title='BEAM CONVERSION: ANOTHER PLAYER',
    rule='A beam-converted weapon type spawned by this machine crashes the converting player\'s game.',
    advice='Do not carry, call in, drop or pick up these weapons while that player is in the lobby.'}
M.NOTICE=NOTICE

local function warn_other(peer,d)
    local names,seen={},{}
    for _,e in ipairs(d.entries)do
        local name=M.weapon_of(e.resource)or('resource '..e.resource)
        if not seen[name]then seen[name]=true;names[#names+1]=name end
    end
    table.sort(names)
    local text=table.concat(names,', ')
    log(('WARNING: member %s has %s converted to Trident beams. A weapon of that type that THIS machine spawns (carried, '
        ..'called in, dropped or picked up) is built on their machine without its ProjectileWeapon and CRASHES THEIR '
        ..'GAME. Do not use %s while they are in the lobby (docs/beam-conversion.md "Multiplayer")'):format(peer,text,
        #names==1 and'it'or'them'))
    pcall(function()
        require('hd2runtime/runtime/matchmaking_safety').notice(NOTICE.title,'Another player has '..text..' converted.',
            NOTICE.rule,NOTICE.advice)
    end)
end

-- Every POLL_EVERY s: the local set handed to the channel when it changed, and every other member read.
local function poll_step()
    local S=st()
    publish_step()
    local world=world_module.open()
    if not world then return end
    local lobby=channel.lobby(world)          -- reads only: nothing is called outside a joined lobby
    if not lobby or#lobby.members<2 then
        if next(S.members)then S.members={};log('solo: no other lobby member')end
        S.decision=nil
        return
    end
    local p=channel.poll(world,{key=M.KEY})
    if not p then return end
    local present={}
    for _,m in ipairs(p.lobby.members)do present[m.peer]=true end
    for peer in pairs(S.members)do
        if not present[peer]then S.members[peer]=nil;log('member '..peer..' left')end
    end
    local local_digest=M.digest()
    local mine=S.ever                         -- this machine applied a conversion in this session: it logs the lobby
    for _,entry in ipairs(p.values)do
        local m=S.members[entry.peer]
        if not m then m={first_seen=S.clock};S.members[entry.peer]=m end
        m.host=entry.peer==p.lobby.host_peer
        local value=entry.value
        if value==nil and entry.error then value='\1'end      -- unreadable / not printable: malformed
        local state,reason,d=M.member_state(value,local_digest,m.first_seen,S.clock)
        local key=state..'|'..tostring(reason)
        if m.key~=key then
            m.key,m.state,m.reason=key,state,reason
            if mine or(d and#d.entries>0)or m.logged then
                m.logged=true
                log(('member %s%s: %s (%s)'):format(entry.peer,m.host and' (host)'or'',M.STATES[state],reason))
            end
        end
        if d and#d.entries>0 and m.warned~=d.digest then
            m.warned=d.digest
            warn_other(entry.peer,d)
        elseif d and#d.entries==0 then m.warned=nil end
    end
    local decision=M.decision()
    local text=decision.code..'|'..decision.reason
    if S.decision~=text then
        S.decision=text
        if mine then
            log(('decision %s (%s): %s; this machine\'s conversions: %s'):format(decision.allowed and'ALLOWED'or'REFUSED',
                decision.code,decision.reason,#S.names>0 and table.concat(S.names,', ')or'none (all restored)'))
        end
    end
end
M.poll_for_tests=poll_step

-- Attaches the watch (once). Started at load in the game (api/hd2.lua); idle (one timer) outside a lobby.
function M.start()
    local S=st()
    if S.watch and S.watch.status=='waiting'then return S.watch end
    local watch={status='waiting',perf_label='beam conversion sync'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        dt=type(dt)=='number'and dt>=0 and dt<10 and dt or 0
        S.clock=S.clock+dt
        S.acc=S.acc+dt
        if S.acc>=M.POLL_EVERY then
            S.acc=0
            local ok,why=pcall(poll_step)
            if not ok then say('read step failed: '..tostring(why))end
        end
    end
    S.watch=watch
    scheduler.attach(watch)
    return watch
end

-- Diagnostics: the local set, what was published, every member read and the decision.
function M.status()
    local S=st()
    local members={}
    for peer,m in pairs(S.members)do members[peer]={state=m.state,reason=m.reason,host=m.host}end
    return {version=M.version(),build=M.build(),catalogue=M.catalogue_hash(),seq=S.seq,digest=M.digest(),
        converted=S.names,entries=#S.entries,published=S.published,members=members,decision=M.decision(),
        running=S.watch~=nil and S.watch.status=='waiting'}
end
return M
