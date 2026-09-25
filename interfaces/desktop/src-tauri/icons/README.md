# App icons

No binary icon files are included here on purpose — an `.icns` needs
`iconutil`, which only exists on macOS, and this scaffold was written in a
Linux sandbox. Hand-producing one elsewhere risks a corrupt or wrong-size
icon that fails silently at bundle time.

Once `@tauri-apps/cli` is installed (`npm install`), generate the full set
from the SAM logo in one step, using the actual source file you already
have:

```bash
cd interfaces/desktop
npm run tauri icon /path/to/SAM_LOGO.png
```

This writes `32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`,
`icon.ico` and a few Android/iOS variants into this folder — exactly the
filenames `tauri.conf.json`'s `bundle.icon` list and `trayIcon.iconPath`
already expect, so nothing else needs to change after you run it.

The source logo has a solid orange background. For the menu-bar (tray)
icon specifically, a near-transparent monochrome glyph usually reads
better than the full-color square once `iconAsTemplate: true` inverts it
for light/dark menu bars — worth a quick look after generating, and a
second, simplified source image for the tray if the auto-generated one
looks muddy at 16–22px.
