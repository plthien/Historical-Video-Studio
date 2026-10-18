# ElevenLabs Forced Alignment Adapter · English-first V1
**Official endpoint:** POST https://api.elevenlabs.io/v1/forced-alignment (multipart file + plain text) per https://elevenlabs.io/docs/api-reference/forced-alignment/create/. **Distinct from ElevenLabs TTS adapter.**

## Interface
- Input: immutable **approved assembled final WAV**, plain exact spoken transcript, audio SHA256, transcript SHA256, expected project/revision and provider configuration.
- Output: WordTimingMap.v1 in integer audio samples with unique word_id/section_id, text, start_sample/end_sample and optional loss/anomaly; preserve original provider result for diagnostics.
- ElevenLabs Forced Alignment MUST be used for either Kokoro or ElevenLabs TTS; do not use character count, WPM or estimated speech timing to fill missing words.
- HTTP key stored only in local backend settings; not project package, browser props or logs.
- English is V1 support lane; do not block English-first development on Vietnamese language provider tests.

## Core validations
1. Validate final audio exists, decodes, has expected section order and nonzero sample count; exact transcript corresponds to approved G1 text and assembled selected attempts.
2. Align with real final WAV + text; server may return words, characters, loss. Word IDs assigned deterministically within one map by section and occurrence.
3. Check all word sample bounds and **no overlaps/non-monotonic order**; compare normalized lexical coverage of original transcript (do not assert success on partial/mismatched result). Highlight proper-name anomalies for G2 correction if needed.
4. Freeze map hash and reference final WAV hash+transcript hash; any new final audio/transcript invalidates map. A rejected/failed alignment blocks G4, but does not erase the previously approved section audio attempts.
5. Report accurate provider errors, limits and retry options. No automatic substitution to another aligner (user selected ElevenLabs specifically).

## Important API nuance
Official references may differ on maximum file size (the API endpoint reference indicates less than 1 GB; overview may mention 3 GB). Implementation must use conservative verified endpoint preflight and test actual constraints before claiming limits.

## Design-only acceptance
Typed interface + error taxonomy + fixture shape + timing invariants; actual English audio and alignment quality are Step 03 evidence.
