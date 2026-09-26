-- HD2-Addon: mods/skyeshade/hd2runtime
local loader=rawget(_G,'CowboyBingusModLoader')
assert(loader and loader.api==1 and type(loader.version)=='number' and loader.version>=16,
    'HD2Runtime requires Bingus Shared Loader v15+ / API 1')
local existing=rawget(_G,'HD2RuntimeLibraryApi1')
if existing then return existing end
local hd2=require('hd2runtime/api/hd2')
rawset(_G,'HD2RuntimeLibraryApi1',hd2)
return hd2
