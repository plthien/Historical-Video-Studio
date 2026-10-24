# PR #10 — V4 bounded execution report (unverified gates remain FAIL)

- Plan: `CODEX_PR10_FINAL_SIX_GATE_REPAIR_PLAN_V4_8020079(1).md`; PLAN_READABLE.
- PR: https://github.com/plthien/Historical-Video-Studio/pull/10
- Branch: `feat/b2-motion-storyboard-player-parity`
- Starting SHA: `8020079b0fa50fffe5cddedc9e0e00d3c42b7a8c`
- Baseline main SHA: `822643bce56709e6c80463fb39b8e6b2461135eb`
- Environment: GitHub connector and Linux container only. Native Windows Remotion Chromium, Windows GDI, SQLite/browser integration and local repo execution **NOT_RUN** here; a GitHub Actions trigger alone is not acceptance evidence.
- Scope: B2-04/B2-05/B2-06; same PR/branch. No main push, merge, new PR or B3.

## Code change
`frontend/src/workspaces/Storyboard/StoryboardStudio.tsx`: preserve existing stage operation edit behavior, allow selecting any authored staging step within an existing beat, reset step when the beat or scene changes, retain exact unchanged staging elements. This is not a claim that all G4 staging forms/operations are supported; the compiler continues to reject unsupported staging.

## Source findings
- `renderer/scripts/b2-motion.ts` has 17 partial phase proofs and 2 blocked dependencies at baseline; no independent 19/19 semantic acceptance is demonstrated by this round.
- `backend/app/director/motion.py` validates the final historical number, not independent intermediate historical values.
- `backend/app/director/compiler.py` sets `transition_out.duration_frames=0`; `renderer/remotion/Primitives.tsx` treats mask-transition as a one-surface reveal.
- `backend/app/api/storyboard.py` explicitly rejects changed `approved_asset_id`; a live second G3-approved alternative has not been demonstrated.
- Camera motion scalar parameters do not yet drive the compiled camera track; camera scalar editing remains intentionally blocked rather than persisted inertly.
- See `docs/step01-02/pr10-contract-dependency-ledger.json` for D01/D02/D03 source-only findings.

## Gate status — no conditional PASS

| Gate | Latest justified status |
|---|---|
| G01 | PASS at audited baseline; same PR/branch retained |
| G02 | NOT_REVERIFIED (previously PASS) |
| G03 | FAIL: 19/19 semantic oracle missing |
| G04 | FAIL: camera, geometry, transitions and counterfactual phases incomplete |
| G05 | FAIL: full typography/font/polygon proof missing |
| G06 | FAIL: camera/alternative asset editing incomplete; only staging step selection added |
| G07 | NOT_REVERIFIED (previously PASS) |
| G08 | FAIL: browser-visible 409/422/424 complete suite NOT_RUN |
| G09 | NOT_REVERIFIED (previously PASS) |
| G10 | NOT_REVERIFIED (previously PASS) |
| G11 | NOT_REVERIFIED (previously PASS) |
| G12 | FAIL UNTIL VERIFIED: exact final HEAD native Windows A1+B2 CI not fully verified |

## Test and artifact limitations
Native Windows npm installs/typechecks, all renderer owners, SQLite, Chromium, FFprobe, browser Player/Node parity, negative regressions and 61-scene timings were **NOT_RUN** from this execution environment. Do not treat the source-only dependency ledger or this report as semantic/pixel/runtime evidence. Missing `pr10-motion-semantic-19-ledger.json`, `pr10-typography-clip-ledger.json`, `pr10-g4-revision-evidence.json`, and `pr10-browser-workflows.json` have not been fabricated.

**Strict verdict: FAIL — NOT MERGE READY.** A historical 6/12 PASS baseline cannot be automatically carried as exact-final-HEAD verification.
