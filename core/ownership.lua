-- Conflict rule shared by every typed write domain.
--
-- A guarded write may replace only the reviewed baseline (`expected`) or bytes that are
-- already desired. An option-bound ensure additionally owns the exact bytes it verified
-- live on its previous successful run (`change.owned`), so moving a setting from one
-- value to another is a transition, not a conflict. Anything else is a third-party value.
local metrics=require('hd2runtime/runtime/metrics')
local M={}
-- Returns the bytes the guarded transaction must find before writing.
function M.expected(change,current,label)
    if current==change.expected or current==change.desired then return change.expected end
    if type(change.owned)=='string'and current==change.owned then
        metrics.count('options.owned_transitions')
        return current
    end
    error('CONFLICT: '..tostring(label or change.field)..' is neither expected nor desired',0)
end
return M
