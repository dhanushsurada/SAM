# App icons

The icon set (`32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`,
`icon.ico`, `icon.png`) is committed and is what the installers use.

To replace the artwork, regenerate the whole set from one square PNG
(1024x1024 recommended) and commit the result:

```bash
cd interfaces/desktop
npm run tauri icon /path/to/SAM_LOGO.png
```
