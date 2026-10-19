# FULL-FLOW IMPLEMENTATION TASK MATRIX — Execution Ready

**Repository:** plthien/Historical-Video-Studio • **Execution authority:** [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md), Visual Contract V1.1, 12 strict JSON Schemas, 30 layout variants and 19 specialized motion grammars. **No pilot product.** Two phases, **35 tasks** in A1–B3. All paths below are TARGET IMPLEMENTATION PATHS, not existing runtime code. This file records what Codex must create, not what already runs.

## 0. How to execute and how not to inflate the codebase

- Read `AGENTS.md`, `docs/engineering/CODING_RULES.md` and `.agents/skills/historical-video-studio/SKILL.md`. Take one task ID at a time. Preserve its module owner; satisfy dependencies before work, not by creating mocks that impersonate approved upstream output.
- **Exactly two engineering phases** A and B; packages A1/A2/A3 and B1/B2/B3 are workstreams, **not** extra PR/phase gates. One production implementation branch/PR, no push/merge to main without user approval. Parallelize only after stable immutable contract interfaces exist.
- **Two test classes per task:** (i) Windows offline/mock/unit/contract (network mocked at boundary, fast CI); (ii) Windows local/real integration, using real SQLite/FFmpeg/Remotion or provider API and operator credentials. Results always labeled OFFLINE_PASS, LOCAL_PASS, LIVE_PASS, BLOCKED, SKIPPED or FAIL; do not collapse them into one green label.
- **Command convention:** Commands shown here for future modules (pytest targets, `backend.tools.smoke`, `npm ... test:frames`, Playwright, PowerShell launcher) are **requirements for Codex to implement**, not runnable today. A1-01 creates/pins these runners and versioned tooling. Current design-only baseline can run now: `py -3.12 -m pip install -r requirements-design.txt; py -3.12 scripts/check_design_contracts.py; py -3.12 scripts/validate_visual_design.py; py -3.12 -m unittest discover -s tests/contracts -p "test_*.py" -v`.
- **Windows PowerShell** from repository root; semicolon-separated commands denote sequential executions. A `--mode live` command must verify real tool/provider outputs and be user-authorized; no secrets recorded. For GitHub CI, add real Windows test jobs when their task's runner exists, never dummy green CI steps.
- **Test economics:** reuse consolidated test modules per lane; `-k` filters identify behavior, NOT license to manufacture a test per field. If closest existing test covers failure, extend it; mock-only cannot certify video or external API. For a fix, show pre-fix failing assertion or equivalent reproducible failure, then post-fix PASS plus `git diff --stat`.
- **Acceptance at task level:** owner behavior works, observable output exists, relevant invariant/failure proved, no unwarranted compatibility/new abstraction; actual external credentials unavailable => provider live result BLOCKED and recorded against task ID without lying or adding an unrelated workstream.

## 1. Dependency graph and phase ordering

```text
Phase A
A1-01 → A1-02 → A1-03 → A1-04 → A1-05 → A1-06
                           ├─ A2-01 → A2-02 → A2-03 → A2-04 → A2-05
                           └─ A3-01 → A3-02 → A3-03 → A3-04 → A3-05
                                   cross-check A3-06 (A1/A2/A3)
Phase B (from frozen Phase A interfaces; independent visual work can start earlier)
B1-01 + B1-02 + A2-04 → B1-03 → B1-04 → B1-05 → B1-06
B1-06 → B2-01 → B2-02 and B2-03 → B2-04 → B2-05 → B2-06
B2-06 → B3-01 → B3-02 → B3-03
                   └─ B3-04 → B3-05 → B3-06
```
**Use each task's explicit Depends below as canonical** when this simplified graph skips a lateral dependency. The graph does not add separate milestones/pilots.

## A1 — Foundation / project + gates + API

### A1-01 — Foundation toolchain & test harness

**Owner modules:** `backend/pyproject.toml; frontend/package.json; renderer/package.json; scripts/windows/verify-environment.ps1`

**Depends:** none (phase A entry). **Input contract:** Python 3.12; Node 22; npm; FFmpeg/ffprobe; design schemas. **Output contract:** Pinned dependency/lock files; Windows environment checker; consolidated pytest/Playwright/Remotion smoke command entrypoints.

**Acceptance:** Fresh Windows checkout installs and checks versions; no Ubuntu CI/Docker; no green placeholder tests.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pip install -r requirements-design.txt; py -3.12 scripts/check_design_contracts.py; py -3.12 scripts/validate_visual_design.py`

**Windows LOCAL/LIVE integration command (planned):** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/verify-environment.ps1`

### A1-02 — Schema/API types & import validation

**Owner modules:** `backend/app/contracts/; frontend/src/api/generated/; backend/app/api/imports.py`

**Depends:** `A1-01`. **Input contract:** 12 canonical JSON Schemas; OpenAPI core and 26-operation extension; external StoryPackage. **Output contract:** Validated immutable story candidate; Python/TS types generated from same schema versions; typed error detail.

**Acceptance:** Valid 24-section import; oneOf 10 visual payloads parsed; unknown code/refs rejected with actionable path; no duplicate model forks.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/backend/test_foundation.py -k 'schema or import'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case story-import --mode local`

### A1-03 — SQLite persistence + immutable artifacts

**Owner modules:** `backend/app/projects/storage.py; backend/app/assets/store.py; backend/app/projects/models.py`

**Depends:** `A1-02`. **Input contract:** Story candidate, media bytes+SHA, project ID/revision. **Output contract:** SQLite durable revisions, content-addressed media, atomically written artifact metadata.

**Acceptance:** Cold reopen preserves exact approval candidate and original bytes; corrupt/mismatched hash fails closed; transaction rollback leaves no partial revision.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/backend/test_foundation.py -k 'storage or artifact'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case reopen-project --mode local`

### A1-04 — G1–G5 gate state + invalidation

**Owner modules:** `backend/app/projects/gates.py; backend/app/projects/revisions.py`

**Depends:** `A1-03`. **Input contract:** ApprovalRecord.v1; candidate revision, dependency fingerprint, gate rules. **Output contract:** Transactional gate events; selective stale graph; protected G1/G3 provenance.

**Acceptance:** G1 before critical claim review and G4 without G2 alignment/G3 approvals rejected; crop edit invalidates G4/G5 only; stale SHA conflict rejected.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/backend/test_foundation.py -k 'gate or invalidation or revision'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case gate-transitions --mode local`

### A1-05 — Persistent queue + retry/cancel

**Owner modules:** `backend/app/jobs/queue.py; backend/app/jobs/worker.py; backend/app/jobs/recovery.py`

**Depends:** `A1-03`, `A1-04`. **Input contract:** RenderJob.v1; idempotency key; provider task IDs. **Output contract:** Durable job status, scoped cancel, retry policy, restart recovery.

**Acceptance:** Killed worker resumes exactly once per operation identity; cancellation cannot stop other tasks; original error preserved, not fake success.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/backend/test_foundation.py -k 'queue or restart or cancel'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case restart-running-job --mode local`

### A1-06 — Real API surface + UI shell

**Owner modules:** `backend/app/api/; frontend/src/routes/; frontend/src/api/client.ts`

**Depends:** `A1-02`, `A1-04`, `A1-05`. **Input contract:** Merged non-overlap OpenAPI; A1-02 types; A1-04 gates; A1-05 queue; UI wireframe. **Output contract:** Revision-aware API handlers & six workspaces, functional supported actions, pending/error state.

**Acceptance:** No inert buttons; unsupported future workstream operation visibly disabled with blocker; Idempotency-Key and 409 stale revision effective.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/backend/test_foundation.py -k 'api or idempotency'; npm --prefix frontend run test:e2e -- --grep 'project-shell'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case api-and-ui --mode local`

## A2 — Voice / alignment

### A2-01 — TTS adapters & identity

**Owner modules:** `backend/app/voice/providers/kokoro.py; backend/app/voice/providers/elevenlabs.py`

**Depends:** `A1-02`, `A1-03`, `A1-05`. **Input contract:** VoiceRequest.v1; G1-approved section text; provider/voice settings. **Output contract:** Versioned provider attempts with identity, raw WAV metadata and transport error.

**Acceptance:** Kokoro and ElevenLabs calls contract-validated; invalid provider identity fails; HTTP errors cannot produce audio success.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/voice/test_voice_pipeline.py -k 'tts or identity or transport'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case tts-kokoro --mode live; py -3.12 -m backend.tools.smoke --case tts-elevenlabs --mode live`

### A2-02 — Regenerate/restore/correction

**Owner modules:** `backend/app/voice/attempts.py; backend/app/voice/correction.py; backend/app/api/voice.py`

**Depends:** `A2-01`, `A1-04`. **Input contract:** Selected immutable TTS attempts, section source SHA, 26-operation API extension. **Output contract:** New attempt, previous-attempt restoration, FFmpeg bounded correction, lineage+states.

**Acceptance:** Only target section regenerated/corrected; restore previous exact SHA and frozen transcript; active request shows state; no accidental G1 mutation.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/voice/test_voice_pipeline.py -k 'attempt or correction or regenerate'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case section-repair --mode local`

### A2-03 — G2 assembly & final WAV

**Owner modules:** `backend/app/voice/assemble.py; backend/app/voice/qc.py`

**Depends:** `A2-02`, `A1-04`, `A1-05`. **Input contract:** G2 section approvals; selected WAV attempts, story SHA. **Output contract:** FinalAudio.v1 WAV, section sample offsets, immutable transcript SHA.

**Acceptance:** Approve Voice triggers one assembly job; no separate user button; exact sample count/offsets match assembled WAV; failures recoverable.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/voice/test_voice_pipeline.py -k 'assemble or sample or final_wav'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case final-wav --mode local`

### A2-04 — ElevenLabs final-WAV alignment

**Owner modules:** `backend/app/voice/alignment.py; backend/app/voice/word_map.py`

**Depends:** `A2-03`. **Input contract:** FinalAudio.v1 + exact transcript; ElevenLabs alignment contract. **Output contract:** WordTimingMap.v1, anomalies, audio+transcript+section lineage.

**Acceptance:** Aligned word samples monotonic/in bounds and verified transcript; failed/stale map blocks G4; TTS source can be Kokoro or ElevenLabs.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/voice/test_voice_pipeline.py -k 'alignment or word_map or stale'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case alignment-elevenlabs --mode live`

### A2-05 — Voice Studio UI & G2 review

**Owner modules:** `frontend/src/workspaces/Voice/; frontend/src/api/voice.ts`

**Depends:** `A2-02`, `A2-03`, `A2-04`, `A1-06`. **Input contract:** A2-01..04 APIs; audio attempt states and QC. **Output contract:** Playable per-section attempts, correction feedback, G2 approval, post-approval alignment states.

**Acceptance:** UI shows immediate pending, error and final WAV/word map; selected attempt and segment status persist after refresh; no sixth gate.

**Windows OFFLINE/MOCK command (planned):** `npm --prefix frontend run test:e2e -- --grep 'voice-workflow'; py -3.12 -m pytest -q tests/voice/test_voice_pipeline.py -k 'gate_2'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case voice-ui --mode local`

## A3 — Archive / G-Labs / G3

### A3-01 — Three archive adapters

**Owner modules:** `backend/app/archives/{wikimedia,loc,europeana}.py; backend/app/archives/interfaces.py`

**Depends:** `A1-02`, `A1-05`. **Input contract:** AssetRequirement; source adapter contracts; keyed Europeana settings. **Output contract:** Search/hydrate/page candidates with raw metadata, source URLs and explicit rights unknown.

**Acceptance:** All 3 adapters page and hydrate real response shapes; 429/404/invalid key propagated; results never auto-approved.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/assets/test_sources.py -k 'search or paging or hydrate'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case archives-all --mode live`

### A3-02 — Source download & G3 evidence

**Owner modules:** `backend/app/assets/provenance.py; backend/app/assets/download.py`

**Depends:** `A3-01`, `A1-03`, `A1-04`. **Input contract:** Candidates A3-01, HistoricalAsset.v1, user-supplied files, source/rights evidence. **Output contract:** Immutable media bytes, documented exactness+license review, versioned G3 decisions.

**Acceptance:** Thumbnail is not original by assumption; wrong-era/unknown rights remain unresolved; raw original SHA and approved variant bound.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/assets/test_sources.py -k 'rights or download or provenance'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case archive-original-download --mode live`

### A3-03 — G-Labs original-webhook adapter

**Owner modules:** `backend/app/assets/providers/glabs.py; backend/app/jobs/provider_tasks.py`

**Depends:** `A1-05`, `A3-02`. **Input contract:** Verbatim G-Labs webhook spec; X-API-Key; G3 resolution authorization. **Output contract:** Scoped async task-id/status/result/cancel; AI_ILLUSTRATION asset candidate.

**Acceptance:** 202/poll/completed/error/499 scoped stop correctly mapped; no auto G3 approval; API secret redacted.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/assets/test_glabs.py -k 'generate or poll or stop or error'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case glabs-image --mode live`

### A3-04 — Missing-asset decision & approval

**Owner modules:** `backend/app/assets/resolution.py; backend/app/api/assets.py`

**Depends:** `A3-02`, `A3-03`, `A1-04`. **Input contract:** AssetResolution.v1; G3 rights+candidate; manual or managed option. **Output contract:** MANUAL_UPLOAD or MANAGED_FALLBACK authorization; re-reviewed candidate; approved G3 snapshot.

**Acceptance:** Missing exact asset never silently substituted; explicit choice and second approval enforced; stale candidate cannot approve.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/assets/test_sources.py -k 'resolution or candidate or gate_3'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case missing-asset-choice --mode local`

### A3-05 — Asset Library/UI & provider settings

**Owner modules:** `frontend/src/workspaces/Assets/; frontend/src/workspaces/Settings/`

**Depends:** `A3-04`, `A1-06`. **Input contract:** A3-01..04 APIs; source metadata and candidate variants. **Output contract:** Search, review, upload, managed fallback, batch approval UI + redacted provider health.

**Acceptance:** No false open-now/provider ready, candidate/approved states differentiated, batch only approved exact SHA; restart retains choices.

**Windows OFFLINE/MOCK command (planned):** `npm --prefix frontend run test:e2e -- --grep 'asset-review'; py -3.12 -m pytest -q tests/assets/test_sources.py -k 'batch_approval'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case asset-ui --mode local`

### A3-06 — Phase A adapter & gates integration

**Owner modules:** `tests/integration/test_phase_a.py; backend/tools/smoke.py`

**Depends:** `A1-06`, `A2-05`, `A3-05`. **Input contract:** A1, A2, A3 completed offline lanes, real SQLite/store/queue. **Output contract:** Phase A evidence report with provider statuses PASS/BLOCKED/NOT_RUN separated.

**Acceptance:** Story→G1→G2 WAV/align job and G3 two-path rights flow survive restart; failure injection does not bypass G4 blockers; live providers reported distinctly.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/integration/test_phase_a.py`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case phase-a --mode local`

### Phase A exit — frozen checklist (do not expand Phase A)

- [ ] A1-01..06, A2-01..05, A3-01..06 have ownership-complete code, non-inert UI interactions and checked-in evidence of relevant offline tests; code is in **one production branch**.
- [ ] External StoryPackage accepted and invalid content rejected; SQLite G1–G5 revision graph and queue survive actual process restart. Actual G1 critical-claim blockers and G2/G3 parallel independence verified.
- [ ] Both TTS adapters, audio attempt correction/restore, G2-triggered final WAV + alignment contract verified; unavailable external ElevenLabs/Kokoro live checks marked BLOCKED, not PASS. No claim of full G4 readiness without verified real word map.
- [ ] Three archive adapters normalize source/rights and fail closed; G-Labs original-webhook async contract implemented; manual and managed missing-source branches keep G3 second approval mandatory. Live provider status per provider explicitly PASS/BLOCKED/SKIPPED with credentials note (no secrets).
- [ ] Windows environment, API/UI shell, job queue, source download, local storage and A1/A2/A3 integration command evidence logged at **one exact commit SHA**. No mock is called historical fact verification.
- [ ] Phase A code/test growth justified, nearest duplicate tests consolidated, no speculative B1–B3 renderer code for convenience, no Linux CI, no previous-tool migration. Operator approval of Phase A scope gate recorded.

**Exit classification:** PHASE_A_PASS if all in-scope offline/local gates pass and any credential-dependent LIVE check is separately BLOCKED with explicit operator deferral; **full V1 remains NOT PASS**. Real audio/rights/render assertions cannot be waived by offline PASS. If a missing provider credential blocks live smoke, carry the same test to B3-06 as a known integration dependency; do not add a new phase.

## B1 — Visual Director / compiler

### B1-01 — Typed visual normalizer

**Owner modules:** `backend/app/director/blueprint.py; backend/app/director/template_payloads.py`

**Depends:** `A1-02`, `A1-04`. **Input contract:** G1 StoryPackage visual_beats, VisualBlueprint.v1, 10 discriminated payloads, 30 layouts. **Output contract:** Revisioned VisualBlueprint with exact role cardinality/claims/slots and carry groups.

**Acceptance:** Unknown focus, card reveal duplicate, wrong quote semantics, missing two-map state rejected; no fabricated historical claim.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/visual/test_compiler.py -k 'blueprint or payload or role'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case normalize-visual --mode local`

### B1-02 — Historical map ingestion/projection

**Owner modules:** `backend/app/maps/ingest.py; backend/app/maps/projection.py`

**Depends:** `A3-02`, `A1-03`. **Input contract:** HistoricalMap.v1, raw GeoJSON/GPKG/raster and G3 period approval. **Output contract:** Pinned WGS84 geometry; projection/viewport feature IDs and source SHA.

**Acceptance:** 1914 request rejects modern border; wrong CRS/feature rejected; derived polygons and route preserve rights/period disclosure.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/visual/test_compiler.py -k 'map or projection or period'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case historical-map --mode local`

### B1-03 — Audio word-cued frame planning

**Owner modules:** `backend/app/director/timing.py; backend/app/director/staging.py`

**Depends:** `A2-04`, `B1-01`. **Input contract:** Verified WordTimingMap from A2-04; G1 beat cue phrase+occurrence. **Output contract:** Frame-accurate beat sequence, scene-local windows, stable focus transitions.

**Acceptance:** Phrase/occurrence resolves unique word; frame rounding uses WAV sample rate; no negative/inverted scene or cumulative drift.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/visual/test_compiler.py -k 'cue or timing or staging'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case align-scene-cues --mode local`

### B1-04 — Layer geometry, typography & source slots

**Owner modules:** `backend/app/director/layout.py; backend/app/director/layers.py`

**Depends:** `B1-01`, `A3-04`. **Input contract:** B1-01 Blueprint; A3-04 approved assets; template layout registry and font metrics. **Output contract:** Pixel rects, source_asset_slot_id, crop/masks, treatment, typography, group hierarchy.

**Acceptance:** T03 has independent cards, T07 2 distinct period maps, T04 route/map separate; overflows block or typed fallback same source only.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/visual/test_compiler.py -k 'layers or typography or slots'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case compile-layout --mode local`

### B1-05 — Nineteen motion grammars & camera

**Owner modules:** `backend/app/director/motion.py; backend/app/director/camera.py`

**Depends:** `B1-02`, `B1-03`, `B1-04`. **Input contract:** 19 pinned presets, typed params/phase_recipe, groups, source geometry, B1-03 cues. **Output contract:** CompiledTimeline events, camera focus path/keyframes, animation parameter lineage.

**Acceptance:** Geographic route uses reviewed linestring; editorial connector separate; deterministic camera/depth/stagger phases, invalid params block.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/visual/test_compiler.py -k 'motion or camera or connector'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case compile-motion --mode local`

### B1-06 — Frozen compiler, provenance & invalidation

**Owner modules:** `backend/app/director/compiler.py; backend/app/director/fingerprint.py`

**Depends:** `B1-02`, `B1-05`, `A1-04`. **Input contract:** B1-01..05, G2 final WAV+alignment, G3 approved source snapshot, revisions. **Output contract:** CompiledTimeline.v1 immutable dependency manifest; selective G4 recompute diagnostics.

**Acceptance:** Same input hashes produce identical output; scene edit preserves G1 facts/G3 rights; stale audio/asset blocks; 48-scene fixture valid.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/visual/test_compiler.py -k 'fingerprint or invariant or deterministic'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case compile-longform --mode local`

## B2 — Remotion / Editor

### B2-01 — Shared Remotion composition foundation

**Owner modules:** `renderer/remotion/HistoryComposition.tsx; renderer/remotion/schema.ts; renderer/package.json`

**Depends:** `B1-06`, `A1-01`. **Input contract:** CompiledTimeline.v1, immutable audio/media/font manifest, template and motion registries. **Output contract:** Single Player and Node render Composition with frame-addressed deterministic layers.

**Acceptance:** Same frame/props produce identical pixel data; no network/random/clock calls during render; text loads frozen font.

**Windows OFFLINE/MOCK command (planned):** `npm --prefix renderer run test:frames -- --case shared-composition`

**Windows LOCAL/LIVE integration command (planned):** `npm --prefix renderer run render:smoke -- --case single-scene`

### B2-02 — T01–T05 real scene implementations

**Owner modules:** `renderer/remotion/templates/{T01,T02,T03,T04,T05}.tsx`

**Depends:** `B2-01`, `B1-02`. **Input contract:** Typed T01–T05 payloads and CompiledTimeline layers; historical maps; approved originals. **Output contract:** Geographic map/portrait/collage/route/timeline React visuals and A/B/C layouts.

**Acceptance:** Multi-layer cards independently staged; reviewed route draws and waypoint progress; 2–6 events chronology true; no generic one-photo fallback.

**Windows OFFLINE/MOCK command (planned):** `npm --prefix renderer run test:frames -- --templates T01,T02,T03,T04,T05`

**Windows LOCAL/LIVE integration command (planned):** `npm --prefix renderer run render:smoke -- --templates T01,T02,T03,T04,T05`

### B2-03 — T06–T10 real scene implementations

**Owner modules:** `renderer/remotion/templates/{T06,T07,T08,T09,T10}.tsx`

**Depends:** `B2-01`, `B1-02`. **Input contract:** Typed T06–T10 payloads, approved documentary claim refs, paired historic maps. **Output contract:** Document focus/maps comparison/fact/quote/consequence React visuals A/B/C.

**Acceptance:** Source quote not fabricated; dual maps share projection; count-up truth; causal graph uses editorial connector not historical route.

**Windows OFFLINE/MOCK command (planned):** `npm --prefix renderer run test:frames -- --templates T06,T07,T08,T09,T10`

**Windows LOCAL/LIVE integration command (planned):** `npm --prefix renderer run render:smoke -- --templates T06,T07,T08,T09,T10`

### B2-04 — Motion compositor/typography/masks

**Owner modules:** `renderer/remotion/motion/; renderer/remotion/typography/; renderer/remotion/media/`

**Depends:** `B2-02`, `B2-03`. **Input contract:** B2-02, B2-03, B1-05 keyframes/phase recipes; original media derivatives. **Output contract:** Transform hierarchy, readable text, crop/feather/cutout/parallax output with controlled presets.

**Acceptance:** All 19 preset evaluators distinguish transform spaces; G3 original never mutated; enter/hold/exit frames don't crop critical text.

**Windows OFFLINE/MOCK command (planned):** `npm --prefix renderer run test:frames -- --case motion-phases`

**Windows LOCAL/LIVE integration command (planned):** `npm --prefix renderer run render:smoke -- --case multi-layer-visual`

### B2-05 — Remotion Player & G4 storyboard editor

**Owner modules:** `frontend/src/workspaces/Storyboard/; frontend/src/components/RemotionPreview.tsx`

**Depends:** `B2-04`, `A1-06`. **Input contract:** B1-06 scene diagnostics; B2-01 Composition; G4 visual-edit API. **Output contract:** Real Player, scene inspector, approved-only asset/crop/motion/beat edit, G4 review revision.

**Acceptance:** Editing presentation creates G4-only revision and selective scene recompile; G1 claim/voice and G3 media history untouched; errors/pending visible.

**Windows OFFLINE/MOCK command (planned):** `npm --prefix frontend run test:e2e -- --grep 'storyboard-editor'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case scene-edit --mode local`

### B2-06 — Player/renderer parity + longform performance

**Owner modules:** `tests/visual/test_renderer.py; tests/e2e/visual.spec.ts`

**Depends:** `B2-04`, `B2-05`. **Input contract:** Same frozen timeline, 10 scene templates/30 variants/19 presets, >60 scenes. **Output contract:** Frame diff evidence at enter/mid/hold/exit; frontend responsive profiling.

**Acceptance:** Player/still compare exact version/fingerprint and measured image differences; no flash/blank/clip/overflow; long project editable without app freeze.

**Windows OFFLINE/MOCK command (planned):** `npm --prefix renderer run test:frames -- --case player-renderer-parity; npm --prefix frontend run test:e2e -- --grep 'longform-storyboard'`

**Windows LOCAL/LIVE integration command (planned):** `npm --prefix renderer run render:smoke -- --case 60-scene-longform`

## B3 — Render / delivery / Windows

### B3-01 — Full Remotion job renderer

**Owner modules:** `backend/app/render/worker.py; backend/app/render/manifest.py`

**Depends:** `B2-06`, `A1-05`. **Input contract:** G4-approved CompiledTimeline + final WAV, approved assets/fonts SHA, B2 Composition. **Output contract:** H264/AAC MP4 artifact, job progress, reproducible render input manifest.

**Acceptance:** Wrong/stale G4 approval blocks; independent render uses same immutable props; cancel/retry preserves existing valid attempt.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/delivery/test_delivery.py -k 'render or manifest or cancel'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case render-mp4 --mode local`

### B3-02 — FFprobe QC + visual diagnostics

**Owner modules:** `backend/app/render/qc.py; backend/app/render/frame_qc.py`

**Depends:** `B3-01`. **Input contract:** Rendered MP4; FinalAudio.v1, source CompiledTimeline/word map. **Output contract:** QC PASS/FAIL report for 1080p/30fps/audio/video duration, anomalous blanks, timing.

**Acceptance:** ffprobe actual tracks/duration; missing audio/blank frames/incorrect fps reject; no synthetic QA accepted as live media PASS.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/delivery/test_delivery.py -k 'qc or ffprobe or black_frame'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case final-video-qc --mode local`

### B3-03 — Attribution, G5 approval & export

**Owner modules:** `backend/app/render/attribution.py; backend/app/api/delivery.py; frontend/src/workspaces/Delivery/`

**Depends:** `B3-02`, `A3-04`, `A1-04`. **Input contract:** QC PASS media+manifest; approved rights and AI disclosure; G5 decision/revision. **Output contract:** G5-gated MP4+credits export bundle, artifact hashes and delivery UI.

**Acceptance:** Unapproved/stale output forbidden; every asset attribution linked to G3 exact SHA; user viewed/listened gate required, export reproducible.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/delivery/test_delivery.py -k 'attribution or gate_5 or export'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case export-approved --mode local`

### B3-04 — Crash recovery, queue UX & bulk operations

**Owner modules:** `backend/app/jobs/recovery.py; frontend/src/workspaces/Queue/; frontend/src/workspaces/Assets/`

**Depends:** `B3-01`, `A3-05`. **Input contract:** A1-05 job persistence; A3 asset batch, render job states. **Output contract:** Recovery of synthesis/search/render jobs and visible per-job progress/error/retry.

**Acceptance:** Force-kill/restart does not double-submit provider task or corrupt approved artifact; batch action partial failures explicitly itemized.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/integration/test_phase_b.py -k 'restart or queue or batch'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case restart-during-render --mode local`

### B3-05 — Windows packaging & setup

**Owner modules:** `scripts/windows/start-studio.ps1; scripts/windows/package.ps1; README.md`

**Depends:** `B3-03`, `B3-04`. **Input contract:** Pinned Python/Node/FFmpeg install, backend frontend/remotion artifacts. **Output contract:** One-click Windows launcher, repeatable setup, local-only state and backup/restore.

**Acceptance:** Clean Windows install/bootstrap verified; launcher opens working UI; reopening preserves G1–G5/project; no Ubuntu container requirement.

**Windows OFFLINE/MOCK command (planned):** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/verify-environment.ps1; py -3.12 -m pytest -q tests/integration/test_phase_b.py -k 'backup or restore'`

**Windows LOCAL/LIVE integration command (planned):** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-studio.ps1`

### B3-06 — Full V1 user outcome validation

**Owner modules:** `tests/e2e/test_full_flow.py; reports/acceptance/`

**Depends:** `B3-02`, `B3-03`, `B3-04`, `B3-05`. **Input contract:** All A1–B3 deliverables; user-reviewed source facts, 2 distinct long-form stories, provider credentials as available. **Output contract:** 2 actual 5–10-minute English MP4s, source attribution, G1–G5 histories, 8-role audit and PASS/FAIL/BLOCKED evidence.

**Acceptance:** Video A and B from same engine without custom JSX; real final WAV and verified alignment, video QC and G5 approvals; absent user/provider evidence explicitly BLOCKED not PASS.

**Windows OFFLINE/MOCK command (planned):** `py -3.12 -m pytest -q tests/e2e/test_full_flow.py -m 'not live'; npm --prefix frontend run test:e2e -- --grep 'full-flow'`

**Windows LOCAL/LIVE integration command (planned):** `py -3.12 -m backend.tools.smoke --case full-flow-two-topics --mode live`

## 2. Phase B exit — full V1 gate and explicit anti-scope-creep checklist

- [ ] B1-01..06 compiler consumes approved story/audio/source only, passes 10 typed template cases, 30 role-specific layouts, 19 preset parameter contracts, negative proof for map-era, quote, editorial connector vs geographic route and G4 edit lineage.
- [ ] B2-01..06 implement **all ten** real React templates and A/B/C variants with actual multi-layer output; G4 edits and Player are functional. Enter/mid/hold/exit screenshot evidence and browser/player vs Node still parity from same Composition on Windows.
- [ ] B3-01..06 render real H.264/AAC 1920×1080/30fps MP4s with real approved English narration/word alignment, archival provenance, reports, G5 operator signoff, stable retry/reopen and Windows one-click startup.
- [ ] At least one **5–10-minute** real English video and a second different-topic full-length video built **without video-specific JSX**; same 10-template engine and approved source process. Both actual MP4s and hashes/QC evidence attached; no pilot acceptance substitution.
- [ ] G1–G5 manual approval semantics preserved; live provider claims only where tested. Missing credentials or G-Labs live user session cannot be misreported; if a branch remains unverified, final status explicitly PARTIAL/BLOCKED for that capability rather than blanket Full-V1 PASS.
- [ ] All Windows required tests and live/local smoke available for installed credentials; failure cases for stale revision, missing rights, wrong map period, broken alignment, bad scene links, render crash and G5 export rejection.
- [ ] No out-of-scope future work, no old tool DB compatibility, no extra features silently pulled in. Code/fixture/LOC difference and duplication review attached to same exact HEAD. UI reviewed with solo operator and eight-role audit for **real footage**, not just JSON validity.

**Exit classification:** FULL_V1_PASS only with real two-topic full-length video evidence, verified G1–G5 user decisions, meaningful Windows render/QC/UX passes and explicit provider evidence ledger. If user defers live G-Labs testing, name the unverified integration separately; do not represent that specific branch as tested.

## 3. Hard scope locks and late-finding triage

**Frozen scope:** exactly 35 task IDs A1-01..B3-06; only A1–A3 and B1–B3 packages; only six existing UI workspaces and 5 human gates; no other phase, API surface or new template type without user-approved change request. A task can be split internally for code review **without adding a phase or gate**.

**Triage procedure when an audit finds an issue:** (1) demonstrate reproduced behavior + actual broken contract/observable consequence; (2) assign the *existing* owner task ID and affected dependency; (3) severity: **CURRENT_PHASE_BLOCKER** only if prevents this phase's acceptance or corrupts upstream truth; **INTEGRATION_DEPENDENCY** if discovered only by downstream cross-lane wiring; **FUTURE_SCOPE/NONBLOCKING** recorded without implementing now; (4) fix once in owner module, reuse closest test; (5) rerun exact affected Windows gate and dependency regressions; (6) record SHA and close. No new “round 2 audit P0” without reproducible evidence.

A previously frozen phase may be reopened **only** by a verified regression or an integration-dependent contract violation demonstrably blocking next-phase output. Code-style preference, unused feature ideas or cosmetic refactor do not reopen accepted phase. All new asks outside 35 task IDs require explicit user approval and separately documented change request with cost and exact acceptance; never turn them into surprise requirements mid-repair.

## 4. Minimal per-task and per-phase evidence record

```text
Task ID / owner module:
Commit SHA / branch:
Input SHA(s) / output artifact(s):
OFFLINE tests: command, PASS/FAIL/BLOCKED, assertion and artifact:
LOCAL integration: command, PASS/FAIL/BLOCKED, artifact/hash:
LIVE provider: provider, command, PASS/FAIL/BLOCKED/NOT_RUN, reason:
Behavior demonstrated / failure rejected:
git diff --stat (production +/−, tests +/−):
Existing logic reused; duplicated code/tests removed:
New dependencies and why:
Current phase blockers / deferred owner task IDs:
Reviewer scope decision:
```

This evidence template is reporting only. **Do not create a separate test, fixture or documentation file for each task**. Keep machine-checkable assertions grouped by actual behavioral domain.
