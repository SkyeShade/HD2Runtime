-- Lightweight runtime diagnostics (docs/diagnostics.md).
--
-- Write conflicts (always on; runs only when an ensure's steady byte-check finds its owned bytes changed while their
-- allocation is still the reviewed one): each ensure-owned target counts how often something else rewrites it and
-- Runtime re-applies it. Past THRESHOLD re-applications within its window (five of its verification intervals, at
-- least 10 s) one warning names the operation, its target and fields, the count and the time span; the next warning
-- for that operation waits a full window. Nothing is inferred about who wrote the bytes.
--
-- Telemetry (off by default): hd2.diagnostics.telemetry({enabled=true}) samples the durations the metrics module
-- already measures (scheduler.tick: the whole Runtime update; steady.verify: one ensure byte-check; events.tick: event
-- polling) into fixed rings, and every report interval logs average, p95, p99 and maximum per section, the active
-- ensures and the re-applications in that interval. Disabled, the cost is one boolean test per timed section.
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local THRESHOLD=3
local RING=512
local conflicts={}
local emit=function(line)require('hd2runtime/runtime/log').emit(line)end

------------------------------------------------------------------------------------------------ write conflicts --
-- A short, stable description of what an operation writes: its target and up to four fields.
function M.describe(kind,body)
    if type(body)~='table'then return kind end
    local function target_name(target)
        if type(target)~='table'then return tostring(target)end
        local name=target.weapon or target.stratagem or target.output or target.entity or target.backpack
            or target.vehicle or target.attachment or target.enemy or target.booster or target.throwable or target.rack
            or target.explosion
        local parts={tostring(target.resource)}
        if name then parts[#parts+1]=tostring(name)end
        if target.attack then parts[#parts+1]=tostring(target.attack)end
        if target.path and target.path~='weapon'then parts[#parts+1]=tostring(target.path)end
        return table.concat(parts,' ')
    end
    local fields,target={},body.target
    if body.field then fields[1]=tostring(body.field)end
    for _,change in ipairs(body.changes or{})do
        if #fields<4 then fields[#fields+1]=tostring(change.field)end
    end
    if body.operations then
        target=(body.operations[1]or{}).target
        fields[#fields+1]=#body.operations..' operations'
    end
    return target_name(target)..': '..table.concat(fields,', ')
end
-- One record per ensure watch: {id, target, interval, times, total, warned}; warnings go to the watch's own log.
function M.watch(id,description,interval,log_line)
    local record={id=id,target=description,interval=math.max(interval or 0,0),times={},total=0,warned=-math.huge,
        warnings=0,emit=log_line}
    conflicts[#conflicts+1]=record
    return record
end
-- An external change of the owned bytes was found at `now` (the watch's own elapsed seconds) and is re-applied.
function M.external_change(record,now)
    metrics.count('ensure.external_changes')
    record.total=record.total+1
    local window=math.max(10,record.interval*5)
    local times=record.times
    times[#times+1]=now
    local first=1
    while times[first]and times[first]<now-window do first=first+1 end
    if first>1 then
        local kept={}
        for index=first,#times do kept[#kept+1]=times[index]end
        record.times=kept;times=kept
    end
    if #times>=THRESHOLD and now-record.warned>=window then
        record.warned=now;record.warnings=record.warnings+1
        metrics.count('ensure.write_conflict_warnings')
        local log_line=record.emit or emit
        log_line(string.format('[HD2Runtime] possible write conflict: operation %s (%s) externally changed and '
            ..'re-applied %d times in %.1f s; another mod may be writing the same memory',record.id,record.target,
            #times,now-times[1]))
    end
end
-- Operations whose targets were changed externally, most first (for tools and the example diagnostics mod).
function M.write_conflicts()
    local out={}
    for _,record in ipairs(conflicts)do
        if record.total>0 then
            out[#out+1]={operation=record.id,target=record.target,externalChanges=record.total,
                warnings=record.warnings,windowSeconds=math.max(10,record.interval*5)}
        end
    end
    table.sort(out,function(a,c)return a.externalChanges>c.externalChanges end)
    return out
end

---------------------------------------------------------------------------------------------------- telemetry --
local telemetry={enabled=false,report=60,elapsed=0,sections={}}
M.telemetry_state=telemetry
local SECTIONS={['scheduler.tick']='update',['steady.verify']='ensure byte-check',['events.tick']='event polling'}
-- Called by metrics.elapsed for every timed section while telemetry is enabled.
function M.sample(name,duration)
    local label=SECTIONS[name]
    if not label then return end
    local section=telemetry.sections[name]
    if not section then section={ring={},next=1,count=0,sum=0,max=0};telemetry.sections[name]=section end
    section.ring[section.next]=duration;section.next=section.next%RING+1
    section.count=section.count+1;section.sum=section.sum+duration
    if duration>section.max then section.max=duration end
end
local function percentile(sorted,fraction)
    if #sorted==0 then return 0 end
    return sorted[math.max(1,math.ceil(#sorted*fraction))]
end
local function summary()
    local parts={}
    for _,name in ipairs({'scheduler.tick','steady.verify','events.tick'})do
        local section=telemetry.sections[name]
        if section and section.count>0 then
            local sorted={};for index,value in ipairs(section.ring)do sorted[index]=value end
            table.sort(sorted)
            parts[#parts+1]={section=SECTIONS[name],samples=section.count,averageMs=section.sum/section.count*1000,
                p95Ms=percentile(sorted,0.95)*1000,p99Ms=percentile(sorted,0.99)*1000,maxMs=section.max*1000}
        end
    end
    return parts
end
local reapplied_before=0
-- Called by the scheduler each tick while telemetry is enabled.
function M.tick(dt,active)
    telemetry.elapsed=telemetry.elapsed+dt
    if telemetry.elapsed<telemetry.report then return end
    local counters=metrics.snapshot().counters
    local reapplied=(counters['ensure.full_resolutions_after_drift']or 0)
    local lines={}
    for _,part in ipairs(summary())do
        lines[#lines+1]=string.format('%s avg %.3f ms p95 %.3f p99 %.3f max %.3f (%d)',part.section,part.averageMs,
            part.p95Ms,part.p99Ms,part.maxMs,part.samples)
    end
    emit(string.format('[HD2Runtime] telemetry %.0f s: %s; active ensures %d; re-applications %d',telemetry.elapsed,
        #lines>0 and table.concat(lines,'; ')or'no timed sections (no precise clock)',active or 0,
        reapplied-reapplied_before))
    reapplied_before=reapplied
    telemetry.elapsed=0;telemetry.sections={}
end
-- hd2.diagnostics.telemetry({enabled=true|false, report_seconds=60}): returns the current state and the samples of
-- the running interval.
function M.telemetry(options)
    if options~=nil then
        assert(type(options)=='table','telemetry options must be a table')
        for key in pairs(options)do assert(key=='enabled'or key=='report_seconds','unsupported telemetry option: '
            ..tostring(key))end
        if options.report_seconds~=nil then
            assert(type(options.report_seconds)=='number'and options.report_seconds>=5
                and options.report_seconds<=3600,'report_seconds must be 5 to 3600')
            telemetry.report=options.report_seconds
        end
        if options.enabled~=nil then
            assert(type(options.enabled)=='boolean','enabled must be a boolean')
            if options.enabled and not telemetry.enabled then
                telemetry.elapsed=0;telemetry.sections={}
                reapplied_before=metrics.snapshot().counters['ensure.full_resolutions_after_drift']or 0
            end
            telemetry.enabled=options.enabled
            metrics.set_sampler(telemetry.enabled and M.sample or nil)
        end
    end
    return {enabled=telemetry.enabled,report_seconds=telemetry.report,timed=metrics.snapshot().timed,
        sections=summary()}
end
function M.telemetry_enabled()return telemetry.enabled end
return M
