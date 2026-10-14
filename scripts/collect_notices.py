"""Copy actual installed distribution license texts alongside the portable build."""
import importlib.metadata
from pathlib import Path
import shutil
import sys


def main():
    target=Path(sys.argv[1]); target.mkdir(parents=True,exist_ok=True)
    for package in ['PySide6','PySide6-Essentials','PySide6-Addons','shiboken6','Pillow','pyinstaller']:
        dist=importlib.metadata.distribution(package)
        for file in dist.files or []:
            if any(word in str(file).lower() for word in ('license','copying','notice')) and not str(file).endswith(('.py','.pyc','.dll','.pyd')):
                source=Path(dist.locate_file(file))
                if source.is_file():
                    destination=target/package/str(file).replace('..','_')
                    destination.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,destination)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.is_file(): shutil.copyfile(python_license,target/'PYTHON-LICENSE.txt')
    shutil.copyfile('LICENSE',target/'LANNOTEX-LICENSE.txt')
    for source in Path('LICENSES').glob('*.txt'):
        shutil.copyfile(source,target/source.name)


if __name__=='__main__': main()
