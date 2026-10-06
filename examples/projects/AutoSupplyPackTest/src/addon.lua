local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the equipment reads and hd2.actions.resupply_from_pack (docs/player-equipment.md,
-- docs/research/player-equipment-F5FEE03DCFDB.md). An auto-consuming Supply Pack: when the weapon in your hands runs
-- low, your own B-1 Supply Pack uses one of its supplies on you, exactly as if you pressed the pack's own key (the
-- game's own self-use: the same animation, one supply spent, the same refill). The "auto" part is this mod; Runtime
-- only offers the reads and the one action.
--
-- What to check, in a mission, wearing a B-1 Supply Pack:
--   * empty your primary down to 1 spare magazine (or less): within half a second the Helldiver uses the pack on
--     itself; the pack's supply counter drops by one and the weapon's magazines refill;
--   * nothing happens while the weapon in hand has more spare magazines, or when the pack is empty;
--   * Alt+F10 logs what you hold and wear (primary, secondary, support, backpack with its supplies, throwables);
--   * Alt+F11 asks for one use at once (refused with NO_AMMO_NEEDED when nothing can be refilled).
-- Every request and refusal is logged with this banner.
local BANNER='AUTO SUPPLY PACK 0.1.0 BUILD'
assert(hd2.actions and hd2.actions.resupply_from_pack,
    'AutoSupplyPackTest needs an HD2Runtime build with hd2.actions.resupply_from_pack')
local mod=hd2.mod()
local LOW_SPARE_MAGAZINES=1      -- use the pack when the weapon in hand has at most this many spare magazines
local RETRY=3                    -- seconds before the next automatic attempt (the game's use takes about 2 s)

local function name(item)return item and(item.name or item.type)or'none'end
local function report(what)
    local me=hd2.local_player()
    if not me then mod:log(BANNER..': '..what..': no local player');return end
    local l,why=me:loadout()
    if not l then mod:log(BANNER..': '..what..': '..tostring(why));return end
    local pack=l.backpack
    local supplies=pack and pack.deposit and(' '..pack.deposit.amount..'/'..pack.deposit.capacity)or''
    local throwable=l.throwable and(name(l.throwable)..' x'..tostring(l.throwable.count))or'none'
    local held=me:held_weapon()
    local ammo=me:ammo()
    mod:log(BANNER..': '..what..': primary '..name(l.primary)..', secondary '..name(l.secondary)..', support '
        ..name(l.support)..', backpack '..name(pack)..supplies..', throwable '..throwable..'; in hand '..name(held)
        ..(held and(' ('..held.slot..')')or'')..(ammo and(', '..ammo.feed..' '..tostring(ammo.rounds)
        ..(ammo.spare_magazines and(' + '..ammo.spare_magazines..' spare')or''))or''))
end

-- Magazine-fed weapons only: a backpack-fed weapon needs its own backpack, so it is never carried with a Supply Pack.
local function low(ammo)return ammo.feed=='magazine'and ammo.spare_magazines<=LOW_SPARE_MAGAZINES end
local last_code
local function use(what)
    local me=hd2.local_player()
    if not me then return end
    local action=hd2.actions.resupply_from_pack(me)
    if action:requested()then
        last_code=nil
        mod:log(BANNER..': '..what..': Supply Pack used ('..action.supplies..'/'..action.capacity..' supplies before)')
    elseif action.code~=last_code or what~='auto'then
        last_code=action.code
        mod:log(BANNER..': '..what..' refused: '..tostring(action.code)..': '..tostring(action.reason))
    end
end

local clock,next_try=0,0
hd2.every(0.5,function()
    clock=clock+0.5
    if clock<next_try then return end
    local me=hd2.local_player()
    if not me then return end
    local pack=me:backpack()
    if not(pack and pack.supply_pack and pack.deposit and pack.deposit.amount>=1)then return end
    local ammo=me:ammo()
    if not(ammo and low(ammo))then return end
    next_try=clock+RETRY
    use('auto')
end,{id='auto_supply_pack.watch'})
hd2.input.bind('auto_supply_pack.report',{key='Alt+F10',on_press=function()report('Alt+F10')end})
hd2.input.bind('auto_supply_pack.use',{key='Alt+F11',on_press=function()use('Alt+F11')end})
mod:log(BANNER..': loaded; wear a B-1 Supply Pack in a mission and empty a weapon down to '..LOW_SPARE_MAGAZINES
    ..' spare magazine, or press Alt+F10 / Alt+F11')
