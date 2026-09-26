-- One bounded transaction over one reviewed contiguous logical field.
-- No yields, callbacks or logs inside the protection/write/restore window.
local M={}
local PAGE=4096
function M.apply(runtime,plan)
    local report={status='REJECTED',writes=0,write_attempted=false,bytes_written=0,protection_changes=0,
        rollback='not_needed',protection_restored=true,non_target_bytes_unchanged=false}
    local address=plan.owner.base+plan.offset
    local page=address-address%PAGE
    local original,opened,attempted,count=nil,false,false,nil
    local contexts,total={},0
    local guard_queries,guard_bytes=0,0
    local function safe(n)return type(n)=='number' and n>=0 and n%1==0 and n<=9007199254740991 end
    local function region(at,owner)
        local r=assert(runtime.query(at),'memory query failed')
        assert(safe(r.base) and safe(r.size) and safe(r.base+r.size)
            and r.base<=at and r.size>0 and at<r.base+r.size and r.state==0x1000
            and r.allocation_base==owner.base and r.type==(owner.type or 0x20000)
            and (r.protect==2 or r.protect==4),'allocation ownership/protection changed')
        return r
    end
    local function read(owner,offset,length)
        assert(offset>=0 and offset+length<=owner.size,'context outside allocation')
        local parts={}
        while length>0 do
            guard_queries=guard_queries+1
            assert(guard_queries<=8192,'synchronous guard query budget exceeded')
            local at=owner.base+offset
            local r=region(at,owner)
            local n=math.min(length,r.base+r.size-at,65536)
            guard_bytes=guard_bytes+n
            assert(guard_bytes<=8*1024*1024,'synchronous guard byte budget exceeded')
            local bytes=assert(runtime.read(at,n),'context read failed')
            assert(#bytes==n,'short context read')
            parts[#parts+1]=bytes;offset=offset+n;length=length-n
        end
        return table.concat(parts)
    end
    local function expected(c,target)
        if not c.target_offset then return c.bytes end
        return c.bytes:sub(1,c.target_offset)..target..c.bytes:sub(c.target_offset+#target+1)
    end
    local function check(target)
        for _,c in ipairs(contexts)do
            assert(read(c.owner,c.offset,#c.bytes)==expected(c,target),
                'ownership/context or non-target bytes changed')
        end
    end
    local function target_page()
        local r=region(page,plan.owner)
        assert(page>=plan.owner.base and page+PAGE<=plan.owner.base+plan.owner.size
            and r.base+r.size>=page+PAGE,'target page extent changed')
        return r
    end
    local function restore()
        if not original then return true end
        for _=1,2 do
            local ok=pcall(function()
                local r=target_page()
                if r.protect~=original then
                    assert(opened and r.protect==4,'unexpected protection before restore')
                    report.protection_changes=report.protection_changes+1
                    assert(runtime.protect(page,PAGE,original)==4,'protection restore failed')
                end
                assert(target_page().protect==original,'protection restore verification failed')
            end)
            if ok then opened=false;return true end
        end
        return false
    end
    local function rollback()
        if not attempted then return 'not_needed' end
        local ok,why=pcall(function()
            local current=read(plan.owner,plan.offset,#plan.old)
            -- A failed native write must report its exact transferred prefix.
            assert(type(count)=='number' and count>=0 and count<=#plan.old and count%1==0,
                'unknown write count; rollback refused')
            local partial=plan.new:sub(1,count)..plan.old:sub(count+1)
            assert(current==plan.old or current==partial,'unknown third-party target; rollback refused')
            check(current)
            if current~=plan.old then
                local r=target_page()
                if r.protect==2 then
                    opened=true;report.protection_changes=report.protection_changes+1
                    assert(runtime.protect(page,PAGE,4)==2,'rollback page open failed')
                end
                assert(target_page().protect==4,'rollback page not writable')
                check(current)
                assert(read(plan.owner,plan.offset,#plan.old)==current,'rollback target changed')
                assert(target_page().protect==4,'rollback writable protection changed')
                report.writes=report.writes+1
                local wrote,reason,n=runtime.write(address,plan.old)
                assert(wrote and n==#plan.old,'rollback write failed: '..tostring(reason))
            end
            check(plan.old)
        end)
        if not ok then report.rollback_error=tostring(why)end
        return ok and 'verified' or 'refused_or_failed'
    end
    local ok,why=pcall(function()
        assert(runtime.system_info()==PAGE,'unsupported page size')
        assert(#plan.old==12 and #plan.new==12 and address%4==0
            and address%PAGE+12<=PAGE,'target width/alignment/page boundary')
        local contained=0
        for _,s in ipairs(plan.snapshots)do
            total=total+#s.bytes
            assert(total<=1024*1024 and #contexts<64,'synchronous guard budget exceeded')
            local c={owner=s.owner,offset=s.offset,bytes=s.bytes}
            local start=s.owner.base+s.offset
            if address<start+#s.bytes and address+12>start then
                assert(address>=start and address+12<=start+#s.bytes,'partial target context')
                c.target_offset=address-start;contained=contained+1
                assert(s.bytes:sub(c.target_offset+1,c.target_offset+12)==plan.old,'inconsistent target snapshot')
            end
            contexts[#contexts+1]=c
        end
        assert(contained==1 and #contexts>=4,'incomplete ownership contexts')
        local r=target_page();original=r.protect
        assert(original==plan.owner.protect,'original protection changed')
        check(plan.old)
        if plan.already_desired then
            assert(plan.old==plan.new,'invalid no-op plan')
            assert(target_page().protect==original,'no-op protection changed')
            report.status='ALREADY_DESIRED';report.non_target_bytes_unchanged=true;return
        end
        if original==2 then
            opened=true;report.protection_changes=report.protection_changes+1
            local prior=runtime.protect(page,PAGE,4)
            if prior==4 then
                -- The OS observed a protection race. Preserve its actual prior state.
                original=prior
                error('original protection raced during page open',0)
            end
            assert(prior==original,'page open failed')
        end
        assert(target_page().protect==4,'target page not writable')
        check(plan.old)
        assert(read(plan.owner,plan.offset,12)==plan.old,'immediate target reread mismatch')
        assert(target_page().protect==4,'writable protection changed before write')
        attempted=true;report.write_attempted=true;report.writes=report.writes+1
        local wrote,reason,n=runtime.write(address,plan.new)
        count=n;report.bytes_written=tonumber(n) or 0
        assert(wrote and n==12,'exact-width write failed: '..tostring(reason))
        assert(read(plan.owner,plan.offset,12)==plan.new,'post-write target reread mismatch')
        check(plan.new)
        assert(restore(),'original protection restoration failed')
        assert(target_page().protect==original,'final protection mismatch')
        check(plan.new)
        assert(target_page().protect==original,'protection changed during final verification')
        report.non_target_bytes_unchanged=true;report.status='APPLIED'
    end)
    if not ok then
        report.status='REJECTED';report.reason=tostring(why)
        report.rollback=rollback()
        report.protection_restored=restore()
    end
    report.guard_queries=guard_queries;report.guard_bytes=guard_bytes
    return report
end
return M
