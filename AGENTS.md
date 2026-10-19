# Codex Instructions — Historical Video Studio (Windows-only)

Read this file **before** writing or reviewing code. Read `docs/engineering/CODING_RULES.md` and use `.agents/skills/historical-video-studio/SKILL.md` for implementation tasks. Contract authority: `docs/step01-02/05_IMPLEMENTATION_PLAN.md` + `docs/step01-02/IMPLEMENTATION_TASK_MATRIX.md`, repaired V1.1 visual contracts, schemas, API core+extension and official G-Labs reference.

## Product boundaries (non-negotiable)
- Single-user **Windows local** desktop workflow; Python 3.12, Node 22, Remotion, SQLite, FFmpeg. Windows CI/tests only. Do not add Ubuntu CI, containers, hosted orchestration, accounts/RBAC or unsupported old-tool migration.
- Implement **one complete V1**. No throwaway pilot, alternative app, independent render engine, runtime LLM API or per-video JSX generation.
- One external ChatGPT StoryPackage import; G1 Story → parallel G2 Voice/G3 Assets → final WAV + ElevenLabs alignment automatically after G2 → G4 Storyboard → render/QC → G5 Final Export.
- Never mark archive candidate as approved, infer historical geography from modern maps, silently choose AI fallback, confuse editorial connectors with geographic routes, or change G1 facts through G4 visual editing.
- Preserve and use the typed 10-template visual grammar, 30 variants, 19 motion presets and SHA-traceable renderer inputs. The original `contracts/providers/reference/WEBHOOK_INTEGRATION.vi(1).md` is authoritative for G-Labs.

## Work execution contract
1. Identify exactly one task ID from `docs/step01-02/IMPLEMENTATION_TASK_MATRIX.md`; verify dependencies/owner module and phase entry state. Respect the user's requested phase/scope.
2. Inspect existing implementation and closest test first. Fix within the owning module; prefer deletion/refactor over parallel wrappers. Avoid speculation about later workstreams.
3. Add only narrowly targeted behavioral tests: demonstrate an actual invariant or a pre-fix failing regression. No tests of file length, Markdown keywords, test counters, implementation details, or mocks alone.
4. Run Windows commands **listed for the task**. Offline/mock results are not evidence of successful live provider, real historical rights, or video render. If credentials/media unavailable, use explicit BLOCKED/SKIPPED and show exact dependency; don't fake PASS.
5. Self-review: correctness, leakage between gates, chronology/evidence, user-visible UI effects, duplicate logic, LOC/test growth, phase boundary. Provide git diff --stat and actual changed behavior, test evidence and risks.
6. Do not open multiple repair PRs for the same phase. Prefer existing implementation PR; no merge or push to `main` without explicit user authorization during implementation.

## Change hygiene
- Contracts and runtime APIs remain aligned; never change canonical schemas to silence a failing test. Update only when requirements authorize semantic changes.
- Keep a single source of truth for field validation, map transforms, preset definitions, source metadata mapping and revision invalidation.
- No mass test generation, snapshot spam, large fixtures copied per test, empty component scaffolds, dependency bloat, duplicated service abstractions or opportunistic unrelated cleanup.
- Review task ownership: defects in current phase gate must be fixed in that phase; later-phase non-blockers are written as a bounded issue for their owner task, **not** implemented early.
- Final response must separate code/test status from live provider checks and operator G1–G5 approval; include exact commit SHA and unverified items.
