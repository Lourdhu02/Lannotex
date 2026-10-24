"""Lannotex Desktop: local project orchestration and native Qt workspace."""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import uuid
from PySide6.QtCore import QEvent, QModelIndex, QSettings, QSize, Qt, QThreadPool, QTimer, Slot
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QDockWidget, QDoubleSpinBox, QFileDialog, QSlider, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QKeySequenceEdit, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget)
from . import __version__
from .canvas import Canvas
from .domain import Annotation, Document, validate_all
from .exporters import analyze, export_project, import_annotations
from .models import ImageListModel
from .palette import CommandPalette, menu_commands
from .thumbnails import Thumbnails
from .tiles import Pyramid, cache_dir as tile_cache_dir, prune as prune_tiles
from .icons import icon, logo
from .storage import ConflictError, Project, atomic_text
from .theme import apply_theme
from .workers import ImageLoader, Job, import_images
from .home import Home, CreateProjectDialog, PIPELINES
from .team import TeamClient, TeamServer, add_member, sync_replica, resolve_conflict

COLORS = ['#37b8a5','#70a8f5','#d5a85a','#bf8bef','#ed8ca4','#74c9db','#9fbd68']
DRAFT_DEBOUNCE_MS = 250
_PRUNED = False
DEFAULT_KEYS = {'save':'Ctrl+S','save_next':'Ctrl+Return','previous':'Alt+Left','next':'Alt+Right',
                'undo':'Ctrl+Z','redo':'Ctrl+Shift+Z','delete':'Del','cancel':'Esc','finish':'Return',
                'fit':'F','select':'V','box':'B','polygon':'P','duplicate':'Ctrl+D','redraw':'R',
                'vertex':'Shift+Del','focus':'Ctrl+Shift+F','open':'Ctrl+O','import':'Ctrl+I',
                'zoom_in':'Ctrl+=','zoom_out':'Ctrl+-','actual':'Ctrl+1','minimap':'M','grid':'G','palette':'Ctrl+K'}


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary: widget.setObjectName('primary')
    widget.clicked.connect(callback)
    return widget


def label(text, style='muted'):
    widget = QLabel(text); widget.setObjectName(style); return widget


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'Lannotex Desktop · {__version__}')
        self.resize(1440,940); self.setMinimumSize(900,620)
        # Explicit INI format: the (org, app) constructor ignores setDefaultFormat/setPath, so tests couldn't isolate it.
        self.settings = QSettings(QSettings.IniFormat, QSettings.UserScope, 'Lannotex', 'Desktop')
        self.bindings = dict(DEFAULT_KEYS)
        stored = self.settings.value('keys', {})
        if isinstance(stored, dict): self.bindings.update(stored)
        self.dark = self.settings.value('dark',False,type=bool)
        apply_theme(QApplication.instance(),self.dark)
        self.project = None; self.current = None; self.document = Document()
        self.dirty = False; self.loading = False; self.guard = False; self.token = 0
        self.job = None; self.job_kind = ''; self.focus_mode = False
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(1)
        self.loader = ImageLoader(self)
        self.thumbnails = Thumbnails(self); self.thumbnails.prune_later()
        self.loader.ready.connect(self.image_ready); self.loader.failed.connect(self.image_failed)
        self.tile_pool = QThreadPool(self); self.tile_pool.setMaxThreadCount(1); self.tile_job = None
        self.tile_cache_root = tile_cache_dir()
        global _PRUNED
        if not _PRUNED:
            # Housekeeping, once per process and behind any real work on this pool.
            _PRUNED = True
            self.tile_pool.start(Job(lambda cancel,progress: prune_tiles(self.tile_cache_root)), -1)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.save)
        self.filter_timer = QTimer(self); self.filter_timer.setSingleShot(True); self.filter_timer.timeout.connect(self.filter_images)
        self.draft_timer = QTimer(self); self.draft_timer.setSingleShot(True); self.draft_timer.timeout.connect(self.flush_draft)
        self.actions = {}; self._build_ui(); self._build_menus()
        self.workspace=self.takeCentralWidget(); self.workspace.setObjectName('workspace')
        self.home=Home(); self.pages=QStackedWidget(); self.pages.addWidget(self.home); self.pages.addWidget(self.workspace)
        self.setCentralWidget(self.pages)
        self.home.create_requested.connect(self.new_project); self.home.open_requested.connect(self.open_project)
        self.home.continue_requested.connect(self.load_project); self.home.theme_requested.connect(self.toggle_theme)
        self.home.preferences_requested.connect(self.preferences); self.home.join_requested.connect(self.join_team)
        self.home.refresh(self.settings.value('recent_projects',[],type=list))
        self.host=None; self.team_client=None; self.team_token=''; self.sync_job=None; self.pending_team=None; self.current_revision=None
        self.sync_timer=QTimer(self); self.sync_timer.setInterval(4000); self.sync_timer.timeout.connect(self.sync_team)
        QApplication.instance().installEventFilter(self)
        geometry = self.settings.value('geometry')
        if geometry: self.restoreGeometry(geometry)
        layout = self.settings.value('layout')
        if layout: self.dock_host.restoreState(layout)
        self.set_save_state('No project'); self.refresh_controls(); self.apply_icons()

    def apply_icons(self):
        palette=QApplication.palette(); color=palette.text().color().name(); on_accent=palette.highlightedText().color().name()
        for widget,name in [(self.home_button,'home'),(self.new_button,'plus'),(self.open_button,'folder-open'),(self.team_button,'users'),
                            (self.theme_button,'theme'),(self.analysis_button,'chart'),(self.import_button,'folder-plus'),(self.files_button,'file-plus'),
                            (self.undo_button,'undo'),(self.redo_button,'redo'),(self.fit_button,'fit'),(self.prev_button,'prev'),
                            (self.next_image_button,'next'),(self.save_button,'save')]:
            widget.setIcon(icon(name,color)); widget.setIconSize(QSize(18,18))
        self.export_button.setIcon(icon('export',on_accent)); self.export_button.setIconSize(QSize(18,18))
        for mode,tool in self.tool_buttons.items():
            tool.setIcon(icon(mode,color)); tool.setIconSize(QSize(18,18)); tool.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.home.set_icon_color(color)
        self.setWindowIcon(logo())

    def _build_ui(self):
        root = QWidget(); outer = QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        header=QFrame(); header.setObjectName('header'); bar=QHBoxLayout(header); bar.setContentsMargins(20,14,20,14)
        self.home_button=button('Home',self.go_home); bar.addWidget(self.home_button)
        brand=QVBoxLayout(); brand.setSpacing(1); brand.addWidget(label('Lannotex','brand')); self.pipeline_title=label('ANNOTATION WORKSPACE'); brand.addWidget(self.pipeline_title)
        bar.addLayout(brand); bar.addSpacing(28)
        self.project_title=label('No project open'); bar.addWidget(self.project_title,1)
        self.new_button=button('New project',self.new_project); bar.addWidget(self.new_button)
        self.open_button=button('Open',self.open_project); bar.addWidget(self.open_button)
        self.team_button=button('Team',self.team_dialog); bar.addWidget(self.team_button)
        self.sync_button=button('Sync',self.sync_team); bar.addWidget(self.sync_button); self.sync_button.hide()
        self.theme_button=button('',self.toggle_theme); self.theme_button.setToolTip('Light / dark theme'); self.theme_button.setAccessibleName('Toggle theme'); bar.addWidget(self.theme_button)
        self.analysis_button=button('Analysis',self.show_analysis); bar.addWidget(self.analysis_button)
        self.export_button=button('Export',self.export_dialog,True); bar.addWidget(self.export_button)
        outer.addWidget(header)
        # Inner main window so panels dock, tab, float and persist within the workspace page only.
        self.dock_host=QMainWindow(); self.dock_host.setWindowFlags(Qt.Widget); self.dock_host.setObjectName('dockHost')
        self.dock_host.setDockOptions(QMainWindow.AnimatedDocks|QMainWindow.AllowTabbedDocks|QMainWindow.AllowNestedDocks)
        self.left=QFrame(); self.left.setObjectName('panel'); left=QVBoxLayout(self.left); left.setContentsMargins(12,10,12,10)
        self.dataset_count=label('0 images'); left.addWidget(self.dataset_count)
        row=QHBoxLayout(); self.import_button=button('Folder',self.import_folder); self.import_button.setToolTip('Import a folder of images (Ctrl+I)'); row.addWidget(self.import_button)
        self.files_button=button('Files',self.import_files); self.files_button.setToolTip('Import image files'); row.addWidget(self.files_button); left.addLayout(row)
        self.search=QLineEdit(); self.search.setPlaceholderText('Search image names…'); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda:self.filter_timer.start(180)); left.addWidget(self.search)
        self.filter=QComboBox()
        for text,data in [('All images','all'),('Unlabeled','new'),('Labeled','done'),('No targets','empty')]: self.filter.addItem(text,data)
        self.filter.currentIndexChanged.connect(self.filter_images); left.addWidget(self.filter)
        self.model=ImageListModel(self,self.thumbnails); self.images=QListView(); self.images.setModel(self.model)
        self.images.setIconSize(QSize(56,42)); self.model.set_show_thumbnails(self.settings.value('thumbnails',True,type=bool))
        self.images.setUniformItemSizes(True); self.images.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.images.setAccessibleName('Project images'); self.images.selectionModel().currentChanged.connect(self.select_index)
        left.addWidget(self.images,1)
        self.left_hint=label('Images stay on your disk.\nNothing is uploaded.'); left.addWidget(self.left_hint)
        self.left.setMinimumWidth(220)
        center=QWidget(); middle=QVBoxLayout(center); middle.setContentsMargins(8,0,8,0); middle.setSpacing(8)
        top=QHBoxLayout(); self.image_title=label('Annotation studio','section'); top.addWidget(self.image_title,1)
        self.save_badge=label('No project','save'); top.addWidget(self.save_badge); middle.addLayout(top)
        tools=QHBoxLayout(); self.tool_buttons={}
        for text,mode,key in [('Select','select','V'),('Box','box','B'),('Polygon','polygon','P')]:
            tool=QToolButton(); tool.setText(f'{text}  {key}'); tool.setCheckable(True); tool.setToolTip(f'{text} tool ({key})')
            tool.clicked.connect(lambda checked=False,m=mode:self.set_tool(m)); tools.addWidget(tool); self.tool_buttons[mode]=tool
        self.tool_buttons['select'].setChecked(True)
        tools.addStretch(); self.undo_button=button('',self.undo); self.undo_button.setToolTip('Undo (Ctrl+Z)'); self.undo_button.setAccessibleName('Undo'); tools.addWidget(self.undo_button)
        self.redo_button=button('',self.redo); self.redo_button.setToolTip('Redo (Ctrl+Shift+Z)'); self.redo_button.setAccessibleName('Redo'); tools.addWidget(self.redo_button)
        self.zoom_label=label('100%'); tools.addWidget(self.zoom_label)
        self.fit_button=button('Fit',lambda:self.canvas.fit()); self.fit_button.setToolTip('Fit image (F)'); tools.addWidget(self.fit_button)
        middle.addLayout(tools)
        self.canvas=Canvas(); self.canvas.edited.connect(self.commit); self.canvas.selected.connect(self.selection_changed)
        self.canvas.message.connect(self.notice); self.canvas.zoomed.connect(lambda n:self.zoom_label.setText(f'{n}%'))
        self.canvas.tiles_wanted.connect(self.request_tiles)
        self.canvas.show_minimap=self.settings.value('minimap',True,type=bool); self.canvas.show_grid=self.settings.value('pixel_grid',True,type=bool)
        middle.addWidget(self.canvas,1)
        self.canvas_hint=label('B  Draw box   ·   P  Draw polygon   ·   Space + drag  Pan   ·   F  Fit')
        self.canvas_hint.setWordWrap(True); middle.addWidget(self.canvas_hint)
        footer=QHBoxLayout(); self.prev_button=button('',lambda:self.navigate(-1)); self.prev_button.setToolTip('Previous image (Alt+Left)')
        self.prev_button.setAccessibleName('Previous image'); footer.addWidget(self.prev_button)
        self.position=label('— / —'); footer.addWidget(self.position)
        self.next_image_button=button('',lambda:self.navigate(1)); self.next_image_button.setToolTip('Next image (Alt+Right)')
        self.next_image_button.setAccessibleName('Next image'); footer.addWidget(self.next_image_button)
        footer.addStretch(); self.save_button=button('Save',self.save); footer.addWidget(self.save_button)
        self.next_button=button('Save && next→',self.save_next,True); footer.addWidget(self.next_button); middle.addLayout(footer)
        self.dock_host.setCentralWidget(center)
        self.right=QScrollArea(); self.right.setWidgetResizable(True); self.right.setMinimumWidth(245)
        inspector=QWidget(); form=QVBoxLayout(inspector); form.setContentsMargins(14,10,14,14); form.setSpacing(9)
        self.inspector_heading=label('LABELS & ANNOTATIONS','section'); form.addWidget(self.inspector_heading)
        labelbar=QHBoxLayout(); self.label_combo=QComboBox(); self.label_combo.setMinimumWidth(100)
        self.label_combo.currentTextChanged.connect(self.label_changed); labelbar.addWidget(self.label_combo,1)
        self.add_label_button=button('+',self.add_label); self.add_label_button.setToolTip('Add a named label'); labelbar.addWidget(self.add_label_button)
        form.addLayout(labelbar)
        tax=QHBoxLayout(); self.rename_button=button('Rename',self.rename_label); self.remove_label_button=button('Remove',self.remove_label)
        tax.addWidget(self.rename_button); tax.addWidget(self.remove_label_button); form.addLayout(tax)
        self.classification_heading=label('IMAGE CLASSIFICATION','section'); form.addWidget(self.classification_heading)
        self.classes=QListWidget(); self.classes.setMinimumHeight(70); self.classes.setMaximumHeight(150)
        self.classes.itemChanged.connect(self.class_changed); form.addWidget(self.classes)
        self.classes.currentItemChanged.connect(self.class_focused)
        self.negative=QCheckBox('No target objects in this image'); self.negative.toggled.connect(self.negative_changed); form.addWidget(self.negative)
        self.objects_heading=label('OBJECTS','section'); form.addWidget(self.objects_heading)
        self.annotation_list=QListWidget(); self.annotation_list.setMinimumHeight(110); self.annotation_list.setMaximumHeight(220)
        self.annotation_list.currentItemChanged.connect(self.annotation_selected); form.addWidget(self.annotation_list)
        self.selection_info=label('Select an object to edit its geometry.'); self.selection_info.setWordWrap(True); form.addWidget(self.selection_info)
        self.geometry_widget=QWidget(); grid=QGridLayout(self.geometry_widget); grid.setContentsMargins(0,0,0,0); self.coordinates=[]
        for i,name in enumerate(['Left %','Top %','Right %','Bottom %']):
            box=QDoubleSpinBox(); box.setRange(0,100); box.setDecimals(3); box.setSingleStep(.1)
            grid.addWidget(label(name),i//2*2,i%2); grid.addWidget(box,i//2*2+1,i%2)
            box.editingFinished.connect(self.geometry_changed); self.coordinates.append(box)
        form.addWidget(self.geometry_widget); self.geometry_widget.hide()
        editrow=QHBoxLayout(); self.duplicate_button=button('Duplicate',self.duplicate); editrow.addWidget(self.duplicate_button)
        self.redraw_button=button('Redraw',lambda:self.canvas.redraw()); editrow.addWidget(self.redraw_button); form.addLayout(editrow)
        self.delete_button=button('Delete selected',self.delete_selected); self.delete_button.setObjectName('danger'); form.addWidget(self.delete_button)
        form.addWidget(button('Clear image annotations',self.clear_annotations))
        self.opacity_heading=label('OVERLAY OPACITY','section'); form.addWidget(self.opacity_heading); self.opacity=QSlider(Qt.Horizontal); self.opacity.setRange(0,70)
        self.opacity.setValue(self.settings.value('opacity',15,type=int)); self.canvas.opacity=self.opacity.value()/100
        self.opacity.valueChanged.connect(self.opacity_changed); form.addWidget(self.opacity)
        self.polygon_hint=label('Polygon: drag a vertex to edit. Double-click an edge to insert. Shift+Delete removes the selected vertex.'); self.polygon_hint.setWordWrap(True); form.addWidget(self.polygon_hint)
        form.addStretch(); form.addWidget(button('Keyboard && preferences',self.preferences))
        self.right.setWidget(inspector)
        self.view_panel=QWidget(); vp=QVBoxLayout(self.view_panel); vp.setContentsMargins(14,10,14,14); vp.setSpacing(4)
        self.adjust_sliders={}
        for key,title,low,high,default in [('brightness','Brightness',-100,100,0),('contrast','Contrast',-100,100,0),('gamma','Gamma',20,300,100)]:
            row=QHBoxLayout(); row.addWidget(label(title)); row.addStretch(); value=label(''); row.addWidget(value); vp.addLayout(row)
            slider=QSlider(Qt.Horizontal); slider.setRange(low,high); slider.setValue(default); slider.setAccessibleName(title)
            slider.valueChanged.connect(self.adjustments_changed); vp.addWidget(slider); self.adjust_sliders[key]=(slider,value,default)
        vp.addWidget(button('Reset adjustments',self.reset_adjustments)); vp.addSpacing(8)
        self.minimap_check=QCheckBox('Minimap when zoomed in'); self.minimap_check.setChecked(self.canvas.show_minimap)
        self.minimap_check.toggled.connect(self.minimap_checked); vp.addWidget(self.minimap_check)
        self.grid_check=QCheckBox('Pixel grid from 1200%'); self.grid_check.setChecked(self.canvas.show_grid)
        self.grid_check.toggled.connect(self.grid_checked); vp.addWidget(self.grid_check)
        vp.addStretch(); self.adjustments_changed()
        self.docks={}
        for key,title,widget,area in [('dataset','Dataset',self.left,Qt.LeftDockWidgetArea),('inspector','Inspector',self.right,Qt.RightDockWidgetArea),
                                      ('view','Image view',self.view_panel,Qt.RightDockWidgetArea)]:
            dock=QDockWidget(title,self.dock_host); dock.setObjectName(f'dock-{key}'); dock.setWidget(widget)
            dock.setFeatures(QDockWidget.DockWidgetMovable|QDockWidget.DockWidgetFloatable|QDockWidget.DockWidgetClosable)
            self.dock_host.addDockWidget(area,dock); self.docks[key]=dock
        self.dock_host.resizeDocks([self.docks['dataset'],self.docks['inspector']],[260,290],Qt.Horizontal)
        # Image view shares a tab with the Inspector so the object list keeps full height on laptop screens.
        self.dock_host.tabifyDockWidget(self.docks['inspector'],self.docks['view']); self.docks['inspector'].raise_()
        self.default_layout=self.dock_host.saveState()
        wrap=QWidget(); layout=QVBoxLayout(wrap); layout.setContentsMargins(8,8,8,8); layout.addWidget(self.dock_host)
        outer.addWidget(wrap,1); self.setCentralWidget(root)
        self.status=label('Ready · local-only workspace'); self.statusBar().addWidget(self.status,1)
        self.progress=QProgressBar(); self.progress.setMaximumWidth(180); self.progress.hide(); self.statusBar().addPermanentWidget(self.progress)
        self.cancel_button=button('Cancel job',self.cancel_job); self.cancel_button.hide(); self.statusBar().addPermanentWidget(self.cancel_button)

    def _build_menus(self):
        def add(menu,text,slot,key=None):
            action=QAction(text,self); action.triggered.connect(slot); menu.addAction(action)
            if key: self.actions[key]=(action,text,slot)
            return action
        file=self.menuBar().addMenu('Project')
        add(file,'New project…',self.new_project); add(file,'Open project…',self.open_project,'open')
        add(file,'Import image folder…',self.import_folder,'import'); add(file,'Import image files…',self.import_files)
        add(file,'Import annotations…',self.import_annotation_dialog)
        add(file,'Import LabelMe folder…',lambda:self.import_annotation_dialog(folder=True)); file.addSeparator()
        add(file,'Save',self.save,'save'); add(file,'Save && next',self.save_next,'save_next')
        add(file,'Export…',self.export_dialog); add(file,'Backup project…',self.backup_dialog)
        add(file,'Restore backup…',self.restore_dialog); add(file,'Relink current image…',self.relink_dialog)
        add(file,'Project tasks…',self.task_settings)
        edit=self.menuBar().addMenu('Edit')
        for key,text,slot in [('undo','Undo',self.undo),('redo','Redo',self.redo),('duplicate','Duplicate',self.duplicate),
                              ('delete','Delete annotation',self.delete_selected),('redraw','Redraw',self.canvas.redraw),
                              ('vertex','Delete polygon vertex',self.canvas.delete_vertex),('cancel','Cancel drawing',self.canvas.cancel),
                              ('finish','Finish polygon',self.canvas.finish_polygon)]: add(edit,text,slot,key)
        view=self.menuBar().addMenu('View')
        add(view,'Command palette…',self.open_palette,'palette'); view.addSeparator()
        add(view,'Fit image',self.canvas.fit,'fit'); add(view,'Actual pixels (100%)',self.canvas.actual_pixels,'actual')
        add(view,'Zoom in',lambda:self.canvas.zoom_by(1.25),'zoom_in'); add(view,'Zoom out',lambda:self.canvas.zoom_by(1/1.25),'zoom_out')
        add(view,'Show minimap',self.toggle_minimap,'minimap'); add(view,'Show pixel grid',self.toggle_grid,'grid')
        add(view,'Reset image adjustments',self.reset_adjustments)
        add(view,'Show thumbnails in image list',self.toggle_thumbnails); view.addSeparator()
        panels=view.addMenu('Panels')
        for dock in self.docks.values(): panels.addAction(dock.toggleViewAction())
        panels.addSeparator()
        add(panels,'Default layout',lambda:self.apply_layout('default'))
        add(panels,'All panels on the right',lambda:self.apply_layout('right'))
        add(view,'Focus mode',self.toggle_focus,'focus')
        add(view,'Toggle light / dark',self.toggle_theme); add(view,'Analysis',self.show_analysis)
        add(view,'Previous image',lambda:self.navigate(-1),'previous'); add(view,'Next image',lambda:self.navigate(1),'next')
        for mode in ('select','box','polygon'): add(view,mode.title()+' tool',lambda checked=False,m=mode:self.set_tool(m),mode)
        helpmenu=self.menuBar().addMenu('Help'); add(helpmenu,'Keyboard && preferences',self.preferences)
        add(helpmenu,'About Lannotex',lambda:QMessageBox.information(self,'Lannotex Desktop',f'Lannotex Desktop {__version__}\nLocal image annotation. No login, telemetry or uploads.\n\nDisplay previews are capped at 2560 px. Geometry uses original dimensions.'))
        self.update_action_labels()

    def update_action_labels(self):
        for key,(action,text,_) in self.actions.items(): action.setText(text+'\t'+self.bindings.get(key,''))

    def eventFilter(self, obj, event):
        if event.type()!=QEvent.KeyPress or QApplication.activeWindow()!=self: return super().eventFilter(obj,event)
        if hasattr(self,'pages') and self.pages.currentWidget()==self.home: return super().eventFilter(obj,event)
        seq=QKeySequence(event.key() | event.modifiers().value).toString()
        typing=isinstance(QApplication.focusWidget(),(QLineEdit,QTextEdit,QAbstractSpinBox,QComboBox,QKeySequenceEdit))
        for key,binding in self.bindings.items():
            if seq != QKeySequence(binding).toString(): continue
            if typing and key not in ('save','save_next'): return False
            if key in self.actions:
                self.actions[key][2](); return True
        if not typing and Qt.Key_1<=event.key()<=Qt.Key_9 and event.modifiers() in (Qt.NoModifier,Qt.KeypadModifier):
            if self.pick_label(event.key()-Qt.Key_1): return True
        if not typing and event.key() in (Qt.Key_Left,Qt.Key_Right,Qt.Key_Up,Qt.Key_Down) and event.modifiers() in (Qt.NoModifier,Qt.ShiftModifier):
            self.nudge(event.key(), .01 if event.modifiers()==Qt.ShiftModifier else .001); return True
        return super().eventFilter(obj,event)

    def notice(self, message): self.status.setText(message)

    def fail(self, title, error):
        self.notice(f'{title}: {error}')
        QMessageBox.warning(self,title,str(error))

    def set_save_state(self, text):
        self.save_badge.setText(text)
        self.setWindowTitle(f"{'● ' if self.dirty else ''}Lannotex Desktop · {self.project.root.name if self.project else __version__}")

    def refresh_controls(self):
        opened=self.project is not None; ready=opened and self.current is not None and not self.loading and self.canvas.image is not None
        for b in (self.import_button,self.files_button,self.analysis_button,self.export_button,self.add_label_button): b.setEnabled(opened and self.job is None)
        remote=bool(self.project.setting('team_remote')) if opened else False
        self.left_hint.setText('Local cache · shared with\nyour chosen team host.' if remote else 'Images stay on your disk.\nNothing is uploaded automatically.')
        self.team_button.setEnabled(opened); self.sync_button.setVisible(remote)
        for b in (self.import_button,self.files_button,self.add_label_button,self.rename_button,self.remove_label_button):
            b.setEnabled(opened and self.job is None and not remote)
        self.label_combo.setEnabled(not remote or ready)
        for b in (self.save_button,self.next_button,self.negative,self.classes,self.annotation_list): b.setEnabled(ready)
        tasks=self.project.setting('tasks',['box','polygon','classification']) if opened else []
        objects=bool(set(tasks)&{'box','polygon'})
        for mode,b in self.tool_buttons.items():
            b.setEnabled(ready and (mode=='select' or mode in tasks)); b.setVisible(objects if mode=='select' else mode in tasks)
        for widget in (self.classes,self.classification_heading): widget.setVisible('classification' in tasks)
        for widget in (self.objects_heading,self.annotation_list,self.selection_info,self.duplicate_button,self.redraw_button,self.delete_button,self.opacity,self.opacity_heading): widget.setVisible(objects)
        self.polygon_hint.setVisible('polygon' in tasks)
        self.label_combo.setVisible(objects)
        self.inspector_heading.setText('CLASSES' if tasks==['classification'] else 'LABELS & ANNOTATIONS')
        self.add_label_button.setText('+ Class' if tasks==['classification'] else '+')
        self.negative.setText('None of these classes apply' if tasks==['classification'] else 'No target objects in this image')
        if tasks==['classification']: self.canvas_hint.setText('Select all classes that describe this image · Save & next to continue')
        if tasks==['classification']: self.geometry_widget.hide()
        self.classes.setEnabled(ready and 'classification' in tasks)
        self.undo_button.setEnabled(ready and bool(self.document.undo_stack)); self.redo_button.setEnabled(ready and bool(self.document.redo_stack))
        selected=ready and self.canvas.selection is not None
        for b in (self.duplicate_button,self.redraw_button,self.delete_button): b.setEnabled(selected)

    def new_project(self,pipeline='classification'):
        if not isinstance(pipeline,str): pipeline='classification'
        if self.job or not self.save(): return
        dialog=CreateProjectDialog(pipeline,self)
        if dialog.exec()!=QDialog.Accepted: return
        try:
            project=Project(dialog.folder)
            project.set_setting('tasks',PIPELINES[dialog.pipeline][2]); project.set_setting('pipeline',dialog.pipeline)
            project.set_setting('mode',dialog.mode.currentData()); project.set_setting('name',dialog.name.text().strip())
            for i,name in enumerate(s.strip() for s in dialog.classes.toPlainText().splitlines() if s.strip()): project.add_label(name,COLORS[i%len(COLORS)])
            project.close()
        except Exception as error: self.fail('Could not create project',error); return
        if self.load_project(dialog.folder) and dialog.mode.currentData()=='team': self.team_dialog()

    def open_project(self):
        folder=QFileDialog.getExistingDirectory(self,'Open project folder',self.settings.value('last_project',''))
        if folder: self.load_project(folder)

    def load_project(self, folder, create=False, client=None):
        if self.sync_job: self.notice('Wait for the current team sync before switching.'); return False
        if self.host and Path(folder).resolve()!=self.project.root:
            self.notice('Stop hosting from Team before switching projects.'); return False
        if self.job: self.notice('Finish or cancel the background job before switching projects.'); return False
        if not self.save(): return False
        try: next_project=Project(folder,create=create)
        except Exception as error: self.fail('Cannot open project',error); return False
        self.timer.stop(); self.token+=1
        self.sync_timer.stop(); self.team_client=client; self.team_token=''
        if self.project: self.project.close()
        self.project=next_project; self.current=None; self.document=Document(); self.dirty=False; self.loading=False
        self.canvas.set_image(None); self.canvas.set_annotations([])
        self.project_title.setText(self.project.root.name); self.project_title.setToolTip(str(self.project.root))
        self.settings.setValue('last_project',str(self.project.root))
        recent=self.settings.value('recent_projects',[],type=list)
        recent=[str(self.project.root)]+[p for p in recent if p!=str(self.project.root)]
        self.settings.setValue('recent_projects',recent[:12]); self.home.refresh(recent[:12])
        self.pipeline_title.setText(' / '.join({'box':'DETECTION','polygon':'SEGMENTATION','classification':'CLASSIFICATION'}[t] for t in self.project.setting('tasks',['box','polygon','classification'])))
        self.pages.setCurrentWidget(self.workspace)
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self.filter.blockSignals(True); self.filter.setCurrentIndex(0); self.filter.blockSignals(False)
        self.refresh_labels(); self.refresh_images(); self.set_save_state('Saved'); self.refresh_controls()
        self.notice('Project open. Add labels, import images, and start annotating.')
        if self.team_client: self.sync_timer.start()
        return True

    def go_home(self):
        if not self.save(): return
        self.canvas.cancel(); self.home.refresh(self.settings.value('recent_projects',[],type=list)); self.pages.setCurrentWidget(self.home)

    def refresh_images(self):
        self.model.refresh(self.project,self.search.text(),self.filter.currentData())
        total=self.project.query(count=True) if self.project else 0
        self.dataset_count.setText(f'{total:,} images · {self.model.total:,} shown')
        if self.model.total and self.current is None: self.images.setCurrentIndex(self.model.index(0))
        elif not self.model.total and self.current is None:
            self.canvas.empty_title='Ready for your images'
            self.canvas.empty_detail='Import a folder or select image files using the dataset panel.'
            self.canvas.update()

    def filter_images(self):
        if not self.project: return
        if not self.save(): return
        self.refresh_images()

    @Slot(QModelIndex,QModelIndex)
    def select_index(self,index,previous=QModelIndex()):
        if not index.isValid() or not self.project: return
        record=self.model.record(index.row())
        if self.current and record['id']==self.current['id'] and (self.canvas.image is not None or self.loading): return
        if not self.save():
            self.images.selectionModel().blockSignals(True); self.images.setCurrentIndex(previous); self.images.selectionModel().blockSignals(False); return
        self.canvas.cancel(); self.timer.stop(); self.cancel_tiles(); self.token+=1; self.current=dict(record)
        annotations,negative,recovered,revision=self.project.load_document(record['id'])
        self.document=Document(annotations,negative); self.dirty=recovered; self.loading=True
        if recovered: self.document.restore_history(self.project.load_history(record['id']))
        self.current_revision=revision
        self.canvas.empty_title='Loading image…'; self.canvas.empty_detail=Path(record['path']).name
        self.canvas.set_image(None); self.canvas.set_annotations(annotations)
        self.image_title.setText(Path(record['path']).name); self.image_title.setToolTip(str(self.project.resolve(record['path'])))
        self.position.setText(f'{index.row()+1:,} / {self.model.total:,}')
        self.set_save_state('Recovered draft' if recovered else 'Saved'); self.sync_inspector(); self.refresh_controls()
        path=self.project.resolve(record['path'])
        if self.team_client and not path.is_file():
            if self.job: self.notice('Wait for the current operation, then select the image again.'); self.loading=False; return
            client=self.team_client; token=self.token; ident=record['id']
            def download(cancel,progress):
                client.download(ident,path,cancel); return (token,str(path))
            self.start_job('download',download)
        else:
            cached=self.cached_pyramid(path,record)
            if cached is not None:
                # Reopening a huge image: its tiles are already on disk, so skip decoding the source.
                self.image_ready(self.token,cached.compose(cached.preview_level()))
                self.canvas.set_pyramid(cached); self.canvas.tiles_requested=True
            else: self.loader.request(self.token,path)

    def cached_pyramid(self,path,record):
        if not record['width'] or not record['height']: return None
        try: pyramid=Pyramid(path,record['width'],record['height'],self.tile_cache_root)
        except OSError: return None
        return pyramid if pyramid.complete() else None

    @Slot(object,object)
    def image_ready(self,token,image):
        if token!=self.token: return
        source=(self.current['width'],self.current['height']) if self.current['width'] and self.current['height'] else None
        self.loading=False; self.canvas.set_image(image,source); self.refresh_controls()
        self.notice(f"{self.current['width']} × {self.current['height']} px · full-resolution coordinates · local project")
        if self.dirty and self.settings.value('autosave',True,type=bool): self.timer.start(700)
        self.prefetch_neighbors()

    def prefetch_neighbors(self):
        row=self.images.currentIndex().row(); paths=[]
        for r in (row+1,row-1,row+2):
            record=self.model.record(r)
            if record:
                path=self.project.resolve(record['path'])
                if path.is_file(): paths.append(path)
        self.loader.prefetch(paths)

    def request_tiles(self):
        """Zooming past the preview asks for full-resolution tiles; build them once, then reuse."""
        if not self.current or not self.project: return
        path=self.project.resolve(self.current['path'])
        if not path.is_file(): return
        try: pyramid=Pyramid(path,self.current['width'],self.current['height'],tile_cache_dir())
        except OSError as error:
            self.notice(f'Showing the preview at this zoom: {error}'); return
        self.canvas.set_pyramid(pyramid)
        if pyramid.complete() or self.tile_job: return
        job=Job(pyramid.build)
        job.events.progress.connect(self.tiles_progress)
        job.events.error.connect(self.tiles_error)
        job.events.finished.connect(self.tiles_finished)
        self.tile_job=job
        self.tile_pool.start(job, 1)

    @Slot(int,str)
    def tiles_progress(self,value,message):
        self.notice(message); self.canvas.update()

    @Slot(str)
    def tiles_error(self,error):
        self.notice(f'Showing the preview at this zoom: {error}')

    @Slot()
    def tiles_finished(self):
        self.tile_job=None; self.canvas.update()

    def cancel_tiles(self):
        if self.tile_job: self.tile_job.cancel.set()

    def toggle_minimap(self):
        self.canvas.toggle_minimap(); self.settings.setValue('minimap',self.canvas.show_minimap)
        self.minimap_check.blockSignals(True); self.minimap_check.setChecked(self.canvas.show_minimap); self.minimap_check.blockSignals(False)

    def minimap_checked(self,on):
        if self.canvas.show_minimap!=on: self.toggle_minimap()

    def grid_checked(self,on):
        if self.canvas.show_grid!=on: self.toggle_grid()

    def toggle_grid(self):
        self.canvas.toggle_grid(); self.settings.setValue('pixel_grid',self.canvas.show_grid)
        self.grid_check.blockSignals(True); self.grid_check.setChecked(self.canvas.show_grid); self.grid_check.blockSignals(False)

    @Slot(object,str)
    def image_failed(self,token,error):
        if token!=self.token: return
        self.loading=False; self.canvas.empty_title='Image unavailable'
        self.canvas.empty_detail='Project → Relink current image to locate the original file.\n'+error
        self.canvas.update(); self.notice(error); self.refresh_controls()

    def navigate(self,step):
        if not self.project: return
        index=self.images.currentIndex().row()
        next_row=max(0,min(self.model.total-1,index+step))
        if self.model.total: self.images.setCurrentIndex(self.model.index(next_row))

    def save_next(self):
        if self.save(): self.navigate(1)

    def save(self):
        if self.canvas.points or (self.canvas.drag and self.canvas.drag['kind']!='pan'):
            self.notice('Finish or cancel the current drawing before saving or leaving this image.'); return False
        if not self.project or not self.current or not self.dirty: return True
        self.timer.stop(); self.draft_timer.stop(); self.set_save_state('Saving…')
        try:
            self.project.save_annotations(self.current['id'],self.document.annotations,self.document.negative,
                                          expected_revision=self.current_revision)
            self.current_revision=self.project.conn.execute('SELECT revision FROM revisions WHERE image_id=?',(self.current['id'],)).fetchone()[0]
        except Exception as error:
            if isinstance(error,ConflictError) and self.project.setting('team_remote'):
                with self.project.conn: self.project.conn.execute('UPDATE team_links SET conflict=1 WHERE image_id=?',(self.current['id'],))
            self.set_save_state('Save failed · retry'); self.notice(f'Save failed: {error}. Your edits are still open.'); return False
        self.dirty=False; self.set_save_state('Saved locally · queued' if self.project.setting('team_remote') else 'Saved'); self.model.invalidate(); return True

    def commit(self,annotations,negative=False):
        if not self.current or self.loading or self.canvas.image is None: return
        errors=validate_all(annotations,set(self.canvas.colors),negative)
        allowed=set(self.project.setting('tasks',['box','polygon','classification']))
        old_ids={a.id for a in self.document.annotations}
        if any(a.kind not in allowed and a.id not in old_ids for a in annotations): errors.append('This annotation type is not enabled in the project pipeline')
        if errors: self.notice(errors[0]); return
        if self.document.change(annotations,negative): self.document_changed()

    def document_changed(self):
        self.dirty=True
        self.canvas.set_annotations(self.document.annotations)
        self.sync_inspector(); self.refresh_controls(); self.set_save_state('Unsaved')
        # Coalesce rapid edits: one draft write per 250 ms instead of one per mouse move.
        self.draft_timer.start(DRAFT_DEBOUNCE_MS)
        if self.settings.value('autosave',True,type=bool): self.timer.start(700)

    def flush_draft(self):
        """Persist the recovery draft and the undo history. Safe to call when nothing is pending."""
        self.draft_timer.stop()
        if not self.project or not self.current or not self.dirty: return
        try:
            self.project.save_draft(self.current['id'],self.document.annotations,self.document.negative,
                                    self.current_revision,self.document.history_json())
        except Exception as error:
            self.set_save_state('Draft write failed'); self.notice(f'Keep this window open: {error}')

    def undo(self):
        if not self.current or self.loading: return
        self.canvas.cancel()
        if self.document.undo(): self.document_changed()

    def redo(self):
        if not self.current or self.loading: return
        self.canvas.cancel()
        if self.document.redo(): self.document_changed()

    def set_tool(self,mode):
        if not self.current or self.loading: return
        if mode!='select' and mode not in self.project.setting('tasks',['box','polygon','classification']): return
        self.canvas.set_mode(mode)
        for m,b in self.tool_buttons.items(): b.setChecked(m==mode)
        hints={'select':'Drag to move · corner handles resize · arrow keys nudge',
               'box':'Drag across an object to draw a box · Escape cancels',
               'polygon':'Click vertices · Enter finishes · Escape cancels'}
        self.canvas_hint.setText(hints[mode])

    def refresh_labels(self):
        self.guard=True; active=self.label_combo.currentText(); self.label_combo.clear(); self.classes.clear()
        self.canvas.colors={row['name']:row['color'] for row in self.project.labels()} if self.project else {}
        for name,color in self.canvas.colors.items():
            self.label_combo.addItem(name)
            item=QListWidgetItem(name); item.setFlags(item.flags()|Qt.ItemIsUserCheckable); item.setCheckState(Qt.Unchecked)
            item.setForeground(QColor(color)); self.classes.addItem(item)
        if active in self.canvas.colors: self.label_combo.setCurrentText(active)
        rows=sum(self.classes.sizeHintForRow(i) for i in range(self.classes.count()))+2*self.classes.frameWidth()
        self.classes.setFixedHeight(min(150,max(70,rows)))
        self.canvas.label=self.label_combo.currentText(); self.guard=False; self.sync_inspector()

    def add_label(self):
        if not self.project or self.job or self.project.setting('team_remote'): return
        name,ok=QInputDialog.getText(self,'Add label','Label name')
        if ok and name.strip():
            try: self.project.add_label(name,COLORS[len(self.canvas.colors)%len(COLORS)])
            except Exception as e: self.fail('Cannot add label',e); return
            self.refresh_labels(); self.label_combo.setCurrentText(name.strip())

    def rename_label(self):
        if not self.project or self.job or self.project.setting('team_remote') or not self.label_combo.currentText(): return
        if self.host: self.fail('Stop hosting first','Taxonomy changes require stopping team hosting so no review changes during the rename.'); return
        old=self.label_combo.currentText(); new,ok=QInputDialog.getText(self,'Rename label','New name · updates every annotation',text=old)
        if not ok or new.strip()==old: return
        if not self.save(): return
        try: self.project.rename_label(old,new)
        except Exception as e: self.fail('Cannot rename label',e); return
        if self.current:
            anns,negative,_,self.current_revision=self.project.load_document(self.current['id']); self.document=Document(anns,negative); self.canvas.set_annotations(anns)
        self.refresh_labels(); self.refresh_controls()

    def remove_label(self):
        if not self.project or self.job or self.project.setting('team_remote') or not self.save(): return
        if self.host: self.fail('Stop hosting first','Stop team hosting before removing a label.'); return
        try: self.project.remove_label(self.label_combo.currentText())
        except Exception as e: self.fail('Cannot remove label',e); return
        self.refresh_labels()

    def label_changed(self,name):
        self.canvas.label=name
        if self.guard or not name or not self.canvas.selection: return
        annotations=deepcopy(self.document.annotations)
        for a in annotations:
            if a.id==self.canvas.selection: a.label=name
        self.commit(annotations)

    def sync_inspector(self):
        self.guard=True
        selected=self.canvas.selection; self.annotation_list.clear()
        classes={a.label for a in self.document.annotations if a.kind=='classification'}
        for i in range(self.classes.count()):
            item=self.classes.item(i); item.setCheckState(Qt.Checked if item.text() in classes else Qt.Unchecked)
        self.negative.setChecked(self.document.negative)
        for i,a in enumerate(self.document.annotations,1):
            if a.kind=='classification': continue
            item=QListWidgetItem(f'{i:02d}   {a.label}\n{a.kind.title()}'+(f' · {len(a.geometry)} vertices' if a.kind=='polygon' else ''))
            item.setData(Qt.UserRole,a.id); self.annotation_list.addItem(item)
            if a.id==selected: self.annotation_list.setCurrentItem(item)
        self.guard=False; self.selection_changed(selected)
        self.annotation_list.setFixedHeight(min(160,max(70,self.annotation_list.count()*48)))

    def class_focused(self,item,previous=None):
        if self.guard or not item or not self.project: return
        if self.project.setting('tasks')==['classification']:
            self.guard=True; self.label_combo.setCurrentText(item.text()); self.guard=False

    def class_changed(self,item):
        if self.guard: return
        annotations=[a for a in self.document.annotations if not(a.kind=='classification' and a.label==item.text())]
        if item.checkState()==Qt.Checked: annotations.append(Annotation(item.text(),'classification'))
        self.commit(annotations)

    def negative_changed(self,checked):
        if self.guard: return
        if checked and self.document.annotations:
            if QMessageBox.question(self,'Mark no targets','Clear annotations and mark this image as containing no targets? This can be undone.')!=QMessageBox.Yes:
                self.sync_inspector(); return
        self.commit([] if checked else self.document.annotations,checked)

    def annotation_selected(self,item,previous=None):
        if not self.guard: self.canvas.select(item.data(Qt.UserRole) if item else None)

    def selection_changed(self,ident):
        a=next((x for x in self.document.annotations if x.id==ident),None)
        self.guard=True
        if a:
            self.label_combo.setCurrentText(a.label)
            self.selection_info.setText(f'{a.kind.title()} · {a.id[:8]}')
            for i in range(self.annotation_list.count()):
                if self.annotation_list.item(i).data(Qt.UserRole)==ident: self.annotation_list.setCurrentRow(i)
            if a.kind=='box':
                for box,value in zip(self.coordinates,a.geometry): box.setValue(value*100)
        else: self.selection_info.setText('Select an object to edit its geometry.')
        self.geometry_widget.setVisible(a is not None and a.kind=='box')
        self.guard=False; self.refresh_controls()

    def geometry_changed(self):
        if self.guard or not self.canvas.selection: return
        annotations=deepcopy(self.document.annotations)
        for a in annotations:
            if a.id==self.canvas.selection and a.kind=='box': a.geometry=[w.value()/100 for w in self.coordinates]
        self.commit(annotations); self.selection_changed(self.canvas.selection)

    def delete_selected(self):
        if self.canvas.selection: self.commit([a for a in self.document.annotations if a.id!=self.canvas.selection])

    def duplicate(self):
        a=next((deepcopy(x) for x in self.document.annotations if x.id==self.canvas.selection),None)
        if a:
            a.id=str(uuid.uuid4()); self.commit(self.document.annotations+[a]); self.canvas.select(a.id)

    def clear_annotations(self):
        if not self.current: return
        if QMessageBox.question(self,'Clear annotations','Clear this image and return it to unlabeled? You can undo this action.')==QMessageBox.Yes:
            self.canvas.cancel(); self.commit([])

    def nudge(self,key,amount):
        a=next((deepcopy(x) for x in self.document.annotations if x.id==self.canvas.selection),None)
        if not a or a.kind=='classification': return
        dx,dy={Qt.Key_Left:(-amount,0),Qt.Key_Right:(amount,0),Qt.Key_Up:(0,-amount),Qt.Key_Down:(0,amount)}[key]
        pts=self.canvas.vertices(a)
        dx=max(-min(p[0] for p in pts),min(dx,1-max(p[0] for p in pts)))
        dy=max(-min(p[1] for p in pts),min(dy,1-max(p[1] for p in pts)))
        if a.kind=='box': a.geometry=[a.geometry[0]+dx,a.geometry[1]+dy,a.geometry[2]+dx,a.geometry[3]+dy]
        else: a.geometry=[[x+dx,y+dy] for x,y in a.geometry]
        self.commit([a if x.id==a.id else x for x in self.document.annotations])

    def opacity_changed(self,value): self.canvas.opacity=value/100; self.canvas.update(); self.settings.setValue('opacity',value)

    def import_folder(self):
        if not self.project or self.job: return
        path=QFileDialog.getExistingDirectory(self,'Import image folder')
        if path: self.start_import([path])

    def import_files(self):
        if not self.project or self.job: return
        paths,_=QFileDialog.getOpenFileNames(self,'Import images','','Images (*.jpg *.jpeg *.png *.webp)')
        if paths: self.start_import(paths)

    def start_import(self,paths):
        if self.project.setting('team_remote'): self.notice('Import images on the project host.'); return
        root=self.project.root
        self.start_job('import',lambda cancel,progress:import_images(root,paths,cancel,progress))

    def import_annotation_dialog(self,folder=False):
        if not self.project or self.job or self.project.setting('team_remote'): return
        if folder: path=QFileDialog.getExistingDirectory(self,'Import a LabelMe folder (subfolders included)')
        else: path,_=QFileDialog.getOpenFileName(self,'Import Labelme JSON or native annotations.jsonl','','Annotations (*.json *.jsonl)')
        if path and self.save():
            root=self.project.root; self.start_job('annotations',lambda cancel,progress:import_annotations(root,path,cancel,progress))

    def start_job(self,kind,function):
        if self.job: return
        self.job_kind=kind; self.job=Job(function)
        self.job.events.progress.connect(self.job_progress); self.job.events.result.connect(self.job_result)
        self.job.events.error.connect(self.job_error); self.job.events.finished.connect(self.job_finished)
        self.progress.setRange(0,0); self.progress.show(); self.cancel_button.show(); self.refresh_controls()
        self.notice(f'{kind.title()} running…'); self.pool.start(self.job)

    @Slot(int,str)
    def job_progress(self,value,message):
        if self.job_kind=='export': self.progress.setRange(0,100); self.progress.setValue(value)
        self.notice(message)

    @Slot(object)
    def job_result(self,result):
        if self.job_kind in ('import','annotations'):
            self.refresh_images(); self.refresh_labels()
            text=f"Imported {result['added']:,} images"+(' · cancelled' if result.get('cancelled') else '')
            shapes=result.get('skipped_shapes') or {}
            details=([('Shapes skipped:\n'+'\n'.join(f'  {n:,} × {reason}' for reason,n in sorted(shapes.items())))] if shapes else [])+(['\n'.join(result['errors'])] if result.get('errors') else [])
            if details: self.show_report('Import summary',text+'\n\n'+'\n\n'.join(details))
            self.notice(text)
        elif self.job_kind=='export':
            self.show_report('Export summary',f"Included: {result['included']}\nUnlabeled included: {result['unlabeled']}\nSkipped images: {result['skipped']}\nAnnotations unsupported by this format: {result['unsupported_annotations']}\nCancelled: {result.get('cancelled',False)}\n\n{result['path']}\n\n"+'\n'.join(result['errors']))
        elif self.job_kind=='analysis': self.analysis_result(result)
        elif self.job_kind=='backup': self.notice(f'Backup saved: {result}')
        elif self.job_kind=='join': self.pending_team=result
        elif self.job_kind=='download':
            token,path=result
            if token==self.token: self.loader.request(token,path)
            elif self.current and self.canvas.image is None: self.pending_image_retry=True
        elif self.job_kind=='resolve':
            self.reload_current(); self.notice('Conflict resolved; project history retains the save.')

    @Slot(str)
    def job_error(self,error):
        if self.job_kind=='download': self.image_failed(self.token,error)
        else: self.fail('Background operation failed',error)

    @Slot()
    def job_finished(self):
        self.job=None; self.job_kind=''; self.progress.hide(); self.cancel_button.hide(); self.refresh_controls()
        if self.pending_team:
            root,client=self.pending_team; self.pending_team=None; self.load_project(root,client=client)
        elif getattr(self,'pending_image_retry',False):
            self.pending_image_retry=False; self.select_index(self.images.currentIndex())

    def cancel_job(self):
        if self.job: self.job.cancel.set(); self.notice('Cancelling after the current file…')

    def export_dialog(self):
        if not self.project or self.job or not self.save(): return
        format_name,ok=QInputDialog.getItem(self,'Export annotations','Editable local export format',
                                          ['Labelme JSON','YOLO boxes','COCO JSON','Classification CSV','Native JSONL'],0,False)
        if not ok: return
        path=QFileDialog.getExistingDirectory(self,'Choose export destination')
        if path:
            root=self.project.root; self.start_job('export',lambda cancel,progress:export_project(root,path,format_name,cancel,progress))

    def show_analysis(self):
        if self.project and not self.job and self.save():
            root=self.project.root; self.start_job('analysis',lambda cancel,progress:analyze(root,cancel,progress))

    def analysis_result(self,result):
        dialog=QDialog(self); dialog.setWindowTitle('Dataset analysis'); dialog.resize(760,620)
        layout=QVBoxLayout(dialog); layout.addWidget(label('Dataset overview','brand'))
        layout.addWidget(label(f"{result['total']:,} images   ·   {result['labeled']:,} labeled   ·   {result['unlabeled']:,} unlabeled   ·   {result['negative']:,} no targets"))
        bar=QProgressBar(); bar.setRange(0,max(1,result['total'])); bar.setValue(result['labeled']+result['negative']); layout.addWidget(bar)
        layout.addWidget(label(f"{result['boxes']} boxes   ·   {result['polygons']} polygons   ·   {result['classes']} classes   ·   {result['drafts']} recovery drafts"))
        table=QTableWidget(len(result['distribution']),2); table.setHorizontalHeaderLabels(['Label','Annotation count']); table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for i,(name,count) in enumerate(sorted(result['distribution'].items(),key=lambda x:-x[1])):
            table.setItem(i,0,QTableWidgetItem(name)); table.setItem(i,1,QTableWidgetItem(str(count)))
        layout.addWidget(table); issues=QTextEdit(); issues.setReadOnly(True); issues.setPlainText('\n'.join(result['problems']) or 'No annotation-validation problems or missing images found.'); layout.addWidget(issues)
        layout.addWidget(button('Close',dialog.accept)); dialog.exec()

    def show_report(self,title,text):
        dialog=QDialog(self); dialog.setWindowTitle(title); dialog.resize(720,460); layout=QVBoxLayout(dialog)
        report=QTextEdit(); report.setReadOnly(True); report.setPlainText(text); layout.addWidget(report)
        layout.addWidget(button('Close',dialog.accept)); dialog.exec()

    def backup_dialog(self):
        if not self.project or self.job or not self.save(): return
        path,_=QFileDialog.getSaveFileName(self,'Backup project database',str(self.project.root.parent/(self.project.root.name+'.sqlite3')),'Project backup (*.sqlite3)')
        if not path: return
        root=self.project.root
        def backup(cancel,progress):
            project=Project(root,create=False)
            try: project.backup(path); return path
            finally: project.close()
        self.start_job('backup',backup)

    def restore_dialog(self):
        if self.job or not self.save(): return
        path,_=QFileDialog.getOpenFileName(self,'Choose backup','','Project backup (*.sqlite3)')
        if not path: return
        folder=QFileDialog.getExistingDirectory(self,'Restore into a new project folder')
        if not folder: return
        try: restored=Project.restore(path,folder); restored.close()
        except Exception as e: self.fail('Restore failed',e); return
        self.load_project(folder)

    def relink_dialog(self):
        if not self.current or not self.save(): return
        path,_=QFileDialog.getOpenFileName(self,'Locate this image','','Images (*.jpg *.jpeg *.png *.webp)')
        if not path: return
        try:
            from PIL import Image
            with Image.open(path) as im:
                w,h=im.size
                if im.getexif().get(274,1) in (5,6,7,8): w,h=h,w
            self.project.relink(self.current['id'],path,w,h)
            self.current=dict(self.project.image(self.current['id'])); self.token+=1; self.loading=True
            self.loader.request(self.token,path); self.model.invalidate()
        except Exception as e: self.fail('Relink failed',e)

    def task_settings(self):
        if not self.project or not self.save(): return
        if self.project.setting('team_remote') or self.host:
            self.notice('Pipeline settings are managed on the host while team hosting is stopped.'); return
        dialog=QDialog(self); dialog.setWindowTitle('Project tasks'); layout=QVBoxLayout(dialog)
        layout.addWidget(label('Enable any combination of tasks. Existing annotations are retained.'))
        tasks=self.project.setting('tasks',['box','polygon','classification']); boxes={}
        for key,title in [('box','Bounding-box detection'),('polygon','Polygon segmentation'),('classification','Multi-label classification')]:
            box=QCheckBox(title); box.setChecked(key in tasks); boxes[key]=box; layout.addWidget(box)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec()==QDialog.Accepted:
            tasks=[key for key,box in boxes.items() if box.isChecked()]
            if not tasks: self.fail('Choose a pipeline','Enable at least one task.'); return
            used={row[0] for row in self.project.conn.execute("SELECT DISTINCT json_extract(data,'$.kind') FROM annotations")}
            if used-set(tasks): self.fail('Existing annotations use this task','Export or remove those annotations before disabling their task.'); return
            self.project.set_setting('tasks',tasks); self.set_tool('select'); self.refresh_controls()

    def toggle_focus(self):
        self.focus_mode=not self.focus_mode
        if self.focus_mode:
            self.pre_focus=self.dock_host.saveState()
            for dock in self.docks.values(): dock.hide()
        else: self.dock_host.restoreState(self.pre_focus)

    def pick_label(self,index):
        """Number keys: toggle a class in classification projects, otherwise choose the drawing label
        (which relabels the selected shape, like choosing it in the label box)."""
        if not self.project or not self.current or self.loading: return False
        if self.project.setting('tasks',['box','polygon','classification'])==['classification']:
            if index>=self.classes.count() or not self.classes.isEnabled(): return False
            item=self.classes.item(index); item.setCheckState(Qt.Unchecked if item.checkState()==Qt.Checked else Qt.Checked)
            return True
        if index>=self.label_combo.count(): return False
        self.label_combo.setCurrentIndex(index); self.notice(f'Label {index+1}: {self.label_combo.currentText()}')
        return True

    def toggle_thumbnails(self):
        self.model.set_show_thumbnails(not self.model.show_thumbnails); self.settings.setValue('thumbnails',self.model.show_thumbnails)

    def open_palette(self):
        commands=[c for c in menu_commands(self.menuBar()) if not c[0].startswith('Command palette')]
        self.command_palette=CommandPalette(self,commands); self.command_palette.open()

    def apply_layout(self,name):
        self.focus_mode=False
        self.dock_host.restoreState(self.default_layout)
        for dock in self.docks.values(): dock.setFloating(False); dock.show()
        if name=='right':
            self.dock_host.addDockWidget(Qt.RightDockWidgetArea,self.docks['dataset'])
            self.dock_host.tabifyDockWidget(self.docks['inspector'],self.docks['dataset'])
        self.docks['inspector'].raise_()

    def adjustments_changed(self,*_):
        values={key:slider.value() for key,(slider,_,_) in self.adjust_sliders.items()}
        for key,(slider,text,_) in self.adjust_sliders.items():
            text.setText(f"{values[key]/100:.2f}" if key=='gamma' else f"{values[key]:+d}")
        self.canvas.set_adjustments(values['brightness'],values['contrast'],values['gamma']/100)

    def reset_adjustments(self):
        for slider,_,default in self.adjust_sliders.values(): slider.setValue(default)

    def join_team(self):
        if self.job or self.sync_job or self.host or not self.save(): return
        dialog=QDialog(self); dialog.setWindowTitle('Join a team project'); dialog.resize(580,420)
        layout=QVBoxLayout(dialog); layout.addWidget(label('Connect to your project host','cardTitle'))
        url=QLineEdit(); url.setPlaceholderText('http://192.168.1.20:8765 or https://your-host')
        token=QLineEdit(); token.setPlaceholderText('Your reviewer access token'); token.setEchoMode(QLineEdit.Password)
        folder=QLineEdit(); folder.setPlaceholderText('Local project cache folder')
        for title,widget in [('Host address',url),('Access token',token),('Local cache',folder)]: layout.addWidget(label(title)); layout.addWidget(widget)
        if self.project and self.project.setting('team_remote'):
            url.setText(self.project.setting('team_remote')); folder.setText(str(self.project.root))
        def browse():
            path=QFileDialog.getExistingDirectory(dialog,'Choose a private local project cache folder')
            if path: folder.setText(path)
        layout.addWidget(button('Choose local folder…',browse))
        info=label('Images are downloaded from your chosen host as you open them. Tokens stay in memory. Use HTTPS or a trusted LAN/VPN.'); info.setWordWrap(True); layout.addWidget(info)
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel); buttons.addButton('Connect',QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec()!=QDialog.Accepted: return
        try:
            client=TeamClient(url.text().strip(),token.text().strip())
            if not token.text().strip() or not folder.text().strip(): raise ValueError('Enter your token and a local cache folder')
            root=Path(folder.text()).resolve()
            if (root/'project.sqlite3').exists():
                check=Project(root,create=False)
                try:
                    if check.setting('team_remote')!=client.url: raise ValueError('Choose a new cache folder or the cache for this host')
                finally: check.close()
            elif root.exists() and any(root.iterdir()): raise ValueError('Use an empty folder for a new team cache')
        except Exception as e: self.fail('Cannot connect',e); return
        def connect(cancel,progress):
            # Authenticate before creating any cache.
            client.request('/meta')
            project=Project(root); project.set_setting('team_remote',client.url); project.close()
            sync_replica(root,client,cancel,progress)
            return root,client
        self.start_job('join',connect)

    def sync_team(self):
        if not self.team_client:
            if self.project and self.project.setting('team_remote'): self.join_team()
            return
        if self.sync_job or self.job or not self.project: return
        if not self.save(): return
        root=self.project.root; client=self.team_client
        self.sync_job=Job(lambda cancel,progress:sync_replica(root,client,cancel,progress))
        self.sync_job.events.result.connect(self.sync_result); self.sync_job.events.error.connect(self.sync_error)
        self.sync_job.events.finished.connect(self.sync_finished)
        self.sync_button.setText('Syncing…'); self.pool.start(self.sync_job)

    @Slot(object)
    def sync_result(self,result):
        current_id=self.current['id'] if self.current else None
        # Do not reset list selection on every timer tick.
        if self.model.total!=self.project.query(self.search.text(),self.filter.currentData(),count=True): self.refresh_images()
        else: self.model.invalidate()
        self.refresh_labels()
        if current_id in result['changed'] and not self.dirty: self.reload_current()
        if result['conflicts']:
            self.notice(f"{len(result['conflicts'])} image conflict(s). Open Team → resolve to choose a version.")
            self.sync_button.setText('Resolve conflicts')
        else:
            queued=self.project.conn.execute('SELECT COUNT(*) FROM team_links WHERE dirty=1').fetchone()[0]
            self.notice('Team synced · '+result['meta']['reviewer'])
            if not self.dirty: self.set_save_state('Queued for sync' if queued else 'Synced to team')

    @Slot(str)
    def sync_error(self,error):
        self.notice(f'Team offline / sync failed: {error}. Local work is retained.')
        self.sync_button.setText('Retry sync')

    @Slot()
    def sync_finished(self):
        self.sync_job=None
        if self.sync_button.text()=='Syncing…': self.sync_button.setText('Sync')

    def reload_current(self):
        if not self.current: return
        anns,negative,recovered,revision=self.project.load_document(self.current['id'])
        self.current=dict(self.project.image(self.current['id']))
        self.current_revision=revision
        self.document=Document(anns,negative); self.dirty=recovered
        self.canvas.set_annotations(anns); self.sync_inspector(); self.model.invalidate()

    def team_dialog(self):
        if not self.project: return
        if self.project.setting('team_remote'):
            self.team_client_dialog(); return
        dialog=QDialog(self); dialog.setWindowTitle('Team workspace'); dialog.resize(620,560)
        layout=QVBoxLayout(dialog); layout.addWidget(label('Work together, on your host.','cardTitle'))
        if self.current and self.dirty:
            latest=self.project.conn.execute('SELECT revision FROM revisions WHERE image_id=?',(self.current['id'],)).fetchone()[0]
            if latest!=self.current_revision:
                layout.addWidget(label('The current image changed on the team while you were editing.'))
                layout.addWidget(button('Resolve my current image…',lambda:(dialog.accept(),self.resolve_owner_conflict())))
        info=label('This computer owns the project. Teammates connect with individual reviewer tokens. Stop hosting to disconnect access.'); info.setWordWrap(True); layout.addWidget(info)
        host=QLineEdit('0.0.0.0'); host.setPlaceholderText('Listen address'); port=QLineEdit('8765')
        row=QHBoxLayout(); row.addWidget(label('Listen')); row.addWidget(host); row.addWidget(label('Port')); row.addWidget(port); layout.addLayout(row)
        status=label('Hosting is stopped'); layout.addWidget(status)
        def toggle():
            if self.host:
                self.host.stop(); self.host=None; status.setText('Hosting stopped'); start.setText('Start hosting'); return
            if not self.save(): return
            try:
                self.host=TeamServer(self.project.root,host.text().strip(),int(port.text())).start()
                self.project.set_setting('mode','team')
                status.setText(f'Listening on port {self.host.server_address[1]}. Share your LAN IP with teammates.')
                start.setText('Stop hosting')
            except Exception as e: self.fail('Could not start host',e)
        start=button('Stop hosting' if self.host else 'Start hosting',toggle,True); layout.addWidget(start)
        if self.host: status.setText(f'Hosting on port {self.host.server_address[1]}')
        layout.addWidget(label('REVIEWERS','section')); members=QListWidget(); layout.addWidget(members)
        def refresh():
            members.clear()
            for member in self.project.conn.execute('SELECT id,name,active FROM team_members ORDER BY name'):
                item=QListWidgetItem(member['name']+('' if member['active'] else ' · revoked')); item.setData(Qt.UserRole,member['id']); members.addItem(item)
        def invite():
            name,ok=QInputDialog.getText(dialog,'Invite reviewer','Reviewer name')
            if not ok: return
            try: access=add_member(self.project.root,name)
            except Exception as e: self.fail('Cannot invite',e); return
            token_dialog=QDialog(dialog); token_dialog.setWindowTitle('Reviewer access token'); token_layout=QVBoxLayout(token_dialog)
            token_layout.addWidget(label('Share privately with this reviewer. It is displayed only now.'))
            field=QLineEdit(access); field.setReadOnly(True); field.setMinimumWidth(440); token_layout.addWidget(field)
            token_layout.addWidget(button('Close',token_dialog.accept)); token_dialog.exec(); refresh()
        def revoke():
            item=members.currentItem()
            if not item: return
            if QMessageBox.question(dialog,'Revoke access','Revoke this reviewer token? Their existing work remains in the project.')!=QMessageBox.Yes: return
            with self.project.conn: self.project.conn.execute('UPDATE team_members SET active=0 WHERE id=?',(item.data(Qt.UserRole),))
            refresh()
        row=QHBoxLayout(); row.addWidget(button('Invite reviewer',invite)); row.addWidget(button('Revoke selected',revoke)); layout.addLayout(row); refresh()
        note=label('Built-in desktop hosting uses HTTP on a trusted LAN/VPN. For TLS, use the CLI host command with a certificate.'); note.setWordWrap(True); layout.addWidget(note)
        layout.addWidget(button('Done',dialog.accept)); dialog.exec()

    def resolve_owner_conflict(self):
        if not self.current: return
        box=QMessageBox(self); box.setWindowTitle('Resolve changed image')
        box.setText('The team saved a newer version. Choose which version to keep. Previous saved versions remain in project history.')
        mine=box.addButton('Publish my version',QMessageBox.AcceptRole)
        theirs=box.addButton('Use team version',QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel); box.exec()
        if box.clickedButton()==mine:
            self.current_revision=self.project.conn.execute('SELECT revision FROM revisions WHERE image_id=?',(self.current['id'],)).fetchone()[0]
            self.save()
        elif box.clickedButton()==theirs:
            with self.project.conn: self.project.conn.execute('DELETE FROM drafts WHERE image_id=?',(self.current['id'],))
            self.reload_current(); self.set_save_state('Saved')

    def team_client_dialog(self):
        dialog=QDialog(self); dialog.setWindowTitle('Team sync & conflicts'); dialog.resize(630,480); layout=QVBoxLayout(dialog)
        layout.addWidget(label(self.project.setting('name',self.project.root.name),'cardTitle'))
        layout.addWidget(label(self.project.setting('team_remote')))
        conflicts=QListWidget(); layout.addWidget(conflicts)
        for row in self.project.conn.execute('SELECT images.id,images.path FROM team_links JOIN images ON images.id=team_links.image_id WHERE conflict=1'):
            item=QListWidgetItem(Path(row['path']).name); item.setData(Qt.UserRole,row['id']); conflicts.addItem(item)
        if not conflicts.count(): layout.addWidget(label('No conflicts. Each saved image is synchronized in the background.'))
        layout.addWidget(button('Reconnect with reviewer token…',lambda:(dialog.accept(),self.join_team())))
        def resolve(keep):
            if self.sync_job or self.job: self.notice('Wait for the current sync to finish.'); return
            if not self.team_client or not conflicts.currentItem(): return
            ident=conflicts.currentItem().data(Qt.UserRole)
            message='Publish your local version over the current team version?' if keep else 'Use the team version? Your local conflicting version will be replaced.'
            if QMessageBox.question(dialog,'Resolve conflict',message)!=QMessageBox.Yes: return
            root=self.project.root; client=self.team_client
            dialog.accept()
            self.start_job('resolve',lambda cancel,progress:resolve_conflict(root,ident,client,keep))
        row=QHBoxLayout(); row.addWidget(button('Use team version',lambda:resolve(False))); row.addWidget(button('Publish my version',lambda:resolve(True))); layout.addLayout(row)
        layout.addWidget(button('Close',dialog.accept)); dialog.exec()

    def toggle_theme(self):
        self.dark=not self.dark; self.settings.setValue('dark',self.dark); apply_theme(QApplication.instance(),self.dark); self.apply_icons()

    def preferences(self):
        dialog=QDialog(self); dialog.setWindowTitle('Keyboard & preferences'); dialog.resize(530,700); layout=QVBoxLayout(dialog)
        autosave=QCheckBox('Autosave after 700 ms · recovery drafts are always written'); autosave.setChecked(self.settings.value('autosave',True,type=bool)); layout.addWidget(autosave)
        layout.addWidget(label('Space + drag pans. Arrow keys nudge; Shift increases the step.'))
        table=QTableWidget(len(self.bindings),2); table.setHorizontalHeaderLabels(['Command','Shortcut']); table.horizontalHeader().setStretchLastSection(True); fields={}
        for i,(key,value) in enumerate(self.bindings.items()):
            item=QTableWidgetItem(key.replace('_',' ').title()); item.setFlags(item.flags() & ~Qt.ItemIsEditable); table.setItem(i,0,item)
            editor=QKeySequenceEdit(QKeySequence(value)); editor.setMaximumSequenceLength(1); table.setCellWidget(i,1,editor); fields[key]=editor
        layout.addWidget(table)
        layout.addWidget(button('Toggle light / dark',self.toggle_theme))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); layout.addWidget(buttons)
        def accept():
            bindings={k:v.keySequence().toString() for k,v in fields.items()}
            values=[v for v in bindings.values() if v]
            if len(values)!=len(set(values)): QMessageBox.warning(dialog,'Shortcut conflict','Choose unique shortcuts.'); return
            self.bindings=bindings; self.settings.setValue('keys',bindings); self.settings.setValue('autosave',autosave.isChecked()); self.update_action_labels(); dialog.accept()
        buttons.accepted.connect(accept); buttons.rejected.connect(dialog.reject); dialog.exec()

    def closeEvent(self,event):
        if self.sync_job:
            self.sync_job.cancel.set(); self.notice('Waiting for the current team request to finish.'); event.ignore(); return
        if self.job:
            self.cancel_job(); self.loader.stop()
            self.notice('Finishing the active file operation. Close again when it has stopped.'); event.ignore(); return
        self.loader.stop(); self.thumbnails.pool.clear(); self.thumbnails.pool.waitForDone(3000)
        self.cancel_tiles(); self.tile_pool.clear(); self.tile_pool.waitForDone(5000)
        if not self.save():
            self.fail('Cannot close safely','Saving failed. Your edits remain in this window. Resolve disk space or permissions and try Save again.'); event.ignore(); return
        self.settings.setValue('geometry',self.saveGeometry()); self.settings.setValue('layout',self.pre_focus if self.focus_mode else self.dock_host.saveState())
        self.sync_timer.stop()
        if self.host: self.host.stop(); self.host=None
        if self.project: self.project.close(); self.project=None
        QApplication.instance().removeEventFilter(self); event.accept()


def main():
    app=QApplication(sys.argv); app.setOrganizationName('Lannotex'); app.setApplicationName('Lannotex Desktop')
    app.setStyle('Fusion'); app.setWindowIcon(logo())
    window=Main(); window.show()
    # A bounded test must actually enter the Qt event loop and report completion.
    if '--smoke-test' in sys.argv:
        def done():
            target=os.environ.get('LANNOTEX_SMOKE_RESULT')
            if target: atomic_text(target,json.dumps({'version':__version__,'window_visible':window.isVisible(),'qt_event_loop':True}))
            window.close()
        QTimer.singleShot(300,done)
    raise SystemExit(app.exec())
