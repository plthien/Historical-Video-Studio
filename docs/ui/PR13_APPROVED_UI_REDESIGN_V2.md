# PR #13 — Approved Production UI Redesign V2
Status: APPROVED VISUAL / PRODUCT LAYOUT AUTHORITY · 2026-10-28
Design version: PR13_APPROVED_UI_REDESIGN_V2
Baseline: PR #13 @ 6048c72af5968af5c1f0da361ff379d28b989c6b

## Authority and non-goals
This document supersedes **only the appearance and interaction hierarchy** of the historical `ui/mockups/index.html`. The mock remains unchanged and is not a pixel-identical acceptance target. Frozen StoryPackage and VisualBlueprint schema, source evidence, G1–G5 human approvals, G2/G3 concurrency, G4 compiled identities and G5 audiovisual hashes retain prior full authority. No LLM API, fake preview, silently approved assets or hosted workflow.

## Tokens and geometry
Charcoal canvas #161a1d, sidebar #1e2326, surface #22272b, raised #2b3238, deep input #171c20, separators #3a4249, readable white #f2efe8, secondary #aeb7bc, sparse primary gold #e3ba65. Space scale: 4, 8, 12, 16, 24, 32 px; 10–14px radii; 40–44px controls. All elements border-box. 238px final sidebar; main track minmax(0,1fr); centered inner content max 1600px with safe 24px or more gutters. At 1366×768 and 1920×1080: no document overflow; 16px minimum right-edge control clearance; no cropped or overlapping buttons. Below 1100px columns collapse; navigation remains reachable.

## State A — Projects landing, no selection
Main heading **Projects**, concise Windows-local subtitle. Balanced **New Project** and **Recent Projects** cards. New title and topic fields, fixed V1 output profile, single gold Create Project primary action; authoring settings saved only when backend acknowledges them. Recents are genuine GET /projects rows, display titles and revisions, individual Open controls. Empty state explains first creation. ID lookup tucked in details. **NO** gate strip, disabled authoring, import wall or misleading Complete CTA. Functional states: loading list, list failure, create pending, create validation, create success.

## State B — selected project
Header: readable title, secondary project ID + revision, source-accurate stage and next action. Project tab is a three-step guided flow: 01 Configure → 02 ChatGPT Brief → 03 Import StoryPackage. Main task ~60% + context/status panel ~40%, with one primary CTA per step. Configure accepts topic, audience, five-to-ten-minute duration and editorial goals; fixed English / HistoryEditorialPaper.v1 / 1920×1080 / 30fps. Save settings via CAS; persisted readback is the only saved indicator. Changed inputs mark existing brief OUTDATED; copying or downloading an outdated brief is blocked. Build external-only, deterministic, complete-schema prompt; copy with selection fallback and download. Import file/paste performs JSON parsing and authoritative backend validation, surfaces path/remediation; on success show candidate SHA/revision and real Story G1 navigation. Reopening a project reloads persisted settings, project-bound identity and state. Never confuse story title and authoring topic.

## Six workspace composition
| Workspace | Primary region | Secondary region | Critical real behavior |
|---|---|---|---|
| 01 Project & ChatGPT | Two cards (A) or stepper form (B) | Recents (A) or source/current gate (B) | Create/open/CAS/brief/import |
| 02 Story G1 | Section rail + readable narration | Claim/evidence list + explicit review/gate decision | Correct only bounded source; invalidation |
| 03 Voice G2 | Section selector + current playable audio/editor | Final WAV, playback and ElevenLabs alignment status; history expandable | Section attempts/correction/restore/G2 |
| 04 Sources G3 | Requirement board, source thumbnails and rights | Missing manual/managed resolution, review staging/approval | Two explicit paths, no automatic fallback |
| 05 Storyboard G4 | Scene rail + large real 16:9 Remotion stage/timeline | Inspector + typed authoring precompile drawer | No fake Player; exact bounded source edits |
| 06 Delivery G5 | Actual video/media review + job/QC progress | Human review/credits/export panel | No export without true G5 authority |

## State contract and CTA map
No project → Create/Open. Project without saved settings → Configure/Save. Settings saved → Build external brief. Brief current → Import JSON. Story G1 draft/blocked → Review claims and evidence, not Approve. G1 approved → Voice G2 and Assets G3 independently. Alignment stale/failed → inspect/retry exact final WAV. Missing G3 original → choose Manual or Managed, inspect candidate; no autoapprove. G2/G3 approved → explicit per-setup typed G4 authoring / real compile. G4 draft → inspect exact Player and prepare/approve; stale returns to source owner. G4 approved → Render/QC; G5 ready → watch/listen/credit review and explicit decision; approved G5 → immutable export. Pending shows spinner/disabled control; errors show code/route/remedy; approval states derive exclusively from the server.

## Accessibility and validation
Semantic header/main/nav/sections; descriptive labels, focus-visible high-contrast outlines, announce job/error transitions, no click-only-only workflows. Minimum 40px hit area, source URLs distinguishable, long IDs wrap, overflow contained within ledger areas not page. Use stable browser snapshots at 1366×768 and 1920×1080 for State A, State B and each real populated workspace. 14+ sets, measurement ledger and independently checked hierarchy required for visual PASS; a PNG diff or synthetic fixture alone is NOT PASS.

## Deliberate departures from historical prototype
New empty-project landing, guided three-step project workflow, media-first G4/G5, contextual source panels, real disabled/review/staleness truth and actual service calls replace simulated mock buttons. The historic mockup is preserved for reference and must never be edited to manufacture parity.
