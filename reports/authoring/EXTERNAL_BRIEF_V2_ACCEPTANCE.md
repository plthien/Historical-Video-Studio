# External Brief V2 Acceptance Ledger

Task owner: A1-06, with the existing B1/G4 timing boundary exercised as regression evidence. Branch: `feat/v1-ui-mockup-parity-and-authoring-bridge`. Verified starting HEAD: `75d9ded8c081fa585198a8c3895a0e936a654569`.

This ledger is finalized from commands executed on native Windows. The exact final commit is recorded in the handoff because a commit cannot contain its own SHA. Offline/mock status is separate from live provider and operator acceptance.

| Gate | Status | Evidence |
|---|---|---|
| E01 Correct PR/scope | PASS | Existing branch and starting HEAD verified; no PR/merge/LLM API; `git diff -- contracts/schema/StoryPackage.v1.schema.json contracts/registries/layouts.v1.json` is empty. |
| E02 Deterministic V2 | PASS | Shared `BRIEF_VERSION`; repeated persisted-settings API responses are identical; saved changes rebuild; unsaved mismatch remains refused. |
| E03 Exact schema | PASS | Test extracts the appendix and compares the parsed value exactly with canonical disk JSON; canonical long-form V1 still parses/imports. |
| E04 Narration | PASS | 5/7/10 targets, hook/arc/escalation/synthesis, Final WAV authority, verbatim goals, topic neutrality, and <=8,000 policy-character budget tested. |
| E05 Templates | PASS | Guide keyset equals canonical T01-T10 registry; prompt requires `preferred_template`; missing reaches existing `LAYOUT_VARIANT_UNKNOWN`, null remains schema-invalid. |
| E06 Cues | PASS | Controlled synthetic maps prove occurrence 0/1 plus `CUE_MISSING`, `CUE_AMBIGUOUS`, `CUE_OCCURRENCE_INVALID`, `CUE_SECTION_MISMATCH`, `CUE_RANGE_INVALID`, and `CUE_OVERLAP`. |
| E07 Source discipline | PASS | Prompt fixes external status to UNVERIFIED, permits empty leads, forbids fabricated browsing/rights/quotes/maps, and documents the frozen-status/G4 mismatch without bypass. |
| E08 UI handshake | PASS | Real Chromium + isolated SQLite/backend passed at 1366x768 and 1920x1080: V2 preview/copy/download, stale lock, rebuild, unchanged import and G1 navigation. Windows clipboard CRLF was normalized only when comparing text; downloaded bytes equalled preview exactly. |
| E09 Contract/G4 | PASS | With FFmpeg/ffprobe 9.0.1 explicitly available to the native process, both positive HTTP -> SQLite -> source-bound compiler paths pass: map T01 and non-map T09, using current G1/G2/G3 heads, Final WAV and WordTimingMap. No validator or production compiler was weakened. |
| E10 Handoff | PASS | Generated sample is byte-compared with the generator; commands/results, blockers, final handoff SHA, and separate global status are recorded. |

## Required truth labels

- `EXTERNAL_MODEL_QUALITY_NOT_RUN`: no external ChatGPT draft or manual Black Death editorial assessment was performed by the app tests.
- `LIVE_RIGHTS_ACCEPTANCE_BLOCKED`: no operator-supplied historical media/right approvals were exercised.
- G1-G5 operator approval and full PR #13 global acceptance remain separate from these ten targeted gates.

## Command evidence

Native Windows commands executed from the repository root:

- `python -m pytest -q tests/backend/test_external_story_brief_v2.py tests/backend/test_post_pr12_authoring_story.py` -> exit 0, `6 passed`.
- `python -m pytest -q tests/backend/test_post_pr12_g4_authoring.py` -> exit 0, `3 passed`.
- Combined required backend/G4 command with the verified FFmpeg WinGet bin prepended to the exact process PATH -> exit 0, `12 passed, 1 warning` (the warning is only denied pytest cache creation). The prior missing-PATH failure remains useful baseline evidence, not the final result.
- `python scripts/check_design_contracts.py` -> exit 0, `12 schema(s)` PASS.
- `python scripts/validate_visual_design.py` -> exit 0, 10 typed templates/10 scenes/30 variants PASS (existing output reports 18 motion grammars; this task did not alter the registry).
- `npm --prefix frontend run typecheck` -> exit 0.
- `npm --prefix frontend run build` -> exit 0; Vite chunk-size warning only.
- Isolated real-browser `npm --prefix frontend run test:e2e -- ui-redesign.spec.ts` on API 8012/UI 5174 -> exit 0, `2 passed`. Port 8000 was already occupied, so the checked test harness now accepts validated isolated port overrides. Known spawned child servers required explicit teardown after the tests printed `ok`; final command exit was 0.

No workflow run URL exists because no push or new CI run was requested. The prompt sample is `PROMPT_SAMPLE_ONLY_BLACK_DEATH_7_MIN_V2.md`; it is not an external-model StoryPackage.

## Verdict and separate PR status

`EXTERNAL_BRIEF_V2 = PASS (10/10)`. E09 is now backed by executable native positive G4 evidence rather than a ledger-only promotion.

The current independent global policy is recorded in `reports/pr13-v3/PR13_FINAL_11_GATE_AUDIT.md`: G01-G11 only, with G12 retired and not scored. External-model editorial quality, real historical source/rights acceptance, live providers and real operator films remain unverified or blocked as labelled above; controlled synthetic approval fixtures are not real rights.
