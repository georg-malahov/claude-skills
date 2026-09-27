#!/usr/bin/env node
// Start the `before` and `after` servers side by side, wait until both answer,
// then either run one command against them or keep them up until Ctrl-C.
//
//   node serve-pair.mjs \
//     --before "npm run start -- -p 4101" --before-cwd ../app-main \
//     --after  "npm run start -- -p 4102" --after-cwd  . \
//     [--before-port 4101] [--after-port 4102] [--path /] [--timeout 300] [--logs DIR] \
//     [-- node screenplay.mjs …]
//
// Each command also gets PORT in its environment. The command after `--` gets
// BEFORE_URL and AFTER_URL; when it exits, both servers are stopped and its
// exit code is returned.
//
// A port that already answers is refused, not reused: an old server left on
// it would be measured in place of the build you meant.
import { spawn } from "node:child_process";
import { openSync, readFileSync, mkdirSync } from "node:fs";
import { createConnection } from "node:net";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { parseArgs, sleep } from "./lib.mjs";

const A = parseArgs();
if (!A.before || !A.after) {
  console.error('usage: node serve-pair.mjs --before "CMD" --after "CMD" [--before-port 4101] [--after-port 4102] [--before-cwd DIR] [--after-cwd DIR] [--path /] [-- CMD …]');
  process.exit(2);
}
const logs = resolve(A.logs ?? join(tmpdir(), `ba-serve-${process.pid}`));
mkdirSync(logs, { recursive: true });
const timeout = +(A.timeout ?? 300) * 1000;
const sides = ["before", "after"].map((side, i) => ({
  side, cmd: String(A[side]), cwd: resolve(A[`${side}-cwd`] ?? "."),
  port: +(A[`${side}-port`] ?? 4101 + i), log: join(logs, `${side}.log`),
}));
if (sides[0].port === sides[1].port) throw new Error("before and after need different ports");

const busy = (port) => new Promise((ok) => {
  const s = createConnection({ port, host: "127.0.0.1" });
  s.once("connect", () => { s.destroy(); ok(true); });
  s.once("error", () => ok(false));
});
for (const s of sides) if (await busy(s.port)) {
  console.error(`port ${s.port} (${s.side}) already has a server on it. Stop it, or pick another port — otherwise that server would be measured.`);
  process.exit(1);
}

const kids = [];
for (const s of sides) {
  const fd = openSync(s.log, "a");
  s.proc = spawn(s.cmd, { cwd: s.cwd, shell: true, detached: true, stdio: ["ignore", fd, fd], env: { ...process.env, PORT: String(s.port) } });
  s.exited = null;
  s.proc.on("exit", (code) => { s.exited = code ?? "signal"; });
  kids.push(s.proc);
}
let stopping = false;
const stop = async () => {
  if (stopping) return; stopping = true;
  for (const k of kids) { try { process.kill(-k.pid, "SIGTERM"); } catch {} }
  await sleep(2500);
  for (const k of kids) { try { process.kill(-k.pid, "SIGKILL"); } catch {} }
};
process.on("SIGINT", () => stop().then(() => process.exit(130)));
process.on("SIGTERM", () => stop().then(() => process.exit(143)));

const path = String(A.path ?? "/");
const answers = async (port) => {
  for (const host of ["127.0.0.1", "localhost", "[::1]"]) {
    try { const r = await fetch(`http://${host}:${port}${path}`, { signal: AbortSignal.timeout(3000) }); if (r.status < 500) return true; } catch {}
  }
  return false;
};
const t0 = Date.now();
for (const s of sides) {
  while (!(await answers(s.port))) {
    if (s.exited !== null) {
      console.error(`${s.side} server exited (${s.exited}) before answering on :${s.port}. Last lines of ${s.log}:\n`
        + readFileSync(s.log, "utf8").split("\n").slice(-20).join("\n"));
      await stop(); process.exit(1);
    }
    if (Date.now() - t0 > timeout) { console.error(`${s.side}: nothing answered on :${s.port}${path} within ${timeout / 1000} s (log: ${s.log})`); await stop(); process.exit(1); }
    await sleep(500);
  }
  console.log(`${s.side}: http://localhost:${s.port}  (log ${s.log})`);
}

const env = { ...process.env, BEFORE_URL: `http://localhost:${sides[0].port}`, AFTER_URL: `http://localhost:${sides[1].port}` };
if (A["--"]?.length) {
  const [cmd, ...rest] = A["--"];
  const code = await new Promise((ok) => spawn(cmd, rest, { stdio: "inherit", env }).on("exit", (c) => ok(c ?? 1)));
  await stop();
  process.exit(code);
} else {
  console.log("both up — Ctrl-C to stop");
  setInterval(() => {
    for (const s of sides) if (s.exited !== null && !stopping) { console.error(`${s.side} server exited (${s.exited}); see ${s.log}`); stop().then(() => process.exit(1)); }
  }, 1000);
}
