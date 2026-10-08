-- The carrier WEAPON pool of expendable custom stratagems (development; docs/custom-stratagem-api.md "expendable").
-- Read-only: it chooses, it writes nothing.
--
-- An expendable custom stratagem delivers a mission-scoped clone of its donor weapon on an unused vanilla weapon type of
-- the donor's expendable component class (runtime/weapon_clone.lua; for the EAT-17: the EAT-700, then the EAT-411, the
-- research order). The pool is the donor's CLONE-COMPATIBLE lifecycle members only; members() lists every expendable
-- lifecycle weapon (the Commando and the Bullet Storm too) with its per-donor compatibility. A candidate is taken by:
--   * a NATIVE pick of any lobby member (its stratagem in someone's loadout: that player brings that weapon);
--   * another expendable custom stratagem's claim (never two definitions on one carrier weapon type).
-- Claims are made in a fixed order (the claiming definitions sorted by id, the pool in its order), from data every
-- machine of a lobby holds alike (the synced picks, every member's record as first seen), so every machine computes the
-- same carrier weapon for the same id. When every candidate is taken, the DONOR ITSELF is the pool's last member where
-- the definition can use it (its claim's `fallback`: the user's rule of 2026-10-06, e.g. the regular EAT-17 when the
-- EAT-700 and the EAT-411 are both picked): {weapon = the donor, donor_self = true, taken = why}. The donor's type is
-- never cloned (the EAT-17 is in the world loot table): its own native pod delivers it and only the call's own launchers
-- change, per projectile. Since the user's rule of 2026-10-06 (later the same day: no fallback that exists beside a
-- native pick) it is claimed and reserved like every other member: a native pick of the donor takes it, two definitions
-- never share it, and as the last viable carrier it is blocked in the native picker. Otherwise the definition is
-- UNAVAILABLE, with who took each candidate.
local catalog=require('hd2runtime/domains/stratagem_authoring')
local clone=require('hd2runtime/runtime/weapon_clone')
local M={}

local function stable_id(name)
    local e=catalog.stratagems[name]
    return e and e.root and e.root.id
end
M.stable_id=stable_id

-- The expendable LIFECYCLE members (runtime/weapon_clone.lua): every support weapon that discards itself when empty and
-- is never reloadable, whatever its vanilla round count, in order: {{name, stable_id, entity, clone_class (the members
-- sharing its component set), pod_capacity, rounds, compatible = {[donor] = true | reason}}}. A member is a carrier
-- for a donor only where compatible[donor] is true (exactly that donor's pool below); the others are expendable but
-- carry no type-level clone of it (e.g. the Commando's extra guidance components, the Bullet Storm's missing
-- Backblast).
function M.members()
    local out={}
    for k,name in ipairs(clone.expendables())do
        local m=clone.expendable(name)
        local compatible={}
        for donor in pairs(m.clone)do
            local ok,why=clone.compatible(donor,name)
            compatible[donor]=ok or why
        end
        out[k]={name=name,stable_id=stable_id(name),entity=m.entity,clone_class=clone.clone_class(name),
            pod_capacity=m.podCapacity,rounds=m.rounds,compatible=compatible}
    end
    return out
end
-- Whether a lifecycle member can carry a donor's clone: true, or false and why.
function M.compatible(donor,carrier)return clone.compatible(donor,carrier)end

-- The pool of a donor: {{name, stable_id, entity}} in order, or nil. variant = true: a variant's (the weapon itself).
function M.pool(donor,variant)
    local list=clone.pool(donor,variant)
    if not list then return nil end
    local out={}
    for k,name in ipairs(list)do
        local c=clone.carrier(name)
        out[k]={name=name,stable_id=stable_id(name),entity=c and c.entity}
    end
    return out
end

local function who_text(list)
    if not list or#list==0 then return'a lobby member\'s loadout'end
    return table.concat(list,', ')
end

-- A pool weapon's pod capacity: its own stratagem's exclusive rack's usable slots (runtime/carrier_pod.lua).
function M.capacity(name)return require('hd2runtime/runtime/carrier_pod').capacity(name)end

-- The donor-self assignment of a definition whose clone carriers are all taken (taken: the reason text).
local function donor_self(donor,taken)
    return {weapon=donor,stable_id=stable_id(donor),donor_self=true,taken=taken}
end
M.donor_self=donor_self
-- Why the donor itself is taken now (nil: free): a native pick, or another definition's claim.
local function donor_taken(donor,present,claims,who)
    local sid=stable_id(donor)
    if sid and present[sid]then return('the regular %s (picked natively: %s)'):format(donor,who_text(who and who[sid]))end
    if claims[donor]then return('the regular %s (the carrier weapon of the custom stratagem %s)'):format(donor,claims[donor])end
    return nil
end

-- defs: {{id, donor, slots, fallback}} (the expendable definitions that claim now; any order; slots: the pod items it
-- needs, nil: the vanilla pod; fallback: true when it may fall back to the donor itself). present: {[stable id] = true}
-- (every
-- native pick this machine can read). opts.who: {[stable id] = {'your loadout', 'peer ...'}} (for the reasons).
-- Returns {assignments = {[id] = {weapon, stable_id, entity} or a donor-self one}, refused = {[id] = reason}, claims =
-- {[weapon] = id}, order = {ids}}.
function M.allocate(defs,present,opts)
    opts=opts or{}
    present=present or{}
    local list={}
    for _,d in ipairs(defs or{})do list[#list+1]=d end
    table.sort(list,function(a,c)return a.id<c.id end)
    local out={assignments={},refused={},claims={},order={}}
    local seen={}
    for _,d in ipairs(list)do
        if not seen[d.id]then
            seen[d.id]=true
            out.order[#out.order+1]=d.id
            local pool=M.pool(d.donor,d.variant)
            if not pool then
                out.refused[d.id]=tostring(d.donor)..' has no reviewed expendable clone class'
            else
                local chosen
                local taken={}
                for _,c in ipairs(pool)do
                    if not chosen then
                        local capacity=d.slots and M.capacity(c.name)
                        if present[c.stable_id]then
                            taken[#taken+1]=('%s (picked natively: %s)'):format(c.name,who_text(opts.who and
                                opts.who[c.stable_id]))
                        elseif capacity and capacity<d.slots then
                            taken[#taken+1]=('%s (its pod holds at most %d, %d asked)'):format(c.name,capacity,d.slots)
                        elseif out.claims[c.name]then
                            taken[#taken+1]=('%s (the carrier weapon of the custom stratagem %s)'):format(c.name,
                                out.claims[c.name])
                        else
                            chosen=c
                        end
                    end
                end
                local donor_why=not chosen and d.fallback and donor_taken(d.donor,present,out.claims,opts.who)
                if donor_why then taken[#taken+1]=donor_why end
                if chosen then
                    out.claims[chosen.name]=d.id
                    out.assignments[d.id]={weapon=chosen.name,stable_id=chosen.stable_id,entity=chosen.entity}
                elseif d.fallback and not donor_why then
                    out.claims[d.donor]=d.id
                    out.assignments[d.id]=donor_self(d.donor,table.concat(taken,'; '))
                else
                    out.refused[d.id]=('UNAVAILABLE: every carrier weapon of the %s\'s expendable class is taken: %s')
                        :format(d.donor,table.concat(taken,'; '))
                end
            end
        end
    end
    return out
end

-- Whether a definition (id, donor) would get a carrier weapon if it claimed now, beside `claims` (the definitions that
-- claim: {{id, donor, slots}}; the definition itself may be among them): nil (available) or the reason. opts.slots: the
-- pod items it needs (a pool weapon whose pod holds fewer is not a candidate); opts.fallback: it may fall back to the
-- donor itself (then nil and a donor-self assignment when every candidate is taken).
-- The other claims are allocated first and the definition takes what remains: definitions of one donor share one pool,
-- so whenever a candidate remains every claimant gets one in the id-ordered allocation too (the order only decides who
-- gets which).
function M.unavailable(id,donor,present,claims,opts)
    local others={}
    for _,d in ipairs(claims or{})do if d.id~=id then others[#others+1]=d end end
    local a=M.allocate(others,present,opts)
    local pool=M.pool(donor,opts and opts.variant)
    if not pool then return tostring(donor)..' has no reviewed expendable clone class'end
    local taken={}
    local slots=opts and opts.slots
    for _,c in ipairs(pool)do
        if present and present[c.stable_id]then
            taken[#taken+1]=('%s (picked natively: %s)'):format(c.name,who_text(opts and opts.who and opts.who[c.stable_id]))
        elseif slots and M.capacity(c.name)<slots then
            taken[#taken+1]=('%s (its pod holds at most %d, %d asked)'):format(c.name,M.capacity(c.name),slots)
        elseif a.claims[c.name]then
            taken[#taken+1]=('%s (the carrier weapon of the custom stratagem %s)'):format(c.name,a.claims[c.name])
        else
            return nil,{weapon=c.name,stable_id=c.stable_id,entity=c.entity}
        end
    end
    if opts and opts.fallback then
        local why=donor_taken(donor,present or{},a.claims,opts.who)
        if not why then return nil,donor_self(donor,table.concat(taken,'; '))end
        taken[#taken+1]=why
    end
    return('UNAVAILABLE: every carrier weapon of the %s\'s expendable class is taken: %s'):format(donor,
        table.concat(taken,'; '))
end
return M
