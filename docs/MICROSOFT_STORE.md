# Microsoft Store preparation

Lannotex targets the Microsoft Store as a v0.3 packaging milestone. The gate for a
store submission is:

1. Build the PyInstaller directory artifact (`dist\Lannotex\Lannotex.exe`) on a clean
   Windows machine using `scripts\build_windows.ps1`.
2. Run the Windows App Certification Kit and fix any failures.
3. Create an MSIX wrapper and review capabilities for the optional team host/client.
   Solo operation must remain usable offline; do not silently enable public hosting.
4. Confirm `LICENSES\THIRD_PARTY_NOTICES.md` is included and matches the bundled
   dependency licenses.
5. Smoke-test the packaged app on a clean Windows VM.

Do **not** package project data inside the installation directory — projects live in
user-chosen folders and must survive app updates.
