// SAM — native desktop shell (Tauri v2)
//
// VERIFICATION STATUS: the tray/menu, global-shortcut, and window-config
// APIs used below were checked against Tauri's own published docs and
// source (tauri-apps/plugins-workspace, v2 branch; v2.tauri.app reference
// pages) via web search — not run through cargo, but no longer purely
// hand-recalled either. One real bug this caught: the global-shortcut
// handler's `event.state` is a field, not a method — fixed below. Full
// verification status, source-by-source, is in NATIVE_SHELL_NOTES.md.
// This sandbox still has no `cargo`/`rustc`/macOS, so `cargo check` from
// this directory remains the mandatory first step on a real machine,
// before touching anything else.
//
// What this does, end to end:
//   - Loads the existing interfaces/desktop React app into a native
//     window instead of a browser tab (Agent 1 scope: wrap it, don't
//     rebuild it — see docs/frontend/PHASE5_PLAN.md).
//   - Keeps SAM resident: closing the main window hides it rather than
//     quitting the process; Cmd+Q / tray "Quit SAM" actually quits.
//   - Adds a menu-bar (tray) icon: Show SAM / Quick Assistant / Quit.
//   - Registers a global shortcut (Cmd+Shift+Space) that shows a small,
//     always-on-top Quick Assistant window — a second window into the
//     same app, not a second app. See QuickAssistantApp.tsx.
//   - Exposes one command to the frontend, `hide_quick_assistant`.
//     Notifications no longer go through a custom command — the frontend
//     (src/lib/native.ts) now calls the notification plugin's own,
//     documented JS bindings directly (isPermissionGranted /
//     requestPermission / sendNotification), which is what that plugin
//     is for. `tauri_plugin_notification::init()` below is still what
//     makes those JS bindings work; only the redundant custom Rust
//     wrapper around it was removed.
//   - Re-shows the main window on Dock-icon reopen, the standard macOS
//     convention for apps that hide-rather-than-quit on window close.

mod runtime;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager, RunEvent, WindowEvent,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use tauri_plugin_autostart::ManagerExt;

/// Built fresh on each use rather than a top-level `const` — that keeps
/// this file from depending on `Shortcut::new` being a `const fn`, which
/// wasn't worth confirming from memory alone.
fn quick_assistant_shortcut() -> Shortcut {
    Shortcut::new(Some(Modifiers::SUPER | Modifiers::SHIFT), Code::Space)
}

fn toggle_quick_assistant(app: &tauri::AppHandle) {
    let Some(win) = app.get_webview_window("quick-assistant") else {
        return;
    };
    let visible = win.is_visible().unwrap_or(false);
    let focused = win.is_focused().unwrap_or(false);
    if visible && focused {
        let _ = win.hide();
    } else {
        let _ = win.show();
        let _ = win.set_focus();
    }
}

#[tauri::command]
fn hide_quick_assistant(app: tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("quick-assistant") {
        let _ = win.hide();
    }
}

#[tauri::command]
fn launch_at_login_enabled(app: tauri::AppHandle) -> Result<bool, String> {
    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

#[tauri::command]
fn set_launch_at_login(app: tauri::AppHandle, enabled: bool) -> Result<bool, String> {
    let manager = app.autolaunch();
    if enabled {
        manager.enable().map_err(|e| e.to_string())?;
    } else {
        manager.disable().map_err(|e| e.to_string())?;
    }
    manager.is_enabled().map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    // `event.state` is a field on ShortcutEvent, not a
                    // method — confirmed against the plugin's own
                    // published examples (tauri-apps/plugins-workspace,
                    // v2 branch); the first draft of this file had it as
                    // `event.state()`, which would not have compiled.
                    if event.state == ShortcutState::Pressed
                        && shortcut == &quick_assistant_shortcut()
                    {
                        toggle_quick_assistant(app);
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            hide_quick_assistant,
            launch_at_login_enabled,
            set_launch_at_login,
            runtime::runtime_status,
            runtime::runtime_start,
            runtime::runtime_stop,
            runtime::runtime_restart,
            runtime::ollama_status,
            runtime::ollama_start,
            runtime::setup_state_get,
            runtime::setup_state_set,
            runtime::runtime_api_base_url,
            runtime::models_list,
            runtime::model_select,
            runtime::model_pull,
            runtime::model_pull_cancel,
        ])
        .setup(|app| {
            if let Err(error) = runtime::initialize_packaged_runtime(app.handle()) {
                eprintln!("SAM: could not initialize bundled runtime configuration: {error}");
            }
            // The desktop app owns the SAM backend lifecycle. Installers do
            // not also register launchd/Task Scheduler services for it.
            std::thread::spawn(|| {
                if let Err(error) = runtime::runtime_start(Some("api".to_string())) {
                    eprintln!("SAM: backend startup failed: {error}");
                }
            });

            // Registered at runtime rather than only declared, so a
            // failure (shortcut already bound to another app) is visible
            // in the logs instead of silently no-op-ing at startup.
            if let Err(e) = app.global_shortcut().register(quick_assistant_shortcut()) {
                eprintln!("SAM: could not register the Quick Assistant shortcut: {e}");
            }

            let show_item = MenuItem::with_id(app, "show", "Show SAM", true, None::<&str>)?;
            let quick_item = MenuItem::with_id(
                app,
                "quick",
                "Quick Assistant",
                true,
                Some("CmdOrCtrl+Shift+Space"),
            )?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit SAM", true, None::<&str>)?;
            let tray_menu = Menu::with_items(app, &[&show_item, &quick_item, &quit_item])?;

            // `icon_as_template` lets macOS invert the glyph automatically
            // between light and dark menu bars — without it the icon
            // reads wrong in one of the two.
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .icon_as_template(true)
                .menu(&tray_menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "quick" => toggle_quick_assistant(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // The main window hides instead of closing — SAM is meant to
            // stay resident (menu bar / background operation, per the
            // product brief), not quit every time its window closes.
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
            // The palette should feel dismissible, not closable: losing
            // focus (click-away) hides it rather than destroying the
            // window, so the next shortcut press doesn't pay a
            // fresh-webview cost.
            if window.label() == "quick-assistant" {
                if let WindowEvent::Focused(false) = event {
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building SAM")
        .run(|app_handle, event| {
            // Clicking the Dock icon while SAM has no visible window
            // (e.g. after CloseRequested hid it) should reopen the main
            // window — the convention every native Mac app follows.
            if let RunEvent::Reopen {
                has_visible_windows,
                ..
            } = event
            {
                if !has_visible_windows {
                    if let Some(w) = app_handle.get_webview_window("main") {
                        let _ = w.show();
                        let _ = w.set_focus();
                    }
                }
            }
        });
}
