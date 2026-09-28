"""Versioned, local metadata store. Never accepts image or video fields."""
import json
import sqlite3
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, path):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
          INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
          CREATE TABLE IF NOT EXISTS cameras(id TEXT PRIMARY KEY, name TEXT NOT NULL,
            building TEXT NOT NULL, floor TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, camera_id TEXT NOT NULL,
            generation TEXT NOT NULL, source_id TEXT NOT NULL, received_at REAL NOT NULL,
            camera_name TEXT NOT NULL, location TEXT NOT NULL, source_ms REAL NOT NULL,
            evidence_ms REAL NOT NULL, model TEXT NOT NULL, detail TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', revision INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL, UNIQUE(camera_id,generation,source_id));
          CREATE TABLE IF NOT EXISTS event_audit(event_id TEXT NOT NULL, status TEXT NOT NULL,
            revision INTEGER NOT NULL, changed_at REAL NOT NULL);
        ''')
        if self.db.execute('SELECT version FROM schema_version').fetchone()[0] != 1:
            raise ValueError('Unsupported classroom metadata schema')

    def cameras(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM cameras ORDER BY created')]

    def camera(self, camera_id):
        r = self.db.execute('SELECT * FROM cameras WHERE id=?', (camera_id,)).fetchone()
        return dict(r) if r else None

    def add_camera(self, name, building, floor):
        if len(self.cameras()) >= 4:
            raise ValueError('This pilot supports at most four camera locations.')
        camera_id = str(uuid.uuid4())
        with self.db:
            self.db.execute('INSERT INTO cameras VALUES(?,?,?,?,1,?)',
                            (camera_id, name, building, floor, time.time()*1000))
        return self.camera(camera_id)

    def update_camera(self, camera_id, name, building, floor, enabled):
        with self.db:
            self.db.execute('UPDATE cameras SET name=?,building=?,floor=?,enabled=? WHERE id=?',
                            (name, building, floor, int(enabled), camera_id))
        return self.camera(camera_id)

    def events(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM events ORDER BY received_at DESC LIMIT 500')]

    def analytics(self):
        return dict(self.db.execute("SELECT COUNT(*) total, COALESCE(SUM(status='open'),0) pending, COALESCE(SUM(status='resolved'),0) resolved FROM events").fetchone())

    def record(self, camera_id, generation, event):
        camera = self.camera(camera_id)
        now = time.time()*1000
        with self.db:
            cursor = self.db.execute('''INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?, 'open',0,?)''',
                (str(uuid.uuid4()), camera_id, generation, str(event['id'])[:120], now,
                 camera['name'], camera['building']+' · '+camera['floor'],
                 float(event['occurredAtMs']), float(event.get('evidenceTimestampMs', event['occurredAtMs'])),
                 str(event.get('evidenceModel','slowfast-ava'))[:100], str(event.get('detail','Review the live scene.'))[:600], now))
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
            self.db.execute('INSERT INTO event_audit VALUES(?,?,?,?)', (event_id,status,revision+1,now))
        return dict(self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone())

    def close(self): self.db.close()
