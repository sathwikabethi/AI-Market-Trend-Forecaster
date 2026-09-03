import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// frontend
const projectRoot = path.resolve(__dirname, "..");

// Usage:
//   node ./scripts/run-vite.mjs dev [vite args...]
//   node ./scripts/run-vite.mjs build [vite args...]
//   node ./scripts/run-vite.mjs preview [vite args...]
const subcommand = process.argv[2] || "dev";
const passthroughArgs = process.argv.slice(3);

if (process.platform === "win32") {
  // Point directly at esbuild.exe. Using a `.cmd` shim here can fail because esbuild
  // spawns the binary without `shell: true`, which makes `.cmd` targets error with
  // "spawn EINVAL" on Windows.
  process.env.ESBUILD_BINARY_PATH = path.join(
    projectRoot,
    "node_modules",
    "@esbuild",
    "win32-x64",
    "esbuild.exe",
  );
}

const viteCli = path.join(projectRoot, "node_modules", "vite", "bin", "vite.js");
const child = spawn(process.execPath, [viteCli, subcommand, ...passthroughArgs], {
  cwd: projectRoot,
  env: process.env,
  stdio: "inherit",
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});

