"""Wait for the GUI executable and require its event-loop completion receipt."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    exe=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='lannotex-smoke-') as folder:
        result=Path(folder)/'receipt.json'
        env=os.environ.copy(); env['LANNOTEX_SMOKE_RESULT']=str(result)
        # The executable must find bundled dependencies without PYTHONPATH.
        env.pop('PYTHONPATH',None); env.pop('QT_QPA_PLATFORM',None)
        started=time.perf_counter()
        completed=subprocess.run([str(exe),'--smoke-test'],env=env,cwd=folder,timeout=30)
        if completed.returncode!=0: raise SystemExit(f'Executable failed: {completed.returncode}')
        if not result.is_file(): raise SystemExit('Executable exited without entering/completing the UI event loop')
        receipt=json.loads(result.read_text())
        if not receipt.get('window_visible') or not receipt.get('qt_event_loop'): raise SystemExit('UI did not start successfully')
        print(json.dumps({'receipt':receipt,'process_to_exit_seconds':round(time.perf_counter()-started,3)}))


if __name__=='__main__': main()
