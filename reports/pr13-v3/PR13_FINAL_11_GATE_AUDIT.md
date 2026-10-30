# PR13 final 11-gate audit — superseded by V4 execution

The earlier V3 `11/11` conclusion was a false positive: it did not prove that the precompiled production bundle called the backend process started by Playwright. The bundle targeted canonical API port 8010 while the old production-preview harness started its isolated backend on 8000 and incorrectly supplied `VITE_API_ORIGIN` only to `vite preview`. V4 supersedes that conclusion with a browser-observed production handshake.

Policy remains `G12_RETIRED_NOT_SCORED`; the denominator is exactly G01–G11. Execution source for the V4 code and browser evidence is `8fe9050ba9e32eaaf27e380c4da7b55e13012fad`; the final evidence-only commit is reported in the handoff because a commit cannot contain its own SHA.

## V4 repair closure

| Finding | Repair and direct evidence | Status |
|---|---|---|
| Production preview origin | Production parity reads `config/ports.json`, starts the isolated backend on compiled port 8010, and refuses a conflicting override before browser execution. Actual Chromium observed health/projects 200 and create 201 on API 8010 while preview ran on 5174. | PASS |
| Clean-package evidence contract | Producer and consumer use `B3CleanPackageLaunchEvidence.v2`; named negative values, non-ready/non-200 state, process cleanup, exact archive/media SHA and unchanged data-tree digest are asserted. Six false-positive mutations are rejected. | PASS |
| Fresh evidence | Production journey passed at 1366x768 and 1920x1080, including copy/download/stale/rebuild/import/reopen. Four populated owner fixtures were recaptured; all 14 images were opened and reviewed. | PASS |

## G01–G11

| Gate | Final evidence | Verdict |
|---|---|---|
| G01 | Same PR13 branch and base; initial remote/local head `64ccc87efac9e60b2fd334ed51f102a92745f02f`; no merge, new PR, workflow or schema edit. | PASS |
| G02 | PS5.1/PS7 identical fingerprints and tamper negatives; native launcher ready/HTTP/clean stop; clean extracted ZIP producer and consumer both pass. | PASS |
| G03 | Production State A/B on both viewports uses backend 8010; projects GET 200, create POST 201, persisted IDs and revision reopen verified. | PASS |
| G04 | G1/source/revision owner suites pass; imported candidate remains distinct from approval and critical synthetic claims stay blocked. | PASS |
| G05 | Voice owner suite and populated Chromium show playable generated WAV, source-locked sections and truthful alignment dependency. | PASS |
| G06 | Asset/Phase A suites and populated Chromium retain exact original SHA, explicit rights/context review and no automatic approval. | PASS |
| G07 | Native compiler plus genuine Remotion Player/Node parity and real-frame repair evidence pass. | PASS |
| G08 | Native H.264/AAC render, QC negatives, G5 authority and immutable export/download pass. | PASS |
| G09 | External Brief V2 production preview completes preview/copy/download/stale/rebuild/import/reopen without runtime or network errors. | PASS |
| G10 | Native positive map T01/non-map T09 and negative cue/source/map suites pass with exact G1–G3 and Final WAV/word-map dependencies. | PASS |
| G11 | Fourteen current two-viewport captures, geometry assertions and direct image review show no horizontal clipping, text overlay or unreachable control. | PASS |

`PR13_UI_CODE = PASS (11/11)`.

## Truthful exclusions

- `EXTERNAL_MODEL_QUALITY=NOT_RUN`: no actual external ChatGPT-authored StoryPackage was supplied for editorial review.
- `LIVE_RIGHTS_ACCEPTANCE=BLOCKED`: synthetic source fixtures are not historical rights approval.
- `REAL_TWO_TOPIC_OPERATOR_FILMS=NOT_RUN` and live provider checks remain operator work, separate from the software verdict.

Detailed commands and preserved failures are in `../pr13-v4/T01_T13_EXECUTION.md`; visual hashes and findings are in `../pr13-v4/VISUAL_REVIEW_LEDGER.md`.
