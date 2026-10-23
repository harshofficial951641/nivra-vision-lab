"""Behavioral tests: no footage or model required."""
import math
import unittest

from .metrics import bootstrap, exposure_ms, point, poisson_upper, score_recording
from .policy import CameraPolicy, Policy, simulate


def windows(values):
    return [dict(timestampMs=4000 + 1000 * i, probability=p) for i, p in enumerate(values)]


def record(events=None, normal=None, group='g1'):
    return dict(group=group, context='classroom', durationMs=16000,
                events=events or [], normalIntervals=normal or [])


class PolicyTests(unittest.TestCase):
    def test_confirmation_strong_and_episode_merging(self):
        p = Policy(.4, .9)
        self.assertEqual(simulate(windows([.4, .4, .8, .95, .7, .7, .7, .7, .7, .7, .7]), p), [5000])
        self.assertEqual(simulate(windows([.9]), p), [4000])

    def test_cooldown_and_rearmed_episode(self):
        p = Policy(.4, .9)
        self.assertEqual(simulate(windows([.95, .1, .1, .1, .95, .95, .95, .95, .95]), p), [4000, 12000])

    def test_short_dip_merges_but_long_dip_rearms(self):
        p = Policy(.4, .9, cooldown_ms=0)
        self.assertEqual(simulate(windows([.9, .1, .9]), p), [4000])
        self.assertEqual(simulate(windows([.9, .1, .1, .9]), p), [4000, 7000])

    def test_gap_or_negative_resets_confirmation(self):
        state = CameraPolicy(Policy(.4, .9))
        self.assertFalse(state.update(4000, .5))
        self.assertFalse(state.update(6000, .5))
        self.assertFalse(state.update(7000, .1))
        self.assertFalse(state.update(8000, .5))
        self.assertTrue(state.update(9000, .5))

    def test_invalid_score_people_and_camera_isolation(self):
        p = Policy(.4, .9, require_two_people=True)
        state = CameraPolicy(p)
        self.assertFalse(state.update(4000, .95))
        self.assertFalse(state.update(5000, math.nan, 3))
        self.assertFalse(state.update(6000, .95, 1))
        self.assertTrue(state.update(7000, .95, 2))
        self.assertTrue(CameraPolicy(p).update(7000, .95, 2))

    def test_out_of_order_rejected(self):
        state = CameraPolicy(Policy(.4, .9))
        state.update(4000, .2)
        with self.assertRaises(ValueError):
            state.update(4000, .3)

    def test_threshold_and_cooldown_boundaries(self):
        p = Policy(.4, .9, cooldown_ms=8000)
        self.assertEqual(simulate(windows([.4, .4]), p), [5000])
        with self.assertRaises(ValueError):
            Policy(.8, .7)


class MetricsTests(unittest.TestCase):
    def test_event_tolerance_and_normal_precedence(self):
        events = [dict(startMs=1000, endMs=5000)]
        r = record(events, [dict(startMs=6500, endMs=10000)])
        self.assertEqual(score_recording(r, [6000])['hits'], 1)
        result = score_recording(r, [6500])
        self.assertEqual(result['hits'], 0)
        self.assertEqual(result['falseAlerts'], 1)
        self.assertEqual(score_recording(r, [7000])['hits'], 0)

    def test_one_alert_cannot_recall_two_events(self):
        r = record([dict(startMs=1000, endMs=5000), dict(startMs=2000, endMs=6000)])
        self.assertEqual(score_recording(r, [4000])['hits'], 1)
        self.assertEqual(score_recording(r, [4000, 5000])['hits'], 2)

    def test_maximum_matching_not_greedy_first_event(self):
        r = record([dict(startMs=4000, endMs=5000), dict(startMs=2000, endMs=7000)])
        self.assertEqual(score_recording(r, [3000, 4500])['hits'], 2)

    def test_exposure_union_warmup_and_unknown(self):
        spans = [dict(startMs=0, endMs=6000), dict(startMs=5000, endMs=10000)]
        self.assertEqual(exposure_ms(spans), 10000)
        result = score_recording(record(normal=spans), [4000, 10000, 15000])
        self.assertEqual(result['normalMs'], 6000)
        self.assertEqual(result['falseAlerts'], 1)
        self.assertEqual(result['unknownAlerts'], 2)
        self.assertEqual(point([result])['falseAlertsPerHour'], 600)

    def test_zero_denominators_and_short_clip(self):
        r = record([dict(startMs=0, endMs=2000)], [dict(startMs=2500, endMs=3500)])
        r['durationMs'] = 3500
        result = point([score_recording(r, [])])
        self.assertEqual(result['eventRecall'], 0)
        self.assertIsNone(result['falseAlertsPerHour'])
        self.assertIsNone(result['medianTimeToAlertMs'])

    def test_exposure_uses_actual_source_clock(self):
        r = record(normal=[dict(startMs=0, endMs=10000)])
        r.update(warmupEndMs=4100, replayEndMs=9900)
        result = score_recording(r, [])
        self.assertEqual(result['normalMs'], 5800)
        self.assertEqual(result['totalNormalMs'], 10000)

    def test_bootstrap_keeps_groups_and_is_reproducible(self):
        a = score_recording(record([dict(startMs=0, endMs=5000)], group='a'), [4000])
        b = score_recording(record([dict(startMs=0, endMs=5000)], group='b'), [])
        first = bootstrap([a, a, b], iterations=300)
        self.assertEqual(first, bootstrap([a, a, b], iterations=300))
        self.assertEqual(first['eventRecall']['eligibleGroups'], 2)
        self.assertEqual(first['eventRecall']['low'], 0)
        self.assertEqual(first['eventRecall']['high'], 1)
        self.assertIsNone(bootstrap([a], iterations=10)['eventRecall']['low'])

    def test_zero_false_bootstrap_does_not_prove_rate(self):
        self.assertAlmostEqual(poisson_upper(0, .25), -math.log(.025) / .25)
        self.assertGreater(poisson_upper(0, .25), 2)


if __name__ == '__main__':
    unittest.main()
