"""Durable single-operator local upload/job ledger. No Vercel filesystem state.

Uploads are sequential, resumable by byte offset, hashed and decoded before use.
Interrupted paid/model jobs are never retried automatically. Delete/retention
removes local footage/results; provider-file removal is attempted separately.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid

STATES={'uploading','queued','running','paused','completed','cancelled','failed','failed_or_unknown'}


class Jobs:
    def __init__(self,root,quota_bytes=512*1024*1024,clock=time.time):
        self.root=Path(root).expanduser().resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.root,0o700)
        self.quota=quota_bytes;self.clock=clock
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,name TEXT,size INTEGER,offset INTEGER,state TEXT,created REAL,expires REAL,mode TEXT,concepts TEXT,sha TEXT,metadata TEXT,result TEXT,error TEXT,model_started INTEGER DEFAULT 0)')
            columns={row[1] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'worker_active' not in columns:db.execute('ALTER TABLE jobs ADD COLUMN worker_active INTEGER DEFAULT 0')
            if 'progress' not in columns:db.execute('ALTER TABLE jobs ADD COLUMN progress TEXT')
        os.chmod(self.root/'jobs.sqlite3',0o600)

    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.root/'jobs.sqlite3',timeout=5,isolation_level=None)
        connection.row_factory=sqlite3.Row
        try: yield connection
        finally: connection.close()

    def path(self,identity):
        if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity): raise ValueError('invalid_job_id')
        return self.root/(identity+'.media')

    def get(self,identity):
        self.path(identity)
        with self.db() as db: row=db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
        if row is None: raise KeyError('job_not_found')
        result=dict(row)
        for key in ('concepts','metadata','result','progress'): result[key]=json.loads(result[key]) if result[key] else None
        return result

    def create(self,name,size,concepts,mode='inspect'):
        if mode not in ('inspect','sam_video'): raise ValueError('unsupported_analysis_mode')
        if not isinstance(name,str) or len(name)>200 or Path(name).suffix.lower() not in ('.mp4','.mov','.webm'): raise ValueError('unsupported_video_filename')
        if isinstance(size,bool) or not isinstance(size,int) or not 1<=size<=64*1024*1024: raise ValueError('video_size_limit')
        if not isinstance(concepts,list) or not 1<=len(concepts)<=4 or any(not isinstance(s,str) or not 1<=len(s)<=100 or re.search('[,;+\\n]',s) for s in concepts): raise ValueError('one_to_four_short_concepts_required')
        identity=uuid.uuid4().hex;now=self.clock()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            size_used,count=db.execute('SELECT COALESCE(SUM(size),0),COUNT(*) FROM jobs').fetchone()
            if size_used+size>self.quota or count>=20: raise ValueError('local_storage_quota_exceeded')
            db.execute('INSERT INTO jobs(id,name,size,offset,state,created,expires,mode,concepts) VALUES(?,?,?,?,?,?,?,?,?)',
                       (identity,Path(name).name,size,0,'uploading',now,now+86400,mode,json.dumps(concepts)))
            self.path(identity).touch(mode=0o600,exist_ok=False);db.commit()
        return self.get(identity)

    def append(self,identity,offset,chunk):
        if not isinstance(chunk,bytes) or not 1<=len(chunk)<=1024*1024: raise ValueError('upload_chunk_limit')
        if isinstance(offset,bool) or not isinstance(offset,int): raise ValueError('invalid_upload_offset')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
            if row is None: raise KeyError('job_not_found')
            if row['state']!='uploading' or row['offset']!=offset or offset+len(chunk)>row['size']: raise ValueError('upload_offset_or_state_conflict')
            with self.path(identity).open('r+b') as stream:
                stream.truncate(offset);stream.seek(offset);stream.write(chunk);stream.flush();os.fsync(stream.fileno())
            db.execute('UPDATE jobs SET offset=? WHERE id=?',(offset+len(chunk),identity));db.commit()
        return self.get(identity)

    def finish(self,identity):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
            if row is None: raise KeyError('job_not_found')
            if row['state']!='uploading' or row['offset']!=row['size']: raise ValueError('upload_incomplete')
            sha=hashlib.sha256()
            with self.path(identity).open('rb') as stream:
                while chunk:=stream.read(1024*1024): sha.update(chunk)
            # Same private local operator only; reuse inspection, never paid inference.
            old=db.execute("SELECT metadata FROM jobs WHERE sha=? AND state='completed'",(sha.hexdigest(),)).fetchone()
            db.execute("UPDATE jobs SET sha=?,state='queued',metadata=? WHERE id=?",(sha.hexdigest(),old['metadata'] if old else None,identity));db.commit()
        return self.get(identity)

    def control(self,identity,action):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
            if row is None: raise KeyError('job_not_found')
            if action=='cancel': target='failed_or_unknown' if row['model_started'] else 'cancelled'
            elif action=='pause' and row['state'] in ('queued','running') and not row['model_started']: target='paused'
            elif action in ('resume','retry') and row['state'] in ('paused','failed') and not row['model_started']:target='queued'
            else: raise ValueError('unsupported_job_transition; uncertain model requests cannot be replayed')
            if row['state']=='completed': raise ValueError('completed_job_cannot_be_changed')
            db.execute('UPDATE jobs SET state=? WHERE id=?',(target,identity));db.commit()
        return self.get(identity)

    def update(self,identity,**fields):
        allowed={'state','metadata','result','error','model_started','progress'}
        if not fields or set(fields)-allowed: raise ValueError('invalid_job_update')
        if 'state' in fields and fields['state'] not in STATES: raise ValueError('invalid_job_state')
        for field,limit in (('result',8*1024*1024),('metadata',256*1024),('progress',16*1024)):
            if field in fields and len(json.dumps(fields[field],allow_nan=False).encode())>limit:raise ValueError('job_result_budget_exceeded')
        values={key:json.dumps(value,allow_nan=False) if key in ('metadata','result','progress') else value for key,value in fields.items()}
        with self.db() as db:
            db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+" WHERE id=? AND state='running'",(*values.values(),identity))

    def claim(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row: db.execute("UPDATE jobs SET state='running',worker_active=1 WHERE id=?",(row['id'],))
            db.commit()
        return row['id'] if row else None

    def recover(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET state=CASE WHEN model_started=1 THEN 'failed_or_unknown' ELSE 'queued' END,error='worker_interrupted',worker_active=0 WHERE state='running'")
            db.execute('UPDATE jobs SET worker_active=0')

    def release(self,identity):
        with self.db() as db:db.execute('UPDATE jobs SET worker_active=0 WHERE id=?',(identity,))

    def delete(self,identity):
        row=self.get(identity)
        if row['state']=='running' or row['worker_active']: raise ValueError('cancel_running_job_before_delete')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self.path(identity).unlink(missing_ok=True);db.execute('DELETE FROM jobs WHERE id=?',(identity,));db.commit()
        return {'deleted':True,'provider_retention':'Provider copies may remain; see model provider retention policy.'}

    def expire(self):
        with self.db() as db: ids=[r['id'] for r in db.execute("SELECT id FROM jobs WHERE expires<? AND state!='running' AND worker_active=0",(self.clock(),))]
        for identity in ids:self.delete(identity)
        return len(ids)
