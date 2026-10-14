"""Real Qt interactions. All images and settings are isolated test fixtures."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import time
import pytest
from PIL import Image
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lannotex.app import Main
from lannotex.domain import Annotation
from lannotex.storage import Project


@pytest.fixture(scope='module')
def qt(tmp_path_factory):
    app=QApplication.instance() or QApplication([])
    if Path('C:/Windows/Fonts/segoeui.ttf').is_file(): QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(tmp_path_factory.mktemp('settings')))
    yield app


def wait_for(qt,predicate,timeout=8):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline: qt.processEvents(); QTest.qWait(10)
    assert predicate()


@pytest.fixture
def window(qt):
    w=Main(); w.show(); qt.processEvents()
    yield w
    if w.job: w.job.cancel.set()
    if w.sync_job: w.sync_job.cancel.set()
    wait_for(qt,lambda:not w.job and not w.loader.active and not w.sync_job)
    w.canvas.cancel(); w.dirty=False; w.close(); qt.processEvents()


def project(tmp_path,tasks=('box','polygon','classification')):
    root=tmp_path/'project'; p=Project(root); p.add_label('cat'); p.add_label('dog'); p.set_setting('tasks',list(tasks))
    for i in range(2):
        path=root/f'image-{i}.png'; Image.new('RGB',(640,360),'#e0e0e0').save(path); p.add_image(path,640,360)
    p.close(); return root


def open_ready(w,qt,root):
    assert w.load_project(root)
    wait_for(qt,lambda:w.canvas.image is not None and not w.loader.active)


def test_home_first_monochrome_and_classification_only(window,qt,tmp_path):
    w=window
    assert w.pages.currentWidget()==w.home
    root=project(tmp_path,('classification',)); open_ready(w,qt,root)
    assert w.classes.isVisible()
    assert not w.annotation_list.isVisible() and not w.tool_buttons['box'].isVisible() and not w.label_combo.isVisible()
    w.classes.item(0).setCheckState(Qt.Checked); assert w.save()
    assert w.project.load_annotations(w.current['id'])[0].kind=='classification'
    for dark in (True,False):
        if w.dark!=dark: w.toggle_theme()
        color=QApplication.palette().window().color()
        assert color.red()==color.green()==color.blue()
    w.go_home(); assert w.pages.currentWidget()==w.home


def test_draw_move_undo_immediate_save_and_restart(window,qt,tmp_path):
    w=window; root=project(tmp_path); open_ready(w,qt,root)
    w.set_tool('box'); a=w.canvas.screen([.1,.1]).toPoint(); b=w.canvas.screen([.5,.6]).toPoint()
    QTest.mousePress(w.canvas,Qt.LeftButton,pos=a); QTest.mouseMove(w.canvas,b); QTest.mouseRelease(w.canvas,Qt.LeftButton,pos=b)
    assert len(w.document.annotations)==1
    original=w.document.annotations[0].geometry[:]; ident=w.document.annotations[0].id
    w.set_tool('select')
    start=w.canvas.screen([.3,.3]).toPoint(); end=w.canvas.screen([.4,.4]).toPoint()
    QTest.mousePress(w.canvas,Qt.LeftButton,pos=start); QTest.mouseMove(w.canvas,end); QTest.mouseRelease(w.canvas,Qt.LeftButton,pos=end)
    assert w.document.annotations[0].geometry!=original
    w.undo(); assert w.save()
    assert w.project.load_annotations(w.current['id'])[0].geometry==original
    w.navigate(1); wait_for(qt,lambda:not w.loader.active and not w.loading)
    w.navigate(-1); wait_for(qt,lambda:not w.loader.active and not w.loading)
    assert w.document.annotations[0].id==ident
    assert w.document.annotations[0].geometry==original


def test_polygon_reopens_and_redraw_cancel_preserves_original(window,qt,tmp_path):
    w=window; root=project(tmp_path); open_ready(w,qt,root)
    ann=Annotation('cat','polygon',[[.1,.1],[.8,.1],[.6,.8]])
    w.commit([ann]); assert w.save()
    w.canvas.select(ann.id); w.canvas.redraw(); w.canvas.points=[[.2,.2],[.3,.3]]; w.canvas.cancel()
    assert w.document.annotations[0].geometry==ann.geometry
    w.navigate(1); wait_for(qt,lambda:not w.loader.active and not w.loading)
    w.navigate(-1); wait_for(qt,lambda:not w.loader.active and not w.loading)
    assert w.canvas.annotations[0].kind=='polygon'
    w.canvas.select(ann.id); w.canvas.vertex=0; w.canvas.delete_vertex()
    assert len(w.document.annotations[0].geometry)==3


def test_failed_save_blocks_navigation_and_retains_edits(window,qt,tmp_path,monkeypatch):
    w=window; open_ready(w,qt,project(tmp_path)); before=w.current['id']
    w.commit([Annotation('cat','box',[.1,.1,.4,.5])])
    def full(*args,**kwargs): raise OSError('Disk full')
    monkeypatch.setattr(w.project,'save_annotations',full)
    w.navigate(1)
    assert w.current['id']==before and w.dirty and len(w.document.annotations)==1
    assert 'failed' in w.save_badge.text().lower()


def test_keyboard_text_entry_and_pending_drawing(window,qt,tmp_path):
    w=window; open_ready(w,qt,project(tmp_path)); w.activateWindow(); qt.processEvents()
    w.search.setFocus(); QTest.keyClicks(w.search,'bfp'); assert w.search.text()=='bfp'
    assert w.canvas.mode=='select'
    w.search.clear(); w.filter_timer.stop()
    w.set_tool('polygon'); w.canvas.points=[[.1,.1],[.2,.2]]
    assert not w.save(); before=w.current['id']; w.navigate(1); assert w.current['id']==before


def test_window_resizes_and_screenshot(window,qt,tmp_path):
    w=window
    artifact=Path(os.environ.get('LANNOTEX_QA_DIR',tmp_path))
    artifact.mkdir(parents=True,exist_ok=True)
    w.resize(1280,850); qt.processEvents(); w.grab().save(str(artifact/'home-light.png'))
    w.toggle_theme(); qt.processEvents(); w.grab().save(str(artifact/'home-dark.png'))
    open_ready(w,qt,project(tmp_path))
    w.commit([Annotation('cat','box',[.15,.15,.7,.8])]); w.resize(1000,720); qt.processEvents()
    assert w.canvas.width()>200 and w.canvas.height()>150
    w.grab().save(str(artifact/'workspace-dark.png'))


def test_team_client_download_edit_save_sync(window,qt,tmp_path):
    from lannotex.team import TeamServer, TeamClient, add_member, sync_replica
    import threading
    root=project(tmp_path,('classification',)); access=add_member(root,'Test reviewer')
    server=TeamServer(root,port=0).start()
    try:
        client=TeamClient(f'http://127.0.0.1:{server.server_address[1]}',access)
        cache=tmp_path/'client'; Project(cache).close()
        sync_replica(cache,client,threading.Event(),lambda *a:None)
        assert window.load_project(cache,client=client)
        wait_for(qt,lambda:not window.job and not window.loader.active and window.canvas.image is not None)
        window.classes.item(0).setCheckState(Qt.Checked); assert window.save()
        window.sync_team(); wait_for(qt,lambda:window.sync_job is None)
        host=Project(root,create=False)
        assert host.load_annotations(window.current['id'])[0].kind=='classification'
        assert host.conn.execute('SELECT member FROM team_audit ORDER BY id DESC LIMIT 1').fetchone()[0]=='Test reviewer'
        host.close(); window.sync_timer.stop()
    finally: server.stop()
