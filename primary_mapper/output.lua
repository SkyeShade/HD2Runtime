local json=require('hd2runtime/primary_mapper/json')
local M={}
local function write(path,body)
    local file,why=io.open(path,'wb');assert(file,why)
    local ok,err=pcall(function()assert(file:write(body));file:flush()end)
    file:close();assert(ok,err)
end
function M.write(report,mapping,lines)
    local loader=assert(rawget(_G,'CowboyBingusModLoader'),'Bingus loader unavailable')
    local sink=assert(loader.open_log('PrimaryWeaponRuntimeMap.log'))
    for _,line in ipairs(lines)do sink:write('[HD2Runtime] '..line..'\n')end
    if sink.flush then sink:flush()end
    local localdata=assert(os.getenv('LOCALAPPDATA'),'LOCALAPPDATA unavailable')
    local folder=localdata..'\\CowboyBingus\\Helldivers2\\Logs\\'
    write(folder..'PrimaryWeaponRuntimeMap.json',json.encode(report)..'\n')
    write(folder..'weapon_identity_candidates.json',json.encode(mapping)..'\n')
    return {report=folder..'PrimaryWeaponRuntimeMap.json',log=folder..'PrimaryWeaponRuntimeMap.log',
        mapping=folder..'weapon_identity_candidates.json'}
end
return M
