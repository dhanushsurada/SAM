This directory is the Tauri resource source for the macOS consumer bundle.

The consumer packaging command stages SAM source, a managed Python runtime,
and the selected core Python dependencies here before creating the `.app` and
DMG. Source-based developer builds may include this note only; their runtime
configuration continues to come from `~/.sam_data/desktop-runtime.json`.
