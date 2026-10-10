-- Beam conversion sync (DEVELOPMENT; docs/beam-conversion.md "Multiplayer"; research/docs/beam-conversion-mp-sync-
-- F5FEE03DCFDB.md, research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md). Not exported to mods.
--
-- Each Runtime publishes the beam conversions applied on it, and reads every other lobby member's, through the game's
-- own PlayFab lobby member data (runtime/peer_channel.lua, the key `hd2bc`, the hd2bc/2 grammar of runtime/beam_
-- conversion_sync_protocol.lua; the channel's rate limits are shared with `hd2rt` and `hd2as`).
--
-- What multiplayer allows, by layout (research, CONFIRMED and pinned):
--   * SWAP (ProjectileWeapon swapped out): never. The game applies a remote weapon's replicated state through a case
--     chosen by its network type alone, and every convertible type's case calls the ProjectileWeapon apply
--     unconditionally; a weapon built from a swapped list has no ProjectileWeapon instance, so the converted machine
--     crashes when another player's weapon of that type spawns, whatever that player converted.
--   * ADD (ProjectileWeapon kept, BeamWeapon added): no crash in any combination (every machine keeps the instance).
--     But every machine simulates every player's beam from the replicated trigger, and the target's owner lowers zone
--     health and shields from the beams IT simulates (health itself stays with the shooter). So every machine must
--     convert the weapon the SAME way: a weapon's conversion is allowed with other players only when every other member
--     is a Runtime of this version, build and catalogue whose posted set holds the identical entry for each of its
--     roots (layout, path, record digest, rows digest). A member without the Runtime is never compatible.
--
-- What it does:
--   * PUBLISH: once this machine applied a conversion in this session, its set: per converted root the resource, the
--     layout, the path, a digest of its BeamWeapon record and of its own rows (both pair-independent), with this
--     Runtime's version, the game build and the catalogue hash. After the last restore the empty set (`-`) is
--     published, so the lobby never keeps a stale set. The channel posts it again in every lobby this machine joins.
--   * READ: in the Runtime's own update, every M.POLL_EVERY s and only in a joined lobby of at least 2 members, every
--     other member's `hd2bc` value. Per member: match | mismatch | incompatible | malformed | pending (no value yet,
--     within M.PENDING_WINDOW s of first seeing it: the channel's own first post waits 10-20 s) | no_runtime; and,
--     when it posted a value, its entries and when they last changed.
--   * DECIDE: M.allow_apply(entries) for an add-layout apply or settings change in a lobby (runtime/beam_conversion.lua
--     gates); M.keep(...) for the lobby watch (runtime/beam_conversion_watch.lua): keep an add conversion while every
--     member holds it identically or is still pending, or while a Runtime member's set changed less than M.GRACE s
--     ago (it may be converging); otherwise restore it (when idle).
--   * WARN THE OTHER SIDE: a member whose set holds SWAP conversions has a game that crashes when THIS machine spawns
--     a weapon of one of those types; a member whose add conversions differ from this machine's is out of step (beams
--     on one machine, bullets on the other). Loud log lines and the Runtime's notice name the weapons.
--   * LOG: `BEAM CONVERSION SYNC:` lines for the posted set, every member state change and the decision.
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
M.GRACE=30
-- Builds on which the ADD layout is proven safe with other players (research/docs/beam-conversion-add-layout-
-- F5FEE03DCFDB.md: the remote apply finds ProjectileWeapon; identical conversions simulate identical beams). The swap
-- layout is safe on none.
M.ADD_LAYOUT_SAFE={F5FEE03DCFDB=true}
M.STATES={match='match',mismatch='mismatch',incompatible='incompatible',malformed='malformed',pending='pending',
    no_runtime='no runtime'}
-- The order a refusal names its reason in: what a member lacks first.
local ORDER={'no_runtime','malformed','incompatible','mismatch','pending'}
local CODE={no_runtime='NO_RUNTIME',malformed='MALFORMED',incompatible='INCOMPATIBLE',mismatch='MISMATCH',
    pending='PENDING'}

local KEY='HD2RuntimeBeamConversionSyncV2'   -- survives a module reload, as the conversions do
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
-- with its layout, record and roots, and the borrowed pairs in research order.
function M.catalogue_hash()
    if not catalogue then
        local lines={'hd2bc/2','build '..tostring(C.source and C.source.build),'trident '..tostring(C.trident.recordHex)}
        for _,w in ipairs(C.weapons)do
            local roots={}
            for _,root in ipairs(w.roots or{})do roots[#roots+1]=root.resource..(root.add and('+'..root.add.listHex)or'')end
            lines[#lines+1]=('%s|%s|%s|%s|%s'):format(w.name,tostring(w.record),tostring(w.supported),
                tostring(w.layout),table.concat(roots,','))
        end
        for i,p in ipairs(C.rows and C.rows.pairs or{})do lines[#lines+1]=('pair %d %s/%s'):format(i,
            tostring(p.beamType),tostring(p.damageInfo))end
        catalogue=fnv1a(table.concat(lines,'\n'))
    end
    return catalogue
end
-- The weapon name a converted root resource (16 hex digits) belongs to.
function M.weapon_of(resource)return BY_RESOURCE[tostring(resource):upper()]end

-- The rows digest of own rows, or the "no own rows" value when they hold exactly the Trident's (a weapon whose own
-- rows went back to the Trident's values fires as one that never had any). Pure.
local TRIDENT_ROWS
function M.rows_digest(beam,damage)
    if not TRIDENT_ROWS then
        local unhex=require('hd2runtime/core/bytes').unhex
        TRIDENT_ROWS=protocol.rows_digest(unhex(C.rows.tridentBeamHex),unhex(C.rows.tridentDamageHex))
    end
    local digest=protocol.rows_digest(beam,damage)
    if digest==TRIDENT_ROWS then return protocol.ZERO end
    return digest
end

-- The entries one weapon posts for its roots: layout ('add' | 'swap'), path ('o' | 's'), record bytes, own rows
-- (beam, damage) or nil. Pure.
function M.weapon_entries(w,layout,path,record,beam,damage)
    local out={}
    local rec=protocol.record_digest(record)
    local rows=M.rows_digest(beam,damage)
    for _,root in ipairs(w.roots or{})do
        out[#out+1]={resource=root.resource:sub(3):upper(),layout=protocol.LAYOUT_CODE[layout],path=path,record=rec,
            rows=rows}
    end
    return out
end

-- The entries of a located beam conversion state (runtime/beam_conversion.lua locate): one per converted or orphaned
-- root of every converted or orphaned weapon. Pure.
function M.entries_of(s)
    local entries,names={},{}
    for name,W in pairs(s.weapons or{})do
        if W.state=='converted'or W.state=='orphaned'then
            names[#names+1]=name
            local layout=protocol.LAYOUT_CODE[W.layout or W.w.layout]or'w'
            local record,rows=protocol.ZERO,protocol.ZERO
            if W.state=='converted'then
                local bytes=s.path_mode=='owned'and W.record or require('hd2runtime/core/bytes').unhex(C.trident.recordHex)
                record=protocol.record_digest(bytes)
                if W.pair and s.rs and s.rs.pairs and s.rs.pairs[W.pair]then
                    local P=s.rs.pairs[W.pair]
                    rows=M.rows_digest(P.beam,P.damage)
                end
            end
            for _,R in ipairs(W.roots or{})do
                if R.state=='converted'or R.state=='orphaned'then
                    local orphan=R.state=='orphaned'
                    entries[#entries+1]={resource=R.root.resource:sub(3):upper(),layout=layout,
                        path=orphan and'x'or(s.path_mode=='owned'and'o'or's'),
                        record=orphan and protocol.ZERO or record,rows=orphan and protocol.ZERO or rows}
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

-- The local set as an hd2bc/2 value (nil before any conversion of this session), or nil, reason.
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

local function members_list(override)
    if override then return override end
    local S=st()
    local list={}
    for peer,m in pairs(S.members)do
        list[#list+1]={peer=peer,state=m.state,host=m.host,d=m.d,changed=m.changed}
    end
    table.sort(list,function(a,c)return a.peer<c.peer end)
    return list
end
local function holds(m,e)
    if not(m.d and(m.state=='match'or m.state=='mismatch'))then return false end
    for _,x in ipairs(m.d.entries)do if x.resource==e.resource then return protocol.same(x,e)end end
    return false
end
local function names_of(entries)
    local names,seen={},{}
    for _,e in ipairs(entries)do
        local n=M.weapon_of(e.resource)or('resource '..e.resource)
        if not seen[n]then seen[n]=true;names[#names+1]=n end
    end
    table.sort(names)
    return table.concat(names,', ')
end

-- The decision for an ADD-layout apply (or settings change) while other players are present. entries: the entries
-- this weapon will post (M.weapon_entries). input (tests): {members, build}. Returns {allowed, code, reason}.
function M.allow_apply(entries,input)
    input=input or{}
    local members=members_list(input.members)
    if#members==0 then
        return {allowed=false,code='PENDING',reason='another player is present; the lobby members\' '..M.KEY
            ..' values are not read yet'}
    end
    for _,e in ipairs(entries or{})do
        if e.layout~='a'then
            return {allowed=false,code='REMOTE_APPLY_UNSAFE',reason='the swap layout is solo only: a remote weapon of a '
                ..'swap-converted type crashes the converted machine at its network apply'}
        end
    end
    if not M.ADD_LAYOUT_SAFE[input.build or M.build()]then
        return {allowed=false,code='REMOTE_APPLY_UNSAFE',reason='the add layout is not proven on this game build'}
    end
    for _,state in ipairs(ORDER)do
        if state~='mismatch'then
            local which={}
            for _,m in ipairs(members)do
                if m.state==state then which[#which+1]=tostring(m.peer)..(m.host and' (host)'or'')end
            end
            if#which>0 then
                return {allowed=false,code=CODE[state],reason=('%s: %s'):format(M.STATES[state],table.concat(which,', '))}
            end
        end
    end
    local lacking={}
    for _,m in ipairs(members)do
        for _,e in ipairs(entries or{})do
            if not holds(m,e)then lacking[#lacking+1]=tostring(m.peer)..(m.host and' (host)'or'');break end
        end
    end
    if#lacking>0 then
        return {allowed=false,code='MISMATCH',reason=('%s %s not converted %s identically: a weapon converts in a lobby '
            ..'only when every other player already has the identical conversion'):format(table.concat(lacking,', '),
            #lacking==1 and'has'or'have',names_of(entries or{}))}
    end
    return {allowed=true,code='ALL_AGREE',reason='every other member holds the identical conversion of '..
        names_of(entries or{})}
end

-- The lobby watch's decision for this machine's ADD conversions: by_weapon = {[name] = {entries}}. Returns
-- {[name] = {keep, code, reason}}. Pure but for the clock (input.clock, input.members for tests).
function M.keep(by_weapon,input)
    input=input or{}
    local members=members_list(input.members)
    local clock=input.clock or st().clock
    local out={}
    for name,entries in pairs(by_weapon)do
        local verdict={keep=true,code='ALL_AGREE',reason='every member holds it identically'}
        for _,m in ipairs(members)do
            local ok=true
            for _,e in ipairs(entries)do if not holds(m,e)then ok=false end end
            if not ok then
                if m.state=='pending'then
                    if verdict.code=='ALL_AGREE'then
                        verdict={keep=true,code='PENDING',reason='waiting for '..tostring(m.peer)..'\'s value'}
                    end
                elseif(m.state=='match'or m.state=='mismatch')and m.changed and clock-m.changed<M.GRACE then
                    if verdict.code=='ALL_AGREE'then
                        verdict={keep=true,code='CONVERGING',reason=tostring(m.peer)..'\'s set changed '
                            ..math.floor(clock-m.changed)..' s ago (a Runtime may still convert it)'}
                    end
                else
                    verdict={keep=false,code=CODE[m.state]or'MISMATCH',reason=tostring(m.peer)..(m.host and' (host)'or'')
                        ..' does not hold the identical conversion ('..M.STATES[m.state]..')'}
                    break
                end
            end
        end
        out[name]=verdict
    end
    return out
end

-- The overall decision (status and logs): SOLO, the first agreement failure in ORDER, REMOTE_APPLY_UNSAFE when this
-- machine has swap conversions, else ALL_MATCH. Pure for tests (input.members, input.build, input.entries).
function M.decide(input)
    input=input or{}
    local members=input.members or members_list()
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
    for _,e in ipairs(input.entries or st().entries)do
        if e.layout~='a'then
            return {allowed=false,code='REMOTE_APPLY_UNSAFE',reason='this machine has swap-layout conversions (solo '
                ..'only): a remote weapon of a swap-converted type crashes this machine'}
        end
    end
    if not M.ADD_LAYOUT_SAFE[input.build or M.build()]then
        return {allowed=false,code='REMOTE_APPLY_UNSAFE',reason='the add layout is not proven on this game build'}
    end
    return {allowed=true,code='ALL_MATCH',reason='every member posts the same conversions (add layout)'}
end

-- Whether any lobby member was read (the watch keeps add conversions while nothing is known yet).
function M.members_known()return next(st().members)~=nil end
-- Tests only: the members as the poll would leave them ({peer = {state, value, host, changed}}).
function M.set_members_for_tests(members)
    local S=st()
    S.members={}
    for peer,m in pairs(members)do
        local state,reason,d=M.member_state(m.value,M.digest(),m.first_seen or S.clock,S.clock)
        S.members[peer]={state=m.state or state,reason=reason,d=d,host=m.host,changed=m.changed or S.clock,
            first_seen=m.first_seen or S.clock}
    end
end
function M.advance_for_tests(seconds)st().clock=st().clock+seconds end

-- The current decision from the last read (solo when no lobby of 2 or more was read).
function M.decision()return M.decide()end
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
    rule='A swap-converted weapon type spawned by this machine crashes the converting player\'s game; add-layout '
        ..'conversions that differ between players put beams on one screen and bullets on the other.',
    advice='Convert the same weapons the same way on every machine (add layout only), or do not use them together.'}
M.NOTICE=NOTICE

local function warn_other(peer,d)
    local swap,add={},{}
    for _,e in ipairs(d.entries)do
        local mine
        for _,x in ipairs(st().entries)do if x.resource==e.resource then mine=x end end
        if e.layout=='w'then swap[#swap+1]=e elseif not protocol.same(mine,e)then add[#add+1]=e end
    end
    if#swap>0 then
        local text=names_of(swap)
        log(('WARNING: member %s has %s converted with the SWAP layout. A weapon of that type that THIS machine spawns '
            ..'(carried, called in, dropped or picked up) is built on their machine without its ProjectileWeapon and '
            ..'CRASHES THEIR GAME. Do not use it while they are in the lobby (docs/beam-conversion.md "Multiplayer")')
            :format(peer,text))
        pcall(function()
            require('hd2runtime/runtime/matchmaking_safety').notice(NOTICE.title,'Another player has '..text..
                ' swap-converted.',NOTICE.rule,NOTICE.advice)
        end)
    end
    if#add>0 then
        log(('member %s has %s converted (add layout) differently from this machine: no crash, but their beams are '
            ..'bullets here and the other way round until both machines hold the identical conversion'):format(peer,
            names_of(add)))
    end
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
        m.d=d
        local their=d and d.digest or nil
        if their~=m.their then m.their=their;m.changed=S.clock end
        local key=state..'|'..tostring(reason)
        if m.key~=key then
            m.key,m.state,m.reason=key,state,reason
            if mine or(d and#d.entries>0)or m.logged then
                m.logged=true
                log(('member %s%s: %s (%s)'):format(entry.peer,m.host and' (host)'or'',M.STATES[state],reason))
            end
        end
        if d and#d.entries>0 and m.warned~=d.digest..'|'..tostring(local_digest)then
            m.warned=d.digest..'|'..tostring(local_digest)
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
        running=S.watch~=nil and S.watch.status=='waiting',protocol=protocol.PROTOCOL}
end
return M
