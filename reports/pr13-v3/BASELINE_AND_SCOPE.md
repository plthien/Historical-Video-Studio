# PR13 V3 baseline and scope

Plan: `CODEX_PR13_REMAINING_REPAIR_NO_G12_11_GATE_V3_5BFD562.md` (`PLAN_READABLE`).

- Repository: `plthien/Historical-Video-Studio`; existing PR #13 only.
- Mandatory branch: `feat/v1-ui-mockup-parity-and-authoring-bridge`.
- Initial local and remote PR head: `5bfd5623dbc82f010fa4292a2e8e4545c0fb1ea5` (`HEAD_VERIFIED`).
- Merge base and `origin/main`: `d368088dba5713b3b4b51b635f585585bd8baf9a`.
- Initial worktree: clean. No new branch, PR, merge, workflow edit, schema edit, or push to `main`.
- Policy: `G12=RETIRED_NOT_COUNTED`; the current global denominator is exactly 11 (G01-G11). GitHub Actions is not an implicit dependency.

## Native environment

- Windows PowerShell 5.1.26100.9711; PowerShell 7.6.9.
- Python 3.12.10; Node 22.14.0; npm 11.21.0.
- FFmpeg/ffprobe 9.0.1 essentials build, from the explicit WinGet package `Gyan.FFmpeg.Essentials` bin directory.
- Chromium: Playwright 1.56.0; Remotion Chrome Headless Shell downloaded by the pinned Remotion 4.0.524 toolchain.

## Baseline reproduction and bounded owners

| Finding | Initial reproduction | Owner/task boundary |
|---|---|---|
| F01 | Same bundle passed PS7 but failed PS5.1 with `FRONTEND_BUNDLE_STALE`; diagnostics showed culture-dependent source ordering changed `input_sha256`. | A1-01 Windows launcher/build identity |
| F02 | Clean package smoke stopped at `PACKAGE_CORRUPT_RUNTIME_NEGATIVE_MISSING`; the corrupt package was safely refused earlier as `FRONTEND_BUNDLE_STALE / BUILD_MISSING`. | B3-05 clean package/runtime refusal |
| F03 | Numbered nav accessible names and closed exact-ID disclosure caused browser regressions; reload also exposed a session-restore race. | A1-06 shared UI navigation; B2/PR10 browser plumbing only |
| F04 | Positive map T01/non-map T09 failed as `VOICE_FFMPEG_FAILED` when the exact process lacked FFmpeg in PATH. | B1/B2 G4 compiler; no validator change |
| F05 | Prior ledger had blocked downstream screenshots and no independent visual review. | G03-G11 browser/visual evidence |
| F06 | No actual external ChatGPT Black Death StoryPackage was supplied. | A1-06 quality handoff; `NOT_RUN`, separate from E01-E10 |

The frozen `StoryPackage.v1`, typed template/motion registries, approval contracts G1-G5, source/rights semantics, and approved PR13 redesign are unchanged.
