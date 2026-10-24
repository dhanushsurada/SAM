//! Phase C4 — the Tauri ↔ Python runtime bridge.
//!
//! UNVERIFIED, same status as main.rs: no `cargo`/`rustc`/macOS in the
//! sandbox this was written in. Run `cargo check` before anything else —
//! the sync/async bridging and the streaming parser below are the least
//! certain pieces, reasoned through and checked against crate
//! documentation, not executed.
//!
//! Two transports, exactly matching docs/RUNTIME_BRIDGE_DESIGN.md §A/§B:
//!   - runtime_status/start/stop/restart and ollama_status/start shell
//!     out to `python sam_cli.py <cmd> --json`. Works even when the API
//!     gateway isn't running — the whole point of these, since bringing
//!     the gateway up is one of the things they do.
//!   - models_list/model_select/model_pull talk HTTP to the gateway
//!     itself, since those are only ever meaningful once it's already up
//!     (Phase B's "can this operation be meaningful before `api`
//!     exists?" test).
//!
//! No command here takes a raw command string or shell fragment from the
//! frontend (Phase C §10/§18) — every argument is either a fixed literal
//! this file chose, or a model name validated against Ollama's own
//! name:tag grammar before it ever reaches a URL or JSON body.

use eventsource_stream::Eventsource;
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::ffi::OsString;
use std::path::PathBuf;
use std::process::Command;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{AppHandle, Emitter, Manager};

static MODEL_PULL_ACTIVE: AtomicBool = AtomicBool::new(false);
static MODEL_PULL_CANCEL: AtomicBool = AtomicBool::new(false);

struct ModelPullGuard;
impl Drop for ModelPullGuard {
    fn drop(&mut self) {
        MODEL_PULL_ACTIVE.store(false, Ordering::Release);
        MODEL_PULL_CANCEL.store(false, Ordering::Release);
    }
}

// ─── Installed runtime configuration ───────────────────────────────────
// setup.sh writes this user-controlled config outside the source checkout.
// Runtime paths never depend on CARGO_MANIFEST_DIR or the app's cwd.
const RUNTIME_CONFIG: &str = ".sam_data/desktop-runtime.json";
const USER_PACKAGES: &str = ".sam_data/python-packages";
const USER_LOGS: &str = ".sam_data/logs";

#[derive(Debug, Deserialize)]
struct RuntimeConfig {
    #[serde(default)]
    runtime_schema_version: u32,
    app_root: PathBuf,
    resources_dir: PathBuf,
    sam_cli: PathBuf,
    python: PathBuf,
    api_base_url: String,
    environment_path: Option<String>,
    #[serde(default)]
    user_packages_dir: Option<PathBuf>,
    #[serde(default)]
    logs_dir: Option<PathBuf>,
}

/// A GUI app that spawns console programs (python.exe, powershell.exe) on
/// Windows would flash a black console window each time. No-op elsewhere.
pub fn hide_console(cmd: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

fn user_path(relative: &str) -> Result<PathBuf, String> {
    let home = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .ok_or_else(|| "User home is unavailable".to_string())?;
    Ok(home.join(relative))
}

fn runtime_config_path() -> Result<PathBuf, String> {
    user_path(RUNTIME_CONFIG)
}

/// Consumer bundles carry the application source and Python runtime below
/// the Tauri resource directory. On first launch, seed the normal per-user
/// runtime config atomically; developer installs keep their setup-written
/// checkout configuration and user-selected API endpoint.
pub fn initialize_packaged_runtime(app: &AppHandle) -> Result<(), String> {
    let path = runtime_config_path()?;
    let resources = app.path().resource_dir().map_err(|e| format!("Cannot locate SAM bundle resources: {e}"))?;
    let root = resources.join("sam-runtime");
    let source = root.join("source");
    let python_root = root.join("python");
    let python = if cfg!(windows) {
        python_root.join("python.exe")
    } else {
        python_root.join("bin").join("python3")
    };
    let site_packages = root.join("site-packages");
    let cli = source.join("sam_cli.py");
    if !cli.exists() || !python.exists() || !site_packages.exists() {
        if path.exists() && runtime_config().is_ok() {
            return Ok(()); // source-based developer setup owns its runtime config
        }
        if path.exists() {
            let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default().as_secs();
            let backup = path.with_file_name(format!("desktop-runtime.invalid-{stamp}.json"));
            std::fs::rename(&path, &backup).map_err(|e| format!(
                "SAM runtime configuration is invalid and could not be preserved at {}: {e}", backup.display()
            ))?;
        }
        return Err(format!(
            "SAM's packaged runtime is missing from {}. Reinstall SAM with its installer, or run the setup script for a developer checkout.",
            root.display()
        ));
    }
    let data_root = user_path(".sam_data")?;
    let user_packages = user_path(USER_PACKAGES)?;
    let logs = user_path(USER_LOGS)?;
    for directory in [&data_root, &user_packages, &logs] {
        std::fs::create_dir_all(directory).map_err(|e| format!(
            "Cannot prepare SAM's user directory {}: {e}", directory.display()
        ))?;
    }

    let existing = if path.exists() {
        let raw = std::fs::read_to_string(&path).map_err(|e| format!(
            "Cannot read SAM runtime configuration {}: {e}", path.display()
        ))?;
        match serde_json::from_str::<Value>(&raw) {
            Ok(Value::Object(value)) => Some(Value::Object(value)),
            _ => {
                let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default().as_secs();
                let backup = path.with_file_name(format!("desktop-runtime.invalid-{stamp}.json"));
                std::fs::rename(&path, &backup).map_err(|e| format!(
                    "SAM runtime configuration is damaged and could not be preserved at {}: {e}", backup.display()
                ))?;
                None
            }
        }
    } else { None };
    if let Some(schema) = existing.as_ref()
        .and_then(|config| config.get("runtime_schema_version"))
        .and_then(Value::as_u64)
    {
        if schema > 1 {
            return Err(format!("SAM runtime configuration schema {schema} is newer than this app supports. Update SAM before repairing it."));
        }
    }
    let preserved_api = existing.as_ref()
        .and_then(|config| config.get("api_base_url"))
        .and_then(Value::as_str)
        .filter(|url| url.starts_with("http://") || url.starts_with("https://"))
        .map(str::to_string)
        .unwrap_or_else(|| "http://127.0.0.1:8420".to_string());
    let mut search_paths: Vec<OsString> = if cfg!(windows) {
        vec![python_root.clone().into_os_string(), python_root.join("Scripts").into_os_string()]
    } else {
        vec![python_root.join("bin").into_os_string()]
    };
    #[cfg(target_os = "macos")]
    for candidate in [
        "/opt/homebrew/bin", "/usr/local/bin", "/opt/homebrew/sbin", "/usr/local/sbin",
        "/Applications/Ollama.app/Contents/Resources",
    ] {
        let path = PathBuf::from(candidate);
        if path.is_dir() { search_paths.push(path.into_os_string()); }
    }
    if let Some(existing) = std::env::var_os("PATH") {
        search_paths.extend(std::env::split_paths(&existing).map(PathBuf::into_os_string));
    }
    let environment_path = std::env::join_paths(search_paths).map_err(|e| e.to_string())?;
    let mut config = existing.unwrap_or_else(|| serde_json::json!({}));
    let Some(object) = config.as_object_mut() else {
        return Err("SAM runtime configuration must be a JSON object".to_string());
    };
    let generated = serde_json::json!({
        "runtime_schema_version": 1,
        "app_root": source,
        "resources_dir": site_packages,
        "sam_cli": cli,
        "python": python,
        "api_base_url": preserved_api,
        "environment_path": environment_path.to_string_lossy(),
        "user_packages_dir": user_packages,
        "logs_dir": logs,
    });
    for (key, value) in generated.as_object().unwrap() {
        object.insert(key.clone(), value.clone());
    }
    if let Some(parent) = path.parent() { std::fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
    let temporary = path.with_extension("json.tmp");
    std::fs::write(&temporary, serde_json::to_vec_pretty(&config).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    std::fs::rename(&temporary, &path).map_err(|e| format!("Cannot save SAM runtime config; retry using Repair runtime setup: {e}"))?;
    Ok(())
}

fn runtime_config() -> Result<RuntimeConfig, String> {
    let path = runtime_config_path()?;
    let raw = std::fs::read_to_string(&path).map_err(|e| format!(
        "SAM Desktop runtime configuration is missing at {}: {e}. Use Repair runtime setup, or reinstall SAM if this app's resources are missing.",
        path.display()
    ))?;
    let config: RuntimeConfig = serde_json::from_str(&raw)
        .map_err(|e| format!("invalid SAM Desktop runtime configuration {}: {e}", path.display()))?;
    if config.runtime_schema_version > 1 {
        return Err(format!("SAM runtime configuration schema {} is newer than this app supports. Update SAM before repairing it.", config.runtime_schema_version));
    }
    for (label, candidate) in [
        ("application root", &config.app_root),
        ("resources directory", &config.resources_dir),
        ("SAM CLI", &config.sam_cli),
        ("Python executable", &config.python),
    ] {
        if !candidate.exists() {
            return Err(format!("configured {label} does not exist: {}", candidate.display()));
        }
    }
    if !config.api_base_url.starts_with("http://") && !config.api_base_url.starts_with("https://") {
        return Err("api_base_url must be an http(s) URL".to_string());
    }
    if let Some(packages) = &config.user_packages_dir {
        if packages != &user_path(USER_PACKAGES)? {
            return Err("user_packages_dir must point to SAM's per-user package directory".to_string());
        }
    }
    Ok(config)
}

fn api_base_url() -> Result<String, String> {
    Ok(runtime_config()?.api_base_url.trim_end_matches('/').to_string())
}

/// Every CLI-bridge command shares this shape: run sam_cli.py, capture
/// stdout, parse the *last* line as JSON (matches sam_cli.py's own
/// convention — exactly one JSON line per --json invocation, printed
/// right before it exits) and turn any failure along the way into a
/// readable Err rather than a panic or a silent empty result.
///
/// An argument *list*, never a shell string — `Command::arg` passes each
/// piece through untouched; nothing here is ever concatenated into
/// `sh -c "..."`, so there's no injection surface even in principle,
/// independent of validate_model_name's own check elsewhere in this file.
fn run_sam_cli(args: &[&str]) -> Result<Value, String> {
    let config = runtime_config()?;
    let mut cmd = Command::new(&config.python);
    cmd.arg(&config.sam_cli);
    cmd.args(args);
    cmd.arg("--json");
    cmd.current_dir(&config.app_root);
    hide_console(&mut cmd);
    let mut python_paths = vec![config.app_root.clone()];
    if let Some(user_packages) = &config.user_packages_dir {
        python_paths.push(user_packages.clone());
        cmd.env("SAM_USER_PACKAGES_DIR", user_packages);
    }
    python_paths.push(config.resources_dir.clone());
    let python_path = std::env::join_paths(python_paths)
        .map_err(|e| format!("Invalid SAM Python resource paths: {e}"))?;
    cmd.env("PYTHONPATH", python_path);
    if let Some(path) = &config.environment_path {
        cmd.env("PATH", path);
    }

    let output = cmd.output().map_err(|e| {
        format!(
            "could not run SAM CLI using configured Python {}: {e}",
            config.python.display()
        )
    })?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let last_line = stdout.lines().last().unwrap_or("").trim();
    serde_json::from_str::<Value>(last_line).map_err(|e| {
        format!(
            "sam_cli.py {args:?} did not print valid JSON on its last line (exit {:?}): {e}. stderr: {}",
            output.status.code(),
            String::from_utf8_lossy(&output.stderr).trim(),
        )
    })
}

#[tauri::command]
pub fn runtime_api_base_url() -> Result<String, String> {
    api_base_url()
}

// ─── Runtime lifecycle (CLI bridge) ────────────────────────────────────────
//
// Plain (non-async) commands, deliberately: Tauri already dispatches
// synchronous commands onto its own thread pool rather than the main
// async runtime, which is exactly the "don't block the event loop"
// property an async fn + spawn_blocking would otherwise exist to get —
// simpler to rely on that than to add it explicitly.

#[tauri::command]
pub fn runtime_status() -> Result<Value, String> {
    run_sam_cli(&["status"])
}

#[tauri::command]
pub fn runtime_start(process: Option<String>) -> Result<Value, String> {
    let mut args = vec!["start"];
    if let Some(p) = process.as_deref() {
        args.push(p);
    }
    run_sam_cli(&args)
}

#[tauri::command]
pub fn runtime_stop(process: Option<String>) -> Result<Value, String> {
    let mut args = vec!["stop"];
    if let Some(p) = process.as_deref() {
        args.push(p);
    }
    run_sam_cli(&args)
}

#[tauri::command]
pub fn runtime_restart(process: Option<String>) -> Result<Value, String> {
    let mut args = vec!["restart"];
    if let Some(p) = process.as_deref() {
        args.push(p);
    }
    run_sam_cli(&args)
}

#[tauri::command]
pub fn ollama_status() -> Result<Value, String> {
    run_sam_cli(&["ollama", "status"])
}

#[tauri::command]
pub fn ollama_start() -> Result<Value, String> {
    run_sam_cli(&["ollama", "start"])
}

#[cfg_attr(target_os = "windows", allow(dead_code))]
fn open_url(url: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    let result = Command::new("open").arg(url).spawn();
    #[cfg(target_os = "windows")]
    let result = {
        let mut cmd = Command::new("cmd");
        cmd.args(["/C", "start", "", url]);
        hide_console(&mut cmd).spawn()
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let result = Command::new("xdg-open").arg(url).spawn();
    result.map(|_| ()).map_err(|e| format!("Could not open {url}: {e}"))
}

/// Windows: download Ollama's official installer, require a valid
/// Authenticode signature whose subject names Ollama, then start it (its own
/// installer UI runs, so the user sees and approves what happens).
/// macOS / Linux: open the official download page; Linux additionally needs
/// the documented one-line command because it requires administrator rights.
#[tauri::command]
pub async fn open_ollama_download() -> Result<String, String> {
    #[cfg(target_os = "windows")]
    {
        let url = "https://ollama.com/download/OllamaSetup.exe";
        let bytes = reqwest::get(url).await
            .map_err(|e| format!("Could not download the Ollama installer: {e}"))?
            .error_for_status().map_err(|e| format!("Ollama's download server refused the request: {e}"))?
            .bytes().await.map_err(|e| format!("The Ollama download was interrupted: {e}"))?;
        if bytes.len() < 1_000_000 {
            return Err("The downloaded Ollama installer is unexpectedly small; not running it.".to_string());
        }
        let dir = std::env::temp_dir().join("sam-ollama-installer");
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let exe = dir.join("OllamaSetup.exe");
        std::fs::write(&exe, &bytes).map_err(|e| format!("Could not save the installer: {e}"))?;
        let mut check = Command::new("powershell");
        check.args(["-NoProfile", "-NonInteractive", "-Command",
            "$s = Get-AuthenticodeSignature -LiteralPath $env:SAM_VERIFY_PATH; if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -like '*Ollama*') { exit 0 } else { exit 3 }"])
            .env("SAM_VERIFY_PATH", &exe);
        let verified = hide_console(&mut check).status().map(|s| s.success()).unwrap_or(false);
        if !verified {
            let _ = std::fs::remove_file(&exe);
            return Err("The downloaded file is not validly signed by Ollama, so SAM did not run it. Download Ollama from https://ollama.com/download instead.".to_string());
        }
        Command::new(&exe).spawn().map_err(|e| format!("Could not start the Ollama installer: {e}"))?;
        return Ok("The Ollama installer is open. Finish it, then return to SAM and press Re-check.".to_string());
    }
    #[cfg(target_os = "macos")]
    {
        open_url("https://ollama.com/download/mac")?;
        return Ok("Opened Ollama's download page. Install it, open it once, then return and press Re-check.".to_string());
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        open_url("https://ollama.com/download/linux")?;
        Ok("Opened Ollama's download page. In a terminal run: curl -fsSL https://ollama.com/install.sh | sh — then return and press Re-check.".to_string())
    }
}

/// Stop every SAM-owned backend process. Called on quit so an installer
/// upgrade or uninstall never finds python.exe still holding bundle files.
pub fn shutdown_backend() {
    if let Err(error) = runtime_stop(None) {
        eprintln!("SAM: backend shutdown reported: {error}");
    }
}

#[tauri::command]
pub fn runtime_repair_configuration(app: AppHandle) -> Result<(), String> {
    initialize_packaged_runtime(&app)
}

// ─── Setup state (Phase C7, CLI bridge) ────────────────────────────────────
//
// Routed through sam_cli.py like everything above, rather than this file
// reading/writing ~/.sam_data/setup_state.json directly — it's "just
// JSON," but what counts as a valid state and how the file is laid out
// is knowledge runtime/setup_state.py already owns (Phase C's own
// reuse-don't-duplicate principle applied here too, not only to the
// bigger subsystems).

#[tauri::command]
pub fn setup_state_get() -> Result<Value, String> {
    run_sam_cli(&["setup-state", "get"])
}

#[tauri::command]
pub fn setup_state_set(state: String, model: Option<String>) -> Result<Value, String> {
    let mut args = vec!["setup-state", "set", "--state", state.as_str()];
    if let Some(m) = model.as_deref() {
        args.push("--model");
        args.push(m);
    }
    run_sam_cli(&args)
}

// ─── Models (HTTP passthrough to the already-running SAM API gateway) ─────

/// Ollama's own name:tag grammar, checked before a model name ever
/// reaches a URL or JSON body. A second, independent gate — not a
/// replacement for ModelManager.validate_selection's own check on the
/// Python side (Phase B §H: the frontend crossing the native boundary
/// doesn't grant it a shortcut past checks that already exist there).
fn validate_model_name(name: &str) -> Result<(), String> {
    let valid = !name.is_empty()
        && name.len() <= 200
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-' | ':'));
    if valid {
        Ok(())
    } else {
        Err(format!("{name:?} doesn't look like a valid model identifier"))
    }
}

#[derive(Serialize)]
struct ModelRequestBody<'a> {
    model: &'a str,
}

/// Shared tail for the two plain-JSON gateway calls below: parses the
/// body as JSON regardless of status (FastAPI's HTTPException responses
/// are themselves JSON, `{"detail": "..."}`), then turns a non-2xx into
/// an Err carrying that same detail message rather than a generic one.
async fn relay_gateway_json(resp: reqwest::Response) -> Result<Value, String> {
    let status = resp.status();
    let body: Value = resp
        .json()
        .await
        .map_err(|e| format!("SAM gateway response wasn't valid JSON: {e}"))?;
    if status.is_success() {
        Ok(body)
    } else {
        let detail = body
            .get("detail")
            .and_then(|d| d.as_str())
            .unwrap_or("the SAM gateway reported an error with no detail message");
        Err(detail.to_string())
    }
}

#[tauri::command]
pub async fn models_list() -> Result<Value, String> {
    let url = format!("{}/api/models", api_base_url()?);
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("could not reach the SAM gateway at {url}: {e}"))?;
    relay_gateway_json(resp).await
}

#[tauri::command]
pub async fn model_select(name: String) -> Result<Value, String> {
    validate_model_name(&name)?;
    let url = format!("{}/api/models/select", api_base_url()?);
    let resp = reqwest::Client::new()
        .post(&url)
        .json(&ModelRequestBody { model: &name })
        .send()
        .await
        .map_err(|e| format!("could not reach the SAM gateway at {url}: {e}"))?;
    relay_gateway_json(resp).await
}

/// Phase C3's `POST /api/models/pull` is an SSE stream, not a single
/// JSON body — this command relays it live as `model-pull-progress`
/// events rather than returning anything useful itself; the frontend
/// listens for those instead of reading this command's return value
/// (Phase B §B: a command for the side effect, events for the data).
///
#[tauri::command]
pub async fn model_pull(app: AppHandle, name: String) -> Result<(), String> {
    validate_model_name(&name)?;
    if MODEL_PULL_ACTIVE.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire).is_err() {
        return Err("A model download is already active".to_string());
    }
    let _guard = ModelPullGuard;
    MODEL_PULL_CANCEL.store(false, Ordering::Release);
    let url = format!("{}/api/models/pull", api_base_url()?);
    let resp = reqwest::Client::new()
        .post(&url)
        .json(&ModelRequestBody { model: &name })
        .send()
        .await
        .map_err(|e| format!("could not reach the SAM gateway at {url}: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!(
            "SAM gateway answered HTTP {} for a pull request",
            resp.status()
        ));
    }

    let mut stream = resp.bytes_stream().eventsource();
    loop {
        let next = tokio::select! {
            event = stream.next() => event,
            _ = tokio::time::sleep(std::time::Duration::from_millis(100)) => {
                if MODEL_PULL_CANCEL.load(Ordering::Acquire) {
                    let _ = app.emit("model-pull-progress", serde_json::json!({
                        "name": name, "status": "cancelled", "detail": "Download cancelled; retry to resume with Ollama."
                    }));
                    return Err("Model download cancelled; retry to resume with Ollama.".to_string());
                }
                continue;
            }
        };
        let Some(event) = next else { break; };
        match event {
            Ok(ev) => {
                // ev.data is the raw text after "data: " -- passed
                // through as-is rather than typed on the Rust side
                // (Phase B §B: "the frontend should be able to
                // calculate completed/total" from the same shape Ollama
                // itself sends, not a Rust-reshaped version of it).
                let payload: Value = serde_json::from_str(&ev.data).unwrap_or_else(|_| {
                    serde_json::json!({"name": name, "status": "error", "error": "unreadable progress line"})
                });
                let _ = app.emit("model-pull-progress", &payload);
                if payload.get("status").and_then(|s| s.as_str()) == Some("error") {
                    let msg = payload
                        .get("error")
                        .and_then(|e| e.as_str())
                        .unwrap_or("pull failed")
                        .to_string();
                    return Err(msg);
                }
            }
            Err(e) => {
                let _ = app.emit(
                    "model-pull-progress",
                    serde_json::json!({"name": name, "status": "error", "error": e.to_string()}),
                );
                return Err(format!("pull stream for {name:?} broke: {e}"));
            }
        }
    }
    Ok(())
}

#[tauri::command]
pub fn model_pull_cancel() -> bool {
    if MODEL_PULL_ACTIVE.load(Ordering::Acquire) {
        MODEL_PULL_CANCEL.store(true, Ordering::Release);
        true
    } else {
        false
    }
}
