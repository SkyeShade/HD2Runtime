local hd2=require('mods/skyeshade/hd2runtime')
-- WeaponVariantShowcase 0.1.0: the live test of weapon VARIANTS beyond the M-1000 Maxigun (docs/custom-stratagem-api.md
-- "weapon"; research/weapon-variants-F5FEE03DCFDB.json). Every support weapon with exclusively owned records and a
-- stratagem of its own can be a variant of ITSELF for one mission: its own stratagem row presents as the custom stratagem
-- and answers to its code, its own pod delivers it, and its type shows the custom name and icon and, for a weapon that
-- fires projectiles, another round of its own compatibility class. Restored aboard the ship.
--   AC-8N NAPALM AUTOCANNON       the AC-8 Autocannon firing the EAT-700's napalm round (explosive_shrapnel)
--   GR-8L LEVELLER RECOILLESS     the GR-8 Recoilless Rifle firing the EAT-411 Leveller's round (explosive_impact)
--   MG-206X ANTI-MATERIEL HMG     the MG-206 Heavy Machine Gun firing the APW-1 Anti-Materiel Rifle's round
--   LAS-98S RENAMED LASER CANNON  the LAS-98 Laser Cannon, name and icon only (a beam: no round), a SHARED type (world
--                                 loot also brings it: allow_shared; a found Laser Cannon is renamed too)
-- While a variant is selected, its vanilla weapon is blocked in the native picker; if anyone in the lobby brings the
-- vanilla weapon, the variant is unavailable (no fallback). Development only; solo host first.
local mod=hd2.mod()
local BUILD='0.1.0 WEAPON VARIANT SHOWCASE'
mod:log('WeaponVariantShowcase '..BUILD..': select up to four of AC-8N NAPALM AUTOCANNON, GR-8L LEVELLER RECOILLESS, '
    ..'MG-206X ANTI-MATERIEL HMG, LAS-98S RENAMED LASER CANNON in the custom panel (do NOT also bring the vanilla AC-8, '
    ..'GR-8, MG-206 or LAS-98), then a solo mission. Call each one and fire it: the pickup prompt and weapon panel show '
    ..'the custom name; the AC-8N fires napalm, the GR-8L the Leveller\'s big blast, the MG-206X anti-materiel rounds.')

local ICON=hd2.resources.image('variant_showcase')
local function variant(spec)
    hd2.custom_stratagem.register({
        id=spec.id,name=spec.name,name_cased=spec.name_cased,description=spec.description,icon=ICON,code=spec.code,
        carrier={group='weapon'},
        delivery={family='weapon',weapon=hd2.support_weapon(spec.weapon),round=spec.round and hd2.attack_output(spec.round),
            allow_shared=spec.allow_shared},
        on_delivered=function(ctx)
            local d=hd2.custom_stratagem.describe(spec.id)
            if not d then return end
            ctx:log(('DELIVERED %s: carrier %s (%s); carrier weapon %s; %d weapon(s) captured; OBSERVE: %s'):format(
                spec.id,d.carrier and d.carrier.name or'?',d.carrier and(d.carrier.condensed and'condensed'or('fallback: '
                ..tostring(d.carrier.fallback)))or'?',d.carrier_weapon and d.carrier_weapon.name or'?',
                #(ctx.weapons or{}),spec.observe))
        end,
    })
end

variant({id='showcase_ac8n',name='AC-8N NAPALM AUTOCANNON',name_cased='AC-8N Napalm Autocannon',
    description='An Autocannon loaded with the EAT-700\'s napalm rounds.',weapon='AC-8 Autocannon',
    round='EAT-700 Expendable Napalm',code={'left','up','down','right','left','up'},
    observe='every shell bursts into napalm fire (the EAT-700\'s round), not the autocannon\'s flak'})
variant({id='showcase_gr8l',name='GR-8L LEVELLER RECOILLESS',name_cased='GR-8L Leveller Recoilless',
    description='A Recoilless Rifle firing the EAT-411 Leveller\'s round.',weapon='GR-8 Recoilless Rifle',
    round='EAT-411 Leveller',code={'right','down','up','left','right','down'},
    observe='each rocket is the Leveller\'s (its much larger blast), the backpack and team reload as usual'})
variant({id='showcase_mg206x',name='MG-206X ANTI-MATERIEL HMG',name_cased='MG-206X Anti-Materiel HMG',
    description='A Heavy Machine Gun chambered for the Anti-Materiel Rifle\'s round.',weapon='MG-206 Heavy Machine Gun',
    round='APW-1 Anti-Materiel Rifle',code={'up','left','down','right','up','left'},
    observe='each bullet is the APW-1\'s round (its heavier hits and penetration), at the HMG\'s fire rate'})
variant({id='showcase_las98s',name='LAS-98S RENAMED LASER CANNON',name_cased='LAS-98S Renamed Laser Cannon',
    description='The Laser Cannon under a custom name and icon (a beam weapon: no round to change).',
    weapon='LAS-98 Laser Cannon',allow_shared=true,code={'down','right','up','left','down','right'},
    observe='the pickup prompt, map label and weapon panel say LAS-98S RENAMED LASER CANNON; the beam is unchanged'})
