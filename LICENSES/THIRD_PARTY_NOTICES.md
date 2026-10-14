Lannotex Desktop bundles software under the licenses of Python, Qt/PySide6, Pillow, and PyInstaller.
The Windows build script copies the actual installed dependency license texts into
the adjacent `licenses/` folder, including Python and this project's MIT license.
Qt/PySide6 remains dynamically linked; retain the `_internal` libraries and notices
when redistributing. Qt/PySide6 and Shiboken include LGPL/GPL/commercial licensing
options; consult their bundled texts for your distribution obligations. Pillow and
Python include their own license notices. PyInstaller's bootloader exception is
included with its license. This notice is not a substitute for those full texts.

The LGPL-3.0-only, GPL-3.0-only and Qt-GPL-exception-1.0 texts are copied verbatim
from https://github.com/qt/qtbase/tree/v6.8.3/LICENSES and shipped with the build.
