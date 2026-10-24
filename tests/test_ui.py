"""Real Qt interactions. All images and settings are isolated test fixtures."""
import os
import tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('LANNOTEX_CACHE_DIR',tempfile.mkdtemp(prefix='lannotex-cache-'))
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
    w.cancel_tiles()
    wait_for(qt,lambda:not w.job and not w.loader.active and not w.sync_job and not w.tile_job,timeout=30)
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


def large_project(tmp_path):
    root=tmp_path/'large'; p=Project(root); p.add_label('cat'); p.set_setting('tasks',['box'])
    for i,size in enumerate([(5000,1200),(800,600)]):
        path=root/f'large-{i}.png'; Image.new('RGB',size,'#808080').save(path); p.add_image(path,*size)
    p.close(); return root


def test_full_resolution_tiles_prefetch_minimap_and_grid(window,qt,tmp_path):
    w=window; root=large_project(tmp_path); open_ready(w,qt,root)
    c=w.canvas
    assert c.image.width()==2560 and c.source==(5000,1200)
    wait_for(qt,lambda:not w.loader.active)
    neighbour=str(root/'large-1.png')
    assert any(key[0]==neighbour for key in w.loader.cache), 'next image should be prefetched'

    c.actual_pixels(); c.repaint()
    assert abs(c.source_scale()-1)<0.01 and w.zoom_label.text()=='100%'
    # Building tiles writes to disk, so allow for a slow shared runner.
    wait_for(qt,lambda:c.pyramid is not None and c.pyramid.complete() and w.tile_job is None,timeout=60)
    assert c.pyramid.level_size(0)==(5000,1200)
    assert c.pyramid.tile_path(0,0,0).is_file()
    c.repaint()
    assert c.draw_tiles_count>0, 'zoomed-in painting must come from tiles'

    c.repaint(); assert not c.minimap_rect.isEmpty()
    QTest.mouseClick(c,Qt.LeftButton,pos=c.minimap_rect.center().toPoint())
    r=c.image_rect(); assert abs(r.center().x()-c.width()/2)<3
    c.set_zoom(10_000); assert c.source_scale()<=64.01
    c.repaint()  # pixel grid path at maximum zoom
    w.toggle_minimap(); c.repaint(); assert c.minimap_rect.isEmpty()
    w.toggle_minimap()


def test_image_adjustments_change_only_the_display(window,qt,tmp_path):
    w=window; open_ready(w,qt,project(tmp_path)); c=w.canvas
    def center_gray(): c.repaint(); return c.grab().toImage().pixelColor(c.width()//2,c.height()//2).red()
    original=center_gray()
    w.adjust_sliders['brightness'][0].setValue(-50)
    assert w.adjust_sliders['brightness'][1].text()=='-50'
    darker=center_gray(); assert darker<original-40
    w.adjust_sliders['gamma'][0].setValue(200); assert center_gray()>darker
    w.reset_adjustments(); assert c.lut is None and center_gray()==original
    path=w.project.resolve(w.current['path']); assert Image.open(path).getpixel((5,5))==(224,224,224)


def test_dockable_panels_focus_and_layout_presets(window,qt,tmp_path):
    w=window; open_ready(w,qt,project(tmp_path))
    assert set(w.docks)=={'dataset','inspector','view'}
    shown=lambda d:d.toggleViewAction().isChecked()  # true for a panel behind another tab too
    assert all(shown(d) for d in w.docks.values()) and w.docks['inspector'].isVisible()
    assert w.docks['view'] in w.dock_host.tabifiedDockWidgets(w.docks['inspector'])
    w.toggle_focus(); qt.processEvents(); assert not any(shown(d) for d in w.docks.values())
    w.toggle_focus(); qt.processEvents(); assert all(shown(d) for d in w.docks.values())
    w.apply_layout('right'); qt.processEvents()
    assert w.dock_host.dockWidgetArea(w.docks['dataset'])==Qt.RightDockWidgetArea
    assert w.docks['dataset'] in w.dock_host.tabifiedDockWidgets(w.docks['inspector'])
    w.docks['view'].hide(); w.apply_layout('default'); qt.processEvents()
    assert w.dock_host.dockWidgetArea(w.docks['dataset'])==Qt.LeftDockWidgetArea and shown(w.docks['view'])
    w.toggle_minimap(); assert w.minimap_check.isChecked()==w.canvas.show_minimap
    w.minimap_check.setChecked(not w.minimap_check.isChecked()); assert w.minimap_check.isChecked()==w.canvas.show_minimap


def test_command_palette_finds_and_runs_commands(window,qt,tmp_path):
    from lannotex.palette import score
    assert score('zoom','Zoom in','View')==0 and score('pix','Actual pixels (100%)','View')==1
    assert score('layout default','Default layout','View › Panels')==3 and score('xyz','Zoom in','View') is None
    w=window; open_ready(w,qt,large_project(tmp_path))
    w.open_palette(); p=w.command_palette; qt.processEvents()
    titles=[p.results.item(i).text().split('\n')[0] for i in range(p.results.count())]
    assert 'Save & next' in titles and 'Default layout' in titles and not any(t.startswith('Command palette') for t in titles)
    QTest.keyClicks(p.query,'actual'); assert p.results.currentItem().text().startswith('Actual pixels')
    QTest.keyClick(p.query,Qt.Key_Return); qt.processEvents()
    assert not p.isVisible() and w.zoom_label.text()=='100%'


def test_thumbnails_load_in_background_and_cache_on_disk(window,qt,tmp_path):
    from lannotex.thumbnails import thumbnail_file
    w=window; open_ready(w,qt,project(tmp_path))
    index=w.model.index(0)
    w.model.data(index,Qt.DecorationRole)
    wait_for(qt,lambda:w.model.data(index,Qt.DecorationRole) is not None)
    icon=w.model.data(index,Qt.DecorationRole); assert not icon.isNull() and icon.availableSizes()[0].width()==128
    path=w.project.resolve(w.model.record(0)['path'])
    assert thumbnail_file(w.thumbnails.folder,path).is_file()
    w.toggle_thumbnails(); assert w.model.data(index,Qt.DecorationRole) is None
    w.toggle_thumbnails(); assert w.model.data(index,Qt.DecorationRole) is not None


def test_thumbnail_cache_key_and_prune(tmp_path):
    from lannotex.thumbnails import make_thumbnail, prune, thumbnail_file
    image=tmp_path/'a.png'; Image.new('RGB',(400,200),'red').save(image)
    folder=tmp_path/'cache'
    thumb=make_thumbnail(folder,image); assert (thumb.width(),thumb.height())==(128,64)
    first=thumbnail_file(folder,image); assert first.is_file()
    assert make_thumbnail(folder,image).width()==128  # served from disk
    os.utime(image,ns=(1_000_000_000,1_000_000_000)); assert thumbnail_file(folder,image)!=first
    with pytest.raises(Exception): make_thumbnail(folder,tmp_path/'missing.png')
    assert prune(folder,budget=0)==0 and not list(folder.glob('*/*.jpg'))


def test_icons_render_and_follow_the_theme(window,qt):
    from lannotex.icons import PATHS, icon, logo
    for name in PATHS: assert not icon(name,'#000000').isNull()
    assert not logo().isNull()
    w=window
    def ink(button):
        image=button.icon().pixmap(32,32).toImage()
        return max((image.pixelColor(x,y) for x in range(32) for y in range(32)),key=lambda c:c.alpha()).lightness()
    before=ink(w.undo_button); w.toggle_theme(); after=ink(w.undo_button); w.toggle_theme()
    assert abs(before-after)>100
    assert w.undo_button.text()=='' and w.undo_button.accessibleName()=='Undo'


def test_number_keys_pick_labels_and_toggle_classes(window,qt,tmp_path):
    w=window; open_ready(w,qt,project(tmp_path)); w.activateWindow(); w.canvas.setFocus(); qt.processEvents()
    QTest.keyClick(w.canvas,Qt.Key_2); assert w.label_combo.currentText()=='dog'
    QTest.keyClick(w.canvas,Qt.Key_1); assert w.label_combo.currentText()=='cat'
    QTest.keyClick(w.canvas,Qt.Key_9); assert w.label_combo.currentText()=='cat'  # no 9th label: ignored
    w.search.setFocus(); QTest.keyClick(w.search,Qt.Key_2); assert w.search.text()=='2' and w.label_combo.currentText()=='cat'
    w.search.clear(); w.filter_timer.stop()


def test_number_keys_toggle_classes_in_classification_projects(window,qt,tmp_path):
    w=window; open_ready(w,qt,project(tmp_path,('classification',))); w.activateWindow(); w.canvas.setFocus(); qt.processEvents()
    QTest.keyClick(w.canvas,Qt.Key_2); assert w.classes.item(1).checkState()==Qt.Checked
    assert [a.label for a in w.document.annotations]==['dog']
    QTest.keyClick(w.canvas,Qt.Key_2); assert w.document.annotations==[]


def test_draft_writes_are_debounced(window,qt,tmp_path):
    w=window; open_ready(w,qt,project(tmp_path)); w.timer.stop()
    drafts=lambda:w.project.conn.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]
    w.commit([Annotation('cat','box',[.1,.1,.4,.4])])
    assert w.draft_timer.isActive() and drafts()==0, 'an edit must not write the draft synchronously'
    w.commit([Annotation('cat','box',[.2,.2,.5,.5])])
    assert drafts()==0
    w.flush_draft()
    assert not w.draft_timer.isActive() and drafts()==1
    assert w.project.load_history(w.current['id'])['undo']
    w.timer.stop(); assert w.save() and drafts()==0


def test_preview_decode_is_capped(tmp_path):
    from lannotex.workers import decode
    path=tmp_path/'big.png'; Image.new('RGB',(3000,2000)).save(path)
    assert decode(path).width()==2560


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
