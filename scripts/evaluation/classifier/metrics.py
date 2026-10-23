"""Explicit-label event metrics and whole-group percentile confidence intervals."""
from __future__ import annotations

import math
import numpy as np


def union(spans):
    result = []
    for a, b in sorted((float(x['startMs']), float(x['endMs'])) for x in spans):
        if not math.isfinite(a + b) or a < 0 or a >= b:
            raise ValueError('invalid interval')
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return [{'startMs': a, 'endMs': b} for a, b in result]


def contains(spans, t):
    return any(s['startMs'] <= t < s['endMs'] for s in spans)


def exposure_ms(spans, start=0, end=math.inf):
    return sum(max(0, min(x['endMs'], end) - max(x['startMs'], start)) for x in union(spans))


def score_recording(record, alerts, warmup_ms=4000, tolerance_ms=2000):
    """One-to-one maximum event matching; explicit normal overrides late grace."""
    events = sorted(record['events'], key=lambda e: (e['endMs'], e['startMs']))
    normal = union(record['normalIntervals'])
    ordered = sorted(alerts)
    assigned = {}

    def eligible(event, t):
        if event['startMs'] <= t < event['endMs']:
            return True
        return event['endMs'] <= t < event['endMs'] + tolerance_ms and not contains(normal, t)

    def match(e, visited):
        for a, t in enumerate(ordered):
            if a in visited or not eligible(events[e], t):
                continue
            visited.add(a)
            if a not in assigned or match(assigned[a], visited):
                assigned[a] = e
                return True
        return False

    for e in range(len(events)):
        match(e, set())
    return dict(group=record['group'], context=record['context'], recordings=1,
                eventCount=len(events), hits=len(assigned),
                falseAlerts=sum(contains(normal, t) for t in ordered),
                normalMs=exposure_ms(normal, record.get('warmupEndMs', warmup_ms),
                                     min(record['durationMs'], record.get('replayEndMs', record['durationMs']))),
                totalNormalMs=exposure_ms(normal, 0, record['durationMs']),
                latenciesMs=[ordered[a] - events[e]['startMs'] for a, e in assigned.items()],
                alertCount=len(ordered),
                unknownAlerts=sum(not contains(normal, t) and not any(eligible(e, t) for e in events) for t in ordered))


def quantile(values, q):
    return float(np.quantile(values, q)) if len(values) else None


def point(rows):
    def total(k):
        return sum(r[k] for r in rows)
    events, hits, hours = total('eventCount'), total('hits'), total('normalMs') / 3600000
    delays = [t for r in rows for t in r['latenciesMs']]
    return dict(recordings=total('recordings'), groups=len({r['group'] for r in rows}),
                positiveGroups=len({r['group'] for r in rows if r['eventCount']}),
                normalGroups=len({r['group'] for r in rows if r['normalMs']}),
                eventCount=events, hits=hits, eventRecall=hits / events if events else None,
                falseAlerts=total('falseAlerts'), normalHours=hours,
                totalExplicitNormalHours=total('totalNormalMs') / 3600000,
                falseAlertsPerHour=total('falseAlerts') / hours if hours else None,
                medianTimeToAlertMs=quantile(delays, .5), p90TimeToAlertMs=quantile(delays, .9),
                alertCount=total('alertCount'), unknownAlerts=total('unknownAlerts'))


def poisson_upper(count, hours, alpha=.025):
    """Exact Poisson 97.5% upper rate; exposure diagnostic, not a group CI."""
    if hours <= 0:
        return None
    def cdf(mean):
        if mean == 0:
            return 1.
        return sum(math.exp(-mean + k * math.log(mean) - math.lgamma(k + 1)) for k in range(count + 1))
    low, high = 0., max(10., count + 10 * math.sqrt(count + 1))
    while cdf(high) > alpha:
        high *= 2
    for _ in range(70):
        middle = (low + high) / 2
        if cdf(middle) > alpha:
            low = middle
        else:
            high = middle
    return high / hours


def bootstrap(rows, iterations=5000, seed=20261023):
    groups = sorted({r['group'] for r in rows})
    buckets = [[r for r in rows if r['group'] == g] for g in groups]
    keys = ['eventRecall', 'falseAlertsPerHour', 'medianTimeToAlertMs', 'p90TimeToAlertMs']
    values = {k: [] for k in keys}
    eligible = dict(eventRecall=len({r['group'] for r in rows if r['eventCount']}),
                    falseAlertsPerHour=len({r['group'] for r in rows if r['normalMs']}),
                    medianTimeToAlertMs=len({r['group'] for r in rows if r['latenciesMs']}),
                    p90TimeToAlertMs=len({r['group'] for r in rows if r['latenciesMs']}))
    rng = np.random.default_rng(seed)
    for _ in range(iterations if groups else 0):
        sampled = [r for i in rng.integers(0, len(groups), len(groups)) for r in buckets[i]]
        result = point(sampled)
        for k in keys:
            if result[k] is not None:
                values[k].append(result[k])
    return {k: dict(low=quantile(v, .025) if eligible[k] >= 2 else None,
                    high=quantile(v, .975) if eligible[k] >= 2 else None,
                    eligibleGroups=eligible[k], validReplicates=len(v), iterations=iterations)
            for k, v in values.items()}


def summary(rows, iterations=5000):
    result = point(rows)
    result['ci95'] = bootstrap(rows, iterations)
    result['poissonUpper97_5PerHour'] = poisson_upper(result['falseAlerts'], result['normalHours'])
    result['contexts'] = {}
    for context in sorted({r['context'] for r in rows}):
        subset = [r for r in rows if r['context'] == context]
        p = point(subset)
        p['ci95'] = bootstrap(subset, iterations)
        p['poissonUpper97_5PerHour'] = poisson_upper(p['falseAlerts'], p['normalHours'])
        result['contexts'][context] = p
    return result
