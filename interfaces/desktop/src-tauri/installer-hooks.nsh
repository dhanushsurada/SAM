; SAM Windows installer hooks (Tauri NSIS bundler).
; Goals: upgrade/uninstall never fails because SAM or its bundled Python is
; still running, and user data is only removed when the user explicitly says so.

!macro SAM_STOP_RUNNING
  ; Stop the desktop app, then any process running out of the bundled runtime.
  nsExec::Exec 'taskkill /F /IM sam-desktop.exe'
  nsExec::Exec 'powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like ''$INSTDIR\*'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"'
  Sleep 800
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro SAM_STOP_RUNNING
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro SAM_STOP_RUNNING
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Silent uninstalls (e.g. managed deployments, upgrades) never delete data.
  IfSilent sam_keep_data
  MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 \
    "Also delete your SAM data (settings, memory, logs) in $PROFILE\.sam_data?$\r$\n$\r$\nChoose No to keep it for a future reinstall. Ollama and its downloaded models are never touched." \
    IDNO sam_keep_data
  RMDir /r "$PROFILE\.sam_data"
  sam_keep_data:
!macroend
