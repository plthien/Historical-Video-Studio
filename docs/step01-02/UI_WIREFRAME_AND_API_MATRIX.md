# UI wireflow + API-to-control mapping (design freeze)
**Viewable design mockup:** ../../ui/mockups/index.html (open in browser; static, no providers connected). Mock interaction is not production data nor real Remotion rendering.

## Screens, states and action routes
| Workspace | Primary buttons/controls | Proposed API owner / outcome | Gate |
|---|---|---|---|
| Project & external ChatGPT | build/copy authoring brief, import JSON, settings | POST /projects, POST /projects/{project_id}/story/import; schema and crossrefs | G1 draft |
| Story review | claim/source inspector, corrections, Approve | POST /projects/{project_id}/gates/G1/decision | G1 |
| Voice Studio | select Kokoro/ElevenLabs, section attempt, correct, Approve Voice | POST /projects/{project_id}/voice/generate, GET /voice/attempts, POST /gates/G2/decision | G2 |
| Historical Assets | discover, filter, resolve manual/managed, upload, approve candidate, approve gate | POST /assets/discover, /assets/{requirement_id}/resolve, /upload, /approve, POST /gates/G3/decision | G3 |
| Motion Storyboard | inspect Player, scene list, change approved asset, crop/layout/motion, create draft, Approve | POST /storyboard/revisions, /storyboard/compile, POST /gates/G4/decision | G4 |
| Render & Delivery | render, status, cancel, QC report, final human approval | POST /render-jobs, GET /jobs/{id}, POST /jobs/{id}/cancel, POST /gates/G5/decision | G5 |

UI checks that **do not imply backend authority**:
- Mock fallback visual choice does not actually search the network or upload an image. Production upload needs source URL, rights statement and file; candidate approval is separate from gate approval.
- Mock TTS is not real audio, and simulated alignment complete is not evidence of ElevenLabs timing; actual implementation must await provider QC.
- Motion picture in prototype is a CSS/SVG conceptual still only. Production storyboard must use genuine @remotion/player running shared HistoryComposition with actual approved CompiledTimeline.
- Mock render produces no video. Production final approval must pin actual MP4 + QC + credits SHA.
- Copy Prompt may be blocked by browser clipboard permissions; production UI should provide select/copy fallback.

## Navigation wireflow
Project → Story G1 → Voice G2 & Assets G3 (parallel) → post-G2 alignment QA → Storyboard G4 → Render → G5. Each gate header displays state, current candidate revision and one next action. BLOCKED gate shows reason and selective repair path; STALE gate shows cause and linked snapshot. No global “approve all” or hidden automatic fallback. Batch candidate approval allowed only with per-item evidence inspection and human confirmation.

## Essential dialogs
**Missing archive modal:** subject, expected era, exactness, why match failed, required status; exactly Option 1 Manual Search+Upload or Option 2 Managed Fallback+review. If managed chosen, show tiers (related sourced context, document/map, approved schematic, G-Labs AI illustration), each with disclosure and new candidate review. “Generate candidate” is never “Approve”.
**G2 approve confirmation:** selected section attempts/identity, playback status, exact script hash, next tasks WAV assembly+ElevenLabs alignment. No manual alignment button.
**G4 edit dialog:** G3-approved asset picker only; preview, color contrast, duration, cue word ID, layout variant, bounded motion params; warn when factual text needs G1.
**G5 sign-off:** MP4 version/hash, QC pass/fail, source attribution completeness, watched/listened acknowledgement, exact version approved.

## UX accessibility
Minimum usable width 1366px; all actionable state conveyed in text and keyboard focus; no empty placeholders advertised as functional. Long asset lists virtualized in real application. Each asynchronous action visually enters pending on click and returns a stable job ID. Empty list has concrete suggestions, not a hidden automatic substitute.

## Evidence needed to call UI implementation PASS
Screenshots of each state; browser automation for missing asset two-option authorization, no silent fallback, double-click prevention, Gate 2 one approval→alignment, downstream staleness on edits, G4/G5 refusal when upstream unapproved, and real preview/export parity. Design mockup does not satisfy these runtime tests.
