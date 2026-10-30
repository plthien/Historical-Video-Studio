# External Story Brief V3 acceptance — PR #13

## PLAN_READABLE

PASS. The implementation plan `CODEX_PR13_EXTERNAL_BRIEF_V3_EXACT_PROMPT_COPY_IMPLEMENTATION_PLAN_A8D7E98.md` and its authoritative prompt source `EXACT_EXTERNAL_STORY_BRIEF_V3_PROMPT_SOURCE.md` were readable in full before changes.

## HEAD_VERIFIED

- Pre-edit HEAD: `a8d7e982fd2b0d12a0fe32e50f8eda4dc66433bd`
- Branch: `feat/v1-ui-mockup-parity-and-authoring-bridge`
- Existing PR only: `https://github.com/plthien/Historical-Video-Studio/pull/13`
- No new PR, merge, or push to `main` was performed.

## PROMPT_COPIED_VERBATIM

- Resource: `backend/app/projects/prompts/external_story_brief_v3.md`
- SHA-256: `e7234d15cc00a1f8b47196e7a7190296218ff9654bff4beb9818826c6848e494`
- UTF-8 bytes: `24,253`; LF bytes: `135`; CR bytes: `0`; BOM: `false`; final LF: `true`
- Sentinel counts in the raw resource: operator metadata `1`, runtime budget `1`, canonical schema `1`.
- `.gitattributes` pins the prompt and generated sample to LF so checkout settings cannot corrupt the byte identity.

## SCOPE

Production changes are confined to the A1-06 authoring bridge plus the B3-05 clean-package consumer required by the plan. The builder loads the static V3 resource, validates inputs and registry coverage, and performs one regex callback pass over exactly three sentinels. The API shape, persisted brief metadata, stale/revision rules, StoryPackage import, and UI redesign remain in place. The package smoke now proves the extracted package contains the exact prompt and can invoke its own packaged `build_brief`.

Changed implementation/test/documentation paths:

- `.gitattributes`
- `backend/app/projects/authoring_brief.py`
- `backend/app/projects/prompts/external_story_brief_v3.md`
- `backend/tools/clean_package_smoke.py`
- `docs/authoring/EXTERNAL_STORY_BRIEF_V3.md`
- `frontend/tests/e2e/ui-redesign.spec.ts`
- `reports/authoring/PROMPT_SAMPLE_ONLY_BLACK_DEATH_7_MIN_V3.md`
- `reports/authoring/v3-screenshots/*`
- `tests/backend/test_external_story_brief_v2.py`
- `tests/backend/test_external_story_brief_v3_contract.py`
- `tests/integration/test_phase_b.py`
- this report.

Frozen authorities were not edited and retain these SHA-256 values:

- `contracts/schema/StoryPackage.v1.schema.json`: `a209646795794042fe4acb10404529288315d47023e2668012af4ff3cbd5d6da`
- `contracts/registries/layouts.v1.json`: `850df2df31b19f4fc5c0751f1cab9d39927743a9471b30d8b22dda9231f69e97`
- `contracts/registries/motion-presets.v1.json`: `17e93bbbdefd688863f9db4e174c2b53d50c32dd20aead6554e48fd0e3772f2d`

No dependency was added. No validator, G1–G5 approval contract, renderer, provider integration, or protected schema/registry was weakened or changed.

## EXECUTION

| Work package | Status | Actual evidence |
|---|---|---|
| WP0 — identity and baselines | DONE | Clean worktree and mandatory branch verified at pre-edit HEAD. Frozen hashes recorded before editing. V2 5/7/10 outputs were captured for comparison. |
| WP1 — exact resource and builder | DONE | Exact resource identity above; V3 builder is deterministic, validates 5–10 integer minutes and nonblank topic/audience, checks T01–T10 registry coverage, and makes no LLM/network call. |
| WP2 — behavioral contracts | DONE | `20 passed in 2.83s` for the new V3 contract; `3 passed in 3.03s` for the existing authoring/cue owner file. Combined focused suite previously completed as `24 passed in 4.79s`. |
| WP3 — UI/package/pilot | DONE for software; pilot NOT_RUN | Production Chromium: `3 passed (22.4s)` at 1366×768 and 1920×1080. Clean extracted package: `CLEAN_PACKAGE_PASS`, archive SHA `c42fc8f3830f628ef4560c99a92d58daa3c766f9a680cef7272ce8b84316e263`; its V3 prompt and builder were exercised. External ChatGPT pilot was not authorized and was not fabricated. |
| WP4 — acceptance/handoff | DONE | Commands below passed, binary matrix is 13/13, exact pushed delivery SHA is reported by the handoff after the report-only commit is created. |

Commands and results:

- `.venv\Scripts\python.exe -m pytest -q tests/backend/test_external_story_brief_v3_contract.py` → `20 passed in 2.83s`.
- `.venv\Scripts\python.exe -m pytest -q tests/backend/test_external_story_brief_v2.py` → `3 passed in 3.03s`; includes actual cue missing/ambiguous/occurrence/section/range/overlap negatives.
- With `D:\tools\G-Labs-Voice-Studio-v2.0.4-win\bin\ffmpeg\win` prepended to PATH, `.venv\Scripts\python.exe -m pytest -q tests/backend/test_post_pr12_authoring_story.py tests/backend/test_pr13_g4_positive.py tests/backend/test_ports_config.py tests/backend/test_frontend_build_http.py` → `7 passed in 19.45s`.
- `.venv\Scripts\python.exe scripts/check_design_contracts.py` → `PASS: 12 schema(s)`.
- `.venv\Scripts\python.exe scripts/validate_visual_design.py` → `PASS: 10 typed templates, 10 multi-layer scenes, 30 variants, 18 motion grammars`.
- `npm.cmd --prefix frontend run typecheck` → PASS.
- `npm.cmd --prefix frontend run build` → PASS, 238 modules transformed; only the pre-existing chunk-size warning.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/verify-frontend-build.ps1` → verified source `16070bd9e97a6b359c4877042a2ae0ab5c201637`, input `903d7d5ea819f8eab42e8cc6692bb517d4c584b3146b201de07a90ac48184238`, bundle `c51709fdcdb5a3334bd8b03bcb260f2eccb0257937f99ab29425446d1a373104`.
- With `HVS_PARITY_PRODUCTION=1` and UI port 5174, `npm.cmd run test:e2e -- --grep "PR13 redesigned|project creation stays truthful"` → `3 passed (22.4s)`; API health/projects 200, create 201, reopened revision 3, no page errors, no failed requests, no horizontal overflow.
- `.venv\Scripts\python.exe -m backend.tools.clean_package_smoke` → `CLEAN_PACKAGE_PASS`; 192/192 manifest hashes verified, two launches/reopen passed, occupied-port/missing-FFmpeg/missing-frontend negatives passed without data mutation, extracted V3 prompt SHA matched and packaged `build_brief` emitted the V3 header.
- `.venv\Scripts\python.exe -m pytest -q tests/integration/test_phase_b.py::test_clean_extracted_package_bootstrap_reopen_evidence tests/integration/test_phase_b.py::test_clean_package_evidence_rejects_false_positive_mutations` → `2 passed in 1.02s`.

Failures retained as evidence rather than hidden: the first focused contract run had three legitimate test/fixture mistakes, which were corrected before the 23/23 and 24/24 passing reruns; the first sample capture used a CP1252 text path and was replaced with exact UTF-8 byte output; the first enhanced package probe exposed an extra-brace syntax error and was fixed before clean-package PASS. A later owner-suite invocation used a nonexistent local FFmpeg PATH and produced two `FAILED_TERMINAL` voice jobs; rerunning unchanged code with the installed FFmpeg directory produced 7/7 PASS. Direct invocation of the verification PowerShell script was blocked by the machine execution policy; the same script passed under explicit `-ExecutionPolicy Bypass`.

Generated Black Death sample SHA-256: `05ffe5978949707930f3a6ca9949a0fccfa8419964ce9c55d72a94bf96cb6160`.

Visual evidence was opened and inspected, not merely existence-checked. There was no horizontal overflow, clipped control, or text collision. The V3 current label and prompt header were visible; G1 truthfully remained BLOCKED for the synthetic fixture. Key screenshot SHA-256 values:

- `projects-A-1366.png`: `c5461fa02f5f775aed89fb9e3886e86bf0be2a3b25b74dc02d2cb5c5a9cd03a3`
- `projects-B-1366.png`: `6be6d0d6ac5b11d83d79910dc1333c36924e906c8e81d0907bd25426f5c946f3`
- `story-G1-1366.png`: `dfea2baac3a6f5b77f48e6df352436ad62074b648091d1427e0f07b6bdc4eaa6`
- `projects-A-1920.png`: `8ba7b8c5412e93afd6e38a12111fe36aa33f998b4c0ba305785273346cd19ef0`
- `projects-B-1920.png`: `e3b456b752b9c8f4a4d27d128bda10fb2cabd6385b8bcf6a96773c84828c6ae9`
- `story-G1-1920.png`: `5c50b029f5006e32f3e5d8981557bac8fe019d16e37456c2663fc8e5f8b3ea46`

## SOFTWARE_GATES

| Gate | Verdict | Evidence |
|---|---|---|
| P01 | PASS | Correct PR13 branch; no new PR/merge; frozen files unchanged. |
| P02 | PASS | Exact SHA/byte/LF/BOM identity proven. |
| P03 | PASS | Three once-only sentinels and one-pass callback; adversarial literal sentinel input survives. |
| P04 | PASS | Exact V3 metadata/version, deterministic 5/7/10 budgets, Unicode/quotes/newline/braces inputs covered. |
| P05 | PASS | Frozen schema appendix equality and T01–T10 registry coverage enforced; no new render/approval output fields. |
| P06 | PASS | Exact V3 narration policy; V2 duplicated block explicitly absent. |
| P07 | PASS | Exact prompt resource carries the required feasibility, truth, UNVERIFIED, quote/map/rights policy. |
| P08 | PASS | Exact resource carries typed T01–T10 visual direction, reveal/beat division and source limits. |
| P09 | PASS | Actual semantic cue positive and negative owner tests pass. |
| P10 | PASS | API and production Chromium cover current/stale/copy/download/import/reopen at both viewports. |
| P11 | PASS | Exact resource is in the ZIP; extracted backend builds V3 brief; package and false-positive negatives pass. |
| P12 | PASS | Owner regressions and frozen source/schema authority pass and remain byte-identical. |
| P13 | PASS | This report records scope, files, commands, results, failures, exclusions, evidence hashes, and avoids an invented editorial PASS. The delivery response records the exact report-containing pushed HEAD. |

`EXTERNAL_BRIEF_V3_SOFTWARE = PASS (13/13)`.

## PR13_G12

`RETIRED_NOT_SCORED`.

## EXTERNAL_MODEL_EDITORIAL_QUALITY

`NOT_RUN`. No authorized external ChatGPT operator interface was available. No model output, production story quality, historical source verification, media rights, provider success, or operator G1–G5 approval is claimed from synthetic tests.

## FINAL_HEAD

Tested implementation/evidence source HEAD before this report-only commit: `16070bd9e97a6b359c4877042a2ae0ab5c201637`. The exact report-containing final pushed HEAD is necessarily created after this file is written and is recorded in the delivery response and on original PR #13. Status: `NOT MERGED`.
