# 01 — PRODUCT SPECIFICATION · V1.0
**Project:** Historical Video Studio (new Windows-only local application)  
**Authority:** MASTER_DESIGN_SPECIFICATION_V1 + DESIGN_DECISIONS_2026-10-19; this is a detailed deliverable for Step 01, not a rewrite of historical evidence.  
**Disposition:** DESIGN FROZEN for Step 03 prototype; runtime unbuilt.

## 1. Product promise and boundaries
One importable StoryPackage JSON authored with **external ChatGPT** → five explicit human review gates → reusable, period-aware 2D motion documentary produced by Remotion. After importing JSON, the application automates eligible jobs *between* gates. No LLM API, autonomous browser research agent, scene-by-scene JSX generation, Codex or Claude Code during video production. One Windows operator, local data and local render. V1 narration is English-first; other languages are feature-gated, not implicitly supported.

Separate success criteria:
- **Process automation:** no manual command line, source editing or recopying ChatGPT prompts between approved gates.
- **Historical integrity:** no silently substituted factual images, no AI images presented as contemporary evidence.
- **Editorial quality:** two distinct historical stories rendered with the same template/preset code; automated technical QC does not imply artistic approval.
- **Operational quality:** durable queue, cancellation and selective rerun, restart-safe project and 5 review gates.

## 2. Personas and user journeys
**Primary operator:** sole creator/editor researching and publishing history videos; may choose Kokoro or ElevenLabs, inspect sources, approve individual/batch items, fix one scene, and continue after crash.

**Happy path:** create project → export ChatGPT authoring brief → upload StoryPackage.v1 JSON → G1 approve story → run TTS and archival discovery concurrently → G2 approve voice, G3 approve assets → assemble exact WAV and ElevenLabs alignment → compile storyboard → G4 approve → render+QC → G5 approve delivery.

**Asset exception:** if exact archival requirement unresolved, show exact two primary options per requirement or deliberate batch selection: (M) operator searches and uploads; (F) operator authorizes managed fallback generation/research and later approves *the specific result*. Neither branch auto-approves; it may pause this asset while unrelated jobs run.

**Provider exception:** G-Labs unavailable/429 → retained task/error state; retry only per documented bounded policy or operator action; no false asset delivered. Voice/alignment errors keep G2 BLOCKED/NEEDS_ACTION and do not synthesize word times.

**Revision journey:** regenerate section → only audio and dependent timings/storyboard/delivery stale; replace image → affected asset bindings/scenes and delivery stale; unrelated approved artifacts stay intact. A draft edit never mutates approved snapshot.

## 3. Information architecture
Six screens and global review navigation:
1. **Project & Prompt** — project profile, language/style, Build ChatGPT Brief, JSON import and validation.
2. **Story Review (G1)** — script sections, claims, sources, corrections, approve exact draft.
3. **Voice Studio (G2)** — provider selection, selected-voice identity, sections/attempts, player, pacing, correction, approve+assemble+alignment.
4. **Historical Assets (G3)** — discovery, thumbnails, evidence, licensing, missing queue, two-option workflow, variants, approval.
5. **Motion Storyboard (G4)** — scene list, real Remotion Player, tracks, approved asset picker, template variant, motion inspector, overflow/continuity flags, approve.
6. **Render & Delivery (G5)** — queue, output, technical QC, source credits, video inspection, final approval.

Persistent global header: project/revision, 5 gates, current job status, blockers, next valid action, provider health. Accessible key actions: approve, request changes, reject, retry, cancel, undo draft; all buttons respond immediately with progress/error and a job identifier. Bulk selection/filter mandatory in Asset Review. Preview must use the production Composition, not a CSS lookalike.

## 4. User-facing states and buttons
- Gate status: DRAFT, PREPARING, READY_FOR_REVIEW, APPROVED, CHANGES_REQUESTED, BLOCKED, REJECTED, STALE. STALE means prior approval is historically preserved but no longer authorizes current dependency revision.
- Job status: QUEUED, RUNNING, SUCCEEDED, FAILED_RETRYABLE, FAILED_TERMINAL, CANCELLED, BLOCKED_REVIEW.
- Approve is disabled unless exact candidate snapshot is READY_FOR_REVIEW and all gate-specific invariants pass. Always show a concrete explanation and eligible repair action.
- Long task click: optimistic processing UI immediately, no duplicate submission; backend returns durable job id; UI polls/streams state; terminal event persists after refresh.
- Voice approval is **one user action**; assembly and ElevenLabs alignment follow automatically, and dependent compilation does not start until alignment QC PASS. Do not add a parallel manual “alignment” button.
- G3 operator can approve candidates in batch only after reviewing evidence and known restrictions; batch never includes unresolved/fallback-unreviewed rows.
- G4 allows scene-specific edits, but fact-changing captions route to G1 revision.
- G5 requires selected render and attribution bundle, watching/listening acknowledgement, and explicit approval; render success is not final approval.

## 5. Gate contracts in plain language
| Gate | Review material | Blocking conditions | Output frozen |
|---|---|---|---|
| G1 Story | script, historical claims/source leads, visual intents | missing section IDs; unresolved critical factual assertion; unsupported JSON | ApprovedStory |
| G2 Voice | voice attempts, pronunciations, final audio | missing section, corrupted audio, unaccepted attempt; alignment job failure before downstream | ApprovedAudio + VerifiedWordTimingMap after post-approval processing |
| G3 Assets | original/archive source, rights, context, variants | missing required asset, rights unknown, fallback not approved, wrong era | ApprovedAssetSnapshot |
| G4 Storyboard | Remotion player, timeline, scenes, cues, layout diagnostics | stale alignment/asset, invalid map, missing cue, unreadable text or unsupported preset | ApprovedCompiledTimeline |
| G5 Delivery | MP4, QC, provenance/credits | render failed, QC failure, changed source fingerprint, absent credits | ApprovedDelivery |

**Ordering nuance:** G2 and G3 can occur in parallel after G1. G2 approves audio *then* assembly/alignment executes. G4 waits for completed alignment and G3. Exactly five human review gates; alignment QA is an automated post-G2 constraint, not a sixth gate.

## 6. System settings
Project: English narration default, 16:9 1920×1080 30fps default; style profile HistoryEditorialPaper.v1; source policy archival-first, fallback opt-in; review mandatory; optional offline export of project minus secrets.
Providers: TTS Kokoro / ElevenLabs; separate ElevenLabsForcedAlignment. G-Labs base URL default loopback :8765, model/aspect/reference settings constrained by supplied contract; store API keys server-side and never in exported project.
Voice identity/config frozen per attempt; timing from approved final WAV not predicted WPM. Scene set and source selection tied to requirements, not one image per sentence.

## 7. Accessibility, responsiveness, and operator workload
Windows desktop 1366px minimum target, useful at 1920px. Keyboard tab/focus and visible error text, AA contrast target, status not conveyed by color alone. Preview aspect remains 16:9; at narrow widths inspectors stack rather than truncate. Large asset/scene collections virtualized in implementation. A batch action must show count and exclusions, then irreversible confirmation for approval.

## 8. Non-goals / explicit exclusions
No claim of fully hands-free production; no automatic historical truth certification or unconditional copyright clearance; no generative AI video required; no full nonlinear video editor; no arbitrary external plug-in code; no old repository migration. No live G-Labs call required to *start implementing* from contract; operational claims require subsequent real execution.

## 9. Product acceptance for Step 01 design
A new contributor can identify every screen, gate, state, user action, retained artifact and recovery path without guessing. Story/voice/assets/storyboard/export have a connected workflow. UI actions have corresponding intended backend contract in 02/04. Cross-language claims reflect English-first and do not block V1 for untested Vietnamese forced alignment.
