"""Versioned, local metadata store. Never accepts image or video fields."""
import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

GUARD_ALERT_FIELDS = ('id', 'camera_id', 'camera_name', 'location', 'detail', 'note',
                      'received_at', 'alerted_at', 'guard_ack_at', 'guard_declined_at',
                      'on_scene_at', 'status', 'revision', 'gps', 'police')


class PoliceContactRateLimit(ValueError):
    pass


def gps_record(row):
    result = dict(row)
    if 'gps' in result:
        result['gps'] = json.loads(result['gps']) if result['gps'] else None
    return result


class Store:
    def __init__(self, path):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute('PRAGMA journal_mode=WAL')
            with self.db:
                # Explicit BEGIN includes SQLite DDL in the migration transaction.
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute('CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)')
                version = self.db.execute('SELECT version FROM schema_version').fetchone()
                if version is not None and version[0] not in (1, 2, 3, 4, 5, 6, 7):
                    raise ValueError('Unsupported classroom metadata schema')
                if version is None:
                    self.db.execute('INSERT INTO schema_version VALUES(3)')
                    self.db.execute('''CREATE TABLE cameras(id TEXT PRIMARY KEY, name TEXT NOT NULL,
            building TEXT NOT NULL, floor TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            created REAL NOT NULL)''')
                    self.db.execute('''CREATE TABLE events(id TEXT PRIMARY KEY, camera_id TEXT NOT NULL,
            generation TEXT NOT NULL, source_id TEXT NOT NULL, received_at REAL NOT NULL,
            camera_name TEXT NOT NULL, location TEXT NOT NULL, source_ms REAL NOT NULL,
            evidence_ms REAL NOT NULL, model TEXT NOT NULL, detail TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', revision INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL, reviewed_at REAL, decision TEXT, reason TEXT,
            note TEXT, guard TEXT, decided_at REAL, alerted_at REAL, on_scene_at REAL,
            guard_ack_at REAL, guard_declined_at REAL,
            UNIQUE(camera_id,generation,source_id))''')
                    self.db.execute('''CREATE TABLE event_audit(event_id TEXT NOT NULL, status TEXT NOT NULL,
            revision INTEGER NOT NULL, changed_at REAL NOT NULL, action TEXT)''')
                elif version[0] == 1:
                    for column in ('reviewed_at REAL', 'decision TEXT', 'reason TEXT', 'note TEXT',
                                   'guard TEXT', 'decided_at REAL', 'alerted_at REAL', 'on_scene_at REAL'):
                        self.db.execute(f'ALTER TABLE events ADD COLUMN {column}')
                    self.db.execute('ALTER TABLE event_audit ADD COLUMN action TEXT')
                    self.db.execute('UPDATE schema_version SET version=2')
                if version is not None and version[0] in (1, 2):
                    self.db.execute('ALTER TABLE events ADD COLUMN guard_ack_at REAL')
                    self.db.execute('ALTER TABLE events ADD COLUMN guard_declined_at REAL')
                    self.db.execute('UPDATE schema_version SET version=3')
                if version is None or version[0] < 4:
                    self.db.execute('CREATE TABLE site(id TEXT PRIMARY KEY, name TEXT NOT NULL)')
                    self.db.execute('INSERT INTO site VALUES(?,?)', (str(uuid.uuid4()), 'NIVRA'))
                    self.db.execute('''CREATE TABLE floors(id TEXT PRIMARY KEY, name TEXT NOT NULL,
                        ord INTEGER NOT NULL, plan_path TEXT, plan_w INTEGER, plan_h INTEGER,
                        plan_hash TEXT, sample INTEGER NOT NULL DEFAULT 0,
                        meters_per_unit REAL, created REAL NOT NULL)''')
                    self.db.execute('''CREATE TABLE guards(id TEXT PRIMARY KEY, callsign TEXT NOT NULL UNIQUE,
                        name TEXT NOT NULL, user_id TEXT UNIQUE, email TEXT UNIQUE COLLATE NOCASE,
                        floor_id TEXT, post_x REAL, post_y REAL,
                        shift TEXT NOT NULL DEFAULT 'off' CHECK(shift IN ('on_shift','break','off')),
                        created REAL NOT NULL)''')
                    for column in ('label TEXT', 'floor_id TEXT', 'x REAL', 'y REAL',
                                   'angle REAL', 'fov REAL', 'range REAL'):
                        self.db.execute(f'ALTER TABLE cameras ADD COLUMN {column}')
                    for index, camera in enumerate(self.db.execute('SELECT id FROM cameras ORDER BY created,id').fetchall(), 1):
                        self.db.execute('UPDATE cameras SET label=? WHERE id=?', (f'CAM-{index:02d}', camera['id']))
                    for column in ('floor_id TEXT', 'reviewer_id TEXT', 'escalated_at REAL'):
                        self.db.execute(f'ALTER TABLE events ADD COLUMN {column}')
                    self.db.execute('ALTER TABLE event_audit ADD COLUMN actor TEXT')
                    self.db.execute('UPDATE schema_version SET version=4')
                if version is None or version[0] < 5:
                    self.db.execute('ALTER TABLE cameras ADD COLUMN gps TEXT')
                    self.db.execute('ALTER TABLE events ADD COLUMN gps TEXT')
                    self.db.execute('UPDATE schema_version SET version=5')
                if version is None or version[0] < 6:
                    self.db.execute('ALTER TABLE guards ADD COLUMN floor_name TEXT')
                    self.db.execute('ALTER TABLE guards ADD COLUMN gps TEXT')
                    self.db.execute('UPDATE schema_version SET version=6')
                self.db.execute('''CREATE TABLE IF NOT EXISTS device_sessions(
                    token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('camera','guard')),
                    subject_id TEXT NOT NULL, expires REAL NOT NULL)''')
                self.db.execute('CREATE INDEX IF NOT EXISTS device_session_subject ON device_sessions(kind,subject_id)')
                self.db.execute('UPDATE schema_version SET version=7')
                # H2 owns all DDL. H4 push storage participates in the same v4
                # transaction; IF NOT EXISTS also supports early v4 dev databases.
                self.db.execute('''CREATE TABLE IF NOT EXISTS guard_push_subscriptions(
                    endpoint TEXT PRIMARY KEY, guard_id TEXT NOT NULL, subscription TEXT NOT NULL)''')
                self.db.execute('CREATE INDEX IF NOT EXISTS guard_push_owner ON guard_push_subscriptions(guard_id)')
                self.db.execute('''CREATE TABLE IF NOT EXISTS guard_push_rounds(
                    event_id TEXT PRIMARY KEY, alerted_at REAL NOT NULL, guard TEXT NOT NULL,
                    last_round INTEGER NOT NULL)''')
        except Exception:
            self.db.close()
            raise

    def cameras(self):
        return [gps_record(r) for r in self.db.execute('SELECT * FROM cameras ORDER BY created')]

    def device_session(self, token_hash, kind):
        if kind not in ('camera', 'guard') or not re.fullmatch(r'[a-f0-9]{64}', token_hash): return None
        table = 'cameras' if kind == 'camera' else 'guards'
        extra = ' AND subject.enabled=1' if kind == 'camera' else ''
        row = self.db.execute(f'''SELECT session.*,subject.id AS valid_subject
            FROM device_sessions session JOIN {table} subject ON subject.id=session.subject_id
            WHERE session.token_hash=? AND session.kind=? AND session.expires>?{extra}''',
            (token_hash,kind,time.time())).fetchone()
        return dict(row) if row else None

    def device_sessions(self):
        return [session for row in self.db.execute('SELECT token_hash,kind FROM device_sessions').fetchall()
                if (session := self.device_session(row['token_hash'],row['kind'])) is not None]

    def save_device_session(self, token_hash, kind, subject_id, expires):
        if not re.fullmatch(r'[a-f0-9]{64}', token_hash) or kind not in ('camera','guard') or expires <= time.time():
            raise ValueError('Invalid device session')
        subject = self.camera(subject_id) if kind == 'camera' else self.guard(subject_id)
        if not subject or (kind == 'camera' and not subject['enabled']): raise ValueError('Device subject unavailable')
        with self.db:
            self.db.execute('DELETE FROM device_sessions WHERE expires<=?', (time.time(),))
            self.db.execute('INSERT INTO device_sessions VALUES(?,?,?,?)', (token_hash,kind,subject_id,expires))

    def revoke_device_sessions(self, *, kind, subject_id=None, token_hash=None):
        if kind not in ('camera','guard'): raise ValueError('Invalid device kind')
        if subject_id is None and token_hash is None: raise ValueError('Device subject required')
        field,value = ('subject_id',subject_id) if subject_id is not None else ('token_hash',token_hash)
        with self.db: self.db.execute(f'DELETE FROM device_sessions WHERE kind=? AND {field}=?', (kind,value))

    def camera(self, camera_id):
        r = self.db.execute('SELECT * FROM cameras WHERE id=?', (camera_id,)).fetchone()
        return gps_record(r) if r else None

    def add_camera(self, name, building, floor):
        camera_id = str(uuid.uuid4())
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            cameras = self.cameras()
            if len(cameras) >= self.max_cameras:
                raise ValueError(f'This site supports at most {self.max_cameras} camera locations.')
            labels = {camera['label'] for camera in cameras}
            number = 1
            while f'CAM-{number:02d}' in labels: number += 1
            self.db.execute('INSERT INTO cameras(id,name,building,floor,enabled,created,label) VALUES(?,?,?,?,1,?,?)',
                            (camera_id, name, building, floor, time.time()*1000, f'CAM-{number:02d}'))
        return self.camera(camera_id)

    def delete_camera(self, camera_id):
        """Remove a device and its access, retaining immutable event/audit history."""
        with self.db:
            camera = self.camera(camera_id)
            if camera is None: raise KeyError(camera_id)
            self.db.execute("DELETE FROM device_sessions WHERE kind='camera' AND subject_id=?", (camera_id,))
            self.db.execute('DELETE FROM cameras WHERE id=?', (camera_id,))
        return camera

    @property
    def max_cameras(self):
        return max(1, int(os.environ.get('NIVRA_MAX_CAMERAS', '12')))

    def update_camera(self, camera_id, name, building, floor, enabled):
        with self.db:
            self.db.execute('UPDATE cameras SET name=?,building=?,floor=?,enabled=? WHERE id=?',
                            (name, building, floor, int(enabled), camera_id))
        return self.camera(camera_id)

    def events(self):
        return self.with_police(self.db.execute('SELECT * FROM events ORDER BY received_at DESC LIMIT 500'))

    def with_police(self, rows):
        """Derive contact summaries in one query; police is never an events column."""
        records = [gps_record(row) for row in rows]
        if not records: return records
        ids = [row['id'] for row in records]
        contacts = {row['event_id']: dict(at=row['changed_at'], by=row['actor'],
                    method=row['action'][7:], count=row['contacts'])
            for row in self.db.execute(f'''SELECT * FROM (
                SELECT event_id,changed_at,actor,action,
                    COUNT(*) OVER (PARTITION BY event_id) AS contacts,
                    ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY changed_at DESC,rowid DESC) AS latest
                FROM event_audit WHERE action IN ('police:call','police:text')
                    AND event_id IN ({','.join('?' for _ in ids)})
            ) WHERE latest=1''', ids)}
        return [{**row, 'police': contacts.get(row['id'])} for row in records]

    def contact_police(self, event_id, method, actor, *, guard=None):
        if method not in ('call', 'text'): raise ValueError('Invalid police contact method.')
        with self.db:
            # Assignment, duplicate suppression and insert are atomic across connections.
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            if row is None or (guard is not None and row['guard'] != guard): raise KeyError(event_id)
            now = time.time()*1000
            action = 'police:'+method
            if self.db.execute('''SELECT 1 FROM event_audit WHERE event_id=? AND actor=?
                AND action=? AND changed_at>? LIMIT 1''', (event_id,actor,action,now-10_000)).fetchone():
                raise PoliceContactRateLimit('Wait 10 seconds before recording this contact again.')
            self.db.execute('''INSERT INTO event_audit(event_id,status,revision,changed_at,action,actor)
                VALUES(?,?,?,?,?,?)''', (event_id,row['status'],row['revision'],now,action,actor))
            return self.with_police([row])[0]['police']

    def analytics(self):
        return dict(self.db.execute("""SELECT COUNT(*) total,
            COALESCE(SUM(status='open'),0) pending, COALESCE(SUM(status='resolved'),0) resolved,
            COALESCE(SUM(decision='confirmed'),0) confirmed,
            COALESCE(SUM(decision='false_alarm'),0) falseAlarms FROM events""").fetchone())

    def record(self, camera_id, generation, event):
        camera = self.camera(camera_id)
        now = time.time()*1000
        with self.db:
            cursor = self.db.execute('''INSERT OR IGNORE INTO events
                (id,camera_id,generation,source_id,received_at,camera_name,location,source_ms,
                 evidence_ms,model,detail,status,revision,updated_at,floor_id,gps)
                VALUES(?,?,?,?,?,?,?,?,?,?,?, 'open',0,?,?,?)''',
                (str(uuid.uuid4()), camera_id, generation, str(event['id'])[:120], now,
                 camera['name'], camera['building']+' · '+camera['floor'],
                 float(event['occurredAtMs']), float(event.get('evidenceTimestampMs', event['occurredAtMs'])),
                 str(event.get('evidenceModel','slowfast-ava'))[:100], str(event.get('detail','Review the live scene.'))[:600], now, camera['floor_id'], json.dumps(camera['gps']) if camera['gps'] else None))
        return cursor.rowcount == 1

    def transition(self, event_id, status, revision):
        now = time.time()*1000
        with self.db:
            row = self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            if row is None: raise KeyError(event_id)
            if row['revision'] != revision: raise ValueError('Event changed. Refresh and try again.')
            allowed = {'open': {'acknowledged', 'resolved'}, 'acknowledged': {'resolved'}, 'resolved': set()}
            if status not in allowed[row['status']]: raise ValueError('Invalid event transition.')
            self.db.execute('UPDATE events SET status=?,revision=revision+1,updated_at=? WHERE id=?', (status,now,event_id))
            self.db.execute('INSERT INTO event_audit(event_id,status,revision,changed_at) VALUES(?,?,?,?)', (event_id,status,revision+1,now))
        return self.with_police(self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)))[0]

    def review(self, event_id, action, revision, *, reason=None, note=None, guard=None, actor=None) -> dict:
        with self.db:
            # Serialize revision checks and writes across connections to this database.
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            if row is None: raise KeyError(event_id)
            if action == 'view' and row['status'] in ('acknowledged', 'resolved'):
                return self.with_police([row])[0]
            if row['revision'] != revision: raise ValueError('Event changed. Refresh and try again.')
            now = time.time()*1000
            changes = {}
            if action == 'view' and row['status'] == 'open':
                changes.update(status='acknowledged', reviewed_at=now)
            elif action == 'confirm' and row['status'] in ('open', 'acknowledged') and row['decision'] is None:
                changes.update(decision='confirmed', status='acknowledged', decided_at=now,
                               reviewed_at=row['reviewed_at'] if row['reviewed_at'] is not None else now)
                if guard is not None:
                    changes.update(guard=guard, alerted_at=now, guard_ack_at=None,
                                   guard_declined_at=None, on_scene_at=None)
                if note is not None: changes['note'] = note
            elif action == 'dismiss' and row['status'] != 'resolved' and row['decision'] is None:
                if reason not in ('play_sport', 'greeting', 'camera_glitch', 'other'):
                    raise ValueError('Invalid review action.')
                changes.update(decision='false_alarm', reason=reason, status='resolved', decided_at=now,
                               reviewed_at=row['reviewed_at'] if row['reviewed_at'] is not None else now)
                if note is not None: changes['note'] = note
            elif action == 'alert' and row['decision'] == 'confirmed' and row['status'] == 'acknowledged':
                if not guard: raise ValueError('Invalid review action.')
                changes.update(guard=guard, alerted_at=now, on_scene_at=None,
                               guard_ack_at=None, guard_declined_at=None)
            elif action == 'on_scene' and row['alerted_at'] is not None and row['on_scene_at'] is None and row['status'] == 'acknowledged':
                changes['on_scene_at'] = now
            elif action == 'clear' and row['decision'] == 'confirmed' and row['status'] == 'acknowledged':
                changes['status'] = 'resolved'
            else:
                raise ValueError('Invalid review action.')
            changes['reviewer_id'] = actor
            if 'alerted_at' in changes: changes['escalated_at'] = None
            changes.update(revision=revision+1, updated_at=now)
            columns = ','.join(f'{key}=?' for key in changes)
            self.db.execute(f'UPDATE events SET {columns} WHERE id=?', (*changes.values(), event_id))
            self.db.execute('''INSERT INTO event_audit(event_id,status,revision,changed_at,action,actor)
                VALUES(?,?,?,?,?,?)''', (event_id, changes.get('status', row['status']), revision+1, now, action, actor))
            result = self.with_police(self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)))[0]
        return result

    def guard_alerts(self, guard, now=None):
        now = time.time()*1000 if now is None else now
        return self.with_police(self.db.execute(f'''SELECT {','.join(key for key in GUARD_ALERT_FIELDS if key != 'police')}
            FROM events WHERE guard=? AND decision='confirmed' AND alerted_at IS NOT NULL
            AND (status!='resolved' OR updated_at>=?) ORDER BY alerted_at DESC, id DESC LIMIT 10''',
            (guard, now-30*60*1000)))

    def guard_action(self, event_id, guard, action, revision, *, actor=None):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM events WHERE id=? AND guard=?', (event_id, guard)).fetchone()
            if row is None: raise KeyError(event_id)
            if row['revision'] != revision: raise ValueError('Event changed. Refresh and try again.')
            if row['decision'] != 'confirmed' or row['alerted_at'] is None or row['status'] != 'acknowledged':
                raise ValueError('Invalid guard action.')
            now = time.time()*1000
            changes = {}
            if action in ('ack', 'decline') and row['guard_ack_at'] is None and row['guard_declined_at'] is None:
                changes['guard_ack_at' if action == 'ack' else 'guard_declined_at'] = now
            elif action == 'on_scene' and row['guard_ack_at'] is not None and row['on_scene_at'] is None:
                changes['on_scene_at'] = now
            elif action == 'clear' and row['on_scene_at'] is not None:
                changes['status'] = 'resolved'
            else:
                raise ValueError('Invalid guard action.')
            changes.update(revision=revision+1, updated_at=now)
            columns = ','.join(f'{key}=?' for key in changes)
            self.db.execute(f'UPDATE events SET {columns} WHERE id=?', (*changes.values(), event_id))
            self.db.execute('''INSERT INTO event_audit(event_id,status,revision,changed_at,action,actor)
                VALUES(?,?,?,?,?,?)''', (event_id, changes.get('status', row['status']), revision+1, now, 'guard:'+action, actor))
            result = self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            return self.with_police([{key: result[key] for key in GUARD_ALERT_FIELDS if key != 'police'}])[0]

    def site(self):
        return dict(self.db.execute('SELECT * FROM site LIMIT 1').fetchone())

    def update_site(self, name):
        with self.db: self.db.execute('UPDATE site SET name=?', (name,))
        return self.site()

    def floors(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM floors ORDER BY ord,created,id')]

    def floor(self, floor_id):
        row = self.db.execute('SELECT * FROM floors WHERE id=?', (floor_id,)).fetchone()
        return dict(row) if row else None

    def _require_floor(self, floor_id):
        if floor_id is not None and self.floor(floor_id) is None:
            raise KeyError(floor_id)

    def add_floor(self, name):
        floor_id = str(uuid.uuid4())
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            order = self.db.execute('SELECT COALESCE(MAX(ord),-1)+1 FROM floors').fetchone()[0]
            self.db.execute('INSERT INTO floors(id,name,ord,created) VALUES(?,?,?,?)',
                            (floor_id, name, order, time.time()*1000))
        return self.floor(floor_id)

    def update_floor(self, floor_id, **changes):
        if not changes.keys() <= {'name', 'ord', 'meters_per_unit', 'plan_path', 'plan_w', 'plan_h', 'plan_hash', 'sample'}:
            raise ValueError('Unsupported floor field')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self._require_floor(floor_id)
            if changes:
                columns = ','.join(f'{key}=?' for key in changes)
                self.db.execute(f'UPDATE floors SET {columns} WHERE id=?', (*changes.values(), floor_id))
        return self.floor(floor_id)

    def delete_floor(self, floor_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self._require_floor(floor_id)
            row = self.floor(floor_id)
            self.db.execute('UPDATE cameras SET floor_id=NULL,x=NULL,y=NULL,angle=NULL,fov=NULL,range=NULL WHERE floor_id=?', (floor_id,))
            self.db.execute('UPDATE guards SET floor_id=NULL,post_x=NULL,post_y=NULL WHERE floor_id=?', (floor_id,))
            self.db.execute('DELETE FROM floors WHERE id=?', (floor_id,))
        return row

    def patch_camera(self, camera_id, **changes):
        if not changes.keys() <= {'name', 'building', 'floor', 'enabled', 'label', 'placement', 'gps'}:
            raise ValueError('Unsupported camera field')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.camera(camera_id) is None: raise KeyError(camera_id)
            if 'gps' in changes:
                changes['gps'] = json.dumps(changes['gps']) if changes['gps'] else None
            if 'placement' in changes:
                placement = changes.pop('placement')
                self._require_floor(placement['floorId'] if placement else None)
                changes.update({key: placement[source] if placement else None for key, source in
                                (('floor_id', 'floorId'), ('x', 'x'), ('y', 'y'), ('angle', 'angle'), ('fov', 'fov'), ('range', 'range'))})
            if changes:
                columns = ','.join(f'{key}=?' for key in changes)
                self.db.execute(f'UPDATE cameras SET {columns} WHERE id=?', (*changes.values(), camera_id))
                if 'enabled' in changes and not changes['enabled']:
                    self.db.execute("DELETE FROM device_sessions WHERE kind='camera' AND subject_id=?", (camera_id,))
        return self.camera(camera_id)

    def guards(self):
        return [gps_record(row) for row in self.db.execute('SELECT * FROM guards ORDER BY created,id')]

    def guard(self, guard_id):
        row = self.db.execute('SELECT * FROM guards WHERE id=?', (guard_id,)).fetchone()
        return gps_record(row) if row else None

    def guard_by_callsign(self, callsign):
        row = self.db.execute('SELECT * FROM guards WHERE callsign=?', (callsign,)).fetchone()
        return gps_record(row) if row else None

    def guard_by_user(self, user_id):
        row = self.db.execute('SELECT * FROM guards WHERE user_id=?', (user_id,)).fetchone()
        return gps_record(row) if row else None

    def guard_by_email(self, email):
        row = self.db.execute('SELECT * FROM guards WHERE email=?', (email.strip().lower(),)).fetchone()
        return gps_record(row) if row else None

    def add_guard(self, callsign, name, email=None, floor_id=None, post=None, floor_name=None):
        guard_id = str(uuid.uuid4())
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self._require_floor(floor_id)
            if post is not None and floor_id is None: raise ValueError('A guard post requires a floor.')
            self.db.execute('''INSERT INTO guards(id,callsign,name,email,floor_id,post_x,post_y,created,floor_name)
                VALUES(?,?,?,?,?,?,?,?,?)''', (guard_id, callsign, name, email.strip().lower() if email else None,
                floor_id, post['x'] if post else None, post['y'] if post else None, time.time()*1000, floor_name))
        return self.guard(guard_id)

    def update_guard(self, guard_id, **changes):
        if not changes.keys() <= {'callsign', 'name', 'email', 'floor_id', 'post', 'shift', 'user_id', 'floor_name', 'gps'}:
            raise ValueError('Unsupported guard field')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            guard = self.guard(guard_id)
            if guard is None: raise KeyError(guard_id)
            if 'gps' in changes:
                changes['gps'] = json.dumps(changes['gps']) if changes['gps'] else None
            floor_id = changes.get('floor_id', guard['floor_id'])
            self._require_floor(floor_id)
            if changes.get('email'): changes['email'] = changes['email'].strip().lower()
            if 'post' in changes:
                post = changes.pop('post')
                if post is not None and floor_id is None: raise ValueError('A guard post requires a floor.')
                changes.update(post_x=post['x'] if post else None, post_y=post['y'] if post else None)
            elif 'floor_id' in changes and floor_id != guard['floor_id']:
                changes.update(post_x=None, post_y=None)
            if changes:
                columns = ','.join(f'{key}=?' for key in changes)
                self.db.execute(f'UPDATE guards SET {columns} WHERE id=?', (*changes.values(), guard_id))
        return self.guard(guard_id)

    def link_guard_user(self, guard_id, user_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            guard = self.guard(guard_id)
            if guard is None: raise KeyError(guard_id)
            if guard['user_id'] is not None and guard['user_id'] != user_id:
                raise ValueError('Guard record belongs to another user.')
            try:
                self.db.execute('UPDATE guards SET user_id=? WHERE id=?', (user_id, guard_id))
            except sqlite3.IntegrityError as error:
                raise ValueError('User is already assigned to a guard.') from error
        return self.guard(guard_id)

    def set_shift(self, guard_id, shift):
        if shift not in ('on_shift', 'break', 'off'): raise ValueError('Invalid shift')
        return self.update_guard(guard_id, shift=shift)

    def delete_guard(self, guard_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            guard = self.guard(guard_id)
            if guard is None: raise KeyError(guard_id)
            self.db.execute('DELETE FROM guard_push_subscriptions WHERE guard_id=?', (guard_id,))
            self.db.execute("DELETE FROM device_sessions WHERE kind='guard' AND subject_id=?", (guard_id,))
            self.db.execute('DELETE FROM guards WHERE id=?', (guard_id,))
        return guard

    def close(self): self.db.close()
