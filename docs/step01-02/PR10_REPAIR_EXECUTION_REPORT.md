# PR #10 — Root-cause motion implementation execution

**PLAN_READABLE** — `CODEX_PR10_CONTRACT_RESOLUTION_AND_MOTION_IMPLEMENTATION_TASK_V1_E994867.md`.
PR: https://github.com/plthien/Historical-Video-Studio/pull/10.
Branch: `feat/b2-motion-storyboard-player-parity`.
Starting HEAD: `e994867f8ce68a4a2df5415761ef69d380c63ba1`.
Original base: `822643bce56709e6c80463fb39b8e6b2461135eb`.
Final HEAD: inspect latest existing PR #10 commit; this report is committed in that branch.
No merge, new PR, main push, or B3 implementation.

## Actual production implementation

- `backend/app/director/camera.py`: `compose_camera_events` compiles `camera-pan` target geometry and `camera-push` focus/scale into bounded scene-local camera keys. Event phases do not move unrelated layer transforms; preserve G2 cue timing. Typed invalid/overlap/fake target errors.
- `backend/app/director/compiler.py`: compile camera preset target refs from authored cue focus, enter every G4 scalar patch into `compile_event`, rebuild full camera track, validate frozen source identity. Derive optional mask overlap **only** for a unique adjacent incoming frame-zero event paired with approved outgoing `mask_reveal` intent. Derive B2 word-glyph spans from exact G2 words and unique matches in unchanged G1 screen text.
- `renderer/remotion/Primitives.tsx`: motion progress now means elapsed phase, never raw scale/rotation degrees. Correct discrete hard-cut phase; word-local kinetic/highlight spans; reject missing historical intermediate number series and unpaired one-layer mask imitation.
- `renderer/remotion/HistoryComposition.tsx`: actual outgoing/incoming shared-Composition mask compositing, screen-space shape/direction/feather, source-authored chronological boundary, no pre-boundary incoming scene.
- `renderer/remotion/schema.ts` + optional `CompiledTimeline.v1.schema.json` word_spans: validate B2-derived glyph offsets, immutable text matching and uniqueness; no G2 map/source head mutation.
- `frontend/src/workspaces/Storyboard/StoryboardStudio.tsx`: expose source-locked camera scalar edits via existing G4 API and refresh persisted numeric controls. Preserve 409 conflict recovery, preview capability, multi-step staging controls.
- `backend/tools/storyboard_smoke.py`: replace previous expected inert-camera 422 with real SQLite PATCH→new camera keys, selective revision, frozen upstream heads, idempotent replay, cold reopen.
- `frontend/tests/e2e/storyboard.spec.ts`: real browser camera scalar PATCH→rendered PNG delta→persisted scene camera keyframes in the same Player/Node composition.
- `renderer/scripts/b2-motion.ts`: remove manually injected camera positive; compare same-frame event-on vs event-off PNG ROI, actual PNG SHA, prestart invariants, typed wrong-space negative; synthetic two-surface Chromium frames; derive 19-row status from assertions rather than hardcoded PARTIAL/PASS.

## Four contract decisions

See `docs/step01-02/pr10-contract-decisions-v1.json`.
Q1 historical number intermediary proof: **REQUIRES_OWNER_APPROVAL**; strict typed fail closed.
Q2 authored adjacent mask pair: **B2_LOCAL_ADDITIVE_EXTENSION**, only for uniquely authorized boundary; other pairs blocked.
Q3 current G3 asset alternatives: **REQUIRES_OWNER_APPROVAL** because current `asset_approval_heads` has one current head per requirement; G4 changed asset selection remains rejected.
Q4 G2 word-to-glyph: **B2_LOCAL_ADDITIVE_EXTENSION**, exact unique lexical binding only; ambiguous repeats block.

## Test and evidence truth

All modifications were committed remotely on existing PR #10 via GitHub. Local native Windows commands **NOT_RUN** from this Linux-only tool environment; tests execute through native GitHub Actions Windows workflows for each branch commit.
Earlier intermediate Windows A1 runs reported success; earlier B2 runs reported failure, including expected fail-closed mandatory motion aggregate, and provided logs for correcting a typed-schema negative oracle. Intermediate source-only results do not certify later commits.
Exact-final-HEAD Windows A1+B2 terminal conclusions and artifact IDs must be read from the current PR head before sign-off. If pending, G12 remains FAIL.
Do not treat sampled motion PNG hashes as historical operator approval, or a 60-frame 2-second real H264 excerpt as a 610-second MP4.

## Strict acceptance on final HEAD

| Original gate | Latest conservative verdict |
|---|---|
| G01 | PASS — existing PR/branch and no merge/main push |
| G02 | FAIL until exact-final-HEAD Windows pinned install/typecheck proves |
| G03 | FAIL — cannot claim 19/19 semantics with historical-number dependency and unproved source rights |
| G04 | FAIL — not every transform/transition event has complete audited causal proof |
| G05 | FAIL — typography, polygon/derivative and all negative evidence not established |
| G06 | FAIL — G3 same-slot approved alternatives require G3 owner authority |
| G07 | FAIL until exact-final-HEAD source-freeze/idempotency/cold-reopen execution proves |
| G08 | FAIL until real 409/422/424 and edit-to-pixel browser workflow owners prove |
| G09 | FAIL until final-HEAD 10-pair Browser/Node parity proves |
| G10 | FAIL until final-HEAD 61 scene browser performance proves |
| G11 | FAIL until final-HEAD real excerpt render/ffprobe proves |
| G12 | FAIL until same final SHA native Windows A1+B2 workflows green |

**Strict verdict: FAIL — NOT MERGE READY.** Historic 6/12 baseline is not an exact-final-HEAD PASS claim; missing/queued tests are NOT_RUN, not PASS.
