# External Story Brief V3

`HVS-EXTERNAL-STORY-BRIEF.v3` is the current deterministic, project-bound prompt for manual use with external ChatGPT. Historical Video Studio does not call an LLM or browse. The app still imports exactly one canonical `StoryPackage.v1` JSON object, and import never grants G1 approval.

## Authority and deterministic substitutions

The sole V3 policy authority is `backend/app/projects/prompts/external_story_brief_v3.md`. Its checked-in UTF-8/LF identity is SHA-256 `e7234d15cc00a1f8b47196e7a7190296218ff9654bff4beb9818826c6848e494`, 24,253 bytes and 135 LF lines. The backend replaces exactly three single-use markers in one regex pass:

- operator metadata serialized as sorted, indented UTF-8 JSON;
- the 150–170 WPM provisional runtime guidance;
- the parsed canonical `StoryPackage.v1` schema serialized as sorted, indented UTF-8 JSON.

Inserted operator text is never scanned again, so literal marker-looking text remains data. The T01–T10 registry is checked before every build. Missing/duplicate markers, registry drift, invalid project/input or a runtime outside 5–10 integer minutes fails closed.

## Operator workflow

1. Configure and save the local project's topic, audience, runtime and editorial goals.
2. Build V3, then copy or download the exact prompt.
3. Use it in an external ChatGPT conversation. Do not use an in-app or runtime LLM API.
4. Return one complete raw UTF-8 `StoryPackage.v1` JSON object and import it as a candidate.
5. Perform G1 claim/editorial review. G2 Final WAV/alignment, G3 source/rights review, G4 typed compilation and G5 export remain separate approvals.

## External-model pilot checklist

Record the exact generated prompt SHA, model/date if known, complete returned JSON, truncation status, editorial narration review, evidence leads, schema/semantic import, cue preflight and separate G1–G4 dependencies. Never synthesize a returned story merely to mark the pilot complete.

Software tests prove deterministic prompt construction, packaging and import workflow only. They do not prove external-model compliance, historical accuracy, creative quality, licensed rights, live providers or completed operator films. When no authorized external conversation is run, report `EXTERNAL_MODEL_EDITORIAL_QUALITY=NOT_RUN`.
