/**
 * What SAM's Hands can do, read from the code that runs them — the ReAct
 * loop's action table (agent/react_loop.py: control, browser, terminal,
 * vision) and the modules behind each — not from the product wish list.
 *
 * `availability` is deliberately three-valued and honest about what the
 * gateway can tell us:
 *   probed           the gateway health check reports it (`checks`)
 *   implemented      the code exists and the ReAct loop can call it, but
 *                    the gateway doesn't report whether it's usable on this
 *                    machine right now (permissions, packages, ...)
 *   not-implemented  nothing in this repository does this
 * Nothing here is fetched, so nothing pretends to be live.
 */

export type Availability = "probed" | "implemented" | "not-implemented";

/** HealthStatus fields that report a runtime dependency (api/types.ts). */
export type HealthCheckField = "vision_model_available" | "whisper_available";

export interface HandsCapability {
  id: string;
  name: string;
  summary: string;
  abilities: string[];
  needs: string;
  source: string;
  availability: Availability;
  checks?: { label: string; field: HealthCheckField }[];
}

export const CAPABILITIES: HandsCapability[] = [
  {
    id: "desktop-control",
    name: "Desktop control",
    summary:
      "Operates the computer the way a person would: launches and focuses apps, clicks, types and presses shortcuts.",
    abilities: [
      "open_app: launch or focus an app, then confirm it's actually in front",
      "click: locate the target with vision and click it, then look again (a target still in the same spot means the click may not have registered)",
      "type: enter text, then look at what appeared",
      "hotkey: press a keyboard shortcut",
      "screenshot: capture the screen",
    ],
    needs: "PyAutoGUI. On macOS: Accessibility and Screen Recording permissions, and Automation for System Events.",
    source: "hands/control/controller.py",
    availability: "implemented",
  },
  {
    id: "vision",
    name: "Screen vision",
    summary: "Reads what's on screen and finds the thing to click, using a local vision model.",
    abilities: [
      "Describe or read the current screen",
      "Locate an element from a plain-language description",
    ],
    needs: "A vision model installed in Ollama (Settings: vision model).",
    source: "hands/vision/screen_reader.py",
    availability: "probed",
    checks: [{ label: "Vision model installed", field: "vision_model_available" }],
  },
  {
    id: "browser",
    name: "Browser",
    summary:
      "Drives a Chromium browser for tasks that live on the web. One capability among the others; nothing else here depends on it.",
    abilities: ["Open a URL", "Click links and controls by their visible text", "Fill fields and read page content"],
    needs: "Playwright and its browser.",
    source: "hands/browser/playwright_agent.py",
    availability: "implemented",
  },
  {
    id: "terminal",
    name: "Terminal",
    summary:
      "Runs shell commands and reports what happened. Dangerous commands are always blocked; risky ones are refused unless you allow them in settings.",
    abilities: ["Run a command", "Read the output and exit status"],
    needs: "Nothing extra. Risky commands need allow_risky_terminal_commands.",
    source: "hands/terminal/runner.py",
    availability: "implemented",
  },
  {
    id: "verification",
    name: "Verification",
    summary:
      "Checks each step's result before moving on, and reports honestly. Known failure signals (a target not found, a click that may not have registered, the wrong app in front, an error) fail the step; SAM retries it once, then stops. Running out of steps without finishing is reported as unable to verify, not as done.",
    abilities: [
      "Look again after click and type; confirm the foreground app after open_app",
      "Retry a failed step once, then stop and say so",
      "Report success, failed, stopped after retries, unable to verify, or cancelled",
    ],
    needs: "Runs on every task. A heuristic check on each step's result, not proof the goal was met.",
    source: "agent/verifier.py, agent/react_loop.py",
    availability: "implemented",
  },
  {
    id: "phone-input",
    name: "Phone-originated tasks",
    summary: "The phone gateway accepts text, voice notes and photos and hands them to the same pipeline as anything typed here.",
    abilities: ["Text tasks", "Voice notes, transcribed locally", "Photos, interpreted by the vision model"],
    needs: "The gateway running on this computer, reachable from the phone.",
    source: "interfaces/api/, multimodal/",
    availability: "probed",
    checks: [
      { label: "Whisper installed", field: "whisper_available" },
      { label: "Vision model installed", field: "vision_model_available" },
    ],
  },
  {
    id: "office-kit",
    name: "Office Kit device control",
    summary: "Screen mirroring, shared clipboard, file transfer and remote control between phone and PC.",
    abilities: [],
    needs: "No integration exists in this repository. The phone reaches SAM over HTTP; nothing here talks to Office Kit.",
    source: "docs/iqoo/OFFICE_KIT.md",
    availability: "not-implemented",
  },
];
