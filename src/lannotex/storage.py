"""Versioned SQLite projects. Every worker owns its connection."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from .domain import Annotation, validate_all

# Migration 1 matches the shipped prototype; changes are appended.
MIGRATIONS = [
    ["CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, width INTEGER, height INTEGER, status TEXT NOT NULL DEFAULT 'new')",
     "CREATE TABLE IF NOT EXISTS labels(name TEXT PRIMARY KEY, color TEXT NOT NULL DEFAULT '#38bdf8')",
     "CREATE TABLE IF NOT EXISTS annotations(id TEXT PRIMARY KEY, image_id INTEGER NOT NULL, data TEXT NOT NULL, FOREIGN KEY(image_id) REFERENCES images(id))",
     "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)"],
    ["CREATE INDEX IF NOT EXISTS annotations_image ON annotations(image_id)",
     "CREATE INDEX IF NOT EXISTS images_status ON images(status)",
     "CREATE TABLE IF NOT EXISTS drafts(image_id INTEGER PRIMARY KEY REFERENCES images(id), data TEXT NOT NULL, negative INTEGER NOT NULL DEFAULT 0)"],
    ["CREATE TABLE revisions(image_id INTEGER PRIMARY KEY REFERENCES images(id), revision INTEGER NOT NULL DEFAULT 0)",
     "CREATE TABLE team_members(id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, active INTEGER NOT NULL DEFAULT 1)",
     "CREATE TABLE team_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, image_id INTEGER NOT NULL, member TEXT NOT NULL, revision INTEGER NOT NULL, saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
     "CREATE TABLE team_changes(seq INTEGER PRIMARY KEY AUTOINCREMENT, image_id INTEGER NOT NULL)",
     "CREATE TABLE team_links(image_id INTEGER PRIMARY KEY REFERENCES images(id), remote_revision INTEGER NOT NULL DEFAULT 0, dirty INTEGER NOT NULL DEFAULT 0, conflict INTEGER NOT NULL DEFAULT 0)",
     "INSERT INTO revisions(image_id) SELECT id FROM images",
     "INSERT INTO team_changes(image_id) SELECT id FROM images",
     "CREATE TRIGGER image_added AFTER INSERT ON images BEGIN INSERT INTO revisions(image_id) VALUES(NEW.id); INSERT INTO team_changes(image_id) VALUES(NEW.id); END"],
    ["ALTER TABLE team_audit ADD COLUMN data TEXT NOT NULL DEFAULT '[]'",
     "ALTER TABLE team_audit ADD COLUMN negative INTEGER NOT NULL DEFAULT 0"],
    ["ALTER TABLE drafts ADD COLUMN base_revision INTEGER"]
]


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.lannotex-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


class Project:
    def __init__(self, root, create=True):
        self.root = Path(root).resolve()
        self.db_path = self.root / 'project.sqlite3'
        if not create and not self.db_path.is_file(): raise FileNotFoundError('No project.sqlite3 in this folder')
        self.root.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=2)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute('PRAGMA foreign_keys=ON')
            self.conn.execute('PRAGMA journal_mode=WAL')
            self.conn.execute('PRAGMA synchronous=FULL')
            self._migrate()
        except Exception:
            self.conn.close()
            raise

    def _migrate(self):
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            self.conn.execute('CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY)')
            done = {r[0] for r in self.conn.execute('SELECT version FROM migrations')}
            if done and max(done) > len(MIGRATIONS): raise ValueError('Project requires a newer Lannotex version')
            for version, statements in enumerate(MIGRATIONS, 1):
                if version not in done:
                    for sql in statements: self.conn.execute(sql)
                    self.conn.execute('INSERT INTO migrations VALUES(?)', (version,))

    def close(self): self.conn.close()
    def labels(self): return self.conn.execute('SELECT name,color FROM labels ORDER BY name').fetchall()

    def add_label(self, name, color='#37b8a5'):
        name = name.strip()
        if not name or len(name) > 120: raise ValueError('Enter a label of 1–120 characters')
        with self.conn: self.conn.execute('INSERT INTO labels VALUES(?,?)', (name, color))

    def rename_label(self, old, new):
        new = new.strip()
        if not new or len(new) > 120: raise ValueError('Enter a label of 1–120 characters')
        with self.conn:
            self.conn.execute('UPDATE labels SET name=? WHERE name=?', (new, old))
            affected=set()
            for row in self.conn.execute('SELECT id,image_id,data FROM annotations').fetchall():
                data = json.loads(row['data'])
                if data['label'] == old:
                    data['label'] = new
                    self.conn.execute('UPDATE annotations SET data=? WHERE id=?', (json.dumps(data), row['id']))
                    affected.add(row['image_id'])
            for row in self.conn.execute('SELECT image_id,data FROM drafts').fetchall():
                data = json.loads(row['data'])
                for a in data:
                    if a['label'] == old: a['label'] = new
                self.conn.execute('UPDATE drafts SET data=? WHERE image_id=?', (json.dumps(data), row['image_id']))
            for ident in affected:
                self.conn.execute('UPDATE revisions SET revision=revision+1 WHERE image_id=?',(ident,))
                self.conn.execute('INSERT INTO team_changes(image_id) VALUES(?)',(ident,))

    def remove_label(self, name):
        for row in self.conn.execute('SELECT data FROM annotations UNION ALL SELECT data FROM drafts'):
            data = json.loads(row[0])
            if any(a['label'] == name for a in (data if isinstance(data, list) else [data])):
                raise ValueError('This label is in use. Rename it, or relabel its annotations first.')
        with self.conn: self.conn.execute('DELETE FROM labels WHERE name=?', (name,))

    def reference(self, path):
        path = Path(path).resolve()
        try: return os.path.relpath(path, self.root)
        except ValueError: return str(path)

    def resolve(self, reference): return (self.root / reference).resolve()

    def add_image(self, path, width=0, height=0):
        path = self.reference(path)
        with self.conn: self.conn.execute('INSERT OR IGNORE INTO images(path,width,height) VALUES(?,?,?)', (path, width, height))
        return self.conn.execute('SELECT id FROM images WHERE path=?', (path,)).fetchone()[0]

    def add_batch(self, records):
        with self.conn:
            inserted = self.conn.executemany('INSERT OR IGNORE INTO images(path,width,height) VALUES(?,?,?)', records)
            return inserted.rowcount

    def images(self): return self.conn.execute('SELECT * FROM images ORDER BY path').fetchall()
    def image(self, ident): return self.conn.execute('SELECT * FROM images WHERE id=?', (ident,)).fetchone()

    def query(self, search='', status='all', offset=0, limit=128, count=False):
        where, args = [], []
        if search:
            where.append("path LIKE ? ESCAPE '\\'")
            args.append('%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        if status != 'all': where.append('status=?'); args.append(status)
        sql = 'SELECT '+('COUNT(*)' if count else '*')+' FROM images'
        if where: sql += ' WHERE '+' AND '.join(where)
        if not count: sql += ' ORDER BY path LIMIT ? OFFSET ?'; args.extend([limit, offset])
        result = self.conn.execute(sql, args)
        return result.fetchone()[0] if count else result.fetchall()

    def load_annotations(self, image_id):
        return [Annotation.from_dict(json.loads(r[0])) for r in self.conn.execute('SELECT data FROM annotations WHERE image_id=? ORDER BY rowid', (image_id,))]

    def load_state(self, image_id):
        draft = self.conn.execute('SELECT * FROM drafts WHERE image_id=?', (image_id,)).fetchone()
        if draft: return [Annotation.from_dict(a) for a in json.loads(draft['data'])], bool(draft['negative']), True
        return self.load_annotations(image_id), self.image(image_id)['status'] == 'empty', False

    def load_document(self, image_id):
        with self.conn:
            self.conn.execute('BEGIN')
            annotations,negative,recovered=self.load_state(image_id)
            revision=self.conn.execute('SELECT revision FROM revisions WHERE image_id=?',(image_id,)).fetchone()[0]
            draft=self.conn.execute('SELECT base_revision FROM drafts WHERE image_id=?',(image_id,)).fetchone()
            if draft and draft[0] is not None: revision=draft[0]
            return annotations,negative,recovered,revision

    def save_draft(self, image_id, annotations, negative=False, base_revision=None):
        with self.conn:
            if base_revision is None:
                base_revision=self.conn.execute('SELECT revision FROM revisions WHERE image_id=?',(image_id,)).fetchone()[0]
            self.conn.execute('INSERT INTO drafts(image_id,data,negative,base_revision) VALUES(?,?,?,?) '
                              'ON CONFLICT(image_id) DO UPDATE SET data=excluded.data,negative=excluded.negative',
                              (image_id, json.dumps([a.to_dict() for a in annotations]), int(negative),base_revision))

    def save_annotations(self, image_id, annotations, negative=False, actor='Local owner', expected_revision=None, clear_draft=True):
        errors = validate_all(annotations, {r['name'] for r in self.labels()}, negative)
        if errors: raise ValueError('; '.join(errors))
        payload = [(a.id, image_id, json.dumps(a.to_dict(), separators=(',', ':'))) for a in annotations]
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            current=self.conn.execute('SELECT revision FROM revisions WHERE image_id=?',(image_id,)).fetchone()
            if current is None: raise ValueError('Image does not exist')
            if expected_revision is not None and current[0]!=expected_revision: raise ConflictError('Another reviewer saved this image. Reload or resolve the conflict before saving.')
            self.conn.execute('DELETE FROM annotations WHERE image_id=?', (image_id,))
            self.conn.executemany('INSERT INTO annotations VALUES(?,?,?)', payload)
            self.conn.execute('UPDATE images SET status=? WHERE id=?', ('empty' if negative else 'done' if annotations else 'new', image_id))
            if clear_draft: self.conn.execute('DELETE FROM drafts WHERE image_id=?', (image_id,))
            self.conn.execute('UPDATE revisions SET revision=revision+1 WHERE image_id=?',(image_id,))
            self.conn.execute('INSERT INTO team_changes(image_id) VALUES(?)',(image_id,))
            self.conn.execute('INSERT INTO team_audit(image_id,member,revision,data,negative) VALUES(?,?,?,?,?)',
                              (image_id,actor,current[0]+1,json.dumps([a.to_dict() for a in annotations]),int(negative)))
            if self.setting('team_remote'):
                self.conn.execute('UPDATE team_links SET dirty=1 WHERE image_id=?',(image_id,))

    def setting(self, key, default=None):
        row = self.conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.conn: self.conn.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))

    def relink(self, image_id, path, width, height):
        old = self.image(image_id)
        if (old['width'], old['height']) != (width, height): raise ValueError('Replacement dimensions differ; annotations would be misaligned')
        with self.conn: self.conn.execute('UPDATE images SET path=? WHERE id=?', (self.reference(path), image_id))

    def backup(self, target):
        target = Path(target).resolve()
        if target == self.db_path: raise ValueError('Choose a different backup path')
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=target.parent, suffix='.sqlite3'); os.close(fd)
        try:
            out = sqlite3.connect(temp)
            try:
                self.conn.backup(out)
                out.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('backup_source_root',json.dumps(str(self.root))))
                out.commit()
            finally: out.close()
            os.replace(temp, target)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    @classmethod
    def restore(cls, source, folder):
        destination = Path(folder) / 'project.sqlite3'
        if destination.exists(): raise ValueError('Restore requires a folder without an existing project')
        source = Path(source).resolve()
        check = sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)
        try:
            if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Backup is damaged')
            check.execute('SELECT version FROM migrations').fetchall()
            Path(folder).mkdir(parents=True, exist_ok=True)
            out = sqlite3.connect(destination)
            try: check.backup(out)
            finally: out.close()
        finally: check.close()
        restored=cls(folder,create=False)
        old_root=restored.setting('backup_source_root')
        if old_root:
            with restored.conn:
                for row in restored.images():
                    old_path=Path(old_root)/row['path']
                    restored.conn.execute('UPDATE images SET path=? WHERE id=?',(restored.reference(old_path),row['id']))
        return restored


class ConflictError(ValueError):
    """A stale edit must never replace a newer shared revision."""
