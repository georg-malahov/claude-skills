/**
 * Demo screenplay — the single source of truth for the narrated walkthrough.
 *
 * `/ralph demo` (re)generates the BEATS below from the plan + `git diff main...HEAD`,
 * then drives: TTS (generate-narration.ts) → paced capture (your *-demo.spec.ts) →
 * mux (build-demo.py). Keep one beat per discrete thing the narrator says; the
 * capture spec matches beats by `id`.
 *
 * Contract:
 *   - BEATS: ordered array. Each beat:
 *       id     — stable, referenced by the capture spec (e.g. "b03"). Don't renumber casually.
 *       say    — the narration line (the page caption is derived from it verbatim).
 *       pace   — "emphasize" | "normal" | "compress": tail hold after the spoken line.
 *       scene  — chapter label; the FIRST beat of each new scene starts a chapter.
 *   - NARRATION (optional): voice/lang/speed/instructions overrides for the TTS step.
 *
 * Pacing is narration-driven: the capture spec records each beat's atMs, performs the
 * action, then holds for the spoken duration (from narration.json) + the pace tail.
 * Seed data in the spec's beforeAll/setup, NEVER inline during a recorded beat —
 * inline seeding shows as dead air in the final video.
 */

export const NARRATION = {
  voice: "nova",
  lang: "de",
  speed: 1.1,
  // instructions: "Sprich Deutsch in einem ruhigen, klaren Demo-Ton.",
};

export interface Beat {
  id: string;
  say: string;
  pace: "emphasize" | "normal" | "compress";
  scene: string;
}

// Replace with beats generated from your plan + diff. Example shape:
export const BEATS: Beat[] = [
  { id: "b01", say: "Kurzer Überblick: das ist die neue Funktion.", pace: "emphasize", scene: "Überblick" },
  { id: "b02", say: "Hier öffnen wir die Ansicht und sehen die wichtigsten Elemente.", pace: "normal", scene: "Überblick" },
  // …
];

/** Tail hold (ms) added after each beat's spoken line, by pace. */
export const PACE_TAIL_MS: Record<Beat["pace"], number> = {
  emphasize: 1300,
  normal: 450,
  compress: 150,
};
