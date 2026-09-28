-- Maps a semantic target resource or validated spec kind to its guarded write domain.
local M={}
local modules={stratagem='hd2runtime/domains/stratagem_writes',
    entity='hd2runtime/domains/entity_writes',weapon='hd2runtime/domains/player_weapon_writes',
    attachment='hd2runtime/domains/attachment_writes'}
local by_resource={stratagem='stratagem',vehicle='entity',backpack='entity',weapon_attachment='attachment',
    player_weapon='weapon',support_weapon='weapon'}
function M.typed_resource(resource)return by_resource[resource]~=nil end
function M.typed_kind(kind)
    return kind=='stratagem'or kind=='entity'or kind=='attachment'or kind=='player_weapon'or kind=='support_weapon'
end
function M.key_for_kind(kind)
    if kind=='stratagem'or kind=='entity'or kind=='attachment'then return kind end
    return 'weapon'
end
function M.for_resource(resource)
    return require(modules[assert(by_resource[resource],'unsupported authoring target: '..tostring(resource))])
end
function M.for_kind(kind)return require(modules[M.key_for_kind(kind)])end
return M
