// Cross-platform launcher: finds a Python 3 interpreter and runs the
// repository's runtime stager. Used by `npm run package` so the same command
// works from PowerShell, cmd, bash and zsh.
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const stager = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../scripts/stage_runtime.py");
const candidates = process.platform === "win32"
  ? [["py", ["-3"]], ["python", []], ["python3", []]]
  : [["python3", []], ["python", []]];

for (const [cmd, pre] of candidates) {
  const probe = spawnSync(cmd, [...pre, "--version"], { stdio: "ignore" });
  if (probe.status === 0) {
    const run = spawnSync(cmd, [...pre, stager, ...process.argv.slice(2)], { stdio: "inherit" });
    if ((run.status ?? 1) !== 0) process.exit(run.status ?? 1);
    // macOS release builds: sign nested binaries before Tauri bundles them.
    if (process.platform === "darwin" && process.env.APPLE_SIGNING_IDENTITY) {
      const sign = spawnSync("bash", [path.resolve(path.dirname(stager), "macos_sign_runtime.sh")], { stdio: "inherit" });
      process.exit(sign.status ?? 1);
    }
    process.exit(0);
  }
}
console.error("Python 3 was not found. Install it from https://www.python.org/downloads/ and retry.");
process.exit(1);
