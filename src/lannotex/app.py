"""Lannotex Desktop: local project orchestration and native Qt workspace."""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import uuid
from PySide6.QtCore import QEvent, QModelIndex, QSettings, Qt, QThreadPool, QTimer, Slot
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QKeySequenceEdit, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget)
from .canvas import Canvas
from .domain import Annotation, Document, validate_all
from .exporters import analyze, export_project, import_annotations
from .models import ImageListModel
from .storage import Project, atomic_text
from .theme import apply_theme
from .workers import ImageLoader, Job, import_images

COLORS = ['#37b8a5','#70a8f5','#d5a85a','#bf8bef','#ed8ca4','#74c9db','#9fbd68']
DEFAULT_KEYS = {'save':'Ctrl+S','save_next':'Ctrl+Return','previous':'Alt+Left','next':'Alt+Right',
                'undo':'Ctrl+Z','redo':'Ctrl+Shift+Z','delete':'Del','cancel':'Esc','finish':'Return',
                'fit':'F','select':'V','box':'B','polygon':'P','duplicate':'Ctrl+D','redraw':'R',
                'vertex':'Shift+Del','focus':'Tab','open':'Ctrl+O','import':'Ctrl+I'}


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
        self.setWindowTitle('Lannotex Desktop · 0.0.2')
        self.resize(1440,940); self.setMinimumSize(900,620)
        self.settings = QSettings('Lannotex','Desktop')
        self.bindings = dict(DEFAULT_KEYS)
        self.bindings.update(self.settings.value('keys',{},type=dict))
        self.dark = self.settings.value('dark',True,type=bool)
        apply_theme(QApplication.instance(),self.dark)
        self.project = None; self.current = None; self.document = Document()
        self.dirty = False; self.loading = False; self.guard = False; self.token = 0
        self.job = None; self.job_kind = ''; self.focus_mode = False
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(1)
        self.loader = ImageLoader(self)
        self.loader.ready.connect(self.image_ready); self.loader.failed.connect(self.image_failed)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.save)
        self.filter_timer = QTimer(self); self.filter_timer.setSingleShot(True); self.filter_timer.timeout.connect(self.filter_images)
        self.actions = {}; self._build_ui(); self._build_menus()
        QApplication.instance().installEventFilter(self)
        geometry = self.settings.value('geometry')
        if geometry: self.restoreGeometry(geometry)
        sizes = self.settings.value('splitter')
        if sizes: self.splitter.restoreState(sizes)
        self.set_save_state('No project'); self.refresh_controls()

    def _build_ui(self):
        root = QWidget(); outer = QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        header=QFrame(); header.setObjectName('header'); bar=QHBoxLayout(header); bar.setContentsMargins(20,14,20,14)
        brand=QVBoxLayout(); brand.setSpacing(1); brand.addWidget(label('Lannotex','brand')); brand.addWidget(label('DESKTOP  /  LOCAL WORKSPACE'))
        bar.addLayout(brand); bar.addSpacing(28)
        self.project_title=label('No project open'); bar.addWidget(self.project_title,1)
        bar.addWidget(button('New project',self.new_project)); bar.addWidget(button('Open',self.open_project))
        self.analysis_button=button('Analysis',self.show_analysis); bar.addWidget(self.analysis_button)
        self.export_button=button('Export',self.export_dialog,True); bar.addWidget(self.export_button)
        outer.addWidget(header)
        self.splitter=QSplitter(); self.splitter.setChildrenCollapsible(False)
        self.left=QFrame(); self.left.setObjectName('panel'); left=QVBoxLayout(self.left); left.setContentsMargins(12,10,12,10)
        left.addWidget(label('DATASET','section'))
        self.dataset_count=label('0 images'); left.addWidget(self.dataset_count)
        row=QHBoxLayout(); self.import_button=button('+ Folder',self.import_folder); row.addWidget(self.import_button)
        self.files_button=button('+ Files',self.import_files); row.addWidget(self.files_button); left.addLayout(row)
        self.search=QLineEdit(); self.search.setPlaceholderText('Search image names…'); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda:self.filter_timer.start(180)); left.addWidget(self.search)
        self.filter=QComboBox()
        for text,data in [('All images','all'),('Unlabeled','new'),('Labeled','done'),('No targets','empty')]: self.filter.addItem(text,data)
        self.filter.currentIndexChanged.connect(self.filter_images); left.addWidget(self.filter)
        self.model=ImageListModel(self); self.images=QListView(); self.images.setModel(self.model)
        self.images.setUniformItemSizes(True); self.images.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.images.setAccessibleName('Project images'); self.images.selectionModel().currentChanged.connect(self.select_index)
        left.addWidget(self.images,1)
        self.left_hint=label('Images stay on your disk.\nNothing is uploaded.'); left.addWidget(self.left_hint)
        self.left.setMinimumWidth(220); self.splitter.addWidget(self.left)
        center=QWidget(); middle=QVBoxLayout(center); middle.setContentsMargins(8,0,8,0); middle.setSpacing(8)
        top=QHBoxLayout(); self.image_title=label('Annotation studio','section'); top.addWidget(self.image_title,1)
        self.save_badge=label('No project','save'); top.addWidget(self.save_badge); middle.addLayout(top)
        tools=QHBoxLayout(); self.tool_buttons={}
        for text,mode,key in [('Select','select','V'),('Box','box','B'),('Polygon','polygon','P')]:
            tool=QToolButton(); tool.setText(f'{text}  {key}'); tool.setCheckable(True); tool.setToolTip(f'{text} tool ({key})')
            tool.clicked.connect(lambda checked=False,m=mode:self.set_tool(m)); tools.addWidget(tool); self.tool_buttons[mode]=tool
        self.tool_buttons['select'].setChecked(True)
        tools.addStretch(); self.undo_button=button('↶',self.undo); self.undo_button.setToolTip('Undo (Ctrl+Z)'); tools.addWidget(self.undo_button)
        self.redo_button=button('↷',self.redo); self.redo_button.setToolTip('Redo (Ctrl+Shift+Z)'); tools.addWidget(self.redo_button)
        self.zoom_label=label('100%'); tools.addWidget(self.zoom_label); tools.addWidget(button('Fit',lambda:self.canvas.fit()))
        middle.addLayout(tools)
        self.canvas=Canvas(); self.canvas.edited.connect(self.commit); self.canvas.selected.connect(self.selection_changed)
        self.canvas.message.connect(self.notice); self.canvas.zoomed.connect(lambda n:self.zoom_label.setText(f'{n}%'))
        middle.addWidget(self.canvas,1)
        self.canvas_hint=label('B  Draw box   ·   P  Draw polygon   ·   Space + drag  Pan   ·   F  Fit')
        self.canvas_hint.setWordWrap(True); middle.addWidget(self.canvas_hint)
        footer=QHBoxLayout(); footer.addWidget(button('←',lambda:self.navigate(-1)))
        self.position=label('— / —'); footer.addWidget(self.position); footer.addWidget(button('→',lambda:self.navigate(1)))
        footer.addStretch(); self.save_button=button('Save',self.save); footer.addWidget(self.save_button)
        self.next_button=button('Save & next  →',self.save_next,True); footer.addWidget(self.next_button); middle.addLayout(footer)
        self.splitter.addWidget(center)
        self.right=QScrollArea(); self.right.setWidgetResizable(True); self.right.setMinimumWidth(245)
        inspector=QWidget(); form=QVBoxLayout(inspector); form.setContentsMargins(14,10,14,14); form.setSpacing(9)
        form.addWidget(label('LABELS & ANNOTATIONS','section'))
        labelbar=QHBoxLayout(); self.label_combo=QComboBox(); self.label_combo.setMinimumWidth(100)
        self.label_combo.currentTextChanged.connect(self.label_changed); labelbar.addWidget(self.label_combo,1)
        self.add_label_button=button('+',self.add_label); self.add_label_button.setToolTip('Add a named label'); labelbar.addWidget(self.add_label_button)
        form.addLayout(labelbar)
        tax=QHBoxLayout(); tax.addWidget(button('Rename',self.rename_label)); tax.addWidget(button('Remove',self.remove_label)); form.addLayout(tax)
        form.addWidget(label('IMAGE CLASSIFICATION','section'))
        self.classes=QListWidget(); self.classes.setMinimumHeight(70); self.classes.setMaximumHeight(150)
        self.classes.itemChanged.connect(self.class_changed); form.addWidget(self.classes)
        self.negative=QCheckBox('No target objects in this image'); self.negative.toggled.connect(self.negative_changed); form.addWidget(self.negative)
        form.addWidget(label('OBJECTS','section'))
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
        from PySide6.QtWidgets import QSlider
        form.addWidget(label('OVERLAY OPACITY','section')); self.opacity=QSlider(Qt.Horizontal); self.opacity.setRange(0,70)
        self.opacity.setValue(self.settings.value('opacity',15,type=int)); self.canvas.opacity=self.opacity.value()/100
        self.opacity.valueChanged.connect(self.opacity_changed); form.addWidget(self.opacity)
        hint=label('Polygon: drag a vertex to edit. Double-click an edge to insert. Shift+Delete removes the selected vertex.'); hint.setWordWrap(True); form.addWidget(hint)
        form.addStretch(); form.addWidget(button('Keyboard & preferences',self.preferences))
        self.right.setWidget(inspector); self.splitter.addWidget(self.right); self.splitter.setSizes([260,850,280])
        wrap=QWidget(); layout=QVBoxLayout(wrap); layout.setContentsMargins(12,12,12,12); layout.addWidget(self.splitter)
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
        add(file,'Import annotations…',self.import_annotation_dialog); file.addSeparator()
        add(file,'Save',self.save,'save'); add(file,'Save & next',self.save_next,'save_next')
        add(file,'Export…',self.export_dialog); add(file,'Backup project…',self.backup_dialog)
        add(file,'Restore backup…',self.restore_dialog); add(file,'Relink current image…',self.relink_dialog)
        add(file,'Project tasks…',self.task_settings)
        edit=self.menuBar().addMenu('Edit')
        for key,text,slot in [('undo','Undo',self.undo),('redo','Redo',self.redo),('duplicate','Duplicate',self.duplicate),
                              ('delete','Delete annotation',self.delete_selected),('redraw','Redraw',self.canvas.redraw),
                              ('vertex','Delete polygon vertex',self.canvas.delete_vertex),('cancel','Cancel drawing',self.canvas.cancel),
                              ('finish','Finish polygon',self.canvas.finish_polygon)]: add(edit,text,slot,key)
        view=self.menuBar().addMenu('View')
        add(view,'Fit image',self.canvas.fit,'fit'); add(view,'Focus mode',self.toggle_focus,'focus')
        add(view,'Toggle light / dark',self.toggle_theme); add(view,'Analysis',self.show_analysis)
        add(view,'Previous image',lambda:self.navigate(-1),'previous'); add(view,'Next image',lambda:self.navigate(1),'next')
        for mode in ('select','box','polygon'): add(view,mode.title()+' tool',lambda checked=False,m=mode:self.set_tool(m),mode)
        helpmenu=self.menuBar().addMenu('Help'); add(helpmenu,'Keyboard & preferences',self.preferences)
        add(helpmenu,'About Lannotex',lambda:QMessageBox.information(self,'Lannotex Desktop','Lannotex Desktop 0.0.2\nLocal image annotation. No login, telemetry or uploads.\n\nDisplay previews are capped at 2560 px. Geometry uses original dimensions.'))
        self.update_action_labels()

    def update_action_labels(self):
        for key,(action,text,_) in self.actions.items(): action.setText(text+'\t'+self.bindings.get(key,''))

    def eventFilter(self, obj, event):
        if event.type()!=QEvent.KeyPress or QApplication.activeWindow()!=self: return super().eventFilter(obj,event)
        seq=QKeySequence(event.key() | event.modifiers().value).toString()
        typing=isinstance(QApplication.focusWidget(),(QLineEdit,QTextEdit,QAbstractSpinBox,QComboBox,QKeySequenceEdit))
        for key,binding in self.bindings.items():
            if seq != QKeySequence(binding).toString(): continue
            if typing and key not in ('save','save_next'): return False
            if key in self.actions:
                self.actions[key][2](); return True
        if not typing and event.key() in (Qt.Key_Left,Qt.Key_Right,Qt.Key_Up,Qt.Key_Down) and event.modifiers() in (Qt.NoModifier,Qt.ShiftModifier):
            self.nudge(event.key(), .01 if event.modifiers()==Qt.ShiftModifier else .001); return True
        return super().eventFilter(obj,event)

    def notice(self, message): self.status.setText(message)

    def fail(self, title, error):
        self.notice(f'{title}: {error}')
        QMessageBox.warning(self,title,str(error))

    def set_save_state(self, text):
        self.save_badge.setText(text)
        self.setWindowTitle(f"{'● ' if self.dirty else ''}Lannotex Desktop · {self.project.root.name if self.project else '0.0.2'}")

    def refresh_controls(self):
        opened=self.project is not None; ready=opened and self.current is not None and not self.loading and self.canvas.image is not None
        for b in (self.import_button,self.files_button,self.analysis_button,self.export_button,self.add_label_button): b.setEnabled(opened and self.job is None)
        for b in (self.save_button,self.next_button,self.negative,self.classes,self.annotation_list): b.setEnabled(ready)
        tasks=self.project.setting('tasks',['box','polygon','classification']) if opened else []
        for mode,b in self.tool_buttons.items(): b.setEnabled(ready and (mode=='select' or mode in tasks))
        self.classes.setEnabled(ready and 'classification' in tasks)
        self.undo_button.setEnabled(ready and bool(self.document.undo_stack)); self.redo_button.setEnabled(ready and bool(self.document.redo_stack))
        selected=ready and self.canvas.selection is not None
        for b in (self.duplicate_button,self.redraw_button,self.delete_button): b.setEnabled(selected)

    def new_project(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose a new project folder')
        if not folder: return
        if (Path(folder)/'project.sqlite3').exists(): self.load_project(folder); return
        if self.load_project(folder,create=True): self.task_settings()

    def open_project(self):
        folder=QFileDialog.getExistingDirectory(self,'Open project folder',self.settings.value('last_project',''))
        if folder: self.load_project(folder)

    def load_project(self, folder, create=False):
        if self.job: self.notice('Finish or cancel the background job before switching projects.'); return False
        if not self.save(): return False
        try: next_project=Project(folder,create=create)
        except Exception as error: self.fail('Cannot open project',error); return False
        self.timer.stop(); self.token+=1
        if self.project: self.project.close()
        self.project=next_project; self.current=None; self.document=Document(); self.dirty=False; self.loading=False
        self.canvas.set_image(None); self.canvas.set_annotations([])
        self.project_title.setText(self.project.root.name); self.project_title.setToolTip(str(self.project.root))
        self.settings.setValue('last_project',str(self.project.root))
        self.refresh_labels(); self.refresh_images(); self.set_save_state('Saved'); self.refresh_controls()
        self.notice('Project open. Add labels, import images, and start annotating.')
        return True

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
        if self.current and record['id']==self.current['id']: return
        if not self.save():
            self.images.selectionModel().blockSignals(True); self.images.setCurrentIndex(previous); self.images.selectionModel().blockSignals(False); return
        self.canvas.cancel(); self.timer.stop(); self.token+=1; self.current=dict(record)
        annotations,negative,recovered=self.project.load_state(record['id'])
        self.document=Document(annotations,negative); self.dirty=recovered; self.loading=True
        self.canvas.empty_title='Loading image…'; self.canvas.empty_detail=Path(record['path']).name
        self.canvas.set_image(None); self.canvas.set_annotations(annotations)
        self.image_title.setText(Path(record['path']).name); self.image_title.setToolTip(str(self.project.resolve(record['path'])))
        self.position.setText(f'{index.row()+1:,} / {self.model.total:,}')
        self.set_save_state('Recovered draft' if recovered else 'Saved'); self.sync_inspector(); self.refresh_controls()
        self.loader.request(self.token,self.project.resolve(record['path']))

    @Slot(object,object)
    def image_ready(self,token,image):
        if token!=self.token: return
        self.loading=False; self.canvas.set_image(image); self.refresh_controls()
        self.notice(f"{self.current['width']} × {self.current['height']} px · full-resolution coordinates · local project")
        if self.dirty and self.settings.value('autosave',True,type=bool): self.timer.start(700)

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
        if not self.project or not self.current or not self.dirty: return True
        self.timer.stop(); self.set_save_state('Saving…')
        try:
            self.project.save_annotations(self.current['id'],self.document.annotations,self.document.negative)
        except Exception as error:
            self.set_save_state('Save failed · retry'); self.notice(f'Save failed: {error}. Your edits are still open.'); return False
        self.dirty=False; self.set_save_state('Saved'); self.model.invalidate(); return True

    def commit(self,annotations,negative=False):
        if not self.current or self.loading or self.canvas.image is None: return
        errors=validate_all(annotations,set(self.canvas.colors),negative)
        if errors: self.notice(errors[0]); return
        if self.document.change(annotations,negative): self.document_changed()

    def document_changed(self):
        self.dirty=True
        self.canvas.set_annotations(self.document.annotations)
        self.sync_inspector(); self.refresh_controls(); self.set_save_state('Unsaved')
        try: self.project.save_draft(self.current['id'],self.document.annotations,self.document.negative)
        except Exception as error:
            self.set_save_state('Draft write failed'); self.notice(f'Keep this window open: {error}')
        if self.settings.value('autosave',True,type=bool): self.timer.start(700)

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
        self.canvas.label=self.label_combo.currentText(); self.guard=False; self.sync_inspector()

    def add_label(self):
        if not self.project or self.job: return
        name,ok=QInputDialog.getText(self,'Add label','Label name')
        if ok and name.strip():
            try: self.project.add_label(name,COLORS[len(self.canvas.colors)%len(COLORS)])
            except Exception as e: self.fail('Cannot add label',e); return
            self.refresh_labels(); self.label_combo.setCurrentText(name.strip())

    def rename_label(self):
        if not self.project or self.job or not self.label_combo.currentText(): return
        old=self.label_combo.currentText(); new,ok=QInputDialog.getText(self,'Rename label','New name · updates every annotation',text=old)
        if not ok or new.strip()==old: return
        if not self.save(): return
        try: self.project.rename_label(old,new)
        except Exception as e: self.fail('Cannot rename label',e); return
        if self.current:
            anns,negative,_=self.project.load_state(self.current['id']); self.document=Document(anns,negative); self.canvas.set_annotations(anns)
        self.refresh_labels(); self.refresh_controls()

    def remove_label(self):
        if not self.project or self.job or not self.save(): return
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
        root=self.project.root
        self.start_job('import',lambda cancel,progress:import_images(root,paths,cancel,progress))

    def import_annotation_dialog(self):
        if not self.project or self.job: return
        path,_=QFileDialog.getOpenFileName(self,'Import Labelme JSON or native annotations.jsonl','','Annotations (*.json *.jsonl)')
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
            if result.get('errors'): self.show_report('Import summary',text+'\n\n'+'\n'.join(result['errors']))
            self.notice(text)
        elif self.job_kind=='export':
            self.show_report('Export summary',f"Included: {result['included']}\nUnlabeled included: {result['unlabeled']}\nSkipped images: {result['skipped']}\nAnnotations unsupported by this format: {result['unsupported_annotations']}\nCancelled: {result.get('cancelled',False)}\n\n{result['path']}\n\n"+'\n'.join(result['errors']))
        elif self.job_kind=='analysis': self.analysis_result(result)
        elif self.job_kind=='backup': self.notice(f'Backup saved: {result}')

    @Slot(str)
    def job_error(self,error): self.fail('Background operation failed',error)

    @Slot()
    def job_finished(self):
        self.job=None; self.job_kind=''; self.progress.hide(); self.cancel_button.hide(); self.refresh_controls()

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
        if not self.project: return
        dialog=QDialog(self); dialog.setWindowTitle('Project tasks'); layout=QVBoxLayout(dialog)
        layout.addWidget(label('Enable any combination of tasks. Existing annotations are retained.'))
        tasks=self.project.setting('tasks',['box','polygon','classification']); boxes={}
        for key,title in [('box','Bounding-box detection'),('polygon','Polygon segmentation'),('classification','Multi-label classification')]:
            box=QCheckBox(title); box.setChecked(key in tasks); boxes[key]=box; layout.addWidget(box)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec()==QDialog.Accepted:
            self.project.set_setting('tasks',[key for key,box in boxes.items() if box.isChecked()]); self.set_tool('select'); self.refresh_controls()

    def toggle_focus(self):
        self.focus_mode=not self.focus_mode; self.left.setVisible(not self.focus_mode); self.right.setVisible(not self.focus_mode)

    def toggle_theme(self):
        self.dark=not self.dark; self.settings.setValue('dark',self.dark); apply_theme(QApplication.instance(),self.dark)

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
        if self.job or self.loader.active:
            self.cancel_job(); self.loader.pending=None
            self.notice('Finishing the active file operation. Close again when it has stopped.'); event.ignore(); return
        if not self.save():
            self.fail('Cannot close safely','Saving failed. Your edits remain in this window. Resolve disk space or permissions and try Save again.'); event.ignore(); return
        self.settings.setValue('geometry',self.saveGeometry()); self.settings.setValue('splitter',self.splitter.saveState())
        if self.project: self.project.close(); self.project=None
        QApplication.instance().removeEventFilter(self); event.accept()


def main():
    app=QApplication(sys.argv); app.setOrganizationName('Lannotex'); app.setApplicationName('Lannotex Desktop')
    app.setStyle('Fusion'); app.setFont(QFont('Segoe UI',10))
    window=Main(); window.show()
    # A bounded test must actually enter the Qt event loop and report completion.
    if '--smoke-test' in sys.argv:
        def done():
            target=os.environ.get('LANNOTEX_SMOKE_RESULT')
            if target: atomic_text(target,json.dumps({'version':'0.0.2','window_visible':window.isVisible(),'qt_event_loop':True}))
            window.close()
        QTimer.singleShot(300,done)
    raise SystemExit(app.exec())
