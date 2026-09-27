-- Compatibility adapter: a patch is a one-change guarded transaction.
local transaction=require('hd2runtime/core/guarded_transaction')
local M={}
function M.apply(runtime,plan)
    local transaction_plan=plan.changes and plan or{snapshots=plan.snapshots,changes={{
        label='armor_penetration',owner=plan.owner,offset=plan.offset,
        expected=plan.already_desired and plan.new or plan.old,desired=plan.new,
        before=plan.old,already_desired=plan.already_desired,
        identity=plan.identity,chain=plan.chain,
    }}}
    local result=transaction.apply(runtime,transaction_plan)
    result.write_attempted=result.writes>0
    return result
end
return M
