# Installation

Lannotex runs on Windows, macOS, and Linux. Install it as a Python tool, or download a
standalone build that needs no Python.

## With uv (recommended)

[uv](https://docs.astral.sh/uv/) installs Lannotex into its own isolated environment and
puts the `lannotex` command on your `PATH`:

```bash
uv tool install lannotex
lannotex
```

To try it without installing anything permanently:

```bash
uvx lannotex
```

Upgrade later with `uv tool upgrade lannotex`.

## With pip

Use Python **3.11 – 3.14**. Installing into a virtual environment keeps Lannotex's Qt
libraries separate from your other projects:

=== "Windows"

    ```powershell
    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install lannotex
    lannotex
    ```

=== "macOS / Linux"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install lannotex
    lannotex
    ```

If you prefer [pipx](https://pipx.pypa.io/), `pipx install lannotex` also works.

## Standalone builds

Each [GitHub release](https://github.com/Lourdhu02/Lannotex/releases) includes a
prebuilt archive for Windows, macOS, and Linux. Extract it and run the `Lannotex`
executable inside. The archive bundles Python and Qt.

!!! note "Unsigned builds"
    Release builds are not yet code-signed. On Windows, SmartScreen may show
    *Windows protected your PC*: choose **More info → Run anyway**. On macOS, Gatekeeper
    may block the first launch. Open it from Finder with **right-click → Open**.

The app stores data only in project folders you choose, never in its installation
directory, so you can replace or delete the app without touching your projects.

## From source

```bash
git clone https://github.com/Lourdhu02/Lannotex.git
cd Lannotex
uv venv && uv pip install -e ".[dev]"   # or: python -m pip install -e ".[dev]"
lannotex
```

See [CONTRIBUTING.md](https://github.com/Lourdhu02/Lannotex/blob/main/CONTRIBUTING.md)
for the test and lint commands.

## Check the install

```bash
lannotex --version
```

Linux desktops need the usual Qt runtime libraries. If the window fails to open with an
`xcb` plugin error, install your distribution's `libxcb-cursor0` (Debian/Ubuntu) or
`xcb-util-cursor` (Fedora/Arch) package.
