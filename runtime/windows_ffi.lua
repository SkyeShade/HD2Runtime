-- Read-only Win32 declarations for the separate diagnostic.
local KEY = 'HD2RuntimeWindowsFfiV1'
local existing = rawget(_G, KEY)
if existing then return existing end

local ffi = require('ffi')
assert(ffi.abi('64bit'), 'Windows x64 LuaJIT is required')
ffi.cdef [[
    void *GetModuleHandleA(const char *name);
    void *GetProcAddress(void *module, const char *name);
    uint32_t GetModuleFileNameW(void *module, uint16_t *path, uint32_t capacity);
    void *GetCurrentProcess(void);
    int ReadProcessMemory(void *process, const void *address, void *buffer,
                          size_t size, size_t *read);
    uint32_t GetLastError(void);
    typedef struct HD2RuntimeMemoryRegion {
        void *base; void *allocation_base; uint32_t allocation_protection;
        uint16_t partition; uint16_t reserved; size_t size;
        uint32_t state; uint32_t protection; uint32_t type;
    } HD2RuntimeMemoryRegion;
    typedef struct HD2RuntimeSystemInfo {
        uint32_t oem_id; uint32_t page_size;
        void *minimum_address; void *maximum_address;
        size_t active_processor_mask;
        uint32_t processor_count; uint32_t processor_type;
        uint32_t allocation_granularity; uint16_t processor_level;
        uint16_t processor_revision;
    } HD2RuntimeSystemInfo;
    size_t VirtualQuery(const void *address, void *region, size_t size);
    void *CreateFileW(const uint16_t *path, uint32_t access, uint32_t share,
                      void *security, uint32_t disposition, uint32_t flags,
                      void *template_file);
    int ReadFile(void *file, void *buffer, uint32_t size, uint32_t *read,
                 void *overlapped);
    int CloseHandle(void *handle);
    int32_t BCryptOpenAlgorithmProvider(void **algorithm, const uint16_t *name,
                                         const uint16_t *provider, uint32_t flags);
    int32_t BCryptCloseAlgorithmProvider(void *algorithm, uint32_t flags);
    int32_t BCryptCreateHash(void *algorithm, void **hash, void *object,
                              uint32_t object_size, const void *secret,
                              uint32_t secret_size, uint32_t flags);
    int32_t BCryptHashData(void *hash, const void *data, uint32_t size,
                            uint32_t flags);
    int32_t BCryptFinishHash(void *hash, void *digest, uint32_t size,
                              uint32_t flags);
    int32_t BCryptDestroyHash(void *hash);
]]
assert(ffi.sizeof('HD2RuntimeSystemInfo') == 48, 'unexpected SYSTEM_INFO size')
local kernel, bcrypt = ffi.load('kernel32'), ffi.load('bcrypt')
local address = kernel.GetProcAddress(kernel.GetModuleHandleA('kernel32.dll'), 'GetSystemInfo')
assert(address ~= nil, 'GetSystemInfo export unavailable')
local get_system_info = ffi.cast(
    'void (__stdcall *)(HD2RuntimeSystemInfo *)', address)
local bindings = {ffi=ffi,kernel=kernel,bcrypt=bcrypt,get_system_info=get_system_info}
rawset(_G, KEY, bindings)
return bindings
