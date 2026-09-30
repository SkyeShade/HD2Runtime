-- Failure-atomic where guarded rollback succeeds. No yields or callbacks occur here.
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local PAGE=4096
-- Hard ceiling on the guarded bytes one transaction may read. The allowance itself is derived from the plan's shape
-- (see M.read_allowance); a plan whose allowance exceeds this is refused before any page is opened.
local READ_CEILING=64*1024*1024
M.READ_CEILING=READ_CEILING
-- Guarded reads scale with the plan: each full check re-reads every context once. A successful apply runs changed+3
-- checks (one before opening the pages, one right before each write, one after the last write and one after
-- restoring protection); a rollback at most changed+2 more. Each target is re-read at most five times (immediate and post-write reads, the rollback's reads).
-- The allowance covers exactly that bound, rollback included, so a rollback is never starved of its reads.
function M.read_allowance(changed,context_bytes,target_bytes)
    return (2*changed+6)*context_bytes+8*target_bytes
end
local function safe(n)return type(n)=='number' and n>=0 and n%1==0 and n<=9007199254740991 end
local function replace(value,offset,bytes)
    return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)
end
-- Build a guarded inverse from the exact post-state of a completed phase. Only bytes
-- actually changed by that phase are reverted; values that were already desired are
-- never claimed by rollback.
function M.inverse(plan)
    local changes=assert(plan.changes,'transaction changes missing')
    local snapshots={}
    for index,snapshot in ipairs(assert(plan.snapshots,'transaction snapshots missing'))do
        snapshots[index]={owner=snapshot.owner,offset=snapshot.offset,bytes=snapshot.bytes}
    end
    for _,change in ipairs(changes)do
        local address=change.owner.base+change.offset
        local contained=0
        for _,snapshot in ipairs(snapshots)do
            local first=snapshot.owner.base+snapshot.offset
            if address>=first and address+#change.desired<=first+#snapshot.bytes then
                snapshot.bytes=replace(snapshot.bytes,address-first,change.desired);contained=contained+1
            end
        end
        assert(contained==1,'inverse transaction target context absent/ambiguous')
    end
    local inverse={changes={},snapshots=snapshots}
    for _,change in ipairs(changes)do if change.before~=change.desired then
        inverse.changes[#inverse.changes+1]={label=change.label,owner=change.owner,
            offset=change.offset,expected=change.desired,desired=change.before,
            before=change.desired,already_desired=false,identity=change.identity,
            chain=change.chain,expect=change.value,value=change.expect,packed=change.packed}
    end end
    return inverse
end
local function hex(value)
    if type(value)~='number'or value<0 or value%1~=0 then return'unknown'end
    local high=math.floor(value/4294967296)
    return high>0 and('0x%X%08X'):format(high,value%4294967296)or('0x%X'):format(value)
end
-- Which region conditions a query failed. The guard itself is unchanged; this only names the reason.
local function failed_conditions(at,owner,r)
    if not r then return {'query_failed'} end
    local failed={}
    if not(safe(r.base) and safe(r.size) and safe(r.base+r.size) and r.size>0)then failed[#failed+1]='extent'
    elseif not(r.base<=at and at<r.base+r.size)then failed[#failed+1]='address_outside_region' end
    if r.state~=0x1000 then failed[#failed+1]='state' end
    if r.allocation_base~=owner.base then failed[#failed+1]='allocation_base' end
    if r.type~=(owner.type or 0x20000)then failed[#failed+1]='type' end
    if not(r.protect==2 or r.protect==4)then failed[#failed+1]='protection' end
    return failed
end
function M.apply(runtime,plan)
    -- non_target_check says how far the non-target comparison got: not_reached (validation stopped before any
    -- comparison completed, so non_target_bytes_unchanged=false says nothing about the bytes), checked (the
    -- captured context matched before the failure), mismatch (bytes around a target changed) or verified.
    local report={status='REJECTED',writes=0,bytes_written=0,protection_changes=0,
        rollback='not_needed',protection_restored=true,non_target_bytes_unchanged=false,
        non_target_check='not_reached',fields={}}
    local changes=assert(plan.changes,'transaction changes missing')
    assert(#changes>=1 and #changes<=128,'unsupported transaction change count')
    local contexts,pages,page_by_key,total={}, {}, {},0
    local queries,bytes_read,allowance=0,0,0
    local refused
    local function region(at,owner)
        assert(safe(at) and safe(owner.base) and safe(owner.size) and owner.size>0,'invalid owner extent')
        queries=queries+1;assert(queries<=16384,'transaction query budget exceeded')
        local r=runtime.query(at)
        local failed=failed_conditions(at,owner,r)
        if #failed>0 and not refused then
            -- The first refused query, as observed (diagnostics only; nothing is read or written here).
            refused={address=at,failed=failed,owner_base=owner.base,owner_size=owner.size,
                expected_type=owner.type or 0x20000,expected_protect=owner.protect,
                region_base=r and r.base,region_size=r and r.size,state=r and r.state,type=r and r.type,
                protect=r and r.protect,allocation_base=r and r.allocation_base,
                allocation_protect=r and r.allocation_protect}
        end
        assert(r,'memory query failed')
        assert(#failed==0,'allocation ownership/protection changed')
        return r
    end
    local function read(owner,offset,length)
        assert(safe(offset) and safe(length) and offset+length<=owner.size,'read outside owner')
        local parts={}
        while length>0 do
            local at=owner.base+offset
            local r=region(at,owner)
            local n=math.min(length,r.base+r.size-at,65536)
            bytes_read=bytes_read+n;assert(bytes_read<=allowance,'transaction read budget exceeded')
            local value=assert(runtime.read(at,n),'memory read failed')
            assert(#value==n,'short memory read')
            parts[#parts+1]=value;offset=offset+n;length=length-n
        end
        return table.concat(parts)
    end
    local function page_region(page)
        local r=region(page.address,page.owner)
        assert(page.address>=page.owner.base and page.address+PAGE<=page.owner.base+page.owner.size
            and r.base<=page.address and r.base+r.size>=page.address+PAGE,
            'target page extent changed')
        return r
    end
    local function context_bytes(context,states)
        if #context.targets==0 then return context.bytes end
        local chunks,cursor={},0
        for _,entry in ipairs(context.targets)do
            assert(entry.offset>=cursor,'overlapping context targets')
            chunks[#chunks+1]=context.bytes:sub(cursor+1,entry.offset)
            chunks[#chunks+1]=states[entry.index]
            cursor=entry.offset+#changes[entry.index].before
        end
        chunks[#chunks+1]=context.bytes:sub(cursor+1)
        return table.concat(chunks)
    end
    local function check(states)
        for _,context in ipairs(contexts)do
            if read(context.owner,context.offset,#context.bytes)~=context_bytes(context,states)then
                report.non_target_check='mismatch'
                error('ownership/context or non-target bytes changed',0)
            end
        end
        if report.non_target_check=='not_reached'then report.non_target_check='checked'end
    end
    local before,desired={},{}
    local intervals={}
    local changed_count,target_bytes=0,0
    for index,change in ipairs(changes)do
        assert(type(change.owner)=='table' and safe(change.offset)
            and type(change.expected)=='string' and type(change.desired)=='string'
            and type(change.before)=='string' and #change.expected==#change.desired
            and #change.before==#change.desired
            and (#change.desired==1 or #change.desired==4 or #change.desired==8
                or #change.desired==12),
            'invalid transaction change')
        assert(change.before==change.expected or change.before==change.desired,
            'transaction change is neither expected nor desired')
        local address=change.owner.base+change.offset
        -- Byte-packed data (entity delta blobs) opts in explicitly; everything else must
        -- stay naturally aligned. All targets must be contained in one page.
        assert(safe(address) and (#change.desired==1 or address%4==0 or change.packed==true)
            and address%PAGE+#change.desired<=PAGE,
            'transaction target alignment/page boundary')
        intervals[#intervals+1]={first=address,last=address+#change.desired,index=index}
        before[index]=change.before;desired[index]=change.desired
        target_bytes=target_bytes+#change.before
        if change.before~=change.desired then changed_count=changed_count+1 end
        report.fields[index]={field=change.label,
            state=change.before==change.desired and 'ALREADY_DESIRED' or 'EXPECTED'}
        if change.before~=change.desired then
            local page_address=address-address%PAGE
            local key=tostring(page_address)
            local page=page_by_key[key]
            if page then assert(page.owner.base==change.owner.base,'page shared by different owners')
            else
                page={address=page_address,owner=change.owner,opened=false}
                page_by_key[key]=page;pages[#pages+1]=page
            end
            change.page=page
        end
    end
    table.sort(intervals,function(a,b)return a.first<b.first end)
    for i=2,#intervals do assert(intervals[i-1].last<=intervals[i].first,
        'overlapping transaction changes')end
    assert(type(plan.snapshots)=='table' and #plan.snapshots>0,'transaction snapshots missing')
    -- One context per captured range. The operations of one plan often prove the same chain (every MG-206 operation
    -- re-captures its call-in delivery proof), so the same range arrives several times: it is checked once. Copies
    -- whose bytes differ were captured from memory that changed in between, which fails closed.
    local context_by_range={}
    for _,snapshot in ipairs(plan.snapshots)do
        local range=tostring(snapshot.owner.base)..':'..tostring(snapshot.offset)..':'..#snapshot.bytes
        local prior=context_by_range[range]
        if prior then
            assert(prior.owner.size==snapshot.owner.size and prior.bytes==snapshot.bytes,
                'duplicate transaction context differs')
        else
            total=total+#snapshot.bytes
            assert(total<=2*1024*1024 and #contexts<128,'transaction context budget exceeded')
            prior={owner=snapshot.owner,offset=snapshot.offset,bytes=snapshot.bytes,targets={}}
            contexts[#contexts+1]=prior;context_by_range[range]=prior
        end
    end
    allowance=M.read_allowance(changed_count,total,target_bytes)
    assert(allowance<=READ_CEILING,('transaction read budget exceeded: %d changes over %d context bytes need up to '
        ..'%d guarded bytes, above the %d ceiling; split the operation'):format(changed_count,total,allowance,
        READ_CEILING))
    for index,change in ipairs(changes)do
        local address=change.owner.base+change.offset
        local contained=0
        for _,context in ipairs(contexts)do
            local first=context.owner.base+context.offset
            if address<first+#context.bytes and address+#change.before>first then
                assert(address>=first and address+#change.before<=first+#context.bytes,
                    'partial transaction target context')
                context.targets[#context.targets+1]={index=index,offset=address-first}
                contained=contained+1
                assert(context.bytes:sub(address-first+1,address-first+#change.before)==change.before,
                    'target differs from captured context')
            end
        end
        assert(contained==1,'transaction target context absent/ambiguous: '..tostring(change.label)
            ..' contexts='..contained)
    end
    for _,context in ipairs(contexts)do
        table.sort(context.targets,function(a,b)return a.offset<b.offset end)
    end
    -- A target page refused here has not been opened or written: the same rejection as before, now reported with
    -- the region diagnostics instead of a bare error.
    local captured,capture_error=pcall(function()
        for _,page in ipairs(pages)do
            page.original=page_region(page).protect
            assert(page.original==page.owner.protect,'original page protection changed')
        end
    end)
    if not captured then
        report.reason=tostring(capture_error)
        if refused then report.guard_failure=M.describe_failure(M.explain(runtime,refused,changes))end
        report.guard_queries=queries;report.guard_bytes=bytes_read
        metrics.count('transaction.applies')
        return report
    end
    local function restore_pages()
        local all=true
        for index=#pages,1,-1 do
            local page=pages[index]
            local restored,why=false,nil
            for _=1,2 do
                local ok
                ok,why=pcall(function()
                    local r=page_region(page)
                    if r.protect~=page.original then
                        assert(page.opened and r.protect==4,'unexpected protection before restore')
                        report.protection_changes=report.protection_changes+1
                        assert(runtime.protect(page.address,PAGE,page.original)==4,
                            'page protection restore failed')
                    end
                    assert(page_region(page).protect==page.original,
                        'page protection restore verification failed')
                end)
                if ok then restored=true;page.opened=false;break end
            end
            if not restored then
                all=false
                report.restore_failure=('protection_restore_failure page=%s original=%s reason=%s'):format(
                    hex(page.address),hex(page.original),tostring(why))
            end
        end
        return all
    end
    local attempted={}
    local current_states={}
    for i,value in ipairs(before)do current_states[i]=value end
    local function open_page(page,label)
        local r=page_region(page)
        if r.protect==4 then return end
        assert(r.protect==2,'unsupported '..label..' page protection')
        report.protection_changes=report.protection_changes+1
        local prior=runtime.protect(page.address,PAGE,4)
        if prior==4 then page.original=4;error(label..' page protection raced during open',0)end
        assert(prior==2,label..' page open failed')
        page.opened=true
        assert(page_region(page).protect==4,label..' page did not become writable')
    end
    local function rollback()
        if #attempted==0 then return 'not_needed' end
        local ok,why=pcall(function()
            local actual={}
            for index,change in ipairs(changes)do actual[index]=read(change.owner,change.offset,#change.before)end
            for _,attempt in ipairs(attempted)do
                local change=changes[attempt.index]
                local value=actual[attempt.index]
                assert(type(attempt.count)=='number' and attempt.count>=0
                    and attempt.count<=#change.before and attempt.count%1==0,
                    'unknown write count; rollback refused')
                local partial=change.desired:sub(1,attempt.count)..change.before:sub(attempt.count+1)
                assert(value==change.before or value==change.desired or value==partial,
                    'unknown third-party target; rollback refused')
            end
            check(actual)
            for at=#attempted,1,-1 do
                local attempt=attempted[at]
                local change=changes[attempt.index]
                if actual[attempt.index]~=change.before then
                    open_page(change.page,'rollback')
                    check(actual)
                    assert(read(change.owner,change.offset,#change.before)==actual[attempt.index],
                        'rollback target changed')
                    assert(page_region(change.page).protect==4,'rollback page protection changed')
                    report.writes=report.writes+1
                    local wrote,reason,count=runtime.write(change.owner.base+change.offset,change.before,change.packed)
                    assert(wrote and count==#change.before,'rollback write failed: '..tostring(reason))
                    actual[attempt.index]=change.before
                    assert(read(change.owner,change.offset,#change.before)==change.before,
                        'rollback reread mismatch')
                end
            end
            check(before)
        end)
        if not ok then report.rollback_error=tostring(why)end
        return ok and 'verified' or 'refused_or_failed'
    end
    local ok,why=pcall(function()
        assert(runtime.system_info()==PAGE,'unsupported page size')
        check(before)
        if #pages==0 then
            report.status='ALREADY_DESIRED';report.non_target_bytes_unchanged=true;return
        end
        for _,page in ipairs(pages)do open_page(page,'target')end
        -- One full check right before every write, and one after the last write. A write that disturbs any context is
        -- caught before the next write (or by the final check), and so is a change by anything else. The checks the
        -- engine used to repeat back to back (after opening the pages, and again after each write, each immediately
        -- followed by the next write's own check with nothing written in between) re-read every context twice.
        for index,change in ipairs(changes)do
            assert(read(change.owner,change.offset,#change.before)==before[index],
                'immediate target reread mismatch')
            if change.before~=change.desired then
                assert(page_region(change.page).protect==4,'writable protection changed before write')
                check(current_states)
                local attempt={index=index,count=-1};attempted[#attempted+1]=attempt
                report.writes=report.writes+1
                local wrote,reason,count=runtime.write(change.owner.base+change.offset,change.desired,change.packed)
                attempt.count=tonumber(count) or -1
                report.bytes_written=report.bytes_written+math.max(0,attempt.count)
                assert(wrote and count==#change.desired,'exact-width write failed: '..tostring(reason))
                current_states[index]=change.desired
                assert(read(change.owner,change.offset,#change.desired)==change.desired,
                    'post-write target reread mismatch')
                report.fields[index].state='APPLIED'
            end
        end
        check(desired)
        assert(restore_pages(),'original page protection restoration failed')
        for _,page in ipairs(pages)do assert(page_region(page).protect==page.original,
            'final page protection mismatch')end
        check(desired)
        report.status='APPLIED';report.non_target_bytes_unchanged=true
    end)
    if not ok then
        report.reason=tostring(why);report.rollback=rollback()
        report.protection_restored=restore_pages();report.status='REJECTED'
        -- Mod-facing results carry no raw addresses as values; the diagnostic is the logged text.
        if refused then report.guard_failure=M.describe_failure(M.explain(runtime,refused,changes))end
    end
    if report.status~='REJECTED'then report.non_target_check='verified'end
    report.guard_queries=queries;report.guard_bytes=bytes_read
    metrics.count('transaction.applies')
    metrics.count('transaction.writes',report.writes)
    metrics.count('transaction.protection_changes',report.protection_changes)
    metrics.count('transaction.guard_bytes',bytes_read)
    for _,field in ipairs(report.fields)do
        if field.state=='ALREADY_DESIRED'then metrics.count('transaction.already_desired_fields')end
    end
    return report
end
-- After a refused region query: the module containing the address, and whether every target still holds the
-- bytes the plan expected. Raw reads use the runtime's fault-safe read (ReadProcessMemory); they cover only the
-- plan's own target extents, follow no pointer and never feed a write.
function M.explain(runtime,failure,changes)
    local module=runtime.module_at and runtime.module_at(failure.address)
    failure.module=module and module.name or'none'
    failure.module_offset=module and failure.address-module.base or nil
    local matched,differ,unreadable=0,0,0
    for _,change in ipairs(changes)do
        local value=runtime.read(change.owner.base+change.offset,#change.before)
        if type(value)~='string'or#value~=#change.before then unreadable=unreadable+1
        elseif value==change.before then matched=matched+1 else differ=differ+1 end
    end
    failure.expected_bytes=unreadable>0 and'unreadable'or differ>0 and'differ'or'match'
    failure.targets_matched,failure.targets_differ,failure.targets_unreadable=matched,differ,unreadable
    return failure
end
-- One log line for a refused region query (Proton/Wine support reports).
function M.describe_failure(failure)
    return ('guard_failure address=%s failed=%s region=%s+%s state=%s type=%s protect=%s allocation_base=%s '
        ..'allocation_protect=%s expected_allocation_base=%s expected_size=%s expected_type=%s expected_protect=%s '
        ..'module=%s%s expected_bytes=%s (%d match, %d differ, %d unreadable)'):format(hex(failure.address),
        table.concat(failure.failed,','),hex(failure.region_base),hex(failure.region_size),hex(failure.state),
        hex(failure.type),hex(failure.protect),hex(failure.allocation_base),hex(failure.allocation_protect),
        hex(failure.owner_base),hex(failure.owner_size),hex(failure.expected_type),hex(failure.expected_protect),
        tostring(failure.module),failure.module_offset and('+'..hex(failure.module_offset))or'',
        tostring(failure.expected_bytes),failure.targets_matched or 0,failure.targets_differ or 0,
        failure.targets_unreadable or 0)
end
-- The report lines every write API logs. Successful lines are unchanged; a rejection also says how far the
-- non-target comparison got and, after a refused region query, what the memory looked like.
function M.report_lines(result)
    local lines={'non_target_bytes_unchanged='..tostring(result.non_target_bytes_unchanged)
        ..(result.status=='REJECTED'and result.non_target_check and' non_target_check='..result.non_target_check or'')}
    if result.guard_failure then lines[#lines+1]=result.guard_failure end
    if result.restore_failure then lines[#lines+1]=result.restore_failure end
    lines[#lines+1]='protection_restored='..tostring(result.protection_restored)
    return lines
end
return M
