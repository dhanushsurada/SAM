# JEV planning adapter

SAM's planning interface now defaults to a JEV-backed adapter. `local-jev`
handles bounded planning-model and execution-route choices; Ollama generates
the ordered, free-form plan. SAM's existing orchestrator executes it through
the same tool dispatch and permission checks. The verifier and its one retry
remain unchanged.

## Configure local-jev

Install and run [amithgc/local-jev](https://github.com/amithgc/local-jev)
separately. Its documented API listens at `http://127.0.0.1:8765/v1/systemone`.
The first model download is managed by that project; SAM does not download or
install local-jev models.

SAM settings (in `~/.sam_data/settings.yaml`, or repo defaults) are:

```yaml
planning_backend: jev
jev_base_url: http://127.0.0.1:8765
jev_model: jev-latest
jev_timeout_seconds: 2.0
```

If `local-jev` is started with `LOCAL_JEV_API_KEY`, set that same variable in
SAM's environment; SAM sends it as a bearer token and does not store it in
settings.

JEV selects a planning model, preferred tool family, and task-priority score.
An explicit `planner_model` setting remains pinned. The generative model
creates steps, dependencies, and success criteria. JEV
answers are advisory. Low-confidence/malformed/unavailable answers do not
authorize actions; SAM uses the retained legacy planner. Suggested tool routes
are included as hints in step prompts. Tools, terminal safeguards, and verifier
decisions remain under SAM's deterministic code.

After an action fails verification and the verifier's existing retry, SAM may
ask JEV whether to continue, stop, or revise only the unfinished plan. Completed
observations are included as state and are not re-executed by the replacement
plan. Successful steps never trigger a replanning request. At most two recovery
replans are allowed per task, and the existing `MAX_STEPS` bound still applies.

## Rollback

Set `planning_backend: legacy` and restart SAM. This bypasses local-jev while
leaving the current tool execution, verification, and adaptive ReAct fallback
unchanged. If local-jev is simply unavailable, the adapter falls back to the
legacy planner automatically.

The default single-step heuristic is retained to avoid paying for an upfront
planning call on straightforward requests. Existing planning and verification
events and the one-prompt task entry point are unchanged.

## Validation status

Offline compatibility coverage exercises response parsing, low-confidence and
unavailable JEV fallback, failure-triggered replanning, and the no-replan path
after successful steps. Live local-jev/Ollama quality and latency still require
measurement on the target Apple Silicon setup; the adapter does not claim a
performance improvement until those measurements are recorded.
