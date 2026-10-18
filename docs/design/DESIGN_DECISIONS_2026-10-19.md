# Design Decisions — 2026-10-19

## Authority and scope
This document records the user's latest decisions and **overrides earlier design-gate wording only where directly conflicting**. The original Master Design Specification and Six-Role Audit remain preserved as historical design records. This is a new repository/new product; no old Historical-Motion-Graphics-Studio code, database, or compatibility requirements are inherited.

## D-001 — English-first production (accepted)
- The intended primary language is **English**.
- ElevenLabs Forced Alignment remains the selected and mandatory alignment provider for production audio, regardless of whether Kokoro or ElevenLabs generates TTS.
- Earlier warnings regarding ElevenLabs Forced Alignment **Vietnamese support are not a V1 implementation blocker**. Do not require Vietnamese compatibility testing to accept the English-first pilot.
- Validate English audio/alignment behavior and failure paths during actual implementation/pilot. Other languages remain future scope, not silently assumed to work.

## D-002 — G-Labs implementation authority (accepted)
- Implement the G-Labs image provider adapter against the supplied **WEBHOOK_INTEGRATION.vi(1).md** API contract.
- **A live G-Labs integration test is not required as a precondition for design approval or coding the adapter**. Build against documented request/response semantics, provide offline contract/mocked tests, and design task persistence/error handling.
- Live generation, account/quota availability, actual quality, and runtime behavior remain *unverified*, rather than declared passing. When the user later tests the complete tool, capture those results then; do not block M0/M1 code-writing on a live account call.
- Runtime must still handle G-Labs failures honestly without false success.

## D-003 — Historical archival fallback (reconfirmed)
- Missing historical assets must pause at the asset-review decision point.
- User chooses **Manual Search + Upload**, or **Managed Fallback + Subsequent User Review**.
- Neither managed-fallback authorization nor an auto-created candidate equals asset approval. No silent replacement, no fabricated historical evidence.

## D-004 — Five gates (reconfirmed)
G1 Story & Research → G2 Voice and G3 Assets in parallel → G4 Storyboard → G5 Final MP4. Every gate requires explicit user approval. Selective revisions invalidate only downstream dependents.

## Precedence
Read this file *with* `MASTER_DESIGN_SPECIFICATION_V1.md` and `SIX_ROLE_DESIGN_AUDIT_V1.md`. Treat the original text about Vietnamese as a historical concern, **not** a blocking V1 gate; treat mandatory live G-Labs early testing as deferred evidence, **not** an M0/M1 coding prerequisite. All other open gates (asset provenance, meaningful visual pilot, technical QC, English alignment tests) remain.

## Status
Design direction only. No production implementation, audio provider execution, or video-pilot acceptance is asserted.
