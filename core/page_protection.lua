-- Page protections as VirtualQuery reports them, in one place: every Runtime reader and the guarded transaction's
-- region checks agree on what may be read and what may be written.
--
-- Readable: read-only, read-write and copy-on-write pages, with or without execute. Proton/Wine maps game.dll's data
-- pages PAGE_WRITECOPY where Windows reports PAGE_READWRITE (GitHub issue #3), so copy-on-write must count as
-- readable. Exact values only: a guard, no-cache or write-combine modifier makes a page something else.
--
-- Writable target: what a guarded write may open and write. READONLY (opened to READWRITE for the write, then restored)
-- or READWRITE. Never copy-on-write and never executable: a write target outside this set is refused before any page
-- is opened.
local M={}
M.READONLY,M.READWRITE,M.WRITECOPY=0x2,0x4,0x8
M.EXECUTE_READ,M.EXECUTE_READWRITE,M.EXECUTE_WRITECOPY=0x20,0x40,0x80
M.READABLE={[0x2]=true,[0x4]=true,[0x8]=true,[0x20]=true,[0x40]=true,[0x80]=true}
M.WRITABLE_TARGET={[0x2]=true,[0x4]=true}
function M.readable(protect)return M.READABLE[protect]==true end
function M.writable_target(protect)return M.WRITABLE_TARGET[protect]==true end

-- REVIEWED DATA IN EXECUTABLE PAGES (the user's decision of 2026-10-08; docs/armor-stats.md): game.dll keeps a few
-- data tables in a section the loader maps PAGE_EXECUTE_READWRITE (the armor weight-class tables and the avatar damage
-- curve: research/armor-stats-F5FEE03DCFDB.json). Such a page may be a write target ONLY for an exact extent a domain
-- registered here after its own proofs (the build fingerprint, its instruction pins, the reviewed bytes), and only when
-- EVERY change of the transaction on that page lies inside a registered extent; the page is already writable, so its
-- protection is never changed. Every other executable page, and every unregistered byte of this one, stays refused.
M.REVIEWED_EXECUTABLE=0x40
local reviewed={}           -- {first, last, label}, absolute addresses for this process
function M.register_executable_data(address,size,label)
    assert(type(address)=='number'and address>0 and address%1==0 and type(size)=='number'and size>=1 and size<=64
        and size%1==0 and type(label)=='string','register_executable_data(address, size, label)')
    for _,e in ipairs(reviewed)do
        if e.first==address and e.last==address+size then return end
        assert(address+size<=e.first or address>=e.last,'overlapping executable data extents')
    end
    assert(#reviewed<64,'too many executable data extents')
    reviewed[#reviewed+1]={first=address,last=address+size,label=label}
end
-- The label of the registered extent holding [address, address + size), or nil.
function M.reviewed_executable_data(address,size)
    for _,e in ipairs(reviewed)do if address>=e.first and address+size<=e.last then return e.label end end
end
function M.reset_executable_data_for_tests()reviewed={}end
return M
