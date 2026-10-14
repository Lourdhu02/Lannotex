"""Local editable exports. No company approval or release status is implied."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import tempfile
import uuid
from .domain import Annotation, polygon_area, validate_all
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
            'lannotex':{'version':'0.0.2','no_targets':negative,'editable':True}}


def labelme(path, image_path, width, height, annotations):
    atomic_text(path,json.dumps(labelme_data(image_path,width,height,annotations),indent=2))


def parse_labelme(data):
    w,h = data['imageWidth'],data['imageHeight']
    if not isinstance(w,(int,float)) or not isinstance(h,(int,float)) or w<=0 or h<=0:
        raise ValueError('Labelme image dimensions must be positive')
    annotations = []
    for shape in data.get('shapes',[]):
        pts = [[x/w,y/h] for x,y in shape['points']]
        kind = shape.get('shape_type','polygon')
        if kind == 'rectangle' and len(pts)==2:
            geometry = [min(pts[0][0],pts[1][0]),min(pts[0][1],pts[1][1]),max(pts[0][0],pts[1][0]),max(pts[0][1],pts[1][1])]
            kind = 'box'
        elif kind == 'polygon': geometry = pts
        else: raise ValueError(f'Unsupported Labelme shape: {kind}')
        annotations.append(Annotation(shape['label'],kind,geometry,shape.get('lannotex_id') or shape.get('labelreview_id') or str(uuid.uuid4())))
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


def export_project(root, destination, format_name, cancel, progress):
    """Stream a consistent DB snapshot; publish the completed directory by rename."""
    project = Project(root,create=False)
    project.conn.execute('BEGIN')
    destination = Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='Lannotex-partial-',dir=destination))
    summary = {'included':0,'unlabeled':0,'skipped':0,'unsupported_annotations':0,'errors':[], 'format':format_name}
    try:
        labels = [r['name'] for r in project.labels()]
        atomic_text(output/'classes.json',json.dumps(labels,indent=2))
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
                summary['included'] += 1
                if row['status']=='new': summary['unlabeled'] += 1
                name = f"{row['id']:08d}_{Path(row['path']).stem}"
                source = str(project.resolve(row['path']))
                image = {'id':row['id'],'file_name':source,'width':row['width'],'height':row['height']}
                ims.write(json.dumps(image)+'\n')
                if format_name == 'Labelme JSON':
                    atomic_text(output/(name+'.json'),json.dumps(labelme_data(source,row['width'],row['height'],annotations,negative),indent=2))
                elif format_name == 'YOLO boxes':
                    lines = [yolo_line(a,labels.index(a.label)) for a in annotations if a.kind=='box']
                    atomic_text(output/(name+'.txt'),'\n'.join(lines)+ ('\n' if lines else ''))
                    summary['unsupported_annotations'] += sum(a.kind!='box' for a in annotations)
                elif format_name == 'COCO JSON':
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
        atomic_text(output/'manifest.json',json.dumps({'version':'0.0.1','format_version':1,'editable_local_export':True,'image_policy':'Referenced, not copied','summary':summary},indent=2))
        if not summary.get('cancelled'):
            final = destination/('Lannotex-export-'+uuid.uuid4().hex[:8]); output.rename(final); output=final
        summary['path'] = str(output)
        return summary
    finally:
        project.conn.rollback(); project.close()


def import_annotations(root, source, cancel, progress):
    """Native JSONL or Labelme; existing labeled images are never overwritten."""
    from PIL import Image
    project = Project(root,create=False)
    source = Path(source)
    count,errors = 0,[]
    try:
        def records():
            if source.suffix=='.jsonl':
                with source.open(encoding='utf-8') as stream:
                    for line in stream:
                        record=json.loads(line)
                        yield record['image']['file_name'], record['image']['width'], record['image']['height'], [Annotation.from_dict(a) for a in record['annotations']], record['status']=='empty'
            else:
                files = sorted(source.glob('*.json')) if source.is_dir() else [source]
                for file in files:
                    data = json.loads(file.read_text(encoding='utf-8'))
                    if 'shapes' not in data: continue
                    anns,neg = parse_labelme(data)
                    yield str((file.parent/data['imagePath']).resolve()),data['imageWidth'],data['imageHeight'],anns,neg
        for path,w,h,annotations,negative in records():
            if cancel.is_set(): break
            try:
                with Image.open(path) as image:
                    size=image.size
                    if image.getexif().get(274,1) in (5,6,7,8): size=size[::-1]
                    if size != (w,h): raise ValueError('Source dimensions differ from annotation metadata')
                errors_found=validate_all(annotations,{a.label for a in annotations},negative)
                if errors_found: raise ValueError('; '.join(errors_found))
                reference=project.reference(path)
                existing=project.conn.execute('SELECT * FROM images WHERE path=?',(reference,)).fetchone()
                if existing and (existing['status']!='new' or project.conn.execute('SELECT 1 FROM drafts WHERE image_id=?',(existing['id'],)).fetchone()):
                    raise ValueError('Image already has annotations or a draft; skipped')
                for label in {a.label for a in annotations}:
                    if label not in {r['name'] for r in project.labels()}: project.add_label(label)
                ident=project.add_image(path,w,h)
                project.save_annotations(ident,annotations,negative)
                count+=1; progress(count,f'Imported annotations for {count} images')
            except Exception as e:
                if len(errors)<100: errors.append(f'{path}: {e}')
        return {'added':count,'errors':errors,'cancelled':cancel.is_set()}
    finally: project.close()


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
