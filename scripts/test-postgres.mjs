// Optional verification tool; downloads live only in the ignored .data directory.
import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { randomBytes } from "node:crypto";
import { cp, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const password = randomBytes(24).toString("hex");
// PostgreSQL's Windows initdb cannot bootstrap UTF8 in some non-ASCII installation paths.
// Isolate binaries and data under the OS temp directory; no system service is installed.
const verificationRoot = await mkdtemp(path.join(tmpdir(), "linktoon-pg-"));
const runtime = path.join(verificationRoot, "runtime");
await cp(path.join(root, ".data", "postgres-runtime"), runtime, {
  recursive: true,
});
const { default: EmbeddedPostgres } = await import(
  pathToFileURL(
    path.join(runtime, "node_modules", "embedded-postgres", "dist", "index.js"),
  )
);
process.chdir(verificationRoot);
const pg = new EmbeddedPostgres({
  databaseDir: path.join(verificationRoot, "cluster"),
  user: "linktoon",
  password,
  port: 55432,
  persistent: true,
  postgresFlags: ["-h", "127.0.0.1"],
  initdbFlags: ["--encoding=UTF8", "--locale=C"],
  onLog: () => {},
  onError: (value) => {
    if (String(value).includes("FATAL")) console.error(String(value));
  },
});
let testExitCode = 1;
try {
  await pg.initialise();
  await pg.start();
  await pg.createDatabase("linktoon_verify");
  const child = spawn(
    path.join(
      root,
      "apps",
      "api",
      ".venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    ),
    [
      "-m",
      "pytest",
      "-q",
      "--tb=short",
      "-p",
      "no:cacheprovider",
      `--basetemp=${path.join(verificationRoot, "pytest")}`,
    ],
    {
      cwd: path.join(root, "apps", "api"),
      stdio: "inherit",
      windowsHide: true,
      env: {
        ...process.env,
        TEST_POSTGRES_URL: `postgresql+pg8000://linktoon:${password}@127.0.0.1:55432/linktoon_verify`,
      },
    },
  );
  testExitCode = await new Promise((resolve, reject) => {
    child.on("exit", (code) => resolve(code ?? 1));
    child.on("error", reject);
  });
} finally {
  await pg.stop();
}
process.exit(testExitCode);
