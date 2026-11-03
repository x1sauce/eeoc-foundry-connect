import type { ExtensionAPI, ExtensionCommandContext } from "@oh-my-pi/pi-coding-agent";
import { fileURLToPath } from "node:url";

const DEFAULT_ENDPOINT = "https://aif-eeoc-daes-dev.services.ai.azure.com";
const SCRIPT_PATH = fileURLToPath(new URL("../scripts/foundry-sync.py", import.meta.url));

type RunResult = {
	code: number;
	stdout: string;
	stderr: string;
	command: string;
};

async function spawnAndCapture(command: string[]): Promise<RunResult> {
	const proc = Bun.spawn(command, {
		stdout: "pipe",
		stderr: "pipe",
	});
	const [stdout, stderr, code] = await Promise.all([
		new Response(proc.stdout).text(),
		new Response(proc.stderr).text(),
		proc.exited,
	]);
	return {
		code,
		stdout: stdout.trim(),
		stderr: stderr.trim(),
		command: command.join(" "),
	};
}

async function runPython(args: string[]): Promise<RunResult> {
	const candidates =
		process.platform === "win32"
			? [
				["python", SCRIPT_PATH, ...args],
				["py", "-3", SCRIPT_PATH, ...args],
			]
			: [
				["python3", SCRIPT_PATH, ...args],
				["python", SCRIPT_PATH, ...args],
			];

	let lastError = "Python was not found.";
	for (const command of candidates) {
		try {
			return await spawnAndCapture(command);
		} catch (err) {
			lastError = err instanceof Error ? err.message : String(err);
		}
	}
	throw new Error(lastError);
}

function compactOutput(text: string, maxLines = 8): string {
	const lines = text
		.split(/\r?\n/)
		.map((line) => line.trimEnd())
		.filter(Boolean);
	if (lines.length <= maxLines) return lines.join("\n");
	return [...lines.slice(0, maxLines - 2), "...", ...lines.slice(-2)].join("\n");
}

async function handleSync(args: string, ctx: ExtensionCommandContext, pi: ExtensionAPI): Promise<void> {
	await ctx.waitForIdle();

	const endpoint = args.trim() || DEFAULT_ENDPOINT;
	ctx.ui.notify("Running Foundry Entra sync…", "info");

	try {
		const result = await runPython(["--endpoint", endpoint]);
		if (result.code !== 0) {
			const detail = compactOutput(result.stderr || result.stdout || `exit code ${result.code}`);
			pi.logger.error(`[eeoc-foundry-connect] sync failed (${result.command}): ${detail}`);
			ctx.ui.notify(`Foundry sync failed:\n${detail}`, "error");
			return;
		}

		const detail = compactOutput(result.stdout);
		pi.logger.info(`[eeoc-foundry-connect] sync complete:\n${result.stdout}`);
		ctx.ui.notify(
			`Foundry sync complete. Restart OMP before using the refreshed models.\n${detail}`,
			"info",
		);
	} catch (err) {
		const message = err instanceof Error ? err.message : String(err);
		pi.logger.error(`[eeoc-foundry-connect] sync launcher failed: ${message}`);
		ctx.ui.notify(`Could not run Foundry sync: ${message}`, "error");
	}
}

export default function eeocFoundryConnect(pi: ExtensionAPI) {
	pi.registerCommand("foundry-sync", {
		description:
			"Configure EEOC Azure AI Foundry for OMP using Entra ID bearer auth. Optional argument: Foundry endpoint.",
		handler: async (args, ctx) => {
			await handleSync(args, ctx, pi);
		},
	});

	pi.registerCommand("foundry-auth-help", {
		description: "Show the EEOC Foundry/OMP Entra authentication setup and recovery steps.",
		handler: async (_args, ctx) => {
			ctx.ui.notify(
				[
					"EEOC Foundry uses Microsoft Entra ID; static API keys are disabled.",
					"1. Run `az login` and verify `az account show`.",
					"2. Run `/foundry-sync` (defaults to EEOC DEV).",
					"3. Restart OMP.",
					"4. Verify with `omp models find foundry`.",
				].join("\n"),
				"info",
			);
		},
	});
}
