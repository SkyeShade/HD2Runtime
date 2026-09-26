-- Deterministic field matcher. Scores are evidence points, never percentages.
local M={}

local rules={
    standard_damage={weight=16,exact=true,high=true,label='standard damage'},
    durable_damage={weight=14,exact=true,high=true,label='durable damage'},
    ap_direct={weight=10,exact=true,high=true,label='AP direct'},
    ap_slight={weight=7,exact=true,high=true,label='AP slight'},
    ap_large={weight=7,exact=true,high=true,label='AP large'},
    ap_extreme={weight=4,exact=true,label='AP extreme'},
    projectile_velocity={weight=12,tolerance=2,high=true,label='velocity'},
    fire_rate={weight=8,tolerance=1,high=true,label='fire rate'},
    capacity={weight=8,exact=true,high=true,label='capacity'},
    projectile_mass={weight=5,tolerance=0.1,label='projectile mass'},
    drag={weight=4,tolerance=0.01,label='drag'},
    gravity={weight=4,tolerance=0.01,label='gravity'},
    demolition={weight=6,exact=true,label='demolition'},
    stagger={weight=6,exact=true,label='stagger'},
    push_force={weight=5,exact=true,label='push force'},
    pellet_count={weight=10,exact=true,high=true,label='pellet count'},
}
local order={'standard_damage','durable_damage','ap_direct','ap_slight','ap_large','ap_extreme',
    'projectile_velocity','fire_rate','capacity','projectile_mass','drag','gravity',
    'demolition','stagger','push_force','pellet_count'}

local function display(value)
    if type(value)=='number' then return string.format('%.9g',value)end
    return tostring(value)
end

local function compare(actual,expected,rule)
    if rule.exact then return actual==expected end
    return math.abs(actual-expected)<=rule.tolerance
end

local function score(runtime,weapon)
    local primary=weapon.primary or {}
    local result={name=weapon.name,score=0,matched={},mismatched={},compared=0,
        highValueMatches=0,highValueMismatches=0,primaryAttack=primary.name,primaryKind=primary.kind}
    for _,field in ipairs(order)do
        local actual,expected=runtime[field],primary[field]
        if type(actual)=='number' and type(expected)=='number' then
            local rule=rules[field];result.compared=result.compared+1
            if compare(actual,expected,rule) then
                result.score=result.score+rule.weight
                if rule.high then result.highValueMatches=result.highValueMatches+1 end
                result.matched[#result.matched+1]=rule.label..'='..display(actual)
            else
                result.score=result.score-rule.weight*2
                if rule.high then result.highValueMismatches=result.highValueMismatches+1 end
                result.mismatched[#result.mismatched+1]=rule.label..' runtime='..display(actual)
                    ..' wiki='..display(expected)
            end
        end
    end
    return result
end

local function before(a,b)
    if a.score~=b.score then return a.score>b.score end
    if #a.mismatched~=#b.mismatched then return #a.mismatched<#b.mismatched end
    if a.compared~=b.compared then return a.compared>b.compared end
    return a.name<b.name
end

function M.rank(runtime,dataset,limit)
    assert(type(runtime)=='table' and type(dataset)=='table' and type(dataset.weapons)=='table',
        'matcher requires runtime fields and wiki dataset')
    local ranked={}
    for _,weapon in ipairs(dataset.weapons)do ranked[#ranked+1]=score(runtime,weapon)end
    table.sort(ranked,before)
    local top,second=ranked[1],ranked[2]
    local margin=top and top.score-(second and second.score or 0) or 0
    local state='UNMATCHED'
    if top and top.score>=15 and top.highValueMatches>=1 then
        if #top.mismatched==0 and top.compared>=5 and top.highValueMatches>=3
            and top.score>=50 and margin>=12 then state='EXACT'
        elseif top.highValueMismatches==0 and top.compared>=4 and top.highValueMatches>=2
            and top.score>=30 and margin>=10 then state='STRONG'
        else state='AMBIGUOUS' end
    end
    local trimmed={}
    for index=1,math.min(limit or 5,#ranked)do trimmed[index]=ranked[index]end
    return {status=state,scoreMargin=margin,rankedWikiMatches=trimmed}
end

M.rules=rules
return M
