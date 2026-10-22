"""Police audit logging preserves lifecycle revisions and capability isolation."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from nivra.classroom_store import Store, PoliceContactRateLimit, GUARD_ALERT_FIELDS
from test_classroom import review_client, post_review, guard_phone, ORIGIN
from test_workspaces import env as workspace_env, create, camera, pair


def contact(client, event, method='call', guard=False, **extra):
    prefix = '/api/v2/guard' if guard else '/api/v2'
    return client.post(f'{prefix}/events/{event["id"]}/police',
                       headers=ORIGIN, json=dict(method=method, **extra))


@pytest.mark.parametrize('role', ['reviewer', 'admin'])
@pytest.mark.parametrize('method', ['call', 'text'])
def test_reviewer_contact_audit_revision_snapshot_and_broadcast(review_client, role, method):
    client, store, event = review_client
    reviewer = TestClient(client.app, base_url=ORIGIN['origin']); reviewer.portal = client.portal
    try:
        assert reviewer.post('/api/v2/auth/dev', headers=ORIGIN, json={'name': 'Reviewer', 'role': role}).status_code == 200
        actor = reviewer.get('/api/v2/me').json()['userId']
        service = client.app.state.classroom
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator', headers=ORIGIN) as wall:
            assert wall.receive_json()['events'][0]['police'] is None
            response = contact(reviewer, event, method)
            assert response.status_code == 200, response.text
            police = response.json()['police']
            assert police == dict(at=police['at'], by=actor, method=method, count=1)
            assert wall.receive_json()['events'][0]['police'] == police
        assert service.snapshot()['events'][0]['police'] == police
        current = store.events()[0]
        assert current['revision'] == event['revision']
        assert current['updated_at'] == event['updated_at']
        row = dict(store.db.execute('SELECT * FROM event_audit').fetchone())
        assert row == dict(event_id=event['id'], status=event['status'], revision=event['revision'],
                          changed_at=police['at'], action='police:'+method, actor=actor)
        # A review using the revision held before contacting police must still succeed.
        assert post_review(reviewer, event, 'confirm').status_code == 200
        assert store.db.execute('SELECT version FROM schema_version').fetchone()[0] == 7
    finally: reviewer.close()


@pytest.mark.parametrize('method', ['call', 'text'])
def test_guard_contact_requires_assignment_and_updates_both_payloads(review_client, method):
    client, store, event = review_client
    phone, other = guard_phone(client, 'G2'), guard_phone(client, 'G3')
    try:
        assert contact(phone, event, method, guard=True).status_code == 404
        event = post_review(client, event, 'confirm', guard='G2').json()
        assert contact(other, event, method, guard=True).status_code == 404
        with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as stream:
            assert stream.receive_json()['alerts'][0]['police'] is None
            response = contact(phone, event, method, guard=True)
            assert response.status_code == 200, response.text
            police = response.json()['police']
            assert police['by'] == 'guard:G2' and police['method'] == method and police['count'] == 1
            alert = stream.receive_json()['alerts'][0]
            assert alert['police'] == police
            assert set(alert) == set(GUARD_ALERT_FIELDS) | {'placement', 'floorId'}
        assert store.guard_alerts('G2')[0]['police'] == police
        assert client.get('/api/v2/state').json()['events'][0]['police'] == police
        assert store.events()[0]['revision'] == event['revision']
        ack = phone.post(f'/api/v2/guard/events/{event["id"]}', headers=ORIGIN, json=dict(action='ack', revision=event['revision']))
        assert ack.status_code == 200 and ack.json()['police'] == police
        row = store.db.execute("SELECT * FROM event_audit WHERE action=?", ('police:'+method,)).fetchone()
        assert row['actor'] == 'guard:G2' and row['revision'] == event['revision']
    finally: phone.close(); other.close()


@pytest.mark.parametrize('guard', [False, True])
@pytest.mark.parametrize('payload', [{}, {'method': 'email'}, {'method': 'CALL'}, {'method': None}, {'method': 112}, {'method': 'call', 'revision': 0}])
def test_method_validation_does_not_write(review_client, guard, payload):
    client, store, event = review_client
    phone = guard_phone(client) if guard else None
    try:
        prefix = '/api/v2/guard' if guard else '/api/v2'
        response = (phone or client).post(f'{prefix}/events/{event["id"]}/police', headers=ORIGIN, json=payload)
        assert response.status_code == 422
        assert store.db.execute('SELECT COUNT(*) FROM event_audit').fetchone()[0] == 0
    finally:
        if phone: phone.close()


def test_auth_origin_and_unknown_event_refused(review_client):
    client, store, event = review_client
    anon = TestClient(client.app, base_url=ORIGIN['origin']); anon.portal = client.portal
    phone = guard_phone(client)
    try:
        for guard in (False, True):
            assert contact(anon, event, guard=guard).status_code in (401, 403)
            prefix = '/api/v2/guard' if guard else '/api/v2'
            assert (phone if guard else client).post(f'{prefix}/events/{event["id"]}/police', headers={'origin': 'https://evil.test'}, json={'method': 'call'}).status_code == 403
        assert contact(phone, event).status_code == 403
        assert contact(client, {'id': 'missing'}).status_code == 404
        assert store.db.execute('SELECT COUNT(*) FROM event_audit').fetchone()[0] == 0
    finally: anon.close(); phone.close()


def test_duplicate_rate_limit_per_actor_method_and_event(review_client, monkeypatch):
    client, store, event = review_client
    import nivra.classroom_store as module
    clock = [1_800_000_000.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock[0]))
    assert contact(client, event).status_code == 200
    duplicate = contact(client, event)
    assert duplicate.status_code == 429 and duplicate.headers['retry-after'] == '10'
    assert contact(client, event, 'text').json()['police']['count'] == 2
    reviewer = TestClient(client.app, base_url=ORIGIN['origin']); reviewer.portal = client.portal
    try:
        reviewer.post('/api/v2/auth/dev', headers=ORIGIN, json={'name': 'Second', 'role': 'reviewer'})
        assert contact(reviewer, event).json()['police']['count'] == 3
    finally: reviewer.close()
    clock[0] += 9.999
    assert contact(client, event).status_code == 429
    clock[0] += .001
    result = contact(client, event)
    assert result.status_code == 200 and result.json()['police']['count'] == 4
    assert store.events()[0]['revision'] == 0


def test_simultaneous_duplicate_writes_are_serialized(review_client):
    _, store, event = review_client
    path = store.db.execute('PRAGMA database_list').fetchone()[2]
    connections = [Store(path), Store(path)]
    barrier = Barrier(2)
    def write(connection):
        barrier.wait()
        try: connection.contact_police(event['id'], 'call', 'same-actor'); return 'recorded'
        except PoliceContactRateLimit: return 'limited'
    try:
        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(write, connections)) == ['limited', 'recorded']
        assert store.events()[0]['police']['count'] == 1
    finally:
        for connection in connections: connection.close()


def test_contact_failure_rolls_back_and_does_not_broadcast(review_client, monkeypatch):
    client, store, event = review_client
    service = client.app.state.classroom
    broadcast = AsyncMock()
    monkeypatch.setattr(service, 'broadcast', broadcast)
    with store.db:
        store.db.execute("CREATE TRIGGER reject_police BEFORE INSERT ON event_audit WHEN NEW.action LIKE 'police:%' BEGIN SELECT RAISE(ABORT,'test failure'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError): contact(client, event)
    assert store.db.execute('SELECT COUNT(*) FROM event_audit').fetchone()[0] == 0
    assert store.events()[0]['revision'] == event['revision']
    broadcast.assert_not_called()


def test_other_workspace_owner_and_guard_cannot_log(workspace_env):
    manager, _, make_client = workspace_env
    a, b, guard_a, guard_b, anon = [make_client() for _ in range(5)]
    wa, wb = create(a, 'Police A'), create(b, 'Police B')
    ca = camera(a, 'Entrance A')
    sa, sb = manager.apps[wa['id']].state.classroom.store, manager.apps[wb['id']].state.classroom.store
    sa.add_guard('G2', 'Guard A'); sb.add_guard('G2', 'Guard B')
    pair(a, guard_a, '/api/v2/guards/G2/pair'); pair(b, guard_b, '/api/v2/guards/G2/pair')
    sa.record(ca['id'], 'test', dict(id='1', occurredAtMs=1))
    event = sa.review(sa.events()[0]['id'], 'confirm', 0, guard='G2', actor='owner-a')
    for caller, guard, expected in [(b, False, 404), (guard_b, True, 404), (anon, False, 403), (anon, True, 403)]:
        prefix = '/api/v2/guard' if guard else '/api/v2'
        r = caller.post(f'{prefix}/events/{event["id"]}/police', json={'method': 'call'})
        assert r.status_code == expected, r.text
    assert sa.events()[0]['police'] is None and not sb.events()
    assert guard_a.post(f'/api/v2/guard/events/{event["id"]}/police', json={'method': 'text'}).status_code == 200
    assert a.get('/api/v2/state').json()['events'][0]['police']['by'] == 'guard:G2'


def test_police_queries_are_batched_and_search_only_relevant_audit_rows(tmp_path):
    store = Store(tmp_path / 'police-index.sqlite')
    try:
        camera = store.add_camera('Entrance', 'Main', '1')
        for i in range(500):
            store.record(camera['id'], 'query-cost', dict(id=str(i), occurredAtMs=i))
        event_id = store.events()[0]['id']
        with store.db:
            store.db.executemany("""INSERT INTO event_audit(event_id,status,revision,changed_at,action,actor)
                VALUES(?,?,?,?,?,?)""", [('unrelated-'+str(i), 'resolved', 0, i, 'confirm', 'qa') for i in range(2000)])
        queries = []
        store.db.set_trace_callback(queries.append)
        police = store.contact_police(event_id, 'call', 'qa')
        events = store.events()
        store.db.set_trace_callback(None)
        assert len(events) == 500
        assert next(e for e in events if e['id'] == event_id)['police'] == police
        summaries = [q for q in queries if 'COUNT(*) OVER' in q]
        lookups = [q for q in queries if 'SELECT 1 FROM event_audit' in q]
        assert len(summaries) == 2 and len(lookups) == 1
        for query in summaries + lookups:
            plan = [row['detail'] for row in store.db.execute('EXPLAIN QUERY PLAN '+query)]
            assert any('SEARCH event_audit ' in detail for detail in plan), plan
        with store.db:
            store.db.execute('DROP INDEX event_audit_police_lookup')
    finally:
        store.close()
    # Existing v7 stores must also get the lookup index on reopen.
    reopened = Store(tmp_path / 'police-index.sqlite')
    try:
        assert reopened.events()[0]['police'] == police
        assert reopened.contact_police(event_id, 'text', 'qa')['count'] == 2
        for query in summaries + lookups:
            plan = [row['detail'] for row in reopened.db.execute('EXPLAIN QUERY PLAN '+query)]
            assert any('SEARCH event_audit ' in detail for detail in plan), plan
    finally:
        reopened.close()
