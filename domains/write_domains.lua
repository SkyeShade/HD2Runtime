-- Maps a semantic target resource or validated spec kind to its guarded write domain.
local M={}
local modules={stratagem='hd2runtime/domains/stratagem_writes',
    entity='hd2runtime/domains/entity_writes',weapon='hd2runtime/domains/player_weapon_writes',
    attachment='hd2runtime/domains/attachment_writes',booster='hd2runtime/domains/booster_writes',
    pod='hd2runtime/domains/pod_payload_writes',throwable='hd2runtime/domains/throwable_writes',
    enemy='hd2runtime/domains/enemy_writes',output='hd2runtime/domains/output_writes'}
local by_resource={stratagem='stratagem',vehicle='entity',backpack='entity',weapon_attachment='attachment',
    player_weapon='weapon',support_weapon='weapon',vehicle_weapon='weapon',booster='booster',pod_rack='pod',
    throwable='throwable',enemy='enemy',attack_output='output'}
function M.typed_resource(resource)return by_resource[resource]~=nil end
function M.typed_kind(kind)
    return kind=='stratagem'or kind=='entity'or kind=='attachment'or kind=='booster'or kind=='pod'
        or kind=='throwable'or kind=='player_weapon'or kind=='support_weapon'or kind=='vehicle_weapon'
        or kind=='enemy'or kind=='attack_output'
end
function M.key_for_kind(kind)
    if kind=='stratagem'or kind=='entity'or kind=='attachment'or kind=='booster'or kind=='pod'
        or kind=='throwable'or kind=='enemy'then return kind end
    if kind=='attack_output'then return 'output'end
    return 'weapon'
end
function M.for_resource(resource)
    return require(modules[assert(by_resource[resource],'unsupported authoring target: '..tostring(resource))])
end
function M.for_kind(kind)return require(modules[M.key_for_kind(kind)])end
return M
