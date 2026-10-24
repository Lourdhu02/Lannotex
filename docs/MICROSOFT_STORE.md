# Packaging for the Microsoft Store

Notes for whoever packages a release. Nothing here changes how Lannotex behaves; it is about
getting a signed, installable app in front of people who will never run `pip`.

## Why the Store first

Microsoft **signs Store apps for you**. That removes the SmartScreen warning without buying a
certificate, and brings automatic updates. Individual developer registration is free, so for a
solo maintainer this is the cheapest route to a real, warning-free install.

Signing outside the Store needs a traditional OV or EV certificate, which costs a few hundred
dollars a year and usually requires a registered business. Azure Trusted Signing is cheaper but
is currently limited to organizations in the USA, Canada, the EU and the UK, and to individual
developers in the USA and Canada — check your eligibility before relying on it.

## Before submitting

1. Build the PyInstaller directory on a clean Windows machine with `scripts\build_windows.ps1`
   and confirm `dist\Lannotex\Lannotex.exe` launches.
2. Remove UPX compression from `Lannotex.spec`. Packed executables trigger antivirus false
   positives and buy little.
3. Wrap it as MSIX, and review the declared capabilities. Solo use must work with no network
   capability at all; never enable hosting silently.
4. Run the Windows App Certification Kit and fix what it reports.
5. Confirm `LICENSES\THIRD_PARTY_NOTICES.md` ships with the package and matches the bundled
   dependencies.
6. Smoke-test on a clean Windows VM, not the build machine.

## Store listing needs

- A privacy policy URL. Lannotex collects nothing, which makes this short and honest: solo mode
  makes no network requests, team mode connects only to the host the user enters, and there is
  no telemetry.
- An age rating questionnaire.
- Screenshots and an icon; the ones in `docs/assets/` are generated from the real app by
  `scripts/bench`-adjacent tooling, so they stay current.

## Rule that must not be broken

**Never package project data inside the installation directory.** Projects live in folders the
user chooses and must survive app updates and uninstalls. Caches belong in the user cache
folder, which is already where thumbnails and tile pyramids go.
