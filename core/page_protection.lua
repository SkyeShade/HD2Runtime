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

-- DATA IN EXECUTABLE PAGES: NEVER WRITTEN (0.40.1, the user's decision of 2026-10-19). game.dll keeps a few data
-- tables in pages the loader maps PAGE_EXECUTE_READWRITE (the armor weight-class tables and the avatar damage curve:
-- research/armor-stats-F5FEE03DCFDB.json; melee templates and enemy director rows in game.dll's image can be there
-- too). From 2026-10-08 to 0.40.0 a domain could register an exact extent of such a page as "reviewed executable data".
-- A player reported GameGuard closing the game right after armor class writes (docs/runtime-requests.md R10 in the
-- editor), so every registration is refused now and no write targets an executable page. The constant stays for the
-- readers and the domains' checks.
M.REVIEWED_EXECUTABLE=0x40
M.EXECUTABLE_DATA_CODE='GAME_DLL_EXECUTABLE_DATA'
M.EXECUTABLE_DATA_REASON='writes into game.dll\'s executable pages are disabled since HD2Runtime 0.40.1 (GameGuard '
    ..'was reported to close the game after them)'
function M.register_executable_data(address,size,label)
    assert(type(address)=='number'and address>0 and address%1==0 and type(size)=='number'and size>=1 and size<=64
        and size%1==0 and type(label)=='string','register_executable_data(address, size, label)')
    error(M.EXECUTABLE_DATA_CODE..': '..label..': '..M.EXECUTABLE_DATA_REASON,0)
end
-- The label of the registered extent holding [address, address + size): always nil, nothing is registered.
function M.reviewed_executable_data(address,size)return nil end
function M.reset_executable_data_for_tests()end
return M
