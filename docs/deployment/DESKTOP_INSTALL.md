# SAM Desktop installation

## Supported route

The current supported desktop route is a **source-based developer install**.
`setup.sh` builds a local macOS `.app` from the checkout and opens it. It does
not produce or distribute a consumer DMG. `setup_windows.ps1` builds and
installs the Tauri MSI from the same source tree. Both need the checkout,
Python dependencies, Node.js, and the Rust toolchain to remain available at
the paths recorded in `~/.sam_data/desktop-runtime.json` (or the equivalent
user home on Windows). Moving or deleting the checkout requires rerunning the
setup script.

The Tauri bridge reads the configured Python executable, SAM CLI path,
resource root, process environment path, and API base URL from that per-user
runtime file. It does not derive these values from `CARGO_MANIFEST_DIR` or
the current working directory. The frontend uses Vite's `/api` proxy in
browser development and the configured native endpoint inside the packaged
Tauri shell. The API explicitly permits the Tauri webview origins needed for
that connection.

The Tauri app owns starting the SAM API process. macOS setup no longer
registers a competing launchd backend job; an existing legacy agent is
unloaded and preserved with a `.disabled` suffix after the app and runtime
config are built. Ollama is a separate service and is only started when
needed. Setup waits for its HTTP readiness instead of assuming a fixed delay.
Model downloads are opt-in and use the models already selected in SAM
settings; setup does not rewrite model configuration.

## Platform scope

- **macOS:** source-based Tauri `.app` build from `setup.sh`; no consumer DMG
  distribution is currently supported.
- **Windows:** source-based Tauri MSI build and install from
  `setup_windows.ps1`; the app starts the API, and Task Scheduler does not
  separately start Python.
- **Linux:** `setup_linux.sh` supports Debian/Ubuntu with `apt-get` for the
  Python backend only. It does not install the Tauri desktop client or set up
  automatic startup. Start the backend manually through `sam_cli.py`.

These paths are implemented but still require validation on their target
operating systems. No successful native Tauri build or first-launch check is
claimed by this change.
