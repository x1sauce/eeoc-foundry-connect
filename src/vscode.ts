/** Optional additive OMP command: /foundry-vscode-sync
 *
 * Uses the Python Azure Resources broker integration, not Azure CLI.
 * No network access or changes happen on extension load.
 * Usage: /foundry-vscode-sync <subscription-guid> [--resource-group <name>] [--tenant-id <guid>] [--apply]
 */
import type { ExtensionAPI, ExtensionCommandContext } from "@oh-my-pi/pi-coding-agent";
import { fileURLToPath } from "node:url";

const SYNC_SCRIPT = fileURLToPath(new URL("../scripts/foundry-vscode-sync.py", import.meta.url));
const GUID = /^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$/;
const RG = /^[A-Za-z0-9_.()\-]{1,90}$/;

function commandArgs(raw: string): string[] {
  const parts = raw.trim().split(/\s+/).filter(Boolean);
  if (!parts.length || !GUID.test(parts[0])) {
    throw new Error("Provide subscription GUID: /foundry-vscode-sync <GUID> [--apply]");
  }
  const args = ["--subscription-id", parts[0]];
  for (let i = 1; i < parts.length; i++) {
    const opt = parts[i];
    if (opt === "--apply") {
      if (args.includes("--apply")) throw new Error("Duplicate --apply");
      args.push("--apply");
    } else if (opt === "--resource-group" || opt === "--tenant-id") {
      const value = parts[++i];
      if (!value || (opt === "--resource-group" ? !RG.test(value) : !GUID.test(value))) {
        throw new Error(`Invalid ${opt}; supply a valid value`);
      }
      args.push(opt, value);
    } else {
      throw new Error(`Unsupported argument ${opt}`);
    }
  }
  return args;
}

async function runPython(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  for (const python of ["python", "py"]) {
    const command = python === "py" ? [python, "-3", SYNC_SCRIPT, ...args] : [python, SYNC_SCRIPT, ...args];
    try {
      const proc = Bun.spawn(command, { stdout: "pipe", stderr: "pipe" });
      const [stdout, stderr, code] = await Promise.all([
        new Response(proc.stdout).text(),
        new Response(proc.stderr).text(),
        proc.exited,
      ]);
      return { code, stdout: stdout.trim(), stderr: stderr.trim() };
    } catch { /* executable not found; try alternative */ }
  }
  throw new Error("Python not found on OMP's PATH; launch OMP from the VS Code Terminal with Python available.");
}

async function sync(raw: string, ctx: ExtensionCommandContext, pi: ExtensionAPI): Promise<void> {
  let args: string[];
  try {
    args = commandArgs(raw);
  } catch (error) {
    ctx.ui.notify(error instanceof Error ? error.message : "Invalid arguments", "error");
    return;
  }
  await ctx.waitForIdle();
  ctx.ui.notify(args.includes("--apply") ? "Running approved local Foundry sync…" : "Previewing Foundry sync (no local writes)…", "info");
  try {
    const result = await runPython(args);
    if (result.code !== 0) {
      const message = result.stderr || `Sync exit code ${result.code}`;
      pi.logger.error(`[eeoc-foundry-connect] VS Code sync failed: ${message}`);
      ctx.ui.notify(message.slice(0, 1500), "error");
      return;
    }
    // Do not log raw YAML; previews may expose local filenames / non-secret IDs.
    const lines = result.stdout.split(/\r?\n/).filter(Boolean);
    ctx.ui.notify(`${args.includes("--apply") ? "Local sync complete; restart OMP." : "Preview complete; no local files changed."}\n${lines.slice(-3).join("\n")}`, "info");
  } catch (error) {
    ctx.ui.notify(`VS Code sync launcher error: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}

export default function eeocFoundryVSCode(pi: ExtensionAPI) {
  pi.registerCommand("foundry-vscode-sync", {
    description: "Preview or sync Foundry deployments using VS Code Azure Resources (no Azure CLI). Usage: <subscription-guid> [--apply]",
    handler: async (args, ctx) => sync(args, ctx, pi),
  });
}
