-- Carrier GROUPS (development; docs/custom-stratagem-api.md "Carrier groups"). Read-only: it classifies, it writes
-- nothing.
--
-- A group is a pool of vanilla carriers defined by STRUCTURE (what the carrier's beacon, row and pod are), never by a
-- fixed list: the allocator draws a custom stratagem's carrier from its group's members nobody in the lobby picked and
-- no other custom stratagem holds, ranked and logged (runtime/carrier_allocator.lua). A definition may name its group
-- (carrier = {group = 'support_pod', slots = 2}); else it gets its payload family's default. A group a payload cannot
-- use is refused at registration with the reason.
--
--   orbital      the catalogue family orbital, any beam colour (the Orbital EMS Strike's is blue): the beacon's own
--                delivery is replaced (nothing, a native barrage, a Pelican)
--   any_red      any red beam (row +0xD4 = 1, offensive), every family but Eagles (the discovery refuses them): for
--                payloads that deploy nothing needing an in-game item icon (a Runtime bombardment, a native barrage,
--                the Pelican CAS, a mod's own delivery)
--   any          any eligible carrier, any beam, any family: the same payloads as any_red
--   support      a blue support or backpack carrier whose beacon is REDIRECTED to a donor's vanilla pod (the donor's
--                rack delivers; the carrier's own pod never comes)
--   support_pod  a blue support or backpack carrier delivering its OWN pod: an exclusive rack (one owner, one consumer
--                row) rewritten for the mission (runtime/carrier_pod.lua); capacity = its usable rack slots (1 or 2);
--                each slot's role (weapon or backpack) takes its kind
--   expendable   the carrier WEAPON's own stratagem (EAT-700, EAT-411 for the EAT-17's class): its row presents as the
--                custom stratagem and answers to its code, its weapon type is the clone, its own pod delivers it
--                (condensed: ONE vanilla stratagem); a separate support carrier only when that stratagem cannot carry
--                a beacon (e.g. not owned). Its members are the expendable LIFECYCLE weapons (discarded when empty,
--                never reloadable: EAT-17, EAT-700, EAT-411, MLS-4X Commando, MGX-42 Bullet Storm;
--                runtime/weapon_carriers.lua members()); a member carries a donor's clone only when it is
--                clone-compatible with it (the donor's component class: the EAT-17's pool stays EAT-700, EAT-411)
--   weapon      a support weapon's OWN stratagem for its mission-scoped VARIANT (family 'weapon': every support weapon
--                with exclusively owned records and a stratagem of its own, 26 of 27; its own type is its only
--                carrier, `shared` names who else brings the type: then allow_shared): its row presents as the
--                custom stratagem and answers to its code, its own type is the variant, its own pod delivers it (with
--                its backpack); a separate support carrier throws the beacon only when that row cannot (e.g. not
--                owned). A lobby member bringing the weapon makes the variant unavailable; the selected variant blocks
--                the weapon in the native picker (no fallback)
--   sentry      the catalogue family sentry (blue): the donor sentry's pod by redirect
--   emplacement  the catalogue family emplacement: not used by a payload family yet
--   eagle        the catalogue family eagle (red, limited uses; the discovery's Eagle mode): the custom Eagle's own
local M={}
M.GROUPS={
    orbital={beacon='any',families={'orbital'},doc='an orbital carrier (any beam colour): its own delivery replaced'},
    any_red={beacon='offensive',doc='any red-beam carrier (no Eagle): its own delivery replaced; nothing native '
        ..'needs an in-game item icon'},
    any={beacon='any',doc='any eligible carrier: its own delivery replaced'},
    support={beacon='support',families={'support','backpack'},doc='a blue support/backpack carrier whose beacon is '
        ..'redirected to a donor\'s vanilla pod'},
    support_pod={beacon='support',families={'support','backpack'},pod=true,doc='a blue support/backpack carrier '
        ..'delivering its OWN exclusive pod, rewritten for the mission (capacity: its usable rack slots)'},
    expendable={beacon='support',families={'support','backpack'},weapon=true,doc='the carrier weapon\'s own '
        ..'stratagem: its beacon, its clone and its own pod (one vanilla stratagem); only when that stratagem cannot carry '
        ..'a beacon, a separate blue support/backpack carrier (the fallback, these families)'},
    weapon={beacon='support',families={'support','backpack'},weapon=true,variant=true,doc='the weapon\'s own '
        ..'stratagem for its variant: its beacon, its own type and its own pod (it has no other carrier); only when that '
        ..'stratagem cannot carry a beacon, a separate blue support/backpack carrier'},
    sentry={beacon='support',families={'sentry'},doc='a sentry carrier: the donor sentry\'s pod by redirect'},
    emplacement={beacon='any',families={'emplacement'},doc='an emplacement carrier (no payload family uses it yet)'},
    eagle={beacon='offensive',families={'eagle'},eagle=true,doc='an Eagle: the custom Eagle\'s own strike and uses'},
}
M.ORDER={'orbital','any_red','any','support','support_pod','expendable','weapon','sentry','emplacement','eagle'}
-- The groups each payload kind may use, its default first (runtime: the mod's own delivery; orbital: a Runtime
-- bombardment; orbital_native: the donor's own barrage).
M.PAYLOADS={
    runtime={'any_red','orbital','any','support'},
    orbital={'any_red','orbital','any','support'},
    orbital_native={'any_red','orbital','any','support'},
    pelican={'any_red','orbital','any','support'},
    support={'support'},
    pod={'support_pod'},
    expendable={'expendable'},
    weapon={'weapon'},
    sentry={'sentry'},
    eagle={'eagle'},
    silo={'support'},
}
local function list_text(t)return t and table.concat(t,'/')or'any'end

-- A definition's payload key (its family): runtime, orbital, orbital_native, pelican, support, pod, expendable, sentry,
-- eagle, silo.
function M.payload_key(kind,native)
    if kind=='orbital'and native then return'orbital_native'end
    return kind or'runtime'
end

-- The policy a group stands for: {beacon, prefer_families, allow_families} (the allocator's own policy fields).
function M.policy(group)
    local g=M.GROUPS[group]
    if not g then return nil end
    return {beacon=g.beacon,prefer_families=g.families,allow_families=g.families}
end

-- Checks a carrier spec's group fields against a payload: the group name (explicit or the default), or nil and why.
-- carrier: the definition's `carrier` table; payload: M.payload_key(...); count: the pod items (support_pod,
-- expendable) or nil.
function M.resolve(carrier,payload,count)
    local allowed=M.PAYLOADS[payload]or M.PAYLOADS.runtime
    local group=carrier.group
    if group==nil then
        -- The payload family's default, unless an explicit legacy policy asks for something the default cannot be (the
        -- legacy policy then keeps deciding the allocation exactly as before; its group is only a label).
        return allowed[1],'default'
    end
    if type(group)~='string'or not M.GROUPS[group]then
        return nil,'carrier.group must be one of '..table.concat(M.ORDER,', ')
    end
    local ok=false
    for _,g in ipairs(allowed)do ok=ok or g==group end
    if not ok then
        return nil,('carrier.group %s cannot carry a %s payload (it needs %s)'):format(group,payload,
            table.concat(allowed,' or '))
    end
    local g=M.GROUPS[group]
    if carrier.beacon~=nil and g.beacon~='any'and carrier.beacon~=g.beacon then
        return nil,('carrier.group %s throws a %s beacon; carrier.beacon %s contradicts it'):format(group,g.beacon,
            tostring(carrier.beacon))
    end
    if g.families then
        local set={}
        for _,f in ipairs(g.families)do set[f]=true end
        for _,key in ipairs({'prefer_families','allow_families'})do
            for _,f in ipairs(carrier[key]or{})do
                if not set[f]then
                    return nil,('carrier.%s lists %s, outside the group %s (%s)'):format(key,tostring(f),group,
                        list_text(g.families))
                end
            end
        end
    end
    if carrier.slots~=nil then
        if not g.pod and not g.weapon then
            return nil,'carrier.slots is a pod capacity: only the support_pod and expendable groups have one'
        end
        if type(carrier.slots)~='number'or carrier.slots%1~=0 or carrier.slots<1 or carrier.slots>8 then
            return nil,'carrier.slots must be a whole number 1..8'
        end
        if count and carrier.slots<count then
            return nil,('carrier.slots %d is below the pod\'s %d items'):format(carrier.slots,count)
        end
    end
    return group,'requested'
end

-- The label of a definition's group when it gave none (the legacy policies keep their allocation; this only names it).
function M.label(policy,payload)
    local allowed=M.PAYLOADS[payload]or M.PAYLOADS.runtime
    if#allowed==1 then return allowed[1]end
    local allow=policy.allow_families
    if allow and#allow==1 and allow[1]=='orbital'then return'orbital'end
    if policy.beacon=='offensive'then return'any_red'end
    if policy.beacon=='support'then return'support'end
    return'any'
end

-- The catalogue (the builder schema's and describe's): {{name, beacon, families, pod, weapon, eagle, doc, payloads
-- (the payload keys that may use it), defaults (those whose default it is)}}.
function M.catalogue()
    local out={}
    for _,name in ipairs(M.ORDER)do
        local g=M.GROUPS[name]
        local payloads,defaults={},{}
        for key,list in pairs(M.PAYLOADS)do
            for k,x in ipairs(list)do
                if x==name then
                    payloads[#payloads+1]=key
                    if k==1 then defaults[#defaults+1]=key end
                end
            end
        end
        table.sort(payloads)
        table.sort(defaults)
        out[#out+1]={name=name,beacon=g.beacon,families=g.families,pod=g.pod==true,weapon=g.weapon==true,
            eagle=g.eagle==true,doc=g.doc,payloads=payloads,defaults=defaults}
        -- The expendable group: its lifecycle members (disposable, never reloadable; research/docs/expendable-carriers-
        -- F5FEE03DCFDB.md), each with the donors it can carry a clone of (only those inside its component class).
        if g.weapon and not g.variant then
            local members={}
            for k,m in ipairs(require('hd2runtime/runtime/weapon_carriers').members())do
                local carries,refused={},{}
                for donor,v in pairs(m.compatible)do
                    if v==true then carries[#carries+1]=donor else refused[#refused+1]=donor..': '..tostring(v)end
                end
                table.sort(carries);table.sort(refused)
                members[k]={name=m.name,stable_id=m.stable_id,rounds=m.rounds,pod_capacity=m.pod_capacity,
                    clone_class=m.clone_class,carries=carries,refused=refused}
            end
            out[#out].members=members
        elseif g.variant then
            -- The weapon group: each variant host is its own (and only) carrier.
            local members={}
            local clone=require('hd2runtime/runtime/weapon_clone')
            local custom=require('hd2runtime/runtime/custom_stratagems')
            for k,name in ipairs(clone.variants())do
                local h=clone.variant(name)
                -- A host whose own pod is not an authored support delivery (the TX-41 Sterilizer: its rack item has no
                -- resolvable pickup name; the MS-11 Solo Silo: it delivers a deployable) cannot be registered: refused
                -- names why, and carries is empty.
                local d,why=custom.support_delivery(name)
                members[k]={name=name,stable_id=require('hd2runtime/runtime/weapon_carriers').stable_id(name),
                    clone_class={name},carries=d and{name}or{},refused=d and{}or{name..': '..tostring(why)},
                    shared=h.shared,round=h.round~=nil}
            end
            out[#out].members=members
        end
    end
    return out
end
return M
