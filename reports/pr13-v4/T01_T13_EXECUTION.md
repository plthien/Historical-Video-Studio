# PR13 V4 T01–T13 native Windows execution

Execution date: 2026-10-30 (Asia/Saigon). Branch `feat/v1-ui-mockup-parity-and-authoring-bridge`; initial local/remote head `64ccc87efac9e60b2fd334ed51f102a92745f02f`; base/merge-base `d368088dba5713b3b4b51b635f585585bd8baf9a`. Code execution source after repair: `8fe9050ba9e32eaaf27e380c4da7b55e13012fad`.

Frozen identities remained unchanged:

- StoryPackage.v1: `a209646795794042fe4acb10404529288315d47023e2668012af4ff3cbd5d6da`
- layouts.v1: `850df2df31b19f4fc5c0751f1cab9d39927743a9471b30d8b22dda9231f69e97`
- motion-presets.v1: `17e93bbbdefd688863f9db4e174c2b53d50c32dd20aead6554e48fd0e3772f2d`

| ID | Actual command/evidence | Result |
|---|---|---|
| T01 | `git rev-parse`, remote head, merge-base, contract hashes and bounded diff | PASS |
| T02 | `verify-frontend-build.ps1`; `test-frontend-build-cross-shell.ps1`; native `start-studio.ps1 -Smoke -SkipBootstrap` | PASS. PS7 7.6.9/PS5.1 5.1 share input `903d7d…` and bundle `c51709…`; all tamper cases refused; launcher ready and stopped cleanly. First sandboxed cross-shell attempt could not start AppX PowerShell; exact rerun outside sandbox passed. |
| T03 | `HVS_PARITY_PRODUCTION=1`, UI 5174, `ui-redesign.spec.ts` | PASS, 3 tests: two full viewports plus outage negative. Actual browser-origin health/projects 200 and project create 201 on API 8010; revisions reopen at 3. |
| T04 | Production API override 8012 `--list`; route-aborted canonical POST negative | PASS: explicit `PRODUCTION_PREVIEW_API_PORT_MISMATCH` exit 1 before browser; aborted POST showed `Failed to fetch`, stayed on project home, created no row/gate. |
| T05 | Same production run, Project A/B at 1366x768 and 1920x1080 | PASS |
| T06 | Same run: V2 preview/copy/download/stale/rebuild, malformed JSON, canonical import, G1 and reopen | PASS |
| T07 | `backend.tools.clean_package_smoke`; then two phase-B evidence tests | PASS: `CLEAN_PACKAGE_PASS`; explicit occupied-port, missing-FFmpeg and `PASS_BUILD_MISSING_NO_DATA_MUTATION`; consumer/mutations 2 passed. |
| T08 | Foundation/authoring/voice owner group | PASS: 51 passed; additional External Brief/G4 matrix 11 passed. |
| T09 | Assets/Phase A owner group; G2/G3 Chromium | PASS: 39 passed; browser 8 passed, focused recapture 2 passed. |
| T10 | G4 authoring/positive owners and `tests/visual/test_compiler.py` | PASS within 10-test protected matrix and 88-test G4/G5/Phase-B group; map T01 and non-map T09 both pass. |
| T11 | Player/Node parity, renderer `typecheck`/`test:repair`, B3 fixture and Delivery Chromium | PASS: parity/browser 4 passed; repair 28 guards + 24 frames; B3 `LOCAL_PASS`; Delivery 1 passed. |
| T12 | `reports/pr13-v4/screenshots` plus direct image inspection | PASS: exactly 14 current captures; hashes in `SCREENSHOT_SHA256.txt`; detailed findings in `VISUAL_REVIEW_LEDGER.md`. A dirty reused G4 fixture initially failed at revision-dependent save; fresh fixture rerun passed without assertion changes. |
| T13 | Post-code-commit typecheck, production build and production browser replay | PASS: source `8fe9050…`, input `903d7d…`, bundle `c51709…`; `ui-redesign.spec.ts` 3 passed in 16.9s. Evidence-only commit SHA is supplied in handoff. |

Additional validators: design contracts 12 schemas PASS; visual contracts 10 templates, 10 scenes, 30 variants and 18 motion grammars PASS; renderer typecheck PASS. Python owner totals were 51 + 39 + 88 + 11; pytest cache warnings were non-behavioral write-permission warnings.

The independently reproduced pre-repair production run failed both viewports after Create Project because the compiled UI called an unrelated stale server on 8010 while Playwright started its test backend on 8012/legacy 8000. That RED evidence is preserved conceptually here and in the V4 brief; it was not relabelled as an application selector failure.
