---
name: historical-video-studio
description: Implement and repair the Windows-local Historical Video Studio full-flow pipeline with exact gates, evidence lineage, deterministic scene composition and lean behavioral tests.
---

# Historical Video Studio — implementation skill

Load `AGENTS.md`, `docs/engineering/CODING_RULES.md`, `docs/step01-02/IMPLEMENTATION_TASK_MATRIX.md` and the owner work-package section of `docs/step01-02/05_IMPLEMENTATION_PLAN.md` first. Use existing `scripts/check_design_contracts.py` and `scripts/validate_visual_design.py` to check the baseline; never use them to claim media was rendered.

## Select the correct lane
- **A1 Foundation:** contracts/schema + core/extension OpenAPI → Python/TS models → SQLite transaction/gates/revisions → durable job queue → typed API and six UI workspaces.
- **A2 Voice:** Kokoro or ElevenLabs → section attempts/correction → approved final WAV → automatic ElevenLabs Forced Alignment → word IDs and sample-aligned frame cues. G2 is the only human voice approval.
- **A3 Historical Assets:** Wikimedia, LOC, Europeana or manual/G-Labs source → normalized evidence/rights → immutable byte hashes → G3 approval. Managed fallback is a candidate only.
- **B1 Director:** external StoryPackage → typed VisualBlueprint (10 template payloads) → frozen CompiledTimeline (camera/staging/motion/source) from aligned words + approved media. Geo route is period-reviewed; editorial arrows have distinct connector preset.
- **B2 Visual Renderer:** 10 T01–T10 templates, 30 genuinely different layout variants, 19 specialized presets → single deterministic shared Remotion Composition + real Player and editor with approved-source-only changes.
- **B3 Delivery:** render + ffprobe/audio QC + source attribution → G5 operator approval → final MP4/export + native Windows launch/restart.

## Work loop
1. Read the task ID, inputs/outputs/dependencies and offline-vs-live acceptance.
2. Inspect code and tests; implement the smallest behavior-producing change in the correct owner module.
3. Check source lineage, gate eligibility and the affected downstream revisions.
4. Run the task's Windows smoke/test command; don't fabricate unavailable commands or call a planned command “already passing”.
5. Self-review 8 lenses as applicable: director, editor, motion designer, architect, QA, solo operator, senior full-stack, BA; focus on failures in **this task**, do not expand into unrequested phase work.
6. Report exact SHA, user-observable result, offline/live results, blockers, `git diff --stat` and code/test growth.

## Acceptance truth
A test fixture checks representation only. A mocked TTS/source/G-Labs response checks adapter behavior only. A Remotion frame check demonstrates render logic only. Full PASS requires authentic approved inputs, one full 5–10-minute MP4, another topic with no custom JSX and G1–G5 human review. Do not create a pilot product or new architecture to make tests pass.
