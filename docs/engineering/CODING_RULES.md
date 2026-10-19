# Coding & Test Rules — Lean Windows Full-Flow V1

**Binding for Codex implementations and repairs.** Favor the simplest code that fulfills the accepted task and produces an observable user outcome. Source: product/contract authority in Step01–02; task execution matrix defines module ownership and acceptance.

## A. Python / TypeScript / Remotion implementation
- Python 3.12 FastAPI: typed request/response models from shared schema, one transaction per revision/gate mutation, optimistic concurrency via expected_revision, immutable approval/asset lineage. SQLite for this one operator; use compact, restart-safe local job queue. No premature repository/service interfaces layered three times.
- TypeScript React: typed API clients, explicit disabled/loading/error/result state. Do not create controls without backend behavior. Reuse one component for repeated interactions; do not flatten six workspaces into giant files.
- Renderer: ONE `HistoryComposition` shared by Player and Node render. Reuse registries instead of per-template hardcoded routing. All transformations per frame deterministic; no random/date/network side effects. Preserve original assets; crop/mask produces controlled derivatives only.
- SourceAdapter and TTSAdapter are justified boundary abstractions because providers genuinely differ; avoid new abstraction when there is only a single concrete owner with no actual differing implementations.
- Avoid old tool compatibility, deprecated code paths, generic frameworks, complex auth/security for one Windows-local operator, premature performance infrastructure, shared globals and hidden fallback.

## B. Change-first repair (no code accretion)
1. Reproduce or describe the failing behavior and the existing owner.
2. Inspect existing caller, handler, validator and nearest behavioral test.
3. Remove/change smallest owning code path. **Do not** append sibling handlers/adapters, clone a service, or retain dead compatibility just to pass CI.
4. Reuse/extend closest test; add a new test only when it proves a different meaningful failure mode.
5. Remove obsolete scaffolding, dead branches, duplicated tests and stale comments touched by change.
6. Confirm external effects (state, file, visual/audio output) rather than only return values or mock invocation counts.

## C. Evidence-first test selection
Every test must answer: **which contract/user behavior can regress? what input triggers it? what wrong output/side-effect would the test reject?** If no clear answer, remove/refactor it.
- Contract/parser changes: one valid representative and one meaningful negative per **distinct invariant**, ideally table-driven; no testing names of Markdown files.
- API/gates: persisted status, conflict/race, idempotency, selective invalidation, blocked transitions; use a real temporary SQLite DB instead of mocked calls where cheap.
- Voice: verify actual WAV samples, final audio SHA, align word offsets and retry preservation; provider request/error mapping tests use mocked HTTP only at network boundary, and live credential tests are separate.
- Archive/G-Labs: fake server for protocol including failure/status/cancel; never count this as licensed-source/real generation PASS.
- Compiler: assert actual scene/layer/motion/frame output and provenance, not just schema validity; wrong-era map/unsupported preset must not reach renderer.
- Remotion: deterministic frame artifacts/visual diff at meaningful enter, middle, hold and exit; after that, one full render/player parity check. Do not multiply screenshot snapshots for every minor change.
- End-to-end: full 5–10 minute English output and second unrelated historical topic on same engine; do not repeat every unit assertion at E2E.

## D. Explicit anti-bloat controls
- New production abstraction: include one sentence naming the concrete duplication/provider variation it removes now. If none, do not introduce it.
- New test: link it to task ID + failure mode, point to closest existing test considered; justify independent value.
- A bugfix adding hundreds of lines, duplicated storage/payload adapters, or broad fixtures triggers mandatory simplification/self-review **before** marking PASS, not an automatic hard line-count failure.
- Prefer parameterization and small meaningful fixtures over copies. Refactor repeated code/tests only for proven repetition; no utility factory solely to reduce LOC.
- Ignore superficial percentage coverage/test count as success KPI. **Behavioral acceptance and real rendered artifacts** are the criterion.
- After each task log `git diff --stat`, production +/− LOC, test +/− LOC, duplicated code removed, new dependencies and why, tests run, evidence and known unverified work. Don't justify bloat with a green CI badge.

## E. Scope & review control
- Work strictly on task IDs and dependencies in `docs/step01-02/IMPLEMENTATION_TASK_MATRIX.md`. Fix a current-phase blocker, classify a later-phase unrelated issue as deferred with owner ID. No extra “audit round” to rediscover or implement future-phase work.
- Freeze a phase only when its exact checklist passes at a named commit. Fixing after a freeze requires an actual regression or integration-dependent defect with reproducible evidence. Cosmetic/code-style preferences do not reopen accepted phase.
- No fake PASS if provider credentials unavailable, license unverified, manual G1–G5 approvals missing or film output absent. Use PASS / FAIL / BLOCKED / NOT RUN separately.
