# 05 — FULL-FLOW IMPLEMENTATION PLAN · HISTORICAL VIDEO STUDIO V1

**Supersedes:** all Step 03 Pilot / Step 04 pilot-first implementation sequencing in prior versions. **Scope:** implement the complete Windows-only application directly on the new repo; no disposable pilot app, no separate PoC gate, no old Historical-Motion-Graphics-Studio runtime or data migration.
**Product:** English-first 5–10 minute historical motion documentaries from one imported external ChatGPT StoryPackage JSON, with G1–G5 human review, real archive search, G-Labs, TTS+alignment, 10 templates, real Remotion visual editor, MP4 and attribution. One operator Windows-local. No runtime LLM API/Codex agent.

## 1. Engineering rules — one production codebase
- Build exactly once with Python 3.12 FastAPI+SQLite durable jobs and immutable file hashes, React/TS frontend and registered Remotion shared Composition, FFmpeg/ffprobe for audio and QC. Lock Node 22, package manager, Python deps, fonts and renderer versions in checked-in lockfiles before coding.
- All provider calls are via adapters. Every API/UX action must reference a declared OpenAPI operation and typed error. No inert buttons; no generated JSX or raw CSS from imported ChatGPT JSON. Do not regress into hardcoded video-specific code.
- Full V1 feature breadth cannot be passed on mocks: adapters require contract+offline tests, real provider operations need operator credentials and must be reported separately if unavailable. No live G-Labs account test required before coding from provided original webhook; final integration acceptance is user-led after full flow is implemented.
- Keep **one coherent implementation branch/PR** unless user explicitly asks otherwise; incremental exact-SHA Windows test gates, self-review once per major workstream, no merge/push main without approval. Only implementation of the user-agreed scope; no multi-tenant accounts, Ubuntu build, arbitrary extra phase count or old data compatibility.

## 2. Target package layout (implementation, not current code)
backend/app/api/ — OpenAPI FastAPI route handlers, revision checks, contracts, error model
backend/app/projects/ — project state, import, G1–G5 transactions, audit ledger
backend/app/jobs/ — persistent local queue, retry, idempotency, cancel, crash recovery
backend/app/voice/ — Kokoro/ElevenLabs TTS, section attempts, correction, WAV assembly, ElevenLabs Forced Alignment
backend/app/archives/ — Wikimedia Commons / LOC / Europeana search/hydrate/download
backend/app/assets/ — original storage, provenance, G3 rights, manual upload, G-Labs provider, fallback candidates, treatments
backend/app/maps/ — period map ingestion/CRS conversion/verified geometry/label layout
backend/app/director/ — StoryPackage→VisualBlueprint→CompiledTimeline compiler with layout/motion registries
backend/app/render/ — Remotion render jobs, FFmpeg mux/QC, credits, G5 export
frontend/src/ — six real workspaces with shared client contracts, job feedback, Remotion Player and scene/asset editor
renderer/remotion/ — shared pinned HistoryComposition and T01–T10 scene components with 30 variants
contracts/ — 12 schema shapes, sample inputs, full-flow API, original G-Labs doc, archive provider specs, registries
tests/ — Windows-only contract/unit/API/functional/browser/e2e (no dummy success assertions)

## 3. Dependency topology and parallel work
**Foundation lane** schema+DB+jobs+gate transitions → API and frontend shell. **Media lane** TTS adapters+WAV/align and archives+G-Labs/manual upload can run in parallel *after* foundation artifact interfaces exist. **Visual lane** template registry, historical maps and deterministic compiler can be built in parallel from frozen contracts; integration requires final audio/approved source artifacts. **Delivery lane** Remotion Player/render shared composition, QC/credits and Windows packaging depend on validated timeline; start UI design earlier using typed mock fixtures, replace mocked services before acceptance.
User review ordering: G1 → [G2 voice, G3 assets parallel] → G2 approval triggers assemble+align → aligned/G3 exact approved inputs → G4 editor/approve → render+QC → G5 approved export. No provider task auto-approves.

## 4. Two engineering phases, four parallel workstreams — not a disposable pilot
### Phase A — Complete foundational production workflow
**A1 Story/DB/jobs/Gates:** strict 12 JSON Schema+semantic validators, SQLite migrations only for this fresh V1 state, all tables and revision hashes, G1–G5 transactional state and selective invalidation; durable queue, idempotency, scoped cancel and resume after worker crash; typed problem error catalog. Implement all declared API endpoints and active six-workspace frontend skeleton. No hidden separate G2 alignment button.
**A2 Audio:** Kokoro and ElevenLabs TTS adapters, section regenerate/correction/select past attempt, audio attempt provenance, playable preview, FFmpeg final WAV assembly with sample offsets, ElevenLabs forced alignment over exact final audio and transcript (English), word-level QC + failure/retry, G2 approval auto-assembly/alignment. All failed tasks remain recoverable without lying about success.
**A3 Archive+G-Labs:** Wikimedia Commons, LOC, Europeana provider adapters including search/page/record details, rights normalization, provenance and immutable original file download. G-Labs from verbatim 1148-line supplied webhook: 202 job, X-API-Key, poll 3–5 s, result download, cancel task_id, error taxonomy, MAX/provider health; account credentials handled via UI. Manual Search+Upload vs Managed Fallback+mandatory later review implemented in G3. No AI-generated reconstruction reclassified archival.
**Phase A exit:** all real screens/actions and provider connectors are implemented to the agreed contract; Windows mock/contract tests green. No claim of whole production PASS yet.

### Phase B — Complete full visual production and shipping
**B1 Storyboard compiler:** one imported StoryPackage with full semantic direction; normalized VisualBlueprint; pinned 30 template layouts, 18 presets, validated historical maps/GeoJSON, exact asset/cue binding, all layer pixel rectangles/crops/masks/fonts/z-order, deterministic motion and camera keyframes, scene transitions and SHA-based revision; no historical data invented by renderer.
**B2 Full renderer/editor:** all 10 T01–T10 React templates, A/B/C variants, map routes/territory overlays, archival document zoom/cutout/typography, composited motion, reading time and overflow diagnostics. Real @remotion/player G4 editor supports editable scene layout, crop, asset switching to approved only, cue retiming, compare attempts and selective recompute. Node Remotion render uses same HistoryComposition, frozen fonts and media bytes.
**B3 QC/delivery:** MP4 H.264/AAC 1920×1080 30fps, audio waveform continuity, timestamps from alignment, frame parity, visual collision/black-frame checks, attribution manifest, source/AI disclosure, render attempts, G5 operator preview/sign-off and export bundle. UI job queue, bulk asset review, crash resume, Windows one-click start, docs and backup.
**Phase B exit:** fully integrated 5–10min real English historical documentary and second different-topic package through same engine+template code, with actual approved media, source provenance, complete gate history, restart and negative regression tests, Windows packaged launcher. No separate 60–90s pilot phase; small engineering render smoke tests are allowed and do not count as product milestone.

## 5. Acceptance gates (strict)
**Contract & backend:** schema parsing + semantic, 24-section/48-scene synthetic long-form fixture, cross-stage content identity, cue occurrence, approval SHA CAS, false gate transitions rejected, selective invalidation, real durable job persistence/crash recovery. Negative fixtures for untrusted code, wrong map years, invalid geometry and unknown presets. No migration of old studio data.
**Voice:** both TTS adapters interface-tested; real English synthesis and ElevenLabs alignment (when credentials supplied), section regeneration/reuse of approved attempts, final WAV checks exact duration and monotonic word samples, alignment failure blocks G4 not G2 decision history.
**Archives/G-Labs:** all three adapters mock pagination/hydration/media/rights/429 and live sample where access allowed; G-Labs mock 202/status/completed/result/failed/stop and user-led live check when available. Unknown rights never marked eligible, candidate never auto-approved, 2-path missing resolution tested end-to-end. User can still use manually approved materials if API offline; never claim auto archive source succeeded.
**Historical map:** reproject sourced geometry into WGS84, checked 1914/1871 validity, GeoJSON label anchors and route, exact vs schematic disclosure, compare in same projected viewport. Negative wrong era / modern borders / CRS mismatch / unknown feature ids.
**Visual/Editor:** all T01–T10 template variants fixture tested, text collision and mask/card fallback same source, no hidden missing asset substitutions, 60+ scenes load with responsive editor, one asset/crop update recomputes affected scene only, Player and video use identical composition.
**Video/G5:** actual full-length MP4 output, FFprobe 1080p/30fps/audio duration, no unexplained dropped frames/black frames, attribution/report, user review G1–G5. Final G5 approve of stale render must fail. Second unrelated historical package proves reuse without modifying template JSX.
**Windows:** run native Windows 10/11 Python 3.12/Node 22/FFmpeg; one-click launcher, local 127.0.0.1, no Ubuntu requirement, no Docker/cloud dependency, restarts preserve jobs and approvals. Provider secrets redacted.

## 6. Test matrix and reporting
Contract fixtures: schema (positive/negative), long-form relationships, OpenAPI spec semantic sanity.
Unit: template registry, camera interpolation, source metadata normalization, historical map transform, voice sample offsets.
API: all G1–G5 operations, invalid revision/race, idempotent retry, remove/regenerate/crop/export, missing asset choice.
Windows integration: real SQLite/local filesystem/restart; FFmpeg installed; Remotion Player and renderer same input; provider call errors.
Browser: six workspaces and all clickable actions, async feedback, correct gate blockers and batch G3 decisions.
Visual: at least two editorial topics with different maps, people and evidentiary assets; six-role quality review not checklist-only.
Reports: exact branch/commit SHA, commands + OS, PASS/FAIL/SKIP separated by mocks and live provider, artifacts/hashes/screenshots, unresolved issues categorized by blocking scope. No fake live pass.

## 7. Build-stop rules
No staging a demo as full app, no additional pilot PR, no elaborate multi-tenant/security/network stack, no source-by-source video hardcoding, no G-Labs runtime live account dependency before adapter coding, no untested asset rights approvals. Blocking technical failure must be fixed in owning full-flow workstream; optional polish can be documented without reopening prior architecture continuously.

## 8. Handoff reference order
1. docs/design/DESIGN_DECISIONS_2026-10-19.md for user overrides (English-first, G-Labs contract-first, five gates).
2. docs/step01-02/FULL_FLOW_VISUAL_COMPILER_CONTRACT.md + HISTORICAL_MAP_ENGINE.md + 01–04 independent docs.
3. contracts/schema/ twelve schema files; contracts/registries/ 30 layouts and 18 presets; contracts/openapi.yaml.
4. contracts/providers/reference/WEBHOOK_INTEGRATION.vi(1).md verbatim; three archive adapters and ElevenLabs alignment docs.
5. ui/mockups/index.html as interaction UX design reference only, not real frontend.
6. This implementation plan as **sole current execution roadmap**. Earlier Master Spec M0–M4 and pilot descriptions are historical, not implementation milestones.

**Final acceptance:** Full V1 flow delivered on Windows; no plan to require a sacrificial pilot first.
