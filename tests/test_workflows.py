import json
import threading
from pathlib import Path
from PIL import Image
import pytest
from lannotex.domain import Annotation
from lannotex.exporters import export_project, import_annotations
from lannotex.storage import Project
from lannotex.workers import import_images


def test_labelme_folder_import_is_recursive_and_survives_bad_files(tmp_path):
    source=tmp_path/'labelme'; (source/'batch2').mkdir(parents=True)
    for folder,name in [(source,'a.png'),(source/'batch2','b.png')]:
        Image.new('RGB',(100,50)).save(folder/name)
        shapes=[{'label':'cat','shape_type':'rectangle','points':[[10,10],[40,30]]},{'label':'eye','shape_type':'point','points':[[5,5]]}]
        (folder/(Path(name).stem+'.json')).write_text(json.dumps({'imagePath':name,'imageWidth':100,'imageHeight':50,'shapes':shapes,'flags':{}}))
    (source/'broken.json').write_text('{ not json')
    root=tmp_path/'project'; Project(root).close()
    result=import_annotations(root,source,threading.Event(),lambda *a:None)
    assert result['added']==2
    assert len(result['errors'])==1 and 'broken.json' in result['errors'][0]
    assert result['skipped_shapes']=={'point shapes (not supported yet)':2}
    p=Project(root,create=False)
    assert sorted(a.kind for i in p.images() for a in p.load_annotations(i['id']))==['box','box']
    p.close()


def test_folder_import_export_all_formats_and_native_roundtrip(tmp_path):
    source=tmp_path/'images'; source.mkdir()
    Image.new('RGB',(200,100),'white').save(source/'image.png')
    (source/'broken.jpg').write_bytes(b'not an image')
    root=tmp_path/'project'; p=Project(root); p.add_label('cat'); p.close()
    result=import_images(root,[source],threading.Event(),lambda *args:None)
    assert result['added']==1 and len(result['errors'])==1
    p=Project(root,create=False); ident=p.images()[0]['id']
    annotations=[Annotation('cat','box',[.1,.2,.5,.6]),Annotation('cat','polygon',[[0,0],[1,0],[1,1]]),Annotation('cat','classification')]
    p.save_annotations(ident,annotations); p.close()
    for fmt in ['YOLO boxes','COCO JSON','Classification CSV','Labelme JSON','Native JSONL']:
        result=export_project(root,tmp_path/'exports',fmt,threading.Event(),lambda *args:None)
        assert result['included']==1 and not result['errors']
        folder=Path(result['path'])
        if fmt=='COCO JSON':
            coco=json.loads((folder/'coco.json').read_text())
            assert coco['annotations'][1]['area']==10000
            assert len({a['id'] for a in coco['annotations']})==2
        if fmt=='Native JSONL':
            restored=tmp_path/'restored'; Project(restored).close()
            imported=import_annotations(restored,folder/'annotations.jsonl',threading.Event(),lambda *args:None)
            assert imported['added']==1 and not imported['errors']
            p=Project(restored,create=False)
            assert [a.to_dict() for a in p.load_annotations(p.images()[0]['id'])]==[a.to_dict() for a in annotations]
            p.close()


def test_failed_transaction_preserves_previous_annotations(tmp_path):
    p=Project(tmp_path); p.add_label('cat'); first=p.add_image(tmp_path/'one.png',10,10); second=p.add_image(tmp_path/'two.png',10,10)
    a=Annotation('cat','box',[0,0,1,1]); b=Annotation('cat','classification')
    p.save_annotations(first,[a]); p.save_annotations(second,[b])
    with pytest.raises(Exception): p.save_annotations(first,[b])  # ID belongs to another image.
    assert p.load_annotations(first)[0].id==a.id
    p.close()


def test_backup_restores_external_image_reference_and_draft(tmp_path):
    root=tmp_path/'old'/'project'; p=Project(root); p.add_label('cat')
    path=tmp_path/'image.png'; Image.new('RGB',(20,20)).save(path); ident=p.add_image(path,20,20)
    a=Annotation('cat','box',[0,0,1,1]); p.save_draft(ident,[a]); p.backup(tmp_path/'copy.sqlite3'); p.close()
    restored=Project.restore(tmp_path/'copy.sqlite3',tmp_path/'another'/'folder')
    assert restored.resolve(restored.image(ident)['path'])==path
    assert restored.load_state(ident)[2] and restored.load_state(ident)[0][0].id==a.id
    restored.close()
