/**
 * Generate TTS narration for a demo screenplay (project-agnostic).
 *
 *   bun run <plugin>/scripts/demo/generate-narration.ts <screenplay-module> [out-dir]
 *
 * The screenplay module (a project-local .ts file) must export:
 *   - BEATS: { id: string; say: string; pace?: string; scene?: string }[]
 *   - NARRATION?: { voice?; speed?; lang?; model?; instructions? }   (optional overrides)
 *
 * For each beat it calls OpenAI TTS once, writes <id>.mp3, measures the spoken
 * duration with ffprobe, and emits narration.json. The capture spec reads
 * narration.json to pace each beat to its spoken length; build-demo.py muxes the
 * clips at their atMs. Output goes to a directory that is a SIBLING of the
 * Playwright capture outputDir, so the per-run outputDir wipe does not delete it.
 *
 * Token: OPENAI_API_KEY env, else ~/.config/video-skill/openai_token.
 *
 * Bundled with the ralph plugin; a project may override it at
 * scripts/preview/generate-narration.ts (three-tier override chain).
 */
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { join, isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const screenplayArg = process.argv[2];
const OUT_DIR = process.argv[3] ?? "test-results/narration";

if (!screenplayArg) {
  console.error("usage: generate-narration.ts <screenplay-module> [out-dir]");
  process.exit(2);
}

// Defaults — overridable per project via the screenplay's NARRATION export.
const DEFAULTS = {
  model: "gpt-4o-mini-tts",
  voice: "nova",
  speed: 1.1, // 10% faster than default — tighter for a product demo
  lang: "de",
  instructions:
    "Sprich in einem ruhigen, freundlichen und klaren Ton, wie ein professioneller Sprecher in einer kurzen Produkt-Demo. Natürliches Tempo, gut verständlich.",
};

interface Beat {
  id: string;
  say: string;
  pace?: string;
  scene?: string;
}

function loadToken(): string {
  if (process.env.OPENAI_API_KEY) return process.env.OPENAI_API_KEY.trim();
  return readFileSync(join(homedir(), ".config/video-skill/openai_token"), "utf8").trim();
}

function durationMs(file: string): number {
  const out = execFileSync(
    "ffprobe",
    ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file],
    { encoding: "utf8" },
  ).trim();
  return Math.round(parseFloat(out) * 1000);
}

async function main() {
  const modPath = isAbsolute(screenplayArg) ? screenplayArg : resolve(process.cwd(), screenplayArg);
  const mod = (await import(pathToFileURL(modPath).href)) as {
    BEATS?: Beat[];
    NARRATION?: Partial<typeof DEFAULTS>;
  };
  const BEATS = mod.BEATS;
  if (!Array.isArray(BEATS) || BEATS.length === 0) {
    throw new Error(`screenplay ${modPath} exports no BEATS array`);
  }
  const cfg = { ...DEFAULTS, ...(mod.NARRATION ?? {}) };

  const token = loadToken();
  mkdirSync(OUT_DIR, { recursive: true });

  const beats: { id: string; text: string; audioFile: string; durationMs: number }[] = [];
  for (const b of BEATS) {
    const mp3 = join(OUT_DIR, `${b.id}.mp3`);
    const res = await fetch("https://api.openai.com/v1/audio/speech", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: cfg.model,
        voice: cfg.voice,
        input: b.say,
        instructions: cfg.instructions,
        speed: cfg.speed,
        response_format: "mp3",
      }),
    });
    if (!res.ok) throw new Error(`TTS failed for ${b.id}: ${res.status} ${await res.text()}`);
    writeFileSync(mp3, Buffer.from(await res.arrayBuffer()));
    const ms = durationMs(mp3);
    beats.push({ id: b.id, text: b.say, audioFile: mp3, durationMs: ms });
    console.log(`[tts] ${b.id}  ${(ms / 1000).toFixed(1)}s  "${b.say.slice(0, 48)}…"`);
  }

  const total = beats.reduce((s, x) => s + x.durationMs, 0);
  const manifest = { model: cfg.model, voice: cfg.voice, lang: cfg.lang, totalMs: total, beats };
  writeFileSync(join(OUT_DIR, "narration.json"), JSON.stringify(manifest, null, 2));
  console.log(
    `\n[tts] ${beats.length} clips, ${(total / 1000).toFixed(1)}s total → ${OUT_DIR}/narration.json`,
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
