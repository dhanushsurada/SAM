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
use serde::Serialize;
use serde_json::Value;
use std::path::PathBuf;
use std::process::Command;
use tauri::{AppHandle, Emitter};

// ─── Dev-mode Python/CLI resolution (Phase C §11's production gap) ────────
//
// Both functions below are correct for a dev checkout and will not be
// correct once this is packaged and installed elsewhere — that's not
// hidden, it's the explicit, named production gap this phase was told
// not to solve yet. Keeping both as single functions (rather than
// inlining `"python3"` and a relative path at each call site) is what
// makes the eventual production fix a one-place change instead of a
// repo-wide find-and-replace.

/// CARGO_MANIFEST_DIR is this crate's own directory
/// (interfaces/desktop/src-tauri) baked in at *compile* time — reliable
/// for a dev build run from a checkout. Meaningless once this binary is
/// installed somewhere else, which is exactly why this isn't the answer
/// for a packaged `.app`.
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}

fn sam_cli_path() -> PathBuf {
    repo_root().join("sam_cli.py")
}

/// Relies on `python3` already being on PATH — true for a repo checkout
/// with its environment active, not guaranteed inside a packaged app
/// with no shell environment inherited the same way.
fn python_command() -> &'static str {
    "python3"
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
    let mut cmd = Command::new(python_command());
    cmd.arg(sam_cli_path());
    cmd.args(args);
    cmd.arg("--json");

    let output = cmd.output().map_err(|e| {
        format!(
            "could not run sam_cli.py (is `{}` on PATH?): {e}",
            python_command()
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

/// Phase C §12's explicit instruction: one function, not
/// "http://localhost:8420" scattered across every command below. Dev
/// value only — see the production-gap note in
/// docs/RUNTIME_BRIDGE_DESIGN.md §I. This is the one place a later
/// production fix (an absolute URL switched on by isNative(), per that
/// doc) needs to change.
fn api_base_url() -> String {
    "http://localhost:8420".to_string()
}

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
    let url = format!("{}/api/models", api_base_url());
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("could not reach the SAM gateway at {url}: {e}"))?;
    relay_gateway_json(resp).await
}

#[tauri::command]
pub async fn model_select(name: String) -> Result<Value, String> {
    validate_model_name(&name)?;
    let url = format!("{}/api/models/select", api_base_url());
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
/// Cancellation: dropping this future (e.g. the window closing, or a
/// future "cancel" command that aborts the task this was spawned as)
/// closes the underlying connection, which is the entire cancellation
/// mechanism — matching ModelManager.pull()'s own design, which relies
/// on exactly that and Ollama's resumability to avoid needing anything
/// more (docs/RUNTIME_BRIDGE_DESIGN.md §E). Nothing here needs to
/// implement a separate cancel path.
#[tauri::command]
pub async fn model_pull(app: AppHandle, name: String) -> Result<(), String> {
    validate_model_name(&name)?;
    let url = format!("{}/api/models/pull", api_base_url());
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
    while let Some(event) = stream.next().await {
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
