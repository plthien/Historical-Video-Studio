# PR13 final 11-gate audit

This is the current policy ledger. Historical 12-gate reports remain unchanged.

`G12_RETIRED_NOT_SCORED` — no CI result is included in the denominator.

## Repair closure

| ID | Root cause and minimal repair | Direct evidence | Status |
|---|---|---|---|
| F01 | `Sort-Object` made source ordering culture/shell dependent. Use ordinal, case-insensitive de-duplication plus ordinal ordering; strict UTF-8 JSON read; diagnostic predicates and stable child reason codes. | Cross-shell first/subsequent runs and forged-head, JS/CSS, ports, missing build, invalid JSON, wrong SHA negatives all pass; real PS5.1 launcher HTTP smoke is repeated after the handoff commit. | PASS |
| F02 | Runtime correctly rejected missing index earlier than the legacy expected string. Negative now requires `FRONTEND_BUNDLE_STALE` + `BUILD_MISSING`, non-ready/non-200 state and unchanged data-tree identity. | `backend.tools.clean_package_smoke` => `CLEAN_PACKAGE_PASS`; evidence `reports/acceptance/generated/clean-package-launch.json`. | PASS |
| F03 | Stable accessible name was missing; exact-ID input was hidden; hydration could replace the transient landing form; several direct API URLs ignored isolated ports. | 8/10 owner cases passed in aggregate, the two database-path regressions passed 2/2 after repair; G4 Player/Node 2/2; PR10 source 1/1 and typography 1/1. | PASS |
| F04 | FFmpeg existed but was not inherited by the exact test process. Explicit verified bin PATH closes real T01/T09 compilation without mocking or validator changes. | Required backend matrix: 12 passed; B3 native render/QC/export `LOCAL_PASS`. | PASS |
| F05 | Populated screenshots were not gathered/reviewed. Added targeted capture synchronization and fixed the one visible 1366 button-wrap defect. | 14 images and `VISUAL_REVIEW_LEDGER.md`; ui-redesign 2/2, G2/G3 2/2, G4 2/2, G5 1/1. | PASS |
| F06 | External creative output is an operator input, not a deterministic unit-test fixture. | `EXTERNAL_MODEL_QUALITY_CHECKLIST.md`; status remains honestly `NOT_RUN`. | PASS (handoff complete) |

## G01-G11

| Gate | Evidence | Verdict |
|---|---|---|
| G01 | Exact branch/remote head/base verified; same PR, bounded diff, no merge/new PR/workflow/schema edits. | PASS |
| G02 | PS5.1/PS7 identical input+bundle identity; tamper negatives; real launcher health/UI/build-info/clean stop; clean ZIP negative. | PASS |
| G03 | State A/B production bundle at both viewports; recents, settings, V2 copy/download/stale/rebuild/import geometry. | PASS |
| G04 | Real imported sections/claims/G1 review plus persisted revisions and browser reopen flow. | PASS |
| G05 | Playable selected-section audio, Final WAV owner flow, approval semantics and truthful missing-alignment credential UX. | PASS |
| G06 | Original candidate SHA/context/rights, manual resolution, atomic batch/conflict, scope isolation and safe managed-job UI regressions. | PASS |
| G07 | Positive compiled G4 plus real Remotion Player/Node immutable-frame parity, PR10 source edit and typography clipping checks. | PASS |
| G08 | Native encoded MP4, full-stream QC, black/near-silent negatives, audible review, G5 approval and SHA-bound export/download. | PASS |
| G09 | Deterministic V2 settings/reopen/copy/download/stale/import and unchanged Story correction/G1 handoff. | PASS |
| G10 | Native positive map T01/non-map T09 and negative cue/source/map/typed-contract suites; exact Final WAV/word map/source heads. | PASS |
| G11 | Fourteen populated Chromium captures, geometry assertions and direct per-screen inspection. | PASS |

`PR13_UI_CODE = PASS (11/11)`.

## Actual command evidence

- Required backend matrix with explicit FFmpeg path: `12 passed, 1 PytestCacheWarning` (cache write permission only).
- `scripts/check_design_contracts.py`: 12 schemas PASS.
- `scripts/validate_visual_design.py`: 10 templates, 10 scenes, 30 variants, 18 motion grammars PASS.
- `npm --prefix frontend run typecheck`: PASS.
- Browser: project/voice/assets aggregate 8/10 plus corrected database-path cases 2/2; isolated G3 screenshot 1/1; ui-redesign 2/2; G4 Player+Node 2/2; PR10 source 1/1; PR10 typography 1/1; G5 1/1.
- Renderer PR10 evidence: `LOCAL_PASS`; native B3 render/recovery/QC/export: `LOCAL_PASS`.
- Clean extracted package: `CLEAN_PACKAGE_PASS`, archive SHA `f46c971072f6a3e3da1a90e67ddfb0302c7b32980c7c84f2f9bd8059e9fa8781`.

Final exact commit SHA is necessarily recorded in the handoff response: a commit cannot contain its own SHA. Live providers, real rights and operator films remain separate from this software verdict.
