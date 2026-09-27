// Small helpers shared by the scripts in this folder. Copy the folder as a
// whole; nothing here needs a package.json of its own.
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

/** --key value / --flag / positionals. `--no-x` sets x=false. */
export function parseArgs(argv = process.argv.slice(2)) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--") { out["--"] = argv.slice(i + 1); break; }
    if (!a.startsWith("--")) { out._.push(a); continue; }
    const [k, inline] = a.slice(2).split(/=(.*)/s);
    if (k.startsWith("no-")) { out[k.slice(3)] = false; continue; }
    if (inline !== undefined) out[k] = inline;
    else if (i + 1 < argv.length && !argv[i + 1].startsWith("--")) out[k] = argv[++i];
    else out[k] = true;
  }
  return out;
}

/**
 * Import a package the way the project would: from the current directory
 * first (run the scripts from the project root and they use its playwright),
 * then from next to this file, then a bare import. BA_NODE_PATH points at any
 * other node_modules parent.
 */
export async function importFromProject(...names) {
  const bases = [process.env.BA_NODE_PATH, process.cwd(), new URL(".", import.meta.url).pathname].filter(Boolean);
  for (const name of names) {
    for (const base of bases) {
      try {
        const p = createRequire(base.endsWith("/") ? base : base + "/").resolve(name);
        const mod = await import(pathToFileURL(p).href);
        return mod.default && !mod.chromium ? mod.default : mod;
      } catch { /* try the next place */ }
    }
    try { return await import(name); } catch { /* next name */ }
  }
  throw new Error(`Cannot find ${names.join(" or ")}. Run from a project that has it installed, `
    + `set BA_NODE_PATH to a folder with node_modules/${names[0]}, or: npm i ${names[0]}`);
}

export function probeDuration(file) {
  const r = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file], { encoding: "utf8" });
  const d = parseFloat(r.stdout);
  if (Number.isFinite(d) && d > 0) return d;
  // Playwright's webm often carries no duration header: decode and read the clock.
  const f = spawnSync("ffmpeg", ["-v", "info", "-i", file, "-f", "null", "-"], { encoding: "utf8" });
  const all = [...(f.stderr || "").matchAll(/time=(\d+):(\d+):([\d.]+)/g)];
  if (!all.length) throw new Error(`cannot read the duration of ${file}`);
  const [, h, m, s] = all[all.length - 1];
  return +h * 3600 + +m * 60 + +s;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
