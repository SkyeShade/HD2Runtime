local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for hd2.status (docs/event-scripting.md#status-effects). When you damage an enemy, Runtime requests the
-- game's own Fire status on it through the game's status request queue (the path the game's stun weapons use). The
-- amount is buildup: 100 is the value the game's own stun requests use; the status starts once the enemy's buildup
-- reaches its susceptibility, and its strength and duration are the game's own. Host only, in a mission; at most
-- one request per enemy every 3 seconds.
--
-- What to check: enemies you hit with a non-fire weapon catch fire (flames, burn damage over time, fire panic on
-- enemies that have it); enemies immune to fire do not; the log names each request.
assert(hd2.status and hd2.events,'StatusActionTest needs an HD2Runtime build with hd2.status')
local mod=hd2.mod()
local STATUS='fire'
local last={}

hd2.events.on('mission_started',function()last={}end,{id='reset'})
hd2.events.on('entity_damaged',function(event)
    if not event.local_attacker or not event.enemy then return end
    local id=event.entity_id
    if last[id]then return end
    last[id]=true
    hd2.after(3,function()last[id]=nil end,{scope='mission'})
    local action=hd2.status.apply(event.entity,STATUS,{buildup=100})
    mod:log(STATUS..' on '..tostring(event.semantic_id)..' ('..id..'): '..action.status
        ..(action.code and(' '..action.code..': '..action.reason)or''))
end,{id='burn'})

mod:log('loaded: hit an enemy in a mission (as host); it should catch fire')
