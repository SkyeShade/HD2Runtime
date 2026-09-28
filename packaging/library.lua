-- HD2-Addon: mods/skyeshade/hd2runtime
local loader=rawget(_G,'CowboyBingusModLoader')
assert(loader and loader.api==1 and type(loader.version)=='number' and loader.version>=16,
    'HD2Runtime requires Bingus Shared Loader v15+ / API 1')
local existing=rawget(_G,'HD2RuntimeLibraryApi1')
if existing then return existing end
-- The engine resolves archived Lua resources only while its startup package is
-- loaded. Modules first required later (at apply time, or on ensure drift) would
-- fail with "module not found". Capture every shipped module's loader now without
-- running it, so later require() calls resolve from package.preload.
local searchers=package.loaders or package.searchers
local missing={}
for _,name in ipairs(require('hd2runtime/runtime/package_modules'))do
    if package.loaded[name]==nil and package.preload[name]==nil then
        local found
        for index=2,#searchers do
            local candidate=searchers[index](name)
            if type(candidate)=='function' then found=candidate;break end
        end
        if found then package.preload[name]=found else missing[#missing+1]=name end
    end
end
assert(#missing==0,'HD2Runtime package is incomplete; unresolved modules: '..table.concat(missing,', '))
local hd2=require('hd2runtime/api/hd2')
rawset(_G,'HD2RuntimeLibraryApi1',hd2)
return hd2
