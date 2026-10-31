# PR #13 — Final 12-gate audit ledger (V2 implementation checkpoint)

**Design authority:** PR13_APPROVED_UI_REDESIGN_V2
**Mandatory branch:** `feat/v1-ui-mockup-parity-and-authoring-bridge`
**Base main:** `d368088dba5713b3b4b51b635f585585bd8baf9a`
**Initial independent PR head:** `6048c72af5968af5c1f0da361ff379d28b989c6b`
**This audit's source checkpoint:** `db8100fd716dfc35516ca4410a132cf2cec64418` (not a self-referential final commit).
**Exactly tested HEAD:** to be resolved by Actions `source-head.json`, not inferred from a PR title or old run.
**Verdict policy:** unsupported, queued, unavailable, not yet executed = **FAIL** for G01–G12.

## Actual source changes
- State A projects landing and State B guided Configure/ChatGPT Brief/Import with source-bound CAS, copy/download and stale brief refusal.
- Global 238px-sidebar border-box, new page gutters, responsive/workspace layout, accessibility/focus and build-SHA footer.
- Complete stage-specific layout redesign for Story G1 (section/claims), G2 (single selected section/final WAV), G3 (requirements/original review), G4 (true Player stage/inspector + schema-guided T01–T10), G5 (QC/media/authority).
- Source-authoritative G4 initial map request API/store and legacy compiler with G3 source/rights/period check. Same Story compiled draft source reauthoring refused.
- Persisted section-correction audit reason + old/new SHA in SQLite same transaction.
- Native Windows source/fingerprint bundle gate for development + packaged ZIP, fail-closed stale -SkipBootstrap, CI FFmpeg prerequisite.
- Rebased protected browser tests onto State A/B navigation (no removed gate/source assertions), added 1366/1920 screenshot captures for actual current audio/G3 original/G4 Player/G5 video inside existing source-authorized suites.

## Binary gate results

| Gate | Verdict | Current evidence / missing required proof |
|---|---|---|
| G01 | **PASS** | Verified same PR #13, mandatory branch, base main `d368088`; GitHub compare `ahead`, merge-base equals `d368088`, 0 behind, protected schema untouched, no main writes or merge |
| G02 | **FAIL** | Geometry/build-freshness source fixed and runnable tests committed, but real exact HEAD Chromium geometry, package/launcher build SHA test result not yet available |
| G03 | **FAIL** | New A/B UI and persistence tests implemented; 1366/1920 approved visual comparison not yet run |
| G04 | **FAIL** | Source inspector/narration and durable audit added; native Windows regression and human visual verification not run |
| G05 | **FAIL** | Single section + actual audio/align test rebase and viewport captures committed; source media playback execution not verified |
| G06 | **FAIL** | Real G3 rights / stored-original controls preserved and reorganized; batch/managed tests and populated screenshots not executed |
| G07 | **FAIL** | Real Remotion-first workbench and typed T01–T10 editor; actual positive Player/Node frame parity on exact HEAD unverified |
| G08 | **FAIL** | Real video-first delivery and unchanged G5 render/QC/export; final-HEAD playback and export test not executed |
| G09 | **FAIL** | Versioned brief/settings/Story PATCH + audit and negative DB tests added; exact-HEAD browser and DB test suite pending |
| G10 | **FAIL** | Map and non-map native Windows positive HTTP compile integration tests added; GDI/word map/approved-source test execution not yet reported |
| G11 | **FAIL** | New browser geometry/state spec, 14 screenshots and additional genuine populated media captures integrated into owner tests; no exact-HEAD screenshot artifacts or independent visual-review verdict |
| G12 | **FAIL** | Five native Windows CI required workflows and exact-head SHA assertions; latest-head completion/artifact uploads missing (queued at inspection) |

**Current binary score: 1/12 PASS** for verified PR ancestry only. **NOT MERGE READY.**

## Scope of evidence and outstanding work
The new 14-screen geometry suite uses actual isolated SQLite UI states and explicitly marks G2/G3/G4/G5 blocked on its fresh unapproved project. Populated source/Player/video screenshots are separately captured during the **actual existing full-flow regression fixtures**. They are not presented as real human-cleared historical rights. Independent human spatial review and positive production render proof remain mandatory.

Native Windows source-bound synthetic test proof is not real provider authentication, real source licensing or a two-topic 5–10-minute production film. The two-topic licensed-source full-length acceptance remains **NOT_RUN/BLOCKED on external inputs**, separate from required code gates.

**Execution blockers:** Windows workflows queued/uncompleted; no direct native Windows runner or authenticated production licensed source/provider media in this assistant's environment; end-to-end browser replay and manual visual appraisal cannot be fabricated. Legacy suites must pass after React redesign before merge.

## Native Windows commands for operator repeat
```powershell
git switch feat/v1-ui-mockup-parity-and-authoring-bridge
git rev-parse HEAD
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/verify-environment.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/verify-frontend-build.ps1
.\.venv\Scripts\python.exe -m pytest -q tests/backend/test_post_pr12_authoring_story.py tests/backend/test_post_pr12_g4_authoring.py tests/backend/test_pr13_g4_positive.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
$env:HVS_PARITY_PRODUCTION='1'
npm --prefix frontend run test:e2e -- tests/e2e/ui-redesign.spec.ts
```
The above commands are test **instructions**, not execution evidence. Consult the exact HEAD Windows workflows, screenshot artifacts, Playback/Node frame hashes, QC and approval records before upgrading any FAIL.
