"""Local editable exports. No company approval or release status is implied."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from collections import Counter
import hashlib
import math
from . import __version__
from .domain import Annotation, polygon_area, validate, validate_all
from .storage import Project, atomic_text


def labelme_data(image_path, width, height, annotations, negative=False):
    shapes = []
    for a in annotations:
        if a.kind == 'classification': continue
        if a.kind == 'box':
            x,y,r,b = a.geometry
            points = [[x*width,y*height],[r*width,b*height]]
        else: points = [[x*width,y*height] for x,y in a.geometry]
        shapes.append({'label':a.label,'points':points,'shape_type':'rectangle' if a.kind=='box' else 'polygon',
                       'flags':{},'group_id':None,'lannotex_id':a.id})
    return {'version':'5.5.0','imageData':None,'imagePath':image_path,'imageWidth':width,'imageHeight':height,
            'flags':{a.label:True for a in annotations if a.kind=='classification'}, 'shapes':shapes,
            'lannotex':{'version':__version__,'no_targets':negative,'editable':True}}


def labelme(path, image_path, width, height, annotations):
    atomic_text(path,json.dumps(labelme_data(image_path,width,height,annotations),indent=2))


def circle_polygon(center, edge, w, h, sides=32):
    """LabelMe circles are (center, point on rim) in pixels; approximate in pixel space, then normalize."""
    radius = math.dist(center, edge)
    points = []
    for i in range(sides):
        t = 2*math.pi*i/sides
        p = [min(1., max(0., (center[0]+radius*math.cos(t))/w)), min(1., max(0., (center[1]+radius*math.sin(t))/h))]
        if not points or p != points[-1]: points.append(p)
    if len(points) > 1 and points[0] == points[-1]: points.pop()
    return points


def parse_labelme(data, skipped=None):
    """Return (annotations, negative). Shapes Lannotex cannot represent, or invalid ones, are dropped
    and counted in `skipped` (a Counter) instead of rejecting the whole file."""
    w,h = data['imageWidth'],data['imageHeight']
    if not isinstance(w,(int,float)) or not isinstance(h,(int,float)) or w<=0 or h<=0:
        raise ValueError('Labelme image dimensions must be positive')
    skipped = Counter() if skipped is None else skipped
    annotations = []
    for shape in data.get('shapes',[]):
        raw = shape.get('points') or []
        pts = [[x/w,y/h] for x,y in raw]
        kind = shape.get('shape_type') or 'polygon'
        if kind == 'rectangle' and len(pts)==2:
            geometry = [min(pts[0][0],pts[1][0]),min(pts[0][1],pts[1][1]),max(pts[0][0],pts[1][0]),max(pts[0][1],pts[1][1])]
            kind = 'box'
        elif kind in ('polygon', 'rotation'): geometry = pts; kind = 'polygon'
        elif kind == 'circle' and len(raw)==2: geometry = circle_polygon(raw[0], raw[1], w, h); kind = 'polygon'
        else:
            skipped[f'{kind} shapes (not supported yet)'] += 1; continue
        a = Annotation(shape['label'],kind,geometry,shape.get('lannotex_id') or shape.get('labelreview_id') or str(uuid.uuid4()))
        problems = validate(a, {a.label})
        if problems: skipped[f'{kind}: {problems[0].lower()}'] += 1; continue
        annotations.append(a)
    for label,enabled in data.get('flags',{}).items():
        if enabled is True: annotations.append(Annotation(label,'classification'))
    negative = bool(data.get('lannotex',{}).get('no_targets',False) or data.get('labelreview',{}).get('no_targets',False))
    errors = validate_all(annotations,{a.label for a in annotations},negative)
    if errors: raise ValueError('; '.join(errors))
    return annotations, negative


def yolo_line(a, class_id):
    if a.kind != 'box': return None
    x,y,r,b = a.geometry
    return f'{class_id} {(x+r)/2:.6f} {(y+b)/2:.6f} {r-x:.6f} {b-y:.6f}'


def coco_record(image, annotations, labels):
    output = []
    w,h = image['width'],image['height']
    for a in annotations:
        if a.kind not in ('box','polygon'): continue
        if a.kind == 'box':
            x,y,r,b = a.geometry
            bbox = [x*w,y*h,(r-x)*w,(b-y)*h]
            segmentation = []; area = bbox[2]*bbox[3]
        else:
            xs,ys = [p[0]*w for p in a.geometry],[p[1]*h for p in a.geometry]
            bbox = [min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)]
            segmentation = [[n for p in a.geometry for n in (p[0]*w,p[1]*h)]]
            area = polygon_area(a.geometry)*w*h
        output.append({'id':len(output)+1,'image_id':image['id'],'category_id':labels.index(a.label)+1,
                       'bbox':bbox,'area':area,'segmentation':segmentation,'iscrowd':0})
    return {'images':[image],'categories':[{'id':i+1,'name':s} for i,s in enumerate(labels)],'annotations':output}


def link_or_copy(source, target):
    try: os.link(source, target)
    except OSError: shutil.copy2(source, target)


EXPORT_FORMATS = ['Labelme JSON', 'YOLO boxes', 'YOLO segments', 'Pascal VOC', 'COCO JSON',
                  'Classification CSV', 'Native JSONL']
SPLITS = ('train', 'val', 'test')
DEFAULT_RATIOS = (.8, .1, .1)


def split_for(image_id, seed, ratios=DEFAULT_RATIOS):
    """Deterministic per-image split: the same image and seed always land in the same set,
    whatever order the export visits them in."""
    digest = hashlib.sha1(f'{seed}:{image_id}'.encode()).digest()
    point = int.from_bytes(digest[:8], 'big') / float(1 << 64)
    edge = 0.
    for name, share in zip(SPLITS, ratios):
        edge += share
        if point < edge: return name
    return SPLITS[0]


def yolo_data_yaml(root, labels, split):
    names = '\n'.join(f'  {i}: {json.dumps(name)}' for i, name in enumerate(labels))
    task = '# Train:  yolo detect train data=data.yaml model=yolo11n.pt\n'
    header = ('# Ultralytics YOLO dataset exported by Lannotex.\n' + task +
              "# Update 'path' if you move this folder.\n")
    if split:
        sets = ''.join(f'{name}: images/{name}\n' for name in SPLITS)
    else:
        header += '# Every image is in one set; export with a split for a real evaluation.\n'
        sets = 'train: images\nval: images\n'
    return f'{header}path: {json.dumps(str(root))}\n{sets}names:\n{names}\n'


def voc_xml(file_name, width, height, annotations, folder='JPEGImages'):
    """Pascal VOC has only axis-aligned boxes, so a polygon is written as its extent."""
    def escape(text):
        return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                .replace('"', '&quot;'))

    parts = [f'<annotation>\n  <folder>{escape(folder)}</folder>\n  <filename>{escape(file_name)}</filename>',
             f'  <size>\n    <width>{width}</width>\n    <height>{height}</height>\n    <depth>3</depth>\n  </size>',
             '  <segmented>0</segmented>']
    for a in annotations:
        if a.kind == 'box':
            x0, y0, x1, y1 = a.geometry
        elif a.kind == 'polygon':
            xs = [p[0] for p in a.geometry]; ys = [p[1] for p in a.geometry]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        else:
            continue
        box = (max(1, round(x0*width)+1), max(1, round(y0*height)+1),
               min(width, round(x1*width)), min(height, round(y1*height)))
        parts.append(f'  <object>\n    <name>{escape(a.label)}</name>\n    <pose>Unspecified</pose>\n'
                     f'    <truncated>0</truncated>\n    <difficult>0</difficult>\n'
                     f'    <bndbox>\n      <xmin>{box[0]}</xmin>\n      <ymin>{box[1]}</ymin>\n'
                     f'      <xmax>{box[2]}</xmax>\n      <ymax>{box[3]}</ymax>\n    </bndbox>\n  </object>')
    parts.append('</annotation>\n')
    return '\n'.join(parts)


def yolo_segment_line(a, class_id):
    if a.kind != 'polygon': return None
    coordinates = ' '.join(f'{value:.6f}' for point in a.geometry for value in point)
    return f'{class_id} {coordinates}'


def rebalance(output, members):
    """A random split can leave val empty on a small dataset, which YOLO refuses to train on.
    Move one image over rather than hand back a dataset that cannot be used."""
    for name in ('val', 'test'):
        while not members[name] and len(members['train']) > 1:
            moved = members['train'].pop()
            members[name].append(moved)
            for folder, suffix in (('labels', '.txt'), ('images', None)):
                source = next((p for p in (output/folder/'train').glob(moved+'.*')), None) if suffix is None \
                    else output/folder/'train'/(moved+suffix)
                if source and source.exists(): source.replace(output/folder/name/source.name)


def export_project(root, destination, format_name, cancel, progress, split=False, seed=0):
    """Stream a consistent DB snapshot; publish the completed directory by rename.

    `split` divides a YOLO export into train/val/test; the assignment is derived from each
    image's id and `seed`, so the same project and seed always produce the same split.
    """
    project = Project(root,create=False)
    project.conn.execute('BEGIN')
    destination = Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='Lannotex-partial-',dir=destination))
    summary = {'included':0,'unlabeled':0,'skipped':0,'unsupported_annotations':0,'errors':[], 'format':format_name}
    try:
        labels = [r['name'] for r in project.labels()]
        atomic_text(output/'classes.json',json.dumps(labels,indent=2))
        yolo_seg = format_name == 'YOLO segments'
        yolo = format_name == 'YOLO boxes' or yolo_seg
        coco = format_name == 'COCO JSON'
        voc = format_name == 'Pascal VOC'
        split = bool(split) and yolo
        if yolo:
            for folder in ('images','labels'):
                for part in (SPLITS if split else ('',)): (output/folder/part).mkdir(parents=True)
        if coco: (output/'images').mkdir()
        if voc:
            for folder in ('Annotations','JPEGImages','ImageSets/Main'): (output/folder).mkdir(parents=True)
        members = {name: [] for name in SPLITS}
        # Spool COCO arrays to disk, rather than keeping all annotations in RAM.
        with (output/'images.jsonl').open('w',encoding='utf-8') as ims, (output/'annotations.jsonl').open('w',encoding='utf-8') as anns, (output/'classification.csv').open('w',encoding='utf-8',newline='') as csvfile:
            writer = csv.writer(csvfile); writer.writerow(['image_id','image_path','status',*labels])
            total = project.query(count=True); aid = 0
            for position,row in enumerate(project.conn.execute('SELECT * FROM images ORDER BY id'),1):
                if cancel.is_set():
                    summary['cancelled'] = True; break
                annotations = project.load_annotations(row['id'])
                negative = row['status']=='empty'
                errors = validate_all(annotations,set(labels),negative)
                if row['width']<=0 or row['height']<=0: errors.append('Invalid image dimensions')
                if not project.resolve(row['path']).is_file(): errors.append('Missing source image')
                if project.conn.execute('SELECT 1 FROM drafts WHERE image_id=?',(row['id'],)).fetchone(): errors.append('Uncommitted recovery draft')
                if errors:
                    summary['skipped'] += 1
                    if len(summary['errors'])<100: summary['errors'].append(f"{row['path']}: {'; '.join(errors)}")
                    continue
                if yolo and row['status']=='new':
                    # YOLO reads an empty label file as "no objects"; never-annotated images would become false negatives.
                    summary['unlabeled'] += 1
                    continue
                summary['included'] += 1
                if row['status']=='new': summary['unlabeled'] += 1
                name = f"{row['id']:08d}_{Path(row['path']).stem}"
                source_path = project.resolve(row['path'])
                source = str(source_path)
                suffix = source_path.suffix.lower()
                image = {'id':row['id'],'file_name':source,'width':row['width'],'height':row['height']}
                if coco:
                    # COCO file_name is resolved against the dataset's images folder, never absolute.
                    ims.write(json.dumps({**image,'file_name':name+suffix})+'\n')
                    link_or_copy(source_path, output/'images'/(name+suffix))
                else:
                    ims.write(json.dumps(image)+'\n')
                if format_name == 'Labelme JSON':
                    atomic_text(output/(name+'.json'),json.dumps(labelme_data(source,row['width'],row['height'],annotations,negative),indent=2))
                elif yolo:
                    part = split_for(row['id'],seed) if split else ''
                    members[part or 'train'].append(name)
                    if yolo_seg:
                        lines = [yolo_segment_line(a,labels.index(a.label)) for a in annotations if a.kind=='polygon']
                        summary['unsupported_annotations'] += sum(a.kind!='polygon' for a in annotations)
                    else:
                        lines = [yolo_line(a,labels.index(a.label)) for a in annotations if a.kind=='box']
                        summary['unsupported_annotations'] += sum(a.kind!='box' for a in annotations)
                    link_or_copy(source_path, output/'images'/part/(name+suffix))
                    atomic_text(output/'labels'/part/(name+'.txt'),'\n'.join(lines)+ ('\n' if lines else ''))
                elif voc:
                    link_or_copy(source_path, output/'JPEGImages'/(name+suffix))
                    atomic_text(output/'Annotations'/(name+'.xml'),
                                voc_xml(name+suffix,row['width'],row['height'],annotations))
                    members['train'].append(name)
                    summary['unsupported_annotations'] += sum(a.kind=='classification' for a in annotations)
                elif coco:
                    record = coco_record(image,annotations,labels)
                    for ann in record['annotations']:
                        aid += 1; ann['id']=aid; anns.write(json.dumps(ann)+'\n')
                    summary['unsupported_annotations'] += sum(a.kind=='classification' for a in annotations)
                elif format_name == 'Native JSONL':
                    anns.write(json.dumps({'image':image,'status':row['status'],'annotations':[a.to_dict() for a in annotations]})+'\n')
                classes = {a.label for a in annotations if a.kind=='classification'}
                writer.writerow([row['id'],source,row['status'],*[int(label in classes) for label in labels]])
                if format_name=='Classification CSV': summary['unsupported_annotations'] += sum(a.kind!='classification' for a in annotations)
                if position%32==0: progress(round(position/max(1,total)*100),f'Exporting {position:,} / {total:,}')
        if format_name == 'COCO JSON' and not summary.get('cancelled'):
            with (output/'coco.json').open('w',encoding='utf-8') as stream:
                stream.write('{"images":[')
                for filename,sep in [('images.jsonl','],"annotations":['),('annotations.jsonl','],"categories":')]:
                    first = True
                    with (output/filename).open(encoding='utf-8') as lines:
                        for line in lines:
                            if not first: stream.write(',')
                            stream.write(line.strip()); first=False
                    stream.write(sep)
                stream.write(json.dumps([{'id':i+1,'name':s} for i,s in enumerate(labels)])+'}')
        if split and not summary.get('cancelled'):
            rebalance(output, members)
        if voc and not summary.get('cancelled'):
            atomic_text(output/'ImageSets'/'Main'/'default.txt','\n'.join(members['train'])+'\n')
        if split: summary['split'] = {name: len(members[name]) for name in SPLITS}
        copied = yolo or voc or coco
        policy = 'Hard-linked or copied into the export' if copied else 'Referenced, not copied'
        atomic_text(output/'manifest.json',json.dumps({'version':__version__,'format_version':1,'editable_local_export':True,'image_policy':policy,'summary':summary},indent=2))
        if not summary.get('cancelled'):
            final = destination/('Lannotex-export-'+uuid.uuid4().hex[:8]); output.rename(final); output=final
            if yolo: atomic_text(output/'data.yaml', yolo_data_yaml(output.resolve(), labels, split))
        summary['path'] = str(output)
        return summary
    finally:
        project.conn.rollback(); project.close()


def analyze(root, cancel, progress):
    project=Project(root,create=False)
    result={'total':0,'labeled':0,'unlabeled':0,'negative':0,'boxes':0,'polygons':0,'classes':0,'distribution':{},'problems':[]}
    try:
        labels={r['name'] for r in project.labels()}
        result['drafts']=project.conn.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]
        for row in project.conn.execute('SELECT * FROM images'):
            if cancel.is_set(): break
            result['total']+=1
            result[{'new':'unlabeled','done':'labeled','empty':'negative'}[row['status']]]+=1
            annotations=project.load_annotations(row['id'])
            problems=validate_all(annotations,labels,row['status']=='empty')
            if not project.resolve(row['path']).is_file(): problems.append('Missing source image')
            for a in annotations:
                result[{'box':'boxes','polygon':'polygons','classification':'classes'}.get(a.kind,'classes')]+=1
                result['distribution'][a.label]=result['distribution'].get(a.label,0)+1
            if problems and len(result['problems'])<200: result['problems'].append(f"{row['path']}: {'; '.join(problems)}")
        return result
    finally: project.close()
