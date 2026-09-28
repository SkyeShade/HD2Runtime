-- Failure-atomic where guarded rollback succeeds. No yields or callbacks occur here.
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local PAGE=4096
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
function M.apply(runtime,plan)
    local report={status='REJECTED',writes=0,bytes_written=0,protection_changes=0,
        rollback='not_needed',protection_restored=true,non_target_bytes_unchanged=false,fields={}}
    local changes=assert(plan.changes,'transaction changes missing')
    assert(#changes>=1 and #changes<=128,'unsupported transaction change count')
    local contexts,pages,page_by_key,total={}, {}, {},0
    local queries,bytes_read=0,0
    local function region(at,owner)
        assert(safe(at) and safe(owner.base) and safe(owner.size) and owner.size>0,'invalid owner extent')
        queries=queries+1;assert(queries<=16384,'transaction query budget exceeded')
        local r=assert(runtime.query(at),'memory query failed')
        assert(safe(r.base) and safe(r.size) and safe(r.base+r.size) and r.size>0
            and r.base<=at and at<r.base+r.size and r.state==0x1000
            and r.allocation_base==owner.base and r.type==(owner.type or 0x20000)
            and (r.protect==2 or r.protect==4),'allocation ownership/protection changed')
        return r
    end
    local function read(owner,offset,length)
        assert(safe(offset) and safe(length) and offset+length<=owner.size,'read outside owner')
        local parts={}
        while length>0 do
            local at=owner.base+offset
            local r=region(at,owner)
            local n=math.min(length,r.base+r.size-at,65536)
            bytes_read=bytes_read+n;assert(bytes_read<=16*1024*1024,'transaction read budget exceeded')
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
            assert(read(context.owner,context.offset,#context.bytes)==context_bytes(context,states),
                'ownership/context or non-target bytes changed')
        end
    end
    local before,desired={},{}
    local intervals={}
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
    for _,snapshot in ipairs(plan.snapshots)do
        total=total+#snapshot.bytes
        assert(total<=2*1024*1024 and #contexts<128,'transaction context budget exceeded')
        contexts[#contexts+1]={owner=snapshot.owner,offset=snapshot.offset,
            bytes=snapshot.bytes,targets={}}
    end
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
    for _,page in ipairs(pages)do
        page.original=page_region(page).protect
        assert(page.original==page.owner.protect,'original page protection changed')
    end
    local function restore_pages()
        local all=true
        for index=#pages,1,-1 do
            local page=pages[index]
            local restored=false
            for _=1,2 do
                local ok=pcall(function()
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
            if not restored then all=false end
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
        check(before)
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
                check(current_states)
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
    end
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
return M
