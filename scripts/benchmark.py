"""Reproducible synthetic benchmarks; fixtures only in a temporary directory."""
import ctypes
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import tempfile
import threading
import time
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from lannotex.app import Main
from lannotex.models import ImageListModel
from lannotex.storage import Project
from lannotex.workers import decode, import_images


def memory_mb():
    if os.name!='nt': return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    counter=Counters(); counter.cb=ctypes.sizeof(counter)
    kernel=ctypes.WinDLL('kernel32'); kernel.GetCurrentProcess.restype=wintypes.HANDLE
    query=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    query.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    query.restype=wintypes.BOOL
    if not query(kernel.GetCurrentProcess(),ctypes.byref(counter),counter.cb): return None
    return round(counter.WorkingSetSize/1024**2,2)


def main():
    app=QApplication([])
    with tempfile.TemporaryDirectory(prefix='lannotex-benchmark-') as tmp:
        root=Path(tmp); QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(root/'settings'))
        started=time.perf_counter(); window=Main(); window.show(); app.processEvents(); startup=time.perf_counter()-started
        sources=root/'images'; sources.mkdir()
        im=Image.effect_noise((1920,1080),70).convert('RGB'); im.save(sources/'0000.jpg',quality=85)
        for i in range(1,300): shutil.copyfile(sources/'0000.jpg',sources/f'{i:04d}.jpg')
        project=Project(root/'project'); project.close()
        result=import_images(root/'project',[sources],threading.Event(),lambda *a:None)
        project=Project(root/'project',create=False)
        before=memory_mb(); started=time.perf_counter()
        project.add_batch([(f'metadata-only/{i:08d}.jpg',1920,1080) for i in range(100000)])
        model=ImageListModel(); model.refresh(project)
        for row in range(0,model.total,17): model.record(row)
        metadata_seconds=time.perf_counter()-started; after=memory_mb()
        decode_times=[]
        for i in range(30):
            start=time.perf_counter(); image=decode(sources/f'{i:04d}.jpg'); decode_times.append((time.perf_counter()-start)*1000)
            assert image.width()==1920
        output={'platform':platform.platform(),'python':platform.python_version(),'cpu':platform.processor(),
            'ui_construction_to_paint_ms':round(startup*1000,2), 'import_images':result['scanned'],
            'import_total_bytes':sum(p.stat().st_size for p in sources.iterdir()),
            'import_seconds':round(result['seconds'],3),'import_images_per_second':round(result['added']/result['seconds'],2),
            'decode_1080p_median_ms':round(statistics.median(decode_times),2),'decode_1080p_p95_ms':round(sorted(decode_times)[28],2),
            'metadata_rows':model.total,'metadata_insert_and_scroll_seconds':round(metadata_seconds,3),
            'metadata_cache_pages':len(model.pages),'metadata_cache_records':sum(len(p) for p in model.pages.values()),
            'process_working_set_before_metadata_mb':before,'process_working_set_after_metadata_mb':after,
            'notes':'Synthetic fixtures. UI timing excludes Python/Qt imports. Decode is worker operation latency, not full image-switch latency. No 10GB real dataset or cross-machine network benchmark.'}
        project.close(); window.close()
        print(json.dumps(output,indent=2))


if __name__=='__main__': main()
