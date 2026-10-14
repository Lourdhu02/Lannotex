from concurrent.futures import ThreadPoolExecutor
import json
import threading
import pytest
from PIL import Image
from lannotex.domain import Annotation
from lannotex.storage import ConflictError, Project
from lannotex.team import TeamClient, TeamServer, add_member, resolve_conflict, sync_replica


@pytest.fixture
def team(tmp_path):
    root=tmp_path/'host'; project=Project(root)
    image=root/'source.png'; Image.new('RGB',(160,90),'white').save(image)
    ident=project.add_image(image,160,90); project.add_label('cat'); project.set_setting('tasks',['box']); project.close()
    one=add_member(root,'Alice'); two=add_member(root,'Bob')
    server=TeamServer(root,port=0).start(); url=f'http://127.0.0.1:{server.server_address[1]}'
    yield root,ident,TeamClient(url,one),TeamClient(url,two)
    server.stop()


def payload(revision=0):
    return {'revision':revision,'negative':False,'annotations':[Annotation('cat','box',[.1,.1,.6,.6]).to_dict()]}


def test_two_simultaneous_saves_never_overwrite_silently(team):
    root,ident,a,b=team
    gate=threading.Barrier(2)
    def save(client):
        gate.wait()
        try: return client.request(f'/state/{ident}',payload())['revision']
        except ConflictError: return 'conflict'
    with ThreadPoolExecutor(2) as pool: result=list(pool.map(save,[a,b]))
    assert sorted(result,key=str)==[1,'conflict']
    p=Project(root,create=False)
    audit=p.conn.execute('SELECT * FROM team_audit').fetchall()
    assert len(audit)==1 and audit[0]['member'] in ('Alice','Bob')
    assert len(json.loads(audit[0]['data']))==1
    p.close()


def test_token_revocation_validation_and_no_path_traversal(team):
    root,ident,a,b=team
    assert a.request('/meta')['reviewer']=='Alice'
    with pytest.raises(ValueError): TeamClient(a.url,'wrong').request('/meta')
    with pytest.raises(ValueError): a.request('/image/../../project.sqlite3')
    invalid=payload(); invalid['annotations'][0]['geometry']=[.8,.1,.2,.6]
    with pytest.raises(ValueError): a.request(f'/state/{ident}',invalid)
    assert a.request(f'/state/{ident}')['revision']==0
    p=Project(root,create=False)
    with p.conn: p.conn.execute("UPDATE team_members SET active=0 WHERE name='Alice'")
    p.close()
    with pytest.raises(ValueError): a.request('/meta')
    assert b.request('/meta')['reviewer']=='Bob'


def sync(root,client): return sync_replica(root,client,threading.Event(),lambda *args:None)


def test_replicas_offline_work_conflict_and_resolution(team,tmp_path):
    root,ident,a,b=team
    ra,rb=tmp_path/'alice',tmp_path/'bob'
    Project(ra).close(); Project(rb).close(); sync(ra,a); sync(rb,b)
    for local in (ra,rb):
        p=Project(local,create=False); p.save_annotations(ident,[Annotation('cat','box',[0,0,.3,.4])]); p.close()
    assert sync(ra,a)['sent']==1
    assert sync(rb,b)['conflicts']==[ident]
    p=Project(rb,create=False)
    assert tuple(p.conn.execute('SELECT dirty,conflict FROM team_links').fetchone())==(1,1)
    assert p.load_annotations(ident)  # Never discarded on conflict.
    p.close()
    assert sync(rb,b)['conflicts']==[ident]  # Conflict remains visible on later polls.
    resolve_conflict(rb,ident,b,False)
    p=Project(rb,create=False)
    assert tuple(p.conn.execute('SELECT dirty,conflict FROM team_links').fetchone())==(0,0)
    assert p.load_annotations(ident)[0].id==Annotation.from_dict(a.request(f'/state/{ident}')['annotations'][0]).id
    p.close()


def test_image_download_and_owner_draft_survives_remote_save(team,tmp_path):
    root,ident,a,b=team
    target=tmp_path/'download.png'; a.download(ident,target)
    with Image.open(target) as image: assert image.size==(160,90)
    p=Project(root,create=False); draft=Annotation('cat','box',[.2,.2,.7,.7]); p.save_draft(ident,[draft]); p.close()
    a.request(f'/state/{ident}',payload())
    p=Project(root,create=False)
    assert p.load_state(ident)[0][0].id==draft.id
    p.close()


def test_disabled_pipeline_is_enforced_on_host(team):
    root,ident,a,b=team
    data=payload(); data['annotations']=[Annotation('cat','classification').to_dict()]
    with pytest.raises(ValueError,match='pipeline'): a.request(f'/state/{ident}',data)
