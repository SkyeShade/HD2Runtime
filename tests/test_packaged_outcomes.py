"""The packaged validator's operation outcomes (scripts/validate_packaged_runtime.py).

A scenario passes only when every operation it registers applied, or is declared a negative control (refused, with
its reason) or not applicable. Registrations come from hd2.diagnostics.operations(), so an operation the addon kept
no handle for is still checked: a refused or skipped write can no longer pass because the resulting state looks
right."""
import sys
import unittest

from support import ROOT

sys.path.insert(0, str(ROOT / 'scripts'))
import validate_packaged_runtime as packaged  # noqa: E402


def op(identifier, status='complete', result='APPLIED', kind='patch', runs=None, error=None, legacy=()):
    return {'id': identifier, 'kind': kind, 'status': status, 'result': result, 'runs': runs, 'error': error,
        'legacy': list(legacy)}


def report(operations, final=None, log=(), writes=3, scenario='synthetic', watches=None):
    return {'scenario': scenario, 'settled': True, 'watches': watches or [], 'operations': operations,
        'operations_final': operations if final is None else final, 'log': list(log), 'counts': {'writes': writes},
        'lookups': {'late_missing': []}}


def failures(extras, value):
    saved = packaged.EXTRAS.get('synthetic')
    packaged.EXTRAS['synthetic'] = extras
    try:
        return packaged.check(value)
    finally:
        if saved is None:
            packaged.EXTRAS.pop('synthetic')
        else:
            packaged.EXTRAS['synthetic'] = saved


class OutcomeTests(unittest.TestCase):
    def test_outcome_classes(self):
        self.assertEqual(packaged.outcome(op('a')), 'applied')
        self.assertEqual(packaged.outcome(op('a', status='rejected', result='REJECTED')), 'rejected')
        self.assertEqual(packaged.outcome(op('a', status='complete', result='REJECTED')), 'rejected')
        self.assertEqual(packaged.outcome(op('a', status='unavailable', result=None)), 'not_applicable')
        self.assertEqual(packaged.outcome(op('a', status='disabled', result=None)), 'not_applicable')
        self.assertEqual(packaged.outcome(op('a', kind='ensure', status='waiting', result='APPLIED', runs=1)), 'applied')
        # An ensure that never ran, a blocked or cancelled one, or a pending patch never applied.
        self.assertEqual(packaged.outcome(op('a', kind='ensure', status='waiting', result=None, runs=0)), 'skipped')
        self.assertEqual(packaged.outcome(op('a', kind='ensure', status='blocked', result=None, runs=0)), 'skipped')
        self.assertEqual(packaged.outcome(op('a', status='cancelled', result=None)), 'skipped')
        self.assertEqual(packaged.outcome(op('a', status='retry_wait', result=None)), 'skipped')

    def test_every_registered_operation_must_apply(self):
        self.assertEqual(failures({}, report([op('a'), op('b', kind='ensure', status='waiting', runs=1)])), [])

    def test_a_refused_operation_fails_the_scenario_even_when_the_addon_kept_no_handle(self):
        # The addon returned only the handle of 'a' (watches); 'b' was refused at registration and dropped.
        value = report([op('a'), op('b', status='rejected', result='REJECTED', error='field requires x')],
            watches=[{'id': 'a', 'status': 'complete', 'result': 'APPLIED'}])
        problems = failures({}, value)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('b: rejected unexpectedly', problems[0])

    def test_a_skipped_write_fails_the_scenario(self):
        problems = failures({}, report([op('a'), op('b', kind='ensure', status='blocked', result=None, runs=0)]))
        self.assertTrue(any(p.startswith('b: skipped, never applied') for p in problems), problems)

    def test_expected_refusals_need_their_reason_and_must_not_apply(self):
        extras = {'rejected': {'b': 'allow_unverified_effect'}}
        reason = 'field requires allow_unverified_effect=true'
        refused = op('b', status='rejected', result='REJECTED', error=reason)
        logged = ['[HD2Runtime] ensure b rejected: ' + reason]
        self.assertEqual(failures(extras, report([op('a'), refused], log=logged)), [])
        other = op('b', status='rejected', result='REJECTED', error='expect differs from reviewed current value')
        problems = failures(extras, report([op('a'), other], log=['[HD2Runtime] ensure b rejected: expect differs']))
        self.assertTrue(any('refused for another reason' in p for p in problems), problems)
        problems = failures(extras, report([op('a'), op('b')]))
        self.assertTrue(any('expected a refusal' in p for p in problems), problems)
        problems = failures(extras, report([op('a')]))
        self.assertTrue(any('never registered' in p for p in problems), problems)

    def test_not_applicable_operations_must_be_declared(self):
        inactive = op('b', kind='ensure', status='unavailable', result=None, runs=0)
        self.assertIn('does not declare it unavailable', failures({}, report([op('a'), inactive]))[0])
        self.assertEqual(failures({'unavailable': ('b',)}, report([op('a'), inactive])), [])

    def test_a_default_off_option_counts_once_the_scenario_turns_it_on(self):
        off = op('t', kind='ensure', status='disabled', result=None, runs=0)
        on = op('t', kind='ensure', status='waiting', result='APPLIED', runs=1)
        self.assertEqual(failures({}, report([op('a'), off], final=[op('a'), on])), [])
        self.assertEqual(packaged.check_operations(report([op('a'), off], final=[op('a'), on]), {})[1]['applied'], 2)
        # Still off at the end, and not declared: it never applied.
        problems = failures({}, report([op('a'), off], final=[op('a'), off]))
        self.assertIn('does not declare it unavailable', problems[0])
        # An operation that applied at startup and was refused later is judged by its startup outcome.
        refused = op('a', status='rejected', result='REJECTED', error='x')
        self.assertEqual(failures({}, report([op('a')], final=[refused])), [])

    def test_legacy_operations_must_be_declared_and_logged(self):
        legacy = op('p', kind='ensure', status='waiting', runs=1, legacy=['projectile.drag'])
        line = '[HD2Runtime] ensure p: legacy SDK 0.27.0 operation from mods/x: ...'
        self.assertIn('applied only through the legacy SDK path', failures({}, report([legacy], log=[line]))[0])
        extras = {'legacy': {'p': ['projectile.drag']}}
        self.assertEqual(failures(extras, report([legacy], log=[line])), [])
        self.assertIn('without its log line', failures(extras, report([legacy]))[0])
        # Declared legacy, but refused (the 0.28.0 behaviour): the scenario fails.
        refused = op('p', status='rejected', result='REJECTED', error='field requires allow_unverified_effect=true')
        problems = failures(extras, report([refused]))
        self.assertTrue(any('rejected unexpectedly' in p for p in problems), problems)
        self.assertTrue(any('expected legacy fields' in p for p in problems), problems)

    def test_operations_registered_after_startup_are_checked_at_the_end(self):
        late = op('late', status='rejected', result='REJECTED', error='bad')
        problems = failures({}, report([op('a')], final=[op('a'), late]))
        self.assertEqual(problems, ['late: rejected unexpectedly (status=rejected result=REJECTED error=bad)'])

    def test_a_runtime_without_the_operation_list_fails(self):
        value = report([op('a')])
        value['operations'] = None
        self.assertIn('does not list its registered operations', failures({}, value)[0])

    def test_writes_match_the_scenario_kind(self):
        self.assertIn('no write reached the overlay', failures({}, report([op('a')], writes=0)))
        self.assertIn('read-only scenario wrote 2 times', failures({'readOnly': True}, report([], writes=2)))
        self.assertEqual(failures({'readOnly': True}, report([], writes=0)), [])

    def test_outcome_counts(self):
        value = report([op('a'), op('b', status='rejected', result='REJECTED', error='x')])
        self.assertEqual(packaged.check_operations(value, {'rejected': {'b': 'x'}})[1],
            {'applied': 1, 'legacy': 0, 'not_applicable': 0, 'rejected_expected': 1, 'rejected': 0, 'skipped': 0})

    def test_the_user_report_purifier_edit_is_expected_to_apply_as_legacy(self):
        extras = packaged.EXTRAS['user-report-full-project']
        self.assertNotIn('rejected', extras)
        self.assertEqual(extras['legacy'], {'gui-object-64f6c65514d7e06d97274943': ['projectile.drag']})


if __name__ == '__main__':
    unittest.main()
