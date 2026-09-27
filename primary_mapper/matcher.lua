-- Deterministic player-weapon/attack-branch matcher. Scores are evidence points.
local M={}

local rules={
    standard_damage={weight=16,exact=true,high=true,label='standard damage',group='damage'},
    durable_damage={weight=14,exact=true,high=true,label='durable damage',group='damage'},
    ap_direct={weight=10,exact=true,high=true,label='AP direct',group='damage'},
    ap_slight={weight=7,exact=true,high=true,label='AP slight',group='damage'},
    ap_large={weight=7,exact=true,high=true,label='AP large',group='damage'},
    ap_extreme={weight=4,exact=true,label='AP extreme',group='damage'},
    projectile_velocity={weight=12,tolerance=2,high=true,label='velocity',group='projectile'},
    fire_rate={weight=8,tolerance=1,high=true,label='fire rate',group='weapon'},
    capacity={weight=8,exact=true,high=true,label='capacity',group='weapon'},
    projectile_mass={weight=5,tolerance=0.1,label='projectile mass',group='projectile'},
    drag={weight=4,tolerance=0.01,label='drag',group='projectile'},
    gravity={weight=4,tolerance=0.01,label='gravity',group='projectile'},
    demolition={weight=6,exact=true,label='demolition',group='damage'},
    stagger={weight=6,exact=true,label='stagger',group='damage'},
    push_force={weight=5,exact=true,label='push force',group='damage'},
    pellet_count={weight=10,exact=true,high=true,label='pellet count',group='projectile'},
}
local order={'standard_damage','durable_damage','ap_direct','ap_slight','ap_large','ap_extreme',
    'projectile_velocity','fire_rate','capacity','projectile_mass','drag','gravity',
    'demolition','stagger','push_force','pellet_count'}
local structural={'projectile_type','damage_type','crosshair_type'}

local function display(value)
    if type(value)=='number'then return string.format('%.9g',value)end
    return tostring(value)
end
local function compare(actual,expected,rule)
    if rule.exact then return actual==expected end
    return math.abs(actual-expected)<=rule.tolerance
end
local function blank()
    return {score=0,matched={},mismatched={},compared=0,
        highValueMatches=0,highValueMismatches=0}
end
local function append(target,source)
    target.score=target.score+source.score;target.compared=target.compared+source.compared
    target.highValueMatches=target.highValueMatches+source.highValueMatches
    target.highValueMismatches=target.highValueMismatches+source.highValueMismatches
    for _,value in ipairs(source.matched)do target.matched[#target.matched+1]=value end
    for _,value in ipairs(source.mismatched)do target.mismatched[#target.mismatched+1]=value end
end
local function score_fields(runtime,expected,group)
    local result=blank()
    for _,field in ipairs(order)do
        local rule=rules[field]
        if rule.group==group then
            local actual,want=runtime[field],expected[field]
            if type(actual)=='number'and type(want)=='number'then
                result.compared=result.compared+1
                if compare(actual,want,rule)then
                    result.score=result.score+rule.weight
                    if rule.high then result.highValueMatches=result.highValueMatches+1 end
                    result.matched[#result.matched+1]=rule.label..'='..display(actual)
                else
                    result.score=result.score-rule.weight*2
                    if rule.high then result.highValueMismatches=result.highValueMismatches+1 end
                    result.mismatched[#result.mismatched+1]=rule.label..' runtime='..display(actual)
                        ..' wiki='..display(want)
                end
            end
        end
    end
    return result
end
local function branch_before(a,b)
    if a.score~=b.score then return a.score>b.score end
    if #a.mismatched~=#b.mismatched then return #a.mismatched<#b.mismatched end
    if a.compared~=b.compared then return a.compared>b.compared end
    if tostring(a.attack.name)~=tostring(b.attack.name)then
        return tostring(a.attack.name)<tostring(b.attack.name)
    end
    return (a.attack.index or 0)<(b.attack.index or 0)
end
local function compatible(runtime_kind,attack)
    return runtime_kind==nil or runtime_kind==attack.kind
end
local function best_branch(runtime,attacks,group)
    local ranked={}
    for _,attack in ipairs(attacks)do
        local scored=score_fields(runtime,attack,group);scored.attack=attack
        if scored.compared>0 then ranked[#ranked+1]=scored end
    end
    table.sort(ranked,branch_before)
    return ranked[1]
end
local function unresolved(runtime,result)
    local found={}
    for _,text in ipairs(result.matched)do found[text:match('^(.-)=')]=true end
    for _,text in ipairs(result.mismatched)do found[text:match('^(.-) runtime=')]=true end
    local missing={}
    for _,field in ipairs(structural)do
        if runtime[field]~=nil then missing[#missing+1]=field..' (runtime structural ID; no wiki ID)'end
    end
    for _,field in ipairs(order)do
        local rule=rules[field]
        if type(runtime[field])=='number'and not found[rule.label]then missing[#missing+1]=field end
    end
    return missing
end
local function score_weapon(runtime,weapon)
    local runtime_kind=runtime.attack_kind or runtime.attackKind
    local runtime_slot=runtime.weapon_slot or runtime.weaponSlot
    local attacks={}
    for _,attack in ipairs(weapon.attacks or {})do
        if compatible(runtime_kind,attack)then attacks[#attacks+1]=attack end
    end
    local result={name=weapon.name,slot=weapon.slot or'primary',category=weapon.category,
        score=-100000,matched={},mismatched={},unresolvedFields={},compared=0,
        highValueMatches=0,highValueMismatches=0,structurallyCompatible=#attacks>0,
        compatibleAttackKind=runtime_kind,compatibleWeaponSlot=runtime_slot}
    if runtime_slot~=nil and weapon.slot~=nil and runtime_slot~=weapon.slot then
        result.structurallyCompatible=false
        result.incompatibility='runtime weapon slot '..tostring(runtime_slot)
            ..' differs from catalog slot '..tostring(weapon.slot)
        return result
    end
    if #attacks==0 then
        result.incompatibility='runtime attack kind '..tostring(runtime_kind)..' absent from catalog weapon'
        return result
    end
    result.score=0
    local weapon_fields={fire_rate=weapon.fire_rate,capacity=weapon.capacity}
    if weapon_fields.fire_rate==nil and weapon.primary then weapon_fields.fire_rate=weapon.primary.fire_rate end
    if weapon_fields.capacity==nil and weapon.primary then weapon_fields.capacity=weapon.primary.capacity end
    append(result,score_fields(runtime,weapon_fields,'weapon'))
    local damage=best_branch(runtime,attacks,'damage')
    local projectile=best_branch(runtime,attacks,'projectile')
    if damage then append(result,damage);result.matchedDamageBranch=damage.attack.name end
    if projectile then append(result,projectile);result.matchedProjectileBranch=projectile.attack.name end
    if damage and projectile and damage.attack.name==projectile.attack.name then
        result.matchedAttackBranch=damage.attack.name;result.branchMode='single'
    elseif damage and projectile then result.branchMode='composite'
    elseif damage then result.matchedAttackBranch=damage.attack.name;result.branchMode='single'
    elseif projectile then result.matchedAttackBranch=projectile.attack.name;result.branchMode='single'
    else result.branchMode='weapon_only'end
    result.unresolvedFields=unresolved(runtime,result)
    return result
end
local function before(a,b)
    if a.score~=b.score then return a.score>b.score end
    if #a.mismatched~=#b.mismatched then return #a.mismatched<#b.mismatched end
    if a.compared~=b.compared then return a.compared>b.compared end
    return a.name<b.name
end
local function plausible(value)
    return value.structurallyCompatible and value.score>=15 and value.highValueMatches>=1
end

function M.rank(runtime,dataset,limit)
    assert(type(runtime)=='table'and type(dataset)=='table'and type(dataset.weapons)=='table',
        'matcher requires runtime fields and wiki dataset')
    local ranked={}
    for _,weapon in ipairs(dataset.weapons)do ranked[#ranked+1]=score_weapon(runtime,weapon)end
    table.sort(ranked,before)
    local top=ranked[1];local credible={}
    if top and plausible(top)then
        for _,value in ipairs(ranked)do
            if plausible(value)and top.score-value.score<12 then
                value.credible=true;credible[#credible+1]=value.name
            end
        end
    end
    local competitor=ranked[2]
    local margin=top and top.score-(competitor and competitor.score or 0)or 0
    local state='UNMATCHED'
    if top and plausible(top)then
        if #credible>1 then state='AMBIGUOUS'
        elseif #top.mismatched==0 and top.compared>=5 and top.highValueMatches>=3
            and top.score>=50 and margin>=12 then state='EXACT'
        elseif top.highValueMismatches==0 and top.compared>=4 and top.highValueMatches>=2
            and top.score>=30 and margin>=10 then state='STRONG'
        else state='AMBIGUOUS'end
    end
    local trimmed={}
    for index=1,math.min(limit or 5,#ranked)do trimmed[index]=ranked[index]end
    return {status=state,scoreMargin=margin,rankedWikiMatches=trimmed,
        allWikiMatches=ranked,credibleWikiIdentities=credible}
end

M.rules=rules;M.order=order;M.plausible=plausible
return M
