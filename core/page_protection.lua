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
return M
