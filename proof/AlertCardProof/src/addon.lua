local hd2=require('mods/skyeshade/hd2runtime')
-- AlertCardProof 0.1.0: THE CUSTOM STRATAGEM ALERT CARD (runtime/stratagem_alert.lua, HD2Runtime 0.30.2). Development
-- only: shows the card's looks on demand with sample text, so it can be judged without a lobby that really fails.
-- Nothing of the game is written. The real cards come from the readiness check aboard the ship, the DISABLED warning
-- and the text fallback.
--   Ctrl+F9   CHECK BEFORE LAUNCH (amber): two problems with their fixes
--   Ctrl+F10  WILL FAIL (red): five problems (three listed, "+2 more in the HD2Runtime log")
--   Ctrl+F11  READY (green): the short confirmation
-- Each card shows for 14 s (5 s for READY) with a shrinking bar along its bottom edge.
local mod=hd2.mod()
local BUILD='0.1.0 ALERT CARD'
local card=require('hd2runtime/runtime/stratagem_alert')
mod:log('AlertCardProof '..BUILD..' BUILD: aboard the ship (and again in a mission) press Ctrl+F9 (amber), Ctrl+F10 '
    ..'(red) and Ctrl+F11 (green). The card shows at the top right. Report: is it visible, readable, well placed, '
    ..'and does it cover anything of the game?')

local function post(alert)
    local ok,queued=pcall(card.post,alert,true)
    mod:log(('posted %s (%s): queued %s; status visible=%s gui_disabled=%s'):format(alert.tag,alert.severity,
        tostring(ok and queued),tostring(card.status().visible),tostring(card.status().gui_disabled)))
end
hd2.input.bind('alert_card_proof.warn',{key='Ctrl+F9',on_press=function()
    post({key='proof',severity='warn',title='Custom stratagems',tag='Check before launch',
        items={{line='1 player without HD2Runtime: your custom slots will be locked.',
                fix='Fix: everyone needs the same mods (or play Friends Only), or pick vanilla.'},
               {line='Pelican Close Air Support: no free member of its carrier group (all Eagle carriers are taken).',
                fix='Fix: free its carrier or pick another custom stratagem.'}},
        footer='Shown again every minute while it stands.'})
end})
hd2.input.bind('alert_card_proof.fail',{key='Ctrl+F10',on_press=function()
    local items={}
    for i=1,5 do
        items[i]={line=('Sample problem %d: this custom stratagem would be locked for the mission.'):format(i),
            fix='Fix: a sample fix line, long enough to show how the card wraps a second line of text.'}
    end
    post({key='proof',severity='fail',title='Custom stratagems',tag='Will fail',items=items,
        footer='Launching anyway: these slots stay locked for the mission.'})
end})
hd2.input.bind('alert_card_proof.ok',{key='Ctrl+F11',on_press=function()
    post({key='proof',severity='ok',title='Custom stratagems',tag='Ready',seconds=5,
        items={{line='The problem is fixed: your selected custom stratagems will work.'}}})
end})
mod:log('loaded ('..BUILD..'): Ctrl+F9 / Ctrl+F10 / Ctrl+F11')
