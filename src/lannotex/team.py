"""Explicit, authenticated team hosting. SQLite is accessed only on the host.

Desktop clients keep private local replicas and an outbox. HTTP work runs in jobs,
never the Qt UI thread. Plain HTTP is for trusted LAN/VPN; CLI supports TLS.
"""
from __future__ import annotations
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import ssl
import tempfile
import threading
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import uuid
from .domain import Annotation, validate_all
from .storage import ConflictError, Project


def add_member(root, name):
    if not name.strip() or len(name)>120: raise ValueError('Enter a reviewer name of 1–120 characters')
    token=secrets.token_urlsafe(32); project=Project(root,create=False)
    try:
        with project.conn:
            project.conn.execute('INSERT INTO team_members(id,name,token_hash) VALUES(?,?,?)',
                                 (uuid.uuid4().hex,name.strip(),hashlib.sha256(token.encode()).hexdigest()))
        return token
    finally: project.close()


class TeamServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self, root, host='127.0.0.1', port=8765, cert=None, key=None):
        self.root=Path(root).resolve()
        project=Project(self.root,create=False)
        if not project.setting('project_id'): project.set_setting('project_id',str(uuid.uuid4()))
        project.close()
        super().__init__((host,port),TeamHandler)
        if cert:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,key)
            self.socket=context.wrap_socket(self.socket,server_side=True)
        self.thread=None

    def start(self):
        self.thread=threading.Thread(target=self.serve_forever,daemon=True); self.thread.start(); return self

    def stop(self):
        self.shutdown(); self.server_close()
        if self.thread: self.thread.join(timeout=3)


class TeamHandler(BaseHTTPRequestHandler):
    server_version='Lannotex/0.0.2'
    def log_message(self,*args): pass  # Never log access tokens or private image names.

    def reply(self,code,payload):
        raw=json.dumps(payload).encode()
        self.send_response(code); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)

    def do_GET(self): self.dispatch(False)
    def do_PUT(self): self.dispatch(True)

    def dispatch(self,write):
        project=None
        try:
            self.connection.settimeout(15)
            project=Project(self.server.root,create=False)
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            member=project.conn.execute('SELECT * FROM team_members WHERE token_hash=? AND active=1',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if not member: self.reply(401,{'error':'Invalid or revoked reviewer token'}); return
            parsed=urlparse(self.path); route=parsed.path.strip('/').split('/'); query=parse_qs(parsed.query)
            if route==['meta'] and not write:
                self.reply(200,{'project_id':project.setting('project_id'),'name':project.setting('name',project.root.name),
                    'tasks':project.setting('tasks',['box','polygon','classification']),'labels':[dict(r) for r in project.labels()],
                    'reviewer':member['name']}); return
            if route==['changes'] and not write:
                project.conn.execute('BEGIN')
                after=max(0,int(query.get('after',['0'])[0]))
                changes=project.conn.execute('SELECT seq,image_id FROM team_changes WHERE seq>? ORDER BY seq LIMIT 128',(after,)).fetchall()
                images=[]
                for ident in dict.fromkeys(r['image_id'] for r in changes):
                    row=project.image(ident)
                    if row:
                        data=dict(row); data['path']=Path(data['path']).name
                        data['revision']=project.conn.execute('SELECT revision FROM revisions WHERE image_id=?',(ident,)).fetchone()[0]
                        images.append(data)
                self.reply(200,{'images':images,'cursor':changes[-1]['seq'] if changes else after,'more':len(changes)==128}); return
            if len(route)!=2 or route[0] not in ('state','image') or not route[1].isdigit(): self.reply(404,{'error':'Unknown endpoint'}); return
            ident=int(route[1]); image=project.image(ident)
            if image is None: self.reply(404,{'error':'Unknown image'}); return
            if route[0]=='image' and not write:
                path=project.resolve(image['path'])
                # IDs resolve exclusively through project records, never URL paths.
                with path.open('rb') as stream:
                    size=os.fstat(stream.fileno()).st_size
                    if size>256*1024*1024: self.reply(413,{'error':'Image exceeds 256 MiB transfer limit'}); return
                    self.send_response(200); self.send_header('Content-Type','application/octet-stream'); self.send_header('Content-Length',str(size)); self.end_headers()
                    while chunk:=stream.read(1024*1024): self.wfile.write(chunk)
                return
            if route[0]!='state': self.reply(405,{'error':'Method not allowed'}); return
            if write:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4*1024*1024: self.reply(413,{'error':'Annotation payload must be under 4 MiB'}); return
                data=json.loads(self.rfile.read(size)); anns=[Annotation.from_dict(a) for a in data['annotations']]
                if len(anns)>10000: raise ValueError('Too many annotations')
                allowed=set(project.setting('tasks',['box','polygon','classification']))
                if any(a.kind not in allowed for a in anns): raise ValueError('Annotation type is not enabled for this pipeline')
                if not isinstance(data['revision'],int) or not isinstance(data['negative'],bool): raise ValueError('Invalid revision or no-target value')
                project.save_annotations(ident,anns,data['negative'],actor=member['name'],expected_revision=data['revision'],clear_draft=False)
            # A read transaction keeps revision, annotations and status consistent.
            project.conn.execute('BEGIN')
            revision=project.conn.execute('SELECT revision FROM revisions WHERE image_id=?',(ident,)).fetchone()[0]
            annotations=project.load_annotations(ident); status=project.image(ident)['status']
            self.reply(200,{'revision':revision,'annotations':[a.to_dict() for a in annotations],'negative':status=='empty','status':status})
        except ConflictError as e: self.reply(409,{'error':str(e)})
        except (ValueError,KeyError,TypeError) as e: self.reply(400,{'error':str(e)})
        except FileNotFoundError: self.reply(404,{'error':'Source image is missing on the host'})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception: self.reply(500,{'error':'Host operation failed; no successful save was confirmed'})
        finally:
            if project: project.close()


class TeamClient:
    def __init__(self,url,token):
        self.url=url.rstrip('/'); self.token=token
        parsed=urlparse(self.url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('Enter a plain http:// or https:// host URL')

    def request(self,path,data=None):
        req=Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,
                    headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'},method='PUT' if data is not None else 'GET')
        try:
            with urlopen(req,timeout=10) as response: return json.loads(response.read(8*1024*1024))
        except HTTPError as e:
            message=json.loads(e.read()).get('error',str(e))
            if e.code==409: raise ConflictError(message) from e
            raise ValueError(message) from e

    def download(self,ident,path,cancel=None):
        path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        req=Request(self.url+f'/image/{ident}',headers={'Authorization':'Bearer '+self.token})
        fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.part')
        try:
            with os.fdopen(fd,'wb') as stream, urlopen(req,timeout=15) as response:
                total=0
                while chunk:=response.read(1024*1024):
                    if cancel and cancel.is_set(): raise ValueError('Download cancelled')
                    total+=len(chunk)
                    if total>256*1024*1024: raise ValueError('Image transfer exceeds 256 MiB')
                    stream.write(chunk)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temp,path)
        finally:
            if os.path.exists(temp): os.unlink(temp)


def sync_replica(root,client,cancel,progress):
    """Push local outbox, then pull incremental changes; preserve drafts/conflicts."""
    local=Project(root,create=False); conflicts=[]; changed=[]; sent=0
    try:
        meta=client.request('/meta')
        if local.setting('remote_id') not in (None,meta['project_id']): raise ValueError('This cache belongs to a different team project')
        local.set_setting('remote_id',meta['project_id']); local.set_setting('team_remote',client.url)
        local.set_setting('tasks',meta['tasks']); local.set_setting('name',meta['name']); local.set_setting('reviewer',meta['reviewer'])
        with local.conn:
            for lab in meta['labels']:
                local.conn.execute('INSERT OR REPLACE INTO labels VALUES(?,?)',(lab['name'],lab['color']))
        for link in local.conn.execute('SELECT * FROM team_links WHERE dirty=1 AND conflict=0').fetchall():
            if cancel.is_set(): break
            ident=link['image_id']; row=local.image(ident)
            payload={'revision':link['remote_revision'],'annotations':[a.to_dict() for a in local.load_annotations(ident)],'negative':row['status']=='empty'}
            try: result=client.request(f'/state/{ident}',payload)
            except ConflictError:
                with local.conn: local.conn.execute('UPDATE team_links SET conflict=1 WHERE image_id=?',(ident,))
                conflicts.append(ident); continue
            with local.conn:
                # A user may have edited again while the request was in flight.
                current=[a.to_dict() for a in local.load_annotations(ident)]
                same=current==payload['annotations'] and (local.image(ident)['status']=='empty')==payload['negative']
                local.conn.execute('UPDATE team_links SET remote_revision=?,dirty=? WHERE image_id=?',(result['revision'],0 if same else 1,ident))
            sent+=1
        cursor=local.setting('remote_cursor',0)
        while not cancel.is_set():
            page=client.request('/changes?after='+str(cursor))
            for remote in page['images']:
                ident=remote['id']; link=local.conn.execute('SELECT * FROM team_links WHERE image_id=?',(ident,)).fetchone()
                draft=local.conn.execute('SELECT 1 FROM drafts WHERE image_id=?',(ident,)).fetchone()
                if link and (link['dirty'] or draft):
                    if remote['revision']!=link['remote_revision']:
                        conflicts.append(ident)
                        with local.conn: local.conn.execute('UPDATE team_links SET conflict=1 WHERE image_id=?',(ident,))
                    continue
                if link and remote['revision']==link['remote_revision']: continue
                state=client.request(f'/state/{ident}')
                suffix=Path(remote['path']).suffix.lower()
                if suffix not in ('.jpg','.jpeg','.png','.webp'): raise ValueError('Unsupported remote image extension')
                ref=f'images/{ident:08d}_{Path(remote["path"]).name}'
                if Path(ref).name!=ref.split('/')[-1] or '\\' in ref: raise ValueError('Unsafe remote filename')
                annotations=[Annotation.from_dict(a) for a in state['annotations']]
                errors=validate_all(annotations,{r['name'] for r in local.labels()},state['negative'])
                if errors: raise ValueError('; '.join(errors))
                with local.conn:
                    local.conn.execute('BEGIN IMMEDIATE')
                    latest=local.conn.execute('SELECT * FROM team_links WHERE image_id=?',(ident,)).fetchone()
                    has_draft=local.conn.execute('SELECT 1 FROM drafts WHERE image_id=?',(ident,)).fetchone()
                    if latest and (latest['dirty'] or has_draft):
                        if state['revision']!=latest['remote_revision']:
                            local.conn.execute('UPDATE team_links SET conflict=1 WHERE image_id=?',(ident,)); conflicts.append(ident)
                        continue
                    local.conn.execute('INSERT OR IGNORE INTO images(id,path,width,height,status) VALUES(?,?,?,?,?)',(ident,ref,remote['width'],remote['height'],state['status']))
                    local.conn.execute('DELETE FROM annotations WHERE image_id=?',(ident,))
                    local.conn.executemany('INSERT INTO annotations VALUES(?,?,?)',[(a.id,ident,json.dumps(a.to_dict())) for a in annotations])
                    local.conn.execute('UPDATE images SET status=? WHERE id=?',(state['status'],ident))
                    local.conn.execute('UPDATE revisions SET revision=revision+1 WHERE image_id=?',(ident,))
                    local.conn.execute('INSERT OR REPLACE INTO team_links VALUES(?,?,0,0)',(ident,state['revision']))
                changed.append(ident)
            cursor=page['cursor']; local.set_setting('remote_cursor',cursor)
            progress(len(changed),f'Synced {len(changed)} images · {sent} saves sent')
            if not page['more']: break
        conflicts.extend(row[0] for row in local.conn.execute('SELECT image_id FROM team_links WHERE conflict=1'))
        return {'changed':changed,'conflicts':list(set(conflicts)),'sent':sent,'root':str(root),'meta':meta}
    finally: local.close()


def resolve_conflict(root,ident,client,keep_local):
    local=Project(root,create=False)
    try:
        state=client.request(f'/state/{ident}')
        if keep_local:
            anns,negative,_=local.load_state(ident)
            state=client.request(f'/state/{ident}',{'revision':state['revision'],'annotations':[a.to_dict() for a in anns],'negative':negative})
        with local.conn:
            local.conn.execute('DELETE FROM annotations WHERE image_id=?',(ident,))
            local.conn.executemany('INSERT INTO annotations VALUES(?,?,?)',[(a['id'],ident,json.dumps(a)) for a in state['annotations']])
            local.conn.execute('DELETE FROM drafts WHERE image_id=?',(ident,))
            local.conn.execute('UPDATE images SET status=? WHERE id=?',(state['status'],ident))
            local.conn.execute('UPDATE revisions SET revision=revision+1 WHERE image_id=?',(ident,))
            local.conn.execute('UPDATE team_links SET remote_revision=?,dirty=0,conflict=0 WHERE image_id=?',(state['revision'],ident))
        return ident
    finally: local.close()
