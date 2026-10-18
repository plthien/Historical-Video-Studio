# 05 — IMPLEMENTATION PLAN · Step 03 and Step 04
**Status:** Step 01–02 design plan; coding has not started. **Target platform:** Windows 10/11 local, Python 3.12, Node 22, TypeScript/React/Remotion. **Repository:** clean Historical-Video-Studio, no history repo migration. **Milestone model:** ONLY 4 product steps: (01) Product/Architecture, (02) Visual Specs, (03) End-to-End PoC, (04) Full Application.

## 1. Scope boundary — no phase proliferation
Step 01 + 02 deliver the 5 design documents, ten JSON Schemas, contract fixtures/tests, API surface, UI interactive design mockup, 10 template sheets with top five pilot ready, and six-role design audit. **Step 03 must deliver a real MP4 before Step 04 begins**. Step 04 adds production UI/features; there are no hidden prerequisite P0–P12 mini-projects.

Implementation coding agent/developer MAY write application code to build the tool. **Production use of the completed tool MUST NOT require a coding agent.** External ChatGPT authoring is a manual JSON import.

## 2. Technical skeleton to create in Step 03
~~~
backend/app/
  api/   projects/   revisions/   gates/   orchestrator/
  voice/{adapters,assembly,alignment,qc}/
  assets/{sources,identity,rights,variants,binding,glabs}/
  director/{templates,semantic_resolver,compiler,qa}/
  render/{jobs,qc,attribution}/
frontend/src/{routes,components,features,player}/
runtime/remotion/src/{HistoryComposition,scenes,templates,presets,styles}/
contracts/schema/    contracts/examples/   contracts/openapi.yaml
tests/{contracts,voice,assets,gates,compiler,ui,e2e}/
start.bat
~~~
Keep schema files, the motion registry and style versions as explicit build artifacts. Shared component entrypoint used in @remotion/player and renderMedia; no CSS-preview substitute. Keep project bytes in SQLite + hash-addressed storage, not transient provider URLs.

## 3. Step 03 — End-to-End PoC (five acceptance work packages)
**Goal:** one 60–90 s English historical video rendered by the new stack, and a second 60–90 s **different** historical story without scene-specific code changes. Use approved manual archival assets in the very first render. No forced G-Labs live test as early blocker; its interface can be implemented and mocked per supplied contract, with live proof deferred to operator testing.

### 03.A Contracts + project/approval core
Implement Draft 2020–12 JSON Schema validator and semantic cross-reference checks; strict StoryPackage.v1 import; canonical hashes; revision service; five gates with approval concurrency rules; durable queue/idempotency and one source of error codes. Real DB tests for retry and stale approvals. **Acceptance:** valid fixture imported, negative fixtures blocked with stable error codes; G4 cannot run until G2-aligned + G3-approved.

### 03.B Voice vertical slice
KokoroTTSAdapter and ElevenLabsTTSAdapter obey same TTS interface; quality checks and per-section attempts, section playback/approval, assembled immutable final WAV. Separate ElevenLabsForcedAlignmentAdapter over final WAV and exact transcript; normalized word map and timestamp QC; English-first. **Acceptance:** representative English 60–90 s audio generated/imported, G2 approved, alignment succeeds on real audio for Step03 pilot, cue checks run; provider failure is visible/recoverable. Offline adapter contract tests before provider access. Direct live ElevenLabs use needs user's configured credentials.

### 03.C Archival assets / limited G3
Implement manual approved local archival assets and a minimal G3 review board with provenance+rights fields, scene bindings, non-destructive variants, cutout/photo-card choice. Missing asset shows Manual Upload vs Managed Fallback modes, with the latter blocked from becoming approved unless reviewed. Archive adapters/G-Labs full integration may await Step 04; avoid fake auto-source selection. **Acceptance:** no unapproved archival image used; replacement updates only dependent scene.

### 03.D Five production scene templates and Remotion
Build T01 map focus, T02 portrait, T03 archival collage, T04 route reconstruction, T08 fact impact. Implement core motion registry (photo-card-enter, title-mask-reveal, route-line-draw, camera-pan, camera-push, stagger-reveal, freeze-hold, text-highlight) with bounded params. Compiler produces frame-indexed timeline from English WordTimingMap and G3 exact assets, with no generated JSX. Use same composition in browser and renderer. **Acceptance:** five templates work in both sample topics with fixture evidence, text/geometry safe-area checks and byte-identical deterministic timeline on repeat.

### 03.E Pilot / six-role visual review / exit
Test A: a reference-style Sarajevo 1914 60–90s fragment (not copying footage/assets unlawfully). Test B: German Unification 1871 60–90s using exact same template registry code without JSX additions. Produce MP4, word map, approved source sheet, screenshots/stills, frame parity comparisons and QC reports; G4/G5 approval UI at least minimal. Test on Windows. **Hard exit:** both MP4s produced end-to-end with explicit approvals and audit; no frame blackouts/audio gaps, source mismatches or silent fallback. If only fixtures/mocks, Step 03 remains PARTIAL.

## 4. Step 04 — Full Application Implementation (grouped deliveries)
**04.A Archives and evidence production:** Wikimedia Commons, Library of Congress, Europeana source adapters; metadata/relevance/rights handling, provenance report, context distinction, batch G3 review, source dedupe and attribution.
**04.B G-Labs production image adapter:** implement documented HTTP 202 submit → poll → download, task cancellation by ID, MAX/health/key/status errors, 429 backoff, retries, offline mock tests; managed fallback candidate generation and explicit later review; derivative processing and source vs AI label. No requirement for live user-account test before writing code; actual operability remains unverified until user test.
**04.C Motion/editor completion:** full ten templates T01–T10, layout A/B/C, preset registry/reduced motion, real Remotion Storyboard Player with virtualized scene and asset panels, detailed layer/track inspector, local draft undo/redo, source-linked captions, targeted compile/revision.
**04.D Operator UX/durable background:** all 6 workspaces, batch approvals, provider settings, local credentials, job queue, crash recovery, cancellation and error repair, English narration presets, reproducible exports and backup.
**04.E Production/hardening:** 4–6 minute full-length video plus second topic, Windows start.bat and one-click packaged guide, performance and disk quotas, source/copyright review report, crash/restart tests, font/media snapshots, no inactive controls. No old data migration.

## 5. Dependencies and release-critical path
~~~
Schemas/API/approvals ─┐
Voice adapters + alignment ─┼→ Compiler + 5 templates → 2 real pilots (Step 03 PASS)
Manual G3 evidence ────────┘
                ↓
Archive adapters + G-Labs contract integration → complete G3
Full 10 templates + editor → robust workflow → long video → Windows release (Step 04 PASS)
~~~
Step 03 should use genuine voice/alignment as soon as credentials permit; do not fake successful timing. G-Labs live test deliberately deferred per user, not forever asserted successful. If provider unavailable, report incomplete milestone rather than bypass human gates.

## 6. Acceptance gates and negative matrix
**Design Step 01/02:** five docs and testable schema/API/UI contracts, 5 templates specified for pilot and 10 for V1, six-role audit with explicit findings and fixes; design status PASS only for scope frozen (not production).
**Step 03:** tests for JSON syntax+crossrefs, word sample monotonicity, stale SHA, approval illegal transition, asset fallback authorization, wrong map era, unsupported preset, layout overflow, preview/render still parity, audio/MP4 length, user G4/G5.
**Step 04:** adapter 401/403/429/5xx/cancel/resume, archive rights-unknown, wrong-person photo, AI illustration labeling, simultaneous jobs, approve conflict, duplicate UI click, crash resume, 60+ scenes project load, source attribution completeness and short/long cases.
Windows tests primary; don't substitute green Ubuntu CI for Windows acceptance. Separate mock PASS from live/provider/operator PASS in reports.

## 7. Six-role review protocol per delivery
Director: semantic visual choices, causal clarity, human emotional emphasis and no slideshow monotony.
Editor: pace/hold/cut continuity, voice-aligned events, transition discipline and correction reuse.
Motion Designer: scene slot fidelity, motion realism, clipping/overflow, map focus and reduced-motion mode.
Architect: adapter separation, deterministic compiler, revision snapshots, no provider calls from render.
QA: JSON/schema negative tests, evidence and rights, stale gates, provider failure and preview/parity tests.
Operator: single-click workflows, batch selection, clear errors and no need for external code tool in production.
Each role must submit evidence and tag blocker vs improvement; don't conflate checklist sign-off with real visual pilot.

## 8. Stop/skip rules
Do **not** implement every Motion Prompt sample, AI-video automation, SaaS permissions, multi-user accounts, vector map historical dataset from scratch or sophisticated non-linear editing as prerequisites for first MP4. Do not force archaeological/source evidence into AI illustrations beyond truth labeling. Do not invent licensing claims. Do not reopen Step 01/02 for improvements that demonstrably belong to Step 04 unless they block Step 03 contracts.

## 9. Handoff checklist for developer
Commit Step 01/02 docs+schemas+fixtures+mockup; tag design baseline. Implement Step 03 on a feature branch unless operator explicitly requests direct main writes for code. Keep root README links current. Record exact Windows toolchain/versions, provider capabilities and screenshots. Every deliverable lists code SHA, test command and factual test evidence. **Do not call Step 03 complete on design-only work.**
