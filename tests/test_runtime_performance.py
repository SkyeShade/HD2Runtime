"""Steady-state cost regressions: ensured mods must go idle once their targets are stable."""
import json
import unittest

from support import ROOT, run


def check(body):
    return run((ROOT / 'tests/transaction_memory.lua').read_text() + '''
local hash=runtime.module_hash;local hashes=0
runtime.module_hash=function(name)hashes=hashes+1;return hash(name)end
local query=runtime.query;local queries=0
runtime.query=function(at)queries=queries+1;return query(at)end
local function typed_cooldown(id,expect,value)
    return {id=id or 'typed-cooldown',target=hd2.stratagem('FX-12 Shield Generator Relay'),
        field=hd2.fields.stratagem.definition_cooldown,expect=expect or 90,value=value or 180}
end
''' + body + "\nreturn 'ok'")


class RuntimePerformanceTests(unittest.TestCase):
    def test_typed_stratagem_cooldown_applies_end_to_end(self):
        # Regression: the stratagem row used to be captured twice, so the guarded
        # transaction found two contexts and refused every typed cooldown write.
        check('''
local w=finish(hd2.patch(typed_cooldown()))
assert(w.status=='complete' and w.result.status=='APPLIED',tostring(w.error))
assert(#writes==1 and writes[1].field=='cooldown')
assert(runtime.read(targets.cooldown.address,4)==targets.cooldown.new)
''')

    def test_ensured_mod_is_idle_after_steady_state(self):
        check('''
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0}
for _=1,3000 do e.tick(0);if e.runs==1 then break end end
assert(e.runs==1 and e.status=='waiting',tostring(e.error));assert_values('new')
local writes0,protections0,hashes0,queries0,logs0=#writes,#protections,hashes,queries,#logs
local reads0=runtime.reads
for _=1,24*3600 do e.tick(1)end
assert(e.runs==1,'full resolution repeated in steady state: '..e.runs)
assert(hashes==hashes0,'module hashed in steady state')
assert(#writes==writes0 and #protections==protections0,'writes/protection changes in steady state')
assert(e.current_interval==600,'interval did not back off: '..e.current_interval)
assert(e.verifications>0 and e.verifications<=160,'verifications='..e.verifications)
local per=(runtime.reads-reads0)/e.verifications
assert(per<=8,'steady verification reads too much: '..per)
assert((queries-queries0)/e.verifications<=8,'steady verification queries too much')
assert(#logs-logs0<=1,'steady state logs every cycle: '..(#logs-logs0))
-- A game reinitialization (target back to vanilla) is detected and fully reapplied.
replace(targets.lifetime.address,targets.lifetime.old)
for _=1,700 do e.tick(1);if e.runs==2 then break end end
assert(e.runs==2 and e.drifts==1 and #writes==writes0+1 and writes[#writes].field=='lifetime')
assert(e.current_interval==60,'interval not reset after drift')
assert_values('new');protection_is(2)
''')

    def test_fingerprint_hashed_once_per_process(self):
        check('''
local w=transaction();assert(w.status=='complete',w.error)
local first=hashes;assert(first==2,'first operation hashed '..first)
for target_name,target in pairs(targets)do replace(target.address,target.old)end
w=transaction();assert(w.status=='complete',w.error)
w=finish(hd2.patch(typed_cooldown('again')));assert(w.result.status=='ALREADY_DESIRED',tostring(w.error))
assert(hashes==first,'module files re-hashed: '..hashes)
local m=hd2.metrics().counters
assert(m['fingerprint.module_hashes']==2 and m['fingerprint.cache_hits']>=4)
''')

    def test_operations_are_serialized_and_gate_released(self):
        check('''
local a=hd2.transaction(transaction_request())
local b=hd2.patch(typed_cooldown('queued'))
a.tick(3.1);b.tick(3.1)
assert(b.status=='queued','second operation was not queued: '..b.status)
finish(a);assert(a.status=='complete',a.error)
finish(b);assert(b.status=='complete' and b.result.status=='ALREADY_DESIRED',tostring(b.error))
-- Cancellation and rejection release the gate.
local c=hd2.patch(typed_cooldown('cancelled'));c.tick(3.1);assert(c.status~='queued');c.cancel()
replace(targets.cooldown.address,string.char(1,2,3,4))
local d=finish(hd2.patch(typed_cooldown('rejected')))
assert(d.status=='rejected' and d.result.code=='CONFLICT')
replace(targets.cooldown.address,targets.cooldown.old)
local f=finish(hd2.patch(typed_cooldown('after')))
assert(f.status=='complete' and f.result.status=='APPLIED',tostring(f.error))
-- Time spent queued does not consume the resolution budget.
for _,target in pairs(targets)do replace(target.address,target.old)end
local g=hd2.transaction(transaction_request());g.tick(3.1)
local h=hd2.patch(typed_cooldown('long-wait'))
for _=1,400 do h.tick(1)end
assert(h.status=='queued','budget consumed while queued: '..h.status)
finish(g);finish(h);assert(h.status=='complete',tostring(h.error))
''')

    def test_steady_state_audit_on_real_snapshot(self):
        audit = json.loads((ROOT / 'validation/steady-state-audit.json').read_text())
        self.assertGreaterEqual(audit['steadySeconds'], 3600)
        self.assertFalse(audit['gameProcessAccess'])
        for scenario in audit['scenarios']:
            name = ','.join(scenario['mods'])
            for watch in scenario['watches']:
                self.assertNotEqual(watch['status'], 'rejected', (name, watch))
            steady = scenario['steady']
            for key in ('module_hashes', 'writes', 'identical_writes', 'protection_changes'):
                self.assertEqual(steady['adapter'][key], 0, (name, key))
            for key in ('discover.walks', 'entity_catalog.captures', 'stratagem.table_captures',
                    'transaction.applies', 'ensure.full_resolutions'):
                self.assertEqual(steady['metrics'].get(key, 0), 0, (name, key))
            if 'reinitialize' in scenario:
                self.assertTrue(scenario['reinitialize']['detected_and_reapplied'], name)
                self.assertEqual(scenario['reinitialize']['adapter']['module_hashes'], 0, name)
        combined = audit['scenarios'][-1]
        self.assertEqual(len(combined['mods']), 7)
        self.assertEqual(combined['startup']['adapter']['module_hashes'], 2)
        before = json.loads((ROOT / 'validation/steady-state-audit-before-0.23.0-22ec478.json').read_text())
        self.assertGreater(before['scenarios'][-1]['steady']['adapter']['module_hashes'], 100)

    def test_metrics_are_exported_without_process_access(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local m=hd2.metrics()
assert(type(m.counters)=='table' and type(m.worst_seconds)=='table')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
